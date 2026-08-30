"""Deterministic investigation-orchestration projection for Pivotglass.

The Pursuit Brief is a read-only workflow lens over existing authorities.  It
does not create evidence, perform enrichment, accept an analytic proposal, or
change investigation state.  Its only policy decision is which already-known
piece of work to show first.

@decision DEC-PURSUIT-BRIEF-001
@title One deterministic next action may summarize, but never replace, source authorities
@status accepted
@rationale Analysts should not have to mentally merge enrichment state,
           scientific-method progress, contradictions, framework review, and
           Dossier coverage.  A bounded projection can rank these records while
           preserving their separate meanings and human-controlled actions.
"""

from __future__ import annotations

from typing import Any, Iterable

POLICY_ID = "pivotglass-pursuit-brief-v1"

_SCIENTIFIC_STAGES: tuple[tuple[str, frozenset[str]], ...] = (
    ("Frame", frozenset({"question", "assumption"})),
    ("Explain", frozenset({"hypothesis", "assertion"})),
    ("Predict", frozenset({"prediction", "signpost"})),
    ("Collect", frozenset({"collection_requirement", "observation", "stop_condition"})),
    ("Test", frozenset({"method_run"})),
    ("Conclude", frozenset({"conclusion", "limitation", "knowledge_gap"})),
)


def build_pursuit_brief(
    *,
    analysis: dict[str, Any],
    dossier_slots: Iterable[dict[str, Any]],
    framework_counts: dict[str, dict[str, int]],
    investigations: Iterable[dict[str, Any]],
    object_count: int,
    latest_target: str | None,
) -> dict[str, Any]:
    """Build a bounded, non-mutating summary of the active pursuit."""

    dossier = [dict(slot) for slot in dossier_slots]
    investigation_rows = list(analysis.get("investigations") or [])
    active = next(
        (
            row
            for row in reversed(investigation_rows)
            if row.get("status") not in {"concluded", "suspended"}
        ),
        investigation_rows[-1] if investigation_rows else None,
    )
    active_id = str(active.get("id")) if active and active.get("id") else None
    lifecycle = [
        row
        for row in analysis.get("lifecycle_items") or []
        if active_id is None or str(row.get("investigation_id")) == active_id
    ]
    primary_question_id = str(active.get("primary_question_id") or "") if active else ""
    active_question_ids = {
        str(row.get("record_id") or "")
        for row in lifecycle
        if row.get("record_kind") == "question" or row.get("item_type") == "question"
    }
    if primary_question_id:
        active_question_ids.add(primary_question_id)
    all_questions = list(analysis.get("questions") or [])
    questions = (
        [row for row in all_questions if str(row.get("id") or "") in active_question_ids]
        if active_question_ids
        else all_questions
    )
    current_question = next(
        (str(row.get("text") or "") for row in questions if str(row.get("id")) == primary_question_id),
        str(questions[-1].get("text") or "") if questions else "",
    )
    if not current_question and active:
        title = str(active.get("title") or "")
        if title and title != "Workspace investigation":
            current_question = title

    stage_counts = {
        label: sum(str(item.get("item_type")) in types for item in lifecycle)
        for label, types in _SCIENTIFIC_STAGES
    }
    completed_stages = sum(count > 0 for count in stage_counts.values())
    current_stage = next(
        (label for label, count in stage_counts.items() if count == 0),
        "Review",
    )

    unresolved = [
        row for row in analysis.get("contradictions") or [] if row.get("status") == "unresolved"
    ]
    high_contradictions = [row for row in unresolved if row.get("materiality") == "high"]
    hypotheses = [
        row
        for row in analysis.get("hypotheses") or []
        if not active_question_ids or str(row.get("question_id") or "") in active_question_ids
        if row.get("status") not in {"rejected", "suspended"}
    ]
    open_gaps = [
        row
        for row in lifecycle
        if row.get("item_type") == "knowledge_gap"
        and row.get("status") not in {"satisfied", "resolved", "rejected"}
    ]
    stop_conditions = [row for row in lifecycle if row.get("item_type") == "stop_condition"]
    pending_method_reviews = [
        row
        for row in analysis.get("method_runs") or []
        if not active_question_ids or str(row.get("question_id") or "") in active_question_ids
        if row.get("analyst_disposition") == "pending"
    ]
    pending_external_reviews = [
        row
        for row in lifecycle
        if row.get("author_kind") in {"model", "external_tool"}
        and row.get("analyst_disposition") == "pending"
    ]
    pending_framework_reviews = sum(
        int(states.get("proposed", 0)) for states in framework_counts.values()
    )
    pending_reviews = (
        len(pending_method_reviews) + len(pending_external_reviews) + pending_framework_reviews
    )

    enrichment_requests = list(analysis.get("enrichment_queue") or [])
    requested_pending = sum(
        str(row.get("status")) in {"planned", "queued", "running"}
        for row in enrichment_requests
    )
    investigation_snapshots = list(investigations)
    active_enrichments = [
        row
        for row in investigation_snapshots
        if row.get("lifecycle") in {"planned", "queued", "running"}
    ]
    failed_events = [
        event
        for snapshot in investigation_snapshots
        for event in snapshot.get("events") or []
        if event.get("lifecycle") == "failed" or event.get("event_class") == "source_fault"
    ]
    event_rows = [
        event for snapshot in investigation_snapshots for event in snapshot.get("events") or []
    ]
    terminal_events = [
        event
        for event in event_rows
        if event.get("lifecycle") in {"succeeded", "empty", "failed", "skipped", "cancelled"}
    ]

    mapped_slots = [slot for slot in dossier if slot.get("status") in {"partial", "filled"}]
    filled_slots = [slot for slot in dossier if slot.get("status") == "filled"]
    weak_slots = sorted(
        (slot for slot in dossier if slot.get("status") in {"empty", "partial"}),
        key=lambda row: (
            0 if row.get("status") == "empty" else 1,
            int(row.get("evidence_count") or 0),
            str(row.get("name") or ""),
        ),
    )

    next_action = _choose_next_action(
        current_question=current_question,
        active_enrichments=active_enrichments,
        failed_events=failed_events,
        high_contradictions=high_contradictions,
        unresolved=unresolved,
        pending_reviews=pending_reviews,
        pending_method_reviews=pending_method_reviews,
        pending_external_reviews=pending_external_reviews,
        pending_framework_reviews=pending_framework_reviews,
        hypotheses=hypotheses,
        stop_conditions=stop_conditions,
        information_requirements=analysis.get("information_requirements") or {},
        weak_slots=weak_slots,
        requested_pending=requested_pending,
        object_count=object_count,
    )

    review_total = pending_reviews + _accepted_review_count(analysis, framework_counts)
    review_complete = max(0, review_total - pending_reviews)
    recent_change = _recent_change(event_rows, lifecycle, object_count, len(mapped_slots))

    return {
        "schema_version": "1.0",
        "policy": {
            "id": POLICY_ID,
            "content_class": "method_derived_workflow",
            "human_authority": "Suggestions never run remote work or accept judgments automatically.",
        },
        "subject": {
            "title": str(active.get("title") or "Untitled investigation") if active else "No investigation framed",
            "question": current_question or None,
            "target": latest_target,
            "workspace_state": str(active.get("status") or "not_started") if active else "not_started",
        },
        "now": {
            "stage": "Enrich" if active_enrichments else current_stage,
            "status": (
                f"{len(active_enrichments)} enrichment run{'s' if len(active_enrichments) != 1 else ''} active"
                if active_enrichments
                else "Ready for analyst action"
            ),
        },
        "next_action": next_action,
        "progress": [
            {
                "id": "evidence_coverage",
                "label": "Evidence coverage",
                "current": len(mapped_slots),
                "total": len(dossier),
                "detail": f"{len(filled_slots)} filled · {len(mapped_slots) - len(filled_slots)} partial",
            },
            {
                "id": "scientific_method",
                "label": "Scientific method",
                "current": completed_stages,
                "total": len(_SCIENTIFIC_STAGES),
                "detail": f"{current_stage} is next" if current_stage != "Review" else "Lifecycle recorded",
            },
            {
                "id": "enrichment_work",
                "label": "Enrichment work",
                "current": len(terminal_events),
                "total": len(event_rows),
                "detail": f"{len(active_enrichments) + requested_pending} waiting or active",
            },
            {
                "id": "analyst_review",
                "label": "Analyst review",
                "current": review_complete,
                "total": review_total,
                "detail": f"{pending_reviews} decision{'s' if pending_reviews != 1 else ''} pending",
            },
        ],
        "open_work": {
            "contradictions": len(unresolved),
            "knowledge_gaps": len(open_gaps),
            "pending_reviews": pending_reviews,
            "queued_enrichments": requested_pending,
            "weak_dossier_dimensions": len(weak_slots),
            "failed_enrichments": len(failed_events),
        },
        "weakest_dimensions": [
            {
                "name": str(slot.get("name") or "unknown").replace("_", " "),
                "status": str(slot.get("status") or "empty"),
                "evidence_count": int(slot.get("evidence_count") or 0),
            }
            for slot in weak_slots[:3]
        ],
        "recent_change": recent_change,
        "object_count": object_count,
    }


def _choose_next_action(**context: Any) -> dict[str, Any]:
    failed_events = context["failed_events"]
    if failed_events:
        event = failed_events[-1]
        return _action(
            "review_failure",
            "Review failed enrichment",
            str(event.get("next_action") or event.get("reason") or "Inspect the source failure before retrying."),
            category="required",
            action_type="pane",
            value="intelligence",
            basis=[_event_ref(event)],
        )

    active_enrichments = context["active_enrichments"]
    if active_enrichments:
        snapshot = active_enrichments[-1]
        return _action(
            "review_active_enrichment",
            "Review live enrichment",
            "An enrichment run is active. Follow its receipts or cancel it without losing completed evidence.",
            category="current_work",
            action_type="pane",
            value="intelligence",
            basis=[{"kind": "investigation", "id": str(snapshot.get("investigation_id") or "active")}],
        )

    contradictions = context["high_contradictions"] or context["unresolved"]
    if contradictions:
        row = contradictions[0]
        return _action(
            "resolve_contradiction",
            "Resolve the strongest contradiction",
            str(row.get("resolution_required") or "Identify evidence that can resolve the recorded conflict."),
            category="required" if row.get("materiality") == "high" else "method_suggestion",
            action_type="workbench",
            value="contradictions",
            basis=[{"kind": "contradiction", "id": str(row.get("id"))}],
        )

    if context["pending_reviews"]:
        if context["pending_method_reviews"]:
            source = context["pending_method_reviews"][0]
            basis = [{"kind": "method_run", "id": str(source.get("id"))}]
        elif context["pending_external_reviews"]:
            source = context["pending_external_reviews"][0]
            basis = [{"kind": str(source.get("record_kind") or "proposal"), "id": str(source.get("record_id") or source.get("id"))}]
        else:
            basis = [{"kind": "framework_mapping", "id": f"{context['pending_framework_reviews']}-proposed"}]
        return _action(
            "review_proposal",
            "Review pending analytic proposals",
            "A proposed method result or framework mapping needs an explicit analyst decision.",
            category="required",
            action_type="workbench",
            value="reviews",
            basis=basis,
        )

    if not context["current_question"]:
        return _action(
            "frame_question",
            "Frame the investigation",
            "State the decision or question this evidence must answer before collection expands.",
            category="required",
            action_type="command",
            value="analysis question ",
            basis=[{"kind": "policy", "id": POLICY_ID}],
            permission="analyst_record",
        )

    if len(context["hypotheses"]) < 2:
        return _action(
            "add_competing_hypothesis",
            "Add a competing explanation",
            "A single explanation is vulnerable to confirmation bias. Record an alternative that the evidence could distinguish.",
            category="method_suggestion",
            action_type="command",
            value="analysis hypothesis ",
            basis=[{"kind": "investigation_question", "id": "active"}],
            permission="analyst_record",
        )

    if not context["stop_conditions"]:
        return _action(
            "define_stop_condition",
            "Define when collection should stop",
            "A stop condition protects attention and makes the hunt's sufficiency test explicit.",
            category="method_suggestion",
            action_type="command",
            value="analysis stop ",
            basis=[{"kind": "policy", "id": POLICY_ID}],
            permission="analyst_record",
        )

    information = context["information_requirements"]
    suggestions = list(information.get("suggestions") or [])
    requirements = [
        row
        for row in information.get("requirements") or []
        if row.get("status") not in {"satisfied", "resolved", "rejected"}
    ]
    if requirements:
        row = requirements[0]
        return _action(
            "review_requirement",
            "Collect the highest-priority information",
            str(row.get("statement") or "Review the highest-ranked information requirement."),
            category="method_suggestion",
            action_type="workbench",
            value="requirements",
            basis=[{"kind": "collection_requirement", "id": str(row.get("id"))}],
        )
    if suggestions:
        row = suggestions[0]
        return _action(
            "adopt_information_requirement",
            "Review what would reduce uncertainty",
            str(row.get("statement") or row.get("rationale") or "Review the top method-derived suggestion."),
            category="method_suggestion",
            action_type="workbench",
            value="requirements",
            basis=list(row.get("source_refs") or []),
        )

    weak_slots = context["weak_slots"]
    if weak_slots:
        slot = weak_slots[0]
        name = str(slot.get("name") or "unknown").replace("_", " ")
        return _action(
            "review_coverage_gap",
            f"Review the {name} gap",
            "Inspect the supporting evidence and choose a relevant configured source; running a source never fills a facet by itself.",
            category="optional_improvement",
            action_type="pane",
            value="dossier",
            basis=[{"kind": "dossier_dimension", "id": str(slot.get("name") or "unknown")}],
        )

    if context["requested_pending"]:
        return _action(
            "review_enrichment_queue",
            "Review queued enrichment",
            "Analyst-approved enrichment requests are waiting for execution.",
            category="current_work",
            action_type="pane",
            value="intelligence",
            basis=[{"kind": "enrichment_queue", "id": "active"}],
        )

    if context["object_count"]:
        return _action(
            "review_and_report",
            "Review the evidence and report",
            "Coverage is strong. Check unresolved limitations, then generate a report whose conclusions remain separate from evidence.",
            category="optional_improvement",
            action_type="command",
            value="report",
            basis=[{"kind": "workspace", "id": "active"}],
        )

    return _action(
        "start_pursuit",
        "Start with an indicator or question",
        "Enter one concrete observable or analyst question. Pivotglass will show each enrichment receipt as it arrives.",
        category="required",
        action_type="focus",
        value="",
        basis=[{"kind": "policy", "id": POLICY_ID}],
    )


def _action(
    action_id: str,
    label: str,
    rationale: str,
    *,
    category: str,
    action_type: str,
    value: str,
    basis: list[dict[str, Any]],
    permission: str = "review_only",
) -> dict[str, Any]:
    return {
        "id": action_id,
        "label": label,
        "rationale": rationale,
        "category": category,
        "action_type": action_type,
        "value": value,
        "basis": basis,
        "permission": permission,
        "confirmation_required": permission in {"remote_enrichment", "external_publication"},
        "auto_eligible": permission == "local_read_only",
        "content_class": "method_derived_workflow",
    }


def _event_ref(event: dict[str, Any]) -> dict[str, str]:
    return {
        "kind": "investigation_event",
        "id": str(event.get("event_id") or "unknown"),
    }


def _accepted_review_count(
    analysis: dict[str, Any], framework_counts: dict[str, dict[str, int]]
) -> int:
    method_reviews = sum(
        row.get("analyst_disposition") in {"accepted", "rejected", "revised"}
        for row in analysis.get("method_runs") or []
    )
    lifecycle_reviews = sum(
        row.get("author_kind") in {"model", "external_tool"}
        and row.get("analyst_disposition") in {"accepted", "rejected", "revised"}
        for row in analysis.get("lifecycle_items") or []
    )
    framework_reviews = sum(
        int(states.get("accepted", 0)) + int(states.get("rejected", 0))
        for states in framework_counts.values()
    )
    return method_reviews + lifecycle_reviews + framework_reviews


def _recent_change(
    events: list[dict[str, Any]],
    lifecycle: list[dict[str, Any]],
    object_count: int,
    mapped_slots: int,
) -> dict[str, Any]:
    if events:
        event = events[-1]
        summary = event.get("summary") or event.get("reason")
        if not summary:
            source = event.get("source") or event.get("tool") or "enrichment"
            summary = f"{source} moved to {event.get('lifecycle') or 'updated'} state."
        return {
            "summary": str(summary),
            "content_class": str(event.get("content_class") or "system"),
            "basis": [_event_ref(event)],
        }
    if lifecycle:
        item = lifecycle[-1]
        return {
            "summary": str(item.get("statement") or "The analytic notebook was updated."),
            "content_class": "analytic_record",
            "basis": [{"kind": str(item.get("record_kind") or item.get("item_type") or "lifecycle_item"), "id": str(item.get("record_id") or item.get("id") or "unknown")}],
        }
    return {
        "summary": f"{object_count} stored observables · {mapped_slots} Dossier dimensions mapped.",
        "content_class": "workspace_summary",
        "basis": [{"kind": "workspace", "id": "active"}],
    }
