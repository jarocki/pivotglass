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

from typing import Any

from adversary_pursuit.core.analytic_ledger import (
    AnalyticLedger,
    AssertionType,
    ConfidenceLevel,
    HypothesisStatus,
    LikelihoodTerm,
)
from adversary_pursuit.core.structured_analysis import StructuredAnalysisWorkbench

ANALYSIS_USAGE = (
    "Usage: analysis show|methods|contradictions|question <text>|"
    "assertion <inferred|assumed|judgment> <text>|"
    "hypothesis <question-id> <text>|"
    "accept|reject|suspend <hypothesis-id>|"
    "confidence <assertion|hypothesis> <id> <low|moderate|high> <rationale>|"
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
    if action == "question" and len(args) >= 2:
        question_id = ledger.create_question(" ".join(args[1:]))
        return {
            "title": "Investigation question created",
            "data": {"question_id": question_id},
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
    if action == "confidence" and len(args) >= 5:
        target_kind = _target_kind(args[1])
        level = _enum_value(ConfidenceLevel, args[3], "confidence level")
        assessment_id = ledger.assess_confidence(
            target_kind=target_kind,
            target_id=args[2],
            level=level,
            rationale=" ".join(args[4:]),
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
