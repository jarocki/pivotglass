"""Tests for the PassiveTotal CTI module (Issue #13).

# @mock-exempt: httpx.AsyncClient is an external HTTP boundary (PassiveTotal REST API).
# Tests must run without real API credentials. Mocking the HTTP layer is the only
# way to exercise error paths (401, 429) hermetically. This is Sacred Practice
# #5's explicitly-permitted exception: "Mocks are acceptable ONLY for external
# boundaries (HTTP APIs, third-party services, databases)."

Production sequence: PluginManager.load_plugins() -> get_module('cti/passivetotal') ->
initialize({passivetotal_user, passivetotal_key}) -> hunt(target, options). Tests cover
the full sequence including domain and IPv4 targets, passive DNS results, optional WHOIS
endpoint, INCLUDE_WHOIS=false, deduplication, and all error paths.

@decision DEC-TEST-PT-001
@title Monkeypatch httpx.AsyncClient with context manager support; per-URL routing via side_effect
@status accepted
@rationale PassiveTotal module uses httpx.AsyncClient as a context manager and calls
           client.get() once (passive DNS) or twice (passive DNS + WHOIS). The mock must
           support __aenter__/__aexit__ and route responses in call order via side_effect.
           This mirrors DEC-TEST-OTX-001 and ensures the multi-endpoint pattern is
           exercised hermetically without real API credentials.
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
from adversary_pursuit.modules.cti.passivetotal import PassiveTotal

# ---------------------------------------------------------------------------
# Sample API responses
# ---------------------------------------------------------------------------

SAMPLE_DOMAIN_PASSIVE_DNS = {
    "queryValue": "evil.example.com",
    "queryType": "domain",
    "firstSeen": "2025-01-15 08:00:00",
    "lastSeen": "2026-03-20 12:00:00",
    "totalRecords": 3,
    "results": [
        {
            "firstSeen": "2025-01-15 08:00:00",
            "lastSeen": "2026-03-20 12:00:00",
            "source": ["riskiq"],
            "value": "198.51.100.42",
            "collected": "2026-03-20 12:00:00",
            "recordType": "A",
            "resolve": "198.51.100.42",
            "resolveType": "ip",
        },
        {
            "firstSeen": "2025-06-01 00:00:00",
            "lastSeen": "2026-01-01 00:00:00",
            "source": ["riskiq"],
            "value": "203.0.113.99",
            "collected": "2026-01-01 00:00:00",
            "recordType": "A",
            "resolve": "203.0.113.99",
            "resolveType": "ip",
        },
        {
            "firstSeen": "2026-01-01 00:00:00",
            "lastSeen": "2026-03-20 12:00:00",
            "source": ["riskiq"],
            "value": "mail.evil.example.com",
            "collected": "2026-03-20 12:00:00",
            "recordType": "MX",
            "resolve": "mail.evil.example.com",
            "resolveType": "domain",
        },
    ],
}

SAMPLE_DOMAIN_WHOIS = {
    "domain": "evil.example.com",
    "registrar": "Evil Registrar Inc.",
    "registrant": "John Doe",
    "registrantEmail": "johndoe@evil.example.com",
    "registered": "2020-01-01",
    "expiresAt": "2027-01-01",
    "nameServers": ["ns1.evil.example.com", "ns2.evil.example.com"],
}

SAMPLE_IP_PASSIVE_DNS = {
    "queryValue": "1.2.3.4",
    "queryType": "ip",
    "firstSeen": "2025-03-01 00:00:00",
    "lastSeen": "2026-04-01 00:00:00",
    "totalRecords": 2,
    "results": [
        {
            "firstSeen": "2025-03-01 00:00:00",
            "lastSeen": "2026-04-01 00:00:00",
            "source": ["riskiq"],
            "value": "evil.example.com",
            "collected": "2026-04-01 00:00:00",
            "recordType": "A",
            "resolve": "evil.example.com",
            "resolveType": "domain",
        },
        {
            "firstSeen": "2025-05-01 00:00:00",
            "lastSeen": "2026-02-01 00:00:00",
            "source": ["riskiq"],
            "value": "other.example.org",
            "collected": "2026-02-01 00:00:00",
            "recordType": "A",
            "resolve": "other.example.org",
            "resolveType": "domain",
        },
    ],
}

SAMPLE_IP_WHOIS = {
    "domain": "1.2.3.4",
    "registrar": "ARIN",
    "registrant": "Some ISP",
    "registrantEmail": "",
    "registered": "2010-06-01",
    "expiresAt": "",
    "nameServers": [],
}

SAMPLE_EMPTY_PASSIVE_DNS = {
    "queryValue": "unknown.example.com",
    "queryType": "domain",
    "firstSeen": "",
    "lastSeen": "",
    "totalRecords": 0,
    "results": [],
}

SAMPLE_DUPLICATE_PASSIVE_DNS = {
    "queryValue": "dup.example.com",
    "queryType": "domain",
    "firstSeen": "2025-01-01 00:00:00",
    "lastSeen": "2026-01-01 00:00:00",
    "totalRecords": 3,
    "results": [
        {
            "firstSeen": "2025-01-01 00:00:00",
            "lastSeen": "2026-01-01 00:00:00",
            "source": ["riskiq"],
            "value": "10.0.0.1",
            "collected": "2026-01-01 00:00:00",
            "recordType": "A",
            "resolve": "10.0.0.1",
            "resolveType": "ip",
        },
        {
            "firstSeen": "2025-01-01 00:00:00",
            "lastSeen": "2026-01-01 00:00:00",
            "source": ["riskiq"],
            "value": "10.0.0.1",  # duplicate
            "collected": "2026-01-01 00:00:00",
            "recordType": "A",
            "resolve": "10.0.0.1",
            "resolveType": "ip",
        },
        {
            "firstSeen": "2025-06-01 00:00:00",
            "lastSeen": "2026-01-01 00:00:00",
            "source": ["riskiq"],
            "value": "dup.example.com",  # same as target
            "collected": "2026-01-01 00:00:00",
            "recordType": "CNAME",
            "resolve": "dup.example.com",
            "resolveType": "domain",
        },
    ],
}


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_mock_response(
    status_code: int,
    body: dict,
    headers: dict | None = None,
) -> MagicMock:
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
# Fixtures: domain target
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_domain_with_whois():
    """Patch httpx.AsyncClient for domain query with passive DNS + WHOIS."""
    responses = [
        _make_mock_response(200, SAMPLE_DOMAIN_PASSIVE_DNS),
        _make_mock_response(200, SAMPLE_DOMAIN_WHOIS),
    ]
    mock_client = _make_client(responses)
    with patch(
        "adversary_pursuit.modules.cti.passivetotal.httpx.AsyncClient", return_value=mock_client
    ):
        yield mock_client


@pytest.fixture
def mock_domain_no_whois():
    """Patch httpx.AsyncClient for domain query with passive DNS only."""
    responses = [
        _make_mock_response(200, SAMPLE_DOMAIN_PASSIVE_DNS),
    ]
    mock_client = _make_client(responses)
    with patch(
        "adversary_pursuit.modules.cti.passivetotal.httpx.AsyncClient", return_value=mock_client
    ):
        yield mock_client


@pytest.fixture
def mock_domain_empty_pdns():
    """Patch httpx.AsyncClient for domain with empty passive DNS results."""
    responses = [
        _make_mock_response(200, SAMPLE_EMPTY_PASSIVE_DNS),
    ]
    mock_client = _make_client(responses)
    with patch(
        "adversary_pursuit.modules.cti.passivetotal.httpx.AsyncClient", return_value=mock_client
    ):
        yield mock_client


@pytest.fixture
def mock_domain_duplicates():
    """Patch httpx.AsyncClient for domain with duplicate passive DNS entries."""
    responses = [
        _make_mock_response(200, SAMPLE_DUPLICATE_PASSIVE_DNS),
    ]
    mock_client = _make_client(responses)
    with patch(
        "adversary_pursuit.modules.cti.passivetotal.httpx.AsyncClient", return_value=mock_client
    ):
        yield mock_client


# ---------------------------------------------------------------------------
# Fixtures: IP target
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_ip_with_whois():
    """Patch httpx.AsyncClient for IP query with passive DNS + WHOIS."""
    responses = [
        _make_mock_response(200, SAMPLE_IP_PASSIVE_DNS),
        _make_mock_response(200, SAMPLE_IP_WHOIS),
    ]
    mock_client = _make_client(responses)
    with patch(
        "adversary_pursuit.modules.cti.passivetotal.httpx.AsyncClient", return_value=mock_client
    ):
        yield mock_client


@pytest.fixture
def mock_ip_no_whois():
    """Patch httpx.AsyncClient for IP query with passive DNS only."""
    responses = [
        _make_mock_response(200, SAMPLE_IP_PASSIVE_DNS),
    ]
    mock_client = _make_client(responses)
    with patch(
        "adversary_pursuit.modules.cti.passivetotal.httpx.AsyncClient", return_value=mock_client
    ):
        yield mock_client


# ---------------------------------------------------------------------------
# Fixtures: error paths
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_401():
    """Patch httpx.AsyncClient to return 401 on the first request."""
    responses = [
        _make_mock_response(401, {"error": "Could not authenticate."}),
    ]
    mock_client = _make_client(responses)
    with patch(
        "adversary_pursuit.modules.cti.passivetotal.httpx.AsyncClient", return_value=mock_client
    ):
        yield mock_client


@pytest.fixture
def mock_429():
    """Patch httpx.AsyncClient to return 429 on the first request."""
    responses = [
        _make_mock_response(
            429,
            {"error": "Rate limit exceeded."},
            headers={"Retry-After": "60"},
        ),
    ]
    mock_client = _make_client(responses)
    with patch(
        "adversary_pursuit.modules.cti.passivetotal.httpx.AsyncClient", return_value=mock_client
    ):
        yield mock_client


# ---------------------------------------------------------------------------
# Protocol and metadata tests
# ---------------------------------------------------------------------------


class TestPassiveTotalMetadata:
    """Module satisfies PursuitModule protocol and declares correct metadata."""

    def test_satisfies_protocol(self):
        """PassiveTotal must satisfy PursuitModule isinstance check."""
        mod = PassiveTotal()
        assert isinstance(mod, PursuitModule)

    def test_module_name(self):
        mod = PassiveTotal()
        assert mod.name == "cti/passivetotal"

    def test_module_type(self):
        mod = PassiveTotal()
        assert mod.module_type == "cti"

    def test_module_author(self):
        mod = PassiveTotal()
        assert mod.author == "Adversary Pursuit"

    def test_description_non_empty(self):
        mod = PassiveTotal()
        assert mod.description

    def test_options_has_target(self):
        mod = PassiveTotal()
        assert "TARGET" in mod.options
        assert mod.options["TARGET"]["required"] is True

    def test_options_has_include_whois(self):
        mod = PassiveTotal()
        assert "INCLUDE_WHOIS" in mod.options
        assert mod.options["INCLUDE_WHOIS"]["required"] is False
        assert mod.options["INCLUDE_WHOIS"]["default"] == "true"


# ---------------------------------------------------------------------------
# Authentication / error path tests
# ---------------------------------------------------------------------------


class TestPassiveTotalErrors:
    """hunt() error handling: missing credentials, 401, 429."""

    def test_hunt_no_config_raises_auth_error(self):
        """hunt() with empty config raises AuthenticationError immediately."""
        mod = PassiveTotal()
        mod.initialize({})
        with pytest.raises(AuthenticationError, match="user"):
            asyncio.run(mod.hunt("evil.example.com", {}))

    def test_hunt_missing_user_raises_auth_error(self):
        """hunt() with key but no user raises AuthenticationError."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_key": "some-key"})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("evil.example.com", {}))

    def test_hunt_missing_key_raises_auth_error(self):
        """hunt() with user but no key raises AuthenticationError."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "user@example.com"})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("evil.example.com", {}))

    def test_hunt_empty_user_raises_auth_error(self):
        """hunt() with empty user string raises AuthenticationError."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "", "passivetotal_key": "key"})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("evil.example.com", {}))

    def test_hunt_empty_key_raises_auth_error(self):
        """hunt() with empty key string raises AuthenticationError."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "user@example.com", "passivetotal_key": ""})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("evil.example.com", {}))

    def test_hunt_401_raises_auth_error(self, mock_401):
        """401 response raises AuthenticationError."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "bad-key"})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("evil.example.com", {}))

    def test_hunt_429_raises_rate_limit_error(self, mock_429):
        """429 response raises RateLimitError."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "test-key"})
        with pytest.raises(RateLimitError):
            asyncio.run(mod.hunt("evil.example.com", {}))


# ---------------------------------------------------------------------------
# Domain target tests
# ---------------------------------------------------------------------------


class TestPassiveTotalDomainTarget:
    """hunt() with a domain target returns correct STIX SCOs."""

    def test_hunt_returns_list(self, mock_domain_with_whois):
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert isinstance(results, list)

    def test_hunt_primary_type_domain_name(self, mock_domain_with_whois):
        """First result is a domain-name SCO for a domain target."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert results[0]["type"] == "domain-name"

    def test_hunt_primary_value(self, mock_domain_with_whois):
        """domain-name SCO value matches the queried domain."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert results[0]["value"] == "evil.example.com"

    def test_hunt_primary_has_first_seen(self, mock_domain_with_whois):
        """Primary SCO has x_first_seen from passive DNS response."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert "x_first_seen" in results[0]
        assert results[0]["x_first_seen"] == "2025-01-15 08:00:00"

    def test_hunt_primary_has_last_seen(self, mock_domain_with_whois):
        """Primary SCO has x_last_seen from passive DNS response."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert "x_last_seen" in results[0]
        assert results[0]["x_last_seen"] == "2026-03-20 12:00:00"

    def test_hunt_primary_has_record_count(self, mock_domain_with_whois):
        """Primary SCO has x_record_count from passive DNS response."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert "x_record_count" in results[0]
        assert results[0]["x_record_count"] == 3

    def test_hunt_related_ip_scos(self, mock_domain_no_whois):
        """Passive DNS IP resolve values are emitted as ipv4-addr SCOs."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("evil.example.com", {"INCLUDE_WHOIS": "false"}))
        ip_values = {r["value"] for r in results if r["type"] == "ipv4-addr"}
        assert "198.51.100.42" in ip_values
        assert "203.0.113.99" in ip_values

    def test_hunt_related_domain_scos(self, mock_domain_no_whois):
        """Passive DNS domain resolve values are emitted as domain-name SCOs."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("evil.example.com", {"INCLUDE_WHOIS": "false"}))
        domain_values = {r["value"] for r in results if r["type"] == "domain-name"}
        assert "mail.evil.example.com" in domain_values


# ---------------------------------------------------------------------------
# IPv4 target tests
# ---------------------------------------------------------------------------


class TestPassiveTotalIPv4Target:
    """hunt() with an IPv4 target returns correct STIX SCOs."""

    def test_hunt_primary_type_ipv4_addr(self, mock_ip_with_whois):
        """First result is an ipv4-addr SCO for an IPv4 target."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["type"] == "ipv4-addr"

    def test_hunt_primary_ip_value(self, mock_ip_with_whois):
        """ipv4-addr SCO value matches the queried IP."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["value"] == "1.2.3.4"

    def test_hunt_ip_has_first_seen(self, mock_ip_with_whois):
        """Primary ipv4-addr SCO has x_first_seen."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_first_seen"] == "2025-03-01 00:00:00"

    def test_hunt_ip_has_last_seen(self, mock_ip_with_whois):
        """Primary ipv4-addr SCO has x_last_seen."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_last_seen"] == "2026-04-01 00:00:00"

    def test_hunt_ip_has_record_count(self, mock_ip_with_whois):
        """Primary ipv4-addr SCO has x_record_count."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_record_count"] == 2

    def test_hunt_ip_related_domains(self, mock_ip_no_whois):
        """Related domain-name SCOs appear from passive DNS resolve values."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {"INCLUDE_WHOIS": "false"}))
        domain_values = {r["value"] for r in results if r["type"] == "domain-name"}
        assert "evil.example.com" in domain_values
        assert "other.example.org" in domain_values


# ---------------------------------------------------------------------------
# WHOIS option tests
# ---------------------------------------------------------------------------


class TestPassiveTotalWHOIS:
    """INCLUDE_WHOIS controls whether the WHOIS endpoint is queried."""

    def test_whois_enabled_makes_two_http_calls(self, mock_domain_with_whois):
        """INCLUDE_WHOIS=true causes 2 HTTP GET calls (pdns + whois)."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        asyncio.run(mod.hunt("evil.example.com", {"INCLUDE_WHOIS": "true"}))
        assert mock_domain_with_whois.get.call_count == 2

    def test_whois_disabled_makes_one_http_call(self, mock_domain_no_whois):
        """INCLUDE_WHOIS=false causes only 1 HTTP GET call (pdns only)."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        asyncio.run(mod.hunt("evil.example.com", {"INCLUDE_WHOIS": "false"}))
        assert mock_domain_no_whois.get.call_count == 1

    def test_whois_default_is_enabled(self, mock_domain_with_whois):
        """Default behavior (no INCLUDE_WHOIS option) queries WHOIS endpoint."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        asyncio.run(mod.hunt("evil.example.com", {}))
        assert mock_domain_with_whois.get.call_count == 2

    def test_whois_data_on_primary_sco(self, mock_domain_with_whois):
        """WHOIS data appears as x_whois on primary SCO when enabled."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        primary = results[0]
        assert "x_whois" in primary
        whois = primary["x_whois"]
        assert isinstance(whois, dict)
        assert whois.get("registrar") == "Evil Registrar Inc."

    def test_whois_not_on_primary_when_disabled(self, mock_domain_no_whois):
        """x_whois is absent on primary SCO when INCLUDE_WHOIS=false."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("evil.example.com", {"INCLUDE_WHOIS": "false"}))
        assert "x_whois" not in results[0]

    def test_whois_second_call_url_contains_whois(self, mock_domain_with_whois):
        """Second HTTP call URL contains the whois endpoint segment."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        asyncio.run(mod.hunt("evil.example.com", {}))
        second_url = mock_domain_with_whois.get.call_args_list[1][0][0]
        assert "whois" in second_url


# ---------------------------------------------------------------------------
# Deduplication tests
# ---------------------------------------------------------------------------


class TestPassiveTotalDeduplication:
    """Duplicate and self-referential passive DNS entries are suppressed."""

    def test_no_duplicate_scos(self, mock_domain_duplicates):
        """Duplicate resolve values produce only one SCO each."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("dup.example.com", {"INCLUDE_WHOIS": "false"}))
        values = [r["value"] for r in results]
        assert len(values) == len(set(values))

    def test_target_not_duplicated_in_results(self, mock_domain_duplicates):
        """Target domain is not added again from passive DNS records."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("dup.example.com", {"INCLUDE_WHOIS": "false"}))
        target_results = [r for r in results if r.get("value") == "dup.example.com"]
        assert len(target_results) == 1  # Only the primary SCO

    def test_duplicate_ip_appears_once(self, mock_domain_duplicates):
        """IP appearing twice in passive DNS records produces one ipv4-addr SCO."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("dup.example.com", {"INCLUDE_WHOIS": "false"}))
        ip_results = [r for r in results if r.get("value") == "10.0.0.1"]
        assert len(ip_results) == 1


# ---------------------------------------------------------------------------
# Empty results test
# ---------------------------------------------------------------------------


class TestPassiveTotalEmptyResults:
    """Empty passive DNS results return only the primary SCO."""

    def test_empty_passive_dns_returns_only_primary(self, mock_domain_empty_pdns):
        """Empty passive DNS list results in only the primary SCO."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("unknown.example.com", {"INCLUDE_WHOIS": "false"}))
        assert len(results) == 1
        assert results[0]["type"] == "domain-name"
        assert results[0]["value"] == "unknown.example.com"


# ---------------------------------------------------------------------------
# HTTP auth tests
# ---------------------------------------------------------------------------


class TestPassiveTotalHTTPAuth:
    """PassiveTotal uses HTTP Basic Auth (user:key) on all requests."""

    def test_basic_auth_credentials_passed(self, mock_domain_no_whois):
        """HTTP Basic Auth is passed to AsyncClient constructor."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "my-pt-key"})
        with patch(
            "adversary_pursuit.modules.cti.passivetotal.httpx.AsyncClient",
            return_value=mock_domain_no_whois,
        ) as mock_cls:
            asyncio.run(mod.hunt("evil.example.com", {"INCLUDE_WHOIS": "false"}))
            call_kwargs = mock_cls.call_args[1]
            assert "auth" in call_kwargs
            auth = call_kwargs["auth"]
            # Auth is a tuple (user, key)
            assert auth == ("u@example.com", "my-pt-key")

    def test_first_request_url_contains_passive_dns(self, mock_domain_no_whois):
        """First HTTP call URL contains the passive DNS endpoint segment."""
        mod = PassiveTotal()
        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        asyncio.run(mod.hunt("evil.example.com", {"INCLUDE_WHOIS": "false"}))
        first_url = mock_domain_no_whois.get.call_args_list[0][0][0]
        assert "dns/passive" in first_url


# ---------------------------------------------------------------------------
# Production sequence test
# ---------------------------------------------------------------------------


class TestPassiveTotalProductionSequence:
    """Simulates the production call sequence end-to-end."""

    def test_production_sequence_domain(self, mock_domain_with_whois):
        """Full production sequence: load -> get -> initialize -> hunt with domain."""
        mgr = PluginManager()
        mgr.load_plugins()

        mod = mgr.get_module("cti/passivetotal")
        assert mod is not None
        assert isinstance(mod, PassiveTotal)

        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))

        assert len(results) >= 1
        assert results[0]["type"] == "domain-name"
        assert results[0]["value"] == "evil.example.com"
        assert results[0]["x_record_count"] == 3

    def test_production_sequence_ip(self, mock_ip_with_whois):
        """Full production sequence: load -> get -> initialize -> hunt with IP."""
        mgr = PluginManager()
        mgr.load_plugins()

        mod = mgr.get_module("cti/passivetotal")
        assert mod is not None

        mod.initialize({"passivetotal_user": "u@example.com", "passivetotal_key": "key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))

        assert len(results) >= 1
        assert results[0]["type"] == "ipv4-addr"
        assert results[0]["value"] == "1.2.3.4"


# ---------------------------------------------------------------------------
# Plugin manager discovery tests
# ---------------------------------------------------------------------------


class TestPassiveTotalDiscovery:
    """PassiveTotal is discoverable via PluginManager."""

    def test_discoverable_via_plugin_manager(self):
        """PluginManager.load_plugins() finds cti/passivetotal."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("cti/passivetotal")
        assert mod is not None

    def test_plugin_manager_returns_passivetotal_instance(self):
        """get_module('cti/passivetotal') returns a PassiveTotal instance."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("cti/passivetotal")
        assert isinstance(mod, PassiveTotal)

    def test_search_finds_passivetotal(self):
        """PluginManager.search('passivetotal') finds the cti/passivetotal module."""
        mgr = PluginManager()
        mgr.load_plugins()
        results = mgr.search("passivetotal")
        assert len(results) >= 1
        names = [r["name"] for r in results]
        assert "cti/passivetotal" in names

    def test_search_by_cti_type(self):
        """PluginManager.search('cti') returns the cti/passivetotal module."""
        mgr = PluginManager()
        mgr.load_plugins()
        results = mgr.search("cti")
        names = [r["name"] for r in results]
        assert "cti/passivetotal" in names


# ---------------------------------------------------------------------------
# Regression tests for Bug 4: PassiveTotal stale error message
# ---------------------------------------------------------------------------


class TestPassiveTotalErrorMessageRegression:
    """Regression tests verifying the missing-credentials error message is accurate.

    Root cause: the error message referenced 'ap config set api_keys.passivetotal_user'
    which does not exist as a CLI command. Updated to reference the three accurate
    configuration paths: the 'model select' wizard, env vars, and ~/.ap/config.toml.
    """

    def test_missing_credentials_error_message_does_not_mention_ap_config_set(self):
        """Error message must NOT reference the non-existent 'ap config set' command."""
        import asyncio

        mod = PassiveTotal()
        mod.initialize({})
        with pytest.raises(AuthenticationError) as exc_info:
            asyncio.run(mod.hunt("google.com", {}))
        message = str(exc_info.value)
        assert "ap config set" not in message, (
            "Error message still references 'ap config set' which does not exist. "
            "Update the message to reference the wizard, env vars, or config.toml."
        )

    def test_missing_credentials_error_message_references_wizard(self):
        """Error message must reference 'model select' (the setup wizard)."""
        import asyncio

        mod = PassiveTotal()
        mod.initialize({})
        with pytest.raises(AuthenticationError) as exc_info:
            asyncio.run(mod.hunt("google.com", {}))
        message = str(exc_info.value)
        assert "model select" in message, (
            "Error message must mention 'model select' so users know how to "
            "configure PassiveTotal credentials via the wizard."
        )

    def test_missing_credentials_error_message_references_env_vars(self):
        """Error message must reference the correct env var names."""
        import asyncio

        mod = PassiveTotal()
        mod.initialize({})
        with pytest.raises(AuthenticationError) as exc_info:
            asyncio.run(mod.hunt("google.com", {}))
        message = str(exc_info.value)
        # Must mention at least one of the correct env var names
        assert "AP_PASSIVETOTAL_USER" in message or "PT_USERNAME" in message, (
            "Error message must mention the correct env var names "
            "(AP_PASSIVETOTAL_USER / PT_USERNAME) so users can configure via env."
        )

    def test_missing_credentials_error_message_references_config_toml(self):
        """Error message must reference ~/.ap/config.toml as a configuration path."""
        import asyncio

        mod = PassiveTotal()
        mod.initialize({})
        with pytest.raises(AuthenticationError) as exc_info:
            asyncio.run(mod.hunt("google.com", {}))
        message = str(exc_info.value)
        assert "config.toml" in message, (
            "Error message must mention ~/.ap/config.toml so users know they can "
            "hand-edit their configuration file directly."
        )
