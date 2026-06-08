"""Tests for dossier/predictions.py serialization — schema versioning.

Covers DEC-M5-FALSIFY-008 (v1->v2 schema bump + backward compat) and
DEC-M4-PERSIST-003 pattern (loud failure on unknown schema version).

@decision DEC-M5-FALSIFY-008
@title _predictions_log envelope schema_version bumps 1->2; v1 still reads cleanly
@status accepted
@rationale v1 envelopes deserialize with falsification_evidence=None,
    created_at_hunt_count=0. Serializer always emits v2. v3+ raises RuntimeError
    (loud-failure pattern preserved from DEC-M4-PERSIST-003, bumped one version).

Tests in this file (~4 required per Evaluation Contract §7):
  S1  v1 envelope deserializes with falsification_evidence=None, created_at_hunt_count=0
  S2  v2 envelope round-trips with falsification_evidence + created_at_hunt_count populated
  S3  schema_version=3 raises RuntimeError (loud-failure pattern)
  S4  Serializer always emits v2 even when falsification_evidence is None
"""

from __future__ import annotations

import json

import pytest

from adversary_pursuit.dossier.predictions import (
    ExpectedEvidence,
    FalsificationEvidence,
    PersistedPrediction,
    _deserialize_predictions,
    _serialize_predictions,
)


def _make_pred(
    pid: str = "pred-ser-001",
    fe: FalsificationEvidence | None = None,
    created_at_hunt_count: int = 0,
) -> PersistedPrediction:
    return PersistedPrediction(
        prediction_id=pid,
        text="Actor will pivot to .ru infrastructure.",
        slot="infrastructure",
        status="pending",
        expected_evidence=ExpectedEvidence(sco_type="domain-name"),
        created_at="2026-06-01T00:00:00+00:00",
        falsification_evidence=fe,
        created_at_hunt_count=created_at_hunt_count,
    )


class TestSchemaVersionBackwardCompat:
    """S1: v1 envelope still deserializes cleanly in M-5 runtime."""

    def test_v1_envelope_deserializes_with_m5_defaults(self):
        """A v1 envelope (no falsification_evidence, no created_at_hunt_count) deserializes
        with falsification_evidence=None and created_at_hunt_count=0.
        """
        v1_payload = json.dumps(
            {
                "schema_version": 1,
                "predictions": [
                    {
                        "prediction_id": "pred-v1-001",
                        "text": "Actor pivots to .ru.",
                        "slot": "infrastructure",
                        "status": "pending",
                        "expected_evidence": {
                            "sco_type": "domain-name",
                            "value_regex": None,
                            "asn_in": None,
                            "note_keyword_any": None,
                        },
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "validated_at": None,
                        "validated_by_sco_id": None,
                        # No falsification_evidence key — v1 schema
                        # No created_at_hunt_count key — v1 schema
                    }
                ],
            }
        )
        predictions = _deserialize_predictions(v1_payload)
        assert len(predictions) == 1
        pred = predictions[0]
        # M-5 fields default correctly for v1 entries
        assert pred.falsification_evidence is None
        assert pred.created_at_hunt_count == 0
        assert pred.prediction_id == "pred-v1-001"
        assert pred.status == "pending"


class TestSchemaVersionV2RoundTrip:
    """S2: v2 envelope round-trips with falsification_evidence + created_at_hunt_count."""

    def test_v2_roundtrip_with_falsification_evidence(self):
        """PersistedPrediction with FalsificationEvidence serializes to v2 and round-trips."""
        fe = FalsificationEvidence(
            negative_value_regex=r".*\.cn$",
            contradiction_keyword_any=["china", ".cn"],
        )
        pred = _make_pred("pred-v2-001", fe=fe, created_at_hunt_count=3)
        payload = _serialize_predictions([pred])

        # Verify envelope is v2
        envelope = json.loads(payload)
        assert envelope["schema_version"] == 2

        # Deserialize and check round-trip fidelity
        restored = _deserialize_predictions(payload)
        assert len(restored) == 1
        r = restored[0]
        assert r.prediction_id == "pred-v2-001"
        assert r.created_at_hunt_count == 3
        assert r.falsification_evidence is not None
        assert r.falsification_evidence.negative_value_regex == r".*\.cn$"
        assert r.falsification_evidence.contradiction_keyword_any == ["china", ".cn"]

    def test_v2_roundtrip_with_stale_rule_only(self):
        """stale_after_n_hunts-only FalsificationEvidence round-trips in v2."""
        fe = FalsificationEvidence(stale_after_n_hunts=5)
        pred = _make_pred("pred-v2-002", fe=fe, created_at_hunt_count=7)
        restored = _deserialize_predictions(_serialize_predictions([pred]))
        r = restored[0]
        assert r.falsification_evidence is not None
        assert r.falsification_evidence.stale_after_n_hunts == 5
        assert r.created_at_hunt_count == 7


class TestSchemaVersionLoudFailure:
    """S3: schema_version=3+ raises RuntimeError (DEC-M4-PERSIST-003 / DEC-M5-FALSIFY-008)."""

    def test_v3_raises_runtime_error(self):
        """Unknown schema version 3 raises RuntimeError with version info."""
        payload = json.dumps(
            {
                "schema_version": 3,
                "predictions": [],
            }
        )
        with pytest.raises(RuntimeError, match="3"):
            _deserialize_predictions(payload)

    def test_v0_raises_runtime_error(self):
        """schema_version=0 (never valid) also raises RuntimeError."""
        payload = json.dumps({"schema_version": 0, "predictions": []})
        with pytest.raises(RuntimeError):
            _deserialize_predictions(payload)


class TestSerializerAlwaysEmitsV2:
    """S4: Serializer always emits v2 regardless of whether falsification_evidence is None."""

    def test_serializer_emits_v2_when_no_falsification_evidence(self):
        """Even a prediction without FalsificationEvidence serializes with schema_version=2."""
        pred = _make_pred("pred-v2-only", fe=None, created_at_hunt_count=0)
        payload = _serialize_predictions([pred])
        envelope = json.loads(payload)
        assert envelope["schema_version"] == 2, (
            f"Serializer must always emit v2; got schema_version={envelope['schema_version']}"
        )

    def test_serializer_emits_v2_for_empty_list(self):
        """Serializing an empty predictions list still emits schema_version=2."""
        payload = _serialize_predictions([])
        envelope = json.loads(payload)
        assert envelope["schema_version"] == 2
