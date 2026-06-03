"""Tests for dossier/predictions.py — M-4 Predictions Log lifecycle and validation.

Evaluation Contract gates (test_dossier_predictions.py ~14 tests):
  P1  load returns empty list on fresh workspace
  P2  save then load round-trips
  P3  second save replaces first (sentinel uniqueness for _predictions_log)
  P4  validate_predictions: empty list => empty results
  P5  validate_predictions: sco_type-only match => confirmed
  P6  validate_predictions: value_regex-only match => confirmed
  P7  validate_predictions: asn_in match against ipv4-addr SCO => confirmed
  P8  validate_predictions: note_keyword_any match against note text => confirmed
  P9  validate_predictions: mixed sco_type + value_regex (both match) => confirmed
  P10 validate_predictions: mixed sco_type + value_regex (only one matches) => not confirmed
  P11 validate_predictions: no SCOs in new_scos => no confirmations
  P12 validate_predictions: already-validated prediction skipped (idempotent)
  P13 validate_predictions: already-falsified prediction skipped (defensive guard)
  P14 create_prediction with empty expected_evidence raises ValueError

@decision DEC-M4-PRED-001
@title PersistedPrediction is the M-4 richer shape; M-2 PredictionRecord stays UNCHANGED
@status accepted

@decision DEC-M4-PRED-002
@title expected_evidence vocabulary v1.0: ANDed fields; empty evidence rejected
@status accepted

@decision DEC-M4-PRED-003
@title Validation scope = current-hunt evidence only
@status accepted
"""

from __future__ import annotations

import pytest

from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.dossier.predictions import (
    PREDICTIONS_LOG_SENTINEL_ACTION,
    ExpectedEvidence,
    PersistedPrediction,
    ValidationResult,
    create_prediction,
    load_predictions_log,
    mark_confirmed,
    save_predictions_log,
    validate_predictions,
)

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _make_workspace(tmp_path) -> WorkspaceManager:
    wm = WorkspaceManager(workspace_dir=tmp_path)
    wm.create("default")
    wm.switch("default")
    return wm


def _pred(
    pid: str = "pred-00000001",
    status: str = "pending",
    sco_type: str | None = None,
    value_regex: str | None = None,
    asn_in: list[int] | None = None,
    note_keyword_any: list[str] | None = None,
    text: str = "Actor pivots to .ru infrastructure.",
    slot: str = "infrastructure",
) -> PersistedPrediction:
    return PersistedPrediction(
        prediction_id=pid,
        text=text,
        slot=slot,
        status=status,
        expected_evidence=ExpectedEvidence(
            sco_type=sco_type,
            value_regex=value_regex,
            asn_in=asn_in,
            note_keyword_any=note_keyword_any,
        ),
        created_at="2026-06-01T00:00:00+00:00",
    )


def _domain_sco(value: str, stix_id: str | None = None) -> dict:
    return {"type": "domain-name", "value": value, "id": stix_id or f"domain-name--{value}"}


def _ip_sco(value: str, asn: int | None = None, stix_id: str | None = None) -> dict:
    sco: dict = {"type": "ipv4-addr", "value": value, "id": stix_id or f"ipv4-addr--{value}"}
    if asn is not None:
        sco["x_autonomous_system"] = {"asn": asn, "name": f"AS{asn}"}
    return sco


def _note(content: str) -> dict:
    return {"content": content}


# ---------------------------------------------------------------------------
# P1: load returns empty list on fresh workspace
# ---------------------------------------------------------------------------


class TestLoadFreshWorkspace:
    def test_load_returns_empty_list_on_fresh_workspace(self, tmp_path):
        """P1: fresh workspace has no sentinel row — load returns []."""
        wm = _make_workspace(tmp_path)
        result = load_predictions_log(wm)
        assert result == []


# ---------------------------------------------------------------------------
# P2: save then load round-trips
# ---------------------------------------------------------------------------


class TestSaveLoadRoundTrip:
    def test_save_then_load_round_trips(self, tmp_path):
        """P2: predictions saved via save_predictions_log are faithfully restored."""
        wm = _make_workspace(tmp_path)
        preds = [
            _pred(pid="pred-00000001", status="pending", value_regex=r".*\.ru$"),
            _pred(pid="pred-00000002", status="validated", sco_type="domain-name"),
        ]
        save_predictions_log(wm, preds)
        loaded = load_predictions_log(wm)
        assert len(loaded) == 2
        assert loaded[0].prediction_id == "pred-00000001"
        assert loaded[0].status == "pending"
        assert loaded[0].expected_evidence.value_regex == r".*\.ru$"
        assert loaded[1].prediction_id == "pred-00000002"
        assert loaded[1].status == "validated"
        assert loaded[1].expected_evidence.sco_type == "domain-name"

    def test_all_expected_evidence_fields_round_trip(self, tmp_path):
        """All ExpectedEvidence fields survive serialization."""
        wm = _make_workspace(tmp_path)
        preds = [
            _pred(
                pid="pred-00000001",
                sco_type="ipv4-addr",
                value_regex=r"^10\.",
                asn_in=[12345, 67890],
                note_keyword_any=["pivoted", "ransomware"],
            )
        ]
        save_predictions_log(wm, preds)
        loaded = load_predictions_log(wm)
        assert len(loaded) == 1
        ee = loaded[0].expected_evidence
        assert ee.sco_type == "ipv4-addr"
        assert ee.value_regex == r"^10\."
        assert ee.asn_in == [12345, 67890]
        assert ee.note_keyword_any == ["pivoted", "ransomware"]


# ---------------------------------------------------------------------------
# P3: sentinel uniqueness
# ---------------------------------------------------------------------------


class TestSentinelUniqueness:
    def test_second_save_replaces_first(self, tmp_path):
        """P3: multiple saves leave exactly one _predictions_log row."""
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from adversary_pursuit.models.database import ScoreEvent

        wm = _make_workspace(tmp_path)
        for i in range(4):
            save_predictions_log(wm, [_pred(pid=f"pred-{i:08x}")])

        with Session(wm._engine) as session:
            rows = (
                session.execute(
                    select(ScoreEvent).where(ScoreEvent.action == PREDICTIONS_LOG_SENTINEL_ACTION)
                )
                .scalars()
                .all()
            )
        assert len(rows) == 1

    def test_sentinel_excluded_from_recent_scores(self, tmp_path):
        """_predictions_log sentinel row excluded from get_recent_scores()."""
        wm = _make_workspace(tmp_path)
        wm.store_score_events([{"action": "new_ip", "points": 5, "indicator": "1.1.1.1"}])
        save_predictions_log(wm, [_pred()])
        recent = wm.get_recent_scores(limit=50)
        actions = {e["action"] for e in recent}
        assert PREDICTIONS_LOG_SENTINEL_ACTION not in actions
        assert "new_ip" in actions

    def test_sentinel_row_has_zero_points(self, tmp_path):
        """Sentinel row points=0 so it never affects get_total_score()."""
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from adversary_pursuit.models.database import ScoreEvent

        wm = _make_workspace(tmp_path)
        save_predictions_log(wm, [_pred()])
        with Session(wm._engine) as session:
            row = session.execute(
                select(ScoreEvent).where(ScoreEvent.action == PREDICTIONS_LOG_SENTINEL_ACTION)
            ).scalar_one()
        assert row.points == 0


# ---------------------------------------------------------------------------
# P4: empty predictions list
# ---------------------------------------------------------------------------


class TestValidateEmpty:
    def test_validate_empty_list_returns_empty_results(self):
        """P4: validate_predictions([]) returns []."""
        results = validate_predictions([], [], [])
        assert results == []


# ---------------------------------------------------------------------------
# P5: sco_type-only match
# ---------------------------------------------------------------------------


class TestScoTypeMatch:
    def test_sco_type_only_match_confirmed(self):
        """P5: sco_type match against a domain-name SCO => confirmed."""
        pred = _pred(sco_type="domain-name")
        scos = [_domain_sco("evil.ru", stix_id="domain-name--evil.ru")]
        results = validate_predictions([pred], scos, [])
        assert len(results) == 1
        assert results[0].confirmed is True
        assert results[0].matched_sco_id == "domain-name--evil.ru"

    def test_sco_type_mismatch_not_confirmed(self):
        """sco_type filter rejects SCO of wrong type."""
        pred = _pred(sco_type="domain-name")
        scos = [_ip_sco("1.2.3.4", stix_id="ipv4-addr--1.2.3.4")]
        results = validate_predictions([pred], scos, [])
        assert results[0].confirmed is False


# ---------------------------------------------------------------------------
# P6: value_regex-only match
# ---------------------------------------------------------------------------


class TestValueRegexMatch:
    def test_value_regex_only_match_confirmed(self):
        """P6: value_regex match against .ru domain => confirmed."""
        pred = _pred(value_regex=r".*\.ru$")
        scos = [_domain_sco("actor.ru", stix_id="domain-name--actor.ru")]
        results = validate_predictions([pred], scos, [])
        assert results[0].confirmed is True

    def test_value_regex_no_match_not_confirmed(self):
        """value_regex that doesn't match => not confirmed."""
        pred = _pred(value_regex=r".*\.ru$")
        scos = [_domain_sco("actor.com", stix_id="domain-name--actor.com")]
        results = validate_predictions([pred], scos, [])
        assert results[0].confirmed is False

    def test_value_regex_matches_first_sco_that_satisfies(self):
        """validate_predictions finds the first matching SCO."""
        pred = _pred(value_regex=r".*\.ru$")
        scos = [
            _domain_sco("benign.com", stix_id="domain-name--benign.com"),
            _domain_sco("evil.ru", stix_id="domain-name--evil.ru"),
        ]
        results = validate_predictions([pred], scos, [])
        assert results[0].confirmed is True
        assert results[0].matched_sco_id == "domain-name--evil.ru"


# ---------------------------------------------------------------------------
# P7: asn_in match
# ---------------------------------------------------------------------------


class TestAsnInMatch:
    def test_asn_in_match_against_ipv4_sco_confirmed(self):
        """P7: asn_in match against ipv4-addr with matching ASN => confirmed."""
        pred = _pred(asn_in=[12345, 67890])
        scos = [_ip_sco("1.2.3.4", asn=12345, stix_id="ipv4-addr--1.2.3.4")]
        results = validate_predictions([pred], scos, [])
        assert results[0].confirmed is True

    def test_asn_in_no_match_not_confirmed(self):
        """ASN not in the list => not confirmed."""
        pred = _pred(asn_in=[12345])
        scos = [_ip_sco("1.2.3.4", asn=99999, stix_id="ipv4-addr--1.2.3.4")]
        results = validate_predictions([pred], scos, [])
        assert results[0].confirmed is False

    def test_asn_in_sco_with_no_asn_not_confirmed(self):
        """SCO with no x_autonomous_system field => no ASN => not confirmed."""
        pred = _pred(asn_in=[12345])
        scos = [{"type": "ipv4-addr", "value": "1.2.3.4", "id": "ipv4-addr--1.2.3.4"}]
        results = validate_predictions([pred], scos, [])
        assert results[0].confirmed is False


# ---------------------------------------------------------------------------
# P8: note_keyword_any match
# ---------------------------------------------------------------------------


class TestNoteKeywordAnyMatch:
    def test_note_keyword_any_match_against_note_text_confirmed(self):
        """P8: note_keyword_any match against analyst note content => confirmed."""
        pred = _pred(note_keyword_any=["pivoted", "ransomware"])
        notes = [_note("We pivoted from the domain to this IP.")]
        results = validate_predictions([pred], [], notes)
        assert results[0].confirmed is True
        assert results[0].matched_sco_id is None

    def test_note_keyword_any_no_match_not_confirmed(self):
        """No note contains any keyword => not confirmed."""
        pred = _pred(note_keyword_any=["ransomware", "cobalt"])
        notes = [_note("Benign infrastructure, no threat indicators found.")]
        results = validate_predictions([pred], [], notes)
        assert results[0].confirmed is False

    def test_note_keyword_any_only_one_keyword_needed(self):
        """Only one of the keywords needs to appear (OR semantics)."""
        pred = _pred(note_keyword_any=["keywordA", "keywordB"])
        notes = [_note("This note contains keywordB but not the other.")]
        results = validate_predictions([pred], [], notes)
        assert results[0].confirmed is True


# ---------------------------------------------------------------------------
# P9: combined sco_type + value_regex (both match)
# ---------------------------------------------------------------------------


class TestCombinedMatch:
    def test_combined_sco_type_and_value_regex_both_match_confirmed(self):
        """P9: sco_type + value_regex both satisfied => confirmed."""
        pred = _pred(sco_type="domain-name", value_regex=r".*\.ru$")
        scos = [_domain_sco("actor.ru", stix_id="domain-name--actor.ru")]
        results = validate_predictions([pred], scos, [])
        assert results[0].confirmed is True

    def test_combined_sco_type_and_value_regex_only_type_matches_not_confirmed(self):
        """P10: sco_type matches but value_regex fails => not confirmed."""
        pred = _pred(sco_type="domain-name", value_regex=r".*\.ru$")
        scos = [_domain_sco("actor.com", stix_id="domain-name--actor.com")]
        results = validate_predictions([pred], scos, [])
        assert results[0].confirmed is False

    def test_combined_value_regex_matches_but_sco_type_fails_not_confirmed(self):
        """sco_type fails even though value would match => not confirmed."""
        pred = _pred(sco_type="domain-name", value_regex=r".*\.ru$")
        # ipv4 SCO won't match sco_type="domain-name"
        scos = [{"type": "ipv4-addr", "value": "1.ru", "id": "ipv4-addr--1.ru"}]
        results = validate_predictions([pred], scos, [])
        assert results[0].confirmed is False


# ---------------------------------------------------------------------------
# P11: no SCOs in new_scos
# ---------------------------------------------------------------------------


class TestNoScos:
    def test_no_scos_in_new_scos_no_confirmations(self):
        """P11: empty new_scos => no prediction with sco criteria confirmed."""
        pred = _pred(sco_type="domain-name")
        results = validate_predictions([pred], [], [])
        assert results[0].confirmed is False

    def test_multiple_pending_predictions_no_scos_all_unconfirmed(self):
        """Multiple predictions, no evidence => all unconfirmed."""
        preds = [
            _pred(pid="pred-00000001", sco_type="domain-name"),
            _pred(pid="pred-00000002", value_regex=r".*\.ru$"),
        ]
        results = validate_predictions(preds, [], [])
        assert all(not r.confirmed for r in results)


# ---------------------------------------------------------------------------
# P12/P13: idempotency — skip already-validated/falsified
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_already_validated_prediction_skipped(self):
        """P12: already-validated prediction is skipped (not re-confirmed)."""
        pred = _pred(sco_type="domain-name", status="validated")
        scos = [_domain_sco("evil.com")]
        results = validate_predictions([pred], scos, [])
        assert results[0].confirmed is False
        assert "skipped" in results[0].rationale

    def test_already_falsified_prediction_skipped(self):
        """P13: already-falsified prediction is defensively skipped."""
        pred = _pred(sco_type="domain-name", status="falsified")
        scos = [_domain_sco("evil.com")]
        results = validate_predictions([pred], scos, [])
        assert results[0].confirmed is False
        assert "skipped" in results[0].rationale

    def test_mix_of_pending_and_validated(self):
        """Only pending predictions are evaluated; validated are skipped."""
        preds = [
            _pred(pid="pred-00000001", sco_type="domain-name", status="pending"),
            _pred(pid="pred-00000002", sco_type="domain-name", status="validated"),
        ]
        scos = [_domain_sco("evil.com")]
        results = validate_predictions(preds, scos, [])
        assert results[0].confirmed is True
        assert results[1].confirmed is False
        assert "skipped" in results[1].rationale


# ---------------------------------------------------------------------------
# P14: empty expected_evidence raises ValueError
# ---------------------------------------------------------------------------


class TestCreatePredictionValidation:
    def test_empty_expected_evidence_raises_value_error(self):
        """P14: create_prediction with all-None expected_evidence raises ValueError."""
        with pytest.raises(ValueError, match="at least one"):
            create_prediction(
                slot="infrastructure",
                text="Actor will pivot.",
                expected_evidence_dict={},
            )

    def test_invalid_slot_raises_value_error(self):
        """create_prediction with invalid slot name raises ValueError."""
        with pytest.raises(ValueError, match="Invalid slot"):
            create_prediction(
                slot="INVALID_SLOT",
                text="Actor will pivot.",
                expected_evidence_dict={"sco_type": "domain-name"},
            )

    def test_valid_creation_returns_persisted_prediction(self):
        """create_prediction with valid args returns a PersistedPrediction."""
        pred = create_prediction(
            slot="infrastructure",
            text="Actor pivots to .ru",
            expected_evidence_dict={"value_regex": r".*\.ru$"},
        )
        assert isinstance(pred, PersistedPrediction)
        assert pred.status == "pending"
        assert pred.slot == "infrastructure"
        assert pred.expected_evidence.value_regex == r".*\.ru$"
        assert pred.prediction_id.startswith("pred-")

    def test_schema_version_mismatch_raises_runtime_error(self):
        """Deserialization of schema_version != 1 raises RuntimeError."""
        import json

        from adversary_pursuit.dossier.predictions import _deserialize_predictions

        bad = json.dumps({"schema_version": 99, "predictions": []})
        with pytest.raises(RuntimeError, match="schema version 99"):
            _deserialize_predictions(bad)


# ---------------------------------------------------------------------------
# mark_confirmed helper
# ---------------------------------------------------------------------------


class TestMarkConfirmed:
    def test_mark_confirmed_flips_confirmed_predictions_to_validated(self):
        """mark_confirmed flips confirmed=True predictions to status='validated'."""
        preds = [
            _pred(pid="pred-00000001", status="pending"),
            _pred(pid="pred-00000002", status="pending"),
        ]
        results = [
            ValidationResult(
                prediction_id="pred-00000001",
                confirmed=True,
                matched_sco_id="sco-1",
                rationale="matched",
            ),
            ValidationResult(
                prediction_id="pred-00000002",
                confirmed=False,
                matched_sco_id=None,
                rationale="no match",
            ),
        ]
        updated = mark_confirmed(preds, results)
        assert updated[0].status == "validated"
        assert updated[0].validated_by_sco_id == "sco-1"
        assert updated[0].validated_at is not None
        assert updated[1].status == "pending"

    def test_mark_confirmed_does_not_mutate_originals(self):
        """mark_confirmed produces a new list; originals unchanged."""
        preds = [_pred(pid="pred-00000001", status="pending")]
        results = [
            ValidationResult(
                prediction_id="pred-00000001",
                confirmed=True,
                matched_sco_id="sco-1",
                rationale="ok",
            ),
        ]
        updated = mark_confirmed(preds, results)
        assert preds[0].status == "pending"  # original unchanged
        assert updated[0].status == "validated"
