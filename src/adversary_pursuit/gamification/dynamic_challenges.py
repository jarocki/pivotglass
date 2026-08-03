"""Evidence-grounded challenges that adapt to the active pursuit.

The generator only reads public-reporting fields already collected into the
workspace.  It never asks a model to invent telemetry or a threat attribution.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from adversary_pursuit.core.graph import RelationshipGraph, persisted_relationships

_CONTEXT_FIELDS: tuple[tuple[str, str, str, str, str], ...] = (
    ("malware", "x_tf_malware", "Malware Thread", "malware-signature", "⌁"),
    ("malware", "x_mb_signature", "Malware Thread", "malware-signature", "⌁"),
    ("malware", "x_abuse_threat", "Malware Thread", "malware-signature", "⌁"),
    ("threat actor", "x_threat_actor", "Actor's Tell", "actor-mask", "◐"),
    ("campaign", "x_campaign", "Campaign Thread", "campaign-thread", "⟲"),
    ("infrastructure", "x_as_owner", "Infrastructure Cartographer", "infrastructure-tower", "⌂"),
    ("infrastructure", "x_org", "Infrastructure Cartographer", "infrastructure-tower", "⌂"),
    ("infrastructure", "x_registrar", "Infrastructure Cartographer", "infrastructure-tower", "⌂"),
)


def _stable_id(*parts: str) -> str:
    raw = "\0".join(parts).encode()
    return hashlib.sha256(raw).hexdigest()[:20]


def _safe_label(value: Any, limit: int = 72) -> str | None:
    if isinstance(value, list):
        value = next((item for item in value if isinstance(item, (str, int))), None)
    if not isinstance(value, (str, int)):
        return None
    label = " ".join(str(value).split())
    if not label or len(label) > 256:
        return None
    return label if len(label) <= limit else f"{label[: limit - 1]}…"


def _target_object(objects: list[dict], target: str | None) -> dict | None:
    if target:
        for item in reversed(objects):
            if target in {
                str(item.get("value", "")),
                str(item.get("name", "")),
                str(item.get("x_indicator_value", "")),
            }:
                return item
    return objects[-1] if objects else None


def _context_facts(observations: list[dict]) -> list[dict]:
    facts: dict[tuple[str, str], dict] = {}
    for observation in observations:
        blob = observation.get("observed_blob") or {}
        if not isinstance(blob, dict):
            continue
        for kind, field, title, artwork, glyph in _CONTEXT_FIELDS:
            label = _safe_label(blob.get(field))
            if label is None:
                continue
            key = (kind, label.casefold())
            fact = facts.setdefault(
                key,
                {
                    "kind": kind,
                    "value": label,
                    "title": title,
                    "artwork": artwork,
                    "glyph": glyph,
                    "evidence": [],
                    "sources": set(),
                },
            )
            dependence = observation.get("source_dependence_group")
            source_key = dependence or observation.get("source_id")
            fact["sources"].add(str(source_key))
            fact["evidence"].append(
                {
                    "observation_id": observation.get("id"),
                    "source": observation.get("source_module"),
                    "field": field,
                    "value": label,
                }
            )
    return list(facts.values())


def generate_hunt_challenges(workspace_mgr: Any, target: str | None = None) -> list[dict]:
    """Generate stable challenge definitions for the current evidence context."""
    objects = workspace_mgr.get_stix_objects()
    subject = _target_object(objects, target)
    if subject is None:
        return []
    subject_ref = str(subject.get("id", ""))
    subject_value = (
        _safe_label(
            subject.get("value", subject.get("name", subject.get("x_indicator_value", target)))
        )
        or "current target"
    )
    subject_type = str(subject.get("type", "indicator"))
    observations = workspace_mgr.get_observations(entity_ref=subject_ref)
    records: list[dict] = []

    def add(
        key: str,
        name: str,
        description: str,
        verification: dict,
        *,
        artwork: str,
        glyph: str,
        evidence_basis: list[dict] | None = None,
        points: int = 125,
    ) -> None:
        challenge_id = f"hunt-{_stable_id(subject_ref, key)}"
        records.append(
            {
                "id": challenge_id,
                "origin": "public-reporting",
                "subject_ref": subject_ref,
                "subject_type": subject_type,
                "subject_value": subject_value,
                "name": name,
                "description": description,
                "challenge_type": "discovery",
                "points": points,
                "verification": verification,
                "hints": [
                    "Use independent passive enrichment sources; inspect provenance before drawing a conclusion."
                ],
                "evidence_basis": evidence_basis or [],
                "badge_id": f"badge-{challenge_id}",
                "badge_name": name,
                "badge_description": f"Completed the {name} evidence challenge for {subject_value}.",
                "badge_rarity": "uncommon",
                "badge_artwork": artwork,
                "badge_glyph": glyph,
                "status": "active",
                "progress_current": 0,
                "progress_target": int(verification.get("minimum", 1)),
                "progress_label": "requirements met",
            }
        )

    add(
        "triangulate",
        "Independent Witnesses",
        f"Corroborate {subject_value} with two independent public-reporting sources.",
        {"type": "independent_sources", "minimum": 2, "subject_ref": subject_ref},
        artwork="crossbeam",
        glyph="✣",
        evidence_basis=[
            {"observation_id": row.get("id"), "source": row.get("source_module")}
            for row in observations
        ],
        points=175,
    )
    add(
        "connections",
        "Constellation Builder",
        f"Establish three evidence-backed connections around {subject_value}.",
        {"type": "connection_count", "minimum": 3, "subject_ref": subject_ref},
        artwork="constellation",
        glyph="✦",
        points=200,
    )

    facts = _context_facts(observations)
    if not facts:
        add(
            "public-context",
            "Public Record",
            f"Find one sourced public-reporting context fact about {subject_value}.",
            {"type": "public_context", "minimum": 1, "subject_ref": subject_ref},
            artwork="public-record",
            glyph="◈",
        )
    for fact in facts[:4]:
        key = f"{fact['kind']}:{fact['value'].casefold()}"
        add(
            key,
            str(fact["title"]),
            f"Corroborate the reported {fact['kind']} context “{fact['value']}” with a second independent source.",
            {
                "type": "context_sources",
                "minimum": 2,
                "subject_ref": subject_ref,
                "kind": fact["kind"],
                "value": fact["value"],
            },
            artwork=str(fact["artwork"]),
            glyph=str(fact["glyph"]),
            evidence_basis=list(fact["evidence"]),
            points=225,
        )
    return records


def evaluate_hunt_challenge(workspace_mgr: Any, record: dict) -> tuple[int, int, str]:
    """Evaluate one persisted challenge from authoritative workspace records."""
    verification = record.get("verification") or {}
    kind = verification.get("type")
    target = max(1, int(verification.get("minimum", 1)))
    subject_ref = str(verification.get("subject_ref", record.get("subject_ref", "")))
    observations = workspace_mgr.get_observations(entity_ref=subject_ref)
    if kind == "independent_sources":
        sources = {
            str(row.get("source_dependence_group") or row.get("source_id")) for row in observations
        }
        return len(sources), target, "independent sources"
    if kind == "connection_count":
        graph = RelationshipGraph()
        graph.build_from_workspace(
            workspace_mgr.get_stix_objects(), persisted_relationships(workspace_mgr)
        )
        edges = graph.to_dict().get("edges", [])
        count = sum(
            1 for edge in edges if subject_ref in {str(edge.get("source")), str(edge.get("target"))}
        )
        return count, target, "evidence-backed connections"
    facts = _context_facts(observations)
    if kind == "public_context":
        return len(facts), target, "public-report context facts"
    if kind == "context_sources":
        expected_kind = str(verification.get("kind", ""))
        expected_value = str(verification.get("value", "")).casefold()
        for fact in facts:
            if fact["kind"] == expected_kind and fact["value"].casefold() == expected_value:
                return len(fact["sources"]), target, "independent sources"
    return 0, target, "requirements met"


def refresh_hunt_challenges(workspace_mgr: Any, target: str | None = None) -> list[dict]:
    """Generate, persist, evaluate, and award current hunt challenges."""
    generated = generate_hunt_challenges(workspace_mgr, target)
    workspace_mgr.upsert_hunt_challenges(generated)
    for record in workspace_mgr.list_hunt_challenges():
        if record["status"] != "active":
            continue
        current, goal, label = evaluate_hunt_challenge(workspace_mgr, record)
        workspace_mgr.update_hunt_challenge_progress(record["id"], current, goal, label)
        if current >= goal:
            workspace_mgr.complete_hunt_challenge(record["id"])
    return workspace_mgr.list_hunt_challenges()


def challenge_snapshot_digest(records: list[dict]) -> str:
    """Return a deterministic digest useful in audits and tests."""
    payload = json.dumps(records, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
