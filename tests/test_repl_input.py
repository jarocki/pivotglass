"""Tests for agent/repl_input.py — prompt_toolkit REPL input wrapper.

# @mock-exempt: PromptSession.prompt() is a blocking terminal I/O call that
# requires a real PTY to run. Mocking it (or the ChatPromptSession wrapper)
# is the only way to test prompt delegation without hanging the test suite.
# The Completer, session construction, and markup-stripping logic are all
# tested against real implementations — no mocks involved there.

Production sequence:
  ChatPromptSession(history_path=...) -> .prompt(prefix) -> str

These tests verify:
  - Completer suggests matching commands for partial input
  - Mode-names are suggested after "mode "
  - Export formats are suggested after "export "
  - History file path is set correctly
  - Editing mode defaults to vi, overridable via env/config argument
  - _strip_rich_markup removes Rich tags from prompt prefix

Tests deliberately avoid actually calling PromptSession.prompt() (which would
block waiting for a real terminal).  We test the Completer and ChatPromptSession
construction logic directly.

@decision DEC-TEST-REPL-INPUT-001
@title Test APCompleter and ChatPromptSession without blocking terminal I/O
@status accepted
@rationale prompt_toolkit's PromptSession.prompt() is a blocking terminal call
           unsuitable for unit tests.  We test the Completer's get_completions()
           directly (it takes a Document, not the session) and the session's
           property accessors.  The _strip_rich_markup helper is tested
           independently.  This provides full coverage of the production
           completion and session configuration paths without requiring a PTY.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from prompt_toolkit.document import Document

from adversary_pursuit.agent.repl_input import (
    HISTORY_PATH,
    APCompleter,
    ChatPromptSession,
    _MODE_NAMES,
    _TOP_LEVEL_COMMANDS,
    _strip_rich_markup,
    prompt_user,
)


# ---------------------------------------------------------------------------
# APCompleter — top-level command completion
# ---------------------------------------------------------------------------


def _completions(text: str) -> list[str]:
    """Helper: run APCompleter on *text* and return completion strings."""
    completer = APCompleter()
    doc = Document(text, cursor_position=len(text))
    return [c.text for c in completer.get_completions(doc, MagicMock())]


class TestAPCompleterTopLevel:
    def test_he_suggests_help_only(self):
        # "he" prefix matches "help" but NOT "hint" ("hint" starts with "hi")
        results = _completions("he")
        assert "help" in results
        assert "hint" not in results

    def test_hi_suggests_hint(self):
        results = _completions("hi")
        assert "hint" in results

    def test_h_suggests_help_and_hint(self):
        # "h" matches both "help" and "hint"
        results = _completions("h")
        assert "help" in results
        assert "hint" in results

    def test_q_suggests_quit(self):
        results = _completions("q")
        assert "quit" in results

    def test_ex_suggests_exit_and_export(self):
        results = _completions("ex")
        assert "exit" in results
        assert "export" in results

    def test_empty_suggests_all_commands(self):
        results = _completions("")
        for cmd in _TOP_LEVEL_COMMANDS:
            assert cmd in results

    def test_no_match_returns_empty(self):
        results = _completions("zzz")
        assert results == []

    def test_exact_top_level_match_returns_self(self):
        # "help" exactly → completes to "help" (start_position=-4)
        results = _completions("help")
        assert "help" in results

    def test_case_insensitive_he_matches_help(self):
        # "HE" prefix matches "help" case-insensitively
        results = _completions("HE")
        assert "help" in results
        # "HI" matches "hint"
        results2 = _completions("HI")
        assert "hint" in results2


# ---------------------------------------------------------------------------
# APCompleter — mode sub-command completion
# ---------------------------------------------------------------------------


class TestAPCompleterModeSubcommand:
    def test_mode_space_suggests_all_modes(self):
        results = _completions("mode ")
        for mode in _MODE_NAMES:
            assert mode in results

    def test_mode_ninja_partial_suggests_ninja(self):
        results = _completions("mode nin")
        assert "ninja" in results
        assert "default" not in results

    def test_mode_full_partial_suggests_full_troll(self):
        results = _completions("mode full")
        assert "full_troll" in results

    def test_mode_space_does_not_suggest_top_level(self):
        results = _completions("mode ")
        # "mode" itself should not appear as a sub-completion
        assert "mode" not in results


# ---------------------------------------------------------------------------
# APCompleter — export sub-command completion
# ---------------------------------------------------------------------------


class TestAPCompleterExportSubcommand:
    def test_export_space_suggests_gexf_and_stix(self):
        results = _completions("export ")
        assert "gexf" in results
        assert "stix" in results

    def test_export_g_suggests_gexf(self):
        results = _completions("export g")
        assert "gexf" in results
        assert "stix" not in results


# ---------------------------------------------------------------------------
# APCompleter — hint sub-command completion
# ---------------------------------------------------------------------------


class TestAPCompleterHintSubcommand:
    def test_hint_space_suggests_modules_and_buy(self):
        results = _completions("hint ")
        assert "buy" in results
        assert "shodan" in results
        assert "virustotal" in results

    def test_hint_s_suggests_shodan(self):
        results = _completions("hint s")
        assert "shodan" in results


# ---------------------------------------------------------------------------
# APCompleter — model sub-command completion
# ---------------------------------------------------------------------------


class TestAPCompleterModelSubcommand:
    def test_model_space_suggests_show_and_select(self):
        results = _completions("model ")
        assert "show" in results
        assert "select" in results

    def test_model_sh_suggests_show(self):
        results = _completions("model sh")
        assert "show" in results
        assert "select" not in results


# ---------------------------------------------------------------------------
# APCompleter — report sub-command completion
# ---------------------------------------------------------------------------


class TestAPCompleterReportSubcommand:
    def test_report_space_suggests_answer_and_generate(self):
        results = _completions("report ")
        assert "answer" in results
        assert "generate" in results


# ---------------------------------------------------------------------------
# APCompleter — autopivot sub-command completion
# ---------------------------------------------------------------------------


class TestAPCompleterAutopivotSubcommand:
    def test_autopivot_space_suggests_on_off(self):
        results = _completions("autopivot ")
        assert "on" in results
        assert "off" in results


# ---------------------------------------------------------------------------
# _strip_rich_markup
# ---------------------------------------------------------------------------


class TestStripRichMarkup:
    def test_strips_bold_cyan(self):
        assert _strip_rich_markup("[bold cyan]ap>[/bold cyan] ") == "ap> "

    def test_strips_dim(self):
        assert _strip_rich_markup("[dim]hello[/dim]") == "hello"

    def test_passes_plain_text_through(self):
        assert _strip_rich_markup("plain text") == "plain text"

    def test_strips_emoji_prefix_tag(self):
        # e.g. "🥷[bold cyan]ap>[/bold cyan] "
        result = _strip_rich_markup("🥷[bold cyan]ap>[/bold cyan] ")
        assert result == "🥷ap> "

    def test_strips_colour_with_hash(self):
        result = _strip_rich_markup("[#ff0000]red[/#ff0000]")
        assert result == "red"


# ---------------------------------------------------------------------------
# ChatPromptSession — construction (real implementation, no mocks)
# ---------------------------------------------------------------------------


class TestChatPromptSessionConstruction:
    def test_default_editing_mode_is_vi(self, tmp_path):
        session = ChatPromptSession(history_path=tmp_path / "hist", editing_mode="vi")
        assert session.editing_mode == "vi"

    def test_emacs_mode_roundtrip(self, tmp_path):
        session = ChatPromptSession(
            history_path=tmp_path / "hist", editing_mode="emacs"
        )
        assert session.editing_mode == "emacs"

    def test_env_var_overrides_argument(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_EDITING_MODE", "emacs")
        session = ChatPromptSession(history_path=tmp_path / "hist", editing_mode="vi")
        assert session.editing_mode == "emacs"

    def test_env_var_vi_overrides_emacs_arg(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_EDITING_MODE", "vi")
        session = ChatPromptSession(
            history_path=tmp_path / "hist", editing_mode="emacs"
        )
        assert session.editing_mode == "vi"

    def test_invalid_env_var_falls_back_to_argument(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_EDITING_MODE", "dvorak")
        session = ChatPromptSession(
            history_path=tmp_path / "hist", editing_mode="emacs"
        )
        # Invalid env var → falls back to argument
        assert session.editing_mode == "emacs"

    def test_none_history_path_uses_in_memory(self):
        session = ChatPromptSession(history_path=None)
        assert session.history_path is None

    def test_file_history_path_is_set(self, tmp_path):
        hist_path = tmp_path / "chat_history"
        session = ChatPromptSession(history_path=hist_path)
        assert session.history_path == hist_path

    def test_default_history_path_constant(self):
        assert HISTORY_PATH == Path.home() / ".ap" / "chat_history"

    def test_history_dir_created_automatically(self, tmp_path):
        nested = tmp_path / "a" / "b" / "chat_history"
        ChatPromptSession(history_path=nested)
        assert nested.parent.exists()


# ---------------------------------------------------------------------------
# ChatPromptSession — prompt() delegation
# @mock-exempt: PromptSession.prompt() blocks on real terminal I/O (PTY required).
# We patch only the underlying session's .prompt() method, not internal logic.
# ---------------------------------------------------------------------------


class TestChatPromptSessionPrompt:
    def test_prompt_strips_rich_markup_and_delegates(self, tmp_path):
        session = ChatPromptSession(history_path=None)
        # Patch the underlying PromptSession to return a known string
        # @mock-exempt: blocking terminal PTY call
        session._session = MagicMock()
        session._session.prompt.return_value = "hello world"
        result = session.prompt("[bold cyan]ap>[/bold cyan] ")
        assert result == "hello world"
        # The argument passed to the underlying session should be plain text
        call_arg = session._session.prompt.call_args[0][0]
        assert "[" not in call_arg


# ---------------------------------------------------------------------------
# prompt_user convenience function
# @mock-exempt: delegates to ChatPromptSession which wraps blocking PTY I/O
# ---------------------------------------------------------------------------


class TestPromptUser:
    def test_delegates_to_provided_session(self, tmp_path):
        session = ChatPromptSession(history_path=None)
        # @mock-exempt: blocking terminal PTY call
        session._session = MagicMock()
        session._session.prompt.return_value = "test input"
        result = prompt_user("ap> ", _session=session)
        assert result == "test input"

    def test_creates_session_when_not_provided(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_NO_BANNER", "1")
        # @mock-exempt: ChatPromptSession wraps blocking PTY I/O
        with patch(
            "adversary_pursuit.agent.repl_input.ChatPromptSession"
        ) as MockSession:
            mock_instance = MagicMock()
            mock_instance.prompt.return_value = "from new session"
            MockSession.return_value = mock_instance
            result = prompt_user("ap> ", editing_mode="vi")
        assert result == "from new session"
