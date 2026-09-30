"""Bounded Shodan DNS pivot for a domain.

Shodan documents GET /dns/domain/{domain} as a query-credit-bearing lookup.
The result preserves each returned record and its last-seen time on the
primary domain; related names and addresses are separate pivot candidates.
"""

from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import quote

import httpx

from pivotglass.modules.base import AuthenticationError, BaseModule, RateLimitError

_MAX_RECORDS = 30


class ShodanDNS(BaseModule):
    """Query Shodan's DNS database for a domain and bounded related values."""

    name = "osint/shodan_dns"
    description = "Query Shodan DNS records and subdomains for a domain"
    author = "Pivotglass"
    module_type = "osint"
    accepts = ("domain",)

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {"required": True, "description": "Domain to query", "default": ""},
            "HISTORY": {
                "required": False,
                "description": "Include Shodan DNS history if entitled",
                "default": "false",
            },
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        key = self._config.get("api_key", "")
        if not key:
            raise AuthenticationError("Shodan API key is not configured.")
        history = str(options.get("HISTORY", "false")).lower() == "true"
        url = f"https://api.shodan.io/dns/domain/{quote(target, safe='.') }"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                params={"key": key, "history": str(history).lower()},
            )
        if response.status_code == 401:
            raise AuthenticationError("Shodan API key was rejected.")
        if response.status_code == 429:
            raise RateLimitError("Shodan DNS query was rate limited.")
        response.raise_for_status()
        data = response.json()
        records = data.get("data", [])[:_MAX_RECORDS]
        primary: dict[str, Any] = {
            "type": "domain-name",
            "value": target,
            "x_shodan_dns_records": [
                {
                    "subdomain": str(item.get("subdomain", "")),
                    "record_type": str(item.get("type", "")),
                    "value": str(item.get("value", "")),
                    "last_seen": str(item.get("last_seen", "")),
                }
                for item in records
                if isinstance(item, dict)
            ],
            "x_shodan_more": bool(data.get("more", False)),
        }
        results: list[dict] = [primary]
        seen = {target.lower()}
        for item in records:
            if not isinstance(item, dict):
                continue
            subdomain = str(item.get("subdomain", "")).strip().lstrip("*.")
            if subdomain:
                name = subdomain if subdomain.endswith(f".{target}") else f"{subdomain}.{target}"
                if name.lower() not in seen:
                    seen.add(name.lower())
                    results.append({"type": "domain-name", "value": name})
            value = str(item.get("value", "")).strip()
            try:
                address = ipaddress.ip_address(value)
            except ValueError:
                continue
            if value not in seen:
                seen.add(value)
                results.append({
                    "type": "ipv4-addr" if address.version == 4 else "ipv6-addr",
                    "value": value,
                })
        return results
