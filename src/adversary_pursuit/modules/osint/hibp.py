"""HaveIBeenPwned email breach lookup module.

Checks email addresses against the HIBP v3 breach database and returns
a STIX email-addr SCO with custom x_breach_* properties.

API docs: https://haveibeenpwned.com/API/v3#BreachedAccount

@decision DEC-MODULE-HIBP-001
@title Single email-addr SCO with embedded breach detail lists
@status accepted
@rationale HIBP returns per-breach metadata (date, data classes) on each
           breach record. Rather than emitting a separate SCO per breach
           (which would create dozens of loosely-connected objects), all
           breach information is embedded on the primary email-addr SCO as
           x_breach_count, x_breaches (list of names), and x_breaches_detail
           (list of dicts with name, x_breach_date, x_data_classes). This
           mirrors how abuseipdb embeds totals on the ipv4-addr SCO and is
           appropriate for a per-email summary view.

@decision DEC-MODULE-HIBP-002
@title 404 = clean email, return SCO with x_breach_count=0
@status accepted
@rationale The HIBP API returns 404 when no breaches exist for an email
           address — it is not an error, it is the "no results" sentinel.
           The module normalises this into a valid email-addr SCO with
           x_breach_count=0 and x_breaches=[] so callers always receive
           a consistent return type regardless of breach status.

@decision DEC-MODULE-HIBP-003
@title user-agent header required by HIBP API
@status accepted
@rationale haveibeenpwned.com enforces a User-Agent header on all API v3
           requests; requests without one return 403. The project-wide
           user-agent string "adversary-pursuit/0.1.0" is used, matching
           the version declared in pyproject.toml. Future implementers
           should update this string when the package version bumps.

@decision DEC-MODULE-HIBP-004
@title TRUNCATE option maps to truncateResponse query parameter
@status accepted
@rationale When TRUNCATE=true, the module sends truncateResponse=true which
           tells the HIBP API to strip all breach metadata and return only
           Name fields. In truncated mode, x_breaches_detail is an empty
           list because the API returns no metadata to populate it. This
           is by design — truncated mode trades detail for bandwidth.
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

_API_BASE = "https://haveibeenpwned.com/api/v3/breachedaccount"
_USER_AGENT = "adversary-pursuit/0.1.0"


class HIBP(BaseModule):
    """Check email addresses against the HaveIBeenPwned v3 breach database.

    Queries the HIBP breachedaccount endpoint and returns a STIX email-addr
    SCO with embedded breach information including count, names, breach dates,
    and data classes exposed.

    Requires a HIBP API key from https://haveibeenpwned.com/API/Key (paid).
    Configure via:
      ap config set api_keys.hibp <key>
    or the AP_HIBP_API_KEY environment variable.

    Returns
    -------
    list[dict]
        Always a single email-addr SCO with:
        - x_breach_count (int): number of breaches; 0 for clean emails
        - x_breaches (list[str]): list of breach Name strings
        - x_breaches_detail (list[dict]): per-breach detail with keys
          name, x_breach_date, x_data_classes (empty when TRUNCATE=true)

    404 is normalised to x_breach_count=0. See DEC-MODULE-HIBP-002.
    """

    name = "osint/hibp"
    description = "Check email addresses against HaveIBeenPwned breach database"
    author = "Adversary Pursuit"
    module_type = "osint"
    accepts = ("email",)

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {
                "required": True,
                "description": "Email address to check",
                "default": "",
            },
            "TRUNCATE": {
                "required": False,
                "description": "Truncate response to just breach names",
                "default": "false",
            },
            "INCLUDE_UNVERIFIED": {
                "required": False,
                "description": "Include unverified breaches",
                "default": "true",
            },
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        """Query the HIBP breachedaccount endpoint for a given email address.

        Parameters
        ----------
        target:
            Email address to check (e.g. "user@example.com")
        options:
            Runtime overrides:
              TRUNCATE          — return only breach names ("true"/"false")
              INCLUDE_UNVERIFIED — include unverified breaches ("true"/"false")

        Returns
        -------
        list[dict]
            Single email-addr SCO with x_breach_count, x_breaches,
            x_breaches_detail. See class docstring for full schema.

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
                "HIBP API key not configured. "
                "Set via 'ap config set api_keys.hibp <key>' "
                "or AP_HIBP_API_KEY env var."
            )

        truncate = options.get("TRUNCATE", self.options["TRUNCATE"]["default"]).lower() == "true"
        include_unverified = options.get(
            "INCLUDE_UNVERIFIED", self.options["INCLUDE_UNVERIFIED"]["default"]
        ).lower()

        params: dict[str, str] = {
            "includeUnverified": include_unverified,
        }
        if truncate:
            params["truncateResponse"] = "true"

        url = f"{_API_BASE}/{target}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params=params,
                headers={
                    "hibp-api-key": api_key,
                    "user-agent": _USER_AGENT,
                },
                timeout=30.0,
            )

            if response.status_code == 404:
                # 404 = no breaches found; normalised to clean SCO
                logger.debug("HIBP %s: no breaches found (404)", target)
                return [_build_clean_sco(target)]

            if response.status_code == 401:
                raise AuthenticationError(
                    "HIBP API key is invalid or revoked. "
                    "Verify the key at https://haveibeenpwned.com/API/Key."
                )
            if response.status_code == 429:
                retry_header = response.headers.get("Retry-After")
                retry_after = int(retry_header) if retry_header else None
                raise RateLimitError(
                    "HIBP rate limit exceeded. The API enforces per-second rate limiting.",
                    retry_after=retry_after,
                )

            response.raise_for_status()
            breaches = response.json()

        sco = _build_breach_sco(target, breaches, truncated=truncate)
        logger.debug("HIBP %s: %d breach(es) found", target, sco["x_breach_count"])
        return [sco]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_clean_sco(target: str) -> dict[str, Any]:
    """Return an email-addr SCO for an address with no breaches.

    Parameters
    ----------
    target:
        The email address that was queried.

    Returns
    -------
    dict
        email-addr SCO with x_breach_count=0 and empty breach lists.
    """
    return {
        "type": "email-addr",
        "value": target,
        "x_breach_count": 0,
        "x_breaches": [],
        "x_breaches_detail": [],
    }


def _build_breach_sco(
    target: str,
    breaches: list[dict[str, Any]],
    *,
    truncated: bool = False,
) -> dict[str, Any]:
    """Construct an email-addr SCO from HIBP breach records.

    Parameters
    ----------
    target:
        The email address that was queried.
    breaches:
        List of breach objects from the HIBP API response.
    truncated:
        When True, the API returned only Name fields; x_breaches_detail
        will be an empty list. See DEC-MODULE-HIBP-004.

    Returns
    -------
    dict
        email-addr SCO with x_breach_count, x_breaches (name list),
        and x_breaches_detail (full per-breach detail unless truncated).
    """
    breach_names = [b.get("Name", "") for b in breaches]

    if truncated:
        detail: list[dict[str, Any]] = []
    else:
        detail = [
            {
                "name": b.get("Name", ""),
                "x_breach_date": b.get("BreachDate", ""),
                "x_data_classes": b.get("DataClasses", []),
            }
            for b in breaches
        ]

    return {
        "type": "email-addr",
        "value": target,
        "x_breach_count": len(breaches),
        "x_breaches": breach_names,
        "x_breaches_detail": detail,
    }
