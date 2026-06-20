"""IoC type detection and module routing.

@decision DEC-IOC-TYPES-001
@title Pattern-based IoC type detection for REPL `hunt <ioc>` dispatch
@status accepted
@rationale Pattern-match is explicit, predictable, and lets us later add
           `hunt --type=ip 8.8.8.8` overrides. The 'accepts' tuple on each
           PursuitModule subclass is the single authority for module/IoC routing —
           no duplicate registries. Detection order matters: URL before IPv4 (URLs
           can contain IPs), SHA256 before SHA1 before MD5 (longer hashes first),
           email before domain (emails contain '@' which domains don't).
"""

from __future__ import annotations

import re
from typing import Literal

IocType = Literal["ipv4", "ipv6", "domain", "url", "md5", "sha1", "sha256", "email"]

_IPV4_RE = re.compile(r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$")
_IPV6_RE = re.compile(r"^[0-9a-fA-F:]+$")
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
)
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_MD5_RE = re.compile(r"^[a-fA-F0-9]{32}$")
_SHA1_RE = re.compile(r"^[a-fA-F0-9]{40}$")
_SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def detect_ioc_type(value: str) -> IocType | None:
    """Detect the IoC type of a string value.

    Detection order (priority):
    1. URL — checked before IPv4 because URLs can contain IPs
    2. IPv4 — strict octet range check
    3. IPv6 — colon-separated hex with at least 2 colons
    4. SHA256 — 64 hex chars (checked before shorter hashes)
    5. SHA1 — 40 hex chars
    6. MD5 — 32 hex chars
    7. Email — contains @ with domain part
    8. Domain — validated FQDN pattern

    Parameters
    ----------
    value:
        Raw string to classify. Leading/trailing whitespace is stripped.

    Returns
    -------
    IocType | None
        The detected IoC type string, or None if the value matches no known pattern.
    """
    s = value.strip()
    if not s:
        return None
    if _URL_RE.match(s):
        return "url"
    if _IPV4_RE.match(s):
        return "ipv4"
    if ":" in s and _IPV6_RE.match(s) and s.count(":") >= 2:
        return "ipv6"
    if _SHA256_RE.match(s):
        return "sha256"
    if _SHA1_RE.match(s):
        return "sha1"
    if _MD5_RE.match(s):
        return "md5"
    if _EMAIL_RE.match(s):
        return "email"
    if _DOMAIN_RE.match(s):
        return "domain"
    return None
