"""Deterministic SCOT4 hunt publication and pivot-intake contracts."""

from __future__ import annotations

import hashlib
import html
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

    schema_version: Literal["pivotglass-scot-publication-1.0"] = "pivotglass-scot-publication-1.0"
    publication_id: str
    workspace: str
    source_snapshot_sha256: str
    items: tuple[ScotPublicationItem, ...]
    connections: tuple[ScotPublishedConnection, ...]
    digest_sha256: str
    approval_required: Literal[True] = True
    published: Literal[False] = False


class ScotWriteOperation(BaseModel):
    """One exact SCOT4 REST operation in a non-executing publication plan."""

    model_config = ConfigDict(frozen=True)

    operation_id: str
    phase: Literal["write", "readback"]
    method: Literal["GET", "POST"]
    path_template: str
    body: dict[str, Any] | None = None
    depends_on: tuple[str, ...] = ()
    captures: tuple[str, ...] = ()
    expected_status: tuple[int, ...]
    client_ref: str | None = None
    description: str


class ScotWritePlan(BaseModel):
    """Reviewable SCOT4 mutation DAG; intentionally cannot execute itself."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-scot-write-plan-1.0"] = "pivotglass-scot-write-plan-1.0"
    publication_id: str
    workspace: str
    manifest_digest_sha256: str
    owner: str
    operations: tuple[ScotWriteOperation, ...]
    digest_sha256: str
    approval_required: Literal[True] = True
    execution_enabled: Literal[False] = False
    readback_required: Literal[True] = True


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


def compile_scot_write_plan(
    manifest: ScotPublicationManifest,
    *,
    owner: str,
) -> ScotWritePlan:
    """Compile a manifest into exact SCOT4 REST writes plus required readbacks.

    Result references are represented as ``{"$result": {"operation_id": ..., "field":
    "id"}}`` in request bodies and ``{result:<operation-id>:id}`` in paths. The
    compiler does not resolve those references, authenticate, or send requests.
    """
    normalized_owner = owner.strip()
    if not normalized_owner or len(normalized_owner) > 254:
        raise ValueError("SCOT publication owner must be between 1 and 254 characters")
    if any(ord(character) < 32 for character in normalized_owner):
        raise ValueError("SCOT publication owner contains unsupported control characters")

    events = [item for item in manifest.items if item.object_type == "event"]
    if len(events) != 1:
        raise ValueError("SCOT publication manifest must contain exactly one event")
    event = events[0]
    event_operation_id = _operation_id("create", event.client_ref)
    operations: list[ScotWriteOperation] = [
        ScotWriteOperation(
            operation_id=event_operation_id,
            phase="write",
            method="POST",
            path_template="/event/",
            body={
                "owner": normalized_owner,
                "tlp": "unset",
                "status": event.payload.get("status", "open"),
                "subject": event.payload.get("subject"),
                "view_count": 0,
                "message_id": manifest.publication_id,
            },
            captures=("id",),
            expected_status=(200,),
            client_ref=event.client_ref,
            description="Create the SCOT4 event that owns this Pivotglass publication.",
        )
    ]
    create_operation_by_ref = {event.client_ref: event_operation_id}

    for item in sorted(
        (candidate for candidate in manifest.items if candidate.object_type != "event"),
        key=lambda candidate: candidate.client_ref,
    ):
        operation_id = _operation_id("create", item.client_ref)
        parent_ref = item.parent_client_ref or event.client_ref
        parent_operation = create_operation_by_ref.get(parent_ref)
        if parent_operation is None:
            raise ValueError(f"SCOT publication item has unknown parent: {parent_ref}")
        if item.object_type == "entity":
            body = {
                "entity": {
                    "status": "tracked",
                    "value": item.payload.get("value"),
                    "type_id": None,
                    "data_ver": manifest.schema_version,
                    "data": {
                        "pivotglass": item.payload.get("pivotglass", {}),
                        "provenance_refs": list(item.provenance_refs),
                    },
                    "type_name": item.payload.get("type"),
                    "classes": [],
                },
                "create_flair_regex": False,
                "target_type": "event",
                "target_id": _result_reference(parent_operation),
            }
            path = "/entity/"
        elif item.object_type == "entry":
            plain_text = str(item.payload.get("plain_text") or item.payload.get("title") or "")
            body = {
                "owner": normalized_owner,
                "tlp": "unset",
                "parent_entry_id": None,
                "target_type": "event",
                "target_id": _result_reference(parent_operation),
                "entry_class": "entry",
                "entry_data_ver": manifest.schema_version,
                "entry_data": {
                    "html": f"<pre>{html.escape(plain_text)}</pre>",
                    "pivotglass": item.payload.get("pivotglass", {}),
                    "provenance_refs": list(item.provenance_refs),
                },
                "parsed": False,
            }
            path = "/entry/"
        else:  # pragma: no cover - constrained by ScotPublicationItem
            raise ValueError(f"unsupported SCOT publication object: {item.object_type}")
        operations.append(
            ScotWriteOperation(
                operation_id=operation_id,
                phase="write",
                method="POST",
                path_template=path,
                body=body,
                depends_on=(parent_operation,),
                captures=("id",),
                expected_status=(200,),
                client_ref=item.client_ref,
                description=f"Create and attach SCOT4 {item.object_type} {item.client_ref}.",
            )
        )
        create_operation_by_ref[item.client_ref] = operation_id

    for item in sorted(manifest.items, key=lambda candidate: candidate.client_ref):
        create_operation = create_operation_by_ref[item.client_ref]
        for tag in sorted(set(item.payload.get("tags", []))):
            tag_operation_id = _operation_id("tag", item.client_ref, str(tag))
            operations.append(
                ScotWriteOperation(
                    operation_id=tag_operation_id,
                    phase="write",
                    method="POST",
                    path_template="/tag/tag_by_name",
                    body={
                        "target_type": item.object_type,
                        "target_id": _result_reference(create_operation),
                        "tag_name": str(tag),
                        "tag_description": "Assigned by an approved Pivotglass publication plan.",
                    },
                    depends_on=(create_operation,),
                    expected_status=(200,),
                    client_ref=item.client_ref,
                    description=f"Assign tag {tag!r} to {item.client_ref}.",
                )
            )

    for connection in manifest.connections:
        source_operation = create_operation_by_ref.get(connection.source_client_ref)
        target_operation = create_operation_by_ref.get(connection.target_client_ref)
        if source_operation is None or target_operation is None:
            raise ValueError("SCOT connection references an unknown publication item")
        source_item = _item_by_ref(manifest, connection.source_client_ref)
        target_item = _item_by_ref(manifest, connection.target_client_ref)
        link_operation_id = _operation_id(
            "link",
            connection.source_client_ref,
            connection.target_client_ref,
            connection.relationship,
            _digest(connection.model_dump(mode="json")),
        )
        operations.append(
            ScotWriteOperation(
                operation_id=link_operation_id,
                phase="write",
                method="POST",
                path_template="/link/",
                body={
                    "v0_type": source_item.object_type,
                    "v0_id": _result_reference(source_operation),
                    "v1_type": target_item.object_type,
                    "v1_id": _result_reference(target_operation),
                    "weight": None,
                    "context": json.dumps(
                        {
                            "relationship": connection.relationship,
                            "truth_kind": connection.truth_kind,
                            "provenance_refs": list(connection.provenance_refs),
                            "rationale": connection.rationale,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                },
                depends_on=tuple(sorted((source_operation, target_operation))),
                captures=("id",),
                expected_status=(200,),
                description=(
                    f"Create typed SCOT4 link {connection.relationship!r} while retaining "
                    f"its {connection.truth_kind!r} truth class."
                ),
            )
        )

    write_operations = tuple(operations)
    for operation in write_operations:
        if operation.path_template == "/link/":
            object_type = "link"
            result_operation = operation.operation_id
        elif operation.path_template == "/tag/tag_by_name":
            if operation.client_ref is None:  # pragma: no cover - compiler invariant
                raise ValueError("SCOT tag operation is missing its target reference")
            object_type = _item_by_ref(manifest, operation.client_ref).object_type
            result_operation = create_operation_by_ref[operation.client_ref]
        elif operation.client_ref is not None and "id" in operation.captures:
            object_type = _item_by_ref(manifest, operation.client_ref).object_type
            result_operation = operation.operation_id
        else:
            continue
        operations.append(
            ScotWriteOperation(
                operation_id=_operation_id("readback", operation.operation_id),
                phase="readback",
                method="GET",
                path_template=f"/{object_type}/{{result:{result_operation}:id}}",
                depends_on=(operation.operation_id,),
                expected_status=(200,),
                client_ref=operation.client_ref,
                description=f"Read back and reconcile the result of {operation.operation_id}.",
            )
        )

    content = {
        "schema_version": "pivotglass-scot-write-plan-1.0",
        "publication_id": manifest.publication_id,
        "workspace": manifest.workspace,
        "manifest_digest_sha256": manifest.digest_sha256,
        "owner": normalized_owner,
        "operations": [operation.model_dump(mode="json") for operation in operations],
    }
    plan = ScotWritePlan(
        publication_id=manifest.publication_id,
        workspace=manifest.workspace,
        manifest_digest_sha256=manifest.digest_sha256,
        owner=normalized_owner,
        operations=tuple(operations),
        digest_sha256=_digest(content),
    )
    validate_scot_write_plan(plan)
    return plan


def validate_scot_write_plan(plan: ScotWritePlan) -> None:
    """Reject ambiguous operation identities before any approval or mutation."""
    operation_ids = [operation.operation_id for operation in plan.operations]
    if len(operation_ids) != len(set(operation_ids)):
        raise ValueError("SCOT publication plan contains duplicate operation IDs")


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
    request_identity = {key: value for key, value in payload.items() if key != "requested_at"}
    return ScotPivotRequest(
        request_id=f"scot-pivot-{_digest(request_identity)[:24]}",
        **payload,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _operation_id(action: str, *parts: str) -> str:
    return f"scot-{action}-{_digest(parts)[:24]}"


def _result_reference(operation_id: str) -> dict[str, dict[str, str]]:
    return {"$result": {"operation_id": operation_id, "field": "id"}}


def _item_by_ref(
    manifest: ScotPublicationManifest,
    client_ref: str,
) -> ScotPublicationItem:
    for item in manifest.items:
        if item.client_ref == client_ref:
            return item
    raise ValueError(f"SCOT publication references unknown item: {client_ref}")
