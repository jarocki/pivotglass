"""URLScan existing-scan search remains read-only and bounded."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pivotglass.modules.osint.urlscan_search import URLScanSearch


def _client(response):
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.mark.parametrize(
    ("target", "expected_query", "expected_type"),
    [
        ("example.org", "page.domain:example.org", "domain-name"),
        ("192.0.2.10", "page.ip:192.0.2.10", "ipv4-addr"),
    ],
)
def test_search_uses_read_only_bounded_get(target, expected_query, expected_type):
    response = MagicMock(status_code=200)
    response.json.return_value = {
        "total": 12,
        "results": [
            {
                "task": {"uuid": "scan-1", "url": "https://example.org/", "time": "2026-09-30"},
                "page": {"url": "https://example.org/"},
                "result": "https://urlscan.io/result/scan-1/",
            }
        ],
    }
    client = _client(response)
    with patch("pivotglass.modules.osint.urlscan_search.httpx.AsyncClient", return_value=client):
        module = URLScanSearch()
        module.initialize({"api_key": "test-key"})
        results = asyncio.run(module.hunt(target, {}))
    assert client.get.await_count == 1
    assert client.post.await_count == 0
    assert client.get.call_args.args[0] == "https://urlscan.io/api/v1/search"
    assert client.get.call_args.kwargs["params"] == {"q": expected_query, "size": 10}
    assert results[0]["type"] == expected_type
    assert results[0]["x_urlscan_search_total"] == 12
    assert results[1]["x_scan_uuid"] == "scan-1"


def test_search_rejects_query_syntax_in_target_before_http():
    module = URLScanSearch()
    module.initialize({"api_key": "test-key"})
    with patch("pivotglass.modules.osint.urlscan_search.httpx.AsyncClient") as client:
        with pytest.raises(ValueError):
            asyncio.run(module.hunt("example.org OR *", {}))
        client.assert_not_called()
