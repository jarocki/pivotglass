"""DNS resolution module — stdlib only, no API key required.

@decision DEC-MODULE-DNS-001
@title Use socket.getaddrinfo for A/AAAA; stdlib only
@status accepted
@rationale dnspython adds a dependency not yet in pyproject.toml.
           socket.getaddrinfo covers A and AAAA records via the OS resolver,
           which respects /etc/hosts and local DNS configuration — useful for
           testing against internal infrastructure. MX, NS, and TXT record
           support can be added via dnspython in a future issue once the
           dependency is approved. The RECORD_TYPE option is accepted now so
           the interface is stable when richer record support arrives.

@decision DEC-MODULE-DNS-002
@title Return STIX 2.1 SCO dicts without python-stix2 objects (Issue #4 deferred)
@status accepted
@rationale Same rationale as DEC-MODULE-WHOIS-002. Plain dicts with type/value
           allow the full hunt pipeline to be exercised before Issue #4 adds
           proper stix2 object construction and ID generation.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any

from adversary_pursuit.modules.base import BaseModule

logger = logging.getLogger(__name__)


class DnsResolve(BaseModule):
    """DNS resolution and record lookup for domains.

    No API key required. Uses socket.getaddrinfo (stdlib) for A and AAAA
    records. See DEC-MODULE-DNS-001.

    Returns STIX 2.1 SCO dicts: domain-name and ipv4-addr/ipv6-addr objects.
    """

    name = "osint/dns_resolve"
    description = "DNS resolution and record lookup"
    author = "Adversary Pursuit"
    module_type = "osint"

    def __init__(self) -> None:
        super().__init__()
        self.options = {
            "TARGET": {
                "required": True,
                "description": "Domain to resolve",
                "default": "",
            },
            "RECORD_TYPE": {
                "required": False,
                "description": "DNS record type (A, AAAA, MX, NS, TXT)",
                "default": "A",
            },
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        """Resolve DNS for target and return STIX-like dicts.

        Parameters
        ----------
        target:
            Domain name to resolve (e.g. "example.com")
        options:
            Runtime overrides. Supports RECORD_TYPE (default: "A").
            MX/NS/TXT are accepted but return an empty resolved set for now;
            the domain-name SCO is always emitted. See DEC-MODULE-DNS-001.

        Returns
        -------
        list[dict]
            Always includes a domain-name SCO for the target. Includes
            ipv4-addr SCOs for each resolved A record and ipv6-addr SCOs
            for each resolved AAAA record.
        """
        target = target.strip()
        record_type = options.get("RECORD_TYPE", "A").upper()

        results: list[dict] = []

        # Always emit the domain-name SCO
        results.append({"type": "domain-name", "value": target})

        # Resolve based on record type
        if record_type in ("A", "AAAA", "ANY"):
            ip_results = await _resolve(target, record_type)
            results.extend(ip_results)
        else:
            # MX, NS, TXT — not yet implemented via stdlib
            logger.debug(
                "RECORD_TYPE=%s not yet supported via stdlib; returning domain-name only",
                record_type,
            )

        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve(domain: str, record_type: str) -> list[dict]:
    """Resolve A and/or AAAA records using socket.getaddrinfo.

    Parameters
    ----------
    domain:
        Hostname to resolve
    record_type:
        "A" (IPv4 only), "AAAA" (IPv6 only), or "ANY" (both)

    Returns
    -------
    list of ipv4-addr and/or ipv6-addr STIX SCO dicts
    """
    # Map record type to socket address family filter
    if record_type == "A":
        families = {socket.AF_INET}
    elif record_type == "AAAA":
        families = {socket.AF_INET6}
    else:
        # ANY or unrecognised — return both
        families = {socket.AF_INET, socket.AF_INET6}

    results: list[dict] = []
    try:
        loop = asyncio.get_event_loop()
        addrs = await loop.run_in_executor(
            None,
            lambda: socket.getaddrinfo(domain, None),
        )
        seen: set[str] = set()
        for family, _type, _proto, _canon, sockaddr in addrs:
            if family not in families:
                continue
            ip = sockaddr[0]
            if ip in seen:
                continue
            seen.add(ip)
            stix_type = "ipv4-addr" if family == socket.AF_INET else "ipv6-addr"
            results.append({"type": stix_type, "value": ip})
    except socket.gaierror as exc:
        logger.warning("DNS resolution failed for %s: %s", domain, exc)
    except OSError as exc:
        logger.warning("socket error resolving %s: %s", domain, exc)

    return results
