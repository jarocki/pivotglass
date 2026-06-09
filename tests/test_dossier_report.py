"""Tests for dossier-style investigation report (M-7 renderer, M-8 sole renderer).

Stage A acceptance tests per plan §4:
- generate_dossier_report() produces correct Markdown sections
- Dossier slot grid, predictions, analyst notes, IOC table present
- _execute_generate_dossier_report dispatcher (parameterless post-M-8)

Production sequence tested:
  workspace create -> store SCOs -> save_dossier_state -> save_predictions_log ->
  add_note -> generate_dossier_report() -> assert sections present
  This is the realistic analyst workflow post-investigation-loop.

@decision DEC-TEST-M7-REPORT-001
@title dossier report tests verify all 7 sections and dispatcher routing
@status accepted
@rationale generate_dossier_report() is the sole report renderer (M-8 cleanup).
           Tests cover: correct Markdown structure, slot grid accuracy,
           predictions block (validated/pending/falsified), analyst notes,
           IOC table, and _execute dispatcher routing (parameterless).
           Classic-path tests deleted at M-8 (DEC-68-DOSSIER-REFRAME-008 closeout).
"""

from __future__ import annotations

import pytest

from adversary_pursuit.core.workspace import WorkspaceManager

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def wm(tmp_path):
    """WorkspaceManager with a populated 'test' workspace."""
    wm = WorkspaceManager(workspace_dir=tmp_path / "workspaces")
    wm.create("test")
    wm.switch("test")
    return wm


@pytest.fixture
def populated_wm(wm):
    """WorkspaceManager with STIX objects, dossier state, predictions, and notes."""
    from adversary_pursuit.dossier.predictions import (
        create_prediction,
        save_predictions_log,
    )
    from adversary_pursuit.dossier.slot_inference import infer_dossier_state_full
    from adversary_pursuit.dossier.state import (
        save_dossier_state,
    )

    # Store some STIX SCOs
    wm.store_stix_objects(
        [
            {"type": "email-addr", "value": "attacker@evil.com"},  # Identity
            {"type": "url", "value": "https://evil.com/c2"},  # TTPs
            {"type": "ipv4-addr", "value": "1.2.3.4"},  # Infrastructure
            {"type": "domain-name", "value": "evil.example.com"},  # Infrastructure
            {"type": "ipv4-addr", "value": "5.6.7.8"},  # Infrastructure
        ],
        module_name="osint/whois_lookup",
        target="evil.example.com",
    )
    wm.store_score_events(
        [
            {"action": "new_ip", "points": 100, "indicator": "1.2.3.4"},
            {"action": "new_domain", "points": 200, "indicator": "evil.example.com"},
        ]
    )

    # Save dossier state with specific slots
    scos = wm.get_stix_objects()
    runs = wm.get_module_runs()
    dossier = infer_dossier_state_full(scos, module_runs=runs, notes=[])
    save_dossier_state(wm, dossier)

    # Create predictions
    pred1 = create_prediction(
        "infrastructure",
        "Actor will reuse .ru TLD infrastructure",
        {"sco_type": "domain-name", "value_regex": r".*\.ru$"},
    )
    pred2 = create_prediction(
        "identity",
        "Actor uses targeted spearphishing",
        {"sco_type": "email-addr"},
    )
    # Mark pred1 as validated
    from dataclasses import replace as _dc_replace

    pred1_validated = _dc_replace(pred1, status="validated", validated_at="2026-06-08T10:00:00")
    save_predictions_log(wm, [pred1_validated, pred2])

    # Add analyst notes via WorkspaceManager.add_note
    wm.add_note("Suspected APT group based on TTP overlap with known campaign")
    wm.add_note("Infrastructure shows clear Bulletproof Hosting pattern")

    return wm


# ---------------------------------------------------------------------------
# Unit tests for generate_dossier_report
# ---------------------------------------------------------------------------


class TestGenerateDossierReport:
    """generate_dossier_report() produces correct Markdown sections."""

    def test_returns_string(self, populated_wm):
        """generate_dossier_report returns a non-empty string."""
        from adversary_pursuit.core.dossier_report import generate_dossier_report

        result = generate_dossier_report(populated_wm)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_has_header(self, populated_wm):
        """Report contains Threat Actor Dossier Report header."""
        from adversary_pursuit.core.dossier_report import generate_dossier_report

        result = generate_dossier_report(populated_wm)
        assert "# Threat Actor Dossier Report" in result

    def test_has_dossier_state_section(self, populated_wm):
        """Report contains Dossier State section header."""
        from adversary_pursuit.core.dossier_report import generate_dossier_report

        result = generate_dossier_report(populated_wm)
        assert "## Dossier State" in result

    def test_dossier_slot_grid_present(self, populated_wm):
        """Dossier slot grid contains all 9 slot names."""
        from adversary_pursuit.core.dossier_report import generate_dossier_report

        result = generate_dossier_report(populated_wm)
        for slot_name in [
            "Identity",
            "Ttps",
            "Infrastructure",
            "Timing",
            "Targeting",
            "Capability",
            "Motivation",
            "Predictions",
            "Denial",
        ]:
            assert slot_name in result, f"Slot '{slot_name}' not found in report"

    def test_has_predictions_section(self, populated_wm):
        """Report contains Predictions section header."""
        from adversary_pursuit.core.dossier_report import generate_dossier_report

        result = generate_dossier_report(populated_wm)
        assert "## Predictions" in result

    def test_predictions_content(self, populated_wm):
        """Report shows validated and pending predictions."""
        from adversary_pursuit.core.dossier_report import generate_dossier_report

        result = generate_dossier_report(populated_wm)
        assert "Actor will reuse .ru TLD infrastructure" in result
        assert "Actor uses targeted spearphishing" in result

    def test_predictions_shows_validated(self, populated_wm):
        """Report shows Validated Predictions subsection."""
        from adversary_pursuit.core.dossier_report import generate_dossier_report

        result = generate_dossier_report(populated_wm)
        assert "Validated" in result

    def test_has_analyst_notes_section(self, populated_wm):
        """Report contains Analyst Notes section header."""
        from adversary_pursuit.core.dossier_report import generate_dossier_report

        result = generate_dossier_report(populated_wm)
        assert "## Analyst Notes" in result

    def test_analyst_notes_content(self, populated_wm):
        """Report contains both analyst notes."""
        from adversary_pursuit.core.dossier_report import generate_dossier_report

        result = generate_dossier_report(populated_wm)
        assert "Suspected APT group" in result
        assert "Bulletproof Hosting" in result

    def test_has_ioc_table(self, populated_wm):
        """Report contains Indicators of Compromise section."""
        from adversary_pursuit.core.dossier_report import generate_dossier_report

        result = generate_dossier_report(populated_wm)
        assert "## Indicators of Compromise" in result
        assert "ipv4-addr" in result
        assert "domain-name" in result

    def test_has_overview_metadata(self, populated_wm):
        """Report contains workspace name and score in overview."""
        from adversary_pursuit.core.dossier_report import generate_dossier_report

        result = generate_dossier_report(populated_wm)
        assert "test" in result  # workspace name
        assert "300" in result  # total score

    def test_has_statistics_section(self, populated_wm):
        """Report contains Statistics section."""
        from adversary_pursuit.core.dossier_report import generate_dossier_report

        result = generate_dossier_report(populated_wm)
        assert "## Statistics" in result

    def test_empty_workspace_graceful(self, wm):
        """generate_dossier_report handles fresh workspace without error."""
        from adversary_pursuit.core.dossier_report import generate_dossier_report

        result = generate_dossier_report(wm)
        assert isinstance(result, str)
        assert "## Dossier State" in result


# ---------------------------------------------------------------------------
# _execute_generate_dossier_report dispatcher (M-8: parameterless)
# ---------------------------------------------------------------------------


class TestExecuteGenerateDossierReport:
    """_execute_generate_dossier_report renders dossier report (sole renderer post-M-8)."""

    def test_returns_dossier_report(self, populated_wm):
        """Returns dossier-format Markdown."""
        from adversary_pursuit.agent.tools import ToolContext, _execute_generate_dossier_report

        ctx = ToolContext(workspace_dir=populated_wm._workspace_dir)
        ctx.workspace_mgr = populated_wm
        result = _execute_generate_dossier_report(ctx)
        assert "## Dossier State" in result

    def test_returns_string(self, populated_wm):
        """Returns a non-empty string."""
        from adversary_pursuit.agent.tools import ToolContext, _execute_generate_dossier_report

        ctx = ToolContext(workspace_dir=populated_wm._workspace_dir)
        ctx.workspace_mgr = populated_wm
        result = _execute_generate_dossier_report(ctx)
        assert isinstance(result, str)
        assert len(result) > 0
