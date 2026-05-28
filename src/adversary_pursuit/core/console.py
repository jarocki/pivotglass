"""APConsole — cmd2-based REPL for Adversary Pursuit.

Metasploit-style interactive console wiring together ConfigManager,
PluginManager, and WorkspaceManager. Uses Rich for formatted output
rendered through cmd2's stdout channel.

@decision DEC-CONSOLE-001
@title cmd2.Cmd base with Rich Console(file=StringIO) for formatted output
@status accepted
@rationale cmd2 does not have a native Cmd2BaseConsole (confirmed in Issue #1 spike).
           Rich output is captured by constructing Console(file=self.stdout) so that
           table/panel rendering flows through cmd2's existing stdout redirect mechanism.
           For testing, _make_rich_console() creates a StringIO-backed Console that
           tests can inspect directly. This pattern was validated in test_cmd2_rich_spike.py.

@decision DEC-CONSOLE-002
@title asyncio.run() bridge for async hunt() in sync cmd2 handlers
@status accepted
@rationale Module.hunt() is async (DEC-MODULE-001: prevents expensive refactor when
           the asyncio event bus arrives in Phase 4). cmd2 command handlers are
           synchronous. asyncio.run() is the correct one-liner bridge for this pattern
           in Python 3.12+. An event loop is not kept alive between commands because
           cmd2 does not run an async loop itself.

@decision DEC-CONSOLE-003
@title Workspace auto-initialized to 'default' on first access
@status accepted
@rationale WorkspaceManager._ensure_active() already handles auto-creation of the
           default workspace. The console calls workspace_mgr.list_workspaces() (safe
           without active workspace) and delegates lifecycle ops to WorkspaceManager.
           This means the console does not need to explicitly create 'default' at
           __init__ time — the workspace is created lazily on first data operation.

@decision DEC-CONSOLE-004
@title ModeManager consulted for prompt prefix, run messages, and score celebration
@status accepted
@rationale APConsole holds a single ModeManager instance. The prompt is rebuilt on
           every mode switch (do_mode) and on module load/unload (do_use, do_back)
           to prepend the active mode's prompt_prefix. run/hunt success messages use
           mode_mgr.active.run_success (displayed via Rich after results). Score
           celebration uses mode_mgr.active.score_celebration.format(points=total).
           This wiring is localised to _execute_hunt and do_mode — future modes
           integration points (hints, celebrations) will follow the same pattern.
"""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
from typing import Any

import cmd2
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from adversary_pursuit.core.config import ConfigManager
from adversary_pursuit.core.error_interpreter import interpret, render_interactive
from adversary_pursuit.core.graph import RelationshipGraph
from adversary_pursuit.core.plugin_mgr import PluginManager
from adversary_pursuit.core.report import ReportGenerator
from adversary_pursuit.core.streak import StreakManager
from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.gamification.badges import BadgeManager
from adversary_pursuit.gamification.celebrations import (
    CelebrationEngine,
    highest_crossed_milestone_id,
)
from adversary_pursuit.gamification.challenges import ChallengeManager
from adversary_pursuit.gamification.hints import HintProvider, InsufficientBalanceError
from adversary_pursuit.gamification.modes import ModeManager
from adversary_pursuit.gamification.scoring import ScoringEngine, make_streak_continued_event
from adversary_pursuit.models.stix import create_bundle, dict_to_stix
from adversary_pursuit.modules.base import ModuleError


class APConsole(cmd2.Cmd):
    """Adversary Pursuit interactive console.

    Metasploit-like REPL with Rich rendering. Wires together
    ConfigManager, PluginManager, and WorkspaceManager.

    State machine:
        [main] ap>  -- no module loaded
        [module] ap(osint/whois_lookup)>  -- module loaded, options settable

    Usage (interactive)::

        ap> use osint/whois_lookup
        ap(osint/whois_lookup)> set TARGET example.com
        ap(osint/whois_lookup)> run
        ap(osint/whois_lookup)> back
        ap>
    """

    # Suppress cmd2's intro message and default prompts
    intro = ""
    prompt = "[main] ap> "

    def __init__(
        self,
        config_dir: Path | None = None,
        workspace_dir: Path | None = None,
        streak_path: Path | None = None,
    ) -> None:
        """Initialise console with optional directory overrides for testability.

        Parameters
        ----------
        config_dir:
            Override for ConfigManager. Pass tmp_path in tests.
        workspace_dir:
            Override for WorkspaceManager. Pass tmp_path in tests.
        streak_path:
            Override for StreakManager path. Pass tmp_path / "streak.json" in
            tests to avoid touching ~/.ap/streak.json (DEC-62-STREAK-001).
        """
        super().__init__()

        # Rich console — created via factory so tests can reset it easily
        self.rich_console: Console = self._make_rich_console()

        # Core subsystems
        self.config_mgr = ConfigManager(config_dir=config_dir)
        self.config = self.config_mgr.load()
        self.plugin_mgr = PluginManager()
        self.plugin_mgr.load_plugins()
        self.workspace_mgr = WorkspaceManager(workspace_dir=workspace_dir)
        self.scoring_engine = ScoringEngine()
        self.challenge_mgr = ChallengeManager()
        self.badge_mgr = BadgeManager()
        self.hint_provider = HintProvider()
        self.mode_mgr = ModeManager()
        self.celebration_engine = CelebrationEngine()
        # StreakManager is the sole authority for streak.json (DEC-62-STREAK-007).
        # streak_path is injectable for tests so real ~/.ap/streak.json is never
        # touched during the test suite.
        self.streak_mgr = StreakManager(path=streak_path)

        # Active module state
        self._active_module: Any = None  # PursuitModule instance or None
        self._active_module_path: str = ""  # e.g. "osint/whois_lookup"
        self._active_module_options: dict[str, str] = {}

        # Report generator — instantiated lazily when 'report' is first used
        self._report_generator: ReportGenerator | None = None
        self._last_report_path: Path | None = None

    # ------------------------------------------------------------------
    # Rich console factory (supports test reset)
    # ------------------------------------------------------------------

    def _make_rich_console(self) -> Console:
        """Create a StringIO-backed Rich Console for output capture.

        Using StringIO as the file means Rich output is captured alongside
        cmd2's poutput() in tests. In production the console is constructed
        the same way — the StringIO content is checked by tests.

        See DEC-CONSOLE-001 for the rationale.
        """
        return Console(file=io.StringIO(), highlight=False, markup=True)

    # ------------------------------------------------------------------
    # cmd2 lifecycle hooks
    # ------------------------------------------------------------------

    def preloop(self) -> None:
        """Display the streak banner line once at REPL startup.

        Called by cmd2 before the command loop begins. Respects AP_NO_BANNER=1
        so CI environments stay clean. The streak line is rendered only when the
        current streak is > 0 (format_banner_line returns empty string otherwise).

        DEC-62-STREAK-006: shared banner line with agent/banner.render_boot_banner.
        """
        import os

        if os.environ.get("AP_NO_BANNER"):
            return
        banner_line = self.streak_mgr.format_banner_line()
        if banner_line:
            self.rich_console.print(f"[bold yellow]{banner_line}[/bold yellow]")

    # ------------------------------------------------------------------
    # cmd2 framework error hook (DEC-ERROR-INTERPRETER-001)
    # ------------------------------------------------------------------

    def pexcept(self, exception: BaseException, **kwargs: object) -> None:
        """Override cmd2's framework-level exception handler.

        cmd2 calls ``pexcept(ex)`` inside ``onecmd_plus_hooks`` for any
        unhandled exception that escapes a do_* command handler.  The default
        implementation prints the exception type+message to stderr (and a full
        traceback when ``self.debug`` is True).

        We replace that with the friendly-error pipeline so the user always
        sees a Rich panel with a diagnostic ID instead of a raw traceback.
        The full traceback is still captured in ``~/.ap/debug.log`` via
        ``interpret()``.

        ``**kwargs`` are accepted for forward-compatibility with the cmd2
        base-class signature.
        """
        interp = interpret(exception, context={"surface": "cmd2_pexcept"})
        render_interactive(
            interp,
            self.rich_console,
            mode=self.mode_mgr.active if hasattr(self, "mode_mgr") else None,
            interactive=False,  # cmd2 exception path is non-interactive
        )

    # ------------------------------------------------------------------
    # search
    # ------------------------------------------------------------------

    def do_search(self, args: str) -> None:
        """Search loaded modules by keyword.

        Usage: search <keyword>

        Searches module name, description, and type fields.
        """
        keyword = args.strip()
        if not keyword:
            self.poutput("Usage: search <keyword>")
            return

        results = self.plugin_mgr.search(keyword)
        if not results:
            self.poutput(f"No modules found matching '{keyword}'")
            return

        table = Table(title=f"Search results for '{keyword}'", show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="yellow")
        table.add_column("Description")
        for r in results:
            table.add_row(r["name"], r["type"], r["description"])
        self.rich_console.print(table)

    # ------------------------------------------------------------------
    # use
    # ------------------------------------------------------------------

    def do_use(self, args: str) -> None:
        """Load a module by path.

        Usage: use <module_path>
        Example: use osint/whois_lookup
        """
        path = args.strip()
        if not path:
            self.poutput("Usage: use <module_path>")
            return

        module = self.plugin_mgr.get_module(path)
        if module is None:
            self.poutput(f"Module not found: '{path}'. Use 'search' to find available modules.")
            return

        self._active_module = module
        self._active_module_path = path
        self._active_module_options = {}
        prefix = self.mode_mgr.active.prompt_prefix
        self.prompt = f"{prefix}[module] ap({path})> "
        self.poutput(f"Module '{path}' loaded. Type 'show options' to see parameters.")

    # ------------------------------------------------------------------
    # back
    # ------------------------------------------------------------------

    def do_back(self, _: str) -> None:
        """Return to main context, unloading the active module.

        Usage: back
        """
        self._active_module = None
        self._active_module_path = ""
        self._active_module_options = {}
        prefix = self.mode_mgr.active.prompt_prefix
        self.prompt = f"{prefix}[main] ap> "

    # ------------------------------------------------------------------
    # show
    # ------------------------------------------------------------------

    def do_show(self, args: str) -> None:
        """Show module options or other info.

        Usage: show options
        """
        sub = args.strip().lower()
        if sub == "options":
            self._show_options()
        else:
            self.poutput("Usage: show options")

    def _show_options(self) -> None:
        """Render the active module's options as a Rich table."""
        if self._active_module is None:
            self.poutput("No module loaded. Use 'use <module_path>' first.")
            return

        options = getattr(self._active_module, "options", {})

        table = Table(
            title=f"Options for {self._active_module_path}",
            show_header=True,
        )
        table.add_column("Name", style="cyan")
        table.add_column("Current Value", style="green")
        table.add_column("Required", style="yellow")
        table.add_column("Description")

        for name, meta in options.items():
            current = self._active_module_options.get(name, meta.get("default", ""))
            required = "yes" if meta.get("required", False) else "no"
            description = meta.get("description", "")
            table.add_row(name, str(current), required, description)

        self.rich_console.print(table)

    # ------------------------------------------------------------------
    # set
    # ------------------------------------------------------------------

    def do_set(self, args: str) -> None:
        """Set a module option.

        Usage: set <OPTION> <value>
        Example: set TARGET example.com
        """
        if self._active_module is None:
            self.poutput("No module loaded. Use 'use <module_path>' first.")
            return

        parts = args.strip().split(None, 1)
        if len(parts) < 2:
            self.poutput("Usage: set <OPTION> <value>")
            return

        name, value = parts[0].upper(), parts[1]
        self._active_module_options[name] = value
        self.poutput(f"{name} => {value}")

    # ------------------------------------------------------------------
    # run / hunt
    # ------------------------------------------------------------------

    def do_run(self, _: str) -> None:
        """Execute the active module's hunt() against TARGET.

        Usage: run

        Requires a module to be loaded ('use') and TARGET to be set ('set TARGET').
        Results are stored in the active workspace and displayed as a Rich table.
        """
        self._execute_hunt()

    def do_hunt(self, _: str) -> None:
        """Alias for 'run'. Execute the active module.

        Usage: hunt
        """
        self._execute_hunt()

    def _execute_hunt(self) -> None:
        """Shared implementation for run and hunt commands."""
        if self._active_module is None:
            self.poutput("No module loaded. Use 'use <module_path>' first.")
            return

        target = self._active_module_options.get("TARGET", "").strip()
        if not target:
            self.poutput("TARGET not set. Use 'set TARGET <value>' first.")
            return

        try:
            results = asyncio.run(self._active_module.hunt(target, self._active_module_options))
        except ModuleError as exc:
            interp = interpret(
                exc,
                context={"surface": "cmd2_execute_hunt", "module": self._active_module_path},
            )
            render_interactive(
                interp,
                self.rich_console,
                mode=self.mode_mgr.active,
                interactive=False,
            )
            # Wire run_fail: mode-flavored failure voice (DEC-62-KILL-DOC-LIES-001).
            # render_interactive already showed the error panel; run_fail adds the
            # character persona voice so the analyst hears the mode's reaction.
            self.rich_console.print(self.mode_mgr.active.run_fail)
            return
        except Exception as exc:  # noqa: BLE001
            interp = interpret(
                exc,
                context={"surface": "cmd2_execute_hunt", "module": self._active_module_path},
            )
            render_interactive(
                interp,
                self.rich_console,
                mode=self.mode_mgr.active,
                interactive=False,
            )
            # Wire run_fail on generic exception path too (DEC-62-KILL-DOC-LIES-001).
            self.rich_console.print(self.mode_mgr.active.run_fail)
            return

        # Display results and show mode-specific success message
        self._display_results(results)
        if results:
            self.rich_console.print(self.mode_mgr.active.run_success)

        # Store in workspace and score
        # @defprog-exempt: workspace/scoring errors are user-visible warnings —
        # hunt results were already displayed; storage failure is non-fatal and
        # reported to the user via poutput so they can investigate.
        try:
            # Capture pre-run total BEFORE storing events — used for quiet-start
            # migration so we seed based on what was already in the workspace,
            # not the post-run total (which would suppress milestones earned by
            # this very run). DEC-63-MIGRATION-001.
            pre_total = self.workspace_mgr.get_total_score()

            # Capture type counts BEFORE storing so solve_count reflects
            # what was already in the workspace (not including these new results).
            stats = self.workspace_mgr.get_stix_type_counts()

            count = self.workspace_mgr.store_stix_objects(
                results,
                module_name=self._active_module_path,
                target=target,
                # Provenance kwargs: None until hunt() surfaces vendor metadata
                # (DEC-59-STIX-PROVENANCE-004). x_ap_fetched_at is defaulted by
                # workspace; the other three require module-author API changes.
                source_url=None,
                api_version=None,
                response_sha256=None,
                fetched_at=None,
            )
            self.poutput(f"\n{count} objects stored in workspace '{self.workspace_mgr.active}'")

            # Score the discoveries and show point gains using active mode celebration
            scoring_events = self.scoring_engine.score_results(results, stats)
            if scoring_events:
                total_gained = self.scoring_engine.total_score(scoring_events)
                self.workspace_mgr.store_score_events(scoring_events)
                celebration = self.mode_mgr.active.score_celebration.format(points=total_gained)
                self.rich_console.print(celebration)
                for event in scoring_events:
                    self.rich_console.print(
                        f"  [cyan]{event['action']}[/cyan]: "
                        f"[green]+{event['points']}[/green] "
                        f"({event['indicator']})"
                    )

            # Milestone catch-up check (DEC-63-MILESTONE-CATCHUP-001).
            # Read last_announced_id AFTER storing score events so post_total
            # reflects all points awarded this run.
            # Quiet-start migration: seed from pre_total (score BEFORE this run)
            # so milestones earned by this run are not suppressed.
            # DEC-63-MIGRATION-001: on first access (last_id is None) with a
            # pre-existing score, initialise last_id from pre_total so
            # retroactive announcements for old scores are suppressed but this
            # run's newly earned milestones are still announced.
            try:
                post_total = self.workspace_mgr.get_total_score()
                last_id = self.workspace_mgr.get_last_milestone_id()
                if last_id is None and pre_total > 0:
                    # Quiet-start: suppress retroactive announcements for
                    # workspaces loaded with a pre-existing score.
                    seeded_id = highest_crossed_milestone_id(pre_total)
                    if seeded_id is not None:
                        self.workspace_mgr.set_last_milestone_id(seeded_id)
                        last_id = seeded_id
                new_milestones = self.celebration_engine.check_milestones(post_total, last_id)
                if new_milestones:
                    highest_new_id = max(ms.id for ms in new_milestones)
                    self.workspace_mgr.set_last_milestone_id(highest_new_id)
                    for ms in new_milestones:
                        self.rich_console.print(f"\n[bold yellow]{ms.message}[/bold yellow]")
            except Exception:  # noqa: BLE001
                pass  # milestone check must never interrupt the hunt flow
        except Exception as exc:  # noqa: BLE001
            self.poutput(f"Warning: could not store results in workspace: {exc}")

        # Check challenges after every run (errors are non-fatal)
        try:
            self._check_challenges_after_run()
        except Exception:  # noqa: BLE001
            pass  # Challenge checks must never interrupt the hunt flow

        # Check badges after every run (errors are non-fatal)
        try:
            self._check_badges_after_run()
        except Exception:  # noqa: BLE001
            pass  # Badge checks must never interrupt the hunt flow

        # Fire first_blood message at post-badge-check site (DEC-62-CELEBRATIONS-001).
        # Fires at most once per session (CelebrationEngine._first_blood_used guard).
        # The "first_blood" badge is awarded by BadgeManager on the first indicator;
        # showing the message here — after _check_badges_after_run — means the badge
        # panel and the first-blood message appear together on the winning run.
        try:
            fb_msg = self.celebration_engine.first_blood_message()
            if fb_msg:
                self.rich_console.print(fb_msg)
        except Exception:  # noqa: BLE001
            pass  # first_blood display must never interrupt the hunt flow

        # Update streak after a successful hunt (DEC-62-STREAK-007).
        # StreakManager.update() is the sole write authority for streak.json.
        # Called here (post-badge-check) so a failed hunt (exception paths above
        # return early) never advances the streak.
        # F63: consume StreakUpdate.incremented to emit streak_continued score event
        # (DEC-63-STREAK-SCORE-001). Step-decay points prevent farming.
        try:
            from datetime import date

            streak_update = self.streak_mgr.update(date.today())
            if streak_update.incremented:
                streak_event = make_streak_continued_event(streak_update.current_streak)
                try:
                    self.workspace_mgr.store_score_events([streak_event])
                    self.rich_console.print(
                        f"  [cyan]{streak_event['action']}[/cyan]: "
                        f"[green]+{streak_event['points']}[/green] "
                        f"({streak_event['indicator']})"
                    )
                except Exception:  # noqa: BLE001
                    pass  # streak score storage must never interrupt the hunt flow
        except Exception:  # noqa: BLE001
            pass  # streak errors must never interrupt the hunt flow

    def _display_results(self, results: list[dict]) -> None:
        """Render hunt() results as a Rich table.

        Shows Type, Value, and any extra fields present in the result dicts.
        """
        if not results:
            self.poutput("No results returned.")
            return

        # Collect all extra field names (beyond type/value)
        extra_keys: list[str] = []
        for r in results:
            for k in r:
                if k not in ("type", "value") and k not in extra_keys:
                    extra_keys.append(k)

        table = Table(title="Results", show_header=True)
        table.add_column("Type", style="cyan")
        table.add_column("Value", style="green")
        for k in extra_keys:
            table.add_column(k.replace("x_", "").replace("_", " ").title())

        for r in results:
            row = [r.get("type", ""), r.get("value", "")]
            for k in extra_keys:
                row.append(str(r.get(k, "")))
            table.add_row(*row)

        self.rich_console.print(table)

    # ------------------------------------------------------------------
    # workspace
    # ------------------------------------------------------------------

    def do_workspace(self, args: str) -> None:
        """Workspace management.

        Usage:
            workspace              -- list workspaces
            workspace list         -- list workspaces
            workspace create <name>
            workspace switch <name>
            workspace delete <name>
        """
        parts = args.strip().split(None, 1)
        sub = parts[0].lower() if parts else "list"
        name = parts[1].strip() if len(parts) > 1 else ""

        if sub in ("list", ""):
            self._workspace_list()
        elif sub == "create":
            self._workspace_create(name)
        elif sub == "switch":
            self._workspace_switch(name)
        elif sub == "delete":
            self._workspace_delete(name)
        else:
            self.poutput(f"Unknown workspace subcommand: '{sub}'")
            self.poutput("Usage: workspace [list|create|switch|delete] [name]")

    def _workspace_list(self) -> None:
        names = self.workspace_mgr.list_workspaces()
        if not names:
            self.poutput("No workspaces found.")
            return
        table = Table(title="Workspaces", show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("Active", style="green")
        try:
            active = self.workspace_mgr.active
        except RuntimeError:
            active = ""
        for n in names:
            marker = "*" if n == active else ""
            table.add_row(n, marker)
        self.rich_console.print(table)

    def _workspace_create(self, name: str) -> None:
        if not name:
            self.poutput("Usage: workspace create <name>")
            return
        try:
            self.workspace_mgr.create(name)
            self.poutput(f"Workspace '{name}' created.")
        except ValueError as exc:
            self.poutput(f"Error: {exc}")

    def _workspace_switch(self, name: str) -> None:
        if not name:
            self.poutput("Usage: workspace switch <name>")
            return
        try:
            self.workspace_mgr.switch(name)
            self.poutput(f"Switched to workspace '{name}'.")
        except ValueError as exc:
            self.poutput(f"Error: {exc}")

    def _workspace_delete(self, name: str) -> None:
        if not name:
            self.poutput("Usage: workspace delete <name>")
            return
        try:
            self.workspace_mgr.delete(name)
            self.poutput(f"Workspace '{name}' deleted.")
        except ValueError as exc:
            self.poutput(f"Error: {exc}")

    # ------------------------------------------------------------------
    # db_status
    # ------------------------------------------------------------------

    def do_db_status(self, _: str) -> None:
        """Show active workspace status and object counts.

        Usage: db_status
        """
        try:
            active = self.workspace_mgr.active
        except RuntimeError:
            active = "(none)"

        workspaces = self.workspace_mgr.list_workspaces()

        table = Table(title="Database Status", show_header=True)
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Active workspace", active)
        table.add_row("Available workspaces", str(len(workspaces)))

        if active != "(none)":
            try:
                objects = self.workspace_mgr.get_stix_objects()
                runs = self.workspace_mgr.get_module_runs()
                table.add_row("STIX objects", str(len(objects)))
                table.add_row("Module runs", str(len(runs)))
                if runs:
                    last = runs[-1]
                    table.add_row("Last run", f"{last['module_name']} @ {last['target']}")
            except Exception:  # noqa: BLE001
                table.add_row("Objects", "(workspace not yet initialized)")

        self.rich_console.print(table)

    # ------------------------------------------------------------------
    # score
    # ------------------------------------------------------------------

    def do_score(self, _: str) -> None:
        """Show current pursuit score and recent scoring events.

        Usage: score

        Displays total accumulated score and the 10 most recent events
        as a Rich table. Score is per-workspace.
        """
        try:
            total = self.workspace_mgr.get_total_score()
            recent = self.workspace_mgr.get_recent_scores(limit=10)
        except Exception as exc:  # noqa: BLE001
            self.poutput(f"Score: 0  (workspace not yet initialized: {exc})")
            return

        self.rich_console.print(f"\n[bold yellow]Total Score: {total} pts[/bold yellow]\n")

        if not recent:
            self.poutput("No scoring events yet. Run a module to start earning points.")
            return

        table = Table(title="Recent Scoring Events", show_header=True)
        table.add_column("Action", style="cyan")
        table.add_column("Points", style="green", justify="right")
        table.add_column("Indicator", style="white")
        for event in recent:
            table.add_row(
                event["action"],
                f"+{event['points']}",
                event.get("indicator") or "",
            )
        self.rich_console.print(table)

    # ------------------------------------------------------------------
    # challenges
    # ------------------------------------------------------------------

    def do_challenges(self, _: str) -> None:
        """Show all challenges with current status.

        Usage: challenges

        Displays a Rich table of all challenges: name, type, points, status,
        and hints. Completed challenges show their completion time.
        """
        items = self.challenge_mgr.list_challenges()

        table = Table(title="Challenges", show_header=True)
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="bold")
        table.add_column("Type", style="yellow")
        table.add_column("Points", style="green", justify="right")
        table.add_column("Status", style="white")
        table.add_column("Description")

        for item in items:
            status = item["status"]
            if status == "completed":
                status_str = "[green]completed[/green]"
            elif status == "expired":
                status_str = "[red]expired[/red]"
            else:
                status_str = "[blue]active[/blue]"

            table.add_row(
                item["id"],
                item["name"],
                item["challenge_type"],
                str(item["points"]),
                status_str,
                item["description"],
            )

        self.rich_console.print(table)

    def _build_workspace_data(self) -> dict:
        """Assemble workspace_data dict for challenge verification.

        Collects stix_type_counts, modules_used, total_score, and
        total_indicators from WorkspaceManager. Returns an empty-data
        dict on any error so challenge checking degrades gracefully.

        Returns
        -------
        dict
            Keys: stix_type_counts, modules_used, total_score,
            total_indicators, indicators.
        """
        try:
            stix_counts = self.workspace_mgr.get_stix_type_counts()
            runs = self.workspace_mgr.get_module_runs()
            modules_used = [r["module_name"] for r in runs]
            total_score = self.workspace_mgr.get_total_score()
            total_indicators = sum(stix_counts.values())
            # Collect flat indicator list for indicator_exists checks
            indicators = [
                {"type": obj.get("type", ""), "value": obj.get("value", "")}
                for obj in self.workspace_mgr.get_stix_objects()
            ]
            return {
                "stix_type_counts": stix_counts,
                "modules_used": modules_used,
                "total_score": total_score,
                "total_indicators": total_indicators,
                "indicators": indicators,
            }
        except Exception:  # noqa: BLE001
            return {
                "stix_type_counts": {},
                "modules_used": [],
                "total_score": 0,
                "total_indicators": 0,
                "indicators": [],
            }

    def _check_challenges_after_run(self) -> None:
        """Check all active challenges after a module run and announce completions.

        Called by _execute_hunt() after results are stored. Newly completed
        challenges are displayed as Rich panels so the analyst sees the reward
        immediately after their hunt.
        """
        workspace_data = self._build_workspace_data()
        newly_completed = self.challenge_mgr.check_all(workspace_data)
        for ch in newly_completed:
            self.rich_console.print(
                Panel(
                    f"[bold yellow]{ch.name}[/bold yellow]\n"
                    f"{ch.description}\n\n"
                    f"[green]+{ch.points} bonus points![/green]",
                    title="[bold green]Challenge Completed![/bold green]",
                    style="green",
                )
            )

    # ------------------------------------------------------------------
    # badges — Issue #17 implementation
    # ------------------------------------------------------------------

    def do_badges(self, _: str) -> None:
        """Show all badges earned in the active workspace.

        Usage: badges

        Displays a Rich table of badges earned, with name, rarity, description,
        and award timestamp. Badges are permanent achievements that persist in
        the workspace database (badge_events table).
        """
        try:
            awarded = self.workspace_mgr.get_awarded_badges()
        except Exception as exc:  # noqa: BLE001
            self.poutput(f"No badges yet (workspace not initialized: {exc})")
            return

        if not awarded:
            self.poutput(
                "No badges earned yet. Run modules to discover indicators and earn badges!"
            )
            return

        # Get badge metadata from BadgeManager for rarity display
        table = Table(title="Earned Badges", show_header=True)
        table.add_column("Badge", style="bold yellow")
        table.add_column("Rarity", style="cyan")
        table.add_column("Description")
        table.add_column("Earned At", style="dim")

        for entry in awarded:
            badge = self.badge_mgr.get_badge(entry["badge_id"])
            rarity = badge.rarity.value.upper() if badge else "UNKNOWN"
            description = badge.description if badge else ""
            earned_at = entry.get("awarded_at")
            earned_str = earned_at.strftime("%Y-%m-%d %H:%M") if earned_at else ""
            table.add_row(entry["badge_name"], rarity, description, earned_str)

        self.rich_console.print(table)

    def _check_badges_after_run(self) -> None:
        """Check all badges after a module run and persist/announce newly earned ones.

        Called by _execute_hunt() after results are stored and scored.
        Builds the already_awarded set from the workspace, evaluates all
        badge conditions via BadgeManager.check_all(), persists new awards
        to the badge_events table, and displays a Rich panel for each new badge.

        Errors are caught by the caller — this method should not raise.
        """
        # Build already_awarded set from workspace (application-layer dedup, DEC-BADGE-002)
        awarded_rows = self.workspace_mgr.get_awarded_badges()
        already_awarded = {row["badge_id"] for row in awarded_rows}

        # Get current workspace stats for evaluation
        stats = self.workspace_mgr.get_workspace_stats()

        # Evaluate all badges
        newly_earned = self.badge_mgr.check_all(stats, already_awarded=already_awarded)

        for badge in newly_earned:
            # Persist
            self.workspace_mgr.store_badge_event(badge.id, badge.name)
            # Announce with rarity-styled panel
            rarity_colors = {
                "common": "white",
                "uncommon": "green",
                "rare": "blue",
                "epic": "magenta",
                "legendary": "bold yellow",
            }
            color = rarity_colors.get(badge.rarity.value, "white")
            self.rich_console.print(
                Panel(
                    f"[bold]{badge.name}[/bold] [{color}]({badge.rarity.value.upper()})[/{color}]\n"
                    f"{badge.description}",
                    title="[bold yellow]Badge Earned![/bold yellow]",
                    style="yellow",
                )
            )

    # ------------------------------------------------------------------
    # report
    # ------------------------------------------------------------------

    def do_report(self, args: str) -> None:
        """Generate and manage investigation reports.

        Usage:
            report generate   -- generate report and save to file
            report interview  -- guided interview (prompts for each question)
            report show       -- display the last generated report

        Reports are Markdown files written to the active workspace directory.
        The interview must be completed (or partially completed) before generate
        to embed analyst answers in the report.
        """
        parts = args.strip().split(None, 1)
        sub = parts[0].lower() if parts else "generate"

        if sub == "generate":
            self._report_generate()
        elif sub == "interview":
            self._report_interview()
        elif sub == "show":
            self._report_show()
        else:
            self.poutput(f"Unknown report subcommand: '{sub}'")
            self.poutput("Usage: report [generate|interview|show]")

    def _get_report_generator(self) -> ReportGenerator:
        """Return the current ReportGenerator, creating it if necessary.

        Re-creates the generator if it hasn't been initialised yet.
        The generator holds in-memory interview answers, so it persists
        for the session once created. Answers survive multiple generate/show calls.
        """
        if self._report_generator is None:
            self._report_generator = ReportGenerator(
                self.workspace_mgr,
                scoring_engine=self.scoring_engine,
            )
        return self._report_generator

    def _report_generate(self) -> None:
        """Generate report and save to a file in the workspace directory."""
        try:
            rg = self._get_report_generator()
            # Derive output path from workspace name
            try:
                ws_name = self.workspace_mgr.active
            except RuntimeError:
                ws_name = "default"

            # Save alongside the workspace DB files
            workspace_dir = self.workspace_mgr._workspace_dir
            workspace_dir.mkdir(parents=True, exist_ok=True)
            output_path = workspace_dir / f"{ws_name}-report.md"
            rg.save(output_path)
            self.poutput(f"Report saved: {output_path}")
            self._last_report_path = output_path
        except Exception as exc:  # noqa: BLE001
            self.poutput(f"Error generating report: {exc}")

    def _report_interview(self) -> None:
        """Interactive interview — prompts for each question and stores answers.

        Uses self.read_input() so tests can inject answers via stdin redirection.
        Answers are stored in the ReportGenerator and included in the next generate().
        """
        rg = self._get_report_generator()
        self.poutput("Investigation Interview")
        self.poutput("Enter your answer for each question (press Enter to skip).")
        self.poutput("")
        for i, section in enumerate(rg.sections):
            self.poutput(f"Q{i + 1}: {section.question}")
            try:
                answer = input("A: ").strip()
            except (EOFError, KeyboardInterrupt):
                answer = ""
            if answer:
                rg.set_answer(i, answer)
            self.poutput("")
        self.poutput("Interview complete. Run 'report generate' to produce the report.")

    def _report_show(self) -> None:
        """Display the report content on stdout."""
        rg = self._get_report_generator()
        content = rg.generate()
        self.poutput(content)

    # ------------------------------------------------------------------
    # sessions (stub)
    # ------------------------------------------------------------------

    def do_sessions(self, _: str) -> None:
        """List active sessions (stub).

        Usage: sessions
        """
        self.poutput("No active sessions.")

    # ------------------------------------------------------------------
    # mode — Issue #16 implementation
    # ------------------------------------------------------------------

    def do_mode(self, args: str) -> None:
        """Switch the active character mode.

        Usage:
            mode <name>      -- switch to named mode
            mode             -- show current mode and list all available

        Available modes: default, ninja, full_troll, drunken_master, sun_tzu,
            chuck_norris, bureaucrat, bobby_hill, bruce_lee, columbo

        Each mode changes the prompt prefix, hunt success/failure messages,
        and score celebration style. See ModeManager and DEFAULT_MODES in
        gamification/modes.py for the full configuration.
        """
        name = args.strip()
        if not name:
            # No argument — show current mode and list all
            current = self.mode_mgr.active
            self.poutput(f"Current mode: {current.name} — {current.personality}")
            self.poutput("Available modes:")
            for entry in self.mode_mgr.list_modes():
                marker = "* " if entry["name"] == current.name else "  "
                self.poutput(f"  {marker}{entry['name']}: {entry['personality']}")
            return

        try:
            mode = self.mode_mgr.switch(name)
        except ValueError as exc:
            self.poutput(f"Error: {exc}")
            return

        # Update prompt to reflect new mode prefix
        prefix = mode.prompt_prefix
        if self._active_module:
            self.prompt = f"{prefix}[module] ap({self._active_module_path})> "
        else:
            self.prompt = f"{prefix}[main] ap> "

        # Display the mode's greeting
        self.rich_console.print(mode.greeting)

    # ------------------------------------------------------------------
    # export
    # ------------------------------------------------------------------

    def do_export(self, args: str) -> None:
        """Export workspace objects.

        Usage:
            export                    -- export as STIX bundle (default)
            export --format stix      -- export as STIX bundle JSON
            export --format gexf      -- export as GEXF XML for Gephi
            export --format csv       -- export as CSV (not yet implemented)
            export --format json      -- export as plain JSON array
        """
        fmt = "stix"
        if "--format" in args:
            parts = args.split("--format", 1)
            fmt = parts[1].strip().lower() if len(parts) > 1 else "stix"

        try:
            raw_objects = self.workspace_mgr.get_stix_objects()
        except Exception as exc:  # noqa: BLE001
            self.poutput(f"Error reading workspace: {exc}")
            return

        if not raw_objects:
            self.poutput("No objects in workspace to export.")
            return

        if fmt in ("stix", ""):
            self._export_stix(raw_objects)
        elif fmt == "gexf":
            self._export_gexf(raw_objects)
        elif fmt == "json":
            self.poutput(json.dumps(raw_objects, indent=2))
        elif fmt == "csv":
            self.poutput("CSV export not yet implemented.")
        else:
            self.poutput(f"Unknown format '{fmt}'. Supported: stix, gexf, json")

    def _export_stix(self, raw_objects: list[dict]) -> None:
        """Construct a STIX bundle from workspace objects and print JSON."""
        stix_objects = []
        for d in raw_objects:
            obj = dict_to_stix(d)
            if not isinstance(obj, dict):
                stix_objects.append(obj)

        if not stix_objects:
            self.poutput("No recognized STIX objects to export.")
            return

        bundle = create_bundle(stix_objects)
        self.poutput(bundle.serialize(pretty=True))

    def _export_gexf(self, raw_objects: list[dict]) -> None:
        """Build a RelationshipGraph from workspace objects and export as GEXF XML."""
        g = RelationshipGraph()
        g.build_from_workspace(raw_objects)
        self.poutput(g.export_gexf())

    # ------------------------------------------------------------------
    # graph
    # ------------------------------------------------------------------

    def do_graph(self, args: str) -> None:
        """Visualize the current workspace as a relationship graph.

        Usage:
            graph                       -- show Rich tree of current workspace
            graph --root <stix_id>      -- show tree rooted at a specific node
            graph --stats               -- show graph statistics only

        The graph is built from all STIX objects in the active workspace.
        Nodes are STIX observables; edges are explicit relationships stored
        via store_stix_objects. Unconnected nodes appear under an 'Unconnected'
        branch at the root.
        """
        # Parse flags
        root_id: str | None = None
        stats_only = "--stats" in args

        if "--root" in args:
            parts = args.split("--root", 1)
            if len(parts) > 1:
                root_id = parts[1].strip().split()[0] if parts[1].strip() else None

        # Load workspace objects
        try:
            raw_objects = self.workspace_mgr.get_stix_objects()
        except Exception as exc:  # noqa: BLE001
            self.poutput(f"Error reading workspace: {exc}")
            return

        # Build graph
        g = RelationshipGraph()
        g.build_from_workspace(raw_objects)

        if stats_only:
            self._graph_show_stats(g)
            return

        if g.node_count == 0:
            self.poutput("No objects in workspace. Run a module first.")
            return

        tree = g.render_tree(root_id=root_id)
        self.rich_console.print(tree)

        # Show stats summary below the tree
        stats = g.get_stats()
        self.rich_console.print(
            f"\n[dim]{stats['node_count']} nodes, {stats['edge_count']} edges[/dim]"
        )

    def _graph_show_stats(self, g: RelationshipGraph) -> None:
        """Render graph statistics as a Rich table."""
        from rich.table import Table as RichTable

        stats = g.get_stats()
        table = RichTable(title="Graph Statistics", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")
        table.add_row("Nodes", str(stats["node_count"]))
        table.add_row("Edges", str(stats["edge_count"]))

        for stix_type, count in sorted(stats.get("types", {}).items()):
            table.add_row(f"  {stix_type}", str(count))

        self.rich_console.print(table)

    # ------------------------------------------------------------------
    # hint — Issue #18 implementation
    # ------------------------------------------------------------------

    def do_hint(self, args: str) -> None:
        """Show contextual hints for the current investigation.

        Usage:
            hint           -- show next hint (free hints first)
            hint free      -- show all free hints for the active module
            hint buy       -- reveal a paid hint (costs 10-20 points)

        Hints are contextual: when a module is loaded, module-specific hints
        are included alongside general hints. Free hints have no score cost.
        Paid hints deduct points from your workspace score (10-20 pts each).

        Module base name is derived from the active module path by stripping
        the namespace prefix (e.g. 'osint/dns_resolve' -> 'dns_resolve').
        See DEC-HINT-004 for rationale.
        """
        sub = args.strip().lower() if args.strip() else ""

        # Derive module base name from active module path (DEC-HINT-004)
        module_name: str | None = None
        if self._active_module_path:
            # "osint/dns_resolve" -> "dns_resolve"; "dns_resolve" -> "dns_resolve"
            module_name = (
                self._active_module_path.split("/")[-1] if self._active_module_path else None
            )

        if sub == "free":
            self._hint_show_free(module_name)
        elif sub == "buy":
            self._hint_buy(module_name)
        elif sub == "":
            self._hint_show_next(module_name)
        else:
            self.poutput(
                "Usage: hint | hint free | hint buy\n"
                "  hint       -- next hint (free first)\n"
                "  hint free  -- all free hints\n"
                "  hint buy   -- purchase a paid hint (10-20 pts)"
            )

    def _hint_show_next(self, module_name: str | None) -> None:
        """Show the next unrevealed hint (free hints first)."""
        result = self.hint_provider.get_next_hint(module=module_name)
        if result is None:
            self.rich_console.print(
                "[dim]All hints revealed. You're on your own now, analyst.[/dim]"
            )
            return
        cost_label = (
            "[green]FREE[/green]"
            if result.hint.cost == 0
            else f"[yellow]{result.hint.cost} pts[/yellow]"
        )
        self.rich_console.print(
            Panel(
                result.hint.text,
                title=f"[bold cyan]Hint[/bold cyan] {cost_label}",
                style="cyan",
            )
        )

    def _hint_show_free(self, module_name: str | None) -> None:
        """Show all free hints for the current module context."""
        free_hints = self.hint_provider.get_free_hints(module=module_name)
        if not free_hints:
            self.poutput("No free hints available for this context.")
            return

        context_label = f"module '{module_name}'" if module_name else "general"
        table = Table(title=f"Free Hints ({context_label})", show_header=True)
        table.add_column("#", style="dim", justify="right")
        table.add_column("Hint", style="white")
        table.add_column("Scope", style="cyan")

        for i, hint in enumerate(free_hints, start=1):
            scope = hint.module if hint.module else "general"
            table.add_row(str(i), hint.text, scope)

        self.rich_console.print(table)

    def _hint_buy(self, module_name: str | None) -> None:
        """Purchase the next paid hint, deducting cost from workspace score."""
        # Get current score — workspace may not be initialized yet
        try:
            current_score = self.workspace_mgr.get_total_score()
        except Exception:  # noqa: BLE001
            current_score = 0

        try:
            result = self.hint_provider.buy_hint(
                current_score=current_score,
                module=module_name,
            )
        except InsufficientBalanceError as exc:
            self.rich_console.print(
                Panel(
                    f"You need [bold]{exc.required}[/bold] pts but have [bold]{exc.available}[/bold] pts.\n"
                    "Run more modules to earn points, then try again.",
                    title="[bold red]Insufficient Score[/bold red]",
                    style="red",
                )
            )
            return

        if result is None:
            self.poutput("No paid hints available for this context. All hints revealed!")
            return

        # Deduct the hint cost from workspace score (DEC-HINT-001)
        try:
            self.workspace_mgr.store_score_events(
                [
                    {
                        "action": "hint_purchase",
                        "points": -result.cost_paid,
                        "indicator": result.hint.id,
                        "rule_description": f"Paid hint purchased: -{result.cost_paid} pts",
                    }
                ]
            )
        except Exception:  # noqa: BLE001
            pass  # Workspace not initialized — cost tracking skipped, hint still shown

        self.rich_console.print(
            Panel(
                result.hint.text,
                title=f"[bold yellow]Paid Hint[/bold yellow] [red]-{result.cost_paid} pts[/red]",
                style="yellow",
            )
        )
