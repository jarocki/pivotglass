"""One read-only two-layer graph projection over workspace authorities.

The entity layer projects stored STIX objects and explicit or conservative
property relationships. The epistemic layer projects questions, observations,
assertions, hypotheses, framework mappings, and their typed links. It does not
persist a second graph or manufacture relationships during rendering.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from adversary_pursuit.core.analytic_ledger import AnalyticLedger
from adversary_pursuit.core.framework_projections import FrameworkProjectionAuthority
from adversary_pursuit.core.graph import RelationshipGraph, persisted_relationships


class GraphLayer(StrEnum):
    ENTITY = "entity"
    EPISTEMIC = "epistemic"
    BRIDGE = "bridge"


class GraphTruthKind(StrEnum):
    OBSERVED = "observed"
    DERIVED_NAVIGATION = "derived_navigation"
    ANALYST_ASSERTION = "analyst_assertion"
    STRUCTURAL = "structural"


class InvestigationGraphNode(BaseModel):
    """A display-safe node retaining its authoritative record reference."""

    model_config = ConfigDict(frozen=True)

    id: str
    layer: GraphLayer
    kind: str
    label: str
    record_ref: str
    state: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class InvestigationGraphEdge(BaseModel):
    """A typed directed edge with explicit provenance and truth status."""

    model_config = ConfigDict(frozen=True)

    id: str
    layer: GraphLayer
    source: str
    target: str
    relationship: str
    truth_kind: GraphTruthKind
    provenance_refs: tuple[str, ...]
    rationale: str
    directed: bool = True


class InvestigationGraphProjection(BaseModel):
    """The complete entity and epistemic projection for one workspace."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "investigation-graph-1.0"
    workspace: str
    nodes: tuple[InvestigationGraphNode, ...]
    edges: tuple[InvestigationGraphEdge, ...]
    counts: dict[str, dict[str, int]]
    caveats: tuple[str, ...]


def build_investigation_graph(workspace_manager: Any) -> InvestigationGraphProjection:
    """Project the active workspace without changing any authoritative record."""

    objects = workspace_manager.get_stix_objects()
    relationships = persisted_relationships(workspace_manager)
    observations = workspace_manager.get_observations()
    analysis = AnalyticLedger(workspace_manager).snapshot()
    mappings = FrameworkProjectionAuthority(workspace_manager).list()

    nodes: dict[str, InvestigationGraphNode] = {}
    edges: dict[str, InvestigationGraphEdge] = {}
    observation_refs_by_entity: dict[str, list[str]] = {}
    for observation in observations:
        observation_refs_by_entity.setdefault(str(observation["entity_ref"]), []).append(
            str(observation["id"])
        )

    for item in objects:
        record_ref = str(item.get("id", ""))
        if not record_ref:
            continue
        node_id = _entity_node_id(record_ref)
        nodes[node_id] = InvestigationGraphNode(
            id=node_id,
            layer=GraphLayer.ENTITY,
            kind=str(item.get("type", "unknown")),
            label=str(
                item.get("value", item.get("x_indicator_value", item.get("name", "unavailable")))
            ),
            record_ref=record_ref,
            attributes={"source_module": item.get("x_ap_source_module")},
        )

    explicit_keys: set[tuple[str, str, str]] = set()
    for relationship in relationships:
        source_ref = str(relationship.get("source_ref", ""))
        target_ref = str(relationship.get("target_ref", ""))
        relation = str(relationship.get("relationship_type", "related-to"))
        source = _entity_node_id(source_ref)
        target = _entity_node_id(target_ref)
        if source not in nodes or target not in nodes:
            continue
        relationship_ref = str(relationship.get("id", ""))
        provenance = tuple(observation_refs_by_entity.get(relationship_ref, ()))
        if not provenance and relationship_ref:
            provenance = (relationship_ref,)
        if not provenance:
            continue
        explicit_keys.add((source_ref, target_ref, relation))
        _put_edge(
            edges,
            layer=GraphLayer.ENTITY,
            source=source,
            target=target,
            relationship=relation,
            truth_kind=GraphTruthKind.OBSERVED,
            provenance_refs=provenance,
            rationale="Stored STIX Relationship Object.",
        )

    entity_graph = RelationshipGraph()
    entity_graph.build_from_workspace(objects, relationships)
    for relationship in entity_graph.to_dict()["edges"]:
        source_ref = str(relationship["source"])
        target_ref = str(relationship["target"])
        relation = str(relationship["relationship"])
        if relationship["basis"] != "property" or (
            source_ref,
            target_ref,
            relation,
        ) in explicit_keys:
            continue
        provenance = tuple(
            dict.fromkeys(
                [
                    *observation_refs_by_entity.get(source_ref, ()),
                    *observation_refs_by_entity.get(target_ref, ()),
                ]
            )
        )
        if not provenance:
            continue
        _put_edge(
            edges,
            layer=GraphLayer.ENTITY,
            source=_entity_node_id(source_ref),
            target=_entity_node_id(target_ref),
            relationship=relation,
            truth_kind=GraphTruthKind.DERIVED_NAVIGATION,
            provenance_refs=provenance,
            rationale="Conservative typed-property pivot; not an observed STIX relationship.",
        )

    for observation in observations:
        record_ref = str(observation["id"])
        node_id = _epistemic_node_id("observation", record_ref)
        nodes[node_id] = InvestigationGraphNode(
            id=node_id,
            layer=GraphLayer.EPISTEMIC,
            kind="observation",
            label=(
                f"{observation['source_module']} observed "
                f"{observation.get('entity_value') or observation['entity_type']}"
            ),
            record_ref=record_ref,
            attributes={
                "source": observation["source_module"],
                "fetched_at": observation["fetched_at"],
            },
        )
        entity_node = _entity_node_id(str(observation["entity_ref"]))
        if entity_node in nodes:
            _put_edge(
                edges,
                layer=GraphLayer.BRIDGE,
                source=node_id,
                target=entity_node,
                relationship="observes",
                truth_kind=GraphTruthKind.OBSERVED,
                provenance_refs=(record_ref,),
                rationale="Immutable source observation of the normalized entity.",
            )

    record_collections = {
        "question": (analysis["questions"], "text", "status"),
        "assertion": (analysis["assertions"], "statement", "status"),
        "hypothesis": (analysis["hypotheses"], "statement", "status"),
    }
    for kind, (records, label_field, state_field) in record_collections.items():
        for record in records:
            record_ref = str(record["id"])
            node_id = _epistemic_node_id(kind, record_ref)
            attributes = {"author_kind": record.get("author_kind", record.get("created_by"))}
            if kind == "assertion":
                attributes["assertion_type"] = record.get("assertion_type")
            nodes[node_id] = InvestigationGraphNode(
                id=node_id,
                layer=GraphLayer.EPISTEMIC,
                kind=kind,
                label=str(record[label_field]),
                record_ref=record_ref,
                state=str(record.get(state_field, "")) or None,
                attributes=attributes,
            )

    for item in analysis["lifecycle_items"]:
        if item.get("record_kind") != "external_analysis" or not item.get("record_id"):
            continue
        record_ref = str(item["record_id"])
        criteria = item.get("criteria") if isinstance(item.get("criteria"), dict) else {}
        nodes[_epistemic_node_id("external_analysis", record_ref)] = InvestigationGraphNode(
            id=_epistemic_node_id("external_analysis", record_ref),
            layer=GraphLayer.EPISTEMIC,
            kind="external_analysis",
            label=str(item.get("statement") or "External analysis proposal"),
            record_ref=record_ref,
            state=str(item.get("analyst_disposition") or "pending"),
            attributes={
                "provider": criteria.get("provider"),
                "operation": criteria.get("operation"),
                "truth_kind": "external-derived-proposal",
                "caveats": criteria.get("caveats", []),
            },
        )

    for hypothesis in analysis["hypotheses"]:
        _put_record_edge(
            edges,
            nodes,
            source_kind="hypothesis",
            source_id=str(hypothesis["id"]),
            target_kind="question",
            target_id=str(hypothesis["question_id"]),
            relationship="answers",
            provenance_ref=str(hypothesis["id"]),
            rationale="Persisted hypothesis-to-question membership.",
        )

    for link in analysis["evidence_links"]:
        _put_record_edge(
            edges,
            nodes,
            source_kind=str(link["source_kind"]),
            source_id=str(link["source_id"]),
            target_kind=str(link["target_kind"]),
            target_id=str(link["target_id"]),
            relationship=str(link["stance"]),
            provenance_ref=f"evidence-link:{link['id']}",
            rationale=str(link["rationale"]),
        )

    for assertion in analysis["assertions"]:
        assertion_node = _epistemic_node_id("assertion", str(assertion["id"]))
        for field, relation in (("subject_ref", "has-subject"), ("object_ref", "has-object")):
            entity_ref = assertion.get(field)
            entity_node = _entity_node_id(str(entity_ref)) if entity_ref else ""
            if entity_node in nodes:
                _put_edge(
                    edges,
                    layer=GraphLayer.BRIDGE,
                    source=assertion_node,
                    target=entity_node,
                    relationship=relation,
                    truth_kind=GraphTruthKind.ANALYST_ASSERTION,
                    provenance_refs=(str(assertion["id"]),),
                    rationale=str(assertion["statement"]),
                )

    for mapping in mappings:
        node_id = _epistemic_node_id("framework_mapping", mapping.id)
        nodes[node_id] = InvestigationGraphNode(
            id=node_id,
            layer=GraphLayer.EPISTEMIC,
            kind="framework_mapping",
            label=f"{mapping.content_label} ({mapping.content_id})",
            record_ref=mapping.id,
            state=mapping.state.value,
            attributes={
                "framework": mapping.framework.value,
                "framework_version": mapping.framework_version,
                "confidence": mapping.confidence.value,
            },
        )
        for observation_ref in mapping.evidence_refs:
            target = _epistemic_node_id("observation", observation_ref)
            if target in nodes:
                _put_edge(
                    edges,
                    layer=GraphLayer.EPISTEMIC,
                    source=node_id,
                    target=target,
                    relationship="derived-from",
                    truth_kind=GraphTruthKind.ANALYST_ASSERTION,
                    provenance_refs=(mapping.id, observation_ref),
                    rationale=mapping.basis,
                )
        if mapping.supersedes_id:
            target = _epistemic_node_id("framework_mapping", mapping.supersedes_id)
            if target in nodes:
                _put_edge(
                    edges,
                    layer=GraphLayer.EPISTEMIC,
                    source=node_id,
                    target=target,
                    relationship="supersedes",
                    truth_kind=GraphTruthKind.STRUCTURAL,
                    provenance_refs=(mapping.id,),
                    rationale="Persisted framework-mapping supersession.",
                )

    for contradiction in analysis["contradictions"]:
        _put_record_edge(
            edges,
            nodes,
            source_kind=str(contradiction["left_kind"]),
            source_id=str(contradiction["left_id"]),
            target_kind=str(contradiction["right_kind"]),
            target_id=str(contradiction["right_id"]),
            relationship="contradicts",
            provenance_ref=str(contradiction["id"]),
            rationale=str(contradiction["summary"]),
        )

    for assessment_kind in ("confidence", "likelihood"):
        for assessment in analysis[assessment_kind]:
            target = _epistemic_node_id(
                str(assessment["target_kind"]), str(assessment["target_id"])
            )
            node = nodes.get(target)
            if node is not None:
                attributes = dict(node.attributes)
                attributes[assessment_kind] = {
                    key: value
                    for key, value in assessment.items()
                    if key not in {"target_kind", "target_id"}
                }
                nodes[target] = node.model_copy(update={"attributes": attributes})

    node_counts: dict[str, int] = {}
    for node in nodes.values():
        node_counts[node.layer.value] = node_counts.get(node.layer.value, 0) + 1
    edge_counts: dict[str, int] = {}
    for edge in edges.values():
        edge_counts[edge.layer.value] = edge_counts.get(edge.layer.value, 0) + 1
    return InvestigationGraphProjection(
        workspace=workspace_manager.active,
        nodes=tuple(nodes.values()),
        edges=tuple(edges.values()),
        counts={"nodes": node_counts, "edges": edge_counts},
        caveats=(
            "Derived navigation edges are typed pivots, not observed relationships.",
            "Moving or filtering a node changes presentation only, never evidence.",
            "No model-generated edge is authoritative without analyst disposition.",
        ),
    )


def _entity_node_id(record_ref: str) -> str:
    return f"entity:{record_ref}"


def _epistemic_node_id(kind: str, record_ref: str) -> str:
    return f"epistemic:{kind}:{record_ref}"


def _put_record_edge(
    edges: dict[str, InvestigationGraphEdge],
    nodes: dict[str, InvestigationGraphNode],
    *,
    source_kind: str,
    source_id: str,
    target_kind: str,
    target_id: str,
    relationship: str,
    provenance_ref: str,
    rationale: str,
) -> None:
    source = _epistemic_node_id(source_kind, source_id)
    target = _epistemic_node_id(target_kind, target_id)
    if source not in nodes or target not in nodes:
        return
    _put_edge(
        edges,
        layer=GraphLayer.EPISTEMIC,
        source=source,
        target=target,
        relationship=relationship,
        truth_kind=GraphTruthKind.STRUCTURAL,
        provenance_refs=(provenance_ref,),
        rationale=rationale,
    )


def _put_edge(
    edges: dict[str, InvestigationGraphEdge],
    *,
    layer: GraphLayer,
    source: str,
    target: str,
    relationship: str,
    truth_kind: GraphTruthKind,
    provenance_refs: tuple[str, ...],
    rationale: str,
) -> None:
    if not provenance_refs:
        raise ValueError("Every investigation-graph edge requires provenance.")
    payload = json.dumps(
        {
            "layer": layer.value,
            "source": source,
            "target": target,
            "relationship": relationship,
            "provenance_refs": provenance_refs,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    edge_id = f"graph-edge-{hashlib.sha256(payload.encode()).hexdigest()[:24]}"
    edges[edge_id] = InvestigationGraphEdge(
        id=edge_id,
        layer=layer,
        source=source,
        target=target,
        relationship=relationship,
        truth_kind=truth_kind,
        provenance_refs=provenance_refs,
        rationale=rationale,
    )
