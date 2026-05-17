"""GreyNoise IP reputation module.

Queries the GreyNoise Community API for IP address classification including
noise status, RIOT (benign services) status, and threat classification.

API docs: https://docs.greynoise.io/reference/get_v3-community-ip

@decision DEC-MODULE-GREYNOISE-001
@title Community API (v3) with lowercase 'key' auth header
@status accepted
@rationale GreyNoise offers both Community (free) and Enterprise APIs. This
           module targets the Community API at https://api.greynoise.io/v3/community/{ip}
           because it is freely available without a paid subscription, making it
           accessible to all AP users out of the box. The auth header is the
           literal lowercase 'key' per the GreyNoise Community API documentation
           (https://docs.greynoise.io/reference/get_v3-community-ip) — NOT
           'Authorization', 'X-Key', or 'API-Key'. Using any other header name
           causes silent 401 failures. httpx.AsyncClient with timeout=30.0 is the
           project-standard HTTP client (abuseipdb.py shape, pyproject.toml dep).

@decision DEC-MODULE-GREYNOISE-002
@title 404 -> unknown stub, 401 -> AuthenticationError, 429 -> RateLimitError
@status accepted
@rationale Three explicit status code branches before raise_for_status():
           - 404: The Community API returns 404 when it has no record for the IP
             (i.e. the IP has not been observed in internet scan traffic). This is
             NOT an error — it is a valid response meaning 'unknown'. We return a
             single ipv4-addr SCO with x_greynoise_classification='unknown' rather
             than raising so callers receive a uniform list[dict] return type.
           - 401: Invalid or revoked API key. Always AuthenticationError (not a
             module bug) — surfaced as SKIP in the smoke test per DEC-SMOKE-005.
           - 429: Rate limit exceeded. RateLimitError with retry_after populated
             from the Retry-After header when present.
           - Any other 4xx/5xx reaches raise_for_status() and propagates as
             httpx.HTTPStatusError to the caller (the only path for unexpected errors).

@decision DEC-MODULE-GREYNOISE-003
@title Single ipv4-addr SCO with x_greynoise_* custom fields
@status accepted
@rationale The GreyNoise Community API returns one record per IP. We model this as
           a single ipv4-addr STIX 2.1 SCO dict (plain dict, not a stix2 library
           object — per DEC-STIX-001/002) with x_greynoise_* custom fields for
           every response attribute. The six custom fields map directly to the
           Community API response shape: classification, noise, riot, name,
           last_seen, and link. No additional SCOs are emitted (unlike AbuseIPDB
           which emits a domain-name SCO when a domain is returned) because the
           Community API response contains no secondary object suitable for a
           separate SCO.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from adversary_pursuit.modules.base import (
    AuthenticationError,
    BaseModule,
    RateLimitError,
)

logger = logging.getLogger(__name__)


class GreyNoise(BaseModule):
    """Check IP address classification via the GreyNoise Community API.

    Identifies whether an IP is a known internet scanner (noise), a known
    benign service (RIOT — Rules of Internet), or unknown. Returns the
    GreyNoise classification (benign/malicious/unknown) and enrichment fields.

    Requires an API key from https://viz.greynoise.io/account/api-key
    (Community tier: free, limited to 50 queries/day). Configure via:
      ap config set api_keys.greynoise <key>
    or the AP_GREYNOISE_API_KEY environment variable.

    Returns a single STIX 2.1 ipv4-addr SCO dict with x_greynoise_*
    custom properties. See DEC-MODULE-GREYNOISE-003.
    """

    name = "osint/greynoise"
    description = "Check IP classification via GreyNoise Community API"
    author = "Adversary Pursuit"
    module_type = "osint"

    _API_URL = "https://api.greynoise.io/v3/community/{ip}"

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {
                "required": True,
                "description": "IP address to classify",
                "default": "",
            },
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        """Query the GreyNoise Community API for IP classification.

        Parameters
        ----------
        target:
            IPv4 address to classify (e.g. "8.8.8.8")
        options:
            Runtime overrides (no module-specific options for the Community API)

        Returns
        -------
        list[dict]
            Single-element list containing one ipv4-addr STIX 2.1 SCO dict
            with the following x_greynoise_* custom fields:
              x_greynoise_classification: "benign", "malicious", or "unknown"
              x_greynoise_noise: True if the IP is a known internet scanner
              x_greynoise_riot: True if the IP belongs to a known benign service
              x_greynoise_name: service/scanner name when available, else ""
              x_greynoise_last_seen: ISO 8601 date string when last observed, else ""
              x_greynoise_link: link to the GreyNoise viz page for the IP

        Raises
        ------
        AuthenticationError
            When no API key is configured, or the API returns 401.
        RateLimitError
            When the API returns 429. retry_after is populated from the
            Retry-After response header when present.
        httpx.HTTPStatusError
            For unexpected 4xx/5xx responses not handled above.
        httpx.RequestError
            For network-level failures (DNS, timeout, connection refused).
        """
        api_key = self._config.get("api_key", "")
        if not api_key:
            raise AuthenticationError(
                "GreyNoise API key not configured. "
                "Set via 'ap config set api_keys.greynoise <key>' "
                "or AP_GREYNOISE_API_KEY env var."
            )

        url = self._API_URL.format(ip=target)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers={
                    "key": api_key,  # lowercase 'key' per GreyNoise Community API docs
                    "Accept": "application/json",
                },
                timeout=30.0,
            )

            if response.status_code == 401:
                raise AuthenticationError("GreyNoise API key invalid/revoked.")
            if response.status_code == 404:
                # IP not in GreyNoise database — valid "unknown" result, not an error.
                # Return a stub SCO with classification=unknown per DEC-MODULE-GREYNOISE-002.
                return [_build_unknown_stub(target)]
            if response.status_code == 429:
                retry_header = response.headers.get("Retry-After")
                retry_after = int(retry_header) if retry_header else None
                raise RateLimitError(
                    "GreyNoise Community API rate limit exceeded.",
                    retry_after=retry_after,
                )

            response.raise_for_status()
            data = response.json()

        result = _build_sco(target, data)
        logger.debug(
            "GreyNoise %s: classification=%s, noise=%s, riot=%s, name=%s",
            target,
            data.get("classification"),
            data.get("noise"),
            data.get("riot"),
            data.get("name"),
        )
        return [result]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_sco(target: str, data: dict[str, Any]) -> dict[str, Any]:
    """Construct a STIX 2.1 ipv4-addr SCO dict from a GreyNoise 200 response.

    Parameters
    ----------
    target:
        The original IP address queried (used as fallback if API omits it).
    data:
        The top-level JSON response dict from the GreyNoise Community API.

    Returns
    -------
    dict
        Single ipv4-addr SCO with x_greynoise_* custom fields per
        DEC-MODULE-GREYNOISE-003.
    """
    return {
        "type": "ipv4-addr",
        "value": data.get("ip", target),
        "x_greynoise_classification": data.get("classification", "unknown"),
        "x_greynoise_noise": bool(data.get("noise", False)),
        "x_greynoise_riot": bool(data.get("riot", False)),
        "x_greynoise_name": data.get("name", ""),
        "x_greynoise_last_seen": data.get("last_seen", ""),
        "x_greynoise_link": data.get("link", ""),
    }


def _build_unknown_stub(target: str) -> dict[str, Any]:
    """Construct the 'unknown' stub SCO returned when GreyNoise has no record.

    Called only on HTTP 404 responses. Returns an ipv4-addr SCO with
    x_greynoise_classification='unknown' and zeroed boolean fields so
    downstream consumers receive a consistent shape per DEC-MODULE-GREYNOISE-002.

    Parameters
    ----------
    target:
        The IP address that was not found in the GreyNoise database.

    Returns
    -------
    dict
        ipv4-addr SCO with x_greynoise_classification='unknown'.
    """
    return {
        "type": "ipv4-addr",
        "value": target,
        "x_greynoise_classification": "unknown",
        "x_greynoise_noise": False,
        "x_greynoise_riot": False,
        "x_greynoise_name": "",
        "x_greynoise_last_seen": "",
        "x_greynoise_link": "",
    }
