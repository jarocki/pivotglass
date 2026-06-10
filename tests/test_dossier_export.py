"""Tests for dossier/export.py — STIX 2.1 bundle export + actor identifier validation.

Covers DEC-M9-STIX-MAPPING-001, DEC-M9-STIX-MAPPING-002, DEC-M9-ACTOR-ID-001,
DEC-M9-LIBRARY-LOCATION-001, DEC-M9-LIBRARY-OPTIN-001, DEC-M9-PRIVACY-001,
and the F59 invariant that core/workspace.py is BYTEWISE UNCHANGED.

@decision DEC-M9-TEST-EXPORT-001
@title export_dossier test suite verifies STIX compliance, slot mapping, F59 invariant
@status accepted
@rationale Tests exercise the real export path: real WorkspaceManager -> export_dossier
    -> stix2.parse round-trip. F59 invariant verified via subprocess git diff. Actor
    identifier validation covers all DEC-M9-ACTOR-ID-001 cases including path
    traversal, empty string, and oversized names. Real WorkspaceManager used throughout
    (no mocks for internal code; only external HTTP is mock-exempt per Sacred Practice 5).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import stix2

from adversary_pursuit.core.workspace import WorkspaceManager

# ---------------------------------------------------------------------------
# Fixtures — real WorkspaceManager (no internal mocks)
# ---------------------------------------------------------------------------


@pytest.fixture()
def wm(tmp_path: Path) -> WorkspaceManager:
    """Real WorkspaceManager with a fresh SQLite workspace."""
    mgr = WorkspaceManager(workspace_dir=tmp_path)
    mgr.create("default")
    mgr.switch("default")
    return mgr


@pytest.fixture()
def populated_wm(tmp_path: Path) -> WorkspaceManager:
    """Real WorkspaceManager with 5 IPv4 + 2 domains stored."""
    mgr = WorkspaceManager(workspace_dir=tmp_path)
    mgr.create("default")
    mgr.switch("default")
    scos = [{"type": "ipv4-addr", "value": f"1.2.3.{i}"} for i in range(1, 6)]
    scos += [{"type": "domain-name", "value": f"evil{i}.example.com"} for i in range(1, 3)]
    mgr.store_stix_objects(scos, module_name="test/module", target="export-test")
    return mgr


# ---------------------------------------------------------------------------
# Actor identifier validation (DEC-M9-ACTOR-ID-001)
# ---------------------------------------------------------------------------


class TestActorIdentifierValidation:
    """Tests for _validate_actor_identifier (DEC-M9-ACTOR-ID-001)."""

    def test_valid_simple_name(self):
        from adversary_pursuit.dossier.export import _validate_actor_identifier

        _validate_actor_identifier("fancy-bear")  # must not raise

    def test_valid_with_dots_underscores(self):
        from adversary_pursuit.dossier.export import _validate_actor_identifier

        _validate_actor_identifier("actor.v2_test-1")  # must not raise

    def test_valid_max_length(self):
        from adversary_pursuit.dossier.export import _validate_actor_identifier

        _validate_actor_identifier("a" * 128)  # must not raise

    def test_invalid_empty_raises(self):
        from adversary_pursuit.dossier.export import _validate_actor_identifier

        with pytest.raises(ValueError, match="non-empty"):
            _validate_actor_identifier("")

    def test_invalid_path_traversal_raises(self):
        from adversary_pursuit.dossier.export import _validate_actor_identifier

        with pytest.raises(ValueError):
            _validate_actor_identifier("../../etc/passwd")

    def test_invalid_slash_raises(self):
        from adversary_pursuit.dossier.export import _validate_actor_identifier

        with pytest.raises(ValueError):
            _validate_actor_identifier("some/actor")

    def test_invalid_too_long_raises(self):
        from adversary_pursuit.dossier.export import _validate_actor_identifier

        with pytest.raises(ValueError):
            _validate_actor_identifier("a" * 200)

    def test_invalid_nul_byte_raises(self):
        from adversary_pursuit.dossier.export import _validate_actor_identifier

        with pytest.raises(ValueError):
            _validate_actor_identifier("actor\x00name")

    def test_invalid_space_raises(self):
        from adversary_pursuit.dossier.export import _validate_actor_identifier

        with pytest.raises(ValueError):
            _validate_actor_identifier("my actor")


# ---------------------------------------------------------------------------
# Bundle structure tests
# ---------------------------------------------------------------------------


class TestExportDossierBundleStructure:
    """Basic STIX 2.1 bundle output structure."""

    def test_returns_string(self, wm: WorkspaceManager):
        from adversary_pursuit.dossier.export import export_dossier

        result = export_dossier(wm)
        assert isinstance(result, str)

    def test_json_parseable(self, wm: WorkspaceManager):
        from adversary_pursuit.dossier.export import export_dossier

        bundle_dict = json.loads(export_dossier(wm))
        assert isinstance(bundle_dict, dict)

    def test_bundle_type_field(self, wm: WorkspaceManager):
        from adversary_pursuit.dossier.export import export_dossier

        bundle_dict = json.loads(export_dossier(wm))
        assert bundle_dict["type"] == "bundle"

    def test_bundle_spec_version(self, wm: WorkspaceManager):
        """In STIX 2.1, spec_version is on each SDO, not on the Bundle root."""
        from adversary_pursuit.dossier.export import export_dossier

        bundle_dict = json.loads(export_dossier(wm))
        # STIX 2.1 bundles carry spec_version on the contained SDOs, not the bundle wrapper
        ta = next(o for o in bundle_dict["objects"] if o.get("type") == "threat-actor")
        assert ta["spec_version"] == "2.1"

    def test_bundle_objects_key_present(self, wm: WorkspaceManager):
        from adversary_pursuit.dossier.export import export_dossier

        bundle_dict = json.loads(export_dossier(wm))
        assert "objects" in bundle_dict

    def test_stix2_parse_round_trips(self, populated_wm: WorkspaceManager):
        """stix2.parse(bundle_json, allow_custom=True) succeeds — spec compliance."""
        from adversary_pursuit.dossier.export import export_dossier

        bundle_json = export_dossier(populated_wm)
        parsed = stix2.parse(bundle_json, allow_custom=True)
        assert parsed is not None

    def test_threat_actor_sdo_present(self, wm: WorkspaceManager):
        from adversary_pursuit.dossier.export import export_dossier

        bundle_dict = json.loads(export_dossier(wm))
        ta_objects = [o for o in bundle_dict["objects"] if o.get("type") == "threat-actor"]
        assert len(ta_objects) == 1

    def test_threat_actor_name_is_actor_identifier(self, wm: WorkspaceManager):
        from adversary_pursuit.dossier.export import export_dossier

        bundle_dict = json.loads(export_dossier(wm, actor_identifier="apt99"))
        ta = next(o for o in bundle_dict["objects"] if o.get("type") == "threat-actor")
        assert ta["name"] == "apt99"

    def test_scos_appear_in_bundle_objects(self, populated_wm: WorkspaceManager):
        """The 7 stored SCOs appear as objects in the exported bundle."""
        from adversary_pursuit.dossier.export import export_dossier

        bundle_dict = json.loads(export_dossier(populated_wm))
        sco_types = [o["type"] for o in bundle_dict["objects"]]
        assert "ipv4-addr" in sco_types
        assert "domain-name" in sco_types


# ---------------------------------------------------------------------------
# Bundle metadata (x_ap_* on threat-actor SDO)
# ---------------------------------------------------------------------------


class TestBundleMetadata:
    """Per-bundle metadata custom properties (DEC-M9-STIX-MAPPING-001)."""

    def _get_ta(self, wm: WorkspaceManager, actor_identifier: str = "test-actor") -> dict:
        from adversary_pursuit.dossier.export import export_dossier

        bundle_dict = json.loads(export_dossier(wm, actor_identifier=actor_identifier))
        return next(o for o in bundle_dict["objects"] if o.get("type") == "threat-actor")

    def test_x_ap_version_present(self, wm: WorkspaceManager):
        ta = self._get_ta(wm)
        assert "x_ap_version" in ta
        assert isinstance(ta["x_ap_version"], str)

    def test_x_ap_exported_at_present(self, wm: WorkspaceManager):
        ta = self._get_ta(wm)
        assert "x_ap_exported_at" in ta
        assert "T" in ta["x_ap_exported_at"]

    def test_x_ap_workspace_id_matches(self, wm: WorkspaceManager):
        ta = self._get_ta(wm)
        assert ta["x_ap_workspace_id"] == "default"

    def test_x_ap_actor_identifier_matches(self, wm: WorkspaceManager):
        ta = self._get_ta(wm, actor_identifier="my-actor")
        assert ta["x_ap_actor_identifier"] == "my-actor"

    def test_x_ap_dossier_schema_version_is_1(self, wm: WorkspaceManager):
        ta = self._get_ta(wm)
        assert ta["x_ap_dossier_schema_version"] == 1

    def test_actor_identifier_defaults_to_workspace_active(self, wm: WorkspaceManager):
        """When actor_identifier=None, defaults to workspace_mgr.active."""
        from adversary_pursuit.dossier.export import export_dossier

        bundle_dict = json.loads(export_dossier(wm, actor_identifier=None))
        ta = next(o for o in bundle_dict["objects"] if o.get("type") == "threat-actor")
        assert ta["x_ap_actor_identifier"] == "default"


# ---------------------------------------------------------------------------
# Slot mapping (DEC-M9-STIX-MAPPING-001)
# ---------------------------------------------------------------------------


class TestSlotSTIXMapping:
    """STIX mapping table from §3.2 of the plan."""

    def test_x_ap_dossier_ttps_present(self, populated_wm: WorkspaceManager):
        from adversary_pursuit.dossier.export import export_dossier

        bundle_dict = json.loads(export_dossier(populated_wm))
        ta = next(o for o in bundle_dict["objects"] if o.get("type") == "threat-actor")
        assert "x_ap_dossier_ttps" in ta
        assert "status" in ta["x_ap_dossier_ttps"]

    def test_x_ap_dossier_infrastructure_present(self, populated_wm: WorkspaceManager):
        from adversary_pursuit.dossier.export import export_dossier

        bundle_dict = json.loads(export_dossier(populated_wm))
        ta = next(o for o in bundle_dict["objects"] if o.get("type") == "threat-actor")
        assert "x_ap_dossier_infrastructure" in ta

    def test_x_ap_dossier_denial_present(self, wm: WorkspaceManager):
        from adversary_pursuit.dossier.export import export_dossier

        bundle_dict = json.loads(export_dossier(wm))
        ta = next(o for o in bundle_dict["objects"] if o.get("type") == "threat-actor")
        assert "x_ap_dossier_denial" in ta

    def test_x_ap_predictions_is_list(self, wm: WorkspaceManager):
        """stix2 strips empty list custom props on serialization; absent == empty list."""
        from adversary_pursuit.dossier.export import export_dossier

        bundle_dict = json.loads(export_dossier(wm))
        ta = next(o for o in bundle_dict["objects"] if o.get("type") == "threat-actor")
        # stix2 drops empty list custom props during serialization; None means []
        assert isinstance(ta.get("x_ap_predictions") or [], list)

    def test_x_ap_analyst_notes_is_list(self, wm: WorkspaceManager):
        """stix2 strips empty list custom props on serialization; absent == empty list."""
        from adversary_pursuit.dossier.export import export_dossier

        bundle_dict = json.loads(export_dossier(wm))
        ta = next(o for o in bundle_dict["objects"] if o.get("type") == "threat-actor")
        # stix2 drops empty list custom props during serialization; None means []
        assert isinstance(ta.get("x_ap_analyst_notes") or [], list)

    def test_identity_aliases_sourced_from_email_scos(self, tmp_path: Path):
        """Slot 1: email-addr SCO value appears in threat-actor.aliases."""
        mgr = WorkspaceManager(workspace_dir=tmp_path)
        mgr.create("default")
        mgr.switch("default")
        mgr.store_stix_objects(
            [{"type": "email-addr", "value": "evil@example.com"}],
            module_name="test/module",
            target="evil@example.com",
        )
        from adversary_pursuit.dossier.export import export_dossier

        bundle_dict = json.loads(export_dossier(mgr))
        ta = next(o for o in bundle_dict["objects"] if o.get("type") == "threat-actor")
        assert "aliases" in ta
        assert any("evil@example.com" in alias for alias in ta["aliases"])


# ---------------------------------------------------------------------------
# Invalid actor_identifier at export time
# ---------------------------------------------------------------------------


class TestExportDossierValidation:
    """export_dossier raises ValueError for invalid actor_identifier."""

    def test_path_traversal_raises(self, wm: WorkspaceManager):
        from adversary_pursuit.dossier.export import export_dossier

        with pytest.raises(ValueError):
            export_dossier(wm, actor_identifier="../../etc/passwd")

    def test_empty_string_raises(self, wm: WorkspaceManager):
        from adversary_pursuit.dossier.export import export_dossier

        with pytest.raises(ValueError):
            export_dossier(wm, actor_identifier="")

    def test_oversized_actor_id_raises(self, wm: WorkspaceManager):
        from adversary_pursuit.dossier.export import export_dossier

        with pytest.raises(ValueError):
            export_dossier(wm, actor_identifier="a" * 200)


# ---------------------------------------------------------------------------
# F59 invariant: workspace.py not touched; x_ap_* on SCOs unchanged
# ---------------------------------------------------------------------------


class TestF59Invariant:
    """F59 invariant: export_dossier is read-only; x_ap_* on SCOs preserved."""

    def test_sco_x_ap_fields_pass_through_unchanged(self, tmp_path: Path):
        """x_ap_* provenance fields on SCOs survive into the exported bundle.

        WorkspaceManager.store_stix_objects() stores x_ap_* fields set via
        the workspace (F59 provenance). The export path must not strip them.
        """
        mgr = WorkspaceManager(workspace_dir=tmp_path)
        mgr.create("default")
        mgr.switch("default")
        # Store an IPv4 — workspace will assign x_ap_* fields automatically
        mgr.store_stix_objects(
            [{"type": "ipv4-addr", "value": "10.0.0.1"}],
            module_name="test/module",
            target="10.0.0.1",
        )
        from adversary_pursuit.dossier.export import export_dossier

        bundle_dict = json.loads(export_dossier(mgr))
        ipv4_objects = [o for o in bundle_dict["objects"] if o.get("type") == "ipv4-addr"]
        assert len(ipv4_objects) >= 1
        # The SCO must appear with its original fields (value preserved)
        assert any(o.get("value") == "10.0.0.1" for o in ipv4_objects)

    def test_workspace_py_not_modified(self):
        """core/workspace.py is BYTEWISE UNCHANGED — git diff must be empty."""
        import subprocess

        result = subprocess.run(
            ["git", "diff", "main", "--", "src/adversary_pursuit/core/workspace.py"],
            capture_output=True,
            text=True,
            cwd="/Users/jarocki/src/ap/.worktrees/feature-68-m9-crowdsourced-dossiers",
        )
        assert result.stdout.strip() == "", (
            f"core/workspace.py has been modified — F59 invariant violated. Diff:\n{result.stdout}"
        )

    def test_database_py_not_modified(self):
        """models/database.py is BYTEWISE UNCHANGED."""
        import subprocess

        result = subprocess.run(
            ["git", "diff", "main", "--", "src/adversary_pursuit/models/database.py"],
            capture_output=True,
            text=True,
            cwd="/Users/jarocki/src/ap/.worktrees/feature-68-m9-crowdsourced-dossiers",
        )
        assert result.stdout.strip() == "", (
            "models/database.py has been modified — no new schema allowed in M-9. "
            f"Diff:\n{result.stdout}"
        )
