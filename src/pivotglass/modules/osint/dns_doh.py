"""Live DNS records over HTTPS (keyless).

API: GET {base}/dns-query?name={domain}&type={RRTYPE}  with ``Accept: application/dns-json``
(base default https://cloudflare-dns.com). Docs:
https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/make-api-requests/dns-json/

@decision DEC-MODULE-DNS-DOH-001
@title Resolve through a DNS-over-HTTPS service; the answer is live, and context, not a verdict
@status accepted
@rationale A keyless install could not resolve a domain, and Pivotglass must
           never resolve from the operator host (tests/test_no_direct_dns.py).
           This module satisfies both: it makes no DNS query of its own. It asks
           an intelligence service, Cloudflare's public resolver, over HTTPS, the
           same way every other module reads a web API. The adversary's
           authoritative server sees Cloudflare's recursive resolver, never the
           operator's address, and Cloudflare does not forward EDNS Client Subnet,
           so the operator's network is not disclosed to it either. The operator
           address is visible to Cloudflare as an HTTPS client, like any other
           service; the base URL is overridable (DEC-ENDPOINTS-001) for a
           gateway or another JSON-compatible DoH service.

           The answer is LIVE at query time. It is not passive DNS history (use
           the Mnemonic module for that): it says what the name resolves to now,
           from one resolver's cache or recursion, and may differ by resolver,
           time, or geography. ``x_dns_queried_at`` and ``x_dns_resolver`` carry
           that provenance. NXDOMAIN is a valid, recorded answer
           (``x_dns_status``), not an error; so are other DNS response codes such
           as SERVFAIL. A transport failure or a malformed body is a ModuleError
           and records nothing.

           A, AAAA, NS, MX, and CNAME answers also become their own SCOs so they
           can be pivoted (``x_dns_resolution_of``, ``x_dns_nameserver_of``,
           ``x_dns_mail_exchanger_of``, ``x_dns_alias_of``, each naming the
           queried domain). Neighbour counts are bounded. TXT records stay a
           property of the domain and are never parsed into indicators: SPF,
           verification tokens, and free text are not observables. Answers
           describe infrastructure configuration, not intent or ownership.
"""

from __future__ import annotations

import asyncio
import ipaddress
from datetime import UTC, datetime
from typing import Any

import httpx

from pivotglass.core.ioc_types import detect_ioc_type
from pivotglass.modules.base import BaseModule, ModuleError
from pivotglass.modules.keyless_http import json_body, keyless_get, unexpected_status

SOURCE = "Cloudflare DNS-over-HTTPS"
RESOLVER_LABEL = "Cloudflare DNS-over-HTTPS (live)"
ACCEPT = "application/dns-json"

# RRtype name -> numeric type in the JSON answer. Order is the query order.
RR_TYPES: dict[str, int] = {"A": 1, "AAAA": 28, "NS": 2, "MX": 15, "TXT": 16, "CNAME": 5}
_RCODES = {0: "NOERROR", 1: "FORMERR", 2: "SERVFAIL", 3: "NXDOMAIN", 4: "NOTIMP", 5: "REFUSED"}
_MAX_RECORDS_PER_TYPE = 25  # answers kept per RRtype and neighbour SCOs per RRtype
_MAX_TXT_LENGTH = 2048
# (rrtype, neighbour SCO type, reference field naming the queried domain)
_NEIGHBOURS = (
    ("A", "ipv4-addr", "x_dns_resolution_of"),
    ("AAAA", "ipv6-addr", "x_dns_resolution_of"),
    ("NS", "domain-name", "x_dns_nameserver_of"),
    ("MX", "domain-name", "x_dns_mail_exchanger_of"),
    ("CNAME", "domain-name", "x_dns_alias_of"),
)


def _clean_name(value: str) -> str:
    return value.strip().rstrip(".").lower()


def _answers(source: str, rrtype: str, body: Any) -> tuple[int, list[str]]:
    """Return (response code, answer data strings of the requested type) from one JSON body."""
    if not isinstance(body, dict) or not isinstance(body.get("Status"), int):
        raise ModuleError(f"{source} returned an unexpected response shape for {rrtype}; no result recorded.")
    answer = body.get("Answer")
    if answer is None:
        answer = []
    if not isinstance(answer, list):
        raise ModuleError(f"{source} returned an unexpected Answer shape for {rrtype}; no result recorded.")
    wanted = RR_TYPES[rrtype]
    data = [
        str(item["data"])
        for item in answer
        if isinstance(item, dict) and item.get("type") == wanted and isinstance(item.get("data"), str)
    ]
    return body["Status"], data


def _normalise(rrtype: str, values: list[str]) -> list[str]:
    """Normalise answer strings, drop invalid ones, de-duplicate, and bound the list."""
    out: list[str] = []
    for raw in values:
        if rrtype in {"A", "AAAA"}:
            try:
                address = ipaddress.ip_address(raw.strip())
            except ValueError:
                continue
            if address.version != (4 if rrtype == "A" else 6):
                continue
            item = str(address)
        elif rrtype in {"NS", "CNAME"}:
            item = _clean_name(raw)
        elif rrtype == "MX":
            parts = raw.split(None, 1)
            if len(parts) != 2 or not parts[0].isdigit():
                continue
            item = f"{int(parts[0])} {_clean_name(parts[1]) or '.'}"
        else:  # TXT: kept verbatim apart from the DoH JSON quoting, never parsed
            item = raw.strip()
            if len(item) >= 2 and item[0] == item[-1] == '"':
                item = item[1:-1]
            item = item[:_MAX_TXT_LENGTH]
        if item and item not in out:
            out.append(item)
        if len(out) >= _MAX_RECORDS_PER_TYPE:
            break
    return out


class DnsOverHttps(BaseModule):
    """A, AAAA, NS, MX, TXT, and CNAME records for a domain via DNS-over-HTTPS (no key)."""

    name = "osint/dns_doh"
    description = "Live DNS records (A, AAAA, NS, MX, TXT, CNAME) via DNS-over-HTTPS (no key)"
    author = "Pivotglass"
    module_type = "osint"
    service_id = "dns_doh"
    accepts = ("domain",)
    requires_api_key = False
    transport: httpx.AsyncBaseTransport | None = None

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {"required": True, "description": "Domain name", "default": ""},
        }

    async def _query(self, name: str, rrtype: str) -> tuple[int, list[str]]:
        response = await keyless_get(
            SOURCE,
            f"{self.base_url}/dns-query",
            params={"name": name, "type": rrtype},
            accept=ACCEPT,
            transport=self.transport,
        )
        if response.status_code != 200:
            raise unexpected_status(SOURCE, response)
        return _answers(SOURCE, rrtype, json_body(SOURCE, response))

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        name = _clean_name(target)
        if detect_ioc_type(name) != "domain":
            raise ModuleError(f"{SOURCE} accepts a domain name; '{target}' is not one.")
        outcomes = await asyncio.gather(*(self._query(name, rrtype) for rrtype in RR_TYPES))
        # Report the first non-NOERROR code (NXDOMAIN, SERVFAIL, ...) so a failure is visible.
        code = next((c for c, _ in outcomes if c != 0), 0)
        records: dict[str, list[str]] = {}
        for rrtype, (_, values) in zip(RR_TYPES, outcomes, strict=True):
            cleaned = _normalise(rrtype, values)
            if cleaned:
                records[rrtype] = cleaned
        primary: dict[str, Any] = {
            "type": "domain-name",
            "value": name,
            "x_dns_records": records,
            "x_dns_status": _RCODES.get(code, f"RCODE{code}"),
            "x_dns_resolver": RESOLVER_LABEL,
            "x_dns_queried_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        results: list[dict] = [primary]
        seen: set[tuple[str, str]] = set()
        for rrtype, sco_type, field in _NEIGHBOURS:
            for item in records.get(rrtype, []):
                value = item.split(" ", 1)[1] if rrtype == "MX" else item
                if sco_type == "domain-name" and (value == "." or detect_ioc_type(value) != "domain"):
                    continue
                if value == name or (sco_type, value) in seen:
                    continue
                seen.add((sco_type, value))
                results.append({"type": sco_type, "value": value, field: name})
        return results
