"""RDAP registration module for domains and IP addresses (keyless).

API: GET {base}/domain/{name} and {base}/ip/{address}  (base default https://rdap.org)
rdap.org is a bootstrap redirector (RFC 9224): it answers with a redirect to the
authoritative registry or RIR server (for example rdap.verisign.com or
rdap.arin.net), which the module follows.

@decision DEC-MODULE-RDAP-001
@title Bootstrap through rdap.org; record registration facts, never personal contacts
@status accepted
@rationale A bootstrap redirector keeps one base URL (overridable per
           DEC-ENDPOINTS-001) instead of a copy of IANA's bootstrap files that
           would drift. 404 means the registry has no object (unregistered name,
           or a reserved block such as 10.0.0.0/8 that no RIR serves): an empty
           result. The module records the registrar, registration, expiry and
           last-changed dates, status codes, nameservers, and for IPs the network
           name, handle, range, and country. Entity names are copied only when the
           vCard says the entity is an organisation (or for the registrar role);
           e-mail addresses, phone numbers, and individuals' names are never
           copied. ``x_rdap_server`` records which authoritative server answered.
           Registration data describes administration, not intent.

@decision DEC-RDAP-REDIRECT-001
@title Follow a bootstrap redirect only to an IANA-listed registry host
@status accepted
@rationale Security review 2026-11-21: following any redirect let a hostile or
           compromised bootstrap answer steer a request to a private address,
           and per-hop address checks alone leave DNS rebinding and encoding
           tricks open. The authority is IANA's RDAP bootstrap registry
           (data.iana.org/rdap, fetched on first use and cached for a day): a
           hop must be https to a host name it lists, at most two hops. IP
           literals are refused. Registry hosts are operated by registries and
           RIRs, so their DNS is not attacker-controlled. The module does no DNS
           resolution of its own (the no-direct-DNS invariant,
           tests/test_no_direct_dns.py); an earlier resolve-and-check layer was
           removed because httpx resolves again on connect, so it never closed
           the rebinding window it was meant to. If a listed name is made to
           resolve inward, TLS verification (httpx default, kept on by
           keyless_http) fails the handshake before any request bytes are
           sent, unless the inward service holds a publicly trusted
           certificate for the registry name. A connect-time peer-address
           check was rejected: behind a configured proxy the peer is the
           proxy, often a private address. The bootstrap fetch goes direct
           to data.iana.org, not through a base-URL override.
"""

from __future__ import annotations

import ipaddress
import time
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from pivotglass.core.ioc_types import detect_ioc_type
from pivotglass.modules.base import BaseModule, ModuleError
from pivotglass.modules.keyless_http import json_body, keyless_get, unexpected_status

SOURCE = "RDAP"


IANA_BOOTSTRAP = "https://data.iana.org/rdap"
_BOOTSTRAP_FILES = ("dns", "ipv4", "ipv6", "asn")
_BOOTSTRAP_TTL = 24 * 3600.0
_bootstrap_cache: tuple[float, frozenset[str]] | None = None


async def _registry_hosts() -> frozenset[str]:
    """Hosts of every RDAP server in the IANA bootstrap registry (cached for a day; patched in tests)."""
    global _bootstrap_cache
    now = time.monotonic()
    if _bootstrap_cache is not None and now - _bootstrap_cache[0] < _BOOTSTRAP_TTL:
        return _bootstrap_cache[1]
    hosts: set[str] = set()
    for name in _BOOTSTRAP_FILES:
        response = await keyless_get(f"{SOURCE} bootstrap", f"{IANA_BOOTSTRAP}/{name}.json")
        if response.status_code != 200:
            raise unexpected_status(f"{SOURCE} bootstrap", response)
        for service in json_body(f"{SOURCE} bootstrap", response).get("services", []):
            for url in service[-1] if isinstance(service, list) and service else []:
                parts = urlsplit(str(url))
                if parts.scheme == "https" and parts.hostname:
                    hosts.add(parts.hostname.lower().rstrip("."))
    if not hosts:
        raise ModuleError(f"{SOURCE} bootstrap registry is empty; no result recorded.")
    _bootstrap_cache = (now, frozenset(hosts))
    return _bootstrap_cache[1]


async def _require_registry_https(url: str) -> None:
    """Refuse a redirect hop unless it is https to an IANA-listed RDAP registry host name.

    The allowlist is the authority (DEC-RDAP-REDIRECT-001): neither a hostile
    bootstrap answer nor a name an attacker controls can steer a request inward.
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme != "https" or not host:
        raise ModuleError(f"{SOURCE} redirected to a non-https address; refused.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ModuleError(f"{SOURCE} redirected to a bare IP address; refused.")
    if host not in await _registry_hosts():
        raise ModuleError(f"{SOURCE} redirected to {host}, which is not an IANA-listed RDAP server; refused.")


_MAX_NAMESERVERS = 13
_SCO_TYPES = {"domain": "domain-name", "ipv4": "ipv4-addr", "ipv6": "ipv6-addr"}


def _vcard(entity: dict[str, Any]) -> dict[str, str]:
    """Return the vCard 'fn' and 'kind' properties of an RDAP entity."""
    fields: dict[str, str] = {}
    card = entity.get("vcardArray")
    if isinstance(card, list) and len(card) == 2 and isinstance(card[1], list):
        for prop in card[1]:
            if isinstance(prop, list) and len(prop) >= 4 and prop[0] in {"fn", "kind"}:
                fields[prop[0]] = str(prop[3])
    return fields


def _walk_entities(entities: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for entity in entities if isinstance(entities, list) else []:
        if isinstance(entity, dict):
            found.append(entity)
            found.extend(_walk_entities(entity.get("entities")))
    return found


def _organisation_for(entities: list[dict[str, Any]], role: str) -> str:
    """Name of the first entity with *role* whose vCard marks it an organisation."""
    for entity in entities:
        if role not in (entity.get("roles") or []):
            continue
        card = _vcard(entity)
        if role == "registrar" or card.get("kind", "").lower() in {"org", "group"}:
            return card.get("fn", "")
    return ""


def _events(data: dict[str, Any]) -> dict[str, str]:
    return {
        str(event.get("eventAction")): str(event.get("eventDate", ""))
        for event in data.get("events") or []
        if isinstance(event, dict) and event.get("eventAction")
    }


class Rdap(BaseModule):
    """Registration data for a domain or IP address via RDAP (no key)."""

    name = "osint/rdap"
    description = "Registrar, registration and expiry dates, and IP network ownership via RDAP (no key)"
    author = "Pivotglass"
    module_type = "osint"
    service_id = "rdap"
    accepts = ("domain", "ipv4", "ipv6")
    requires_api_key = False
    transport: httpx.AsyncBaseTransport | None = None

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {"required": True, "description": "Domain or IP address", "default": ""},
        }

    async def _get_following_registry_redirects(self, url: str) -> httpx.Response:
        """GET *url*, following at most two redirects to IANA-listed https registry servers.

        rdap.org answers with a redirect to the authoritative registry. Each hop
        is checked before it is requested (see ``_require_registry_https``), so a
        hostile bootstrap answer cannot steer a request inward.
        """
        for _hop in range(3):
            response = await keyless_get(SOURCE, url, follow_redirects=False, transport=self.transport)
            if response.status_code not in {301, 302, 303, 307, 308}:
                return response
            location = response.headers.get("Location", "")
            next_url = str(response.url.join(location)) if location else ""
            await _require_registry_https(next_url)
            url = next_url
        raise ModuleError(f"{SOURCE} redirected too many times; no result recorded.")

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        target = target.strip().rstrip(".").lower()
        kind = detect_ioc_type(target) or ""
        sco_type = _SCO_TYPES.get(kind)
        if sco_type is None:
            raise ModuleError(f"{SOURCE} accepts a domain or IP address; '{target}' is neither.")
        path = "domain" if kind == "domain" else "ip"
        response = await self._get_following_registry_redirects(
            f"{self.base_url}/{path}/{quote(target, safe='.:')}"
        )
        if response.status_code == 404:
            return []
        if response.status_code != 200:
            raise unexpected_status(SOURCE, response)
        data = json_body(SOURCE, response)
        if not isinstance(data, dict):
            raise ModuleError(f"{SOURCE} returned an unexpected response shape; no result recorded.")

        entities = _walk_entities(data.get("entities"))
        events = _events(data)
        primary: dict[str, Any] = {
            "type": sco_type,
            "value": target,
            "x_rdap_server": f"{response.url.scheme}://{response.url.host}",
            "x_rdap_handle": str(data.get("handle") or ""),
            "x_rdap_status": [str(s) for s in data.get("status") or []],
            "x_rdap_registered": events.get("registration", ""),
            "x_rdap_last_changed": events.get("last changed", ""),
            "x_rdap_abuse_organisation": _organisation_for(entities, "abuse"),
        }
        results: list[dict] = [primary]
        if kind == "domain":
            nameservers = [
                str(ns.get("ldhName", "")).rstrip(".").lower()
                for ns in data.get("nameservers") or []
                if isinstance(ns, dict) and ns.get("ldhName")
            ][:_MAX_NAMESERVERS]
            registrar = next((e for e in entities if "registrar" in (e.get("roles") or [])), {})
            iana_id = next(
                (str(p.get("identifier")) for p in registrar.get("publicIds") or []
                 if isinstance(p, dict) and "IANA" in str(p.get("type", ""))),
                "",
            )
            primary.update({
                "x_rdap_registrar": _organisation_for(entities, "registrar"),
                "x_rdap_registrar_iana_id": iana_id,
                "x_rdap_expires": events.get("expiration", ""),
                "x_rdap_nameservers": nameservers,
            })
            results.extend(
                {"type": "domain-name", "value": ns, "x_rdap_nameserver_of": target}
                for ns in dict.fromkeys(nameservers)
                if detect_ioc_type(ns) == "domain"
            )
        else:
            cidrs = [
                f"{c.get('v4prefix') or c.get('v6prefix')}/{c.get('length')}"
                for c in data.get("cidr0_cidrs") or []
                if isinstance(c, dict) and (c.get("v4prefix") or c.get("v6prefix"))
            ]
            primary.update({
                "x_rdap_network_name": str(data.get("name") or ""),
                "x_rdap_range": f"{data.get('startAddress', '')} - {data.get('endAddress', '')}".strip(" -"),
                "x_rdap_cidrs": cidrs,
                "x_rdap_country": str(data.get("country") or ""),
                "x_rdap_registrant_organisation": _organisation_for(entities, "registrant"),
            })
        return results
