"""Tests for the HaveIBeenPwned OSINT module (Issue #11).

# @mock-exempt: httpx.AsyncClient is an external HTTP boundary (HIBP REST API).
# Tests must run without a real API key. Mocking the HTTP layer is the only
# way to exercise error paths (401, 404, 429) hermetically. This is Sacred
# Practice #5's explicitly-permitted exception: "Mocks are acceptable ONLY
# for external boundaries (HTTP APIs, third-party services, databases)."

Production sequence: PluginManager.load_plugins() -> get_module() ->
initialize({api_key}) -> hunt(email, options). Tests cover the full
sequence plus error paths (401, 404/clean email, 429, missing key),
TRUNCATE option, INCLUDE_UNVERIFIED option, and the custom email-addr SCO
with x_breach_count, x_breaches, x_breach_date, x_data_classes fields.

@decision DEC-TEST-HIBP-001
@title Monkeypatch httpx.AsyncClient for hermetic tests
@status accepted
@rationale Same pattern as test_abuseipdb.py (DEC-TEST-ABUSEIPDB-001).
           respx is not in the project dependency set. Python's
           unittest.mock (via pytest monkeypatch) patches the same
           interface and keeps the test suite self-contained.
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
from adversary_pursuit.modules.osint.hibp import HIBP
from adversary_pursuit.core.plugin_mgr import PluginManager


# ---------------------------------------------------------------------------
# Sample API response data
# ---------------------------------------------------------------------------

SAMPLE_BREACHES = [
    {
        "Name": "Adobe",
        "Title": "Adobe",
        "Domain": "adobe.com",
        "BreachDate": "2013-10-04",
        "AddedDate": "2013-12-04T00:00:00Z",
        "ModifiedDate": "2013-12-04T00:00:00Z",
        "PwnCount": 153000000,
        "Description": "In October 2013, Adobe suffered a massive breach.",
        "LogoPath": "https://haveibeenpwned.com/Content/Images/PwnedLogos/Adobe.png",
        "DataClasses": ["Email addresses", "Password hints", "Passwords", "Usernames"],
        "IsVerified": True,
        "IsFabricated": False,
        "IsSensitive": False,
        "IsRetired": False,
        "IsSpamList": False,
        "IsMalware": False,
    },
    {
        "Name": "Gawker",
        "Title": "Gawker",
        "Domain": "gawker.com",
        "BreachDate": "2010-12-11",
        "AddedDate": "2013-12-04T00:00:00Z",
        "ModifiedDate": "2013-12-04T00:00:00Z",
        "PwnCount": 1247574,
        "Description": "In December 2010, Gawker was hacked.",
        "LogoPath": "https://haveibeenpwned.com/Content/Images/PwnedLogos/Gawker.png",
        "DataClasses": ["Email addresses", "Passwords", "Usernames"],
        "IsVerified": True,
        "IsFabricated": False,
        "IsSensitive": False,
        "IsRetired": False,
        "IsSpamList": False,
        "IsMalware": False,
    },
]

SAMPLE_BREACH_SINGLE = [SAMPLE_BREACHES[0]]

SAMPLE_TRUNCATED_BREACHES = [
    {"Name": "Adobe"},
    {"Name": "Gawker"},
]


def _make_mock_response(
    status_code: int,
    body: Any,
    headers: dict | None = None,
) -> MagicMock:
    """Build a mock httpx.Response-like object."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.headers = headers or {}
    mock_resp.json.return_value = body
    if status_code < 400:
        mock_resp.raise_for_status.return_value = None
    else:
        mock_resp.raise_for_status.side_effect = None
    return mock_resp


@pytest.fixture
def mock_success():
    """Patch httpx.AsyncClient to return two breaches (full detail)."""
    mock_resp = _make_mock_response(200, SAMPLE_BREACHES)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("adversary_pursuit.modules.osint.hibp.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_success_single():
    """Patch httpx.AsyncClient to return one breach."""
    mock_resp = _make_mock_response(200, SAMPLE_BREACH_SINGLE)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("adversary_pursuit.modules.osint.hibp.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_404():
    """Patch httpx.AsyncClient to return 404 (no breaches found)."""
    mock_resp = _make_mock_response(404, "")
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("adversary_pursuit.modules.osint.hibp.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_401():
    """Patch httpx.AsyncClient to return 401 Unauthorized."""
    mock_resp = _make_mock_response(401, {"statusCode": 401, "message": "Access denied"})
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("adversary_pursuit.modules.osint.hibp.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_429():
    """Patch httpx.AsyncClient to return 429 Too Many Requests."""
    mock_resp = _make_mock_response(
        429,
        {"statusCode": 429, "message": "Rate limit is currently exceeded, please try again later."},
        headers={"Retry-After": "1500"},
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("adversary_pursuit.modules.osint.hibp.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_429_no_retry_after():
    """Patch httpx.AsyncClient to return 429 without Retry-After header."""
    mock_resp = _make_mock_response(
        429,
        {"statusCode": 429, "message": "Rate limit exceeded."},
        headers={},
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("adversary_pursuit.modules.osint.hibp.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


# ---------------------------------------------------------------------------
# Protocol and metadata tests
# ---------------------------------------------------------------------------

class TestHIBPMetadata:
    """Module satisfies PursuitModule protocol and declares correct metadata."""

    def test_satisfies_protocol(self):
        """HIBP must satisfy PursuitModule isinstance check."""
        mod = HIBP()
        assert isinstance(mod, PursuitModule)

    def test_module_name(self):
        mod = HIBP()
        assert mod.name == "osint/hibp"

    def test_module_type(self):
        mod = HIBP()
        assert mod.module_type == "osint"

    def test_module_author(self):
        mod = HIBP()
        assert mod.author == "Adversary Pursuit"

    def test_description_non_empty(self):
        mod = HIBP()
        assert mod.description

    def test_options_has_target(self):
        mod = HIBP()
        assert "TARGET" in mod.options
        assert mod.options["TARGET"]["required"] is True

    def test_options_target_default_empty(self):
        mod = HIBP()
        assert mod.options["TARGET"]["default"] == ""

    def test_options_has_truncate(self):
        mod = HIBP()
        assert "TRUNCATE" in mod.options
        assert mod.options["TRUNCATE"]["required"] is False
        assert mod.options["TRUNCATE"]["default"] == "false"

    def test_options_has_include_unverified(self):
        mod = HIBP()
        assert "INCLUDE_UNVERIFIED" in mod.options
        assert mod.options["INCLUDE_UNVERIFIED"]["required"] is False
        assert mod.options["INCLUDE_UNVERIFIED"]["default"] == "true"


# ---------------------------------------------------------------------------
# Authentication / error path tests
# ---------------------------------------------------------------------------

class TestHIBPErrors:
    """hunt() error handling: missing key, 401, 429."""

    def test_hunt_no_api_key_raises_auth_error(self):
        """hunt() without an API key must raise AuthenticationError immediately."""
        mod = HIBP()
        mod.initialize({})
        with pytest.raises(AuthenticationError, match="API key"):
            asyncio.run(mod.hunt("victim@example.com", {}))

    def test_hunt_empty_api_key_raises_auth_error(self):
        """hunt() with empty string API key raises AuthenticationError."""
        mod = HIBP()
        mod.initialize({"api_key": ""})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("victim@example.com", {}))

    def test_hunt_401_raises_auth_error(self, mock_401):
        """401 response raises AuthenticationError."""
        mod = HIBP()
        mod.initialize({"api_key": "bad-key"})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt("victim@example.com", {}))

    def test_hunt_429_raises_rate_limit_error(self, mock_429):
        """429 response raises RateLimitError."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        with pytest.raises(RateLimitError):
            asyncio.run(mod.hunt("victim@example.com", {}))

    def test_hunt_429_retry_after_is_set(self, mock_429):
        """RateLimitError.retry_after is populated from Retry-After header."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        with pytest.raises(RateLimitError) as exc_info:
            asyncio.run(mod.hunt("victim@example.com", {}))
        assert exc_info.value.retry_after == 1500

    def test_hunt_429_no_retry_after_is_none(self, mock_429_no_retry_after):
        """RateLimitError.retry_after is None when header is absent."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        with pytest.raises(RateLimitError) as exc_info:
            asyncio.run(mod.hunt("victim@example.com", {}))
        assert exc_info.value.retry_after is None


# ---------------------------------------------------------------------------
# 404: clean email (no breaches)
# ---------------------------------------------------------------------------

class TestHIBPCleanEmail:
    """hunt() returns email-addr SCO with x_breach_count=0 on 404."""

    def test_404_returns_list(self, mock_404):
        """hunt() still returns a list on 404."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("clean@example.com", {}))
        assert isinstance(results, list)

    def test_404_returns_one_sco(self, mock_404):
        """hunt() returns exactly one SCO on 404."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("clean@example.com", {}))
        assert len(results) == 1

    def test_404_sco_type_is_email_addr(self, mock_404):
        """The SCO on 404 is of type email-addr."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("clean@example.com", {}))
        assert results[0]["type"] == "email-addr"

    def test_404_sco_value_matches_email(self, mock_404):
        """The email-addr SCO value matches the queried email."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("clean@example.com", {}))
        assert results[0]["value"] == "clean@example.com"

    def test_404_x_breach_count_is_zero(self, mock_404):
        """x_breach_count is 0 for a clean email."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("clean@example.com", {}))
        assert results[0]["x_breach_count"] == 0

    def test_404_x_breaches_is_empty_list(self, mock_404):
        """x_breaches is an empty list for a clean email."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("clean@example.com", {}))
        assert results[0]["x_breaches"] == []


# ---------------------------------------------------------------------------
# Successful breach results
# ---------------------------------------------------------------------------

class TestHIBPBreachResults:
    """hunt() result structure when breaches are found."""

    def test_returns_list(self, mock_success):
        """hunt() returns a list."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("victim@example.com", {}))
        assert isinstance(results, list)

    def test_primary_sco_type_is_email_addr(self, mock_success):
        """First result is an email-addr SCO."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("victim@example.com", {}))
        assert results[0]["type"] == "email-addr"

    def test_primary_sco_value_matches_email(self, mock_success):
        """email-addr SCO value matches the queried email."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("victim@example.com", {}))
        assert results[0]["value"] == "victim@example.com"

    def test_x_breach_count_matches_response(self, mock_success):
        """x_breach_count equals the number of breaches in the response."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("victim@example.com", {}))
        assert results[0]["x_breach_count"] == 2

    def test_x_breaches_contains_breach_names(self, mock_success):
        """x_breaches is a list of breach Name strings."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("victim@example.com", {}))
        assert "Adobe" in results[0]["x_breaches"]
        assert "Gawker" in results[0]["x_breaches"]

    def test_x_breach_date_present_on_breach(self, mock_success):
        """Each breach entry in x_breaches_detail includes x_breach_date."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("victim@example.com", {}))
        # x_breaches_detail holds full per-breach info including date
        detail = results[0].get("x_breaches_detail", [])
        assert len(detail) == 2
        adobe = next(b for b in detail if b["name"] == "Adobe")
        assert adobe["x_breach_date"] == "2013-10-04"

    def test_x_data_classes_present_on_breach(self, mock_success):
        """Each breach entry in x_breaches_detail includes x_data_classes."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("victim@example.com", {}))
        detail = results[0].get("x_breaches_detail", [])
        adobe = next(b for b in detail if b["name"] == "Adobe")
        assert "Email addresses" in adobe["x_data_classes"]
        assert "Passwords" in adobe["x_data_classes"]

    def test_single_breach_count_is_one(self, mock_success_single):
        """x_breach_count is 1 when only one breach is returned."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("victim@example.com", {}))
        assert results[0]["x_breach_count"] == 1

    def test_hunt_result_is_single_sco(self, mock_success):
        """hunt() returns exactly one email-addr SCO (all info embedded)."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        results = asyncio.run(mod.hunt("victim@example.com", {}))
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Request mechanics
# ---------------------------------------------------------------------------

class TestHIBPRequestMechanics:
    """Verify the HTTP request is constructed correctly."""

    def test_api_request_uses_correct_url(self, mock_success):
        """GET is called with the HIBP v3 breachedaccount endpoint."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("victim@example.com", {}))
        url = mock_success.get.call_args.args[0]
        assert "haveibeenpwned.com/api/v3/breachedaccount/" in url
        assert "victim@example.com" in url

    def test_api_key_header_is_set(self, mock_success):
        """hibp-api-key header is set from config."""
        mod = HIBP()
        mod.initialize({"api_key": "my-secret-key"})
        asyncio.run(mod.hunt("victim@example.com", {}))
        headers = mock_success.get.call_args.kwargs.get("headers", {})
        assert headers.get("hibp-api-key") == "my-secret-key"

    def test_user_agent_header_is_set(self, mock_success):
        """user-agent header tracks the canonical runtime version."""
        from adversary_pursuit import __version__

        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("victim@example.com", {}))
        headers = mock_success.get.call_args.kwargs.get("headers", {})
        assert headers.get("user-agent") == f"adversary-pursuit/{__version__}"

    def test_truncate_false_omits_query_param(self, mock_success):
        """Default TRUNCATE=false does not send truncateResponse param."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("victim@example.com", {}))
        params = mock_success.get.call_args.kwargs.get("params", {})
        # truncateResponse should not be "true"
        assert params.get("truncateResponse") != "true"

    def test_truncate_true_sends_query_param(self, mock_success):
        """TRUNCATE=true sends truncateResponse=true query parameter."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("victim@example.com", {"TRUNCATE": "true"}))
        params = mock_success.get.call_args.kwargs.get("params", {})
        assert params.get("truncateResponse") == "true"

    def test_include_unverified_sends_query_param(self, mock_success):
        """INCLUDE_UNVERIFIED=true sends includeUnverified=true param."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("victim@example.com", {}))
        params = mock_success.get.call_args.kwargs.get("params", {})
        assert params.get("includeUnverified") == "true"

    def test_include_unverified_false_sends_false_param(self, mock_success):
        """INCLUDE_UNVERIFIED=false sends includeUnverified=false param."""
        mod = HIBP()
        mod.initialize({"api_key": "test-key"})
        asyncio.run(mod.hunt("victim@example.com", {"INCLUDE_UNVERIFIED": "false"}))
        params = mock_success.get.call_args.kwargs.get("params", {})
        assert params.get("includeUnverified") == "false"


# ---------------------------------------------------------------------------
# Plugin manager integration test
# ---------------------------------------------------------------------------

class TestHIBPDiscovery:
    """HIBP is discoverable via PluginManager."""

    def test_discoverable_via_plugin_manager(self):
        """PluginManager.load_plugins() finds osint/hibp."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/hibp")
        assert mod is not None

    def test_plugin_manager_returns_hibp_instance(self):
        """get_module('osint/hibp') returns a HIBP instance."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/hibp")
        assert isinstance(mod, HIBP)

    def test_production_sequence_load_search_get_initialize(self):
        """Production sequence: load_plugins -> search('hibp') -> get -> initialize."""
        mgr = PluginManager()
        mgr.load_plugins()

        results = mgr.search("hibp")
        assert len(results) >= 1
        names = [r["name"] for r in results]
        assert "osint/hibp" in names

        mod = mgr.get_module("osint/hibp")
        assert mod is not None
        mod.initialize({"api_key": "test-key"})
        assert mod._config["api_key"] == "test-key"
