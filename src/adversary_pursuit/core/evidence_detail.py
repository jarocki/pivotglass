"""Deterministic, credential-safe evidence detail projections."""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

_SENSITIVE_PARTS = ("api_key", "apikey", "secret", "password", "token", "credential")
_PROVENANCE_FIELDS = {
    "x_ap_source_url": "source_url",
    "x_ap_api_version": "api_version",
    "x_ap_response_sha256": "response_sha256",
    "x_ap_fetched_at": "retrieved_at",
}


def evidence_ref(stix_id: str) -> str:
    """Return a compact session-visible reference derived from a STIX ID."""
    digest = hashlib.sha256(stix_id.encode("utf-8")).hexdigest()[:8]
    return f"ev-{digest}"


def _scrub(value: Any, key: str = "") -> Any:
    if any(part in key.lower() for part in _SENSITIVE_PARTS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _scrub(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub(item) for item in value)
    return value


def project_evidence(objects: Iterable[dict[str, Any]], identifier: str) -> dict[str, Any]:
    """Project one stored STIX object into the shared evidence detail envelope."""
    matched: dict[str, Any] | None = None
    for item in objects:
        stix_id = str(item.get("id", ""))
        if stix_id and identifier in {stix_id, evidence_ref(stix_id)}:
            matched = item
            break
    if matched is None:
        raise ValueError("unknown evidence reference")

    stix_id = str(matched["id"])
    provenance = {
        output: matched.get(field, "unavailable")
        for field, output in _PROVENANCE_FIELDS.items()
    }
    normalized = {
        key: _scrub(value, key)
        for key, value in matched.items()
        if key not in _PROVENANCE_FIELDS and not key.startswith("x_ap_")
    }
    return {
        "reference": evidence_ref(stix_id),
        "stix_id": stix_id,
        "type": matched.get("type", "unavailable"),
        "value": matched.get("value", matched.get("name", "unavailable")),
        "source_module": matched.get("x_ap_source_module", "unavailable"),
        "original_query": matched.get("x_ap_original_query", "unavailable"),
        "provenance": provenance,
        "normalized": normalized,
        "raw": _scrub(matched),
        "relationships": matched.get("x_ap_relationships", []),
        "dossier_contributions": matched.get("x_ap_dossier_contributions", []),
        "supporting_observations": matched.get("x_ap_supporting_observations", []),
        "conflicting_observations": matched.get("x_ap_conflicting_observations", []),
        "next_pivots": matched.get("x_ap_next_pivots", []),
    }


def list_evidence(objects: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return compact evidence cards without copying raw fields."""
    cards = []
    for item in objects:
        stix_id = str(item.get("id", ""))
        if not stix_id:
            continue
        cards.append(
            {
                "reference": evidence_ref(stix_id),
                "stix_id": stix_id,
                "type": item.get("type", "unknown"),
                "value": item.get("value", item.get("name", "unavailable")),
                "retrieved_at": item.get("x_ap_fetched_at", "unavailable"),
            }
        )
    return cards
