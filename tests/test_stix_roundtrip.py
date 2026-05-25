"""Tests for #59: STIX 2.1 spec compliance + per-SCO provenance.

Evaluation Contract (MASTER_PLAN.md Phase 11, lines 923+):

1. test_bundle_parses_through_stix2_parse
2. test_every_sco_has_required_spec_fields
3. test_provenance_passthrough
4. test_deterministic_id_independent_of_provenance
5. test_legacy_call_no_provenance_kwargs
6. (in test_workspace.py) test_workspace_rejects_caller_supplied_x_ap_fields
7. test_export_stix_bundle_is_spec_compliant  (in test_graph.py)
8. Full suite regression (in test_workspace.py + test_graph.py)

This file covers tests 1-5 plus compound integration tests that exercise the
full production path: store_stix_objects → export_stix_bundle → stix2.parse().

@decision DEC-59-STIX-PROVENANCE-001
@title workspace.store_stix_objects() is the sole x_ap_* authority
@status accepted
@rationale Modules MUST NOT emit x_ap_* fields. Tests assert this boundary.

@decision DEC-59-STIX-PROVENANCE-002
@title Provenance added AFTER obj.serialize() — deterministic id is stable
@status accepted
@rationale Same SCO content → same id regardless of when/where fetched.

@decision DEC-59-STIX-PROVENANCE-005
@title export_stix_bundle uses stix2.v21.Bundle — no hand-rolled dicts
@status accepted
@rationale Guarantees spec compliance and parse-ability via python-stix2.
"""

from __future__ import annotations

import json

import pytest
import stix2
import stix2.v21

from adversary_pursuit.core.graph import RelationshipGraph
from adversary_pursuit.core.workspace import WorkspaceManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FIVE_SCO_TYPES = [
    {"type": "ipv4-addr", "value": "198.51.100.1"},
    {"type": "ipv6-addr", "value": "2001:db8::1"},
    {"type": "domain-name", "value": "malware.example.com"},
    {"type": "url", "value": "https://malware.example.com/payload"},
    {"type": "email-addr", "value": "threat@actor.example"},
]

_PROVENANCE_KWARGS = {
    "source_url": "https://api.vendor.example/v2/indicators",
    "api_version": "v2",
    "response_sha256": "a" * 64,  # 64-char hex string per DEC-59-STIX-PROVENANCE-003
}


@pytest.fixture()
def workspace(tmp_path):
    """Fresh WorkspaceManager backed by a temp directory."""
    wm = WorkspaceManager(workspace_dir=tmp_path)
    wm.create("default")
    wm.switch("default")
    return wm


@pytest.fixture()
def populated_workspace(workspace):
    """Workspace with all five SCO types stored, some with full provenance."""
    # Store three SCOs with full provenance kwargs
    workspace.store_stix_objects(
        _FIVE_SCO_TYPES[:3],
        module_name="test/module",
        target="198.51.100.1",
        **_PROVENANCE_KWARGS,
    )
    # Store remaining two with no provenance kwargs (legacy degraded state)
    workspace.store_stix_objects(
        _FIVE_SCO_TYPES[3:],
        module_name="test/module",
        target="198.51.100.1",
    )
    return workspace


def _build_graph_from_workspace(wm: WorkspaceManager) -> RelationshipGraph:
    """Reproduce the production path: workspace → RelationshipGraph."""
    g = RelationshipGraph()
    objects = wm.get_stix_objects()
    g.build_from_workspace(objects)
    return g


# ---------------------------------------------------------------------------
# Test 1: bundle round-trips through stix2.parse()
# ---------------------------------------------------------------------------


class TestBundleParseThroughStix2Parse:
    """Evaluation Contract test 1: stix2.parse() returns stix2.v21.Bundle."""

    def test_bundle_parses_through_stix2_parse(self, populated_workspace):
        """stix2.parse(bundle, allow_custom=True) must return a stix2.v21.Bundle.

        This is the primary spec-compliance gate. A non-compliant bundle
        (e.g. missing spec_version on objects) raises during parse.
        """
        g = _build_graph_from_workspace(populated_workspace)
        bundle_dict = g.export_stix_bundle()

        # Must be parseable — will raise STIXError if spec-non-compliant
        parsed = stix2.parse(bundle_dict, allow_custom=True)

        assert isinstance(parsed, stix2.v21.Bundle), (
            f"Expected stix2.v21.Bundle, got {type(parsed).__name__}"
        )
        # objects count matches stored SCO count (5 SCOs, 0 relationships)
        assert len(parsed.objects) == 5

    def test_bundle_has_required_top_level_fields(self, populated_workspace):
        """Bundle dict must carry type, id, and objects per STIX 2.1 spec."""
        g = _build_graph_from_workspace(populated_workspace)
        bundle_dict = g.export_stix_bundle()

        assert bundle_dict["type"] == "bundle"
        assert bundle_dict["id"].startswith("bundle--")
        assert "objects" in bundle_dict
        assert len(bundle_dict["objects"]) == 5


# ---------------------------------------------------------------------------
# Test 2: every SCO has required spec fields
# ---------------------------------------------------------------------------


class TestEveryScoHasRequiredSpecFields:
    """Evaluation Contract test 2: id, spec_version="2.1", x_ap_fetched_at."""

    def test_every_sco_has_required_spec_fields(self, populated_workspace):
        """Every SCO in the parsed bundle must have id, spec_version, fetched_at."""
        g = _build_graph_from_workspace(populated_workspace)
        bundle_dict = g.export_stix_bundle()
        parsed = stix2.parse(bundle_dict, allow_custom=True)

        for obj in parsed.objects:
            # id must follow <type>--<uuid> format
            assert obj.id, f"Object missing id: {obj}"
            assert "--" in obj.id, f"id format wrong: {obj.id}"
            obj_type = obj.id.split("--")[0]
            assert obj.id.startswith(f"{obj_type}--"), f"id prefix mismatch: {obj.id}"

            # spec_version must be "2.1"
            assert obj.spec_version == "2.1", (
                f"spec_version wrong on {obj.id}: {obj.spec_version!r}"
            )

            # x_ap_fetched_at must be present and non-null (DEC-59-STIX-PROVENANCE-004)
            raw = bundle_dict["objects"]
            raw_obj = next((o for o in raw if o.get("id") == obj.id), None)
            assert raw_obj is not None
            assert "x_ap_fetched_at" in raw_obj, f"x_ap_fetched_at missing from {obj.id}"
            assert raw_obj["x_ap_fetched_at"] is not None, f"x_ap_fetched_at is null on {obj.id}"

    def test_sco_ids_match_expected_type_prefixes(self, populated_workspace):
        """Each SCO id prefix matches its STIX type."""
        g = _build_graph_from_workspace(populated_workspace)
        bundle_dict = g.export_stix_bundle()

        for obj in bundle_dict["objects"]:
            stix_type = obj.get("type", "")
            stix_id = obj.get("id", "")
            assert stix_id.startswith(f"{stix_type}--"), (
                f"id {stix_id!r} does not start with type {stix_type!r}"
            )


# ---------------------------------------------------------------------------
# Test 3: provenance pass-through
# ---------------------------------------------------------------------------


class TestProvenancePassthrough:
    """Evaluation Contract test 3: supplied provenance survives into bundle SCOs."""

    def test_provenance_passthrough(self, populated_workspace):
        """source_url, api_version, response_sha256 survive verbatim into bundle."""
        g = _build_graph_from_workspace(populated_workspace)
        bundle_dict = g.export_stix_bundle()

        # The first three SCOs were stored with full provenance kwargs
        first_three_values = {d["value"] for d in _FIVE_SCO_TYPES[:3]}
        provenance_objects = [
            o for o in bundle_dict["objects"] if o.get("value") in first_three_values
        ]
        assert len(provenance_objects) == 3, (
            f"Expected 3 objects with full provenance, found {len(provenance_objects)}"
        )

        for obj in provenance_objects:
            assert obj.get("x_ap_source_url") == _PROVENANCE_KWARGS["source_url"], (
                f"x_ap_source_url mismatch on {obj.get('id')}: {obj.get('x_ap_source_url')!r}"
            )
            assert obj.get("x_ap_api_version") == _PROVENANCE_KWARGS["api_version"], (
                f"x_ap_api_version mismatch on {obj.get('id')}: {obj.get('x_ap_api_version')!r}"
            )
            assert obj.get("x_ap_response_sha256") == _PROVENANCE_KWARGS["response_sha256"], (
                f"x_ap_response_sha256 mismatch on {obj.get('id')}"
            )

    def test_provenance_sha256_stored_verbatim(self, workspace):
        """response_sha256 hex string is stored exactly as supplied (DEC-59-STIX-PROVENANCE-003)."""
        sha = "b" * 64
        workspace.store_stix_objects(
            [{"type": "ipv4-addr", "value": "10.0.0.1"}],
            module_name="test/module",
            target="10.0.0.1",
            response_sha256=sha,
        )
        objects = workspace.get_stix_objects()
        assert len(objects) == 1
        assert objects[0]["x_ap_response_sha256"] == sha

    def test_fetched_at_is_rfc3339_z_suffix(self, workspace):
        """x_ap_fetched_at from workspace default must end with 'Z'."""
        workspace.store_stix_objects(
            [{"type": "domain-name", "value": "example.com"}],
            module_name="test/module",
            target="example.com",
        )
        objects = workspace.get_stix_objects()
        ts = objects[0]["x_ap_fetched_at"]
        assert isinstance(ts, str)
        assert ts.endswith("Z"), f"x_ap_fetched_at not Z-suffixed: {ts!r}"


# ---------------------------------------------------------------------------
# Test 4: deterministic id is independent of provenance
# ---------------------------------------------------------------------------


class TestDeterministicIdIndependentOfProvenance:
    """Evaluation Contract test 4: DEC-59-STIX-PROVENANCE-002 invariant."""

    def test_deterministic_id_independent_of_provenance(self, tmp_path):
        """Same SCO content stored twice at different times → same id.

        Provenance (fetched_at) differs between the two stores, but id and
        spec_version are unchanged. Deduplication (DEC-WS-004) ensures only
        one copy is stored; the test verifies it by storing in two separate
        workspaces (to bypass dedup) and comparing ids.
        """
        # Workspace A: store with explicit early timestamp
        wm_a = WorkspaceManager(workspace_dir=tmp_path / "a")
        wm_a.create("default")
        wm_a.switch("default")
        wm_a.store_stix_objects(
            [{"type": "ipv4-addr", "value": "192.0.2.1"}],
            module_name="test/mod",
            target="192.0.2.1",
            fetched_at="2024-01-01T00:00:00Z",
            source_url="https://first-fetch.example/",
        )

        # Workspace B: same content, later timestamp, different source_url
        wm_b = WorkspaceManager(workspace_dir=tmp_path / "b")
        wm_b.create("default")
        wm_b.switch("default")
        wm_b.store_stix_objects(
            [{"type": "ipv4-addr", "value": "192.0.2.1"}],
            module_name="test/mod",
            target="192.0.2.1",
            fetched_at="2025-06-01T12:00:00Z",
            source_url="https://second-fetch.example/",
        )

        obj_a = wm_a.get_stix_objects()[0]
        obj_b = wm_b.get_stix_objects()[0]

        assert obj_a["id"] == obj_b["id"], (
            f"Same SCO content produced different ids: {obj_a['id']!r} vs {obj_b['id']!r}"
        )
        assert obj_a["spec_version"] == "2.1"
        assert obj_b["spec_version"] == "2.1"

        # Provenance differs — confirming the dedup is id-stable
        assert obj_a["x_ap_fetched_at"] != obj_b["x_ap_fetched_at"]
        assert obj_a["x_ap_source_url"] != obj_b["x_ap_source_url"]

    def test_dedup_within_workspace_preserves_first_stored_provenance(self, workspace):
        """Within a single workspace, dedup keeps the first-stored SCO's provenance."""
        workspace.store_stix_objects(
            [{"type": "domain-name", "value": "dedup-test.example"}],
            module_name="test/mod",
            target="dedup-test.example",
            fetched_at="2024-01-01T00:00:00Z",
            source_url="https://first.example/",
        )
        # Store same observable again — should be deduped (DEC-WS-004)
        workspace.store_stix_objects(
            [{"type": "domain-name", "value": "dedup-test.example"}],
            module_name="test/mod2",
            target="dedup-test.example",
            fetched_at="2025-06-01T12:00:00Z",
            source_url="https://second.example/",
        )

        objects = workspace.get_stix_objects()
        assert len(objects) == 1, "Deduplication failed — same SCO stored twice"
        # The first-stored provenance is preserved
        assert objects[0]["x_ap_source_url"] == "https://first.example/"


# ---------------------------------------------------------------------------
# Test 5: legacy call sites — no provenance kwargs
# ---------------------------------------------------------------------------


class TestLegacyCallNoProvenanceKwargs:
    """Evaluation Contract test 5: legacy call sites produce valid bundles."""

    def test_legacy_call_no_provenance_kwargs(self, workspace):
        """store_stix_objects() with no provenance kwargs still works.

        x_ap_fetched_at is populated by the workspace default; the other three
        provenance fields are absent from the json_blob (null/absent per
        DEC-59-STIX-PROVENANCE-004).
        """
        workspace.store_stix_objects(
            [
                {"type": "ipv4-addr", "value": "203.0.113.1"},
                {"type": "domain-name", "value": "legacy.example.com"},
            ],
            module_name="osint/legacy",
            target="203.0.113.1",
            # No source_url, api_version, response_sha256, fetched_at
        )

        objects = workspace.get_stix_objects()
        assert len(objects) == 2

        for obj in objects:
            # x_ap_fetched_at always populated
            assert "x_ap_fetched_at" in obj
            assert obj["x_ap_fetched_at"] is not None

            # Other three absent (not in dict at all, since we only insert
            # them when non-None — see store_stix_objects provenance overlay)
            assert "x_ap_source_url" not in obj
            assert "x_ap_api_version" not in obj
            assert "x_ap_response_sha256" not in obj

    def test_legacy_call_bundle_still_parses(self, workspace):
        """Bundle from legacy call site round-trips through stix2.parse()."""
        workspace.store_stix_objects(
            [{"type": "ipv4-addr", "value": "198.51.100.2"}],
            module_name="osint/legacy",
            target="198.51.100.2",
        )

        g = _build_graph_from_workspace(workspace)
        bundle_dict = g.export_stix_bundle()

        # Must parse without error
        parsed = stix2.parse(bundle_dict, allow_custom=True)
        assert isinstance(parsed, stix2.v21.Bundle)
        assert len(parsed.objects) == 1

    def test_explicit_none_kwargs_same_as_omitted(self, workspace):
        """Passing None for all provenance kwargs is equivalent to omitting them.

        This verifies the console.py and agent/tools.py call sites (which pass
        None explicitly per DEC-59-STIX-PROVENANCE-004) behave identically to
        callers that omit the kwargs.
        """
        workspace.store_stix_objects(
            [{"type": "ipv4-addr", "value": "198.51.100.3"}],
            module_name="osint/console",
            target="198.51.100.3",
            source_url=None,
            api_version=None,
            response_sha256=None,
            fetched_at=None,
        )

        objects = workspace.get_stix_objects()
        assert len(objects) == 1
        obj = objects[0]

        # x_ap_fetched_at is always populated
        assert "x_ap_fetched_at" in obj
        assert obj["x_ap_fetched_at"] is not None

        # The three nullable fields must be absent (we don't store null-valued keys)
        assert "x_ap_source_url" not in obj
        assert "x_ap_api_version" not in obj
        assert "x_ap_response_sha256" not in obj


# ---------------------------------------------------------------------------
# Compound integration test: full production sequence end-to-end
# ---------------------------------------------------------------------------


class TestProductionSequenceEndToEnd:
    """Compound-interaction test exercising the full production sequence.

    Production path:
      module.hunt() → store_stix_objects() → get_stix_objects()
      → RelationshipGraph.build_from_workspace() → export_stix_bundle()
      → stix2.parse()

    This crosses: workspace storage layer, graph construction, bundle export,
    and spec-compliance validation — all real components, no mocks.
    """

    def test_full_production_sequence_all_five_sco_types(self, workspace):
        """Store all 5 SCO types, export bundle, parse, verify fields.

        This is the compound-interaction test required by the implementer spec.
        Exercises: storage-layer provenance augmentation, graph construction,
        stix2.v21.Bundle construction, round-trip parse, field validation.
        """
        # Simulate a module producing mixed provenance: some with full kwargs,
        # some via the legacy (null) path.
        workspace.store_stix_objects(
            [
                {"type": "ipv4-addr", "value": "198.51.100.10"},
                {"type": "ipv6-addr", "value": "2001:db8::10"},
                {"type": "domain-name", "value": "compound.example.com"},
            ],
            module_name="test/full_module",
            target="198.51.100.10",
            source_url="https://vendor.example/api/v3/ip/198.51.100.10",
            api_version="v3",
            response_sha256="c" * 64,
        )
        workspace.store_stix_objects(
            [
                {"type": "url", "value": "https://compound.example.com/c2"},
                {"type": "email-addr", "value": "c2@compound.example.com"},
            ],
            module_name="test/full_module2",
            target="compound.example.com",
            # No provenance — legacy path
        )

        # Build graph and export bundle
        g = _build_graph_from_workspace(workspace)
        assert g.node_count == 5

        bundle_dict = g.export_stix_bundle()
        assert bundle_dict["type"] == "bundle"
        assert len(bundle_dict["objects"]) == 5

        # Parse the bundle — real stix2.parse(), no mocks
        parsed = stix2.parse(bundle_dict, allow_custom=True)
        assert isinstance(parsed, stix2.v21.Bundle)
        assert len(parsed.objects) == 5

        # Every object: id format + spec_version
        for obj in parsed.objects:
            assert obj.id
            assert obj.spec_version == "2.1"

        # x_ap_fetched_at: all 5 objects must have it (4 from default, N from kwargs)
        for raw_obj in bundle_dict["objects"]:
            assert "x_ap_fetched_at" in raw_obj, f"x_ap_fetched_at missing from {raw_obj.get('id')}"
            assert raw_obj["x_ap_fetched_at"] is not None

        # Objects with full provenance have all three optional fields
        provenance_values = {"198.51.100.10", "2001:db8::10", "compound.example.com"}
        for raw_obj in bundle_dict["objects"]:
            if raw_obj.get("value") in provenance_values:
                assert (
                    raw_obj.get("x_ap_source_url")
                    == "https://vendor.example/api/v3/ip/198.51.100.10"
                )
                assert raw_obj.get("x_ap_api_version") == "v3"
                assert raw_obj.get("x_ap_response_sha256") == "c" * 64

        # Objects without full provenance lack the three optional fields
        legacy_values = {
            "https://compound.example.com/c2",
            "c2@compound.example.com",
        }
        for raw_obj in bundle_dict["objects"]:
            if raw_obj.get("value") in legacy_values:
                assert "x_ap_source_url" not in raw_obj
                assert "x_ap_api_version" not in raw_obj
                assert "x_ap_response_sha256" not in raw_obj

    def test_bundle_json_is_serializable(self, workspace):
        """export_stix_bundle() result is a plain dict serializable with json.dumps()."""
        workspace.store_stix_objects(
            [{"type": "ipv4-addr", "value": "10.1.2.3"}],
            module_name="test/mod",
            target="10.1.2.3",
        )
        g = _build_graph_from_workspace(workspace)
        bundle_dict = g.export_stix_bundle()

        # Must not raise — callers use json.dumps() to write bundle to disk
        serialized = json.dumps(bundle_dict)
        reloaded = json.loads(serialized)

        assert reloaded["type"] == "bundle"
        assert len(reloaded["objects"]) == 1
