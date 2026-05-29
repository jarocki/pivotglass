"""Tests for dossier/slots.py — schema vocabulary, weights, status enum,
and M-2 scaffold dataclasses (PredictionRecord, DenialStrategyRecord).

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

@decision DEC-M2-DOSSIER-004
@title PredictionRecord / DenialStrategyRecord are typed scaffold dataclasses in slots.py
@status accepted
@rationale M-2 ships typed shapes for both slot 8 (Predictions) and slot 9 (Denial/Deception).
    The actual inference for these slots is deferred to M-4/M-5. Having typed dataclasses
    here (a) lets callers import the shapes now, (b) prevents future implementers from
    inventing incompatible shapes, and (c) is testable without any new persistence.
"""

from __future__ import annotations

import dataclasses

from adversary_pursuit.dossier.slots import (
    SLOT_WEIGHTS,
    DenialStrategyRecord,
    DossierSlotName,
    PredictionRecord,
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


# ---------------------------------------------------------------------------
# M-2 scaffold dataclasses — DEC-M2-DOSSIER-004
# ---------------------------------------------------------------------------


class TestPredictionRecord:
    """PredictionRecord is a typed scaffold dataclass for slot 8 (Predictions Log)."""

    def test_prediction_record_is_dataclass(self):
        """PredictionRecord is a dataclass (importable from slots.py)."""
        assert dataclasses.is_dataclass(PredictionRecord)

    def test_prediction_record_has_text_field(self):
        """PredictionRecord has a 'text' field for the prediction content."""
        fields = {f.name for f in dataclasses.fields(PredictionRecord)}
        assert "text" in fields, f"PredictionRecord missing 'text' field. Got: {fields}"

    def test_prediction_record_has_status_field(self):
        """PredictionRecord has a 'status' field (pending/validated/falsified)."""
        fields = {f.name for f in dataclasses.fields(PredictionRecord)}
        assert "status" in fields, f"PredictionRecord missing 'status' field. Got: {fields}"

    def test_prediction_record_default_status_is_pending(self):
        """PredictionRecord default status is 'pending'."""
        rec = PredictionRecord(text="Actor will pivot to Tor infrastructure.")
        assert rec.status == "pending", (
            f"PredictionRecord default status should be 'pending', got '{rec.status}'"
        )

    def test_prediction_record_can_be_constructed(self):
        """PredictionRecord can be constructed with text only (status defaults)."""
        rec = PredictionRecord(text="Actor will use Cobalt Strike next.")
        assert rec.text == "Actor will use Cobalt Strike next."

    def test_prediction_record_validated_status(self):
        """PredictionRecord status can be set to 'validated'."""
        rec = PredictionRecord(text="Actor will pivot to Tor.", status="validated")
        assert rec.status == "validated"

    def test_prediction_record_falsified_status(self):
        """PredictionRecord status can be set to 'falsified'."""
        rec = PredictionRecord(text="Actor will go silent.", status="falsified")
        assert rec.status == "falsified"


class TestDenialStrategyRecord:
    """DenialStrategyRecord is a typed scaffold dataclass for slot 9 (Denial/Deception Strategies)."""

    def test_denial_strategy_record_is_dataclass(self):
        """DenialStrategyRecord is a dataclass (importable from slots.py)."""
        assert dataclasses.is_dataclass(DenialStrategyRecord)

    def test_denial_strategy_record_has_strategy_field(self):
        """DenialStrategyRecord has a 'strategy' field for the countermeasure text."""
        fields = {f.name for f in dataclasses.fields(DenialStrategyRecord)}
        assert "strategy" in fields, f"DenialStrategyRecord missing 'strategy' field. Got: {fields}"

    def test_denial_strategy_record_has_linked_evidence_field(self):
        """DenialStrategyRecord has a 'linked_evidence' field for evidence pointers."""
        fields = {f.name for f in dataclasses.fields(DenialStrategyRecord)}
        assert "linked_evidence" in fields, (
            f"DenialStrategyRecord missing 'linked_evidence' field. Got: {fields}"
        )

    def test_denial_strategy_record_default_linked_evidence_is_empty(self):
        """DenialStrategyRecord default linked_evidence is empty list."""
        rec = DenialStrategyRecord(strategy="Block all Tor exit nodes at perimeter.")
        assert rec.linked_evidence == [], (
            f"DenialStrategyRecord default linked_evidence should be [], got {rec.linked_evidence}"
        )

    def test_denial_strategy_record_can_be_constructed(self):
        """DenialStrategyRecord can be constructed with strategy only."""
        rec = DenialStrategyRecord(strategy="Honeypot the actor's preferred registrar.")
        assert rec.strategy == "Honeypot the actor's preferred registrar."

    def test_denial_strategy_record_accepts_linked_evidence(self):
        """DenialStrategyRecord accepts a list of evidence pointer strings."""
        rec = DenialStrategyRecord(
            strategy="Block Cobalt Strike C2 beacons.",
            linked_evidence=["domain-name--001", "ipv4-addr--002"],
        )
        assert len(rec.linked_evidence) == 2
        assert "domain-name--001" in rec.linked_evidence
