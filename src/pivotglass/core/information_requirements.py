"""Deterministic priority intelligence requirement advisor.

This module ranks persisted collection requirements and derives bounded
next-best-information suggestions from the analytic ledger.  Suggestions are
method output, not evidence, and never become authoritative records without an
explicit analyst action.

@decision DEC-INFORMATION-REQUIREMENTS-001
@title Human priority outranks deterministic information-value scoring
@status accepted
@rationale Analysts own investigation purpose and priorities. When an analyst
           supplies an explicit 1-100 priority it is the ranking authority.
           Otherwise Pivotglass applies a visible, versioned four-factor policy
           using only factors the analyst recorded; absent factors remain zero.
"""

from __future__ import annotations

import hashlib
from typing import Any

POLICY_ID = "pivotglass-information-value-v1"
FACTOR_WEIGHTS: dict[str, int] = {
    "decision_impact": 30,
    "discriminating_power": 30,
    "time_sensitivity": 20,
    "feasibility": 20,
}
MATERIALITY_SCORES = {"high": 95, "medium": 80, "low": 65}


def validate_requirement_criteria(criteria: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the transparent information-value factors."""

    if not isinstance(criteria, dict):
        raise ValueError("Requirement criteria must be a JSON object.")
    normalized: dict[str, Any] = {}
    for name in FACTOR_WEIGHTS:
        value = criteria.get(name, 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Requirement factor {name} must be a number from 0 to 4.")
        if value < 0 or value > 4:
            raise ValueError(f"Requirement factor {name} must be between 0 and 4.")
        normalized[name] = float(value)
    if "addresses" in criteria:
        addresses = criteria["addresses"]
        if not isinstance(addresses, list) or not all(isinstance(item, dict) for item in addresses):
            raise ValueError("Requirement addresses must be a list of record references.")
        normalized["addresses"] = addresses
    if "notes" in criteria:
        normalized["notes"] = str(criteria["notes"]).strip()
    return normalized


def information_value(criteria: dict[str, Any]) -> tuple[int, dict[str, int]]:
    """Return the 0-100 score and exact weighted contribution by factor."""

    normalized = validate_requirement_criteria(criteria)
    contributions = {
        name: round((float(normalized[name]) / 4.0) * weight)
        for name, weight in FACTOR_WEIGHTS.items()
    }
    return sum(contributions.values()), contributions


def build_information_requirements(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Rank persisted requirements and derive non-authoritative suggestions."""

    investigations = list(snapshot.get("investigations", []))
    active = next(
        (
            row
            for row in reversed(investigations)
            if row.get("status") not in {"concluded", "suspended"}
        ),
        investigations[-1] if investigations else None,
    )
    investigation_id = str(active["id"]) if active else None
    lifecycle = [
        row
        for row in snapshot.get("lifecycle_items", [])
        if investigation_id is None or row.get("investigation_id") == investigation_id
    ]

    requirements: list[dict[str, Any]] = []
    for row in lifecycle:
        if row.get("item_type") != "collection_requirement":
            continue
        raw_criteria = row.get("criteria") if isinstance(row.get("criteria"), dict) else {}
        scoring_error = None
        try:
            score, contributions = information_value(raw_criteria)
        except ValueError as exc:
            score = 0
            contributions = {name: 0 for name in FACTOR_WEIGHTS}
            scoring_error = str(exc)
        analyst_priority = _bounded_priority(row.get("priority", 0))
        requirements.append(
            {
                "id": str(row["id"]),
                "statement": str(row.get("statement") or ""),
                "status": str(row.get("status") or "open"),
                "analyst_priority": analyst_priority,
                "information_value": score,
                "rank_score": analyst_priority or score,
                "priority_source": "analyst" if analyst_priority else "deterministic",
                "criteria": raw_criteria,
                "contributions": contributions,
                "scoring_error": scoring_error,
                "evidence_refs": list(row.get("evidence_refs") or []),
                "analyst_disposition": str(row.get("analyst_disposition") or "accepted"),
            }
        )
    requirements.sort(
        key=lambda row: (
            row["status"] not in {"open", "deferred"},
            -row["rank_score"],
            row["statement"].casefold(),
            row["id"],
        )
    )
    for index, row in enumerate(requirements, start=1):
        row["rank"] = index

    suggestions = _derive_suggestions(snapshot, lifecycle)
    return {
        "policy": {
            "id": POLICY_ID,
            "factor_scale": "0-4",
            "weights": FACTOR_WEIGHTS,
            "missing_factor_behavior": "zero; never inferred",
            "human_authority": "An explicit analyst priority from 1 to 100 controls rank.",
        },
        "investigation_id": investigation_id,
        "requirements": requirements,
        "suggestions": suggestions,
    }


def _derive_suggestions(
    snapshot: dict[str, Any],
    lifecycle: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    recorded_requirements = [
        row
        for row in lifecycle
        if row.get("item_type") == "collection_requirement"
        and row.get("status") not in {"satisfied", "resolved"}
    ]
    recorded_statements = {
        str(row.get("statement") or "").strip().casefold() for row in recorded_requirements
    }
    addressed_records = {
        (str(ref.get("kind")), str(ref.get("id")))
        for row in recorded_requirements
        for ref in (
            row.get("criteria", {}).get("addresses", [])
            if isinstance(row.get("criteria"), dict)
            else []
        )
        if isinstance(ref, dict) and ref.get("kind") and ref.get("id")
    }
    open_contradictions = [
        row for row in snapshot.get("contradictions", []) if row.get("status") == "unresolved"
    ]
    for row in open_contradictions:
        source_ref = ("contradiction", str(row["id"]))
        if source_ref in addressed_records:
            continue
        materiality = str(row.get("materiality") or "medium")
        score = MATERIALITY_SCORES.get(materiality, 80)
        criteria = {
            "decision_impact": 4 if materiality == "high" else 3,
            "discriminating_power": 4,
            "time_sensitivity": 2,
            "feasibility": 2,
            "addresses": [{"kind": "contradiction", "id": str(row["id"])}],
        }
        suggestions.append(
            _suggestion(
                "contradiction_resolution",
                str(row.get("resolution_required") or "Resolve the recorded contradiction."),
                score,
                "Resolving an explicit contradiction can change the analytic judgment.",
                [{"kind": "contradiction", "id": str(row["id"])}],
                criteria=criteria,
                adoptable=True,
            )
        )

    evidence_links = list(snapshot.get("evidence_links", []))
    for row in snapshot.get("hypotheses", []):
        if row.get("status") in {"rejected", "suspended"}:
            continue
        hypothesis_id = str(row["id"])
        if ("hypothesis", hypothesis_id) in addressed_records:
            continue
        links = [
            link
            for link in evidence_links
            if link.get("target_kind") == "hypothesis"
            and str(link.get("target_id")) == hypothesis_id
        ]
        if links:
            continue
        statement = str(row.get("statement") or "the active hypothesis")
        suggestions.append(
            _suggestion(
                "hypothesis_discrimination",
                f"Seek independently sourced evidence that could support or contradict: {statement}",
                78,
                "The hypothesis has no explicitly linked supporting or contradicting evidence.",
                [{"kind": "hypothesis", "id": hypothesis_id}],
                criteria={
                    "decision_impact": 3,
                    "discriminating_power": 4,
                    "time_sensitivity": 1,
                    "feasibility": 2,
                    "addresses": [{"kind": "hypothesis", "id": hypothesis_id}],
                },
                adoptable=True,
            )
        )

    for row in lifecycle:
        if row.get("item_type") != "knowledge_gap" or row.get("status") != "open":
            continue
        if ("lifecycle_item", str(row["id"])) in addressed_records:
            continue
        suggestions.append(
            _suggestion(
                "knowledge_gap",
                f"Resolve the recorded intelligence gap: {row.get('statement') or 'unspecified gap'}",
                _bounded_priority(row.get("priority")) or 60,
                "The analyst explicitly recorded this unresolved gap.",
                [{"kind": "lifecycle_item", "id": str(row["id"])}],
                criteria={
                    "decision_impact": 3,
                    "discriminating_power": 2,
                    "time_sensitivity": 1,
                    "feasibility": 2,
                    "addresses": [{"kind": "lifecycle_item", "id": str(row["id"])}],
                },
                adoptable=True,
            )
        )

    active_hypotheses = [
        row
        for row in snapshot.get("hypotheses", [])
        if row.get("status") not in {"rejected", "suspended"}
    ]
    if snapshot.get("questions") and len(active_hypotheses) < 2:
        suggestions.append(
            _suggestion(
                "analytic_safeguard",
                "Develop at least two credible competing explanations before selecting a leading hypothesis.",
                85,
                "A single explanation cannot be compared for relative consistency.",
                [],
                criteria=None,
                adoptable=False,
            )
        )
    open_requirements = [
        row for row in lifecycle if row.get("item_type") == "collection_requirement" and row.get("status") == "open"
    ]
    has_stop = any(
        row.get("item_type") == "stop_condition" and row.get("status") == "open"
        for row in lifecycle
    )
    if open_requirements and not has_stop:
        suggestions.append(
            _suggestion(
                "analytic_safeguard",
                "Define when collection should stop before expanding the investigation.",
                72,
                "Open collection requirements have no recorded stop condition.",
                [],
                criteria=None,
                adoptable=False,
            )
        )

    unique = {
        row["id"]: row
        for row in suggestions
        if row["statement"].strip().casefold() not in recorded_statements
    }
    return sorted(
        unique.values(),
        key=lambda row: (-row["score"], row["statement"].casefold(), row["id"]),
    )[:8]


def _suggestion(
    suggestion_type: str,
    statement: str,
    score: int,
    rationale: str,
    source_refs: list[dict[str, str]],
    *,
    criteria: dict[str, Any] | None,
    adoptable: bool,
) -> dict[str, Any]:
    basis = "|".join(
        [suggestion_type, statement, *(f"{ref['kind']}:{ref['id']}" for ref in source_refs)]
    )
    return {
        "id": f"suggestion-{hashlib.sha256(basis.encode()).hexdigest()[:16]}",
        "suggestion_type": suggestion_type,
        "statement": statement,
        "score": score,
        "rationale": rationale,
        "source_refs": source_refs,
        "criteria": criteria,
        "adoptable": adoptable,
        "content_class": "method_derived_suggestion",
    }


def _bounded_priority(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, number))
