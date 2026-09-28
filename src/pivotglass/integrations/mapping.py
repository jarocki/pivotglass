"""Deterministic Pivotglass indicator mappings for external graph systems."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any

_HASH_LENGTHS = {"md5": 32, "sha1": 40, "sha256": 64, "sha512": 128}
_STIX_TO_SYNAPSE = {
    "ipv4-addr": "inet:ipv4",
    "ipv6-addr": "inet:ipv6",
    "domain-name": "inet:fqdn",
    "url": "inet:url",
    "email-addr": "inet:email",
    "md5": "hash:md5",
    "sha1": "hash:sha1",
    "sha256": "hash:sha256",
    "sha512": "hash:sha512",
}


@dataclass(frozen=True)
class SynapseLift:
    """A parameterized, read-only lift of one normalized Pivotglass value."""

    form: str
    value: str
    query: str
    variables: dict[str, Any]


def synapse_lift(indicator_type: str, value: str) -> SynapseLift:
    """Map one supported indicator to a parameterized Synapse form lift."""
    normalized_type = indicator_type.strip().casefold()
    form = _STIX_TO_SYNAPSE.get(normalized_type)
    if form is None:
        raise ValueError(f"unsupported Synapse indicator type: {indicator_type}")
    normalized_value = _normalize(normalized_type, value)
    return SynapseLift(
        form=form,
        value=normalized_value,
        query=f"{form}=$pivotglass_value",
        variables={"pivotglass_value": normalized_value},
    )


def _normalize(indicator_type: str, value: str) -> str:
    stripped = value.strip()
    if indicator_type in {"ipv4-addr", "ipv6-addr"}:
        address = ipaddress.ip_address(stripped)
        expected = 4 if indicator_type == "ipv4-addr" else 6
        if address.version != expected:
            raise ValueError(f"value is not a valid {indicator_type}")
        return address.compressed
    if indicator_type == "domain-name":
        domain = stripped.rstrip(".").encode("idna").decode("ascii").casefold()
        if not domain or len(domain) > 253:
            raise ValueError("invalid domain name")
        return domain
    if indicator_type == "email-addr":
        local, separator, domain = stripped.rpartition("@")
        if not separator or not local or not domain:
            raise ValueError("invalid email address")
        return f"{local}@{domain.encode('idna').decode('ascii').casefold()}"
    if indicator_type in _HASH_LENGTHS:
        digest = stripped.casefold()
        if len(digest) != _HASH_LENGTHS[indicator_type] or not re.fullmatch(r"[0-9a-f]+", digest):
            raise ValueError(f"invalid {indicator_type} digest")
        return digest
    if not stripped:
        raise ValueError("indicator value cannot be empty")
    return stripped
