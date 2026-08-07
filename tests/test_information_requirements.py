"""Deterministic priority-intelligence-requirement contracts."""

from __future__ import annotations

import json

import pytest

from adversary_pursuit.core.analytic_commands import execute_analysis_command
from adversary_pursuit.core.analytic_ledger import (
    AnalyticLedger,
    AssertionType,
    AuthorKind,
    LifecycleItemType,
    Materiality,
)
from adversary_pursuit.core.command_completion import command_completions
from adversary_pursuit.core.dossier_report import generate_dossier_report
from adversary_pursuit.core.information_requirements import (
    POLICY_ID,
    build_information_requirements,
    information_value,
    validate_requirement_criteria,
)
from adversary_pursuit.core.workspace import WorkspaceManager


def _workspace(tmp_path) -> WorkspaceManager:
    manager = WorkspaceManager(tmp_path)
    manager.create("case")
    manager.switch("case")
    return manager


def _criteria(**overrides):
    values = {
        "decision_impact": 0,
        "discriminating_power": 0,
        "time_sensitivity": 0,
        "feasibility": 0,
    }
    values.update(overrides)
    return values


def test_information_value_scores_only_declared_factors():
    score, contributions = information_value(
        _criteria(
            decision_impact=4,
            discriminating_power=2,
            time_sensitivity=1,
            feasibility=4,
        )
    )

    assert score == 70
    assert contributions == {
        "decision_impact": 30,
        "discriminating_power": 15,
        "time_sensitivity": 5,
        "feasibility": 20,
    }
    assert information_value({})[0] == 0
    with pytest.raises(ValueError, match="between 0 and 4"):
        validate_requirement_criteria(_criteria(decision_impact=5))
    with pytest.raises(ValueError, match="must be a number"):
        validate_requirement_criteria(_criteria(feasibility="easy"))


def test_analyst_priority_is_visible_ranking_authority(tmp_path):
    manager = _workspace(tmp_path)
    ledger = AnalyticLedger(manager)
    question_id = ledger.create_question("Which explanation best fits the activity?")
    investigation_id = ledger.active_investigation()["id"]
    ledger.create_hypothesis(question_id, "A shared provider explains the overlap.")
    first_id = ledger.add_lifecycle_item(
        investigation_id,
        LifecycleItemType.COLLECTION_REQUIREMENT,
        "Obtain contemporaneous allocation records.",
        criteria=_criteria(
            decision_impact=4,
            discriminating_power=2,
            time_sensitivity=1,
            feasibility=4,
        ),
    )
    second_id = ledger.add_lifecycle_item(
        investigation_id,
        LifecycleItemType.COLLECTION_REQUIREMENT,
        "Compare certificate issuance patterns.",
        criteria=_criteria(
            decision_impact=4,
            discriminating_power=4,
            time_sensitivity=4,
            feasibility=4,
        ),
    )

    ledger.prioritize_information_requirement(second_id, 25)
    ranked = build_information_requirements(ledger.snapshot())
    assert ranked["policy"]["id"] == POLICY_ID
    assert [row["id"] for row in ranked["requirements"]] == [first_id, second_id]
    assert ranked["requirements"][0]["priority_source"] == "deterministic"
    assert ranked["requirements"][0]["rank_score"] == 70
    assert ranked["requirements"][1]["priority_source"] == "analyst"
    assert ranked["requirements"][1]["rank_score"] == 25

    ledger.prioritize_information_requirement(second_id, 90)
    assert build_information_requirements(ledger.snapshot())["requirements"][0]["id"] == second_id
    malformed_id = ledger.add_lifecycle_item(
        investigation_id,
        LifecycleItemType.COLLECTION_REQUIREMENT,
        "Legacy malformed requirement.",
        criteria={"decision_impact": "unknown"},
    )
    malformed = next(
        row
        for row in build_information_requirements(ledger.snapshot())["requirements"]
        if row["id"] == malformed_id
    )
    assert malformed["information_value"] == 0
    assert "must be a number" in malformed["scoring_error"]
    with pytest.raises(ValueError, match="Only an explicit human action"):
        ledger.prioritize_information_requirement(
            first_id,
            100,
            decided_by=AuthorKind.MODEL,
        )


def test_next_information_suggestions_are_sourced_and_not_persisted(tmp_path):
    manager = _workspace(tmp_path)
    ledger = AnalyticLedger(manager)
    question_id = ledger.create_question("Who controls the infrastructure?")
    hypothesis_id = ledger.create_hypothesis(question_id, "One operator controls it.")
    left_id = ledger.create_assertion(
        "The address was dedicated.",
        assertion_type=AssertionType.JUDGMENT,
    )
    right_id = ledger.create_assertion(
        "The address was shared.",
        assertion_type=AssertionType.JUDGMENT,
    )
    contradiction_id = ledger.record_contradiction(
        left_kind="assertion",
        left_id=left_id,
        right_kind="assertion",
        right_id=right_id,
        summary="Tenancy assessments conflict.",
        resolution_required="Obtain contemporaneous provider allocation records.",
        materiality=Materiality.HIGH,
    )

    before = ledger.snapshot()
    ranked = build_information_requirements(before)
    assert ranked["requirements"] == []
    assert ranked["suggestions"][0]["suggestion_type"] == "contradiction_resolution"
    assert ranked["suggestions"][0]["score"] == 95
    assert ranked["suggestions"][0]["source_refs"] == [
        {"kind": "contradiction", "id": contradiction_id}
    ]
    hypothesis_suggestion = next(
        row for row in ranked["suggestions"] if row["suggestion_type"] == "hypothesis_discrimination"
    )
    assert hypothesis_suggestion["source_refs"] == [
        {"kind": "hypothesis", "id": hypothesis_id}
    ]
    assert hypothesis_suggestion["content_class"] == "method_derived_suggestion"
    assert ledger.snapshot()["lifecycle_items"] == before["lifecycle_items"]

    investigation_id = ledger.active_investigation()["id"]
    ledger.add_lifecycle_item(
        investigation_id,
        LifecycleItemType.COLLECTION_REQUIREMENT,
        hypothesis_suggestion["statement"],
        criteria=hypothesis_suggestion["criteria"],
    )
    after_adoption = build_information_requirements(ledger.snapshot())
    assert hypothesis_suggestion["id"] not in {
        row["id"] for row in after_adoption["suggestions"]
    }


def test_requirement_commands_and_completions_share_one_authority(tmp_path):
    manager = _workspace(tmp_path)
    execute_analysis_command(("question", "What", "should", "we", "collect", "next?"), manager)
    criteria = _criteria(
        decision_impact=4,
        discriminating_power=3,
        time_sensitivity=2,
        feasibility=3,
    )
    result = execute_analysis_command(
        (
            "requirement",
            "Obtain",
            "an",
            "independent",
            "certificate",
            "history",
            "|",
            json.dumps(criteria),
        ),
        manager,
    )
    item_id = result["data"]["item_id"]
    execute_analysis_command(("prioritize", item_id, "75"), manager)
    priorities = execute_analysis_command(("priorities",), manager)["data"]

    assert priorities["requirements"][0]["statement"] == (
        "Obtain an independent certificate history"
    )
    assert priorities["requirements"][0]["analyst_priority"] == 75
    assert "analysis priorities" in command_completions("analysis pr")
    assert "analysis prioritize " in command_completions("analysis pr")
    assert "analysis requirement " in command_completions("analysis req")
    report = generate_dossier_report(manager)
    assert "Priority Intelligence Requirements and Next Best Information" in report
    assert "Obtain an independent certificate history" in report
    assert "75/100" in report
