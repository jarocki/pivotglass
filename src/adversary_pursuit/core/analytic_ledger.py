"""Deterministic authority for Pivotglass analytic-method records.

The ledger distinguishes what was observed from what an analyst or model
asserts about it.  It also keeps probability language separate from confidence
in the evidentiary basis.  UI adapters may guide a workflow, but they must use
this authority to persist questions, hypotheses, evidence links, confidence,
likelihood, and contradictions.

@decision DEC-EPISTEMIC-LEDGER-001
@title Observations, assertions, hypotheses, evidence links, and contradictions are distinct
@status accepted
@rationale A normalized entity is not evidence and an inference is not an
           observation. Separate durable records make each judgment traceable,
           challengeable, and revisable without rewriting collected evidence.

@decision DEC-ANALYTIC-CONFIDENCE-001
@title Analytic confidence and likelihood use separate records and vocabularies
@status accepted
@rationale Confidence evaluates the evidentiary and logical basis of a judgment;
           likelihood estimates the proposition. Combining them into one score
           creates false precision and hides weak sourcing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import select

from adversary_pursuit.models.database import (
    AnalyticAssertion,
    AnalyticConfidenceAssessment,
    AnalyticContradiction,
    AnalyticEvidenceLink,
    AnalyticHypothesis,
    EvidenceObservation,
    InvestigationQuestion,
    LikelihoodAssessment,
)


class AuthorKind(StrEnum):
    HUMAN = "human"
    MODEL = "model"
    SYSTEM = "system"


class AssertionType(StrEnum):
    INFERRED = "inferred"
    ASSUMED = "assumed"
    JUDGMENT = "judgment"


class HypothesisStatus(StrEnum):
    PROPOSED = "proposed"
    RETAINED = "retained"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class EvidenceStance(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"


class ConfidenceLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class Materiality(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ContradictionStatus(StrEnum):
    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"


class LikelihoodTerm(StrEnum):
    ALMOST_NO_CHANCE = "almost_no_chance"
    VERY_UNLIKELY = "very_unlikely"
    UNLIKELY = "unlikely"
    ROUGHLY_EVEN_CHANCE = "roughly_even_chance"
    LIKELY = "likely"
    VERY_LIKELY = "very_likely"
    ALMOST_CERTAIN = "almost_certain"


LIKELIHOOD_RANGES: dict[LikelihoodTerm, tuple[float, float]] = {
    LikelihoodTerm.ALMOST_NO_CHANCE: (0.01, 0.05),
    LikelihoodTerm.VERY_UNLIKELY: (0.05, 0.20),
    LikelihoodTerm.UNLIKELY: (0.20, 0.45),
    LikelihoodTerm.ROUGHLY_EVEN_CHANCE: (0.45, 0.55),
    LikelihoodTerm.LIKELY: (0.55, 0.80),
    LikelihoodTerm.VERY_LIKELY: (0.80, 0.95),
    LikelihoodTerm.ALMOST_CERTAIN: (0.95, 0.99),
}


class AnalyticLedger:
    """Persist and retrieve the epistemic graph for one active workspace."""

    def __init__(self, workspace_manager: Any) -> None:
        self._workspace = workspace_manager

    def create_question(self, text: str, *, created_by: AuthorKind = AuthorKind.HUMAN) -> str:
        text = _required(text, "question")
        question_id = _new_id("question")
        with self._workspace.get_session() as session:
            session.add(
                InvestigationQuestion(
                    id=question_id,
                    text=text,
                    status="open",
                    created_by=created_by.value,
                )
            )
            session.commit()
        return question_id

    def create_assertion(
        self,
        statement: str,
        *,
        assertion_type: AssertionType,
        author_kind: AuthorKind = AuthorKind.HUMAN,
        subject_ref: str | None = None,
        predicate: str | None = None,
        object_ref: str | None = None,
        object_value: str | None = None,
        method: str | None = None,
    ) -> str:
        assertion_id = _new_id("assertion")
        with self._workspace.get_session() as session:
            session.add(
                AnalyticAssertion(
                    id=assertion_id,
                    statement=_required(statement, "assertion"),
                    assertion_type=assertion_type.value,
                    status="proposed" if author_kind is AuthorKind.MODEL else "active",
                    subject_ref=subject_ref,
                    predicate=predicate,
                    object_ref=object_ref,
                    object_value=object_value,
                    author_kind=author_kind.value,
                    method=method,
                )
            )
            session.commit()
        return assertion_id

    def create_hypothesis(
        self,
        question_id: str,
        statement: str,
        *,
        author_kind: AuthorKind = AuthorKind.HUMAN,
    ) -> str:
        hypothesis_id = _new_id("hypothesis")
        with self._workspace.get_session() as session:
            if session.get(InvestigationQuestion, question_id) is None:
                raise ValueError(f"Unknown investigation question: {question_id}")
            session.add(
                AnalyticHypothesis(
                    id=hypothesis_id,
                    question_id=question_id,
                    statement=_required(statement, "hypothesis"),
                    status=HypothesisStatus.PROPOSED.value,
                    author_kind=author_kind.value,
                )
            )
            session.commit()
        return hypothesis_id

    def set_hypothesis_status(
        self,
        hypothesis_id: str,
        status: HypothesisStatus,
        *,
        decided_by: AuthorKind = AuthorKind.HUMAN,
    ) -> None:
        if decided_by is not AuthorKind.HUMAN:
            raise ValueError("Only an explicit human action may disposition a hypothesis.")
        with self._workspace.get_session() as session:
            row = session.get(AnalyticHypothesis, hypothesis_id)
            if row is None:
                raise ValueError(f"Unknown hypothesis: {hypothesis_id}")
            row.status = status.value
            row.updated_at = datetime.now(timezone.utc)
            session.commit()

    def link_evidence(
        self,
        *,
        source_kind: str,
        source_id: str,
        target_kind: str,
        target_id: str,
        stance: EvidenceStance,
        rationale: str,
    ) -> int:
        if source_kind not in {"observation", "assertion"}:
            raise ValueError("Evidence source_kind must be observation or assertion.")
        if target_kind not in {"assertion", "hypothesis"}:
            raise ValueError("Evidence target_kind must be assertion or hypothesis.")
        with self._workspace.get_session() as session:
            _require_record(session, source_kind, source_id)
            _require_record(session, target_kind, target_id)
            row = AnalyticEvidenceLink(
                source_kind=source_kind,
                source_id=source_id,
                target_kind=target_kind,
                target_id=target_id,
                stance=stance.value,
                rationale=_required(rationale, "evidence-link rationale"),
            )
            session.add(row)
            session.commit()
            return int(row.id)

    def assess_confidence(
        self,
        *,
        target_kind: str,
        target_id: str,
        level: ConfidenceLevel,
        rationale: str,
        factors: dict[str, Any] | None = None,
        assessed_by: AuthorKind = AuthorKind.HUMAN,
    ) -> str:
        assessment_id = _new_id("confidence")
        with self._workspace.get_session() as session:
            _require_judgment_target(session, target_kind, target_id)
            session.add(
                AnalyticConfidenceAssessment(
                    id=assessment_id,
                    target_kind=target_kind,
                    target_id=target_id,
                    level=level.value,
                    rationale=_required(rationale, "confidence rationale"),
                    factors=factors or {},
                    assessed_by=assessed_by.value,
                )
            )
            session.commit()
        return assessment_id

    def assess_likelihood(
        self,
        *,
        target_kind: str,
        target_id: str,
        term: LikelihoodTerm,
        rationale: str,
        assessed_by: AuthorKind = AuthorKind.HUMAN,
    ) -> str:
        assessment_id = _new_id("likelihood")
        probability_min, probability_max = LIKELIHOOD_RANGES[term]
        with self._workspace.get_session() as session:
            _require_judgment_target(session, target_kind, target_id)
            session.add(
                LikelihoodAssessment(
                    id=assessment_id,
                    target_kind=target_kind,
                    target_id=target_id,
                    term=term.value,
                    probability_min=probability_min,
                    probability_max=probability_max,
                    rationale=_required(rationale, "likelihood rationale"),
                    assessed_by=assessed_by.value,
                )
            )
            session.commit()
        return assessment_id

    def record_contradiction(
        self,
        *,
        left_kind: str,
        left_id: str,
        right_kind: str,
        right_id: str,
        summary: str,
        resolution_required: str,
        materiality: Materiality = Materiality.MEDIUM,
    ) -> str:
        if left_kind == right_kind and left_id == right_id:
            raise ValueError("A record cannot contradict itself.")
        contradiction_id = _new_id("contradiction")
        with self._workspace.get_session() as session:
            _require_record(session, left_kind, left_id)
            _require_record(session, right_kind, right_id)
            session.add(
                AnalyticContradiction(
                    id=contradiction_id,
                    left_kind=left_kind,
                    left_id=left_id,
                    right_kind=right_kind,
                    right_id=right_id,
                    summary=_required(summary, "contradiction summary"),
                    materiality=materiality.value,
                    status=ContradictionStatus.UNRESOLVED.value,
                    resolution_required=_required(
                        resolution_required,
                        "contradiction resolution requirement",
                    ),
                )
            )
            session.commit()
        return contradiction_id

    def resolve_contradiction(
        self,
        contradiction_id: str,
        resolution_note: str,
        *,
        status: ContradictionStatus = ContradictionStatus.RESOLVED,
    ) -> None:
        if status is ContradictionStatus.UNRESOLVED:
            raise ValueError("Resolution status must be resolved or superseded.")
        with self._workspace.get_session() as session:
            row = session.get(AnalyticContradiction, contradiction_id)
            if row is None:
                raise ValueError(f"Unknown contradiction: {contradiction_id}")
            row.status = status.value
            row.resolution_note = _required(resolution_note, "contradiction resolution note")
            row.resolved_at = datetime.now(timezone.utc)
            session.commit()

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        """Return the exact persisted analytic records for UI and export adapters."""

        with self._workspace.get_session() as session:
            return {
                "questions": [
                    _row_dict(row)
                    for row in session.execute(
                        select(InvestigationQuestion).order_by(InvestigationQuestion.created_at)
                    ).scalars()
                ],
                "hypotheses": [
                    _row_dict(row)
                    for row in session.execute(
                        select(AnalyticHypothesis).order_by(AnalyticHypothesis.created_at)
                    ).scalars()
                ],
                "assertions": [
                    _row_dict(row)
                    for row in session.execute(
                        select(AnalyticAssertion).order_by(AnalyticAssertion.created_at)
                    ).scalars()
                ],
                "evidence_links": [
                    _row_dict(row)
                    for row in session.execute(
                        select(AnalyticEvidenceLink).order_by(AnalyticEvidenceLink.id)
                    ).scalars()
                ],
                "confidence": [
                    _row_dict(row)
                    for row in session.execute(
                        select(AnalyticConfidenceAssessment).order_by(
                            AnalyticConfidenceAssessment.created_at
                        )
                    ).scalars()
                ],
                "likelihood": [
                    _row_dict(row)
                    for row in session.execute(
                        select(LikelihoodAssessment).order_by(LikelihoodAssessment.created_at)
                    ).scalars()
                ],
                "contradictions": [
                    _row_dict(row)
                    for row in session.execute(
                        select(AnalyticContradiction).order_by(AnalyticContradiction.created_at)
                    ).scalars()
                ],
            }


def _required(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{label} must not be empty.")
    return cleaned


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _require_judgment_target(session: Any, target_kind: str, target_id: str) -> None:
    if target_kind not in {"assertion", "hypothesis"}:
        raise ValueError("Assessment target_kind must be assertion or hypothesis.")
    _require_record(session, target_kind, target_id)


def _require_record(session: Any, kind: str, record_id: str) -> None:
    models = {
        "observation": EvidenceObservation,
        "assertion": AnalyticAssertion,
        "hypothesis": AnalyticHypothesis,
        "question": InvestigationQuestion,
    }
    model = models.get(kind)
    if model is None:
        raise ValueError(f"Unsupported analytic record kind: {kind}")
    if session.get(model, record_id) is None:
        raise ValueError(f"Unknown {kind}: {record_id}")


def _row_dict(row: Any) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}
