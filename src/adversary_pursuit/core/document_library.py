"""Persistent document library and analyst pivot-trail authorities.

The document library exposes metadata, parser receipts, and exact-span
candidates without returning raw document bytes.  Pivot records describe how
the analyst navigated; they are workflow provenance, not threat evidence.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from adversary_pursuit.core.document_entity_extraction import (
    DocumentEntityExtractionService,
    EntityExtractionLimits,
)
from adversary_pursuit.core.document_ingestion import (
    DocumentIntakeReceipt,
    DocumentIntakeService,
    DocumentLimits,
)
from adversary_pursuit.models.database import (
    DocumentContent,
    DocumentEntityCandidate,
    DocumentOccurrence,
    DocumentParserReceipt,
    PivotTrailEvent,
    StixObject,
)


class DocumentLibraryRecord(BaseModel):
    """Display-safe metadata for one admitted document occurrence."""

    model_config = ConfigDict(frozen=True)

    occurrence_id: str
    filename: str
    source_kind: str
    source_uri: str | None
    detected_media_type: str
    size_bytes: int
    content_sha256: str
    parser_state: str
    candidate_count: int
    acquired_at: str
    operator: str
    reused_content: bool


class DocumentAdmissionReceipt(BaseModel):
    """Loud receipt for explicit browser document admission."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "pivotglass-document-admission-1.0"
    intake: DocumentIntakeReceipt
    extraction_receipt_id: str
    candidate_count: int
    pivot_event_id: str
    truth_boundary: str = (
        "The source document, parser receipt, and text candidates are stored. "
        "Candidates remain reviewable candidates; ingestion does not validate the "
        "document's claims, assign a verdict, or attribute an actor."
    )


class PivotTrailAuthority:
    """Append and read chronological, non-evidentiary analyst navigation."""

    def __init__(self, workspace_manager: Any) -> None:
        self._workspace = workspace_manager

    def record(
        self,
        *,
        to_kind: str,
        to_ref: str,
        to_label: str,
        action: str,
        basis: str,
        provenance_refs: tuple[str, ...] = (),
        from_kind: str | None = None,
        from_ref: str | None = None,
        from_label: str | None = None,
        created_by: str = "human",
    ) -> str:
        if not to_kind.strip() or not to_ref.strip() or not to_label.strip():
            raise ValueError("pivot destination kind, reference, and label are required")
        if not action.strip() or not basis.strip():
            raise ValueError("pivot action and basis are required")
        with self._workspace.get_session() as session:
            previous = session.execute(
                select(PivotTrailEvent).order_by(
                    PivotTrailEvent.created_at.desc(), PivotTrailEvent.id.desc()
                ).limit(1)
            ).scalar_one_or_none()
            effective_from_kind = from_kind or (previous.to_kind if previous else None)
            effective_from_ref = from_ref or (previous.to_ref if previous else None)
            effective_from_label = from_label or (previous.to_label if previous else None)
            # Repeated state refreshes must not fabricate navigation history.
            if (
                previous is not None
                and previous.to_kind == to_kind
                and previous.to_ref == to_ref
                and previous.action == action
            ):
                return previous.id
            event_id = f"pivot-event-{uuid.uuid4().hex}"
            session.add(
                PivotTrailEvent(
                    id=event_id,
                    from_kind=effective_from_kind,
                    from_ref=effective_from_ref,
                    from_label=effective_from_label,
                    to_kind=to_kind.strip(),
                    to_ref=to_ref.strip(),
                    to_label=to_label.strip(),
                    action=action.strip(),
                    basis=basis.strip(),
                    provenance_refs=sorted(set(provenance_refs)),
                    created_by=created_by.strip() or "human",
                )
            )
            session.commit()
            return event_id

    def record_indicator(self, value: str, *, action: str = "investigated") -> str:
        normalized = value.strip()
        with self._workspace.get_session() as session:
            match = session.execute(
                select(StixObject).where(StixObject.value == normalized).limit(1)
            ).scalar_one_or_none()
        record_ref = (
            match.id
            if match is not None
            else f"unresolved-indicator:{hashlib.sha256(normalized.encode()).hexdigest()[:24]}"
        )
        return self.record(
            to_kind="indicator",
            to_ref=record_ref,
            to_label=normalized,
            action=action,
            basis="Explicit analyst investigation action in Pivotglass.",
            provenance_refs=(record_ref,) if match is not None else (),
        )

    def list(self, *, limit: int = 500) -> list[dict[str, Any]]:
        bounded = max(1, min(limit, 2_000))
        with self._workspace.get_session() as session:
            rows = session.execute(
                select(PivotTrailEvent).order_by(
                    PivotTrailEvent.created_at.desc(), PivotTrailEvent.id.desc()
                ).limit(bounded)
            ).scalars()
            result = [
                {
                    column.name: getattr(row, column.name)
                    for column in row.__table__.columns
                }
                for row in rows
            ]
        result.reverse()
        return result


class DocumentLibraryService:
    """Explicit admission plus persistent, display-safe document inventory."""

    def __init__(self, workspace_manager: Any) -> None:
        self._workspace = workspace_manager

    def ingest_bytes(
        self,
        data: bytes,
        *,
        filename: str,
        operator: str,
        expected_sha256: str,
        supplied_media_type: str | None = None,
    ) -> DocumentAdmissionReceipt:
        actual = hashlib.sha256(data).hexdigest()
        if not expected_sha256 or actual != expected_sha256.casefold():
            raise ValueError("document bytes changed after preview; preview the file again")
        intake = DocumentIntakeService(self._workspace).store_bytes(
            data,
            filename=filename,
            operator=operator,
            supplied_media_type=supplied_media_type,
            limits=DocumentLimits(max_output_chars=100_000),
        )
        extraction = DocumentEntityExtractionService(self._workspace).extract_parser_receipt(
            intake.parser_receipt_id,
            limits=EntityExtractionLimits(max_candidates=2_000, context_chars=60),
        )
        pivot_event_id = PivotTrailAuthority(self._workspace).record(
            to_kind="document",
            to_ref=intake.occurrence_id,
            to_label=intake.preview.filename,
            action="document_ingested",
            basis="Explicit analyst admission after local preview.",
            provenance_refs=(intake.occurrence_id, intake.parser_receipt_id),
        )
        return DocumentAdmissionReceipt(
            intake=intake,
            extraction_receipt_id=extraction.extraction_receipt_id,
            candidate_count=len(extraction.candidates),
            pivot_event_id=pivot_event_id,
        )

    def list(self) -> tuple[DocumentLibraryRecord, ...]:
        with self._workspace.get_session() as session:
            candidate_counts = (
                select(
                    DocumentEntityCandidate.occurrence_id,
                    func.count(DocumentEntityCandidate.id).label("candidate_count"),
                )
                .group_by(DocumentEntityCandidate.occurrence_id)
                .subquery()
            )
            rows = session.execute(
                select(
                    DocumentOccurrence,
                    DocumentContent,
                    DocumentParserReceipt,
                    func.coalesce(candidate_counts.c.candidate_count, 0),
                )
                .join(
                    DocumentContent,
                    DocumentOccurrence.content_sha256 == DocumentContent.sha256,
                )
                .join(
                    DocumentParserReceipt,
                    DocumentParserReceipt.occurrence_id == DocumentOccurrence.id,
                )
                .outerjoin(
                    candidate_counts,
                    candidate_counts.c.occurrence_id == DocumentOccurrence.id,
                )
                .order_by(DocumentOccurrence.acquired_at.desc(), DocumentOccurrence.id.desc())
            ).all()
            content_occurrences: dict[str, int] = {}
            for occurrence, _content, _parser, _count in rows:
                content_occurrences[occurrence.content_sha256] = (
                    content_occurrences.get(occurrence.content_sha256, 0) + 1
                )
            return tuple(
                DocumentLibraryRecord(
                    occurrence_id=occurrence.id,
                    filename=occurrence.filename,
                    source_kind=occurrence.source_kind,
                    source_uri=occurrence.source_uri,
                    detected_media_type=occurrence.detected_media_type,
                    size_bytes=content.size_bytes,
                    content_sha256=content.sha256,
                    parser_state=parser.state,
                    candidate_count=int(candidate_count),
                    acquired_at=occurrence.acquired_at.isoformat(),
                    operator=occurrence.operator,
                    reused_content=content_occurrences[content.sha256] > 1,
                )
                for occurrence, content, parser, candidate_count in rows
            )

    def detail(self, occurrence_id: str) -> dict[str, Any]:
        with self._workspace.get_session() as session:
            occurrence = session.get(DocumentOccurrence, occurrence_id)
            if occurrence is None:
                raise ValueError("document was not found in the active workspace")
            parser = session.execute(
                select(DocumentParserReceipt)
                .where(DocumentParserReceipt.occurrence_id == occurrence_id)
                .order_by(DocumentParserReceipt.created_at.desc())
                .limit(1)
            ).scalar_one()
            candidates = session.execute(
                select(DocumentEntityCandidate)
                .where(DocumentEntityCandidate.occurrence_id == occurrence_id)
                .order_by(DocumentEntityCandidate.start_char, DocumentEntityCandidate.id)
            ).scalars()
            return {
                "occurrence_id": occurrence.id,
                "filename": occurrence.filename,
                "source_kind": occurrence.source_kind,
                "source_uri": occurrence.source_uri,
                "detected_media_type": occurrence.detected_media_type,
                "operator": occurrence.operator,
                "acquired_at": occurrence.acquired_at.isoformat(),
                "parser": {
                    "id": parser.id,
                    "state": parser.state,
                    "output_text": parser.output_text,
                    "warnings": parser.warnings,
                    "errors": parser.errors,
                    "skipped": parser.skipped,
                },
                "candidates": [
                    {
                        column.name: getattr(row, column.name)
                        for column in row.__table__.columns
                        if column.name not in {"context"}
                    }
                    for row in candidates
                ],
                "truth_boundary": (
                    "Stored source content and parser output are provenance. Candidate strings "
                    "remain unverified until an analyst admits or rejects them."
                ),
            }
