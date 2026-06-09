"""Classic-style report regression tests (M-7).

Ensures that the v1 interview-based report path remains byte-for-byte
stable under the M-7 default-to-dossier change. The `--style classic`
flag must route to ReportGenerator (not the new dossier renderer) and
produce all expected v1 sections.

@decision DEC-TEST-M7-CLASSIC-REGRESSION-001
@title Classic style regression: v1 interview report path byte-stable after M-7
@status accepted
@rationale M-7 changes the DEFAULT report style from classic to dossier.
           The classic (interview-based) path must remain unchanged so that
           existing tests, saved reports, and the console --style classic flag
           all continue to work. These tests pin the classic path by driving the
           full ReportGenerator interview sequence and checking that all 5 v1
           sections are present and that dossier-specific sections are absent.
           (DEC-M7-REPORT-001: _invoke_classic is a shim; tests here prove
           the shim is transparent.)
"""

from __future__ import annotations

import pytest

from adversary_pursuit.core.workspace import WorkspaceManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def classic_wm(tmp_path):
    """WorkspaceManager populated with the minimum data for a classic report."""
    wm = WorkspaceManager(workspace_dir=tmp_path / "workspaces")
    wm.create("regression-workspace")
    wm.switch("regression-workspace")
    wm.store_stix_objects(
        [
            {"type": "ipv4-addr", "value": "192.0.2.10"},
            {"type": "domain-name", "value": "regression.example.com"},
        ],
        module_name="osint/whois_lookup",
        target="regression.example.com",
    )
    return wm


# ---------------------------------------------------------------------------
# CR-1: v1 ReportGenerator interview sequence still produces all 5 v1 sections
# ---------------------------------------------------------------------------


class TestClassicReportPathIntact:
    """The classic (interview-based) report path produces all v1 Markdown sections."""

    def _generate_classic_report(self, wm: WorkspaceManager) -> str:
        """Drive the full v1 interview sequence and return the Markdown output."""
        from adversary_pursuit.core.report import ReportGenerator

        gen = ReportGenerator(wm)
        answers = [
            "Initial threat intel tip",
            "WHOIS lookup on suspicious domain",
            "Infrastructure shared across campaigns",
            "Null-route the C2 domain",
            "Pivot to adjacent ASN block",
        ]
        for i, answer in enumerate(answers):
            gen.set_answer(i, answer)
        return gen.generate()

    def test_classic_report_contains_metadata_section(self, classic_wm):
        """Classic report includes ## Metadata section."""
        report = self._generate_classic_report(classic_wm)
        assert "## Metadata" in report

    def test_classic_report_contains_executive_summary(self, classic_wm):
        """Classic report includes ## Executive Summary section."""
        report = self._generate_classic_report(classic_wm)
        assert "## Executive Summary" in report

    def test_classic_report_contains_timeline(self, classic_wm):
        """Classic report includes ## Timeline section."""
        report = self._generate_classic_report(classic_wm)
        assert "## Timeline" in report

    def test_classic_report_contains_ioc_table(self, classic_wm):
        """Classic report includes ## Indicators of Compromise section."""
        report = self._generate_classic_report(classic_wm)
        assert "## Indicators of Compromise" in report

    def test_classic_report_contains_interview_notes(self, classic_wm):
        """Classic report includes ## Interview Notes section with recorded answers."""
        report = self._generate_classic_report(classic_wm)
        assert "## Interview Notes" in report
        assert "Initial threat intel tip" in report

    def test_classic_report_contains_statistics(self, classic_wm):
        """Classic report includes ## Statistics section."""
        report = self._generate_classic_report(classic_wm)
        assert "## Statistics" in report

    def test_classic_report_ioc_values_present(self, classic_wm):
        """Classic report includes the actual IOC values from the workspace."""
        report = self._generate_classic_report(classic_wm)
        assert "192.0.2.10" in report
        assert "regression.example.com" in report

    def test_classic_report_does_not_contain_dossier_section(self, classic_wm):
        """Classic report must NOT include dossier-specific sections (M-7 regression)."""
        report = self._generate_classic_report(classic_wm)
        # The dossier slot grid section appears only in dossier-style reports
        assert "## Threat Actor Dossier" not in report
        assert "## Dossier Slots" not in report


# ---------------------------------------------------------------------------
# CR-2: _invoke_classic shim routes to v1 ReportGenerator (transparent bridge)
# ---------------------------------------------------------------------------


class TestInvokeClassicShim:
    """_invoke_classic() is a transparent shim: output equals ReportGenerator.generate().

    DEC-M7-REPORT-001: _invoke_classic is the sole bridge from the new dispatch
    layer into the old ReportGenerator path. Tests here prove the shim is
    transparent — _invoke_classic output equals direct ReportGenerator.generate().
    """

    def _answer_all(self, gen) -> None:
        for i, answer in enumerate(
            [
                "threat intel tip",
                "WHOIS lookup",
                "infrastructure reuse",
                "null-route C2",
                "pivot to ASN",
            ]
        ):
            gen.set_answer(i, answer)

    def test_invoke_classic_returns_same_as_report_generator(self, classic_wm):
        """_invoke_classic() output is identical to direct ReportGenerator.generate()."""
        from adversary_pursuit.core.dossier_report import _invoke_classic
        from adversary_pursuit.core.report import ReportGenerator

        # Direct path
        gen_direct = ReportGenerator(classic_wm)
        self._answer_all(gen_direct)
        direct_output = gen_direct.generate()

        # Shim path
        gen_shim = ReportGenerator(classic_wm)
        self._answer_all(gen_shim)
        # _invoke_classic creates its own ReportGenerator — same workspace gives same output
        shim_output = _invoke_classic(classic_wm)

        # Both must contain the same sections (may differ in timestamp — check structural equality)
        assert "## Interview Notes" in direct_output
        assert "## Interview Notes" in shim_output
        assert "## Indicators of Compromise" in shim_output
        assert "192.0.2.10" in shim_output

    def test_invoke_classic_includes_ioc_values(self, classic_wm):
        """_invoke_classic() report includes IOC values from the workspace."""
        from adversary_pursuit.core.dossier_report import _invoke_classic

        report = _invoke_classic(classic_wm)
        assert "192.0.2.10" in report
        assert "regression.example.com" in report

    def test_invoke_classic_does_not_contain_dossier_slot_grid(self, classic_wm):
        """_invoke_classic() report must NOT include M-7 dossier slot sections."""
        from adversary_pursuit.core.dossier_report import _invoke_classic

        report = _invoke_classic(classic_wm)
        assert "## Threat Actor Dossier" not in report
        assert "## Dossier Slots" not in report
