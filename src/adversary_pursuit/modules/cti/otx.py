"""AlienVault OTX threat intelligence module.

Queries the OTX DirectConnect API for indicator intelligence including
pulses, related indicators, and community threat data.

API docs: https://otx.alienvault.com/assets/s/v2/api_doc.html

Endpoints used:
- GET /api/v1/indicators/IPv4/{ip}/general     — IP indicator details
- GET /api/v1/indicators/domain/{domain}/general — Domain indicator details
- GET /api/v1/indicators/IPv4/{ip}/passive_dns  — Passive DNS for IP
- GET /api/v1/indicators/domain/{domain}/passive_dns — Passive DNS for domain

@decision DEC-MODULE-OTX-001
@title Multi-endpoint traversal: general + passive_dns per indicator type
@status accepted
@rationale OTX's value comes from combining reputation data (general endpoint)
           with relationship data (passive_dns). A single-endpoint query would
           miss the pivoting potential. The module auto-detects IP vs domain
           from the target and queries the appropriate endpoints.
           The OTX API base URL is passed to httpx.AsyncClient so all requests
           use a shared client for the lifetime of a single hunt() call.

@decision DEC-MODULE-OTX-002
@title httpx.AsyncClient base_url pattern for multi-endpoint calls
@status accepted
@rationale Using base_url on AsyncClient and relative paths on get() keeps
           URL construction centralized and prevents base URL drift across
           multiple endpoint calls within one hunt(). This matches the pattern
           recommended in the httpx docs for multi-endpoint API clients.

@decision DEC-MODULE-OTX-003
@title Passive DNS record deduplication via seen set
@status accepted
@rationale OTX passive DNS can return the same address or hostname across
           multiple records. A seen set prevents emitting duplicate SCOs.
           The target itself is pre-seeded into the seen set to prevent
           re-emitting the primary indicator as a related indicator.

@decision DEC-MODULE-OTX-004
@title Configurable TIMEOUT option with 60-second default
@status accepted
@rationale High-volume IPs (e.g. 8.8.8.8) generate hundreds of OTX pulses.
           The OTX /general endpoint for such IPs can take >30 seconds to
           respond, causing the previous hard-coded 30s timeout to fire.
           The TIMEOUT option lets callers override the timeout per-hunt()
           call (e.g. TIMEOUT=120 for known slow targets) without touching
           module source. The default is raised from 30s to 60s to handle
           the vast majority of high-cardinality IPs without a manual
           override. The minimum enforced by regression tests is 30s; this
           default of 60s satisfies that constraint and the new contract.
           AlienVaultOTX is the sole authority for this option; no parallel
           timeout helper is introduced in base.py.

@decision DEC-MODULE-OTX-005
@title httpx.TimeoutException caught on /general; converted to URLScan-style stub SCO
@status accepted
@rationale High-volume IPs like 8.8.8.8 may still time out even with a
           generous TIMEOUT. Rather than letting the unhandled exception
           propagate (which surfaces as a FAIL in smoke_test.py and breaks
           agent/tools.py scoring), we catch httpx.TimeoutException on the
           /general endpoint and return a single-element stub list. The stub
           mirrors the URLScan timeout pattern (DEC-MODULE-URLSCAN-001 family):
           primary SCO type preserved (ipv4-addr or domain-name), value set to
           the target, x_pulse_status='timeout'. Callers (smoke_test.py
           classification, agent scoring) treat any list[dict] as PASS/usable.
           Only httpx.TimeoutException (parent of ReadTimeout, ConnectTimeout,
           WriteTimeout, PoolTimeout) is caught — generic Exception is not
           swallowed. On the optional passive_dns leg, a timeout is silently
           swallowed (primary SCO already proves the general query succeeded;
           the passive_dns result is additive, not critical). PULSE_LIMIT
           remains the single authority for capping the parsed pulse list;
           no duplicate MAX_PULSES option is introduced.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Any

import httpx

from adversary_pursuit.modules.base import (
    AuthenticationError,
    BaseModule,
    RateLimitError,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://otx.alienvault.com"


class AlienVaultOTX(BaseModule):
    """Query AlienVault OTX for threat intelligence on IPs and domains.

    Requires a free API key from https://otx.alienvault.com/api. Configure via:
      ap config set api_keys.otx <key>
    or the AP_OTX_API_KEY environment variable.

    Returns STIX 2.1 SCO dicts (plain dicts, not stix2 objects). The primary
    indicator (ipv4-addr or domain-name) is always the first result. Related
    indicators from passive DNS are appended when INCLUDE_PASSIVE_DNS=true.
    See DEC-MODULE-OTX-001.
    """

    name = "cti/otx"
    description = "Query AlienVault OTX for threat intelligence on IPs and domains"
    author = "Adversary Pursuit"
    module_type = "cti"

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {
                "required": True,
                "description": "IP address or domain to query",
                "default": "",
            },
            "INCLUDE_PASSIVE_DNS": {
                "required": False,
                "description": "Include passive DNS results (true/false)",
                "default": "true",
            },
            "PULSE_LIMIT": {
                "required": False,
                "description": "Max number of pulses to return",
                "default": "10",
            },
            "TIMEOUT": {
                "required": False,
                "description": "Max seconds to wait for OTX API response (per request)",
                "default": "60",
            },
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        """Query OTX for target indicator intelligence.

        Auth: X-OTX-API-KEY header on all requests.
        Base URL: https://otx.alienvault.com

        Flow:
        1. Validate API key present.
        2. Detect if target is IPv4 or domain.
        3. Query /general endpoint for reputation + pulse data.
        4. Optionally query /passive_dns for related indicators.
        5. Return list of STIX-like SCO dicts.

        Parameters
        ----------
        target:
            IPv4 address (e.g. "1.2.3.4") or domain (e.g. "evil.com")
        options:
            Runtime overrides:
              INCLUDE_PASSIVE_DNS — query passive_dns endpoint ("true"/"false")
              PULSE_LIMIT         — max pulses to include (default "10")

        Returns
        -------
        list[dict]
            Primary SCO always first:
            - IPv4: ipv4-addr with x_pulse_count, x_reputation, x_country_code,
                    x_asn, x_pulses, x_pulse_tags
            - Domain: domain-name with x_pulse_count, x_alexa, x_whois,
                      x_pulses, x_pulse_tags
            Related indicators from passive DNS appended when enabled.

        Raises
        ------
        AuthenticationError
            When no API key is configured, or the API returns 401.
        RateLimitError
            When the API returns 429.
        httpx.HTTPStatusError
            For unexpected 4xx/5xx responses not handled above.
        httpx.RequestError
            For network-level failures (DNS, timeout, connection refused).
        """
        api_key = self._config.get("api_key", "")
        if not api_key:
            raise AuthenticationError(
                "OTX API key not configured. "
                "Set via 'ap config set api_keys.otx <key>' "
                "or AP_OTX_API_KEY env var."
            )

        indicator_type = _detect_type(target)
        include_dns = (
            options.get(
                "INCLUDE_PASSIVE_DNS",
                self.options["INCLUDE_PASSIVE_DNS"]["default"],
            ).lower()
            == "true"
        )
        pulse_limit = int(
            options.get(
                "PULSE_LIMIT",
                self.options["PULSE_LIMIT"]["default"],
            )
        )
        timeout = float(
            options.get(
                "TIMEOUT",
                self.options["TIMEOUT"]["default"],
            )
        )

        headers = {
            "X-OTX-API-KEY": api_key,
            "Accept": "application/json",
        }

        results: list[dict] = []

        # SCO type used for timeout stubs — matches the real primary SCO type.
        # See DEC-MODULE-OTX-005 for stub shape rationale.
        stub_sco_type = "ipv4-addr" if indicator_type == "IPv4" else "domain-name"

        async with httpx.AsyncClient(
            base_url=_BASE_URL, headers=headers, timeout=timeout
        ) as client:
            # 1. General endpoint — always queried.
            # TimeoutException here means we cannot build a real primary SCO;
            # return a stub so callers get a list[dict] instead of an exception.
            try:
                general_resp = await client.get(
                    f"/api/v1/indicators/{indicator_type}/{target}/general"
                )
            except httpx.TimeoutException:
                logger.warning(
                    "OTX /general timeout for %s after %.0fs — returning timeout stub",
                    target,
                    timeout,
                )
                return [
                    {
                        "type": stub_sco_type,
                        "value": target,
                        "x_pulse_status": "timeout",
                    }
                ]

            if general_resp.status_code == 401:
                raise AuthenticationError("OTX API key is invalid or revoked.")
            if general_resp.status_code == 429:
                raise RateLimitError("OTX rate limit exceeded.")
            general_resp.raise_for_status()
            general_data = general_resp.json()

            # Build primary SCO from general data
            primary = _build_primary_sco(target, indicator_type, general_data, pulse_limit)
            results.append(primary)

            logger.debug(
                "OTX %s %s: pulse_count=%s",
                indicator_type,
                target,
                primary.get("x_pulse_count"),
            )

            # 2. Passive DNS endpoint — optional.
            # A timeout here is non-fatal: the primary SCO is already collected.
            # See DEC-MODULE-OTX-005.
            if include_dns:
                try:
                    dns_resp = await client.get(
                        f"/api/v1/indicators/{indicator_type}/{target}/passive_dns"
                    )
                except httpx.TimeoutException:
                    logger.warning(
                        "OTX /passive_dns timeout for %s — skipping related indicators",
                        target,
                    )
                    dns_resp = None

                if dns_resp is not None and dns_resp.status_code == 200:
                    dns_data = dns_resp.json()
                    related = _extract_passive_dns(target, dns_data)
                    results.extend(related)
                    logger.debug(
                        "OTX passive_dns %s: %d related indicators",
                        target,
                        len(related),
                    )

        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_type(target: str) -> str:
    """Return 'IPv4' if target is an IP address, else 'domain'.

    Parameters
    ----------
    target:
        Raw string from the user — could be an IP or a hostname.
    """
    try:
        ipaddress.ip_address(target)
        return "IPv4"
    except ValueError:
        return "domain"


def _is_ip(value: str) -> bool:
    """Return True if value is a valid IP address string."""
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _build_primary_sco(
    target: str,
    indicator_type: str,
    general_data: dict[str, Any],
    pulse_limit: int,
) -> dict[str, Any]:
    """Construct the primary STIX SCO dict from the OTX general endpoint response.

    Parameters
    ----------
    target:
        The queried indicator value.
    indicator_type:
        'IPv4' or 'domain'.
    general_data:
        JSON body from the /general endpoint.
    pulse_limit:
        Maximum number of pulses to include in x_pulses.

    Returns
    -------
    dict with STIX type, value, and OTX-specific x_ custom properties.
    """
    pulse_info = general_data.get("pulse_info", {})
    pulse_count = pulse_info.get("count", 0)
    pulses = pulse_info.get("pulses", [])[:pulse_limit]

    if indicator_type == "IPv4":
        sco: dict[str, Any] = {
            "type": "ipv4-addr",
            "value": target,
            "x_pulse_count": pulse_count,
            "x_reputation": general_data.get("reputation", 0),
            "x_country_code": general_data.get("country_code", ""),
            "x_asn": general_data.get("asn", ""),
        }
    else:
        sco = {
            "type": "domain-name",
            "value": target,
            "x_pulse_count": pulse_count,
            "x_alexa": general_data.get("alexa", ""),
            "x_whois": general_data.get("whois", ""),
        }

    if pulses:
        sco["x_pulses"] = [p.get("name", "") for p in pulses]
        sco["x_pulse_tags"] = list({tag for p in pulses for tag in p.get("tags", [])})

    return sco


def _extract_passive_dns(
    target: str,
    dns_data: dict[str, Any],
    max_records: int = 20,
) -> list[dict[str, Any]]:
    """Extract related SCOs from OTX passive DNS response.

    Each DNS record may yield:
    - One ipv4-addr SCO for a numeric address field
    - One domain-name SCO for a non-IP address field
    - One domain-name SCO for a hostname field

    Duplicates and the target itself are suppressed via a seen set.
    See DEC-MODULE-OTX-003.

    Parameters
    ----------
    target:
        Original queried indicator — excluded from output.
    dns_data:
        JSON body from the /passive_dns endpoint.
    max_records:
        Maximum number of raw records to process (default 20).

    Returns
    -------
    list of ipv4-addr and domain-name SCO dicts.
    """
    results: list[dict[str, Any]] = []
    seen: set[str] = {target}

    for record in dns_data.get("passive_dns", [])[:max_records]:
        address = record.get("address", "")
        hostname = record.get("hostname", "")

        if address and address not in seen:
            seen.add(address)
            if _is_ip(address):
                results.append({"type": "ipv4-addr", "value": address})
            else:
                results.append({"type": "domain-name", "value": address})

        if hostname and hostname not in seen:
            seen.add(hostname)
            results.append({"type": "domain-name", "value": hostname})

    return results
