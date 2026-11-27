"""CISA Known Exploited Vulnerabilities (KEV) catalog module (keyless).

Feed: GET {base}/sites/default/files/feeds/known_exploited_vulnerabilities.json
      (base default https://www.cisa.gov)
Docs: https://www.cisa.gov/known-exploited-vulnerabilities-catalog

@decision DEC-MODULE-CISA-KEV-001
@title KEV is one whole-catalog file, cached in memory; "not listed" is evidence, not an empty result
@status accepted
@rationale CISA publishes KEV only as a single JSON file (about 1.9 MB, roughly 1,800
           entries; verified 2026-11-27), so there is no per-CVE query. The module
           fetches the file once and keeps an index of it for the process for
           ``CATALOG_TTL_SECONDS`` (6 hours); every CVE looked up in that window
           reads the cache, never the network. The cache is keyed by base URL so a
           gateway override never serves another endpoint's catalog. A failed fetch
           is a ModuleError and is not cached, and an expired cache is never served
           after a failed refresh: stale "not listed" answers would read as current.
           One ``vulnerability`` dict is returned for every valid CVE. A CVE absent
           from the catalog returns ``x_kev_listed: false`` plus ``x_kev_catalog_version``
           and ``x_kev_catalog_released``, because "checked and not listed in version
           X" is evidence and "not checked" is not. Listed CVEs add
           ``x_kev_date_added``, ``x_kev_due_date``, ``x_kev_known_ransomware`` (the
           feed's ``knownRansomwareCampaignUse`` string as published), ``x_kev_vendor``,
           ``x_kev_product``, ``x_kev_vulnerability_name``, ``x_kev_required_action``,
           ``x_kev_notes`` and ``x_kev_cwes``. The module writes only ``x_kev_*``
           fields (DEC-MODULE-VULNERABILITY-001). KEV membership means CISA has
           evidence of exploitation in the wild; it does not say the CVE affects any
           host in the investigation.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from pivotglass.modules.base import BaseModule, ModuleError
from pivotglass.modules.keyless_http import json_body, keyless_get, unexpected_status
from pivotglass.modules.vulnerability import cve_target, vulnerability_object

SOURCE = "CISA KEV"
FEED_PATH = "/sites/default/files/feeds/known_exploited_vulnerabilities.json"
CATALOG_TTL_SECONDS = 6 * 60 * 60
_FETCH_TIMEOUT = 60.0  # the catalog is ~1.9 MB


@dataclass(frozen=True)
class _Catalog:
    version: str
    released: str
    entries: dict[str, dict[str, Any]]
    fetched_at: float


# Process-wide cache, keyed by feed URL. A threading.Lock guards the dict only;
# it is never held across an await (each asyncio.run has its own event loop).
_CACHE: dict[str, _Catalog] = {}
_CACHE_LOCK = threading.Lock()
_clock = time.monotonic


def clear_catalog_cache() -> None:
    """Drop every cached catalog (tests, and an analyst forcing a refresh)."""
    with _CACHE_LOCK:
        _CACHE.clear()


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value if item] if isinstance(value, list) else []


async def _catalog(url: str, transport: httpx.AsyncBaseTransport | None) -> _Catalog:
    with _CACHE_LOCK:
        cached = _CACHE.get(url)
    if cached is not None and _clock() - cached.fetched_at < CATALOG_TTL_SECONDS:
        return cached
    response = await keyless_get(SOURCE, url, timeout=_FETCH_TIMEOUT, transport=transport)
    if response.status_code != 200:
        raise unexpected_status(SOURCE, response)
    data = json_body(SOURCE, response)
    rows = data.get("vulnerabilities") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not data.get("catalogVersion"):
        raise ModuleError(f"{SOURCE} returned an unexpected catalog shape; no result recorded.")
    entries = {
        str(row["cveID"]).strip().upper(): row
        for row in rows
        if isinstance(row, dict) and row.get("cveID")
    }
    catalog = _Catalog(
        version=str(data["catalogVersion"]),
        released=str(data.get("dateReleased") or ""),
        entries=entries,
        fetched_at=_clock(),
    )
    with _CACHE_LOCK:
        _CACHE[url] = catalog
    return catalog


class CisaKev(BaseModule):
    """Is a CVE in CISA's Known Exploited Vulnerabilities catalog? (no key)"""

    name = "cti/cisa_kev"
    description = "Known-exploited status from the CISA KEV catalog (no key; catalog cached 6 hours)"
    author = "Pivotglass"
    module_type = "cti"
    service_id = "cisa_kev"
    accepts = ("cve",)
    requires_api_key = False
    transport: httpx.AsyncBaseTransport | None = None

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {"required": True, "description": "CVE identifier (CVE-YYYY-NNNN)", "default": ""},
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        cve = cve_target(SOURCE, target)
        catalog = await _catalog(f"{self.base_url}{FEED_PATH}", self.transport)
        fields: dict[str, Any] = {
            "x_kev_catalog_version": catalog.version,
            "x_kev_catalog_released": catalog.released,
        }
        row = catalog.entries.get(cve)
        if row is None:
            return [vulnerability_object(cve, x_kev_listed=False, **fields)]
        return [
            vulnerability_object(
                cve,
                x_kev_listed=True,
                **fields,
                x_kev_date_added=str(row.get("dateAdded") or ""),
                x_kev_due_date=str(row.get("dueDate") or ""),
                x_kev_known_ransomware=str(row.get("knownRansomwareCampaignUse") or ""),
                x_kev_vendor=str(row.get("vendorProject") or ""),
                x_kev_product=str(row.get("product") or ""),
                x_kev_vulnerability_name=str(row.get("vulnerabilityName") or ""),
                x_kev_required_action=str(row.get("requiredAction") or ""),
                x_kev_notes=str(row.get("notes") or ""),
                x_kev_cwes=_strings(row.get("cwes")),
            )
        ]
