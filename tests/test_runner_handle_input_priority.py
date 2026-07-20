"""Tests for AgentRunner.handle_input priority order: verb → yield → LLM chat.

DEC-RUNNER-INPUT-PRIORITY-001: local REPL verbs intercept first, yield commands
second, LLM chat last. Tests verify:

  R-1: REPL verb input ('help') → dispatch_repl_verb called; yield + chat NOT called.
  R-2: Yield command ('stop') → dispatch_yield called; verb + chat NOT called.
  R-3: Unmatched input ('who owns 8.8.8.8') → chat() called; verb + yield NOT called.
  R-4: 'use suspicious.example' → verb path (no LLM call).
  R-5: 'use notarealhost' (not an IOC) → falls through to LLM.
  R-6: 'mode ninja' → verb path; no LLM.
  R-7: Return value is always str, never None.

Production sequence:
  user types text
  → TuiApplication._on_input_accepted (yield block removed; all goes to handle_input)
  → AgentRunner.handle_input(text, status_bar=live_pane)
  → parse_repl_verb → ReplVerb or None
  → parse_yield → YieldCommand or None
  → self.chat(text, status_bar=…)

@decision DEC-TEST-RUNNER-PRIORITY-001
@title Runner priority tests verify verb > yield > chat routing via AgentRunner + mocks
@status accepted
@rationale Priority routing is pure Python; no LLM or network call needed.
           Mock strategy:
           AgentRunner.chat → litellm.completion() (external LLM API). @mock-exempt.
           dispatch_repl_verb → phrase cache + mode/workspace state; mocked to isolate
           routing from gamification sub-system. @mock-exempt.
           dispatch_yield → phrase cache + EventBus; mocked to isolate routing. @mock-exempt.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from adversary_pursuit.agent.runner import AgentRunner


def _make_runner() -> AgentRunner:
    return AgentRunner(model="test/model")


# ---------------------------------------------------------------------------
# R-1: REPL verb wins over yield and chat
# ---------------------------------------------------------------------------


class TestReplVerbWins:
    """REPL verb match → dispatch_repl_verb called; yield and chat never called."""

    def test_help_calls_dispatch_repl_verb_not_chat(self):
        """'help' → dispatch_repl_verb; chat() must NOT be called.

        Production sequence: parse_repl_verb('help') returns ReplVerb('help', ())
        → dispatch_repl_verb → character-voiced help text.  LLM never reached.
        """
        runner = _make_runner()

        # @mock-exempt: dispatch_repl_verb → phrase cache + mode state; mocked to
        #               isolate routing from gamification sub-system setup.
        # @mock-exempt: AgentRunner.chat → litellm.completion() (external LLM boundary)
        # @mock-exempt: dispatch_yield → phrase cache + EventBus; mocked for routing isolation
        with (
            patch(
                "adversary_pursuit.agent.repl_verbs.dispatch_repl_verb",
                return_value="[help text]",
            ) as mock_verb,
            patch(
                "adversary_pursuit.agent.yield_commands.dispatch_yield",
            ) as mock_yield,
            patch(
                "adversary_pursuit.agent.runner.AgentRunner.chat",
                return_value="llm response",
            ) as mock_chat,
        ):
            result = runner.handle_input("help")

        # Only verb dispatch was called
        assert mock_verb.call_count == 1
        mock_yield.assert_not_called()
        mock_chat.assert_not_called()
        assert result == "[help text]"

    def test_question_mark_routes_to_verb_not_chat(self):
        runner = _make_runner()

        with (
            patch(
                "adversary_pursuit.agent.repl_verbs.dispatch_repl_verb",
                return_value="[help]",
            ) as mock_verb,
            patch(
                "adversary_pursuit.agent.runner.AgentRunner.chat",
            ) as mock_chat,
        ):
            result = runner.handle_input("?")

        assert mock_verb.call_count == 1
        mock_chat.assert_not_called()
        assert result == "[help]"

    def test_status_routes_to_verb_not_chat(self):
        runner = _make_runner()

        with (
            patch(
                "adversary_pursuit.agent.repl_verbs.dispatch_repl_verb",
                return_value="[status]",
            ) as mock_verb,
            patch("adversary_pursuit.agent.runner.AgentRunner.chat") as mock_chat,
        ):
            runner.handle_input("status")

        mock_verb.assert_called_once()
        mock_chat.assert_not_called()


# ---------------------------------------------------------------------------
# R-2: Yield command wins over chat (when no verb match)
# ---------------------------------------------------------------------------


class TestYieldWinsOverChat:
    """Yield command ('stop') → dispatch_yield called; chat NOT called."""

    def test_stop_calls_dispatch_yield_not_chat(self):
        """'stop' → parse_repl_verb returns None (not a REPL verb); parse_yield
        returns YieldCommand('stop', None) → dispatch_yield called. chat() NOT called.
        """
        runner = _make_runner()

        # @mock-exempt: AgentRunner.chat → litellm.completion() (external LLM boundary)
        # @mock-exempt: dispatch_yield → phrase cache + EventBus; mocked for routing isolation
        with (
            patch(
                "adversary_pursuit.agent.yield_commands.dispatch_yield",
                return_value="battery stopped",
            ) as mock_yield,
            patch(
                "adversary_pursuit.agent.runner.AgentRunner.chat",
                return_value="llm response",
            ) as mock_chat,
        ):
            result = runner.handle_input("stop")

        assert mock_yield.call_count == 1
        mock_chat.assert_not_called()
        assert result == "battery stopped"

    def test_focus_with_arg_calls_dispatch_yield(self):
        runner = _make_runner()

        with (
            patch(
                "adversary_pursuit.agent.yield_commands.dispatch_yield",
                return_value="focusing",
            ) as mock_yield,
            patch("adversary_pursuit.agent.runner.AgentRunner.chat") as mock_chat,
        ):
            runner.handle_input("focus whois_lookup")

        dispatched_cmd = mock_yield.call_args[0][0]
        assert dispatched_cmd.primitive == "focus"
        assert dispatched_cmd.argument == "whois_lookup"
        mock_chat.assert_not_called()


# ---------------------------------------------------------------------------
# R-3: Unmatched input falls through to chat
# ---------------------------------------------------------------------------


class TestUnmatchedFallsToChat:
    """Natural language queries fall through to chat(); neither verb nor yield called."""

    def test_natural_language_calls_chat(self):
        """'who owns 8.8.8.8' → parse_repl_verb None + parse_yield None → chat()."""
        runner = _make_runner()

        # @mock-exempt: AgentRunner.chat → litellm.completion() (external LLM boundary)
        with patch(
            "adversary_pursuit.agent.runner.AgentRunner.chat",
            return_value="Google LLC",
        ) as mock_chat:
            result = runner.handle_input("who owns 8.8.8.8")

        mock_chat.assert_called_once_with("who owns 8.8.8.8", status_bar=None)
        assert result == "Google LLC"

    def test_investigate_query_calls_chat(self):
        runner = _make_runner()

        with patch(
            "adversary_pursuit.agent.runner.AgentRunner.chat",
            return_value="here is the intel",
        ) as mock_chat:
            result = runner.handle_input("investigate 192.168.1.1 for malware")

        mock_chat.assert_called_once()
        assert result == "here is the intel"


# ---------------------------------------------------------------------------
# R-4: 'use <ioc>' → verb path; no LLM
# ---------------------------------------------------------------------------


class TestUseSuspiciousIocDoesNotCallChat:
    """'use suspicious.example' → parse_repl_verb matches (domain IOC) → verb dispatch."""

    def test_use_target_does_not_call_chat(self):
        runner = _make_runner()

        # @mock-exempt: dispatch_repl_verb → phrase cache + workspace state; mocked for isolation
        # @mock-exempt: AgentRunner.chat → litellm.completion() (external LLM boundary)
        with (
            patch(
                "adversary_pursuit.agent.repl_verbs.dispatch_repl_verb",
                return_value="Target set: suspicious.example",
            ) as mock_verb,
            patch("adversary_pursuit.agent.runner.AgentRunner.chat") as mock_chat,
        ):
            result = runner.handle_input("use suspicious.example")

        mock_verb.assert_called_once()
        mock_chat.assert_not_called()
        assert result == "Target set: suspicious.example"

    def test_use_ip_does_not_call_chat(self):
        runner = _make_runner()

        with (
            patch(
                "adversary_pursuit.agent.repl_verbs.dispatch_repl_verb",
                return_value="Target set: 203.0.113.1",
            ) as mock_verb,
            patch("adversary_pursuit.agent.runner.AgentRunner.chat") as mock_chat,
        ):
            runner.handle_input("use 203.0.113.1")

        mock_verb.assert_called_once()
        mock_chat.assert_not_called()


# ---------------------------------------------------------------------------
# R-5: 'use notarealhost' (not an IOC) → falls through to LLM
# ---------------------------------------------------------------------------


class TestUseGibberishFallsToLLM:
    """'use notarealhost' — not an IOC — routes to LLM."""

    def test_use_non_ioc_falls_through_to_chat(self):
        runner = _make_runner()

        with (
            patch(
                "adversary_pursuit.agent.runner.AgentRunner.chat",
                return_value="here is info about notarealhost",
            ) as mock_chat,
        ):
            runner.handle_input("use notarealhost")

        mock_chat.assert_called_once()
        assert "notarealhost" in mock_chat.call_args[0][0]


# ---------------------------------------------------------------------------
# R-6: 'mode ninja' → verb path; no LLM
# ---------------------------------------------------------------------------


class TestModeVerbDoesNotCallChat:
    """'mode ninja' → parse_repl_verb matches → verb dispatch; no LLM."""

    def test_mode_switch_does_not_call_chat(self):
        runner = _make_runner()

        with (
            patch(
                "adversary_pursuit.agent.repl_verbs.dispatch_repl_verb",
                return_value="ninja mode engaged",
            ) as mock_verb,
            patch("adversary_pursuit.agent.runner.AgentRunner.chat") as mock_chat,
        ):
            runner.handle_input("mode ninja")

        mock_verb.assert_called_once()
        mock_chat.assert_not_called()

    def test_mode_switch_updates_llm_persona_and_live_pane(self):
        """A local mode switch changes voice authority, not only TUI color."""
        runner = _make_runner()
        status = MagicMock()

        runner.handle_input("mode ninja", status_bar=status)

        assert runner._character == "ninja"
        assert runner.system_prompt.startswith("Character mode: ninja\n")
        status.set_character.assert_called_once_with("ninja")

    @pytest.mark.parametrize("text", ["mode", "mode list"])
    def test_mode_list_is_local_stable_and_does_not_call_llm(self, text: str):
        runner = _make_runner()
        with patch("adversary_pursuit.agent.runner.AgentRunner.chat") as mock_chat:
            first = runner.handle_input(text)
            second = runner.handle_input(text)
        mock_chat.assert_not_called()
        assert first == second
        assert first.startswith("Character modes (* active)\n")


# ---------------------------------------------------------------------------
# R-7: Return value is always str, never None
# ---------------------------------------------------------------------------


class TestHandleInputAlwaysReturnsStr:
    """handle_input must return str in every code path (TUI appends to scrollback)."""

    def test_verb_path_returns_str(self):
        runner = _make_runner()
        with patch(
            "adversary_pursuit.agent.repl_verbs.dispatch_repl_verb",
            return_value="ok",
        ):
            result = runner.handle_input("help")
        assert isinstance(result, str)

    def test_yield_path_returns_str(self):
        runner = _make_runner()
        with patch(
            "adversary_pursuit.agent.yield_commands.dispatch_yield",
            return_value="stopped",
        ):
            result = runner.handle_input("stop")
        assert isinstance(result, str)

    def test_chat_path_returns_str(self):
        runner = _make_runner()
        with patch(
            "adversary_pursuit.agent.runner.AgentRunner.chat",
            return_value="answer",
        ):
            result = runner.handle_input("who is 8.8.8.8?")
        assert isinstance(result, str)

    def test_empty_chat_response_still_returns_str(self):
        runner = _make_runner()
        with patch(
            "adversary_pursuit.agent.runner.AgentRunner.chat",
            return_value="",
        ):
            result = runner.handle_input("mystery input xyz")
        assert isinstance(result, str)
