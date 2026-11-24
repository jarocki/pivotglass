"""Keyless context sources (#46, #45): Mnemonic passive DNS, Shodan InternetDB,
SANS ISC, RDAP, Wayback CDX, and CIRCL hashlookup.

# @mock-exempt: each source is an external HTTP boundary. httpx.MockTransport
# replaces only the network; URL building, status semantics, and SCO shaping run
# for real. Response bodies mirror live answers captured 2026-11-21 for public,
# non-case values (8.8.8.8, example.com, an NSRL hash).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

from pivotglass.agent.model_control import ModelControl, execute_configuration_command
from pivotglass.agent.provider_setup import CTI_SERVICES, _validate_cti_key
from pivotglass.core.config import ConfigManager
from pivotglass.core.plugin_mgr import PluginManager
from pivotglass.core.service_endpoints import SERVICE_BASE_URLS, endpoint_init_config
from pivotglass.modules.base import ModuleError, PursuitModule, RateLimitError
from pivotglass.modules.cti.hashlookup import HashLookup
from pivotglass.modules.keyless_http import USER_AGENT
from pivotglass.modules.osint.mnemonic_pdns import MnemonicPassiveDNS
from pivotglass.modules.osint.rdap import Rdap
from pivotglass.modules.osint.sans_isc import SansIsc
from pivotglass.modules.osint.shodan_internetdb import ShodanInternetDB
from pivotglass.modules.osint.wayback import Wayback

KEYLESS = {
    "osint/mnemonic_pdns": "mnemonic_pdns",
    "osint/shodan_internetdb": "shodan_internetdb",
    "osint/sans_isc": "sans_isc",
    "osint/rdap": "rdap",
    "osint/wayback": "wayback",
    "cti/hashlookup": "hashlookup",
}


def _module(cls: type, handler: Callable[[httpx.Request], httpx.Response], config: dict | None = None):
    mod = cls()
    mod.initialize(config or {})
    mod.transport = httpx.MockTransport(handler)
    return mod


def _json(status: int, body: Any, **headers: str) -> Callable[[httpx.Request], httpx.Response]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, content=json.dumps(body).encode(), headers=headers)

    handler.seen = seen  # type: ignore[attr-defined]
    return handler


# ---------------------------------------------------------------------------
# Registration and configuration
# ---------------------------------------------------------------------------


def test_every_keyless_module_is_registered_with_a_service_base_url():
    manager = PluginManager()
    manager.load_plugins()
    for path, service_id in KEYLESS.items():
        mod = manager.get_module(path)
        assert isinstance(mod, PursuitModule), path
        assert mod.service_id == service_id
        assert mod.requires_api_key is False
        assert SERVICE_BASE_URLS[service_id].startswith("https://")
        assert mod.base_url == SERVICE_BASE_URLS[service_id]


def test_keyless_services_appear_in_configuration_without_credentials(tmp_path: Path):
    control = ModelControl(ConfigManager(config_dir=tmp_path))
    services = {item["id"]: item for item in control.configuration_summary()["services"]}
    for service_id in KEYLESS.values():
        entry = services[service_id]
        assert entry["credential_source"] == "not-required"
        assert entry["credential_fields"] == []
        assert entry["default_base_url"] == SERVICE_BASE_URLS[service_id]
        assert entry["enabled"] is True
    # Keyed services keep their credential state.
    assert services["virustotal"]["credential_source"] == "missing"


def test_keyless_specs_are_derived_from_the_one_service_list():
    keyless_specs = {spec.id for spec in CTI_SERVICES if not spec.needs_credential}
    assert keyless_specs == set(KEYLESS.values())


def test_base_url_override_reaches_the_request(tmp_path: Path):
    config = ConfigManager(config_dir=tmp_path)
    config.set_endpoint_override("shodan_internetdb", "https://gateway.example.test/internetdb")
    handler = _json(200, {"ip": "8.8.8.8", "ports": [53]})
    mod = _module(ShodanInternetDB, handler, endpoint_init_config(config, "shodan_internetdb"))

    import asyncio

    asyncio.run(mod.hunt("8.8.8.8", {}))
    assert str(handler.seen[0].url) == "https://gateway.example.test/internetdb/8.8.8.8"
    assert handler.seen[0].headers["User-Agent"] == USER_AGENT


def test_keyless_service_can_be_disabled_and_reenabled(tmp_path: Path):
    control = ModelControl(ConfigManager(config_dir=tmp_path))
    assert "disabled" in execute_configuration_command(("disable", "rdap"), control)
    assert control.config_mgr.is_service_enabled("rdap") is False
    execute_configuration_command(("enable", "rdap"), control)
    assert control.config_mgr.is_service_enabled("rdap") is True


@pytest.mark.parametrize("module_path,service_id", sorted(KEYLESS.items()))
def test_disabling_a_keyless_service_stops_its_module(tmp_path: Path, module_path: str, service_id: str):
    from pivotglass.core.module_config import ServiceDisabledError, resolve_module_credentials

    config = ConfigManager(config_dir=tmp_path)
    resolve_module_credentials(module_path, config)  # enabled by default: no error
    config.set_service_enabled(service_id, False)
    with pytest.raises(ServiceDisabledError):
        resolve_module_credentials(module_path, config)


def test_reachability_check_sends_no_credential(monkeypatch):
    spec = next(item for item in CTI_SERVICES if item.id == "sans_isc")
    captured: dict[str, Any] = {}

    def fake_get(url, headers, timeout, follow_redirects):
        captured.update(url=url, headers=headers)
        return httpx.Response(200, json={"ip": {}})

    monkeypatch.setattr("pivotglass.agent.provider_setup.httpx.get", fake_get)
    ok, message = _validate_cti_key(spec, [])
    assert ok and "no credential" in message.lower()
    assert captured["url"] == "https://isc.sans.edu/api/ip/8.8.8.8?json"
    assert captured["headers"] == {"User-Agent": USER_AGENT}


def test_user_agent_carries_no_contact_detail():
    assert USER_AGENT.startswith("pivotglass/")
    assert "@" not in USER_AGENT and "http" not in USER_AGENT


# ---------------------------------------------------------------------------
# Mnemonic passive DNS
# ---------------------------------------------------------------------------

_PDNS_DOMAIN = {
    "responseCode": 200, "limit": 100, "offset": 0, "count": 34, "metaData": {}, "messages": [],
    "data": [
        {"query": "example.com", "answer": "93.184.215.14", "rrtype": "a", "times": 11688,
         "maxTtl": 3600, "firstSeenTimestamp": 1713478195121, "lastSeenTimestamp": 1736884763267},
        {"query": "example.com", "answer": "2606:4700:10::6814:179a", "rrtype": "aaaa", "times": 1012,
         "maxTtl": 300, "firstSeenTimestamp": 0, "lastSeenTimestamp": 0, "flags": ["partialResult"]},
        {"query": "example.com", "answer": "a.iana-servers.net", "rrtype": "ns", "times": 5,
         "maxTtl": 86400, "firstSeenTimestamp": 1713478195121, "lastSeenTimestamp": 1713478195121},
    ],
    "size": 3,
}


async def test_mnemonic_domain_history_and_neighbours():
    handler = _json(200, _PDNS_DOMAIN)
    results = await _module(MnemonicPassiveDNS, handler).hunt("Example.com.", {"LIMIT": "5000"})

    request = handler.seen[0]
    assert request.url.path == "/pdns/v3/example.com"
    assert request.url.params["limit"] == "1000"  # clamped: >1000 returns HTTP 412
    primary = results[0]
    assert primary["type"] == "domain-name" and primary["value"] == "example.com"
    assert primary["x_mnemonic_pdns_total"] == 34
    assert primary["x_mnemonic_pdns_returned"] == 3
    assert primary["x_mnemonic_pdns_first_seen"] == "2024-04-18T22:09:55.121000Z"
    partial = primary["x_mnemonic_pdns_records"][1]
    assert partial["first_seen"] == "" and partial["last_seen"] == ""  # 0 is unknown, not 1970
    # A and AAAA answers become pivotable SCOs; the NS record does not.
    assert [(r["type"], r["value"]) for r in results[1:]] == [
        ("ipv4-addr", "93.184.215.14"),
        ("ipv6-addr", "2606:4700:10::6814:179a"),
    ]


async def test_mnemonic_ip_query_yields_names():
    body = {"count": 1, "data": [{"query": "example.org", "answer": "93.184.215.14", "rrtype": "a",
                                  "firstSeenTimestamp": 1713506665533, "lastSeenTimestamp": 1736910339299}]}
    results = await _module(MnemonicPassiveDNS, _json(200, body)).hunt("93.184.215.14", {})
    assert results[0]["type"] == "ipv4-addr"
    assert results[1] == {"type": "domain-name", "value": "example.org",
                          "x_mnemonic_pdns_resolution_of": "93.184.215.14"}


async def test_mnemonic_no_records_is_empty():
    body = {"responseCode": 200, "count": 0, "data": [], "size": 0,
            "messages": [{"messageTemplate": "object.not.found", "type": "INFO"}]}
    assert await _module(MnemonicPassiveDNS, _json(200, body)).hunt("no-such-name.example", {}) == []


async def test_mnemonic_quota_is_a_rate_limit_with_retry_after():
    body = {"responseCode": 402, "metaData": {"millisUntilResourcesAvailable": 41_500}}
    with pytest.raises(RateLimitError) as info:
        await _module(MnemonicPassiveDNS, _json(402, body)).hunt("example.com", {})
    assert info.value.retry_after == 42


async def test_mnemonic_rejects_unsupported_target():
    with pytest.raises(ModuleError, match="domain or IP"):
        await _module(MnemonicPassiveDNS, _json(200, {})).hunt("analyst@example.com", {})


# ---------------------------------------------------------------------------
# Shodan InternetDB
# ---------------------------------------------------------------------------


async def test_internetdb_record():
    body = {"cpes": ["cpe:/a:example:server"], "hostnames": ["dns.google", "not a host"],
            "ip": "8.8.8.8", "ports": [53, 443], "tags": ["pqc"], "vulns": ["CVE-2000-0001"]}
    results = await _module(ShodanInternetDB, _json(200, body)).hunt("8.8.8.8", {})
    primary = results[0]
    assert primary["x_internetdb_ports"] == [53, 443]
    assert primary["x_internetdb_tags"] == ["pqc"]
    assert primary["x_internetdb_vulns"] == ["CVE-2000-0001"]
    assert results[1:] == [{"type": "domain-name", "value": "dns.google", "x_internetdb_hostname_of": "8.8.8.8"}]


async def test_internetdb_404_is_no_data():
    handler = _json(404, {"detail": "No information available"})
    assert await _module(ShodanInternetDB, handler).hunt("192.0.2.1", {}) == []


async def test_internetdb_server_error_is_a_clear_module_error():
    with pytest.raises(ModuleError, match="HTTP 503"):
        await _module(ShodanInternetDB, _json(503, {})).hunt("8.8.8.8", {})


async def test_network_failure_degrades_to_a_named_module_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ModuleError, match="Shodan InternetDB is unreachable"):
        await _module(ShodanInternetDB, handler).hunt("8.8.8.8", {})


async def test_timeout_degrades_to_a_named_module_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ModuleError, match="did not answer"):
        await _module(Wayback, handler).hunt("example.com", {})


# ---------------------------------------------------------------------------
# SANS ISC
# ---------------------------------------------------------------------------

_ISC = {"ip": {"number": "8.8.8.8", "count": None, "attacks": None, "maxdate": None, "mindate": None,
               "updated": None, "comment": "Google public recursive name server", "maxrisk": 0,
               "asabusecontact": "network-abuse@google.com", "as": 15169, "asname": "GOOGLE",
               "ascountry": "US", "network": "8.8.8.0/24",
               "threatfeeds": {"openresolver": {"lastseen": "2026-11-21", "firstseen": "2022-02-04"}}}}


async def test_sans_isc_record_without_reports_is_explicit_and_drops_contacts():
    handler = _json(200, _ISC)
    [sco] = await _module(SansIsc, handler).hunt("8.8.8.8", {})
    assert handler.seen[0].url.path == "/api/ip/8.8.8.8"
    assert "json" in handler.seen[0].url.params
    assert handler.seen[0].headers["User-Agent"] == USER_AGENT
    assert sco["x_sans_isc_reports"] == 0 and sco["x_sans_isc_targets"] == 0
    assert sco["x_sans_isc_asn"] == 15169 and sco["x_sans_isc_network"] == "8.8.8.0/24"
    assert sco["x_sans_isc_feeds"] == [{"feed": "openresolver", "first_seen": "2022-02-04", "last_seen": "2026-11-21"}]
    assert "network-abuse@google.com" not in json.dumps(sco)


async def test_sans_isc_error_body_is_a_module_error():
    with pytest.raises(ModuleError, match="bad IP address"):
        await _module(SansIsc, _json(200, {"error": "bad IP address"})).hunt("8.8.8.8", {})


async def test_sans_isc_429_is_rate_limit():
    with pytest.raises(RateLimitError) as info:
        await _module(SansIsc, _json(429, {}, **{"Retry-After": "30"})).hunt("8.8.8.8", {})
    assert info.value.retry_after == 30


async def test_sans_isc_rejects_ipv6():
    with pytest.raises(ModuleError, match="IPv4"):
        await _module(SansIsc, _json(200, _ISC)).hunt("2001:db8::1", {})


# ---------------------------------------------------------------------------
# RDAP
# ---------------------------------------------------------------------------

_RDAP_DOMAIN = {
    "objectClassName": "domain", "handle": "2336799_DOMAIN_COM-VRSN", "ldhName": "EXAMPLE.COM",
    "status": ["client delete prohibited"],
    "events": [{"eventAction": "registration", "eventDate": "1995-08-14T04:00:00Z"},
               {"eventAction": "expiration", "eventDate": "2027-08-13T04:00:00Z"},
               {"eventAction": "last changed", "eventDate": "2026-08-14T07:01:39Z"}],
    "nameservers": [{"ldhName": "A.IANA-SERVERS.NET"}, {"ldhName": "B.IANA-SERVERS.NET"}],
    "entities": [{
        "roles": ["registrar"], "publicIds": [{"type": "IANA Registrar ID", "identifier": "376"}],
        "vcardArray": ["vcard", [["version", {}, "text", "4.0"],
                                 ["fn", {}, "text", "RESERVED-Internet Assigned Numbers Authority"]]],
        "entities": [{"roles": ["abuse"], "vcardArray": ["vcard", [
            ["fn", {}, "text", "Jane Analyst"], ["email", {}, "text", "jane@example.net"],
            ["tel", {}, "uri", "tel:+1.5555550100"]]]}],
    }],
}


@pytest.mark.parametrize("location", [
    "http://rdap.verisign.com/com/v1/domain/example.com",  # downgrade
    "https://127.0.0.1/domain/example.com",
    "https://169.254.169.254/latest/meta-data",
    "https://10.0.0.5/domain/example.com",
    "https://localhost/domain/example.com",
    "https://localhost./domain/example.com",
    "https://2130706433/domain/example.com",  # 127.0.0.1 as a bare integer
    "https://0x7f.1/domain/example.com",
    "https://[::ffff:7f00:1]/domain/example.com",  # IPv4-mapped loopback
    "https://192.0.2.10/domain/example.com",  # an IP literal, even if a registry listed one
    "https://attacker.example/domain/example.com",  # public, but not an IANA-listed RDAP server
])
async def test_rdap_refuses_redirects_to_local_or_plain_http_targets(location):
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"Location": location})

    with pytest.raises(ModuleError, match="refused"):
        await _module(Rdap, handler).hunt("example.com", {})
    assert len(requested) == 1  # the unsafe hop is never requested


@pytest.fixture(autouse=True)
def _registry_allowlist(monkeypatch):
    """IANA's bootstrap registry, without the network (includes an IP literal to prove it is still refused)."""
    from pivotglass.modules.osint import rdap

    async def registries():
        return frozenset({"rdap.verisign.com", "rdap.arin.net", "rdap.example-registry.net", "192.0.2.10"})

    monkeypatch.setattr(rdap, "_registry_hosts", registries)


async def test_rdap_stops_after_bounded_redirects():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://rdap.example-registry.net/next"})

    with pytest.raises(ModuleError, match="too many times"):
        await _module(Rdap, handler).hunt("example.com", {})


async def test_rdap_domain_follows_bootstrap_redirect_and_records_registration():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "rdap.org":
            return httpx.Response(302, headers={"Location": "https://rdap.verisign.com/com/v1/domain/example.com"})
        return httpx.Response(200, json=_RDAP_DOMAIN)

    results = await _module(Rdap, handler).hunt("example.com", {})
    primary = results[0]
    assert primary["x_rdap_server"] == "https://rdap.verisign.com"
    assert primary["x_rdap_registrar"] == "RESERVED-Internet Assigned Numbers Authority"
    assert primary["x_rdap_registrar_iana_id"] == "376"
    assert primary["x_rdap_registered"] == "1995-08-14T04:00:00Z"
    assert primary["x_rdap_expires"] == "2027-08-13T04:00:00Z"
    assert primary["x_rdap_nameservers"] == ["a.iana-servers.net", "b.iana-servers.net"]
    assert [r["value"] for r in results[1:]] == ["a.iana-servers.net", "b.iana-servers.net"]
    # An individual's name, e-mail, and phone never enter evidence.
    blob = json.dumps(results)
    assert "Jane" not in blob and "jane@" not in blob and "5555550100" not in blob
    assert primary["x_rdap_abuse_organisation"] == ""


async def test_rdap_ip_network():
    body = {"objectClassName": "ip network", "handle": "NET-8-8-8-0-2", "name": "GOGL",
            "startAddress": "8.8.8.0", "endAddress": "8.8.8.255", "country": "US",
            "cidr0_cidrs": [{"v4prefix": "8.8.8.0", "length": 24}],
            "events": [{"eventAction": "registration", "eventDate": "2014-03-14T15:52:05-04:00"}],
            "entities": [{"roles": ["registrant"], "vcardArray": ["vcard", [
                ["kind", {}, "text", "org"], ["fn", {}, "text", "Google LLC"]]],
                "entities": [{"roles": ["abuse"], "vcardArray": ["vcard", [
                    ["kind", {}, "text", "group"], ["fn", {}, "text", "Abuse"],
                    ["email", {}, "text", "network-abuse@google.com"]]]}]}]}
    handler = _json(200, body)
    [sco] = await _module(Rdap, handler).hunt("8.8.8.8", {})
    assert handler.seen[0].url.path == "/ip/8.8.8.8"
    assert sco["x_rdap_network_name"] == "GOGL"
    assert sco["x_rdap_cidrs"] == ["8.8.8.0/24"]
    assert sco["x_rdap_range"] == "8.8.8.0 - 8.8.8.255"
    assert sco["x_rdap_registrant_organisation"] == "Google LLC"
    assert sco["x_rdap_abuse_organisation"] == "Abuse"
    assert "network-abuse@google.com" not in json.dumps(sco)


async def test_rdap_404_is_no_data():
    body = {"errorCode": 404, "title": "No RDAP service is available for this resource"}
    assert await _module(Rdap, _json(404, body)).hunt("10.0.0.1", {}) == []


# ---------------------------------------------------------------------------
# Wayback CDX
# ---------------------------------------------------------------------------


async def test_wayback_first_last_and_months():
    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        assert params["url"] == "example.com" and params["output"] == "json"
        if params.get("limit") == "-1":
            return httpx.Response(200, json=[["timestamp", "original", "statuscode"],
                                             ["20261122010310", "https://example.com/", "200"]])
        assert params["collapse"] == "timestamp:6"
        return httpx.Response(200, json=[["timestamp", "original", "statuscode"],
                                         ["20020120142510", "http://example.com:80/", "200"],
                                         ["20261101000441", "https://example.com/", "200"]])

    [sco] = await _module(Wayback, handler).hunt("Example.com", {})
    assert sco["type"] == "domain-name"
    assert sco["x_wayback_first_capture"] == "2002-01-20T14:25:10Z"
    assert sco["x_wayback_last_capture"] == "2026-11-22T01:03:10Z"
    assert sco["x_wayback_capture_months"] == 2
    assert sco["x_wayback_capture_months_truncated"] is False
    assert sco["x_wayback_first_capture_url"] == "https://web.archive.org/web/20020120142510/http://example.com:80/"


async def test_wayback_empty_archive_is_no_data():
    assert await _module(Wayback, _json(200, [])).hunt("no-such-name.example", {}) == []


async def test_wayback_url_target():
    rows = [["timestamp", "original", "statuscode"], ["20200101000000", "https://example.com/a", "200"]]
    [sco] = await _module(Wayback, _json(200, rows)).hunt("https://example.com/a", {})
    assert sco["type"] == "url" and sco["value"] == "https://example.com/a"


# ---------------------------------------------------------------------------
# CIRCL hashlookup (output contract consumed by the known-good authority)
# ---------------------------------------------------------------------------

_NSRL = {"CRC32": "7A5407CA", "FileName": "timezones.resources.manifest", "FileSize": "2520",
         "MD5": "8ED4B4ED952526D89899E723F3488DE4",
         "ProductCode": {"ProductName": "Cumulative Update for Windows Server 2016 for x64 (KB4338817)"},
         "SHA-1": "00000079FD7AAC9B2F9C988C50750E1F50B27EB5", "db": "nsrl_modern_rds",
         "source": "NSRL", "hashlookup:trust": 50}


async def test_hashlookup_known_file_contract():
    handler = _json(200, _NSRL)
    [sco] = await _module(HashLookup, handler).hunt("8ed4b4ed952526d89899e723f3488de4", {})
    assert handler.seen[0].url.path == "/lookup/md5/8ed4b4ed952526d89899e723f3488de4"
    assert sco["type"] == "file"
    assert sco["hashes"] == {"MD5": "8ed4b4ed952526d89899e723f3488de4",
                             "SHA-1": "00000079fd7aac9b2f9c988c50750e1f50b27eb5"}
    assert sco["name"] == "timezones.resources.manifest"
    assert sco["x_hashlookup_known"] is True
    assert sco["x_hashlookup_sources"] == ["NSRL", "nsrl_modern_rds"]
    assert sco["x_hashlookup_product"].startswith("Cumulative Update")
    assert sco["x_hashlookup_known_malicious"] == []
    assert sco["x_hashlookup_trust"] == 50


async def test_hashlookup_package_and_known_malicious():
    body = {"SHA-256": "A" * 64, "FileName": "./usr/bin/ls", "source": "debian",
            "parents": [{"PackageName": "coreutils"}], "KnownMalicious": "example-feed"}
    [sco] = await _module(HashLookup, _json(200, body)).hunt("a" * 64, {})
    assert sco["hashes"] == {"SHA-256": "a" * 64}
    assert sco["x_hashlookup_product"] == "coreutils"
    assert sco["x_hashlookup_known_malicious"] == ["example-feed"]


async def test_hashlookup_404_is_not_in_any_set():
    body = {"message": "Non existing MD5", "query": "0" * 32}
    assert await _module(HashLookup, _json(404, body)).hunt("0" * 32, {}) == []


async def test_hashlookup_400_is_a_module_error():
    with pytest.raises(ModuleError, match="malformed"):
        await _module(HashLookup, _json(400, {"message": "bad"})).hunt("0" * 40, {})


# ---------------------------------------------------------------------------
# Persisted provenance: the known-good authority trusts x_hashlookup_* only on
# objects whose x_pivotglass_source_module is "cti/hashlookup". The workspace
# stamps that field at storage time and strips caller-supplied x_pivotglass_*
# keys (DEC-59-STIX-PROVENANCE-001), so neither a module nor an import can forge it.
# ---------------------------------------------------------------------------


def _tool_context(tmp_path: Path):
    from pivotglass.agent.tools import ToolContext

    (tmp_path / "config").mkdir()
    (tmp_path / "workspaces").mkdir()
    ctx = ToolContext(config_dir=tmp_path / "config", workspace_dir=tmp_path / "workspaces")
    ctx.workspace_mgr.create("default")
    ctx.workspace_mgr.switch("default")
    return ctx


def _stored_files(ctx) -> list[dict]:
    return [obj for obj in ctx.workspace_mgr.get_stix_objects() if obj.get("type") == "file"]


def test_persisted_hashlookup_result_is_stamped_with_its_module(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(HashLookup, "transport", httpx.MockTransport(_json(200, _NSRL)))
    ctx = _tool_context(tmp_path)

    result = ctx.run_module("cti/hashlookup", "8ed4b4ed952526d89899e723f3488de4", {})

    assert "error" not in result
    [stored] = _stored_files(ctx)
    assert stored["x_pivotglass_source_module"] == "cti/hashlookup"
    assert stored["x_indicator_value"] == "8ed4b4ed952526d89899e723f3488de4"
    assert stored["hashes"] == {"MD5": "8ed4b4ed952526d89899e723f3488de4",
                                "SHA-1": "00000079fd7aac9b2f9c988c50750e1f50b27eb5"}
    assert stored["name"] == "timezones.resources.manifest"
    assert stored["x_hashlookup_known"] is True
    assert stored["x_hashlookup_sources"] == ["NSRL", "nsrl_modern_rds"]


def test_file_objects_with_several_hashes_persist(tmp_path: Path):
    """create_file merges a module's ``hashes`` instead of colliding with them.

    Before this fix any file SCO carrying ``hashes`` (MalwareBazaar's shape too)
    raised TypeError at storage time.
    """
    ctx = _tool_context(tmp_path)
    sha256 = "b" * 64
    ctx.workspace_mgr.store_stix_objects(
        [{"type": "file", "hashes": {"MD5": "c" * 32, "SHA-256": sha256}, "x_mb_signature": "Example"}],
        "cti/malwarebazaar",
        sha256,
    )
    [stored] = _stored_files(ctx)
    assert stored["hashes"] == {"MD5": "c" * 32, "SHA-256": sha256}
    assert stored["x_indicator_value"] == sha256


def test_caller_cannot_forge_hashlookup_provenance(tmp_path: Path):
    ctx = _tool_context(tmp_path)
    forged = {"type": "file", "hashes": {"MD5": "0" * 32}, "x_hashlookup_known": True,
              "x_pivotglass_source_module": "cti/hashlookup"}

    ctx.workspace_mgr.store_stix_objects([forged], "import/stix-bundle", "bundle.json")

    [stored] = _stored_files(ctx)
    assert stored["x_pivotglass_source_module"] == "import/stix-bundle"


def test_keyless_requests_keep_tls_verification_on():
    """DEC-RDAP-REDIRECT-001 relies on certificate checks to stop a rebound registry name."""
    source = Path(__file__).parents[1].joinpath("src/pivotglass/modules/keyless_http.py").read_text()
    assert "verify=" not in source
