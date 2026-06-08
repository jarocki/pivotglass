"""Tests for get_dossier_state LLM tool — DEC-M2-DOSSIER-005.

# @mock-exempt: the panel.render isolation test patches panel.render to verify
# it is NOT called from the LLM tool path (F64 invariant test, not a unit mock).
# All other tests use real ToolContext, real workspace I/O, and real inference.

Verifies:
- Tool returns a typed dict (no Rich markup, no panel.render() invocation)
- Summary field is JSON-serialisable
- All 9 slot keys are present
- FILLED/PARTIAL/EMPTY/DEFERRED statuses are plain strings
- get_dossier_state is registered in create_tools()
- execute_tool dispatch routes correctly and returns typed dict JSON
- No Rich markup leakage in any field

Production sequence:
  ToolContext -> create_tools() -> execute_tool('get_dossier_state', {})
  -> _execute_get_dossier_state(ctx) -> JSON string
  The LLM receives this as a tool result and can reason over it.

@decision DEC-M2-DOSSIER-005
@title get_dossier_state returns typed JSON dict ONLY — no Rich markup
@status accepted
@rationale F64 LLM-Panel separation: the LLM must receive only structured data.
    Rich markup in a tool result would cause the LLM to narrate formatting tags.
    No panel.render() call. No _SLOT_DISPLAY_NAME lookups. No [bold]/[green] etc.
"""

from __future__ import annotations

import json
import re
from unittest.mock import patch

import pytest

from adversary_pursuit.agent.tools import ToolContext, create_tools, execute_tool
from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_ctx(tmp_path):
    """ToolContext with temp dirs and a seeded default workspace."""
    config_dir = tmp_path / "config"
    workspace_dir = tmp_path / "workspaces"
    config_dir.mkdir()
    workspace_dir.mkdir()
    ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
    ctx.workspace_mgr.create("default")
    ctx.workspace_mgr.switch("default")
    return ctx


@pytest.fixture
def ctx_with_scos(tmp_path):
    """ToolContext with some SCOs stored in the workspace."""
    config_dir = tmp_path / "config"
    workspace_dir = tmp_path / "workspaces"
    config_dir.mkdir()
    workspace_dir.mkdir()
    ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
    ctx.workspace_mgr.create("default")
    ctx.workspace_mgr.switch("default")
    # Store some SCOs to ensure at least one slot is non-empty
    scos = [
        {
            "type": "email-addr",
            "value": "threat@actor.ru",
            "id": "email-addr--ca718fdb-1d62-417e-8b40-78acdf9b546d",
        },
        {
            "type": "domain-name",
            "value": "evil.example.com",
            "id": "domain-name--0dc5ba27-3565-4a23-a50c-c780ae670a20",
        },
        {
            "type": "ipv4-addr",
            "value": "1.2.3.4",
            "id": "ipv4-addr--aeb51e3d-a811-4d44-a8d7-f9e93e31b048",
        },
    ]
    ctx.workspace_mgr.store_stix_objects(scos, "test/module", "test-target")
    return ctx


# ---------------------------------------------------------------------------
# Tool registration tests
# ---------------------------------------------------------------------------


class TestGetDossierStateRegistration:
    """get_dossier_state must appear in create_tools() list — F64 gate."""

    def test_get_dossier_state_in_create_tools(self, tmp_ctx):
        """create_tools() includes get_dossier_state tool definition."""
        tools = create_tools(tmp_ctx)
        names = [t["function"]["name"] for t in tools]
        assert "get_dossier_state" in names, (
            "get_dossier_state tool must be registered in create_tools(). "
            "DEC-M2-DOSSIER-005 requires this tool to be LLM-accessible."
        )

    def test_get_dossier_state_count_increased_by_one(self, tmp_ctx):
        """create_tools() has 30 tools after M-2 (get_dossier_state) + M-4 (create_dossier_prediction) + M-5 (+create_dossier_note +falsify_dossier_prediction)."""
        tools = create_tools(tmp_ctx)
        # M-1 had 26 tools; M-2 adds get_dossier_state (27); M-4 adds create_dossier_prediction (28);
        # M-5 adds create_dossier_note (29) and falsify_dossier_prediction (30)
        assert len(tools) == 30, (
            f"Expected 30 tools after M-2+M-4+M-5 additions, got {len(tools)}. "
            "If this fails, a different tool count was agreed — update this assertion."
        )

    def test_get_dossier_state_has_type_function(self, tmp_ctx):
        """get_dossier_state tool entry has type='function'."""
        tools = create_tools(tmp_ctx)
        tool = next(t for t in tools if t["function"]["name"] == "get_dossier_state")
        assert tool["type"] == "function"

    def test_get_dossier_state_has_description(self, tmp_ctx):
        """get_dossier_state description is non-empty."""
        tools = create_tools(tmp_ctx)
        tool = next(t for t in tools if t["function"]["name"] == "get_dossier_state")
        desc = tool["function"]["description"]
        assert isinstance(desc, str) and len(desc) > 20

    def test_get_dossier_state_has_no_required_parameters(self, tmp_ctx):
        """get_dossier_state takes no required parameters — self-contained workspace read."""
        tools = create_tools(tmp_ctx)
        tool = next(t for t in tools if t["function"]["name"] == "get_dossier_state")
        params = tool["function"].get("parameters", {})
        # Either 'required' is absent or empty
        required = params.get("required", [])
        assert required == [], (
            f"get_dossier_state should have no required parameters, got {required}. "
            "The tool reads workspace state autonomously."
        )


# ---------------------------------------------------------------------------
# execute_tool dispatch tests
# ---------------------------------------------------------------------------


class TestGetDossierStateDispatch:
    """execute_tool('get_dossier_state', {}) dispatches and returns a 4-tuple."""

    def test_execute_tool_returns_four_tuple(self, tmp_ctx):
        """execute_tool for get_dossier_state returns (summary, None, [], [])."""
        result = execute_tool(tmp_ctx, "get_dossier_state", {})
        assert isinstance(result, tuple) and len(result) == 4

    def test_celebration_is_none(self, tmp_ctx):
        """Dossier state tool returns celebration=None (no scoring side-effects)."""
        _, celebration, _, _ = execute_tool(tmp_ctx, "get_dossier_state", {})
        assert celebration is None

    def test_badges_is_empty_list(self, tmp_ctx):
        """Dossier state tool returns badges=[] (no badge checks)."""
        _, _, badges, _ = execute_tool(tmp_ctx, "get_dossier_state", {})
        assert badges == []

    def test_challenges_is_empty_list(self, tmp_ctx):
        """Dossier state tool returns challenges=[] (no challenge checks)."""
        _, _, _, challenges = execute_tool(tmp_ctx, "get_dossier_state", {})
        assert challenges == []

    def test_summary_is_string(self, tmp_ctx):
        """Summary returned by get_dossier_state is a string."""
        summary, _, _, _ = execute_tool(tmp_ctx, "get_dossier_state", {})
        assert isinstance(summary, str)


# ---------------------------------------------------------------------------
# Return value content tests (DEC-M2-DOSSIER-005 — typed dict only)
# ---------------------------------------------------------------------------


class TestGetDossierStateReturnContent:
    """get_dossier_state returns typed JSON dict — no Rich markup, no panel calls."""

    def test_summary_is_json_serialisable(self, tmp_ctx):
        """Summary string is valid JSON (typed dict output, not free text)."""
        summary, _, _, _ = execute_tool(tmp_ctx, "get_dossier_state", {})
        try:
            parsed = json.loads(summary)
        except json.JSONDecodeError as e:
            pytest.fail(f"get_dossier_state summary is not valid JSON: {e}\nGot: {summary[:200]}")
        assert isinstance(parsed, dict)

    def test_summary_has_slots_key(self, tmp_ctx):
        """JSON output contains a 'slots' key mapping slot names to state dicts."""
        summary, _, _, _ = execute_tool(tmp_ctx, "get_dossier_state", {})
        parsed = json.loads(summary)
        assert "slots" in parsed, f"'slots' key missing from get_dossier_state output: {parsed}"

    def test_summary_has_all_nine_slots(self, tmp_ctx):
        """'slots' dict contains all 9 DossierSlotName keys."""
        summary, _, _, _ = execute_tool(tmp_ctx, "get_dossier_state", {})
        parsed = json.loads(summary)
        slots = parsed["slots"]
        expected_slot_names = {s.value for s in DossierSlotName}
        actual_slot_names = set(slots.keys())
        assert expected_slot_names == actual_slot_names, (
            f"Slot names mismatch in get_dossier_state output.\n"
            f"Expected: {expected_slot_names}\nGot: {actual_slot_names}"
        )

    def test_each_slot_has_status_field(self, tmp_ctx):
        """Each slot dict in the output has a 'status' field."""
        summary, _, _, _ = execute_tool(tmp_ctx, "get_dossier_state", {})
        parsed = json.loads(summary)
        for slot_name, slot_data in parsed["slots"].items():
            assert "status" in slot_data, (
                f"Slot '{slot_name}' is missing 'status' field: {slot_data}"
            )

    def test_each_slot_status_is_valid_string(self, tmp_ctx):
        """Each slot status is a valid SlotStatus string value."""
        summary, _, _, _ = execute_tool(tmp_ctx, "get_dossier_state", {})
        parsed = json.loads(summary)
        valid_statuses = {s.value for s in SlotStatus}
        for slot_name, slot_data in parsed["slots"].items():
            status = slot_data["status"]
            assert status in valid_statuses, (
                f"Slot '{slot_name}' has invalid status '{status}'. Valid values: {valid_statuses}"
            )

    def test_each_slot_has_evidence_count(self, tmp_ctx):
        """Each slot dict has an 'evidence_count' integer field."""
        summary, _, _, _ = execute_tool(tmp_ctx, "get_dossier_state", {})
        parsed = json.loads(summary)
        for slot_name, slot_data in parsed["slots"].items():
            assert "evidence_count" in slot_data, (
                f"Slot '{slot_name}' missing 'evidence_count': {slot_data}"
            )
            assert isinstance(slot_data["evidence_count"], int), (
                f"Slot '{slot_name}' evidence_count must be int, "
                f"got {type(slot_data['evidence_count'])}"
            )

    def test_summary_has_total_sco_count(self, tmp_ctx):
        """JSON output contains 'total_sco_count' integer field."""
        summary, _, _, _ = execute_tool(tmp_ctx, "get_dossier_state", {})
        parsed = json.loads(summary)
        assert "total_sco_count" in parsed, (
            f"'total_sco_count' key missing from get_dossier_state output: {parsed}"
        )
        assert isinstance(parsed["total_sco_count"], int)

    def test_no_rich_markup_in_summary(self, tmp_ctx):
        """Summary contains no Rich markup tags like [bold], [green], etc. (DEC-M2-DOSSIER-005)."""
        summary, _, _, _ = execute_tool(tmp_ctx, "get_dossier_state", {})
        rich_tag_pattern = re.compile(r"\[/?[^\]]+\]")
        matches = rich_tag_pattern.findall(summary)
        assert not matches, (
            f"Rich markup found in get_dossier_state summary — F64 violation.\n"
            f"Tags found: {matches}\nFull summary: {summary[:300]}"
        )

    def test_empty_workspace_returns_all_empty_or_deferred(self, tmp_ctx):
        """Empty workspace: all slots are empty or deferred in JSON output."""
        summary, _, _, _ = execute_tool(tmp_ctx, "get_dossier_state", {})
        parsed = json.loads(summary)
        valid_empty = {"empty", "deferred"}
        for slot_name, slot_data in parsed["slots"].items():
            assert slot_data["status"] in valid_empty, (
                f"Slot '{slot_name}' has status '{slot_data['status']}' for empty workspace. "
                f"Expected empty or deferred."
            )

    def test_scos_produce_non_empty_slots(self, ctx_with_scos):
        """Workspace with SCOs yields at least one slot with status != empty."""
        summary, _, _, _ = execute_tool(ctx_with_scos, "get_dossier_state", {})
        parsed = json.loads(summary)
        non_empty = [
            name
            for name, data in parsed["slots"].items()
            if data["status"] not in ("empty", "deferred")
        ]
        assert len(non_empty) >= 1, (
            "Workspace with email-addr, domain-name, ipv4-addr SCOs should produce "
            "at least one non-empty slot (Identity, Infrastructure). "
            f"Got all slots empty/deferred: {parsed['slots']}"
        )

    def test_total_sco_count_matches_stored(self, ctx_with_scos):
        """total_sco_count in output matches actual workspace SCO count."""
        summary, _, _, _ = execute_tool(ctx_with_scos, "get_dossier_state", {})
        parsed = json.loads(summary)
        # ctx_with_scos stored 3 SCOs
        assert parsed["total_sco_count"] == 3, (
            f"total_sco_count mismatch. Expected 3, got {parsed['total_sco_count']}"
        )


# ---------------------------------------------------------------------------
# Panel isolation test (DEC-M2-DOSSIER-005: no panel.render() invocation)
# ---------------------------------------------------------------------------


class TestGetDossierStatePanelIsolation:
    """panel.render() must NOT be called from the LLM tool path (F64 invariant)."""

    def test_panel_render_not_called(self, tmp_ctx):
        """get_dossier_state does not invoke panel.render() (DEC-M2-DOSSIER-005).

        # @mock-exempt: patching panel.render to assert it is NOT invoked verifies
        # the F64 LLM/Panel separation invariant. This is a negative-invocation test,
        # not a unit mock that replaces real logic.
        """
        panel_was_called = []

        def _fail_if_called(*args, **kwargs):
            panel_was_called.append(True)
            raise AssertionError(
                "panel.render() was called from get_dossier_state — DEC-M2-DOSSIER-005 violation"
            )

        with patch("adversary_pursuit.dossier.panel.render", side_effect=_fail_if_called):
            try:
                execute_tool(tmp_ctx, "get_dossier_state", {})
            except AssertionError as e:
                pytest.fail(str(e))

        assert not panel_was_called, "panel.render should never be called from LLM tool path"


# ---------------------------------------------------------------------------
# Compound / production sequence test
# ---------------------------------------------------------------------------


class TestGetDossierStateProductionSequence:
    """End-to-end test of the real production sequence.

    Production: ToolContext -> store SCOs via workspace -> execute_tool get_dossier_state
    -> JSON string -> parse -> verify slot fill states reflect stored evidence.
    """

    def test_compound_store_scos_then_get_dossier_state(self, tmp_path):
        """Store infrastructure + identity SCOs, then call get_dossier_state and verify.

        This exercises the real production sequence: workspace has live SCOs,
        infer_dossier_state_full() reads them, returns typed dict via tool.
        No mocks for workspace I/O — this is real workspace state.

        Slot expectations:
          Infrastructure: domain-name + ipv4-addr = 2 distinct types -> FILLED
          Identity: email-addr only = 1 distinct type -> PARTIAL
          Predictions/Denial: always DEFERRED in M-2 (DEC-M2-DOSSIER-004)

        Note: dict_to_stix() (stix.py) only converts the 5 types in _SCO_CREATORS
        (ipv4-addr, ipv6-addr, domain-name, url, email-addr). x509-certificate and
        user-account are not in _SCO_CREATORS and are silently skipped by
        store_stix_objects(). This is a known stix.py scope limitation, not an
        inference bug. Infrastructure uses 4 supported types so FILLED is reachable
        from the storage path; Identity FILLED requires a stix.py expansion (M-3+).
        """
        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")

        # Store infrastructure evidence: domain-name + ipv4-addr = 2 distinct types -> FILLED
        infra_scos = [
            {
                "type": "domain-name",
                "value": "evil.example.com",
                "id": "domain-name--0dc5ba27-3565-4a23-a50c-c780ae670a20",
            },
            {
                "type": "ipv4-addr",
                "value": "1.2.3.4",
                "id": "ipv4-addr--aeb51e3d-a811-4d44-a8d7-f9e93e31b048",
            },
        ]
        ctx.workspace_mgr.store_stix_objects(infra_scos, "osint/dns_resolve", "evil.example.com")

        # Store identity evidence: email-addr only = 1 distinct type -> PARTIAL
        identity_scos = [
            {
                "type": "email-addr",
                "value": "threat@actor.ru",
                "id": "email-addr--ca718fdb-1d62-417e-8b40-78acdf9b546d",
            },
        ]
        ctx.workspace_mgr.store_stix_objects(identity_scos, "osint/hibp", "threat@actor.ru")

        summary, celebration, badges, challenges = execute_tool(ctx, "get_dossier_state", {})

        # Validate tuple structure
        assert celebration is None
        assert badges == []
        assert challenges == []

        # Parse JSON
        parsed = json.loads(summary)
        assert "slots" in parsed
        assert "total_sco_count" in parsed

        # Infrastructure should be FILLED (domain-name + ipv4-addr = 2 distinct types)
        infra = parsed["slots"]["infrastructure"]
        assert infra["status"] == "filled", (
            f"Infrastructure should be filled with 2 distinct SCO types, got: {infra}"
        )

        # Identity should be PARTIAL (email-addr only = 1 distinct type)
        identity = parsed["slots"]["identity"]
        assert identity["status"] == "partial", (
            f"Identity should be partial with 1 SCO type, got: {identity}"
        )

        # Predictions: M-4 overlay sets to "empty" (no predictions in log); no longer "deferred"
        # Denial: M-5 ships real extractor; with no DGA/fast-flux/note evidence, returns "empty"
        assert parsed["slots"]["predictions"]["status"] in ("deferred", "empty"), (
            f"Predictions slot should be deferred or empty (M-4 overlay), got: {parsed['slots']['predictions']}"
        )
        assert parsed["slots"]["denial"]["status"] in ("empty", "partial", "filled"), (
            f"Denial slot should be empty/partial/filled after M-5 (not deferred), got: {parsed['slots']['denial']}"
        )

        # total_sco_count = 3 (2 infra + 1 identity)
        assert parsed["total_sco_count"] == 3


class TestGetDossierStateM4Persistence:
    """M-4 extension: get_dossier_state reads persistent snapshot when present.

    Evaluation Contract gate: GS1 - get_dossier_state returns persisted state when present;
    falls back to fresh inference when no snapshot exists (DEC-M4-PERSIST-001).
    """

    def test_gs1_reads_persistent_snapshot_when_present(self, tmp_path):
        """GS1: get_dossier_state reads persisted state; no fresh inference needed."""
        import json

        from adversary_pursuit.agent.tools import execute_tool
        from adversary_pursuit.dossier.slot_inference import DossierState, SlotState
        from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus
        from adversary_pursuit.dossier.state import save_dossier_state

        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")

        # Persist a state with specific slot statuses — no SCOs stored
        slots = {slot: SlotState(name=slot, status=SlotStatus.EMPTY) for slot in DossierSlotName}
        slots[DossierSlotName.TTPS] = SlotState(
            name=DossierSlotName.TTPS, status=SlotStatus.FILLED, evidence_count=5
        )
        slots[DossierSlotName.CAPABILITY] = SlotState(
            name=DossierSlotName.CAPABILITY, status=SlotStatus.PARTIAL, evidence_count=2
        )
        persisted = DossierState(slots=slots, total_sco_count=10)
        save_dossier_state(ctx.workspace_mgr, persisted)

        result_text, *_ = execute_tool(ctx, "get_dossier_state", {})
        result = json.loads(result_text)

        # Persisted state must be returned (not fresh inference which would show EMPTY)
        assert result["slots"]["ttps"]["status"] == "filled"
        assert result["slots"]["ttps"]["evidence_count"] == 5
        assert result["slots"]["capability"]["status"] == "partial"

    def test_gs1_falls_back_to_fresh_inference_when_no_snapshot(self, tmp_path):
        """GS1 fallback: no snapshot => fresh inference returns all-empty/deferred."""
        import json

        from adversary_pursuit.agent.tools import execute_tool

        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")

        result_text, *_ = execute_tool(ctx, "get_dossier_state", {})
        result = json.loads(result_text)

        # No snapshot, no SCOs => all slots empty or deferred (fresh inference)
        assert "slots" in result
        for slot_name, slot_data in result["slots"].items():
            assert slot_data["status"] in ("empty", "deferred"), (
                f"Slot {slot_name} should be empty/deferred on fresh workspace; got {slot_data['status']}"
            )
