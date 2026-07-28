"""VirusTotal v3 multi-scanner CTI module.

Queries the VirusTotal v3 API for analysis of IPs, domains, URLs, and file hashes.
Auto-detects the target type from the input string.

API docs: https://docs.virustotal.com/reference/overview

@decision DEC-MODULE-VT-001
@title Auto-detect target type from input string
@status accepted
@rationale Users shouldn't need to specify whether their target is an IP, domain,
           URL, or hash. Simple heuristics (regex for IP, URL prefix, hex string
           length for hashes) handle 99% of cases. TARGET_TYPE option overrides
           for edge cases.

@decision DEC-MODULE-VT-002
@title Return unified STIX dict regardless of target type
@status accepted
@rationale All target types produce the same core fields (malicious/suspicious/
           harmless/undetected counts, reputation, last_analysis_date). Type-specific
           fields (as_owner, country for IPs/domains) are added when present.
           This simplifies downstream scoring and storage.

@decision DEC-MODULE-VT-003
@title URL targets are base64-encoded per VT v3 API spec
@status accepted
@rationale VT v3 requires URL identifiers to be base64-encoded (without padding).
           The module handles this transparently — the analyst provides a plain URL.
"""

from __future__ import annotations

import base64
import ipaddress
import logging
import re
from typing import Any

import httpx

from adversary_pursuit.modules.base import (
    AuthenticationError,
    BaseModule,
    RateLimitError,
)

logger = logging.getLogger(__name__)

# Regex for SHA-256, SHA-1, MD5 hashes
_HASH_RE = re.compile(r"^(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
_FILE_RELATIONSHIPS = (
    "bundled_files",
    "dropped_files",
    "execution_parents",
    "contacted_domains",
    "contacted_ips",
    "contacted_urls",
)


class VirusTotal(BaseModule):
    """Query VirusTotal v3 for file, URL, IP, and domain analysis."""

    name: str = "cti/virustotal"
    description: str = "Query VirusTotal v3 for file, URL, IP, and domain analysis"
    author: str = "Adversary Pursuit"
    module_type: str = "cti"
    accepts = ("ipv4", "ipv6", "domain", "url", "md5", "sha1", "sha256")

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {
                "required": True,
                "description": "IP, domain, URL, or file hash to check",
                "default": "",
            },
            "TARGET_TYPE": {
                "required": False,
                "description": "Type override: ip, domain, url, hash (auto-detected if omitted)",
                "default": "",
            },
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        """Query VirusTotal v3 for the target indicator."""
        api_key = self._config.get("api_key", "")
        if not api_key:
            raise AuthenticationError(
                "VirusTotal API key not configured. "
                "Set via 'ap config set api_keys.virustotal <key>' or AP_VT_API_KEY env var."
            )

        target_type = options.get("TARGET_TYPE", "") or self._detect_type(target)
        url = self._build_url(target, target_type)

        async with httpx.AsyncClient(timeout=30.0) as client:
            request_kwargs: dict[str, Any] = {
                "headers": {"x-apikey": api_key, "Accept": "application/json"}
            }
            if target_type == "hash":
                request_kwargs["params"] = {
                    "relationships": ",".join(_FILE_RELATIONSHIPS)
                }
            resp = await client.get(url, **request_kwargs)

            if resp.status_code == 401:
                raise AuthenticationError("VirusTotal API key is invalid.")
            if resp.status_code == 429:
                retry = resp.headers.get("Retry-After")
                raise RateLimitError(
                    "VirusTotal rate limit exceeded.",
                    retry_after=int(retry) if retry else None,
                )
            resp.raise_for_status()
            data = resp.json()

        return self._build_results(target, target_type, data)

    def _detect_type(self, target: str) -> str:
        """Auto-detect target type."""
        # URL
        if target.startswith(("http://", "https://")):
            return "url"
        # IP
        try:
            ipaddress.ip_address(target)
            return "ip"
        except ValueError:
            pass
        # Hash
        if _HASH_RE.match(target):
            return "hash"
        # Default: domain
        return "domain"

    def _build_url(self, target: str, target_type: str) -> str:
        """Build VT v3 API URL for the target."""
        base = "https://www.virustotal.com/api/v3"
        if target_type == "ip":
            return f"{base}/ip_addresses/{target}"
        if target_type == "domain":
            return f"{base}/domains/{target}"
        if target_type == "url":
            url_id = base64.urlsafe_b64encode(target.encode()).rstrip(b"=").decode()
            return f"{base}/urls/{url_id}"
        if target_type == "hash":
            return f"{base}/files/{target}"
        return f"{base}/domains/{target}"

    def _build_results(self, target: str, target_type: str, data: dict) -> list[dict]:
        """Convert VT API response to STIX-like dicts."""
        object_data = data.get("data", {})
        attrs = object_data.get("attributes", {})
        stats = attrs.get("last_analysis_stats", {})

        stix_type_map = {
            "ip": "ipv4-addr",
            "domain": "domain-name",
            "url": "url",
            "hash": "file",
        }
        stix_type = stix_type_map.get(target_type, "domain-name")

        result: dict[str, Any] = {
            "type": stix_type,
            "value": target,
            "x_malicious": stats.get("malicious", 0),
            "x_suspicious": stats.get("suspicious", 0),
            "x_harmless": stats.get("harmless", 0),
            "x_undetected": stats.get("undetected", 0),
            "x_reputation": attrs.get("reputation", 0),
            "x_last_analysis_date": attrs.get("last_analysis_date", 0),
        }

        # Type-specific fields
        if target_type in ("ip", "domain"):
            result["x_as_owner"] = attrs.get("as_owner", "")
            result["x_country"] = attrs.get("country", "")

        results = [result]
        if target_type == "hash":
            result.update(
                {
                    "x_meaningful_name": attrs.get("meaningful_name", ""),
                    "x_file_names": attrs.get("names", [])[:20],
                    "x_type_description": attrs.get("type_description", ""),
                    "x_magic": attrs.get("magic", ""),
                    "x_size": attrs.get("size", 0),
                    "x_tags": attrs.get("tags", [])[:30],
                    "x_md5": attrs.get("md5", ""),
                    "x_sha1": attrs.get("sha1", ""),
                    "x_sha256": attrs.get("sha256", ""),
                    "x_creation_date": attrs.get("creation_date", 0),
                    "x_first_submission_date": attrs.get("first_submission_date", 0),
                    "x_last_submission_date": attrs.get("last_submission_date", 0),
                    "x_times_submitted": attrs.get("times_submitted", 0),
                    "x_exiftool": attrs.get("exiftool", {}),
                    "x_signature_info": attrs.get("signature_info", {}),
                    "x_trid": attrs.get("trid", [])[:12],
                }
            )
            related, related_results, related_links = _related_file_objects(
                object_data.get("relationships", {})
            )
            result["x_related_objects"] = related
            result["x_related_links"] = related_links
            for relationship in _FILE_RELATIONSHIPS:
                result[f"x_{relationship}"] = [
                    entry["value"]
                    for entry in related
                    if entry["relationship"] == relationship and entry.get("value")
                ]
            results.extend(related_results)

        return results


def _related_file_objects(
    relationships: dict[str, Any],
) -> tuple[list[dict[str, str]], list[dict[str, Any]], list[str]]:
    """Normalize relationship expansions included in a VT file response."""
    related: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []
    links: list[str] = []
    seen: set[tuple[str, str]] = set()
    type_map = {
        "file": "file",
        "domain": "domain-name",
        "ip_address": "ipv4-addr",
        "url": "url",
    }
    for relationship in _FILE_RELATIONSHIPS:
        envelope = relationships.get(relationship, {})
        if not isinstance(envelope, dict):
            continue
        relation_links = envelope.get("links", {})
        if isinstance(relation_links, dict):
            links.extend(
                value
                for value in relation_links.values()
                if isinstance(value, str) and value.startswith(("https://", "http://"))
            )
        entries = envelope.get("data", [])
        if isinstance(entries, dict):
            entries = [entries]
        for entry in entries[:20] if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            vendor_type = str(entry.get("type", ""))
            attrs = entry.get("attributes", {})
            attrs = attrs if isinstance(attrs, dict) else {}
            stix_type = type_map.get(vendor_type)
            if vendor_type == "url":
                value = str(attrs.get("url", ""))
            else:
                value = str(
                    attrs.get("value")
                    or attrs.get("sha256")
                    or entry.get("id", "")
                )
            if not value or stix_type is None or (stix_type, value) in seen:
                continue
            seen.add((stix_type, value))
            related.append(
                {
                    "relationship": relationship,
                    "type": stix_type,
                    "value": value,
                }
            )
            results.append({"type": stix_type, "value": value})
    return related, results, list(dict.fromkeys(links))[:12]
