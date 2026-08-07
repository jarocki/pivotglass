"""Shared deterministic command adapter for Pivotglass analytic records.

The TUI and web cockpit call this module rather than maintaining parallel
parsers.  Commands only mutate the analytic ledger after validating explicit
operator input; no model is consulted and no evidence is manufactured.

@decision DEC-ANALYSIS-COMMAND-001
@title TUI and Pivotglass share one deterministic analytic-command authority
@status accepted
@rationale Parallel command implementations drift and can silently apply
           different epistemic rules. A shared adapter gives both interfaces the
           same validation, human gates, record types, and local-only behavior.
"""

from __future__ import annotations

import json
from typing import Any

from adversary_pursuit.core.analytic_ledger import (
    AnalystDisposition,
    AnalyticLedger,
    AssertionType,
    ConfidenceLevel,
    ContradictionStatus,
    HypothesisStatus,
    InvestigationStatus,
    LifecycleItemStatus,
    LifecycleItemType,
    LikelihoodTerm,
    Materiality,
)
from adversary_pursuit.core.information_requirements import (
    build_information_requirements,
    validate_requirement_criteria,
)
from adversary_pursuit.core.structured_analysis import (
    StructuredAnalysisWorkbench,
    StructuredTechnique,
)

ANALYSIS_USAGE = (
    "Usage: analysis show|lifecycle|methods|contradictions|priorities|question <text>|"
    "assertion <inferred|assumed|judgment> <text>|"
    "assumption <text>|"
    "hypothesis <question-id> <text>|"
    "prediction|signpost|collect|stop|limitation|gap <text>|"
    "requirement <text> | <factor-json>|prioritize <item-id> <0-100>|"
    "conclude <text>|status <framing|collecting|analyzing|concluded|suspended>|"
    "item <item-id> <open|satisfied|rejected|resolved|deferred> "
    "[accepted|rejected|revised]|"
    "contradiction <left-kind> <left-id> <right-kind> <right-id> "
    "<summary> | <resolution requirement>|resolve <contradiction-id> <note>|"
    "method list [question-id]|method start <question-id> <technique> <json>|"
    "method complete <run-id> <json>|method accept|reject|revise <run-id>|"
    "accept|reject|suspend <hypothesis-id>|"
    "confidence <assertion|hypothesis> <id> <low|moderate|high> "
    "<rationale> | <factor-json>|"
    "likelihood <assertion|hypothesis> <id> <term> <rationale>"
)


def execute_analysis_command(args: tuple[str, ...], workspace_manager: Any) -> dict[str, Any]:
    """Execute one local analytic-ledger command and return structured data."""

    ledger = AnalyticLedger(workspace_manager)
    action = args[0].casefold() if args else "show"

    if action == "show":
        return {
            "title": "Analytic ledger",
            "data": ledger.snapshot(),
        }
    if action == "lifecycle":
        snapshot = ledger.snapshot()
        return {
            "title": "Scientific investigation lifecycle",
            "data": {
                "investigations": snapshot["investigations"],
                "items": snapshot["lifecycle_items"],
            },
        }
    if action == "methods":
        methods = StructuredAnalysisWorkbench(workspace_manager).definitions()
        return {
            "title": "Structured analytic techniques",
            "data": [
                {
                    "technique": method.technique.value,
                    "label": method.label,
                    "version": method.version,
                    "purpose": method.purpose,
                    "required_inputs": method.required_inputs,
                    "required_outputs": method.required_outputs,
                }
                for method in methods
            ],
        }
    if action == "contradictions":
        contradictions = ledger.snapshot()["contradictions"]
        return {
            "title": "Analytic contradictions",
            "data": contradictions,
        }
    if action == "priorities":
        return {
            "title": "Priority intelligence requirements",
            "data": build_information_requirements(ledger.snapshot()),
        }
    if action == "question" and len(args) >= 2:
        question_id = ledger.create_question(" ".join(args[1:]))
        return {
            "title": "Investigation question created",
            "data": {"question_id": question_id},
        }
    if action == "assumption" and len(args) >= 2:
        assertion_id = ledger.create_assertion(
            " ".join(args[1:]),
            assertion_type=AssertionType.ASSUMED,
        )
        return {
            "title": "Key assumption recorded",
            "data": {"assertion_id": assertion_id, "assertion_type": "assumed"},
        }
    if action == "assertion" and len(args) >= 3:
        assertion_type = _enum_value(AssertionType, args[1], "assertion type")
        assertion_id = ledger.create_assertion(
            " ".join(args[2:]),
            assertion_type=assertion_type,
        )
        return {
            "title": "Analytic assertion created",
            "data": {"assertion_id": assertion_id, "assertion_type": assertion_type.value},
        }
    if action == "hypothesis" and len(args) >= 3:
        hypothesis_id = ledger.create_hypothesis(args[1], " ".join(args[2:]))
        return {
            "title": "Hypothesis proposed",
            "data": {"hypothesis_id": hypothesis_id, "status": "proposed"},
        }
    if action in {"accept", "reject", "suspend"} and len(args) == 2:
        status = {
            "accept": HypothesisStatus.RETAINED,
            "reject": HypothesisStatus.REJECTED,
            "suspend": HypothesisStatus.SUSPENDED,
        }[action]
        ledger.set_hypothesis_status(args[1], status)
        return {
            "title": "Hypothesis disposition recorded",
            "data": {"hypothesis_id": args[1], "status": status.value},
        }
    if action == "requirement" and len(args) >= 2:
        statement, separator, criteria_json = " ".join(args[1:]).partition("|")
        if not separator:
            raise ValueError(
                "Separate the collection requirement and four-factor JSON with |."
            )
        criteria = validate_requirement_criteria(
            _json_object(criteria_json, "requirement factors")
        )
        investigation_id = _active_investigation_id(ledger)
        item_id = ledger.add_lifecycle_item(
            investigation_id,
            LifecycleItemType.COLLECTION_REQUIREMENT,
            statement,
            criteria=criteria,
        )
        return {
            "title": "Priority intelligence requirement recorded",
            "data": {
                "investigation_id": investigation_id,
                "item_id": item_id,
                "criteria": criteria,
            },
        }
    if action == "prioritize" and len(args) == 3:
        try:
            priority = int(args[2])
        except ValueError as exc:
            raise ValueError("Information-requirement priority must be 0 to 100.") from exc
        ledger.prioritize_information_requirement(args[1], priority)
        return {
            "title": "Information requirement prioritized",
            "data": {"item_id": args[1], "priority": priority},
        }
    lifecycle_types = {
        "prediction": LifecycleItemType.PREDICTION,
        "signpost": LifecycleItemType.SIGNPOST,
        "collect": LifecycleItemType.COLLECTION_REQUIREMENT,
        "stop": LifecycleItemType.STOP_CONDITION,
        "limitation": LifecycleItemType.LIMITATION,
        "gap": LifecycleItemType.KNOWLEDGE_GAP,
    }
    if action in lifecycle_types and len(args) >= 2:
        investigation_id = _active_investigation_id(ledger)
        item_type = lifecycle_types[action]
        item_id = ledger.add_lifecycle_item(
            investigation_id,
            item_type,
            " ".join(args[1:]),
        )
        return {
            "title": f"{item_type.value.replace('_', ' ').title()} recorded",
            "data": {
                "investigation_id": investigation_id,
                "item_id": item_id,
                "item_type": item_type.value,
            },
        }
    if action == "conclude" and len(args) >= 2:
        investigation_id = _active_investigation_id(ledger)
        item_id = ledger.add_lifecycle_item(
            investigation_id,
            LifecycleItemType.CONCLUSION,
            " ".join(args[1:]),
        )
        ledger.set_investigation_status(
            investigation_id,
            InvestigationStatus.CONCLUDED,
        )
        return {
            "title": "Investigation conclusion recorded",
            "data": {
                "investigation_id": investigation_id,
                "item_id": item_id,
                "status": InvestigationStatus.CONCLUDED.value,
            },
        }
    if action == "status" and len(args) == 2:
        investigation_id = _active_investigation_id(ledger, include_closed=True)
        status = _enum_value(InvestigationStatus, args[1], "investigation status")
        ledger.set_investigation_status(investigation_id, status)
        return {
            "title": "Investigation state updated",
            "data": {"investigation_id": investigation_id, "status": status.value},
        }
    if action == "item" and len(args) in {3, 4}:
        status = _enum_value(LifecycleItemStatus, args[2], "lifecycle item status")
        disposition = (
            _enum_value(AnalystDisposition, args[3], "analyst disposition")
            if len(args) == 4
            else None
        )
        ledger.update_lifecycle_item(
            args[1],
            status=status,
            disposition=disposition,
        )
        return {
            "title": "Lifecycle item updated",
            "data": {
                "item_id": args[1],
                "status": status.value,
                "analyst_disposition": disposition.value if disposition else None,
            },
        }
    if action == "contradiction" and len(args) >= 6:
        summary, separator, requirement = " ".join(args[5:]).partition("|")
        if not separator:
            raise ValueError("Separate the contradiction summary and required resolution with |.")
        contradiction_id = ledger.record_contradiction(
            left_kind=args[1],
            left_id=args[2],
            right_kind=args[3],
            right_id=args[4],
            summary=summary,
            resolution_required=requirement,
            materiality=Materiality.HIGH,
        )
        return {
            "title": "Analytic contradiction recorded",
            "data": {"contradiction_id": contradiction_id, "status": "unresolved"},
        }
    if action == "resolve" and len(args) >= 3:
        ledger.resolve_contradiction(
            args[1],
            " ".join(args[2:]),
            status=ContradictionStatus.RESOLVED,
        )
        return {
            "title": "Analytic contradiction resolved",
            "data": {"contradiction_id": args[1], "status": "resolved"},
        }
    if action == "method":
        return _execute_method_command(args[1:], workspace_manager)
    if action == "confidence" and len(args) >= 5:
        target_kind = _target_kind(args[1])
        level = _enum_value(ConfidenceLevel, args[3], "confidence level")
        rationale, separator, factor_json = " ".join(args[4:]).partition("|")
        if not separator:
            raise ValueError("Separate the confidence rationale and factor JSON with |.")
        assessment_id = ledger.assess_confidence(
            target_kind=target_kind,
            target_id=args[2],
            level=level,
            rationale=rationale,
            factors=_json_object(factor_json, "confidence factors"),
        )
        return {
            "title": "Confidence assessment recorded",
            "data": {"assessment_id": assessment_id, "level": level.value},
        }
    if action == "likelihood" and len(args) >= 5:
        target_kind = _target_kind(args[1])
        term_text = args[3].casefold().replace("-", "_")
        term = _enum_value(LikelihoodTerm, term_text, "likelihood term")
        assessment_id = ledger.assess_likelihood(
            target_kind=target_kind,
            target_id=args[2],
            term=term,
            rationale=" ".join(args[4:]),
        )
        return {
            "title": "Likelihood assessment recorded",
            "data": {
                "assessment_id": assessment_id,
                "term": term.value,
            },
        }

    raise ValueError(ANALYSIS_USAGE)


def _target_kind(value: str) -> str:
    normalized = value.casefold()
    if normalized not in {"assertion", "hypothesis"}:
        raise ValueError("Judgment target must be assertion or hypothesis.")
    return normalized


def _enum_value(enum_type: type, value: str, label: str):
    try:
        return enum_type(value.casefold())
    except ValueError as exc:
        choices = ", ".join(item.value for item in enum_type)
        raise ValueError(f"Unknown {label}: {value}. Choose: {choices}.") from exc


def _active_investigation_id(
    ledger: AnalyticLedger,
    *,
    include_closed: bool = False,
) -> str:
    active = ledger.active_investigation()
    if active is not None:
        return str(active["id"])
    if include_closed:
        investigations = ledger.snapshot()["investigations"]
        if investigations:
            return str(investigations[-1]["id"])
    raise ValueError("No active investigation. Record an analysis question first.")


def _execute_method_command(
    args: tuple[str, ...],
    workspace_manager: Any,
) -> dict[str, Any]:
    workbench = StructuredAnalysisWorkbench(workspace_manager)
    action = args[0].casefold() if args else "list"
    if action == "list" and len(args) <= 2:
        runs = workbench.list_runs(question_id=args[1] if len(args) == 2 else None)
        return {"title": "Structured analytic method runs", "data": runs}
    if action == "start" and len(args) >= 4:
        technique = _enum_value(
            StructuredTechnique,
            args[2].casefold().replace("-", "_"),
            "structured analytic technique",
        )
        inputs = _json_object(" ".join(args[3:]), "method inputs")
        run_id = workbench.start(args[1], technique, inputs)
        return {
            "title": "Structured analytic method started",
            "data": {"run_id": run_id, "technique": technique.value},
        }
    if action == "complete" and len(args) >= 3:
        outputs = _json_object(" ".join(args[2:]), "method outputs")
        workbench.complete(args[1], outputs)
        return {
            "title": "Structured analytic method completed",
            "data": {"run_id": args[1], "status": "complete"},
        }
    if action in {"accept", "reject", "revise"} and len(args) == 2:
        disposition = {
            "accept": AnalystDisposition.ACCEPTED,
            "reject": AnalystDisposition.REJECTED,
            "revise": AnalystDisposition.REVISED,
        }[action]
        workbench.disposition(args[1], disposition)
        return {
            "title": "Structured analytic method disposition recorded",
            "data": {"run_id": args[1], "analyst_disposition": disposition.value},
        }
    raise ValueError(ANALYSIS_USAGE)


def _json_object(value: str, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be a valid JSON object: {exc.msg}.") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return parsed
