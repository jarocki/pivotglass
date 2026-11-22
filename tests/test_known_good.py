"""Known-good recognition (DEC-KNOWN-GOOD-001): context from curated lists, never a verdict."""

from __future__ import annotations

import pytest

from pivotglass.core.known_good import (
    SELECTED_LISTS,
    bundle_status,
    known_matches,
    object_matches,
    summarize,
)


def _first(entity_type, value):
    matches = known_matches(entity_type, value)
    return matches[0] if matches else None


def test_bundle_carries_every_selected_list_with_its_upstream_commit():
    status = bundle_status()
    assert status["present"] and len(status["commit"]) == 40
    assert set(status["lists"]) == set(SELECTED_LISTS)
    assert all(item["entries"] > 0 and item["version"] for item in status["lists"].values())


@pytest.mark.parametrize(
    ("entity_type", "value", "category", "label"),
    [
        ("ipv4-addr", "8.8.8.8", "benign", "Public DNS resolver"),
        ("ipv4-addr", "1.1.1.1", "benign", "Public DNS resolver"),
        ("ipv4-addr", "162.142.125.10", "scanner", "Censys scanner"),
        ("domain-name", "google.com", "benign", "Tranco top-10k site"),
        ("domain-name", "www.wikipedia.org", "benign", "Tranco top-10k site"),
        ("file", "d41d8cd98f00b204e9800998ecf8427e", "benign", "Hash of an empty file"),
        ("file-hash-sha256", "E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855", "benign",
         "Hash of an empty file"),
    ],
)
def test_known_good_and_scanner_matches_may_be_set_aside(entity_type, value, category, label):
    match = _first(entity_type, value)
    assert match is not None
    assert (match.category, match.label) == (category, label)
    assert match.set_aside is True
    assert match.source.startswith("MISP warninglist ")


def test_shared_infrastructure_is_context_and_never_offered_for_set_aside():
    aws = _first("ipv4-addr", "3.5.140.2")
    assert aws is not None and aws.category == "shared" and aws.set_aside is False
    # Attackers abuse subdomains and URLs of popular hosting: not known good.
    subdomain = _first("domain-name", "evil-update.blogspot.com")
    assert subdomain is not None and subdomain.category == "shared"
    assert subdomain.label == "Subdomain of popular site blogspot.com"
    assert all(m.category == "shared" for m in known_matches("url", "https://bit.ly/3xYz"))
    assert summarize(known_matches("domain-name", "x.duckdns.org"))["set_aside"] is False
    # A parent-domain match on any benign host list is shared, never set aside.
    crl_child = known_matches("domain-name", "attacker.ocsp.digicert.com")
    assert crl_child and all(m.category == "shared" and not m.set_aside for m in crl_child)


def test_unknown_and_private_values_have_no_matches():
    assert known_matches("ipv4-addr", "154.86.17.52") == []
    assert known_matches("domain-name", "unlikely-pivotglass-test.example") == []
    assert known_matches("ipv4-addr", "not-an-ip") == []
    assert summarize([]) is None


def test_hashlookup_evidence_marks_a_known_file_unless_a_source_reports_it_malicious():
    known_file = {
        "type": "file",
        "hashes": {"SHA-256": "a" * 64},
        "x_hashlookup_known": True,
        "x_hashlookup_sources": ["NSRL"],
        "x_hashlookup_product": "Windows 11",
        "x_pivotglass_source_module": "cti/hashlookup",
    }
    match = object_matches(known_file)[0]
    assert (match.category, match.label, match.source) == ("benign", "Known file: Windows 11 (NSRL)", "cti/hashlookup")
    assert summarize([match])["set_aside"] is True

    # Imported objects cannot claim hashlookup knowledge.
    assert object_matches({**known_file, "x_pivotglass_source_module": "import/stix"}) == []
    assert object_matches({k: v for k, v in known_file.items() if k != "x_pivotglass_source_module"}) == []

    contested = object_matches({**known_file, "x_hashlookup_known_malicious": ["vx-underground"]})
    assert contested[0].category == "contested"
    assert summarize(contested)["set_aside"] is False


def test_views_label_known_indicators():
    from pivotglass.core import visualization

    graph = {"nodes": [{"id": "ipv4-addr--a", "type": "ipv4-addr", "value": "8.8.8.8"},
                       {"id": "ipv4-addr--b", "type": "ipv4-addr", "value": "154.86.17.52"}], "edges": []}
    nodes = {n.reference: n for n in visualization.relationship_graph_intent("test", graph).data.nodes}
    assert (nodes["ipv4-addr--a"].known_category, nodes["ipv4-addr--a"].known_label) == ("benign", "Public DNS resolver")
    assert nodes["ipv4-addr--b"].known_category == ""

    objects = [{"id": "ipv4-addr--a", "type": "ipv4-addr", "value": "8.8.8.8"}]
    rows = visualization.indicator_constellation_intent("test", objects, graph).data.rows
    assert rows[0]["known"] == "Public DNS resolver"
    assert rows[0]["known_source"].startswith("MISP warninglist public-dns-v4 v")
