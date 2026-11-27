"""Keyless infrastructure pivots (#21): DNS over HTTPS, IP to ASN, and their graph edges.

# @mock-exempt: DNS-over-HTTPS is an external HTTP boundary; httpx.MockTransport
# replaces only the network. The DB-IP database is a licensed local file that is
# not shipped in tests, so a small reader double stands in for the memory-mapped
# maxminddb reader (the same approach as tests/test_geolocation.py); path,
# prefix, and SCO shaping run for real.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from pivotglass.core.event_bus import DEFAULT_SUBSCRIPTIONS
from pivotglass.core.geolocation import ATTRIBUTION, GeoDatabase
from pivotglass.core.graph import RelationshipGraph
from pivotglass.core.plugin_mgr import PluginManager
from pivotglass.modules.base import ModuleError
from pivotglass.modules.osint import ip_asn
from pivotglass.modules.osint.dns_doh import ACCEPT, DnsOverHttps
from pivotglass.modules.osint.ip_asn import INSTALL_HINT, IpAsn

TYPE_NUMBERS = {"A": 1, "AAAA": 28, "NS": 2, "MX": 15, "TXT": 16, "CNAME": 5}


def _doh(answers: dict[str, list[str]], status: dict[str, int] | None = None, seen: list | None = None):
    """MockTransport answering each RRtype from *answers* (rrtype -> data strings)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        rrtype = request.url.params["type"]
        body: dict[str, Any] = {"Status": (status or {}).get(rrtype, 0)}
        if answers.get(rrtype):
            body["Answer"] = [
                {"name": request.url.params["name"], "type": TYPE_NUMBERS[rrtype], "TTL": 300, "data": data}
                for data in answers[rrtype]
            ]
        return httpx.Response(200, content=json.dumps(body).encode())

    return httpx.MockTransport(handler)


def _run(transport: httpx.AsyncBaseTransport, target: str = "example.com", config: dict | None = None):
    module = DnsOverHttps()
    module.initialize(config or {})
    module.transport = transport
    return asyncio.run(module.hunt(target, {}))


def test_all_rrtypes_become_properties_and_neighbours():
    seen: list[httpx.Request] = []
    results = _run(
        _doh(
            {
                "A": ["93.184.216.34", "93.184.216.34"],
                "AAAA": ["2606:2800:21f:cb07:6820:80da:af6b:8b2c"],
                "NS": ["a.iana-servers.net.", "B.iana-servers.net."],
                "MX": ["10 mail.example.com.", "0 ."],
                "TXT": ['"v=spf1 -all"', '"include:evil.test 1.2.3.4"'],
                "CNAME": ["Target.example.net."],
            },
            seen=seen,
        )
    )
    primary = results[0]
    assert primary["type"] == "domain-name" and primary["value"] == "example.com"
    assert primary["x_dns_status"] == "NOERROR"
    assert primary["x_dns_resolver"] == "Cloudflare DNS-over-HTTPS (live)"
    assert primary["x_dns_records"] == {
        "A": ["93.184.216.34"],
        "AAAA": ["2606:2800:21f:cb07:6820:80da:af6b:8b2c"],
        "NS": ["a.iana-servers.net", "b.iana-servers.net"],
        "MX": ["10 mail.example.com", "0 ."],
        "TXT": ["v=spf1 -all", "include:evil.test 1.2.3.4"],
        "CNAME": ["target.example.net"],
    }
    neighbours = {(r["type"], r["value"]): [k for k in r if k.startswith("x_dns_")] for r in results[1:]}
    assert neighbours == {
        ("ipv4-addr", "93.184.216.34"): ["x_dns_resolution_of"],
        ("ipv6-addr", "2606:2800:21f:cb07:6820:80da:af6b:8b2c"): ["x_dns_resolution_of"],
        ("domain-name", "a.iana-servers.net"): ["x_dns_nameserver_of"],
        ("domain-name", "b.iana-servers.net"): ["x_dns_nameserver_of"],
        ("domain-name", "mail.example.com"): ["x_dns_mail_exchanger_of"],
        ("domain-name", "target.example.net"): ["x_dns_alias_of"],
    }
    assert all(r[next(k for k in r if k.startswith("x_dns_"))] == "example.com" for r in results[1:])
    # TXT is never parsed into indicators: neither the IP nor the domain inside it is emitted.
    assert ("ipv4-addr", "1.2.3.4") not in neighbours and ("domain-name", "evil.test") not in neighbours
    assert sorted(r.url.params["type"] for r in seen) == sorted(TYPE_NUMBERS)
    assert all(r.headers["Accept"] == ACCEPT for r in seen)
    assert all(str(r.url).startswith("https://cloudflare-dns.com/dns-query?") for r in seen)


def test_nxdomain_is_a_recorded_empty_answer_not_an_error():
    results = _run(_doh({}, status={rr: 3 for rr in TYPE_NUMBERS}), "no-such-name.example.com")
    assert len(results) == 1
    assert results[0]["x_dns_status"] == "NXDOMAIN" and results[0]["x_dns_records"] == {}


def test_servfail_is_recorded_as_status():
    results = _run(_doh({"A": ["93.184.216.34"]}, status={"NS": 2}))
    assert results[0]["x_dns_status"] == "SERVFAIL"
    assert results[0]["x_dns_records"] == {"A": ["93.184.216.34"]}


def test_base_url_override_reaches_the_request():
    seen: list[httpx.Request] = []
    _run(_doh({}, seen=seen), config={"base_url": "https://gateway.example.test/doh"})
    assert str(seen[0].url).startswith("https://gateway.example.test/doh/dns-query?")


def test_neighbour_counts_are_bounded_and_invalid_answers_dropped():
    many = [f"10.0.{i // 250}.{i % 250 + 1}" for i in range(100)]
    results = _run(_doh({"A": many + ["not-an-ip"], "NS": [f"ns{i}.example.net" for i in range(100)]}))
    assert len(results[0]["x_dns_records"]["A"]) == 25
    assert len(results[0]["x_dns_records"]["NS"]) == 25
    assert len(results) == 1 + 25 + 25


def test_self_reference_and_garbage_names_are_not_emitted():
    results = _run(_doh({"NS": ["example.com.", "not a domain", "ns.example.net"], "MX": ["bad", "x y"]}))
    assert [r["value"] for r in results[1:]] == ["ns.example.net"]


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[]", b'{"Answer": []}', b'{"Status": "0"}', b'{"Status": 0, "Answer": "x"}'],
)
def test_malformed_responses_raise_and_record_nothing(body: bytes):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=body))
    with pytest.raises(ModuleError):
        _run(transport)


def test_http_error_and_unreachable_raise():
    with pytest.raises(ModuleError, match="HTTP 503"):
        _run(httpx.MockTransport(lambda request: httpx.Response(503)))

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(ModuleError, match="unreachable"):
        _run(httpx.MockTransport(boom))


@pytest.mark.parametrize("value", ["8.8.8.8", "not a domain", ""])
def test_non_domain_targets_are_refused(value: str):
    with pytest.raises(ModuleError, match="accepts a domain"):
        _run(_doh({}), value)


# ---------------------------------------------------------------------------
# IP to ASN
# ---------------------------------------------------------------------------


class _Reader:
    def __init__(self, table: dict[str, tuple[dict | None, int]]):
        self.table = table

    def get_with_prefix_len(self, ip: str):
        return self.table.get(ip, (None, 0))


def _asn_module(tmp_path, monkeypatch, table, installed=True) -> IpAsn:
    db = GeoDatabase(tmp_path / "geo")
    if installed:
        db.directory.mkdir()
        db.path("asn").write_bytes(b"asn")
        db.path("city").write_bytes(b"city")
        (db.directory / "edition.json").write_text('{"edition": "2026-11"}')
    monkeypatch.setattr(ip_asn, "_reader", lambda path, mtime: _Reader(table))
    module = IpAsn()
    module.database = db
    return module


def test_ip_asn_maps_ip_to_asn_prefix_and_attribution(tmp_path, monkeypatch):
    module = _asn_module(
        tmp_path, monkeypatch,
        {"8.8.8.8": ({"autonomous_system_number": 15169, "autonomous_system_organization": "GOOGLE"}, 24)},
    )
    ip_sco, as_sco = asyncio.run(module.hunt(" 8.8.8.8 ", {}))
    assert ip_sco == {
        "type": "ipv4-addr", "value": "8.8.8.8", "x_asn_number": 15169, "x_asn_name": "GOOGLE",
        "x_asn_prefix": "8.8.8.0/24", "x_asn_source": "DB-IP Lite 2026-11 (local)",
        "x_asn_attribution": ATTRIBUTION,
    }
    assert as_sco["type"] == "autonomous-system" and as_sco["number"] == 15169
    assert as_sco["name"] == "GOOGLE" and as_sco["x_asn_of"] == "8.8.8.8"
    assert as_sco["x_asn_attribution"] == ATTRIBUTION


def test_ip_asn_ipv6_prefix(tmp_path, monkeypatch):
    module = _asn_module(
        tmp_path, monkeypatch,
        {"2001:4860:4860::8888": ({"autonomous_system_number": 15169}, 32)},
    )
    ip_sco = asyncio.run(module.hunt("2001:4860:4860::8888", {}))[0]
    assert ip_sco["type"] == "ipv6-addr" and ip_sco["x_asn_prefix"] == "2001:4860::/32"


@pytest.mark.parametrize("value", ["10.0.0.1", "127.0.0.1", "192.168.1.9", "fe80::1"])
def test_ip_asn_non_global_is_empty(tmp_path, monkeypatch, value):
    assert asyncio.run(_asn_module(tmp_path, monkeypatch, {}).hunt(value, {})) == []


def test_ip_asn_unknown_address_is_empty(tmp_path, monkeypatch):
    assert asyncio.run(_asn_module(tmp_path, monkeypatch, {}).hunt("8.8.4.4", {})) == []


def test_ip_asn_missing_database_says_how_to_install(tmp_path, monkeypatch):
    module = _asn_module(tmp_path, monkeypatch, {}, installed=False)
    with pytest.raises(ModuleError) as caught:
        asyncio.run(module.hunt("8.8.8.8", {}))
    assert str(caught.value) == INSTALL_HINT and "Geolocation data" in INSTALL_HINT


def test_ip_asn_rejects_non_ip(tmp_path, monkeypatch):
    with pytest.raises(ModuleError, match="accepts an IP"):
        asyncio.run(_asn_module(tmp_path, monkeypatch, {}).hunt("example.com", {}))


# ---------------------------------------------------------------------------
# Registration, auto-pivot wiring, and graph edges
# ---------------------------------------------------------------------------


def test_modules_are_registered_and_subscribed():
    manager = PluginManager()
    manager.load_plugins()
    assert isinstance(manager.get_module("osint/dns_doh"), DnsOverHttps)
    assert isinstance(manager.get_module("osint/ip_asn"), IpAsn)
    assert DEFAULT_SUBSCRIPTIONS["osint/dns_doh"] == ["domain-name"]
    assert DEFAULT_SUBSCRIPTIONS["osint/ip_asn"] == ["ipv4-addr", "ipv6-addr"]


def test_neighbour_fields_become_labelled_property_edges():
    objects = [
        {"id": "domain-name--t", "type": "domain-name", "value": "example.com"},
        {"id": "domain-name--ns", "type": "domain-name", "value": "ns.example.net",
         "x_rdap_nameserver_of": "example.com"},
        {"id": "domain-name--ns2", "type": "domain-name", "value": "ns2.example.net",
         "x_dns_nameserver_of": "example.com"},
        {"id": "domain-name--mx", "type": "domain-name", "value": "mail.example.com",
         "x_dns_mail_exchanger_of": "example.com"},
        {"id": "domain-name--cn", "type": "domain-name", "value": "alias.example.net",
         "x_dns_alias_of": "example.com"},
        {"id": "ipv4-addr--a", "type": "ipv4-addr", "value": "93.184.216.34",
         "x_dns_resolution_of": "example.com"},
        {"id": "ipv4-addr--p", "type": "ipv4-addr", "value": "93.184.216.35",
         "x_mnemonic_pdns_resolution_of": "example.com"},
        {"id": "autonomous-system--15133", "type": "autonomous-system", "number": 15133,
         "name": "EDGECAST", "x_asn_of": "93.184.216.34"},
    ]
    graph = RelationshipGraph()
    graph.build_from_workspace(objects)
    edges = {(e["source"], e["target"], e["relationship"]) for e in graph.to_dict()["edges"]}
    assert edges == {
        ("domain-name--ns", "domain-name--t", "nameserver-of"),
        ("domain-name--ns2", "domain-name--t", "nameserver-of"),
        ("domain-name--mx", "domain-name--t", "mail-exchanger-of"),
        ("domain-name--cn", "domain-name--t", "alias-of"),
        ("ipv4-addr--a", "domain-name--t", "resolution-of"),
        ("ipv4-addr--p", "domain-name--t", "resolution-of"),
        ("autonomous-system--15133", "ipv4-addr--a", "announces"),
    }


def test_registrar_is_not_a_shared_property_edge():
    objects = [
        {"id": "domain-name--a", "type": "domain-name", "value": "a.test", "x_rdap_registrar": "Example Registrar"},
        {"id": "domain-name--b", "type": "domain-name", "value": "b.test", "x_rdap_registrar": "Example Registrar"},
    ]
    graph = RelationshipGraph()
    graph.build_from_workspace(objects)
    assert graph.to_dict()["edges"] == []
