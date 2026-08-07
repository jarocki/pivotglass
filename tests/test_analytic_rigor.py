"""Deterministic confidence review and contradiction-candidate contracts."""

from adversary_pursuit.core.analytic_rigor import (
    build_analytic_rigor,
    canonical_claim_value,
)


def _assertion(identifier: str, value: str) -> dict[str, object]:
    return {
        "id": identifier,
        "status": "active",
        "subject_ref": "ipv4-addr--example",
        "predicate": "active_window_days",
        "object_value": value,
    }


def test_value_and_nonoverlapping_interval_conflicts_are_review_candidates():
    snapshot = {
        "assertions": [
            _assertion("assertion-a", '{"min":1,"max":3,"unit":"days"}'),
            _assertion("assertion-b", '{"min":7,"max":9,"unit":"days"}'),
        ],
        "confidence": [],
        "contradictions": [],
    }

    first = build_analytic_rigor(snapshot)
    second = build_analytic_rigor(snapshot)
    candidate = first["contradiction_candidates"][0]

    assert first == second
    assert candidate["conflict_kind"] == "non_overlapping_interval"
    assert candidate["content_class"] == "method_derived_suggestion"
    assert "not contradictions" in first["policy"]["candidate_authority"]


def test_overlapping_or_different_unit_intervals_are_not_called_contradictions():
    snapshot = {
        "assertions": [
            _assertion("assertion-a", '{"min":1,"max":7,"unit":"days"}'),
            _assertion("assertion-b", '{"min":5,"max":9,"unit":"days"}'),
            _assertion("assertion-c", '{"min":20,"max":30,"unit":"hours"}'),
        ],
        "confidence": [],
        "contradictions": [],
    }
    assert build_analytic_rigor(snapshot)["contradiction_candidates"] == []


def test_existing_unresolved_pair_suppresses_duplicate_candidate():
    snapshot = {
        "assertions": [_assertion("assertion-a", "actor-a"), _assertion("assertion-b", "actor-b")],
        "confidence": [],
        "contradictions": [
            {
                "left_id": "assertion-b",
                "right_id": "assertion-a",
                "status": "unresolved",
            }
        ],
    }
    assert build_analytic_rigor(snapshot)["contradiction_candidates"] == []


def test_confidence_review_counts_dependence_groups_not_duplicate_sources():
    snapshot = {
        "assertions": [],
        "contradictions": [],
        "confidence": [
            {
                "id": "confidence-a",
                "target_kind": "hypothesis",
                "target_id": "hypothesis-a",
                "level": "high",
                "factors": {
                    "source_independence": {
                        "source_count": 4,
                        "dependence_group_count": 1,
                        "notes": "three feeds repeat one upstream report",
                    }
                },
            }
        ],
    }
    warnings = build_analytic_rigor(snapshot)["confidence_reviews"][0]["warnings"]
    assert {row["code"] for row in warnings} == {
        "dependent_sources",
        "insufficient_independent_groups",
    }
    assert "silently change" in build_analytic_rigor(snapshot)["policy"]["confidence_authority"]


def test_claim_value_is_canonical_but_plain_text_remains_available():
    assert canonical_claim_value('{ "unit": "days", "max": 3, "min": 1 }') == (
        '{"max":3,"min":1,"unit":"days"}'
    )
    assert canonical_claim_value("actor-a") == "actor-a"
