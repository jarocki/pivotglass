"""NVD CVE API 2.0 module: description, CVSS, CWEs, affected configurations (keyless).

API: GET {base}/rest/json/cves/2.0?cveId=CVE-...  (base default https://services.nvd.nist.gov)
Docs: https://nvd.nist.gov/developers/vulnerabilities

@decision DEC-MODULE-NVD-CVE-001
@title Unauthenticated NVD: a process-wide 5-per-30-seconds limiter; 403/429/503 mean "retry later"
@status accepted
@rationale NVD allows 5 requests per rolling 30 seconds without an API key. Several
           CVEs pivoted at once (an InternetDB host can list dozens) would exceed that
           and get the address blocked, so every request first passes ``NVD_LIMITER``,
           a sliding window shared by the whole process (the lock is a threading lock
           because each asyncio.run has its own event loop). The limiter waits rather
           than failing: a queued CVE is slower, not lost. If NVD still answers 403,
           429 or 503, the module raises a ModuleError whose message says the service
           is rate limited and to retry later, naming the status. An unknown CVE returns
           HTTP 200 with ``totalResults: 0`` (verified 2026-11-27) and yields ``[]``; a
           malformed id returns 404 and is a ModuleError. The result is one
           ``vulnerability`` dict. ``description`` is the English description.
           ``x_nvd_cvss`` lists every ``metrics.cvssMetric*`` entry (3.1, 3.0, 4.0 and
           2.0 as published; the 2.0 severity sits beside ``cvssData`` rather than in
           it), each with its source and Primary/Secondary type, because CNA and NVD
           scores can differ and the module does not choose between them. Other metric
           families (for example ``ssvcV203``) are not CVSS and are ignored.
           ``x_nvd_cwes`` is every weakness id, NVD's placeholders included.
           ``x_nvd_configurations`` holds only ``vulnerable: true`` CPE matches (the
           ``false`` ones are platform context), capped at 200 with
           ``x_nvd_configurations_truncated``; ``x_nvd_references`` is capped at 100.
           NVD data is analysis by NIST and CNAs, not an observation that any host in
           the investigation is affected. Only ``x_nvd_*`` fields and ``description``
           are written (DEC-MODULE-VULNERABILITY-001).
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

import httpx

from pivotglass.modules.base import BaseModule, ModuleError, RateLimitError
from pivotglass.modules.keyless_http import json_body, keyless_get
from pivotglass.modules.vulnerability import cve_target, vulnerability_object

SOURCE = "NVD"
MAX_CONFIGURATIONS = 200
MAX_REFERENCES = 100
_RATE_LIMIT_STATUSES = frozenset({403, 429, 503})


class SlidingWindowLimiter:
    """At most *limit* acquisitions in any rolling *window* seconds; waits, never drops."""

    def __init__(
        self,
        limit: int,
        window: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        self._limit = limit
        self._window = window
        self._clock = clock
        self._sleep = sleep
        self._stamps: deque[float] = deque()
        self._lock = threading.Lock()

    def _reserve(self) -> float:
        """Return 0 after recording a slot, else the seconds until one frees."""
        with self._lock:
            now = self._clock()
            while self._stamps and now - self._stamps[0] >= self._window:
                self._stamps.popleft()
            if len(self._stamps) < self._limit:
                self._stamps.append(now)
                return 0.0
            return self._stamps[0] + self._window - now

    async def acquire(self) -> None:
        while (wait := self._reserve()) > 0:
            await self._sleep(wait)


NVD_LIMITER = SlidingWindowLimiter(limit=5, window=30.0)


def _cvss(metrics: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(metrics, dict):
        return out
    for key, entries in metrics.items():
        if not key.startswith("cvssMetric") or not isinstance(entries, list):
            continue
        for entry in entries:
            data = entry.get("cvssData") if isinstance(entry, dict) else None
            if not isinstance(data, dict):
                continue
            out.append(
                {
                    "version": str(data.get("version", "")),
                    "vector": str(data.get("vectorString", "")),
                    "base_score": data.get("baseScore"),
                    "base_severity": str(data.get("baseSeverity") or entry.get("baseSeverity") or ""),
                    "source": str(entry.get("source", "")),
                    "type": str(entry.get("type", "")),
                }
            )
    return out


def _cwes(weaknesses: Any) -> list[str]:
    found: list[str] = []
    for weakness in weaknesses if isinstance(weaknesses, list) else []:
        for desc in weakness.get("description", []) if isinstance(weakness, dict) else []:
            value = desc.get("value") if isinstance(desc, dict) else None
            if value and value not in found:
                found.append(str(value))
    return found


def _configurations(configurations: Any) -> tuple[list[dict[str, Any]], bool]:
    matches: list[dict[str, Any]] = []
    truncated = False
    for config in configurations if isinstance(configurations, list) else []:
        for node in config.get("nodes", []) if isinstance(config, dict) else []:
            for match in node.get("cpeMatch", []) if isinstance(node, dict) else []:
                if not isinstance(match, dict) or match.get("vulnerable") is not True:
                    continue
                if len(matches) >= MAX_CONFIGURATIONS:
                    truncated = True
                    continue
                matches.append(
                    {
                        "criteria": str(match.get("criteria", "")),
                        "version_start_including": match.get("versionStartIncluding"),
                        "version_start_excluding": match.get("versionStartExcluding"),
                        "version_end_including": match.get("versionEndIncluding"),
                        "version_end_excluding": match.get("versionEndExcluding"),
                    }
                )
    return matches, truncated


def _references(references: Any) -> list[dict[str, Any]]:
    out = []
    for ref in (references if isinstance(references, list) else [])[:MAX_REFERENCES]:
        if isinstance(ref, dict) and ref.get("url"):
            tags = ref.get("tags")
            out.append(
                {
                    "url": str(ref["url"]),
                    "source": str(ref.get("source", "")),
                    "tags": [str(t) for t in tags] if isinstance(tags, list) else [],
                }
            )
    return out


def _english(descriptions: Any) -> str:
    for desc in descriptions if isinstance(descriptions, list) else []:
        if isinstance(desc, dict) and desc.get("lang") == "en" and desc.get("value"):
            return str(desc["value"])
    return ""


class NvdCve(BaseModule):
    """NVD record for a CVE: description, CVSS, CWEs, configurations, references (no key)."""

    name = "cti/nvd_cve"
    description = "CVE description, CVSS, CWEs, affected products and references via NVD (no key; 5 requests per 30 s)"
    author = "Pivotglass"
    module_type = "cti"
    service_id = "nvd_cve"
    accepts = ("cve",)
    requires_api_key = False
    transport: httpx.AsyncBaseTransport | None = None
    limiter: SlidingWindowLimiter = NVD_LIMITER

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {"required": True, "description": "CVE identifier (CVE-YYYY-NNNN)", "default": ""},
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        cve = cve_target(SOURCE, target)
        await self.limiter.acquire()
        try:
            response = await keyless_get(
                SOURCE,
                f"{self.base_url}/rest/json/cves/2.0",
                params={"cveId": cve},
                timeout=30.0,
                transport=self.transport,
            )
        except RateLimitError as exc:
            raise RateLimitError(
                f"{SOURCE} is rate limited (HTTP 429); retry later.", retry_after=exc.retry_after
            ) from exc
        if response.status_code in _RATE_LIMIT_STATUSES:
            raise RateLimitError(f"{SOURCE} is rate limited (HTTP {response.status_code}); retry later.")
        if response.status_code == 404:
            raise ModuleError(f"{SOURCE} rejected '{cve}' as a malformed CVE identifier.")
        if response.status_code != 200:
            raise ModuleError(f"{SOURCE} returned HTTP {response.status_code}; no result recorded.")
        body = json_body(SOURCE, response)
        rows = body.get("vulnerabilities") if isinstance(body, dict) else None
        if not isinstance(rows, list):
            raise ModuleError(f"{SOURCE} returned an unexpected response shape; no result recorded.")
        record = next(
            (r["cve"] for r in rows if isinstance(r, dict) and str(r.get("cve", {}).get("id", "")).upper() == cve),
            None,
        )
        if record is None:
            return []
        configurations, truncated = _configurations(record.get("configurations"))
        return [
            vulnerability_object(
                cve,
                description=_english(record.get("descriptions")),
                x_nvd_published=str(record.get("published", "")),
                x_nvd_last_modified=str(record.get("lastModified", "")),
                x_nvd_vuln_status=str(record.get("vulnStatus", "")),
                x_nvd_cvss=_cvss(record.get("metrics")),
                x_nvd_cwes=_cwes(record.get("weaknesses")),
                x_nvd_configurations=configurations,
                x_nvd_configurations_truncated=truncated,
                x_nvd_references=_references(record.get("references")),
            )
        ]
