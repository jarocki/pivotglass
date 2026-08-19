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
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": "T1003"}
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
    manifest = execute_framework_command(
        ("manifest",), manager, attack_catalog_path=catalog_path
    )
    assert manifest["data"]["attack"]["version"] == "19.2"
    assert len(manifest["data"]["attack"]["sha256"]) == 64
    assert "does not silently download" in manifest["data"]["download_policy"]
    with pytest.raises(ValueError, match="not installed"):
        execute_framework_command(
            ("navigator",), manager, attack_catalog_path=catalog_path
        )


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
