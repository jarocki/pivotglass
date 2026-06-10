"""Tests for dossier/import_.py — STIX bundle import + ImportedDossier shape.

Covers DEC-M9-IMPORT-READONLY-001 (read-only consumer), DEC-M9-CONFLICT-001
(no workspace conflict), and loud failure contracts (Sacred Practice 5).

@decision DEC-M9-TEST-IMPORT-001
@title import_dossier test suite verifies round-trip, loud failure, read-only invariant
@status accepted
@rationale Tests verify that import_dossier produces an ImportedDossier whose
    slot_states, predictions, and analyst_notes match the source export. The
    read-only invariant is checked by asserting the workspace SQLite mtime is
    unchanged after import. Real WorkspaceManager used throughout (no internal mocks).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.dossier.export import export_dossier
from adversary_pursuit.dossier.import_ import ImportedDossier, import_dossier

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def wm(tmp_path: Path) -> WorkspaceManager:
    """Real WorkspaceManager with a fresh workspace."""
    mgr = WorkspaceManager(workspace_dir=tmp_path)
    mgr.create("default")
    mgr.switch("default")
    return mgr


@pytest.fixture()
def bundle_json_empty(wm: WorkspaceManager) -> str:
    """Export an empty workspace dossier bundle."""
    return export_dossier(wm, actor_identifier="test-actor")


@pytest.fixture()
def bundle_json_populated(tmp_path: Path) -> str:
    """Export a workspace with SCOs."""
    mgr = WorkspaceManager(workspace_dir=tmp_path)
    mgr.create("default")
    mgr.switch("default")
    mgr.store_stix_objects(
        [
            {"type": "ipv4-addr", "value": "1.2.3.4"},
            {"type": "domain-name", "value": "c2.evil.com"},
        ],
        module_name="test/module",
        target="1.2.3.4",
    )
    return export_dossier(mgr, actor_identifier="populated-actor")


# ---------------------------------------------------------------------------
# Basic shape of ImportedDossier
# ---------------------------------------------------------------------------


class TestImportDossierShape:
    """ImportedDossier is produced with expected fields."""

    def test_returns_imported_dossier_instance(self, bundle_json_empty: str):
        result = import_dossier(bundle_json_empty)
        assert isinstance(result, ImportedDossier)

    def test_actor_identifier_matches(self, bundle_json_empty: str):
        result = import_dossier(bundle_json_empty)
        assert result.actor_identifier == "test-actor"

    def test_slot_states_has_9_entries(self, bundle_json_empty: str):
        from adversary_pursuit.dossier.slots import DossierSlotName

        result = import_dossier(bundle_json_empty)
        assert len(result.slot_states) == len(list(DossierSlotName))

    def test_predictions_is_list(self, bundle_json_empty: str):
        result = import_dossier(bundle_json_empty)
        assert isinstance(result.predictions, list)

    def test_analyst_notes_is_list(self, bundle_json_empty: str):
        result = import_dossier(bundle_json_empty)
        assert isinstance(result.analyst_notes, list)

    def test_metadata_has_expected_keys(self, bundle_json_empty: str):
        result = import_dossier(bundle_json_empty)
        assert "x_ap_version" in result.metadata
        assert "x_ap_exported_at" in result.metadata
        assert "x_ap_workspace_id" in result.metadata
        assert "x_ap_actor_identifier" in result.metadata
        assert "x_ap_dossier_schema_version" in result.metadata


# ---------------------------------------------------------------------------
# Round-trip: export -> import -> verify fields
# ---------------------------------------------------------------------------


class TestImportRoundTrip:
    """export_dossier -> import_dossier produces matching data."""

    def test_actor_identifier_round_trips(self, wm: WorkspaceManager):
        bundle = export_dossier(wm, actor_identifier="apt-28")
        imported = import_dossier(bundle)
        assert imported.actor_identifier == "apt-28"

    def test_slot_states_all_present_after_import(self, wm: WorkspaceManager):
        from adversary_pursuit.dossier.slots import DossierSlotName

        bundle = export_dossier(wm)
        imported = import_dossier(bundle)
        for slot in DossierSlotName:
            assert slot in imported.slot_states

    def test_predictions_round_trip(self, tmp_path: Path):
        """Predictions stored in workspace appear in ImportedDossier after export/import."""
        from adversary_pursuit.dossier.predictions import (
            ExpectedEvidence,
            PersistedPrediction,
            save_predictions_log,
        )

        mgr = WorkspaceManager(workspace_dir=tmp_path)
        mgr.create("default")
        mgr.switch("default")

        pred = PersistedPrediction(
            prediction_id="pred-abc12345",
            text="Actor will use .ru domains",
            slot="infrastructure",
            status="pending",
            expected_evidence=ExpectedEvidence(value_regex=r"\.ru$"),
            created_at="2024-01-01T00:00:00Z",
        )
        save_predictions_log(mgr, [pred])

        bundle = export_dossier(mgr, actor_identifier="test-round-trip")
        imported = import_dossier(bundle)

        assert len(imported.predictions) == 1
        assert imported.predictions[0].prediction_id == "pred-abc12345"
        assert imported.predictions[0].text == "Actor will use .ru domains"
        assert imported.predictions[0].status == "pending"

    def test_analyst_notes_round_trip(self, tmp_path: Path):
        """Analyst notes stored in workspace appear in ImportedDossier."""
        mgr = WorkspaceManager(workspace_dir=tmp_path)
        mgr.create("default")
        mgr.switch("default")
        mgr.add_note("actor uses .ru TLDs consistently")

        bundle = export_dossier(mgr, actor_identifier="note-test")
        imported = import_dossier(bundle)

        assert len(imported.analyst_notes) == 1
        assert "actor uses .ru TLDs consistently" in imported.analyst_notes[0]


# ---------------------------------------------------------------------------
# Loud failure contract (Sacred Practice 5)
# ---------------------------------------------------------------------------


class TestImportLoudFailure:
    """import_dossier raises loudly on invalid input (Sacred Practice 5)."""

    def test_malformed_json_raises_value_error(self):
        with pytest.raises(ValueError, match="not valid JSON"):
            import_dossier("{not a bundle}")

    def test_empty_dict_missing_type_raises_value_error(self):
        with pytest.raises(ValueError, match="missing required 'type'"):
            import_dossier(json.dumps({}))

    def test_non_bundle_type_raises_value_error(self):
        with pytest.raises(ValueError, match="'bundle'"):
            import_dossier(json.dumps({"type": "indicator", "spec_version": "2.1"}))

    def test_bundle_missing_threat_actor_raises_value_error(self):
        import stix2

        # Build a bundle with only an IPv4 SCO (no threat-actor SDO)
        dummy_ipv4 = stix2.IPv4Address(value="1.2.3.4")
        bundle = stix2.v21.Bundle(objects=[dummy_ipv4], allow_custom=True)
        with pytest.raises(ValueError, match="threat-actor"):
            import_dossier(bundle.serialize())

    def test_schema_version_mismatch_raises_runtime_error(self, wm: WorkspaceManager):
        """x_ap_dossier_schema_version != 1 raises RuntimeError."""
        bundle_json = export_dossier(wm)
        bundle_dict = json.loads(bundle_json)
        # Tamper with schema version on the threat-actor SDO
        for obj in bundle_dict["objects"]:
            if obj.get("type") == "threat-actor":
                obj["x_ap_dossier_schema_version"] = 99
        with pytest.raises(RuntimeError, match="schema version"):
            import_dossier(json.dumps(bundle_dict))

    def test_bundle_missing_schema_version_raises_value_error(self, wm: WorkspaceManager):
        """Bundle with no x_ap_dossier_schema_version raises ValueError."""
        bundle_json = export_dossier(wm)
        bundle_dict = json.loads(bundle_json)
        for obj in bundle_dict["objects"]:
            if obj.get("type") == "threat-actor":
                obj.pop("x_ap_dossier_schema_version", None)
        with pytest.raises(ValueError, match="x_ap_dossier_schema_version"):
            import_dossier(json.dumps(bundle_dict))


# ---------------------------------------------------------------------------
# Read-only invariant (DEC-M9-IMPORT-READONLY-001)
# ---------------------------------------------------------------------------


class TestImportReadOnly:
    """import_dossier never mutates the workspace SQLite."""

    def test_workspace_mtime_unchanged_after_import(self, tmp_path: Path):
        """SQLite file mtime does not change when import_dossier is called."""
        mgr = WorkspaceManager(workspace_dir=tmp_path)
        mgr.create("default")
        mgr.switch("default")
        # Store one SCO to create the db file
        mgr.store_stix_objects(
            [{"type": "ipv4-addr", "value": "10.0.0.1"}],
            module_name="test/module",
            target="10.0.0.1",
        )

        # Build a bundle from a different workspace to import
        other_tmp = tmp_path / "other"
        other_tmp.mkdir()
        other_mgr = WorkspaceManager(workspace_dir=other_tmp)
        other_mgr.create("default")
        other_mgr.switch("default")
        bundle_json = export_dossier(other_mgr, actor_identifier="peer-actor")

        # Record the mtime of the db file before import
        db_path = tmp_path / "default.db"
        mtime_before = os.path.getmtime(db_path)

        # import_dossier must not write to mgr's database
        import_dossier(bundle_json)

        mtime_after = os.path.getmtime(db_path)
        assert mtime_before == mtime_after, (
            "import_dossier modified the workspace SQLite — DEC-M9-IMPORT-READONLY-001 violated"
        )
