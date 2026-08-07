"""Deterministic helpers for confidence review and contradiction discovery.

These helpers do not create analytic facts or mutate the ledger. They expose
reviewable warnings and candidate conflicts from fields the analyst explicitly
recorded. Persisting a contradiction remains a separate human action.
"""

from __future__ import annotations

import hashlib
import json
from itertools import combinations
from typing import Any


def canonical_claim_value(value: str) -> str:
    """Return stable text for a scalar or JSON interval/value claim."""

    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Structured claim value must not be empty.")
    try:
        decoded = json.loads(cleaned)
    except json.JSONDecodeError:
        return cleaned
    if decoded is None or isinstance(decoded, (dict, list)) and not decoded:
        raise ValueError("Structured claim value must not be empty.")
    return json.dumps(decoded, sort_keys=True, separators=(",", ":"))


def build_analytic_rigor(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Project review warnings and unpersisted contradiction candidates."""

    return {
        "policy": {
            "id": "analytic-rigor-v1",
            "candidate_authority": (
                "Candidates are deterministic review prompts, not contradictions, until an "
                "analyst records one."
            ),
            "confidence_authority": (
                "Warnings expose source dependence but do not silently change an analyst's "
                "recorded confidence level."
            ),
        },
        "contradiction_candidates": _contradiction_candidates(snapshot),
        "confidence_reviews": [
            {
                "assessment_id": str(row.get("id") or ""),
                "target_kind": str(row.get("target_kind") or ""),
                "target_id": str(row.get("target_id") or ""),
                "level": str(row.get("level") or ""),
                "warnings": _confidence_warnings(row),
            }
            for row in snapshot.get("confidence", [])
        ],
    }


def _contradiction_candidates(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    assertions = [
        row
        for row in snapshot.get("assertions", [])
        if row.get("subject_ref")
        and row.get("predicate")
        and row.get("object_value") not in {None, ""}
        and row.get("status") not in {"rejected", "superseded"}
    ]
    recorded_pairs = {
        frozenset((str(row.get("left_id")), str(row.get("right_id"))))
        for row in snapshot.get("contradictions", [])
        if row.get("status") == "unresolved"
    }
    candidates: list[dict[str, Any]] = []
    for left, right in combinations(assertions, 2):
        if left["subject_ref"] != right["subject_ref"] or left["predicate"] != right["predicate"]:
            continue
        pair = frozenset((str(left["id"]), str(right["id"])))
        if pair in recorded_pairs:
            continue
        conflict_kind = _conflict_kind(left["object_value"], right["object_value"])
        if conflict_kind is None:
            continue
        subject = str(left["subject_ref"])
        predicate = str(left["predicate"])
        left_value = str(left["object_value"])
        right_value = str(right["object_value"])
        digest = hashlib.sha256(
            "\0".join(sorted(pair)).encode("utf-8")
        ).hexdigest()[:16]
        candidates.append(
            {
                "id": f"conflict-candidate-{digest}",
                "content_class": "method_derived_suggestion",
                "conflict_kind": conflict_kind,
                "left_kind": "assertion",
                "left_id": str(left["id"]),
                "right_kind": "assertion",
                "right_id": str(right["id"]),
                "subject_ref": subject,
                "predicate": predicate,
                "left_value": left_value,
                "right_value": right_value,
                "summary": (
                    f"Recorded claims disagree about {predicate} for {subject}: "
                    f"{left_value} versus {right_value}."
                ),
                "resolution_required": (
                    f"Obtain source-backed {predicate} evidence for the same observation "
                    "interval and document whether the sources are independent."
                ),
                "materiality": "medium",
            }
        )
    return sorted(candidates, key=lambda row: (row["subject_ref"], row["predicate"], row["id"]))


def _decode(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value.strip()


def _interval(value: Any) -> tuple[float, float, str | None] | None:
    decoded = _decode(value)
    if not isinstance(decoded, dict):
        return None
    lower = decoded.get("min")
    upper = decoded.get("max")
    if isinstance(lower, bool) or isinstance(upper, bool):
        return None
    if not isinstance(lower, (int, float)) or not isinstance(upper, (int, float)):
        return None
    if lower > upper:
        return None
    unit = decoded.get("unit")
    return float(lower), float(upper), str(unit) if unit is not None else None


def _conflict_kind(left: Any, right: Any) -> str | None:
    left_interval = _interval(left)
    right_interval = _interval(right)
    if left_interval is not None or right_interval is not None:
        if left_interval is None or right_interval is None:
            return None
        left_min, left_max, left_unit = left_interval
        right_min, right_max, right_unit = right_interval
        if left_unit != right_unit:
            return None
        return "non_overlapping_interval" if left_max < right_min or right_max < left_min else None
    left_value = _decode(left)
    right_value = _decode(right)
    if isinstance(left_value, (dict, list)) or isinstance(right_value, (dict, list)):
        return None
    return "value_mismatch" if left_value != right_value else None


def _confidence_warnings(assessment: dict[str, Any]) -> list[dict[str, str]]:
    level = str(assessment.get("level") or "").casefold()
    factors = assessment.get("factors") if isinstance(assessment.get("factors"), dict) else {}
    independence = factors.get("source_independence")
    warnings: list[dict[str, str]] = []
    if isinstance(independence, dict):
        source_count = _nonnegative_int(independence.get("source_count"))
        group_count = _nonnegative_int(independence.get("dependence_group_count"))
        if source_count is not None and group_count is not None and group_count < source_count:
            warnings.append(
                {
                    "code": "dependent_sources",
                    "message": (
                        f"{source_count} cited sources collapse to {group_count} independent "
                        "dependence group(s); duplicate reporting is not corroboration."
                    ),
                }
            )
        if level in {"moderate", "high"} and group_count is not None and group_count < 2:
            warnings.append(
                {
                    "code": "insufficient_independent_groups",
                    "message": (
                        f"{level.title()} confidence is recorded with fewer than two independent "
                        "source groups. Review the level or explain the non-source basis."
                    ),
                }
            )
    elif isinstance(independence, str):
        normalized = independence.casefold()
        signals_dependence = any(
            marker in normalized
            for marker in ("one dependence group", "single dependence group", "dependent source")
        )
        if signals_dependence and level in {"moderate", "high"}:
            warnings.append(
                {
                    "code": "legacy_dependence_warning",
                    "message": (
                        f"{level.title()} confidence is recorded while the source-independence "
                        "factor describes dependent or single-group sourcing."
                    ),
                }
            )
    return warnings


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value
