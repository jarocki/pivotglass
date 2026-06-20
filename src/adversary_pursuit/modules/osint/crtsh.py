"""Certificate Transparency log search module via crt.sh.

Queries crt.sh for SSL/TLS certificate records associated with a domain,
surfacing subdomains discovered through Certificate Transparency logs.

API: https://crt.sh/?q=%25.<domain>&output=json

@decision DEC-MODULE-CRTSH-001
@title GET with wildcard prefix; deduplicate on name_value; seed seen with query target
@status accepted
@rationale crt.sh exposes a simple GET endpoint: ?q=%25.<domain>&output=json
           The %25 encodes a URL-encoded '%' which acts as a SQL LIKE wildcard
           prefix, returning all certificates for subdomains of <domain> plus
           the domain itself. Responses are JSON arrays of certificate records.
           Each record may contain a 'name_value' field with one or more newline-
           separated SANs (Subject Alternative Names). Deduplication is on the
           individual name_value strings (after wildcard-*.  prefix strip) to
           avoid duplicate SCOs for the same subdomain discovered in multiple
           certs. The seen set is seeded with the query target and an empty
           string — mirroring DEC-MODULE-URLSCAN-003. No API key is required.
           TIMEOUT = 60.0 per project standard.

@decision DEC-MODULE-CRTSH-002
@title 404 / empty JSON array → empty list; HTML response → ModuleError (DEC-61-CRTSH-001)
@status accepted
@rationale crt.sh returns an empty JSON array [] when no certificates are
           found for the queried domain. This is a valid clean result. An
           empty list is returned to preserve the uniform list[dict] return
           type. HTTP 404 from crt.sh (unusual but possible) is also mapped
           to an empty list rather than raising. However, crt.sh occasionally
           serves HTML (a status page or rate-limit error) when the JSON
           endpoint is degraded. Parsing HTML would create a fragile parallel
           data path. Per DEC-61-CRTSH-001, an HTML response raises ModuleError,
           not returns a synthesized SCO list.

@decision DEC-MODULE-CRTSH-003
@title One domain-name--<uuid5> SCO per unique stripped name; 50 SCO cap per call
@status accepted
@rationale Each unique subdomain/SAN discovered via CT logs becomes one
           domain-name STIX 2.1 SCO. The SCO ID is uuid5 namespaced on the
           name_value string (post-strip) for stable, deterministic identifiers.
           Custom fields use the x_crtsh_ namespace: issuer_ca_id (int), not_after
           (expiry timestamp string), entry_timestamp (when the CT log entry
           was observed). Wildcard '*.  ' prefix is stripped before dedup and
           before SCO construction (DEC-61-CRTSH-001). Cap at 50 unique
           domain-name SCOs per call — large apex domains routinely have
           hundreds of certificates and unbounded output overwhelms downstream
           consumers (mirrors URLScan's 15-cap, scaled up for subdomain enumeration).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from adversary_pursuit.modules.base import (
    BaseModule,
    ModuleError,
    RateLimitError,
)

# Maximum SCOs emitted per hunt() call (DEC-MODULE-CRTSH-003)
_MAX_RESULTS = 50

logger = logging.getLogger(__name__)

TIMEOUT = 60.0

# crt.sh namespace for deterministic SCO IDs
_CRTSH_NS = uuid.UUID("6ba7b818-9dad-11d1-80b4-00c04fd430c8")


class CrtSh(BaseModule):
    """Search Certificate Transparency logs via crt.sh for domain subdomains.

    crt.sh is a free, keyless CT log aggregator. Querying a domain returns
    all SSL/TLS certificates issued for that domain and its subdomains as
    discovered in public Certificate Transparency logs.

    Returns STIX 2.1 domain-name SCO dicts with x_crtsh_* custom fields
    for each unique SAN/name_value found across all matching certificates.

    No API key is required.
    """

    name = "osint/crtsh"
    description = "Search Certificate Transparency logs via crt.sh for subdomains"
    author = "Adversary Pursuit"
    module_type = "osint"
    accepts = ("domain",)
    requires_api_key = False

    _API_URL = "https://crt.sh/"

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {
                "required": True,
                "description": "Domain name to search CT logs for (e.g. example.com)",
                "default": "",
            },
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        """Search crt.sh Certificate Transparency logs for the given domain.

        Parameters
        ----------
        target:
            Domain name to query (e.g. "example.com"). The wildcard prefix
            (%25.) is appended automatically so subdomains are included.
        options:
            Runtime overrides (no module-specific options for crt.sh).

        Returns
        -------
        list[dict]
            Zero or more domain-name STIX 2.1 SCO dicts. Empty list when no
            CT log entries are found. Each dict has:
              type: "domain-name"
              id: "domain-name--<uuid5-of-name_value>"
              value: the SAN/subdomain string (e.g. "sub.example.com")
              x_crtsh_issuer_ca_id: integer CA identifier from crt.sh
              x_crtsh_not_after: certificate expiry timestamp string
              x_crtsh_entry_timestamp: CT log entry timestamp string

        Raises
        ------
        RateLimitError
            When the API returns 429.
        httpx.HTTPStatusError
            For unexpected 4xx/5xx responses (404 is mapped to empty list).
        httpx.RequestError
            For network-level failures.
        """
        params = {"q": f"%.{target}", "output": "json"}

        async with httpx.AsyncClient() as client:
            response = await client.get(
                self._API_URL,
                params=params,
                headers={"Accept": "application/json"},
                timeout=TIMEOUT,
            )

            if response.status_code == 404:
                # crt.sh 404 — domain has no CT log entries
                logger.debug("crt.sh %s: 404 (no CT records)", target)
                return []

            if response.status_code == 429:
                retry_header = response.headers.get("Retry-After")
                retry_after = int(retry_header) if retry_header else None
                raise RateLimitError(
                    "crt.sh API rate limit exceeded.",
                    retry_after=retry_after,
                )

            response.raise_for_status()

            # crt.sh can return an empty body or 'null' for domains with no records
            raw = response.text.strip()
            if not raw or raw == "null":
                logger.debug("crt.sh %s: empty response (no CT records)", target)
                return []

            # HTML response signals endpoint degradation or rate limiting — per
            # DEC-61-CRTSH-001, raise ModuleError rather than parse HTML.
            content_type = response.headers.get("content-type", "").lower()
            if raw.lstrip().startswith("<") or "text/html" in content_type:
                raise ModuleError(
                    f"crt.sh returned HTML instead of JSON for target '{target}'. "
                    "The endpoint may be degraded or rate-limiting. Try again later."
                )

            entries = response.json()

        if not entries or not isinstance(entries, list):
            logger.debug("crt.sh %s: no entries in response", target)
            return []

        results = []
        # Seed seen with the query target and empty string (DEC-MODULE-CRTSH-001,
        # mirrors DEC-MODULE-URLSCAN-003) to suppress the apex domain itself and
        # any blank names from the result set.
        seen: set[str] = {target, ""}

        for entry in entries:
            if len(results) >= _MAX_RESULTS:
                logger.debug("crt.sh %s: capped at %d results", target, _MAX_RESULTS)
                break
            name_value = entry.get("name_value", "")
            if not name_value:
                continue
            # name_value may contain multiple newline-separated SANs
            for name in name_value.splitlines():
                name = name.strip()
                # Strip wildcard prefix before dedup (DEC-MODULE-CRTSH-003)
                if name.startswith("*."):
                    name = name[2:]
                if not name or name in seen:
                    continue
                seen.add(name)
                sco = _build_domain_sco(name, entry)
                results.append(sco)
                if len(results) >= _MAX_RESULTS:
                    break

        logger.debug("crt.sh %s: found %d unique CT entries", target, len(results))
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_domain_sco(name: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Construct a STIX 2.1 domain-name SCO from a crt.sh CT log entry.

    Parameters
    ----------
    name:
        The unique SAN/subdomain string (already deduplicated by the caller).
    entry:
        One element from the crt.sh JSON array response.

    Returns
    -------
    dict
        domain-name SCO with x_crtsh_* custom fields per DEC-MODULE-CRTSH-003.
    """
    sco_id = f"domain-name--{uuid.uuid5(_CRTSH_NS, name)}"
    return {
        "type": "domain-name",
        "id": sco_id,
        "value": name,
        "x_crtsh_issuer_ca_id": int(entry.get("issuer_ca_id", 0) or 0),
        "x_crtsh_not_after": entry.get("not_after", "") or "",
        "x_crtsh_entry_timestamp": entry.get("entry_timestamp", "") or "",
    }
