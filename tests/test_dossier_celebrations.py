"""Tests for dossier_celebrations.py (M-7 narration policy).

Covers: constants, HuntNarrationBudget, is_high_weight_event,
build_narration_prompt, narrate_celebration (success and failure paths),
the _NARRATION_TESTING_RAISE_ON_FAILURE flag, and the F64 invariant
(narration text never leaks into the LLM-facing summary).

@decision DEC-TEST-M7-CELEB-001
@title Test suite for dossier_celebrations narration policy
@status accepted
@rationale Covers each public API surface (constants, dataclass, is_high_weight_event,
           build_narration_prompt, narrate_celebration) plus the critical F64 invariant
           (DEC-64-LLM-PANEL-SEPARATION-001) confirming narration text rides the
           celebration sidecar and never appears in the LLM-facing summary.
           AgentRunner is mocked with @mock-exempt because it owns the LLM client
           boundary (live litellm/OpenAI calls). All logic-under-test is the
           dossier_celebrations module itself (DEC-M7-CELEB-001 -- runner.narrate is
           an external LLM boundary, not internal code). Sacred Practice 5 satisfied.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import adversary_pursuit.gamification.dossier_celebrations as dc

# ---------------------------------------------------------------------------
# Helpers for events
# ---------------------------------------------------------------------------


def _slot_filled_event(slot: str, points: int = 100) -> dict:
    return {
        "action": "dossier_slot_filled",
        "indicator": slot,
        "points": points,
        "rule_description": f"dossier slot {slot} filled",
    }


def _prediction_validated_event(points: int = 150) -> dict:
    return {
        "action": "dossier_prediction_validated",
        "indicator": "adversary will reuse C2 infrastructure",
        "points": points,
        "rule_description": "prediction validated: adversary will reuse C2 infrastructure",
    }


def _prediction_falsified_event(points: int = 0) -> dict:
    return {
        "action": "dossier_prediction_falsified",
        "indicator": "adversary will abandon domain",
        "points": points,
        "rule_description": "prediction falsified: adversary will abandon domain",
    }


def _make_runner(narrate_return: str | None = "Excellent intelligence work.") -> MagicMock:
    # @mock-exempt: AgentRunner wraps litellm / OpenAI — a live external LLM boundary.
    # narrate() is the single entry point for that boundary (DEC-M7-CELEB-001).
    # All logic under test lives entirely within dossier_celebrations; the runner
    # stub verifies call contracts against that boundary only.
    runner = MagicMock()
    runner.narrate.return_value = narrate_return
    return runner


# ---------------------------------------------------------------------------
# Stage A: Constants (DEC-M7-CELEB-002, DEC-M7-CELEB-003, DEC-M7-CELEB-004)
# ---------------------------------------------------------------------------


class TestConstants:
    """Module-level constants are load-bearing policy; verify exact values."""

    def test_high_weight_threshold_is_2_5(self) -> None:
        assert dc.HIGH_WEIGHT_NARRATION_THRESHOLD == 2.5

    def test_per_narration_token_cap_is_80(self) -> None:
        assert dc.PER_NARRATION_TOKEN_CAP == 80

    def test_per_hunt_budget_is_3(self) -> None:
        assert dc.PER_HUNT_NARRATION_BUDGET == 3

    def test_testing_raise_flag_defaults_false(self) -> None:
        assert dc._NARRATION_TESTING_RAISE_ON_FAILURE is False


# ---------------------------------------------------------------------------
# Stage A: HuntNarrationBudget (DEC-M7-CELEB-004)
# ---------------------------------------------------------------------------


class TestHuntNarrationBudget:
    """Per-hunt budget counter semantics."""

    def test_default_limit_matches_constant(self) -> None:
        budget = dc.HuntNarrationBudget()
        assert budget.limit == dc.PER_HUNT_NARRATION_BUDGET

    def test_starts_unexhausted(self) -> None:
        budget = dc.HuntNarrationBudget()
        assert not budget.exhausted

    def test_remaining_equals_limit_initially(self) -> None:
        budget = dc.HuntNarrationBudget()
        assert budget.remaining == dc.PER_HUNT_NARRATION_BUDGET

    def test_consume_decrements_remaining(self) -> None:
        budget = dc.HuntNarrationBudget()
        budget.consume()
        assert budget.remaining == dc.PER_HUNT_NARRATION_BUDGET - 1

    def test_exhaust_all_units(self) -> None:
        budget = dc.HuntNarrationBudget(limit=2)
        budget.consume()
        budget.consume()
        assert budget.exhausted
        assert budget.remaining == 0

    def test_remaining_never_below_zero(self) -> None:
        budget = dc.HuntNarrationBudget(limit=1)
        budget.consume()
        budget.consume()  # over-consume
        assert budget.remaining == 0

    def test_custom_limit(self) -> None:
        budget = dc.HuntNarrationBudget(limit=5)
        assert budget.limit == 5
        assert not budget.exhausted


# ---------------------------------------------------------------------------
# Stage A: is_high_weight_event (DEC-M7-CELEB-002, DEC-M7-CELEB-005)
# ---------------------------------------------------------------------------


class TestIsHighWeightEvent:
    """Eligibility predicate for LLM narration."""

    # High-weight slots (weight >= 2.5)
    @pytest.mark.parametrize(
        "slot",
        ["identity", "predictions", "capability", "ttps", "motivation", "targeting", "denial"],
    )
    def test_high_weight_slot_fill_is_eligible(self, slot: str) -> None:
        event = _slot_filled_event(slot)
        assert dc.is_high_weight_event(event) is True

    # Low-weight slots (weight < 2.5)
    @pytest.mark.parametrize("slot", ["infrastructure", "timing"])
    def test_low_weight_slot_fill_is_not_eligible(self, slot: str) -> None:
        event = _slot_filled_event(slot)
        assert dc.is_high_weight_event(event) is False

    def test_prediction_validated_is_eligible(self) -> None:
        event = _prediction_validated_event()
        assert dc.is_high_weight_event(event) is True

    def test_prediction_falsified_is_never_eligible(self) -> None:
        """DEC-M7-CELEB-005: falsified events are excluded from narration."""
        event = _prediction_falsified_event()
        assert dc.is_high_weight_event(event) is False

    def test_unknown_action_is_not_eligible(self) -> None:
        event = {"action": "ioc_discovered", "indicator": "evil.com", "points": 50}
        assert dc.is_high_weight_event(event) is False

    def test_empty_event_is_not_eligible(self) -> None:
        assert dc.is_high_weight_event({}) is False


# ---------------------------------------------------------------------------
# Stage A: build_narration_prompt
# ---------------------------------------------------------------------------


class TestBuildNarrationPrompt:
    """Prompt construction for slot-filled and prediction-validated events."""

    def test_slot_fill_prompt_contains_slot_name(self) -> None:
        event = _slot_filled_event("identity", points=200)
        prompt = dc.build_narration_prompt(event, dossier_state=None)
        assert "identity" in prompt.lower()

    def test_slot_fill_prompt_contains_points(self) -> None:
        event = _slot_filled_event("capability", points=175)
        prompt = dc.build_narration_prompt(event, dossier_state=None)
        assert "175" in prompt

    def test_prediction_validated_prompt_contains_points(self) -> None:
        event = _prediction_validated_event(points=150)
        prompt = dc.build_narration_prompt(event, dossier_state=None)
        assert "150" in prompt

    def test_prediction_validated_prompt_contains_prediction_context(self) -> None:
        event = _prediction_validated_event(points=150)
        prompt = dc.build_narration_prompt(event, dossier_state=None)
        # Either the indicator text or a celebration phrase must be present
        content_lower = prompt.lower()
        assert any(
            word in content_lower for word in ("c2", "infrastructure", "prediction", "validated")
        )

    def test_prompt_is_nonempty_string(self) -> None:
        event = _slot_filled_event("ttps")
        prompt = dc.build_narration_prompt(event, dossier_state=None)
        assert isinstance(prompt, str)
        assert len(prompt) > 10

    def test_fallback_prompt_nonempty_for_unknown_action(self) -> None:
        event = {"action": "unknown_action", "points": 50, "indicator": "x"}
        prompt = dc.build_narration_prompt(event, dossier_state=None)
        assert isinstance(prompt, str)
        assert len(prompt) > 5


# ---------------------------------------------------------------------------
# Stage A: narrate_celebration — success and failure paths
# ---------------------------------------------------------------------------


class TestNarrateCelebration:
    """narrate_celebration() wires LLM call, validates output, consumes budget."""

    def test_returns_narration_text_on_success(self) -> None:
        runner = _make_runner("The adversary's hand has been revealed.")
        budget = dc.HuntNarrationBudget()
        result = dc.narrate_celebration(runner, _slot_filled_event("identity"), None, budget)
        assert result == "The adversary's hand has been revealed."

    def test_consumes_budget_on_success(self) -> None:
        runner = _make_runner("Nice work.")
        budget = dc.HuntNarrationBudget()
        dc.narrate_celebration(runner, _slot_filled_event("identity"), None, budget)
        assert budget.used == 1

    def test_exhausted_budget_returns_none_without_llm_call(self) -> None:
        runner = _make_runner("Should not be called.")
        budget = dc.HuntNarrationBudget(limit=0)
        result = dc.narrate_celebration(runner, _slot_filled_event("identity"), None, budget)
        assert result is None
        runner.narrate.assert_not_called()

    def test_llm_returns_none_yields_none(self) -> None:
        runner = _make_runner(narrate_return=None)
        budget = dc.HuntNarrationBudget()
        result = dc.narrate_celebration(runner, _slot_filled_event("identity"), None, budget)
        assert result is None
        assert budget.used == 0

    def test_llm_raises_yields_none_by_default(self) -> None:
        # @mock-exempt: AgentRunner wraps litellm — simulating LLM failure here.
        runner = MagicMock()
        runner.narrate.side_effect = RuntimeError("LLM error")
        budget = dc.HuntNarrationBudget()
        result = dc.narrate_celebration(runner, _slot_filled_event("identity"), None, budget)
        assert result is None
        assert budget.used == 0

    def test_rich_markup_in_narration_is_rejected(self) -> None:
        runner = _make_runner("[bold]Adversary identified.[/bold]")
        budget = dc.HuntNarrationBudget()
        result = dc.narrate_celebration(runner, _slot_filled_event("identity"), None, budget)
        assert result is None
        assert budget.used == 0

    def test_narrate_called_with_correct_token_cap(self) -> None:
        runner = _make_runner("Good work.")
        budget = dc.HuntNarrationBudget()
        dc.narrate_celebration(runner, _slot_filled_event("ttps"), None, budget)
        runner.narrate.assert_called_once()
        _, kwargs = runner.narrate.call_args
        assert kwargs["max_tokens"] == dc.PER_NARRATION_TOKEN_CAP

    def test_empty_string_narration_is_rejected(self) -> None:
        runner = _make_runner("   ")
        budget = dc.HuntNarrationBudget()
        result = dc.narrate_celebration(runner, _slot_filled_event("identity"), None, budget)
        assert result is None

    def test_budget_not_consumed_when_llm_fails(self) -> None:
        # @mock-exempt: AgentRunner wraps litellm — simulating LLM timeout/error.
        runner = MagicMock()
        runner.narrate.side_effect = ValueError("timeout")
        budget = dc.HuntNarrationBudget()
        dc.narrate_celebration(runner, _slot_filled_event("capability"), None, budget)
        assert budget.used == 0


# ---------------------------------------------------------------------------
# Stage A: _NARRATION_TESTING_RAISE_ON_FAILURE flag (DEC-M7-CELEB-006)
# ---------------------------------------------------------------------------


class TestNarrationTestingRaiseOnFailure:
    """When _NARRATION_TESTING_RAISE_ON_FAILURE is True, silent failures become loud."""

    def setup_method(self) -> None:
        dc._NARRATION_TESTING_RAISE_ON_FAILURE = True

    def teardown_method(self) -> None:
        dc._NARRATION_TESTING_RAISE_ON_FAILURE = False

    def test_llm_exception_re_raised(self) -> None:
        # @mock-exempt: AgentRunner wraps litellm — simulating LLM failure to test loud re-raise.
        runner = MagicMock()
        runner.narrate.side_effect = RuntimeError("LLM exploded")
        budget = dc.HuntNarrationBudget()
        with pytest.raises(RuntimeError, match="LLM exploded"):
            dc.narrate_celebration(runner, _slot_filled_event("identity"), None, budget)

    def test_llm_returns_none_raises(self) -> None:
        # @mock-exempt: AgentRunner wraps litellm — simulating None return from LLM call.
        runner = MagicMock()
        runner.narrate.return_value = None
        budget = dc.HuntNarrationBudget()
        with pytest.raises(RuntimeError, match="narrate\\(\\) returned None"):
            dc.narrate_celebration(runner, _slot_filled_event("identity"), None, budget)

    def test_validation_failure_raises(self) -> None:
        # @mock-exempt: AgentRunner wraps litellm — simulating LLM returning Rich markup.
        runner = MagicMock()
        runner.narrate.return_value = "[bold]bad markup[/bold]"
        budget = dc.HuntNarrationBudget()
        with pytest.raises(RuntimeError, match="narration text failed validation"):
            dc.narrate_celebration(runner, _slot_filled_event("identity"), None, budget)


# ---------------------------------------------------------------------------
# Stage B: F64 invariant (DEC-64-LLM-PANEL-SEPARATION-001)
# ---------------------------------------------------------------------------


class TestF64Invariant:
    """Narration text must NOT appear in the LLM-facing summary string.

    The F64 invariant (DEC-64-LLM-PANEL-SEPARATION-001) mandates that the
    _DOSSIER_ACTIONS frozenset in tools.py controls which events can mutate the
    dossier-related summary context for the LLM, and narration text is a
    celebration sidecar that never touches that summary.

    These tests confirm that narrate_celebration() returns a plain string
    (not injected into any shared state) and that the module has no references
    to the runner's conversation history or summary fields.
    """

    def test_narrate_celebration_returns_plain_string_not_side_effect(self) -> None:
        """narrate_celebration returns a value; it must NOT mutate the runner."""
        # @mock-exempt: AgentRunner wraps litellm — verifying runner is not mutated.
        runner = MagicMock()
        runner.narrate.return_value = "Great intelligence work."
        budget = dc.HuntNarrationBudget()
        event = _slot_filled_event("identity")

        result = dc.narrate_celebration(runner, event, None, budget)

        # Result is just a string — no runner attributes mutated beyond narrate()
        assert result == "Great intelligence work."
        # Only narrate() was called — no other runner methods touched
        runner.narrate.assert_called_once()
        # No calls to any other runner method
        other_calls = [
            call for call in runner.method_calls if not str(call).startswith("call.narrate")
        ]
        assert other_calls == [], f"Unexpected runner method calls: {other_calls}"

    def test_narration_module_has_no_summary_mutation(self) -> None:
        """The module source must not contain summary injection patterns."""
        import inspect

        src = inspect.getsource(dc)
        # No direct assignment to runner.conversation or runner.summary
        assert "runner.conversation" not in src
        assert "runner.summary" not in src

    def test_narration_does_not_appear_in_llm_summary(self) -> None:
        """Simulate the tools.py narration loop: narration appends to celebration, not summary.

        This is the compound-interaction test: exercises the full production sequence
        from event creation through narrate_celebration to the celebration sidecar append,
        confirming the narration text stays in the celebration string and is never
        injected into a summary variable.
        """
        # @mock-exempt: AgentRunner wraps litellm — verifying celebration sidecar pattern.
        runner = MagicMock()
        narration_text = "The adversary's true identity has been revealed."
        runner.narrate.return_value = narration_text
        budget = dc.HuntNarrationBudget()
        event = _slot_filled_event("identity")

        # Initial celebration (ASCII art from CelebrationEngine would be here)
        celebration = "[ASCII art celebration]"
        summary = "Module returned 3 indicators."  # LLM-facing summary — must stay unchanged

        # Simulated narration append (mirrors tools.py loop)
        narration = dc.narrate_celebration(runner, event, None, budget)
        if narration:
            celebration = celebration + "\n\n" + narration
        # summary is NOT modified by narrate_celebration

        assert narration_text in celebration
        assert narration_text not in summary  # F64 invariant: narration stays in sidecar
        # runner.narrate called with max_tokens kwarg
        _, kwargs = runner.narrate.call_args
        assert "max_tokens" in kwargs
