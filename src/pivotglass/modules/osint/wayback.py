"""Wayback Machine capture history module (keyless CDX API).

API: GET {base}/cdx/search/cdx?url=...&output=json  (base default https://web.archive.org)
Docs: https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server

@decision DEC-MODULE-WAYBACK-001
@title Two bounded CDX queries: one capture per month, then the latest capture
@status accepted
@rationale Counting every capture of a popular site would page through millions of
           rows. The first query collapses on ``timestamp:6`` (one row per month,
           at most 1000 rows), which yields the first capture and the number of
           months with captures. The second asks for ``limit=-1``, the single most
           recent capture. An empty array means the archive holds nothing for the
           URL, an empty result. The CDX server answers 429/503 under load; 429 is
           a RateLimitError and other statuses a ModuleError. Capture history shows
           when the archive saw content, not who published it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from pivotglass.core.ioc_types import detect_ioc_type
from pivotglass.modules.base import BaseModule, ModuleError
from pivotglass.modules.keyless_http import json_body, keyless_get, unexpected_status

SOURCE = "Wayback Machine"
_MONTH_LIMIT = 1000
_TIMEOUT = 30.0
_SCO_TYPES = {"domain": "domain-name", "url": "url"}


def _iso(timestamp: str) -> str:
    try:
        moment = datetime.strptime(timestamp[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return ""
    return moment.isoformat().replace("+00:00", "Z")


def _rows(source_body: Any) -> list[dict[str, str]]:
    """CDX JSON is a header row followed by value rows."""
    if not isinstance(source_body, list) or len(source_body) < 2 or not isinstance(source_body[0], list):
        return []
    header = [str(name) for name in source_body[0]]
    return [dict(zip(header, map(str, row))) for row in source_body[1:] if isinstance(row, list)]


class Wayback(BaseModule):
    """First and last Wayback Machine capture and months captured for a domain or URL (no key)."""

    name = "osint/wayback"
    description = "First/last capture and capture months via the Wayback Machine CDX API (no key)"
    author = "Pivotglass"
    module_type = "osint"
    service_id = "wayback"
    accepts = ("domain", "url")
    requires_api_key = False
    transport: httpx.AsyncBaseTransport | None = None

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {"required": True, "description": "Domain or URL", "default": ""},
        }

    async def _query(self, target: str, **params: Any) -> list[dict[str, str]]:
        response = await keyless_get(
            SOURCE,
            f"{self.base_url}/cdx/search/cdx",
            params={"url": target, "output": "json", "fl": "timestamp,original,statuscode", **params},
            timeout=_TIMEOUT,
            transport=self.transport,
        )
        if response.status_code == 404:
            return []
        if response.status_code != 200:
            raise unexpected_status(SOURCE, response)
        if not response.content.strip():
            return []
        return _rows(json_body(SOURCE, response))

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        target = target.strip()
        kind = detect_ioc_type(target) or ""
        sco_type = _SCO_TYPES.get(kind)
        if sco_type is None:
            raise ModuleError(f"{SOURCE} accepts a domain or URL; '{target}' is neither.")
        if kind == "domain":
            target = target.rstrip(".").lower()

        months = await self._query(target, collapse="timestamp:6", limit=_MONTH_LIMIT)
        if not months:
            return []
        latest = await self._query(target, limit=-1) or months[-1:]
        first, last = months[0], latest[-1]

        def archive_url(row: dict[str, str]) -> str:
            return f"https://web.archive.org/web/{row.get('timestamp', '')}/{row.get('original', '')}"

        return [
            {
                "type": sco_type,
                "value": target,
                "x_wayback_first_capture": _iso(first.get("timestamp", "")),
                "x_wayback_last_capture": _iso(last.get("timestamp", "")),
                "x_wayback_first_capture_url": archive_url(first),
                "x_wayback_last_capture_url": archive_url(last),
                "x_wayback_capture_months": len(months),
                "x_wayback_capture_months_truncated": len(months) >= _MONTH_LIMIT,
            }
        ]
