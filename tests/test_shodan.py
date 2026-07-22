"""Tests for the Shodan OSINT module (Issue #6).

# @mock-exempt: httpx.AsyncClient is an external HTTP boundary (Shodan REST API).
# Tests must run without a real API key. Mocking the HTTP layer is the only
# way to exercise error paths (401, 429, 404) hermetically. This is Sacred Practice
# #5's explicitly-permitted exception: "Mocks are acceptable ONLY for external
# boundaries (HTTP APIs, third-party services, databases)."

Production sequence: PluginManager.load_plugins() -> get_module('osint/shodan_ip') ->
initialize({api_key}) -> hunt(ip, options). Tests cover the full sequence including
open ports, hostnames, vulnerability data (both dict and list formats for vulns),
MINIFY option, and all error paths (401, 429, 404, missing key).

@decision DEC-TEST-SHODAN-001
@title Monkeypatch httpx.AsyncClient for hermetic Shodan tests
@status accepted
@rationale respx is not in the project's dependency set. Python's unittest.mock
           (via pytest monkeypatch / patch) patches httpx.AsyncClient.__aenter__
           and provides full context-manager semantics. This matches the established
           pattern from DEC-TEST-ABUSEIPDB-001 and DEC-TEST-OTX-001 — consistent
           approach across all API modules avoids introducing new test infrastructure.

@decision DEC-TEST-SHODAN-002
@title Test both dict and list formats for the Shodan vulns field
@status accepted
@rationale Shodan documents vulns as a dict (keys are CVE IDs) but in practice
           also returns it as a list. Both formats must be handled correctly.
           Separate test fixtures exercise each code path to guarantee robustness.
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
from adversary_pursuit.modules.osint.shodan_ip import ShodanIP

# ---------------------------------------------------------------------------
# Sample API responses
# ---------------------------------------------------------------------------

SAMPLE_RESPONSE_FULL = {
    "ip_str": "1.2.3.4",
    "ports": [22, 80, 443],
    "hostnames": ["host.example.com", "mail.example.com"],
    "os": "Linux 3.x",
    "org": "Example Corp",
    "isp": "Example ISP",
    "country_code": "US",
    "vulns": {
        "CVE-2021-44228": {"cvss": 10.0, "summary": "Log4Shell"},
        "CVE-2022-0001": {"cvss": 5.5, "summary": "Some vuln"},
    },
    "last_update": "2026-04-01T00:00:00.000000",
}

SAMPLE_RESPONSE_VULNS_AS_LIST = {
    "ip_str": "5.6.7.8",
    "ports": [443],
    "hostnames": ["secure.example.org"],
    "os": None,
    "org": "Secure Corp",
    "isp": "Secure ISP",
    "country_code": "DE",
    "vulns": ["CVE-2020-1234", "CVE-2021-9999"],
    "last_update": "2026-03-15T00:00:00.000000",
}

SAMPLE_RESPONSE_NO_VULNS = {
    "ip_str": "9.10.11.12",
    "ports": [80],
    "hostnames": [],
    "os": None,
    "org": "Clean Corp",
    "isp": "Clean ISP",
    "country_code": "JP",
    "last_update": "2026-02-01T00:00:00.000000",
}

SAMPLE_RESPONSE_MINIFY = {
    "ip_str": "1.2.3.4",
    "ports": [80],
    "hostnames": [],
    "country_code": "US",
    "org": "Example Corp",
    "last_update": "2026-04-01T00:00:00.000000",
}


def _make_mock_response(
    status_code: int, body: dict | None = None, headers: dict | None = None
) -> MagicMock:
    """Build a mock httpx.Response-like object."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.headers = headers or {}
    mock_resp.json.return_value = body or {}
    if status_code >= 400:
        mock_resp.raise_for_status.return_value = None  # handled manually
    else:
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
    with patch("adversary_pursuit.modules.osint.shodan_ip.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_success_vulns_list():
    """Patch httpx.AsyncClient to return vulns as a list."""
    mock_resp = _make_mock_response(200, SAMPLE_RESPONSE_VULNS_AS_LIST)
    mock_client = _make_client_mock(mock_resp)
    with patch("adversary_pursuit.modules.osint.shodan_ip.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_success_no_vulns():
    """Patch httpx.AsyncClient to return response without vulns field."""
    mock_resp = _make_mock_response(200, SAMPLE_RESPONSE_NO_VULNS)
    mock_client = _make_client_mock(mock_resp)
    with patch("adversary_pursuit.modules.osint.shodan_ip.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_success_minify():
    """Patch httpx.AsyncClient to return the minified response."""
    mock_resp = _make_mock_response(200, SAMPLE_RESPONSE_MINIFY)
    mock_client = _make_client_mock(mock_resp)
    with patch("adversary_pursuit.modules.osint.shodan_ip.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_401():
    """Patch httpx.AsyncClient to return 401 Unauthorized."""
    mock_resp = _make_mock_response(401, {"error": "Invalid API key."})
    mock_client = _make_client_mock(mock_resp)
    with patch("adversary_pursuit.modules.osint.shodan_ip.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_429():
    """Patch httpx.AsyncClient to return 429 Too Many Requests with Retry-After."""
    mock_resp = _make_mock_response(
        429,
        {"error": "Rate limit reached."},
        headers={"Retry-After": "60"},
    )
    mock_client = _make_client_mock(mock_resp)
    with patch("adversary_pursuit.modules.osint.shodan_ip.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_429_no_retry():
    """Patch httpx.AsyncClient to return 429 without Retry-After header."""
    mock_resp = _make_mock_response(429, {"error": "Rate limit reached."}, headers={})
    mock_client = _make_client_mock(mock_resp)
    with patch("adversary_pursuit.modules.osint.shodan_ip.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_404():
    """Patch httpx.AsyncClient to return 404 Not Found."""
    mock_resp = _make_mock_response(404, {"error": "No information available for that IP."})
    mock_client = _make_client_mock(mock_resp)
    with patch("adversary_pursuit.modules.osint.shodan_ip.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


# ---------------------------------------------------------------------------
# Protocol and metadata tests
# ---------------------------------------------------------------------------

class TestShodanIPMetadata:
    """ShodanIP satisfies PursuitModule protocol and declares correct metadata."""

    def test_satisfies_protocol(self):
        """ShodanIP must satisfy PursuitModule isinstance check."""
        mod = ShodanIP()
        assert isinstance(mod, PursuitModule)

    def test_module_name(self):
        mod = ShodanIP()
        assert mod.name == "osint/shodan_ip"

    def test_module_type(self):
        mod = ShodanIP()
        assert mod.module_type == "osint"

    def test_module_author(self):
        mod = ShodanIP()
        assert mod.author == "Adversary Pursuit"

    def test_description_non_empty(self):
        mod = ShodanIP()
        assert mod.description

    def test_options_has_target(self):
        mod = ShodanIP()
        assert "TARGET" in mod.options
        assert mod.options["TARGET"]["required"] is True

    def test_options_has_minify(self):
        mod = ShodanIP()
        assert "MINIFY" in mod.options
        assert mod.options["MINIFY"]["required"] is False
        assert mod.options["MINIFY"]["default"] == "false"


# ---------------------------------------------------------------------------
# Authentication / error path tests
# ---------------------------------------------------------------------------

class TestShodanIPErrors:
    """hunt() error handling: missing key, 401, 429, 404."""

    def test_hunt_no_api_key_raises_auth_error(self):
        """hunt() without an API key must raise AuthenticationError immediately."""
        mod = ShodanIP()
        mod.initialize({})
        with pytest.raises(AuthenticationError, match="API key"):
            asyncio.run(mod.hunt("1.2.3.4", {}))

    def test_hunt_empty_api_key_raises_auth_error(self):
        """hunt() with empty string key raises AuthenticationError before HTTP."""
        mod = ShodanIP()
        mod.initialize({"api_key": ""})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("1.2.3.4", {}))

    def test_hunt_401_raises_auth_error(self, mock_401):
        """401 response from Shodan raises AuthenticationError."""
        mod = ShodanIP()
        mod.initialize({"api_key": "bad-key"})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("1.2.3.4", {}))

    def test_hunt_429_raises_rate_limit_error(self, mock_429):
        """429 response raises RateLimitError."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        with pytest.raises(RateLimitError):
            asyncio.run(mod.hunt("1.2.3.4", {}))

    def test_hunt_429_retry_after_populated(self, mock_429):
        """RateLimitError.retry_after is populated from Retry-After header."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        with pytest.raises(RateLimitError) as exc_info:
            asyncio.run(mod.hunt("1.2.3.4", {}))
        assert exc_info.value.retry_after == 60

    def test_hunt_429_no_retry_after_is_none(self, mock_429_no_retry):
        """RateLimitError.retry_after is None when header is absent."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        with pytest.raises(RateLimitError) as exc_info:
            asyncio.run(mod.hunt("1.2.3.4", {}))
        assert exc_info.value.retry_after is None

    def test_hunt_404_returns_empty_list(self, mock_404):
        """404 response returns an empty list (IP not in Shodan's index)."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results == []


# ---------------------------------------------------------------------------
# Successful hunt() result structure tests
# ---------------------------------------------------------------------------

class TestShodanIPHuntResults:
    """hunt() result structure with mocked API responses."""

    def test_hunt_returns_list(self, mock_success):
        """hunt() always returns a list."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert isinstance(results, list)

    def test_hunt_primary_result_is_ipv4_addr(self, mock_success):
        """First result is an ipv4-addr SCO."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["type"] == "ipv4-addr"

    def test_hunt_ipv4_value_matches_target(self, mock_success):
        """ipv4-addr SCO value matches the queried IP."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["value"] == "1.2.3.4"

    def test_hunt_x_ports_present(self, mock_success):
        """x_ports custom property is present and correct."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_ports"] == [22, 80, 443]

    def test_hunt_x_hostnames_present(self, mock_success):
        """x_hostnames custom property is present and correct."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_hostnames"] == ["host.example.com", "mail.example.com"]

    def test_hunt_x_os_present(self, mock_success):
        """x_os custom property is present."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_os"] == "Linux 3.x"

    def test_hunt_x_org_present(self, mock_success):
        """x_org custom property is present."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_org"] == "Example Corp"

    def test_hunt_x_isp_present(self, mock_success):
        """x_isp custom property is present."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_isp"] == "Example ISP"

    def test_hunt_x_country_code_present(self, mock_success):
        """x_country_code custom property is present."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_country_code"] == "US"

    def test_hunt_x_last_update_present(self, mock_success):
        """x_last_update custom property is present."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_last_update"] == "2026-04-01T00:00:00.000000"

    def test_hunt_x_vulns_from_dict(self, mock_success):
        """x_vulns is a list of CVE IDs extracted from a dict-format vulns field."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        vulns = results[0]["x_vulns"]
        assert isinstance(vulns, list)
        assert "CVE-2021-44228" in vulns
        assert "CVE-2022-0001" in vulns

    def test_hunt_x_vulns_from_list(self, mock_success_vulns_list):
        """x_vulns is a list of CVE IDs when vulns field is already a list."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("5.6.7.8", {}))
        vulns = results[0]["x_vulns"]
        assert isinstance(vulns, list)
        assert "CVE-2020-1234" in vulns
        assert "CVE-2021-9999" in vulns

    def test_hunt_x_vulns_empty_when_absent(self, mock_success_no_vulns):
        """x_vulns is an empty list when vulns field is absent from response."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("9.10.11.12", {}))
        assert results[0]["x_vulns"] == []

    def test_hunt_emits_domain_name_scos_for_hostnames(self, mock_success):
        """A domain-name SCO is emitted for each hostname returned by Shodan."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        domain_scos = [r for r in results if r.get("type") == "domain-name"]
        assert len(domain_scos) == 2

    def test_hunt_domain_sco_values_match_hostnames(self, mock_success):
        """domain-name SCO values match the API-returned hostnames."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        domain_values = {r["value"] for r in results if r.get("type") == "domain-name"}
        assert domain_values == {"host.example.com", "mail.example.com"}

    def test_hunt_no_hostnames_omits_domain_scos(self, mock_success_no_vulns):
        """When hostnames list is empty, no domain-name SCOs are emitted."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("9.10.11.12", {}))
        domain_scos = [r for r in results if r.get("type") == "domain-name"]
        assert len(domain_scos) == 0

    def test_hunt_total_result_count_with_hostnames(self, mock_success):
        """Full response: 1 ipv4-addr + 2 domain-name SCOs = 3 total."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert len(results) == 3

    def test_hunt_total_result_count_without_hostnames(self, mock_success_no_vulns):
        """No hostnames: exactly 1 SCO (ipv4-addr only)."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("9.10.11.12", {}))
        assert len(results) == 1


# ---------------------------------------------------------------------------
# API request construction tests
# ---------------------------------------------------------------------------

class TestShodanIPRequestConstruction:
    """Verify the HTTP request is constructed correctly."""

    def test_request_url_contains_ip(self, mock_success):
        """GET URL includes the target IP address."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("1.2.3.4", {}))
        url = mock_success.get.call_args.args[0]
        assert "1.2.3.4" in url

    def test_request_url_uses_shodan_host_endpoint(self, mock_success):
        """GET URL uses the Shodan host endpoint."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("1.2.3.4", {}))
        url = mock_success.get.call_args.args[0]
        assert "api.shodan.io/shodan/host" in url

    def test_request_params_contain_api_key(self, mock_success):
        """API key is passed as 'key' query parameter."""
        mod = ShodanIP()
        mod.initialize({"api_key": "my-shodan-key"})
        asyncio.run(mod.hunt("1.2.3.4", {}))
        params = mock_success.get.call_args.kwargs.get("params", {})
        assert params.get("key") == "my-shodan-key"

    def test_request_no_minify_by_default(self, mock_success):
        """minify param is not set (or False) when MINIFY option is 'false'."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("1.2.3.4", {}))
        params = mock_success.get.call_args.kwargs.get("params", {})
        # minify should be absent or False
        assert not params.get("minify", False)

    def test_request_minify_true_when_option_set(self, mock_success_minify):
        """minify=true is passed when MINIFY option is 'true'."""
        mod = ShodanIP()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("1.2.3.4", {"MINIFY": "true"}))
        params = mock_success_minify.get.call_args.kwargs.get("params", {})
        assert params.get("minify") is True


# ---------------------------------------------------------------------------
# Plugin manager integration tests
# ---------------------------------------------------------------------------

class TestShodanIPDiscovery:
    """ShodanIP is discoverable via PluginManager."""

    def test_discoverable_via_plugin_manager(self):
        """PluginManager.load_plugins() finds osint/shodan_ip."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/shodan_ip")
        assert mod is not None

    def test_plugin_manager_returns_shodan_instance(self):
        """get_module('osint/shodan_ip') returns a ShodanIP instance."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/shodan_ip")
        assert isinstance(mod, ShodanIP)

    def test_production_sequence_load_search_get_initialize(self):
        """Production sequence: load_plugins -> search('shodan') -> get -> initialize."""
        mgr = PluginManager()
        mgr.load_plugins()

        results = mgr.search("shodan")
        assert len(results) >= 1
        names = [r["name"] for r in results]
        assert "osint/shodan_ip" in names

        mod = mgr.get_module("osint/shodan_ip")
        assert mod is not None
        mod.initialize({"api_key": "test-key"})
        assert mod._config["api_key"] == "test-key"
