"""Tests for the crt.sh OSINT module (Issue #61).

# @mock-exempt: httpx.AsyncClient is an external HTTP boundary (crt.sh CT log API).
# Tests must run without network access. Mocking the HTTP layer is the only way
# to exercise all branches (200/results, 200/empty, 404, 429, HTML response,
# _MAX_RESULTS cap) hermetically. Follows Sacred Practice #5: mocks are permitted
# only for external boundaries.

Production sequence: PluginManager.load_plugins() -> get_module('osint/crtsh') ->
initialize({}) -> hunt(domain, options). crt.sh requires no API key so initialize
is called with an empty dict.

@decision DEC-TEST-CRTSH-001
@title Monkeypatch httpx.AsyncClient for hermetic crt.sh tests
@status accepted
@rationale crt.sh exposes a keyless GET endpoint. unittest.mock.patch on
           httpx.AsyncClient exercises 200/results, 200/empty, 200/HTML,
           404, and 429 branches without live network access. ModuleError
           for HTML responses is also tested per DEC-MODULE-CRTSH-002.
           Mirrors DEC-TEST-GREYNOISE-001 / DEC-TEST-URLHAUS-001.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adversary_pursuit.core.plugin_mgr import PluginManager
from adversary_pursuit.modules.base import ModuleError, PursuitModule, RateLimitError
from adversary_pursuit.modules.osint.crtsh import _MAX_RESULTS, CrtSh, _build_domain_sco

# ---------------------------------------------------------------------------
# Sample crt.sh API response data
# ---------------------------------------------------------------------------

_SAMPLE_ENTRY: dict[str, Any] = {
    "issuer_ca_id": 12345,
    "not_after": "2027-06-01T00:00:00",
    "entry_timestamp": "2026-05-01T08:00:00.000",
    "name_value": "sub.example.com",
    "common_name": "sub.example.com",
}

_MULTI_ENTRY_RESPONSE: list[dict] = [
    {
        "issuer_ca_id": 12345,
        "not_after": "2027-06-01T00:00:00",
        "entry_timestamp": "2026-05-01T08:00:00.000",
        "name_value": "api.example.com",
    },
    {
        "issuer_ca_id": 12346,
        "not_after": "2027-07-01T00:00:00",
        "entry_timestamp": "2026-04-15T10:00:00.000",
        "name_value": "mail.example.com",
    },
    {
        "issuer_ca_id": 12347,
        "not_after": "2027-08-01T00:00:00",
        "entry_timestamp": "2026-03-20T14:00:00.000",
        "name_value": "www.example.com",
    },
]

# Response with a wildcard name_value that should be stripped
_WILDCARD_ENTRY_RESPONSE: list[dict] = [
    {
        "issuer_ca_id": 99999,
        "not_after": "2027-09-01T00:00:00",
        "entry_timestamp": "2026-05-10T09:00:00.000",
        "name_value": "*.example.com",  # Should be stripped to "example.com" and then skipped (seeded)
    },
    {
        "issuer_ca_id": 99998,
        "not_after": "2027-09-01T00:00:00",
        "entry_timestamp": "2026-05-10T09:01:00.000",
        "name_value": "*.staging.example.com",  # Should be stripped to "staging.example.com"
    },
]

# Response with multi-SAN name_value (newline-separated)
_MULTI_SAN_ENTRY_RESPONSE: list[dict] = [
    {
        "issuer_ca_id": 11111,
        "not_after": "2027-06-01T00:00:00",
        "entry_timestamp": "2026-05-01T08:00:00.000",
        "name_value": "a.example.com\nb.example.com\nc.example.com",
    },
]


def _make_mock_response(
    status_code: int,
    body: list | dict | str | None = None,
    headers: dict | None = None,
    is_text: bool = False,
) -> MagicMock:
    """Build a mock httpx.Response-like object for crt.sh API responses."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.headers = headers or {"content-type": "application/json"}
    if is_text:
        mock_resp.text = body or ""
        mock_resp.json.side_effect = ValueError("not JSON")
    else:
        import json

        mock_resp.text = json.dumps(body) if body is not None else "[]"
        mock_resp.json.return_value = body or []
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def _make_mock_client_get(mock_resp: MagicMock) -> AsyncMock:
    """Build a mock httpx.AsyncClient that returns mock_resp from .get()."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


def _patched_client_get(
    body: list | dict | str | None, status_code: int = 200, **kwargs: Any
) -> Any:
    """Context manager: patch httpx.AsyncClient with a GET response."""
    mock_resp = _make_mock_response(status_code, body, **kwargs)
    mock_client = _make_mock_client_get(mock_resp)
    return patch(
        "adversary_pursuit.modules.osint.crtsh.httpx.AsyncClient",
        return_value=mock_client,
    )


@pytest.fixture
def mock_single_result():
    """200 response with a single domain-name CT entry."""
    mock_resp = _make_mock_response(200, [_SAMPLE_ENTRY])
    mock_client = _make_mock_client_get(mock_resp)
    with patch(
        "adversary_pursuit.modules.osint.crtsh.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def mock_multi_result():
    """200 response with three distinct CT entries."""
    mock_resp = _make_mock_response(200, _MULTI_ENTRY_RESPONSE)
    mock_client = _make_mock_client_get(mock_resp)
    with patch(
        "adversary_pursuit.modules.osint.crtsh.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def mock_empty():
    """200 response with empty JSON array."""
    mock_resp = _make_mock_response(200, [])
    mock_client = _make_mock_client_get(mock_resp)
    with patch(
        "adversary_pursuit.modules.osint.crtsh.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def mock_404():
    """404 response."""
    mock_resp = _make_mock_response(404, None)
    mock_client = _make_mock_client_get(mock_resp)
    with patch(
        "adversary_pursuit.modules.osint.crtsh.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def mock_429():
    """429 response with Retry-After header."""
    mock_resp = _make_mock_response(
        429,
        None,
        headers={"Retry-After": "3600", "content-type": "text/plain"},
    )
    mock_client = _make_mock_client_get(mock_resp)
    mock_resp.text = ""
    with patch(
        "adversary_pursuit.modules.osint.crtsh.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def mock_429_no_header():
    """429 response without Retry-After header."""
    mock_resp = _make_mock_response(429, None, headers={"content-type": "text/plain"})
    mock_client = _make_mock_client_get(mock_resp)
    mock_resp.text = ""
    with patch(
        "adversary_pursuit.modules.osint.crtsh.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def mock_html_response():
    """200 response that returns HTML instead of JSON (endpoint degradation)."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
    mock_resp.text = "<html><body>Service Unavailable</body></html>"
    mock_resp.raise_for_status.return_value = None
    mock_client = _make_mock_client_get(mock_resp)
    with patch(
        "adversary_pursuit.modules.osint.crtsh.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


# ---------------------------------------------------------------------------
# TestCrtShMetadata — protocol and metadata checks
# ---------------------------------------------------------------------------


class TestCrtShMetadata:
    """CrtSh satisfies PursuitModule protocol and declares correct metadata."""

    def test_satisfies_protocol(self):
        mod = CrtSh()
        assert isinstance(mod, PursuitModule)

    def test_module_name(self):
        mod = CrtSh()
        assert mod.name == "osint/crtsh"

    def test_module_type(self):
        mod = CrtSh()
        assert mod.module_type == "osint"

    def test_requires_api_key_is_false(self):
        """crt.sh is keyless — requires_api_key must be False."""
        mod = CrtSh()
        assert mod.requires_api_key is False

    def test_description_non_empty(self):
        mod = CrtSh()
        assert mod.description

    def test_options_has_required_target(self):
        mod = CrtSh()
        assert "TARGET" in mod.options
        assert mod.options["TARGET"]["required"] is True

    def test_options_target_default_empty_string(self):
        mod = CrtSh()
        assert mod.options["TARGET"]["default"] == ""


# ---------------------------------------------------------------------------
# TestCrtShHappyPath — successful lookup
# ---------------------------------------------------------------------------


class TestCrtShHappyPath:
    """hunt() with CT log entries returns domain-name SCO dicts."""

    def test_hunt_returns_list(self, mock_single_result):
        mod = CrtSh()
        mod.initialize({})
        results = asyncio.run(mod.hunt("example.com", {}))
        assert isinstance(results, list)

    def test_single_result_returns_one_sco(self, mock_single_result):
        mod = CrtSh()
        mod.initialize({})
        results = asyncio.run(mod.hunt("example.com", {}))
        assert len(results) == 1

    def test_sco_type_is_domain_name(self, mock_single_result):
        mod = CrtSh()
        mod.initialize({})
        results = asyncio.run(mod.hunt("example.com", {}))
        assert results[0]["type"] == "domain-name"

    def test_sco_id_has_domain_name_prefix(self, mock_single_result):
        mod = CrtSh()
        mod.initialize({})
        results = asyncio.run(mod.hunt("example.com", {}))
        assert results[0]["id"].startswith("domain-name--")

    def test_sco_value_matches_name_value(self, mock_single_result):
        mod = CrtSh()
        mod.initialize({})
        results = asyncio.run(mod.hunt("example.com", {}))
        assert results[0]["value"] == "sub.example.com"

    def test_sco_x_crtsh_issuer_ca_id_present(self, mock_single_result):
        mod = CrtSh()
        mod.initialize({})
        results = asyncio.run(mod.hunt("example.com", {}))
        assert "x_crtsh_issuer_ca_id" in results[0]
        assert results[0]["x_crtsh_issuer_ca_id"] == 12345

    def test_sco_x_crtsh_not_after_present(self, mock_single_result):
        mod = CrtSh()
        mod.initialize({})
        results = asyncio.run(mod.hunt("example.com", {}))
        assert "x_crtsh_not_after" in results[0]
        assert results[0]["x_crtsh_not_after"] == "2027-06-01T00:00:00"

    def test_sco_x_crtsh_entry_timestamp_present(self, mock_single_result):
        mod = CrtSh()
        mod.initialize({})
        results = asyncio.run(mod.hunt("example.com", {}))
        assert "x_crtsh_entry_timestamp" in results[0]

    def test_multi_result_returns_correct_count(self, mock_multi_result):
        mod = CrtSh()
        mod.initialize({})
        results = asyncio.run(mod.hunt("example.com", {}))
        assert len(results) == 3

    def test_multi_san_name_value_split(self):
        """Newline-separated SANs in name_value produce one SCO per unique name."""
        mod = CrtSh()
        mod.initialize({})
        with _patched_client_get(_MULTI_SAN_ENTRY_RESPONSE):
            results = asyncio.run(mod.hunt("example.com", {}))
        values = {r["value"] for r in results}
        assert "a.example.com" in values
        assert "b.example.com" in values
        assert "c.example.com" in values


# ---------------------------------------------------------------------------
# TestCrtShWildcardStripping — wildcard prefix removal
# ---------------------------------------------------------------------------


class TestCrtShWildcardStripping:
    """Wildcard SANs ('*.sub.example.com') are stripped before dedup/SCO creation."""

    def test_wildcard_stripped_produces_subdomain_sco(self):
        """'*.staging.example.com' → 'staging.example.com' as SCO value."""
        mod = CrtSh()
        mod.initialize({})
        with _patched_client_get(_WILDCARD_ENTRY_RESPONSE):
            results = asyncio.run(mod.hunt("example.com", {}))
        values = {r["value"] for r in results}
        # *.example.com → example.com which is seeded → skipped
        assert "example.com" not in values
        # *.staging.example.com → staging.example.com → kept
        assert "staging.example.com" in values

    def test_wildcard_apex_domain_seeded_and_skipped(self):
        """'*.example.com' stripped to 'example.com' is seeded (= query target) and excluded."""
        mod = CrtSh()
        mod.initialize({})
        with _patched_client_get(_WILDCARD_ENTRY_RESPONSE):
            results = asyncio.run(mod.hunt("example.com", {}))
        for r in results:
            assert r["value"] != "example.com"


# ---------------------------------------------------------------------------
# TestCrtShEmptyResults — empty and null responses
# ---------------------------------------------------------------------------


class TestCrtShEmptyResults:
    """hunt() with no CT log entries returns an empty list."""

    def test_empty_array_returns_empty_list(self, mock_empty):
        mod = CrtSh()
        mod.initialize({})
        results = asyncio.run(mod.hunt("newdomain.example.com", {}))
        assert results == []

    def test_404_returns_empty_list(self, mock_404):
        """404 from crt.sh is treated as 'no CT records' — returns []."""
        mod = CrtSh()
        mod.initialize({})
        results = asyncio.run(mod.hunt("unknown.example.com", {}))
        assert results == []

    def test_null_body_returns_empty_list(self):
        """'null' JSON body (no records) returns []."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.text = "null"
        mock_resp.raise_for_status.return_value = None
        mock_client = _make_mock_client_get(mock_resp)
        with patch(
            "adversary_pursuit.modules.osint.crtsh.httpx.AsyncClient",
            return_value=mock_client,
        ):
            mod = CrtSh()
            mod.initialize({})
            results = asyncio.run(mod.hunt("example.com", {}))
        assert results == []


# ---------------------------------------------------------------------------
# TestCrtShHTMLError — HTML response raises ModuleError (DEC-MODULE-CRTSH-002)
# ---------------------------------------------------------------------------


class TestCrtShHTMLError:
    """crt.sh returning HTML (endpoint degradation) raises ModuleError."""

    def test_html_content_type_raises_module_error(self, mock_html_response):
        """HTTP 200 with Content-Type: text/html raises ModuleError."""
        mod = CrtSh()
        mod.initialize({})
        with pytest.raises(ModuleError, match="HTML"):
            asyncio.run(mod.hunt("example.com", {}))

    def test_html_body_without_content_type_header_raises_module_error(self):
        """Body starting with '<' raises ModuleError even without html content-type."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}  # misleading header
        mock_resp.text = "<html>some error page</html>"
        mock_resp.raise_for_status.return_value = None
        mock_client = _make_mock_client_get(mock_resp)
        with patch(
            "adversary_pursuit.modules.osint.crtsh.httpx.AsyncClient",
            return_value=mock_client,
        ):
            mod = CrtSh()
            mod.initialize({})
            with pytest.raises(ModuleError):
                asyncio.run(mod.hunt("example.com", {}))


# ---------------------------------------------------------------------------
# TestCrtShRateLimit — 429 response handling
# ---------------------------------------------------------------------------


class TestCrtShRateLimit:
    """hunt() on 429 raises RateLimitError with correct retry_after."""

    def test_429_raises_rate_limit_error(self, mock_429):
        mod = CrtSh()
        mod.initialize({})
        with pytest.raises(RateLimitError):
            asyncio.run(mod.hunt("example.com", {}))

    def test_429_retry_after_populated(self, mock_429):
        mod = CrtSh()
        mod.initialize({})
        with pytest.raises(RateLimitError) as exc_info:
            asyncio.run(mod.hunt("example.com", {}))
        assert exc_info.value.retry_after == 3600

    def test_429_no_header_retry_after_is_none(self, mock_429_no_header):
        mod = CrtSh()
        mod.initialize({})
        with pytest.raises(RateLimitError) as exc_info:
            asyncio.run(mod.hunt("example.com", {}))
        assert exc_info.value.retry_after is None


# ---------------------------------------------------------------------------
# TestCrtShResultCap — _MAX_RESULTS enforcement
# ---------------------------------------------------------------------------


class TestCrtShResultCap:
    """hunt() caps results at _MAX_RESULTS (50) per call."""

    def test_results_capped_at_max(self):
        """A response with >50 entries produces at most _MAX_RESULTS SCOs."""
        large_response = [
            {
                "issuer_ca_id": i,
                "not_after": "2027-01-01",
                "entry_timestamp": "2026-01-01",
                "name_value": f"sub{i}.example.com",
            }
            for i in range(1, _MAX_RESULTS + 20)  # 69 entries
        ]
        mod = CrtSh()
        mod.initialize({})
        with _patched_client_get(large_response):
            results = asyncio.run(mod.hunt("example.com", {}))
        assert len(results) <= _MAX_RESULTS

    def test_max_results_constant_is_50(self):
        """_MAX_RESULTS is 50 per DEC-MODULE-CRTSH-003."""
        assert _MAX_RESULTS == 50


# ---------------------------------------------------------------------------
# TestCrtShDedup — duplicate name_value entries
# ---------------------------------------------------------------------------


class TestCrtShDedup:
    """hunt() deduplicates name_value entries across CT log records."""

    def test_duplicate_name_values_deduplicated(self):
        """Two certs with the same name_value produce only one SCO."""
        dup_response = [
            {
                "issuer_ca_id": 1,
                "not_after": "2027-01-01",
                "entry_timestamp": "2026-01-01",
                "name_value": "dup.example.com",
            },
            {
                "issuer_ca_id": 2,
                "not_after": "2027-06-01",
                "entry_timestamp": "2026-02-01",
                "name_value": "dup.example.com",
            },
        ]
        mod = CrtSh()
        mod.initialize({})
        with _patched_client_get(dup_response):
            results = asyncio.run(mod.hunt("example.com", {}))
        assert len(results) == 1


# ---------------------------------------------------------------------------
# TestCrtShBuildDomainSco — unit tests for _build_domain_sco helper
# ---------------------------------------------------------------------------


class TestCrtShBuildDomainSco:
    """Unit tests for the _build_domain_sco internal helper."""

    def test_id_is_deterministic(self):
        """Same name always produces the same SCO id."""
        sco1 = _build_domain_sco("sub.example.com", _SAMPLE_ENTRY)
        sco2 = _build_domain_sco("sub.example.com", _SAMPLE_ENTRY)
        assert sco1["id"] == sco2["id"]

    def test_different_names_different_ids(self):
        """Different names produce different SCO IDs."""
        sco1 = _build_domain_sco("a.example.com", _SAMPLE_ENTRY)
        sco2 = _build_domain_sco("b.example.com", _SAMPLE_ENTRY)
        assert sco1["id"] != sco2["id"]

    def test_id_has_domain_name_prefix(self):
        sco = _build_domain_sco("sub.example.com", _SAMPLE_ENTRY)
        assert sco["id"].startswith("domain-name--")

    def test_value_matches_name(self):
        sco = _build_domain_sco("sub.example.com", _SAMPLE_ENTRY)
        assert sco["value"] == "sub.example.com"

    def test_issuer_ca_id_is_int(self):
        sco = _build_domain_sco("sub.example.com", _SAMPLE_ENTRY)
        assert isinstance(sco["x_crtsh_issuer_ca_id"], int)
        assert sco["x_crtsh_issuer_ca_id"] == 12345

    def test_missing_issuer_ca_id_defaults_zero(self):
        """Missing issuer_ca_id in entry defaults to 0 (not None or error)."""
        sco = _build_domain_sco("sub.example.com", {})
        assert sco["x_crtsh_issuer_ca_id"] == 0


# ---------------------------------------------------------------------------
# TestCrtShRequestShape — HTTP request structure
# ---------------------------------------------------------------------------


class TestCrtShRequestShape:
    """Verify the HTTP request shape emitted to crt.sh."""

    def test_method_is_get(self, mock_single_result):
        mod = CrtSh()
        mod.initialize({})
        asyncio.run(mod.hunt("example.com", {}))
        mock_single_result.get.assert_called_once()

    def test_output_param_is_json(self, mock_single_result):
        mod = CrtSh()
        mod.initialize({})
        asyncio.run(mod.hunt("example.com", {}))
        call_kwargs = mock_single_result.get.call_args.kwargs
        assert call_kwargs["params"]["output"] == "json"

    def test_query_param_includes_wildcard_prefix(self, mock_single_result):
        mod = CrtSh()
        mod.initialize({})
        asyncio.run(mod.hunt("example.com", {}))
        call_kwargs = mock_single_result.get.call_args.kwargs
        # The query should be "%.example.com" to get subdomains
        assert "example.com" in call_kwargs["params"]["q"]
        assert call_kwargs["params"]["q"].startswith("%.")


# ---------------------------------------------------------------------------
# TestCrtShDiscovery — PluginManager integration (compound interaction)
# ---------------------------------------------------------------------------


class TestCrtShDiscovery:
    """CrtSh is discoverable via PluginManager (production plug-in loading sequence).

    Compound-interaction test: crosses PluginManager.load_plugins() -> get_module()
    -> initialize() -> hunt() boundaries in the real production call order.
    """

    def test_discoverable_via_plugin_manager(self):
        """PluginManager.load_plugins() finds osint/crtsh."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/crtsh")
        assert mod is not None

    def test_plugin_manager_returns_crtsh_instance(self):
        """get_module('osint/crtsh') returns a CrtSh instance."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/crtsh")
        assert isinstance(mod, CrtSh)

    def test_production_sequence_load_initialize_hunt(self):
        """Full sequence: load_plugins -> get -> initialize -> hunt (mocked HTTP)."""
        mgr = PluginManager()
        mgr.load_plugins()

        mod = mgr.get_module("osint/crtsh")
        assert mod is not None

        mod.initialize({})  # keyless

        with _patched_client_get([]):
            results = asyncio.run(mod.hunt("newdomain.example.com", {}))

        assert isinstance(results, list)
        assert results == []
