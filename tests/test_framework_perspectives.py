"""Tests for version-pinned ATT&CK, Kill Chain, and Diamond perspectives."""

from __future__ import annotations

import hashlib
import json

import pytest

from adversary_pursuit.core.analytic_ledger import ConfidenceLevel
from adversary_pursuit.core.framework_perspectives import (
    AttackCatalog,
    AttackContentManifest,
    DiamondMetaFeature,
    DiamondVertex,
    KillChainPhase,
    KillChainRelation,
    KillChainTransition,
    build_attack_navigator_layer,
    build_attack_perspective,
    build_diamond_event,
    build_kill_chain_perspective,
)
from adversary_pursuit.core.framework_projections import (
    Framework,
    FrameworkProjectionAuthority,
    MappingOrigin,
    MappingState,
)
from adversary_pursuit.core.workspace import WorkspaceManager


def _workspace(tmp_path) -> WorkspaceManager:
    manager = WorkspaceManager(tmp_path / "workspaces")
    manager.create("case")
    manager.switch("case")
    return manager


def _observation(manager: WorkspaceManager, value: str) -> str:
    manager.store_stix_objects(
        [{"type": "domain-name", "value": value}],
        module_name="test/source",
        target=value,
    )
    return manager.get_observations()[-1]["id"]


def _catalog(tmp_path) -> AttackCatalog:
    payload = {
        "type": "bundle",
        "id": "bundle--test",
        "objects": [
            {
                "type": "x-mitre-collection",
                "id": "x-mitre-collection--test",
                "name": "Enterprise ATT&CK",
                "x_mitre_version": "19.2",
                "modified": "2026-08-05T21:33:58.496Z",
            },
            {
                "type": "x-mitre-tactic",
                "id": "x-mitre-tactic--credential-access",
                "name": "Credential Access",
                "x_mitre_shortname": "credential-access",
                "x_mitre_domains": ["enterprise-attack"],
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": "TA0006"}
                ],
            },
            {
                "type": "attack-pattern",
                "id": "attack-pattern--credential-dumping",
                "name": "OS Credential Dumping",
                "x_mitre_domains": ["enterprise-attack"],
                "x_mitre_version": "3.0",
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": "T1003"}
                ],
                "kill_chain_phases": [
                    {"kill_chain_name": "mitre-attack", "phase_name": "credential-access"}
                ],
            },
            {
                "type": "attack-pattern",
                "id": "attack-pattern--deprecated",
                "name": "Deprecated",
                "x_mitre_domains": ["enterprise-attack"],
                "x_mitre_deprecated": True,
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": "T9999"}
                ],
            },
        ],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    path = tmp_path / "enterprise-attack-19.2.json"
    path.write_bytes(raw)
    manifest = AttackContentManifest(
        domain="enterprise-attack",
        version="19.2",
        source_url="https://example.test/enterprise-attack-19.2.json",
        sha256=hashlib.sha256(raw).hexdigest(),
        collection_name="Enterprise ATT&CK",
        navigator_layer_version="4.5",
        navigator_version="5.3.2",
    )
    return AttackCatalog.from_path(path, manifest=manifest)


def _propose(
    authority: FrameworkProjectionAuthority,
    *,
    framework: Framework,
    version: str,
    content_id: str,
    evidence_ref: str,
):
    return authority.propose(
        framework=framework,
        framework_version=version,
        content_id=content_id,
        content_label=content_id,
        evidence_refs=(evidence_ref,),
        basis=f"{evidence_ref} supports {content_id}.",
        mapper="test-analyst",
        mapper_version="1.0",
        origin=MappingOrigin.HUMAN,
        confidence=ConfidenceLevel.MODERATE,
        confidence_rationale="One direct observation; corroboration remains open.",
    )


def test_attack_catalog_verifies_digest_version_and_filters_deprecated(tmp_path) -> None:
    catalog = _catalog(tmp_path)
    assert catalog.manifest.version == "19.2"
    assert [item.attack_id for item in catalog.tactics] == ["TA0006"]
    assert [item.attack_id for item in catalog.techniques] == ["T1003"]
    assert catalog.technique("t1003").tactics == ("credential-access",)

    path = tmp_path / "tampered.json"
    path.write_text("{}")
    with pytest.raises(ValueError, match="digest mismatch"):
        AttackCatalog.from_path(path, manifest=catalog.manifest)


def test_attack_navigator_export_retains_state_and_evidence(tmp_path) -> None:
    manager = _workspace(tmp_path)
    authority = FrameworkProjectionAuthority(manager)
    observation_id = _observation(manager, "credential-dumping.example")
    mapping = _propose(
        authority,
        framework=Framework.ATTACK,
        version="19.2",
        content_id="T1003",
        evidence_ref=observation_id,
    )
    authority.disposition(mapping.id, MappingState.ACCEPTED)
    catalog = _catalog(tmp_path)
    perspective = build_attack_perspective(
        authority,
        catalog,
        required_technique_ids=("T1003", "T1059"),
    )
    assert perspective.unknown_content_ids == ("T1059",)
    layer = build_attack_navigator_layer(
        perspective,
        catalog,
        name="Case ATT&CK view",
        description="Evidence-backed mappings only.",
    )
    assert layer["versions"] == {"attack": "19.2", "navigator": "5.3.2", "layer": "4.5"}
    assert layer["techniques"][0]["techniqueID"] == "T1003"
    assert layer["techniques"][0]["color"] == "#4CAF50"
    assert observation_id in layer["techniques"][0]["metadata"][3]["value"]


def test_kill_chain_does_not_infer_linearity_and_supports_loops(tmp_path) -> None:
    manager = _workspace(tmp_path)
    authority = FrameworkProjectionAuthority(manager)
    delivery_observation = _observation(manager, "delivery.example")
    c2_observation = _observation(manager, "command-and-control.example")
    delivery = _propose(
        authority,
        framework=Framework.KILL_CHAIN,
        version="lockheed-martin-2011",
        content_id="kill-chain:delivery",
        evidence_ref=delivery_observation,
    )
    c2 = _propose(
        authority,
        framework=Framework.KILL_CHAIN,
        version="lockheed-martin-2011",
        content_id="kill-chain:command-and-control",
        evidence_ref=c2_observation,
    )
    authority.disposition(delivery.id, MappingState.ACCEPTED)
    authority.disposition(c2.id, MappingState.ACCEPTED)
    transition = KillChainTransition(
        source_mapping_id=c2.id,
        target_mapping_id=delivery.id,
        relation=KillChainRelation.LOOPS_TO,
        evidence_refs=(c2_observation,),
        rationale="The operator returned to a delivery channel after C2 was established.",
    )
    perspective = build_kill_chain_perspective(authority, transitions=(transition,))
    assert [item.phase for item in perspective.assignments] == [
        KillChainPhase.DELIVERY,
        KillChainPhase.COMMAND_AND_CONTROL,
    ]
    assert perspective.transitions[0].relation is KillChainRelation.LOOPS_TO
    assert KillChainPhase.WEAPONIZATION in perspective.unmapped_phases
    assert "not a claim" in perspective.caveat


def test_diamond_event_keeps_unknown_vertices_and_provisional_state(tmp_path) -> None:
    manager = _workspace(tmp_path)
    authority = FrameworkProjectionAuthority(manager)
    observation_id = _observation(manager, "diamond-infrastructure.example")
    infrastructure = _propose(
        authority,
        framework=Framework.DIAMOND,
        version="diamond-model-1.0",
        content_id="diamond:infrastructure:domain-name--example",
        evidence_ref=observation_id,
    )
    event = build_diamond_event(
        authority,
        event_id="diamond-event-1",
        mapping_ids=(infrastructure.id,),
        confidence=ConfidenceLevel.LOW,
        confidence_rationale="Only infrastructure is presently known.",
        meta_features=(
            DiamondMetaFeature(
                name="first_seen",
                value="2026-08-18T01:00:00Z",
                evidence_refs=(observation_id,),
            ),
        ),
        activity_thread="thread-1",
    )
    assert event.provisional is True
    assert event.vertices[0].vertex is DiamondVertex.INFRASTRUCTURE
    assert set(event.unknown_vertices) == {
        DiamondVertex.ADVERSARY,
        DiamondVertex.CAPABILITY,
        DiamondVertex.VICTIM,
    }
    assert event.meta_features[0].evidence_refs == (observation_id,)


def test_diamond_event_rejects_duplicate_core_vertices(tmp_path) -> None:
    manager = _workspace(tmp_path)
    authority = FrameworkProjectionAuthority(manager)
    one_observation = _observation(manager, "diamond-one.example")
    two_observation = _observation(manager, "diamond-two.example")
    one = _propose(
        authority,
        framework=Framework.DIAMOND,
        version="diamond-model-1.0",
        content_id="diamond:infrastructure:domain-name--one",
        evidence_ref=one_observation,
    )
    two = _propose(
        authority,
        framework=Framework.DIAMOND,
        version="diamond-model-1.0",
        content_id="diamond:infrastructure:ipv4-addr--two",
        evidence_ref=two_observation,
    )
    with pytest.raises(ValueError, match="one assignment"):
        build_diamond_event(
            authority,
            event_id="diamond-event-duplicate",
            mapping_ids=(one.id, two.id),
            confidence=ConfidenceLevel.LOW,
            confidence_rationale="Conflicting infrastructure assignments require separation.",
        )
