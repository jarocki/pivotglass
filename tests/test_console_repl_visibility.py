"""Visibility regression tests for Phase 17R Rich console fix.

Verifies that Rich output (search results, show options tables, hunt results)
actually appears in the captured stdout after the _make_rich_console() fix
(DEC-CONSOLE-001: Console(file=self.stdout) instead of Console(file=StringIO())).

@decision DEC-CONSOLE-VISIBILITY-001
@title Regression tests for Rich output visibility through self.stdout
@status accepted
@rationale Prior to Phase 17R, _make_rich_console() created a dead io.StringIO
           buffer that was never shown to the user. These tests verify the fix:
           Rich Console(file=self.stdout) routes all table/panel output through
           cmd2's stdout channel. Tests also verify prompt is plain ap>/ap(<mod>)>
           with no mode prefix, and run_fail persona strings are absent from REPL.
"""

from __future__ import annotations

import io

import pytest

from adversary_pursuit.core.console import APConsole


@pytest.fixture
def console(tmp_path):
    """APConsole with temp dirs, stdout=StringIO for output capture."""
    app = APConsole(
        config_dir=tmp_path / "config",
        workspace_dir=tmp_path / "workspaces",
    )
    app.stdout = io.StringIO()
    return app


def run_cmd(app: APConsole, cmd: str) -> str:
    """Run a command and return all output from app.stdout."""
    app.stdout = io.StringIO()
    app.rich_console = app._make_rich_console()
    app.onecmd_plus_hooks(cmd)
    return app.stdout.getvalue()


class TestRichOutputVisibility:
    """Verify Rich output is not silently dropped into a dead buffer."""

    def test_search_output_is_visible(self, console):
        """search threatfox output should contain 'threatfox' in captured stdout."""
        out = run_cmd(console, "search threatfox")
        assert out.strip(), "Expected non-empty output from search"
        assert "threatfox" in out.lower()

    def test_show_options_output_is_visible(self, console):
        """show options after use should show TARGET or Options in output."""
        run_cmd(console, "use cti/threatfox")
        out = run_cmd(console, "show options")
        assert "TARGET" in out or "Options for" in out or "options" in out.lower()

    def test_repl_prompt_no_mode_prefix_at_init(self, console):
        """Prompt at init is 'ap> ' — no [main] or mode prefix."""
        assert console.prompt == "ap> "
        assert "[main]" not in console.prompt
        assert "default" not in console.prompt

    def test_repl_prompt_module_context_after_use(self, console):
        """After 'use cti/threatfox', prompt is 'ap(cti/threatfox)> '."""
        run_cmd(console, "use cti/threatfox")
        assert console.prompt == "ap(cti/threatfox)> "
        assert "[module]" not in console.prompt
        assert "[main]" not in console.prompt

    def test_repl_prompt_back_to_plain(self, console):
        """After 'back', prompt returns to 'ap> '."""
        run_cmd(console, "use cti/threatfox")
        run_cmd(console, "back")
        assert console.prompt == "ap> "

    def test_mode_command_does_not_change_prompt(self, console):
        """Switching modes does not inject a mode prefix into the REPL prompt."""
        run_cmd(console, "mode ninja")
        # Prompt must still be plain 'ap> ' — mode only affects ap chat surface
        assert console.prompt == "ap> "

    def test_run_fail_string_not_in_output(self, console, monkeypatch):
        """When hunt() raises, the mode-flavored run_fail string is NOT in output.

        The error panel from render_interactive is sufficient. The personality
        voice (run_fail) has been removed from _execute_hunt (Phase 17R).
        """
        from adversary_pursuit.modules.base import ModuleError

        class _RaisingModule:
            name = "test/raiser"
            description = "raises"
            author = "test"
            module_type = "osint"
            options: dict = {}
            accepts: tuple = ()

            def initialize(self, config):
                pass

            async def hunt(self, target, options):
                raise ModuleError("API key missing")

        class _Factory(_RaisingModule):
            def __init__(self):
                super().__init__() if hasattr(super(), "__init__") else None

        console.plugin_mgr._modules["test/raiser"] = _Factory
        run_cmd(console, "use test/raiser")
        run_cmd(console, "set TARGET 1.2.3.4")
        out = run_cmd(console, "run")

        # render_interactive uses mode.run_fail in the panel title (once is OK —
        # that's the error panel header). What we verify here is that run_fail is
        # NOT printed a second time as a raw standalone line after the panel.
        # Prior to Phase 17R there were two occurrences: one in the panel title
        # and one from `self.rich_console.print(self.mode_mgr.active.run_fail)`.
        # After the fix there should be at most one occurrence (in the panel).
        run_fail = console.mode_mgr.active.run_fail
        count = out.count(run_fail)
        assert count <= 1, (
            f"run_fail string '{run_fail}' appears {count} times — "
            "expected at most 1 (in panel title only, not as standalone duplicate)"
        )
