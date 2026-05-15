"""Tests for the URLScan.io OSINT module (Issue #9).

# @mock-exempt: httpx.AsyncClient is an external HTTP boundary (URLScan.io REST API).
# asyncio.sleep is mocked to avoid real wait times in the poll loop.
# Tests must run without a real API key. This is Sacred Practice #5's
# explicitly-permitted exception: "Mocks are acceptable ONLY for external
# boundaries (HTTP APIs, third-party services, databases)."

Production sequence:
  PluginManager.load_plugins() -> get_module("osint/urlscan") ->
  initialize({api_key}) -> hunt(url, options)

The URLScan flow is async: submit POST -> poll GET (may retry on 404) -> parse.
Tests exercise the full sequence and validate:
  - Protocol conformance (PursuitModule isinstance check)
  - Module metadata (name, type, author, options)
  - No API key -> AuthenticationError before any HTTP call
  - 401 on submit -> AuthenticationError
  - 429 on submit -> RateLimitError (with and without Retry-After header)
  - Successful submit+poll flow returning URL, domain-name, ipv4-addr SCOs
  - x_ custom properties on URL SCO (page_title, screenshot_url, etc.)
  - Poll timeout scenario (poll always 404) returns timeout stub SCO
  - Deduplication: page domain/IP not duplicated in lists results
  - VISIBILITY option forwarded to submit POST body
  - TIMEOUT and POLL_INTERVAL options respected
  - PluginManager discovery

@decision DEC-TEST-URLSCAN-001
@title Monkeypatch httpx.AsyncClient and asyncio.sleep for hermetic async tests
@status accepted
@rationale The submit+poll pattern requires two different mock responses
           in sequence: a POST for submission and one or more GETs for polling.
           We mock httpx.AsyncClient with separate AsyncMock for .post()
           and .get() methods. asyncio.sleep is patched to avoid real delays
           in the poll loop. This is the cleanest approach without adding
           external test dependencies (respx, vcrpy) for a single module.

@decision DEC-TEST-URLSCAN-002
@title side_effect list for sequential mock responses
@status accepted
@rationale The poll loop may call GET multiple times (404 then 200). Using
           side_effect as a list on the mock.get makes subsequent calls return
           different responses in order — the standard unittest.mock pattern
           for sequence-dependent test scenarios.
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
from adversary_pursuit.modules.osint.urlscan import URLScan

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

TARGET_URL = "https://example.com/malware"
SCAN_UUID = "12345678-1234-1234-1234-123456789abc"

SUBMIT_RESPONSE = {
    "uuid": SCAN_UUID,
    "api": f"https://urlscan.io/api/v1/result/{SCAN_UUID}/",
    "result": f"https://urlscan.io/result/{SCAN_UUID}/",
    "visibility": "unlisted",
    "options": {"useragent": "Mozilla/5.0"},
    "url": TARGET_URL,
}

RESULT_RESPONSE = {
    "task": {
        "url": TARGET_URL,
        "visibility": "unlisted",
        "screenshotURL": f"https://urlscan.io/screenshots/{SCAN_UUID}.png",
    },
    "page": {
        "url": "https://example.com/malware",
        "domain": "example.com",
        "ip": "93.184.216.34",
        "title": "Malware Example Page",
        "status": 200,
        "server": "nginx/1.18.0",
        "asn": "AS15133",
    },
    "lists": {
        "ips": ["93.184.216.34", "8.8.8.8", "1.1.1.1"],
        "domains": ["example.com", "cdn.example.com", "static.example.com"],
        "urls": [TARGET_URL],
    },
    "stats": {
        "uniqIPs": 3,
        "uniqDomains": 3,
    },
}


def _make_mock_response(
    status_code: int,
    body: dict,
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
        mock_resp.raise_for_status.side_effect = None  # handled manually for 401/429
    return mock_resp


def _make_client(post_resp: MagicMock, get_resp) -> AsyncMock:
    """Build an AsyncMock httpx.AsyncClient with post and get configured.

    get_resp may be a single MagicMock or a list (for side_effect sequences).
    """
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=post_resp)
    if isinstance(get_resp, list):
        mock_client.get = AsyncMock(side_effect=get_resp)
    else:
        mock_client.get = AsyncMock(return_value=get_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ---------------------------------------------------------------------------
# Protocol and metadata tests
# ---------------------------------------------------------------------------


class TestURLScanMetadata:
    """Module satisfies PursuitModule protocol and declares correct metadata."""

    def test_satisfies_protocol(self):
        """URLScan must satisfy PursuitModule isinstance check."""
        mod = URLScan()
        assert isinstance(mod, PursuitModule)

    def test_module_name(self):
        mod = URLScan()
        assert mod.name == "osint/urlscan"

    def test_module_type(self):
        mod = URLScan()
        assert mod.module_type == "osint"

    def test_module_author(self):
        mod = URLScan()
        assert mod.author == "Adversary Pursuit"

    def test_description_non_empty(self):
        mod = URLScan()
        assert mod.description

    def test_options_has_target(self):
        mod = URLScan()
        assert "TARGET" in mod.options
        assert mod.options["TARGET"]["required"] is True

    def test_options_has_visibility(self):
        mod = URLScan()
        assert "VISIBILITY" in mod.options
        assert mod.options["VISIBILITY"]["required"] is False
        assert mod.options["VISIBILITY"]["default"] == "unlisted"

    def test_options_has_timeout(self):
        mod = URLScan()
        assert "TIMEOUT" in mod.options
        assert mod.options["TIMEOUT"]["required"] is False
        assert mod.options["TIMEOUT"]["default"] == "60"

    def test_options_has_poll_interval(self):
        mod = URLScan()
        assert "POLL_INTERVAL" in mod.options
        assert mod.options["POLL_INTERVAL"]["required"] is False
        assert mod.options["POLL_INTERVAL"]["default"] == "5"


# ---------------------------------------------------------------------------
# Authentication / error path tests
# ---------------------------------------------------------------------------


class TestURLScanErrors:
    """hunt() error handling: missing key, 401, 429."""

    def test_hunt_no_api_key_raises_auth_error(self):
        """hunt() without an API key must raise AuthenticationError immediately."""
        mod = URLScan()
        mod.initialize({})
        with pytest.raises(AuthenticationError, match="API key"):
            asyncio.run(mod.hunt(TARGET_URL, {}))

    def test_hunt_empty_api_key_raises_auth_error(self):
        """hunt() with empty string API key raises AuthenticationError."""
        mod = URLScan()
        mod.initialize({"api_key": ""})
        with pytest.raises(AuthenticationError):
            asyncio.run(mod.hunt(TARGET_URL, {}))

    def test_hunt_401_on_submit_raises_auth_error(self):
        """401 on submit POST raises AuthenticationError."""
        submit_resp = _make_mock_response(401, {"message": "Not authorized"})
        mock_client = _make_client(submit_resp, MagicMock())
        with patch(
            "adversary_pursuit.modules.osint.urlscan.httpx.AsyncClient",
            return_value=mock_client,
        ):
            mod = URLScan()
            mod.initialize({"api_key": "bad-key"})
            with pytest.raises(AuthenticationError):
                asyncio.run(mod.hunt(TARGET_URL, {}))

    def test_hunt_429_on_submit_raises_rate_limit_error(self):
        """429 on submit POST raises RateLimitError."""
        submit_resp = _make_mock_response(
            429,
            {"message": "Too many scans"},
            headers={"Retry-After": "3600"},
        )
        mock_client = _make_client(submit_resp, MagicMock())
        with patch(
            "adversary_pursuit.modules.osint.urlscan.httpx.AsyncClient",
            return_value=mock_client,
        ):
            mod = URLScan()
            mod.initialize({"api_key": "test-key"})
            with pytest.raises(RateLimitError):
                asyncio.run(mod.hunt(TARGET_URL, {}))

    def test_hunt_429_retry_after_is_set(self):
        """RateLimitError.retry_after is populated from Retry-After header."""
        submit_resp = _make_mock_response(
            429,
            {"message": "Too many scans"},
            headers={"Retry-After": "3600"},
        )
        mock_client = _make_client(submit_resp, MagicMock())
        with patch(
            "adversary_pursuit.modules.osint.urlscan.httpx.AsyncClient",
            return_value=mock_client,
        ):
            mod = URLScan()
            mod.initialize({"api_key": "test-key"})
            with pytest.raises(RateLimitError) as exc_info:
                asyncio.run(mod.hunt(TARGET_URL, {}))
        assert exc_info.value.retry_after == 3600

    def test_hunt_429_no_retry_after_is_none(self):
        """RateLimitError.retry_after is None when Retry-After header absent."""
        submit_resp = _make_mock_response(
            429,
            {"message": "Too many scans"},
            headers={},
        )
        mock_client = _make_client(submit_resp, MagicMock())
        with patch(
            "adversary_pursuit.modules.osint.urlscan.httpx.AsyncClient",
            return_value=mock_client,
        ):
            mod = URLScan()
            mod.initialize({"api_key": "test-key"})
            with pytest.raises(RateLimitError) as exc_info:
                asyncio.run(mod.hunt(TARGET_URL, {}))
        assert exc_info.value.retry_after is None

    def test_hunt_403_on_submit_raises_auth_error(self):
        """403 on submit POST raises AuthenticationError mentioning 403/forbidden.

        # @mock-exempt: httpx.AsyncClient mocked at HTTP boundary (external URLScan API).
        """
        submit_resp = _make_mock_response(403, {"message": "Forbidden"})
        mock_client = _make_client(submit_resp, MagicMock())
        with patch(
            "adversary_pursuit.modules.osint.urlscan.httpx.AsyncClient",
            return_value=mock_client,
        ):
            mod = URLScan()
            mod.initialize({"api_key": "test-key"})
            with pytest.raises(AuthenticationError, match="(?i)403|forbidden"):
                asyncio.run(mod.hunt(TARGET_URL, {}))


# ---------------------------------------------------------------------------
# Successful hunt() submit+poll flow
# ---------------------------------------------------------------------------


class TestURLScanHuntResults:
    """hunt() result structure with mocked submit and poll responses."""

    def _run_successful_hunt(self, options: dict | None = None) -> list[dict]:
        """Helper: run hunt() with a successful submit+poll mock."""
        submit_resp = _make_mock_response(200, SUBMIT_RESPONSE)
        poll_resp = _make_mock_response(200, RESULT_RESPONSE)
        mock_client = _make_client(submit_resp, poll_resp)

        with (
            patch(
                "adversary_pursuit.modules.osint.urlscan.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("adversary_pursuit.modules.osint.urlscan.asyncio.sleep", new_callable=AsyncMock),
        ):
            mod = URLScan()
            mod.initialize({"api_key": "test-key"})
            return asyncio.run(mod.hunt(TARGET_URL, options or {}))

    def test_hunt_returns_list(self):
        """hunt() returns a list."""
        results = self._run_successful_hunt()
        assert isinstance(results, list)

    def test_hunt_first_result_is_url_sco(self):
        """First result is a url SCO."""
        results = self._run_successful_hunt()
        assert results[0]["type"] == "url"

    def test_hunt_url_sco_value_matches_target(self):
        """url SCO value matches the submitted URL."""
        results = self._run_successful_hunt()
        assert results[0]["value"] == TARGET_URL

    def test_hunt_url_sco_has_scan_uuid(self):
        """url SCO contains x_scan_uuid from submit response."""
        results = self._run_successful_hunt()
        assert results[0].get("x_scan_uuid") == SCAN_UUID

    def test_hunt_url_sco_has_page_title(self):
        """url SCO contains x_page_title from result page data."""
        results = self._run_successful_hunt()
        assert results[0].get("x_page_title") == "Malware Example Page"

    def test_hunt_url_sco_has_screenshot_url(self):
        """url SCO contains x_screenshot_url from result task data."""
        results = self._run_successful_hunt()
        expected = f"https://urlscan.io/screenshots/{SCAN_UUID}.png"
        assert results[0].get("x_screenshot_url") == expected

    def test_hunt_url_sco_has_page_status(self):
        """url SCO contains x_page_status from result page data."""
        results = self._run_successful_hunt()
        assert results[0].get("x_page_status") == 200

    def test_hunt_url_sco_has_server(self):
        """url SCO contains x_server from result page data."""
        results = self._run_successful_hunt()
        assert results[0].get("x_server") == "nginx/1.18.0"

    def test_hunt_includes_domain_name_sco_for_page_domain(self):
        """Results contain a domain-name SCO for the page domain."""
        results = self._run_successful_hunt()
        domain_scos = [r for r in results if r.get("type") == "domain-name"]
        domain_values = [r["value"] for r in domain_scos]
        assert "example.com" in domain_values

    def test_hunt_includes_ipv4_addr_sco_for_page_ip(self):
        """Results contain an ipv4-addr SCO for the page IP."""
        results = self._run_successful_hunt()
        ip_scos = [r for r in results if r.get("type") == "ipv4-addr"]
        ip_values = [r["value"] for r in ip_scos]
        assert "93.184.216.34" in ip_values

    def test_hunt_ip_sco_has_asn(self):
        """ipv4-addr SCO for page IP includes x_asn."""
        results = self._run_successful_hunt()
        ip_scos = [r for r in results if r.get("type") == "ipv4-addr"]
        page_ip_sco = next(
            (r for r in ip_scos if r.get("value") == "93.184.216.34"),
            None,
        )
        assert page_ip_sco is not None
        assert page_ip_sco.get("x_asn") == "AS15133"

    def test_hunt_includes_additional_ips_from_lists(self):
        """Results include additional IPs from result lists.ips (deduplicated)."""
        results = self._run_successful_hunt()
        ip_scos = [r for r in results if r.get("type") == "ipv4-addr"]
        ip_values = {r["value"] for r in ip_scos}
        # 8.8.8.8 is in lists.ips and not the page IP — should be included
        assert "8.8.8.8" in ip_values

    def test_hunt_includes_additional_domains_from_lists(self):
        """Results include additional domains from result lists.domains (deduplicated)."""
        results = self._run_successful_hunt()
        domain_scos = [r for r in results if r.get("type") == "domain-name"]
        domain_values = {r["value"] for r in domain_scos}
        assert "cdn.example.com" in domain_values

    def test_hunt_no_duplicate_page_domain_in_lists(self):
        """Page domain (example.com) not duplicated when it appears in lists.domains."""
        results = self._run_successful_hunt()
        domain_scos = [r for r in results if r.get("type") == "domain-name"]
        domain_values = [r["value"] for r in domain_scos]
        # example.com is in both page.domain and lists.domains — should appear once
        assert domain_values.count("example.com") == 1

    def test_hunt_no_duplicate_page_ip_in_lists(self):
        """Page IP (93.184.216.34) not duplicated when it appears in lists.ips."""
        results = self._run_successful_hunt()
        ip_scos = [r for r in results if r.get("type") == "ipv4-addr"]
        ip_values = [r["value"] for r in ip_scos]
        # 93.184.216.34 is in both page.ip and lists.ips — should appear once
        assert ip_values.count("93.184.216.34") == 1


# ---------------------------------------------------------------------------
# Poll behavior tests
# ---------------------------------------------------------------------------


class TestURLScanPollBehavior:
    """Poll loop: timeout, retry on 404, TIMEOUT and POLL_INTERVAL options."""

    def test_poll_timeout_returns_stub_sco(self):
        """When poll always returns 404 and timeout is reached, return stub url SCO."""
        submit_resp = _make_mock_response(200, SUBMIT_RESPONSE)
        # poll always returns 404 (not ready)
        poll_404 = _make_mock_response(404, {})
        mock_client = _make_client(submit_resp, poll_404)

        with (
            patch(
                "adversary_pursuit.modules.osint.urlscan.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("adversary_pursuit.modules.osint.urlscan.asyncio.sleep", new_callable=AsyncMock),
        ):
            mod = URLScan()
            mod.initialize({"api_key": "test-key"})
            # Use short timeout so the loop exits quickly
            results = asyncio.run(mod.hunt(TARGET_URL, {"TIMEOUT": "10", "POLL_INTERVAL": "5"}))

        assert len(results) == 1
        assert results[0]["type"] == "url"
        assert results[0]["value"] == TARGET_URL
        assert results[0].get("x_scan_status") == "timeout"
        assert results[0].get("x_scan_uuid") == SCAN_UUID

    def test_poll_retries_on_404_then_succeeds(self):
        """Poll loop retries when result is 404, then parses 200 results."""
        submit_resp = _make_mock_response(200, SUBMIT_RESPONSE)
        # First poll returns 404, second returns 200
        poll_404 = _make_mock_response(404, {})
        poll_200 = _make_mock_response(200, RESULT_RESPONSE)
        mock_client = _make_client(submit_resp, [poll_404, poll_200])

        with (
            patch(
                "adversary_pursuit.modules.osint.urlscan.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("adversary_pursuit.modules.osint.urlscan.asyncio.sleep", new_callable=AsyncMock),
        ):
            mod = URLScan()
            mod.initialize({"api_key": "test-key"})
            results = asyncio.run(mod.hunt(TARGET_URL, {"TIMEOUT": "30", "POLL_INTERVAL": "5"}))

        assert results[0]["type"] == "url"
        assert results[0].get("x_scan_uuid") == SCAN_UUID
        assert results[0].get("x_page_title") == "Malware Example Page"

    def test_poll_sleep_called_with_poll_interval(self):
        """asyncio.sleep is called with POLL_INTERVAL seconds each iteration."""
        submit_resp = _make_mock_response(200, SUBMIT_RESPONSE)
        poll_resp = _make_mock_response(200, RESULT_RESPONSE)
        mock_client = _make_client(submit_resp, poll_resp)

        sleep_mock = AsyncMock()
        with (
            patch(
                "adversary_pursuit.modules.osint.urlscan.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("adversary_pursuit.modules.osint.urlscan.asyncio.sleep", sleep_mock),
        ):
            mod = URLScan()
            mod.initialize({"api_key": "test-key"})
            asyncio.run(mod.hunt(TARGET_URL, {"POLL_INTERVAL": "7"}))

        sleep_mock.assert_called_with(7)

    def test_visibility_option_forwarded_to_submit(self):
        """VISIBILITY option is passed in the POST body to the submit endpoint."""
        submit_resp = _make_mock_response(200, SUBMIT_RESPONSE)
        poll_resp = _make_mock_response(200, RESULT_RESPONSE)
        mock_client = _make_client(submit_resp, poll_resp)

        with (
            patch(
                "adversary_pursuit.modules.osint.urlscan.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("adversary_pursuit.modules.osint.urlscan.asyncio.sleep", new_callable=AsyncMock),
        ):
            mod = URLScan()
            mod.initialize({"api_key": "test-key"})
            asyncio.run(mod.hunt(TARGET_URL, {"VISIBILITY": "public"}))

        post_call_kwargs = mock_client.post.call_args
        body = post_call_kwargs.kwargs.get("json", {})
        assert body.get("visibility") == "public"

    def test_submit_request_has_api_key_header(self):
        """POST submit uses API-Key header with the configured API key."""
        submit_resp = _make_mock_response(200, SUBMIT_RESPONSE)
        poll_resp = _make_mock_response(200, RESULT_RESPONSE)
        mock_client = _make_client(submit_resp, poll_resp)

        with (
            patch(
                "adversary_pursuit.modules.osint.urlscan.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("adversary_pursuit.modules.osint.urlscan.asyncio.sleep", new_callable=AsyncMock),
        ):
            mod = URLScan()
            mod.initialize({"api_key": "my-secret-urlscan-key"})
            asyncio.run(mod.hunt(TARGET_URL, {}))

        headers = mock_client.post.call_args.kwargs.get("headers", {})
        assert headers.get("API-Key") == "my-secret-urlscan-key"

    def test_submit_url_forwarded_in_post_body(self):
        """The target URL is forwarded in the POST body as 'url'."""
        submit_resp = _make_mock_response(200, SUBMIT_RESPONSE)
        poll_resp = _make_mock_response(200, RESULT_RESPONSE)
        mock_client = _make_client(submit_resp, poll_resp)

        with (
            patch(
                "adversary_pursuit.modules.osint.urlscan.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("adversary_pursuit.modules.osint.urlscan.asyncio.sleep", new_callable=AsyncMock),
        ):
            mod = URLScan()
            mod.initialize({"api_key": "test-key"})
            asyncio.run(mod.hunt(TARGET_URL, {}))

        body = mock_client.post.call_args.kwargs.get("json", {})
        assert body.get("url") == TARGET_URL

    def test_poll_request_has_api_key_header(self):
        """GET poll uses API-Key header with the configured API key.

        # @mock-exempt: httpx.AsyncClient at HTTP boundary
        """
        submit_resp = _make_mock_response(200, SUBMIT_RESPONSE)
        poll_resp = _make_mock_response(200, RESULT_RESPONSE)
        mock_client = _make_client(submit_resp, poll_resp)

        with (
            patch(
                "adversary_pursuit.modules.osint.urlscan.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("adversary_pursuit.modules.osint.urlscan.asyncio.sleep", new_callable=AsyncMock),
        ):
            mod = URLScan()
            mod.initialize({"api_key": "my-secret-urlscan-key"})
            asyncio.run(mod.hunt(TARGET_URL, {}))

        assert (
            mock_client.get.call_args.kwargs.get("headers", {}).get("API-Key")
            == "my-secret-urlscan-key"
        )

    def test_poll_retries_on_403_then_succeeds(self):
        """Poll loop retries when result is 403, then parses 200 results.

        # @mock-exempt: httpx.AsyncClient at HTTP boundary
        """
        submit_resp = _make_mock_response(200, SUBMIT_RESPONSE)
        # First poll returns 403 (transient not-ready), second returns 200
        poll_403 = _make_mock_response(403, {})
        poll_200 = _make_mock_response(200, RESULT_RESPONSE)
        mock_client = _make_client(submit_resp, [poll_403, poll_200])

        with (
            patch(
                "adversary_pursuit.modules.osint.urlscan.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("adversary_pursuit.modules.osint.urlscan.asyncio.sleep", new_callable=AsyncMock),
        ):
            mod = URLScan()
            mod.initialize({"api_key": "test-key"})
            results = asyncio.run(mod.hunt(TARGET_URL, {"TIMEOUT": "30", "POLL_INTERVAL": "5"}))

        assert results[0]["type"] == "url"
        assert results[0].get("x_scan_uuid") == SCAN_UUID
        assert results[0].get("x_page_title") == "Malware Example Page"


# ---------------------------------------------------------------------------
# Lists cap test
# ---------------------------------------------------------------------------


class TestURLScanListsCap:
    """hunt() caps IPs and domains from lists at 15 each."""

    def test_lists_ips_capped_at_15(self):
        """No more than 15 additional IPs from lists.ips."""
        # Build a result with 20 unique IPs in lists
        big_ips = [f"10.0.0.{i}" for i in range(20)]
        big_result = {
            **RESULT_RESPONSE,
            "lists": {**RESULT_RESPONSE["lists"], "ips": big_ips},
        }
        submit_resp = _make_mock_response(200, SUBMIT_RESPONSE)
        poll_resp = _make_mock_response(200, big_result)
        mock_client = _make_client(submit_resp, poll_resp)

        with (
            patch(
                "adversary_pursuit.modules.osint.urlscan.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("adversary_pursuit.modules.osint.urlscan.asyncio.sleep", new_callable=AsyncMock),
        ):
            mod = URLScan()
            mod.initialize({"api_key": "test-key"})
            results = asyncio.run(mod.hunt(TARGET_URL, {}))

        ip_scos = [r for r in results if r.get("type") == "ipv4-addr"]
        # 1 page IP + up to 15 from lists = at most 16
        assert len(ip_scos) <= 16

    def test_lists_domains_capped_at_15(self):
        """No more than 15 additional domains from lists.domains."""
        big_domains = [f"sub{i}.example.com" for i in range(20)]
        big_result = {
            **RESULT_RESPONSE,
            "page": {**RESULT_RESPONSE["page"], "domain": ""},  # no page domain to simplify count
            "lists": {**RESULT_RESPONSE["lists"], "domains": big_domains},
        }
        submit_resp = _make_mock_response(200, SUBMIT_RESPONSE)
        poll_resp = _make_mock_response(200, big_result)
        mock_client = _make_client(submit_resp, poll_resp)

        with (
            patch(
                "adversary_pursuit.modules.osint.urlscan.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("adversary_pursuit.modules.osint.urlscan.asyncio.sleep", new_callable=AsyncMock),
        ):
            mod = URLScan()
            mod.initialize({"api_key": "test-key"})
            results = asyncio.run(mod.hunt(TARGET_URL, {}))

        domain_scos = [r for r in results if r.get("type") == "domain-name"]
        assert len(domain_scos) <= 15


# ---------------------------------------------------------------------------
# Request shape tests — assert exact URL, method, header, and body contract
# ---------------------------------------------------------------------------


class TestURLScanRequestShape:
    """Verify the submit POST conforms to the canonical urlscan.io API contract.

    These tests exercise the full production sequence (initialize -> hunt) with
    the HTTP boundary mocked, then inspect the captured call arguments to assert
    the exact URL string, HTTP method, Content-Type header, and JSON body keys.

    # @mock-exempt: httpx.AsyncClient is mocked at the external HTTP boundary only.
    # The full internal code path (key validation, option resolution, request
    # construction) executes unmodified. See DEC-TEST-URLSCAN-001.
    """

    def _run_hunt_and_capture(self) -> AsyncMock:
        """Run hunt() through to submit and return the mock_client for call inspection."""
        submit_resp = _make_mock_response(200, SUBMIT_RESPONSE)
        poll_resp = _make_mock_response(200, RESULT_RESPONSE)
        mock_client = _make_client(submit_resp, poll_resp)

        with (
            patch(
                "adversary_pursuit.modules.osint.urlscan.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("adversary_pursuit.modules.osint.urlscan.asyncio.sleep", new_callable=AsyncMock),
        ):
            mod = URLScan()
            mod.initialize({"api_key": "test-key"})
            asyncio.run(mod.hunt(TARGET_URL, {}))

        return mock_client

    def test_submit_endpoint_url_matches_spec(self):
        """Submit POST is called with the exact canonical URL including trailing slash.

        Asserts the literal string 'https://urlscan.io/api/v1/scan/' — the
        trailing slash is required; Cloudflare returns 403 for the slash-less
        variant. See DEC-MODULE-URLSCAN-005.
        """
        mock_client = self._run_hunt_and_capture()
        post_call_args = mock_client.post.call_args
        called_url = (
            post_call_args.args[0] if post_call_args.args else post_call_args.kwargs.get("url")
        )
        assert called_url == "https://urlscan.io/api/v1/scan/", (
            f"Expected submit URL 'https://urlscan.io/api/v1/scan/' (with trailing slash), "
            f"got {called_url!r}. Missing slash causes Cloudflare 403."
        )

    def test_submit_method_is_post(self):
        """Submit request uses the POST method (not GET, PUT, etc.)."""
        mock_client = self._run_hunt_and_capture()
        # The mock records the call on .post — if .post was called, method is POST
        assert mock_client.post.called, (
            "Expected httpx.AsyncClient.post() to be called for scan submission"
        )

    def test_submit_content_type_is_json(self):
        """Submit POST includes Content-Type: application/json header."""
        mock_client = self._run_hunt_and_capture()
        headers = mock_client.post.call_args.kwargs.get("headers", {})
        assert headers.get("Content-Type") == "application/json", (
            f"Expected Content-Type 'application/json', got {headers.get('Content-Type')!r}"
        )

    def test_submit_body_required_keys(self):
        """Submit POST body is JSON containing the 'url' key set to the target."""
        mock_client = self._run_hunt_and_capture()
        body = mock_client.post.call_args.kwargs.get("json", {})
        assert "url" in body, f"Expected 'url' key in POST body, got keys: {list(body.keys())}"
        assert body["url"] == TARGET_URL, (
            f"Expected body['url'] == {TARGET_URL!r}, got {body['url']!r}"
        )


# ---------------------------------------------------------------------------
# Plugin manager integration test
# ---------------------------------------------------------------------------


class TestURLScanDiscovery:
    """URLScan is discoverable via PluginManager."""

    def test_discoverable_via_plugin_manager(self):
        """PluginManager.load_plugins() finds osint/urlscan."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/urlscan")
        assert mod is not None

    def test_plugin_manager_returns_urlscan_instance(self):
        """get_module('osint/urlscan') returns a URLScan instance."""
        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/urlscan")
        assert isinstance(mod, URLScan)

    def test_production_sequence_load_search_get_initialize(self):
        """Production sequence: load_plugins -> search('urlscan') -> get -> initialize."""
        mgr = PluginManager()
        mgr.load_plugins()

        results = mgr.search("urlscan")
        assert len(results) >= 1
        names = [r["name"] for r in results]
        assert "osint/urlscan" in names

        mod = mgr.get_module("osint/urlscan")
        assert mod is not None
        mod.initialize({"api_key": "test-key"})
        assert mod._config["api_key"] == "test-key"
