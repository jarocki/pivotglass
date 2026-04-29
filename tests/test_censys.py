"""Tests for the Censys Host OSINT module (Issue #8).

# @mock-exempt: httpx.AsyncClient is an external HTTP boundary (Censys REST API).
# Tests must run without real API credentials. Mocking the HTTP layer is the only
# way to exercise error paths (401, 403, 404, 429) hermetically. This is Sacred
# Practice #5's explicitly-permitted exception: "Mocks are acceptable ONLY for
# external boundaries (HTTP APIs, third-party services, databases)."

Production sequence: PluginManager.load_plugins() -> get_module('osint/censys_host') ->
initialize({censys_id, censys_secret}) -> hunt(ip, options). Tests cover the full
sequence including services, certificates, OS, location, autonomous system data,
and all error paths (missing creds, 401, 403, 404, 429).

@decision DEC-TEST-CENSYS-001
@title Monkeypatch httpx.AsyncClient for hermetic Censys tests
@status accepted
@rationale respx is not in the project's dependency set. Python's unittest.mock
           (via patch) patches httpx.AsyncClient.__aenter__ and provides full
           context-manager semantics. This matches the established pattern from
           DEC-TEST-ABUSEIPDB-001, DEC-TEST-OTX-001, and DEC-TEST-SHODAN-001 —
           consistent approach across all API modules avoids introducing new
           test infrastructure.

@decision DEC-TEST-CENSYS-002
@title Censys uses HTTP Basic Auth (censys_id:censys_secret), not an API key header
@status accepted
@rationale Censys API v2 authenticates via HTTP Basic Auth with the censys_id
           as username and censys_secret as password. Tests verify both credentials
           are required (not just one) and that the httpx call uses auth=(...).
           Missing either credential raises AuthenticationError before HTTP.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adversary_pursuit.modules.base import (
    AuthenticationError,
    PursuitModule,
    RateLimitError,
)
from adversary_pursuit.modules.osint.censys_host import CensysHost
from adversary_pursuit.core.plugin_mgr import PluginManager


# ---------------------------------------------------------------------------
# Sample API responses
# ---------------------------------------------------------------------------

# Full response with services, certificates, OS, location, autonomous_system
SAMPLE_RESPONSE_FULL = {
    "result": {
        "ip": "8.8.8.8",
        "services": [
            {
                "port": 53,
                "transport_protocol": "UDP",
                "service_name": "DNS",
                "certificate": None,
            },
            {
                "port": 443,
                "transport_protocol": "TCP",
                "service_name": "HTTPS",
                "certificate": "sha256:abc123def456",
            },
            {
                "port": 80,
                "transport_protocol": "TCP",
                "service_name": "HTTP",
                "certificate": None,
            },
        ],
        "operating_system": {
            "product": "Linux",
            "version": "5.x",
        },
        "location": {
            "country": "United States",
            "country_code": "US",
            "city": "Mountain View",
        },
        "autonomous_system": {
            "asn": 15169,
            "name": "GOOGLE",
            "bgp_prefix": "8.8.8.0/24",
            "country_code": "US",
        },
        "last_updated_at": "2026-04-01T12:00:00.000000Z",
    }
}

# Response with multiple services having certificates
SAMPLE_RESPONSE_MULTI_CERTS = {
    "result": {
        "ip": "1.2.3.4",
        "services": [
            {
                "port": 443,
                "transport_protocol": "TCP",
                "service_name": "HTTPS",
                "certificate": "sha256:cert1111",
            },
            {
                "port": 8443,
                "transport_protocol": "TCP",
                "service_name": "HTTPS",
                "certificate": "sha256:cert2222",
            },
            {
                "port": 22,
                "transport_protocol": "TCP",
                "service_name": "SSH",
                "certificate": None,
            },
        ],
        "operating_system": None,
        "location": {
            "country": "Germany",
            "country_code": "DE",
            "city": "Berlin",
        },
        "autonomous_system": {
            "asn": 13335,
            "name": "CLOUDFLARENET",
            "bgp_prefix": "1.2.3.0/24",
            "country_code": "DE",
        },
        "last_updated_at": "2026-03-15T08:00:00.000000Z",
    }
}

# Minimal response — no OS, no certificates on any service
SAMPLE_RESPONSE_MINIMAL = {
    "result": {
        "ip": "192.0.2.1",
        "services": [
            {
                "port": 80,
                "transport_protocol": "TCP",
                "service_name": "HTTP",
                "certificate": None,
            },
        ],
        "operating_system": None,
        "location": {
            "country": "Japan",
            "country_code": "JP",
            "city": "",
        },
        "autonomous_system": {
            "asn": 2497,
            "name": "IIJ",
            "bgp_prefix": "192.0.2.0/24",
            "country_code": "JP",
        },
        "last_updated_at": "2026-02-20T00:00:00.000000Z",
    }
}

# Response with no services at all
SAMPLE_RESPONSE_NO_SERVICES = {
    "result": {
        "ip": "10.0.0.1",
        "services": [],
        "operating_system": None,
        "location": {
            "country": "United States",
            "country_code": "US",
            "city": "",
        },
        "autonomous_system": {
            "asn": 0,
            "name": "",
            "bgp_prefix": "",
            "country_code": "US",
        },
        "last_updated_at": "",
    }
}


def _make_mock_response(
    status_code: int, body: dict | None = None, headers: dict | None = None
) -> MagicMock:
    """Build a mock httpx.Response-like object."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.headers = headers or {}
    mock_resp.json.return_value = body or {}
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def _make_client_mock(response: MagicMock) -> MagicMock:
    """Wrap a mock response in a context-manager-compatible AsyncClient mock."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_success():
    """Patch httpx.AsyncClient to return the full success response."""
    mock_resp = _make_mock_response(200, SAMPLE_RESPONSE_FULL)
    mock_client = _make_client_mock(mock_resp)
    with patch("adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_success_multi_certs():
    """Patch httpx.AsyncClient to return response with multiple certificate services."""
    mock_resp = _make_mock_response(200, SAMPLE_RESPONSE_MULTI_CERTS)
    mock_client = _make_client_mock(mock_resp)
    with patch("adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_success_minimal():
    """Patch httpx.AsyncClient to return a minimal response (no OS, no certs)."""
    mock_resp = _make_mock_response(200, SAMPLE_RESPONSE_MINIMAL)
    mock_client = _make_client_mock(mock_resp)
    with patch("adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_success_no_services():
    """Patch httpx.AsyncClient to return a response with empty services list."""
    mock_resp = _make_mock_response(200, SAMPLE_RESPONSE_NO_SERVICES)
    mock_client = _make_client_mock(mock_resp)
    with patch("adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_401():
    """Patch httpx.AsyncClient to return 401 Unauthorized."""
    mock_resp = _make_mock_response(401, {"code": 401, "status": "Unauthorized", "error": "Invalid API credentials."})
    mock_client = _make_client_mock(mock_resp)
    with patch("adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_403():
    """Patch httpx.AsyncClient to return 403 Forbidden (plan restriction)."""
    mock_resp = _make_mock_response(403, {"code": 403, "status": "Forbidden", "error": "Forbidden. Your account does not have access to this endpoint."})
    mock_client = _make_client_mock(mock_resp)
    with patch("adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_404():
    """Patch httpx.AsyncClient to return 404 Not Found (IP not in index)."""
    mock_resp = _make_mock_response(404, {"code": 404, "status": "Not Found", "error": "404: Not Found"})
    mock_client = _make_client_mock(mock_resp)
    with patch("adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_429():
    """Patch httpx.AsyncClient to return 429 with Retry-After header."""
    mock_resp = _make_mock_response(
        429,
        {"code": 429, "status": "Too Many Requests", "error": "Rate limit exceeded."},
        headers={"Retry-After": "60"},
    )
    mock_client = _make_client_mock(mock_resp)
    with patch("adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_429_no_retry():
    """Patch httpx.AsyncClient to return 429 without Retry-After header."""
    mock_resp = _make_mock_response(
        429,
        {"code": 429, "status": "Too Many Requests", "error": "Rate limit exceeded."},
        headers={},
    )
    mock_client = _make_client_mock(mock_resp)
    with patch("adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


# ---------------------------------------------------------------------------
# Protocol and metadata tests
# ---------------------------------------------------------------------------

class TestCensysHostMetadata:
    """CensysHost satisfies PursuitModule protocol and declares correct metadata."""

    def test_satisfies_protocol(self):
        """CensysHost must satisfy PursuitModule isinstance check."""
        mod = CensysHost()
        assert isinstance(mod, PursuitModule)

    def test_module_name(self):
        mod = CensysHost()
        assert mod.name == "osint/censys_host"

    def test_module_type(self):
        mod = CensysHost()
        assert mod.module_type == "osint"

    def test_module_author(self):
        mod = CensysHost()
        assert mod.author == "Adversary Pursuit"

    def test_description_non_empty(self):
        mod = CensysHost()
        assert mod.description

    def test_options_has_target(self):
        mod = CensysHost()
        assert "TARGET" in mod.options
        assert mod.options["TARGET"]["required"] is True

    def test_target_default_empty_string(self):
        mod = CensysHost()
        assert mod.options["TARGET"]["default"] == ""


# ---------------------------------------------------------------------------
# Authentication / error path tests
# ---------------------------------------------------------------------------

class TestCensysHostErrors:
    """hunt() error handling: missing creds, 401, 403, 404, 429."""

    def test_hunt_no_censys_id_raises_auth_error(self):
        """hunt() without censys_id raises AuthenticationError immediately."""
        mod = CensysHost()
        mod.initialize({})
        with pytest.raises(AuthenticationError, match="censys_id"):
            asyncio.run(mod.hunt("8.8.8.8", {}))

    def test_hunt_empty_censys_id_raises_auth_error(self):
        """hunt() with empty censys_id raises AuthenticationError."""
        mod = CensysHost()
        mod.initialize({"censys_id": "", "censys_secret": "secret"})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("8.8.8.8", {}))

    def test_hunt_missing_censys_secret_raises_auth_error(self):
        """hunt() without censys_secret raises AuthenticationError immediately."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id"})
        with pytest.raises(AuthenticationError, match="censys_secret"):
            asyncio.run(mod.hunt("8.8.8.8", {}))

    def test_hunt_empty_censys_secret_raises_auth_error(self):
        """hunt() with empty censys_secret raises AuthenticationError."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": ""})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("8.8.8.8", {}))

    def test_hunt_401_raises_auth_error(self, mock_401):
        """401 response raises AuthenticationError."""
        mod = CensysHost()
        mod.initialize({"censys_id": "bad-id", "censys_secret": "bad-secret"})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("8.8.8.8", {}))

    def test_hunt_403_raises_auth_error(self, mock_403):
        """403 response raises AuthenticationError (plan restriction)."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("8.8.8.8", {}))

    def test_hunt_404_returns_empty_list(self, mock_404):
        """404 response returns empty list (IP not in Censys index)."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        results = asyncio.run(mod.hunt("192.0.2.99", {}))
        assert results == []

    def test_hunt_429_raises_rate_limit_error(self, mock_429):
        """429 response raises RateLimitError."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        with pytest.raises(RateLimitError):
            asyncio.run(mod.hunt("8.8.8.8", {}))

    def test_hunt_429_retry_after_populated(self, mock_429):
        """RateLimitError.retry_after is populated from Retry-After header."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        with pytest.raises(RateLimitError) as exc_info:
            asyncio.run(mod.hunt("8.8.8.8", {}))
        assert exc_info.value.retry_after == 60

    def test_hunt_429_no_retry_after_is_none(self, mock_429_no_retry):
        """RateLimitError.retry_after is None when header is absent."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        with pytest.raises(RateLimitError) as exc_info:
            asyncio.run(mod.hunt("8.8.8.8", {}))
        assert exc_info.value.retry_after is None


# ---------------------------------------------------------------------------
# Successful hunt() result structure tests
# ---------------------------------------------------------------------------

class TestCensysHostHuntResults:
    """hunt() result structure with mocked API responses."""

    def test_hunt_returns_list(self, mock_success):
        """hunt() always returns a list."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert isinstance(results, list)

    def test_hunt_primary_result_is_ipv4_addr(self, mock_success):
        """First result is an ipv4-addr SCO."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert results[0]["type"] == "ipv4-addr"

    def test_hunt_ipv4_value_matches_target(self, mock_success):
        """ipv4-addr SCO value matches the queried IP."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert results[0]["value"] == "8.8.8.8"

    def test_hunt_x_services_present(self, mock_success):
        """x_services custom property is present and is a list."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert "x_services" in results[0]
        assert isinstance(results[0]["x_services"], list)

    def test_hunt_x_services_count(self, mock_success):
        """x_services has 3 entries matching the sample response."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert len(results[0]["x_services"]) == 3

    def test_hunt_x_services_structure(self, mock_success):
        """Each x_services entry has port, protocol, and service_name."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        for svc in results[0]["x_services"]:
            assert "port" in svc
            assert "protocol" in svc
            assert "service_name" in svc

    def test_hunt_x_services_values(self, mock_success):
        """x_services entries have correct port/protocol/service_name values."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        services = results[0]["x_services"]
        ports = {s["port"] for s in services}
        assert 53 in ports
        assert 443 in ports
        assert 80 in ports

    def test_hunt_x_os_present(self, mock_success):
        """x_os custom property is present."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert "x_os" in results[0]
        assert results[0]["x_os"] == "Linux"

    def test_hunt_x_os_empty_when_none(self, mock_success_minimal):
        """x_os is empty string when operating_system is None in response."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        results = asyncio.run(mod.hunt("192.0.2.1", {}))
        assert results[0]["x_os"] == ""

    def test_hunt_x_location_country_present(self, mock_success):
        """x_location_country custom property is present."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert "x_location_country" in results[0]
        assert results[0]["x_location_country"] == "United States"

    def test_hunt_x_autonomous_system_present(self, mock_success):
        """x_autonomous_system custom property is present."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert "x_autonomous_system" in results[0]

    def test_hunt_x_autonomous_system_structure(self, mock_success):
        """x_autonomous_system has asn and name fields."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        asn = results[0]["x_autonomous_system"]
        assert asn["asn"] == 15169
        assert asn["name"] == "GOOGLE"

    def test_hunt_x_last_updated_present(self, mock_success):
        """x_last_updated custom property is present."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert "x_last_updated" in results[0]
        assert results[0]["x_last_updated"] == "2026-04-01T12:00:00.000000Z"

    def test_hunt_x_certificates_on_service_with_cert(self, mock_success):
        """Services with a certificate include x_certificates field."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        services = results[0]["x_services"]
        https_service = next(s for s in services if s["port"] == 443)
        assert "x_certificates" in https_service
        assert https_service["x_certificates"] == "sha256:abc123def456"

    def test_hunt_no_x_certificates_on_service_without_cert(self, mock_success):
        """Services without a certificate do not include x_certificates field."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        services = results[0]["x_services"]
        dns_service = next(s for s in services if s["port"] == 53)
        assert "x_certificates" not in dns_service

    def test_hunt_x_services_empty_when_no_services(self, mock_success_no_services):
        """x_services is an empty list when response has no services."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        results = asyncio.run(mod.hunt("10.0.0.1", {}))
        assert results[0]["x_services"] == []

    def test_hunt_multiple_certificates(self, mock_success_multi_certs):
        """Multiple services with certificates each get x_certificates."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        services = results[0]["x_services"]
        cert_services = [s for s in services if "x_certificates" in s]
        assert len(cert_services) == 2
        cert_values = {s["x_certificates"] for s in cert_services}
        assert "sha256:cert1111" in cert_values
        assert "sha256:cert2222" in cert_values

    def test_hunt_no_certificates_when_all_services_lack_certs(self, mock_success_minimal):
        """When no service has a certificate, no x_certificates fields are set."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        results = asyncio.run(mod.hunt("192.0.2.1", {}))
        services = results[0]["x_services"]
        cert_services = [s for s in services if "x_certificates" in s]
        assert len(cert_services) == 0


# ---------------------------------------------------------------------------
# HTTP request construction tests
# ---------------------------------------------------------------------------

class TestCensysHostRequestConstruction:
    """Verify the HTTP request is constructed correctly."""

    def test_request_url_uses_censys_v2_hosts_endpoint(self, mock_success):
        """GET URL uses the Censys v2 hosts endpoint."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        asyncio.run(mod.hunt("8.8.8.8", {}))
        url = mock_success.get.call_args.args[0]
        assert "search.censys.io/api/v2/hosts" in url

    def test_request_url_contains_ip(self, mock_success):
        """GET URL includes the target IP address."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        asyncio.run(mod.hunt("8.8.8.8", {}))
        url = mock_success.get.call_args.args[0]
        assert "8.8.8.8" in url

    def test_request_uses_basic_auth(self, mock_success):
        """Request uses HTTP Basic Auth with censys_id and censys_secret."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        asyncio.run(mod.hunt("8.8.8.8", {}))
        call_kwargs = mock_success.get.call_args.kwargs
        auth = call_kwargs.get("auth")
        assert auth is not None
        assert auth == ("my-id", "my-secret")


# ---------------------------------------------------------------------------
# Plugin manager integration tests
# ---------------------------------------------------------------------------

class TestCensysHostDiscovery:
    """CensysHost is discoverable via PluginManager."""

    def test_discoverable_via_plugin_manager(self):
        """PluginManager.load_plugins() finds osint/censys_host."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/censys_host")
        assert mod is not None

    def test_plugin_manager_returns_censys_instance(self):
        """get_module('osint/censys_host') returns a CensysHost instance."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/censys_host")
        assert isinstance(mod, CensysHost)

    def test_production_sequence_load_search_get_initialize(self):
        """Production sequence: load_plugins -> search('censys') -> get -> initialize."""
        mgr = PluginManager()
        mgr.load_plugins()

        results = mgr.search("censys")
        assert len(results) >= 1
        names = [r["name"] for r in results]
        assert "osint/censys_host" in names

        mod = mgr.get_module("osint/censys_host")
        assert mod is not None
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        assert mod._config["censys_id"] == "my-id"
        assert mod._config["censys_secret"] == "my-secret"
