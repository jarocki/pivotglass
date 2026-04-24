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
from adversary_pursuit.core.plugin_mgr import PluginManager
from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.gamification.modes import ModeManager
from adversary_pursuit.gamification.scoring import ScoringEngine
from adversary_pursuit.modules.base import ModuleError
from adversary_pursuit.models.stix import create_bundle, dict_to_stix


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
    ) -> None:
        """Initialise console with optional directory overrides for testability.

        Parameters
        ----------
        config_dir:
            Override for ConfigManager. Pass tmp_path in tests.
        workspace_dir:
            Override for WorkspaceManager. Pass tmp_path in tests.
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
        self.mode_mgr = ModeManager()

        # Active module state
        self._active_module: Any = None          # PursuitModule instance or None
        self._active_module_path: str = ""       # e.g. "osint/whois_lookup"
        self._active_module_options: dict[str, str] = {}

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
            results = asyncio.run(
                self._active_module.hunt(target, self._active_module_options)
            )
        except ModuleError as exc:
            self.rich_console.print(
                Panel(str(exc), title="Module Error", style="red")
            )
            return
        except Exception as exc:  # noqa: BLE001
            self.rich_console.print(
                Panel(f"Unexpected error: {exc}", title="Error", style="red")
            )
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
            # Capture type counts BEFORE storing so solve_count reflects
            # what was already in the workspace (not including these new results).
            stats = self.workspace_mgr.get_stix_type_counts()

            count = self.workspace_mgr.store_stix_objects(
                results,
                module_name=self._active_module_path,
                target=target,
            )
            self.poutput(
                f"\n{count} objects stored in workspace '{self.workspace_mgr.active}'"
            )

            # Score the discoveries and show point gains using active mode celebration
            scoring_events = self.scoring_engine.score_results(results, stats)
            if scoring_events:
                total_gained = self.scoring_engine.total_score(scoring_events)
                self.workspace_mgr.store_score_events(scoring_events)
                celebration = self.mode_mgr.active.score_celebration.format(
                    points=total_gained
                )
                self.rich_console.print(celebration)
                for event in scoring_events:
                    self.rich_console.print(
                        f"  [cyan]{event['action']}[/cyan]: "
                        f"[green]+{event['points']}[/green] "
                        f"({event['indicator']})"
                    )
        except Exception as exc:  # noqa: BLE001
            self.poutput(f"Warning: could not store results in workspace: {exc}")

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

        self.rich_console.print(
            f"\n[bold yellow]Total Score: {total} pts[/bold yellow]\n"
        )

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
        """Export workspace objects as a STIX 2.1 bundle.

        Usage:
            export                    -- export as STIX bundle (default)
            export --format stix      -- export as STIX bundle JSON
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
        elif fmt == "json":
            self.poutput(json.dumps(raw_objects, indent=2))
        elif fmt == "csv":
            self.poutput("CSV export not yet implemented.")
        else:
            self.poutput(f"Unknown format '{fmt}'. Supported: stix, json")

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
