from __future__ import annotations

from copy import deepcopy

from adversary_pursuit.core.pursuit_brief import POLICY_ID, build_pursuit_brief


def _analysis(**overrides):
    value = {
        "investigations": [],
        "lifecycle_items": [],
        "questions": [],
        "hypotheses": [],
        "method_runs": [],
        "contradictions": [],
        "enrichment_queue": [],
        "information_requirements": {"requirements": [], "suggestions": []},
    }
    value.update(overrides)
    return value


def _slots(*, filled=0, partial=0):
    rows = []
    for index in range(9):
        status = "filled" if index < filled else "partial" if index < filled + partial else "empty"
        rows.append({"name": f"slot_{index}", "status": status, "evidence_count": index})
    return rows


def _build(analysis=None, slots=None, investigations=None, frameworks=None, objects=0):
    return build_pursuit_brief(
        analysis=analysis or _analysis(),
        dossier_slots=slots or _slots(),
        framework_counts=frameworks or {},
        investigations=investigations or [],
        object_count=objects,
        latest_target=None,
    )


def test_empty_workspace_prompts_for_a_question_without_running_work():
    brief = _build()

    assert brief["policy"]["id"] == POLICY_ID
    assert brief["next_action"]["id"] == "frame_question"
    assert brief["next_action"]["permission"] == "analyst_record"
    assert brief["next_action"]["auto_eligible"] is False
    assert brief["next_action"]["confirmation_required"] is False
    assert brief["progress"][0] == {
        "id": "evidence_coverage",
        "label": "Evidence coverage",
        "current": 0,
        "total": 9,
        "detail": "0 filled · 0 partial",
    }


def test_high_materiality_contradiction_outranks_other_gaps():
    analysis = _analysis(
        investigations=[{"id": "inv-1", "title": "Who controls it?", "status": "analyzing"}],
        questions=[{"id": "q-1", "text": "Who controls it?"}],
        hypotheses=[
            {"id": "h-1", "status": "proposed"},
            {"id": "h-2", "status": "proposed"},
        ],
        contradictions=[
            {
                "id": "c-1",
                "status": "unresolved",
                "materiality": "high",
                "resolution_required": "Obtain contemporaneous allocation records.",
            }
        ],
    )

    brief = _build(analysis=analysis, objects=3)

    assert brief["next_action"]["id"] == "resolve_contradiction"
    assert brief["next_action"]["category"] == "required"
    assert brief["next_action"]["basis"] == [{"kind": "contradiction", "id": "c-1"}]
    assert brief["open_work"]["contradictions"] == 1


def test_active_enrichment_is_current_work_but_failure_takes_priority():
    investigations = [
        {
            "investigation_id": "run-1",
            "lifecycle": "running",
            "events": [
                {
                    "event_id": "run-1:1",
                    "event_class": "source_fault",
                    "lifecycle": "failed",
                    "reason": "provider timeout",
                    "next_action": "Retry after checking service status.",
                }
            ],
        }
    ]

    brief = _build(investigations=investigations)

    assert brief["next_action"]["id"] == "review_failure"
    assert brief["next_action"]["rationale"] == "Retry after checking service status."
    assert brief["open_work"]["failed_enrichments"] == 1
    assert brief["now"]["stage"] == "Enrich"


def test_progress_measures_remain_separate_and_truthful():
    analysis = _analysis(
        investigations=[{"id": "inv-1", "title": "Test", "status": "collecting"}],
        questions=[{"id": "q-1", "text": "What changed?"}],
        lifecycle_items=[
            {"id": "life-1", "investigation_id": "inv-1", "item_type": "question"},
            {"id": "life-2", "investigation_id": "inv-1", "item_type": "hypothesis"},
            {"id": "life-3", "investigation_id": "inv-1", "item_type": "stop_condition"},
        ],
        hypotheses=[{"id": "h-1", "status": "proposed"}],
    )
    original = deepcopy(analysis)

    brief = _build(analysis=analysis, slots=_slots(filled=2, partial=3), objects=7)

    assert analysis == original
    progress = {row["id"]: row for row in brief["progress"]}
    assert progress["evidence_coverage"]["current"] == 5
    assert progress["evidence_coverage"]["detail"] == "2 filled · 3 partial"
    assert progress["scientific_method"]["current"] == 3
    assert "overall_score" not in brief
    assert brief["next_action"]["id"] == "add_competing_hypothesis"


def test_pending_framework_mapping_requires_human_review():
    analysis = _analysis(
        investigations=[{"id": "inv-1", "title": "Test", "status": "analyzing"}],
        questions=[{"id": "q-1", "text": "What behavior is present?"}],
    )

    brief = _build(analysis=analysis, frameworks={"attack": {"proposed": 2}})

    assert brief["next_action"]["id"] == "review_proposal"
    assert brief["next_action"]["permission"] == "review_only"
    assert brief["open_work"]["pending_reviews"] == 2


def test_current_investigation_does_not_borrow_another_questions_hypotheses():
    analysis = _analysis(
        investigations=[
            {
                "id": "inv-old",
                "title": "Old investigation",
                "status": "concluded",
                "primary_question_id": "q-old",
            },
            {
                "id": "inv-current",
                "title": "Current investigation",
                "status": "framing",
                "primary_question_id": "q-current",
            },
        ],
        lifecycle_items=[
            {
                "id": "life-current",
                "investigation_id": "inv-current",
                "item_type": "question",
                "record_kind": "question",
                "record_id": "q-current",
            }
        ],
        questions=[
            {"id": "q-old", "text": "Who controlled the old cluster?"},
            {"id": "q-current", "text": "What changed in the current cluster?"},
        ],
        hypotheses=[
            {"id": "h-old-1", "question_id": "q-old", "status": "proposed"},
            {"id": "h-old-2", "question_id": "q-old", "status": "proposed"},
        ],
    )

    brief = _build(analysis=analysis)

    assert brief["subject"]["question"] == "What changed in the current cluster?"
    assert brief["next_action"]["id"] == "add_competing_hypothesis"
