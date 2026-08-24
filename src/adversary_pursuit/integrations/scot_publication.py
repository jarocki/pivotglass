"""Deterministic SCOT4 hunt publication and pivot-intake contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from adversary_pursuit.core.graph_repository import GraphRepositorySnapshot
from adversary_pursuit.core.ioc_types import detect_ioc_type
from adversary_pursuit.integrations.scot import SCOT_OBJECT_TYPES


class ScotPublicationItem(BaseModel):
    """One proposed SCOT object mutation; this model performs no write."""

    model_config = ConfigDict(frozen=True)

    client_ref: str
    object_type: Literal["event", "entity", "entry"]
    action: Literal["create", "update"] = "create"
    parent_client_ref: str | None = None
    payload: dict[str, Any]
    provenance_refs: tuple[str, ...]


class ScotPublishedConnection(BaseModel):
    """A relationship SCOT must present without changing its truth class."""

    model_config = ConfigDict(frozen=True)

    source_client_ref: str
    target_client_ref: str
    relationship: str
    truth_kind: str
    provenance_refs: tuple[str, ...]
    rationale: str


class ScotPublicationManifest(BaseModel):
    """Exact, reviewable desired SCOT state for one hunt session."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-scot-publication-1.0"] = (
        "pivotglass-scot-publication-1.0"
    )
    publication_id: str
    workspace: str
    source_snapshot_sha256: str
    items: tuple[ScotPublicationItem, ...]
    connections: tuple[ScotPublishedConnection, ...]
    digest_sha256: str
    approval_required: Literal[True] = True
    published: Literal[False] = False


class ScotPivotRequest(BaseModel):
    """Validated request from SCOT; acceptance does not enqueue it."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-scot-pivot-request-1.0"] = (
        "pivotglass-scot-pivot-request-1.0"
    )
    request_id: str
    workspace: str
    scot_object_type: str
    scot_object_id: int = Field(gt=0)
    scot_revision: str | None = None
    indicator: str
    indicator_type: str
    requested_by: str
    requested_at: datetime
    reason: str
    disposition: Literal["preview"] = "preview"
    enqueue_requires_analyst_action: Literal[True] = True


def build_scot_publication_manifest(snapshot: GraphRepositorySnapshot) -> ScotPublicationManifest:
    """Build one deterministic, non-executing SCOT4 publication preview."""
    publication_id = f"scot-publication-{snapshot.digest_sha256[:24]}"
    event_ref = f"scot-event:{publication_id}"
    source_tags = sorted(
        {
            f"source:{node.attributes['source']}"
            for node in snapshot.nodes
            if node.kind == "observation" and node.attributes.get("source")
        }
    )
    items: list[ScotPublicationItem] = [
        ScotPublicationItem(
            client_ref=event_ref,
            object_type="event",
            payload={
                "subject": f"Pivotglass hunt: {snapshot.workspace}",
                "status": "open",
                "tags": ["pivotglass", f"workspace:{snapshot.workspace}", *source_tags],
                "pivotglass": {
                    "graph_schema": snapshot.schema_version,
                    "graph_digest_sha256": snapshot.digest_sha256,
                    "node_count": len(snapshot.nodes),
                    "connection_count": len(snapshot.edges),
                },
            },
            provenance_refs=(snapshot.digest_sha256,),
        )
    ]
    node_client_ref: dict[str, str] = {}
    for node in snapshot.nodes:
        if node.layer == "entity":
            client_ref = f"scot-entity:{_digest({'node': node.id})[:24]}"
            object_type: Literal["entity", "entry"] = "entity"
            payload = {
                "value": node.label,
                "type": node.kind,
                "status": node.state,
                "tags": ["pivotglass", f"indicator-type:{node.kind}"],
                "pivotglass": {
                    "node_id": node.id,
                    "record_ref": node.record_ref,
                    "layer": node.layer,
                },
            }
        else:
            client_ref = f"scot-entry:{_digest({'node': node.id})[:24]}"
            object_type = "entry"
            payload = {
                "title": f"{node.kind.replace('_', ' ').title()}: {node.label}",
                "plain_text": node.label,
                "tags": ["pivotglass", f"analytic-record:{node.kind}"],
                "pivotglass": {
                    "node_id": node.id,
                    "record_ref": node.record_ref,
                    "layer": node.layer,
                    "state": node.state,
                    "attributes": node.attributes,
                },
            }
        node_client_ref[node.id] = client_ref
        items.append(
            ScotPublicationItem(
                client_ref=client_ref,
                object_type=object_type,
                parent_client_ref=event_ref,
                payload=payload,
                provenance_refs=(node.record_ref,),
            )
        )

    connections = tuple(
        sorted(
            (
                ScotPublishedConnection(
                    source_client_ref=node_client_ref[edge.source],
                    target_client_ref=node_client_ref[edge.target],
                    relationship=edge.relationship,
                    truth_kind=edge.truth_kind,
                    provenance_refs=edge.provenance_refs,
                    rationale=edge.rationale,
                )
                for edge in snapshot.edges
            ),
            key=lambda item: (
                item.source_client_ref,
                item.target_client_ref,
                item.relationship,
            ),
        )
    )
    relationship_lines = [
        (
            f"- `{item.source_client_ref}` --{item.relationship}--> "
            f"`{item.target_client_ref}` [{item.truth_kind}]"
        )
        for item in connections
    ]
    items.append(
        ScotPublicationItem(
            client_ref=f"scot-entry:{publication_id}:relationships",
            object_type="entry",
            parent_client_ref=event_ref,
            payload={
                "title": "Pivotglass relationship index",
                "plain_text": "\n".join(relationship_lines) or "No relationships recorded.",
                "tags": ["pivotglass", "relationship-index"],
                "pivotglass": {
                    "connections": [item.model_dump(mode="json") for item in connections]
                },
            },
            provenance_refs=tuple(
                sorted({ref for item in connections for ref in item.provenance_refs})
            )
            or (snapshot.digest_sha256,),
        )
    )
    items_tuple = tuple(sorted(items, key=lambda item: item.client_ref))
    content = {
        "schema_version": "pivotglass-scot-publication-1.0",
        "publication_id": publication_id,
        "workspace": snapshot.workspace,
        "source_snapshot_sha256": snapshot.digest_sha256,
        "items": [item.model_dump(mode="json") for item in items_tuple],
        "connections": [item.model_dump(mode="json") for item in connections],
    }
    return ScotPublicationManifest(
        publication_id=publication_id,
        workspace=snapshot.workspace,
        source_snapshot_sha256=snapshot.digest_sha256,
        items=items_tuple,
        connections=connections,
        digest_sha256=_digest(content),
    )


def validate_scot_pivot_request(
    *,
    workspace: str,
    scot_object_type: str,
    scot_object_id: int,
    indicator: str,
    requested_by: str,
    requested_at: datetime,
    reason: str,
    scot_revision: str | None = None,
) -> ScotPivotRequest:
    """Validate an inbound pivot without enqueuing or changing evidence."""
    normalized_object_type = scot_object_type.strip().casefold()
    if normalized_object_type not in SCOT_OBJECT_TYPES:
        raise ValueError("SCOT pivot parent type is unsupported")
    normalized_indicator = indicator.strip()
    indicator_type = detect_ioc_type(normalized_indicator)
    if indicator_type is None:
        raise ValueError("SCOT pivot value is not a supported indicator")
    normalized_workspace = workspace.strip()
    normalized_requester = requested_by.strip()
    normalized_reason = reason.strip()
    if not normalized_workspace or not normalized_requester or not normalized_reason:
        raise ValueError("workspace, requester, and reason are required")
    if len(normalized_requester) > 254 or len(normalized_reason) > 1000:
        raise ValueError("SCOT pivot requester or reason exceeds the supported length")
    if requested_at.utcoffset() is None:
        raise ValueError("SCOT pivot timestamp must include a timezone")
    payload = {
        "workspace": normalized_workspace,
        "scot_object_type": normalized_object_type,
        "scot_object_id": scot_object_id,
        "scot_revision": scot_revision,
        "indicator": normalized_indicator,
        "indicator_type": indicator_type,
        "requested_by": normalized_requester,
        "requested_at": requested_at.isoformat(),
        "reason": normalized_reason,
    }
    return ScotPivotRequest(
        request_id=f"scot-pivot-{_digest(payload)[:24]}",
        **payload,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
