"""Presentation-only saved graph layout contracts."""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import inspect

from adversary_pursuit.agent.repl_verbs import dispatch_repl_verb, parse_repl_verb
from adversary_pursuit.agent.tools import ToolContext
from adversary_pursuit.core.command_completion import command_completions
from adversary_pursuit.core.graph_presentation import (
    GraphPresentationAuthority,
    graph_fingerprint,
)
from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.core.workspace_admin import export_workspace, merge_workspaces
from adversary_pursuit.core.workspace_migrations import CURRENT_WORKSPACE_SCHEMA_VERSION
from adversary_pursuit.web.server import WebCockpitService


def _workspace(tmp_path) -> WorkspaceManager:
    manager = WorkspaceManager(tmp_path)
    manager.create("case")
    manager.switch("case")
    manager.store_stix_objects(
        [
            {"type": "domain-name", "value": "layout.example"},
            {"type": "ipv4-addr", "value": "198.51.100.14"},
        ],
        module_name="test/layout",
        target="layout.example",
    )
    return manager


def _refs(manager: WorkspaceManager) -> set[str]:
    return {str(item["id"]) for item in manager.get_stix_objects()}


def test_saved_layout_is_bounded_presentation_state_and_reports_drift(tmp_path) -> None:
    manager = _workspace(tmp_path)
    refs = _refs(manager)
    authority = GraphPresentationAuthority(manager)
    before = manager.get_stix_objects()

    saved = authority.save(
        "Primary analyst view",
        node_positions={reference: {"x": index * 80, "y": 90} for index, reference in enumerate(refs)},
        viewport={"x": 5, "y": -4, "scale": 1.25},
        filter_text="domain",
        labels={next(iter(refs)): "Analyst display label"},
        pinned_refs=[next(iter(refs))],
        current_node_refs=refs,
        current_edge_keys=set(),
    )
    assert saved["name"] == "Primary analyst view"
    assert list(saved["labels"].values()) == ["Analyst display label"]
    assert saved["pinned_refs"] == [next(iter(refs))]
    assert manager.get_stix_objects() == before

    manager.store_stix_objects(
        [{"type": "url", "value": "https://layout.example/path"}],
        module_name="test/layout",
        target="layout.example",
    )
    current_refs = _refs(manager)
    resolved = authority.resolve(
        "Primary analyst view",
        current_node_refs=current_refs,
        current_edge_keys=set(),
    )
    assert resolved["topology_changed"] is True
    assert len(resolved["new_node_refs"]) == 1
    assert resolved["missing_node_refs"] == []
    assert set(resolved["node_positions"]) == refs


def test_layout_rejects_unknown_nodes_and_unbounded_coordinates(tmp_path) -> None:
    manager = _workspace(tmp_path)
    refs = _refs(manager)
    authority = GraphPresentationAuthority(manager)
    with pytest.raises(ValueError, match="outside the current graph"):
        authority.save(
            "Invalid",
            node_positions={"invented-node": {"x": 1, "y": 2}},
            viewport={"x": 0, "y": 0, "scale": 1},
            filter_text="",
            labels={},
            pinned_refs=[],
            current_node_refs=refs,
            current_edge_keys=set(),
        )
    with pytest.raises(ValueError, match="supported presentation range"):
        authority.save(
            "Invalid",
            node_positions={next(iter(refs)): {"x": 1_000_000, "y": 2}},
            viewport={"x": 0, "y": 0, "scale": 1},
            filter_text="",
            labels={},
            pinned_refs=[],
            current_node_refs=refs,
            current_edge_keys=set(),
        )


def test_layout_round_trips_through_export_merge_and_clear(tmp_path) -> None:
    manager = WorkspaceManager(tmp_path)
    manager.create("source")
    manager.create("destination")
    manager.switch("source")
    manager.store_stix_objects(
        [{"type": "domain-name", "value": "portable.example"}],
        module_name="test/layout",
        target="portable.example",
    )
    refs = _refs(manager)
    GraphPresentationAuthority(manager).save(
        "Portable",
        node_positions={next(iter(refs)): {"x": 10, "y": 20}},
        viewport={"x": 0, "y": 0, "scale": 1},
        filter_text="",
        labels={},
        pinned_refs=[],
        current_node_refs=refs,
        current_edge_keys=set(),
    )
    exported = export_workspace(manager, "source")
    assert exported["tables"]["graph_presentation_layouts"][0]["name"] == "Portable"

    merge_workspaces(manager, "source", "destination")
    manager.switch("destination")
    assert GraphPresentationAuthority(manager).list()[0]["name"] == "Portable"
    deleted = manager.clear()
    assert deleted["graph_presentation_layouts"] == 1
    assert GraphPresentationAuthority(manager).list() == []


def test_schema_v6_migrates_layout_table_backup_first(tmp_path) -> None:
    manager = WorkspaceManager(tmp_path)
    manager.create("legacy-v6")
    manager.switch("legacy-v6")
    manager._engine.dispose()
    with sqlite3.connect(tmp_path / "legacy-v6.db") as connection:
        connection.execute("DROP TABLE graph_presentation_layouts")
        connection.execute("UPDATE workspace_schema_version SET version = 6 WHERE id = 1")
        connection.commit()

    migrated = WorkspaceManager(tmp_path)
    migrated.switch("legacy-v6")
    assert (tmp_path / "legacy-v6.db.pre-v6-backup").is_file()
    assert "graph_presentation_layouts" in inspect(migrated._engine).get_table_names()
    assert migrated.get_workspace_schema_status()["to_version"] == CURRENT_WORKSPACE_SCHEMA_VERSION


def test_schema_v7_reconciles_development_layout_shape_without_losing_positions(tmp_path) -> None:
    manager = WorkspaceManager(tmp_path)
    manager.create("legacy-layout")
    manager.switch("legacy-layout")
    manager._engine.dispose()
    with sqlite3.connect(tmp_path / "legacy-layout.db") as connection:
        connection.execute("DROP TABLE graph_presentation_layouts")
        connection.execute(
            """
            CREATE TABLE graph_presentation_layouts (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                graph_schema_version VARCHAR NOT NULL,
                positions JSON NOT NULL,
                pinned_refs JSON NOT NULL,
                filters JSON NOT NULL,
                viewport JSON NOT NULL,
                created_by VARCHAR NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO graph_presentation_layouts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-layout-id",
                "Recovered",
                "investigation-graph-0.9",
                '{"domain-name--legacy":{"x":12,"y":34}}',
                '["domain-name--legacy"]',
                '{"query":"domain"}',
                '{"x":1,"y":2,"scale":1.5}',
                "human",
                "2026-08-01 00:00:00",
                "2026-08-01 00:01:00",
            ),
        )
        connection.execute("UPDATE workspace_schema_version SET version = 7 WHERE id = 1")
        connection.commit()

    migrated = WorkspaceManager(tmp_path)
    migrated.switch("legacy-layout")
    assert (tmp_path / "legacy-layout.db.pre-v7-backup").is_file()
    recovered = GraphPresentationAuthority(migrated).list()[0]
    assert recovered["node_positions"] == {"domain-name--legacy": {"x": 12.0, "y": 34.0}}
    assert recovered["pinned_refs"] == ["domain-name--legacy"]
    assert recovered["filter_text"] == "domain"
    assert recovered["viewport"] == {"x": 1.0, "y": 2.0, "scale": 1.5}


def test_web_service_and_tui_share_layout_management(tmp_path) -> None:
    service = WebCockpitService(
        ToolContext(config_dir=tmp_path / "config", workspace_dir=tmp_path / "workspaces")
    )
    service.ctx.workspace_mgr.store_stix_objects(
        [{"type": "domain-name", "value": "command-layout.example"}],
        module_name="test/layout",
        target="command-layout.example",
    )
    refs, edges = service._graph_presentation_scope()
    GraphPresentationAuthority(service.ctx.workspace_mgr).save(
        "Shared",
        node_positions={next(iter(refs)): {"x": 1, "y": 2}},
        viewport={"x": 0, "y": 0, "scale": 1},
        filter_text="",
        labels={},
        pinned_refs=[],
        current_node_refs=refs,
        current_edge_keys=edges,
    )
    assert service.execute_command("graph layout list")["data"][0]["name"] == "Shared"
    shown = service.execute_command("graph layout show Shared")["data"]
    assert shown["topology_changed"] is False

    verb = parse_repl_verb("graph layout list")
    assert verb is not None
    rendered = dispatch_repl_verb(verb, None, None, service.ctx.workspace_mgr)
    assert '"name": "Shared"' in rendered
    assert "graph layout list" in command_completions("graph layout l")


def test_graph_node_annotations_reuse_workspace_notes_across_web_and_tui(tmp_path) -> None:
    service = WebCockpitService(
        ToolContext(config_dir=tmp_path / "config", workspace_dir=tmp_path / "workspaces")
    )
    service.ctx.workspace_mgr.store_stix_objects(
        [{"type": "domain-name", "value": "annotated-node.example"}],
        module_name="test/annotation",
        target="annotated-node.example",
    )
    node_ref = next(iter(service._graph_presentation_scope()[0]))

    saved = service.annotate_graph(
        {"node_ref": node_ref, "text": "Review the passive-DNS history."}
    )
    assert saved["annotation"]["node_ref"] == node_ref
    assert saved["annotation"]["content_class"] == "analyst_annotation"
    assert saved["annotation"]["evidence"] is False
    assert service.graph_annotations(node_ref)["annotations"] == [saved["annotation"]]

    verb = parse_repl_verb(f"graph annotate {node_ref} | Compare certificate reuse")
    assert verb is not None
    rendered = dispatch_repl_verb(verb, None, None, service.ctx.workspace_mgr)
    assert "Compare certificate reuse" in rendered
    assert "graph annotate " in command_completions("graph ann")

    with pytest.raises(ValueError, match="current graph"):
        service.annotate_graph({"node_ref": "domain-name--missing", "text": "Invalid"})


def test_graph_fingerprint_is_order_independent() -> None:
    assert graph_fingerprint({"b", "a"}, {"y", "x"}) == graph_fingerprint(
        {"a", "b"}, {"x", "y"}
    )
