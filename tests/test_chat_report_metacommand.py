"""Tests for the 'report' meta-command in agent/chat.py (M-8 post-cleanup).

M-8 removes the --style flag and classic interview path from the chat report
meta-command (DEC-68-DOSSIER-REFRAME-008 / DEC-M8-CLEANUP-001).
The sole behaviour after M-8: bare 'report' and 'report generate' both render
the dossier report via _execute_generate_dossier_report().

@decision DEC-TEST-M8-CHAT-REPORT-001
@title test_chat_report_metacommand verifies M-8 dossier-only report meta-command
@status accepted
@rationale After M-8 the chat 'report' meta-command has one path: dossier renderer.
           Tests confirm: dossier report renders on 'report', 'report generate',
           unknown sub-commands produce a usage message, and no --style flag exists.
           No mocks — uses real _execute_generate_dossier_report via unit import.
"""

from __future__ import annotations

import inspect

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ctx(tmp_path):
    """Minimal ToolContext pointed at a fresh workspace."""
    from adversary_pursuit.agent.tools import ToolContext

    return ToolContext(workspace_dir=tmp_path / "workspaces")


# ---------------------------------------------------------------------------
# Unit tests for _execute_generate_dossier_report (sole renderer post-M-8)
# ---------------------------------------------------------------------------


class TestExecuteGenerateDossierReportPostM8:
    """_execute_generate_dossier_report is parameterless and renders dossier report."""

    def test_parameterless_signature(self):
        """_execute_generate_dossier_report accepts only ctx — no style param."""
        from adversary_pursuit.agent.tools import _execute_generate_dossier_report

        sig = inspect.signature(_execute_generate_dossier_report)
        params = list(sig.parameters.keys())
        assert params == ["ctx"], (
            f"Expected only 'ctx' parameter, got: {params}. "
            "style= was removed at M-8 (DEC-M8-CLEANUP-002)."
        )

    def test_raises_on_style_kwarg(self, ctx):
        """Passing style= raises TypeError (parameter does not exist)."""
        from adversary_pursuit.agent.tools import _execute_generate_dossier_report

        with pytest.raises(TypeError):
            _execute_generate_dossier_report(ctx, style="dossier")  # type: ignore[call-arg]

    def test_returns_dossier_markdown(self, ctx):
        """Calling without style returns dossier Markdown."""
        from adversary_pursuit.agent.tools import _execute_generate_dossier_report

        result = _execute_generate_dossier_report(ctx)
        assert isinstance(result, str)
        assert "## Dossier State" in result

    def test_no_classic_report_format(self, ctx):
        """Dossier renderer does NOT produce the classic interview header."""
        from adversary_pursuit.agent.tools import _execute_generate_dossier_report

        result = _execute_generate_dossier_report(ctx)
        assert "## Interview Notes" not in result


# ---------------------------------------------------------------------------
# Audit: --style flag is absent from chat.py report meta-command
# ---------------------------------------------------------------------------


class TestNoChatStyleFlag:
    """--style flag and classic branch are absent from agent/chat.py post-M-8."""

    def test_no_style_flag_in_chat_report_block(self):
        """The string '--style' does not appear in agent/chat.py."""
        from pathlib import Path

        chat_path = (
            Path(__file__).parent.parent
            / "src"
            / "adversary_pursuit"
            / "agent"
            / "chat.py"
        )
        source = chat_path.read_text(encoding="utf-8")
        assert "--style" not in source, (
            "Found '--style' in agent/chat.py — should have been removed at M-8."
        )

    def test_no_report_style_variable_in_chat(self):
        """The 'report_style' variable is absent from agent/chat.py."""
        from pathlib import Path

        chat_path = (
            Path(__file__).parent.parent
            / "src"
            / "adversary_pursuit"
            / "agent"
            / "chat.py"
        )
        source = chat_path.read_text(encoding="utf-8")
        assert "report_style" not in source, (
            "Found 'report_style' in agent/chat.py — should have been removed at M-8."
        )

    def test_no_classic_report_imports_in_chat(self):
        """_execute_generate_report and _execute_start_report_interview are not imported."""
        from pathlib import Path

        chat_path = (
            Path(__file__).parent.parent
            / "src"
            / "adversary_pursuit"
            / "agent"
            / "chat.py"
        )
        source = chat_path.read_text(encoding="utf-8")
        assert "_execute_generate_report" not in source, (
            "Found '_execute_generate_report' in chat.py — classic import survived M-8 cleanup."
        )
        assert "_execute_start_report_interview" not in source, (
            "Found '_execute_start_report_interview' in chat.py — classic import survived M-8."
        )
