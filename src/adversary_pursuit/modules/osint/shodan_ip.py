"""Shodan IP host information module.

Queries the Shodan host endpoint for IP address intelligence including
open ports, hostnames, OS fingerprints, organization data, and vulnerability
cross-references (CVE IDs).

API docs: https://developer.shodan.io/api

@decision DEC-MODULE-SHODAN-001
@title httpx.AsyncClient with key param; x_ custom properties on ipv4-addr SCO
@status accepted
@rationale httpx is the project's standard async HTTP library (declared in
           pyproject.toml, ADR-009). Shodan authenticates via a 'key' query
           parameter, not a header. The host response contains fields beyond core
           STIX SCO schema (ports, hostnames, org, isp, vulns) which are stored
           as x_-prefixed custom properties on the ipv4-addr SCO, matching the
           pattern established by abuseipdb (DEC-MODULE-ABUSEIPDB-001) and
           whois_lookup (DEC-MODULE-WHOIS-002).

@decision DEC-MODULE-SHODAN-002
@title domain-name SCOs emitted for each Shodan hostname
@status accepted
@rationale Shodan returns a hostnames list for the IP. Rather than storing them
           only in x_hostnames on the ipv4-addr SCO, we also emit a standalone
           domain-name SCO per hostname so downstream consumers (graph builders,
           STIX bundles) can establish relationships without parsing custom fields.
           This matches DEC-MODULE-ABUSEIPDB-002 for consistency across modules.

@decision DEC-MODULE-SHODAN-003
@title vulns field normalisation: handle both dict and list formats
@status accepted
@rationale Shodan's API docs show vulns as a dict (keys are CVE IDs, values are
           dicts with cvss/summary). However, the API also returns vulns as a
           plain list of CVE ID strings in some responses. Both formats must be
           handled: list(vulns.keys()) for dicts, list(vulns) for lists.
           This is documented in the issue spec and verified by two separate
           test fixtures (DEC-TEST-SHODAN-002).

@decision DEC-MODULE-SHODAN-004
@title 404 returns empty list, not an exception
@status accepted
@rationale A 404 from Shodan means the IP has no data indexed — a normal outcome
           for private IPs, newly allocated addresses, or non-routable space.
           Raising an exception would force callers to catch it for a common,
           non-error condition. Returning [] signals "no data" clearly and matches
           the convention of other modules that may return empty results on valid
           queries with no hits. Callers distinguish between [] (no data) and an
           exception (API failure) as appropriate.
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

_API_BASE = "https://api.shodan.io"


class ShodanIP(BaseModule):
    """Query Shodan for IP host information, open ports, and vulnerabilities.

    Requires a Shodan API key from https://account.shodan.io (free tier available).
    Configure via:
      ap config set api_keys.shodan <key>
    or the AP_SHODAN_API_KEY environment variable.

    Returns STIX 2.1 SCO dicts (plain dicts, not stix2 objects). At minimum
    returns an ipv4-addr SCO with x_* custom properties. A domain-name SCO is
    appended for each hostname Shodan associates with the IP.
    See DEC-MODULE-SHODAN-002.
    """

    name = "osint/shodan_ip"
    description = "Query Shodan for IP host information, open ports, and vulnerabilities"
    author = "Adversary Pursuit"
    module_type = "osint"
    accepts = ("ipv4", "ipv6")

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {
                "required": True,
                "description": "IP address to query",
                "default": "",
            },
            "MINIFY": {
                "required": False,
                "description": "Return only basic host info",
                "default": "false",
            },
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        """Query the Shodan host endpoint for IP intelligence.

        Parameters
        ----------
        target:
            IPv4 address to query (e.g. "1.2.3.4")
        options:
            Runtime overrides:
              MINIFY — return only basic host info ("true"/"false")

        Returns
        -------
        list[dict]
            List of STIX-like SCO dicts:
            - ipv4-addr with x_ports, x_hostnames, x_os, x_org, x_isp,
              x_country_code, x_vulns (list of CVE IDs), x_last_update
            - domain-name SCO for each hostname in the Shodan response
            - [] when the IP has no data in Shodan (404 response)

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
                "Shodan API key not configured. "
                "Set via 'ap config set api_keys.shodan <key>' "
                "or AP_SHODAN_API_KEY env var."
            )

        minify = options.get("MINIFY", self.options["MINIFY"]["default"]).lower() == "true"

        params: dict[str, Any] = {"key": api_key}
        if minify:
            params["minify"] = True

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_API_BASE}/shodan/host/{target}",
                params=params,
                timeout=30.0,
            )

            if response.status_code == 401:
                raise AuthenticationError(
                    "Shodan API key is invalid or revoked. "
                    "Verify the key at https://account.shodan.io."
                )
            if response.status_code == 429:
                retry_header = response.headers.get("Retry-After")
                retry_after = int(retry_header) if retry_header else None
                raise RateLimitError(
                    "Shodan API rate limit exceeded.",
                    retry_after=retry_after,
                )
            if response.status_code == 404:
                logger.debug("Shodan: no data for %s (404)", target)
                return []

            response.raise_for_status()
            data = response.json()

        results = _build_results(target, data)
        logger.debug(
            "Shodan %s: ports=%s, hostnames=%s, vulns=%s",
            target,
            data.get("ports"),
            data.get("hostnames"),
            len(results[0].get("x_vulns", [])) if results else 0,
        )
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalise_vulns(vulns: Any) -> list[str]:
    """Extract CVE IDs from Shodan's vulns field regardless of format.

    Shodan may return vulns as:
    - dict: keys are CVE IDs, values are detail dicts
    - list: CVE ID strings directly

    See DEC-MODULE-SHODAN-003.

    Parameters
    ----------
    vulns:
        The raw vulns value from the Shodan API response, or None/missing.

    Returns
    -------
    list[str]
        List of CVE ID strings, empty if vulns is absent or empty.
    """
    if not vulns:
        return []
    if isinstance(vulns, dict):
        return list(vulns.keys())
    return list(vulns)


def _build_results(target: str, data: dict[str, Any]) -> list[dict]:
    """Construct STIX-like SCO dicts from the Shodan host API response.

    Parameters
    ----------
    target:
        The original IP address queried (used as fallback if API omits ip_str).
    data:
        The JSON body from the Shodan host endpoint.

    Returns
    -------
    list[dict]
        One ipv4-addr SCO always present. One domain-name SCO appended per
        hostname in data["hostnames"]. See DEC-MODULE-SHODAN-002.
    """
    ip_sco: dict[str, Any] = {
        "type": "ipv4-addr",
        "value": data.get("ip_str", target),
        "x_ports": data.get("ports", []),
        "x_hostnames": data.get("hostnames", []),
        "x_os": data.get("os") or "",
        "x_org": data.get("org", ""),
        "x_isp": data.get("isp", ""),
        "x_country_code": data.get("country_code", ""),
        "x_vulns": _normalise_vulns(data.get("vulns")),
        "x_last_update": data.get("last_update", ""),
    }

    results: list[dict] = [ip_sco]

    for hostname in data.get("hostnames", []):
        if hostname:
            results.append({"type": "domain-name", "value": hostname})

    return results
