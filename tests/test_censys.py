"""Tests for the Censys Host OSINT module.

# @mock-exempt: httpx.AsyncClient is an external HTTP boundary (Censys REST API).
# Tests must run without real API credentials. Mocking the HTTP layer is the only
# way to exercise error paths (401, 403, 404, 429) hermetically. This is Sacred
# Practice #5's explicitly-permitted exception: "Mocks are acceptable ONLY for
# external boundaries (HTTP APIs, third-party services, databases)."

Production sequence: PluginManager.load_plugins() -> get_module('osint/censys_host') ->
initialize({censys_pat}) -> hunt(ip, options). Tests cover the full
sequence including services, certificates, OS, location, autonomous system data,
and all error paths (missing creds, legacy creds migration error, 401, 403, 404, 429).

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
@title Censys uses Bearer PAT (censys_pat), not Basic Auth censys_id:censys_secret
@status accepted (updated from original to reflect DEC-MODULE-CENSYS-005 migration)
@rationale Censys Platform API v3 authenticates via Bearer Personal Access Token.
           Tests verify the PAT is required (legacy id/secret triggers a migration
           error), and that the httpx Authorization header carries the Bearer token.
           The redirect chain regression test mocks the actual observed failure:
           search.censys.io/api/v2 returning 302 with no Location header.

@decision DEC-TEST-CENSYS-003
@title v3 response envelope: result.resource wraps host data; service fields renamed
@status accepted
@rationale Censys v3 wraps the host object under {"result": {"resource": {...}}}.
           Service field names differ from v2: "protocol" is the service name (HTTP,
           SSH), "transport_protocol" is TCP/UDP. Certificates are nested as
           cert.fingerprint_sha256. Tests use sample responses matching this schema.
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adversary_pursuit.core.plugin_mgr import PluginManager
from adversary_pursuit.modules.base import (
    AuthenticationError,
    PursuitModule,
    RateLimitError,
)
from adversary_pursuit.modules.osint.censys_host import CensysHost

# ---------------------------------------------------------------------------
# Sample API responses (v3 Platform API format)
# ---------------------------------------------------------------------------

# Full v3 response with services, certificates, OS, location, autonomous_system.
# Envelope: {"result": {"resource": {...}, "extensions": {...}}}
SAMPLE_RESPONSE_FULL = {
    "result": {
        "resource": {
            "ip": "8.8.8.8",
            "services": [
                {
                    "port": 53,
                    "transport_protocol": "UDP",
                    "protocol": "DNS",
                    "cert": None,
                },
                {
                    "port": 443,
                    "transport_protocol": "TCP",
                    "protocol": "HTTPS",
                    "cert": {"fingerprint_sha256": "abc123def456"},
                },
                {
                    "port": 80,
                    "transport_protocol": "TCP",
                    "protocol": "HTTP",
                    "cert": None,
                },
            ],
            "operating_system": {
                "value": "Linux",
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
        },
        "extensions": {},
    }
}

# Response with multiple services having certificates
SAMPLE_RESPONSE_MULTI_CERTS = {
    "result": {
        "resource": {
            "ip": "1.2.3.4",
            "services": [
                {
                    "port": 443,
                    "transport_protocol": "TCP",
                    "protocol": "HTTPS",
                    "cert": {"fingerprint_sha256": "cert1111"},
                },
                {
                    "port": 8443,
                    "transport_protocol": "TCP",
                    "protocol": "HTTPS",
                    "cert": {"fingerprint_sha256": "cert2222"},
                },
                {
                    "port": 22,
                    "transport_protocol": "TCP",
                    "protocol": "SSH",
                    "cert": None,
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
        },
        "extensions": {},
    }
}

# Minimal response — no OS, no certificates on any service
SAMPLE_RESPONSE_MINIMAL = {
    "result": {
        "resource": {
            "ip": "192.0.2.1",
            "services": [
                {
                    "port": 80,
                    "transport_protocol": "TCP",
                    "protocol": "HTTP",
                    "cert": None,
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
        },
        "extensions": {},
    }
}

# Response with no services at all
SAMPLE_RESPONSE_NO_SERVICES = {
    "result": {
        "resource": {
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
        },
        "extensions": {},
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
    with patch(
        "adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient", return_value=mock_client
    ):
        yield mock_client


@pytest.fixture
def mock_success_multi_certs():
    """Patch httpx.AsyncClient to return response with multiple certificate services."""
    mock_resp = _make_mock_response(200, SAMPLE_RESPONSE_MULTI_CERTS)
    mock_client = _make_client_mock(mock_resp)
    with patch(
        "adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient", return_value=mock_client
    ):
        yield mock_client


@pytest.fixture
def mock_success_minimal():
    """Patch httpx.AsyncClient to return a minimal response (no OS, no certs)."""
    mock_resp = _make_mock_response(200, SAMPLE_RESPONSE_MINIMAL)
    mock_client = _make_client_mock(mock_resp)
    with patch(
        "adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient", return_value=mock_client
    ):
        yield mock_client


@pytest.fixture
def mock_success_no_services():
    """Patch httpx.AsyncClient to return a response with empty services list."""
    mock_resp = _make_mock_response(200, SAMPLE_RESPONSE_NO_SERVICES)
    mock_client = _make_client_mock(mock_resp)
    with patch(
        "adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient", return_value=mock_client
    ):
        yield mock_client


@pytest.fixture
def mock_401():
    """Patch httpx.AsyncClient to return 401 Unauthorized."""
    mock_resp = _make_mock_response(
        401,
        {
            "error": {
                "code": 401,
                "status": "Unauthorized",
                "message": "Access credentials are invalid.",
            }
        },
    )
    mock_client = _make_client_mock(mock_resp)
    with patch(
        "adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient", return_value=mock_client
    ):
        yield mock_client


@pytest.fixture
def mock_403():
    """Patch httpx.AsyncClient to return 403 Forbidden (plan restriction)."""
    mock_resp = _make_mock_response(
        403,
        {
            "error": {
                "code": 403,
                "status": "Forbidden",
                "message": "Forbidden. Your account does not have access to this endpoint.",
            }
        },
    )
    mock_client = _make_client_mock(mock_resp)
    with patch(
        "adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient", return_value=mock_client
    ):
        yield mock_client


@pytest.fixture
def mock_404():
    """Patch httpx.AsyncClient to return 404 Not Found (IP not in index)."""
    mock_resp = _make_mock_response(
        404, {"error": {"code": 404, "status": "Not Found", "message": "Not Found"}}
    )
    mock_client = _make_client_mock(mock_resp)
    with patch(
        "adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient", return_value=mock_client
    ):
        yield mock_client


@pytest.fixture
def mock_429():
    """Patch httpx.AsyncClient to return 429 with Retry-After header."""
    mock_resp = _make_mock_response(
        429,
        {"error": {"code": 429, "status": "Too Many Requests", "message": "Rate limit exceeded."}},
        headers={"Retry-After": "60"},
    )
    mock_client = _make_client_mock(mock_resp)
    with patch(
        "adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient", return_value=mock_client
    ):
        yield mock_client


@pytest.fixture
def mock_429_no_retry():
    """Patch httpx.AsyncClient to return 429 without Retry-After header."""
    mock_resp = _make_mock_response(
        429,
        {"error": {"code": 429, "status": "Too Many Requests", "message": "Rate limit exceeded."}},
        headers={},
    )
    mock_client = _make_client_mock(mock_resp)
    with patch(
        "adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient", return_value=mock_client
    ):
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
    """hunt() error handling: missing creds, legacy creds, 401, 403, 404, 429."""

    def test_hunt_no_censys_pat_raises_auth_error(self):
        """hunt() without censys_pat raises AuthenticationError immediately."""
        mod = CensysHost()
        mod.initialize({})
        with pytest.raises(AuthenticationError, match="censys_pat"):
            asyncio.run(mod.hunt("8.8.8.8", {}))

    def test_hunt_empty_censys_pat_raises_auth_error(self):
        """hunt() with empty censys_pat raises AuthenticationError."""
        mod = CensysHost()
        mod.initialize({"censys_pat": ""})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("8.8.8.8", {}))

    def test_hunt_legacy_credentials_raises_migration_error(self):
        """hunt() with legacy censys_id+censys_secret raises AuthenticationError with migration message."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        with pytest.raises(AuthenticationError, match="migrated"):
            asyncio.run(mod.hunt("8.8.8.8", {}))

    def test_hunt_legacy_credentials_migration_message_mentions_pat(self):
        """Migration error message references the new censys_pat config key."""
        mod = CensysHost()
        mod.initialize({"censys_id": "my-id", "censys_secret": "my-secret"})
        with pytest.raises(AuthenticationError, match="censys_pat"):
            asyncio.run(mod.hunt("8.8.8.8", {}))

    def test_hunt_pat_from_env_var(self):
        """hunt() reads censys_pat from AP_CENSYS_PAT env var."""
        mock_resp = _make_mock_response(200, SAMPLE_RESPONSE_FULL)
        mock_client = _make_client_mock(mock_resp)
        with patch(
            "adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient",
            return_value=mock_client,
        ):
            mod = CensysHost()
            mod.initialize({})  # no censys_pat in config
            with patch.dict(os.environ, {"AP_CENSYS_PAT": "env-pat-token"}):
                results = asyncio.run(mod.hunt("8.8.8.8", {}))
            assert len(results) == 1
            assert results[0]["type"] == "ipv4-addr"

    def test_hunt_pat_from_censys_pat_env_var(self):
        """hunt() reads censys_pat from CENSYS_PAT env var as fallback."""
        mock_resp = _make_mock_response(200, SAMPLE_RESPONSE_FULL)
        mock_client = _make_client_mock(mock_resp)
        with patch(
            "adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient",
            return_value=mock_client,
        ):
            mod = CensysHost()
            mod.initialize({})
            # Ensure AP_CENSYS_PAT is not set so fallback to CENSYS_PAT is tested
            env = {k: v for k, v in os.environ.items() if k != "AP_CENSYS_PAT"}
            env["CENSYS_PAT"] = "vendor-env-pat"
            with patch.dict(os.environ, env, clear=True):
                results = asyncio.run(mod.hunt("8.8.8.8", {}))
            assert len(results) == 1

    def test_hunt_401_raises_auth_error(self, mock_401):
        """401 response raises AuthenticationError."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("8.8.8.8", {}))

    def test_hunt_403_raises_auth_error(self, mock_403):
        """403 response raises AuthenticationError (plan restriction)."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("8.8.8.8", {}))

    def test_hunt_404_returns_empty_list(self, mock_404):
        """404 response returns empty list (IP not in Censys index)."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("192.0.2.99", {}))
        assert results == []

    def test_hunt_429_raises_rate_limit_error(self, mock_429):
        """429 response raises RateLimitError."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        with pytest.raises(RateLimitError):
            asyncio.run(mod.hunt("8.8.8.8", {}))

    def test_hunt_429_retry_after_populated(self, mock_429):
        """RateLimitError.retry_after is populated from Retry-After header."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        with pytest.raises(RateLimitError) as exc_info:
            asyncio.run(mod.hunt("8.8.8.8", {}))
        assert exc_info.value.retry_after == 60

    def test_hunt_429_no_retry_after_is_none(self, mock_429_no_retry):
        """RateLimitError.retry_after is None when header is absent."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
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
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert isinstance(results, list)

    def test_hunt_primary_result_is_ipv4_addr(self, mock_success):
        """First result is an ipv4-addr SCO."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert results[0]["type"] == "ipv4-addr"

    def test_hunt_ipv4_value_matches_target(self, mock_success):
        """ipv4-addr SCO value matches the queried IP."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert results[0]["value"] == "8.8.8.8"

    def test_hunt_x_services_present(self, mock_success):
        """x_services custom property is present and is a list."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert "x_services" in results[0]
        assert isinstance(results[0]["x_services"], list)

    def test_hunt_x_services_count(self, mock_success):
        """x_services has 3 entries matching the sample response."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert len(results[0]["x_services"]) == 3

    def test_hunt_x_services_structure(self, mock_success):
        """Each x_services entry has port, protocol, and service_name."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        for svc in results[0]["x_services"]:
            assert "port" in svc
            assert "protocol" in svc
            assert "service_name" in svc

    def test_hunt_x_services_values(self, mock_success):
        """x_services entries have correct port values."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        services = results[0]["x_services"]
        ports = {s["port"] for s in services}
        assert 53 in ports
        assert 443 in ports
        assert 80 in ports

    def test_hunt_x_services_service_name_from_protocol_field(self, mock_success):
        """service_name is populated from v3 'protocol' field (not 'service_name')."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        services = results[0]["x_services"]
        https_svc = next(s for s in services if s["port"] == 443)
        assert https_svc["service_name"] == "HTTPS"

    def test_hunt_x_services_protocol_from_transport_protocol_field(self, mock_success):
        """protocol is populated from v3 'transport_protocol' field (TCP/UDP)."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        services = results[0]["x_services"]
        dns_svc = next(s for s in services if s["port"] == 53)
        assert dns_svc["protocol"] == "UDP"

    def test_hunt_x_os_present(self, mock_success):
        """x_os custom property is present."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert "x_os" in results[0]
        assert results[0]["x_os"] == "Linux"

    def test_hunt_x_os_empty_when_none(self, mock_success_minimal):
        """x_os is empty string when operating_system is None in response."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("192.0.2.1", {}))
        assert results[0]["x_os"] == ""

    def test_hunt_x_location_country_present(self, mock_success):
        """x_location_country custom property is present."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert "x_location_country" in results[0]
        assert results[0]["x_location_country"] == "United States"

    def test_hunt_x_autonomous_system_present(self, mock_success):
        """x_autonomous_system custom property is present."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert "x_autonomous_system" in results[0]

    def test_hunt_x_autonomous_system_structure(self, mock_success):
        """x_autonomous_system has asn and name fields."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        asn = results[0]["x_autonomous_system"]
        assert asn["asn"] == 15169
        assert asn["name"] == "GOOGLE"

    def test_hunt_x_last_updated_present(self, mock_success):
        """x_last_updated custom property is present (may be empty in v3)."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert "x_last_updated" in results[0]

    def test_hunt_x_certificates_on_service_with_cert(self, mock_success):
        """Services with a certificate include x_certificates field."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        services = results[0]["x_services"]
        https_service = next(s for s in services if s["port"] == 443)
        assert "x_certificates" in https_service
        assert https_service["x_certificates"] == "abc123def456"

    def test_hunt_no_x_certificates_on_service_without_cert(self, mock_success):
        """Services without a certificate do not include x_certificates field."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        services = results[0]["x_services"]
        dns_service = next(s for s in services if s["port"] == 53)
        assert "x_certificates" not in dns_service

    def test_hunt_x_services_empty_when_no_services(self, mock_success_no_services):
        """x_services is an empty list when response has no services."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("10.0.0.1", {}))
        assert results[0]["x_services"] == []

    def test_hunt_multiple_certificates(self, mock_success_multi_certs):
        """Multiple services with certificates each get x_certificates."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        services = results[0]["x_services"]
        cert_services = [s for s in services if "x_certificates" in s]
        assert len(cert_services) == 2
        cert_values = {s["x_certificates"] for s in cert_services}
        assert "cert1111" in cert_values
        assert "cert2222" in cert_values

    def test_hunt_no_certificates_when_all_services_lack_certs(self, mock_success_minimal):
        """When no service has a certificate, no x_certificates fields are set."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        results = asyncio.run(mod.hunt("192.0.2.1", {}))
        services = results[0]["x_services"]
        cert_services = [s for s in services if "x_certificates" in s]
        assert len(cert_services) == 0


# ---------------------------------------------------------------------------
# HTTP request construction tests
# ---------------------------------------------------------------------------


class TestCensysHostRequestConstruction:
    """Verify the HTTP request is constructed correctly for the v3 Platform API."""

    def test_request_url_uses_platform_api_host(self, mock_success):
        """GET URL uses the Censys Platform API host (api.platform.censys.io)."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        asyncio.run(mod.hunt("8.8.8.8", {}))
        url = mock_success.get.call_args.args[0]
        assert "api.platform.censys.io" in url

    def test_request_url_uses_v3_host_path(self, mock_success):
        """GET URL uses the /v3/global/asset/host/{ip} path."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        asyncio.run(mod.hunt("8.8.8.8", {}))
        url = mock_success.get.call_args.args[0]
        assert "/v3/global/asset/host/" in url

    def test_request_url_contains_ip(self, mock_success):
        """GET URL includes the target IP address."""
        mod = CensysHost()
        mod.initialize({"censys_pat": "valid-pat"})
        asyncio.run(mod.hunt("8.8.8.8", {}))
        url = mock_success.get.call_args.args[0]
        assert "8.8.8.8" in url

    def test_request_uses_bearer_auth_header(self):
        """AsyncClient is constructed with Authorization: Bearer header (not Basic auth)."""
        mock_resp = _make_mock_response(200, SAMPLE_RESPONSE_FULL)
        mock_client = _make_client_mock(mock_resp)
        with patch(
            "adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient",
        ) as mock_cls:
            mock_cls.return_value = mock_client
            mod = CensysHost()
            mod.initialize({"censys_pat": "my-test-pat"})
            asyncio.run(mod.hunt("8.8.8.8", {}))

            _, kwargs = mock_cls.call_args
            headers = kwargs.get("headers", {})
            assert "Authorization" in headers
            assert headers["Authorization"] == "Bearer my-test-pat"

    def test_request_does_not_use_basic_auth(self):
        """AsyncClient is NOT constructed with auth= param (no Basic auth)."""
        mock_resp = _make_mock_response(200, SAMPLE_RESPONSE_FULL)
        mock_client = _make_client_mock(mock_resp)
        with patch(
            "adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient",
        ) as mock_cls:
            mock_cls.return_value = mock_client
            mod = CensysHost()
            mod.initialize({"censys_pat": "my-test-pat"})
            asyncio.run(mod.hunt("8.8.8.8", {}))

            _, kwargs = mock_cls.call_args
            assert "auth" not in kwargs, "Should not use auth= param; Bearer header is used instead"


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
        mod.initialize({"censys_pat": "my-pat"})
        assert mod._config["censys_pat"] == "my-pat"


# ---------------------------------------------------------------------------
# Regression tests: Censys 302 redirect chain (issue #43)
# ---------------------------------------------------------------------------


class TestCensysHostRedirectRegression:
    """Regression tests for issue #43: Censys 302 redirect.

    Root cause analysis:
      The search.censys.io/api/v2 endpoint returns HTTP 302 with NO Location
      header. httpx's follow_redirects=True cannot follow a redirect without a
      Location header, so the 302 response is returned as-is. Then
      raise_for_status() raises HTTPStatusError('Redirect response 302 Found')
      because httpx raises for all non-2xx status codes including 3xx.

    Fix applied (DEC-MODULE-CENSYS-005):
      Migrate to the Censys Platform API v3 (https://api.platform.censys.io/
      v3/global/asset/host/{ip}) with Bearer PAT authentication. The new
      endpoint returns 200 directly, avoiding the redirect chain entirely.

    Observed redirect chain:
      GET https://search.censys.io/api/v2/hosts/8.8.8.8
        → 302 Found (no Location header)
        → httpx returns 302 response; raise_for_status() raises HTTPStatusError
      GET https://api.platform.censys.io/v3/global/asset/host/8.8.8.8
        → 200 OK (with Bearer PAT)

    Production sequence: hunt() -> httpx.AsyncClient(Bearer) ->
      GET /v3/global/asset/host/{ip} -> 200 -> parse result.resource.
    """

    def test_uses_platform_api_not_search_api(self):
        """hunt() calls api.platform.censys.io, not the deprecated search.censys.io."""
        mock_resp = _make_mock_response(200, SAMPLE_RESPONSE_FULL)
        mock_client = _make_client_mock(mock_resp)
        with patch(
            "adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient",
            return_value=mock_client,
        ):
            mod = CensysHost()
            mod.initialize({"censys_pat": "valid-pat"})
            asyncio.run(mod.hunt("8.8.8.8", {}))
            url = mock_client.get.call_args.args[0]
            assert "search.censys.io" not in url, (
                "Must not call search.censys.io (deprecated, returns 302 with no Location)"
            )
            assert "api.platform.censys.io" in url

    def test_legacy_creds_raise_migration_error_not_302(self):
        """hunt() with legacy credentials raises AuthenticationError, not a 302/network error.

        This is the exact production failure mode from issue #43: the old module
        called search.censys.io with Basic auth, got 302, then raise_for_status()
        raised HTTPStatusError. Now the module detects legacy credentials before
        making any HTTP request and raises a clear AuthenticationError with
        migration instructions.
        """
        mod = CensysHost()
        mod.initialize({"censys_id": "legacy-id", "censys_secret": "legacy-secret"})
        with pytest.raises(AuthenticationError) as exc_info:
            asyncio.run(mod.hunt("8.8.8.8", {}))
        # The error must be our AuthenticationError (a domain error), not an
        # httpx.HTTPStatusError wrapping the raw 302 network response.
        # AuthenticationError is not httpx.HTTPStatusError:
        import httpx as _httpx

        assert not isinstance(exc_info.value, _httpx.HTTPStatusError), (
            "Must be AuthenticationError, not an httpx.HTTPStatusError 302"
        )
        # Message must reference migration, not raw HTTP status text
        assert (
            "migrated" in str(exc_info.value).lower() or "platform" in str(exc_info.value).lower()
        )

    def test_hunt_parses_v3_envelope_result_resource(self):
        """hunt() correctly unpacks result.resource from v3 response envelope.

        v3 response: {"result": {"resource": {...host...}, "extensions": {}}}
        v2 response was: {"result": {...host...}}
        This test verifies the v3 envelope unpacking so a regression to v2 parsing
        would immediately fail with missing data in the SCO.
        """
        # Wrap the same host data in the v3 envelope
        v3_response = SAMPLE_RESPONSE_FULL.copy()
        mock_resp = _make_mock_response(200, v3_response)
        mock_client = _make_client_mock(mock_resp)
        with patch(
            "adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient",
            return_value=mock_client,
        ):
            mod = CensysHost()
            mod.initialize({"censys_pat": "valid-pat"})
            results = asyncio.run(mod.hunt("8.8.8.8", {}))

        assert len(results) == 1
        sco = results[0]
        assert sco["type"] == "ipv4-addr"
        assert sco["value"] == "8.8.8.8"
        # Services must be populated (not empty — that would indicate v3 envelope mis-parse)
        assert len(sco["x_services"]) == 3
        assert sco["x_os"] == "Linux"
        assert sco["x_location_country"] == "United States"
        assert sco["x_autonomous_system"]["asn"] == 15169

    def test_hunt_end_to_end_production_sequence(self):
        """End-to-end production sequence: PluginManager -> initialize -> hunt.

        Exercises the real production sequence crossing multiple component
        boundaries: plugin discovery -> config initialization -> HTTP client
        construction -> response parsing -> SCO construction.

        Compound-interaction requirement: this test crosses PluginManager
        (plugin discovery), BaseModule (initialize/config), CensysHost (hunt),
        httpx.AsyncClient (HTTP boundary mock), and _build_results (parsing).
        """
        mock_resp = _make_mock_response(200, SAMPLE_RESPONSE_FULL)
        mock_client = _make_client_mock(mock_resp)

        with patch(
            "adversary_pursuit.modules.osint.censys_host.httpx.AsyncClient",
            return_value=mock_client,
        ):
            # Step 1: Discover module via PluginManager (production entry point)
            mgr = PluginManager()
            mgr.load_plugins()
            mod = mgr.get_module("osint/censys_host")
            assert mod is not None

            # Step 2: Initialize with PAT credentials (as CLI/agent would)
            mod.initialize({"censys_pat": "production-pat-token"})

            # Step 3: Execute hunt
            results = asyncio.run(mod.hunt("8.8.8.8", {}))

        # Step 4: Verify full SCO output
        assert len(results) == 1
        sco = results[0]
        assert sco["type"] == "ipv4-addr"
        assert sco["value"] == "8.8.8.8"
        assert len(sco["x_services"]) == 3
        assert sco["x_os"] == "Linux"
        assert sco["x_location_country"] == "United States"
        asn = sco["x_autonomous_system"]
        assert asn["asn"] == 15169
        assert asn["name"] == "GOOGLE"
        assert asn["bgp_prefix"] == "8.8.8.0/24"

        # Step 5: Verify HTTP call was to Platform API with Bearer auth
        call_url = mock_client.get.call_args.args[0]
        assert "api.platform.censys.io/v3/global/asset/host/8.8.8.8" in call_url
