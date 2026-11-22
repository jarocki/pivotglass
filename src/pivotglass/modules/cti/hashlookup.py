"""CIRCL hashlookup module: known-file recognition (keyless).

API: GET {base}/lookup/{md5|sha1|sha256}/{hash}  (base default https://hashlookup.circl.lu)
Docs: https://www.circl.lu/services/hashlookup/

@decision DEC-MODULE-HASHLOOKUP-001
@title Known file (NSRL and other known-software sets) is context, not a verdict
@status accepted
@rationale hashlookup answers whether a hash appears in known-software sets such as
           NIST NSRL and Linux distribution packages. 404 means "not present in any
           database" and yields an empty result: absence is not evidence of
           malice. 400 means a malformed hash and is a ModuleError. A match yields
           one ``file`` SCO whose output contract the known-good authority reads:
           ``hashes`` (MD5 / SHA-1 / SHA-256 when present), ``name`` from FileName,
           ``x_hashlookup_known: true``, ``x_hashlookup_sources`` (the response's
           ``source`` and ``db`` values, as returned), ``x_hashlookup_product``
           (ProductName or package name), ``x_hashlookup_known_malicious`` (the
           ``KnownMalicious`` field when present, else []), and
           ``x_hashlookup_trust`` (CIRCL's 0-100 score; 50 means no opinion).
           ``x_pivotglass_source_module`` is stamped by the workspace at storage
           time (DEC-WORKSPACE-SOURCE-PROVENANCE-001), as for every module.
"""

from __future__ import annotations

from typing import Any

import httpx

from pivotglass.core.ioc_types import detect_ioc_type
from pivotglass.modules.base import BaseModule, ModuleError
from pivotglass.modules.keyless_http import json_body, keyless_get, unexpected_status

SOURCE = "CIRCL hashlookup"
_HASH_FIELDS = (("MD5", "MD5"), ("SHA-1", "SHA-1"), ("SHA-256", "SHA-256"))


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


def _product(data: dict[str, Any]) -> str:
    code = data.get("ProductCode")
    if isinstance(code, dict) and code.get("ProductName"):
        return str(code["ProductName"])
    for key in ("ProductName", "PackageName"):
        if data.get(key):
            return str(data[key])
    for parent in data.get("parents") or []:
        if isinstance(parent, dict) and parent.get("PackageName"):
            return str(parent["PackageName"])
    return ""


class HashLookup(BaseModule):
    """Check whether a file hash is in CIRCL's known-software sets (no key)."""

    name = "cti/hashlookup"
    description = "Known-file check (NSRL and other known-software sets) via CIRCL hashlookup (no key)"
    author = "Pivotglass"
    module_type = "cti"
    service_id = "hashlookup"
    accepts = ("md5", "sha1", "sha256")
    requires_api_key = False
    transport: httpx.AsyncBaseTransport | None = None

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {"required": True, "description": "MD5, SHA-1, or SHA-256 hash", "default": ""},
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        target = target.strip()
        kind = detect_ioc_type(target) or ""
        if kind not in self.accepts:
            raise ModuleError(f"{SOURCE} accepts an MD5, SHA-1, or SHA-256 hash; '{target}' is not one.")
        response = await keyless_get(
            SOURCE, f"{self.base_url}/lookup/{kind}/{target}", transport=self.transport
        )
        if response.status_code == 404:
            return []
        if response.status_code == 400:
            raise ModuleError(f"{SOURCE} rejected the hash as malformed.")
        if response.status_code != 200:
            raise unexpected_status(SOURCE, response)
        data = json_body(SOURCE, response)
        if not isinstance(data, dict):
            raise ModuleError(f"{SOURCE} returned an unexpected response shape; no result recorded.")

        hashes = {stix: str(data[field]).lower() for field, stix in _HASH_FIELDS if data.get(field)}
        stix_key = {"md5": "MD5", "sha1": "SHA-1", "sha256": "SHA-256"}[kind]
        hashes.setdefault(stix_key, target.lower())
        sco: dict[str, Any] = {
            "type": "file",
            # The queried hash, so the stored object matches the analyst's indicator.
            "value": target.lower(),
            "hashes": hashes,
            "x_hashlookup_known": True,
            "x_hashlookup_sources": list(dict.fromkeys(_strings(data.get("source")) + _strings(data.get("db")))),
            "x_hashlookup_product": _product(data),
            "x_hashlookup_known_malicious": _strings(data.get("KnownMalicious")),
        }
        if data.get("FileName"):
            sco["name"] = str(data["FileName"])
        trust = data.get("hashlookup:trust")
        if isinstance(trust, (int, float)):
            sco["x_hashlookup_trust"] = int(trust)
        return [sco]
