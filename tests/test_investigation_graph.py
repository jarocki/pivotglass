"""Two-layer investigation graph projection contracts."""

from __future__ import annotations

import json
import sqlite3

import pytest
from sqlalchemy import inspect
from stix2 import DomainName, IPv4Address, Relationship

from adversary_pursuit.agent.repl_verbs import dispatch_repl_verb, parse_repl_verb
from adversary_pursuit.core.analytic_ledger import (
    AnalyticLedger,
    AssertionType,
    ConfidenceLevel,
    EvidenceStance,
)
from adversary_pursuit.core.command_completion import command_completions
from adversary_pursuit.core.framework_projections import (
    Framework,
    FrameworkProjectionAuthority,
    MappingOrigin,
)
from adversary_pursuit.core.investigation_graph import (
    GraphLayer,
    GraphPresentationAuthority,
    GraphTruthKind,
    build_investigation_graph,
)
from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.core.workspace_migrations import get_workspace_schema_version


def _workspace(tmp_path) -> WorkspaceManager:
    manager = WorkspaceManager(tmp_path / "workspaces")
    manager.create("case")
    manager.switch("case")
    return manager


def test_two_layer_projection_preserves_entity_and_epistemic_provenance(tmp_path) -> None:
    manager = _workspace(tmp_path)
    domain = DomainName(value="graph.example")
    address = IPv4Address(value="198.51.100.42")
    relationship = Relationship(
        source_ref=domain.id,
        target_ref=address.id,
        relationship_type="resolves-to",
    )
    manager.store_stix_objects(
        [domain, address, relationship],
        module_name="test/source",
        target="graph.example",
        fetched_at="2026-08-18T12:00:00Z",
    )
    observations = manager.get_observations()
    domain_observation = next(item for item in observations if item["entity_ref"] == domain.id)

    ledger = AnalyticLedger(manager)
    question_id = ledger.create_question("Who controls graph.example?")
    hypothesis_id = ledger.create_hypothesis(question_id, "Actor A controls the domain.")
    assertion_id = ledger.create_assertion(
        "The domain resolves to the observed address.",
        assertion_type=AssertionType.INFERRED,
        subject_ref=domain.id,
        predicate="resolves-to",
        object_ref=address.id,
    )
    ledger.link_evidence(
        source_kind="observation",
        source_id=domain_observation["id"],
        target_kind="assertion",
        target_id=assertion_id,
        stance=EvidenceStance.SUPPORTS,
        rationale="The domain was returned by the source.",
    )
    ledger.link_evidence(
        source_kind="assertion",
        source_id=assertion_id,
        target_kind="hypothesis",
        target_id=hypothesis_id,
        stance=EvidenceStance.SUPPORTS,
        rationale="The relationship is consistent with the hypothesis.",
    )
    ledger.assess_confidence(
        target_kind="hypothesis",
        target_id=hypothesis_id,
        level=ConfidenceLevel.LOW,
        rationale="One source-backed relationship is insufficient for attribution.",
        factors={
            "source_quality": "direct provider output",
            "source_independence": "one dependence group",
            "corroboration": "none",
            "assumptions": "infrastructure control implies actor control",
            "knowledge_gaps": "registrant and operator identity",
            "analytic_rigor": "competing explanations remain open",
        },
    )
    FrameworkProjectionAuthority(manager).propose(
        framework=Framework.ATTACK,
        framework_version="19.2",
        content_id="T1583.001",
        content_label="Acquire Infrastructure: Domains",
        evidence_refs=(domain_observation["id"],),
        basis="The source observed infrastructure used in the investigation.",
        mapper="test-analyst",
        mapper_version="1.0",
        origin=MappingOrigin.HUMAN,
        confidence=ConfidenceLevel.LOW,
        confidence_rationale="Infrastructure acquisition is plausible but uncorroborated.",
    )

    projection = build_investigation_graph(manager)
    node_ids = {node.id for node in projection.nodes}
    assert f"entity:{domain.id}" in node_ids
    assert f"epistemic:observation:{domain_observation['id']}" in node_ids
    assert f"epistemic:hypothesis:{hypothesis_id}" in node_ids
    assert any(node.kind == "framework_mapping" for node in projection.nodes)
    assert all(edge.provenance_refs for edge in projection.edges)
    assert any(
        edge.layer is GraphLayer.ENTITY
        and edge.relationship == "resolves-to"
        and edge.truth_kind is GraphTruthKind.OBSERVED
        for edge in projection.edges
    )
    assert any(
        edge.layer is GraphLayer.BRIDGE and edge.relationship == "observes"
        for edge in projection.edges
    )
    assert any(
        edge.layer is GraphLayer.EPISTEMIC and edge.relationship == "supports"
        for edge in projection.edges
    )
    hypothesis = next(node for node in projection.nodes if node.record_ref == hypothesis_id)
    assert hypothesis.attributes["confidence"]["level"] == "low"


def test_property_pivots_are_explicitly_non_observed(tmp_path) -> None:
    manager = _workspace(tmp_path)
    manager.store_stix_objects(
        [
            {"type": "domain-name", "value": "seed.example"},
            {"type": "url", "value": "seed.example"},
        ],
        module_name="test/source",
        target="seed.example",
    )

    projection = build_investigation_graph(manager)
    edge = next(edge for edge in projection.edges if edge.relationship == "same-observable-value")
    assert edge.truth_kind is GraphTruthKind.DERIVED_NAVIGATION
    assert "not an observed" in edge.rationale
    assert len(edge.provenance_refs) == 2


def test_layered_graph_command_is_shared_and_completed(tmp_path) -> None:
    manager = _workspace(tmp_path)
    manager.store_stix_objects(
        [{"type": "domain-name", "value": "command.example"}],
        module_name="test/source",
        target="command.example",
    )
    verb = parse_repl_verb("graph layers")
    assert verb is not None
    rendered = dispatch_repl_verb(verb, None, None, manager)
    assert '"schema_version": "investigation-graph-1.0"' in rendered
    assert "graph layers" in command_completions("graph l")
    assert "graph layout list" in command_completions("graph layout l")


def test_saved_layout_is_validated_presentation_state_not_graph_truth(tmp_path) -> None:
    manager = _workspace(tmp_path)
    manager.store_stix_objects(
        [{"type": "domain-name", "value": "layout.example"}],
        module_name="test/source",
        target="layout.example",
    )
    before = build_investigation_graph(manager)
    entity = next(node for node in before.nodes if node.layer is GraphLayer.ENTITY)

    authority = GraphPresentationAuthority(manager)
    saved = authority.save(
        "Triage view",
        {
            "positions": {entity.record_ref: {"x": 120.5, "y": 88}},
            "pinned_refs": [entity.record_ref],
            "filters": {"query": "layout", "layers": ["entity"]},
            "viewport": {"x": 10, "y": -5, "scale": 1.25},
        },
    )
    assert saved.name == "Triage view"
    assert saved.positions[entity.record_ref].x == 120.5
    assert saved.pinned_refs == (entity.record_ref,)
    assert authority.list() == (saved,)

    replaced = authority.save(
        "Triage view",
        {
            "positions": {entity.record_ref: {"x": 150, "y": 90}},
            "filters": {"query": ""},
        },
    )
    assert replaced.id == saved.id
    assert len(authority.list()) == 1
    after = build_investigation_graph(manager)
    assert after.nodes == before.nodes
    assert after.edges == before.edges


def test_layout_rejects_unknown_nodes_invalid_coordinates_and_schema(tmp_path) -> None:
    manager = _workspace(tmp_path)
    manager.store_stix_objects(
        [{"type": "domain-name", "value": "guard.example"}],
        module_name="test/source",
        target="guard.example",
    )
    authority = GraphPresentationAuthority(manager)
    with pytest.raises(ValueError, match="outside the current graph"):
        authority.save("Unknown", {"positions": {"domain-name--missing": {"x": 1, "y": 2}}})
    with pytest.raises(ValueError, match="outside the supported range"):
        authority.save(
            "Infinite",
            {"positions": {manager.get_stix_objects()[0]["id"]: {"x": float("inf"), "y": 2}}},
        )
    with pytest.raises(ValueError, match="current graph schema"):
        authority.save("Old", {"graph_schema_version": "investigation-graph-0.9"})


def test_graph_annotations_reuse_analyst_notes_and_shared_command(tmp_path) -> None:
    manager = _workspace(tmp_path)
    manager.store_stix_objects(
        [{"type": "domain-name", "value": "annotate.example"}],
        module_name="test/source",
        target="annotate.example",
    )
    entity = next(
        node for node in build_investigation_graph(manager).nodes if node.layer is GraphLayer.ENTITY
    )
    verb = parse_repl_verb(f"graph annotate {entity.id} | Verify passive DNS history")
    assert verb is not None
    rendered = json.loads(dispatch_repl_verb(verb, None, None, manager))
    assert rendered["annotation"]["record_ref"] == entity.record_ref
    assert rendered["annotation"]["content"] == "Verify passive DNS history"
    assert manager.get_workspace_stats()["note_count"] == 1

    verb = parse_repl_verb(f"graph annotations {entity.id}")
    assert verb is not None
    annotations = json.loads(dispatch_repl_verb(verb, None, None, manager))["annotations"]
    assert [item["content"] for item in annotations] == ["Verify passive DNS history"]


def test_schema_v5_migrates_to_graph_layout_schema_with_backup(tmp_path) -> None:
    manager = WorkspaceManager(tmp_path / "migration")
    manager.create("v5")
    manager._engine = None
    manager._active = None
    connection = sqlite3.connect(tmp_path / "migration" / "v5.db")
    connection.execute("DROP TABLE graph_presentation_layouts")
    connection.execute("UPDATE workspace_schema_version SET version = 5 WHERE id = 1")
    connection.commit()
    connection.close()

    manager.switch("v5")

    assert (tmp_path / "migration" / "v5.db.pre-v5-backup").is_file()
    assert get_workspace_schema_version(manager._engine) == 6
    assert "graph_presentation_layouts" in inspect(manager._engine).get_table_names()
