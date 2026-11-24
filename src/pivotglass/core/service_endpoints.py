"""Default API base URLs and the rules for overriding them.

@decision DEC-ENDPOINTS-001
@title One registry of default base URLs; config stores only overrides
@status accepted
@rationale Analysts route provider and intelligence traffic through API gateways
           and proxies (LiteLLM proxy, Cloudflare AI Gateway, corporate egress).
           Each service's default base URL lives here exactly once. Modules,
           credential checks, and model listing build request URLs from the
           *effective* base (override or default), so a gateway applies to every
           call for that service. Configuration stores only the override; clearing
           it restores the default. Overrides must be https, except http on a
           loopback host for local gateways, and may not carry credentials, a
           query, or a fragment: secrets travel in headers, never in a URL that
           could be logged.
"""

from __future__ import annotations

import ipaddress
from typing import Any, Protocol
from urllib.parse import urlsplit

# Intelligence services, keyed by the same id as CTI_SERVICES / disabled_services.
SERVICE_BASE_URLS: dict[str, str] = {
    "shodan": "https://api.shodan.io",
    "virustotal": "https://www.virustotal.com/api/v3",
    "abuseipdb": "https://api.abuseipdb.com/api/v2",
    "hibp": "https://haveibeenpwned.com/api/v3",
    "otx": "https://otx.alienvault.com",
    "urlscan": "https://urlscan.io",
    "censys_pat": "https://api.platform.censys.io",
    "greynoise": "https://api.greynoise.io",
    # abuse.ch: three hosts, one shared Auth-Key (DEC-ABUSECH-AUTH-001).
    "threatfox": "https://threatfox-api.abuse.ch/api/v1",
    "urlhaus": "https://urlhaus-api.abuse.ch/v1",
    "malwarebazaar": "https://mb-api.abuse.ch/api/v1",
    # Keyless context sources (no credential; base URL still overridable).
    "mnemonic_pdns": "https://api.mnemonic.no",
    "shodan_internetdb": "https://internetdb.shodan.io",
    "sans_isc": "https://isc.sans.edu/api",
    "rdap": "https://rdap.org",
    "wayback": "https://web.archive.org",
    "hashlookup": "https://hashlookup.circl.lu",
}


class EndpointOverrides(Protocol):
    def get_endpoint_override(self, service_id: str) -> str | None: ...


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def normalize_base_url(value: str) -> str:
    """Return a validated base URL without a trailing slash, or raise ValueError."""
    text = value.strip()
    if not text:
        raise ValueError("Base URL is empty")
    parts = urlsplit(text)
    host = (parts.hostname or "").lower()
    if parts.scheme not in {"https", "http"} or not host:
        raise ValueError("Base URL must start with https:// and name a host")
    if parts.scheme == "http" and not _is_loopback(host):
        raise ValueError("Use https:// (http:// is allowed only for localhost gateways)")
    if parts.username or parts.password:
        raise ValueError("Base URL must not contain credentials")
    if parts.query or parts.fragment:
        raise ValueError("Base URL must not contain a query or fragment")
    return text.rstrip("/")


def effective_base_url(config: EndpointOverrides | None, service_id: str, default: str) -> str:
    """Return the override for *service_id* when one is set, else *default*."""
    override = config.get_endpoint_override(service_id) if config is not None else None
    return (override or default).rstrip("/")


def endpoint_init_config(config: EndpointOverrides | None, service_id: str) -> dict[str, Any]:
    """Return the ``base_url`` entry a module's ``initialize()`` needs, if overridden."""
    if config is None or not service_id:
        return {}
    override = config.get_endpoint_override(service_id)
    return {"base_url": override} if override else {}
