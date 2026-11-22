"""Mnemonic passive DNS module (keyless public tier).

API: GET {base}/pdns/v3/{query}?limit=N  (base default https://api.mnemonic.no)
Docs: https://docs.mnemonic.no/service-integration-guides/passivedns/docs/public/01-public_api.html

@decision DEC-MODULE-MNEMONIC-PDNS-001
@title Keyless public tier; 402/429 are quota signals; count 0 is "no records"
@status accepted
@rationale The public tier needs no key and sees only TLP:WHITE records. It allows
           10 requests per minute and 1000 per day; exceeding it returns HTTP 402
           with ``metaData.millisUntilResourcesAvailable``, which becomes a
           RateLimitError with retry_after. A name or address with no records
           returns 200 with ``count: 0`` and an ``object.not.found`` message, which
           is an empty result, not an error. ``limit`` above 1000 returns 412, so
           the option is clamped.

@decision DEC-MODULE-MNEMONIC-PDNS-002
@title One primary SCO carrying the resolution history, plus resolved neighbours
@status accepted
@rationale The queried observable carries ``x_mnemonic_pdns_records`` (rrtype,
           query, answer, first/last seen, times, max TTL) and the total match
           count. A/AAAA/CNAME neighbours become their own SCOs so they can be
           pivoted. Mnemonic reports 0 for first/last seen on partial records;
           those become empty strings (unknown), never the Unix epoch.
           Resolution history is infrastructure context, not a verdict.
"""

from __future__ import annotations

import ipaddress
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from pivotglass.core.ioc_types import detect_ioc_type
from pivotglass.modules.base import BaseModule, ModuleError, RateLimitError
from pivotglass.modules.keyless_http import json_body, keyless_get, unexpected_status

logger = logging.getLogger(__name__)

SOURCE = "Mnemonic passive DNS"
_MAX_LIMIT = 1000
_DEFAULT_LIMIT = 100
_MAX_NEIGHBOURS = 50
_SCO_TYPES = {"domain": "domain-name", "ipv4": "ipv4-addr", "ipv6": "ipv6-addr"}


def _iso_ms(value: Any) -> str:
    try:
        millis = int(value or 0)
    except (TypeError, ValueError):
        return ""
    if millis <= 0:
        return ""
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _address_type(value: str) -> str | None:
    try:
        return "ipv4-addr" if ipaddress.ip_address(value).version == 4 else "ipv6-addr"
    except ValueError:
        return None


class MnemonicPassiveDNS(BaseModule):
    """Look up passive DNS resolutions for a domain or IP via Mnemonic (no key)."""

    name = "osint/mnemonic_pdns"
    description = "Passive DNS resolutions with first/last seen via Mnemonic (no key)"
    author = "Pivotglass"
    module_type = "osint"
    service_id = "mnemonic_pdns"
    accepts = ("domain", "ipv4", "ipv6")
    requires_api_key = False
    transport: httpx.AsyncBaseTransport | None = None

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {"required": True, "description": "Domain or IP address", "default": ""},
            "LIMIT": {
                "required": False,
                "description": f"Maximum records to return (1-{_MAX_LIMIT})",
                "default": str(_DEFAULT_LIMIT),
            },
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        target = target.strip().rstrip(".").lower()
        sco_type = _SCO_TYPES.get(detect_ioc_type(target) or "")
        if sco_type is None:
            raise ModuleError(f"{SOURCE} accepts a domain or IP address; '{target}' is neither.")
        try:
            limit = int(options.get("LIMIT", _DEFAULT_LIMIT))
        except (TypeError, ValueError):
            limit = _DEFAULT_LIMIT
        limit = max(1, min(limit, _MAX_LIMIT))

        response = await keyless_get(
            SOURCE,
            f"{self.base_url}/pdns/v3/{quote(target, safe='.:')}",
            params={"limit": limit},
            transport=self.transport,
        )
        if response.status_code == 402:
            body = json_body(SOURCE, response) if response.content else {}
            millis = (body.get("metaData") or {}).get("millisUntilResourcesAvailable") if isinstance(body, dict) else None
            retry = int(millis) // 1000 + 1 if isinstance(millis, (int, float)) else None
            raise RateLimitError(
                f"{SOURCE} public quota reached (10 per minute, 1000 per day).", retry_after=retry
            )
        if response.status_code == 404:
            return []
        if response.status_code != 200:
            raise unexpected_status(SOURCE, response)

        body = json_body(SOURCE, response)
        records = body.get("data") if isinstance(body, dict) else None
        if not records:
            logger.debug("%s %s: no records", SOURCE, target)
            return []

        normalized = [
            {
                "rrtype": str(item.get("rrtype", "")),
                "query": str(item.get("query", "")),
                "answer": str(item.get("answer", "")),
                "first_seen": _iso_ms(item.get("firstSeenTimestamp")),
                "last_seen": _iso_ms(item.get("lastSeenTimestamp")),
                "times": int(item.get("times") or 0),
                "max_ttl": int(item.get("maxTtl") or 0),
            }
            for item in records
            if isinstance(item, dict)
        ]
        first = sorted(r["first_seen"] for r in normalized if r["first_seen"])
        last = sorted(r["last_seen"] for r in normalized if r["last_seen"])
        primary: dict[str, Any] = {
            "type": sco_type,
            "value": target,
            "x_mnemonic_pdns_records": normalized,
            "x_mnemonic_pdns_total": int(body.get("count") or len(normalized)),
            "x_mnemonic_pdns_returned": len(normalized),
            "x_mnemonic_pdns_first_seen": first[0] if first else "",
            "x_mnemonic_pdns_last_seen": last[-1] if last else "",
        }
        results: list[dict] = [primary]
        seen = {(sco_type, target)}
        for record in normalized:
            if len(results) - 1 >= _MAX_NEIGHBOURS:
                break
            if record["rrtype"] not in {"a", "aaaa", "cname"}:
                continue
            # The neighbour is whichever side of the record is not the target.
            other = record["answer"] if record["query"].rstrip(".").lower() == target else record["query"]
            other = other.rstrip(".").lower()
            other_type = _address_type(other) or ("domain-name" if detect_ioc_type(other) == "domain" else None)
            if other_type is None or (other_type, other) in seen:
                continue
            seen.add((other_type, other))
            results.append({
                "type": other_type,
                "value": other,
                "x_mnemonic_pdns_resolution_of": target,
            })
        return results
