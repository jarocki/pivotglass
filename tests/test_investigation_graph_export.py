"""Exact multi-layer investigation graph export tests."""

import csv
import io
import json
from xml.etree import ElementTree as ET

import pytest

from adversary_pursuit.agent.repl_verbs import dispatch_repl_verb, parse_repl_verb
from adversary_pursuit.agent.tools import ToolContext
from adversary_pursuit.core.investigation_graph import (
    GraphLayer,
    GraphTruthKind,
    InvestigationGraphEdge,
    InvestigationGraphNode,
    InvestigationGraphProjection,
)
from adversary_pursuit.core.investigation_graph_export import export_investigation_graph
from adversary_pursuit.web.server import WebCockpitService


def _projection() -> InvestigationGraphProjection:
    return InvestigationGraphProjection(
        workspace="qa workspace",
        nodes=(
            InvestigationGraphNode(
                id="entity:one",
                layer=GraphLayer.ENTITY,
                kind="domain-name",
                label="=formula.test",
                record_ref="domain-name--one",
            ),
            InvestigationGraphNode(
                id="epistemic:observation:one",
                layer=GraphLayer.EPISTEMIC,
                kind="observation",
                label="Source observed formula.test",
                record_ref="observation-one",
                attributes={"source": "qa/source"},
            ),
        ),
        edges=(
            InvestigationGraphEdge(
                id="edge:bridge",
                layer=GraphLayer.BRIDGE,
                source="epistemic:observation:one",
                target="entity:one",
                relationship="observes",
                truth_kind=GraphTruthKind.OBSERVED,
                provenance_refs=("observation-one",),
                rationale="Immutable source observation.",
            ),
        ),
        counts={},
        caveats=("No relationship is inferred from proximity.",),
    )


def test_layered_graph_json_and_bridge_scope_preserve_truth_and_provenance():
    artifact = export_investigation_graph(_projection(), format="json", layer="bridge")
    payload = json.loads(artifact.content)

    assert artifact.filename == "qa-workspace-investigation-graph-bridge.json"
    assert artifact.node_count == 2
    assert artifact.edge_count == 1
    assert payload["export_layer"] == "bridge"
    assert payload["edges"][0]["truth_kind"] == "observed"
    assert payload["edges"][0]["provenance_refs"] == ["observation-one"]


def test_layered_graph_csv_is_exact_and_spreadsheet_safe():
    artifact = export_investigation_graph(_projection(), format="csv", layer="all")
    rows = list(csv.DictReader(io.StringIO(artifact.content)))

    assert len(rows) == 3
    assert rows[0]["label"] == "'=formula.test"
    edge = next(row for row in rows if row["record_type"] == "edge")
    assert edge["layer"] == "bridge"
    assert edge["truth_kind"] == "observed"
    assert json.loads(edge["provenance_refs"]) == ["observation-one"]


def test_layered_graph_gexf_contains_governed_edge_attributes():
    artifact = export_investigation_graph(_projection(), format="gexf", layer="all")
    root = ET.fromstring(artifact.content)
    namespace = {"g": "http://gexf.net/1.2"}

    assert len(root.findall(".//g:node", namespace)) == 2
    assert len(root.findall(".//g:edge", namespace)) == 1
    values = {
        item.attrib["for"]: item.attrib["value"]
        for item in root.findall(".//g:edge/g:attvalues/g:attvalue", namespace)
    }
    assert values["e0"] == "bridge"
    assert values["e1"] == "observed"
    assert json.loads(values["e2"]) == ["observation-one"]


@pytest.mark.parametrize("value", ["pdf", "stix"])
def test_layered_graph_export_rejects_unsupported_format(value):
    with pytest.raises(ValueError, match="json, csv, or gexf"):
        export_investigation_graph(_projection(), format=value)


def test_tui_and_web_share_layered_graph_export_command(tmp_path):
    ctx = ToolContext(
        config_dir=tmp_path / "config",
        workspace_dir=tmp_path / "workspaces",
    )
    ctx.workspace_mgr.store_stix_objects(
        [{"type": "domain-name", "value": "export.example"}],
        module_name="qa/source",
        target="export.example",
    )
    verb = parse_repl_verb("graph export json entity")
    assert verb is not None
    tui = dispatch_repl_verb(verb, ctx, ctx.mode_mgr, ctx.workspace_mgr)
    web = WebCockpitService(ctx).execute_command("graph export json entity")

    assert json.loads(tui)["export_layer"] == "entity"
    assert web["kind"] == "download"
    assert web["mime"] == "application/json"
    assert json.loads(web["content"])["nodes"][0]["label"] == "export.example"
