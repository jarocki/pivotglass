"""Tests for the 'report' meta-command in agent/chat.py (M-8 post-cleanup).

M-8 removes the --style flag and classic interview path from the chat report
meta-command (DEC-68-DOSSIER-REFRAME-008 / DEC-M8-CLEANUP-001).
Since v1.5.0 (#50) the meta-command is the shared `report` command
(reports/commands.py); bare 'report' and 'report generate' preview the
investigation report.

@decision DEC-TEST-M8-CHAT-REPORT-001
@title test_chat_report_metacommand verifies M-8 dossier-only report meta-command
@status accepted
@rationale After M-8 the chat 'report' meta-command has one path: dossier renderer.
           Tests confirm: dossier report renders on 'report', 'report generate',
           unknown sub-commands produce a usage message, and no --style flag exists.
           No mocks — uses the real report preview via unit import.
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
    from pivotglass.agent.tools import ToolContext

    return ToolContext(workspace_dir=tmp_path / "workspaces")


# ---------------------------------------------------------------------------
# The report preview the chat meta-command and the LLM tool share
# ---------------------------------------------------------------------------


class TestReportPreview:
    """_execute_preview_report renders through reports/commands.py."""

    def test_signature_has_no_style_param(self):
        from pivotglass.agent.tools import _execute_preview_report

        assert list(inspect.signature(_execute_preview_report).parameters) == ["ctx", "report_type"]

    def test_returns_the_investigation_report(self, ctx):
        from pivotglass.agent.tools import _execute_preview_report

        result = _execute_preview_report(ctx)
        assert "## Dossier State" in result
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
            / "pivotglass"
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
            / "pivotglass"
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
            / "pivotglass"
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
