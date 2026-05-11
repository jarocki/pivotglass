"""Censys Host information module.

Queries the Censys Search API v2 for host information including services,
ports, OS fingerprints, geolocation, autonomous system data, and TLS
certificate fingerprints.

API docs: https://search.censys.io/api

Authentication: HTTP Basic Auth (censys_id:censys_secret). Obtain a free
API key pair at https://search.censys.io/account/api (250 queries/month
on the community tier).

@decision DEC-MODULE-CENSYS-001
@title HTTP Basic Auth via httpx auth= param; credentials stored as censys_id/censys_secret
@status accepted
@rationale Censys API v2 uses HTTP Basic Auth (not an API-Key header like
           AbuseIPDB or a query-param key like Shodan). httpx natively supports
           Basic Auth via the auth=(user, password) parameter. Storing them as
           separate censys_id and censys_secret keys in _config mirrors Censys'
           own documentation naming and makes it unambiguous at call sites.
           Requiring both fields explicitly (not just one) prevents silent auth
           failures with a partial config.

@decision DEC-MODULE-CENSYS-002
@title x_services stores list-of-dicts; x_certificates on service dict (not top-level SCO)
@status accepted
@rationale Each Censys service entry has a distinct port/protocol/service_name and
           may have a TLS certificate fingerprint. Embedding certificates at the
           service level (not as a parallel top-level list) maintains the
           port-to-certificate relationship, which is the useful unit for pivoting.
           This is richer than AbuseIPDB/Shodan's flat x_domain/x_hostnames
           approach — Censys returns structured service data, so the SCO reflects
           that structure rather than collapsing it.

@decision DEC-MODULE-CENSYS-003
@title 404 returns empty list, not an exception
@status accepted
@rationale A 404 from Censys means the IP has no indexed data — a normal outcome
           for private, reserved, or recently allocated addresses. Returning [] is
           the established project convention (DEC-MODULE-SHODAN-004), signalling
           "no data" without forcing callers to catch an exception for a common
           non-error case.

@decision DEC-MODULE-CENSYS-004
@title 403 raises AuthenticationError (plan restriction treated as auth failure)
@status accepted
@rationale Censys returns 403 when the authenticated user's plan does not permit
           access to an endpoint. From the module consumer's perspective this is
           indistinguishable from an authentication failure — the module cannot
           fulfil its purpose. Raising AuthenticationError (rather than a generic
           ModuleError) causes the console to present a clear "check your
           credentials/plan" message rather than a confusing generic error.
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

_API_BASE = "https://search.censys.io/api/v2"


class CensysHost(BaseModule):
    """Query Censys for host information, services, and certificates.

    Queries GET /api/v2/hosts/{ip} authenticated via HTTP Basic Auth.
    Returns STIX 2.1 SCO dicts — at minimum an ipv4-addr SCO with x_* custom
    properties including services, OS, location, and autonomous system data.
    Certificate fingerprints are embedded per-service when present.

    Requires a Censys API ID and secret from https://search.censys.io/account/api
    (free community tier: 250 queries/month). Configure via:
      ap config set censys_id <id>
      ap config set censys_secret <secret>

    See DEC-MODULE-CENSYS-001 for auth design.
    See DEC-MODULE-CENSYS-002 for service/certificate schema.
    See DEC-MODULE-CENSYS-003 for 404 handling.
    See DEC-MODULE-CENSYS-004 for 403 handling.
    """

    name = "osint/censys_host"
    description = "Query Censys for host information, services, and certificates"
    author = "Adversary Pursuit"
    module_type = "osint"

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {
                "required": True,
                "description": "IP address to query",
                "default": "",
            },
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        """Query the Censys v2 hosts endpoint for IP intelligence.

        Parameters
        ----------
        target:
            IPv4 address to query (e.g. "8.8.8.8")
        options:
            Runtime overrides (none defined for this module beyond TARGET).

        Returns
        -------
        list[dict]
            List of STIX-like SCO dicts:
            - ipv4-addr with x_services (list of dicts with port, protocol,
              service_name, and optionally x_certificates), x_os, x_location_country,
              x_autonomous_system (dict with asn, name, bgp_prefix, country_code),
              x_last_updated
            - [] when the IP has no data in Censys index (404 response)

        Raises
        ------
        AuthenticationError
            When censys_id or censys_secret is missing/empty, or the API returns
            401 (invalid credentials) or 403 (plan restriction). See DEC-MODULE-CENSYS-004.
        RateLimitError
            When the API returns 429. retry_after is populated from the
            Retry-After response header when present.
        httpx.HTTPStatusError
            For unexpected 4xx/5xx responses not handled above.
        httpx.RequestError
            For network-level failures (DNS, timeout, connection refused).
        """
        censys_id = self._config.get("censys_id", "")
        censys_secret = self._config.get("censys_secret", "")

        if not censys_id:
            raise AuthenticationError(
                "Censys censys_id not configured. "
                "Set via 'ap config set censys_id <id>' "
                "or obtain credentials at https://search.censys.io/account/api."
            )
        if not censys_secret:
            raise AuthenticationError(
                "Censys censys_secret not configured. "
                "Set via 'ap config set censys_secret <secret>' "
                "or obtain credentials at https://search.censys.io/account/api."
            )

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                f"{_API_BASE}/hosts/{target}",
                auth=(censys_id, censys_secret),
                timeout=30.0,
            )

            if response.status_code == 401:
                raise AuthenticationError(
                    "Censys API credentials are invalid or revoked. "
                    "Verify at https://search.censys.io/account/api."
                )
            if response.status_code == 403:
                raise AuthenticationError(
                    "Censys API access forbidden. Your account plan may not "
                    "permit access to this endpoint. "
                    "Check your plan at https://search.censys.io/account/api."
                )
            if response.status_code == 429:
                retry_header = response.headers.get("Retry-After")
                retry_after = int(retry_header) if retry_header else None
                raise RateLimitError(
                    "Censys API rate limit exceeded (250 queries/month on community tier).",
                    retry_after=retry_after,
                )
            if response.status_code == 404:
                logger.debug("Censys: no data for %s (404)", target)
                return []

            response.raise_for_status()
            data = response.json().get("result", {})

        results = _build_results(target, data)
        logger.debug(
            "Censys %s: services=%s, os=%s, asn=%s",
            target,
            len(data.get("services", [])),
            (data.get("operating_system") or {}).get("product", ""),
            (data.get("autonomous_system") or {}).get("asn", ""),
        )
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_service_entry(service: dict[str, Any]) -> dict[str, Any]:
    """Build a single service dict from a Censys service object.

    Parameters
    ----------
    service:
        A single entry from the Censys result["services"] list.

    Returns
    -------
    dict
        Keys: port (int), protocol (str), service_name (str).
        Optional key: x_certificates (str) — only present when the service
        has a non-empty certificate fingerprint. See DEC-MODULE-CENSYS-002.
    """
    entry: dict[str, Any] = {
        "port": service.get("port", 0),
        "protocol": service.get("transport_protocol", ""),
        "service_name": service.get("service_name", ""),
    }
    cert = service.get("certificate")
    if cert:
        entry["x_certificates"] = cert
    return entry


def _build_results(target: str, data: dict[str, Any]) -> list[dict]:
    """Construct STIX-like SCO dicts from the Censys hosts API response.

    Parameters
    ----------
    target:
        The original IP address queried (used as fallback if API omits ip).
    data:
        The result sub-object from the Censys v2 hosts JSON response.

    Returns
    -------
    list[dict]
        One ipv4-addr SCO always present. Service entries include x_certificates
        only when the certificate fingerprint is non-empty. See DEC-MODULE-CENSYS-002.
    """
    raw_os = data.get("operating_system") or {}
    os_product = raw_os.get("product", "") if raw_os else ""

    raw_location = data.get("location") or {}
    location_country = raw_location.get("country", "") if raw_location else ""

    raw_asn = data.get("autonomous_system") or {}
    autonomous_system: dict[str, Any] = (
        {
            "asn": raw_asn.get("asn", 0),
            "name": raw_asn.get("name", ""),
            "bgp_prefix": raw_asn.get("bgp_prefix", ""),
            "country_code": raw_asn.get("country_code", ""),
        }
        if raw_asn
        else {"asn": 0, "name": "", "bgp_prefix": "", "country_code": ""}
    )

    services = [_build_service_entry(svc) for svc in data.get("services", [])]

    ip_sco: dict[str, Any] = {
        "type": "ipv4-addr",
        "value": data.get("ip", target),
        "x_services": services,
        "x_os": os_product,
        "x_location_country": location_country,
        "x_autonomous_system": autonomous_system,
        "x_last_updated": data.get("last_updated_at", ""),
    }

    return [ip_sco]
