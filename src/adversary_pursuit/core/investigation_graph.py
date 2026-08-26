"""One read-only two-layer graph projection over workspace authorities.

The entity layer projects stored STIX objects and explicit or conservative
property relationships. The epistemic layer projects questions, observations,
assertions, hypotheses, framework mappings, and their typed links. It does not
persist a second graph or manufacture relationships during rendering.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from adversary_pursuit.core.analytic_ledger import AnalyticLedger
from adversary_pursuit.core.framework_projections import FrameworkProjectionAuthority
from adversary_pursuit.core.graph import RelationshipGraph, persisted_relationships
from adversary_pursuit.models.database import AnalystNote
from adversary_pursuit.models.database import GraphPresentationLayout as GraphPresentationLayoutRow

_LAYOUT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")
_MAX_LAYOUT_NODES = 250


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


class GraphPoint(BaseModel):
    """One presentation-only node position."""

    model_config = ConfigDict(frozen=True)

    x: float
    y: float


class GraphViewport(BaseModel):
    """Pan and zoom state for a saved graph view."""

    model_config = ConfigDict(frozen=True)

    x: float = 0.0
    y: float = 0.0
    scale: float = 1.0


class GraphLayoutFilters(BaseModel):
    """Allow-listed filters that affect visibility, never graph truth."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(default="", max_length=120)
    layers: tuple[GraphLayer, ...] = ()
    kinds: tuple[str, ...] = ()
    truth_kinds: tuple[GraphTruthKind, ...] = ()


class GraphPresentationDraft(BaseModel):
    """Validated payload for creating or replacing one named layout."""

    model_config = ConfigDict(frozen=True)

    graph_schema_version: str = Field(default="investigation-graph-1.0", max_length=64)
    positions: dict[str, GraphPoint] = Field(default_factory=dict)
    pinned_refs: tuple[str, ...] = ()
    filters: GraphLayoutFilters = Field(default_factory=GraphLayoutFilters)
    viewport: GraphViewport = Field(default_factory=GraphViewport)


class GraphPresentationRecord(BaseModel):
    """Durable named graph layout returned to TUI and web clients."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    graph_schema_version: str
    positions: dict[str, GraphPoint]
    pinned_refs: tuple[str, ...]
    filters: GraphLayoutFilters
    viewport: GraphViewport
    created_by: str
    created_at: datetime
    updated_at: datetime


class GraphAnnotationRecord(BaseModel):
    """An analyst note resolved through an existing graph node."""

    model_config = ConfigDict(frozen=True)

    id: int
    node_id: str
    record_ref: str
    content: str
    created_at: datetime


class GraphPresentationAuthority:
    """Single persistence authority for graph view state and annotations.

    Layout records are presentation state. Annotations deliberately reuse the
    existing analyst-note table so the graph cannot create a competing note or
    assertion store.
    """

    def __init__(self, workspace_manager: Any) -> None:
        self.workspace_manager = workspace_manager

    def list(self) -> tuple[GraphPresentationRecord, ...]:
        with self.workspace_manager.get_session() as session:
            rows = list(
                session.execute(
                    select(GraphPresentationLayoutRow).order_by(
                        GraphPresentationLayoutRow.updated_at.desc(),
                        GraphPresentationLayoutRow.name,
                    )
                ).scalars()
            )
            return tuple(_presentation_record(row) for row in rows)

    def get(self, name: str) -> GraphPresentationRecord:
        layout_id = _layout_id(_normalize_layout_name(name))
        with self.workspace_manager.get_session() as session:
            row = session.get(GraphPresentationLayoutRow, layout_id)
            if row is None:
                raise ValueError(f"graph layout does not exist: {name}")
            return _presentation_record(row)

    def save(
        self,
        name: str,
        payload: GraphPresentationDraft | dict[str, Any],
        *,
        created_by: str = "human",
    ) -> GraphPresentationRecord:
        normalized_name = _normalize_layout_name(name)
        draft = (
            payload
            if isinstance(payload, GraphPresentationDraft)
            else GraphPresentationDraft.model_validate(payload)
        )
        _validate_presentation_draft(draft, build_investigation_graph(self.workspace_manager))
        layout_id = _layout_id(normalized_name)
        now = datetime.now(timezone.utc)
        encoded = draft.model_dump(mode="json")
        with self.workspace_manager.get_session() as session:
            row = session.get(GraphPresentationLayoutRow, layout_id)
            if row is None:
                row = GraphPresentationLayoutRow(
                    id=layout_id,
                    name=normalized_name,
                    graph_schema_version=draft.graph_schema_version,
                    positions=encoded["positions"],
                    pinned_refs=encoded["pinned_refs"],
                    filters=encoded["filters"],
                    viewport=encoded["viewport"],
                    created_by=created_by,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.name = normalized_name
                row.graph_schema_version = draft.graph_schema_version
                row.positions = encoded["positions"]
                row.pinned_refs = encoded["pinned_refs"]
                row.filters = encoded["filters"]
                row.viewport = encoded["viewport"]
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _presentation_record(row)

    def delete(self, name: str, *, confirm: str) -> None:
        normalized_name = _normalize_layout_name(name)
        if confirm != normalized_name:
            raise ValueError("graph layout deletion requires the exact layout name as confirmation")
        layout_id = _layout_id(normalized_name)
        with self.workspace_manager.get_session() as session:
            row = session.get(GraphPresentationLayoutRow, layout_id)
            if row is None:
                raise ValueError(f"graph layout does not exist: {name}")
            session.delete(row)
            session.commit()

    def annotate(self, node_id: str, content: str) -> GraphAnnotationRecord:
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("annotation text is required")
        if len(clean_content) > 4_000:
            raise ValueError("annotation text must be 4000 characters or fewer")
        node = _resolve_graph_node(self.workspace_manager, node_id)
        self.workspace_manager.add_note(clean_content, node.record_ref)
        with self.workspace_manager.get_session() as session:
            row = session.execute(
                select(AnalystNote)
                .where(AnalystNote.stix_object_id == node.record_ref)
                .order_by(AnalystNote.id.desc())
                .limit(1)
            ).scalar_one()
            return _annotation_record(row, node.id)

    def annotations(self, node_id: str | None = None) -> tuple[GraphAnnotationRecord, ...]:
        record_ref: str | None = None
        resolved_node_id = ""
        if node_id:
            node = _resolve_graph_node(self.workspace_manager, node_id)
            record_ref = node.record_ref
            resolved_node_id = node.id
        projection = build_investigation_graph(self.workspace_manager)
        node_by_ref = {node.record_ref: node.id for node in projection.nodes}
        with self.workspace_manager.get_session() as session:
            statement = select(AnalystNote).order_by(AnalystNote.id)
            if record_ref is not None:
                statement = statement.where(AnalystNote.stix_object_id == record_ref)
            rows = list(session.execute(statement).scalars())
        return tuple(
            _annotation_record(
                row,
                resolved_node_id or node_by_ref.get(str(row.stix_object_id), "unresolved"),
            )
            for row in rows
            if row.stix_object_id is not None
        )


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
        if (
            relationship["basis"] != "property"
            or (
                source_ref,
                target_ref,
                relation,
            )
            in explicit_keys
        ):
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


def _normalize_layout_name(name: str) -> str:
    normalized = " ".join(name.strip().split())
    if not _LAYOUT_NAME.fullmatch(normalized):
        raise ValueError(
            "layout name must be 1-64 characters using letters, numbers, spaces, '.', '_', or '-'"
        )
    return normalized


def _layout_id(name: str) -> str:
    digest = hashlib.sha256(name.casefold().encode()).hexdigest()[:24]
    return f"graph-layout-{digest}"


def _validate_presentation_draft(
    draft: GraphPresentationDraft,
    projection: InvestigationGraphProjection,
) -> None:
    if draft.graph_schema_version != projection.schema_version:
        raise ValueError(
            f"layout targets {draft.graph_schema_version}; current graph schema is "
            f"{projection.schema_version}"
        )
    if len(draft.positions) > _MAX_LAYOUT_NODES or len(draft.pinned_refs) > _MAX_LAYOUT_NODES:
        raise ValueError(f"graph layouts may contain at most {_MAX_LAYOUT_NODES} node references")
    allowed_refs = {
        reference for node in projection.nodes for reference in (node.id, node.record_ref)
    }
    supplied_refs = {*draft.positions, *draft.pinned_refs}
    unknown = sorted(supplied_refs - allowed_refs)
    if unknown:
        raise ValueError(f"layout references nodes outside the current graph: {unknown[0]}")
    for reference, point in draft.positions.items():
        if not all(math.isfinite(value) and abs(value) <= 100_000 for value in (point.x, point.y)):
            raise ValueError(f"layout position is outside the supported range: {reference}")
    viewport = draft.viewport
    if not all(
        math.isfinite(value) and abs(value) <= 100_000 for value in (viewport.x, viewport.y)
    ):
        raise ValueError("layout viewport is outside the supported range")
    if not math.isfinite(viewport.scale) or not 0.2 <= viewport.scale <= 5:
        raise ValueError("layout viewport scale must be between 0.2 and 5")
    if len(set(draft.pinned_refs)) != len(draft.pinned_refs):
        raise ValueError("layout pinned_refs must not contain duplicates")
    if len(draft.filters.kinds) > 50:
        raise ValueError("layout may filter at most 50 node kinds")
    if any(not kind.strip() or len(kind) > 80 for kind in draft.filters.kinds):
        raise ValueError("layout node-kind filters must be 1-80 characters")


def _presentation_record(row: GraphPresentationLayoutRow) -> GraphPresentationRecord:
    draft = GraphPresentationDraft.model_validate(
        {
            "graph_schema_version": row.graph_schema_version,
            "positions": row.positions or {},
            "pinned_refs": row.pinned_refs or [],
            "filters": row.filters or {},
            "viewport": row.viewport or {},
        }
    )
    return GraphPresentationRecord(
        id=row.id,
        name=row.name,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        **draft.model_dump(),
    )


def _resolve_graph_node(workspace_manager: Any, reference: str) -> InvestigationGraphNode:
    supplied = reference.strip()
    if not supplied:
        raise ValueError("graph node reference is required")
    matches = [
        node
        for node in build_investigation_graph(workspace_manager).nodes
        if supplied in {node.id, node.record_ref}
    ]
    if not matches:
        raise ValueError(f"graph node does not exist in the current workspace: {supplied}")
    if len(matches) > 1 and not supplied.startswith(("entity:", "epistemic:")):
        raise ValueError("record reference is ambiguous; use the complete graph node id")
    return matches[0]


def _annotation_record(row: AnalystNote, node_id: str) -> GraphAnnotationRecord:
    return GraphAnnotationRecord(
        id=int(row.id),
        node_id=node_id,
        record_ref=str(row.stix_object_id),
        content=row.content,
        created_at=row.created_at,
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
