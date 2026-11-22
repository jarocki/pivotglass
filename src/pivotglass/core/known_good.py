"""Known-good and shared-infrastructure recognition.

The single authority for "this indicator is on a curated public list". It lets
the analyst set aside a public resolver, a revocation server, an empty-file hash
or a research scanner in one action, and see when an indicator sits on shared
cloud, CDN, shortener or dynamic-DNS infrastructure.

@decision DEC-KNOWN-GOOD-001
@title A list match is labelled context, never a verdict; only some categories may be set aside
@status accepted
@rationale Owner decision 2026-11-21 (docs/plans/V1.4.0_ENRICHMENT_STORY_PLAN.md).
           A curated MISP warninglist subset (CC0 1.0) ships with the package so
           recognition is offline and deterministic; ``scripts/update_warninglists.py``
           refreshes it once per minor release and records the upstream commit.
           CIRCL hashlookup evidence is read from stored objects, and only from
           objects written by the ``cti/hashlookup`` module, so online knowledge
           enters only as cited evidence and imported data cannot whitewash a hash. Every
           match names its list and version. Categories carry their own meaning:
           ``benign`` and ``scanner`` may be set aside (tagged role=benign by the
           analyst); ``shared`` and ``sinkhole`` are context that often matters
           *more*, not less (malware on a cloud host, a domain taken over by a
           sinkhole), so they are never offered for set-aside. A subdomain of a
           popular site is shared infrastructure, not known good: attackers abuse
           subdomains of popular hosting; the same holds for every list's parent-domain
           match (only an explicit leading-dot suffix entry covers subdomains). A hash that hashlookup knows but that a
           source also lists as malicious is ``contested``.
"""

from __future__ import annotations

import gzip
import ipaddress
import json
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

BUNDLE_PATH = Path(__file__).resolve().parents[1] / "data" / "warninglists.json.gz"

# category, value kind, short label shown beside the indicator.
SELECTED_LISTS: dict[str, tuple[str, str, str]] = {
    "public-dns-v4": ("benign", "ip", "Public DNS resolver"),
    "public-dns-v6": ("benign", "ip", "Public DNS resolver"),
    "public-dns-hostname": ("benign", "host", "Public DNS resolver"),
    "crl-hostname": ("benign", "host", "Certificate revocation (CRL/OCSP)"),
    "crl-ip": ("benign", "ip", "Certificate revocation (CRL/OCSP)"),
    "whats-my-ip": ("benign", "host", "IP-echo service"),
    "captive-portals": ("benign", "host", "Connectivity check"),
    "security-provider-blogpost": ("benign", "host", "Security vendor blog"),
    "tranco10k": ("benign", "host", "Tranco top-10k site"),
    "empty-hashes": ("benign", "hash", "Hash of an empty file"),
    "eicar.com": ("benign", "hash", "EICAR test file"),
    "common-ioc-false-positive": ("benign", "hash", "Common IoC false positive"),
    "ti-falsepositives": ("benign", "hash", "Common IoC false positive"),
    "shodan-scanning": ("scanner", "ip", "Shodan scanner"),
    "censys-scanning": ("scanner", "ip", "Censys scanner"),
    "shadowserver": ("scanner", "ip", "Shadowserver scanner"),
    "rapid7-scanning": ("scanner", "ip", "Rapid7 Sonar scanner"),
    "amazon-aws": ("shared", "ip", "AWS address space"),
    "google-gcp": ("shared", "ip", "Google Cloud address space"),
    "microsoft-azure": ("shared", "ip", "Azure address space"),
    "cloudflare": ("shared", "ip", "Cloudflare address space"),
    "akamai": ("shared", "ip", "Akamai address space"),
    "fastly": ("shared", "ip", "Fastly address space"),
    "parking-domain": ("shared", "ip", "Domain-parking server"),
    "url-shortener": ("shared", "host", "URL shortener"),
    "dynamic-dns": ("shared", "host", "Dynamic DNS provider"),
    "sinkholes": ("sinkhole", "ip", "Known sinkhole"),
}

CATEGORIES: dict[str, dict[str, Any]] = {
    "benign": {"label": "Known good", "set_aside": True},
    "scanner": {"label": "Internet scanner", "set_aside": True},
    "shared": {"label": "Shared infrastructure", "set_aside": False},
    "sinkhole": {"label": "Sinkhole", "set_aside": False},
    "contested": {"label": "Known file, also reported malicious", "set_aside": False},
}

_HASH = re.compile(r"^(?:[0-9a-f]{32}|[0-9a-f]{40}|[0-9a-f]{56}|[0-9a-f]{64}|[0-9a-f]{128})$")
_POPULARITY_LIST = "tranco10k"
HASHLOOKUP_MODULE = "cti/hashlookup"


@dataclass(frozen=True)
class KnownMatch:
    list_id: str
    list_name: str
    category: str
    label: str
    matched: str
    source: str  # e.g. "MISP warninglist tranco10k v20261005"

    @property
    def set_aside(self) -> bool:
        return bool(CATEGORIES[self.category]["set_aside"])

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "set_aside": self.set_aside,
                "category_label": CATEGORIES[self.category]["label"]}


class _Index:
    def __init__(self, bundle: dict[str, Any]) -> None:
        self.commit = str(bundle.get("commit") or "")
        self.lists: dict[str, dict[str, Any]] = {}
        # ip: {prefixlen: {network_int: [list_id]}} per address family
        self.networks: dict[int, dict[int, dict[int, list[str]]]] = {4: {}, 6: {}}
        self.hosts: dict[str, list[str]] = {}
        self.suffixes: dict[str, list[str]] = {}
        self.hashes: dict[str, list[str]] = {}
        for list_id, data in (bundle.get("lists") or {}).items():
            if list_id not in SELECTED_LISTS:
                continue
            self.lists[list_id] = data
            kind = SELECTED_LISTS[list_id][1]
            for raw in data.get("list", ()):
                entry = str(raw).strip().casefold()
                if kind == "ip":
                    try:
                        net = ipaddress.ip_network(entry, strict=False)
                    except ValueError:
                        continue
                    bucket = self.networks[net.version].setdefault(net.prefixlen, {})
                    bucket.setdefault(int(net.network_address), []).append(list_id)
                elif kind == "host":
                    if entry.startswith("."):
                        self.suffixes.setdefault(entry[1:].rstrip("."), []).append(list_id)
                    else:
                        self.hosts.setdefault(entry.rstrip("."), []).append(list_id)
                elif kind == "hash":
                    self.hashes.setdefault(entry, []).append(list_id)

    def match_ip(self, value: str) -> list[tuple[str, str]]:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return []
        number = int(address)
        width = address.max_prefixlen
        found: list[tuple[str, str]] = []
        for prefix, bucket in self.networks[address.version].items():
            network = number >> (width - prefix) << (width - prefix) if prefix else 0
            for list_id in bucket.get(network, ()):
                found.append((list_id, f"{ipaddress.ip_address(network)}/{prefix}"))
        return found

    def match_host(self, host: str) -> list[tuple[str, str, bool]]:
        """(list_id, entry, exact) for the host, its parents, and suffix rules."""
        labels = host.split(".")
        found: list[tuple[str, str, bool]] = []
        for index in range(len(labels) - 1):
            candidate = ".".join(labels[index:])
            exact = index == 0 or (index == 1 and labels[0] == "www")
            for list_id in self.hosts.get(candidate, ()):
                found.append((list_id, candidate, exact))
            if index > 0:
                for list_id in self.suffixes.get(candidate, ()):
                    found.append((list_id, "." + candidate, True))
        return found


@lru_cache(maxsize=1)
def _index() -> _Index:
    try:
        bundle = json.loads(gzip.decompress(BUNDLE_PATH.read_bytes()))
    except (OSError, ValueError):
        bundle = {}
    return _Index(bundle)


def bundle_status() -> dict[str, Any]:
    index = _index()
    return {
        "present": bool(index.lists),
        "commit": index.commit,
        "lists": {list_id: {"name": data.get("name"), "version": data.get("version"),
                            "entries": len(data.get("list", ()))}
                  for list_id, data in index.lists.items()},
        "attribution": "MISP warninglists (https://github.com/MISP/misp-warninglists), CC0 1.0",
    }


def _make(index: _Index, list_id: str, matched: str, *, category: str | None = None,
          label: str | None = None) -> KnownMatch:
    default_category, _kind, default_label = SELECTED_LISTS[list_id]
    data = index.lists[list_id]
    return KnownMatch(
        list_id=list_id,
        list_name=str(data.get("name") or list_id),
        category=category or default_category,
        label=label or default_label,
        matched=matched,
        source=f"MISP warninglist {list_id} v{data.get('version')}",
    )


def _host_of(entity_type: str, value: str) -> str:
    if entity_type in {"domain-name", "hostname"}:
        return value.casefold().rstrip(".")
    if entity_type == "url":
        try:
            host = urlsplit(value if "://" in value else f"http://{value}").hostname
        except ValueError:
            return ""
        return (host or "").casefold().rstrip(".")
    return ""


def known_matches(entity_type: str, value: str) -> list[KnownMatch]:
    """Every bundled-list match for one indicator, most actionable first."""
    text = str(value or "").strip()
    kind = entity_type.strip()
    if not text:
        return []
    index = _index()
    found: dict[str, KnownMatch] = {}
    if kind in {"ipv4-addr", "ipv6-addr"}:
        for list_id, matched in index.match_ip(text):
            found.setdefault(list_id, _make(index, list_id, matched))
    elif kind in {"file"} or kind.startswith("file-hash-") or (kind == "" and _HASH.match(text.casefold())):
        for list_id in index.hashes.get(text.casefold(), ()):
            found.setdefault(list_id, _make(index, list_id, text.casefold()))
    host = _host_of(kind, text)
    if host:
        for list_id, matched, exact in index.match_host(host):
            if list_id == _POPULARITY_LIST and kind == "url":
                match = _make(index, list_id, matched, category="shared",
                              label=f"Hosted on popular site {matched}")
            elif not exact and not matched.startswith("."):
                # A parent-domain match is never whole-domain trust: anyone who
                # controls a subdomain can host anything. Only an explicit
                # leading-dot suffix entry (dynamic DNS) covers subdomains.
                label = (f"Subdomain of popular site {matched}" if list_id == _POPULARITY_LIST
                         else f"Subdomain of {matched} ({SELECTED_LISTS[list_id][2]})")
                match = _make(index, list_id, matched, category="shared", label=label)
            else:
                match = _make(index, list_id, matched)
            # Prefer an exact match over a parent-domain match from the same list.
            if list_id not in found or (exact and found[list_id].category == "shared"):
                found[list_id] = match
    return sorted(found.values(), key=_rank)


_CATEGORY_ORDER = {"contested": 0, "benign": 1, "scanner": 2, "sinkhole": 3, "shared": 4}
_LIST_ORDER = {list_id: position for position, list_id in enumerate(SELECTED_LISTS)}


def _rank(match: KnownMatch) -> tuple[int, int]:
    """Most actionable category first; within it, the most specific list (selection order)."""
    return _CATEGORY_ORDER[match.category], _LIST_ORDER.get(match.list_id, -1)


def _hashes_of(obj: dict[str, Any]) -> list[str]:
    hashes = obj.get("hashes") or {}
    values = [str(item) for item in hashes.values()] if isinstance(hashes, dict) else []
    value = str(obj.get("value") or "")
    if _HASH.match(value.casefold()):
        values.append(value)
    return sorted({item.casefold() for item in values})


def object_matches(obj: dict[str, Any]) -> list[KnownMatch]:
    """Matches for a stored STIX object: list matches plus CIRCL hashlookup evidence."""
    entity_type = str(obj.get("type") or "")
    matches: dict[tuple[str, str], KnownMatch] = {}
    if entity_type == "file":
        for digest in _hashes_of(obj):
            for match in known_matches("file", digest):
                matches.setdefault((match.list_id, match.category), match)
    else:
        for match in known_matches(entity_type, str(obj.get("value") or "")):
            matches.setdefault((match.list_id, match.category), match)
    # Trust hashlookup properties only on objects the cti/hashlookup module wrote;
    # an imported bundle could otherwise carry x_hashlookup_* to whitewash a hash.
    if obj.get("x_hashlookup_known") and obj.get("x_pivotglass_source_module") == HASHLOOKUP_MODULE:
        sources = [str(item) for item in obj.get("x_hashlookup_sources") or [] if str(item)]
        flagged = [str(item) for item in obj.get("x_hashlookup_known_malicious") or [] if str(item)]
        product = str(obj.get("x_hashlookup_product") or obj.get("name") or "").strip()
        label = "Known file" + (f": {product}" if product else "")
        if sources:
            label += f" ({', '.join(sources[:3])})"
        match = KnownMatch(
            list_id="circl-hashlookup",
            list_name="CIRCL hashlookup",
            category="contested" if flagged else "benign",
            label=label + (f"; reported malicious by {', '.join(flagged[:3])}" if flagged else ""),
            matched=(_hashes_of(obj) or [""])[0],
            source=HASHLOOKUP_MODULE,
        )
        matches[(match.list_id, match.category)] = match
    return sorted(matches.values(), key=_rank)


def summarize(matches: Iterable[KnownMatch]) -> dict[str, Any] | None:
    """One compact descriptor for list badges and graph nodes, or None."""
    items = list(matches)
    if not items:
        return None
    first = items[0]
    return {
        "category": first.category,
        "label": first.label,
        "set_aside": first.set_aside and not any(item.category == "contested" for item in items),
        "sources": sorted({item.source for item in items}),
        "count": len(items),
    }
