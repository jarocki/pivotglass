"""SANS Internet Storm Center (DShield) IP module (keyless).

API: GET {base}/ip/{ip}?json  (base default https://isc.sans.edu/api)
Docs: https://isc.sans.edu/api/

@decision DEC-MODULE-SANS-ISC-001
@title DShield sensor reports and feed membership as context; generic User-Agent
@status accepted
@rationale ISC asks API clients for a descriptive User-Agent; the shared keyless
           helper sends ``pivotglass/<version>`` with no contact detail. ``count``
           is the number of DShield sensor reports and ``attacks`` the number of
           distinct targets; both are null for an address with no reports, which
           becomes 0, an explicit "no reports" result. ``threatfeeds`` lists the
           ISC feeds the address appears in (for example ``openresolver`` or
           ``miner`` for 8.8.8.8): feed membership is context, not a verdict.
           ``asabusecontact`` is deliberately not copied because it can be a
           personal mailbox. A body of ``{"error": ...}`` (bad address) is a
           ModuleError. IPv6 is not offered: ISC's IP data is IPv4-centric.
"""

from __future__ import annotations

from typing import Any

import httpx

from pivotglass.core.ioc_types import detect_ioc_type
from pivotglass.modules.base import BaseModule, ModuleError
from pivotglass.modules.keyless_http import json_body, keyless_get, unexpected_status

SOURCE = "SANS ISC"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class SansIsc(BaseModule):
    """DShield attack reports, first/last reported, AS, and ISC feed membership (no key)."""

    name = "osint/sans_isc"
    description = "DShield attack reports, AS, and ISC feed membership via SANS ISC (no key)"
    author = "Pivotglass"
    module_type = "osint"
    service_id = "sans_isc"
    accepts = ("ipv4",)
    requires_api_key = False
    transport: httpx.AsyncBaseTransport | None = None

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {"required": True, "description": "IPv4 address", "default": ""},
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        target = target.strip()
        if detect_ioc_type(target) != "ipv4":
            raise ModuleError(f"{SOURCE} accepts an IPv4 address; '{target}' is not one.")
        response = await keyless_get(
            SOURCE, f"{self.base_url}/ip/{target}", params={"json": ""}, transport=self.transport
        )
        if response.status_code == 404:
            return []
        if response.status_code != 200:
            raise unexpected_status(SOURCE, response)
        body = json_body(SOURCE, response)
        if isinstance(body, dict) and body.get("error"):
            raise ModuleError(f"{SOURCE} rejected the query: {str(body['error'])[:120]}")
        data = body.get("ip") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise ModuleError(f"{SOURCE} returned an unexpected response shape; no result recorded.")
        feeds = data.get("threatfeeds") if isinstance(data.get("threatfeeds"), dict) else {}
        return [
            {
                "type": "ipv4-addr",
                "value": str(data.get("number") or target),
                "x_sans_isc_reports": _int(data.get("count")),
                "x_sans_isc_targets": _int(data.get("attacks")),
                "x_sans_isc_first_reported": str(data.get("mindate") or ""),
                "x_sans_isc_last_reported": str(data.get("maxdate") or ""),
                "x_sans_isc_updated": str(data.get("updated") or ""),
                "x_sans_isc_comment": str(data.get("comment") or ""),
                "x_sans_isc_asn": _int(data.get("as")),
                "x_sans_isc_as_name": str(data.get("asname") or ""),
                "x_sans_isc_as_country": str(data.get("ascountry") or ""),
                "x_sans_isc_network": str(data.get("network") or ""),
                "x_sans_isc_feeds": [
                    {
                        "feed": str(name),
                        "first_seen": str((entry or {}).get("firstseen") or ""),
                        "last_seen": str((entry or {}).get("lastseen") or ""),
                    }
                    for name, entry in feeds.items()
                    if isinstance(entry, dict) or entry is None
                ],
            }
        ]
