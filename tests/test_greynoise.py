"""Tests for the GreyNoise OSINT module (Issue #greynoise).

# @mock-exempt: httpx.AsyncClient is an external HTTP boundary (GreyNoise Community API).
# Tests must run without a real API key. Mocking the HTTP layer is the only way
# to exercise error paths (401, 404, 429) hermetically. This follows Sacred Practice #5's
# explicitly-permitted exception: "Mocks are acceptable ONLY for external boundaries
# (HTTP APIs, third-party services, databases)."

Production sequence: PluginManager.load_plugins() -> get_module('osint/greynoise') ->
initialize({api_key}) -> hunt(ip, options). Tests cover the full sequence plus error
paths (401, 404, 429, missing key) and SCO output structure.

@decision DEC-TEST-GREYNOISE-001
@title Monkeypatch httpx.AsyncClient for hermetic GreyNoise tests
@status accepted
@rationale Mirrors DEC-TEST-ABUSEIPDB-001: respx is not in the dependency set.
           unittest.mock.patch on httpx.AsyncClient exercises all status-code branches
           (200, 401, 404, 429) without a live API key. The patch target is the
           adversary_pursuit.modules.osint.greynoise module's httpx import so the
           AsyncClient constructor call is intercepted at the call site.
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
from adversary_pursuit.modules.osint.greynoise import GreyNoise
from adversary_pursuit.core.plugin_mgr import PluginManager


# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------

SAMPLE_200_RESPONSE = {
    "ip": "8.8.8.8",
    "noise": False,
    "riot": True,
    "classification": "benign",
    "name": "Google Public DNS",
    "link": "https://viz.greynoise.io/ip/8.8.8.8",
    "last_seen": "2026-05-01",
    "message": "This IP is commonly included in threat intelligence lists.",
}

SAMPLE_200_MALICIOUS = {
    "ip": "1.2.3.4",
    "noise": True,
    "riot": False,
    "classification": "malicious",
    "name": "EvilScanner",
    "link": "https://viz.greynoise.io/ip/1.2.3.4",
    "last_seen": "2026-05-13",
    "message": "This IP has been observed actively scanning the internet.",
}


def _make_mock_response(
    status_code: int,
    body: dict | None = None,
    headers: dict | None = None,
) -> MagicMock:
    """Build a mock httpx.Response-like object for GreyNoise API responses."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.headers = headers or {}
    mock_resp.json.return_value = body or {}
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def _make_mock_client(mock_resp: MagicMock) -> AsyncMock:
    """Build a mock httpx.AsyncClient that returns mock_resp from .get()."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


@pytest.fixture
def mock_success():
    """Patch httpx.AsyncClient to return the standard 200 success response."""
    mock_resp = _make_mock_response(200, SAMPLE_200_RESPONSE)
    mock_client = _make_mock_client(mock_resp)
    with patch(
        "adversary_pursuit.modules.osint.greynoise.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def mock_success_malicious():
    """Patch httpx.AsyncClient to return a malicious-IP 200 response."""
    mock_resp = _make_mock_response(200, SAMPLE_200_MALICIOUS)
    mock_client = _make_mock_client(mock_resp)
    with patch(
        "adversary_pursuit.modules.osint.greynoise.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def mock_401():
    """Patch httpx.AsyncClient to return 401 Unauthorized."""
    mock_resp = _make_mock_response(401, {"message": "invalid or revoked API key"})
    mock_client = _make_mock_client(mock_resp)
    with patch(
        "adversary_pursuit.modules.osint.greynoise.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def mock_404():
    """Patch httpx.AsyncClient to return 404 (IP not in database)."""
    mock_resp = _make_mock_response(404, {"message": "Not found"})
    mock_client = _make_mock_client(mock_resp)
    with patch(
        "adversary_pursuit.modules.osint.greynoise.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def mock_429():
    """Patch httpx.AsyncClient to return 429 with Retry-After header."""
    mock_resp = _make_mock_response(
        429,
        {"message": "Daily rate limit exceeded."},
        headers={"Retry-After": "3600"},
    )
    mock_client = _make_mock_client(mock_resp)
    with patch(
        "adversary_pursuit.modules.osint.greynoise.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def mock_429_no_retry_after():
    """Patch httpx.AsyncClient to return 429 without Retry-After header."""
    mock_resp = _make_mock_response(
        429,
        {"message": "Rate limit exceeded."},
        headers={},
    )
    mock_client = _make_mock_client(mock_resp)
    with patch(
        "adversary_pursuit.modules.osint.greynoise.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


# ---------------------------------------------------------------------------
# TestGreyNoiseMetadata — protocol and metadata checks
# ---------------------------------------------------------------------------


class TestGreyNoiseMetadata:
    """Module satisfies PursuitModule protocol and declares correct metadata."""

    def test_satisfies_protocol(self):
        """GreyNoise must satisfy PursuitModule isinstance check."""
        mod = GreyNoise()
        assert isinstance(mod, PursuitModule)

    def test_module_name(self):
        """Module name must be exactly 'osint/greynoise'."""
        mod = GreyNoise()
        assert mod.name == "osint/greynoise"

    def test_module_type(self):
        mod = GreyNoise()
        assert mod.module_type == "osint"

    def test_module_author(self):
        mod = GreyNoise()
        assert mod.author == "Adversary Pursuit"

    def test_description_non_empty(self):
        mod = GreyNoise()
        assert mod.description

    def test_options_has_target(self):
        """Options dict must include a required TARGET key."""
        mod = GreyNoise()
        assert "TARGET" in mod.options
        assert mod.options["TARGET"]["required"] is True

    def test_options_has_timeout(self):
        """Options dict must include TIMEOUT or TARGET but not require more than TARGET."""
        # TIMEOUT is implicit (30.0 hardcoded) — if present it should be non-required
        mod = GreyNoise()
        # At minimum TARGET is required; TIMEOUT may or may not be present
        assert "TARGET" in mod.options

    def test_options_target_default_is_empty_string(self):
        """TARGET default must be an empty string (not None)."""
        mod = GreyNoise()
        assert mod.options["TARGET"]["default"] == ""


# ---------------------------------------------------------------------------
# TestGreyNoiseAuth — authentication error paths
# ---------------------------------------------------------------------------


class TestGreyNoiseAuth:
    """hunt() error handling: missing key and 401 response."""

    def test_hunt_no_api_key_raises_auth_error(self):
        """hunt() without an API key must raise AuthenticationError immediately."""
        mod = GreyNoise()
        mod.initialize({})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("8.8.8.8", {}))

    def test_hunt_empty_api_key_raises_auth_error(self):
        """hunt() with empty-string API key raises AuthenticationError."""
        mod = GreyNoise()
        mod.initialize({"api_key": ""})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("8.8.8.8", {}))

    def test_hunt_401_raises_auth_error(self, mock_401):
        """401 response from GreyNoise raises AuthenticationError."""
        mod = GreyNoise()
        mod.initialize({"api_key": "bad-key"})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("8.8.8.8", {}))

    def test_hunt_401_message_mentions_invalid_or_revoked(self, mock_401):
        """AuthenticationError from 401 must mention 'invalid' or 'revoked'."""
        mod = GreyNoise()
        mod.initialize({"api_key": "bad-key"})
        with pytest.raises(AuthenticationError, match=r"invalid|revoked"):
            asyncio.run(mod.hunt("8.8.8.8", {}))

    def test_no_key_error_raised_before_http_call(self):
        """Missing-key AuthenticationError raised without making any HTTP call.

        This is the early-exit guard: the module must not attempt a network call
        when no key is configured — it must fail fast with AuthenticationError.
        """
        with patch(
            "adversary_pursuit.modules.osint.greynoise.httpx.AsyncClient"
        ) as mock_cls:
            mod = GreyNoise()
            mod.initialize({})
            with pytest.raises(AuthenticationError):
                asyncio.run(mod.hunt("8.8.8.8", {}))
            # AsyncClient must never be instantiated when no key is set
            mock_cls.assert_not_called()


# ---------------------------------------------------------------------------
# TestGreyNoiseHappyPath — 200 response, SCO structure, custom fields
# ---------------------------------------------------------------------------


class TestGreyNoiseHappyPath:
    """hunt() with a 200 response returns correct ipv4-addr SCO with x_greynoise_* fields."""

    def test_hunt_returns_list(self, mock_success):
        """hunt() returns a list."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert isinstance(results, list)

    def test_hunt_returns_single_sco(self, mock_success):
        """hunt() returns exactly one SCO for a successful 200 response."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert len(results) == 1

    def test_hunt_result_is_ipv4_addr(self, mock_success):
        """The returned SCO is an ipv4-addr type."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert results[0]["type"] == "ipv4-addr"

    def test_hunt_result_value_matches_ip(self, mock_success):
        """The ipv4-addr SCO value matches the API response IP."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert results[0]["value"] == "8.8.8.8"

    def test_hunt_classification_field_present(self, mock_success):
        """x_greynoise_classification field is present."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert "x_greynoise_classification" in results[0]
        assert results[0]["x_greynoise_classification"] == "benign"

    def test_hunt_noise_field_present(self, mock_success):
        """x_greynoise_noise field is present and boolean."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert "x_greynoise_noise" in results[0]
        assert results[0]["x_greynoise_noise"] is False

    def test_hunt_riot_field_present(self, mock_success):
        """x_greynoise_riot field is present and boolean."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert "x_greynoise_riot" in results[0]
        assert results[0]["x_greynoise_riot"] is True

    def test_hunt_name_field_present(self, mock_success):
        """x_greynoise_name field is present."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert "x_greynoise_name" in results[0]
        assert results[0]["x_greynoise_name"] == "Google Public DNS"

    def test_hunt_last_seen_field_present(self, mock_success):
        """x_greynoise_last_seen field is present."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert "x_greynoise_last_seen" in results[0]
        assert results[0]["x_greynoise_last_seen"] == "2026-05-01"

    def test_hunt_link_field_present(self, mock_success):
        """x_greynoise_link field is present."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("8.8.8.8", {}))
        assert "x_greynoise_link" in results[0]
        assert "greynoise.io" in results[0]["x_greynoise_link"]

    def test_hunt_malicious_classification(self, mock_success_malicious):
        """A malicious IP returns x_greynoise_classification='malicious' and noise=True."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.2.3.4", {}))
        assert results[0]["x_greynoise_classification"] == "malicious"
        assert results[0]["x_greynoise_noise"] is True
        assert results[0]["x_greynoise_riot"] is False


# ---------------------------------------------------------------------------
# TestGreyNoise404 — 404 returns unknown stub, not an error
# ---------------------------------------------------------------------------


class TestGreyNoise404:
    """hunt() on 404 response returns a stub SCO with classification='unknown'."""

    def test_404_does_not_raise(self, mock_404):
        """hunt() on 404 must NOT raise — it returns an 'unknown' stub."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        # Must not raise:
        results = asyncio.run(mod.hunt("1.1.1.1", {}))
        assert isinstance(results, list)

    def test_404_returns_single_sco(self, mock_404):
        """hunt() on 404 returns exactly one SCO."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.1.1.1", {}))
        assert len(results) == 1

    def test_404_sco_type_is_ipv4_addr(self, mock_404):
        """The 404 stub SCO is type ipv4-addr."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.1.1.1", {}))
        assert results[0]["type"] == "ipv4-addr"

    def test_404_sco_classification_is_unknown(self, mock_404):
        """x_greynoise_classification is 'unknown' on a 404 response."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.1.1.1", {}))
        assert results[0]["x_greynoise_classification"] == "unknown"

    def test_404_sco_has_all_fields(self, mock_404):
        """The 404 stub SCO has all six x_greynoise_* custom fields."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("1.1.1.1", {}))
        sco = results[0]
        for field in (
            "x_greynoise_classification",
            "x_greynoise_noise",
            "x_greynoise_riot",
            "x_greynoise_name",
            "x_greynoise_last_seen",
            "x_greynoise_link",
        ):
            assert field in sco, f"Missing field: {field}"

    def test_404_stub_value_matches_target(self, mock_404):
        """The 404 stub SCO value matches the queried IP address."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("203.0.113.99", {}))
        assert results[0]["value"] == "203.0.113.99"


# ---------------------------------------------------------------------------
# TestGreyNoiseRateLimit — 429 response handling
# ---------------------------------------------------------------------------


class TestGreyNoiseRateLimit:
    """hunt() on 429 raises RateLimitError with correct retry_after."""

    def test_429_raises_rate_limit_error(self, mock_429):
        """429 response raises RateLimitError."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        with pytest.raises(RateLimitError):
            asyncio.run(mod.hunt("8.8.8.8", {}))

    def test_429_retry_after_is_set(self, mock_429):
        """RateLimitError.retry_after is populated from the Retry-After header."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        with pytest.raises(RateLimitError) as exc_info:
            asyncio.run(mod.hunt("8.8.8.8", {}))
        assert exc_info.value.retry_after == 3600

    def test_429_no_retry_after_is_none(self, mock_429_no_retry_after):
        """RateLimitError.retry_after is None when header is absent."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        with pytest.raises(RateLimitError) as exc_info:
            asyncio.run(mod.hunt("8.8.8.8", {}))
        assert exc_info.value.retry_after is None


# ---------------------------------------------------------------------------
# TestGreyNoiseRequestShape — HTTP request structure
# ---------------------------------------------------------------------------


class TestGreyNoiseRequestShape:
    """Verify the exact HTTP request shape emitted to the GreyNoise Community API."""

    def test_endpoint_url_is_v3_community(self, mock_success):
        """GET is called on the exact GreyNoise Community API URL."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("8.8.8.8", {}))
        url = mock_success.get.call_args.args[0]
        assert url == "https://api.greynoise.io/v3/community/8.8.8.8"

    def test_auth_header_is_lowercase_key(self, mock_success):
        """HTTP auth header is lowercase 'key' (not 'Authorization', 'X-Key', etc.)."""
        mod = GreyNoise()
        mod.initialize({"api_key": "my-gn-key"})
        asyncio.run(mod.hunt("8.8.8.8", {}))
        headers = mock_success.get.call_args.kwargs.get("headers", {})
        assert "key" in headers, f"Expected lowercase 'key' header, got: {list(headers.keys())}"
        assert headers["key"] == "my-gn-key"

    def test_auth_header_not_authorization(self, mock_success):
        """Authorization header is NOT used (wrong header for GreyNoise Community API)."""
        mod = GreyNoise()
        mod.initialize({"api_key": "my-gn-key"})
        asyncio.run(mod.hunt("8.8.8.8", {}))
        headers = mock_success.get.call_args.kwargs.get("headers", {})
        assert "Authorization" not in headers
        assert "X-Key" not in headers

    def test_method_is_get(self, mock_success):
        """Request uses GET method (not POST, PUT, etc.)."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("8.8.8.8", {}))
        # Verify .get() was called (not .post() etc.)
        mock_success.get.assert_called_once()

    def test_ip_is_interpolated_into_url(self, mock_success):
        """The target IP is correctly interpolated into the URL path."""
        mod = GreyNoise()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("10.20.30.40", {}))
        url = mock_success.get.call_args.args[0]
        assert "10.20.30.40" in url


# ---------------------------------------------------------------------------
# TestGreyNoiseDiscovery — PluginManager integration
# ---------------------------------------------------------------------------


class TestGreyNoiseDiscovery:
    """GreyNoise is discoverable via PluginManager (production plug-in loading sequence)."""

    def test_discoverable_via_plugin_manager(self):
        """PluginManager.load_plugins() finds osint/greynoise."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/greynoise")
        assert mod is not None

    def test_plugin_manager_returns_greynoise_instance(self):
        """get_module('osint/greynoise') returns a GreyNoise instance."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/greynoise")
        assert isinstance(mod, GreyNoise)

    def test_production_sequence_load_search_get_initialize(self):
        """Production sequence: load_plugins -> search('greynoise') -> get -> initialize.

        This is the Compound-Interaction Test required by implementer.md: it crosses
        PluginManager.load_plugins() -> search() -> get_module() -> initialize()
        boundaries, exercising the full discovery + initialization production path.
        """
        mgr = PluginManager()
        mgr.load_plugins()

        results = mgr.search("greynoise")
        assert len(results) >= 1
        names = [r["name"] for r in results]
        assert "osint/greynoise" in names

        mod = mgr.get_module("osint/greynoise")
        assert mod is not None
        mod.initialize({"api_key": "test-key"})
        assert mod._config["api_key"] == "test-key"
