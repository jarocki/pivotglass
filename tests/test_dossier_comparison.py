"""Tests for dossier/comparison.py — slot-by-slot dossier diffing.

Covers DEC-M9-COMPLETION-001 (weighted completion math),
DEC-M9-PRED-RATIO-001 (validated-prediction ratio),
and the pure-function / F64 invariants.

@decision DEC-M9-TEST-COMPARISON-001
@title compare_dossiers test suite verifies completion math, slot diff, and purity
@status accepted
@rationale Tests cover the full DEC-M9-COMPLETION-001 formula (filled=1.0,
    partial=0.5, empty=0.0, deferred=0.0 weighted by SLOT_WEIGHTS), the
    DEC-M9-PRED-RATIO-001 edge cases (0/0, N/0, N/N, mixed), slot-by-slot
    diff correctness across all 9 slots, unique-slot-fill lists, and the
    plain-ASCII summary_line F64 invariant. Self-compare always yields
    equal completion and all-same slot_diff tuples.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.dossier.comparison import (
    compare_dossiers,
    format_comparison_report,
)
from adversary_pursuit.dossier.export import export_dossier
from adversary_pursuit.dossier.import_ import ImportedDossier, import_dossier
from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_imported_dossier(
    actor_identifier: str = "test-actor",
    slot_overrides: dict | None = None,
    predictions: list | None = None,
    analyst_notes: list[str] | None = None,
) -> ImportedDossier:
    """Build an ImportedDossier with all slots defaulting to DEFERRED, overridable per slot."""
    base_states = {slot: SlotStatus.DEFERRED for slot in DossierSlotName}
    if slot_overrides:
        base_states.update(slot_overrides)
    return ImportedDossier(
        actor_identifier=actor_identifier,
        slot_states=base_states,
        predictions=predictions or [],
        analyst_notes=analyst_notes or [],
        metadata={"x_ap_dossier_schema_version": "1"},
    )


def _make_persisted_prediction(status: str = "pending") -> object:
    """Build a minimal PersistedPrediction for ratio tests."""
    from adversary_pursuit.dossier.predictions import ExpectedEvidence, PersistedPrediction

    return PersistedPrediction(
        prediction_id=f"pred-{status}-001",
        text=f"Test prediction ({status})",
        slot="infrastructure",
        status=status,
        expected_evidence=ExpectedEvidence(sco_type="domain-name"),
        created_at="2024-01-01T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# Self-compare: all slots equal, completion_local == completion_remote
# ---------------------------------------------------------------------------


class TestSelfCompare:
    """Comparing a dossier against itself yields identical results."""

    def test_self_compare_all_slot_diff_equal(self):
        d = _make_imported_dossier()
        report = compare_dossiers(d, d)
        for slot, (local_s, remote_s) in report.slot_diff.items():
            assert local_s == remote_s, f"Self-compare: slot {slot} should have equal statuses"

    def test_self_compare_completion_equal(self):
        d = _make_imported_dossier()
        report = compare_dossiers(d, d)
        assert report.completion_local == report.completion_remote

    def test_self_compare_no_unique_slots(self):
        d = _make_imported_dossier(slot_overrides={DossierSlotName.IDENTITY: SlotStatus.FILLED})
        report = compare_dossiers(d, d)
        assert report.unique_to_local == []
        assert report.unique_to_remote == []

    def test_self_compare_pred_ratios_equal(self):
        preds = [_make_persisted_prediction("validated"), _make_persisted_prediction("pending")]
        d = _make_imported_dossier(predictions=preds)
        report = compare_dossiers(d, d)
        assert report.prediction_validation_ratio_local == report.prediction_validation_ratio_remote


# ---------------------------------------------------------------------------
# slot_diff correctness
# ---------------------------------------------------------------------------


class TestSlotDiff:
    """Slot-by-slot diff captures local vs remote status correctly."""

    def test_one_slot_flip_appears_in_diff(self):
        local = _make_imported_dossier(slot_overrides={DossierSlotName.IDENTITY: SlotStatus.FILLED})
        remote = _make_imported_dossier(slot_overrides={DossierSlotName.IDENTITY: SlotStatus.EMPTY})
        report = compare_dossiers(local, remote)
        local_s, remote_s = report.slot_diff[DossierSlotName.IDENTITY]
        assert local_s == SlotStatus.FILLED
        assert remote_s == SlotStatus.EMPTY

    def test_all_9_slots_present_in_diff(self):
        local = _make_imported_dossier()
        remote = _make_imported_dossier()
        report = compare_dossiers(local, remote)
        assert len(report.slot_diff) == 9
        for slot in DossierSlotName:
            assert slot in report.slot_diff

    def test_unique_to_local_detected(self):
        """Local filled, remote empty -> appears in unique_to_local."""
        local = _make_imported_dossier(
            slot_overrides={DossierSlotName.INFRASTRUCTURE: SlotStatus.FILLED}
        )
        remote = _make_imported_dossier(
            slot_overrides={DossierSlotName.INFRASTRUCTURE: SlotStatus.EMPTY}
        )
        report = compare_dossiers(local, remote)
        assert DossierSlotName.INFRASTRUCTURE in report.unique_to_local
        assert DossierSlotName.INFRASTRUCTURE not in report.unique_to_remote

    def test_unique_to_remote_detected(self):
        """Remote filled, local empty -> appears in unique_to_remote."""
        local = _make_imported_dossier(slot_overrides={DossierSlotName.TTPS: SlotStatus.EMPTY})
        remote = _make_imported_dossier(slot_overrides={DossierSlotName.TTPS: SlotStatus.PARTIAL})
        report = compare_dossiers(local, remote)
        assert DossierSlotName.TTPS in report.unique_to_remote
        assert DossierSlotName.TTPS not in report.unique_to_local

    def test_partial_counts_as_substantive(self):
        """partial status is 'substantive' for unique-slot detection."""
        local = _make_imported_dossier(
            slot_overrides={DossierSlotName.CAPABILITY: SlotStatus.PARTIAL}
        )
        remote = _make_imported_dossier()  # all DEFERRED
        report = compare_dossiers(local, remote)
        assert DossierSlotName.CAPABILITY in report.unique_to_local

    def test_deferred_not_unique(self):
        """deferred on both sides -> not unique to either."""
        local = _make_imported_dossier()  # all DEFERRED
        remote = _make_imported_dossier()  # all DEFERRED
        report = compare_dossiers(local, remote)
        assert report.unique_to_local == []
        assert report.unique_to_remote == []


# ---------------------------------------------------------------------------
# Completion math (DEC-M9-COMPLETION-001)
# ---------------------------------------------------------------------------


class TestCompletionMath:
    """Weighted completion formula: filled=1.0, partial=0.5, empty=0.0, deferred=0.0."""

    def test_all_deferred_completion_is_zero(self):
        d = _make_imported_dossier()  # all DEFERRED
        report = compare_dossiers(d, d)
        assert report.completion_local == pytest.approx(0.0)

    def test_all_filled_completion_is_one(self):
        d = _make_imported_dossier(
            slot_overrides={slot: SlotStatus.FILLED for slot in DossierSlotName}
        )
        report = compare_dossiers(d, d)
        assert report.completion_local == pytest.approx(1.0)

    def test_all_empty_completion_is_zero(self):
        d = _make_imported_dossier(
            slot_overrides={slot: SlotStatus.EMPTY for slot in DossierSlotName}
        )
        report = compare_dossiers(d, d)
        assert report.completion_local == pytest.approx(0.0)

    def test_all_partial_completion_is_half(self):
        d = _make_imported_dossier(
            slot_overrides={slot: SlotStatus.PARTIAL for slot in DossierSlotName}
        )
        report = compare_dossiers(d, d)
        assert report.completion_local == pytest.approx(0.5)

    def test_completion_is_weighted_by_slot_weights(self):
        """Filling only the highest-weight slot (IDENTITY=5.0) gives a specific result."""
        from adversary_pursuit.dossier.slots import SLOT_WEIGHTS

        d = _make_imported_dossier(slot_overrides={DossierSlotName.IDENTITY: SlotStatus.FILLED})
        report = compare_dossiers(d, d)
        total_weight = sum(SLOT_WEIGHTS.values())
        identity_weight = SLOT_WEIGHTS[DossierSlotName.IDENTITY]
        expected = (identity_weight * 1.0) / total_weight
        assert report.completion_local == pytest.approx(expected)

    def test_completion_bounds(self):
        """Completion is always in [0, 1]."""
        for status in [
            SlotStatus.FILLED,
            SlotStatus.PARTIAL,
            SlotStatus.EMPTY,
            SlotStatus.DEFERRED,
        ]:
            d = _make_imported_dossier(slot_overrides={slot: status for slot in DossierSlotName})
            report = compare_dossiers(d, d)
            assert 0.0 <= report.completion_local <= 1.0


# ---------------------------------------------------------------------------
# Prediction validation ratio (DEC-M9-PRED-RATIO-001)
# ---------------------------------------------------------------------------


class TestPredictionValidationRatio:
    """validated / total predictions; 0.0 for empty set."""

    def test_empty_predictions_ratio_is_zero(self):
        d = _make_imported_dossier(predictions=[])
        report = compare_dossiers(d, d)
        assert report.prediction_validation_ratio_local == pytest.approx(0.0)

    def test_all_pending_ratio_is_zero(self):
        preds = [_make_persisted_prediction("pending") for _ in range(3)]
        d = _make_imported_dossier(predictions=preds)
        report = compare_dossiers(d, d)
        assert report.prediction_validation_ratio_local == pytest.approx(0.0)

    def test_all_validated_ratio_is_one(self):
        preds = [_make_persisted_prediction("validated") for _ in range(3)]
        d = _make_imported_dossier(predictions=preds)
        report = compare_dossiers(d, d)
        assert report.prediction_validation_ratio_local == pytest.approx(1.0)

    def test_mixed_predictions_ratio_correct(self):
        """2 validated, 1 pending, 1 falsified -> ratio = 2/4 = 0.5."""
        preds = [
            _make_persisted_prediction("validated"),
            _make_persisted_prediction("validated"),
            _make_persisted_prediction("pending"),
            _make_persisted_prediction("falsified"),
        ]
        d = _make_imported_dossier(predictions=preds)
        report = compare_dossiers(d, d)
        assert report.prediction_validation_ratio_local == pytest.approx(0.5)

    def test_local_and_remote_ratios_independent(self):
        """Local and remote ratios computed independently."""
        local_preds = [_make_persisted_prediction("validated")]
        remote_preds = [
            _make_persisted_prediction("pending"),
            _make_persisted_prediction("pending"),
        ]
        local = _make_imported_dossier(predictions=local_preds)
        remote = _make_imported_dossier(predictions=remote_preds)
        report = compare_dossiers(local, remote)
        assert report.prediction_validation_ratio_local == pytest.approx(1.0)
        assert report.prediction_validation_ratio_remote == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Summary line F64 compliance
# ---------------------------------------------------------------------------


class TestSummaryLineF64:
    """summary_line is plain ASCII with no Rich markup."""

    RICH_MARKERS = ("[bold]", "[green]", "[red]", "[/bold]", "[dim]", "[cyan]", "[yellow]")

    def test_summary_line_is_string(self):
        d = _make_imported_dossier()
        report = compare_dossiers(d, d)
        assert isinstance(report.summary_line, str)

    def test_summary_line_no_rich_markup(self):
        d = _make_imported_dossier()
        report = compare_dossiers(d, d)
        for marker in self.RICH_MARKERS:
            assert marker not in report.summary_line, (
                f"Rich markup '{marker}' found in summary_line — F64 violation"
            )

    def test_summary_line_contains_actor_identifier(self):
        d = _make_imported_dossier(actor_identifier="fancy-bear")
        report = compare_dossiers(d, d)
        assert "fancy-bear" in report.summary_line

    def test_format_comparison_report_no_rich_markup(self):
        """format_comparison_report output is plain ASCII."""
        d = _make_imported_dossier()
        report = compare_dossiers(d, d)
        formatted = format_comparison_report(report)
        for marker in self.RICH_MARKERS:
            assert marker not in formatted, (
                f"Rich markup '{marker}' found in format_comparison_report output"
            )


# ---------------------------------------------------------------------------
# Determinism (same inputs -> same report)
# ---------------------------------------------------------------------------


class TestComparisonDeterminism:
    """compare_dossiers is deterministic for the same inputs."""

    def test_same_inputs_produce_same_report(self):
        local = _make_imported_dossier(slot_overrides={DossierSlotName.IDENTITY: SlotStatus.FILLED})
        remote = _make_imported_dossier(slot_overrides={DossierSlotName.TTPS: SlotStatus.PARTIAL})
        report1 = compare_dossiers(local, remote)
        report2 = compare_dossiers(local, remote)
        assert report1.completion_local == report2.completion_local
        assert report1.completion_remote == report2.completion_remote
        assert report1.summary_line == report2.summary_line
        assert list(report1.unique_to_local) == list(report2.unique_to_local)

    def test_pure_no_env_side_effects(self, monkeypatch):
        """compare_dossiers produces the same result regardless of env var state."""
        monkeypatch.setenv("AP_DOSSIER_PUBLISH", "on")
        d = _make_imported_dossier()
        report_with_env = compare_dossiers(d, d)

        monkeypatch.delenv("AP_DOSSIER_PUBLISH", raising=False)
        report_without_env = compare_dossiers(d, d)

        assert report_with_env.completion_local == report_without_env.completion_local


# ---------------------------------------------------------------------------
# ComparisonReport is a frozen dataclass
# ---------------------------------------------------------------------------


class TestComparisonReportImmutable:
    def test_report_is_frozen(self):
        d = _make_imported_dossier()
        report = compare_dossiers(d, d)
        with pytest.raises((AttributeError, TypeError)):
            report.completion_local = 0.99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# End-to-end: export -> import -> compare (compound integration test)
# ---------------------------------------------------------------------------


class TestExportImportCompareIntegration:
    """Full production sequence: real workspace -> export -> import -> compare."""

    def test_round_trip_self_compare_identical(self, tmp_path: Path):
        """export -> import -> self-compare yields all-equal slot_diff."""
        mgr = WorkspaceManager(workspace_dir=tmp_path)
        mgr.create("default")
        mgr.switch("default")
        mgr.store_stix_objects(
            [
                {"type": "ipv4-addr", "value": "1.2.3.4"},
                {"type": "domain-name", "value": "evil.ru"},
            ],
            module_name="test/module",
            target="1.2.3.4",
        )
        bundle_json = export_dossier(mgr, actor_identifier="apt-test")
        imported = import_dossier(bundle_json)
        report = compare_dossiers(imported, imported)

        assert report.completion_local == report.completion_remote
        for slot, (local_s, remote_s) in report.slot_diff.items():
            assert local_s == remote_s, f"Self-compare slot {slot} should be equal"

    def test_two_workspaces_with_different_predictions_differ(self, tmp_path: Path):
        """Two workspaces with different predictions produce different comparison reports.

        DossierState slots come from persisted scoring snapshots (not raw SCO storage).
        To produce a real observable difference between two exports, we use the
        predictions log — which is directly persisted by save_predictions_log and
        faithfully round-trips through export/import without a scoring snapshot.
        """
        from adversary_pursuit.dossier.predictions import (
            ExpectedEvidence,
            PersistedPrediction,
            save_predictions_log,
        )

        # Workspace A: one validated prediction
        tmp_a = tmp_path / "wm_a"
        tmp_a.mkdir()
        wm_a = WorkspaceManager(workspace_dir=tmp_a)
        wm_a.create("default")
        wm_a.switch("default")
        pred = PersistedPrediction(
            prediction_id="pred-int-001",
            text="Actor uses .ru infrastructure",
            slot="infrastructure",
            status="validated",
            expected_evidence=ExpectedEvidence(value_regex=r"\.ru$"),
            created_at="2024-01-01T00:00:00Z",
        )
        save_predictions_log(wm_a, [pred])

        # Workspace B: no predictions
        tmp_b = tmp_path / "wm_b"
        tmp_b.mkdir()
        wm_b = WorkspaceManager(workspace_dir=tmp_b)
        wm_b.create("default")
        wm_b.switch("default")

        bundle_a = export_dossier(wm_a, actor_identifier="actor-a")
        bundle_b = export_dossier(wm_b, actor_identifier="actor-a")

        imported_a = import_dossier(bundle_a)
        imported_b = import_dossier(bundle_b)

        # Workspace A has 1 validated prediction -> prediction_validation_ratio > 0
        # Workspace B has no predictions -> ratio == 0.0
        report = compare_dossiers(imported_a, imported_b)
        assert (
            report.prediction_validation_ratio_local != report.prediction_validation_ratio_remote
        ), "Expected prediction_validation_ratio to differ: A has 1 validated, B has none"
