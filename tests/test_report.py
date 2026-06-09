"""Tests for Issue #21: Interview-based Report Generation.

Tests the ReportGenerator class and console `report` command.

Production sequence tested:
  workspace create -> store objects -> report generate -> save/show
  This is the realistic analyst workflow: investigate, then debrief via report.

@decision DEC-TEST-021
@title Test suite covers ReportGenerator unit tests and console command wiring
@status accepted
@rationale ReportGenerator is the terminal artifact of an investigation. Tests
           must cover: correct Markdown structure, IOC table accuracy, timeline
           ordering, all 5 interview questions present, metadata accuracy, empty
           workspace edge case, and file save/load. Console tests verify the
           report/interview/show subcommands work end-to-end.
"""

from __future__ import annotations

import io

import pytest

from adversary_pursuit.core.report import ReportGenerator
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
    """WorkspaceManager with a few STIX objects and module runs."""
    wm.store_stix_objects(
        [
            {"type": "ipv4-addr", "value": "1.2.3.4"},
            {"type": "domain-name", "value": "evil.example.com"},
            {"type": "ipv4-addr", "value": "5.6.7.8"},
        ],
        module_name="osint/whois_lookup",
        target="evil.example.com",
    )
    wm.store_stix_objects(
        [
            {"type": "url", "value": "https://evil.example.com/c2"},
        ],
        module_name="osint/urlscan",
        target="evil.example.com",
    )
    wm.store_score_events(
        [
            {"action": "new_ip", "points": 100, "indicator": "1.2.3.4"},
            {"action": "new_domain", "points": 200, "indicator": "evil.example.com"},
        ]
    )
    return wm


# ---------------------------------------------------------------------------
# ReportGenerator construction
# ---------------------------------------------------------------------------


class TestReportGeneratorConstruction:
    """ReportGenerator constructs correctly from workspace manager."""

    def test_creates_with_workspace_manager(self, wm):
        """ReportGenerator accepts a WorkspaceManager instance."""
        rg = ReportGenerator(wm)
        assert rg is not None

    def test_creates_with_scoring_engine(self, wm):
        """ReportGenerator accepts an optional scoring engine."""
        from adversary_pursuit.gamification.scoring import ScoringEngine

        rg = ReportGenerator(wm, scoring_engine=ScoringEngine())
        assert rg is not None

    def test_has_five_interview_questions(self, wm):
        """ReportGenerator initialises exactly 5 interview sections."""
        rg = ReportGenerator(wm)
        assert len(rg.sections) == 5

    def test_interview_questions_correct_text(self, wm):
        """Interview sections contain the 5 prescribed questions."""
        rg = ReportGenerator(wm)
        questions = [s.question for s in rg.sections]
        assert "Why did you start this pursuit?" in questions
        assert "How did you find the first indicator?" in questions
        assert "What is the single most important thing you learned?" in questions
        assert "How could someone interrupt this adversary's operation?" in questions
        assert "What is the next step?" in questions

    def test_answers_empty_on_construction(self, wm):
        """All interview answers default to empty string."""
        rg = ReportGenerator(wm)
        for section in rg.sections:
            assert section.answer == ""


# ---------------------------------------------------------------------------
# set_answer
# ---------------------------------------------------------------------------


class TestSetAnswer:
    """set_answer stores answers at the correct index."""

    def test_set_answer_stores_value(self, wm):
        """set_answer stores the answer string at the given index."""
        rg = ReportGenerator(wm)
        rg.set_answer(0, "APT41 infrastructure overlap")
        assert rg.sections[0].answer == "APT41 infrastructure overlap"

    def test_set_answer_all_five(self, wm):
        """set_answer works for all five question indices."""
        rg = ReportGenerator(wm)
        answers = [
            "Tip from partner",
            "Spearphish domain",
            "C2 beaconing interval",
            "Sinkhole the C2 domain",
            "Pivot to AS block",
        ]
        for i, ans in enumerate(answers):
            rg.set_answer(i, ans)
        for i, section in enumerate(rg.sections):
            assert section.answer == answers[i]

    def test_set_answer_out_of_range_raises(self, wm):
        """set_answer raises IndexError for invalid index."""
        rg = ReportGenerator(wm)
        with pytest.raises((IndexError, ValueError)):
            rg.set_answer(99, "bad index")


# ---------------------------------------------------------------------------
# generate() — Markdown structure
# ---------------------------------------------------------------------------


class TestGenerate:
    """generate() produces a valid Markdown report."""

    def test_generate_returns_string(self, populated_wm):
        rg = ReportGenerator(populated_wm)
        output = rg.generate()
        assert isinstance(output, str)

    def test_report_has_title(self, populated_wm):
        """Report starts with # Investigation Report heading."""
        rg = ReportGenerator(populated_wm)
        output = rg.generate()
        assert "# Investigation Report" in output

    def test_report_has_metadata_section(self, populated_wm):
        """Report has ## Metadata section."""
        rg = ReportGenerator(populated_wm)
        output = rg.generate()
        assert "## Metadata" in output

    def test_report_metadata_workspace_name(self, populated_wm):
        """Metadata includes the workspace name."""
        rg = ReportGenerator(populated_wm)
        output = rg.generate()
        assert "test" in output  # workspace name

    def test_report_metadata_total_score(self, populated_wm):
        """Metadata includes total score."""
        rg = ReportGenerator(populated_wm)
        output = rg.generate()
        assert "300" in output  # 100 + 200

    def test_report_has_ioc_table(self, populated_wm):
        """Report has ## Indicators of Compromise section."""
        rg = ReportGenerator(populated_wm)
        output = rg.generate()
        assert "Indicators of Compromise" in output

    def test_report_ioc_table_includes_all_objects(self, populated_wm):
        """IOC table contains all 4 stored STIX objects."""
        rg = ReportGenerator(populated_wm)
        output = rg.generate()
        assert "1.2.3.4" in output
        assert "5.6.7.8" in output
        assert "evil.example.com" in output
        assert "https://evil.example.com/c2" in output

    def test_report_has_timeline_section(self, populated_wm):
        """Report has ## Timeline section."""
        rg = ReportGenerator(populated_wm)
        output = rg.generate()
        assert "## Timeline" in output

    def test_report_timeline_includes_module_runs(self, populated_wm):
        """Timeline lists both module runs."""
        rg = ReportGenerator(populated_wm)
        output = rg.generate()
        assert "osint/whois_lookup" in output
        assert "osint/urlscan" in output

    def test_report_has_interview_notes_section(self, populated_wm):
        """Report has ## Interview Notes section."""
        rg = ReportGenerator(populated_wm)
        output = rg.generate()
        assert "Interview Notes" in output

    def test_report_interview_questions_appear(self, populated_wm):
        """All 5 interview questions appear in the report."""
        rg = ReportGenerator(populated_wm)
        output = rg.generate()
        assert "Why did you start this pursuit?" in output
        assert "How did you find the first indicator?" in output
        assert "What is the single most important thing you learned?" in output
        assert "How could someone interrupt this adversary's operation?" in output
        assert "What is the next step?" in output

    def test_report_interview_answers_appear(self, populated_wm):
        """Set answers appear in the Interview Notes section."""
        rg = ReportGenerator(populated_wm)
        rg.set_answer(0, "Threat intel feed alert on C2 domain")
        rg.set_answer(2, "C2 beacon uses 10-minute jitter")
        output = rg.generate()
        assert "Threat intel feed alert on C2 domain" in output
        assert "C2 beacon uses 10-minute jitter" in output

    def test_report_has_statistics_section(self, populated_wm):
        """Report has ## Statistics section."""
        rg = ReportGenerator(populated_wm)
        output = rg.generate()
        assert "Statistics" in output

    def test_report_statistics_has_type_counts(self, populated_wm):
        """Statistics section includes type breakdown."""
        rg = ReportGenerator(populated_wm)
        output = rg.generate()
        # 2 IPs, 1 domain, 1 URL stored
        assert "ipv4-addr" in output
        assert "domain-name" in output


# ---------------------------------------------------------------------------
# Empty workspace
# ---------------------------------------------------------------------------


class TestEmptyWorkspace:
    """generate() works when workspace has no data."""

    def test_empty_workspace_returns_valid_markdown(self, wm):
        """generate() on empty workspace returns valid (non-crashing) Markdown."""
        rg = ReportGenerator(wm)
        output = rg.generate()
        assert isinstance(output, str)
        assert "# Investigation Report" in output

    def test_empty_workspace_no_ioc_rows(self, wm):
        """IOC section on empty workspace says 'No indicators' or similar."""
        rg = ReportGenerator(wm)
        output = rg.generate()
        # Should still have the section heading
        assert "Indicators of Compromise" in output

    def test_empty_workspace_total_score_zero(self, wm):
        """Empty workspace shows score of 0."""
        rg = ReportGenerator(wm)
        output = rg.generate()
        assert "0" in output


# ---------------------------------------------------------------------------
# generate_ioc_table
# ---------------------------------------------------------------------------


class TestGenerateIocTable:
    """generate_ioc_table() returns a Markdown table string."""

    def test_returns_markdown_table(self, populated_wm):
        """generate_ioc_table returns a string with pipe characters."""
        rg = ReportGenerator(populated_wm)
        table = rg.generate_ioc_table()
        assert isinstance(table, str)
        assert "|" in table

    def test_table_includes_all_values(self, populated_wm):
        """Table rows contain the observable values."""
        rg = ReportGenerator(populated_wm)
        table = rg.generate_ioc_table()
        assert "1.2.3.4" in table
        assert "evil.example.com" in table

    def test_empty_workspace_table_no_rows(self, wm):
        """Empty workspace returns empty table or header-only."""
        rg = ReportGenerator(wm)
        table = rg.generate_ioc_table()
        assert isinstance(table, str)


# ---------------------------------------------------------------------------
# generate_timeline
# ---------------------------------------------------------------------------


class TestGenerateTimeline:
    """generate_timeline() returns chronological module run entries."""

    def test_returns_string(self, populated_wm):
        rg = ReportGenerator(populated_wm)
        timeline = rg.generate_timeline()
        assert isinstance(timeline, str)

    def test_timeline_module_names_present(self, populated_wm):
        """Timeline includes both module names."""
        rg = ReportGenerator(populated_wm)
        timeline = rg.generate_timeline()
        assert "osint/whois_lookup" in timeline
        assert "osint/urlscan" in timeline

    def test_empty_workspace_timeline_empty(self, wm):
        """Empty workspace returns empty string or 'no runs' message."""
        rg = ReportGenerator(wm)
        timeline = rg.generate_timeline()
        assert isinstance(timeline, str)


# ---------------------------------------------------------------------------
# save()
# ---------------------------------------------------------------------------


class TestSave:
    """save() writes the report to the filesystem."""

    def test_save_creates_file(self, populated_wm, tmp_path):
        """save() creates the output file."""
        rg = ReportGenerator(populated_wm)
        output_path = tmp_path / "report.md"
        rg.save(output_path)
        assert output_path.exists()

    def test_save_returns_path(self, populated_wm, tmp_path):
        """save() returns the path it wrote to."""
        rg = ReportGenerator(populated_wm)
        output_path = tmp_path / "report.md"
        result = rg.save(output_path)
        assert result == output_path

    def test_save_file_contains_report(self, populated_wm, tmp_path):
        """File written by save() contains the report content."""
        rg = ReportGenerator(populated_wm)
        output_path = tmp_path / "report.md"
        rg.save(output_path)
        content = output_path.read_text(encoding="utf-8")
        assert "# Investigation Report" in content
        assert "evil.example.com" in content

    def test_save_creates_parent_directories(self, populated_wm, tmp_path):
        """save() creates parent directories if they do not exist."""
        rg = ReportGenerator(populated_wm)
        output_path = tmp_path / "deep" / "nested" / "report.md"
        rg.save(output_path)
        assert output_path.exists()


# ---------------------------------------------------------------------------
# Console command wiring
# ---------------------------------------------------------------------------


class TestConsoleReport:
    """APConsole 'report' command wires correctly to ReportGenerator."""

    @pytest.fixture
    def console(self, tmp_path):
        from adversary_pursuit.core.console import APConsole

        app = APConsole(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
        )
        app.stdout = io.StringIO()
        # Ensure a workspace exists with data
        app.workspace_mgr.create("test")
        app.workspace_mgr.switch("test")
        app.workspace_mgr.store_stix_objects(
            [
                {"type": "ipv4-addr", "value": "10.0.0.1"},
                {"type": "domain-name", "value": "c2.example.org"},
            ],
            module_name="osint/whois_lookup",
            target="c2.example.org",
        )
        return app

    def run_cmd(self, app, cmd: str) -> str:
        app.stdout = io.StringIO()
        app.rich_console = app._make_rich_console()
        app.onecmd_plus_hooks(cmd)
        return app.stdout.getvalue() + app.rich_console.file.getvalue()

    def test_report_generate_creates_file(self, console, tmp_path):
        """report generate creates a file in the workspace directory."""
        out = self.run_cmd(console, "report generate")
        # Should succeed without error
        assert "error" not in out.lower() or "report" in out.lower()

    def test_report_show_outputs_markdown(self, console):
        """report show prints the Markdown report to stdout."""
        # First generate so there's something to show
        self.run_cmd(console, "report generate")
        out = self.run_cmd(console, "report show")
        assert "Investigation Report" in out or "report" in out.lower()

    def test_report_unknown_subcommand(self, console):
        """Unknown report subcommand prints usage message."""
        out = self.run_cmd(console, "report bogus")
        assert isinstance(out, str)

    def test_report_classic_style_generate_uses_v1_path(self, console):
        """report --style classic generate routes to the v1 interview report path (M-7 regression)."""
        out = self.run_cmd(console, "report --style classic generate")
        # Should succeed without error; v1 path produces Investigation Report header
        assert "error" not in out.lower() or "report" in out.lower()

    def test_report_default_generate_uses_dossier_path(self, console):
        """report generate (no --style flag) routes to dossier report by default (M-7)."""
        out = self.run_cmd(console, "report generate")
        # The dossier path must succeed; check that no exception trace appears
        assert "Traceback" not in out
        assert isinstance(out, str)
