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
from stix2 import AttackPattern, Vulnerability

from pivotglass.core.document_entity_extraction import (
    DocumentEntityExtractionService,
    EntityExtractionLimits,
)
from pivotglass.core.document_ingestion import (
    DocumentIntakeReceipt,
    DocumentIntakeService,
    DocumentLimits,
)
from pivotglass.models.database import (
    DocumentContent,
    DocumentEntityCandidate,
    DocumentOccurrence,
    DocumentParserReceipt,
    PivotTrailEvent,
    StixObject,
)
from pivotglass.models.stix import dict_to_stix


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


class CandidateAdmissionReceipt(BaseModel):
    """Receipt for an analyst's explicit candidate-to-entity decision."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "pivotglass-document-candidate-admission-1.0"
    occurrence_id: str
    selected_count: int
    admitted_candidate_count: int
    already_admitted_count: int
    entity_count: int
    new_entity_count: int
    entity_refs: tuple[str, ...]
    pivot_event_ids: tuple[str, ...]
    truth_boundary: str = (
        "The selected strings are admitted as workspace entities with document and "
        "parser provenance. Admission records that the analyst chose these entities; "
        "it does not make the document's claims true, assign a malicious verdict, "
        "create a threat relationship, or attribute an actor."
    )


def document_candidate_selection_key(
    content_sha256: str,
    candidate: Any,
) -> str:
    """Return an opaque key binding a selection to source bytes and exact span."""

    def field(name: str) -> Any:
        if isinstance(candidate, dict):
            return candidate[name]
        return getattr(candidate, name)

    basis = "\0".join(
        (
            content_sha256.casefold(),
            str(field("entity_type")),
            str(field("start_char")),
            str(field("end_char")),
            str(field("normalized_value")),
            str(field("rule_id")),
            str(field("rule_version")),
        )
    )
    return f"document-selection-{hashlib.sha256(basis.encode()).hexdigest()}"


def _candidate_stix_object(candidate: DocumentEntityCandidate) -> Any:
    """Map one qualified extractor candidate to a deterministic STIX entity."""

    value = candidate.normalized_value
    if candidate.entity_type.startswith("file-hash-"):
        converted = dict_to_stix({"type": "file", "value": value})
    elif candidate.entity_type == "vulnerability":
        identifier = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"pivotglass:vulnerability:{value}",
        )
        converted = Vulnerability(
            id=f"vulnerability--{identifier}",
            name=value,
            external_references=[{"source_name": "cve", "external_id": value}],
            x_indicator_value=value,
            allow_custom=True,
        )
    elif candidate.entity_type == "attack-pattern":
        identifier = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"pivotglass:attack-pattern:{value}",
        )
        converted = AttackPattern(
            id=f"attack-pattern--{identifier}",
            name=value,
            external_references=[
                {"source_name": "mitre-attack", "external_id": value}
            ],
            x_indicator_value=value,
            allow_custom=True,
        )
    else:
        converted = dict_to_stix({"type": candidate.entity_type, "value": value})
    if isinstance(converted, dict):
        raise ValueError(
            f"candidate type '{candidate.entity_type}' cannot be admitted as a workspace entity"
        )
    return converted


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

    def list_groups(self) -> list[dict[str, Any]]:
        """Read durable explicit batches independently of the recent navigation window."""
        with self._workspace.get_session() as session:
            rows = session.execute(select(PivotTrailEvent).where(
                PivotTrailEvent.action == "analyst_group_created"
            ).order_by(PivotTrailEvent.created_at, PivotTrailEvent.id)).scalars()
            return [{column.name: getattr(row, column.name)
                     for column in row.__table__.columns} for row in rows]

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

    def admit_candidates(
        self,
        occurrence_id: str,
        candidate_ids: list[str] | tuple[str, ...],
        *,
        operator: str,
    ) -> CandidateAdmissionReceipt:
        """Admit only analyst-selected candidates through workspace evidence authority."""

        selected_ids = tuple(dict.fromkeys(item.strip() for item in candidate_ids if item.strip()))
        if not selected_ids:
            raise ValueError("select at least one document candidate to admit")
        if len(selected_ids) > 2_000:
            raise ValueError("no more than 2,000 document candidates may be admitted at once")
        normalized_operator = operator.strip() or "local analyst"

        with self._workspace.get_session() as session:
            occurrence = session.get(DocumentOccurrence, occurrence_id)
            if occurrence is None:
                raise ValueError("document was not found in the active workspace")
            content = session.get(DocumentContent, occurrence.content_sha256)
            if content is None:
                raise ValueError("stored document content is unavailable")
            candidates = list(
                session.execute(
                    select(DocumentEntityCandidate)
                    .where(DocumentEntityCandidate.id.in_(selected_ids))
                    .order_by(DocumentEntityCandidate.start_char, DocumentEntityCandidate.id)
                ).scalars()
            )
            found_ids = {candidate.id for candidate in candidates}
            missing = [item for item in selected_ids if item not in found_ids]
            if missing:
                raise ValueError("one or more selected document candidates were not found")
            if any(candidate.occurrence_id != occurrence_id for candidate in candidates):
                raise ValueError("selected document candidates do not belong to this document")
            pending = [candidate for candidate in candidates if candidate.state != "admitted"]
            already_admitted_count = len(candidates) - len(pending)

        candidate_objects = [(candidate, _candidate_stix_object(candidate)) for candidate in candidates]
        unique_objects: dict[str, Any] = {}
        pending_refs: set[str] = set()
        refs_to_candidates: dict[str, list[DocumentEntityCandidate]] = {}
        for candidate, obj in candidate_objects:
            unique_objects[obj.id] = obj
            refs_to_candidates.setdefault(obj.id, []).append(candidate)
            if candidate in pending:
                pending_refs.add(obj.id)

        with self._workspace.get_session() as session:
            existing_refs = {
                value
                for value in session.execute(
                    select(StixObject.id).where(StixObject.id.in_(tuple(pending_refs)))
                ).scalars()
            } if pending_refs else set()

        objects_to_store = [unique_objects[ref] for ref in sorted(pending_refs)]
        if objects_to_store:
            self._workspace.store_stix_objects(
                objects_to_store,
                module_name="document/entity-admission",
                target=occurrence_id,
                response_sha256=occurrence.content_sha256,
                fetched_at=occurrence.acquired_at.isoformat().replace("+00:00", "Z"),
                collector_version="pivotglass-deterministic-entity-extractor/1.0",
                response_media_type=occurrence.detected_media_type,
                transformation_id=pending[0].extraction_receipt_id,
                raw_artifact_ref=f"sha256:{occurrence.content_sha256}",
                source_dependence_group=f"document:{occurrence.content_sha256}",
            )

        if pending:
            with self._workspace.get_session() as session:
                rows = list(
                    session.execute(
                        select(DocumentEntityCandidate).where(
                            DocumentEntityCandidate.id.in_(tuple(candidate.id for candidate in pending))
                        )
                    ).scalars()
                )
                for row in rows:
                    row.state = "admitted"
                    row.disposition = "admit"
                    row.disposition_reason = (
                        f"Explicitly admitted by {normalized_operator} from document "
                        f"occurrence {occurrence_id}."
                    )
                session.commit()

        pivot_event_ids: list[str] = []
        group_ref = None
        if len(pending_refs) > 1:
            group_ref = f"analyst-group-{uuid.uuid4().hex}"
            pivot_event_ids.append(PivotTrailAuthority(self._workspace).record(
                from_kind="document", from_ref=occurrence_id, from_label=occurrence.filename,
                to_kind="analyst_group", to_ref=group_ref,
                to_label=f"Analyst promotion group · {len(pending_refs)} indicators",
                action="analyst_group_created",
                basis="Selected and promoted together by the analyst; grouping does not assert shared adversary ownership or activity.",
                provenance_refs=(occurrence_id, *sorted(pending_refs)),
                created_by=normalized_operator,
            ))
        for entity_ref in sorted(pending_refs):
            source_candidates = refs_to_candidates[entity_ref]
            pivot_event_ids.append(
                PivotTrailAuthority(self._workspace).record(
                    from_kind="analyst_group" if group_ref else "document",
                    from_ref=group_ref or occurrence_id,
                    from_label=f"Analyst promotion group · {len(pending_refs)} indicators" if group_ref else occurrence.filename,
                    to_kind="indicator",
                    to_ref=entity_ref,
                    to_label=source_candidates[0].normalized_value,
                    created_by=normalized_operator,
                    action="document_candidate_admitted",
                    basis=(
                        "Explicit analyst admission of a deterministic document candidate; "
                        "no verdict or attribution was assigned."
                    ),
                    provenance_refs=(
                        occurrence_id,
                        entity_ref,
                        *(candidate.id for candidate in source_candidates),
                    ),
                )
            )

        return CandidateAdmissionReceipt(
            occurrence_id=occurrence_id,
            selected_count=len(candidates),
            admitted_candidate_count=len(pending),
            already_admitted_count=already_admitted_count,
            entity_count=len(unique_objects),
            new_entity_count=len(pending_refs - existing_refs),
            entity_refs=tuple(sorted(unique_objects)),
            pivot_event_ids=tuple(pivot_event_ids),
        )

    def admit_candidate_keys(
        self,
        occurrence_id: str,
        selection_keys: list[str] | tuple[str, ...],
        *,
        operator: str,
    ) -> CandidateAdmissionReceipt:
        """Resolve preview-bound selection keys to persisted candidates, then admit."""

        selected_keys = tuple(dict.fromkeys(item.strip() for item in selection_keys if item.strip()))
        if not selected_keys:
            raise ValueError("select at least one document candidate to admit")
        with self._workspace.get_session() as session:
            occurrence = session.get(DocumentOccurrence, occurrence_id)
            if occurrence is None:
                raise ValueError("document was not found in the active workspace")
            candidates = list(
                session.execute(
                    select(DocumentEntityCandidate).where(
                        DocumentEntityCandidate.occurrence_id == occurrence_id
                    )
                ).scalars()
            )
            candidate_by_key = {
                document_candidate_selection_key(occurrence.content_sha256, candidate): candidate
                for candidate in candidates
            }
        missing = [key for key in selected_keys if key not in candidate_by_key]
        if missing:
            raise ValueError(
                "one or more selections do not match the reviewed document candidates"
            )
        return self.admit_candidates(
            occurrence_id,
            [candidate_by_key[key].id for key in selected_keys],
            operator=operator,
        )

    def detail(self, occurrence_id: str) -> dict[str, Any]:
        with self._workspace.get_session() as session:
            occurrence = session.get(DocumentOccurrence, occurrence_id)
            if occurrence is None:
                raise ValueError("document was not found in the active workspace")
            content = session.get(DocumentContent, occurrence.content_sha256)
            if content is None:
                raise ValueError("stored document content is missing from the active workspace")
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
                "content_sha256": content.sha256,
                "size_bytes": content.size_bytes,
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
                    } | {
                        "selection_key": document_candidate_selection_key(
                            occurrence.content_sha256,
                            row,
                        )
                    }
                    for row in candidates
                ],
                "truth_boundary": (
                    "Stored source content and parser output are provenance. Candidate strings "
                    "remain unverified until an analyst admits or rejects them."
                ),
            }
