"""Tests for dossier/state.py — M-4 DossierState persistence + overlay.

Evaluation Contract gates (test_dossier_state.py ~12 tests):
  S1  load returns None on fresh workspace
  S2  default_deferred_state returns valid DossierState with all 9 slots
  S3  save then load round-trips
  S4  second save replaces first (sentinel uniqueness: exactly one row after N writes)
  S5  JSON deserializer rejects unknown slot key with loud ValueError
  S6  JSON deserializer rejects unknown SlotStatus value with loud ValueError
  S7  schema_version=1 round-trips; schema_version=2 raises loud RuntimeError
  S8  apply_predictions_overlay: 0 entries => EMPTY
  S9  apply_predictions_overlay: 1 pending => PARTIAL
  S10 apply_predictions_overlay: 2 validated => FILLED
  S11 apply_predictions_overlay: mixed (1 validated + 3 pending) => PARTIAL
  S12 apply_predictions_overlay: does not mutate input state (frozen dataclass discipline)

@decision DEC-M4-PERSIST-001
@title Persistent DossierState storage authority is the F63 sentinel-row pattern
@status accepted
@rationale Tests verify the sentinel-row pattern: exactly one row per workspace,
    JSON payload in indicator, points=0, excluded from get_recent_scores().

@decision DEC-M4-PERSIST-003
@title JSON envelope carries schema_version=1; mismatched versions raise loud RuntimeError
@status accepted
@rationale Tests verify both the happy path and the loud failure path.
"""

from __future__ import annotations

import json

import pytest

from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.dossier.predictions import ExpectedEvidence, PersistedPrediction
from adversary_pursuit.dossier.slot_inference import DossierState, SlotState
from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus
from adversary_pursuit.dossier.state import (
    DOSSIER_STATE_SENTINEL_ACTION,
    _deserialize_dossier_state,
    _serialize_dossier_state,
    apply_predictions_overlay,
    default_deferred_state,
    load_dossier_state,
    save_dossier_state,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workspace(tmp_path) -> WorkspaceManager:
    wm = WorkspaceManager(workspace_dir=tmp_path)
    wm.create("default")
    wm.switch("default")
    return wm


def _all_empty_state() -> DossierState:
    slots = {slot: SlotState(name=slot, status=SlotStatus.EMPTY) for slot in DossierSlotName}
    return DossierState(slots=slots, total_sco_count=5)


def _make_persisted_prediction(
    pid: str = "pred-00000001",
    status: str = "pending",
) -> PersistedPrediction:
    return PersistedPrediction(
        prediction_id=pid,
        text="Actor pivots to .ru infrastructure.",
        slot="infrastructure",
        status=status,
        expected_evidence=ExpectedEvidence(value_regex=r".*\.ru$"),
        created_at="2026-06-01T00:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# S1: load returns None on fresh workspace
# ---------------------------------------------------------------------------


class TestLoadFreshWorkspace:
    def test_load_returns_none_on_fresh_workspace(self, tmp_path):
        """S1: fresh workspace has no sentinel row — load returns None."""
        wm = _make_workspace(tmp_path)
        result = load_dossier_state(wm)
        assert result is None


# ---------------------------------------------------------------------------
# S2: default_deferred_state
# ---------------------------------------------------------------------------


class TestDefaultDeferredState:
    def test_returns_valid_dossier_state_with_all_9_slots(self):
        """S2: default_deferred_state returns DossierState with all 9 slots in DEFERRED."""
        state = default_deferred_state()
        assert isinstance(state, DossierState)
        assert len(state.slots) == 9
        for slot in DossierSlotName:
            assert slot in state.slots
            assert state.slots[slot].status is SlotStatus.DEFERRED

    def test_default_state_total_sco_count_is_zero(self):
        """Default state has total_sco_count=0."""
        state = default_deferred_state()
        assert state.total_sco_count == 0


# ---------------------------------------------------------------------------
# S3: save then load round-trips
# ---------------------------------------------------------------------------


class TestSaveLoadRoundTrip:
    def test_save_then_load_round_trips(self, tmp_path):
        """S3: state saved via save_dossier_state is faithfully restored by load."""
        wm = _make_workspace(tmp_path)
        state = _all_empty_state()
        save_dossier_state(wm, state)
        loaded = load_dossier_state(wm)
        assert loaded is not None
        assert loaded.total_sco_count == state.total_sco_count
        for slot in DossierSlotName:
            assert loaded.slots[slot].status == state.slots[slot].status

    def test_all_slot_statuses_round_trip(self, tmp_path):
        """All SlotStatus values survive serialization round-trip."""
        wm = _make_workspace(tmp_path)
        # Build a state with all four statuses represented
        statuses = [SlotStatus.EMPTY, SlotStatus.PARTIAL, SlotStatus.FILLED, SlotStatus.DEFERRED]
        slots = {}
        slot_list = list(DossierSlotName)
        for i, slot in enumerate(slot_list):
            slots[slot] = SlotState(
                name=slot,
                status=statuses[i % len(statuses)],
                evidence_count=i,
                contributing_types=frozenset({f"type-{i}"}) if i > 0 else frozenset(),
            )
        state = DossierState(slots=slots, total_sco_count=42)
        save_dossier_state(wm, state)
        loaded = load_dossier_state(wm)
        assert loaded is not None
        assert loaded.total_sco_count == 42
        for slot in DossierSlotName:
            assert loaded.slots[slot].status == state.slots[slot].status
            assert loaded.slots[slot].evidence_count == state.slots[slot].evidence_count


# ---------------------------------------------------------------------------
# S4: sentinel uniqueness — second save replaces first
# ---------------------------------------------------------------------------


class TestSentinelUniqueness:
    def test_second_save_replaces_first(self, tmp_path):
        """S4: multiple saves leave exactly one _dossier_state_snapshot row."""
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from adversary_pursuit.models.database import ScoreEvent

        wm = _make_workspace(tmp_path)
        state1 = _all_empty_state()
        state2 = default_deferred_state()

        for _ in range(5):
            save_dossier_state(wm, state1)
        save_dossier_state(wm, state2)

        with Session(wm._engine) as session:
            rows = (
                session.execute(
                    select(ScoreEvent).where(ScoreEvent.action == DOSSIER_STATE_SENTINEL_ACTION)
                )
                .scalars()
                .all()
            )
        assert len(rows) == 1

    def test_load_returns_last_saved_state(self, tmp_path):
        """After multiple saves, load returns the most recent state."""
        wm = _make_workspace(tmp_path)
        state1 = _all_empty_state()
        save_dossier_state(wm, state1)

        # Save a second state with all PARTIAL
        slots = {
            slot: SlotState(name=slot, status=SlotStatus.PARTIAL, evidence_count=1)
            for slot in DossierSlotName
        }
        state2 = DossierState(slots=slots, total_sco_count=99)
        save_dossier_state(wm, state2)

        loaded = load_dossier_state(wm)
        assert loaded is not None
        assert loaded.total_sco_count == 99
        for slot in DossierSlotName:
            assert loaded.slots[slot].status is SlotStatus.PARTIAL

    def test_sentinel_row_has_zero_points(self, tmp_path):
        """Sentinel row points=0 so it never affects get_total_score()."""
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from adversary_pursuit.models.database import ScoreEvent

        wm = _make_workspace(tmp_path)
        save_dossier_state(wm, _all_empty_state())
        with Session(wm._engine) as session:
            row = session.execute(
                select(ScoreEvent).where(ScoreEvent.action == DOSSIER_STATE_SENTINEL_ACTION)
            ).scalar_one()
        assert row.points == 0


# ---------------------------------------------------------------------------
# S5: unknown slot key raises ValueError
# ---------------------------------------------------------------------------


class TestDeserializationErrors:
    def test_unknown_slot_key_raises_value_error(self):
        """S5: deserializer rejects unknown slot key with loud ValueError."""
        bad_payload = json.dumps(
            {
                "schema_version": 1,
                "slots": {
                    "identity": {
                        "status": "empty",
                        "evidence_count": 0,
                        "name": "identity",
                        "contributing_types": [],
                    },
                    "UNKNOWN_SLOT_XYZ": {
                        "status": "empty",
                        "evidence_count": 0,
                        "name": "UNKNOWN_SLOT_XYZ",
                        "contributing_types": [],
                    },
                },
                "total_sco_count": 0,
            }
        )
        with pytest.raises(ValueError, match="unknown slot key"):
            _deserialize_dossier_state(bad_payload)

    def test_unknown_slot_status_raises_value_error(self):
        """S6: deserializer rejects unknown SlotStatus value with loud ValueError."""
        bad_payload = json.dumps(
            {
                "schema_version": 1,
                "slots": {
                    "identity": {
                        "status": "INVALID_STATUS_999",
                        "evidence_count": 0,
                        "name": "identity",
                        "contributing_types": [],
                    },
                },
                "total_sco_count": 0,
            }
        )
        with pytest.raises(ValueError, match="unknown SlotStatus value"):
            _deserialize_dossier_state(bad_payload)

    def test_schema_version_mismatch_raises_runtime_error(self):
        """S7: schema_version != 1 raises loud RuntimeError (DEC-M4-PERSIST-003)."""
        bad_payload = json.dumps(
            {
                "schema_version": 2,
                "slots": {},
                "total_sco_count": 0,
            }
        )
        with pytest.raises(RuntimeError, match="schema version 2"):
            _deserialize_dossier_state(bad_payload)

    def test_schema_version_1_round_trips_cleanly(self, tmp_path):
        """S7 happy path: schema_version=1 round-trips without error."""
        wm = _make_workspace(tmp_path)
        state = _all_empty_state()
        save_dossier_state(wm, state)
        loaded = load_dossier_state(wm)
        assert loaded is not None  # no exception means version matched

    def test_serialized_payload_contains_schema_version_1(self):
        """_serialize_dossier_state embeds schema_version=1 in the envelope."""
        state = _all_empty_state()
        payload = _serialize_dossier_state(state)
        envelope = json.loads(payload)
        assert envelope["schema_version"] == 1


# ---------------------------------------------------------------------------
# S8–S12: apply_predictions_overlay
# ---------------------------------------------------------------------------


class TestApplyPredictionsOverlay:
    def _base_state(self) -> DossierState:
        """DossierState with Predictions slot DEFERRED (M-2 baseline)."""
        slots = {
            slot: SlotState(
                name=slot,
                status=SlotStatus.DEFERRED
                if slot is DossierSlotName.PREDICTIONS
                else SlotStatus.EMPTY,
            )
            for slot in DossierSlotName
        }
        return DossierState(slots=slots, total_sco_count=0)

    def test_zero_predictions_gives_empty(self):
        """S8: 0 predictions => Predictions slot EMPTY."""
        state = self._base_state()
        result = apply_predictions_overlay(state, [])
        assert result.slots[DossierSlotName.PREDICTIONS].status is SlotStatus.EMPTY

    def test_one_pending_gives_partial(self):
        """S9: 1 pending prediction => Predictions slot PARTIAL."""
        state = self._base_state()
        predictions = [_make_persisted_prediction(status="pending")]
        result = apply_predictions_overlay(state, predictions)
        assert result.slots[DossierSlotName.PREDICTIONS].status is SlotStatus.PARTIAL

    def test_two_validated_gives_filled(self):
        """S10: 2 validated predictions => Predictions slot FILLED."""
        state = self._base_state()
        predictions = [
            _make_persisted_prediction(pid="pred-00000001", status="validated"),
            _make_persisted_prediction(pid="pred-00000002", status="validated"),
        ]
        result = apply_predictions_overlay(state, predictions)
        assert result.slots[DossierSlotName.PREDICTIONS].status is SlotStatus.FILLED

    def test_mixed_one_validated_three_pending_gives_partial(self):
        """S11: mixed (1 validated + 3 pending) => PARTIAL (not yet 2 validated)."""
        state = self._base_state()
        predictions = [
            _make_persisted_prediction(pid="pred-00000001", status="validated"),
            _make_persisted_prediction(pid="pred-00000002", status="pending"),
            _make_persisted_prediction(pid="pred-00000003", status="pending"),
            _make_persisted_prediction(pid="pred-00000004", status="pending"),
        ]
        result = apply_predictions_overlay(state, predictions)
        assert result.slots[DossierSlotName.PREDICTIONS].status is SlotStatus.PARTIAL

    def test_overlay_does_not_mutate_input_state(self):
        """S12: apply_predictions_overlay returns a new DossierState; input is unchanged."""
        state = self._base_state()
        original_predictions_status = state.slots[DossierSlotName.PREDICTIONS].status
        predictions = [
            _make_persisted_prediction(status="validated"),
            _make_persisted_prediction(pid="pred-00000002", status="validated"),
        ]
        result = apply_predictions_overlay(state, predictions)
        # Input unchanged
        assert state.slots[DossierSlotName.PREDICTIONS].status is original_predictions_status
        # Result updated
        assert result.slots[DossierSlotName.PREDICTIONS].status is SlotStatus.FILLED
        # Other slots preserved
        for slot in DossierSlotName:
            if slot is not DossierSlotName.PREDICTIONS:
                assert result.slots[slot].status == state.slots[slot].status

    def test_overlay_evidence_count_matches_predictions_list_length(self):
        """Predictions slot evidence_count equals len(predictions)."""
        state = self._base_state()
        predictions = [
            _make_persisted_prediction(pid=f"pred-{i:08x}", status="pending") for i in range(3)
        ]
        result = apply_predictions_overlay(state, predictions)
        assert result.slots[DossierSlotName.PREDICTIONS].evidence_count == 3

    def test_sentinel_excluded_from_recent_scores(self, tmp_path):
        """Saved dossier state sentinel row excluded from get_recent_scores()."""
        wm = _make_workspace(tmp_path)
        wm.store_score_events([{"action": "new_ip", "points": 10, "indicator": "1.2.3.4"}])
        save_dossier_state(wm, _all_empty_state())
        recent = wm.get_recent_scores(limit=50)
        actions = {e["action"] for e in recent}
        assert DOSSIER_STATE_SENTINEL_ACTION not in actions
        assert "new_ip" in actions


# ---------------------------------------------------------------------------
# M-5: apply_predictions_overlay with falsified entries
# (plan §4: falsified entries count toward PARTIAL but NOT FILLED)
# ---------------------------------------------------------------------------


def _make_falsified_pred(pid: str = "pred-fal-001") -> PersistedPrediction:
    return PersistedPrediction(
        prediction_id=pid,
        text="Actor will pivot to .ru.",
        slot="infrastructure",
        status="falsified",
        expected_evidence=ExpectedEvidence(sco_type="domain-name"),
        created_at="2026-06-01T00:00:00+00:00",
    )


def _make_validated_pred(pid: str = "pred-val-001") -> PersistedPrediction:
    return PersistedPrediction(
        prediction_id=pid,
        text="Actor uses .ru domains.",
        slot="infrastructure",
        status="validated",
        expected_evidence=ExpectedEvidence(sco_type="domain-name"),
        created_at="2026-06-01T00:00:00+00:00",
        validated_at="2026-06-02T00:00:00+00:00",
        validated_by_sco_id="domain-name--fake",
    )


class TestApplyPredictionsOverlayWithFalsified:
    """M-5 overlay semantics: falsified entries count as engagement (PARTIAL), not FILLED.

    Plan §4: falsified entries do NOT count toward validated_count (not FILLED),
    but DO satisfy len(predictions) >= 1 (PARTIAL rather than EMPTY).
    """

    def test_falsified_only_yields_partial(self):
        """[falsified] only -> PARTIAL (not EMPTY; ≥1 entry threshold satisfied)."""
        preds = [_make_falsified_pred("pred-f1")]
        result = apply_predictions_overlay(_all_empty_state(), preds)
        predictions_slot = result.slots[DossierSlotName.PREDICTIONS]
        assert predictions_slot.status == SlotStatus.PARTIAL, (
            f"[falsified] should yield PARTIAL (engagement without validation), "
            f"got {predictions_slot.status}"
        )

    def test_two_falsified_yields_partial(self):
        """[falsified, falsified] -> PARTIAL (no validated entries; not FILLED)."""
        preds = [_make_falsified_pred("pred-f1"), _make_falsified_pred("pred-f2")]
        result = apply_predictions_overlay(_all_empty_state(), preds)
        predictions_slot = result.slots[DossierSlotName.PREDICTIONS]
        assert predictions_slot.status == SlotStatus.PARTIAL

    def test_two_validated_plus_falsified_yields_filled(self):
        """[validated, validated, falsified] -> FILLED (≥2 validated; falsified does not block)."""
        preds = [
            _make_validated_pred("pred-v1"),
            _make_validated_pred("pred-v2"),
            _make_falsified_pred("pred-f1"),
        ]
        result = apply_predictions_overlay(_all_empty_state(), preds)
        predictions_slot = result.slots[DossierSlotName.PREDICTIONS]
        assert predictions_slot.status == SlotStatus.FILLED, (
            f"[validated, validated, falsified] should yield FILLED, got {predictions_slot.status}"
        )
