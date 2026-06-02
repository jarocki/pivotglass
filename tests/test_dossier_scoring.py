"""Tests for dossier/scoring.py — M-3 dossier slot-fill event emitter.

Covers emit_dossier_slot_filled_events (all 9 transition paths, idempotency,
skip-step, deferred-target handling, event-dict shape) and the M-3 scaffold for
emit_dossier_prediction_validated_event (DEC-M3-DOSSIER-005).

Evaluation Contract gates:
  A1  empty->partial Identity: one event, points=5, indicator="identity"
  A2  empty->partial TTPs: one event, points=3
  A3  empty->partial Infrastructure: points=2
  A4  empty->partial Timing: points=2
  A5  empty->partial Capability: points=3 (int(3.5) floor)
  A6  empty->partial Motivation: points=3
  A7  partial->filled Identity: one event, points=5
  A8  skip-step empty->filled Identity: ONE event (not two), points=5
  A9  filled->filled: idempotency — zero events
  A10 partial->partial: no transition — zero events
  A11 empty->empty: no transition — zero events
  A12 deferred target: Predictions/Denial stay DEFERRED in M-3 — no events
  A13 deferred->real: defensive skip + debug log
  A14 multiple slot transitions in one hunt: correct count and indicators
  A15 event dict shape contract: exactly 4 keys with correct types
  A16 emit_dossier_prediction_validated_event scaffold exists + shape correct

@decision DEC-M3-DOSSIER-001
@title emit_dossier_slot_filled_events is a pure function; tests are hermetic
@status accepted
@rationale Pure function takes two DossierState frozen dataclasses and returns
    list[dict]. No fixtures requiring live workspace — all tests construct
    DossierState objects directly from slot_inference value objects, mirroring
    the production sequence (infer_dossier_state_full -> emit_dossier_slot_filled_events).

@decision DEC-M3-DOSSIER-005
@title dossier_prediction_validated scaffold test proves shape contract
@status accepted
@rationale M-4 implementers must be able to import and call
    emit_dossier_prediction_validated_event without any persistence layer.
    Test A16 proves the function is importable, returns the documented shape,
    and uses the documented weight (4 = int(SLOT_WEIGHTS[PREDICTIONS])).
"""

from __future__ import annotations

import logging

from adversary_pursuit.dossier.scoring import (
    emit_dossier_prediction_validated_event,
    emit_dossier_slot_filled_events,
)
from adversary_pursuit.dossier.slot_inference import DossierState, SlotState
from adversary_pursuit.dossier.slots import DossierSlotName, PredictionRecord, SlotStatus

# ---------------------------------------------------------------------------
# Helper factories — build minimal DossierState objects without live workspace
# ---------------------------------------------------------------------------


def _all_empty_state() -> DossierState:
    """DossierState where every slot is EMPTY (no SCO evidence)."""
    slots = {slot: SlotState(name=slot, status=SlotStatus.EMPTY) for slot in DossierSlotName}
    return DossierState(slots=slots, total_sco_count=0)


def _all_deferred_state() -> DossierState:
    """DossierState where every slot is DEFERRED (scaffold-only milestone marker)."""
    slots = {slot: SlotState(name=slot, status=SlotStatus.DEFERRED) for slot in DossierSlotName}
    return DossierState(slots=slots, total_sco_count=0)


def _state_with(overrides: dict[DossierSlotName, SlotStatus]) -> DossierState:
    """DossierState starting from all-EMPTY with specified slot overrides."""
    slots = {slot: SlotState(name=slot, status=SlotStatus.EMPTY) for slot in DossierSlotName}
    for slot_name, status in overrides.items():
        slots[slot_name] = SlotState(
            name=slot_name, status=status, evidence_count=1 if status != SlotStatus.EMPTY else 0
        )
    return DossierState(
        slots=slots, total_sco_count=sum(1 for s in slots.values() if s.evidence_count > 0)
    )


# ---------------------------------------------------------------------------
# A1–A6: empty -> partial transitions (one per slot weight class)
# ---------------------------------------------------------------------------


class TestEmptyToPartialTransitions:
    """Upward empty->partial transitions fire one event per slot."""

    def test_empty_to_partial_identity_emits_one_event(self):
        """A1: Identity slot empty->partial: one event, points=5, indicator='identity'."""
        pre = _all_empty_state()
        post = _state_with({DossierSlotName.IDENTITY: SlotStatus.PARTIAL})
        events = emit_dossier_slot_filled_events(pre, post)
        assert len(events) == 1
        ev = events[0]
        assert ev["action"] == "dossier_slot_filled"
        assert ev["points"] == 5
        assert ev["indicator"] == "identity"
        assert "identity" in ev["rule_description"].lower()

    def test_empty_to_partial_ttps_emits_one_event(self):
        """A2: TTPs slot empty->partial: one event, points=3."""
        pre = _all_empty_state()
        post = _state_with({DossierSlotName.TTPS: SlotStatus.PARTIAL})
        events = emit_dossier_slot_filled_events(pre, post)
        assert len(events) == 1
        assert events[0]["points"] == 3
        assert events[0]["indicator"] == "ttps"

    def test_empty_to_partial_infrastructure(self):
        """A3: Infrastructure slot empty->partial: points=2."""
        pre = _all_empty_state()
        post = _state_with({DossierSlotName.INFRASTRUCTURE: SlotStatus.PARTIAL})
        events = emit_dossier_slot_filled_events(pre, post)
        assert len(events) == 1
        assert events[0]["points"] == 2
        assert events[0]["indicator"] == "infrastructure"

    def test_empty_to_partial_timing(self):
        """A4: Timing slot empty->partial: points=2."""
        pre = _all_empty_state()
        post = _state_with({DossierSlotName.TIMING: SlotStatus.PARTIAL})
        events = emit_dossier_slot_filled_events(pre, post)
        assert len(events) == 1
        assert events[0]["points"] == 2
        assert events[0]["indicator"] == "timing"

    def test_empty_to_partial_capability(self):
        """A5: Capability slot empty->partial: points=3 (int(3.5) floor)."""
        pre = _all_empty_state()
        post = _state_with({DossierSlotName.CAPABILITY: SlotStatus.PARTIAL})
        events = emit_dossier_slot_filled_events(pre, post)
        assert len(events) == 1
        assert events[0]["points"] == 3  # int(3.5) == 3
        assert events[0]["indicator"] == "capability"

    def test_empty_to_partial_motivation(self):
        """A6: Motivation slot empty->partial: points=3."""
        pre = _all_empty_state()
        post = _state_with({DossierSlotName.MOTIVATION: SlotStatus.PARTIAL})
        events = emit_dossier_slot_filled_events(pre, post)
        assert len(events) == 1
        assert events[0]["points"] == 3
        assert events[0]["indicator"] == "motivation"


# ---------------------------------------------------------------------------
# A7: partial -> filled transition
# ---------------------------------------------------------------------------


class TestPartialToFilledTransition:
    """partial->filled fires one event at the slot weight."""

    def test_partial_to_filled_identity(self):
        """A7: Identity partial->filled: one event, points=5."""
        pre = _state_with({DossierSlotName.IDENTITY: SlotStatus.PARTIAL})
        post = _state_with({DossierSlotName.IDENTITY: SlotStatus.FILLED})
        events = emit_dossier_slot_filled_events(pre, post)
        assert len(events) == 1
        ev = events[0]
        assert ev["action"] == "dossier_slot_filled"
        assert ev["points"] == 5
        assert ev["indicator"] == "identity"
        assert "partial" in ev["rule_description"]
        assert "filled" in ev["rule_description"]


# ---------------------------------------------------------------------------
# A8: skip-step empty -> filled (one event, not two)
# ---------------------------------------------------------------------------


class TestSkipStepTransition:
    """empty->filled skip-step emits ONE event (not double-billed)."""

    def test_skip_step_empty_to_filled_identity_one_event(self):
        """A8: Identity empty->filled in one hunt: exactly one event, points=5."""
        pre = _all_empty_state()
        post = _state_with({DossierSlotName.IDENTITY: SlotStatus.FILLED})
        events = emit_dossier_slot_filled_events(pre, post)
        assert len(events) == 1, (
            f"Skip-step must emit exactly ONE event, not {len(events)}: {events}"
        )
        ev = events[0]
        assert ev["points"] == 5
        assert ev["indicator"] == "identity"
        assert "empty" in ev["rule_description"]
        assert "filled" in ev["rule_description"]


# ---------------------------------------------------------------------------
# A9–A11: idempotency / no-transition cases
# ---------------------------------------------------------------------------


class TestIdempotencyAndNoTransition:
    """Idempotent and same-status cases produce zero events."""

    def test_filled_to_filled_no_event(self):
        """A9: Slot already filled — idempotency: zero events."""
        pre = _state_with({DossierSlotName.IDENTITY: SlotStatus.FILLED})
        post = _state_with({DossierSlotName.IDENTITY: SlotStatus.FILLED})
        events = emit_dossier_slot_filled_events(pre, post)
        assert events == []

    def test_partial_to_partial_no_event(self):
        """A10: Slot stays partial — no transition: zero events."""
        pre = _state_with({DossierSlotName.IDENTITY: SlotStatus.PARTIAL})
        post = _state_with({DossierSlotName.IDENTITY: SlotStatus.PARTIAL})
        events = emit_dossier_slot_filled_events(pre, post)
        assert events == []

    def test_empty_to_empty_no_event(self):
        """A11: All slots remain empty — zero events."""
        pre = _all_empty_state()
        post = _all_empty_state()
        events = emit_dossier_slot_filled_events(pre, post)
        assert events == []

    def test_filled_to_partial_no_event(self):
        """Downward transitions (filled->partial) must never fire events."""
        pre = _state_with({DossierSlotName.TTPS: SlotStatus.FILLED})
        post = _state_with({DossierSlotName.TTPS: SlotStatus.PARTIAL})
        events = emit_dossier_slot_filled_events(pre, post)
        assert events == []

    def test_filled_to_empty_no_event(self):
        """Downward transitions (filled->empty) must never fire events."""
        pre = _state_with({DossierSlotName.INFRASTRUCTURE: SlotStatus.FILLED})
        post = _state_with({DossierSlotName.INFRASTRUCTURE: SlotStatus.EMPTY})
        events = emit_dossier_slot_filled_events(pre, post)
        assert events == []


# ---------------------------------------------------------------------------
# A12: deferred target — Predictions/Denial always DEFERRED in M-3
# ---------------------------------------------------------------------------


class TestDeferredSlots:
    """Slots that stay DEFERRED in M-3 inference produce no events."""

    def test_deferred_target_predictions_no_event(self):
        """A12a: Predictions slot stays DEFERRED in M-3 — no event."""
        pre = _all_deferred_state()
        post = _all_deferred_state()
        events = emit_dossier_slot_filled_events(pre, post)
        assert events == []

    def test_deferred_target_denial_no_event(self):
        """A12b: Denial slot stays DEFERRED in M-3 — no event."""
        # Both pre and post have Denial as DEFERRED — no transition, no event
        pre_slots = {
            slot: SlotState(
                name=slot,
                status=SlotStatus.DEFERRED if slot == DossierSlotName.DENIAL else SlotStatus.EMPTY,
            )
            for slot in DossierSlotName
        }
        post_slots = dict(pre_slots)  # identical state
        pre = DossierState(slots=pre_slots, total_sco_count=0)
        post = DossierState(slots=post_slots, total_sco_count=0)
        events = emit_dossier_slot_filled_events(pre, post)
        assert events == []

    def test_deferred_to_deferred_always_silent(self):
        """A12c: deferred->deferred on all slots produces zero events (full all-deferred state)."""
        pre = _all_deferred_state()
        post = _all_deferred_state()
        events = emit_dossier_slot_filled_events(pre, post)
        assert events == []


# ---------------------------------------------------------------------------
# A13: deferred -> real defensive guard (future inference change protection)
# ---------------------------------------------------------------------------


class TestDeferredToRealDefensiveGuard:
    """deferred->real transitions are silently skipped with a debug log."""

    def test_deferred_to_real_status_skipped_with_debug_log(self, caplog):
        """A13: deferred->partial transition is skipped and debug-logged."""
        pre_slots = {
            slot: SlotState(name=slot, status=SlotStatus.DEFERRED) for slot in DossierSlotName
        }
        post_slots = dict(pre_slots)
        # Simulate a future inference change: Predictions moves from deferred to partial
        post_slots[DossierSlotName.PREDICTIONS] = SlotState(
            name=DossierSlotName.PREDICTIONS,
            status=SlotStatus.PARTIAL,
            evidence_count=1,
        )
        pre = DossierState(slots=pre_slots, total_sco_count=0)
        post = DossierState(slots=post_slots, total_sco_count=1)

        with caplog.at_level(logging.DEBUG, logger="adversary_pursuit.dossier.scoring"):
            events = emit_dossier_slot_filled_events(pre, post)

        assert events == [], "deferred->real must produce zero events in M-3"
        # Debug log must mention the skipped slot
        assert any(
            "deferred" in record.message.lower() and "predictions" in record.message.lower()
            for record in caplog.records
        ), (
            f"Expected debug log about deferred->real skip; got: {[r.message for r in caplog.records]}"
        )


# ---------------------------------------------------------------------------
# A14: multiple slot transitions in one hunt
# ---------------------------------------------------------------------------


class TestMultipleSlotTransitions:
    """Multiple slot transitions in one hunt produce correct event count and indicators."""

    def test_multiple_slot_transitions_in_one_hunt(self):
        """A14: 3 empty slots; 2 become partial, 1 becomes filled (skip-step); 3 events."""
        pre = _all_empty_state()
        post = _state_with(
            {
                DossierSlotName.IDENTITY: SlotStatus.FILLED,  # skip-step: empty->filled
                DossierSlotName.TTPS: SlotStatus.PARTIAL,  # empty->partial
                DossierSlotName.INFRASTRUCTURE: SlotStatus.PARTIAL,  # empty->partial
            }
        )
        events = emit_dossier_slot_filled_events(pre, post)
        assert len(events) == 3, f"Expected 3 events; got {len(events)}: {events}"

        indicators = {e["indicator"] for e in events}
        assert "identity" in indicators
        assert "ttps" in indicators
        assert "infrastructure" in indicators

        # Verify points for each slot
        by_indicator = {e["indicator"]: e for e in events}
        assert by_indicator["identity"]["points"] == 5
        assert by_indicator["ttps"]["points"] == 3
        assert by_indicator["infrastructure"]["points"] == 2

    def test_already_filled_slot_not_included(self):
        """Pre-filled slot not counted when another slot transitions."""
        pre = _state_with({DossierSlotName.IDENTITY: SlotStatus.FILLED})
        post = _state_with(
            {
                DossierSlotName.IDENTITY: SlotStatus.FILLED,  # already filled — no event
                DossierSlotName.TTPS: SlotStatus.PARTIAL,  # new transition
            }
        )
        events = emit_dossier_slot_filled_events(pre, post)
        assert len(events) == 1
        assert events[0]["indicator"] == "ttps"


# ---------------------------------------------------------------------------
# A15: event dict shape contract
# ---------------------------------------------------------------------------


class TestEventDictShape:
    """Every returned event has exactly the 4 documented keys with correct types."""

    def test_event_dict_shape_contract(self):
        """A15: action(str), points(int), indicator(str), rule_description(str)."""
        pre = _all_empty_state()
        post = _state_with({DossierSlotName.CAPABILITY: SlotStatus.PARTIAL})
        events = emit_dossier_slot_filled_events(pre, post)
        assert len(events) == 1
        ev = events[0]

        # Exactly 4 keys
        assert set(ev.keys()) == {"action", "points", "indicator", "rule_description"}, (
            f"Unexpected keys: {set(ev.keys())}"
        )

        # Type assertions
        assert isinstance(ev["action"], str)
        assert isinstance(ev["points"], int)
        assert isinstance(ev["indicator"], str)
        assert isinstance(ev["rule_description"], str)

        # Value assertions
        assert ev["action"] == "dossier_slot_filled"
        assert ev["points"] > 0
        assert len(ev["indicator"]) > 0
        assert len(ev["rule_description"]) > 0

    def test_rule_description_is_plain_ascii(self):
        """F64: rule_description must not contain Rich markup brackets."""
        pre = _all_empty_state()
        post = _state_with({DossierSlotName.IDENTITY: SlotStatus.PARTIAL})
        events = emit_dossier_slot_filled_events(pre, post)
        assert len(events) == 1
        desc = events[0]["rule_description"]
        # No Rich markup — no [cyan], [bold], [green] etc.
        assert "[" not in desc and "]" not in desc, (
            f"rule_description contains Rich markup brackets: {desc!r}"
        )

    def test_all_slot_transitions_produce_integer_points(self):
        """Points for every slot are integers (int() floor of float weights)."""
        for slot in DossierSlotName:
            pre = _all_empty_state()
            post_slots = {s: SlotState(name=s, status=SlotStatus.EMPTY) for s in DossierSlotName}
            # Only fire if the slot can actually transition (not deferred in M-3)
            if slot in (
                DossierSlotName.PREDICTIONS,
                DossierSlotName.DENIAL,
                DossierSlotName.TARGETING,
            ):
                # These remain DEFERRED in M-2/M-3 inference — skip
                continue
            post_slots[slot] = SlotState(name=slot, status=SlotStatus.PARTIAL, evidence_count=1)
            post = DossierState(slots=post_slots, total_sco_count=1)
            events = emit_dossier_slot_filled_events(pre, post)
            if events:
                assert isinstance(events[0]["points"], int), (
                    f"Points for slot {slot} is not int: {type(events[0]['points'])}"
                )


# ---------------------------------------------------------------------------
# A16: emit_dossier_prediction_validated_event scaffold (DEC-M3-DOSSIER-005)
# ---------------------------------------------------------------------------


class TestPredictionValidatedScaffold:
    """emit_dossier_prediction_validated_event is importable and returns documented shape."""

    def test_emit_prediction_validated_scaffold_exists(self):
        """A16: Function is importable, returns action='dossier_prediction_validated', points=4."""
        prediction = PredictionRecord(text="APT actor will target EU energy sector Q2 2026")
        result = emit_dossier_prediction_validated_event(prediction)

        assert isinstance(result, dict), "Must return a dict"
        assert set(result.keys()) == {"action", "points", "indicator", "rule_description"}, (
            f"Unexpected keys: {set(result.keys())}"
        )
        assert result["action"] == "dossier_prediction_validated"
        assert result["points"] == 4  # int(SLOT_WEIGHTS[PREDICTIONS]) == int(4.0) == 4
        assert isinstance(result["indicator"], str) and len(result["indicator"]) > 0
        assert isinstance(result["rule_description"], str) and len(result["rule_description"]) > 0

    def test_prediction_validated_event_not_emitted_by_slot_emitter(self):
        """DEC-M3-DOSSIER-005: emit_dossier_slot_filled_events never returns prediction_validated."""
        pre = _all_empty_state()
        post = _state_with({DossierSlotName.IDENTITY: SlotStatus.PARTIAL})
        events = emit_dossier_slot_filled_events(pre, post)
        for ev in events:
            assert ev["action"] != "dossier_prediction_validated", (
                "prediction_validated must not be emitted by slot emitter in M-3"
            )

    def test_prediction_validated_rule_description_non_empty(self):
        """Scaffold rule_description is a non-empty plain ASCII string."""
        prediction = PredictionRecord(text="test prediction")
        result = emit_dossier_prediction_validated_event(prediction)
        desc = result["rule_description"]
        assert len(desc) > 0
        assert "[" not in desc and "]" not in desc, f"Rich markup in scaffold desc: {desc!r}"

    def test_different_predictions_produce_different_indicators(self):
        """Two different PredictionRecord texts produce different indicator values."""
        p1 = PredictionRecord(text="prediction A")
        p2 = PredictionRecord(text="prediction B")
        r1 = emit_dossier_prediction_validated_event(p1)
        r2 = emit_dossier_prediction_validated_event(p2)
        assert r1["indicator"] != r2["indicator"], (
            "Different prediction texts should produce different indicator strings"
        )

    def test_same_prediction_produces_same_indicator(self):
        """Same PredictionRecord text always produces the same indicator (deterministic)."""
        text = "repeatable prediction text"
        p1 = PredictionRecord(text=text)
        p2 = PredictionRecord(text=text)
        r1 = emit_dossier_prediction_validated_event(p1)
        r2 = emit_dossier_prediction_validated_event(p2)
        assert r1["indicator"] == r2["indicator"]


# ---------------------------------------------------------------------------
# Compound: production sequence — all events together in one hunt
# ---------------------------------------------------------------------------


class TestCompoundProductionSequence:
    """Compound test: pre/post dossier diff across multiple slot types."""

    def test_compound_hunt_produces_ordered_events(self):
        """Multiple slot transitions: verify all indicators present and points correct."""
        # Simulate a hunt that:
        # - moves Identity from empty to partial (+5)
        # - moves TTPs from empty to filled skip-step (+3)
        # - Motivation was already partial, stays partial (no event)
        # - Infrastructure stays empty (no event)
        pre = _state_with({DossierSlotName.MOTIVATION: SlotStatus.PARTIAL})
        post = _state_with(
            {
                DossierSlotName.IDENTITY: SlotStatus.PARTIAL,
                DossierSlotName.TTPS: SlotStatus.FILLED,
                DossierSlotName.MOTIVATION: SlotStatus.PARTIAL,  # unchanged
            }
        )
        events = emit_dossier_slot_filled_events(pre, post)

        # Exactly 2 events (Identity and TTPs transitioned; Motivation unchanged)
        assert len(events) == 2
        indicators = {e["indicator"] for e in events}
        assert "identity" in indicators
        assert "ttps" in indicators
        assert "motivation" not in indicators

        by_ind = {e["indicator"]: e for e in events}
        assert by_ind["identity"]["points"] == 5
        assert by_ind["ttps"]["points"] == 3

    def test_no_events_returned_on_no_new_scos(self):
        """Hunt that stores zero SCOs produces zero dossier events."""
        # pre and post are identical (no new evidence)
        state = _state_with({DossierSlotName.IDENTITY: SlotStatus.PARTIAL})
        events = emit_dossier_slot_filled_events(state, state)
        assert events == []
