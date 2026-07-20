"""WHOIS lookup module — stdlib only, no API key required.

@decision DEC-MODULE-WHOIS-001
@title Use subprocess whois without DNS resolution; stdlib only
@status accepted
@rationale python-whois is an optional dependency and was not included in the
           initial dependency set. The system whois command is available on
           macOS and most Linux distributions. We try subprocess first and
           never fall back to an operating-system resolver: direct DNS queries from the
           operator host are forbidden. DNS and hosting metadata must come
           from explicit intelligence services such as DomainTools, DNSDB,
           URLScan, VirusTotal, PassiveTotal, or Censys.
           Full python-whois or ipwhois integration can replace this in a
           future issue once the dependency is approved.

@decision DEC-MODULE-WHOIS-002
@title Return STIX 2.1 SCO dicts without python-stix2 objects (Issue #4 deferred)
@status accepted
@rationale python-stix2 object construction requires schema validation and ID
           generation (deterministic UUID5 for SCOs). That logic is scoped to
           Issue #4. For now, modules return plain dicts with the minimum STIX
           fields (type, value) so the pipeline can be exercised end-to-end.
           Issue #4 will wrap these dicts in proper stix2 objects.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
from typing import Any

from adversary_pursuit.modules.base import BaseModule

logger = logging.getLogger(__name__)


class WhoisLookup(BaseModule):
    """WHOIS lookup for domains and IP addresses.

    No API key required. Uses the system whois command when available,
    without performing DNS resolution. See DEC-MODULE-WHOIS-001.

    Returns STIX 2.1 SCO dicts (plain dicts, not stix2 objects).
    At minimum returns a domain-name or ipv4-addr/ipv6-addr SCO.
    Additional registrar/org info is included as custom properties when
    parsed from whois output.
    """

    name = "osint/whois_lookup"
    description = "WHOIS lookup for domains and IPs"
    author = "Adversary Pursuit"
    module_type = "osint"
    accepts = ("ipv4", "ipv6", "domain")

    def __init__(self) -> None:
        super().__init__()
        self.options = {
            "TARGET": {
                "required": True,
                "description": "Domain or IP to look up",
                "default": "",
            },
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        """Query WHOIS for target and return STIX-like dicts.

        Parameters
        ----------
        target:
            Domain name (e.g. "example.com") or IP address (e.g. "8.8.8.8")
        options:
            Runtime overrides (currently unused for this module)

        Returns
        -------
        list[dict]
            List of STIX 2.1 SCO dicts. Always includes at least one entry
            for the target itself. May include additional records parsed from
            whois output.
        """
        target = target.strip()
        results: list[dict] = []

        # Determine if target is an IP address or domain
        is_ip, ip_version = _classify_target(target)

        # Build the primary SCO for the target itself
        if is_ip:
            stix_type = "ipv4-addr" if ip_version == 4 else "ipv6-addr"
            primary = {"type": stix_type, "value": target}
        else:
            primary = {"type": "domain-name", "value": target}

        # Try to enrich with whois data
        whois_raw = await _run_whois(target)
        if whois_raw:
            parsed = _parse_whois(whois_raw)
            primary.update(parsed)

        results.append(primary)

        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _classify_target(target: str) -> tuple[bool, int | None]:
    """Return (is_ip, version) for the given target string."""
    try:
        addr = ipaddress.ip_address(target)
        return True, addr.version
    except ValueError:
        return False, None


async def _run_whois(target: str) -> str | None:
    """Run system whois command and return stdout, or None on failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "whois",
            target,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        return stdout.decode("utf-8", errors="replace") if stdout else None
    except FileNotFoundError:
        logger.debug("whois command not found; skipping enrichment for %s", target)
        return None
    except asyncio.TimeoutError:
        # Bug 1 fix (Phase 18 Slice 4): whois timeout is expected for many targets;
        # downgrade to debug so resolver noise never bleeds into REPL stdout.
        logger.debug("whois timed out for %s", target)
        return None
    except OSError as exc:
        logger.debug("whois failed for %s: %s", target, exc)
        return None


def _parse_whois(raw: str) -> dict[str, Any]:
    """Extract key-value pairs from raw whois output.

    Returns a dict of custom properties (x_ prefixed per STIX spec) for
    fields of interest: registrar, org, country, creation_date.
    """
    custom: dict[str, Any] = {}
    field_map = {
        "registrar": ("registrar:", "x_registrar"),
        "org": ("org:", "x_org"),
        "organisation": ("organisation:", "x_org"),
        "country": ("country:", "x_country"),
        "creation date": ("creation date:", "x_creation_date"),
        "created": ("created:", "x_creation_date"),
    }

    for line in raw.splitlines():
        line_lower = line.lower().strip()
        for _key, (prefix, prop) in field_map.items():
            if line_lower.startswith(prefix):
                value = line.split(":", 1)[-1].strip()
                if value and prop not in custom:
                    custom[prop] = value
                break

    return custom
