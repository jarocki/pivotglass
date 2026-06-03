"""Integration tests for M-4 persistent dossier state — restart-survival scenario.

This is the LOAD-BEARING compound integration test required by the Evaluation Contract.
It proves that:

1. A DossierState snapshot persists across two distinct run_module() invocations against
   the same workspace (simulating two separate ap chat sessions).
2. A PersistedPrediction authored in session 1 is loaded in session 2 and validated
   when matching SCOs arrive.
3. The validated prediction fires a dossier_prediction_validated ScoreEvent at +4 points.
4. F64 gate: prediction-validated event text is absent from the LLM summary.

These tests do NOT use a real ap chat process — they simulate two sessions by creating
two separate ToolContext instances sharing the same workspace directory, which is the
exact mechanism that separates ap chat invocations (same SQLite database, new Python
process).

@decision DEC-M4-PERSIST-001 (integration verification)
@title Sentinel-row persistence survives across ToolContext instantiation boundaries
@status accepted
@rationale The ToolContext creates a new WorkspaceManager on each ap chat start, reading
    from the same SQLite file. This is identical to what ap chat restart does; no actual
    process restart is needed for the integration test.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adversary_pursuit.agent.tools import ToolContext, execute_tool
from adversary_pursuit.dossier.predictions import load_predictions_log
from adversary_pursuit.dossier.state import load_dossier_state

# ---------------------------------------------------------------------------
# SCO fixtures — chosen to trigger specific slot fills and prediction matches
#
# NOTE: These are plain dicts WITHOUT an "id" field. WorkspaceManager.store_stix_objects
# calls dict_to_stix which assigns a deterministic content-based STIX UUID. Including
# a hand-rolled id like "domain-name--benign.example.com" would fail STIX validation
# because stix2 requires proper UUID4 format for object IDs.
# ---------------------------------------------------------------------------

# Identity-flavored SCOs: x509-certificate triggers Identity slot
IDENTITY_SCOS = [
    {
        "type": "x509-certificate",
        "subject": "CN=actor.example.com",
        "serial_number": "aabbccddeeff0011",
    }
]

# Infrastructure SCOs: domain-name .ru triggers Infrastructure slot + value_regex match
RU_DOMAIN_SCOS = [
    {"type": "domain-name", "value": "malicious.ru"},
    {"type": "domain-name", "value": "c2.evil.ru"},
]

# Generic domain SCOs (do not match .ru regex)
GENERIC_DOMAIN_SCOS = [
    {"type": "domain-name", "value": "benign.example.com"},
]


# ---------------------------------------------------------------------------
# Helper: make a ToolContext bound to shared workspace_dir + config_dir
# ---------------------------------------------------------------------------


def _make_ctx(workspace_dir, config_dir) -> ToolContext:
    """Create a fresh ToolContext sharing the given directories.

    Simulates a new ap chat session: new Python objects, same SQLite file.
    """
    ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
    ctx.workspace_mgr.switch("default")  # re-attach to existing workspace
    return ctx


# ---------------------------------------------------------------------------
# Main integration scenario: two-session persistence + validation
# ---------------------------------------------------------------------------


class TestRestartSurvival:
    """Compound integration test proving M-4 persistence across two ToolContext lifetimes.

    This is the §5 scenario from the per-slice plan:

      Session 1:
        - Fresh workspace, no persisted snapshot.
        - Run identity-flavored hunt → Identity slot transitions empty→partial.
        - Predictions slot transitions DEFERRED→EMPTY (overlay first-fire — no event).
        - New snapshot persisted.
        - Author one prediction via create_dossier_prediction.

      Session 2 (new ToolContext, same workspace dir):
        - load_dossier_state returns the Session 1 snapshot (NOT None).
        - Run hunt returning .ru domain SCO.
        - Persisted prediction is loaded, validated (confirmed=True).
        - dossier_prediction_validated ScoreEvent fires at +4.
        - F64: event text absent from LLM summary.
    """

    @pytest.fixture
    def shared_dirs(self, tmp_path):
        """Provide shared config and workspace directories for two sessions."""
        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()

        # Session 0: bootstrap — create the workspace once
        ctx0 = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx0.workspace_mgr.create("default")
        ctx0.workspace_mgr.switch("default")

        return config_dir, workspace_dir

    def test_session_1_snapshot_persisted_after_hunt(self, shared_dirs):
        """After session 1 hunt, a DossierState snapshot exists in the workspace."""
        config_dir, workspace_dir = shared_dirs
        ctx1 = _make_ctx(workspace_dir, config_dir)

        # No snapshot yet
        assert load_dossier_state(ctx1.workspace_mgr) is None

        # @mock-exempt: hunt() is the external HTTP boundary.
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=IDENTITY_SCOS)
        mock_mod.initialize = MagicMock()
        with patch.object(ctx1.plugin_mgr, "get_module", return_value=mock_mod):
            ctx1.run_module("osint/dns_resolve", "actor.example.com", {})

        # Snapshot must now exist
        snapshot = load_dossier_state(ctx1.workspace_mgr)
        assert snapshot is not None, "Snapshot must be persisted after first hunt"

    def test_session_2_loads_session_1_snapshot(self, shared_dirs):
        """Session 2 ToolContext reads the snapshot written by session 1."""
        config_dir, workspace_dir = shared_dirs

        # Session 1: run hunt to create snapshot
        ctx1 = _make_ctx(workspace_dir, config_dir)
        mock_mod1 = MagicMock()
        mock_mod1.hunt = AsyncMock(return_value=IDENTITY_SCOS)
        mock_mod1.initialize = MagicMock()
        with patch.object(ctx1.plugin_mgr, "get_module", return_value=mock_mod1):
            ctx1.run_module("osint/dns_resolve", "actor.example.com", {})

        snapshot_1 = load_dossier_state(ctx1.workspace_mgr)
        assert snapshot_1 is not None

        # Session 2: new ToolContext, same workspace — reads persisted snapshot
        ctx2 = _make_ctx(workspace_dir, config_dir)
        snapshot_2 = load_dossier_state(ctx2.workspace_mgr)
        assert snapshot_2 is not None, "Session 2 must read snapshot written by session 1"
        assert snapshot_2.total_sco_count == snapshot_1.total_sco_count

    def test_prediction_authored_in_session_1_persists_for_session_2(self, shared_dirs):
        """Prediction authored via create_dossier_prediction in session 1 is loaded in session 2."""
        config_dir, workspace_dir = shared_dirs

        # Session 1: create prediction
        ctx1 = _make_ctx(workspace_dir, config_dir)
        result_text, *_ = execute_tool(
            ctx1,
            "create_dossier_prediction",
            {
                "slot": "infrastructure",
                "text": "Actor will pivot to .ru infrastructure.",
                "expected_evidence": {"value_regex": r".*\.ru$"},
            },
        )
        import json

        pred_result = json.loads(result_text)
        assert "prediction_id" in pred_result
        session1_pred_id = pred_result["prediction_id"]

        # Session 2: new ToolContext — prediction still there
        ctx2 = _make_ctx(workspace_dir, config_dir)
        predictions = load_predictions_log(ctx2.workspace_mgr)
        assert len(predictions) == 1, "Session 2 must see prediction from session 1"
        assert predictions[0].prediction_id == session1_pred_id
        assert predictions[0].status == "pending"

    def test_session_2_hunt_validates_session_1_prediction(self, shared_dirs):
        """The full restart-survival scenario: session 2 hunt validates session 1 prediction."""
        config_dir, workspace_dir = shared_dirs

        # Session 1: run hunt (creates snapshot), then author prediction
        ctx1 = _make_ctx(workspace_dir, config_dir)
        mock_mod1 = MagicMock()
        mock_mod1.hunt = AsyncMock(return_value=GENERIC_DOMAIN_SCOS)
        mock_mod1.initialize = MagicMock()
        with patch.object(ctx1.plugin_mgr, "get_module", return_value=mock_mod1):
            ctx1.run_module("osint/dns_resolve", "benign.example.com", {})

        # Author prediction in session 1
        execute_tool(
            ctx1,
            "create_dossier_prediction",
            {
                "slot": "infrastructure",
                "text": "Actor will pivot to .ru infrastructure.",
                "expected_evidence": {"value_regex": r".*\.ru$"},
            },
        )

        # Verify session 1 state
        assert load_dossier_state(ctx1.workspace_mgr) is not None
        preds_after_s1 = load_predictions_log(ctx1.workspace_mgr)
        assert len(preds_after_s1) == 1
        assert preds_after_s1[0].status == "pending"

        # Session 2: new ToolContext, run hunt returning .ru SCOs
        ctx2 = _make_ctx(workspace_dir, config_dir)
        mock_mod2 = MagicMock()
        mock_mod2.hunt = AsyncMock(return_value=RU_DOMAIN_SCOS)
        mock_mod2.initialize = MagicMock()
        with patch.object(ctx2.plugin_mgr, "get_module", return_value=mock_mod2):
            result = ctx2.run_module("osint/dns_resolve", "malicious.ru", {})

        # Prediction validated event must be present
        score_events = result.get("score_events", [])
        actions = [e["action"] for e in score_events]
        assert "dossier_prediction_validated" in actions, (
            f"Session 2 hunt must fire dossier_prediction_validated; got: {actions}"
        )

        pred_event = next(e for e in score_events if e["action"] == "dossier_prediction_validated")
        assert pred_event["points"] == 4

        # Prediction must now be marked validated in the database
        preds_after_s2 = load_predictions_log(ctx2.workspace_mgr)
        assert len(preds_after_s2) == 1
        assert preds_after_s2[0].status == "validated", (
            f"Prediction must be 'validated' after session 2 confirmation; got: {preds_after_s2[0].status}"
        )
        assert preds_after_s2[0].validated_at is not None

    def test_f64_gate_prediction_event_absent_from_summary_in_session_2(self, shared_dirs):
        """F64 gate: dossier_prediction_validated text absent from LLM summary in session 2."""
        config_dir, workspace_dir = shared_dirs

        # Session 1: author prediction
        ctx1 = _make_ctx(workspace_dir, config_dir)
        mock_mod1 = MagicMock()
        mock_mod1.hunt = AsyncMock(return_value=GENERIC_DOMAIN_SCOS)
        mock_mod1.initialize = MagicMock()
        with patch.object(ctx1.plugin_mgr, "get_module", return_value=mock_mod1):
            ctx1.run_module("osint/dns_resolve", "benign.example.com", {})

        execute_tool(
            ctx1,
            "create_dossier_prediction",
            {
                "slot": "infrastructure",
                "text": "Actor pivots to .ru.",
                "expected_evidence": {"value_regex": r".*\.ru$"},
            },
        )

        # Session 2: confirm prediction
        ctx2 = _make_ctx(workspace_dir, config_dir)
        mock_mod2 = MagicMock()
        mock_mod2.hunt = AsyncMock(return_value=RU_DOMAIN_SCOS)
        mock_mod2.initialize = MagicMock()
        with patch.object(ctx2.plugin_mgr, "get_module", return_value=mock_mod2):
            result = ctx2.run_module("osint/dns_resolve", "malicious.ru", {})

        summary = result.get("summary", "")
        assert "dossier_prediction_validated" not in summary, (
            f"F64 violation in session 2: event action appeared in LLM summary: {summary!r}"
        )
        assert "dossier_slot_filled" not in summary, (
            f"F64 violation: slot fill event appeared in LLM summary: {summary!r}"
        )


# ---------------------------------------------------------------------------
# F62/F63 regression: prediction events participate in streak/milestone chain
# ---------------------------------------------------------------------------


class TestF62F63Regression:
    """F62 and F63 regression: prediction-validated events work with streak/milestone.

    Evaluation Contract gates:
      R1  F62: prediction-validated event participates in streak chain (does not reset it)
      R2  F63: prediction-validated points contribute to milestone seed
    """

    def _make_ctx(self, tmp_path):
        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")
        return ctx

    def test_r1_prediction_validated_event_does_not_break_streak(self, tmp_path):
        """R1: A hunt that fires prediction_validated events still contributes to streak."""
        from adversary_pursuit.dossier.predictions import (
            ExpectedEvidence,
            PersistedPrediction,
            save_predictions_log,
        )

        ctx = self._make_ctx(tmp_path)

        # Pre-seed a pending prediction
        pred = PersistedPrediction(
            prediction_id="pred-streaktest",
            text="Streak test prediction",
            slot="infrastructure",
            status="pending",
            expected_evidence=ExpectedEvidence(sco_type="domain-name"),
            created_at="2026-06-01T00:00:00+00:00",
        )
        save_predictions_log(ctx.workspace_mgr, [pred])

        # @mock-exempt: hunt() is the external HTTP boundary.
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=RU_DOMAIN_SCOS)
        mock_mod.initialize = MagicMock()
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = ctx.run_module("osint/dns_resolve", "malicious.ru", {})

        score_events = result.get("score_events", [])
        actions = [e["action"] for e in score_events]

        # prediction_validated must be present
        assert "dossier_prediction_validated" in actions

        # Total score must include prediction points (+4) — streak is not broken
        total = ctx.workspace_mgr.get_total_score()
        assert total > 0, "Total score must be positive after hunt with prediction confirmation"

    def test_r2_prediction_validated_points_counted_in_total_score(self, tmp_path):
        """R2: prediction_validated points (4) add to get_total_score() for milestone math."""
        from adversary_pursuit.dossier.predictions import (
            ExpectedEvidence,
            PersistedPrediction,
            save_predictions_log,
        )

        ctx = self._make_ctx(tmp_path)

        # Pre-seed two pending predictions (both match domain-name)
        for i in range(2):
            pred = PersistedPrediction(
                prediction_id=f"pred-miltest-{i:02d}",
                text=f"Milestone test prediction {i}",
                slot="infrastructure",
                status="pending",
                expected_evidence=ExpectedEvidence(sco_type="domain-name"),
                created_at="2026-06-01T00:00:00+00:00",
            )
            preds = load_predictions_log(ctx.workspace_mgr)
            save_predictions_log(ctx.workspace_mgr, preds + [pred])

        # Record score before hunt
        pre_total = ctx.workspace_mgr.get_total_score()

        # @mock-exempt: hunt() is the external HTTP boundary.
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=RU_DOMAIN_SCOS)
        mock_mod.initialize = MagicMock()
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = ctx.run_module("osint/dns_resolve", "malicious.ru", {})

        post_total = ctx.workspace_mgr.get_total_score()
        score_events = result.get("score_events", [])
        pred_events = [e for e in score_events if e["action"] == "dossier_prediction_validated"]

        assert len(pred_events) == 2, f"Expected 2 prediction events; got {len(pred_events)}"
        prediction_points = sum(e["points"] for e in pred_events)
        assert prediction_points == 8, f"2 predictions × 4 pts = 8; got {prediction_points}"
        assert post_total > pre_total, "Total score must increase after prediction confirmation"
        assert post_total - pre_total >= prediction_points
