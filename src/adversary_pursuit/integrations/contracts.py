"""Versioned exchange contracts for optional external integrations.

Remote data remains explicitly sourced.  These models do not assert that a
Synapse node or SCOT object is Pivotglass evidence; an analyst or a future
import authority must make that disposition deliberately.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ExternalReference(BaseModel):
    """Stable identity and revision metadata for one remote object."""

    system: Literal["vertex-synapse", "sandia-scot4"]
    object_type: str
    object_id: str
    revision: str | None = None
    endpoint: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    permissions: list[str] = Field(default_factory=list)
    source_url: str | None = None


class IntegrationRecord(BaseModel):
    """A bounded, source-labelled view of one remote object."""

    schema_version: Literal["pivotglass-integration-1.0"] = "pivotglass-integration-1.0"
    record_kind: Literal["remote_observation"] = "remote_observation"
    external_id: str
    entity_type: str
    value: str
    properties: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    references: list[ExternalReference]
    related_external_ids: list[str] = Field(default_factory=list)
    conflict_key: str


class QueryReceipt(BaseModel):
    """Auditable, secret-safe receipt for one bounded remote operation."""

    system: Literal["vertex-synapse", "sandia-scot4"]
    operation: str
    request_sha256: str
    started_at: datetime
    completed_at: datetime
    pages: int = 0
    records: int = 0
    validated: bool | None = None
    cancelled: bool = False
    complete: bool = True
    boundary_reason: str | None = None
