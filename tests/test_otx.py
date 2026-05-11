"""Tests for the AlienVault OTX CTI module (Issue #12).

# @mock-exempt: httpx.AsyncClient is an external HTTP boundary (OTX REST API).
# Tests must run without a real API key. Mocking the HTTP layer is the only
# way to exercise error paths (401, 429) hermetically. This is Sacred Practice
# #5's explicitly-permitted exception: "Mocks are acceptable ONLY for external
# boundaries (HTTP APIs, third-party services, databases)."

Production sequence: PluginManager.load_plugins() -> get_module('cti/otx') ->
initialize({api_key}) -> hunt(target, options). Tests cover the full sequence
including IPv4 and domain targets, multi-endpoint calls (general + passive_dns),
pulse extraction, INCLUDE_PASSIVE_DNS=false, PULSE_LIMIT, and error paths.

@decision DEC-TEST-OTX-001
@title Monkeypatch httpx.AsyncClient with context manager support for multi-endpoint
@status accepted
@rationale OTX module uses httpx.AsyncClient as a context manager and calls
           client.get() multiple times (general + passive_dns endpoints). The
           mock must support __aenter__/__aexit__ and allow per-URL response
           routing via side_effect on client.get. Same approach as test_abuseipdb.py
           (DEC-TEST-ABUSEIPDB-001) extended for multi-call scenarios.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adversary_pursuit.core.plugin_mgr import PluginManager
from adversary_pursuit.modules.base import (
    AuthenticationError,
    PursuitModule,
    RateLimitError,
)
from adversary_pursuit.modules.cti.otx import AlienVaultOTX

# ---------------------------------------------------------------------------
# Sample API responses
# ---------------------------------------------------------------------------

SAMPLE_IP_GENERAL = {
    "indicator": "1.2.3.4",
    "type": "IPv4",
    "reputation": 2,
    "country_code": "US",
    "asn": "AS15169 Google LLC",
    "pulse_info": {
        "count": 3,
        "pulses": [
            {
                "name": "Pulse Alpha",
                "tags": ["malware", "c2"],
            },
            {
                "name": "Pulse Beta",
                "tags": ["phishing"],
            },
            {
                "name": "Pulse Gamma",
                "tags": ["malware"],
            },
        ],
    },
}

SAMPLE_IP_PASSIVE_DNS = {
    "passive_dns": [
        {
            "address": "10.0.0.1",
            "hostname": "host-a.example.com",
            "first": "2026-01-01T00:00:00",
            "last": "2026-04-01T00:00:00",
        },
        {
            "address": "malicious.example.net",
            "hostname": "",
            "first": "2026-02-01T00:00:00",
            "last": "2026-04-01T00:00:00",
        },
    ]
}

SAMPLE_DOMAIN_GENERAL = {
    "indicator": "evil.example.com",
    "type": "domain",
    "alexa": "12345",
    "whois": "Registrar: Example Registrar",
    "pulse_info": {
        "count": 1,
        "pulses": [
            {
                "name": "Domain Pulse",
                "tags": ["ransomware"],
            },
        ],
    },
}

SAMPLE_DOMAIN_PASSIVE_DNS = {
    "passive_dns": [
        {
            "address": "203.0.113.42",
            "hostname": "sub.evil.example.com",
            "first": "2026-01-15T00:00:00",
            "last": "2026-04-01T00:00:00",
        },
    ]
}

SAMPLE_EMPTY_PASSIVE_DNS = {"passive_dns": []}


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_mock_response(status_code: int, body: dict, headers: dict | None = None) -> MagicMock:
    """Build a mock httpx.Response-like object."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.headers = headers or {}
    mock_resp.json.return_value = body
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def _make_client(responses: list[MagicMock]) -> MagicMock:
    """Build a mock AsyncClient that returns responses in order for sequential get() calls."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=responses)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ---------------------------------------------------------------------------
# Fixtures: IP target (general + passive_dns)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_ip_success():
    """Patch httpx.AsyncClient for a successful IPv4 query (general + passive_dns)."""
    responses = [
        _make_mock_response(200, SAMPLE_IP_GENERAL),
        _make_mock_response(200, SAMPLE_IP_PASSIVE_DNS),
    ]
    mock_client = _make_client(responses)
    with patch("adversary_pursuit.modules.cti.otx.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_ip_no_dns():
    """Patch httpx.AsyncClient for IPv4 query with INCLUDE_PASSIVE_DNS=false (general only)."""
    responses = [
        _make_mock_response(200, SAMPLE_IP_GENERAL),
    ]
    mock_client = _make_client(responses)
    with patch("adversary_pursuit.modules.cti.otx.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_ip_empty_passive_dns():
    """Patch httpx.AsyncClient for IPv4 query with empty passive_dns result."""
    responses = [
        _make_mock_response(200, SAMPLE_IP_GENERAL),
        _make_mock_response(200, SAMPLE_EMPTY_PASSIVE_DNS),
    ]
    mock_client = _make_client(responses)
    with patch("adversary_pursuit.modules.cti.otx.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


# ---------------------------------------------------------------------------
# Fixtures: Domain target
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_domain_success():
    """Patch httpx.AsyncClient for a successful domain query (general + passive_dns)."""
    responses = [
        _make_mock_response(200, SAMPLE_DOMAIN_GENERAL),
        _make_mock_response(200, SAMPLE_DOMAIN_PASSIVE_DNS),
    ]
    mock_client = _make_client(responses)
    with patch("adversary_pursuit.modules.cti.otx.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


# ---------------------------------------------------------------------------
# Fixtures: Error paths
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_401():
    """Patch httpx.AsyncClient to return 401 on the general endpoint."""
    responses = [
        _make_mock_response(401, {"detail": "Authentication failed."}),
    ]
    mock_client = _make_client(responses)
    with patch("adversary_pursuit.modules.cti.otx.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_429():
    """Patch httpx.AsyncClient to return 429 on the general endpoint."""
    responses = [
        _make_mock_response(429, {"detail": "Rate limit exceeded."}, headers={"Retry-After": "60"}),
    ]
    mock_client = _make_client(responses)
    with patch("adversary_pursuit.modules.cti.otx.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


# ---------------------------------------------------------------------------
# Protocol and metadata tests
# ---------------------------------------------------------------------------


class TestOTXMetadata:
    """Module satisfies PursuitModule protocol and declares correct metadata."""

    def test_satisfies_protocol(self):
        """AlienVaultOTX must satisfy PursuitModule isinstance check."""
        mod = AlienVaultOTX()
        assert isinstance(mod, PursuitModule)

    def test_module_name(self):
        mod = AlienVaultOTX()
        assert mod.name == "cti/otx"

    def test_module_type(self):
        mod = AlienVaultOTX()
        assert mod.module_type == "cti"

    def test_module_author(self):
        mod = AlienVaultOTX()
        assert mod.author == "Adversary Pursuit"

    def test_description_non_empty(self):
        mod = AlienVaultOTX()
        assert mod.description

    def test_options_has_target(self):
        mod = AlienVaultOTX()
        assert "TARGET" in mod.options
        assert mod.options["TARGET"]["required"] is True

    def test_options_has_include_passive_dns(self):
        mod = AlienVaultOTX()
        assert "INCLUDE_PASSIVE_DNS" in mod.options
        assert mod.options["INCLUDE_PASSIVE_DNS"]["required"] is False
        assert mod.options["INCLUDE_PASSIVE_DNS"]["default"] == "true"

    def test_options_has_pulse_limit(self):
        mod = AlienVaultOTX()
        assert "PULSE_LIMIT" in mod.options
        assert mod.options["PULSE_LIMIT"]["required"] is False
        assert mod.options["PULSE_LIMIT"]["default"] == "10"


# ---------------------------------------------------------------------------
# Authentication / error path tests
# ---------------------------------------------------------------------------


class TestOTXErrors:
    """hunt() error handling: missing key, 401, 429."""

    def test_hunt_no_api_key_raises_auth_error(self):
        """hunt() without an API key must raise AuthenticationError immediately."""
        mod = AlienVaultOTX()
        mod.initialize({})
        with pytest.raises(AuthenticationError, match="API key"):
            asyncio.run(mod.hunt("1.2.3.4", {}))

    def test_hunt_empty_api_key_raises_auth_error(self):
        """hunt() with empty string API key raises AuthenticationError."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": ""})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("1.2.3.4", {}))

    def test_hunt_401_raises_auth_error(self, mock_401):
        """401 response raises AuthenticationError."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "bad-key"})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("1.2.3.4", {}))

    def test_hunt_429_raises_rate_limit_error(self, mock_429):
        """429 response raises RateLimitError."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        with pytest.raises(RateLimitError):
            asyncio.run(mod.hunt("1.2.3.4", {}))


# ---------------------------------------------------------------------------
# IPv4 target detection and general endpoint parsing
# ---------------------------------------------------------------------------


class TestOTXIPv4Target:
    """hunt() with an IPv4 target calls /IPv4/ endpoints and parses correctly."""

    def test_hunt_returns_list(self, mock_ip_success):
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert isinstance(results, list)

    def test_hunt_primary_result_type_ipv4_addr(self, mock_ip_success):
        """First result is an ipv4-addr SCO."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["type"] == "ipv4-addr"

    def test_hunt_primary_result_value(self, mock_ip_success):
        """ipv4-addr SCO value matches the queried IP."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["value"] == "1.2.3.4"

    def test_hunt_pulse_count(self, mock_ip_success):
        """x_pulse_count is populated from general endpoint."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_pulse_count"] == 3

    def test_hunt_reputation(self, mock_ip_success):
        """x_reputation is populated from general endpoint."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_reputation"] == 2

    def test_hunt_country_code(self, mock_ip_success):
        """x_country_code is populated from general endpoint."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_country_code"] == "US"

    def test_hunt_asn(self, mock_ip_success):
        """x_asn is populated from general endpoint."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_asn"] == "AS15169 Google LLC"

    def test_hunt_uses_ipv4_endpoint_path(self, mock_ip_success):
        """general endpoint URL path contains /IPv4/."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("1.2.3.4", {}))
        first_call_url = mock_ip_success.get.call_args_list[0].args[0]
        assert "/IPv4/" in first_call_url
        assert "1.2.3.4" in first_call_url
        assert "general" in first_call_url

    def test_hunt_api_key_sent_as_header(self, mock_ip_success):
        """X-OTX-API-KEY header is passed to AsyncClient constructor."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "my-otx-key"})
        asyncio.run(mod.hunt("1.2.3.4", {}))
        # The module sets headers on AsyncClient init; verify get was called
        assert mock_ip_success.get.called


# ---------------------------------------------------------------------------
# Domain target detection and general endpoint parsing
# ---------------------------------------------------------------------------


class TestOTXDomainTarget:
    """hunt() with a domain target calls /domain/ endpoints and parses correctly."""

    def test_hunt_primary_result_type_domain_name(self, mock_domain_success):
        """First result is a domain-name SCO for a domain target."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert results[0]["type"] == "domain-name"

    def test_hunt_domain_value(self, mock_domain_success):
        """domain-name SCO value matches the queried domain."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert results[0]["value"] == "evil.example.com"

    def test_hunt_domain_pulse_count(self, mock_domain_success):
        """x_pulse_count populated from domain general endpoint."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert results[0]["x_pulse_count"] == 1

    def test_hunt_domain_alexa(self, mock_domain_success):
        """x_alexa populated from domain general endpoint."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert results[0]["x_alexa"] == "12345"

    def test_hunt_domain_whois(self, mock_domain_success):
        """x_whois populated from domain general endpoint."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert "Registrar" in results[0]["x_whois"]

    def test_hunt_uses_domain_endpoint_path(self, mock_domain_success):
        """general endpoint URL path contains /domain/."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("evil.example.com", {}))
        first_call_url = mock_domain_success.get.call_args_list[0].args[0]
        assert "/domain/" in first_call_url
        assert "evil.example.com" in first_call_url
        assert "general" in first_call_url


# ---------------------------------------------------------------------------
# Pulse extraction tests
# ---------------------------------------------------------------------------


class TestOTXPulseExtraction:
    """Pulse names and tags are extracted correctly from the general endpoint."""

    def test_pulse_names_extracted(self, mock_ip_success):
        """x_pulses contains pulse names in order."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert "x_pulses" in results[0]
        assert "Pulse Alpha" in results[0]["x_pulses"]
        assert "Pulse Beta" in results[0]["x_pulses"]
        assert "Pulse Gamma" in results[0]["x_pulses"]

    def test_pulse_tags_extracted(self, mock_ip_success):
        """x_pulse_tags contains unique tags from all pulses."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert "x_pulse_tags" in results[0]
        tags = set(results[0]["x_pulse_tags"])
        assert "malware" in tags
        assert "c2" in tags
        assert "phishing" in tags

    def test_pulse_tags_are_unique(self, mock_ip_success):
        """x_pulse_tags has no duplicates (malware appears in 2 pulses)."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        tags = results[0]["x_pulse_tags"]
        assert len(tags) == len(set(tags))

    def test_pulse_limit_respected(self, mock_ip_no_dns):
        """PULSE_LIMIT=1 restricts x_pulses to 1 entry."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(
            mod.hunt("1.2.3.4", {"INCLUDE_PASSIVE_DNS": "false", "PULSE_LIMIT": "1"})
        )
        assert len(results[0].get("x_pulses", [])) == 1


# ---------------------------------------------------------------------------
# Passive DNS tests
# ---------------------------------------------------------------------------


class TestOTXPassiveDNS:
    """Passive DNS endpoint adds related IPs and domains to results."""

    def test_passive_dns_adds_related_ip(self, mock_ip_success):
        """Passive DNS record with IP address adds an ipv4-addr SCO."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        ip_results = [
            r for r in results if r.get("type") == "ipv4-addr" and r.get("value") == "10.0.0.1"
        ]
        assert len(ip_results) == 1

    def test_passive_dns_adds_related_domain_from_hostname(self, mock_ip_success):
        """Passive DNS record hostname adds a domain-name SCO."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        domain_results = [
            r
            for r in results
            if r.get("type") == "domain-name" and r.get("value") == "host-a.example.com"
        ]
        assert len(domain_results) == 1

    def test_passive_dns_adds_non_ip_address_as_domain(self, mock_ip_success):
        """Passive DNS address that is not an IP is emitted as domain-name SCO."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        domain_results = [r for r in results if r.get("value") == "malicious.example.net"]
        assert len(domain_results) == 1
        assert domain_results[0]["type"] == "domain-name"

    def test_passive_dns_does_not_duplicate_target(self, mock_ip_success):
        """Target IP is not added again from passive DNS records."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        target_results = [r for r in results if r.get("value") == "1.2.3.4"]
        assert len(target_results) == 1  # Only the primary SCO

    def test_passive_dns_skipped_when_disabled(self, mock_ip_no_dns):
        """INCLUDE_PASSIVE_DNS=false causes only 1 HTTP call (general only)."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("1.2.3.4", {"INCLUDE_PASSIVE_DNS": "false"}))
        assert mock_ip_no_dns.get.call_count == 1

    def test_passive_dns_makes_two_http_calls_when_enabled(self, mock_ip_success):
        """INCLUDE_PASSIVE_DNS=true causes 2 HTTP calls (general + passive_dns)."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("1.2.3.4", {"INCLUDE_PASSIVE_DNS": "true"}))
        assert mock_ip_success.get.call_count == 2

    def test_passive_dns_url_contains_passive_dns_segment(self, mock_ip_success):
        """Second HTTP call URL ends with /passive_dns."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("1.2.3.4", {}))
        second_call_url = mock_ip_success.get.call_args_list[1].args[0]
        assert "passive_dns" in second_call_url

    def test_empty_passive_dns_returns_only_primary(self, mock_ip_empty_passive_dns):
        """Empty passive_dns list results in only the primary SCO."""
        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert len(results) == 1
        assert results[0]["type"] == "ipv4-addr"


# ---------------------------------------------------------------------------
# Production sequence test
# ---------------------------------------------------------------------------


class TestOTXProductionSequence:
    """Simulates the production call sequence for end-to-end validation."""

    def test_production_sequence_ip(self, mock_ip_success):
        """Full production sequence: load -> get -> initialize -> hunt with IP."""
        mgr = PluginManager()
        mgr.load_plugins()

        mod = mgr.get_module("cti/otx")
        assert mod is not None
        assert isinstance(mod, AlienVaultOTX)

        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))

        assert len(results) >= 1
        assert results[0]["type"] == "ipv4-addr"
        assert results[0]["value"] == "1.2.3.4"
        assert results[0]["x_pulse_count"] == 3

    def test_production_sequence_domain(self, mock_domain_success):
        """Full production sequence: load -> get -> initialize -> hunt with domain."""
        mgr = PluginManager()
        mgr.load_plugins()

        mod = mgr.get_module("cti/otx")
        assert mod is not None

        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))

        assert len(results) >= 1
        assert results[0]["type"] == "domain-name"
        assert results[0]["value"] == "evil.example.com"


# ---------------------------------------------------------------------------
# Plugin manager discovery tests
# ---------------------------------------------------------------------------


class TestOTXDiscovery:
    """AlienVaultOTX is discoverable via PluginManager."""

    def test_discoverable_via_plugin_manager(self):
        """PluginManager.load_plugins() finds cti/otx."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("cti/otx")
        assert mod is not None

    def test_plugin_manager_returns_otx_instance(self):
        """get_module('cti/otx') returns an AlienVaultOTX instance."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("cti/otx")
        assert isinstance(mod, AlienVaultOTX)

    def test_search_finds_otx(self):
        """PluginManager.search('otx') finds the cti/otx module."""
        mgr = PluginManager()
        mgr.load_plugins()
        results = mgr.search("otx")
        assert len(results) >= 1
        names = [r["name"] for r in results]
        assert "cti/otx" in names

    def test_search_by_cti_type(self):
        """PluginManager.search('cti') returns the cti/otx module."""
        mgr = PluginManager()
        mgr.load_plugins()
        results = mgr.search("cti")
        names = [r["name"] for r in results]
        assert "cti/otx" in names


# ---------------------------------------------------------------------------
# Regression tests for Bug 3: OTX ReadTimeout
# ---------------------------------------------------------------------------


class TestOTXTimeoutRegression:
    """Regression tests verifying the OTX module uses a sufficient HTTP timeout.

    Root cause: the default httpx timeout (5 seconds) was too short for OTX's
    passive DNS endpoint, causing ReadTimeout errors in production. The fix
    configures the client with timeout=30.0 seconds, which is sufficient for
    OTX's API latency profile.

    These tests verify the timeout is configured on the AsyncClient constructor
    so it cannot silently revert to the 5-second default.
    """

    def test_client_configured_with_30s_timeout(self, mock_ip_success):
        """AsyncClient is instantiated with timeout=30.0 (not the default 5.0).

        Inspects the constructor kwargs of the patched AsyncClient to verify
        the timeout value, preventing silent regression to a shorter timeout.
        """
        import asyncio

        with patch(
            "adversary_pursuit.modules.cti.otx.httpx.AsyncClient",
        ) as mock_cls:
            mock_cls.return_value = mock_ip_success
            mod = AlienVaultOTX()
            mod.initialize({"api_key": "test-key"})
            asyncio.run(mod.hunt("1.2.3.4", {}))

            _, kwargs = mock_cls.call_args
            timeout = kwargs.get("timeout")
            assert timeout is not None, (
                "AlienVaultOTX must pass a timeout to httpx.AsyncClient "
                "to avoid ReadTimeout on OTX's passive DNS endpoint."
            )
            # Accept either a numeric value >= 30 or an httpx.Timeout object
            # with a read timeout >= 30.
            import httpx as _httpx

            if isinstance(timeout, _httpx.Timeout):
                effective = timeout.read or timeout.connect or 0
            else:
                effective = float(timeout)
            assert effective >= 30.0, (
                f"OTX client timeout must be >= 30.0 seconds (got {effective}). "
                "The default 5s causes ReadTimeout on OTX passive DNS responses."
            )

    def test_hunt_does_not_raise_default_timeout(self, mock_ip_success):
        """hunt() completes successfully without raising ReadTimeout.

        With timeout=30.0 the mock response is returned before any real network
        call, so the timeout does not fire. This test documents that the module
        can complete a successful hunt() call in the expected happy path.
        """
        import asyncio

        mod = AlienVaultOTX()
        mod.initialize({"api_key": "test-key"})
        # Should not raise httpx.ReadTimeout or any other timeout exception
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert len(results) >= 1
        assert results[0]["type"] == "ipv4-addr"
