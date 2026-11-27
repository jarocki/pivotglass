"""Shodan InternetDB module (keyless).

API: GET {base}/{ip}  (base default https://internetdb.shodan.io)
Docs: https://internetdb.shodan.io/

@decision DEC-MODULE-INTERNETDB-001
@title 404 is "no data"; ports, hostnames, CPEs, tags, and vulns as reported
@status accepted
@rationale InternetDB is Shodan's free, keyless, weekly-refreshed summary of an
           IP. HTTP 404 (``{"detail": "No information available"}``) means Shodan
           holds nothing for the address, which is an empty result. ``vulns`` are
           CVEs Shodan associates with the reported software versions; they are
           not confirmed exploitable, and ``tags`` are Shodan's labels, not
           verdicts, so both are recorded under the source's namespace without
           interpretation. Hostnames become domain-name SCOs for pivoting, and each
           reported CVE becomes a bare ``vulnerability`` stub (name and CVE
           reference only, no x_ fields) so cti/cisa_kev, cti/first_epss and
           cti/nvd_cve pivot on it through the same event-bus mechanism (#58). The stub
           claims nothing about the CVE: severity, exploitation and exposure come
           from those modules. The keyed Shodan host module stays the authority for
           banners and history.
"""

from __future__ import annotations

from typing import Any

import httpx

from pivotglass.core.ioc_types import detect_ioc_type
from pivotglass.modules.base import BaseModule, ModuleError
from pivotglass.modules.keyless_http import json_body, keyless_get, unexpected_status
from pivotglass.modules.vulnerability import cve_stubs

SOURCE = "Shodan InternetDB"
_MAX_HOSTNAMES = 25
_SCO_TYPES = {"ipv4": "ipv4-addr", "ipv6": "ipv6-addr"}


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


class ShodanInternetDB(BaseModule):
    """Open ports, hostnames, CPEs, tags, and associated CVEs for an IP (no key)."""

    name = "osint/shodan_internetdb"
    description = "Open ports, hostnames, CPEs, tags, and CVEs via Shodan InternetDB (no key)"
    author = "Pivotglass"
    module_type = "osint"
    service_id = "shodan_internetdb"
    accepts = ("ipv4", "ipv6")
    requires_api_key = False
    transport: httpx.AsyncBaseTransport | None = None

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {"required": True, "description": "IP address", "default": ""},
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        target = target.strip()
        sco_type = _SCO_TYPES.get(detect_ioc_type(target) or "")
        if sco_type is None:
            raise ModuleError(f"{SOURCE} accepts an IP address; '{target}' is not one.")
        response = await keyless_get(SOURCE, f"{self.base_url}/{target}", transport=self.transport)
        if response.status_code == 404:
            return []
        if response.status_code != 200:
            raise unexpected_status(SOURCE, response)
        data = json_body(SOURCE, response)
        if not isinstance(data, dict):
            raise ModuleError(f"{SOURCE} returned an unexpected response shape; no result recorded.")
        hostnames = _strings(data.get("hostnames"))
        primary = {
            "type": sco_type,
            "value": str(data.get("ip") or target),
            "x_internetdb_ports": [int(p) for p in data.get("ports", []) if isinstance(p, int)],
            "x_internetdb_hostnames": hostnames,
            "x_internetdb_cpes": _strings(data.get("cpes")),
            "x_internetdb_tags": _strings(data.get("tags")),
            "x_internetdb_vulns": _strings(data.get("vulns")),
        }
        results: list[dict] = [primary]
        seen: set[str] = set()
        for name in hostnames:
            name = name.rstrip(".").lower()
            if len(seen) >= _MAX_HOSTNAMES or name in seen or detect_ioc_type(name) != "domain":
                continue
            seen.add(name)
            results.append({"type": "domain-name", "value": name, "x_internetdb_hostname_of": primary["value"]})
        results.extend(cve_stubs(primary["x_internetdb_vulns"]))
        return results
