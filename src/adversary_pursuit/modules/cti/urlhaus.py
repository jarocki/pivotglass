"""abuse.ch URLhaus URL blocklist module.

Queries the URLhaus API for malicious URL information given a URL or host.
URLhaus is a community project operated by abuse.ch to collect and share
malicious URLs used for malware distribution.

API docs: https://urlhaus-api.abuse.ch/

@decision DEC-MODULE-URLHAUS-001
@title POST-based keyless API with host/url dispatch
@status accepted
@rationale URLhaus exposes two endpoints: /v1/url/ for full URL lookups and
           /v1/host/ for IP/domain host lookups. The correct endpoint is chosen
           by a simple heuristic: if the target starts with "http://" or "https://"
           it is a URL; otherwise it is a host. Both endpoints use POST with a
           JSON body (not a query string) per the URLhaus API spec. No API key
           is required — URLhaus is freely accessible. TIMEOUT = 60.0 per the
           project standard for external CTI sources (DEC-61-MODULES-TIMEOUT-001).

@decision DEC-MODULE-URLHAUS-002
@title query_status != 'is_listed' mapped to empty list, not an error
@status accepted
@rationale URLhaus returns query_status='no_results' when a URL/host has no
           known malicious entries. This is a valid "clean" result — not an
           error condition. Returning an empty list preserves the uniform
           list[dict] return type and lets callers distinguish "no results"
           from "error". Other non-error statuses (e.g. 'is_whitelisted') are
           also mapped to empty list for the same reason.

@decision DEC-MODULE-URLHAUS-003
@title One url--<uuid5> SCO per URL entry in the response
@status accepted
@rationale Each entry in the URLhaus 'urls' array maps to a STIX 2.1 url SCO
           (per DEC-STIX-001/002). Custom fields use the x_abuse_ namespace to
           group all URLhaus-specific metadata without colliding with other
           abuse.ch modules. SCO ID is uuid5 namespaced on the URL value to
           produce stable, deterministic identifiers across re-queries.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from adversary_pursuit.modules.base import (
    BaseModule,
    RateLimitError,
)

logger = logging.getLogger(__name__)

TIMEOUT = 60.0

# URLhaus namespace for deterministic SCO IDs (uuid5 per DEC-STIX-001)
_URLHAUS_NS = uuid.UUID("6ba7b812-9dad-11d1-80b4-00c04fd430c8")


class URLHaus(BaseModule):
    """Check URLs and hosts against the abuse.ch URLhaus malicious URL blocklist.

    URLhaus collects malicious URLs used for malware distribution and provides
    a free, keyless public API for lookups. Returns STIX 2.1 url SCO dicts
    with x_abuse_* custom fields for each matching URL record.

    No API key is required. Accepts both full URLs (https://...) and
    plain host values (IP address or domain name).

    Returns a list of STIX 2.1 url SCO dicts with x_abuse_* custom properties.
    See DEC-MODULE-URLHAUS-003.
    """

    name = "cti/urlhaus"
    description = "Check URLs/hosts against abuse.ch URLhaus malicious URL blocklist"
    author = "Adversary Pursuit"
    module_type = "cti"
    requires_api_key = False

    _HOST_URL = "https://urlhaus-api.abuse.ch/v1/host/"
    _URL_URL = "https://urlhaus-api.abuse.ch/v1/url/"

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {
                "required": True,
                "description": "URL (https://...) or host (IP/domain) to check",
                "default": "",
            },
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        """Query URLhaus for malicious URL records associated with a URL or host.

        Parameters
        ----------
        target:
            A full URL (starting with http:// or https://) or a plain host
            (IPv4 address or domain name).
        options:
            Runtime overrides (no module-specific options for URLhaus).

        Returns
        -------
        list[dict]
            Zero or more url STIX 2.1 SCO dicts. Empty list when no records
            are found (query_status='no_results'). Each dict has:
              type: "url"
              value: the malicious URL string
              x_abuse_tags: list of tag strings
              x_abuse_threat: threat type string (e.g. "malware_download")
              x_abuse_reporter: reporter identifier string
              x_abuse_dateadded: ISO 8601 date string when the URL was added

        Raises
        ------
        RateLimitError
            When the API returns 429. retry_after is populated from the
            Retry-After response header when present.
        httpx.HTTPStatusError
            For unexpected 4xx/5xx responses not handled above.
        httpx.RequestError
            For network-level failures (DNS, timeout, connection refused).
        """
        # Determine endpoint and payload by target shape
        is_url = target.startswith("http://") or target.startswith("https://")
        endpoint = self._URL_URL if is_url else self._HOST_URL
        payload = {"url": target} if is_url else {"host": target}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                endpoint,
                json=payload,
                headers={"Accept": "application/json"},
                timeout=TIMEOUT,
            )

            if response.status_code == 429:
                retry_header = response.headers.get("Retry-After")
                retry_after = int(retry_header) if retry_header else None
                raise RateLimitError(
                    "URLhaus API rate limit exceeded.",
                    retry_after=retry_after,
                )

            response.raise_for_status()
            data = response.json()

        query_status = data.get("query_status", "")
        # 'no_results' or 'is_whitelisted' or any non-'is_listed' → clean, return []
        if query_status != "is_listed":
            logger.debug("URLhaus %s: query_status=%s (no malicious results)", target, query_status)
            return []

        urls_data = data.get("urls", [])
        results = []
        seen: set[str] = set()
        for entry in urls_data:
            url_value = entry.get("url", "")
            if not url_value or url_value in seen:
                continue
            seen.add(url_value)
            sco = _build_url_sco(url_value, entry)
            results.append(sco)

        logger.debug("URLhaus %s: found %d URL records", target, len(results))
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_url_sco(url_value: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Construct a STIX 2.1 url SCO dict from a URLhaus URL entry.

    Parameters
    ----------
    url_value:
        The URL string (used as the 'value' field and for uuid5 ID).
    entry:
        One element from the URLhaus 'urls' array in the API response.

    Returns
    -------
    dict
        url SCO with x_abuse_* custom fields per DEC-MODULE-URLHAUS-003.
    """
    sco_id = f"url--{uuid.uuid5(_URLHAUS_NS, url_value)}"
    tags = entry.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    return {
        "type": "url",
        "id": sco_id,
        "value": url_value,
        "x_abuse_tags": list(tags),
        "x_abuse_threat": entry.get("threat", ""),
        "x_abuse_reporter": entry.get("reporter", ""),
        "x_abuse_dateadded": entry.get("date_added", ""),
    }
