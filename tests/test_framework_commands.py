"""Shared command coverage for framework mapping and export workflows."""

from __future__ import annotations

import hashlib
import json

import pytest

from adversary_pursuit.core.framework_commands import execute_framework_command
from adversary_pursuit.core.framework_perspectives import AttackContentManifest
from adversary_pursuit.core.workspace import WorkspaceManager


def _workspace(tmp_path) -> WorkspaceManager:
    manager = WorkspaceManager(tmp_path / "workspaces")
    manager.create("case")
    manager.switch("case")
    return manager


def _observation(manager: WorkspaceManager) -> str:
    manager.store_stix_objects(
        [{"type": "domain-name", "value": "credential-dumping.example"}],
        module_name="test/source",
        target="credential-dumping.example",
    )
    return manager.get_observations()[0]["id"]


def _attack_catalog(tmp_path):
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
                "type": "attack-pattern",
                "id": "attack-pattern--credential-dumping",
                "name": "OS Credential Dumping",
                "x_mitre_domains": ["enterprise-attack"],
                "external_references": [{"source_name": "mitre-attack", "external_id": "T1003"}],
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
    return path, manifest


def test_shared_commands_map_review_and_show(tmp_path) -> None:
    manager = _workspace(tmp_path)
    observation_id = _observation(manager)
    proposed = execute_framework_command(
        tuple(
            (
                f"map attack 19.2 T1003 {observation_id} | OS Credential Dumping | "
                "The observation records credential access behavior. | moderate | "
                "One direct observation; independent corroboration remains open."
            ).split()
        ),
        manager,
    )
    mapping_id = proposed["data"]["id"]
    assert proposed["data"]["state"] == "proposed"

    accepted = execute_framework_command(
        tuple(f"accept {mapping_id} | Reviewed against the immutable observation.".split()),
        manager,
    )
    assert accepted["data"]["state"] == "accepted"
    shown = execute_framework_command(("show", "attack"), manager)
    assert shown["data"]["framework_version"] == "19.2"
    assert shown["data"]["mappings"][0]["evidence_refs"] == [observation_id]


def test_manifest_is_pinned_and_navigator_never_silently_downloads(tmp_path) -> None:
    manager = _workspace(tmp_path)
    catalog_path = tmp_path / "missing.json"
    manifest = execute_framework_command(("manifest",), manager, attack_catalog_path=catalog_path)
    assert manifest["data"]["attack"]["version"] == "19.2"
    assert len(manifest["data"]["attack"]["sha256"]) == 64
    assert "does not silently download" in manifest["data"]["download_policy"]
    with pytest.raises(ValueError, match="not installed"):
        execute_framework_command(("navigator",), manager, attack_catalog_path=catalog_path)


def test_navigator_export_uses_verified_content_and_mapping(tmp_path) -> None:
    manager = _workspace(tmp_path)
    observation_id = _observation(manager)
    proposed = execute_framework_command(
        tuple(
            (
                f"map attack 19.2 T1003 {observation_id} | OS Credential Dumping | "
                "Source-backed behavior. | high | Direct evidence reviewed by the analyst."
            ).split()
        ),
        manager,
    )
    execute_framework_command(
        tuple(f"accept {proposed['data']['id']} | Analyst verified.".split()), manager
    )
    path, manifest = _attack_catalog(tmp_path)
    exported = execute_framework_command(
        ("navigator",), manager, attack_catalog_path=path, attack_manifest=manifest
    )
    assert exported["filename"].endswith(".navigator.json")
    assert exported["data"]["techniques"][0]["techniqueID"] == "T1003"
    assert exported["data"]["techniques"][0]["color"] == "#4CAF50"


def test_framework_gap_becomes_one_sourced_information_requirement(tmp_path) -> None:
    manager = _workspace(tmp_path)
    factors = {
        "decision_impact": 4,
        "discriminating_power": 3,
        "time_sensitivity": 2,
        "feasibility": 3,
    }
    command = tuple(
        (
            "require attack 19.2 T1059 | Command and Scripting Interpreter | "
            "Collect and disposition evidence relevant to command execution. | "
            f"{json.dumps(factors)}"
        ).split()
    )

    recorded = execute_framework_command(command, manager)
    changed_factors = {**factors, "decision_impact": 1}
    repeated = execute_framework_command(
        tuple(
            (
                "require attack 19.2 T1059 | Command and Scripting Interpreter | "
                "A retry must not replace the stored requirement. | "
                f"{json.dumps(changed_factors)}"
            ).split()
        ),
        manager,
    )
    gaps = execute_framework_command(("gaps",), manager)["data"]["requirements"]

    assert recorded["data"]["created"] is True
    assert repeated["data"]["created"] is False
    assert repeated["data"]["item_id"] == recorded["data"]["item_id"]
    assert repeated["data"]["criteria"] == recorded["data"]["criteria"]
    assert len(gaps) == 1
    assert gaps[0]["item_type"] == "collection_requirement"
    assert gaps[0]["record_kind"] == "framework_gap"
    assert gaps[0]["record_id"] == "attack:19.2:T1059"
    assert gaps[0]["criteria"]["addresses"] == [
        {
            "kind": "framework_content",
            "id": "attack:19.2:T1059",
            "framework": "attack",
            "version": "19.2",
            "content_id": "T1059",
            "label": "Command and Scripting Interpreter",
        }
    ]
    assert recorded["data"]["content_class"] == "analyst_collection_requirement"


def test_accepted_mapping_cannot_be_recorded_as_framework_gap(tmp_path) -> None:
    manager = _workspace(tmp_path)
    observation_id = _observation(manager)
    proposed = execute_framework_command(
        tuple(
            (
                f"map attack 19.2 T1003 {observation_id} | OS Credential Dumping | "
                "Source-backed behavior. | high | Direct evidence reviewed by the analyst."
            ).split()
        ),
        manager,
    )
    execute_framework_command(
        tuple(f"accept {proposed['data']['id']} | Analyst verified.".split()), manager
    )
    factors = json.dumps(
        {
            "decision_impact": 4,
            "discriminating_power": 4,
            "time_sensitivity": 1,
            "feasibility": 2,
        }
    )
    with pytest.raises(ValueError, match="not a framework gap"):
        execute_framework_command(
            tuple(
                (
                    "require attack 19.2 T1003 | OS Credential Dumping | "
                    f"Collect more evidence. | {factors}"
                ).split()
            ),
            manager,
        )
