"""Versioned graph-repository boundary for local-to-Synapse migration."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from adversary_pursuit.core.investigation_graph import build_investigation_graph


class GraphRepositoryNode(BaseModel):
    """One governed graph node, independent of the storage implementation."""

    model_config = ConfigDict(frozen=True)

    id: str
    layer: str
    kind: str
    label: str
    record_ref: str
    state: str | None = None
    attributes: dict[str, Any]


class GraphRepositoryEdge(BaseModel):
    """One governed edge with its truth class and immutable basis references."""

    model_config = ConfigDict(frozen=True)

    id: str
    layer: str
    source: str
    target: str
    relationship: str
    truth_kind: str
    provenance_refs: tuple[str, ...]
    rationale: str
    directed: bool


class GraphRepositorySnapshot(BaseModel):
    """Canonical snapshot transferred between graph repository backends."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-graph-repository-1.0"] = (
        "pivotglass-graph-repository-1.0"
    )
    workspace: str
    source_backend: str
    nodes: tuple[GraphRepositoryNode, ...]
    edges: tuple[GraphRepositoryEdge, ...]
    caveats: tuple[str, ...]
    digest_sha256: str


class GraphRepository(Protocol):
    """The single persistence boundary a future Synapse backend must satisfy."""

    def snapshot(self) -> GraphRepositorySnapshot: ...


class WorkspaceGraphRepository:
    """Current local-workspace implementation used during guarded migration."""

    def __init__(self, workspace_manager: Any) -> None:
        self._workspace = workspace_manager

    def snapshot(self) -> GraphRepositorySnapshot:
        projection = build_investigation_graph(self._workspace)
        nodes = tuple(
            GraphRepositoryNode(
                id=node.id,
                layer=node.layer.value,
                kind=node.kind,
                label=node.label,
                record_ref=node.record_ref,
                state=node.state,
                attributes=node.attributes,
            )
            for node in sorted(projection.nodes, key=lambda item: item.id)
        )
        edges = tuple(
            GraphRepositoryEdge(
                id=edge.id,
                layer=edge.layer.value,
                source=edge.source,
                target=edge.target,
                relationship=edge.relationship,
                truth_kind=edge.truth_kind.value,
                provenance_refs=tuple(sorted(edge.provenance_refs)),
                rationale=edge.rationale,
                directed=edge.directed,
            )
            for edge in sorted(projection.edges, key=lambda item: item.id)
        )
        content = {
            "schema_version": "pivotglass-graph-repository-1.0",
            "workspace": projection.workspace,
            "nodes": [item.model_dump(mode="json") for item in nodes],
            "edges": [item.model_dump(mode="json") for item in edges],
            "caveats": sorted(projection.caveats),
        }
        digest = hashlib.sha256(
            json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return GraphRepositorySnapshot(
            workspace=projection.workspace,
            source_backend="workspace-local",
            nodes=nodes,
            edges=edges,
            caveats=tuple(sorted(projection.caveats)),
            digest_sha256=digest,
        )
