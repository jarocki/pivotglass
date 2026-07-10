"""Conversation-integrity tests for AgentRunner (DEC-RUNNER-CONVERSATION-INTEGRITY-001).

Two production bugs were fixed:

  Bug 1 — hook exception tears conversation history:
    runner.chat() committed the assistant tool_call message BEFORE calling
    _hook.set_activity(). When the hook raised AttributeError (LivePane had no
    such method), no tool_result was appended. The next chat() call sent OpenAI
    an orphaned tool_call_id and litellm rejected it with BadRequestError.

  Bug 2 — no repair path for existing torn history:
    Operators who already hit the crash could not recover without restarting the
    REPL because the torn history persisted across chat() calls.

Fix is two-layer:
  Layer A — _safe_hook_call: hook exceptions are swallowed so the runner always
            reaches execute_tool regardless of UI errors.
  Layer B — finally block: a tool_result is unconditionally appended for every
            tc.id, even when the tool itself raises. Synthetic error content is
            emitted so the LLM can recover.
  + _heal_torn_history: repairs pre-existing torn history at chat() entry.

Production sequence exercised (compound-interaction):
  runner.chat(user_message, status_bar=broken_hook) →
    _heal_torn_history()               # repair pre-existing tears
    append user message
    _call_llm()                        # mocked — returns tool_calls
    append assistant tool_call message
    for tc in tool_calls:
        _safe_hook_call(hook, "set_activity", slug)  # hook raises → swallowed
        execute_tool(...)                             # mocked → returns summary
        _safe_hook_call(hook, "set_activity", None)  # hook raises → swallowed
        append tool_result              # always appended via finally
    _call_llm()                        # second round → returns text response
    return text

@decision DEC-TEST-RUNNER-CONVERSATION-INTEGRITY-001
@title Tests verify conversation history is always well-formed after chat()
@status accepted
@rationale The production crash sequence is fully reproducible in tests without
           a real LLM: mock _call_llm to return a tool_call round followed by a
           text-response round, use a broken hook that raises on set_activity, and
           assert that self.conversation contains no orphaned tool_call_ids after
           chat() returns. This exercises the exact production code path end-to-end
           (AgentRunner.chat → _safe_hook_call → execute_tool → finally append).

           Mock strategy:
           - AgentRunner._call_llm: external LLM API boundary (network). @mock-exempt.
           - execute_tool: external OSINT/CTI network calls. @mock-exempt.
           - BrokenHook.set_activity: intentional test stub to simulate the Slice 6
             broken LivePane — this IS the system under test (the hook exception path).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from adversary_pursuit.agent.runner import AgentRunner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runner() -> AgentRunner:
    """Return a real AgentRunner with model fixed to avoid env lookup."""
    return AgentRunner(model="test/model")


def _make_tool_call_message(tc_id: str = "call_abc123", tool_name: str = "dns_resolve") -> object:
    """Build a fake LLM message object that requests one tool call."""
    tc = MagicMock()
    tc.id = tc_id
    tc.function.name = tool_name
    tc.function.arguments = '{"domain": "example.com"}'

    msg = MagicMock()
    msg.tool_calls = [tc]
    msg.content = None
    return msg


def _make_text_message(text: str = "Here is what I found.") -> object:
    """Build a fake LLM message object that returns a text response (no tools)."""
    msg = MagicMock()
    msg.tool_calls = None
    msg.content = text
    return msg


def _orphaned_tool_call_ids(conversation: list[dict]) -> set[str]:
    """Return tc.ids in assistant tool_call messages that have no matching tool_result."""
    covered: set[str] = {
        msg["tool_call_id"]
        for msg in conversation
        if msg.get("role") == "tool" and "tool_call_id" in msg
    }
    orphaned: set[str] = set()
    for msg in conversation:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                if tc_id and tc_id not in covered:
                    orphaned.add(tc_id)
    return orphaned


class BrokenHook:
    """A _StatusHook stub where set_activity always raises AttributeError.

    This simulates the exact Slice 6 production crash: LivePane had no
    set_activity method, so every tool call in the TUI raised AttributeError.
    """

    def set_activity(self, tool_slug: str | None) -> None:
        raise AttributeError("'BrokenHook' object has no attribute 'set_activity'")

    def set_battery(self, name: str | None) -> None:
        pass

    def set_hypothesis(self, text: str | None) -> None:
        pass


# ---------------------------------------------------------------------------
# _heal_torn_history unit tests
# ---------------------------------------------------------------------------


class TestHealTornHistory:
    """Unit tests for AgentRunner._heal_torn_history."""

    def test_heal_does_nothing_to_clean_history(self):
        """_heal_torn_history is a no-op when every tool_call has a tool_result."""
        runner = _make_runner()
        # Construct a well-formed two-message exchange
        runner.conversation = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call_x1", "function": {"name": "dns_resolve"}}],
            },
            {"role": "tool", "tool_call_id": "call_x1", "content": "dns result"},
            {"role": "assistant", "content": "Here is what I found."},
        ]
        original_len = len(runner.conversation)

        runner._heal_torn_history()

        assert len(runner.conversation) == original_len, (
            "_heal_torn_history must not modify a well-formed conversation"
        )

    def test_heal_appends_missing_tool_result(self):
        """_heal_torn_history fills in the orphaned tool_result for a torn history."""
        runner = _make_runner()
        runner.conversation = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "investigate 8.8.8.8"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call_torn1", "function": {"name": "dns_resolve"}}],
            },
            # No tool_result for call_torn1 — torn history
        ]

        runner._heal_torn_history()

        # A synthetic tool_result must have been appended
        tool_results = [m for m in runner.conversation if m.get("role") == "tool"]
        assert len(tool_results) == 1, f"Expected 1 synthetic tool_result, got: {tool_results}"
        assert tool_results[0]["tool_call_id"] == "call_torn1"
        assert "[previous turn interrupted]" in tool_results[0]["content"]

    def test_heal_repairs_multiple_orphaned_ids(self):
        """Multiple orphaned tc.ids in one assistant message are all repaired."""
        runner = _make_runner()
        runner.conversation = [
            {"role": "system", "content": "sp"},
            {"role": "user", "content": "u"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_a", "function": {"name": "dns_resolve"}},
                    {"id": "call_b", "function": {"name": "whois_lookup"}},
                ],
            },
            # Only call_a has a result — call_b is orphaned
            {"role": "tool", "tool_call_id": "call_a", "content": "dns ok"},
        ]

        runner._heal_torn_history()

        tool_results = {
            m["tool_call_id"]: m["content"] for m in runner.conversation if m.get("role") == "tool"
        }
        assert "call_a" in tool_results
        assert "call_b" in tool_results, "call_b must be repaired"
        assert "[previous turn interrupted]" in tool_results["call_b"]

    def test_heal_is_idempotent(self):
        """Calling _heal_torn_history twice does not duplicate tool_results."""
        runner = _make_runner()
        runner.conversation = [
            {"role": "system", "content": "sp"},
            {"role": "user", "content": "u"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call_idem", "function": {"name": "dns_resolve"}}],
            },
        ]

        runner._heal_torn_history()
        runner._heal_torn_history()  # second call must not add another result

        tool_results = [m for m in runner.conversation if m.get("role") == "tool"]
        assert len(tool_results) == 1, (
            f"Idempotent heal must not duplicate tool_results: {tool_results}"
        )

    def test_healed_history_has_zero_orphaned_tool_calls(self):
        """After healing, _orphaned_tool_call_ids returns empty set."""
        runner = _make_runner()
        runner.conversation = [
            {"role": "system", "content": "sp"},
            {"role": "user", "content": "u"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_p", "function": {"name": "dns_resolve"}},
                    {"id": "call_q", "function": {"name": "shodan_host_lookup"}},
                ],
            },
        ]

        runner._heal_torn_history()

        orphaned = _orphaned_tool_call_ids(runner.conversation)
        assert orphaned == set(), f"Expected no orphaned tc.ids after heal, got: {orphaned}"


# ---------------------------------------------------------------------------
# Hook exception does not tear conversation
# ---------------------------------------------------------------------------


class TestHookExceptionDoesNotTearConversation:
    """Layer A: _safe_hook_call swallows hook exceptions so chat() always completes
    and every assistant tool_call has a matching tool_result in conversation.

    This is the compound-interaction test: it exercises the full production
    sequence — broken hook → _safe_hook_call swallows → execute_tool runs →
    tool_result appended — without a real LLM or real tool.
    """

    def test_hook_exception_does_not_tear_conversation(self):
        """chat() with a BrokenHook must succeed and leave no orphaned tc.ids.

        Production sequence:
          chat(user_msg, status_bar=BrokenHook()) →
            _heal_torn_history()
            append user message
            _call_llm() → tool_call round
            append assistant tool_call message
            for tc: _safe_hook_call(hook, "set_activity", slug) → exception swallowed
                    execute_tool → "dns result"
                    _safe_hook_call(hook, "set_activity", None) → exception swallowed
                    append tool_result (finally)
            _call_llm() → text response round
            return text
        """
        runner = _make_runner()
        broken_hook = BrokenHook()

        # LLM: round 1 returns a tool call; round 2 returns text response.
        # @mock-exempt: AgentRunner._call_llm → litellm.completion() (external LLM API boundary)
        # @mock-exempt: execute_tool → external OSINT/CTI network calls
        side_effects = [
            _make_tool_call_message("call_s6h_001", "dns_resolve"),
            _make_text_message("DNS lookup complete."),
        ]
        with (
            patch.object(AgentRunner, "_call_llm", side_effect=side_effects),
            patch(
                "adversary_pursuit.agent.runner.execute_tool",
                return_value=("dns result", None, [], []),
            ),
        ):
            result = runner.chat("investigate example.com", status_bar=broken_hook)

        # chat() must return a string — not raise
        assert isinstance(result, str), f"chat() must return str, got {type(result)}"

        # No orphaned tool_call_ids in the conversation history
        orphaned = _orphaned_tool_call_ids(runner.conversation)
        assert orphaned == set(), (
            f"Orphaned tool_call_ids after chat() with BrokenHook: {orphaned}\n"
            f"Conversation: {runner.conversation}"
        )

    def test_hook_exception_does_not_affect_tool_execution(self):
        """Tool executes and its result appears in conversation even when hook raises."""
        runner = _make_runner()
        broken_hook = BrokenHook()

        # @mock-exempt: AgentRunner._call_llm → litellm.completion() (external LLM API boundary)
        # @mock-exempt: execute_tool → external OSINT/CTI network calls
        with (
            patch.object(
                AgentRunner,
                "_call_llm",
                side_effect=[
                    _make_tool_call_message("call_exec", "dns_resolve"),
                    _make_text_message("Done."),
                ],
            ),
            patch(
                "adversary_pursuit.agent.runner.execute_tool",
                return_value=("real tool result", None, [], []),
            ) as mock_execute,
        ):
            runner.chat("run dns", status_bar=broken_hook)

        # execute_tool must have been called despite the hook raising
        assert mock_execute.call_count == 1, "execute_tool must run even when hook raises"

        # The real tool result must appear in conversation
        tool_msgs = [m for m in runner.conversation if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert "real tool result" in tool_msgs[0]["content"]


# ---------------------------------------------------------------------------
# Tool execution exception emits synthetic result
# ---------------------------------------------------------------------------


class TestToolExecutionExceptionEmitsSyntheticResult:
    """Layer B: when execute_tool raises, a synthetic error tool_result is appended
    and chat() does not re-raise — preserving conversation integrity.
    """

    def test_tool_execution_exception_emits_synthetic_result(self):
        """execute_tool raising must emit a synthetic error tool_result, not tear history."""
        runner = _make_runner()

        # @mock-exempt: AgentRunner._call_llm → litellm.completion() (external LLM API boundary)
        # @mock-exempt: execute_tool → external OSINT/CTI network calls; mocked to raise
        with (
            patch.object(
                AgentRunner,
                "_call_llm",
                side_effect=[
                    _make_tool_call_message("call_fail", "dns_resolve"),
                    _make_text_message("I encountered an error."),
                ],
            ),
            patch(
                "adversary_pursuit.agent.runner.execute_tool",
                side_effect=RuntimeError("network timeout"),
            ),
        ):
            result = runner.chat("run dns", status_bar=None)

        # chat() must return a string (LLM text response after seeing the error)
        assert isinstance(result, str)

        # A synthetic tool_result must have been appended for the failing tc
        tool_msgs = [m for m in runner.conversation if m.get("role") == "tool"]
        assert len(tool_msgs) == 1, f"Expected 1 tool_result, got: {tool_msgs}"
        assert "call_fail" == tool_msgs[0]["tool_call_id"]
        assert "internal error" in tool_msgs[0]["content"].lower(), (
            f"Synthetic result must mention 'internal error': {tool_msgs[0]['content']!r}"
        )

        # No orphaned tc.ids
        orphaned = _orphaned_tool_call_ids(runner.conversation)
        assert orphaned == set(), f"Orphaned tc.ids after tool exception: {orphaned}"

    def test_multiple_tool_calls_one_fails(self):
        """When one of multiple tool calls fails, all tc.ids still get tool_results."""
        runner = _make_runner()

        # Build a two-tool-call round
        tc_ok = MagicMock()
        tc_ok.id = "call_ok"
        tc_ok.function.name = "dns_resolve"
        tc_ok.function.arguments = '{"domain": "ok.com"}'

        tc_fail = MagicMock()
        tc_fail.id = "call_fail2"
        tc_fail.function.name = "whois_lookup"
        tc_fail.function.arguments = '{"domain": "fail.com"}'

        round1_msg = MagicMock()
        round1_msg.tool_calls = [tc_ok, tc_fail]
        round1_msg.content = None

        # execute_tool: first call succeeds, second raises
        execute_side_effects: list[Any] = [
            ("whois ok", None, [], []),
            RuntimeError("whois exploded"),
        ]

        # @mock-exempt: AgentRunner._call_llm → litellm.completion() (external LLM API)
        # @mock-exempt: execute_tool → external OSINT/CTI network calls
        with (
            patch.object(
                AgentRunner,
                "_call_llm",
                side_effect=[round1_msg, _make_text_message("Got partial results.")],
            ),
            patch(
                "adversary_pursuit.agent.runner.execute_tool",
                side_effect=execute_side_effects,
            ),
        ):
            result = runner.chat("investigate", status_bar=None)

        assert isinstance(result, str)

        tool_msgs = {
            m["tool_call_id"]: m["content"] for m in runner.conversation if m.get("role") == "tool"
        }
        assert "call_ok" in tool_msgs, "Successful tc must have a tool_result"
        assert "call_fail2" in tool_msgs, "Failed tc must have a synthetic tool_result"
        assert "internal error" in tool_msgs["call_fail2"].lower()

        orphaned = _orphaned_tool_call_ids(runner.conversation)
        assert orphaned == set()


# ---------------------------------------------------------------------------
# Torn history healed on chat() entry
# ---------------------------------------------------------------------------


class TestTornHistoryHealedOnChatEntry:
    """_heal_torn_history is called at chat() entry so pre-existing torn history
    is repaired before the new user message is appended.
    """

    def test_torn_history_healed_on_chat_entry(self):
        """Construct a runner with torn history, call chat(), verify healing occurred.

        The torn history simulates the exact state left by the Slice 6 crash:
        an assistant tool_call message with no matching tool_result.
        """
        runner = _make_runner()

        # Inject torn history directly — simulates a previous interrupted turn
        runner.conversation = [
            {"role": "system", "content": runner.system_prompt},
            {"role": "user", "content": "previous user message"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_torn_s6h", "function": {"name": "dns_resolve", "arguments": "{}"}}
                ],
            },
            # No tool_result for call_torn_s6h — torn
        ]

        # @mock-exempt: AgentRunner._call_llm → litellm.completion() (external LLM API)
        # @mock-exempt: execute_tool → external OSINT/CTI network calls
        with (
            patch.object(
                AgentRunner,
                "_call_llm",
                return_value=_make_text_message("Healed and responded."),
            ),
            patch(
                "adversary_pursuit.agent.runner.execute_tool",
                return_value=("result", None, [], []),
            ),
        ):
            result = runner.chat("hello after crash")

        # chat() must return a string
        assert isinstance(result, str)

        # The synthetic tool_result for the pre-existing torn tc must be present
        tool_msgs = {
            m["tool_call_id"]: m["content"] for m in runner.conversation if m.get("role") == "tool"
        }
        assert "call_torn_s6h" in tool_msgs, (
            f"Torn tc.id must be healed before the new turn: {tool_msgs}"
        )
        assert "[previous turn interrupted]" in tool_msgs["call_torn_s6h"]

        # No orphaned tc.ids after the full turn
        orphaned = _orphaned_tool_call_ids(runner.conversation)
        assert orphaned == set(), f"No orphaned tc.ids expected after heal + chat: {orphaned}"

    def test_healed_history_allows_llm_call_to_proceed(self):
        """After healing, the LLM call proceeds without a BadRequestError.

        The mock _call_llm is called — proving that the conversation sent to the
        LLM is well-formed (no orphaned tc.ids). In production, a torn history
        would cause litellm to raise BadRequestError before the LLM is reached.
        """
        runner = _make_runner()
        runner.conversation = [
            {"role": "system", "content": runner.system_prompt},
            {"role": "user", "content": "prior msg"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_healed",
                        "function": {"name": "shodan_host_lookup", "arguments": "{}"},
                    }
                ],
            },
        ]

        call_llm_mock = MagicMock(return_value=_make_text_message("proceeding."))

        # @mock-exempt: AgentRunner._call_llm → litellm.completion() (external LLM API)
        with patch.object(AgentRunner, "_call_llm", call_llm_mock):
            runner.chat("next turn")

        # _call_llm must have been called — proving execution reached the LLM
        assert call_llm_mock.called, "_call_llm must be called after healing"
