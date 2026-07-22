"""Tests for deterministic evidence references and safe detail projection."""

import pytest

from adversary_pursuit.core.evidence_detail import evidence_ref, list_evidence, project_evidence


def _object() -> dict:
    return {
        "id": "domain-name--f5b40ef5-66af-4f96-8fe3-b1e45a69b92b",
        "type": "domain-name",
        "value": "suspect.test",
        "x_ap_fetched_at": "2026-07-21T10:00:00+00:00",
        "x_ap_source_url": "https://service.test/domain/suspect.test",
        "attributes": {"api_token": "do-not-render", "score": 7},
    }


def test_reference_is_stable_and_compact():
    obj = _object()

    assert evidence_ref(obj["id"]) == evidence_ref(obj["id"])
    assert evidence_ref(obj["id"]).startswith("ev-")
    assert len(evidence_ref(obj["id"])) == 11


def test_projection_marks_missing_provenance_and_scrubs_credentials():
    obj = _object()

    detail = project_evidence([obj], evidence_ref(obj["id"]))

    assert detail["source_module"] == "unavailable"
    assert detail["provenance"]["api_version"] == "unavailable"
    assert detail["raw"]["attributes"]["api_token"] == "[REDACTED]"
    assert detail["normalized"]["attributes"]["score"] == 7


def test_list_projection_does_not_expose_raw_fields():
    cards = list_evidence([_object()])

    assert cards[0]["value"] == "suspect.test"
    assert "attributes" not in cards[0]


def test_unknown_reference_fails_without_fabricating_link():
    with pytest.raises(ValueError, match="unknown evidence"):
        project_evidence([_object()], "ev-missing")
