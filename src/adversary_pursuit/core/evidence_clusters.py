"""Deterministic summaries of connected, admitted entity-graph components."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from pydantic import BaseModel, ConfigDict

from adversary_pursuit.core.framework_projections import FrameworkProjectionAuthority
from adversary_pursuit.core.graph_repository import WorkspaceGraphRepository
from adversary_pursuit.dossier.slot_inference import infer_dossier_state
from adversary_pursuit.dossier.slots import SlotStatus


class EvidenceClusterEntity(BaseModel):
    model_config = ConfigDict(frozen=True)

    reference: str
    entity_type: str
    value: str


class EvidenceClusterBehavior(BaseModel):
    model_config = ConfigDict(frozen=True)

    framework: str
    framework_version: str
    content_id: str
    content_label: str
    state: str
    mapping_id: str


class EvidenceCluster(BaseModel):
    """One stable connected component; never an actor-attribution claim."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "pivotglass-evidence-cluster-1.0"
    id: str
    workspace: str
    entities: tuple[EvidenceClusterEntity, ...]
    edge_ids: tuple[str, ...]
    truth_classes: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    provenance_sources: tuple[str, ...]
    first_observed: str | None
    last_observed: str | None
    mapped_behaviors: tuple[EvidenceClusterBehavior, ...]
    dossier_gaps: tuple[str, ...]
    caveat: str = (
        "A connected evidence cluster is a navigation summary, not proof of common control, "
        "campaign membership, or actor attribution."
    )


def _stable_cluster_id(record_refs: list[str]) -> str:
    payload = json.dumps(sorted(record_refs), separators=(",", ":"))
    return f"evidence-cluster-{hashlib.sha256(payload.encode()).hexdigest()[:24]}"


def build_evidence_clusters(workspace_manager: Any) -> tuple[EvidenceCluster, ...]:
    """Return stable entity components from the governed graph snapshot.

    Only entity-layer edges already admitted by the graph authority participate.
    Isolated stored entities remain visible as one-node clusters.
    """

    snapshot = WorkspaceGraphRepository(workspace_manager).snapshot()
    nodes = {node.id: node for node in snapshot.nodes if node.layer == "entity"}
    parents = {node_id: node_id for node_id in nodes}

    def find(node_id: str) -> str:
        parent = parents[node_id]
        while parent != parents[parent]:
            parents[parent] = parents[parents[parent]]
            parent = parents[parent]
        parents[node_id] = parent
        return parent

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return
        low, high = sorted((left_root, right_root))
        parents[high] = low

    entity_edges = [
        edge
        for edge in snapshot.edges
        if edge.layer == "entity" and edge.source in nodes and edge.target in nodes
    ]
    for edge in entity_edges:
        union(edge.source, edge.target)

    members: dict[str, list[str]] = defaultdict(list)
    for node_id in sorted(nodes):
        members[find(node_id)].append(node_id)

    observations = workspace_manager.get_observations()
    observations_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for observation in observations:
        observations_by_entity[str(observation["entity_ref"])].append(observation)
    mappings = FrameworkProjectionAuthority(workspace_manager).list()
    objects = {
        str(item.get("id")): item
        for item in workspace_manager.get_stix_objects()
        if item.get("id")
    }

    result: list[EvidenceCluster] = []
    for component_ids in members.values():
        record_refs = sorted(nodes[node_id].record_ref for node_id in component_ids)
        edges = sorted(
            (
                edge
                for edge in entity_edges
                if edge.source in component_ids and edge.target in component_ids
            ),
            key=lambda item: item.id,
        )
        component_observations = [
            observation
            for record_ref in record_refs
            for observation in observations_by_entity.get(record_ref, ())
        ]
        times = sorted(
            str(observation["fetched_at"])
            for observation in component_observations
            if observation.get("fetched_at")
        )
        observation_ids = {str(item["id"]) for item in component_observations}
        behaviors = tuple(
            EvidenceClusterBehavior(
                framework=mapping.framework.value,
                framework_version=mapping.framework_version,
                content_id=mapping.content_id,
                content_label=mapping.content_label,
                state=mapping.state.value,
                mapping_id=mapping.id,
            )
            for mapping in sorted(mappings, key=lambda item: item.id)
            if observation_ids.intersection(mapping.evidence_refs)
        )
        dossier = infer_dossier_state(
            [objects[record_ref] for record_ref in record_refs if record_ref in objects]
        )
        gaps = tuple(
            slot.value
            for slot, state in dossier.slots.items()
            if state.status in {SlotStatus.EMPTY, SlotStatus.PARTIAL}
        )
        provenance_refs = sorted(
            {
                *observation_ids,
                *(reference for edge in edges for reference in edge.provenance_refs),
            }
        )
        result.append(
            EvidenceCluster(
                id=_stable_cluster_id(record_refs),
                workspace=snapshot.workspace,
                entities=tuple(
                    EvidenceClusterEntity(
                        reference=nodes[node_id].record_ref,
                        entity_type=nodes[node_id].kind,
                        value=nodes[node_id].label,
                    )
                    for node_id in sorted(component_ids, key=lambda item: nodes[item].record_ref)
                ),
                edge_ids=tuple(edge.id for edge in edges),
                truth_classes=tuple(sorted({edge.truth_kind for edge in edges})),
                provenance_refs=tuple(provenance_refs),
                provenance_sources=tuple(
                    sorted(
                        {
                            str(observation["source_id"])
                            for observation in component_observations
                            if observation.get("source_id")
                        }
                    )
                ),
                first_observed=times[0] if times else None,
                last_observed=times[-1] if times else None,
                mapped_behaviors=behaviors,
                dossier_gaps=gaps,
            )
        )

    return tuple(sorted(result, key=lambda item: (item.last_observed or "", item.id), reverse=True))
