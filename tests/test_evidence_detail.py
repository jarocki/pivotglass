"""Tests for deterministic evidence references and safe detail projection."""

import pytest

from adversary_pursuit.core.evidence_detail import evidence_ref, list_evidence, project_evidence
from adversary_pursuit.models.stix import dict_to_stix


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


def test_relationship_projection_exposes_safe_related_reference():
    source = _object()
    target = {
        "id": "ipv4-addr--33809c0f-4388-4c60-a5dd-3f96f881a01a",
        "type": "ipv4-addr",
        "value": "192.0.2.8",
    }
    relation = {
        "source_ref": source["id"],
        "target_ref": target["id"],
        "relationship_type": "resolves-to",
    }

    detail = project_evidence([source, target], evidence_ref(source["id"]), [relation])

    assert detail["relationships"] == [
        {
            "direction": "outgoing",
            "relationship": "resolves-to",
            "indicator": "192.0.2.8",
            "reference": evidence_ref(target["id"]),
        }
    ]


def test_list_projection_only_marks_source_backed_geo_and_malware():
    obj = {
        **_object(),
        "country_code": "JP",
        "latitude": 35.68,
        "longitude": 139.76,
        "x_ap_known_malware": True,
    }

    card = list_evidence([obj])[0]

    assert card["country"] == "JP"
    assert card["latitude"] == 35.68
    assert card["longitude"] == 139.76
    assert card["known_malware"] is True


def test_file_conversion_retains_analyst_facing_hash():
    value = "a" * 64
    file_sco = dict_to_stix({"type": "file", "value": value, "x_magic": "PE32"})
    serialized = file_sco.serialize()

    assert file_sco.x_indicator_value == value
    assert value in serialized


def test_vendor_summary_surfaces_urlscan_links_before_raw_record():
    obj = {
        **_object(),
        "type": "url",
        "value": "https://suspect.test/",
        "x_ap_source_module": "osint/urlscan",
        "x_scan_uuid": "scan-1",
        "x_result_url": "https://urlscan.io/result/scan-1/",
        "x_screenshot_url": "https://urlscan.io/screenshots/scan-1.png",
        "x_page_title": "Observed title",
    }

    detail = project_evidence([obj], evidence_ref(obj["id"]))

    assert detail["source_intelligence"]["provider"] == "urlscan.io"
    labels = {link["label"] for link in detail["source_intelligence"]["links"]}
    assert labels == {"Open urlscan result", "Open screenshot"}
