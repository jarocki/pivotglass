"""Longitudinal cluster snapshots preserve exact governed graph change."""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlalchemy import select
from stix2 import DomainName, IPv4Address, Relationship

from adversary_pursuit.agent.repl_verbs import dispatch_repl_verb, parse_repl_verb
from adversary_pursuit.agent.tools import ToolContext
from adversary_pursuit.core.command_completion import command_completions
from adversary_pursuit.core.evidence_cluster_history import (
    ClusterSnapshotEnvelope,
    ClusterSnapshotLimits,
    EvidenceClusterHistory,
)
from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.models.database import EvidenceClusterSnapshot
from adversary_pursuit.web.server import WebCockpitService


def _workspace(tmp_path):
    manager = WorkspaceManager(tmp_path)
    manager.create("history")
    manager.switch("history")
    return manager


def test_cluster_snapshots_show_added_entities_edges_and_membership_without_rewriting(tmp_path) -> None:
    manager = _workspace(tmp_path)
    domain = DomainName(value="history.example")
    manager.store_stix_objects([domain], module_name="source/one", target=domain.value)
    history = EvidenceClusterHistory(manager)
    before = history.capture(captured_by="analyst")

    address = IPv4Address(value="198.51.100.44")
    relationship = Relationship(
        source_ref=domain.id,
        target_ref=address.id,
        relationship_type="resolves-to",
    )
    manager.store_stix_objects(
        [address, relationship],
        module_name="source/two",
        target=address.value,
    )
    after = history.capture(captured_by="analyst")
    comparison = history.diff(before.id, after.id)

    assert before.graph_fingerprint != after.graph_fingerprint
    assert {item.after["record_ref"] for item in comparison.added_entities if item.after} == {
        address.id
    }
    assert len(comparison.added_relationships) == 1
    assert comparison.removed_entities == ()
    assert comparison.removed_relationships == ()
    assert {item.entity_ref for item in comparison.cluster_membership_changes} == {
        domain.id,
        address.id,
    }
    assert "not conflict" in comparison.caveat
    assert [item.id for item in history.list()] == [before.id, after.id]
    assert manager.get_workspace_table_counts()["evidence_cluster_snapshots"] == 2


def test_snapshot_limits_fail_clearly_without_partial_record(tmp_path) -> None:
    manager = _workspace(tmp_path)
    manager.store_stix_objects(
        [DomainName(value="one.example"), DomainName(value="two.example")],
        module_name="source/one",
        target="one.example",
    )

    with pytest.raises(ValueError, match="snapshot limit"):
        EvidenceClusterHistory(manager).capture(
            captured_by="analyst",
            limits=ClusterSnapshotLimits(max_nodes=1),
        )

    assert manager.get_workspace_table_counts()["evidence_cluster_snapshots"] == 0


def test_diff_calls_only_explicit_relationship_a_recorded_contradiction(tmp_path) -> None:
    manager = _workspace(tmp_path)
    history = EvidenceClusterHistory(manager)
    base = ClusterSnapshotEnvelope(
        id="cluster-snapshot-before",
        workspace="history",
        graph_fingerprint="a" * 64,
        captured_by="analyst",
        captured_at="2026-08-31T00:00:00+00:00",
        nodes=(),
        edges=(),
        clusters=(),
    )
    contradiction_edge = {
        "id": "edge-contradiction",
        "layer": "epistemic",
        "source": "hypothesis-a",
        "target": "observation-a",
        "relationship": "contradicts",
        "truth_kind": "analyst-assertion",
        "provenance_refs": ["analytic-link-a"],
        "rationale": "Analyst recorded the conflict.",
        "directed": True,
    }
    changed = base.model_copy(
        update={
            "id": "cluster-snapshot-after",
            "graph_fingerprint": "b" * 64,
            "captured_at": "2026-08-31T00:01:00+00:00",
            "edges": (contradiction_edge,),
        }
    )
    with manager.get_session() as session:
        for snapshot in (base, changed):
            session.add(
                EvidenceClusterSnapshot(
                    id=snapshot.id,
                    graph_fingerprint=snapshot.graph_fingerprint,
                    captured_by=snapshot.captured_by,
                    captured_at=datetime.fromisoformat(snapshot.captured_at),
                    snapshot=json.loads(snapshot.model_dump_json()),
                )
            )
        session.commit()

    comparison = history.diff(base.id, changed.id)

    assert [item.id for item in comparison.added_recorded_contradictions] == [
        "edge-contradiction"
    ]
    with manager.get_session() as session:
        assert len(session.execute(select(EvidenceClusterSnapshot)).scalars().all()) == 2


def test_web_and_tui_share_cluster_snapshot_commands(tmp_path) -> None:
    service = WebCockpitService(
        ToolContext(config_dir=tmp_path / "config", workspace_dir=tmp_path / "workspaces")
    )
    service.ctx.workspace_mgr.store_stix_objects(
        [DomainName(value="snapshot-command.example")],
        module_name="source/command",
        target="snapshot-command.example",
    )

    web = service.execute_command("graph snapshot capture analyst")
    verb = parse_repl_verb("graph snapshot list")
    assert verb is not None
    tui = dispatch_repl_verb(verb, None, None, service.ctx.workspace_mgr)

    assert web["data"]["captured_by"] == "analyst"
    assert web["data"]["id"] in tui
    assert "graph snapshot list" in command_completions("graph snapshot l")
