"""Shodan DNS pivot tests with HTTP isolated at the provider boundary."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pivotglass.modules.base import AuthenticationError
from pivotglass.modules.osint.shodan_dns import ShodanDNS


def _client(response):
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def test_dns_records_preserve_observation_time_and_pivot_values():
    response = MagicMock(status_code=200)
    response.json.return_value = {
        "more": True,
        "data": [
            {
                "subdomain": "vpn",
                "type": "A",
                "value": "192.0.2.10",
                "last_seen": "2026-09-30T00:00:00Z",
            },
            {"subdomain": "vpn", "type": "AAAA", "value": "2001:db8::10"},
        ],
    }
    client = _client(response)
    with patch("pivotglass.modules.osint.shodan_dns.httpx.AsyncClient", return_value=client):
        module = ShodanDNS()
        module.initialize({"api_key": "test-key"})
        results = asyncio.run(module.hunt("example.org", {"HISTORY": "true"}))
    assert client.get.call_args.args[0] == "https://api.shodan.io/dns/domain/example.org"
    assert client.get.call_args.kwargs["params"] == {"key": "test-key", "history": "true"}
    assert results[0]["x_shodan_more"] is True
    assert results[0]["x_shodan_dns_records"][0]["last_seen"] == "2026-09-30T00:00:00Z"
    assert {item["value"] for item in results[1:]} == {
        "vpn.example.org", "192.0.2.10", "2001:db8::10",
    }


def test_missing_key_does_not_call_shodan():
    module = ShodanDNS()
    module.initialize({})
    with patch("pivotglass.modules.osint.shodan_dns.httpx.AsyncClient") as client:
        with pytest.raises(AuthenticationError):
            asyncio.run(module.hunt("example.org", {}))
        client.assert_not_called()
