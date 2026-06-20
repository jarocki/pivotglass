"""Censys Host information module.

Queries the Censys Platform API v3 for host information including services,
ports, OS fingerprints, geolocation, autonomous system data, and TLS
certificate fingerprints.

API docs: https://docs.censys.com/reference/get-started

Authentication: Bearer Personal Access Token (PAT). Obtain from
https://app.censys.io/user/tokens (free tier available).

Configure via:
  ap config set censys_pat <token>   (recommended — new Platform API)

Legacy credentials (censys_id + censys_secret) were used with the deprecated
search.censys.io v2 API which now returns 302 redirects and cannot be used.
See DEC-MODULE-CENSYS-005 for the migration rationale.

@decision DEC-MODULE-CENSYS-001
@title HTTP Basic Auth via httpx auth= param; credentials stored as censys_id/censys_secret
@status superseded by DEC-MODULE-CENSYS-005
@rationale Censys API v2 used HTTP Basic Auth with censys_id:censys_secret. That API
           has been retired (returns 302 with no Location header as of 2026-05).
           See DEC-MODULE-CENSYS-005 for the current auth approach.

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

@decision DEC-MODULE-CENSYS-005
@title Migrate from search.censys.io v2 (Basic Auth) to api.platform.censys.io v3 (Bearer PAT)
@status accepted
@rationale The Censys search.censys.io/api/v2 endpoint returns HTTP 302 with no
           Location header as of 2026-05, making it effectively unusable. The
           canonical Censys Platform API is now https://api.platform.censys.io
           with path /v3/global/asset/host/{ip} and Bearer token authentication
           using a Personal Access Token (PAT). The v3 response wraps data under
           result.resource instead of result directly, and uses "protocol" for
           service name and "transport_protocol" for TCP/UDP.
           config key: censys_pat (string, Bearer token value)
           env var fallbacks: AP_CENSYS_PAT, CENSYS_PAT
           The old censys_id/censys_secret fields remain accepted in _config but
           trigger an AuthenticationError with a migration message, ensuring users
           receive a clear path forward rather than a confusing 302 error.

@decision DEC-MODULE-CENSYS-006
@title Read censys_pat from _config dict or env vars without touching core/config.py
@status accepted
@rationale core/config.py (ApiKeysConfig) is outside this work item's scope. The
           module reads censys_pat from self._config (a plain dict populated by the
           caller), falling back to AP_CENSYS_PAT and CENSYS_PAT env vars directly
           via os.environ. This is the same pattern used throughout the codebase for
           service-specific credential handling. Users can set the key via:
             ap config set censys_pat <token>   (once ApiKeysConfig is updated)
             export AP_CENSYS_PAT=<token>        (works today without config change)
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from adversary_pursuit.modules.base import (
    AuthenticationError,
    BaseModule,
    RateLimitError,
)

logger = logging.getLogger(__name__)

# New Censys Platform API (as of 2026-05). See DEC-MODULE-CENSYS-005.
_API_BASE = "https://api.platform.censys.io"
_HOST_PATH = "/v3/global/asset/host/{ip}"

# Legacy endpoint that now returns 302 with no Location header.
# Preserved here for documentation only — not called.
_LEGACY_API_BASE = "https://search.censys.io/api/v2"  # noqa: F841


class CensysHost(BaseModule):
    """Query Censys for host information, services, and certificates.

    Queries GET /v3/global/asset/host/{ip} authenticated via Bearer PAT.
    Returns STIX 2.1 SCO dicts — at minimum an ipv4-addr SCO with x_* custom
    properties including services, OS, location, and autonomous system data.
    Certificate SHA-256 fingerprints are embedded per-service when present.

    Requires a Censys Personal Access Token from https://app.censys.io/user/tokens
    (free tier available). Configure via:
      ap config set censys_pat <token>
    or:
      export AP_CENSYS_PAT=<token>

    See DEC-MODULE-CENSYS-005 for migration from the deprecated v2 Basic Auth API.
    See DEC-MODULE-CENSYS-002 for service/certificate schema.
    See DEC-MODULE-CENSYS-003 for 404 handling.
    See DEC-MODULE-CENSYS-004 for 403 handling.
    """

    name = "osint/censys_host"
    description = "Query Censys for host information, services, and certificates"
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
        }

    def _resolve_pat(self) -> str:
        """Resolve the Censys Personal Access Token from config or env vars.

        Resolution order (DEC-MODULE-CENSYS-006):
          1. self._config["censys_pat"] — set by initialize() from config.toml
          2. AP_CENSYS_PAT env var — project-namespaced per-session override
          3. CENSYS_PAT env var — direct vendor env var

        Returns
        -------
        str
            The PAT value, or empty string if not configured.
        """
        pat = self._config.get("censys_pat", "")
        if not pat:
            pat = os.environ.get("AP_CENSYS_PAT", "")
        if not pat:
            pat = os.environ.get("CENSYS_PAT", "")
        return pat

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        """Query the Censys v3 Platform hosts endpoint for IP intelligence.

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
            When censys_pat is missing/empty (or only legacy censys_id/censys_secret
            are configured), or the API returns 401/403. See DEC-MODULE-CENSYS-004,
            DEC-MODULE-CENSYS-005.
        RateLimitError
            When the API returns 429. retry_after is populated from the
            Retry-After response header when present.
        httpx.HTTPStatusError
            For unexpected 4xx/5xx responses not handled above.
        httpx.RequestError
            For network-level failures (DNS, timeout, connection refused).
        """
        pat = self._resolve_pat()

        if not pat:
            # Check if the user has legacy credentials to give a targeted migration message.
            has_legacy = bool(
                self._config.get("censys_id", "") and self._config.get("censys_secret", "")
            )
            if has_legacy:
                raise AuthenticationError(
                    "Censys API has migrated. Your censys_id and censys_secret credentials "
                    "are no longer accepted — the search.censys.io v2 API now returns 302 "
                    "redirects and is effectively retired. "
                    "Obtain a Personal Access Token (PAT) from "
                    "https://app.censys.io/user/tokens and configure it via: "
                    "'ap config set censys_pat <token>' or export AP_CENSYS_PAT=<token>. "
                    "See DEC-MODULE-CENSYS-005 for details."
                )
            raise AuthenticationError(
                "Censys censys_pat not configured. "
                "Obtain a Personal Access Token from https://app.censys.io/user/tokens "
                "and set via 'ap config set censys_pat <token>' "
                "or export AP_CENSYS_PAT=<token>."
            )

        url = f"{_API_BASE}{_HOST_PATH.format(ip=target)}"

        async with httpx.AsyncClient(
            follow_redirects=True,
            headers={"Authorization": f"Bearer {pat}"},
        ) as client:
            response = await client.get(url, timeout=30.0)

            if response.status_code == 401:
                raise AuthenticationError(
                    "Censys API credentials are invalid or revoked. "
                    "Verify your Personal Access Token at https://app.censys.io/user/tokens."
                )
            if response.status_code == 403:
                raise AuthenticationError(
                    "Censys API access forbidden. Your account plan may not "
                    "permit access to this endpoint. "
                    "Check your plan at https://app.censys.io."
                )
            if response.status_code == 429:
                retry_header = response.headers.get("Retry-After")
                retry_after = int(retry_header) if retry_header else None
                raise RateLimitError(
                    "Censys API rate limit exceeded.",
                    retry_after=retry_after,
                )
            if response.status_code == 404:
                logger.debug("Censys: no data for %s (404)", target)
                return []

            response.raise_for_status()

            # v3 envelope: {"result": {"resource": {...host data...}, "extensions": {...}}}
            body = response.json()
            data = body.get("result", {}).get("resource", {})

        results = _build_results(target, data)
        logger.debug(
            "Censys %s: services=%s, os=%s, asn=%s",
            target,
            len(data.get("services", []) or []),
            (data.get("operating_system") or {}).get("value", ""),
            (data.get("autonomous_system") or {}).get("asn", ""),
        )
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_service_entry(service: dict[str, Any]) -> dict[str, Any]:
    """Build a single service dict from a Censys v3 service object.

    Parameters
    ----------
    service:
        A single entry from the v3 result.resource["services"] list.

    Returns
    -------
    dict
        Keys: port (int), protocol (str), service_name (str).
        Optional key: x_certificates (str) — only present when the service
        has a non-empty certificate SHA-256 fingerprint.
        See DEC-MODULE-CENSYS-002.

    Notes
    -----
    v3 API field mapping vs v2:
      v2 service_name  → v3 protocol  (e.g. "HTTPS", "SSH")
      v2 transport_protocol → v3 transport_protocol (TCP/UDP, same name)
      v2 certificate (str) → v3 cert.fingerprint_sha256 (nested dict)
    """
    entry: dict[str, Any] = {
        "port": service.get("port", 0),
        "protocol": service.get("transport_protocol", ""),
        "service_name": service.get("protocol", ""),
    }
    cert_obj = service.get("cert") or {}
    cert_fp = cert_obj.get("fingerprint_sha256", "")
    if cert_fp:
        entry["x_certificates"] = cert_fp
    return entry


def _build_results(target: str, data: dict[str, Any]) -> list[dict]:
    """Construct STIX-like SCO dicts from the Censys v3 hosts API response.

    Parameters
    ----------
    target:
        The original IP address queried (used as fallback if API omits ip).
    data:
        The result.resource sub-object from the Censys v3 hosts JSON response.

    Returns
    -------
    list[dict]
        One ipv4-addr SCO always present. Service entries include x_certificates
        only when the certificate fingerprint is non-empty. See DEC-MODULE-CENSYS-002.

    Notes
    -----
    v3 API field mapping vs v2:
      v2 result.ip  → v3 result.resource.ip
      v2 result.operating_system.product → v3 result.resource.operating_system.value
      v2 result.location.country → v3 result.resource.location.country (same)
      v2 result.autonomous_system.{asn,name,...} → v3 result.resource.autonomous_system
        (via routing sub-object: asn, name, bgp_prefix, country_code same field names)
      v2 result.last_updated_at → v3 not directly present; omit/empty
    """
    raw_os = data.get("operating_system") or {}
    # v3: operating_system is an Attribute object with "value" field
    os_product = raw_os.get("value", "") or raw_os.get("product", "") if raw_os else ""

    raw_location = data.get("location") or {}
    location_country = raw_location.get("country", "") if raw_location else ""

    # v3: autonomous_system is a Routing object — same field names as v2
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

    raw_services = data.get("services") or []
    services = [_build_service_entry(svc) for svc in raw_services]

    ip_sco: dict[str, Any] = {
        "type": "ipv4-addr",
        "value": data.get("ip", target),
        "x_services": services,
        "x_os": os_product,
        "x_location_country": location_country,
        "x_autonomous_system": autonomous_system,
        # v3 does not expose last_updated_at at the host level; preserve key for compat
        "x_last_updated": data.get("last_updated_at", ""),
    }

    return [ip_sco]
