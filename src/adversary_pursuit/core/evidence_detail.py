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


def _indicator_value(item: dict[str, Any]) -> str:
    return str(item.get("value", item.get("x_indicator_value", item.get("name", "unavailable"))))


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


def _source_intelligence(item: dict[str, Any]) -> dict[str, Any] | None:
    """Project vendor enrichment into a compact, source-labelled summary."""
    source = str(item.get("x_ap_source_module", "")).lower()
    facts: list[dict[str, Any]] = []
    links: list[dict[str, str]] = []
    groups: list[dict[str, Any]] = []

    def fact(label: str, key: str) -> None:
        value = item.get(key)
        if value not in (None, "", [], {}):
            facts.append({"label": label, "value": _scrub(value, key)})

    def link(label: str, key: str) -> None:
        value = item.get(key)
        if isinstance(value, str) and value.startswith(("https://", "http://")):
            links.append({"label": label, "url": value})

    if "abuseipdb" in source or "x_abuse_confidence_score" in item:
        for label, key in (
            ("Abuse confidence", "x_abuse_confidence_score"),
            ("Total reports", "x_total_reports"),
            ("Last reported", "x_last_reported_at"),
            ("ISP", "x_isp"),
            ("Usage type", "x_usage_type"),
            ("Country", "x_country_code"),
            ("Whitelisted", "x_is_whitelisted"),
        ):
            fact(label, key)
        reports = item.get("x_recent_reports")
        if isinstance(reports, list) and reports:
            groups.append({"title": "Recent AbuseIP reports", "items": _scrub(reports)})
        return {
            "provider": "AbuseIPDB",
            "headline": "Recent IP reputation evidence",
            "facts": facts,
            "links": links,
            "groups": groups,
        }

    if "urlscan" in source or "x_scan_uuid" in item:
        for label, key in (
            ("Page title", "x_page_title"),
            ("HTTP status", "x_page_status"),
            ("Effective URL", "x_effective_url"),
            ("Page domain", "x_page_domain"),
            ("Page IP", "x_page_ip"),
            ("Server", "x_server"),
            ("Scan time", "x_scan_time"),
            ("Verdict", "x_verdict_summary"),
            ("Contacted resources", "x_contacted_counts"),
        ):
            fact(label, key)
        for label, key in (
            ("Open urlscan result", "x_result_url"),
            ("Open screenshot", "x_screenshot_url"),
            ("Open captured DOM", "x_dom_url"),
        ):
            link(label, key)
        contacted = item.get("x_contacted_urls")
        if isinstance(contacted, list) and contacted:
            groups.append({"title": "Contacted URLs", "items": _scrub(contacted)})
        return {
            "provider": "urlscan.io",
            "headline": "Rendered site scan",
            "facts": facts,
            "links": links,
            "groups": groups,
        }

    if "virustotal" in source or "x_last_analysis_date" in item:
        for label, key in (
            ("Malicious detections", "x_malicious"),
            ("Suspicious detections", "x_suspicious"),
            ("Reputation", "x_reputation"),
            ("Meaningful name", "x_meaningful_name"),
            ("File names", "x_file_names"),
            ("Type", "x_type_description"),
            ("Magic", "x_magic"),
            ("Size", "x_size"),
            ("Tags", "x_tags"),
            ("First submitted", "x_first_submission_date"),
            ("Last submitted", "x_last_submission_date"),
            ("Times submitted", "x_times_submitted"),
        ):
            fact(label, key)
        for title, key in (
            ("EXIF / file metadata", "x_exiftool"),
            ("Signature information", "x_signature_info"),
            ("Related files and infrastructure", "x_related_objects"),
        ):
            value = item.get(key)
            if value not in (None, "", [], {}):
                groups.append({"title": title, "items": _scrub(value, key)})
        related_links = item.get("x_related_links")
        if isinstance(related_links, list):
            for index, url in enumerate(related_links):
                if isinstance(url, str) and url.startswith(("https://", "http://")):
                    links.append({"label": f"Related data {index + 1}", "url": url})
        return {
            "provider": "VirusTotal",
            "headline": "Multi-engine file and relationship metadata",
            "facts": facts,
            "links": links,
            "groups": groups,
        }
    return None


def project_evidence(
    objects: Iterable[dict[str, Any]],
    identifier: str,
    relationships: Iterable[dict[str, Any]] = (),
    module_runs: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Project one stored STIX object into the shared evidence detail envelope."""
    object_list = list(objects)
    matched: dict[str, Any] | None = None
    for item in object_list:
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
    values = {
        str(item.get("id")): _indicator_value(item)
        for item in object_list
        if item.get("id")
    }
    related = []
    roles = []
    for relation in relationships:
        source, target = str(relation.get("source_ref", "")), str(relation.get("target_ref", ""))
        if stix_id not in {source, target}:
            continue
        other = target if source == stix_id else source
        verb = str(relation.get("relationship_type", "related-to"))
        related.append(
            {
                "direction": "outgoing" if source == stix_id else "incoming",
                "relationship": verb,
                "indicator": values.get(other, "unavailable"),
                "reference": evidence_ref(other) if other in values else None,
            }
        )
        lowered = verb.lower()
        if "resolves" in lowered:
            roles.append("DNS resolution source" if source == stix_id else "DNS resolution target")
        if any(word in lowered for word in ("command", "control", "communicat")):
            roles.append("communications infrastructure")
        if "hosts" in lowered:
            roles.append("hosting source" if source == stix_id else "hosted resource")
    declared_role = matched.get("x_ap_role") or matched.get("role") or matched.get("purpose")
    if declared_role:
        roles.insert(0, str(declared_role))
    original_query = matched.get("x_ap_original_query")
    breadcrumbs = []
    if original_query and str(original_query) != _indicator_value(matched):
        breadcrumbs.append({"indicator": str(original_query), "relationship": "investigated"})
    breadcrumbs.append(
        {
            "indicator": _indicator_value(matched),
            "relationship": "produced by " + str(matched.get("x_ap_source_module", "unavailable")),
        }
    )
    history = [
        {
            "module": run.get("module_name", "unavailable"),
            "target": run.get("target", "unavailable"),
            "timestamp": run.get("timestamp", "unavailable"),
            "result_count": run.get("result_count", 0),
        }
        for run in module_runs
        if str(run.get("target", "")) in {str(original_query or ""), _indicator_value(matched)}
        or str(run.get("module_name", "")) == str(matched.get("x_ap_source_module", ""))
    ]
    dossier_contributions = matched.get("x_ap_dossier_contributions", [])
    if not dossier_contributions:
        try:
            from adversary_pursuit.dossier.slot_inference import infer_dossier_state

            single_state = infer_dossier_state([matched])
            dossier_contributions = [
                {
                    "facet": slot_name.value,
                    "status": slot.status.value,
                    "evidence_count": slot.evidence_count,
                }
                for slot_name, slot in single_state.slots.items()
                if slot.evidence_count
            ]
        except (AttributeError, KeyError, TypeError, ValueError):
            dossier_contributions = []
    return {
        "reference": evidence_ref(stix_id),
        "stix_id": stix_id,
        "type": matched.get("type", "unavailable"),
        "value": _indicator_value(matched),
        "source_module": matched.get("x_ap_source_module", "unavailable"),
        "original_query": matched.get("x_ap_original_query", "unavailable"),
        "provenance": provenance,
        "normalized": normalized,
        "raw": _scrub(matched),
        "relationships": related or matched.get("x_ap_relationships", []),
        "purpose": list(dict.fromkeys(roles)) or ["unclassified observable"],
        "breadcrumbs": breadcrumbs,
        "history": history,
        "dossier_contributions": dossier_contributions,
        "source_intelligence": _source_intelligence(matched),
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
                "value": _indicator_value(item),
                "retrieved_at": item.get("x_ap_fetched_at", "unavailable"),
                "country": item.get("country")
                or item.get("country_code")
                or item.get("x_country_code"),
                "latitude": item.get("latitude") or item.get("x_latitude"),
                "longitude": item.get("longitude") or item.get("x_longitude"),
                "known_malware": bool(
                    item.get("malware")
                    or item.get("malicious")
                    or item.get("x_malware_family")
                    or item.get("x_ap_known_malware")
                ),
            }
        )
    return cards
