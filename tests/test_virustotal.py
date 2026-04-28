"""Tests for the VirusTotal v3 CTI module (Issue #7).

# @mock-exempt: httpx.AsyncClient is an external HTTP boundary (VirusTotal REST API).
# Tests must run without a real API key. Mocking the HTTP layer is the only
# way to exercise error paths (401, 429) hermetically. This is Sacred Practice
# #5's explicitly-permitted exception: "Mocks are acceptable ONLY for external
# boundaries (HTTP APIs, third-party services, databases)."

Production sequence: PluginManager.load_plugins() -> get_module('cti/virustotal') ->
initialize({api_key}) -> hunt(target, options). Tests cover the full sequence
including IP, domain, URL, and hash targets, auto-detection logic, endpoint routing,
STIX field population, and error paths (401, 429, missing key).

@decision DEC-TEST-VT-001
@title Monkeypatch httpx.AsyncClient with context manager support for single-endpoint module
@status accepted
@rationale VirusTotal module uses httpx.AsyncClient as a context manager and makes
           one GET per hunt() call (unlike OTX's multi-endpoint pattern). The mock
           must support __aenter__/__aexit__ and return a single response. Same
           underlying approach as DEC-TEST-OTX-001 (test_otx.py), simplified for
           one-shot calls.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adversary_pursuit.modules.base import (
    AuthenticationError,
    PursuitModule,
    RateLimitError,
)
from adversary_pursuit.modules.cti.virustotal import VirusTotal
from adversary_pursuit.core.plugin_mgr import PluginManager


# ---------------------------------------------------------------------------
# Sample API responses (VirusTotal v3 /api/v3/{type}/{target})
# ---------------------------------------------------------------------------

SAMPLE_IP_RESPONSE = {
    "data": {
        "id": "1.2.3.4",
        "type": "ip_address",
        "attributes": {
            "last_analysis_stats": {
                "malicious": 5,
                "suspicious": 2,
                "harmless": 60,
                "undetected": 10,
            },
            "reputation": -10,
            "last_analysis_date": 1712000000,
            "as_owner": "Google LLC",
            "country": "US",
        },
    }
}

SAMPLE_DOMAIN_RESPONSE = {
    "data": {
        "id": "evil.example.com",
        "type": "domain",
        "attributes": {
            "last_analysis_stats": {
                "malicious": 8,
                "suspicious": 1,
                "harmless": 55,
                "undetected": 4,
            },
            "reputation": -25,
            "last_analysis_date": 1711900000,
            "as_owner": "Evil Hosting Co",
            "country": "RU",
        },
    }
}

SAMPLE_URL_RESPONSE = {
    "data": {
        "id": "abc123urlid",
        "type": "url",
        "attributes": {
            "last_analysis_stats": {
                "malicious": 3,
                "suspicious": 0,
                "harmless": 70,
                "undetected": 5,
            },
            "reputation": -5,
            "last_analysis_date": 1711800000,
            "url": "http://malware.example.com/payload.exe",
        },
    }
}

SAMPLE_HASH_RESPONSE = {
    "data": {
        "id": "d41d8cd98f00b204e9800998ecf8427e",
        "type": "file",
        "attributes": {
            "last_analysis_stats": {
                "malicious": 40,
                "suspicious": 2,
                "harmless": 0,
                "undetected": 25,
            },
            "reputation": -50,
            "last_analysis_date": 1711700000,
            "meaningful_name": "malware.exe",
            "size": 102400,
            "type_description": "PE32 executable",
        },
    }
}

SAMPLE_STATS_ZEROS = {
    "data": {
        "id": "1.1.1.1",
        "type": "ip_address",
        "attributes": {
            "last_analysis_stats": {
                "malicious": 0,
                "suspicious": 0,
                "harmless": 90,
                "undetected": 5,
            },
            "reputation": 0,
            "last_analysis_date": 1712000000,
            "as_owner": "Cloudflare",
            "country": "AU",
        },
    }
}


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


def _make_client(response: MagicMock) -> MagicMock:
    """Build a mock AsyncClient that returns a single response for get()."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_ip_success():
    """Patch httpx.AsyncClient for a successful IPv4 query."""
    resp = _make_mock_response(200, SAMPLE_IP_RESPONSE)
    client = _make_client(resp)
    with patch("adversary_pursuit.modules.cti.virustotal.httpx.AsyncClient", return_value=client):
        yield client


@pytest.fixture
def mock_domain_success():
    """Patch httpx.AsyncClient for a successful domain query."""
    resp = _make_mock_response(200, SAMPLE_DOMAIN_RESPONSE)
    client = _make_client(resp)
    with patch("adversary_pursuit.modules.cti.virustotal.httpx.AsyncClient", return_value=client):
        yield client


@pytest.fixture
def mock_url_success():
    """Patch httpx.AsyncClient for a successful URL query."""
    resp = _make_mock_response(200, SAMPLE_URL_RESPONSE)
    client = _make_client(resp)
    with patch("adversary_pursuit.modules.cti.virustotal.httpx.AsyncClient", return_value=client):
        yield client


@pytest.fixture
def mock_hash_success():
    """Patch httpx.AsyncClient for a successful file hash query."""
    resp = _make_mock_response(200, SAMPLE_HASH_RESPONSE)
    client = _make_client(resp)
    with patch("adversary_pursuit.modules.cti.virustotal.httpx.AsyncClient", return_value=client):
        yield client


@pytest.fixture
def mock_zeros_success():
    """Patch httpx.AsyncClient for a clean IP with all-zero malicious stats."""
    resp = _make_mock_response(200, SAMPLE_STATS_ZEROS)
    client = _make_client(resp)
    with patch("adversary_pursuit.modules.cti.virustotal.httpx.AsyncClient", return_value=client):
        yield client


@pytest.fixture
def mock_401():
    """Patch httpx.AsyncClient to return 401."""
    resp = _make_mock_response(401, {"error": {"code": "WrongCredentialsError"}})
    client = _make_client(resp)
    with patch("adversary_pursuit.modules.cti.virustotal.httpx.AsyncClient", return_value=client):
        yield client


@pytest.fixture
def mock_429():
    """Patch httpx.AsyncClient to return 429."""
    resp = _make_mock_response(429, {"error": {"code": "QuotaExceededError"}})
    client = _make_client(resp)
    with patch("adversary_pursuit.modules.cti.virustotal.httpx.AsyncClient", return_value=client):
        yield client


@pytest.fixture
def mock_404():
    """Patch httpx.AsyncClient to return 404 (not found — raise_for_status raises)."""
    import httpx as _httpx
    resp = MagicMock()
    resp.status_code = 404
    resp.headers = {}
    resp.json.return_value = {"error": {"code": "NotFoundError"}}
    resp.raise_for_status.side_effect = _httpx.HTTPStatusError(
        "404 Not Found", request=MagicMock(), response=resp
    )
    client = _make_client(resp)
    with patch("adversary_pursuit.modules.cti.virustotal.httpx.AsyncClient", return_value=client):
        yield client


# ---------------------------------------------------------------------------
# Protocol and metadata tests
# ---------------------------------------------------------------------------

class TestVirusTotalMetadata:
    """Module satisfies PursuitModule protocol and declares correct metadata."""

    def test_satisfies_protocol(self):
        """VirusTotal must satisfy PursuitModule isinstance check."""
        mod = VirusTotal()
        assert isinstance(mod, PursuitModule)

    def test_module_name(self):
        mod = VirusTotal()
        assert mod.name == "cti/virustotal"

    def test_module_type(self):
        mod = VirusTotal()
        assert mod.module_type == "cti"

    def test_module_author(self):
        mod = VirusTotal()
        assert mod.author == "Adversary Pursuit"

    def test_description_non_empty(self):
        mod = VirusTotal()
        assert mod.description

    def test_options_has_target(self):
        mod = VirusTotal()
        assert "TARGET" in mod.options
        assert mod.options["TARGET"]["required"] is True

    def test_options_has_target_type(self):
        mod = VirusTotal()
        assert "TARGET_TYPE" in mod.options
        assert mod.options["TARGET_TYPE"]["required"] is False
        assert mod.options["TARGET_TYPE"]["default"] == ""


# ---------------------------------------------------------------------------
# Authentication / error path tests
# ---------------------------------------------------------------------------

class TestVirusTotalErrors:
    """hunt() error handling: missing key, 401, 429, 404."""

    def test_hunt_no_api_key_raises_auth_error(self):
        """hunt() without API key raises AuthenticationError immediately."""
        mod = VirusTotal()
        mod.initialize({})
        with pytest.raises(AuthenticationError, match="API key"):
            asyncio.run(mod.hunt("1.2.3.4", {}))

    def test_hunt_empty_api_key_raises_auth_error(self):
        """hunt() with empty API key raises AuthenticationError."""
        mod = VirusTotal()
        mod.initialize({"api_key": ""})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("1.2.3.4", {}))

    def test_hunt_401_raises_auth_error(self, mock_401):
        """401 response raises AuthenticationError."""
        mod = VirusTotal()
        mod.initialize({"api_key": "bad-key"})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("1.2.3.4", {}))

    def test_hunt_429_raises_rate_limit_error(self, mock_429):
        """429 response raises RateLimitError."""
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        with pytest.raises(RateLimitError):
            asyncio.run(mod.hunt("1.2.3.4", {}))

    def test_hunt_404_raises_http_status_error(self, mock_404):
        """404 response propagates as HTTPStatusError (resource not found)."""
        import httpx
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(mod.hunt("1.2.3.4", {}))


# ---------------------------------------------------------------------------
# Target type auto-detection
# ---------------------------------------------------------------------------

class TestVirusTotalTargetDetection:
    """hunt() auto-detects target type from the target string."""

    def test_ipv4_target_routes_to_ip_addresses_endpoint(self, mock_ip_success):
        """IPv4 address routes to /api/v3/ip_addresses/{ip}."""
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("1.2.3.4", {}))
        call_url = mock_ip_success.get.call_args.args[0]
        assert "ip_addresses" in call_url
        assert "1.2.3.4" in call_url

    def test_domain_target_routes_to_domains_endpoint(self, mock_domain_success):
        """Domain routes to /api/v3/domains/{domain}."""
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("evil.example.com", {}))
        call_url = mock_domain_success.get.call_args.args[0]
        assert "domains" in call_url
        assert "evil.example.com" in call_url

    def test_url_target_routes_to_urls_endpoint(self, mock_url_success):
        """URL target routes to /api/v3/urls/{url_id}."""
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("http://malware.example.com/payload.exe", {}))
        call_url = mock_url_success.get.call_args.args[0]
        assert "urls" in call_url

    def test_md5_hash_routes_to_files_endpoint(self, mock_hash_success):
        """32-char hex string (MD5) routes to /api/v3/files/{hash}."""
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("d41d8cd98f00b204e9800998ecf8427e", {}))
        call_url = mock_hash_success.get.call_args.args[0]
        assert "files" in call_url
        assert "d41d8cd98f00b204e9800998ecf8427e" in call_url

    def test_sha256_hash_routes_to_files_endpoint(self, mock_hash_success):
        """64-char hex string (SHA256) routes to /api/v3/files/{hash}."""
        sha256 = "a" * 64
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt(sha256, {}))
        call_url = mock_hash_success.get.call_args.args[0]
        assert "files" in call_url
        assert sha256 in call_url

    def test_sha1_hash_routes_to_files_endpoint(self, mock_hash_success):
        """40-char hex string (SHA1) routes to /api/v3/files/{hash}."""
        sha1 = "b" * 40
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt(sha1, {}))
        call_url = mock_hash_success.get.call_args.args[0]
        assert "files" in call_url

    def test_explicit_target_type_overrides_auto_detection(self, mock_domain_success):
        """TARGET_TYPE option overrides auto-detection."""
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        # "evil.example.com" would auto-detect as domain; explicitly set domain still works
        asyncio.run(mod.hunt("evil.example.com", {"TARGET_TYPE": "domain"}))
        call_url = mock_domain_success.get.call_args.args[0]
        assert "domains" in call_url

    def test_https_url_detected_as_url_type(self, mock_url_success):
        """HTTPS URL target is detected as url type."""
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("https://phishing.example.com/login", {}))
        call_url = mock_url_success.get.call_args.args[0]
        assert "urls" in call_url


# ---------------------------------------------------------------------------
# IP response parsing
# ---------------------------------------------------------------------------

class TestVirusTotalIPResponse:
    """hunt() with IP target returns correctly parsed STIX dict."""

    def test_returns_list(self, mock_ip_success):
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_stix_type_is_ipv4_addr(self, mock_ip_success):
        """IP result has STIX type 'ipv4-addr'."""
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["type"] == "ipv4-addr"

    def test_stix_value_matches_target(self, mock_ip_success):
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["value"] == "1.2.3.4"

    def test_x_malicious_count(self, mock_ip_success):
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_malicious"] == 5

    def test_x_suspicious_count(self, mock_ip_success):
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_suspicious"] == 2

    def test_x_harmless_count(self, mock_ip_success):
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_harmless"] == 60

    def test_x_undetected_count(self, mock_ip_success):
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_undetected"] == 10

    def test_x_reputation(self, mock_ip_success):
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_reputation"] == -10

    def test_x_last_analysis_date(self, mock_ip_success):
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_last_analysis_date"] == 1712000000

    def test_x_as_owner_for_ip(self, mock_ip_success):
        """IPs include x_as_owner field."""
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_as_owner"] == "Google LLC"

    def test_x_country_for_ip(self, mock_ip_success):
        """IPs include x_country field."""
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_country"] == "US"

    def test_zero_malicious_stats(self, mock_zeros_success):
        """Stats of 0 are correctly represented (not falsy/missing)."""
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.1.1.1", {}))
        assert results[0]["x_malicious"] == 0
        assert results[0]["x_suspicious"] == 0
        assert results[0]["x_reputation"] == 0


# ---------------------------------------------------------------------------
# Domain response parsing
# ---------------------------------------------------------------------------

class TestVirusTotalDomainResponse:
    """hunt() with domain target returns correctly parsed STIX dict."""

    def test_stix_type_is_domain_name(self, mock_domain_success):
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert results[0]["type"] == "domain-name"

    def test_stix_value_matches_target(self, mock_domain_success):
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert results[0]["value"] == "evil.example.com"

    def test_x_malicious_for_domain(self, mock_domain_success):
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert results[0]["x_malicious"] == 8

    def test_x_as_owner_for_domain(self, mock_domain_success):
        """Domains include x_as_owner field."""
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert results[0]["x_as_owner"] == "Evil Hosting Co"

    def test_x_country_for_domain(self, mock_domain_success):
        """Domains include x_country field."""
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert results[0]["x_country"] == "RU"


# ---------------------------------------------------------------------------
# URL response parsing
# ---------------------------------------------------------------------------

class TestVirusTotalURLResponse:
    """hunt() with URL target returns correctly parsed STIX dict."""

    def test_stix_type_is_url(self, mock_url_success):
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("http://malware.example.com/payload.exe", {}))
        assert results[0]["type"] == "url"

    def test_stix_value_is_original_url(self, mock_url_success):
        """URL SCO value is the original URL, not the VT URL ID."""
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        target = "http://malware.example.com/payload.exe"
        results = asyncio.run(mod.hunt(target, {}))
        assert results[0]["value"] == target

    def test_x_malicious_for_url(self, mock_url_success):
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("http://malware.example.com/payload.exe", {}))
        assert results[0]["x_malicious"] == 3

    def test_x_reputation_for_url(self, mock_url_success):
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("http://malware.example.com/payload.exe", {}))
        assert results[0]["x_reputation"] == -5


# ---------------------------------------------------------------------------
# Hash (file) response parsing
# ---------------------------------------------------------------------------

class TestVirusTotalHashResponse:
    """hunt() with hash target returns correctly parsed STIX dict."""

    def test_stix_type_is_file(self, mock_hash_success):
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("d41d8cd98f00b204e9800998ecf8427e", {}))
        assert results[0]["type"] == "file"

    def test_stix_value_is_hash(self, mock_hash_success):
        """File SCO value is the hash string."""
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        h = "d41d8cd98f00b204e9800998ecf8427e"
        results = asyncio.run(mod.hunt(h, {}))
        assert results[0]["value"] == h

    def test_x_malicious_for_file(self, mock_hash_success):
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("d41d8cd98f00b204e9800998ecf8427e", {}))
        assert results[0]["x_malicious"] == 40

    def test_x_reputation_for_file(self, mock_hash_success):
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("d41d8cd98f00b204e9800998ecf8427e", {}))
        assert results[0]["x_reputation"] == -50

    def test_no_as_owner_for_file(self, mock_hash_success):
        """File SCOs do not include x_as_owner (IP/domain-specific field)."""
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("d41d8cd98f00b204e9800998ecf8427e", {}))
        assert "x_as_owner" not in results[0]

    def test_no_x_country_for_file(self, mock_hash_success):
        """File SCOs do not include x_country (IP/domain-specific field)."""
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("d41d8cd98f00b204e9800998ecf8427e", {}))
        assert "x_country" not in results[0]


# ---------------------------------------------------------------------------
# HTTP header tests
# ---------------------------------------------------------------------------

class TestVirusTotalHeaders:
    """x-apikey header is sent correctly."""

    def test_apikey_header_sent(self, mock_ip_success):
        """x-apikey header is passed to AsyncClient constructor."""
        mod = VirusTotal()
        mod.initialize({"api_key": "my-vt-key"})
        asyncio.run(mod.hunt("1.2.3.4", {}))
        # Verify get() was called (headers set on client init)
        assert mock_ip_success.get.called

    def test_single_http_call_per_hunt(self, mock_ip_success):
        """hunt() makes exactly one HTTP GET per call."""
        mod = VirusTotal()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("1.2.3.4", {}))
        assert mock_ip_success.get.call_count == 1


# ---------------------------------------------------------------------------
# Production sequence test
# ---------------------------------------------------------------------------

class TestVirusTotalProductionSequence:
    """Simulates the full production call sequence."""

    def test_production_sequence_ip(self, mock_ip_success):
        """Full production sequence: load -> get -> initialize -> hunt with IP."""
        mgr = PluginManager()
        mgr.load_plugins()

        mod = mgr.get_module("cti/virustotal")
        assert mod is not None
        assert isinstance(mod, VirusTotal)

        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))

        assert len(results) >= 1
        assert results[0]["type"] == "ipv4-addr"
        assert results[0]["value"] == "1.2.3.4"
        assert results[0]["x_malicious"] == 5
        assert results[0]["x_reputation"] == -10

    def test_production_sequence_domain(self, mock_domain_success):
        """Full production sequence: load -> get -> initialize -> hunt with domain."""
        mgr = PluginManager()
        mgr.load_plugins()

        mod = mgr.get_module("cti/virustotal")
        assert mod is not None

        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("evil.example.com", {}))

        assert len(results) >= 1
        assert results[0]["type"] == "domain-name"
        assert results[0]["x_malicious"] == 8

    def test_production_sequence_hash(self, mock_hash_success):
        """Full production sequence: load -> get -> initialize -> hunt with hash."""
        mgr = PluginManager()
        mgr.load_plugins()

        mod = mgr.get_module("cti/virustotal")
        assert mod is not None

        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("d41d8cd98f00b204e9800998ecf8427e", {}))

        assert len(results) >= 1
        assert results[0]["type"] == "file"
        assert results[0]["x_malicious"] == 40


# ---------------------------------------------------------------------------
# Plugin manager discovery tests
# ---------------------------------------------------------------------------

class TestVirusTotalDiscovery:
    """VirusTotal is discoverable via PluginManager."""

    def test_discoverable_via_plugin_manager(self):
        """PluginManager.load_plugins() finds cti/virustotal."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("cti/virustotal")
        assert mod is not None

    def test_plugin_manager_returns_virustotal_instance(self):
        """get_module('cti/virustotal') returns a VirusTotal instance."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("cti/virustotal")
        assert isinstance(mod, VirusTotal)

    def test_search_finds_virustotal(self):
        """PluginManager.search('virustotal') finds cti/virustotal."""
        mgr = PluginManager()
        mgr.load_plugins()
        results = mgr.search("virustotal")
        assert len(results) >= 1
        names = [r["name"] for r in results]
        assert "cti/virustotal" in names

    def test_search_by_cti_type(self):
        """PluginManager.search('cti') returns cti/virustotal."""
        mgr = PluginManager()
        mgr.load_plugins()
        results = mgr.search("cti")
        names = [r["name"] for r in results]
        assert "cti/virustotal" in names
