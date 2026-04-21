"""Tests for the AbuseIPDB OSINT module (Issue #10).

# @mock-exempt: httpx.AsyncClient is an external HTTP boundary (AbuseIPDB REST API).
# Tests must run without a real API key. Mocking the HTTP layer is the only
# way to exercise error paths (401, 429) hermetically. This is Sacred Practice
# #5's explicitly-permitted exception: "Mocks are acceptable ONLY for external
# boundaries (HTTP APIs, third-party services, databases)."

Production sequence: PluginManager.load_plugins() -> get_module() ->
initialize({api_key}) -> hunt(ip, options). Tests cover the full sequence
plus error paths (401, 429, missing key) and optional domain SCO output.

@decision DEC-TEST-ABUSEIPDB-001
@title Monkeypatch httpx.AsyncClient for hermetic tests
@status accepted
@rationale respx is not in the project's dependency set and adding it for
           one test file is unnecessary overhead. Python's unittest.mock
           (via pytest monkeypatch) patches the same interface and keeps
           the test suite self-contained. VCR cassettes would need initial
           recording with a live key — acceptable for future enrichment but
           not a day-1 requirement.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adversary_pursuit.modules.base import (
    AuthenticationError,
    PursuitModule,
    RateLimitError,
)
from adversary_pursuit.modules.osint.abuseipdb import AbuseIPDB
from adversary_pursuit.core.plugin_mgr import PluginManager


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_RESPONSE_DATA = {
    "data": {
        "ipAddress": "1.2.3.4",
        "isPublic": True,
        "abuseConfidenceScore": 75,
        "countryCode": "US",
        "usageType": "Data Center/Web Hosting/Transit",
        "isp": "Example ISP",
        "domain": "example.com",
        "totalReports": 42,
        "numDistinctUsers": 15,
        "lastReportedAt": "2026-04-01T12:00:00+00:00",
        "isWhitelisted": False,
    }
}

SAMPLE_RESPONSE_NO_DOMAIN = {
    "data": {
        "ipAddress": "5.6.7.8",
        "isPublic": True,
        "abuseConfidenceScore": 0,
        "countryCode": "DE",
        "usageType": "Fixed Line ISP",
        "isp": "German ISP",
        "domain": "",
        "totalReports": 0,
        "numDistinctUsers": 0,
        "lastReportedAt": "",
        "isWhitelisted": False,
    }
}


def _make_mock_response(status_code: int, body: dict, headers: dict | None = None) -> MagicMock:
    """Build a mock httpx.Response-like object."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.headers = headers or {}
    mock_resp.json.return_value = body
    if status_code >= 400:
        from httpx import HTTPStatusError, Request, Response
        # raise_for_status raises on 4xx/5xx
        mock_resp.raise_for_status.side_effect = None  # we handle 401/429 manually
    else:
        mock_resp.raise_for_status.return_value = None
    return mock_resp


@pytest.fixture
def mock_success():
    """Patch httpx.AsyncClient to return the standard success response."""
    mock_resp = _make_mock_response(200, SAMPLE_RESPONSE_DATA)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("adversary_pursuit.modules.osint.abuseipdb.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_success_no_domain():
    """Patch httpx.AsyncClient to return success response without domain."""
    mock_resp = _make_mock_response(200, SAMPLE_RESPONSE_NO_DOMAIN)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("adversary_pursuit.modules.osint.abuseipdb.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_401():
    """Patch httpx.AsyncClient to return a 401 Unauthorized."""
    mock_resp = _make_mock_response(401, {"errors": [{"detail": "Authentication failed."}]})
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("adversary_pursuit.modules.osint.abuseipdb.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_429():
    """Patch httpx.AsyncClient to return a 429 Too Many Requests."""
    mock_resp = _make_mock_response(
        429,
        {"errors": [{"detail": "Daily rate limit of 1000 requests exceeded."}]},
        headers={"Retry-After": "3600"},
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("adversary_pursuit.modules.osint.abuseipdb.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_429_no_retry_after():
    """Patch httpx.AsyncClient to return 429 without Retry-After header."""
    mock_resp = _make_mock_response(
        429,
        {"errors": [{"detail": "Rate limit exceeded."}]},
        headers={},
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("adversary_pursuit.modules.osint.abuseipdb.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


# ---------------------------------------------------------------------------
# Protocol and metadata tests
# ---------------------------------------------------------------------------

class TestAbuseIPDBMetadata:
    """Module satisfies PursuitModule protocol and declares correct metadata."""

    def test_satisfies_protocol(self):
        """AbuseIPDB must satisfy PursuitModule isinstance check."""
        mod = AbuseIPDB()
        assert isinstance(mod, PursuitModule)

    def test_module_name(self):
        mod = AbuseIPDB()
        assert mod.name == "osint/abuseipdb"

    def test_module_type(self):
        mod = AbuseIPDB()
        assert mod.module_type == "osint"

    def test_module_author(self):
        mod = AbuseIPDB()
        assert mod.author == "Adversary Pursuit"

    def test_description_non_empty(self):
        mod = AbuseIPDB()
        assert mod.description

    def test_options_has_target(self):
        mod = AbuseIPDB()
        assert "TARGET" in mod.options
        assert mod.options["TARGET"]["required"] is True

    def test_options_has_max_age(self):
        mod = AbuseIPDB()
        assert "MAX_AGE" in mod.options
        assert mod.options["MAX_AGE"]["required"] is False
        assert mod.options["MAX_AGE"]["default"] == "90"

    def test_options_has_verbose(self):
        mod = AbuseIPDB()
        assert "VERBOSE" in mod.options
        assert mod.options["VERBOSE"]["required"] is False
        assert mod.options["VERBOSE"]["default"] == "false"


# ---------------------------------------------------------------------------
# Authentication / error path tests
# ---------------------------------------------------------------------------

class TestAbuseIPDBErrors:
    """hunt() error handling: missing key, 401, 429."""

    def test_hunt_no_api_key_raises_auth_error(self):
        """hunt() without an API key must raise AuthenticationError immediately."""
        mod = AbuseIPDB()
        mod.initialize({})
        with pytest.raises(AuthenticationError, match="API key"):
            asyncio.run(mod.hunt("1.2.3.4", {}))

    def test_hunt_empty_api_key_raises_auth_error(self):
        """hunt() with empty string API key raises AuthenticationError."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": ""})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("1.2.3.4", {}))

    def test_hunt_401_raises_auth_error(self, mock_401):
        """401 response raises AuthenticationError."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "bad-key"})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("1.2.3.4", {}))

    def test_hunt_429_raises_rate_limit_error(self, mock_429):
        """429 response raises RateLimitError."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        with pytest.raises(RateLimitError):
            asyncio.run(mod.hunt("1.2.3.4", {}))

    def test_hunt_429_retry_after_is_set(self, mock_429):
        """RateLimitError.retry_after is populated from Retry-After header."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        with pytest.raises(RateLimitError) as exc_info:
            asyncio.run(mod.hunt("1.2.3.4", {}))
        assert exc_info.value.retry_after == 3600

    def test_hunt_429_no_retry_after_is_none(self, mock_429_no_retry_after):
        """RateLimitError.retry_after is None when header is absent."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        with pytest.raises(RateLimitError) as exc_info:
            asyncio.run(mod.hunt("1.2.3.4", {}))
        assert exc_info.value.retry_after is None


# ---------------------------------------------------------------------------
# Successful hunt() result tests
# ---------------------------------------------------------------------------

class TestAbuseIPDBHuntResults:
    """hunt() result structure with mocked API responses."""

    def test_hunt_returns_list(self, mock_success):
        """hunt() returns a list."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert isinstance(results, list)

    def test_hunt_primary_result_is_ipv4_addr(self, mock_success):
        """First result is an ipv4-addr SCO."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["type"] == "ipv4-addr"

    def test_hunt_primary_result_value(self, mock_success):
        """ipv4-addr SCO value matches the queried IP."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["value"] == "1.2.3.4"

    def test_hunt_abuse_score_present(self, mock_success):
        """x_abuse_confidence_score is present and correct."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert "x_abuse_confidence_score" in results[0]
        assert results[0]["x_abuse_confidence_score"] == 75

    def test_hunt_isp_present(self, mock_success):
        """x_isp custom property is present."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_isp"] == "Example ISP"

    def test_hunt_usage_type_present(self, mock_success):
        """x_usage_type custom property is present."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_usage_type"] == "Data Center/Web Hosting/Transit"

    def test_hunt_total_reports_present(self, mock_success):
        """x_total_reports custom property is present."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_total_reports"] == 42

    def test_hunt_country_code_present(self, mock_success):
        """x_country_code custom property is present."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_country_code"] == "US"

    def test_hunt_includes_domain_sco(self, mock_success):
        """When API returns a domain, a domain-name SCO is appended."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        domain_results = [r for r in results if r.get("type") == "domain-name"]
        assert len(domain_results) == 1
        assert domain_results[0]["value"] == "example.com"

    def test_hunt_no_domain_omits_domain_sco(self, mock_success_no_domain):
        """When API returns empty domain, no domain-name SCO is added."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("5.6.7.8", {}))
        domain_results = [r for r in results if r.get("type") == "domain-name"]
        assert len(domain_results) == 0

    def test_hunt_result_count_with_domain(self, mock_success):
        """With domain present, hunt() returns 2 SCOs (ipv4-addr + domain-name)."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert len(results) == 2

    def test_hunt_result_count_without_domain(self, mock_success_no_domain):
        """Without domain, hunt() returns exactly 1 SCO."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("5.6.7.8", {}))
        assert len(results) == 1

    def test_hunt_api_request_uses_correct_headers(self, mock_success):
        """httpx GET is called with Key header and Accept: application/json."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "my-secret-key"})
        asyncio.run(mod.hunt("1.2.3.4", {}))
        call_kwargs = mock_success.get.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers.get("Key") == "my-secret-key"
        assert headers.get("Accept") == "application/json"

    def test_hunt_api_request_uses_correct_url(self, mock_success):
        """httpx GET is called with the AbuseIPDB v2 check endpoint."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("1.2.3.4", {}))
        url = mock_success.get.call_args.args[0]
        assert "abuseipdb.com/api/v2/check" in url

    def test_hunt_passes_ip_as_param(self, mock_success):
        """ipAddress parameter is forwarded to the API call."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("1.2.3.4", {}))
        params = mock_success.get.call_args.kwargs.get("params", {})
        assert params.get("ipAddress") == "1.2.3.4"

    def test_hunt_default_max_age_is_90(self, mock_success):
        """maxAgeInDays defaults to 90 when MAX_AGE option is not set."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("1.2.3.4", {}))
        params = mock_success.get.call_args.kwargs.get("params", {})
        assert params.get("maxAgeInDays") == 90

    def test_hunt_custom_max_age(self, mock_success):
        """MAX_AGE option overrides the default maxAgeInDays parameter."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("1.2.3.4", {"MAX_AGE": "30"}))
        params = mock_success.get.call_args.kwargs.get("params", {})
        assert params.get("maxAgeInDays") == 30

    def test_hunt_verbose_false_by_default(self, mock_success):
        """verbose param defaults to 'no' when VERBOSE option is not set."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("1.2.3.4", {}))
        params = mock_success.get.call_args.kwargs.get("params", {})
        assert params.get("verbose") == "no"

    def test_hunt_verbose_enabled(self, mock_success):
        """VERBOSE=true sets verbose param to 'yes'."""
        mod = AbuseIPDB()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("1.2.3.4", {"VERBOSE": "true"}))
        params = mock_success.get.call_args.kwargs.get("params", {})
        assert params.get("verbose") == "yes"


# ---------------------------------------------------------------------------
# Plugin manager integration test
# ---------------------------------------------------------------------------

class TestAbuseIPDBDiscovery:
    """AbuseIPDB is discoverable via PluginManager."""

    def test_discoverable_via_plugin_manager(self):
        """PluginManager.load_plugins() finds osint/abuseipdb."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/abuseipdb")
        assert mod is not None

    def test_plugin_manager_returns_abuseipdb_instance(self):
        """get_module('osint/abuseipdb') returns an AbuseIPDB instance."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/abuseipdb")
        assert isinstance(mod, AbuseIPDB)

    def test_production_sequence_load_search_get_initialize(self):
        """Production sequence: load_plugins -> search('abuseipdb') -> get -> initialize."""
        mgr = PluginManager()
        mgr.load_plugins()

        results = mgr.search("abuseipdb")
        assert len(results) >= 1
        names = [r["name"] for r in results]
        assert "osint/abuseipdb" in names

        mod = mgr.get_module("osint/abuseipdb")
        assert mod is not None
        mod.initialize({"api_key": "test-key"})
        assert mod._config["api_key"] == "test-key"
