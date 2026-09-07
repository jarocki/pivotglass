"""Persistent document library and analyst pivot trail contracts."""

from __future__ import annotations

import hashlib
import sqlite3

import pytest
from sqlalchemy import inspect

from adversary_pursuit.core.document_library import (
    DocumentLibraryService,
    PivotTrailAuthority,
)
from adversary_pursuit.core.investigation_graph import GraphTruthKind, build_investigation_graph
from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.core.workspace_admin import export_workspace, merge_workspaces
from adversary_pursuit.core.workspace_migrations import CURRENT_WORKSPACE_SCHEMA_VERSION


def _workspace(tmp_path) -> WorkspaceManager:
    manager = WorkspaceManager(tmp_path)
    manager.create("library")
    manager.switch("library")
    return manager


def test_explicit_ingestion_populates_library_candidates_graph_and_pivot_trail(tmp_path) -> None:
    manager = _workspace(tmp_path)
    data = b"Source reporting names 198.51.100.8 and node.example."
    service = DocumentLibraryService(manager)

    receipt = service.ingest_bytes(
        data,
        filename="report.txt",
        operator="analyst",
        expected_sha256=hashlib.sha256(data).hexdigest(),
    )

    assert receipt.candidate_count == 2
    assert "does not validate" in receipt.truth_boundary
    library = service.list()
    assert len(library) == 1
    assert library[0].filename == "report.txt"
    assert library[0].candidate_count == 2
    assert not hasattr(library[0], "output_text")
    detail = service.detail(library[0].occurrence_id)
    assert "198.51.100.8" in detail["parser"]["output_text"]
    assert len(detail["candidates"]) == 2

    graph = build_investigation_graph(manager)
    assert any(node.kind == "document" and node.label == "report.txt" for node in graph.nodes)
    assert sum(node.kind == "document_candidate" for node in graph.nodes) == 2
    candidate_edges = [edge for edge in graph.edges if edge.relationship == "contains-candidate"]
    assert len(candidate_edges) == 2
    assert all(edge.truth_kind is GraphTruthKind.STRUCTURAL for edge in candidate_edges)
    assert PivotTrailAuthority(manager).list()[0]["action"] == "document_ingested"


def test_ingestion_is_bound_to_the_reviewed_sha256(tmp_path) -> None:
    manager = _workspace(tmp_path)
    with pytest.raises(ValueError, match="changed after preview"):
        DocumentLibraryService(manager).ingest_bytes(
            b"changed",
            filename="report.txt",
            operator="analyst",
            expected_sha256=hashlib.sha256(b"reviewed").hexdigest(),
        )
    assert DocumentLibraryService(manager).list() == ()


def test_pivot_trail_is_ordered_deduplicated_and_not_observed_truth(tmp_path) -> None:
    manager = _workspace(tmp_path)
    trail = PivotTrailAuthority(manager)
    first = trail.record_indicator("198.51.100.10")
    assert trail.record_indicator("198.51.100.10") == first
    trail.record_indicator("second.example")

    events = trail.list()
    assert len(events) == 2
    assert events[1]["from_ref"] == events[0]["to_ref"]
    graph = build_investigation_graph(manager)
    edge = next(edge for edge in graph.edges if edge.relationship == "pivoted-to")
    assert edge.truth_kind is GraphTruthKind.DERIVED_NAVIGATION
    assert "not a threat relationship" in edge.rationale


def test_schema_v11_migrates_pivot_trail_backup_first(tmp_path) -> None:
    manager = _workspace(tmp_path)
    manager._engine.dispose()
    manager._engine = None
    manager._active = None
    db_path = tmp_path / "library.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP TABLE pivot_trail_events")
        connection.execute("UPDATE workspace_schema_version SET version = 11 WHERE id = 1")

    migrated = WorkspaceManager(tmp_path)
    migrated.switch("library")
    assert "pivot_trail_events" in set(inspect(migrated._engine).get_table_names())
    assert migrated.get_workspace_schema_status()["to_version"] == CURRENT_WORKSPACE_SCHEMA_VERSION
    assert (tmp_path / "library.db.pre-v11-backup").is_file()


def test_document_library_exports_and_merges_with_verified_source_bytes(tmp_path) -> None:
    manager = WorkspaceManager(tmp_path)
    manager.create("source")
    manager.create("destination")
    manager.switch("source")
    data = b"Merge source document.example into the destination library."
    digest = hashlib.sha256(data).hexdigest()
    DocumentLibraryService(manager).ingest_bytes(
        data,
        filename="merge.txt",
        operator="analyst",
        expected_sha256=digest,
    )

    exported = export_workspace(manager, "source")
    assert exported["format"] == "pivotglass-workspace-v12"
    assert exported["tables"]["document_occurrences"][0]["filename"] == "merge.txt"
    counts = merge_workspaces(manager, "source", "destination")
    assert counts["document_occurrences"] == 1
    assert counts["pivot_trail_events"] == 1
    assert counts["raw_document_files"] == 1

    manager.switch("destination")
    assert DocumentLibraryService(manager).list()[0].filename == "merge.txt"
    merged_content = tmp_path / "destination.content" / "sha256" / digest[:2] / digest
    assert merged_content.read_bytes() == data
