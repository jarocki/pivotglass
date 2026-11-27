"""IP to ASN, AS organisation, and announced prefix from the local DB-IP ASN database (keyless, offline).

@decision DEC-MODULE-IP-ASN-001
@title ASN and prefix come from the local DB-IP Lite database; no case IP leaves the machine
@status accepted
@rationale Extends DEC-GEO-LOCAL-001. The module makes no network request: it
           reads the DB-IP Lite ASN database that the analyst downloaded to
           ~/.pivotglass/geo/ (Configuration -> Geolocation data), so a keyless
           install can map an IP to its network without disclosing the IP to a
           third party. The data is a licensed local copy (CC BY 4.0), labelled
           with its edition in ``x_asn_source``; the required attribution
           (``x_asn_attribution``, geolocation.ATTRIBUTION) travels with every
           record. The prefix is the database's matching network (maxminddb
           ``get_with_prefix_len``), which is DB-IP's aggregation and may differ
           from the BGP announcement seen at any given vantage point. Non-global
           addresses yield an empty result. A missing database is an error that
           says how to install it, never a silent empty result. The AS is its own
           ``autonomous-system`` SCO, linked to the IP by ``x_asn_of`` so the graph
           shows it. An ASN names a network operator, not an actor.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from pivotglass.core.geolocation import ATTRIBUTION, GeoDatabase, _reader
from pivotglass.core.ioc_types import detect_ioc_type
from pivotglass.modules.base import BaseModule, ModuleError

SOURCE = "Local DB-IP ASN database"
_SCO_TYPES = {"ipv4": "ipv4-addr", "ipv6": "ipv6-addr"}
INSTALL_HINT = (
    "The DB-IP Lite geolocation databases are not installed. Download them once from "
    "Configuration -> Geolocation data (about 65 MB, stored in ~/.pivotglass/geo/); "
    "no case IP is sent anywhere."
)


class IpAsn(BaseModule):
    """ASN, AS organisation, and announced prefix for an IP from a local database (no key, offline)."""

    name = "osint/ip_asn"
    description = "IP to ASN, AS organisation, and prefix from the local DB-IP database (offline)"
    author = "Pivotglass"
    module_type = "osint"
    service_id = "ip_asn"
    accepts = ("ipv4", "ipv6")
    requires_api_key = False
    # Tests point this at a fixture directory; production uses the default geo directory.
    database: GeoDatabase | None = None

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
        db = self.database or GeoDatabase()
        path = db.path("asn")
        if not path.is_file():
            raise ModuleError(INSTALL_HINT)
        address = ipaddress.ip_address(target)
        if not address.is_global:
            return []
        try:
            found = _reader(str(path), path.stat().st_mtime).get_with_prefix_len(str(address))
        except (OSError, ValueError) as exc:
            raise ModuleError(
                f"{SOURCE} could not be read ({type(exc).__name__}); reinstall it from Configuration."
            ) from exc
        record, prefix_len = found if found else (None, 0)
        number = (record or {}).get("autonomous_system_number")
        if not isinstance(number, int):
            return []
        organisation = str((record or {}).get("autonomous_system_organization") or "")
        network = ipaddress.ip_network(f"{address}/{prefix_len}", strict=False)
        ip_value = str(address)
        return [
            {
                "type": sco_type,
                "value": ip_value,
                "x_asn_number": number,
                "x_asn_name": organisation,
                "x_asn_prefix": str(network),
                "x_asn_source": db.source_label(),
                "x_asn_attribution": ATTRIBUTION,
            },
            {
                "type": "autonomous-system",
                "number": number,
                "name": organisation,
                "x_asn_of": ip_value,
                "x_asn_source": db.source_label(),
                "x_asn_attribution": ATTRIBUTION,
            },
        ]
