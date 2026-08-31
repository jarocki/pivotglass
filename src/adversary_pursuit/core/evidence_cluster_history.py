"""Persistent, deterministic change history for governed graph clusters."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from adversary_pursuit.core.evidence_clusters import build_evidence_clusters
from adversary_pursuit.core.graph_repository import WorkspaceGraphRepository
from adversary_pursuit.models.database import EvidenceClusterSnapshot


class ClusterSnapshotLimits(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_nodes: int = Field(default=50_000, ge=1, le=250_000)
    max_edges: int = Field(default=100_000, ge=1, le=500_000)


class ClusterSnapshotEnvelope(BaseModel):
    """Immutable graph and cluster presentation state at one instant."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-evidence-cluster-snapshot-1.0"] = (
        "pivotglass-evidence-cluster-snapshot-1.0"
    )
    id: str
    workspace: str
    graph_fingerprint: str
    captured_by: str
    captured_at: str
    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]
    clusters: tuple[dict[str, Any], ...]
    caveat: str = (
        "This is a presentation snapshot of governed graph state. Change does not prove "
        "common control, maliciousness, causality, or actor attribution."
    )


class ClusterSnapshotSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    graph_fingerprint: str
    captured_by: str
    captured_at: str
    node_count: int
    edge_count: int
    cluster_count: int


class ClusterChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class ClusterMembershipChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity_ref: str
    before_cluster_id: str | None
    after_cluster_id: str | None
    before_members: tuple[str, ...]
    after_members: tuple[str, ...]


class ClusterSnapshotDiff(BaseModel):
    """Exact added, removed, reclassified, and membership changes."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-evidence-cluster-diff-1.0"] = (
        "pivotglass-evidence-cluster-diff-1.0"
    )
    workspace: str
    before_snapshot_id: str
    after_snapshot_id: str
    added_entities: tuple[ClusterChange, ...]
    removed_entities: tuple[ClusterChange, ...]
    reclassified_entities: tuple[ClusterChange, ...]
    added_relationships: tuple[ClusterChange, ...]
    removed_relationships: tuple[ClusterChange, ...]
    reclassified_relationships: tuple[ClusterChange, ...]
    cluster_membership_changes: tuple[ClusterMembershipChange, ...]
    added_recorded_contradictions: tuple[ClusterChange, ...]
    caveat: str = (
        "Only explicitly recorded contradiction edges are called contradictions. Other "
        "differences are graph changes, not conflict, attribution, or confidence changes."
    )


class EvidenceClusterHistory:
    """Capture and compare graph state without rewriting evidence."""

    def __init__(self, workspace_manager: Any) -> None:
        self._workspace = workspace_manager

    def capture(
        self,
        *,
        captured_by: str,
        limits: ClusterSnapshotLimits | None = None,
    ) -> ClusterSnapshotEnvelope:
        active_limits = limits or ClusterSnapshotLimits()
        graph = WorkspaceGraphRepository(self._workspace).snapshot()
        if len(graph.nodes) > active_limits.max_nodes:
            raise ValueError(
                f"Graph has {len(graph.nodes)} nodes; snapshot limit is {active_limits.max_nodes}."
            )
        if len(graph.edges) > active_limits.max_edges:
            raise ValueError(
                f"Graph has {len(graph.edges)} edges; snapshot limit is {active_limits.max_edges}."
            )
        clusters = build_evidence_clusters(self._workspace)
        captured_at = datetime.now(timezone.utc).isoformat()
        snapshot_id = f"cluster-snapshot-{uuid.uuid4().hex}"
        envelope = ClusterSnapshotEnvelope(
            id=snapshot_id,
            workspace=graph.workspace,
            graph_fingerprint=graph.digest_sha256,
            captured_by=captured_by.strip() or "local analyst",
            captured_at=captured_at,
            nodes=tuple(node.model_dump(mode="json") for node in graph.nodes),
            edges=tuple(edge.model_dump(mode="json") for edge in graph.edges),
            clusters=tuple(cluster.model_dump(mode="json") for cluster in clusters),
        )
        with self._workspace.get_session() as session:
            session.add(
                EvidenceClusterSnapshot(
                    id=snapshot_id,
                    graph_fingerprint=envelope.graph_fingerprint,
                    captured_by=envelope.captured_by,
                    captured_at=datetime.fromisoformat(captured_at),
                    snapshot=envelope.model_dump(mode="json"),
                )
            )
            session.commit()
        return envelope

    def list(self) -> tuple[ClusterSnapshotSummary, ...]:
        with self._workspace.get_session() as session:
            rows = session.execute(
                select(EvidenceClusterSnapshot).order_by(
                    EvidenceClusterSnapshot.captured_at,
                    EvidenceClusterSnapshot.id,
                )
            ).scalars()
            return tuple(_summary(_envelope(row)) for row in rows)

    def diff(self, before_snapshot_id: str, after_snapshot_id: str) -> ClusterSnapshotDiff:
        before = self._load(before_snapshot_id)
        after = self._load(after_snapshot_id)
        if before.workspace != after.workspace:
            raise ValueError("Cluster snapshots belong to different workspaces.")
        before_nodes = {
            str(item["id"]): item for item in before.nodes if item.get("layer") == "entity"
        }
        after_nodes = {
            str(item["id"]): item for item in after.nodes if item.get("layer") == "entity"
        }
        before_edges = {
            str(item["id"]): item for item in before.edges if item.get("layer") == "entity"
        }
        after_edges = {
            str(item["id"]): item for item in after.edges if item.get("layer") == "entity"
        }
        added_nodes, removed_nodes, changed_nodes = _changes(before_nodes, after_nodes)
        added_edges, removed_edges, changed_edges = _changes(before_edges, after_edges)
        before_membership = _membership(before.clusters)
        after_membership = _membership(after.clusters)
        membership_changes = tuple(
            ClusterMembershipChange(
                entity_ref=reference,
                before_cluster_id=(before_membership.get(reference) or (None, ()))[0],
                after_cluster_id=(after_membership.get(reference) or (None, ()))[0],
                before_members=(before_membership.get(reference) or (None, ()))[1],
                after_members=(after_membership.get(reference) or (None, ()))[1],
            )
            for reference in sorted(set(before_membership) | set(after_membership))
            if (before_membership.get(reference) or (None, ()))[1]
            != (after_membership.get(reference) or (None, ()))[1]
        )
        before_all_edges = {str(item["id"]): item for item in before.edges}
        after_all_edges = {str(item["id"]): item for item in after.edges}
        added_all_edges, _removed_all_edges, _changed_all_edges = _changes(
            before_all_edges, after_all_edges
        )
        added_contradictions = tuple(
            item
            for item in added_all_edges
            if str((item.after or {}).get("relationship", "")).casefold()
            in {"contradicts", "contradiction"}
        )
        return ClusterSnapshotDiff(
            workspace=before.workspace,
            before_snapshot_id=before.id,
            after_snapshot_id=after.id,
            added_entities=added_nodes,
            removed_entities=removed_nodes,
            reclassified_entities=changed_nodes,
            added_relationships=added_edges,
            removed_relationships=removed_edges,
            reclassified_relationships=changed_edges,
            cluster_membership_changes=membership_changes,
            added_recorded_contradictions=added_contradictions,
        )

    def _load(self, snapshot_id: str) -> ClusterSnapshotEnvelope:
        with self._workspace.get_session() as session:
            row = session.get(EvidenceClusterSnapshot, snapshot_id)
            if row is None:
                raise ValueError("Evidence-cluster snapshot was not found in this workspace.")
            return _envelope(row)


def _envelope(row: EvidenceClusterSnapshot) -> ClusterSnapshotEnvelope:
    return ClusterSnapshotEnvelope.model_validate(row.snapshot)


def _summary(snapshot: ClusterSnapshotEnvelope) -> ClusterSnapshotSummary:
    return ClusterSnapshotSummary(
        id=snapshot.id,
        graph_fingerprint=snapshot.graph_fingerprint,
        captured_by=snapshot.captured_by,
        captured_at=snapshot.captured_at,
        node_count=len(snapshot.nodes),
        edge_count=len(snapshot.edges),
        cluster_count=len(snapshot.clusters),
    )


def _changes(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
) -> tuple[tuple[ClusterChange, ...], tuple[ClusterChange, ...], tuple[ClusterChange, ...]]:
    added = tuple(
        ClusterChange(id=identifier, after=after[identifier])
        for identifier in sorted(set(after) - set(before))
    )
    removed = tuple(
        ClusterChange(id=identifier, before=before[identifier])
        for identifier in sorted(set(before) - set(after))
    )
    changed = tuple(
        ClusterChange(id=identifier, before=before[identifier], after=after[identifier])
        for identifier in sorted(set(before) & set(after))
        if _canonical(before[identifier]) != _canonical(after[identifier])
    )
    return added, removed, changed


def _membership(clusters: tuple[dict[str, Any], ...]) -> dict[str, tuple[str, tuple[str, ...]]]:
    result: dict[str, tuple[str, tuple[str, ...]]] = {}
    for cluster in clusters:
        members = tuple(sorted(str(entity["reference"]) for entity in cluster.get("entities", ())))
        for reference in members:
            result[reference] = (str(cluster["id"]), members)
    return result


def _canonical(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
