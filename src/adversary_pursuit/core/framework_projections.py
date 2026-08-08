"""Evidence-grounded projections for ATT&CK, Kill Chain, and Diamond Model.

Framework views are useful ways to ask different questions of the same
investigation. They are never a second evidence or relationship authority:
every mapping keeps its pinned content version, evidence basis, mapper, and
analyst disposition. A model or automated mapper can propose a mapping, but an
accepted mapping always has a human disposition recorded in the ledger.

This module is deliberately content-neutral. ATT&CK/STIX content packages can
be added as optional adapters later; this authority validates and persists the
mapping contract without silently downloading or inventing framework content.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select

from adversary_pursuit.core.analytic_ledger import ConfidenceLevel
from adversary_pursuit.models.database import FrameworkMappingRecord


class Framework(StrEnum):
    ATTACK = "attack"
    KILL_CHAIN = "kill_chain"
    DIAMOND = "diamond"


class MappingOrigin(StrEnum):
    AUTOMATED = "automated"
    HUMAN = "human"
    MODEL = "model"


class MappingState(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"


class FrameworkMapping(BaseModel):
    """One version-pinned, evidence-backed framework mapping."""

    model_config = ConfigDict(frozen=True)

    id: str
    framework: Framework
    framework_version: str = Field(min_length=1)
    content_id: str = Field(min_length=1)
    content_label: str = Field(min_length=1)
    evidence_refs: tuple[str, ...]
    basis: str = Field(min_length=1)
    mapper: str = Field(min_length=1)
    mapper_version: str = Field(min_length=1)
    origin: MappingOrigin
    confidence: ConfidenceLevel
    confidence_rationale: str = Field(min_length=1)
    analyst_override: str | None = None
    state: MappingState = MappingState.PROPOSED
    supersedes_id: str | None = None
    revoked_reason: str | None = None

    @field_validator("evidence_refs")
    @classmethod
    def normalize_evidence_refs(cls, refs: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(ref.strip() for ref in refs if ref.strip()))
        if not normalized:
            raise ValueError("framework mappings require at least one evidence reference")
        return normalized

    @model_validator(mode="after")
    def validate_disposition(self) -> FrameworkMapping:
        if self.state is MappingState.ACCEPTED and self.origin is MappingOrigin.MODEL:
            if not self.analyst_override:
                raise ValueError("model mappings require an analyst override before acceptance")
        if self.state is MappingState.REVOKED and not self.revoked_reason:
            raise ValueError("revoked mappings require a reason")
        return self


class FrameworkGap(BaseModel):
    """A requested framework content item without accepted evidence support."""

    model_config = ConfigDict(frozen=True)

    content_id: str
    explanation: str
    intelligence_requirement: str


class FrameworkProjection(BaseModel):
    """A read-only view over accepted and pending mapping records."""

    model_config = ConfigDict(frozen=True)

    framework: Framework
    framework_version: str
    mappings: tuple[FrameworkMapping, ...]
    gaps: tuple[FrameworkGap, ...]


FRAMEWORK_LABELS: dict[Framework, str] = {
    Framework.ATTACK: "MITRE ATT&CK",
    Framework.KILL_CHAIN: "Cyber Kill Chain",
    Framework.DIAMOND: "Diamond Model",
}


class FrameworkProjectionAuthority:
    """Persist and project mappings for one workspace.

    The authority is append-only in spirit: changing a disposition updates the
    current record, while supersession/revocation fields preserve why the view
    changed. It never writes observations, STIX relationships, or hypotheses.
    """

    def __init__(self, workspace_manager: Any) -> None:
        self._workspace = workspace_manager

    def propose(
        self,
        *,
        framework: Framework,
        framework_version: str,
        content_id: str,
        content_label: str,
        evidence_refs: Iterable[str],
        basis: str,
        mapper: str,
        mapper_version: str,
        origin: MappingOrigin,
        confidence: ConfidenceLevel,
        confidence_rationale: str,
    ) -> FrameworkMapping:
        refs = tuple(evidence_refs)
        fingerprint = _basis_fingerprint(framework, framework_version, content_id, refs)
        mapping = FrameworkMapping(
            id=f"framework-map-{uuid.uuid4()}",
            framework=framework,
            framework_version=framework_version,
            content_id=content_id,
            content_label=content_label,
            evidence_refs=refs,
            basis=basis,
            mapper=mapper,
            mapper_version=mapper_version,
            origin=origin,
            confidence=confidence,
            confidence_rationale=confidence_rationale,
        )
        with self._workspace.get_session() as session:
            duplicate = session.execute(
                select(FrameworkMappingRecord).where(
                    FrameworkMappingRecord.framework == mapping.framework.value,
                    FrameworkMappingRecord.framework_version == mapping.framework_version,
                    FrameworkMappingRecord.content_id == mapping.content_id,
                    FrameworkMappingRecord.evidence_fingerprint == fingerprint,
                )
            ).scalar_one_or_none()
            if duplicate is not None:
                return _record_to_mapping(duplicate)
            session.add(_mapping_to_record(mapping, fingerprint=fingerprint))
            session.commit()
        return mapping

    def disposition(
        self,
        mapping_id: str,
        state: MappingState,
        *,
        analyst_override: str | None = None,
        revoked_reason: str | None = None,
        supersedes_id: str | None = None,
    ) -> FrameworkMapping:
        with self._workspace.get_session() as session:
            record = session.get(FrameworkMappingRecord, mapping_id)
            if record is None:
                raise ValueError(f"Unknown framework mapping: {mapping_id}")
            mapping = _record_to_mapping(
                record,
                state=state,
                analyst_override=analyst_override,
                revoked_reason=revoked_reason,
                supersedes_id=supersedes_id,
            )
            record.state = mapping.state.value
            record.analyst_override = mapping.analyst_override
            record.revoked_reason = mapping.revoked_reason
            record.supersedes_id = mapping.supersedes_id
            record.updated_at = datetime.now(timezone.utc)
            session.commit()
        return mapping

    def list(self, *, framework: Framework | None = None) -> list[FrameworkMapping]:
        with self._workspace.get_session() as session:
            statement = select(FrameworkMappingRecord).order_by(FrameworkMappingRecord.created_at)
            if framework is not None:
                statement = statement.where(FrameworkMappingRecord.framework == framework.value)
            return [_record_to_mapping(row) for row in session.execute(statement).scalars()]

    def projection(
        self,
        framework: Framework,
        *,
        framework_version: str,
        required_content: Iterable[tuple[str, str]] = (),
    ) -> FrameworkProjection:
        mappings = tuple(
            mapping
            for mapping in self.list(framework=framework)
            if mapping.framework_version == framework_version
        )
        accepted = {mapping.content_id for mapping in mappings if mapping.state is MappingState.ACCEPTED}
        gaps = tuple(
            FrameworkGap(
                content_id=content_id,
                explanation=f"No accepted evidence-backed {FRAMEWORK_LABELS[framework]} mapping.",
                intelligence_requirement=(
                    f"Collect and disposition evidence relevant to {content_label} ({content_id})."
                ),
            )
            for content_id, content_label in required_content
            if content_id not in accepted
        )
        return FrameworkProjection(
            framework=framework,
            framework_version=framework_version,
            mappings=mappings,
            gaps=gaps,
        )

    def export(self) -> dict[str, Any]:
        """Return a deterministic, secret-free exchange envelope."""

        mappings = self.list()
        return {
            "schema_version": "framework-mappings-1.0",
            "mappings": [mapping.model_dump(mode="json") for mapping in mappings],
        }


def _basis_fingerprint(
    framework: Framework,
    framework_version: str,
    content_id: str,
    evidence_refs: Iterable[str],
) -> str:
    payload = json.dumps(
        {
            "framework": framework.value,
            "framework_version": framework_version,
            "content_id": content_id,
            "evidence_refs": sorted(set(evidence_refs)),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _mapping_to_record(mapping: FrameworkMapping, *, fingerprint: str) -> FrameworkMappingRecord:
    values = mapping.model_dump(mode="json")
    values.update(
        evidence_refs=list(mapping.evidence_refs),
        evidence_fingerprint=fingerprint,
        framework=mapping.framework.value,
        origin=mapping.origin.value,
        confidence=mapping.confidence.value,
        state=mapping.state.value,
    )
    return FrameworkMappingRecord(**values)


def _record_to_mapping(
    record: FrameworkMappingRecord,
    *,
    state: MappingState | None = None,
    analyst_override: str | None = None,
    revoked_reason: str | None = None,
    supersedes_id: str | None = None,
) -> FrameworkMapping:
    return FrameworkMapping(
        id=record.id,
        framework=Framework(record.framework),
        framework_version=record.framework_version,
        content_id=record.content_id,
        content_label=record.content_label,
        evidence_refs=tuple(record.evidence_refs or ()),
        basis=record.basis,
        mapper=record.mapper,
        mapper_version=record.mapper_version,
        origin=MappingOrigin(record.origin),
        confidence=ConfidenceLevel(record.confidence),
        confidence_rationale=record.confidence_rationale,
        analyst_override=(
            analyst_override if analyst_override is not None else record.analyst_override
        ),
        state=state or MappingState(record.state),
        supersedes_id=(supersedes_id if supersedes_id is not None else record.supersedes_id),
        revoked_reason=(revoked_reason if revoked_reason is not None else record.revoked_reason),
    )
