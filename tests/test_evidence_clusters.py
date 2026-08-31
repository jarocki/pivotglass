"""Stable evidence-cluster summaries never become attribution claims."""

from __future__ import annotations

from stix2 import DomainName, IPv4Address, Relationship

from adversary_pursuit.agent.repl_verbs import dispatch_repl_verb, parse_repl_verb
from adversary_pursuit.agent.tools import ToolContext
from adversary_pursuit.core.analytic_ledger import ConfidenceLevel
from adversary_pursuit.core.command_completion import command_completions
from adversary_pursuit.core.evidence_clusters import build_evidence_clusters
from adversary_pursuit.core.framework_projections import (
    Framework,
    FrameworkProjectionAuthority,
    MappingOrigin,
)
from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.web.server import WebCockpitService


def _workspace(tmp_path):
    manager = WorkspaceManager(tmp_path)
    manager.create("case")
    manager.switch("case")
    return manager


def test_connected_entities_form_stable_cluster_with_provenance_and_gaps(tmp_path) -> None:
    manager = _workspace(tmp_path)
    domain = DomainName(value="cluster.example")
    address = IPv4Address(value="198.51.100.9")
    relationship = Relationship(
        source_ref=domain.id,
        target_ref=address.id,
        relationship_type="resolves-to",
    )
    manager.store_stix_objects(
        [domain, address, relationship],
        module_name="source/one",
        target="cluster.example",
        fetched_at="2026-08-01T00:00:00Z",
        source_dependence_group="provider-one",
    )
    observation = next(
        item for item in manager.get_observations() if item["entity_ref"] == domain.id
    )
    FrameworkProjectionAuthority(manager).propose(
        framework=Framework.ATTACK,
        framework_version="19.2",
        content_id="T1583.001",
        content_label="Acquire Infrastructure: Domains",
        evidence_refs=(observation["id"],),
        basis="Source reporting describes acquired infrastructure.",
        mapper="analyst",
        mapper_version="1.0",
        origin=MappingOrigin.HUMAN,
        confidence=ConfidenceLevel.LOW,
        confidence_rationale="One source; alternative explanations remain open.",
    )

    first = build_evidence_clusters(manager)
    second = build_evidence_clusters(manager)

    assert first == second
    assert len(first) == 1
    cluster = first[0]
    assert {item.reference for item in cluster.entities} == {domain.id, address.id}
    assert cluster.truth_classes == ("observed",)
    assert cluster.first_observed == "2026-08-01T00:00:00Z"
    assert cluster.last_observed == "2026-08-01T00:00:00Z"
    assert cluster.provenance_sources
    assert cluster.mapped_behaviors[0].content_id == "T1583.001"
    assert cluster.dossier_gaps
    assert "not proof" in cluster.caveat


def test_isolated_entities_remain_visible_without_invented_edges(tmp_path) -> None:
    manager = _workspace(tmp_path)
    manager.store_stix_objects(
        [DomainName(value="one.example"), DomainName(value="two.example")],
        module_name="source/one",
        target="one.example",
    )

    clusters = build_evidence_clusters(manager)

    assert len(clusters) == 2
    assert all(len(cluster.entities) == 1 for cluster in clusters)
    assert all(cluster.edge_ids == () for cluster in clusters)
    assert all(cluster.truth_classes == () for cluster in clusters)


def test_web_and_tui_share_cluster_command(tmp_path) -> None:
    service = WebCockpitService(
        ToolContext(config_dir=tmp_path / "config", workspace_dir=tmp_path / "workspaces")
    )
    service.ctx.workspace_mgr.store_stix_objects(
        [DomainName(value="command-cluster.example")],
        module_name="source/command",
        target="command-cluster.example",
    )

    web = service.execute_command("graph clusters")
    verb = parse_repl_verb("graph clusters")
    assert verb is not None
    tui = dispatch_repl_verb(verb, None, None, service.ctx.workspace_mgr)

    assert web["data"][0]["entities"][0]["value"] == "command-cluster.example"
    assert "command-cluster.example" in tui
    assert "graph clusters" in command_completions("graph cl")
