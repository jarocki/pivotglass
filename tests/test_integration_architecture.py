"""Executable target-architecture contracts for Synapse and SCOT4."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from stix2 import DomainName, IPv4Address, Relationship

from adversary_pursuit.core.analytic_ledger import AnalyticLedger
from adversary_pursuit.core.graph_repository import WorkspaceGraphRepository
from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.integrations.scot_publication import (
    build_scot_publication_manifest,
    validate_scot_pivot_request,
)
from adversary_pursuit.integrations.synapse_graph import (
    build_synapse_shadow_manifest,
    compare_synapse_shadow,
)


def _workspace(tmp_path) -> WorkspaceManager:
    manager = WorkspaceManager(tmp_path / "workspaces")
    manager.create("case")
    manager.switch("case")
    domain = DomainName(value="graph.example")
    address = IPv4Address(value="198.51.100.42")
    relation = Relationship(
        source_ref=domain.id,
        target_ref=address.id,
        relationship_type="resolves-to",
    )
    manager.store_stix_objects(
        [domain, address, relation],
        module_name="test/source",
        target="graph.example",
        fetched_at="2026-08-23T12:00:00Z",
    )
    AnalyticLedger(manager).create_question("Who operates graph.example?")
    return manager


def test_graph_repository_snapshot_is_deterministic_and_provenance_complete(tmp_path):
    repository = WorkspaceGraphRepository(_workspace(tmp_path))

    first = repository.snapshot()
    second = repository.snapshot()

    assert first == second
    assert first.schema_version == "pivotglass-graph-repository-1.0"
    assert first.source_backend == "workspace-local"
    assert all(edge.provenance_refs for edge in first.edges)


def test_synapse_shadow_uses_native_entities_and_exact_parity(tmp_path):
    snapshot = WorkspaceGraphRepository(_workspace(tmp_path)).snapshot()
    manifest = build_synapse_shadow_manifest(snapshot)

    forms = {node.form for node in manifest.nodes}
    assert {"inet:fqdn", "inet:ipv4", "pivotglass:record"} <= forms
    assert all(edge.provenance_refs for edge in manifest.edges)
    assert compare_synapse_shadow(manifest, manifest).cutover_ready is True

    incomplete = manifest.model_copy(
        update={"nodes": manifest.nodes[:-1], "digest_sha256": "0" * 64}
    )
    receipt = compare_synapse_shadow(manifest, incomplete)
    assert receipt.cutover_ready is False
    assert receipt.missing_node_ids

    wrong_workspace = manifest.model_copy(update={"workspace": "other"})
    metadata_receipt = compare_synapse_shadow(manifest, wrong_workspace)
    assert metadata_receipt.metadata_match is False
    assert metadata_receipt.cutover_ready is False


def test_scot_publication_is_deterministic_reviewable_and_relationship_complete(tmp_path):
    snapshot = WorkspaceGraphRepository(_workspace(tmp_path)).snapshot()

    first = build_scot_publication_manifest(snapshot)
    second = build_scot_publication_manifest(snapshot)

    assert first == second
    assert first.approval_required is True
    assert first.published is False
    assert any(item.object_type == "event" for item in first.items)
    assert any(item.object_type == "entity" for item in first.items)
    assert any(
        item.object_type == "entry" and item.payload.get("title") == "Pivotglass relationship index"
        for item in first.items
    )
    assert len(first.connections) == len(snapshot.edges)
    assert all(connection.provenance_refs for connection in first.connections)


def test_scot_pivot_request_validates_but_does_not_enqueue():
    request = validate_scot_pivot_request(
        workspace="case",
        scot_object_type="event",
        scot_object_id=42,
        indicator="198.51.100.42",
        requested_by="analyst@example.test",
        requested_at=datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
        reason="Investigate the related address.",
        scot_revision="7",
    )

    assert request.indicator_type == "ipv4"
    assert request.disposition == "preview"
    assert request.enqueue_requires_analyst_action is True

    with pytest.raises(ValueError):
        validate_scot_pivot_request(
            workspace="case",
            scot_object_type="event",
            scot_object_id=42,
            indicator="not-an-indicator",
            requested_by="analyst",
            requested_at=datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
            reason="Try it.",
        )

    with pytest.raises(ValueError):
        validate_scot_pivot_request(
            workspace="case",
            scot_object_type="event",
            scot_object_id=42,
            indicator="198.51.100.42",
            requested_by="analyst",
            requested_at=datetime(2026, 8, 23, 12, 0),
            reason="Try it.",
        )

    with pytest.raises(ValueError):
        validate_scot_pivot_request(
            workspace="case",
            scot_object_type="unknown",
            scot_object_id=42,
            indicator="198.51.100.42",
            requested_by="analyst",
            requested_at=datetime(2026, 8, 23, 12, 0),
            reason="Try it.",
        )
