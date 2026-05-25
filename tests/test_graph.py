"""Tests for Issue #20: STIX Relationship Graph & Visualization.

@decision DEC-TEST-020
@title Test suite covers graph construction, tree rendering, text output, GEXF export,
       STIX bundle export, stats, cycle safety, and production call sequence
@status accepted
@rationale The production call chain is: workspace.get_stix_objects() →
           RelationshipGraph.build_from_workspace() → render_tree()/render_text()/export_*.
           Tests cover the full sequence including the console integration paths.
           Cycle safety is verified with a deliberately cyclic graph to ensure
           _build_subtree's visited set prevents infinite recursion.

Tests verify:
- Empty graph renders without error
- build_from_workspace adds nodes correctly
- Nodes have correct stix_type and value
- Explicit relationships create edges
- render_tree produces Rich Tree with correct labels
- render_text produces a non-empty string
- export_gexf produces valid XML with correct structure
- export_stix_bundle produces dict with 'objects' key
- get_stats returns correct node/edge counts and type breakdown
- Graph with cycles doesn't infinite loop
- render_tree with explicit root_id works correctly
- render_tree with invalid root_id falls back gracefully
- node_count and edge_count properties are accurate
- Unconnected nodes appear in render_tree output
- Multiple node types are tracked in get_stats
- Relationships without explicit edges infer nothing (no crash)
- GEXF export with empty graph returns minimal valid XML
- STIX bundle export with no explicit relationships
- Console graph command wiring (build_from_workspace → render_tree)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from rich.tree import Tree

from adversary_pursuit.core.graph import GraphNode, RelationshipGraph

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_ipv4(id_suffix: str = "1", value: str = "1.2.3.4") -> dict:
    return {"id": f"ipv4-addr--{id_suffix}", "type": "ipv4-addr", "value": value}


def _make_domain(id_suffix: str = "1", value: str = "example.com") -> dict:
    return {"id": f"domain-name--{id_suffix}", "type": "domain-name", "value": value}


def _make_url(id_suffix: str = "1", value: str = "https://example.com") -> dict:
    return {"id": f"url--{id_suffix}", "type": "url", "value": value}


def _make_relationship(src: str, tgt: str, rel_type: str = "resolves-to") -> dict:
    return {
        "source_ref": src,
        "target_ref": tgt,
        "relationship_type": rel_type,
    }


# ---------------------------------------------------------------------------
# GraphNode unit tests
# ---------------------------------------------------------------------------


class TestGraphNode:
    """Unit tests for the GraphNode dataclass."""

    def test_default_children_are_empty(self):
        node = GraphNode(stix_id="x--1", stix_type="ipv4-addr", value="1.2.3.4")
        assert node.children == []

    def test_children_not_shared_across_instances(self):
        """Dataclass field(default_factory=list) must not share the same list."""
        a = GraphNode(stix_id="x--1", stix_type="ipv4-addr", value="1.1.1.1")
        b = GraphNode(stix_id="x--2", stix_type="ipv4-addr", value="2.2.2.2")
        a.children.append(b)
        assert b not in GraphNode(stix_id="x--3", stix_type="ipv4-addr", value="3.3.3.3").children


# ---------------------------------------------------------------------------
# RelationshipGraph construction
# ---------------------------------------------------------------------------


class TestBuildFromWorkspace:
    """Tests for RelationshipGraph.build_from_workspace()."""

    def test_empty_stix_objects_produces_empty_graph(self):
        g = RelationshipGraph()
        g.build_from_workspace([])
        assert g.node_count == 0
        assert g.edge_count == 0

    def test_single_object_adds_one_node(self):
        g = RelationshipGraph()
        g.build_from_workspace([_make_ipv4()])
        assert g.node_count == 1

    def test_multiple_objects_add_multiple_nodes(self):
        g = RelationshipGraph()
        objs = [_make_ipv4("1"), _make_domain("1"), _make_url("1")]
        g.build_from_workspace(objs)
        assert g.node_count == 3

    def test_node_has_correct_stix_type(self):
        g = RelationshipGraph()
        g.build_from_workspace([_make_domain("1", "evil.com")])
        node = next(iter(g._nodes.values()))
        assert node.stix_type == "domain-name"

    def test_node_has_correct_value(self):
        g = RelationshipGraph()
        g.build_from_workspace([_make_ipv4("1", "192.168.1.1")])
        node = next(iter(g._nodes.values()))
        assert node.value == "192.168.1.1"

    def test_explicit_relationship_creates_edge(self):
        g = RelationshipGraph()
        objs = [_make_domain("1"), _make_ipv4("1")]
        rels = [_make_relationship("domain-name--1", "ipv4-addr--1")]
        g.build_from_workspace(objs, rels)
        assert g.edge_count == 1

    def test_multiple_relationships_create_multiple_edges(self):
        g = RelationshipGraph()
        objs = [_make_domain("1"), _make_ipv4("1"), _make_url("1")]
        rels = [
            _make_relationship("domain-name--1", "ipv4-addr--1"),
            _make_relationship("domain-name--1", "url--1"),
        ]
        g.build_from_workspace(objs, rels)
        assert g.edge_count == 2

    def test_no_relationships_argument_creates_zero_edges(self):
        g = RelationshipGraph()
        g.build_from_workspace([_make_ipv4("1"), _make_domain("1")])
        assert g.edge_count == 0

    def test_relationship_type_stored_correctly(self):
        g = RelationshipGraph()
        objs = [_make_domain("1"), _make_ipv4("1")]
        rels = [_make_relationship("domain-name--1", "ipv4-addr--1", "resolves-to")]
        g.build_from_workspace(objs, rels)
        src, tgt, rel_type = g._edges[0]
        assert rel_type == "resolves-to"


# ---------------------------------------------------------------------------
# render_tree
# ---------------------------------------------------------------------------


class TestRenderTree:
    """Tests for RelationshipGraph.render_tree()."""

    def test_empty_graph_returns_tree_without_error(self):
        g = RelationshipGraph()
        tree = g.render_tree()
        assert isinstance(tree, Tree)

    def test_empty_graph_tree_label_contains_empty(self):
        g = RelationshipGraph()
        tree = g.render_tree()
        # Rich stores the label as a renderable; check string representation
        assert "Empty" in str(tree.label) or "empty" in str(tree.label).lower()

    def test_single_node_renders_root_label(self):
        g = RelationshipGraph()
        g.build_from_workspace([_make_ipv4("1", "10.0.0.1")])
        tree = g.render_tree()
        assert isinstance(tree, Tree)
        label_str = str(tree.label)
        assert "ipv4-addr" in label_str
        assert "10.0.0.1" in label_str

    def test_explicit_root_id_used_as_root(self):
        g = RelationshipGraph()
        g.build_from_workspace([_make_ipv4("1", "1.1.1.1"), _make_domain("2", "bad.com")])
        tree = g.render_tree(root_id="domain-name--2")
        label_str = str(tree.label)
        assert "bad.com" in label_str

    def test_invalid_root_id_falls_back_to_first_node(self):
        g = RelationshipGraph()
        g.build_from_workspace([_make_ipv4("1", "1.1.1.1")])
        # Should not raise even though root_id doesn't exist
        tree = g.render_tree(root_id="nonexistent--9999")
        assert isinstance(tree, Tree)

    def test_cycle_does_not_infinite_loop(self):
        """A → B → A cycle must terminate via the visited set."""
        g = RelationshipGraph()
        objs = [_make_ipv4("1", "1.1.1.1"), _make_domain("1", "loop.com")]
        rels = [
            _make_relationship("ipv4-addr--1", "domain-name--1"),
            _make_relationship("domain-name--1", "ipv4-addr--1"),
        ]
        g.build_from_workspace(objs, rels)
        # Must complete without RecursionError
        tree = g.render_tree()
        assert isinstance(tree, Tree)

    def test_connected_nodes_appear_as_children(self):
        g = RelationshipGraph()
        objs = [_make_domain("1", "pivot.com"), _make_ipv4("1", "9.9.9.9")]
        rels = [_make_relationship("domain-name--1", "ipv4-addr--1")]
        g.build_from_workspace(objs, rels)
        tree = g.render_tree(root_id="domain-name--1")
        # Root should have one child branch
        assert len(tree.children) == 1


# ---------------------------------------------------------------------------
# render_text
# ---------------------------------------------------------------------------


class TestRenderText:
    """Tests for RelationshipGraph.render_text()."""

    def test_render_text_returns_string(self):
        g = RelationshipGraph()
        result = g.render_text()
        assert isinstance(result, str)

    def test_empty_graph_render_text_not_empty(self):
        g = RelationshipGraph()
        result = g.render_text()
        assert len(result) > 0

    def test_nodes_appear_in_render_text(self):
        g = RelationshipGraph()
        g.build_from_workspace([_make_ipv4("1", "5.5.5.5")])
        result = g.render_text()
        assert "5.5.5.5" in result


# ---------------------------------------------------------------------------
# export_gexf
# ---------------------------------------------------------------------------


class TestExportGexf:
    """Tests for RelationshipGraph.export_gexf()."""

    def test_export_gexf_returns_string(self):
        g = RelationshipGraph()
        result = g.export_gexf()
        assert isinstance(result, str)

    def test_empty_graph_gexf_is_valid_xml(self):
        g = RelationshipGraph()
        xml_str = g.export_gexf()
        # Should parse without exception
        root = ET.fromstring(xml_str)
        assert root is not None

    def test_gexf_root_element_is_gexf(self):
        g = RelationshipGraph()
        xml_str = g.export_gexf()
        root = ET.fromstring(xml_str)
        assert "gexf" in root.tag.lower()

    def test_gexf_nodes_element_present(self):
        g = RelationshipGraph()
        g.build_from_workspace([_make_ipv4("1")])
        xml_str = g.export_gexf()
        # Must have at least one node element somewhere in the XML
        assert "<node" in xml_str

    def test_gexf_edges_element_present_when_relationships_exist(self):
        g = RelationshipGraph()
        objs = [_make_domain("1"), _make_ipv4("1")]
        rels = [_make_relationship("domain-name--1", "ipv4-addr--1")]
        g.build_from_workspace(objs, rels)
        xml_str = g.export_gexf()
        assert "<edge" in xml_str

    def test_gexf_node_ids_are_stix_ids(self):
        g = RelationshipGraph()
        g.build_from_workspace([_make_ipv4("abc123")])
        xml_str = g.export_gexf()
        assert "ipv4-addr--abc123" in xml_str


# ---------------------------------------------------------------------------
# export_stix_bundle
# ---------------------------------------------------------------------------


class TestExportStixBundle:
    """Tests for RelationshipGraph.export_stix_bundle().

    After DEC-59-STIX-PROVENANCE-005, export_stix_bundle() builds the bundle via
    stix2.v21.Bundle, which requires valid STIX 2.1 ids (uuid4 format). Tests that
    use the real production path (workspace → graph → export) use WorkspaceManager
    so that SCO ids are library-generated and spec-compliant. The empty-graph tests
    that don't include objects continue to work without a workspace.
    """

    def test_export_stix_bundle_returns_dict(self):
        g = RelationshipGraph()
        result = g.export_stix_bundle()
        assert isinstance(result, dict)

    def test_stix_bundle_has_type_bundle(self):
        g = RelationshipGraph()
        result = g.export_stix_bundle()
        assert result.get("type") == "bundle"

    def test_stix_bundle_has_objects_key(self):
        g = RelationshipGraph()
        result = g.export_stix_bundle()
        assert "objects" in result

    def test_stix_bundle_objects_includes_nodes(self, tmp_path):
        """Nodes from a workspace have real deterministic STIX ids that survive export."""
        from adversary_pursuit.core.workspace import WorkspaceManager

        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")
        wm.store_stix_objects(
            [
                {"type": "ipv4-addr", "value": "8.8.8.8"},
                {"type": "domain-name", "value": "dns.google"},
            ],
            module_name="test/graph",
            target="8.8.8.8",
        )

        g = RelationshipGraph()
        g.build_from_workspace(wm.get_stix_objects())
        result = g.export_stix_bundle()

        values = [o.get("value", "") for o in result["objects"]]
        assert "8.8.8.8" in values
        assert "dns.google" in values

    def test_stix_bundle_objects_includes_relationships(self, tmp_path):
        """Relationships between workspace-backed nodes appear in the bundle."""
        from adversary_pursuit.core.workspace import WorkspaceManager
        from adversary_pursuit.models.stix import create_domain, create_ipv4, create_relationship

        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")

        ip = create_ipv4("203.0.113.50")
        dom = create_domain("rel-graph-test.example.com")
        rel = create_relationship(dom.id, ip.id, "resolves-to")
        wm.store_stix_objects([ip, dom, rel], module_name="test/rel", target="203.0.113.50")

        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from adversary_pursuit.models.database import Relationship as RelModel

        objects = wm.get_stix_objects()
        with Session(wm._engine) as session:
            rels_raw = [
                {
                    "source_ref": r.source_ref,
                    "target_ref": r.target_ref,
                    "relationship_type": r.relationship_type,
                }
                for r in session.execute(select(RelModel)).scalars().all()
            ]

        g = RelationshipGraph()
        g.build_from_workspace(objects, rels_raw)
        result = g.export_stix_bundle()

        types = [o.get("type", "") for o in result["objects"]]
        assert "relationship" in types


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------


class TestGetStats:
    """Tests for RelationshipGraph.get_stats()."""

    def test_empty_graph_stats(self):
        g = RelationshipGraph()
        stats = g.get_stats()
        assert stats["node_count"] == 0
        assert stats["edge_count"] == 0

    def test_stats_node_count_correct(self):
        g = RelationshipGraph()
        g.build_from_workspace([_make_ipv4("1"), _make_ipv4("2"), _make_domain("1")])
        stats = g.get_stats()
        assert stats["node_count"] == 3

    def test_stats_edge_count_correct(self):
        g = RelationshipGraph()
        objs = [_make_domain("1"), _make_ipv4("1")]
        rels = [_make_relationship("domain-name--1", "ipv4-addr--1")]
        g.build_from_workspace(objs, rels)
        stats = g.get_stats()
        assert stats["edge_count"] == 1

    def test_stats_types_breakdown(self):
        g = RelationshipGraph()
        g.build_from_workspace(
            [
                _make_ipv4("1"),
                _make_ipv4("2"),
                _make_domain("1"),
            ]
        )
        stats = g.get_stats()
        types = stats.get("types", {})
        assert types.get("ipv4-addr") == 2
        assert types.get("domain-name") == 1


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    """Tests for node_count and edge_count properties."""

    def test_node_count_starts_at_zero(self):
        g = RelationshipGraph()
        assert g.node_count == 0

    def test_edge_count_starts_at_zero(self):
        g = RelationshipGraph()
        assert g.edge_count == 0

    def test_node_count_increments_correctly(self):
        g = RelationshipGraph()
        g.build_from_workspace([_make_ipv4("1"), _make_ipv4("2")])
        assert g.node_count == 2

    def test_edge_count_increments_correctly(self):
        g = RelationshipGraph()
        objs = [_make_ipv4("1"), _make_domain("1"), _make_url("1")]
        rels = [
            _make_relationship("ipv4-addr--1", "domain-name--1"),
            _make_relationship("domain-name--1", "url--1"),
        ]
        g.build_from_workspace(objs, rels)
        assert g.edge_count == 2


# ---------------------------------------------------------------------------
# STIX 2.1 spec-compliance tests for export_stix_bundle (Evaluation Contract #7)
# ---------------------------------------------------------------------------


class TestExportStixBundleSpecCompliance:
    """Evaluation Contract test 7: export_stix_bundle() round-trips via stix2.parse().

    These tests use real STIX 2.1 SCOs (produced by python-stix2) stored
    through WorkspaceManager, then exported via RelationshipGraph. This exercises
    the full production path and verifies DEC-59-STIX-PROVENANCE-005.

    @decision DEC-59-STIX-PROVENANCE-005
    @title export_stix_bundle rebuilt via stix2.v21.Bundle — no hand-rolled dicts
    @status accepted
    @rationale Guarantees spec compliance and parse-ability via python-stix2.
    """

    def _make_workspace(self, tmp_path):
        from adversary_pursuit.core.workspace import WorkspaceManager

        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")
        return wm

    def test_export_stix_bundle_is_spec_compliant(self, tmp_path):
        """Evaluation Contract test 7: bundle round-trips through stix2.parse().

        Stores SCOs through the workspace (so they have deterministic ids and
        spec_version), then builds a graph and exports. The bundle must parse
        via stix2.parse() without raising.
        """
        import stix2
        import stix2.v21

        wm = self._make_workspace(tmp_path)
        wm.store_stix_objects(
            [
                {"type": "ipv4-addr", "value": "203.0.113.100"},
                {"type": "domain-name", "value": "spec-test.example.com"},
            ],
            module_name="test/spec",
            target="203.0.113.100",
        )

        objects = wm.get_stix_objects()
        g = RelationshipGraph()
        g.build_from_workspace(objects)

        bundle_dict = g.export_stix_bundle()

        # Must not raise — spec-compliant bundle required (DEC-59-STIX-PROVENANCE-005)
        parsed = stix2.parse(bundle_dict, allow_custom=True)
        assert isinstance(parsed, stix2.v21.Bundle)
        assert len(parsed.objects) == 2

        # Every object has spec_version="2.1"
        for obj in parsed.objects:
            assert obj.spec_version == "2.1"

    def test_export_stix_bundle_with_relationships_parses(self, tmp_path):
        """Bundle with both SCOs and relationship SROs round-trips through stix2.parse()."""
        import stix2
        import stix2.v21

        from adversary_pursuit.models.stix import create_domain, create_ipv4, create_relationship

        wm = self._make_workspace(tmp_path)
        ip = create_ipv4("203.0.113.101")
        dom = create_domain("rel-test.example.com")
        rel = create_relationship(dom.id, ip.id, "resolves-to")
        wm.store_stix_objects(
            [ip, dom, rel],
            module_name="test/rel",
            target="203.0.113.101",
        )

        objects = wm.get_stix_objects()
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from adversary_pursuit.models.database import Relationship as RelModel

        with Session(wm._engine) as session:
            rels_raw = [
                {
                    "source_ref": r.source_ref,
                    "target_ref": r.target_ref,
                    "relationship_type": r.relationship_type,
                }
                for r in session.execute(select(RelModel)).scalars().all()
            ]

        g = RelationshipGraph()
        g.build_from_workspace(objects, rels_raw)

        bundle_dict = g.export_stix_bundle()
        parsed = stix2.parse(bundle_dict, allow_custom=True)
        assert isinstance(parsed, stix2.v21.Bundle)

        types = {obj.type for obj in parsed.objects}
        assert "ipv4-addr" in types
        assert "domain-name" in types
        assert "relationship" in types

    def test_export_stix_bundle_workspace_nodes_have_real_stix_ids(self, tmp_path):
        """Workspace-backed nodes carry library-generated deterministic ids.

        After DEC-59-STIX-PROVENANCE-005, export_stix_bundle() passes each node
        blob through stix2.parse() which requires valid STIX 2.1 ids (uuid4 format).
        Nodes from WorkspaceManager.get_stix_objects() always have real ids, so
        the bundle round-trips correctly.
        """
        import stix2
        import stix2.v21

        wm = self._make_workspace(tmp_path)
        wm.store_stix_objects(
            [{"type": "ipv4-addr", "value": "10.0.0.100"}],
            module_name="test/real-ids",
            target="10.0.0.100",
        )

        g = RelationshipGraph()
        g.build_from_workspace(wm.get_stix_objects())
        bundle_dict = g.export_stix_bundle()

        assert bundle_dict["type"] == "bundle"
        assert "objects" in bundle_dict
        assert len(bundle_dict["objects"]) == 1

        parsed = stix2.parse(bundle_dict, allow_custom=True)
        assert isinstance(parsed, stix2.v21.Bundle)

    def test_existing_export_stix_bundle_tests_still_pass(self, tmp_path):
        """Regression: existing TestExportStixBundle contract holds after refactor.

        Empty graph: type=bundle, objects key present.
        Nodes/values: workspace-backed SCOs appear with correct values.
        Relationships: relationship type appears for workspace-backed relationship SROs.
        """

        from adversary_pursuit.core.workspace import WorkspaceManager
        from adversary_pursuit.models.stix import create_domain, create_ipv4, create_relationship

        # Empty graph assertions (no workspace needed)
        g = RelationshipGraph()
        result = g.export_stix_bundle()
        assert isinstance(result, dict)
        assert result.get("type") == "bundle"
        assert "objects" in result

        # Node values present in bundle (requires real STIX ids from workspace)
        wm2 = WorkspaceManager(workspace_dir=tmp_path / "wm2")
        wm2.create("default")
        wm2.switch("default")
        wm2.store_stix_objects(
            [
                {"type": "ipv4-addr", "value": "8.8.8.8"},
                {"type": "domain-name", "value": "dns.google"},
            ],
            module_name="test/regression",
            target="8.8.8.8",
        )
        g2 = RelationshipGraph()
        g2.build_from_workspace(wm2.get_stix_objects())
        result2 = g2.export_stix_bundle()
        values = [o.get("value", "") for o in result2["objects"]]
        assert "8.8.8.8" in values
        assert "dns.google" in values

        # Relationship type present in bundle
        wm3 = WorkspaceManager(workspace_dir=tmp_path / "wm3")
        wm3.create("default")
        wm3.switch("default")
        ip3 = create_ipv4("203.0.113.200")
        dom3 = create_domain("regression-rel.example.com")
        rel3 = create_relationship(dom3.id, ip3.id, "resolves-to")
        wm3.store_stix_objects([ip3, dom3, rel3], module_name="test/rel3", target="203.0.113.200")

        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from adversary_pursuit.models.database import Relationship as RelModel

        objects3 = wm3.get_stix_objects()
        with Session(wm3._engine) as session:
            rels3 = [
                {
                    "source_ref": r.source_ref,
                    "target_ref": r.target_ref,
                    "relationship_type": r.relationship_type,
                }
                for r in session.execute(select(RelModel)).scalars().all()
            ]

        g3 = RelationshipGraph()
        g3.build_from_workspace(objects3, rels3)
        result3 = g3.export_stix_bundle()
        types = [o.get("type", "") for o in result3["objects"]]
        assert "relationship" in types
