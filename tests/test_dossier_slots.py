"""Tests for dossier/slots.py — schema vocabulary, weights, and status enum.

@decision DEC-M1-DOSSIER-002 (status enum coverage)
@title Test suite exercises the 9-slot vocabulary, Phase 16 weights, and {empty, partial, filled, deferred} status
@status accepted
@rationale The Evaluation Contract requires 3 schema tests:
    - test_nine_slot_vocabulary_matches_schema_v1
    - test_slot_weights_match_phase16_table
    - test_slot_status_vocabulary_is_empty_partial_filled_deferred
   These guard against accidental schema mutation before M-2 lands; any implementer
   who adds or removes a slot or changes a weight without a planner re-stage will
   break these tests first.
"""

from __future__ import annotations

from adversary_pursuit.dossier.slots import (
    SLOT_WEIGHTS,
    DossierSlotName,
    SlotStatus,
)


class TestNineSlotVocabulary:
    """Guard that the 9-slot schema v1.0 (Phase 16 §3) is unchanged at M-1 landing."""

    def test_nine_slot_vocabulary_matches_schema_v1(self):
        """DEC-68-DOSSIER-REFRAME-010: 9 canonical slots, names match §3 table."""
        expected_names = {
            "identity",
            "ttps",
            "infrastructure",
            "timing",
            "targeting",
            "capability",
            "motivation",
            "predictions",
            "denial",
        }
        actual_names = {s.value for s in DossierSlotName}
        assert actual_names == expected_names, (
            f"Slot vocabulary mismatch. Expected {expected_names}, got {actual_names}. "
            "Changing the 9-slot vocabulary requires a planner re-stage and a successor DEC-ID "
            "(DEC-68-DOSSIER-REFRAME-010)."
        )

    def test_slot_weights_match_phase16_table(self):
        """Slot weights must match the Phase 16 §3 table exactly.

        Weights per roadmap §3:
          Identity (5.0) — highest, puzzle keystone
          Predictions (4.0) — deep analytic signal
          Capability (3.5) — rare and predictive
          TTPs (3.0) — analytic-value backbone
          Motivation (3.0) — analytic-value backbone
          Targeting (2.5) — downstream-derivable
          Denial (2.5) — downstream-derivable
          Infrastructure (2.0) — baseline-above-routine
          Timing (2.0) — baseline-above-routine
        """
        expected_weights = {
            DossierSlotName.IDENTITY: 5.0,
            DossierSlotName.PREDICTIONS: 4.0,
            DossierSlotName.CAPABILITY: 3.5,
            DossierSlotName.TTPS: 3.0,
            DossierSlotName.MOTIVATION: 3.0,
            DossierSlotName.TARGETING: 2.5,
            DossierSlotName.DENIAL: 2.5,
            DossierSlotName.INFRASTRUCTURE: 2.0,
            DossierSlotName.TIMING: 2.0,
        }
        assert SLOT_WEIGHTS == expected_weights, (
            f"Slot weight table diverged from Phase 16 §3. "
            f"Diff: {set(SLOT_WEIGHTS.items()) ^ set(expected_weights.items())}. "
            "Weight changes require M-3 Evaluation Contract, not M-1."
        )

    def test_all_slots_have_weights_defined(self):
        """Every DossierSlotName must appear in SLOT_WEIGHTS — no orphaned slots."""
        for slot in DossierSlotName:
            assert slot in SLOT_WEIGHTS, (
                f"Slot {slot!r} is missing from SLOT_WEIGHTS. "
                "Every slot in the vocabulary must have a weight defined."
            )


class TestSlotStatusVocabulary:
    """Guard the {empty, partial, filled, deferred} status enum (DEC-M1-DOSSIER-002)."""

    def test_slot_status_vocabulary_is_empty_partial_filled_deferred(self):
        """DEC-M1-DOSSIER-002: exactly four status values — no additions without planner approval."""
        expected_values = {"empty", "partial", "filled", "deferred"}
        actual_values = {s.value for s in SlotStatus}
        assert actual_values == expected_values, (
            f"SlotStatus vocabulary mismatch. Expected {expected_values}, got {actual_values}. "
            "Adding or removing status values requires a planner re-stage."
        )

    def test_slot_status_members_count(self):
        """Exactly 4 SlotStatus members — guards against silent additions."""
        assert len(list(SlotStatus)) == 4

    def test_slot_status_values_are_strings(self):
        """Status values are plain strings for easy JSON serialisation."""
        for status in SlotStatus:
            assert isinstance(status.value, str)
