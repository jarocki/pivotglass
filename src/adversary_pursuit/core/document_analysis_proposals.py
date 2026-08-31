"""Span-grounded entity, relationship, and behavior proposal authority.

Models and tools may propose. Only an explicit human disposition can accept or
reject a proposal, and acceptance still does not materialize graph truth.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from adversary_pursuit.core.analytic_ledger import ConfidenceLevel
from adversary_pursuit.core.framework_perspectives import ATTACK_ENTERPRISE_V19_2
from adversary_pursuit.models.database import (
    DocumentAnalysisProposal,
    DocumentEntityCandidate,
    DocumentProposalDisposition,
    EvidenceObservation,
)

_ATTACK_ID = re.compile(r"^T\d{4}(?:\.\d{3})?$")
_MAX_PAYLOAD_BYTES = 100_000


class ProposalDisposition(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    decision: Literal["accepted", "rejected", "revised"]
    decided_by: str
    reason: str
    evidence_refs: tuple[str, ...]
    alternative_explanations: tuple[str, ...]
    confidence_level: ConfidenceLevel | None
    confidence_rationale: str | None
    created_at: str


class AnalysisProposalRecord(BaseModel):
    """One immutable proposal with its latest append-only human disposition."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-document-analysis-proposal-1.0"] = (
        "pivotglass-document-analysis-proposal-1.0"
    )
    id: str
    proposal_kind: Literal["entity", "relationship", "behavior"]
    statement: str
    candidate_ids: tuple[str, ...]
    source_spans: tuple[dict[str, Any], ...]
    payload: dict[str, Any]
    framework_comparison: dict[str, Any]
    proposed_by: Literal["human", "model", "tool"]
    model_provider: str | None
    model_id: str | None
    prompt_sha256: str | None
    response_sha256: str | None
    created_at: str
    latest_disposition: ProposalDisposition | None = None
    truth_boundary: str = (
        "This proposal is not observed content, an admitted entity or relationship, a "
        "framework mapping, a newly discovered TTP, or permission to publish."
    )


class DocumentAnalysisProposalAuthority:
    """Record and disposition proposals without materializing them."""

    def __init__(self, workspace_manager: Any) -> None:
        self._workspace = workspace_manager

    def propose(
        self,
        *,
        proposal_kind: Literal["entity", "relationship", "behavior"],
        statement: str,
        candidate_ids: tuple[str, ...],
        payload: dict[str, Any],
        proposed_by: Literal["human", "model", "tool"],
        model_provider: str | None = None,
        model_id: str | None = None,
        prompt_sha256: str | None = None,
        response_sha256: str | None = None,
    ) -> AnalysisProposalRecord:
        statement = statement.strip()
        if not statement or len(statement) > 4_000:
            raise ValueError("Proposal statement must contain 1 to 4,000 characters.")
        unique_candidates = tuple(dict.fromkeys(candidate_ids))
        if not unique_candidates or len(unique_candidates) > 100:
            raise ValueError("A proposal requires 1 to 100 extracted candidate references.")
        if len(json.dumps(payload, sort_keys=True, default=str).encode()) > _MAX_PAYLOAD_BYTES:
            raise ValueError("Proposal payload exceeds the 100,000-byte limit.")
        if proposed_by == "model":
            _require_model_receipt(model_provider, model_id, prompt_sha256, response_sha256)
        elif any((model_provider, model_id, prompt_sha256, response_sha256)):
            raise ValueError("Model receipt fields are allowed only for model proposals.")
        with self._workspace.get_session() as session:
            candidates = tuple(
                session.execute(
                    select(DocumentEntityCandidate).where(
                        DocumentEntityCandidate.id.in_(unique_candidates)
                    )
                ).scalars()
            )
            found = {row.id for row in candidates}
            missing = sorted(set(unique_candidates) - found)
            if missing:
                raise ValueError(f"Unknown document candidate references: {', '.join(missing)}")
            by_id = {row.id: row for row in candidates}
            ordered = tuple(by_id[item] for item in unique_candidates)
            _validate_kind_payload(proposal_kind, payload, unique_candidates)
            source_spans = tuple(_source_span(row) for row in ordered)
            framework_comparison = _framework_comparison(proposal_kind, payload)
            identity = json.dumps(
                {
                    "kind": proposal_kind,
                    "statement": statement,
                    "candidate_ids": unique_candidates,
                    "payload": payload,
                    "proposed_by": proposed_by,
                    "model_provider": model_provider,
                    "model_id": model_id,
                    "prompt_sha256": prompt_sha256,
                    "response_sha256": response_sha256,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            proposal_id = f"document-proposal-{hashlib.sha256(identity.encode()).hexdigest()[:32]}"
            existing = session.get(DocumentAnalysisProposal, proposal_id)
            if existing is None:
                session.add(
                    DocumentAnalysisProposal(
                        id=proposal_id,
                        proposal_kind=proposal_kind,
                        statement=statement,
                        candidate_ids=list(unique_candidates),
                        source_spans=list(source_spans),
                        payload=payload,
                        framework_comparison=framework_comparison,
                        proposed_by=proposed_by,
                        model_provider=model_provider,
                        model_id=model_id,
                        prompt_sha256=prompt_sha256,
                        response_sha256=response_sha256,
                    )
                )
                session.commit()
            return self._record(session.get(DocumentAnalysisProposal, proposal_id), session)

    def list(self) -> tuple[AnalysisProposalRecord, ...]:
        with self._workspace.get_session() as session:
            rows = session.execute(
                select(DocumentAnalysisProposal).order_by(
                    DocumentAnalysisProposal.created_at,
                    DocumentAnalysisProposal.id,
                )
            ).scalars()
            return tuple(self._record(row, session) for row in rows)

    def review(
        self,
        proposal_id: str,
        *,
        decision: Literal["accepted", "rejected", "revised"],
        decided_by: str,
        reason: str,
        human_decision: bool,
        evidence_refs: tuple[str, ...] = (),
        alternative_explanations: tuple[str, ...] = (),
        confidence_level: ConfidenceLevel | None = None,
        confidence_rationale: str | None = None,
    ) -> AnalysisProposalRecord:
        if human_decision is not True:
            raise ValueError("Only an explicit human action may disposition a proposal.")
        decided_by = decided_by.strip()
        reason = reason.strip()
        if not decided_by or not reason:
            raise ValueError("Human reviewer and reason are required.")
        with self._workspace.get_session() as session:
            proposal = session.get(DocumentAnalysisProposal, proposal_id)
            if proposal is None:
                raise ValueError("Document analysis proposal was not found.")
            unique_evidence = tuple(dict.fromkeys(evidence_refs))
            alternatives = tuple(
                item.strip() for item in dict.fromkeys(alternative_explanations) if item.strip()
            )
            if decision == "accepted":
                if not unique_evidence:
                    raise ValueError("Acceptance requires at least one admitted evidence reference.")
                if not alternatives:
                    raise ValueError("Acceptance requires at least one alternative explanation.")
                if confidence_level is None or not (confidence_rationale or "").strip():
                    raise ValueError("Acceptance requires formal confidence and rationale.")
                found_evidence = set(
                    session.execute(
                        select(EvidenceObservation.id).where(
                            EvidenceObservation.id.in_(unique_evidence)
                        )
                    ).scalars()
                )
                missing = sorted(set(unique_evidence) - found_evidence)
                if missing:
                    raise ValueError(
                        f"Unknown admitted evidence references: {', '.join(missing)}"
                    )
            disposition = DocumentProposalDisposition(
                id=f"document-proposal-disposition-{uuid.uuid4().hex}",
                proposal_id=proposal.id,
                decision=decision,
                decided_by=decided_by,
                reason=reason,
                evidence_refs=list(unique_evidence),
                alternative_explanations=list(alternatives),
                confidence_level=confidence_level.value if confidence_level else None,
                confidence_rationale=(confidence_rationale or "").strip() or None,
            )
            session.add(disposition)
            session.commit()
            return self._record(proposal, session)

    def _record(
        self,
        row: DocumentAnalysisProposal | None,
        session: Any,
    ) -> AnalysisProposalRecord:
        if row is None:
            raise RuntimeError("Proposal disappeared during persistence.")
        latest = session.execute(
            select(DocumentProposalDisposition)
            .where(DocumentProposalDisposition.proposal_id == row.id)
            .order_by(
                DocumentProposalDisposition.created_at.desc(),
                DocumentProposalDisposition.id.desc(),
            )
            .limit(1)
        ).scalar_one_or_none()
        return AnalysisProposalRecord(
            id=row.id,
            proposal_kind=row.proposal_kind,
            statement=row.statement,
            candidate_ids=tuple(row.candidate_ids),
            source_spans=tuple(row.source_spans),
            payload=row.payload,
            framework_comparison=row.framework_comparison,
            proposed_by=row.proposed_by,
            model_provider=row.model_provider,
            model_id=row.model_id,
            prompt_sha256=row.prompt_sha256,
            response_sha256=row.response_sha256,
            created_at=_iso(row.created_at),
            latest_disposition=_disposition(latest) if latest else None,
        )


def _require_model_receipt(
    provider: str | None,
    model_id: str | None,
    prompt_sha256: str | None,
    response_sha256: str | None,
) -> None:
    if not (provider or "").strip() or not (model_id or "").strip():
        raise ValueError("Model proposals require provider and model ID.")
    for label, value in (("prompt", prompt_sha256), ("response", response_sha256)):
        if value is None or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError(f"Model proposals require a lowercase SHA-256 {label} receipt.")


def _validate_kind_payload(
    kind: str,
    payload: dict[str, Any],
    candidate_ids: tuple[str, ...],
) -> None:
    if kind == "relationship":
        source = str(payload.get("source_candidate_id", ""))
        target = str(payload.get("target_candidate_id", ""))
        relation = str(payload.get("relationship", "")).strip()
        rationale = str(payload.get("rationale", "")).strip()
        if source not in candidate_ids or target not in candidate_ids or source == target:
            raise ValueError("Relationship proposals require two distinct cited candidates.")
        if not relation or not rationale:
            raise ValueError("Relationship proposals require relation and rationale.")
    if kind == "behavior" and not str(payload.get("behavior", "")).strip():
        raise ValueError("Behavior proposals require a behavior description.")


def _framework_comparison(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    if kind != "behavior":
        return {"state": "not_applicable", "matches": [], "gaps": []}
    attack_candidates = tuple(
        dict.fromkeys(str(item).strip().upper() for item in payload.get("attack_candidates", ()))
    )
    invalid = tuple(item for item in attack_candidates if _ATTACK_ID.fullmatch(item) is None)
    if invalid:
        raise ValueError(f"Invalid ATT&CK candidate identifiers: {', '.join(invalid)}")
    matches = [
        {
            "framework": "attack",
            "framework_version": ATTACK_ENTERPRISE_V19_2.version,
            "content_id": item,
            "state": "unverified_candidate_reference",
            "caveat": "Syntax is valid; pinned catalog content and evidence mapping are not yet verified.",
        }
        for item in attack_candidates
    ]
    if matches:
        return {
            "state": "candidate_matches",
            "matches": matches,
            "gaps": [],
            "caveat": "Candidate references are not accepted framework mappings.",
        }
    return {
        "state": "unmatched_candidate_behavior",
        "matches": [],
        "gaps": [str(payload["behavior"]).strip()],
        "caveat": (
            "Unmatched text is a candidate behavior or framework gap, not an automatically "
            "discovered TTP."
        ),
    }


def _source_span(row: DocumentEntityCandidate) -> dict[str, Any]:
    return {
        "candidate_id": row.id,
        "occurrence_id": row.occurrence_id,
        "parser_receipt_id": row.parser_receipt_id,
        "entity_type": row.entity_type,
        "raw_value": row.raw_value,
        "normalized_value": row.normalized_value,
        "start_char": row.start_char,
        "end_char": row.end_char,
        "start_byte": row.start_byte,
        "end_byte": row.end_byte,
        "start_line": row.start_line,
        "start_column": row.start_column,
        "end_line": row.end_line,
        "end_column": row.end_column,
        "context": row.context,
        "rule_id": row.rule_id,
        "rule_version": row.rule_version,
    }


def _disposition(row: DocumentProposalDisposition) -> ProposalDisposition:
    return ProposalDisposition(
        id=row.id,
        decision=row.decision,
        decided_by=row.decided_by,
        reason=row.reason,
        evidence_refs=tuple(row.evidence_refs),
        alternative_explanations=tuple(row.alternative_explanations),
        confidence_level=(ConfidenceLevel(row.confidence_level) if row.confidence_level else None),
        confidence_rationale=row.confidence_rationale,
        created_at=_iso(row.created_at),
    )


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
