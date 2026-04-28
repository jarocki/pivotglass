"""PassiveTotal/RiskIQ passive DNS and WHOIS history module.

Queries the PassiveTotal API for passive DNS records and optional WHOIS
history on domains and IP addresses.

API docs: https://api.passivetotal.org/api/docs/

@decision DEC-MODULE-PT-001
@title HTTP Basic Auth with user+key pair, not single API key
@status accepted
@rationale PassiveTotal uses HTTP Basic Auth (username:key) unlike most other
           modules which use a single API key. Config stores passivetotal_user
           and passivetotal_key separately.

@decision DEC-MODULE-PT-002
@title Passive DNS + optional WHOIS in a single hunt() call
@status accepted
@rationale The two endpoints provide complementary data. WHOIS adds registrant
           and registrar context that enriches the passive DNS infrastructure map.
           INCLUDE_WHOIS defaults to true but can be disabled to halve API calls.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Any

import httpx

from adversary_pursuit.modules.base import (
    AuthenticationError,
    BaseModule,
    RateLimitError,
)

logger = logging.getLogger(__name__)


class PassiveTotal(BaseModule):
    """Query PassiveTotal/RiskIQ for passive DNS and WHOIS history."""

    name: str = "cti/passivetotal"
    description: str = "Query PassiveTotal/RiskIQ for passive DNS and WHOIS history"
    author: str = "Adversary Pursuit"
    module_type: str = "cti"

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {
                "required": True,
                "description": "Domain or IP to query",
                "default": "",
            },
            "INCLUDE_WHOIS": {
                "required": False,
                "description": "Include WHOIS history",
                "default": "true",
            },
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        """Query PassiveTotal for passive DNS and optional WHOIS."""
        user = self._config.get("passivetotal_user", "")
        key = self._config.get("passivetotal_key", "")
        if not user or not key:
            raise AuthenticationError(
                "PassiveTotal credentials not configured. "
                "Set via 'ap config set api_keys.passivetotal_user <user>' and "
                "'ap config set api_keys.passivetotal_key <key>' or "
                "AP_PT_USER / AP_PT_API_KEY env vars."
            )

        include_whois = options.get("INCLUDE_WHOIS", "true").lower() == "true"
        is_ip = self._is_ip(target)

        results: list[dict] = []

        async with httpx.AsyncClient(timeout=30.0, auth=(user, key)) as client:

            # Passive DNS
            dns_resp = await client.get(
                "https://api.passivetotal.org/v2/dns/passive",
                params={"query": target},
            )
            self._check_response(dns_resp)
            dns_data = dns_resp.json()

            # Build primary SCO
            primary_type = "ipv4-addr" if is_ip else "domain-name"
            primary: dict[str, Any] = {
                "type": primary_type,
                "value": target,
                "x_first_seen": dns_data.get("firstSeen", ""),
                "x_last_seen": dns_data.get("lastSeen", ""),
                "x_record_count": dns_data.get("totalRecords", 0),
            }
            results.append(primary)

            # Related indicators from passive DNS
            seen = {target}
            for record in dns_data.get("results", [])[:20]:
                resolve = record.get("resolve", "")
                if resolve and resolve not in seen:
                    seen.add(resolve)
                    resolve_type = record.get("resolveType", "")
                    if resolve_type == "ip" or self._is_ip(resolve):
                        results.append({"type": "ipv4-addr", "value": resolve})
                    else:
                        results.append({"type": "domain-name", "value": resolve})

            # Optional WHOIS
            if include_whois:
                whois_resp = await client.get(
                    "https://api.passivetotal.org/v2/whois",
                    params={"query": target},
                    )
                if whois_resp.status_code == 200:
                    whois_data = whois_resp.json()
                    primary["x_whois"] = whois_data

        return results

    def _check_response(self, resp: httpx.Response) -> None:
        """Check response for common error codes."""
        if resp.status_code == 401:
            raise AuthenticationError("PassiveTotal credentials are invalid.")
        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After")
            raise RateLimitError(
                "PassiveTotal rate limit exceeded.",
                retry_after=int(retry) if retry else None,
            )
        resp.raise_for_status()

    @staticmethod
    def _is_ip(value: str) -> bool:
        """Check if value is an IP address."""
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False
