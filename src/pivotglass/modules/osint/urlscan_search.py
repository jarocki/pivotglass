"""Read-only, bounded search of existing URLScan scans for an IP or domain."""

from __future__ import annotations

import ipaddress
import re
from typing import Any

import httpx

from pivotglass.modules.base import AuthenticationError, BaseModule, RateLimitError

_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")
_MAX_SCANS = 10


class URLScanSearch(BaseModule):
    """Find existing URLScan observations without submitting a URL."""

    name = "osint/urlscan_search"
    description = "Search existing URLScan results for a domain or IPv4 address"
    author = "Pivotglass"
    module_type = "osint"
    accepts = ("ipv4", "domain")

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {"required": True, "description": "Domain or IPv4 address", "default": ""},
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        key = self._config.get("api_key", "")
        if not key:
            raise AuthenticationError("URLScan API key is not configured.")
        try:
            address = ipaddress.ip_address(target)
        except ValueError:
            address = None
        if address is not None:
            if address.version != 4:
                raise ValueError("URLScan search currently supports IPv4 addresses and domains")
            query = f"page.ip:{target}"
            sco_type = "ipv4-addr"
        else:
            if not _DOMAIN_RE.fullmatch(target) or ".." in target:
                raise ValueError("URLScan search requires a domain or IPv4 address")
            query = f"page.domain:{target}"
            sco_type = "domain-name"

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                "https://urlscan.io/api/v1/search",
                params={"q": query, "size": _MAX_SCANS},
                headers={"api-key": key, "Accept": "application/json"},
            )
        if response.status_code == 401:
            raise AuthenticationError("URLScan API key was rejected.")
        if response.status_code == 429:
            raise RateLimitError("URLScan search quota was exceeded.")
        response.raise_for_status()
        data = response.json()
        matches: list[dict[str, str]] = []
        related: list[dict] = []
        seen_urls: set[str] = set()
        for item in data.get("results", [])[:_MAX_SCANS]:
            if not isinstance(item, dict):
                continue
            task = item.get("task") or {}
            page = item.get("page") or {}
            if not isinstance(task, dict) or not isinstance(page, dict):
                continue
            scan_id = str(task.get("uuid") or item.get("_id") or "")
            page_url = str(page.get("url") or "")
            match = {
                "scan_id": scan_id,
                "task_url": str(task.get("url") or ""),
                "page_url": page_url,
                "scan_time": str(task.get("time") or ""),
                "result_url": str(item.get("result") or ""),
                "screenshot_url": str(item.get("screenshot") or ""),
            }
            matches.append(match)
            if page_url and page_url not in seen_urls:
                seen_urls.add(page_url)
                related.append({
                    "type": "url",
                    "value": page_url,
                    "x_scan_uuid": scan_id,
                    "x_scan_time": match["scan_time"],
                    "x_result_url": match["result_url"],
                })
        primary = {
            "type": sco_type,
            "value": target,
            "x_urlscan_search_total": data.get("total", 0),
            "x_urlscan_matches": matches,
        }
        return [primary, *related]
