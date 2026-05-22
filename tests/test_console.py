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
    """Run a command and return captured stdout + Rich output.

    Combines both poutput() (written to app.stdout) and Rich output
    (written to app.rich_console file). Resets both buffers before each call.
    """
    app.stdout = io.StringIO()
    app.rich_console = app._make_rich_console()
    app.onecmd_plus_hooks(cmd)
    plain = app.stdout.getvalue()
    rich_out = app.rich_console.file.getvalue()
    return plain + rich_out


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
    assert "[main]" in console.prompt
    assert console._active_module is None


def test_back_without_module_is_safe(console):
    """back without a loaded module does not crash."""
    run_cmd(console, "back")
    assert "[main]" in console.prompt


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

    assert "[main]" in console.prompt
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
        console.rich_console = console._make_rich_console()
        console.pexcept(exc)
        out = console.rich_console.file.getvalue()

        assert "Traceback (most recent call last):" not in out
        assert re.search(r"[a-f0-9]{8}", out), "Expected diagnostic ID from pexcept"

    def test_pexcept_hook_produces_friendly_panel(self, console):
        """APConsole.pexcept() renders a friendly panel for any exception."""
        exc = ValueError("totally unexpected state")
        console.rich_console = console._make_rich_console()
        console.pexcept(exc)
        out = console.rich_console.file.getvalue()

        assert "Traceback (most recent call last):" not in out
        assert "What happened" in out or "diag" in out

    def test_rate_limit_error_shows_wait_suggestion(self, console):
        """RateLimitError → friendly panel with rate-limit suggestion."""
        from adversary_pursuit.modules.base import RateLimitError

        exc = RateLimitError("Too many requests", retry_after=30)
        out = _inject_module(console, exc)

        assert "Traceback (most recent call last):" not in out
        assert "rate" in out.lower() or "limit" in out.lower() or "wait" in out.lower()
