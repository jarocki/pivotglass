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
    AnalyticInvestigation,
    AnalyticLifecycleItem,
    AnalyticMethodRun,
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


class InvestigationStatus(StrEnum):
    FRAMING = "framing"
    COLLECTING = "collecting"
    ANALYZING = "analyzing"
    CONCLUDED = "concluded"
    SUSPENDED = "suspended"


class LifecycleItemType(StrEnum):
    QUESTION = "question"
    HYPOTHESIS = "hypothesis"
    ASSUMPTION = "assumption"
    ASSERTION = "assertion"
    PREDICTION = "prediction"
    SIGNPOST = "signpost"
    COLLECTION_REQUIREMENT = "collection_requirement"
    STOP_CONDITION = "stop_condition"
    OBSERVATION = "observation"
    METHOD_RUN = "method_run"
    CONCLUSION = "conclusion"
    LIMITATION = "limitation"
    KNOWLEDGE_GAP = "knowledge_gap"


class LifecycleItemStatus(StrEnum):
    OPEN = "open"
    SATISFIED = "satisfied"
    REJECTED = "rejected"
    RESOLVED = "resolved"
    DEFERRED = "deferred"


class AnalystDisposition(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REVISED = "revised"


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

CONFIDENCE_FACTOR_KEYS = (
    "source_quality",
    "source_independence",
    "corroboration",
    "assumptions",
    "knowledge_gaps",
    "analytic_rigor",
)


class AnalyticLedger:
    """Persist and retrieve the epistemic graph for one active workspace."""

    def __init__(self, workspace_manager: Any) -> None:
        self._workspace = workspace_manager

    def create_investigation(
        self,
        title: str,
        *,
        purpose: str,
        scope: str,
        created_by: AuthorKind = AuthorKind.HUMAN,
    ) -> str:
        investigation_id = _new_id("investigation")
        with self._workspace.get_session() as session:
            session.add(
                AnalyticInvestigation(
                    id=investigation_id,
                    title=_required(title, "investigation title"),
                    purpose=_required(purpose, "investigation purpose"),
                    scope=_required(scope, "investigation scope"),
                    status=InvestigationStatus.FRAMING.value,
                    created_by=created_by.value,
                )
            )
            session.commit()
        return investigation_id

    def active_investigation(self) -> dict[str, Any] | None:
        """Return the newest non-closed investigation, if one exists."""

        with self._workspace.get_session() as session:
            row = (
                session.execute(
                    select(AnalyticInvestigation)
                    .where(
                        AnalyticInvestigation.status.notin_(
                            [
                                InvestigationStatus.CONCLUDED.value,
                                InvestigationStatus.SUSPENDED.value,
                            ]
                        )
                    )
                    .order_by(AnalyticInvestigation.created_at.desc())
                )
                .scalars()
                .first()
            )
            return _row_dict(row) if row is not None else None

    def create_question(
        self,
        text: str,
        *,
        created_by: AuthorKind = AuthorKind.HUMAN,
        investigation_id: str | None = None,
    ) -> str:
        text = _required(text, "question")
        question_id = _new_id("question")
        with self._workspace.get_session() as session:
            investigation = self._ensure_investigation(session, investigation_id)
            session.add(
                InvestigationQuestion(
                    id=question_id,
                    text=text,
                    status="open",
                    created_by=created_by.value,
                )
            )
            session.flush()
            self._link_lifecycle_item(
                session,
                investigation=investigation,
                item_type=LifecycleItemType.QUESTION,
                record_kind="question",
                record_id=question_id,
                statement=text,
                author_kind=created_by,
            )
            if investigation.primary_question_id is None:
                investigation.primary_question_id = question_id
                if investigation.title == "Workspace investigation":
                    investigation.title = text
                investigation.updated_at = datetime.now(timezone.utc)
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
        investigation_id: str | None = None,
    ) -> str:
        assertion_id = _new_id("assertion")
        cleaned_statement = _required(statement, "assertion")
        with self._workspace.get_session() as session:
            investigation = self._ensure_investigation(session, investigation_id)
            session.add(
                AnalyticAssertion(
                    id=assertion_id,
                    statement=cleaned_statement,
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
            session.flush()
            item_type = (
                LifecycleItemType.ASSUMPTION
                if assertion_type is AssertionType.ASSUMED
                else LifecycleItemType.ASSERTION
            )
            self._link_lifecycle_item(
                session,
                investigation=investigation,
                item_type=item_type,
                record_kind="assertion",
                record_id=assertion_id,
                statement=cleaned_statement,
                author_kind=author_kind,
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
        cleaned_statement = _required(statement, "hypothesis")
        with self._workspace.get_session() as session:
            question = session.get(InvestigationQuestion, question_id)
            if question is None:
                raise ValueError(f"Unknown investigation question: {question_id}")
            question_link = session.execute(
                select(AnalyticLifecycleItem).where(
                    AnalyticLifecycleItem.record_kind == "question",
                    AnalyticLifecycleItem.record_id == question_id,
                )
            ).scalar_one_or_none()
            if question_link is None:
                investigation = self._ensure_investigation(session)
                self._link_lifecycle_item(
                    session,
                    investigation=investigation,
                    item_type=LifecycleItemType.QUESTION,
                    record_kind="question",
                    record_id=question_id,
                    statement=question.text,
                    author_kind=AuthorKind(question.created_by),
                )
            else:
                investigation = session.get(
                    AnalyticInvestigation,
                    question_link.investigation_id,
                )
                if investigation is None:
                    raise ValueError(f"Question {question_id} references a missing investigation.")
            session.add(
                AnalyticHypothesis(
                    id=hypothesis_id,
                    question_id=question_id,
                    statement=cleaned_statement,
                    status=HypothesisStatus.PROPOSED.value,
                    author_kind=author_kind.value,
                )
            )
            session.flush()
            self._link_lifecycle_item(
                session,
                investigation=investigation,
                item_type=LifecycleItemType.HYPOTHESIS,
                record_kind="hypothesis",
                record_id=hypothesis_id,
                statement=cleaned_statement,
                author_kind=author_kind,
            )
            session.commit()
        return hypothesis_id

    def add_lifecycle_item(
        self,
        investigation_id: str,
        item_type: LifecycleItemType,
        statement: str,
        *,
        criteria: dict[str, Any] | None = None,
        evidence_refs: list[dict[str, Any]] | None = None,
        priority: int = 0,
        author_kind: AuthorKind = AuthorKind.HUMAN,
    ) -> str:
        with self._workspace.get_session() as session:
            investigation = session.get(AnalyticInvestigation, investigation_id)
            if investigation is None:
                raise ValueError(f"Unknown investigation: {investigation_id}")
            row = self._link_lifecycle_item(
                session,
                investigation=investigation,
                item_type=item_type,
                statement=_required(statement, item_type.value.replace("_", " ")),
                criteria=criteria,
                evidence_refs=evidence_refs,
                priority=priority,
                author_kind=author_kind,
            )
            session.commit()
            return str(row.id)

    def link_method_run(
        self,
        question_id: str,
        run_id: str,
        *,
        created_by: AuthorKind,
        statement: str,
    ) -> str:
        """Connect a persisted SAT run to its question's investigation."""

        with self._workspace.get_session() as session:
            question = session.get(InvestigationQuestion, question_id)
            if question is None:
                raise ValueError(f"Unknown investigation question: {question_id}")
            if session.get(AnalyticMethodRun, run_id) is None:
                raise ValueError(f"Unknown method run: {run_id}")
            question_link = session.execute(
                select(AnalyticLifecycleItem).where(
                    AnalyticLifecycleItem.record_kind == "question",
                    AnalyticLifecycleItem.record_id == question_id,
                )
            ).scalar_one_or_none()
            if question_link is None:
                investigation = self._ensure_investigation(session)
                self._link_lifecycle_item(
                    session,
                    investigation=investigation,
                    item_type=LifecycleItemType.QUESTION,
                    record_kind="question",
                    record_id=question_id,
                    statement=question.text,
                    author_kind=AuthorKind(question.created_by),
                )
            else:
                investigation = session.get(
                    AnalyticInvestigation,
                    question_link.investigation_id,
                )
                if investigation is None:
                    raise ValueError(f"Question {question_id} references a missing investigation.")
            row = self._link_lifecycle_item(
                session,
                investigation=investigation,
                item_type=LifecycleItemType.METHOD_RUN,
                record_kind="method_run",
                record_id=run_id,
                statement=_required(statement, "method-run summary"),
                author_kind=created_by,
            )
            session.commit()
            return str(row.id)

    def update_lifecycle_item(
        self,
        item_id: str,
        *,
        status: LifecycleItemStatus | None = None,
        disposition: AnalystDisposition | None = None,
        decided_by: AuthorKind = AuthorKind.HUMAN,
    ) -> None:
        if disposition is not None and decided_by is not AuthorKind.HUMAN:
            raise ValueError("Only an explicit human action may disposition analytic work.")
        if status is None and disposition is None:
            raise ValueError("A lifecycle status or disposition is required.")
        if disposition is AnalystDisposition.PENDING:
            raise ValueError("A disposition must be accepted, rejected, or revised.")
        with self._workspace.get_session() as session:
            row = session.get(AnalyticLifecycleItem, item_id)
            if row is None:
                raise ValueError(f"Unknown lifecycle item: {item_id}")
            now = datetime.now(timezone.utc)
            if status is not None:
                row.status = status.value
                row.resolved_at = None if status is LifecycleItemStatus.OPEN else now
            if disposition is not None:
                row.analyst_disposition = disposition.value
            row.updated_at = now
            session.commit()

    def update_linked_record(
        self,
        record_kind: str,
        record_id: str,
        *,
        status: LifecycleItemStatus | None = None,
        disposition: AnalystDisposition | None = None,
        decided_by: AuthorKind = AuthorKind.HUMAN,
    ) -> None:
        """Update the lifecycle entry that organizes an authoritative record."""

        if disposition is not None and decided_by is not AuthorKind.HUMAN:
            raise ValueError("Only an explicit human action may disposition analytic work.")
        if status is None and disposition is None:
            raise ValueError("A lifecycle status or disposition is required.")
        if disposition is AnalystDisposition.PENDING:
            raise ValueError("A disposition must be accepted, rejected, or revised.")
        with self._workspace.get_session() as session:
            row = session.execute(
                select(AnalyticLifecycleItem).where(
                    AnalyticLifecycleItem.record_kind == record_kind,
                    AnalyticLifecycleItem.record_id == record_id,
                )
            ).scalar_one_or_none()
            if row is None:
                raise ValueError(f"No lifecycle item links {record_kind}: {record_id}")
            now = datetime.now(timezone.utc)
            if status is not None:
                row.status = status.value
                row.resolved_at = None if status is LifecycleItemStatus.OPEN else now
            if disposition is not None:
                row.analyst_disposition = disposition.value
            row.updated_at = now
            session.commit()

    def set_investigation_status(
        self,
        investigation_id: str,
        status: InvestigationStatus,
        *,
        decided_by: AuthorKind = AuthorKind.HUMAN,
    ) -> None:
        if decided_by is not AuthorKind.HUMAN:
            raise ValueError("Only an explicit human action may change investigation state.")
        with self._workspace.get_session() as session:
            row = session.get(AnalyticInvestigation, investigation_id)
            if row is None:
                raise ValueError(f"Unknown investigation: {investigation_id}")
            now = datetime.now(timezone.utc)
            row.status = status.value
            row.updated_at = now
            row.concluded_at = now if status is InvestigationStatus.CONCLUDED else None
            session.commit()

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
            lifecycle = session.execute(
                select(AnalyticLifecycleItem).where(
                    AnalyticLifecycleItem.record_kind == "hypothesis",
                    AnalyticLifecycleItem.record_id == hypothesis_id,
                )
            ).scalar_one_or_none()
            if lifecycle is not None:
                lifecycle_status = {
                    HypothesisStatus.PROPOSED: LifecycleItemStatus.OPEN,
                    HypothesisStatus.RETAINED: LifecycleItemStatus.SATISFIED,
                    HypothesisStatus.REJECTED: LifecycleItemStatus.REJECTED,
                    HypothesisStatus.SUSPENDED: LifecycleItemStatus.DEFERRED,
                }[status]
                lifecycle.status = lifecycle_status.value
                lifecycle.updated_at = datetime.now(timezone.utc)
                lifecycle.resolved_at = (
                    None
                    if lifecycle_status is LifecycleItemStatus.OPEN
                    else datetime.now(timezone.utc)
                )
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
        factors: dict[str, Any],
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
                    factors=_confidence_factors(factors),
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
                "investigations": [
                    _row_dict(row)
                    for row in session.execute(
                        select(AnalyticInvestigation).order_by(AnalyticInvestigation.created_at)
                    ).scalars()
                ],
                "lifecycle_items": [
                    _row_dict(row)
                    for row in session.execute(
                        select(AnalyticLifecycleItem).order_by(AnalyticLifecycleItem.created_at)
                    ).scalars()
                ],
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
                "method_runs": [
                    _row_dict(row)
                    for row in session.execute(
                        select(AnalyticMethodRun).order_by(AnalyticMethodRun.created_at)
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

    def _ensure_investigation(
        self,
        session: Any,
        investigation_id: str | None = None,
    ) -> AnalyticInvestigation:
        if investigation_id is not None:
            row = session.get(AnalyticInvestigation, investigation_id)
            if row is None:
                raise ValueError(f"Unknown investigation: {investigation_id}")
            return row
        row = (
            session.execute(
                select(AnalyticInvestigation)
                .where(
                    AnalyticInvestigation.status.notin_(
                        [
                            InvestigationStatus.CONCLUDED.value,
                            InvestigationStatus.SUSPENDED.value,
                        ]
                    )
                )
                .order_by(AnalyticInvestigation.created_at.desc())
            )
            .scalars()
            .first()
        )
        if row is not None:
            return row
        row = AnalyticInvestigation(
            id=_new_id("investigation"),
            title="Workspace investigation",
            purpose="Answer an evidence-grounded analytic question.",
            scope="Active workspace evidence and analyst-defined boundaries.",
            status=InvestigationStatus.FRAMING.value,
            created_by=AuthorKind.SYSTEM.value,
        )
        session.add(row)
        session.flush()
        return row

    def _link_lifecycle_item(
        self,
        session: Any,
        *,
        investigation: AnalyticInvestigation,
        item_type: LifecycleItemType,
        statement: str,
        author_kind: AuthorKind,
        record_kind: str | None = None,
        record_id: str | None = None,
        criteria: dict[str, Any] | None = None,
        evidence_refs: list[dict[str, Any]] | None = None,
        priority: int = 0,
    ) -> AnalyticLifecycleItem:
        row = AnalyticLifecycleItem(
            id=_new_id("lifecycle"),
            investigation_id=investigation.id,
            item_type=item_type.value,
            record_kind=record_kind,
            record_id=record_id,
            statement=statement,
            status=LifecycleItemStatus.OPEN.value,
            priority=priority,
            criteria=criteria or {},
            evidence_refs=evidence_refs or [],
            author_kind=author_kind.value,
            analyst_disposition=(
                AnalystDisposition.PENDING.value
                if author_kind is AuthorKind.MODEL
                else AnalystDisposition.ACCEPTED.value
            ),
        )
        session.add(row)
        return row


def _required(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{label} must not be empty.")
    return cleaned


def _confidence_factors(factors: dict[str, Any]) -> dict[str, Any]:
    missing = [key for key in CONFIDENCE_FACTOR_KEYS if key not in factors]
    if missing:
        raise ValueError("Confidence factors are missing required fields: " + ", ".join(missing))
    empty = [
        key
        for key in CONFIDENCE_FACTOR_KEYS
        if factors[key] is None or (isinstance(factors[key], str) and not factors[key].strip())
    ]
    if empty:
        raise ValueError("Confidence factors must make unknowns explicit for: " + ", ".join(empty))
    return dict(factors)


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
