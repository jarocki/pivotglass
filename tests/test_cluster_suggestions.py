"""Cluster suggestions from shared pivot values (#30, DEC-CLUSTER-SUGGEST-001)."""

from __future__ import annotations

import pytest

from pivotglass.core.cluster_suggestions import execute_cluster_command, suggest_clusters
from pivotglass.core.indicator_tags import IndicatorTagAuthority
from pivotglass.core.workspace import WorkspaceManager


@pytest.fixture()
def wm(tmp_path) -> WorkspaceManager:
    manager = WorkspaceManager(workspace_dir=tmp_path / "ws")
    manager.create("case")
    manager.switch("case")
    ns = ["ns1.parked.example", "ns2.parked.example"]
    manager.store_stix_objects(
        [
            {"type": "domain-name", "value": "a.example.net", "x_rdap_nameservers": ns,
             "x_rdap_registrar": "Example Registrar", "x_rdap_registered": "2026-10-01T00:00:00Z"},
            {"type": "domain-name", "value": "b.example.net", "x_dns_records": {"NS": [f"{n}." for n in reversed(ns)]},
             "x_rdap_registrar": "Example Registrar", "x_rdap_registered": "2026-10-09T00:00:00Z"},
            {"type": "domain-name", "value": "c.example.org", "x_rdap_nameservers": ["ns1.other.example"],
             "x_rdap_registrar": "Example Registrar", "x_rdap_registered": "2026-12-30T00:00:00Z"},
            {"type": "ipv4-addr", "value": "192.0.2.10", "x_asn_number": 64500, "jarm": "29d29d00029d29d00042d43d00041d"},
            {"type": "ipv4-addr", "value": "192.0.2.11", "x_autonomous_system": {"asn": 64500}, "jarm": "29d29d00029d29d00042d43d00041d"},
            {"type": "ipv4-addr", "value": "192.0.2.12", "x_asn_number": 64501, "jarm": "29d29d00029d29d00042d43d00041d"},
        ],
        module_name="test/fixture",
        target="a.example.net",
    )
    return manager


def _by_rule(wm):
    return {s["rule"]: s for s in suggest_clusters(wm)}


def test_shared_values_produce_labelled_suggestions_strongest_first(wm):
    suggestions = suggest_clusters(wm)
    assert [s["rule"] for s in suggestions] == ["asn-jarm", "nameservers", "registrar-window"]
    rules = _by_rule(wm)
    assert [m["value"] for m in rules["asn-jarm"]["members"]] == ["192.0.2.10", "192.0.2.11"]  # AS64501 differs
    assert [m["value"] for m in rules["nameservers"]["members"]] == ["a.example.net", "b.example.net"]
    window = rules["registrar-window"]
    assert [m["value"] for m in window["members"]] == ["a.example.net", "b.example.net"]  # c is outside 14 days
    assert window["strength"] == "weak" and "not a finding" in window["basis"]


def test_accept_tags_members_with_the_shared_values_as_evidence_and_stops_suggesting(wm):
    sid = _by_rule(wm)["nameservers"]["id"]
    result = execute_cluster_command(f"accept {sid} Parked NS kit!", wm)
    assert result["data"]["cluster"] == "parked ns kit"
    tags = [t for t in IndicatorTagAuthority(wm).current() if t["dimension"] == "cluster"]
    assert {t["normalized_value"] for t in tags} == {"a.example.net", "b.example.net"}
    assert all("ns1.parked.example" in (t.get("note") or "") for t in tags)
    assert "nameservers" not in _by_rule(wm)
    # The registrar suggestion has the same members, who now share a cluster: also not offered.
    assert "registrar-window" not in _by_rule(wm)


def test_reject_needs_a_reason_and_is_remembered(wm):
    sid = _by_rule(wm)["asn-jarm"]["id"]
    with pytest.raises(ValueError, match="say why"):
        execute_cluster_command(f"reject {sid}", wm)
    execute_cluster_command(f"reject {sid} | Shared CDN edge, not one operator", wm)
    assert "asn-jarm" not in _by_rule(wm)
    with pytest.raises(ValueError, match="no open cluster suggestion"):
        execute_cluster_command(f"accept {sid}", wm)


def test_benign_members_are_left_out(wm):
    IndicatorTagAuthority(wm).apply(
        [{"entity_type": "ipv4-addr", "normalized_value": "192.0.2.11", "dimension": "role", "value": "benign"}],
        operator="local analyst",
    )
    assert "asn-jarm" not in _by_rule(wm)


def test_usage(wm):
    with pytest.raises(ValueError, match="usage"):
        execute_cluster_command("merge everything", wm)


def test_pivot_values_reported_later_by_another_module_are_used(wm):
    """An existing object keeps its first fields; a later module's ASN arrives as an observation."""
    wm.store_stix_objects([{"type": "ipv4-addr", "value": "198.51.100.7"}, {"type": "ipv4-addr", "value": "198.51.100.8"}],
                          module_name="test/first", target="x")
    jarm = "3fd3fd0003fd3fd0003fd3fd3fd3fd"
    wm.store_stix_objects([{"type": "ipv4-addr", "value": v, "x_asn_number": 64510, "jarm": jarm} for v in ("198.51.100.7", "198.51.100.8")],
                          module_name="osint/ip_asn", target="y")
    pairs = [s for s in suggest_clusters(wm) if s["rule"] == "asn-jarm" and "AS64510" in s["shared"]]
    assert [m["value"] for m in pairs[0]["members"]] == ["198.51.100.7", "198.51.100.8"]
