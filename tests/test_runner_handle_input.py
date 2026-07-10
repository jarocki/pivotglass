"""Tests for AgentRunner.handle_input — TUI input routing (DEC-RUNNER-HANDLE-INPUT-001).

The handle_input method is the single authoritative entry point for TUI input.
It routes yield commands through dispatch_yield and all other text through
chat(). Tests cover:

  C-1: yield command input → dispatch_yield called, chat() NOT called
  C-2: regular text → chat() called
  C-3: malformed yield-shaped input (e.g. "focus" with no arg) → chat() called, no crash
  C-4: return value is always str, never None
  C-5: TuiApplication._on_input_accepted calls handle_input with status_bar=live_pane

Production sequence:
  user types text → TuiApplication._on_input_accepted →
    runner.handle_input(text, status_bar=live_pane) →
      [yield path] dispatch_yield(cmd, None, bus, character) → feedback str
      [llm path]   self.chat(text, status_bar=status_bar) → llm response str

@decision DEC-TEST-RUNNER-HANDLE-INPUT-001
@title Tests exercise handle_input routing contract via real AgentRunner + LLM mock
@status accepted
@rationale handle_input routing logic is pure Python — no LLM or network call needed
           to verify yield vs non-yield branching.

           Mock strategy (all mocks are at genuine external or sub-system boundaries):

           AgentRunner.chat: chat() calls litellm.completion() which is an external
           LLM API boundary (network, API keys). Mocking chat() at the class level
           keeps the LLM out of routing tests while exercising the real handle_input
           routing logic. @mock-exempt applies.

           dispatch_yield: publishes TUI events and reads the phrases cache which
           requires the full gamification sub-system to be warm. For C-1 tests
           that only verify routing (yield vs LLM), dispatch_yield is mocked to
           isolate the routing decision from phrase-cache setup. @mock-exempt applies.

           sys.stdin.isatty: OS/TTY boundary — no terminal available in CI.
           TuiApplication._build_app: requires a real prompt_toolkit terminal
           session with a live pty. Both @mock-exempt.

           FakeRunner.handle_input as MagicMock: FakeRunner is a test-internal
           duck-type stub (not the production class under test). MagicMock on
           handle_input lets us assert call args without running the real LLM.
           The real routing contract is covered by TestHandleInputYieldRouting
           and TestHandleInputChatRouting which use real AgentRunner.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from adversary_pursuit.agent.runner import AgentRunner
from adversary_pursuit.agent.tui.application import TuiApplication
from adversary_pursuit.agent.tui.events import EventBus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runner() -> AgentRunner:
    """Return a real AgentRunner with model fixed to avoid env lookup."""
    return AgentRunner(model="test/model")


# ---------------------------------------------------------------------------
# C-1: yield command routes to dispatch_yield, NOT chat()
# ---------------------------------------------------------------------------


class TestHandleInputYieldRouting:
    """Yield commands are intercepted and routed to dispatch_yield."""

    def test_handle_input_routes_stop_to_dispatch_yield(self):
        """'stop' → dispatch_yield called; chat() must NOT be called.

        Production sequence: handle_input('stop') → parse_yield('stop') returns
        YieldCommand('stop', None) → dispatch_yield(cmd, None, bus, character)
        → character-voiced string returned.  _call_llm is never reached.
        """
        runner = _make_runner()

        # @mock-exempt: AgentRunner.chat → litellm.completion() (external LLM API boundary)
        # @mock-exempt: dispatch_yield → phrase cache + EventBus pub sub; mocked to
        #               isolate the routing decision from gamification sub-system setup.
        with (
            patch(
                "adversary_pursuit.agent.runner.AgentRunner.chat",
                return_value="llm response",
            ) as patched_chat,
            patch(
                "adversary_pursuit.agent.yield_commands.dispatch_yield",
                return_value="acknowledged",
            ) as mock_dispatch,
        ):
            result = runner.handle_input("stop")

            # dispatch_yield must have been called once
            assert mock_dispatch.call_count == 1
            dispatched_cmd = mock_dispatch.call_args[0][0]
            assert dispatched_cmd.primitive == "stop"
            assert dispatched_cmd.argument is None

            # chat() must NOT have been called
            patched_chat.assert_not_called()

        assert result == "acknowledged"

    def test_handle_input_routes_focus_with_arg_to_dispatch_yield(self):
        """'focus whois_lookup' → dispatch_yield with YieldCommand('focus', 'whois_lookup')."""
        runner = _make_runner()

        # @mock-exempt: AgentRunner.chat → litellm.completion() (external LLM API boundary)
        # @mock-exempt: dispatch_yield → phrase cache + EventBus; mocked for routing isolation
        with (
            patch(
                "adversary_pursuit.agent.runner.AgentRunner.chat",
                return_value="llm response",
            ) as patched_chat,
            patch(
                "adversary_pursuit.agent.yield_commands.dispatch_yield",
                return_value="focusing",
            ) as mock_dispatch,
        ):
            result = runner.handle_input("focus whois_lookup")

        dispatched_cmd = mock_dispatch.call_args[0][0]
        assert dispatched_cmd.primitive == "focus"
        assert dispatched_cmd.argument == "whois_lookup"
        patched_chat.assert_not_called()
        assert result == "focusing"


# ---------------------------------------------------------------------------
# C-2: regular text routes to chat()
# ---------------------------------------------------------------------------


class TestHandleInputChatRouting:
    """Non-yield input is forwarded to chat()."""

    def test_handle_input_routes_regular_text_to_chat(self):
        """'who is 8.8.8.8?' → chat() called with that text; dispatch_yield NOT called.

        Production sequence: handle_input('who is 8.8.8.8?') →
        parse_yield returns None → self.chat('who is 8.8.8.8?') → response str.
        """
        runner = _make_runner()

        # @mock-exempt: AgentRunner.chat → litellm.completion() (external LLM API boundary)
        # @mock-exempt: dispatch_yield → phrase cache + EventBus; mocked for routing isolation
        with (
            patch(
                "adversary_pursuit.agent.runner.AgentRunner.chat",
                return_value="8.8.8.8 is Google DNS",
            ) as mock_chat,
            patch(
                "adversary_pursuit.agent.yield_commands.dispatch_yield",
            ) as mock_dispatch,
        ):
            result = runner.handle_input("who is 8.8.8.8?")

        mock_chat.assert_called_once_with("who is 8.8.8.8?", status_bar=None)
        mock_dispatch.assert_not_called()
        assert result == "8.8.8.8 is Google DNS"

    def test_handle_input_passes_status_bar_to_chat(self):
        """status_bar kwarg is forwarded to chat() when provided."""
        runner = _make_runner()
        # @mock-exempt: _StatusHook protocol implementor — any duck-type satisfies
        #               the protocol; MagicMock avoids importing LivePane TTY deps.
        fake_hook = MagicMock()  # @mock-exempt: _StatusHook protocol duck-type

        # @mock-exempt: AgentRunner.chat → litellm.completion() (external LLM API boundary)
        with patch(
            "adversary_pursuit.agent.runner.AgentRunner.chat",
            return_value="response with hook",
        ) as mock_chat:
            result = runner.handle_input("query something", status_bar=fake_hook)

        mock_chat.assert_called_once_with("query something", status_bar=fake_hook)
        assert result == "response with hook"


# ---------------------------------------------------------------------------
# C-3: malformed yield-shaped input → chat(), no exception
# ---------------------------------------------------------------------------


class TestHandleInputMalformedYield:
    """Yield-shaped but incomplete input must route to chat, never crash."""

    def test_handle_input_routes_focus_no_arg_to_chat(self):
        """'focus' (missing required arg) → parse_yield returns None → chat().

        This is the graceful-degradation path: a user who types 'focus' without
        an argument gets an LLM response rather than a crash or silent drop.
        Sacred Practice 5: fail-graceful on user-typed ambiguity.
        """
        runner = _make_runner()

        # @mock-exempt: AgentRunner.chat → litellm.completion() (external LLM API boundary)
        # @mock-exempt: dispatch_yield → phrase cache + EventBus; mocked for routing isolation
        with (
            patch(
                "adversary_pursuit.agent.runner.AgentRunner.chat",
                return_value="I'm not sure what to focus on",
            ) as mock_chat,
            patch(
                "adversary_pursuit.agent.yield_commands.dispatch_yield",
            ) as mock_dispatch,
        ):
            # Must not raise
            result = runner.handle_input("focus")

        mock_chat.assert_called_once_with("focus", status_bar=None)
        mock_dispatch.assert_not_called()
        assert isinstance(result, str)

    def test_handle_input_routes_add_no_arg_to_chat(self):
        """'add' alone (missing arg) → chat(), no exception."""
        runner = _make_runner()

        # @mock-exempt: AgentRunner.chat → litellm.completion() (external LLM API boundary)
        with (
            patch(
                "adversary_pursuit.agent.runner.AgentRunner.chat",
                return_value="what do you want to add?",
            ) as mock_chat,
        ):
            result = runner.handle_input("add")

        mock_chat.assert_called_once()
        assert isinstance(result, str)

    def test_handle_input_stop_with_trailing_text_routes_to_chat(self):
        """'stop that guy' — 'stop' with trailing tokens → parse_yield None → chat()."""
        runner = _make_runner()

        # @mock-exempt: AgentRunner.chat → litellm.completion() (external LLM API boundary)
        with (
            patch(
                "adversary_pursuit.agent.runner.AgentRunner.chat",
                return_value="I can't stop that person",
            ) as mock_chat,
        ):
            result = runner.handle_input("stop that guy")

        mock_chat.assert_called_once()
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# C-4: return value is always str, never None
# ---------------------------------------------------------------------------


class TestHandleInputReturnType:
    """handle_input always returns a str — TUI concatenates results to scrollback."""

    def test_returns_str_for_yield_command(self):
        runner = _make_runner()
        # @mock-exempt: dispatch_yield → phrase cache + EventBus; mocked for routing isolation
        with patch(
            "adversary_pursuit.agent.yield_commands.dispatch_yield",
            return_value="ok",
        ):
            result = runner.handle_input("stop")
        assert isinstance(result, str)

    def test_returns_str_for_regular_text(self):
        runner = _make_runner()
        # @mock-exempt: AgentRunner.chat → litellm.completion() (external LLM API boundary)
        with patch(
            "adversary_pursuit.agent.runner.AgentRunner.chat",
            return_value="llm answer",
        ):
            result = runner.handle_input("hello")
        assert isinstance(result, str)

    def test_returns_str_for_empty_chat_response(self):
        """Even when chat() returns '', handle_input returns a str."""
        runner = _make_runner()
        # @mock-exempt: AgentRunner.chat → litellm.completion() (external LLM API boundary)
        with patch(
            "adversary_pursuit.agent.runner.AgentRunner.chat",
            return_value="",
        ):
            result = runner.handle_input("mystery input")
        assert isinstance(result, str)

    def test_returns_str_for_malformed_yield(self):
        """Malformed yield falls through to chat; return value is still str."""
        runner = _make_runner()
        # @mock-exempt: AgentRunner.chat → litellm.completion() (external LLM API boundary)
        with patch(
            "adversary_pursuit.agent.runner.AgentRunner.chat",
            return_value="chat fallback",
        ):
            result = runner.handle_input("focus")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# C-5: TuiApplication._on_input_accepted calls handle_input(text, status_bar=live_pane)
# ---------------------------------------------------------------------------


class TestTuiOnInputAcceptedWiring:
    """_on_input_accepted calls runner.handle_input with status_bar=self._live_pane.

    This is the compound-interaction test: it exercises the real production
    sequence from the TUI input handler through the runner boundary.
    """

    def _make_tui(self) -> TuiApplication:
        """Construct a TuiApplication with TTY and _build_app stubbed out.

        FakeRunner.handle_input is a MagicMock because FakeRunner is an
        internal test stub, not the production AgentRunner. The real
        handle_input routing contract is covered by TestHandleInputYieldRouting
        and TestHandleInputChatRouting using a real AgentRunner instance.
        Here we only verify that _on_input_accepted wires the call correctly.
        """
        bus = EventBus()

        class FakeRunner:
            model = "test/model"
            # @mock-exempt: FakeRunner is a test-internal duck-type stub for AgentRunner.
            # The real routing contract is tested in TestHandleInputYieldRouting /
            # TestHandleInputChatRouting. Here we only verify _on_input_accepted call args.
            handle_input = MagicMock(return_value="runner says hi")

        class FakeModeManager:
            class active:
                name = "default"

        with (
            patch("sys.stdin.isatty", return_value=True),  # @mock-exempt: OS/TTY boundary
            patch.object(  # @mock-exempt: _build_app needs a real PTK terminal session
                TuiApplication, "_build_app", return_value=MagicMock()
            ),
        ):
            return TuiApplication(
                runner=FakeRunner(),
                workspace_mgr=None,
                mode_mgr=FakeModeManager(),
                event_bus=bus,
            )

    def test_on_input_accepted_calls_handle_input_with_status_bar(self):
        """_on_input_accepted must call runner.handle_input(text, status_bar=self._live_pane).

        This is the critical regression test: before this fix,
        TuiApplication called runner.handle_input(text) with no status_bar
        and AgentRunner had no handle_input method at all — causing
        AttributeError on every non-yield keystroke (P18S6-R2-N2).
        """
        app = self._make_tui()
        live_pane = app._live_pane

        # @mock-exempt: prompt_toolkit Buffer — we need a fake buffer object to
        #               simulate the accept_handler callback; no real PTK session available.
        fake_buffer = MagicMock()  # @mock-exempt: PTK Buffer (requires live terminal)
        fake_buffer.text = "hello"
        app._on_input_accepted(fake_buffer)

        # Verify handle_input was called with the right arguments
        app._runner.handle_input.assert_called_once_with("hello", status_bar=live_pane)

    def test_on_input_accepted_does_not_raise(self):
        """_on_input_accepted must not raise AttributeError for any text input."""
        app = self._make_tui()

        # @mock-exempt: prompt_toolkit Buffer (requires live terminal)
        fake_buffer = MagicMock()  # @mock-exempt: PTK Buffer
        fake_buffer.text = "who is 8.8.8.8?"

        # Before this fix, this raised AttributeError: 'FakeRunner' object
        # has no attribute 'handle_input' — now it must not raise.
        try:
            app._on_input_accepted(fake_buffer)
        except AttributeError as exc:
            pytest.fail(
                f"_on_input_accepted raised AttributeError: {exc}\n"
                "Ensure runner exposes handle_input() method."
            )

    def test_on_input_accepted_emits_result_to_scrollback(self):
        """Result from handle_input is appended to the scrollback buffer."""
        app = self._make_tui()
        app._runner.handle_input.return_value = "the runner replied"

        # @mock-exempt: prompt_toolkit Buffer (requires live terminal)
        fake_buffer = MagicMock()  # @mock-exempt: PTK Buffer
        fake_buffer.text = "investigate 8.8.8.8"
        app._on_input_accepted(fake_buffer)

        final_lines = app._scrollback.get_lines()
        all_text = " ".join(final_lines)
        assert "the runner replied" in all_text, (
            f"Expected 'the runner replied' in scrollback, got: {final_lines}"
        )
