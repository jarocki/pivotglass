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
    compile_scot_write_plan,
    validate_scot_pivot_request,
)
from adversary_pursuit.integrations.synapse_graph import (
    build_synapse_shadow_manifest,
    compare_synapse_shadow,
)
from adversary_pursuit.integrations.synapse_migration import (
    compile_synapse_migration_plan,
    pivotglass_synapse_model_contract,
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
    assert {"inet:fqdn", "inet:ipv4", "_pivotglass:record"} <= forms
    assert all(edge.provenance_refs for edge in manifest.edges)
    assert all(edge.directed is True for edge in manifest.edges)
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


def test_synapse_model_and_migration_plan_are_versioned_bound_and_disabled(tmp_path):
    snapshot = WorkspaceGraphRepository(_workspace(tmp_path)).snapshot()
    manifest = build_synapse_shadow_manifest(snapshot)

    model = pivotglass_synapse_model_contract()
    first = compile_synapse_migration_plan(manifest)
    second = compile_synapse_migration_plan(manifest)

    assert first == second
    assert first.model_digest_sha256 == model.digest_sha256
    assert first.approval_required is True
    assert first.execution_enabled is False
    assert first.storm_validation_required is True
    assert first.isolated_shadow_view_required is True
    assert first.backup_required is True
    assert first.readback_required is True
    form_names = {form[0] for form in model.model_definition["forms"]}
    assert form_names == {"_pivotglass:record", "_pivotglass:edge"}
    writes = [operation for operation in first.operations if operation.phase == "write"]
    readbacks = [operation for operation in first.operations if operation.phase == "readback"]
    assert len(writes) == len(readbacks)
    assert all(operation.opts == {"readonly": False} for operation in writes)
    assert all(operation.opts == {"readonly": True} for operation in readbacks)
    assert all(operation.variables for operation in first.operations)
    assert all(
        str(value) not in operation.query
        for operation in first.operations
        for value in operation.variables.values()
        if isinstance(value, str) and len(value) > 3
    )
    seen: set[str] = set()
    for operation in first.operations:
        assert set(operation.depends_on) <= seen
        seen.add(operation.operation_id)
    edge_writes = [operation for operation in writes if "_pivotglass:edge" in operation.query]
    assert len(edge_writes) == len(manifest.edges)
    assert all(operation.variables["provenance_refs"] for operation in edge_writes)


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


def test_scot_write_plan_is_exact_ordered_review_only_and_read_back(tmp_path):
    snapshot = WorkspaceGraphRepository(_workspace(tmp_path)).snapshot()
    manifest = build_scot_publication_manifest(snapshot)

    first = compile_scot_write_plan(manifest, owner="analyst@example.test")
    second = compile_scot_write_plan(manifest, owner=" analyst@example.test ")

    assert first == second
    assert first.approval_required is True
    assert first.execution_enabled is False
    assert first.readback_required is True
    assert first.manifest_digest_sha256 == manifest.digest_sha256
    writes = [operation for operation in first.operations if operation.phase == "write"]
    readbacks = [operation for operation in first.operations if operation.phase == "readback"]
    assert len(readbacks) == len(writes)
    assert writes[0].path_template == "/event/"
    assert writes[0].body == {
        "owner": "analyst@example.test",
        "tlp": "unset",
        "status": "open",
        "subject": "Pivotglass hunt: case",
        "view_count": 0,
        "message_id": manifest.publication_id,
    }
    assert {operation.path_template for operation in writes} >= {
        "/event/",
        "/entity/",
        "/entry/",
        "/tag/tag_by_name",
        "/link/",
    }
    seen: set[str] = set()
    for operation in first.operations:
        assert set(operation.depends_on) <= seen
        seen.add(operation.operation_id)
    links = [operation for operation in writes if operation.path_template == "/link/"]
    assert len(links) == len(manifest.connections)
    assert all("truth_kind" in operation.body["context"] for operation in links)
    assert all(operation.method == "GET" and operation.body is None for operation in readbacks)


def test_scot_write_plan_escapes_entry_html_and_rejects_invalid_owner(tmp_path):
    snapshot = WorkspaceGraphRepository(_workspace(tmp_path)).snapshot()
    manifest = build_scot_publication_manifest(snapshot)
    entry_index = next(
        index for index, item in enumerate(manifest.items) if item.object_type == "entry"
    )
    entry = manifest.items[entry_index]
    items = list(manifest.items)
    items[entry_index] = entry.model_copy(
        update={"payload": {**entry.payload, "plain_text": "<script>alert(1)</script>"}}
    )
    hostile_manifest = manifest.model_copy(update={"items": tuple(items)})

    plan = compile_scot_write_plan(hostile_manifest, owner="analyst")
    entry_write = next(
        operation
        for operation in plan.operations
        if operation.phase == "write"
        and operation.client_ref == entry.client_ref
        and operation.path_template == "/entry/"
    )

    assert "<script>" not in entry_write.body["entry_data"]["html"]
    assert "&lt;script&gt;" in entry_write.body["entry_data"]["html"]
    with pytest.raises(ValueError):
        compile_scot_write_plan(manifest, owner="\n")


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
    repeated_request = validate_scot_pivot_request(
        workspace="case",
        scot_object_type="event",
        scot_object_id=42,
        indicator="198.51.100.42",
        requested_by="analyst@example.test",
        requested_at=datetime(2026, 8, 23, 13, 0, tzinfo=UTC),
        reason="Investigate the related address.",
        scot_revision="7",
    )
    assert repeated_request.request_id == request.request_id

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
