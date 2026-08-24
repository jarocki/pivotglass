"""Deterministic Synapse shadow manifests and parity receipts."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from adversary_pursuit.core.graph_repository import GraphRepositorySnapshot
from adversary_pursuit.integrations.mapping import synapse_lift


class SynapseManifestNode(BaseModel):
    """One desired Synapse node without executable Storm."""

    model_config = ConfigDict(frozen=True)

    id: str
    form: str
    value: str
    source_node_ids: tuple[str, ...]
    properties: dict[str, Any]


class SynapseManifestEdge(BaseModel):
    """One desired typed edge retaining Pivotglass provenance."""

    model_config = ConfigDict(frozen=True)

    id: str
    source: str
    target: str
    relationship: str
    truth_kind: str
    provenance_refs: tuple[str, ...]
    rationale: str
    directed: bool


class SynapseShadowManifest(BaseModel):
    """Versioned desired state for shadow comparison before cutover."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-synapse-shadow-1.0"] = (
        "pivotglass-synapse-shadow-1.0"
    )
    workspace: str
    source_snapshot_sha256: str
    nodes: tuple[SynapseManifestNode, ...]
    edges: tuple[SynapseManifestEdge, ...]
    digest_sha256: str


class SynapseParityReceipt(BaseModel):
    """Exact comparison between desired and observed Synapse manifest state."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-synapse-parity-1.0"] = (
        "pivotglass-synapse-parity-1.0"
    )
    expected_digest_sha256: str
    observed_digest_sha256: str
    metadata_match: bool
    nodes_match: bool
    edges_match: bool
    missing_node_ids: tuple[str, ...]
    extra_node_ids: tuple[str, ...]
    changed_node_ids: tuple[str, ...]
    missing_edge_ids: tuple[str, ...]
    extra_edge_ids: tuple[str, ...]
    changed_edge_ids: tuple[str, ...]
    cutover_ready: bool


def build_synapse_shadow_manifest(snapshot: GraphRepositorySnapshot) -> SynapseShadowManifest:
    """Compile a repository snapshot into non-executable desired Synapse state."""
    grouped: dict[tuple[str, str], list[Any]] = defaultdict(list)
    node_target: dict[str, tuple[str, str]] = {}
    for node in snapshot.nodes:
        form, value = _form_and_value(node.kind, node.label, node.id)
        grouped[(form, value)].append(node)
        node_target[node.id] = (form, value)

    nodes: list[SynapseManifestNode] = []
    target_id: dict[tuple[str, str], str] = {}
    for (form, value), source_nodes in sorted(grouped.items()):
        manifest_id = _stable_id("synapse-node", {"form": form, "value": value})
        target_id[(form, value)] = manifest_id
        nodes.append(
            SynapseManifestNode(
                id=manifest_id,
                form=form,
                value=value,
                source_node_ids=tuple(sorted(item.id for item in source_nodes)),
                properties={
                    "pivotglass:layers": sorted({item.layer for item in source_nodes}),
                    "pivotglass:kinds": sorted({item.kind for item in source_nodes}),
                    "pivotglass:labels": sorted({item.label for item in source_nodes}),
                    "pivotglass:record_refs": sorted(
                        {item.record_ref for item in source_nodes}
                    ),
                    "pivotglass:states": sorted(
                        {item.state for item in source_nodes if item.state}
                    ),
                },
            )
        )

    edges: list[SynapseManifestEdge] = []
    for edge in snapshot.edges:
        source = target_id[node_target[edge.source]]
        target = target_id[node_target[edge.target]]
        payload = {
            "source": source,
            "target": target,
            "relationship": edge.relationship,
            "truth_kind": edge.truth_kind,
            "provenance_refs": sorted(edge.provenance_refs),
        }
        edges.append(
            SynapseManifestEdge(
                id=_stable_id("synapse-edge", payload),
                source=source,
                target=target,
                relationship=edge.relationship,
                truth_kind=edge.truth_kind,
                provenance_refs=edge.provenance_refs,
                rationale=edge.rationale,
                directed=edge.directed,
            )
        )
    nodes_tuple = tuple(sorted(nodes, key=lambda item: item.id))
    edges_tuple = tuple(sorted(edges, key=lambda item: item.id))
    content = _manifest_content(snapshot.workspace, snapshot.digest_sha256, nodes_tuple, edges_tuple)
    return SynapseShadowManifest(
        workspace=snapshot.workspace,
        source_snapshot_sha256=snapshot.digest_sha256,
        nodes=nodes_tuple,
        edges=edges_tuple,
        digest_sha256=_digest(content),
    )


def compare_synapse_shadow(
    expected: SynapseShadowManifest,
    observed: SynapseShadowManifest,
) -> SynapseParityReceipt:
    """Compare two manifests without treating a count match as graph parity."""
    expected_nodes = {item.id: item.model_dump(mode="json") for item in expected.nodes}
    observed_nodes = {item.id: item.model_dump(mode="json") for item in observed.nodes}
    expected_edges = {item.id: item.model_dump(mode="json") for item in expected.edges}
    observed_edges = {item.id: item.model_dump(mode="json") for item in observed.edges}
    missing_nodes, extra_nodes, changed_nodes = _differences(expected_nodes, observed_nodes)
    missing_edges, extra_edges, changed_edges = _differences(expected_edges, observed_edges)
    metadata_match = (
        expected.schema_version == observed.schema_version
        and expected.workspace == observed.workspace
        and expected.source_snapshot_sha256 == observed.source_snapshot_sha256
    )
    nodes_match = not (missing_nodes or extra_nodes or changed_nodes)
    edges_match = not (missing_edges or extra_edges or changed_edges)
    return SynapseParityReceipt(
        expected_digest_sha256=expected.digest_sha256,
        observed_digest_sha256=observed.digest_sha256,
        metadata_match=metadata_match,
        nodes_match=nodes_match,
        edges_match=edges_match,
        missing_node_ids=missing_nodes,
        extra_node_ids=extra_nodes,
        changed_node_ids=changed_nodes,
        missing_edge_ids=missing_edges,
        extra_edge_ids=extra_edges,
        changed_edge_ids=changed_edges,
        cutover_ready=(
            metadata_match
            and nodes_match
            and edges_match
            and expected.digest_sha256 == observed.digest_sha256
        ),
    )


def _form_and_value(kind: str, label: str, node_id: str) -> tuple[str, str]:
    try:
        lift = synapse_lift(kind, label)
        return lift.form, lift.value
    except (ValueError, UnicodeError):
        return "pivotglass:record", node_id


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    return f"{prefix}-{_digest(payload)[:24]}"


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _manifest_content(
    workspace: str,
    source_digest: str,
    nodes: tuple[SynapseManifestNode, ...],
    edges: tuple[SynapseManifestEdge, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "pivotglass-synapse-shadow-1.0",
        "workspace": workspace,
        "source_snapshot_sha256": source_digest,
        "nodes": [item.model_dump(mode="json") for item in nodes],
        "edges": [item.model_dump(mode="json") for item in edges],
    }


def _differences(
    expected: dict[str, dict[str, Any]],
    observed: dict[str, dict[str, Any]],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    missing = tuple(sorted(set(expected) - set(observed)))
    extra = tuple(sorted(set(observed) - set(expected)))
    changed = tuple(
        sorted(key for key in set(expected) & set(observed) if expected[key] != observed[key])
    )
    return missing, extra, changed
