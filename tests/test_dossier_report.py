"""Tests for M-7 sub-slice 1: Dossier-style investigation report.

Stage A acceptance tests per plan §4:
- generate_dossier_report() produces correct Markdown sections
- Dossier slot grid, predictions, analyst notes, IOC table present
- Style switch: dossier vs classic
- _execute_generate_dossier_report dispatcher
- _invoke_classic shim wrapper

Production sequence tested:
  workspace create -> store SCOs -> save_dossier_state -> save_predictions_log ->
  add_note -> generate_dossier_report() -> assert sections present
  This is the realistic analyst workflow post-investigation-loop.

@decision DEC-TEST-M7-REPORT-001
@title dossier report tests verify all 7 sections and style dispatch
@status accepted
@rationale generate_dossier_report() is the new default report renderer.
           Tests must cover: correct Markdown structure, slot grid accuracy,
           predictions block (validated/pending/falsified), analyst notes,
           IOC table, style switch to classic, and _execute dispatcher routing.
"""

from __future__ import annotations

import re
from pathlib import Path

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
# _invoke_classic shim wrapper
# ---------------------------------------------------------------------------


class TestInvokeClassic:
    """_invoke_classic() delegates to v1 ReportGenerator."""

    def test_returns_classic_report(self, wm):
        """_invoke_classic returns a string containing classic report header."""
        from adversary_pursuit.core.dossier_report import _invoke_classic

        result = _invoke_classic(wm)
        assert isinstance(result, str)
        assert "# Investigation Report" in result

    def test_classic_has_interview_notes(self, wm):
        """Classic report includes Interview Notes section."""
        from adversary_pursuit.core.dossier_report import _invoke_classic

        result = _invoke_classic(wm)
        assert "## Interview Notes" in result


# ---------------------------------------------------------------------------
# _execute_generate_dossier_report dispatcher
# ---------------------------------------------------------------------------


class TestExecuteGenerateDossierReport:
    """_execute_generate_dossier_report routes style correctly."""

    def test_dossier_style_returns_dossier_report(self, populated_wm):
        """style='dossier' returns dossier-format Markdown."""
        from adversary_pursuit.agent.tools import ToolContext, _execute_generate_dossier_report

        ctx = ToolContext(workspace_dir=populated_wm._workspace_dir)
        ctx.workspace_mgr = populated_wm
        result = _execute_generate_dossier_report(ctx, style="dossier")
        assert "## Dossier State" in result

    def test_classic_style_routes_to_classic_path(self, populated_wm):
        """style='classic' routes to the v1 interview path (not dossier renderer)."""
        from adversary_pursuit.agent.tools import ToolContext, _execute_generate_dossier_report

        ctx = ToolContext(workspace_dir=populated_wm._workspace_dir)
        ctx.workspace_mgr = populated_wm

        # Prime the classic path: start interview and answer all 5 questions
        from adversary_pursuit.core.report import ReportGenerator

        gen = ReportGenerator(populated_wm)
        for i, ans in enumerate(
            ["tip", "WHOIS", "infrastructure reuse", "null-route C2", "pivot ASN"]
        ):
            gen.set_answer(i, ans)
        ctx.report_generator = gen

        result = _execute_generate_dossier_report(ctx, style="classic")
        # Classic path produces the v1 interview-based Markdown
        assert "## Interview Notes" in result
        # Classic path does NOT produce dossier slot sections
        assert "## Dossier State" not in result

    def test_default_style_is_dossier(self, populated_wm):
        """No style argument defaults to dossier."""
        from adversary_pursuit.agent.tools import ToolContext, _execute_generate_dossier_report

        ctx = ToolContext(workspace_dir=populated_wm._workspace_dir)
        ctx.workspace_mgr = populated_wm
        result = _execute_generate_dossier_report(ctx)
        assert "## Dossier State" in result


# ---------------------------------------------------------------------------
# Classic style regression test
# ---------------------------------------------------------------------------


class TestClassicStyleRegression:
    """Classic report output is stable against fixture.

    Fixture at tests/fixtures/v1_classic_report.md was generated from a
    workspace with these settings:
      - workspace name: 'fixture-workspace'
      - 2 SCOs: ipv4-addr 1.2.3.4, domain-name evil.example.com
      - 1 module run: osint/whois_lookup on evil.example.com
      - score: 300 pts (100 + 200)
      - 5 interview answers set

    To regenerate the fixture, run the helper function at the bottom of
    this module with a fresh workspace matching those settings.
    """

    def _build_fixture_workspace(self, tmp_path) -> WorkspaceManager:
        """Build the exact workspace shape that generated v1_classic_report.md."""
        wm = WorkspaceManager(workspace_dir=tmp_path / "workspaces")
        wm.create("fixture-workspace")
        wm.switch("fixture-workspace")
        wm.store_stix_objects(
            [
                {"type": "ipv4-addr", "value": "1.2.3.4"},
                {"type": "domain-name", "value": "evil.example.com"},
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
        return wm

    def test_classic_report_matches_fixture_structure(self, tmp_path):
        """Classic report contains all expected structural elements of the fixture."""
        from adversary_pursuit.core.report import ReportGenerator

        wm = self._build_fixture_workspace(tmp_path)
        rg = ReportGenerator(wm)
        rg.set_answer(0, "Threat intel tip from partner")
        rg.set_answer(1, "WHOIS lookup on suspicious domain")
        rg.set_answer(2, "Infrastructure reuse across campaigns")
        rg.set_answer(3, "Sinkhole the C2 domain")
        rg.set_answer(4, "Pivot to related ASN block")

        result = rg.generate()
        # Redact dynamic timestamp
        result_redacted = re.sub(r"\*\*Date:\*\* .+", "**Date:** {DYNAMIC_DATE}", result)
        result_redacted = re.sub(
            r"- `[^`]+` — \*\*osint/whois_lookup\*\*",
            "- `{DYNAMIC_TIMESTAMP}` — **osint/whois_lookup**",
            result_redacted,
        )

        # Load fixture
        fixture_path = Path(__file__).parent / "fixtures" / "v1_classic_report.md"
        fixture = fixture_path.read_text(encoding="utf-8")

        # Compare line by line ignoring the dynamic lines
        result_lines = [
            line
            for line in result_redacted.splitlines()
            if "{DYNAMIC_" not in line and line.strip()
        ]
        fixture_lines = [
            line for line in fixture.splitlines() if "{DYNAMIC_" not in line and line.strip()
        ]
        assert result_lines == fixture_lines, (
            "Classic report does not match fixture structure.\n"
            f"Result lines: {result_lines}\n"
            f"Fixture lines: {fixture_lines}"
        )

    def test_classic_report_interview_answers_present(self, tmp_path):
        """Classic report includes all 5 interview answers."""
        from adversary_pursuit.core.report import ReportGenerator

        wm = self._build_fixture_workspace(tmp_path)
        rg = ReportGenerator(wm)
        rg.set_answer(0, "Threat intel tip from partner")
        rg.set_answer(1, "WHOIS lookup on suspicious domain")
        rg.set_answer(2, "Infrastructure reuse across campaigns")
        rg.set_answer(3, "Sinkhole the C2 domain")
        rg.set_answer(4, "Pivot to related ASN block")

        result = rg.generate()
        assert "Threat intel tip from partner" in result
        assert "Infrastructure reuse across campaigns" in result
        assert "Pivot to related ASN block" in result
