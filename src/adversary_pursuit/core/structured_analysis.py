"""Versioned Structured Analytic Technique protocols for Pivotglass.

The workbench persists auditable method inputs and outputs. It does not ask a
model to "do analysis" behind an opaque prompt: each technique has a bounded,
human-readable contract, and model-produced work remains pending until an
analyst explicitly accepts, rejects, or revises it.

@decision DEC-SAT-WORKBENCH-001
@title Structured analysis runs are versioned protocols with human disposition
@status accepted
@rationale Required inputs and outputs make analytic methods reviewable and
           reproducible. Models may draft a run, but only an explicit human action
           may accept, reject, or revise consequential analytic work.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import select

from adversary_pursuit.core.analytic_ledger import (
    AnalystDisposition,
    AnalyticLedger,
    AuthorKind,
    LifecycleItemStatus,
)
from adversary_pursuit.models.database import AnalyticMethodRun, InvestigationQuestion


class StructuredTechnique(StrEnum):
    QUALITY_OF_INFORMATION = "quality_of_information_check"
    KEY_ASSUMPTIONS = "key_assumptions_check"
    COMPETING_HYPOTHESES = "analysis_of_competing_hypotheses"
    INDICATORS_SIGNPOSTS = "indicators_and_signposts"
    DEVILS_ADVOCACY = "devils_advocacy"
    PREMORTEM = "premortem_analysis"
    CHRONOLOGY = "chronology_and_timeline"


class MethodRunStatus(StrEnum):
    DRAFT = "draft"
    COMPLETE = "complete"


@dataclass(frozen=True)
class TechniqueDefinition:
    technique: StructuredTechnique
    label: str
    version: str
    purpose: str
    required_inputs: tuple[str, ...]
    required_outputs: tuple[str, ...]


TECHNIQUE_DEFINITIONS: dict[StructuredTechnique, TechniqueDefinition] = {
    StructuredTechnique.QUALITY_OF_INFORMATION: TechniqueDefinition(
        technique=StructuredTechnique.QUALITY_OF_INFORMATION,
        label="Quality of Information Check",
        version="1.0",
        purpose="Evaluate source access, credibility, currency, relevance, and gaps.",
        required_inputs=("source_ids",),
        required_outputs=("assessments", "gaps"),
    ),
    StructuredTechnique.KEY_ASSUMPTIONS: TechniqueDefinition(
        technique=StructuredTechnique.KEY_ASSUMPTIONS,
        label="Key Assumptions Check",
        version="1.0",
        purpose="Expose assumptions that carry a judgment and test their fragility.",
        required_inputs=("assumptions",),
        required_outputs=("challenged_assumptions", "implications"),
    ),
    StructuredTechnique.COMPETING_HYPOTHESES: TechniqueDefinition(
        technique=StructuredTechnique.COMPETING_HYPOTHESES,
        label="Analysis of Competing Hypotheses",
        version="1.0",
        purpose="Compare hypotheses against diagnostic supporting and contradicting evidence.",
        required_inputs=("hypothesis_ids", "evidence_ids"),
        required_outputs=("matrix", "least_inconsistent", "sensitivity"),
    ),
    StructuredTechnique.INDICATORS_SIGNPOSTS: TechniqueDefinition(
        technique=StructuredTechnique.INDICATORS_SIGNPOSTS,
        label="Indicators and Signposts",
        version="1.0",
        purpose="Define observable developments that would change a judgment.",
        required_inputs=("hypothesis_id",),
        required_outputs=("signposts", "thresholds"),
    ),
    StructuredTechnique.DEVILS_ADVOCACY: TechniqueDefinition(
        technique=StructuredTechnique.DEVILS_ADVOCACY,
        label="Devil's Advocacy",
        version="1.0",
        purpose="Construct the strongest evidence-grounded challenge to a leading judgment.",
        required_inputs=("judgment_id",),
        required_outputs=("challenge", "alternative_explanation"),
    ),
    StructuredTechnique.PREMORTEM: TechniqueDefinition(
        technique=StructuredTechnique.PREMORTEM,
        label="Premortem Analysis",
        version="1.0",
        purpose="Assume the judgment failed and identify plausible reasons before publication.",
        required_inputs=("judgment_id",),
        required_outputs=("failure_modes", "mitigations"),
    ),
    StructuredTechnique.CHRONOLOGY: TechniqueDefinition(
        technique=StructuredTechnique.CHRONOLOGY,
        label="Chronology and Timeline Analysis",
        version="1.0",
        purpose="Order sourced events, identify gaps, and expose temporal conflicts.",
        required_inputs=("event_ids",),
        required_outputs=("ordered_events", "gaps", "temporal_conflicts"),
    ),
}


class StructuredAnalysisWorkbench:
    """Run bounded SAT protocols against an active workspace."""

    def __init__(self, workspace_manager: Any) -> None:
        self._workspace = workspace_manager

    def definitions(self) -> tuple[TechniqueDefinition, ...]:
        return tuple(TECHNIQUE_DEFINITIONS.values())

    def start(
        self,
        question_id: str,
        technique: StructuredTechnique,
        inputs: dict[str, Any],
        *,
        created_by: AuthorKind = AuthorKind.HUMAN,
    ) -> str:
        definition = TECHNIQUE_DEFINITIONS[technique]
        _require_fields(inputs, definition.required_inputs, "input")
        run_id = f"method-run-{uuid.uuid4()}"
        with self._workspace.get_session() as session:
            if session.get(InvestigationQuestion, question_id) is None:
                raise ValueError(f"Unknown investigation question: {question_id}")
            session.add(
                AnalyticMethodRun(
                    id=run_id,
                    question_id=question_id,
                    technique=technique.value,
                    technique_version=definition.version,
                    status=MethodRunStatus.DRAFT.value,
                    input_blob=inputs,
                    output_blob=None,
                    created_by=created_by.value,
                    analyst_disposition=AnalystDisposition.PENDING.value,
                )
            )
            session.commit()
        AnalyticLedger(self._workspace).link_method_run(
            question_id,
            run_id,
            created_by=created_by,
            statement=f"{definition.label}: {definition.purpose}",
        )
        return run_id

    def complete(self, run_id: str, outputs: dict[str, Any]) -> None:
        with self._workspace.get_session() as session:
            run = session.get(AnalyticMethodRun, run_id)
            if run is None:
                raise ValueError(f"Unknown method run: {run_id}")
            technique = StructuredTechnique(run.technique)
            definition = TECHNIQUE_DEFINITIONS[technique]
            _require_fields(outputs, definition.required_outputs, "output")
            run.output_blob = outputs
            run.status = MethodRunStatus.COMPLETE.value
            run.completed_at = datetime.now(timezone.utc)
            session.commit()
        AnalyticLedger(self._workspace).update_linked_record(
            "method_run",
            run_id,
            status=LifecycleItemStatus.SATISFIED,
            decided_by=AuthorKind.SYSTEM,
        )

    def disposition(
        self,
        run_id: str,
        disposition: AnalystDisposition,
        *,
        decided_by: AuthorKind = AuthorKind.HUMAN,
    ) -> None:
        if decided_by is not AuthorKind.HUMAN:
            raise ValueError("Only an explicit human action may disposition analytic work.")
        if disposition is AnalystDisposition.PENDING:
            raise ValueError("A disposition must be accepted, rejected, or revised.")
        with self._workspace.get_session() as session:
            run = session.get(AnalyticMethodRun, run_id)
            if run is None:
                raise ValueError(f"Unknown method run: {run_id}")
            if run.status != MethodRunStatus.COMPLETE.value:
                raise ValueError("A method run must be complete before analyst disposition.")
            run.analyst_disposition = disposition.value
            session.commit()
        AnalyticLedger(self._workspace).update_linked_record(
            "method_run",
            run_id,
            disposition=disposition,
            decided_by=decided_by,
        )

    def list_runs(self, *, question_id: str | None = None) -> list[dict[str, Any]]:
        with self._workspace.get_session() as session:
            statement = select(AnalyticMethodRun)
            if question_id is not None:
                statement = statement.where(AnalyticMethodRun.question_id == question_id)
            rows = session.execute(statement.order_by(AnalyticMethodRun.created_at)).scalars()
            return [
                {column.name: getattr(row, column.name) for column in row.__table__.columns}
                for row in rows
            ]


def _require_fields(payload: dict[str, Any], required: tuple[str, ...], label: str) -> None:
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"Technique {label} is missing required fields: {', '.join(missing)}")
