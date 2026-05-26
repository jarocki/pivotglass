"""Tests for the ThreatFox CTI module (Issue #61).

# @mock-exempt: httpx.AsyncClient is an external HTTP boundary (ThreatFox API).
# Tests must run without network access. Mocking the HTTP layer is the only way
# to exercise all branches (200/ok, 200/no_results, 429, ioc_type dispatch)
# hermetically. Follows Sacred Practice #5: mocks are permitted only for
# external boundaries.

Production sequence: PluginManager.load_plugins() -> get_module('cti/threatfox') ->
initialize({}) -> hunt(target, options). ThreatFox requires no API key so
initialize is called with an empty dict.

@decision DEC-TEST-THREATFOX-001
@title Monkeypatch httpx.AsyncClient for hermetic ThreatFox tests
@status accepted
@rationale ThreatFox exposes a keyless POST endpoint. unittest.mock.patch on
           httpx.AsyncClient exercises 200/ok-with-data, 200/no_results, 429,
           and all ioc_type dispatch branches (ip:port, url, domain, md5_hash,
           sha256_hash, unknown) without live network access. Mirrors
           DEC-TEST-GREYNOISE-001 / DEC-TEST-URLHAUS-001.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adversary_pursuit.core.plugin_mgr import PluginManager
from adversary_pursuit.modules.base import PursuitModule, RateLimitError
from adversary_pursuit.modules.cti.threatfox import ThreatFox, _build_common_fields, _build_sco

# ---------------------------------------------------------------------------
# Sample API responses
# ---------------------------------------------------------------------------


def _make_ioc_record(ioc_value: str, ioc_type: str, **kwargs: Any) -> dict:
    base: dict[str, Any] = {
        "ioc": ioc_value,
        "ioc_type": ioc_type,
        "malware": "Emotet",
        "confidence_level": 85,
        "first_seen": "2026-05-01 12:00:00 UTC",
        "last_seen": "2026-05-15 08:00:00 UTC",
        "reporter": "threatfox_user",
        "tags": ["botnet", "c2"],
    }
    base.update(kwargs)
    return base


_IP_PORT_RESPONSE = {
    "query_status": "ok",
    "data": [
        _make_ioc_record("192.168.1.1:4444", "ip:port"),
    ],
}

_URL_RESPONSE = {
    "query_status": "ok",
    "data": [
        _make_ioc_record("http://evil.example.com/c2", "url"),
    ],
}

_DOMAIN_RESPONSE = {
    "query_status": "ok",
    "data": [
        _make_ioc_record("evil.example.com", "domain"),
    ],
}

_MD5_RESPONSE = {
    "query_status": "ok",
    "data": [
        _make_ioc_record("d41d8cd98f00b204e9800998ecf8427e", "md5_hash"),
    ],
}

_SHA256_RESPONSE = {
    "query_status": "ok",
    "data": [
        _make_ioc_record(
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "sha256_hash",
        ),
    ],
}

_NO_RESULTS_RESPONSE: dict[str, Any] = {
    "query_status": "no_results",
    "data": [],
}

_MULTI_IOC_RESPONSE = {
    "query_status": "ok",
    "data": [
        _make_ioc_record("192.168.1.1:4444", "ip:port"),
        _make_ioc_record("evil.example.com", "domain"),
        _make_ioc_record("http://evil.example.com/c2", "url"),
    ],
}

_DUP_RESPONSE = {
    "query_status": "ok",
    "data": [
        _make_ioc_record("192.168.1.1:4444", "ip:port", malware="Emotet"),
        _make_ioc_record("192.168.1.1:4444", "ip:port", malware="TrickBot"),
    ],
}


def _make_mock_response(
    status_code: int,
    body: dict | None = None,
    headers: dict | None = None,
) -> MagicMock:
    """Build a mock httpx.Response-like object for ThreatFox API responses."""
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


def _patched_client(body: dict) -> Any:
    """Context manager: patch httpx.AsyncClient with a 200 body response."""
    mock_resp = _make_mock_response(200, body)
    mock_client = _make_mock_client(mock_resp)
    return patch(
        "adversary_pursuit.modules.cti.threatfox.httpx.AsyncClient",
        return_value=mock_client,
    )


@pytest.fixture
def mock_ip_port():
    """200 response with a single ip:port IOC record."""
    mock_resp = _make_mock_response(200, _IP_PORT_RESPONSE)
    mock_client = _make_mock_client(mock_resp)
    with patch(
        "adversary_pursuit.modules.cti.threatfox.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def mock_no_results():
    """200 response with no_results status."""
    mock_resp = _make_mock_response(200, _NO_RESULTS_RESPONSE)
    mock_client = _make_mock_client(mock_resp)
    with patch(
        "adversary_pursuit.modules.cti.threatfox.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def mock_429():
    """429 response with Retry-After header."""
    mock_resp = _make_mock_response(
        429,
        {"message": "Rate limit exceeded."},
        headers={"Retry-After": "3600"},
    )
    mock_client = _make_mock_client(mock_resp)
    with patch(
        "adversary_pursuit.modules.cti.threatfox.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


@pytest.fixture
def mock_429_no_header():
    """429 response without Retry-After header."""
    mock_resp = _make_mock_response(429, {}, headers={})
    mock_client = _make_mock_client(mock_resp)
    with patch(
        "adversary_pursuit.modules.cti.threatfox.httpx.AsyncClient",
        return_value=mock_client,
    ):
        yield mock_client


# ---------------------------------------------------------------------------
# TestThreatFoxMetadata — protocol and metadata checks
# ---------------------------------------------------------------------------


class TestThreatFoxMetadata:
    """ThreatFox satisfies PursuitModule protocol and declares correct metadata."""

    def test_satisfies_protocol(self):
        mod = ThreatFox()
        assert isinstance(mod, PursuitModule)

    def test_module_name(self):
        mod = ThreatFox()
        assert mod.name == "cti/threatfox"

    def test_module_type(self):
        mod = ThreatFox()
        assert mod.module_type == "cti"

    def test_requires_api_key_is_false(self):
        """ThreatFox is keyless — requires_api_key must be False."""
        mod = ThreatFox()
        assert mod.requires_api_key is False

    def test_description_non_empty(self):
        mod = ThreatFox()
        assert mod.description

    def test_options_has_required_target(self):
        mod = ThreatFox()
        assert "TARGET" in mod.options
        assert mod.options["TARGET"]["required"] is True

    def test_options_target_default_empty_string(self):
        mod = ThreatFox()
        assert mod.options["TARGET"]["default"] == ""


# ---------------------------------------------------------------------------
# TestThreatFoxIocTypeDispatch — ioc_type → STIX SCO type mapping
# ---------------------------------------------------------------------------


class TestThreatFoxIocTypeDispatch:
    """hunt() maps each ThreatFox ioc_type to the correct STIX SCO type."""

    def test_ip_port_produces_ipv4_addr(self, mock_ip_port):
        mod = ThreatFox()
        mod.initialize({})
        results = asyncio.run(mod.hunt("192.168.1.1:4444", {}))
        assert len(results) == 1
        assert results[0]["type"] == "ipv4-addr"

    def test_ip_port_value_is_ip_only(self, mock_ip_port):
        """For ip:port IOC, SCO value is the IP portion only (not 'IP:port')."""
        mod = ThreatFox()
        mod.initialize({})
        results = asyncio.run(mod.hunt("192.168.1.1:4444", {}))
        assert results[0]["value"] == "192.168.1.1"

    def test_ip_port_has_x_tf_port(self, mock_ip_port):
        """ip:port SCO includes x_tf_port custom field with the port string."""
        mod = ThreatFox()
        mod.initialize({})
        results = asyncio.run(mod.hunt("192.168.1.1:4444", {}))
        assert results[0]["x_tf_port"] == "4444"

    def test_url_ioc_produces_url_sco(self):
        mod = ThreatFox()
        mod.initialize({})
        with _patched_client(_URL_RESPONSE):
            results = asyncio.run(mod.hunt("http://evil.example.com/c2", {}))
        assert len(results) == 1
        assert results[0]["type"] == "url"

    def test_domain_ioc_produces_domain_name_sco(self):
        mod = ThreatFox()
        mod.initialize({})
        with _patched_client(_DOMAIN_RESPONSE):
            results = asyncio.run(mod.hunt("evil.example.com", {}))
        assert len(results) == 1
        assert results[0]["type"] == "domain-name"

    def test_md5_hash_produces_file_sco_with_md5(self):
        mod = ThreatFox()
        mod.initialize({})
        with _patched_client(_MD5_RESPONSE):
            results = asyncio.run(mod.hunt("d41d8cd98f00b204e9800998ecf8427e", {}))
        assert len(results) == 1
        assert results[0]["type"] == "file"
        assert "MD5" in results[0]["hashes"]

    def test_sha256_hash_produces_file_sco_with_sha256(self):
        sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        mod = ThreatFox()
        mod.initialize({})
        with _patched_client(_SHA256_RESPONSE):
            results = asyncio.run(mod.hunt(sha, {}))
        assert len(results) == 1
        assert results[0]["type"] == "file"
        assert "SHA-256" in results[0]["hashes"]

    def test_unknown_ioc_type_skipped(self):
        """An unrecognised ioc_type is skipped and does not produce a SCO."""
        unknown_response = {
            "query_status": "ok",
            "data": [_make_ioc_record("some_value", "unknown_type")],
        }
        mod = ThreatFox()
        mod.initialize({})
        with _patched_client(unknown_response):
            results = asyncio.run(mod.hunt("some_value", {}))
        assert results == []


# ---------------------------------------------------------------------------
# TestThreatFoxCustomFields — x_tf_* field verification
# ---------------------------------------------------------------------------


class TestThreatFoxCustomFields:
    """hunt() includes all x_tf_* custom fields on every SCO type."""

    def test_x_tf_malware_present(self, mock_ip_port):
        mod = ThreatFox()
        mod.initialize({})
        results = asyncio.run(mod.hunt("192.168.1.1:4444", {}))
        assert "x_tf_malware" in results[0]
        assert results[0]["x_tf_malware"] == "Emotet"

    def test_x_tf_confidence_is_int(self, mock_ip_port):
        mod = ThreatFox()
        mod.initialize({})
        results = asyncio.run(mod.hunt("192.168.1.1:4444", {}))
        assert "x_tf_confidence" in results[0]
        assert isinstance(results[0]["x_tf_confidence"], int)
        assert results[0]["x_tf_confidence"] == 85

    def test_x_tf_first_seen_present(self, mock_ip_port):
        mod = ThreatFox()
        mod.initialize({})
        results = asyncio.run(mod.hunt("192.168.1.1:4444", {}))
        assert "x_tf_first_seen" in results[0]
        assert results[0]["x_tf_first_seen"] == "2026-05-01 12:00:00 UTC"

    def test_x_tf_last_seen_present(self, mock_ip_port):
        mod = ThreatFox()
        mod.initialize({})
        results = asyncio.run(mod.hunt("192.168.1.1:4444", {}))
        assert "x_tf_last_seen" in results[0]

    def test_x_tf_reporter_present(self, mock_ip_port):
        mod = ThreatFox()
        mod.initialize({})
        results = asyncio.run(mod.hunt("192.168.1.1:4444", {}))
        assert "x_tf_reporter" in results[0]
        assert results[0]["x_tf_reporter"] == "threatfox_user"

    def test_x_tf_tags_is_list(self, mock_ip_port):
        mod = ThreatFox()
        mod.initialize({})
        results = asyncio.run(mod.hunt("192.168.1.1:4444", {}))
        assert "x_tf_tags" in results[0]
        assert isinstance(results[0]["x_tf_tags"], list)
        assert "botnet" in results[0]["x_tf_tags"]


# ---------------------------------------------------------------------------
# TestThreatFoxEmptyResults — no_results maps to empty list
# ---------------------------------------------------------------------------


class TestThreatFoxEmptyResults:
    """hunt() with no_results or empty data returns an empty list."""

    def test_no_results_returns_empty_list(self, mock_no_results):
        mod = ThreatFox()
        mod.initialize({})
        results = asyncio.run(mod.hunt("clean.example.com", {}))
        assert results == []

    def test_null_data_returns_empty_list(self):
        """data field missing or null returns []."""
        null_data_response = {"query_status": "ok", "data": None}
        mod = ThreatFox()
        mod.initialize({})
        with _patched_client(null_data_response):
            results = asyncio.run(mod.hunt("something", {}))
        assert results == []


# ---------------------------------------------------------------------------
# TestThreatFoxDedup — duplicate IOC entries
# ---------------------------------------------------------------------------


class TestThreatFoxDedup:
    """hunt() deduplicates IOC entries with the same ioc value."""

    def test_duplicate_ioc_values_deduplicated(self):
        """Two records with the same ioc_value produce one SCO."""
        mod = ThreatFox()
        mod.initialize({})
        with _patched_client(_DUP_RESPONSE):
            results = asyncio.run(mod.hunt("192.168.1.1:4444", {}))
        assert len(results) == 1

    def test_multi_ioc_response_preserves_distinct(self):
        """Three distinct IOC values produce three SCOs."""
        mod = ThreatFox()
        mod.initialize({})
        with _patched_client(_MULTI_IOC_RESPONSE):
            results = asyncio.run(mod.hunt("query_term", {}))
        assert len(results) == 3


# ---------------------------------------------------------------------------
# TestThreatFoxRateLimit — 429 response handling
# ---------------------------------------------------------------------------


class TestThreatFoxRateLimit:
    """hunt() on 429 raises RateLimitError with correct retry_after."""

    def test_429_raises_rate_limit_error(self, mock_429):
        mod = ThreatFox()
        mod.initialize({})
        with pytest.raises(RateLimitError):
            asyncio.run(mod.hunt("192.168.1.1:4444", {}))

    def test_429_retry_after_populated(self, mock_429):
        mod = ThreatFox()
        mod.initialize({})
        with pytest.raises(RateLimitError) as exc_info:
            asyncio.run(mod.hunt("192.168.1.1:4444", {}))
        assert exc_info.value.retry_after == 3600

    def test_429_no_header_retry_after_is_none(self, mock_429_no_header):
        mod = ThreatFox()
        mod.initialize({})
        with pytest.raises(RateLimitError) as exc_info:
            asyncio.run(mod.hunt("192.168.1.1:4444", {}))
        assert exc_info.value.retry_after is None


# ---------------------------------------------------------------------------
# TestThreatFoxBuildSco — unit tests for _build_sco helper
# ---------------------------------------------------------------------------


class TestThreatFoxBuildSco:
    """Unit tests for the _build_sco internal helper."""

    def test_id_is_deterministic_ipv4(self):
        """Same ioc_value always produces the same SCO id."""
        record = _make_ioc_record("1.2.3.4:80", "ip:port")
        sco1 = _build_sco("1.2.3.4:80", record)
        sco2 = _build_sco("1.2.3.4:80", record)
        assert sco1 is not None
        assert sco2 is not None
        assert sco1["id"] == sco2["id"]

    def test_different_values_different_ids(self):
        """Different ioc_values produce different SCO IDs."""
        record = _make_ioc_record("1.2.3.4:80", "ip:port")
        sco1 = _build_sco("1.2.3.4:80", record)
        sco2 = _build_sco("1.2.3.5:80", record)
        assert sco1 is not None and sco2 is not None
        assert sco1["id"] != sco2["id"]

    def test_unknown_ioc_type_returns_none(self):
        """Unknown ioc_type returns None (not a dict)."""
        record = _make_ioc_record("something", "x-custom-type")
        result = _build_sco("something", record)
        assert result is None

    def test_common_fields_tags_string_normalised(self):
        """_build_common_fields wraps a plain string tag in a list."""
        record = {
            "malware": "Emotet",
            "confidence_level": 50,
            "first_seen": "2026-01-01",
            "last_seen": "",
            "reporter": "user1",
            "tags": "single_tag",
        }
        common = _build_common_fields(record)
        assert isinstance(common["x_tf_tags"], list)
        assert "single_tag" in common["x_tf_tags"]

    def test_common_fields_missing_confidence_defaults_zero(self):
        """Missing confidence_level defaults to 0 (not None or error)."""
        record = {"malware": "Unknown"}
        common = _build_common_fields(record)
        assert common["x_tf_confidence"] == 0


# ---------------------------------------------------------------------------
# TestThreatFoxRequestShape — HTTP request structure
# ---------------------------------------------------------------------------


class TestThreatFoxRequestShape:
    """Verify the HTTP request shape emitted to the ThreatFox API."""

    def test_method_is_post(self, mock_ip_port):
        mod = ThreatFox()
        mod.initialize({})
        asyncio.run(mod.hunt("192.168.1.1:4444", {}))
        mock_ip_port.post.assert_called_once()

    def test_payload_contains_search_ioc_query(self, mock_ip_port):
        mod = ThreatFox()
        mod.initialize({})
        asyncio.run(mod.hunt("192.168.1.1:4444", {}))
        call_kwargs = mock_ip_port.post.call_args.kwargs
        assert call_kwargs["json"]["query"] == "search_ioc"

    def test_payload_contains_search_term_as_target(self, mock_ip_port):
        mod = ThreatFox()
        mod.initialize({})
        asyncio.run(mod.hunt("192.168.1.1:4444", {}))
        call_kwargs = mock_ip_port.post.call_args.kwargs
        assert call_kwargs["json"]["search_term"] == "192.168.1.1:4444"


# ---------------------------------------------------------------------------
# TestThreatFoxDiscovery — PluginManager integration (compound interaction)
# ---------------------------------------------------------------------------


class TestThreatFoxDiscovery:
    """ThreatFox is discoverable via PluginManager (production plug-in loading sequence).

    Compound-interaction test: crosses PluginManager.load_plugins() -> get_module()
    -> initialize() -> hunt() boundaries in the real production call order.
    """

    def test_discoverable_via_plugin_manager(self):
        """PluginManager.load_plugins() finds cti/threatfox."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("cti/threatfox")
        assert mod is not None

    def test_plugin_manager_returns_threatfox_instance(self):
        """get_module('cti/threatfox') returns a ThreatFox instance."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("cti/threatfox")
        assert isinstance(mod, ThreatFox)

    def test_production_sequence_load_initialize_hunt(self):
        """Full sequence: load_plugins -> get -> initialize -> hunt (mocked HTTP)."""
        mgr = PluginManager()
        mgr.load_plugins()

        mod = mgr.get_module("cti/threatfox")
        assert mod is not None

        mod.initialize({})  # keyless

        with _patched_client(_NO_RESULTS_RESPONSE):
            results = asyncio.run(mod.hunt("safe.example.com", {}))

        assert isinstance(results, list)
        assert results == []


# ---------------------------------------------------------------------------
# TestNoProvenance — DEC-61-MODULES-EMIT-NO-PROVENANCE-001
# ---------------------------------------------------------------------------


class TestNoProvenance:
    """DEC-61-MODULES-EMIT-NO-PROVENANCE-001: modules emit no x_ap_* fields.

    Provenance augmentation is workspace.store_stix_objects's authority (F59).
    Modules must not duplicate it.
    """

    def test_module_emits_no_x_ap_provenance_fields(self, mock_ip_port):
        """hunt() must not emit any key starting with 'x_ap_' on any SCO.

        Per DEC-61-MODULES-EMIT-NO-PROVENANCE-001, provenance stamping
        (x_ap_source, x_ap_retrieved_at, etc.) belongs exclusively to
        workspace.store_stix_objects (F59). Modules that pre-populate these
        fields would create duplicate authority and cause silent data drift.
        """
        mod = ThreatFox()
        mod.initialize({})
        results = asyncio.run(mod.hunt("192.168.1.1:4444", {}))
        assert len(results) > 0, "Expected non-empty results for this fixture"
        for sco in results:
            for key in sco:
                assert not key.startswith("x_ap_"), (
                    f"Module emitted forbidden x_ap_* field '{key}' in SCO {sco.get('id')}. "
                    f"Provenance is workspace.store_stix_objects's authority "
                    f"(DEC-61-MODULES-EMIT-NO-PROVENANCE-001)."
                )
