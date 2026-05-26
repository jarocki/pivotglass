"""abuse.ch ThreatFox IOC platform module.

Queries the ThreatFox API for threat intelligence on indicators of compromise
including IP:port combinations, URLs, domains, and file hashes.

API docs: https://threatfox.abuse.ch/api/

@decision DEC-MODULE-THREATFOX-001
@title Single POST endpoint with JSON body; ioc_type dispatch to STIX SCO type
@status accepted
@rationale ThreatFox uses a single POST endpoint for all queries. The request
           body contains {"query": "search_ioc", "search_term": target}. The
           response 'data' array contains IOC records where each record has an
           'ioc_type' field that determines the correct STIX SCO type:
             - 'ip:port'    -> ipv4-addr SCO (value = IP portion)
             - 'url'        -> url SCO
             - 'domain'     -> domain-name SCO
             - 'md5_hash'   -> file SCO (hashes.MD5)
             - 'sha256_hash'-> file SCO (hashes.SHA-256)
           Unknown ioc_types are emitted as-is with a best-effort type guess.
           No API key is required. TIMEOUT = 60.0 per project standard.

@decision DEC-MODULE-THREATFOX-002
@title query_status != 'ok' with empty data mapped to empty list
@status accepted
@rationale ThreatFox returns query_status='no_results' when the IOC is not
           in the database. This is a valid clean result, not an error. An
           empty list is returned to preserve the uniform list[dict] return
           type. Any status where 'data' is absent or empty also maps to [].

@decision DEC-MODULE-THREATFOX-003
@title One SCO per IOC record; dedup on ioc_value within a single hunt() call
@status accepted
@rationale ThreatFox can return multiple records for the same IOC value from
           different threat actor attributions. Each record becomes one SCO.
           Within a single hunt() call, duplicate ioc_values are collapsed to
           avoid storing the same observable twice. The first record's metadata
           is used; subsequent identical values are skipped.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from adversary_pursuit.modules.base import (
    BaseModule,
    RateLimitError,
)

logger = logging.getLogger(__name__)

TIMEOUT = 60.0

# ThreatFox namespace for deterministic SCO IDs
_THREATFOX_NS = uuid.UUID("6ba7b814-9dad-11d1-80b4-00c04fd430c8")


class ThreatFox(BaseModule):
    """Query abuse.ch ThreatFox for threat intelligence on IPs, domains, URLs, and hashes.

    ThreatFox is a free, keyless IOC sharing platform operated by abuse.ch.
    Returns STIX 2.1 SCO dicts typed based on the ioc_type field in each
    ThreatFox record (ipv4-addr, url, domain-name, or file).

    No API key is required.
    """

    name = "cti/threatfox"
    description = "Search abuse.ch ThreatFox IOC platform for threat intelligence"
    author = "Adversary Pursuit"
    module_type = "cti"
    requires_api_key = False

    _API_URL = "https://threatfox-api.abuse.ch/api/v1/"

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {
                "required": True,
                "description": "IP address, domain, URL, or file hash to query",
                "default": "",
            },
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        """Query ThreatFox for IOC records matching the target.

        Parameters
        ----------
        target:
            Any IOC value: IPv4 address, domain name, URL, MD5 hash, or
            SHA-256 hash. ThreatFox performs a substring search.
        options:
            Runtime overrides (no module-specific options for ThreatFox).

        Returns
        -------
        list[dict]
            Zero or more STIX 2.1 SCO dicts. The SCO type is chosen based on
            the ThreatFox ioc_type field for each record:
              'ip:port'     -> ipv4-addr with value=IP and x_tf_port=port
              'url'         -> url with value=url
              'domain'      -> domain-name with value=domain
              'md5_hash'    -> file with hashes.MD5 set
              'sha256_hash' -> file with hashes.SHA-256 set
            All SCOs include x_tf_* custom fields:
              x_tf_malware: malware family string
              x_tf_confidence: integer confidence score (0-100)
              x_tf_first_seen: ISO 8601 first-seen timestamp
              x_tf_last_seen: ISO 8601 last-seen timestamp (may be empty)
              x_tf_reporter: reporter identifier string
              x_tf_tags: list of tag strings

        Raises
        ------
        RateLimitError
            When the API returns 429.
        httpx.HTTPStatusError
            For unexpected 4xx/5xx responses.
        httpx.RequestError
            For network-level failures.
        """
        payload = {"query": "search_ioc", "search_term": target}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._API_URL,
                json=payload,
                headers={"Accept": "application/json"},
                timeout=TIMEOUT,
            )

            if response.status_code == 429:
                retry_header = response.headers.get("Retry-After")
                retry_after = int(retry_header) if retry_header else None
                raise RateLimitError(
                    "ThreatFox API rate limit exceeded.",
                    retry_after=retry_after,
                )

            response.raise_for_status()
            data = response.json()

        query_status = data.get("query_status", "")
        records = data.get("data") or []

        if not records or query_status == "no_results":
            logger.debug("ThreatFox %s: query_status=%s (no results)", target, query_status)
            return []

        results = []
        seen: set[str] = set()
        for record in records:
            ioc_value = record.get("ioc", "") or record.get("ioc_value", "")
            if not ioc_value or ioc_value in seen:
                continue
            seen.add(ioc_value)
            sco = _build_sco(ioc_value, record)
            if sco:
                results.append(sco)

        logger.debug("ThreatFox %s: found %d IOC records", target, len(results))
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_sco(ioc_value: str, record: dict[str, Any]) -> dict[str, Any] | None:
    """Construct the appropriate STIX 2.1 SCO dict from a ThreatFox IOC record.

    Parameters
    ----------
    ioc_value:
        The IOC value string from the ThreatFox record.
    record:
        One element from the ThreatFox API 'data' array.

    Returns
    -------
    dict or None
        A typed STIX 2.1 SCO dict with x_tf_* custom fields, or None if
        the ioc_type is unrecognised and no SCO can be constructed.
    """
    ioc_type = record.get("ioc_type", "")
    common = _build_common_fields(record)

    if ioc_type == "ip:port":
        # ioc_value is "IP:port" — split on last colon to handle IPv4
        ip = ioc_value.rsplit(":", 1)[0] if ":" in ioc_value else ioc_value
        port_str = ioc_value.rsplit(":", 1)[1] if ":" in ioc_value else ""
        sco: dict[str, Any] = {
            "type": "ipv4-addr",
            "id": f"ipv4-addr--{uuid.uuid5(_THREATFOX_NS, ioc_value)}",
            "value": ip,
            "x_tf_port": port_str,
        }
        sco.update(common)
        return sco

    if ioc_type == "url":
        sco = {
            "type": "url",
            "id": f"url--{uuid.uuid5(_THREATFOX_NS, ioc_value)}",
            "value": ioc_value,
        }
        sco.update(common)
        return sco

    if ioc_type == "domain":
        sco = {
            "type": "domain-name",
            "id": f"domain-name--{uuid.uuid5(_THREATFOX_NS, ioc_value)}",
            "value": ioc_value,
        }
        sco.update(common)
        return sco

    if ioc_type == "md5_hash":
        sco = {
            "type": "file",
            "id": f"file--{uuid.uuid5(_THREATFOX_NS, ioc_value)}",
            "hashes": {"MD5": ioc_value},
        }
        sco.update(common)
        return sco

    if ioc_type == "sha256_hash":
        sco = {
            "type": "file",
            "id": f"file--{uuid.uuid5(_THREATFOX_NS, ioc_value)}",
            "hashes": {"SHA-256": ioc_value},
        }
        sco.update(common)
        return sco

    # Unknown ioc_type — emit as a generic note/x-unknown SCO; log and skip
    logger.debug("ThreatFox: unrecognised ioc_type=%r for value=%r, skipping", ioc_type, ioc_value)
    return None


def _build_common_fields(record: dict[str, Any]) -> dict[str, Any]:
    """Build the x_tf_* custom fields common to all ThreatFox SCO types.

    Parameters
    ----------
    record:
        One element from the ThreatFox 'data' array.

    Returns
    -------
    dict
        x_tf_* custom fields ready to merge into a typed SCO dict.
    """
    tags = record.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    return {
        "x_tf_malware": record.get("malware", "") or record.get("malware_printable", ""),
        "x_tf_confidence": int(record.get("confidence_level", 0) or 0),
        "x_tf_first_seen": record.get("first_seen", "") or "",
        "x_tf_last_seen": record.get("last_seen", "") or "",
        "x_tf_reporter": record.get("reporter", "") or "",
        "x_tf_tags": list(tags),
    }
