"""AbuseIPDB IP reputation module.

Queries the AbuseIPDB v2 API for IP address reputation data including
abuse confidence score, ISP, usage type, and recent report history.

API docs: https://docs.abuseipdb.com/#check-endpoint

@decision DEC-MODULE-ABUSEIPDB-001
@title httpx.AsyncClient for HTTP; x_ custom properties on ipv4-addr SCO
@status accepted
@rationale httpx is the project's standard async HTTP library (declared in
           pyproject.toml, ADR-009). The AbuseIPDB response contains fields
           beyond core STIX SCO schema (abuseConfidenceScore, isp, usageType,
           totalReports) which are stored as x_-prefixed custom properties on
           the ipv4-addr SCO, matching the pattern established by whois_lookup
           (DEC-MODULE-WHOIS-002). dict_to_stix() in models/stix.py handles
           allow_custom=True downstream.

@decision DEC-MODULE-ABUSEIPDB-002
@title Domain-name SCO emitted as separate object when API returns a domain
@status accepted
@rationale AbuseIPDB returns the reverse-DNS domain associated with the IP.
           Rather than embedding it only as x_domain on the ipv4-addr SCO,
           we also emit a standalone domain-name SCO so downstream consumers
           (graph builders, STIX bundles) can establish relationships between
           the IP and domain without parsing custom fields. The x_domain field
           is retained on the ipv4-addr SCO for consumers that prefer flat
           access.
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


class AbuseIPDB(BaseModule):
    """Check IP address reputation via the AbuseIPDB v2 API.

    Requires an API key from https://www.abuseipdb.com/register (free tier:
    1,000 queries/day). Configure via:
      ap config set api_keys.abuseipdb <key>
    or the AP_ABUSEIPDB_API_KEY environment variable.

    Returns STIX 2.1 SCO dicts (plain dicts, not stix2 objects). At minimum
    returns an ipv4-addr SCO with x_* custom properties. If the API returns
    a domain, an additional domain-name SCO is appended. See DEC-MODULE-ABUSEIPDB-002.
    """

    name = "osint/abuseipdb"
    description = "Check IP reputation via AbuseIPDB"
    author = "Adversary Pursuit"
    module_type = "osint"

    _API_URL = "https://api.abuseipdb.com/api/v2/check"

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {
                "required": True,
                "description": "IP address to check",
                "default": "",
            },
            "MAX_AGE": {
                "required": False,
                "description": "Max age of reports in days (1-365)",
                "default": "90",
            },
            "VERBOSE": {
                "required": False,
                "description": "Include recent report details (true/false)",
                "default": "false",
            },
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        """Query the AbuseIPDB check endpoint for IP reputation.

        Parameters
        ----------
        target:
            IPv4 or IPv6 address to check (e.g. "1.2.3.4")
        options:
            Runtime overrides:
              MAX_AGE — maximum report age in days (default "90")
              VERBOSE  — include per-report details ("true"/"false")

        Returns
        -------
        list[dict]
            List of STIX-like SCO dicts:
            - ipv4-addr with x_abuse_confidence_score, x_isp, x_usage_type,
              x_domain, x_country_code, x_total_reports, x_is_whitelisted,
              x_last_reported_at
            - domain-name (only when API returns a non-empty domain)

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
                "AbuseIPDB API key not configured. "
                "Set via 'ap config set api_keys.abuseipdb <key>' "
                "or AP_ABUSEIPDB_API_KEY env var."
            )

        max_age = int(options.get("MAX_AGE", self.options["MAX_AGE"]["default"]))
        verbose = options.get("VERBOSE", self.options["VERBOSE"]["default"]).lower() == "true"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                self._API_URL,
                params={
                    "ipAddress": target,
                    "maxAgeInDays": max_age,
                    "verbose": "yes" if verbose else "no",
                },
                headers={
                    "Key": api_key,
                    "Accept": "application/json",
                },
                timeout=30.0,
            )

            if response.status_code == 401:
                raise AuthenticationError(
                    "AbuseIPDB API key is invalid or revoked. "
                    "Verify the key at https://www.abuseipdb.com/account/api."
                )
            if response.status_code == 429:
                retry_header = response.headers.get("Retry-After")
                retry_after = int(retry_header) if retry_header else None
                raise RateLimitError(
                    "AbuseIPDB daily rate limit exceeded (1,000 queries/day on free tier).",
                    retry_after=retry_after,
                )

            response.raise_for_status()
            data = response.json().get("data", {})

        results = _build_results(target, data)
        logger.debug(
            "AbuseIPDB %s: score=%s, reports=%s, isp=%s",
            target,
            data.get("abuseConfidenceScore"),
            data.get("totalReports"),
            data.get("isp"),
        )
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_results(target: str, data: dict[str, Any]) -> list[dict]:
    """Construct STIX-like SCO dicts from the AbuseIPDB API response data.

    Parameters
    ----------
    target:
        The original IP address queried (used as fallback if API omits it).
    data:
        The ``data`` sub-object from the AbuseIPDB JSON response.

    Returns
    -------
    list[dict]
        One ipv4-addr SCO always present. One domain-name SCO appended when
        the API returns a non-empty domain string.
    """
    ip_sco: dict[str, Any] = {
        "type": "ipv4-addr",
        "value": data.get("ipAddress", target),
        "x_abuse_confidence_score": data.get("abuseConfidenceScore", 0),
        "x_isp": data.get("isp", ""),
        "x_usage_type": data.get("usageType", ""),
        "x_domain": data.get("domain", ""),
        "x_country_code": data.get("countryCode", ""),
        "x_total_reports": data.get("totalReports", 0),
        "x_is_whitelisted": data.get("isWhitelisted", False),
        "x_last_reported_at": data.get("lastReportedAt", ""),
    }

    results: list[dict] = [ip_sco]

    domain = data.get("domain", "")
    if domain:
        results.append({"type": "domain-name", "value": domain})

    return results
