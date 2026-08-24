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

import hashlib
import json
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
    EXTERNAL_TOOL = "external_tool"


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

    def create_framework_gap_requirement(
        self,
        *,
        framework: str,
        framework_version: str,
        content_id: str,
        statement: str,
        criteria: dict[str, Any],
        investigation_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Persist one explicit framework gap as an information requirement.

        The framework reference is planning provenance, not evidence. Repeating
        the same command returns the existing lifecycle item so UI retries do
        not create duplicate requirements.
        """

        framework_ref = ":".join(
            (
                _required(framework, "framework"),
                _required(framework_version, "framework version"),
                _required(content_id, "framework content ID"),
            )
        )
        from adversary_pursuit.core.information_requirements import (
            validate_requirement_criteria,
        )

        validated_criteria = validate_requirement_criteria(criteria)
        with self._workspace.get_session() as session:
            investigation = self._ensure_investigation(session, investigation_id)
            existing = session.execute(
                select(AnalyticLifecycleItem).where(
                    AnalyticLifecycleItem.investigation_id == investigation.id,
                    AnalyticLifecycleItem.item_type
                    == LifecycleItemType.COLLECTION_REQUIREMENT.value,
                    AnalyticLifecycleItem.record_kind == "framework_gap",
                    AnalyticLifecycleItem.record_id == framework_ref,
                )
            ).scalar_one_or_none()
            if existing is not None:
                return _row_dict(existing), False
            row = self._link_lifecycle_item(
                session,
                investigation=investigation,
                item_type=LifecycleItemType.COLLECTION_REQUIREMENT,
                record_kind="framework_gap",
                record_id=framework_ref,
                statement=_required(statement, "framework intelligence requirement"),
                criteria=validated_criteria,
                author_kind=AuthorKind.HUMAN,
            )
            session.commit()
            return _row_dict(row), True

    def framework_gap_requirements(self) -> list[dict[str, Any]]:
        """Return recorded framework-gap requirements from the active workspace."""

        with self._workspace.get_session() as session:
            rows = session.execute(
                select(AnalyticLifecycleItem)
                .where(AnalyticLifecycleItem.record_kind == "framework_gap")
                .order_by(AnalyticLifecycleItem.created_at)
            ).scalars()
            return [_row_dict(row) for row in rows]

    def enqueue_scot_pivot_request(
        self,
        request: dict[str, Any],
        *,
        approved_by: str,
        investigation_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Persist one accepted SCOT pivot as a collection requirement."""

        request_id = _required(str(request.get("request_id") or ""), "SCOT pivot request ID")
        indicator = _required(str(request.get("indicator") or ""), "SCOT pivot indicator")
        approver = _required(approved_by, "SCOT pivot approver")
        if len(approver) > 254:
            raise ValueError("SCOT pivot approver exceeds the supported length")
        request_copy = json.loads(json.dumps(request, sort_keys=True, default=str))
        now = datetime.now(timezone.utc)
        with self._workspace.get_session() as session:
            existing = session.execute(
                select(AnalyticLifecycleItem).where(
                    AnalyticLifecycleItem.record_kind == "enrichment_request",
                    AnalyticLifecycleItem.record_id == request_id,
                )
            ).scalar_one_or_none()
            if existing is not None:
                return _row_dict(existing), False
            investigation = self._ensure_investigation(session, investigation_id)
            row = self._link_lifecycle_item(
                session,
                investigation=investigation,
                item_type=LifecycleItemType.COLLECTION_REQUIREMENT,
                record_kind="enrichment_request",
                record_id=request_id,
                statement=f"Enrich {indicator} from an approved SCOT pivot request.",
                criteria={
                    "queue_state": "queued",
                    "origin_system": "scot4",
                    "approved_by": approver,
                    "request": request_copy,
                    "truth_kind": "operator-request",
                    "history": [
                        {
                            "state": "queued",
                            "recorded_at": now.isoformat(),
                            "actor": approver,
                        }
                    ],
                },
                evidence_refs=[
                    {
                        "kind": "scot-object",
                        "ref": (
                            f"{request_copy.get('scot_object_type')}:"
                            f"{request_copy.get('scot_object_id')}"
                        ),
                    }
                ],
                author_kind=AuthorKind.HUMAN,
            )
            session.commit()
            return _row_dict(row), True

    def enrichment_requests(self) -> list[dict[str, Any]]:
        """Return the durable enrichment queue in creation order."""

        with self._workspace.get_session() as session:
            rows = session.execute(
                select(AnalyticLifecycleItem)
                .where(AnalyticLifecycleItem.record_kind == "enrichment_request")
                .order_by(AnalyticLifecycleItem.created_at)
            ).scalars()
            return [_row_dict(row) for row in rows]

    def transition_enrichment_request(
        self,
        request_id: str,
        state: str,
        *,
        investigation_id: str | None = None,
        actor: AuthorKind = AuthorKind.SYSTEM,
    ) -> dict[str, Any]:
        """Advance one queued request through the shared enrichment lifecycle."""

        transitions = {
            "queued": {"running", "cancelled"},
            "running": {"succeeded", "empty", "failed", "cancelled"},
        }
        normalized_state = state.strip().casefold()
        with self._workspace.get_session() as session:
            row = session.execute(
                select(AnalyticLifecycleItem).where(
                    AnalyticLifecycleItem.record_kind == "enrichment_request",
                    AnalyticLifecycleItem.record_id == request_id,
                )
            ).scalar_one_or_none()
            if row is None:
                raise ValueError(f"Unknown enrichment request: {request_id}")
            criteria = dict(row.criteria or {})
            current = str(criteria.get("queue_state") or "queued")
            if normalized_state == current:
                return _row_dict(row)
            if normalized_state not in transitions.get(current, set()):
                raise ValueError(
                    f"Invalid enrichment request transition: {current} -> {normalized_state}"
                )
            now = datetime.now(timezone.utc)
            history = list(criteria.get("history") or [])
            history.append(
                {
                    "state": normalized_state,
                    "recorded_at": now.isoformat(),
                    "actor": actor.value,
                    "investigation_id": investigation_id,
                }
            )
            criteria["queue_state"] = normalized_state
            criteria["history"] = history
            if investigation_id:
                criteria["investigation_id"] = investigation_id
            row.criteria = criteria
            row.status = (
                LifecycleItemStatus.OPEN.value
                if normalized_state in {"queued", "running"}
                else (
                    LifecycleItemStatus.SATISFIED.value
                    if normalized_state in {"succeeded", "empty"}
                    else LifecycleItemStatus.REJECTED.value
                )
            )
            row.updated_at = now
            if normalized_state not in {"queued", "running"}:
                row.resolved_at = now
            session.commit()
            return _row_dict(row)

    def record_external_analysis_proposal(
        self,
        *,
        provider: str,
        operation: str,
        statement: str,
        payload_sha256: str,
        provenance_refs: tuple[str, ...],
        caveats: tuple[str, ...],
        details: dict[str, Any],
        observation_refs: tuple[str, ...] = (),
        investigation_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Record a deterministic tool result as pending analytic work, not evidence."""
        normalized_provider = _required(provider, "external analysis provider")
        if normalized_provider not in {"go-roast", "nucleotide"}:
            raise ValueError("Unsupported external analysis provider.")
        normalized_operation = _required(operation, "external analysis operation")
        normalized_statement = _required(statement, "external analysis statement")
        normalized_digest = payload_sha256.strip().casefold()
        if len(normalized_digest) != 64 or any(
            character not in "0123456789abcdef" for character in normalized_digest
        ):
            raise ValueError("External analysis payload requires a SHA-256 digest.")
        normalized_refs = tuple(
            sorted({_required(ref, "provenance reference") for ref in provenance_refs})
        )
        if not normalized_refs:
            raise ValueError("External analysis proposals require provenance.")
        normalized_caveats = tuple(
            sorted({_required(caveat, "external analysis caveat") for caveat in caveats})
        )
        normalized_observations = tuple(
            sorted({_required(ref, "observation reference") for ref in observation_refs})
        )
        detail_copy = json.loads(json.dumps(details, sort_keys=True, default=str))
        encoded_details = json.dumps(detail_copy, sort_keys=True, separators=(",", ":"))
        if len(encoded_details.encode()) > 64_000:
            raise ValueError("External analysis proposal details exceed 64 KB.")
        record_basis = {
            "provider": normalized_provider,
            "operation": normalized_operation,
            "statement": normalized_statement,
            "payload_sha256": normalized_digest,
            "provenance_refs": normalized_refs,
            "observation_refs": normalized_observations,
            "details": detail_copy,
        }
        record_id = (
            "external-analysis-"
            + hashlib.sha256(
                json.dumps(record_basis, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()[:32]
        )
        with self._workspace.get_session() as session:
            missing_observations = [
                ref for ref in normalized_observations if session.get(EvidenceObservation, ref) is None
            ]
            if missing_observations:
                raise ValueError(
                    "External analysis references unknown observations: "
                    + ", ".join(missing_observations)
                )
            investigation = self._ensure_investigation(session, investigation_id)
            existing = session.execute(
                select(AnalyticLifecycleItem).where(
                    AnalyticLifecycleItem.investigation_id == investigation.id,
                    AnalyticLifecycleItem.record_kind == "external_analysis",
                    AnalyticLifecycleItem.record_id == record_id,
                )
            ).scalar_one_or_none()
            if existing is not None:
                return _row_dict(existing), False
            row = self._link_lifecycle_item(
                session,
                investigation=investigation,
                item_type=LifecycleItemType.ASSERTION,
                record_kind="external_analysis",
                record_id=record_id,
                statement=normalized_statement,
                criteria={
                    "provider": normalized_provider,
                    "operation": normalized_operation,
                    "payload_sha256": normalized_digest,
                    "caveats": list(normalized_caveats),
                    "details": detail_copy,
                    "reviews": [],
                    "truth_kind": "external-derived-proposal",
                },
                evidence_refs=[
                    *(
                        {"kind": "external-tool-receipt", "ref": ref}
                        for ref in normalized_refs
                    ),
                    *(
                        {"kind": "observation", "ref": ref}
                        for ref in normalized_observations
                    ),
                ],
                author_kind=AuthorKind.EXTERNAL_TOOL,
            )
            session.commit()
            return _row_dict(row), True

    def external_analysis_proposals(self) -> list[dict[str, Any]]:
        """Return reviewable external-derived proposals in creation order."""
        with self._workspace.get_session() as session:
            rows = session.execute(
                select(AnalyticLifecycleItem)
                .where(AnalyticLifecycleItem.record_kind == "external_analysis")
                .order_by(AnalyticLifecycleItem.created_at)
            ).scalars()
            return [_row_dict(row) for row in rows]

    def review_external_analysis_proposal(
        self,
        proposal_id: str,
        *,
        disposition: AnalystDisposition,
        reason: str,
        decided_by: AuthorKind = AuthorKind.HUMAN,
    ) -> dict[str, Any]:
        """Record an explicit human disposition while retaining tool caveats."""
        if decided_by is not AuthorKind.HUMAN:
            raise ValueError("Only an explicit human action may review external analysis.")
        if disposition not in {AnalystDisposition.ACCEPTED, AnalystDisposition.REJECTED}:
            raise ValueError("External analysis must be explicitly accepted or rejected.")
        normalized_reason = _required(reason, "external analysis review reason")
        with self._workspace.get_session() as session:
            row = session.execute(
                select(AnalyticLifecycleItem).where(
                    AnalyticLifecycleItem.record_kind == "external_analysis",
                    AnalyticLifecycleItem.record_id == proposal_id,
                )
            ).scalar_one_or_none()
            if row is None:
                raise ValueError(f"Unknown external analysis proposal: {proposal_id}")
            criteria = dict(row.criteria or {})
            reviews = list(criteria.get("reviews") or [])
            reviews.append(
                {
                    "disposition": disposition.value,
                    "reason": normalized_reason,
                    "decided_by": decided_by.value,
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            criteria["reviews"] = reviews
            row.criteria = criteria
            row.analyst_disposition = disposition.value
            row.status = (
                LifecycleItemStatus.SATISFIED.value
                if disposition is AnalystDisposition.ACCEPTED
                else LifecycleItemStatus.REJECTED.value
            )
            row.updated_at = datetime.now(timezone.utc)
            row.resolved_at = row.updated_at
            session.commit()
            return _row_dict(row)

    def materialize_external_analysis_proposal(
        self,
        proposal_id: str,
        *,
        rationale: str,
        decided_by: AuthorKind = AuthorKind.HUMAN,
    ) -> dict[str, Any]:
        """Promote an accepted tool proposal to a sourced inferred assertion.

        Materialization never creates an observation or an authoritative entity
        relationship. The external tool remains the assertion author, while the
        human review and this explicit promotion are retained in lifecycle
        provenance.
        """

        if decided_by is not AuthorKind.HUMAN:
            raise ValueError("Only an explicit human action may materialize external analysis.")
        normalized_rationale = _required(rationale, "external analysis materialization rationale")
        now = datetime.now(timezone.utc)
        with self._workspace.get_session() as session:
            proposal = session.execute(
                select(AnalyticLifecycleItem).where(
                    AnalyticLifecycleItem.record_kind == "external_analysis",
                    AnalyticLifecycleItem.record_id == proposal_id,
                )
            ).scalar_one_or_none()
            if proposal is None:
                raise ValueError(f"Unknown external analysis proposal: {proposal_id}")
            if (
                proposal.analyst_disposition != AnalystDisposition.ACCEPTED.value
                or proposal.status != LifecycleItemStatus.SATISFIED.value
            ):
                raise ValueError(
                    "External analysis must be explicitly accepted before materialization."
                )

            proposal_criteria = dict(proposal.criteria or {})
            assertion_id = (
                "assertion-external-" + hashlib.sha256(proposal_id.encode()).hexdigest()[:32]
            )
            recorded_assertion_id = proposal_criteria.get("materialized_assertion_id")
            if recorded_assertion_id and recorded_assertion_id != assertion_id:
                raise RuntimeError("External analysis materialization lineage is inconsistent.")

            assertion = session.get(AnalyticAssertion, assertion_id)
            lifecycle = session.execute(
                select(AnalyticLifecycleItem).where(
                    AnalyticLifecycleItem.investigation_id == proposal.investigation_id,
                    AnalyticLifecycleItem.record_kind == "assertion",
                    AnalyticLifecycleItem.record_id == assertion_id,
                )
            ).scalar_one_or_none()
            if assertion is not None or lifecycle is not None:
                if assertion is None or lifecycle is None:
                    raise RuntimeError("External analysis materialization is incomplete.")
                return {
                    "created": False,
                    "proposal": _row_dict(proposal),
                    "assertion": _row_dict(assertion),
                    "lifecycle_item": _row_dict(lifecycle),
                }

            components = _external_assertion_components(proposal_criteria)
            assertion = AnalyticAssertion(
                id=assertion_id,
                statement=_required(proposal.statement or "", "external analysis statement"),
                assertion_type=AssertionType.INFERRED.value,
                status="active",
                subject_ref=components["subject_ref"],
                predicate=components["predicate"],
                object_ref=components["object_ref"],
                object_value=components["object_value"],
                author_kind=AuthorKind.EXTERNAL_TOOL.value,
                method=(
                    f"external-analysis:{proposal_criteria['provider']}:"
                    f"{proposal_criteria['operation']}"
                ),
            )
            session.add(assertion)
            session.flush()
            investigation = session.get(AnalyticInvestigation, proposal.investigation_id)
            if investigation is None:
                raise RuntimeError("External analysis proposal references a missing investigation.")
            lifecycle = self._link_lifecycle_item(
                session,
                investigation=investigation,
                item_type=LifecycleItemType.ASSERTION,
                record_kind="assertion",
                record_id=assertion_id,
                statement=assertion.statement,
                criteria={
                    "source_proposal_id": proposal_id,
                    "provider": proposal_criteria["provider"],
                    "operation": proposal_criteria["operation"],
                    "truth_kind": "external-derived-assertion",
                    "analyst_rationale": normalized_rationale,
                    "caveats": list(proposal_criteria.get("caveats") or []),
                    "details": proposal_criteria.get("details") or {},
                    "typed_components": components,
                },
                evidence_refs=[
                    *list(proposal.evidence_refs or []),
                    {"kind": "external-analysis-proposal", "ref": proposal_id},
                ],
                author_kind=AuthorKind.EXTERNAL_TOOL,
            )
            lifecycle.status = LifecycleItemStatus.SATISFIED.value
            lifecycle.analyst_disposition = AnalystDisposition.ACCEPTED.value
            lifecycle.resolved_at = now
            lifecycle.updated_at = now
            proposal_criteria["materialized_assertion_id"] = assertion_id
            proposal_criteria["materialization"] = {
                "rationale": normalized_rationale,
                "decided_by": decided_by.value,
                "recorded_at": now.isoformat(),
                "truth_kind": "external-derived-assertion",
            }
            proposal.criteria = proposal_criteria
            proposal.updated_at = now
            session.commit()
            return {
                "created": True,
                "proposal": _row_dict(proposal),
                "assertion": _row_dict(assertion),
                "lifecycle_item": _row_dict(lifecycle),
            }

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

    def prioritize_information_requirement(
        self,
        item_id: str,
        priority: int,
        *,
        criteria: dict[str, Any] | None = None,
        decided_by: AuthorKind = AuthorKind.HUMAN,
    ) -> None:
        """Set human-owned priority and optional transparent scoring factors."""

        if decided_by is not AuthorKind.HUMAN:
            raise ValueError("Only an explicit human action may prioritize analytic work.")
        if isinstance(priority, bool) or not isinstance(priority, int) or not 0 <= priority <= 100:
            raise ValueError("Information-requirement priority must be an integer from 0 to 100.")
        if criteria is not None:
            from adversary_pursuit.core.information_requirements import (
                validate_requirement_criteria,
            )

            criteria = validate_requirement_criteria(criteria)
        with self._workspace.get_session() as session:
            row = session.get(AnalyticLifecycleItem, item_id)
            if row is None:
                raise ValueError(f"Unknown lifecycle item: {item_id}")
            if row.item_type != LifecycleItemType.COLLECTION_REQUIREMENT.value:
                raise ValueError("Only a collection requirement may receive requirement priority.")
            row.priority = priority
            if criteria is not None:
                row.criteria = criteria
            row.updated_at = datetime.now(timezone.utc)
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
                if author_kind in {AuthorKind.MODEL, AuthorKind.EXTERNAL_TOOL}
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


def _external_assertion_components(criteria: dict[str, Any]) -> dict[str, str | None]:
    """Map a supported external proposal to typed assertion fields."""

    provider = criteria.get("provider")
    operation = criteria.get("operation")
    details = criteria.get("details")
    if provider not in {"go-roast", "nucleotide"} or not isinstance(details, dict):
        raise ValueError("External analysis proposal has unsupported materialization data.")

    if provider == "go-roast" and operation == "decode-relationship":
        source = details.get("source_node")
        target = details.get("target_node")
        relationship = details.get("relationship")
        if not isinstance(source, dict) or not isinstance(target, dict):
            raise ValueError("go-roast proposal is missing typed relationship nodes.")
        return {
            "subject_ref": _required(str(source.get("id") or ""), "go-roast source node"),
            "predicate": _required(str(relationship or ""), "go-roast relationship"),
            "object_ref": _required(str(target.get("id") or ""), "go-roast target node"),
            "object_value": str(target.get("value")) if target.get("value") is not None else None,
        }

    if provider == "nucleotide" and operation == "url-template-lookup":
        url = _required(str(details.get("url") or ""), "Nucleotide lookup URL")
        attribution = _required(
            str(details.get("attribution") or ""), "Nucleotide lookup attribution"
        )
        template_id = details.get("template_id")
        return {
            "subject_ref": url,
            "predicate": "has-nucleotide-template-attribution",
            "object_ref": None,
            "object_value": str(template_id) if template_id else attribution,
        }

    if provider == "nucleotide" and operation == "actor-behavior-fingerprint":
        batch = _required(
            str(details.get("analyst_grouped_batch") or ""),
            "Nucleotide analyst-grouped batch",
        )
        fingerprint = _required(
            str(details.get("fingerprint_sha256") or ""),
            "Nucleotide fingerprint digest",
        )
        return {
            "subject_ref": batch,
            "predicate": "has-nucleotide-behavior-fingerprint",
            "object_ref": None,
            "object_value": fingerprint,
        }

    raise ValueError(f"Unsupported external analysis materialization: {provider} {operation}.")


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
