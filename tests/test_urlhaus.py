"""Tests for the URLhaus CTI module (Issue #61).

# @mock-exempt: httpx.AsyncClient is an external HTTP boundary (URLhaus API).
# Tests must run without network access. Mocking the HTTP layer is the only way
# to exercise all status-code paths (200/listed, 200/no_results, 200/whitelisted,
# 429) hermetically. Follows Sacred Practice #5: mocks are permitted only for
# external boundaries.

Production sequence: PluginManager.load_plugins() -> get_module('cti/urlhaus') ->
initialize({}) -> hunt(target, options). URLhaus requires no API key so initialize
is called with an empty dict.

@decision DEC-TEST-URLHAUS-001
@title Monkeypatch httpx.AsyncClient for hermetic URLhaus tests
@status accepted
@rationale URLhaus exposes a keyless POST endpoint. unittest.mock.patch on
           httpx.AsyncClient exercises 200/is_listed, 200/no_results,
           200/is_whitelisted, and 429 branches without live network access.
           The patch target is adversary_pursuit.modules.cti.urlhaus's httpx
           import so the AsyncClient constructor call is intercepted at the
           call site. Mirrors DEC-TEST-GREYNOISE-001.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adversary_pursuit.core.plugin_mgr import PluginManager
from adversary_pursuit.modules.base import PursuitModule, RateLimitError
from adversary_pursuit.modules.cti.urlhaus import URLHaus, _build_url_sco

# ---------------------------------------------------------------------------
# Sample API responses
# ---------------------------------------------------------------------------

_HOST_LISTED_RESPONSE = {
    "query_status": "is_listed",
    "urlhaus_reference": "https://urlhaus.abuse.ch/host/evil.example.com/",
    "urls": [
        {
            "url": "http://evil.example.com/malware.exe",
            "url_status": "online",
            "date_added": "2026-05-01 12:00:00 UTC",
            "threat": "malware_download",
            "reporter": "reporter1",
            "tags": ["emotet", "botnet"],
        },
        {
            "url": "http://evil.example.com/payload.zip",
            "url_status": "online",
            "date_added": "2026-05-02 08:00:00 UTC",
            "threat": "malware_download",
            "reporter": "reporter2",
            "tags": ["trickbot"],
        },
    ],
}

_URL_LISTED_RESPONSE = {
    "query_status": "is_listed",
    "urlhaus_reference": "https://urlhaus.abuse.ch/url/12345/",
    "urls": [
        {
            "url": "http://evil.example.com/malware.exe",
            "url_status": "online",
            "date_added": "2026-05-01 12:00:00 UTC",
            "threat": "malware_download",
            "reporter": "reporter1",
            "tags": ["emotet"],
        },
    ],
}

_NO_RESULTS_RESPONSE = {
    "query_status": "no_results",
}

_WHITELISTED_RESPONSE = {
    "query_status": "is_whitelisted",
}


def _make_mock_response(
    status_code: int,
    body: dict | None = None,
    headers: dict | None = None,
) -> MagicMock:
    """Build a mock httpx.Response-like object for URLhaus API responses."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.headers = headers or {}
    mock_resp.json.return_value = body or {}
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def _make_mock_client(mock_resp: MagicMock) -> AsyncMock:
    """Build a mock httpx.AsyncClient that returns mock_resp from .post()."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


@pytest.fixture
def mock_host_listed():
    """Patch httpx.AsyncClient to return a host is_listed 200 response."""
    mock_resp = _make_mock_response(200, _HOST_LISTED_RESPONSE)
    mock_client = _make_mock_client(mock_resp)
    with patch(
        "adversary_pursuit.modules.cti.urlhaus.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def mock_url_listed():
    """Patch httpx.AsyncClient to return a URL is_listed 200 response."""
    mock_resp = _make_mock_response(200, _URL_LISTED_RESPONSE)
    mock_client = _make_mock_client(mock_resp)
    with patch(
        "adversary_pursuit.modules.cti.urlhaus.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def mock_no_results():
    """Patch httpx.AsyncClient to return no_results 200 response."""
    mock_resp = _make_mock_response(200, _NO_RESULTS_RESPONSE)
    mock_client = _make_mock_client(mock_resp)
    with patch(
        "adversary_pursuit.modules.cti.urlhaus.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def mock_whitelisted():
    """Patch httpx.AsyncClient to return is_whitelisted 200 response."""
    mock_resp = _make_mock_response(200, _WHITELISTED_RESPONSE)
    mock_client = _make_mock_client(mock_resp)
    with patch(
        "adversary_pursuit.modules.cti.urlhaus.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def mock_429():
    """Patch httpx.AsyncClient to return 429 with Retry-After header."""
    mock_resp = _make_mock_response(
        429,
        {"message": "Rate limit exceeded."},
        headers={"Retry-After": "3600"},
    )
    mock_client = _make_mock_client(mock_resp)
    with patch(
        "adversary_pursuit.modules.cti.urlhaus.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def mock_429_no_header():
    """Patch httpx.AsyncClient to return 429 without Retry-After header."""
    mock_resp = _make_mock_response(
        429,
        {"message": "Rate limit."},
        headers={},
    )
    mock_client = _make_mock_client(mock_resp)
    with patch(
        "adversary_pursuit.modules.cti.urlhaus.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


# ---------------------------------------------------------------------------
# TestURLHausMetadata — protocol and metadata checks
# ---------------------------------------------------------------------------


class TestURLHausMetadata:
    """URLHaus satisfies PursuitModule protocol and declares correct metadata."""

    def test_satisfies_protocol(self):
        """URLHaus must satisfy PursuitModule isinstance check."""
        mod = URLHaus()
        assert isinstance(mod, PursuitModule)

    def test_module_name(self):
        """Module name must be exactly 'cti/urlhaus'."""
        mod = URLHaus()
        assert mod.name == "cti/urlhaus"

    def test_module_type(self):
        mod = URLHaus()
        assert mod.module_type == "cti"

    def test_requires_api_key_is_false(self):
        """URLHaus is keyless — requires_api_key must be False."""
        mod = URLHaus()
        assert mod.requires_api_key is False

    def test_description_non_empty(self):
        mod = URLHaus()
        assert mod.description

    def test_options_has_target(self):
        """Options dict must include a required TARGET key."""
        mod = URLHaus()
        assert "TARGET" in mod.options
        assert mod.options["TARGET"]["required"] is True

    def test_options_target_default_empty_string(self):
        mod = URLHaus()
        assert mod.options["TARGET"]["default"] == ""


# ---------------------------------------------------------------------------
# TestURLHausHappyPathHost — host query that returns is_listed
# ---------------------------------------------------------------------------


class TestURLHausHappyPathHost:
    """hunt() with a host target and is_listed response returns url SCOs."""

    def test_hunt_returns_list(self, mock_host_listed):
        mod = URLHaus()
        mod.initialize({})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert isinstance(results, list)

    def test_hunt_host_returns_two_scos(self, mock_host_listed):
        mod = URLHaus()
        mod.initialize({})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert len(results) == 2

    def test_hunt_sco_type_is_url(self, mock_host_listed):
        mod = URLHaus()
        mod.initialize({})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        for sco in results:
            assert sco["type"] == "url"

    def test_hunt_sco_id_has_url_prefix(self, mock_host_listed):
        mod = URLHaus()
        mod.initialize({})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        for sco in results:
            assert sco["id"].startswith("url--")

    def test_hunt_sco_value_matches_url_entries(self, mock_host_listed):
        mod = URLHaus()
        mod.initialize({})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        values = {r["value"] for r in results}
        assert "http://evil.example.com/malware.exe" in values
        assert "http://evil.example.com/payload.zip" in values

    def test_hunt_sco_has_x_abuse_tags(self, mock_host_listed):
        mod = URLHaus()
        mod.initialize({})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        for sco in results:
            assert "x_abuse_tags" in sco
            assert isinstance(sco["x_abuse_tags"], list)

    def test_hunt_sco_has_x_abuse_threat(self, mock_host_listed):
        mod = URLHaus()
        mod.initialize({})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert results[0]["x_abuse_threat"] == "malware_download"

    def test_hunt_sco_has_x_abuse_reporter(self, mock_host_listed):
        mod = URLHaus()
        mod.initialize({})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert results[0]["x_abuse_reporter"] == "reporter1"

    def test_hunt_sco_has_x_abuse_dateadded(self, mock_host_listed):
        mod = URLHaus()
        mod.initialize({})
        results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert results[0]["x_abuse_dateadded"] == "2026-05-01 12:00:00 UTC"


# ---------------------------------------------------------------------------
# TestURLHausHappyPathURL — URL-typed target dispatch
# ---------------------------------------------------------------------------


class TestURLHausHappyPathURL:
    """hunt() with a full URL target uses the /v1/url/ endpoint."""

    def test_url_target_calls_url_endpoint(self, mock_url_listed):
        mod = URLHaus()
        mod.initialize({})
        asyncio.run(mod.hunt("http://evil.example.com/malware.exe", {}))
        called_url = mock_url_listed.post.call_args.args[0]
        assert "/v1/url/" in called_url

    def test_url_target_sends_url_key_in_payload(self, mock_url_listed):
        mod = URLHaus()
        mod.initialize({})
        asyncio.run(mod.hunt("http://evil.example.com/malware.exe", {}))
        kwargs = mock_url_listed.post.call_args.kwargs
        assert kwargs["json"]["url"] == "http://evil.example.com/malware.exe"

    def test_host_target_calls_host_endpoint(self, mock_host_listed):
        mod = URLHaus()
        mod.initialize({})
        asyncio.run(mod.hunt("evil.example.com", {}))
        called_url = mock_host_listed.post.call_args.args[0]
        assert "/v1/host/" in called_url

    def test_host_target_sends_host_key_in_payload(self, mock_host_listed):
        mod = URLHaus()
        mod.initialize({})
        asyncio.run(mod.hunt("evil.example.com", {}))
        kwargs = mock_host_listed.post.call_args.kwargs
        assert kwargs["json"]["host"] == "evil.example.com"


# ---------------------------------------------------------------------------
# TestURLHausEmptyResults — no_results and whitelisted map to empty list
# ---------------------------------------------------------------------------


class TestURLHausEmptyResults:
    """hunt() with no_results or is_whitelisted returns an empty list."""

    def test_no_results_returns_empty_list(self, mock_no_results):
        mod = URLHaus()
        mod.initialize({})
        results = asyncio.run(mod.hunt("clean.example.com", {}))
        assert results == []

    def test_whitelisted_returns_empty_list(self, mock_whitelisted):
        mod = URLHaus()
        mod.initialize({})
        results = asyncio.run(mod.hunt("trusted.example.com", {}))
        assert results == []

    def test_empty_urls_array_returns_empty_list(self):
        """An is_listed response with an empty urls array returns []."""
        empty_listed = {"query_status": "is_listed", "urls": []}
        mock_resp = _make_mock_response(200, empty_listed)
        mock_client = _make_mock_client(mock_resp)
        with patch(
            "adversary_pursuit.modules.cti.urlhaus.httpx.AsyncClient",
            return_value=mock_client,
        ):
            mod = URLHaus()
            mod.initialize({})
            results = asyncio.run(mod.hunt("empty.example.com", {}))
        assert results == []


# ---------------------------------------------------------------------------
# TestURLHausRateLimit — 429 handling
# ---------------------------------------------------------------------------


class TestURLHausRateLimit:
    """hunt() on 429 raises RateLimitError with correct retry_after."""

    def test_429_raises_rate_limit_error(self, mock_429):
        mod = URLHaus()
        mod.initialize({})
        with pytest.raises(RateLimitError):
            asyncio.run(mod.hunt("evil.example.com", {}))

    def test_429_retry_after_populated(self, mock_429):
        mod = URLHaus()
        mod.initialize({})
        with pytest.raises(RateLimitError) as exc_info:
            asyncio.run(mod.hunt("evil.example.com", {}))
        assert exc_info.value.retry_after == 3600

    def test_429_no_header_retry_after_is_none(self, mock_429_no_header):
        mod = URLHaus()
        mod.initialize({})
        with pytest.raises(RateLimitError) as exc_info:
            asyncio.run(mod.hunt("evil.example.com", {}))
        assert exc_info.value.retry_after is None


# ---------------------------------------------------------------------------
# TestURLHausBuildSco — unit tests for _build_url_sco helper
# ---------------------------------------------------------------------------


class TestURLHausBuildSco:
    """Unit tests for the _build_url_sco internal helper."""

    def test_id_is_deterministic(self):
        """Same URL always produces the same SCO id (uuid5-based)."""
        entry: dict[str, Any] = {
            "threat": "malware_download",
            "reporter": "r1",
            "date_added": "2026-01-01",
        }
        sco1 = _build_url_sco("http://example.com/bad.exe", entry)
        sco2 = _build_url_sco("http://example.com/bad.exe", entry)
        assert sco1["id"] == sco2["id"]

    def test_different_urls_different_ids(self):
        """Different URL values produce different SCO IDs."""
        entry: dict[str, Any] = {"threat": "malware_download"}
        sco1 = _build_url_sco("http://example.com/a.exe", entry)
        sco2 = _build_url_sco("http://example.com/b.exe", entry)
        assert sco1["id"] != sco2["id"]

    def test_tags_string_normalised_to_list(self):
        """If the tags field is a plain string, it is wrapped in a list."""
        entry: dict[str, Any] = {"tags": "emotet"}
        sco = _build_url_sco("http://example.com/x.exe", entry)
        assert isinstance(sco["x_abuse_tags"], list)
        assert "emotet" in sco["x_abuse_tags"]

    def test_tags_none_becomes_empty_list(self):
        """If tags is None/missing, x_abuse_tags is an empty list."""
        entry: dict[str, Any] = {"tags": None}
        sco = _build_url_sco("http://example.com/x.exe", entry)
        assert sco["x_abuse_tags"] == []

    def test_sco_type_is_url(self):
        sco = _build_url_sco("http://example.com/x.exe", {})
        assert sco["type"] == "url"


# ---------------------------------------------------------------------------
# TestURLHausDedup — duplicate URL entries in same response
# ---------------------------------------------------------------------------


class TestURLHausDedup:
    """hunt() deduplicates entries with the same URL value."""

    def test_duplicate_urls_deduplicated(self):
        """Two entries with the same URL produce only one SCO."""
        dup_response = {
            "query_status": "is_listed",
            "urls": [
                {"url": "http://dup.example.com/bad.exe", "threat": "t1"},
                {"url": "http://dup.example.com/bad.exe", "threat": "t2"},
            ],
        }
        mock_resp = _make_mock_response(200, dup_response)
        mock_client = _make_mock_client(mock_resp)
        with patch(
            "adversary_pursuit.modules.cti.urlhaus.httpx.AsyncClient",
            return_value=mock_client,
        ):
            mod = URLHaus()
            mod.initialize({})
            results = asyncio.run(mod.hunt("dup.example.com", {}))
        assert len(results) == 1


# ---------------------------------------------------------------------------
# TestURLHausDiscovery — PluginManager integration (compound interaction)
# ---------------------------------------------------------------------------


class TestURLHausDiscovery:
    """URLHaus is discoverable via PluginManager (production plug-in loading sequence).

    This is the Compound-Interaction Test: exercises the full sequence
    PluginManager.load_plugins() -> get_module() -> initialize() -> hunt()
    crossing PluginManager, BaseModule, and URLHaus boundaries.
    """

    def test_discoverable_via_plugin_manager(self):
        """PluginManager.load_plugins() finds cti/urlhaus."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("cti/urlhaus")
        assert mod is not None

    def test_plugin_manager_returns_urlhaus_instance(self):
        """get_module('cti/urlhaus') returns a URLHaus instance."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("cti/urlhaus")
        assert isinstance(mod, URLHaus)

    def test_production_sequence_load_initialize_hunt(self):
        """Full production sequence: load_plugins -> get -> initialize -> hunt (mocked HTTP).

        Compound-interaction test: crosses PluginManager, BaseModule.initialize(),
        and URLHaus.hunt() boundaries in the real production call order.
        """
        response_data = {"query_status": "no_results"}
        mock_resp = _make_mock_response(200, response_data)
        mock_client = _make_mock_client(mock_resp)

        mgr = PluginManager()
        mgr.load_plugins()

        mod = mgr.get_module("cti/urlhaus")
        assert mod is not None

        mod.initialize({})  # keyless — no API key needed

        with patch(
            "adversary_pursuit.modules.cti.urlhaus.httpx.AsyncClient",
            return_value=mock_client,
        ):
            results = asyncio.run(mod.hunt("safe.example.com", {}))

        assert isinstance(results, list)
        assert results == []  # no_results → empty list
