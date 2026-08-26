"""Exact exports for the governed entity, epistemic, and bridge graph."""

from __future__ import annotations

import csv
import io
import json
from typing import Literal
from xml.etree import ElementTree as ET

from pydantic import BaseModel, ConfigDict

from adversary_pursuit.core.investigation_graph import (
    GraphLayer,
    InvestigationGraphEdge,
    InvestigationGraphNode,
    InvestigationGraphProjection,
)

GraphExportFormat = Literal["json", "csv", "gexf"]
GraphExportLayer = Literal["all", "entity", "epistemic", "bridge"]


class InvestigationGraphExport(BaseModel):
    """One downloadable exact-data artifact with an explicit layer scope."""

    model_config = ConfigDict(frozen=True)

    filename: str
    mime: str
    content: str
    format: GraphExportFormat
    layer: GraphExportLayer
    node_count: int
    edge_count: int


def export_investigation_graph(
    projection: InvestigationGraphProjection,
    *,
    format: str,
    layer: str = "all",
) -> InvestigationGraphExport:
    """Export a bounded projection without changing evidence or presentation state."""

    normalized_format = format.casefold()
    normalized_layer = layer.casefold()
    if normalized_format not in {"json", "csv", "gexf"}:
        raise ValueError("Layered graph export format must be json, csv, or gexf.")
    if normalized_layer not in {"all", "entity", "epistemic", "bridge"}:
        raise ValueError("Layered graph export scope must be all, entity, epistemic, or bridge.")
    nodes, edges = _select(projection, normalized_layer)
    if normalized_format == "json":
        content = _json_export(projection, nodes, edges, normalized_layer)
        mime, suffix = "application/json", "json"
    elif normalized_format == "csv":
        content = _csv_export(nodes, edges)
        mime, suffix = "text/csv", "csv"
    else:
        content = _gexf_export(projection, nodes, edges, normalized_layer)
        mime, suffix = "application/xml", "gexf"
    safe_workspace = "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in projection.workspace
    ).strip("-") or "workspace"
    return InvestigationGraphExport(
        filename=f"{safe_workspace}-investigation-graph-{normalized_layer}.{suffix}",
        mime=mime,
        content=content,
        format=normalized_format,
        layer=normalized_layer,
        node_count=len(nodes),
        edge_count=len(edges),
    )


def _select(
    projection: InvestigationGraphProjection,
    layer: str,
) -> tuple[tuple[InvestigationGraphNode, ...], tuple[InvestigationGraphEdge, ...]]:
    if layer == "all":
        return projection.nodes, projection.edges
    selected_layer = GraphLayer(layer)
    edges = tuple(edge for edge in projection.edges if edge.layer is selected_layer)
    if selected_layer is GraphLayer.BRIDGE:
        endpoint_ids = {value for edge in edges for value in (edge.source, edge.target)}
        nodes = tuple(node for node in projection.nodes if node.id in endpoint_ids)
    else:
        nodes = tuple(node for node in projection.nodes if node.layer is selected_layer)
    admitted = {node.id for node in nodes}
    edges = tuple(edge for edge in edges if edge.source in admitted and edge.target in admitted)
    return nodes, edges


def _json_export(
    projection: InvestigationGraphProjection,
    nodes: tuple[InvestigationGraphNode, ...],
    edges: tuple[InvestigationGraphEdge, ...],
    layer: str,
) -> str:
    payload = {
        "schema_version": projection.schema_version,
        "workspace": projection.workspace,
        "export_layer": layer,
        "nodes": [node.model_dump(mode="json") for node in nodes],
        "edges": [edge.model_dump(mode="json") for edge in edges],
        "counts": {"nodes": len(nodes), "edges": len(edges)},
        "caveats": list(projection.caveats),
    }
    return json.dumps(payload, indent=2, sort_keys=True, default=str)


def _csv_export(
    nodes: tuple[InvestigationGraphNode, ...],
    edges: tuple[InvestigationGraphEdge, ...],
) -> str:
    fields = (
        "record_type",
        "id",
        "layer",
        "kind",
        "label",
        "record_ref",
        "state",
        "source",
        "target",
        "relationship",
        "truth_kind",
        "provenance_refs",
        "rationale",
        "directed",
        "attributes",
    )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for node in nodes:
        writer.writerow(
            {
                "record_type": "node",
                "id": _csv_safe(node.id),
                "layer": node.layer.value,
                "kind": _csv_safe(node.kind),
                "label": _csv_safe(node.label),
                "record_ref": _csv_safe(node.record_ref),
                "state": _csv_safe(node.state or ""),
                "attributes": _csv_safe(json.dumps(node.attributes, sort_keys=True, default=str)),
            }
        )
    for edge in edges:
        writer.writerow(
            {
                "record_type": "edge",
                "id": _csv_safe(edge.id),
                "layer": edge.layer.value,
                "source": _csv_safe(edge.source),
                "target": _csv_safe(edge.target),
                "relationship": _csv_safe(edge.relationship),
                "truth_kind": edge.truth_kind.value,
                "provenance_refs": _csv_safe(json.dumps(edge.provenance_refs)),
                "rationale": _csv_safe(edge.rationale),
                "directed": str(edge.directed).lower(),
            }
        )
    return stream.getvalue()


def _gexf_export(
    projection: InvestigationGraphProjection,
    nodes: tuple[InvestigationGraphNode, ...],
    edges: tuple[InvestigationGraphEdge, ...],
    layer: str,
) -> str:
    root = ET.Element(
        "gexf",
        {"xmlns": "http://gexf.net/1.2", "version": "1.2"},
    )
    meta = ET.SubElement(root, "meta")
    ET.SubElement(meta, "creator").text = "Pivotglass"
    ET.SubElement(meta, "description").text = (
        f"{projection.workspace} governed investigation graph; layer={layer}"
    )
    graph = ET.SubElement(root, "graph", {"mode": "static", "defaultedgetype": "directed"})
    node_attributes = ET.SubElement(graph, "attributes", {"class": "node"})
    for attribute_id, title in (
        ("n0", "layer"),
        ("n1", "kind"),
        ("n2", "record_ref"),
        ("n3", "state"),
        ("n4", "attributes_json"),
    ):
        ET.SubElement(
            node_attributes,
            "attribute",
            {"id": attribute_id, "title": title, "type": "string"},
        )
    edge_attributes = ET.SubElement(graph, "attributes", {"class": "edge"})
    for attribute_id, title in (
        ("e0", "layer"),
        ("e1", "truth_kind"),
        ("e2", "provenance_refs"),
        ("e3", "rationale"),
    ):
        ET.SubElement(
            edge_attributes,
            "attribute",
            {"id": attribute_id, "title": title, "type": "string"},
        )
    nodes_element = ET.SubElement(graph, "nodes")
    for node in nodes:
        element = ET.SubElement(nodes_element, "node", {"id": node.id, "label": node.label})
        values = ET.SubElement(element, "attvalues")
        _attvalue(values, "n0", node.layer.value)
        _attvalue(values, "n1", node.kind)
        _attvalue(values, "n2", node.record_ref)
        _attvalue(values, "n3", node.state or "")
        _attvalue(values, "n4", json.dumps(node.attributes, sort_keys=True, default=str))
    edges_element = ET.SubElement(graph, "edges")
    for edge in edges:
        element = ET.SubElement(
            edges_element,
            "edge",
            {
                "id": edge.id,
                "source": edge.source,
                "target": edge.target,
                "label": edge.relationship,
                "type": "directed" if edge.directed else "undirected",
            },
        )
        values = ET.SubElement(element, "attvalues")
        _attvalue(values, "e0", edge.layer.value)
        _attvalue(values, "e1", edge.truth_kind.value)
        _attvalue(values, "e2", json.dumps(edge.provenance_refs))
        _attvalue(values, "e3", edge.rationale)
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def _attvalue(parent: ET.Element, attribute_id: str, value: str) -> None:
    ET.SubElement(parent, "attvalue", {"for": attribute_id, "value": value})


def _csv_safe(value: str) -> str:
    return f"'{value}" if value.lstrip().startswith(("=", "+", "-", "@")) else value
