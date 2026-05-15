"""URLScan.io URL analysis module.

Submits URLs for scanning and retrieves results including page details,
IP addresses, domains contacted, and certificate information.

API docs: https://urlscan.io/docs/api/

Flow: POST /api/v1/scan/ (submit) -> poll GET /api/v1/result/{uuid}/ -> parse results

@decision DEC-MODULE-URLSCAN-001
@title Async submit+poll pattern with configurable timeout and poll interval
@status accepted
@rationale URLScan.io scans are asynchronous — submission returns a UUID,
           results become available after processing (typically 10-30s). The
           module polls with asyncio.sleep between attempts until results are
           ready (200) or timeout is reached. 404 during polling means "not
           ready yet" (the URLScan API convention); any other non-200 status
           is raised via raise_for_status(). This is the first module to
           demonstrate real async behavior in hunt().

@decision DEC-MODULE-URLSCAN-002
@title asyncio imported at module level, sleep called as asyncio.sleep
@status accepted
@rationale Importing asyncio at module level and calling asyncio.sleep (not
           `from asyncio import sleep`) makes the sleep call patchable by
           tests via `patch("adversary_pursuit.modules.osint.urlscan.asyncio.sleep")`.
           This is the standard pattern for making asyncio primitives
           mockable without altering the production call signature.

@decision DEC-MODULE-URLSCAN-003
@title Deduplication via a seen set seeded with target, page domain, and page IP
@status accepted
@rationale URLScan result lists (lists.ips, lists.domains) frequently include
           the same values as the primary page object. The seen set prevents
           emitting duplicate SCOs. The target URL, page domain, and page IP
           are pre-seeded. Empty strings are pre-seeded to prevent emitting
           SCOs for missing fields. This matches the pattern from OTX passive
           DNS deduplication (DEC-MODULE-OTX-003).

@decision DEC-MODULE-URLSCAN-004
@title Lists capped at 15 entries each (IPs and domains)
@status accepted
@rationale URLScan results can include hundreds of IPs and domains contacted
           during a page load (ads, CDN, analytics). Returning all of them
           would overwhelm downstream consumers and inflate STIX bundles.
           15 entries each is a practical limit for the hunting use case —
           enough to spot C2 / CDN overlap without noise. Future implementers
           can expose a MAX_RESULTS option if needed.

@decision DEC-MODULE-URLSCAN-005
@title Submit endpoint URL uses trailing slash: https://urlscan.io/api/v1/scan/
@status accepted
@rationale The canonical urlscan.io/docs/api/ curl reference uses the trailing
           slash: https://urlscan.io/api/v1/scan/. URLScan is fronted by
           Cloudflare, which returns HTTP 403 for unmatched paths before the
           request reaches the auth layer — omitting the slash causes Cloudflare
           to return 403 even with a valid API key. The slash-less variant
           https://urlscan.io/api/v1/scan (no slash) is NOT canonical.
           This endpoint string must remain singular and exact; do not introduce
           a fallback retry without the slash.
           Reference: https://urlscan.io/docs/api/

@decision DEC-MODULE-URLSCAN-006
@title 403 from submit endpoint raises AuthenticationError (same as 401)
@status accepted
@rationale HTTP 403 from URLScan submit can mean two things: (a) Cloudflare
           path mismatch (resolved by DEC-MODULE-URLSCAN-005 trailing slash),
           or (b) API key exists but lacks permission for this scan type (plan
           tier restriction, private-scan allowance, region restriction). In
           either case raising AuthenticationError keeps the smoke-test
           classification contract: AuthenticationError -> SKIP (not FAIL).
           The message deliberately mentions "403" and "forbidden" to distinguish
           it from the 401 "invalid or revoked" message, aiding debugging.
           Reference: scripts/smoke_test.py _run_urlscan classification logic.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from adversary_pursuit.modules.base import (
    AuthenticationError,
    BaseModule,
    RateLimitError,
)

logger = logging.getLogger(__name__)

_SUBMIT_URL = "https://urlscan.io/api/v1/scan/"
_LIST_CAP = 15


class URLScan(BaseModule):
    """Submit and analyze URLs via URLScan.io.

    Submits a URL for scanning, polls for results, and returns STIX 2.1 SCO
    dicts representing the scanned URL, contacted domains, and contacted IPs.

    Requires an API key from https://urlscan.io/ (free tier: 5,000 scans/month).
    Configure via:
      ap config set api_keys.urlscan <key>
    or the AP_URLSCAN_API_KEY environment variable.

    The scan is asynchronous — submission returns a UUID, and results are
    polled until ready (200) or timeout is reached. See DEC-MODULE-URLSCAN-001.

    Returns
    -------
    list of STIX-like SCO dicts:
      - url SCO (always first) with x_scan_uuid, x_effective_url, x_page_title,
        x_page_status, x_server, x_screenshot_url
      - domain-name SCO for the page domain (if present)
      - ipv4-addr SCO for the page IP (if present), with x_asn
      - Additional domain-name and ipv4-addr SCOs from lists (capped at 15 each)

    On timeout, returns a single url SCO with x_scan_status="timeout".
    """

    name = "osint/urlscan"
    description = "Submit and analyze URLs via URLScan.io"
    author = "Adversary Pursuit"
    module_type = "osint"

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {
                "required": True,
                "description": "URL to scan",
                "default": "",
            },
            "VISIBILITY": {
                "required": False,
                "description": "Scan visibility: public, unlisted, private",
                "default": "unlisted",
            },
            "TIMEOUT": {
                "required": False,
                "description": "Max seconds to wait for results",
                "default": "60",
            },
            "POLL_INTERVAL": {
                "required": False,
                "description": "Seconds between poll attempts",
                "default": "5",
            },
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        """Submit URL for scanning, poll for results, return STIX dicts.

        Flow:
        1. Validate API key present — raise AuthenticationError if missing.
        2. POST /api/v1/scan with url and visibility, handle 401/429.
        3. Extract UUID and result URL from submit response.
        4. Poll GET /api/v1/result/{uuid}/ with asyncio.sleep(POLL_INTERVAL)
           between attempts until 200 or TIMEOUT is reached.
        5. On timeout return a stub url SCO with x_scan_status="timeout".
        6. On success parse results into STIX SCO dicts.

        Parameters
        ----------
        target:
            The URL to scan (e.g. "https://evil.example.com/malware")
        options:
            Runtime overrides:
              VISIBILITY    — scan visibility ("public", "unlisted", "private")
              TIMEOUT       — max seconds to poll (default "60")
              POLL_INTERVAL — seconds between poll attempts (default "5")

        Returns
        -------
        list[dict]
            STIX-like SCO dicts. See class docstring for full schema.

        Raises
        ------
        AuthenticationError
            When no API key is configured; when the API returns 401 on submit
            (key invalid or revoked); or when the API returns 403 on submit
            (key lacks permission for this scan — plan tier, visibility
            allowance, or region restriction). Both 401 and 403 raise
            AuthenticationError so the smoke-test classifies the run as SKIP
            rather than FAIL. See DEC-MODULE-URLSCAN-006.
        RateLimitError
            When the API returns 429 on submit. retry_after is populated from
            the Retry-After response header when present.
        httpx.HTTPStatusError
            For unexpected 4xx/5xx responses not handled above.
        httpx.RequestError
            For network-level failures (DNS, timeout, connection refused).
        """
        api_key = self._config.get("api_key", "")
        if not api_key:
            raise AuthenticationError(
                "URLScan API key not configured. "
                "Set via 'ap config set api_keys.urlscan <key>' "
                "or AP_URLSCAN_API_KEY env var."
            )

        visibility = options.get("VISIBILITY", self.options["VISIBILITY"]["default"])
        timeout = int(options.get("TIMEOUT", self.options["TIMEOUT"]["default"]))
        poll_interval = int(options.get("POLL_INTERVAL", self.options["POLL_INTERVAL"]["default"]))

        headers = {
            "API-Key": api_key,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Submit scan
            submit_resp = await client.post(
                _SUBMIT_URL,
                json={"url": target, "visibility": visibility},
                headers=headers,
            )

            if submit_resp.status_code == 401:
                raise AuthenticationError("URLScan API key is invalid or revoked.")
            if submit_resp.status_code == 403:
                raise AuthenticationError(
                    "URLScan API key lacks permission for this scan (403 forbidden). "
                    "Check the key's plan tier, visibility allowance, or region restrictions."
                )
            if submit_resp.status_code == 429:
                retry_header = submit_resp.headers.get("Retry-After")
                retry_after = int(retry_header) if retry_header else None
                raise RateLimitError(
                    "URLScan rate limit exceeded (5,000 scans/month on free tier).",
                    retry_after=retry_after,
                )
            submit_resp.raise_for_status()

            submit_data = submit_resp.json()
            scan_uuid = submit_data.get("uuid", "")
            result_url = submit_data.get(
                "api",
                f"https://urlscan.io/api/v1/result/{scan_uuid}/",
            )

            logger.debug("URLScan submitted %s -> uuid=%s", target, scan_uuid)

            # Step 2: Poll for results
            elapsed = 0
            result_data = None

            while elapsed < timeout:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                result_resp = await client.get(result_url)
                if result_resp.status_code == 200:
                    result_data = result_resp.json()
                    logger.debug(
                        "URLScan result ready after %ds: uuid=%s",
                        elapsed,
                        scan_uuid,
                    )
                    break
                elif result_resp.status_code == 404:
                    logger.debug(
                        "URLScan result not ready (elapsed=%ds, uuid=%s) — retrying",
                        elapsed,
                        scan_uuid,
                    )
                    continue
                else:
                    result_resp.raise_for_status()

        # Step 3: Handle timeout
        if result_data is None:
            logger.warning(
                "URLScan timed out after %ds waiting for uuid=%s",
                timeout,
                scan_uuid,
            )
            return [
                {
                    "type": "url",
                    "value": target,
                    "x_scan_status": "timeout",
                    "x_scan_uuid": scan_uuid,
                }
            ]

        # Step 4: Parse results
        return _build_results(target, scan_uuid, result_data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_results(
    target: str,
    scan_uuid: str,
    result_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Construct STIX-like SCO dicts from a URLScan result response.

    Parameters
    ----------
    target:
        The original URL submitted for scanning.
    scan_uuid:
        The UUID returned by the submit endpoint.
    result_data:
        The full JSON body from GET /api/v1/result/{uuid}/.

    Returns
    -------
    list of SCO dicts:
      [0] url SCO (always present)
      [1] domain-name SCO for page domain (if non-empty)
      [2] ipv4-addr SCO for page IP (if non-empty), with x_asn
      [3+] additional ipv4-addr SCOs from lists.ips (capped at 15, deduplicated)
      [n+] additional domain-name SCOs from lists.domains (capped at 15, deduplicated)

    Deduplication is handled via a seen set; see DEC-MODULE-URLSCAN-003.
    Lists are capped at _LIST_CAP (15) entries; see DEC-MODULE-URLSCAN-004.
    """
    page = result_data.get("page", {})
    task = result_data.get("task", {})
    lists = result_data.get("lists", {})

    page_domain = page.get("domain", "")
    page_ip = page.get("ip", "")

    # Primary URL SCO — always first result
    url_sco: dict[str, Any] = {
        "type": "url",
        "value": target,
        "x_scan_uuid": scan_uuid,
        "x_effective_url": page.get("url", target),
        "x_page_title": page.get("title", ""),
        "x_page_status": page.get("status", 0),
        "x_server": page.get("server", ""),
        "x_screenshot_url": task.get("screenshotURL", ""),
    }

    results: list[dict[str, Any]] = [url_sco]

    # Deduplication seen set — pre-seed with values that appear in page object
    # so lists entries that duplicate them are skipped. See DEC-MODULE-URLSCAN-003.
    seen: set[str] = {target, page_domain, page_ip, ""}

    # domain-name SCO for the page domain
    if page_domain:
        results.append({"type": "domain-name", "value": page_domain})

    # ipv4-addr SCO for the page IP (include x_asn from page object)
    if page_ip:
        results.append(
            {
                "type": "ipv4-addr",
                "value": page_ip,
                "x_asn": page.get("asn", ""),
            }
        )

    # Additional IPs from lists.ips (capped, deduplicated)
    for entry in lists.get("ips", [])[:_LIST_CAP]:
        if entry and entry not in seen:
            seen.add(entry)
            results.append({"type": "ipv4-addr", "value": entry})

    # Additional domains from lists.domains (capped, deduplicated)
    for entry in lists.get("domains", [])[:_LIST_CAP]:
        if entry and entry not in seen:
            seen.add(entry)
            results.append({"type": "domain-name", "value": entry})

    return results
