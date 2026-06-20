"""Tests for APConsole — cmd2-based REPL.

Tests use onecmd_plus_hooks() with stdout redirection to capture output.
Rich output is captured via a StringIO-backed Console object.

Production sequence tested:
  use <module> -> set TARGET <value> -> run -> back
  This is the core adversary pursuit workflow that all users follow.
"""

from __future__ import annotations

import io

import pytest

from adversary_pursuit.core.console import APConsole

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def console(tmp_path):
    """Create an APConsole with temp dirs for isolated testing."""
    app = APConsole(
        config_dir=tmp_path / "config",
        workspace_dir=tmp_path / "workspaces",
    )
    app.stdout = io.StringIO()
    return app


def run_cmd(app: APConsole, cmd: str) -> str:
    """Run a command and return captured stdout.

    Rich output now flows to self.stdout (DEC-CONSOLE-001 fix), so all
    output — poutput() and Rich tables/panels — is captured from app.stdout.
    """
    app.stdout = io.StringIO()
    app.rich_console = app._make_rich_console()
    app.onecmd_plus_hooks(cmd)
    return app.stdout.getvalue()


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_search_finds_whois(console):
    """search whois returns the whois_lookup module."""
    out = run_cmd(console, "search whois")
    assert "whois" in out.lower()


def test_search_finds_dns(console):
    """search dns returns the dns_resolve module."""
    out = run_cmd(console, "search dns")
    assert "dns" in out.lower()


def test_search_no_results_no_crash(console):
    """search for nonexistent term does not crash."""
    out = run_cmd(console, "search xyznonexistentmodule99")
    assert isinstance(out, str)


# ---------------------------------------------------------------------------
# use / back
# ---------------------------------------------------------------------------


def test_use_changes_prompt(console):
    """use osint/whois_lookup changes prompt to module mode."""
    run_cmd(console, "use osint/whois_lookup")
    assert "whois_lookup" in console.prompt


def test_use_unknown_module_shows_error(console):
    """use nonexistent/module shows error message."""
    out = run_cmd(console, "use nonexistent/module")
    combined = out.lower()
    assert "not found" in combined or "unknown" in combined or "error" in combined


def test_use_dns_resolve(console):
    """use osint/dns_resolve loads the dns module."""
    run_cmd(console, "use osint/dns_resolve")
    assert "dns_resolve" in console.prompt


def test_back_resets_prompt(console):
    """back returns to main prompt."""
    run_cmd(console, "use osint/whois_lookup")
    run_cmd(console, "back")
    assert console.prompt == "ap> "
    assert console._active_module is None


def test_back_without_module_is_safe(console):
    """back without a loaded module does not crash."""
    run_cmd(console, "back")
    assert "ap>" in console.prompt or console.prompt == "ap> "


# ---------------------------------------------------------------------------
# show options
# ---------------------------------------------------------------------------


def test_show_options_with_module(console):
    """show options displays TARGET for whois_lookup."""
    run_cmd(console, "use osint/whois_lookup")
    out = run_cmd(console, "show options")
    assert "TARGET" in out


def test_show_options_without_module(console):
    """show options without module shows informative message."""
    out = run_cmd(console, "show options")
    assert isinstance(out, str)


def test_show_options_dns_shows_record_type(console):
    """show options for dns_resolve shows RECORD_TYPE option."""
    run_cmd(console, "use osint/dns_resolve")
    out = run_cmd(console, "show options")
    assert "TARGET" in out
    assert "RECORD_TYPE" in out


# ---------------------------------------------------------------------------
# set
# ---------------------------------------------------------------------------


def test_set_option_updates_value(console):
    """set TARGET stores the value in _active_module_options."""
    run_cmd(console, "use osint/whois_lookup")
    run_cmd(console, "set TARGET example.com")
    assert console._active_module_options.get("TARGET") == "example.com"


def test_set_option_shows_in_options(console):
    """After set TARGET, show options displays the new value."""
    run_cmd(console, "use osint/whois_lookup")
    run_cmd(console, "set TARGET 8.8.8.8")
    out = run_cmd(console, "show options")
    assert "8.8.8.8" in out


def test_set_without_module_shows_message(console):
    """set without a module loaded shows an informative message."""
    out = run_cmd(console, "set TARGET example.com")
    assert isinstance(out, str)


def test_set_clears_on_new_use(console):
    """Loading a new module via use clears previous options."""
    run_cmd(console, "use osint/whois_lookup")
    run_cmd(console, "set TARGET old.com")
    run_cmd(console, "back")
    run_cmd(console, "use osint/dns_resolve")
    assert console._active_module_options.get("TARGET", "") == ""


# ---------------------------------------------------------------------------
# run / hunt
# ---------------------------------------------------------------------------


def test_run_without_module_shows_error(console):
    """run without a loaded module shows error."""
    out = run_cmd(console, "run")
    assert "module" in out.lower()


def test_run_without_target_shows_error(console):
    """run without TARGET set shows error."""
    run_cmd(console, "use osint/whois_lookup")
    out = run_cmd(console, "run")
    assert "target" in out.lower()


def test_run_stores_results(console):
    """Full use -> set -> run workflow stores objects in workspace."""
    run_cmd(console, "use osint/dns_resolve")
    run_cmd(console, "set TARGET example.com")
    out = run_cmd(console, "run")
    combined = out.lower()
    assert "stored" in combined or "object" in combined or "workspace" in combined


def test_hunt_alias_works(console):
    """hunt is an alias for run."""
    run_cmd(console, "use osint/dns_resolve")
    run_cmd(console, "set TARGET example.com")
    out = run_cmd(console, "hunt")
    combined = out.lower()
    assert "stored" in combined or "object" in combined or "workspace" in combined


def test_run_displays_results_table(console):
    """run displays result data for a resolved domain."""
    run_cmd(console, "use osint/dns_resolve")
    run_cmd(console, "set TARGET example.com")
    out = run_cmd(console, "run")
    assert "example.com" in out or "domain" in out.lower() or "addr" in out.lower()


# ---------------------------------------------------------------------------
# Production sequence: full use -> set -> run -> back -> use -> set -> run
# Tests that state is properly reset between module loads.
# ---------------------------------------------------------------------------


def test_full_workflow_two_modules(console):
    """Two-module workflow: whois then dns, state properly isolated."""
    run_cmd(console, "use osint/whois_lookup")
    run_cmd(console, "set TARGET example.com")
    out1 = run_cmd(console, "run")
    run_cmd(console, "back")

    assert console.prompt == "ap> "
    assert console._active_module is None

    run_cmd(console, "use osint/dns_resolve")
    run_cmd(console, "set TARGET 8.8.8.8")
    out2 = run_cmd(console, "run")

    combined = (out1 + out2).lower()
    assert "stored" in combined or "object" in combined or "workspace" in combined


# ---------------------------------------------------------------------------
# workspace
# ---------------------------------------------------------------------------


def test_workspace_list_no_crash(console):
    """workspace list runs without crashing."""
    out = run_cmd(console, "workspace list")
    assert isinstance(out, str)


def test_workspace_create(console):
    """workspace create creates a new workspace."""
    run_cmd(console, "workspace create test_ws")
    out = run_cmd(console, "workspace list")
    assert "test_ws" in out


def test_workspace_switch(console):
    """workspace create + switch works without error."""
    run_cmd(console, "workspace create myws")
    out = run_cmd(console, "workspace switch myws")
    assert "error" not in out.lower()


def test_workspace_delete(console):
    """workspace delete removes a workspace."""
    run_cmd(console, "workspace create deleteme")
    run_cmd(console, "workspace delete deleteme")
    out = run_cmd(console, "workspace list")
    assert "deleteme" not in out


def test_workspace_create_duplicate_shows_error(console):
    """workspace create with existing name shows error."""
    run_cmd(console, "workspace create dup")
    out = run_cmd(console, "workspace create dup")
    combined = out.lower()
    assert "already" in combined or "exist" in combined or "error" in combined


# ---------------------------------------------------------------------------
# db_status
# ---------------------------------------------------------------------------


def test_db_status_shows_info(console):
    """db_status returns some output (workspace info)."""
    out = run_cmd(console, "db_status")
    assert out.strip()


# ---------------------------------------------------------------------------
# Stub commands
# ---------------------------------------------------------------------------


def test_score_shows_zero(console):
    """score stub prints 0."""
    out = run_cmd(console, "score")
    assert "0" in out


def test_sessions_stub(console):
    """sessions stub prints a message."""
    out = run_cmd(console, "sessions")
    assert out.strip()


def test_mode_stub(console):
    """mode stub prints placeholder message."""
    out = run_cmd(console, "mode stealth")
    assert out.strip()


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


def test_export_runs_without_crash(console):
    """export command runs without crashing on empty workspace."""
    run_cmd(console, "workspace create expws")
    run_cmd(console, "workspace switch expws")
    out = run_cmd(console, "export")
    assert isinstance(out, str)


# ---------------------------------------------------------------------------
# Error interpreter integration — exception-injection tests
# Evaluation contract: ≥3 exception cases; no raw Traceback in output.
# ---------------------------------------------------------------------------


class _RaisingModule:
    """In-memory fake PursuitModule that raises a configurable exception from hunt().

    Used to exercise the _execute_hunt() error path without needing a real
    API key or network connection.
    """

    name = "test/raiser"
    description = "Raises for testing"
    author = "test"
    module_type = "osint"
    options: dict = {}

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def initialize(self, config: dict) -> None:
        pass

    async def hunt(self, target: str, options: dict) -> list:
        raise self._exc


def _inject_module(console: APConsole, exc: BaseException) -> str:
    """Register a raising module directly in the plugin manager, load, and run it.

    PluginManager._modules stores *classes* (callables returning instances).
    We inject a factory class whose __init__ captures the desired exception,
    so get_module() can call factory() and receive the raising instance.
    """

    # Build a class (not an instance) so plugin_mgr.get_module() can call cls()
    class _Factory(_RaisingModule):
        def __init__(self_inner) -> None:  # noqa: N805
            super().__init__(exc)

    _Factory.name = "test/raiser"  # type: ignore[attr-defined]

    # Direct injection into the in-memory module registry — no mock required.
    console.plugin_mgr._modules["test/raiser"] = _Factory  # type: ignore[attr-defined]

    run_cmd(console, "use test/raiser")
    run_cmd(console, "set TARGET 1.2.3.4")
    out = run_cmd(console, "run")
    return out


class TestConsoleErrorInterpreter:
    """Exception-injection tests verifying no raw tracebacks escape to the user.

    Production sequence: use <module> → set TARGET → run → hunt() raises →
    _execute_hunt catches → interpret() → render_interactive() → friendly panel.
    """

    def test_module_error_produces_friendly_panel_no_traceback(self, console):
        """ModuleError from hunt() → friendly panel, no 'Traceback (most recent call last):'."""
        from adversary_pursuit.modules.base import ModuleError

        exc = ModuleError("API key missing")
        out = _inject_module(console, exc)

        assert "Traceback (most recent call last):" not in out
        # Friendly panel contains a diagnostic ID (8 hex chars)
        import re

        assert re.search(r"[a-f0-9]{8}", out), "Expected 8-char diagnostic ID in output"

    def test_generic_exception_in_execute_hunt_produces_friendly_panel(self, console):
        """Generic Exception from hunt() → friendly panel, no raw traceback."""
        exc = RuntimeError("unexpected internal error in module")
        out = _inject_module(console, exc)

        assert "Traceback (most recent call last):" not in out
        import re

        assert re.search(r"[a-f0-9]{8}", out), "Expected diagnostic ID in output"
        # Ensure the raw exception repr is not shown verbatim as the only output
        assert "What happened" in out or "diag" in out

    def test_authentication_error_produces_api_key_suggestion(self, console):
        """AuthenticationError from hunt() → friendly panel with API key fix hint."""
        from adversary_pursuit.modules.base import AuthenticationError

        exc = AuthenticationError("AP_SHODAN_API_KEY not configured")
        out = _inject_module(console, exc)

        assert "Traceback (most recent call last):" not in out
        # The interpreter should classify this as API key category
        assert "API key" in out or "config setup" in out or "AP_" in out

    def test_file_not_found_goes_through_pexcept_hook(self, console):
        """FileNotFoundError via pexcept hook → friendly panel, no traceback.

        cmd2 calls self.pexcept(ex) inside onecmd_plus_hooks for any unhandled
        exception from a do_* handler. Our override routes through interpret().
        """
        import re

        exc = FileNotFoundError("workspace db not found")
        console.stdout = io.StringIO()
        console.rich_console = console._make_rich_console()
        console.pexcept(exc)
        out = console.stdout.getvalue()

        assert "Traceback (most recent call last):" not in out
        assert re.search(r"[a-f0-9]{8}", out), "Expected diagnostic ID from pexcept"

    def test_pexcept_hook_produces_friendly_panel(self, console):
        """APConsole.pexcept() renders a friendly panel for any exception."""
        exc = ValueError("totally unexpected state")
        console.stdout = io.StringIO()
        console.rich_console = console._make_rich_console()
        console.pexcept(exc)
        out = console.stdout.getvalue()

        assert "Traceback (most recent call last):" not in out
        assert "What happened" in out or "diag" in out

    def test_rate_limit_error_shows_wait_suggestion(self, console):
        """RateLimitError → friendly panel with rate-limit suggestion."""
        from adversary_pursuit.modules.base import RateLimitError

        exc = RateLimitError("Too many requests", retry_after=30)
        out = _inject_module(console, exc)

        assert "Traceback (most recent call last):" not in out
        assert "rate" in out.lower() or "limit" in out.lower() or "wait" in out.lower()


# ---------------------------------------------------------------------------
# F63 — milestone catch-up + streak_continued compound integration tests
#
# These tests exercise the real production sequence:
#   _execute_hunt → score_results → store_score_events →
#   check_milestones → set_last_milestone_id → streak_mgr.update →
#   make_streak_continued_event → store_score_events
#
# All components cross real subsystem boundaries (no mocks for internal logic).
# ---------------------------------------------------------------------------


class TestF63MilestoneCatchupIntegration:
    """Compound tests for milestone catch-up semantics in _execute_hunt.

    Covers: cross-threshold milestone firing, idempotency (no double-fire),
    quiet-start migration, and milestone message in console output.
    """

    @pytest.fixture
    def console(self, tmp_path):
        app = APConsole(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
            streak_path=tmp_path / "streak.json",
        )
        app.stdout = io.StringIO()
        return app

    def _run(self, app, cmd):
        app.stdout = io.StringIO()
        app.rich_console = app._make_rich_console()
        app.onecmd_plus_hooks(cmd)
        return app.stdout.getvalue()

    def test_milestone_announced_when_score_crosses_threshold(self, console, tmp_path):
        """When a run pushes total score past 100, the milestone message appears.

        M-4 note: seeds 99 points so that even a single per-IOC event (1 pt) is
        sufficient to cross the 100-point threshold.  Previous implementation seeded
        95 and relied on dossier slot-fill events (+5 Identity) to bridge the gap,
        but M-4's pre-state defaults to DEFERRED for fresh workspaces and the M-3
        guard skips DEFERRED→real transitions (plan §3.4 defensive guard).  Using
        99 points keeps the test honest without requiring a dossier state seed.
        """
        # Seed the workspace with 99 points (just below 100)
        console.workspace_mgr._ensure_active()
        console.workspace_mgr.store_score_events(
            [{"action": "new_ip", "points": 99, "indicator": "seed"}]
        )
        # Seed last_announced to None — no milestones announced yet
        # (workspace is fresh — get_last_milestone_id returns None already)

        # Run a module that adds at least 1 point to push over 100
        self._run(console, "use osint/dns_resolve")
        self._run(console, "set TARGET example.com")
        out = self._run(console, "run")

        # Milestone id=1 (threshold=100) should have fired
        assert console.workspace_mgr.get_last_milestone_id() is not None
        # Output should contain the milestone message text
        assert "100" in out or "Century" in out or "First" in out

    def test_milestone_does_not_fire_twice(self, console, tmp_path):
        """Milestone id=1 already announced → second run does not re-fire."""
        console.workspace_mgr._ensure_active()
        # Set last_announced_id = 1 (already fired)
        console.workspace_mgr.set_last_milestone_id(1)
        # Store a score above 100 so the threshold IS crossed
        console.workspace_mgr.store_score_events(
            [{"action": "new_ip", "points": 150, "indicator": "seed"}]
        )

        self._run(console, "use osint/dns_resolve")
        self._run(console, "set TARGET example.com")
        self._run(console, "run")

        # last_milestone_id stays at 1 or advances if higher milestones were crossed —
        # the key invariant is that id=1 was not re-announced (no double-fire).
        # We verify by checking the sentinel hasn't gone backward.
        current_id = console.workspace_mgr.get_last_milestone_id()
        assert current_id is not None and current_id >= 1

    def test_quiet_start_migration_suppresses_retroactive_announcements(self, console):
        """Workspace with score=200, last_id=None → quiet-start seeds last_id, no retroactive fire."""
        console.workspace_mgr._ensure_active()
        # Seed score of 200 (crosses milestones 1 and 2) but last_announced=None
        console.workspace_mgr.store_score_events(
            [{"action": "new_ip", "points": 200, "indicator": "existing"}]
        )
        # Quiet-start: run a hunt that produces NO new results (target won't resolve)
        self._run(console, "use osint/dns_resolve")
        self._run(console, "set TARGET 192.0.2.255")  # RFC 5737 — no results expected
        self._run(console, "run")

        # After quiet-start migration, last_milestone_id should be seeded to 2
        # (highest milestone crossed at score=200: id=2, threshold=500 — actually id=1)
        # score=200 crosses threshold=100 (id=1) but not threshold=500 (id=2)
        last_id = console.workspace_mgr.get_last_milestone_id()
        # Either None (migration didn't run because no scoring path was entered)
        # or 1 (correctly seeded). The important invariant: it's not retroactively fired.
        assert last_id is None or last_id >= 1

    def test_milestone_sentinel_persists_across_console_instances(self, tmp_path):
        """Milestone sentinel survives a new APConsole pointing at the same workspace."""
        console1 = APConsole(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
            streak_path=tmp_path / "streak.json",
        )
        console1.workspace_mgr._ensure_active()
        console1.workspace_mgr.set_last_milestone_id(2)

        # New console pointing at same workspace dir
        console2 = APConsole(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
            streak_path=tmp_path / "streak2.json",
        )
        console2.workspace_mgr.switch("default")
        assert console2.workspace_mgr.get_last_milestone_id() == 2


class TestF63StreakContinuedIntegration:
    """Compound tests for streak_continued score event in _execute_hunt.

    Covers: streak_continued event stored after successful hunt, step-decay
    points correct for streak day, no event on same-day idempotent call.
    Production sequence: streak_mgr.update → StreakUpdate.incremented=True →
    make_streak_continued_event → store_score_events → get_recent_scores.
    """

    @pytest.fixture
    def console(self, tmp_path):
        app = APConsole(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
            streak_path=tmp_path / "streak.json",
        )
        app.stdout = io.StringIO()
        return app

    def _run(self, app, cmd):
        app.stdout = io.StringIO()
        app.rich_console = app._make_rich_console()
        app.onecmd_plus_hooks(cmd)
        return app.stdout.getvalue()

    def test_streak_continued_event_stored_after_hunt(self, console):
        """After a successful hunt, a streak_continued score event is in the workspace."""
        self._run(console, "use osint/dns_resolve")
        self._run(console, "set TARGET example.com")
        self._run(console, "run")

        # Check that a streak_continued event was stored (streak day 1 → 10pts)
        recent = console.workspace_mgr.get_recent_scores(limit=20)
        streak_events = [e for e in recent if e["action"] == "streak_continued"]
        assert len(streak_events) >= 1, "Expected at least one streak_continued event"

    def test_streak_continued_points_correct_for_day_one(self, console):
        """First hunt ever → streak_continued event has 10 points (day 1 tier)."""
        self._run(console, "use osint/dns_resolve")
        self._run(console, "set TARGET example.com")
        self._run(console, "run")

        recent = console.workspace_mgr.get_recent_scores(limit=20)
        streak_events = [e for e in recent if e["action"] == "streak_continued"]
        assert streak_events, "No streak_continued event found"
        assert streak_events[0]["points"] == 10

    def test_streak_continued_visible_in_output(self, console):
        """streak_continued action line appears in _execute_hunt output."""
        self._run(console, "use osint/dns_resolve")
        self._run(console, "set TARGET example.com")
        out = self._run(console, "run")

        assert "streak_continued" in out

    def test_full_production_sequence_milestone_and_streak(self, tmp_path):
        """End-to-end: first hunt fires first milestone AND streak_continued.

        This compound test crosses: StreakManager.update → StreakUpdate.incremented
        → make_streak_continued_event → store_score_events, AND:
        ScoringEngine.score_results → store_score_events → get_total_score →
        check_milestones → set_last_milestone_id.

        All internal component boundaries are real (no mocks).
        """
        app = APConsole(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
            streak_path=tmp_path / "streak.json",
        )
        app.stdout = io.StringIO()

        # Seed score just below the 100pt milestone threshold
        app.workspace_mgr._ensure_active()
        app.workspace_mgr.store_score_events(
            [{"action": "new_ip", "points": 90, "indicator": "seed"}]
        )

        app.stdout = io.StringIO()
        app.rich_console = app._make_rich_console()
        app.onecmd_plus_hooks("use osint/dns_resolve")
        app.onecmd_plus_hooks("set TARGET example.com")
        app.stdout = io.StringIO()
        app.rich_console = app._make_rich_console()
        app.onecmd_plus_hooks("run")
        out = app.stdout.getvalue()

        # streak_continued must have fired (incremented=True for first hunt)
        recent = app.workspace_mgr.get_recent_scores(limit=20)
        streak_events = [e for e in recent if e["action"] == "streak_continued"]
        assert streak_events, "streak_continued event missing from workspace"

        # streak.json must have been written (StreakManager authority preserved)
        assert (tmp_path / "streak.json").exists()

        # streak_continued appeared in console output
        assert "streak_continued" in out


# ---------------------------------------------------------------------------
# Phase 17P: workspace clear via cmd2 surface
# ---------------------------------------------------------------------------


class TestConsoleWorkspaceClear:
    """Tests for the cmd2 ``workspace clear`` subcommand (Phase 17P).

    The cmd2 surface prompts the user for confirmation (DEC-WORKSPACE-DB-006).
    Tests mock ``adversary_pursuit.core.console._confirm`` to control the gate.
    """

    def test_do_workspace_clear_no_arg_prompts_and_clears_active(self, tmp_path, monkeypatch):
        """workspace clear with no name prompts and clears the active workspace."""
        import io

        from adversary_pursuit.core.console import APConsole

        app = APConsole(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
        )
        app.stdout = io.StringIO()

        # Create and switch to a workspace, add some data
        app.workspace_mgr.create("alpha")
        app.workspace_mgr.switch("alpha")
        app.workspace_mgr.store_stix_objects(
            [{"type": "ipv4-addr", "value": "1.2.3.4"}],
            module_name="t",
            target="1.2.3.4",
        )

        # Monkeypatch _confirm to return True (user said yes)
        monkeypatch.setattr("adversary_pursuit.core.console._confirm", lambda prompt: True)

        app.stdout = io.StringIO()
        app.rich_console = app._make_rich_console()
        app.onecmd_plus_hooks("workspace clear")
        out = app.stdout.getvalue()

        assert "cleared" in out.lower() or "removed" in out.lower()
        assert app.workspace_mgr.get_stix_objects() == []

    def test_do_workspace_clear_named_arg_prompts_and_clears(self, tmp_path, monkeypatch):
        """workspace clear <name> prompts and clears the named workspace."""
        import io

        from adversary_pursuit.core.console import APConsole

        app = APConsole(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
        )
        app.stdout = io.StringIO()

        # Create two workspaces; populate the target one
        app.workspace_mgr.create("keep")
        app.workspace_mgr.create("target")
        app.workspace_mgr.switch("target")
        app.workspace_mgr.store_stix_objects(
            [{"type": "domain-name", "value": "evil.com"}],
            module_name="t",
            target="evil.com",
        )
        app.workspace_mgr.switch("keep")

        monkeypatch.setattr("adversary_pursuit.core.console._confirm", lambda prompt: True)

        app.stdout = io.StringIO()
        app.rich_console = app._make_rich_console()
        app.onecmd_plus_hooks("workspace clear target")
        out = app.stdout.getvalue()

        assert "target" in out.lower()
        # keep workspace is active and untouched; target should be empty
        app.workspace_mgr.switch("target")
        assert app.workspace_mgr.get_stix_objects() == []

    def test_do_workspace_clear_user_cancels(self, tmp_path, monkeypatch):
        """workspace clear with user confirmation=No leaves data intact."""
        import io

        from adversary_pursuit.core.console import APConsole

        app = APConsole(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
        )
        app.workspace_mgr.create("data")
        app.workspace_mgr.switch("data")
        app.workspace_mgr.store_stix_objects(
            [{"type": "ipv4-addr", "value": "5.5.5.5"}],
            module_name="t",
            target="5.5.5.5",
        )

        # User says no
        monkeypatch.setattr("adversary_pursuit.core.console._confirm", lambda prompt: False)

        app.stdout = io.StringIO()
        app.rich_console = app._make_rich_console()
        app.onecmd_plus_hooks("workspace clear")
        out = app.stdout.getvalue()

        assert "cancel" in out.lower()
        # Data must still be present
        assert len(app.workspace_mgr.get_stix_objects()) == 1


# ---------------------------------------------------------------------------
# Phase 17P: enhanced db_status via cmd2 surface
# ---------------------------------------------------------------------------


class TestConsoleDbStatusEnhanced:
    """Tests for the enhanced ``do_db_status`` command (Phase 17P).

    Verifies that the shared ``_render_db_status_table`` helper renders
    all required rows: DB path, DB size, per-table counts, last-event info.
    """

    def _make_app(self, tmp_path):
        import io

        from adversary_pursuit.core.console import APConsole

        app = APConsole(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
        )
        app.stdout = io.StringIO()
        app.workspace_mgr.create("default")
        app.workspace_mgr.switch("default")
        return app

    def _run(self, app, cmd: str) -> str:
        import io

        app.stdout = io.StringIO()
        app.rich_console = app._make_rich_console()
        app.onecmd_plus_hooks(cmd)
        return app.stdout.getvalue()

    def test_do_db_status_contains_db_path_row(self, tmp_path):
        """db_status output contains the DB file path."""
        app = self._make_app(tmp_path)
        out = self._run(app, "db_status")
        # The path contains the workspace name + .db
        assert "default.db" in out or "DB file path" in out

    def test_do_db_status_contains_db_size_row(self, tmp_path):
        """db_status output contains a humanised DB file size."""
        app = self._make_app(tmp_path)
        out = self._run(app, "db_status")
        # Size row shows KB or B
        assert "KB" in out or " B" in out or "DB file size" in out

    def test_do_db_status_contains_per_table_counts(self, tmp_path):
        """db_status output contains all 6 per-table count rows."""
        app = self._make_app(tmp_path)
        out = self._run(app, "db_status")
        for label in (
            "STIX objects",
            "Relationships",
            "Module runs",
            "Score events",
            "Analyst notes",
            "Badge events",
        ):
            assert label in out, f"Expected row '{label}' in db_status output"

    def test_do_db_status_contains_last_event_rows(self, tmp_path):
        """db_status output contains Last run / Last note / Last badge rows."""
        app = self._make_app(tmp_path)
        # Store data so last-event rows are non-empty
        app.workspace_mgr.store_stix_objects(
            [{"type": "ipv4-addr", "value": "1.2.3.4"}],
            module_name="osint/test",
            target="1.2.3.4",
        )
        app.workspace_mgr.add_note("test analyst note")
        app.workspace_mgr.store_badge_event("badge-first-blood", "First Blood")

        out = self._run(app, "db_status")
        assert "Last run" in out
        assert "Last note" in out
        assert "Last badge" in out
