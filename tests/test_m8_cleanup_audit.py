"""M-8 cleanup audit tests — Stage A acceptance per plan §4.

Verifies the classic-shim removal checklist (DEC-M8-CLEANUP-001..003):
1. core/report.py deleted
2. tests/fixtures/v1_classic_report.md deleted
3. tests/test_classic_style_regression.py deleted
4. tests/test_report.py deleted
5. No ReportGenerator import in src/
6. No --style flag in src/
7. Classic tool names absent from agent/tools.py
8. create_tools() returns exactly 28 tools
9. generate_dossier_report tool has empty properties and required
10. _execute_generate_dossier_report signature is (ctx,) — no style param

@decision DEC-TEST-M8-AUDIT-001
@title test_m8_cleanup_audit enforces classic-shim removal invariants
@status accepted
@rationale Mechanical verification that every item in plan §3 removal checklist
           is satisfied. File-existence checks, source-grep checks, and schema
           checks give the reviewer concrete proof of each deletion without
           requiring manual inspection. DEC-M8-CLEANUP-001..003 compliance.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

# Root is two levels up from tests/
_REPO_ROOT = Path(__file__).parent.parent
_SRC_ROOT = _REPO_ROOT / "src" / "adversary_pursuit"


# ---------------------------------------------------------------------------
# Stage A-1..A-4: deleted file checks
# ---------------------------------------------------------------------------


class TestDeletedFiles:
    """Verify the four files mandated for deletion are absent."""

    def test_classic_report_file_deleted(self):
        """src/adversary_pursuit/core/report.py must not exist (DEC-M8-CLEANUP-003)."""
        assert not (_SRC_ROOT / "core" / "report.py").exists(), (
            "core/report.py still exists — classic shim was not removed at M-8."
        )

    def test_classic_fixture_deleted(self):
        """tests/fixtures/v1_classic_report.md must not exist."""
        assert not (_REPO_ROOT / "tests" / "fixtures" / "v1_classic_report.md").exists(), (
            "tests/fixtures/v1_classic_report.md still exists."
        )

    def test_classic_regression_test_deleted(self):
        """tests/test_classic_style_regression.py must not exist."""
        assert not (_REPO_ROOT / "tests" / "test_classic_style_regression.py").exists(), (
            "tests/test_classic_style_regression.py still exists."
        )

    def test_v1_report_test_deleted(self):
        """tests/test_report.py must not exist."""
        assert not (_REPO_ROOT / "tests" / "test_report.py").exists(), (
            "tests/test_report.py still exists."
        )


# ---------------------------------------------------------------------------
# Stage A-5..A-7: source-grep checks
# ---------------------------------------------------------------------------


def _read_src_files() -> list[tuple[Path, str]]:
    """Return (path, source) pairs for all .py files under src/."""
    return [(p, p.read_text(encoding="utf-8")) for p in _SRC_ROOT.rglob("*.py")]


class TestNoClassicSourceReferences:
    """Verify that classic-shim symbols are absent from all source files."""

    def test_no_reportgenerator_import_in_src(self):
        """No src file imports ReportGenerator (DEC-M8-CLEANUP-003)."""
        matches = []
        for path, src in _read_src_files():
            if "ReportGenerator" in src:
                matches.append(str(path))
        assert not matches, f"ReportGenerator still referenced in: {matches}"

    def test_no_style_flag_in_src(self):
        """No src file contains '--style' flag (DEC-M8-CLEANUP-001)."""
        matches = []
        for path, src in _read_src_files():
            if "--style" in src:
                matches.append(str(path))
        assert not matches, f"'--style' flag still in source files: {matches}"

    def test_no_classic_tool_names_in_tools_py(self):
        """start_report_interview, answer_report_question, generate_report absent as string literals in tools.py.

        Checks for quoted string forms only (e.g. "start_report_interview") to avoid
        false positives from @decision annotation rationale text which legitimately
        names removed tools for documentation purposes (DEC-M8-CLEANUP-002).
        """
        tools_src = (_SRC_ROOT / "agent" / "tools.py").read_text(encoding="utf-8")
        for name in ("start_report_interview", "answer_report_question"):
            quoted = f'"{name}"'
            assert quoted not in tools_src, (
                f"'{quoted}' string literal still in agent/tools.py — classic tool was not removed."
            )
        # 'generate_report' may appear as a substring of 'generate_dossier_report';
        # check that the standalone tool name string literal is absent.
        assert '"generate_report"' not in tools_src, (
            "'\"generate_report\"' tool definition still in agent/tools.py."
        )

    def test_no_invoke_classic_in_src(self):
        """_invoke_classic is absent from all source files."""
        matches = []
        for path, src in _read_src_files():
            if "_invoke_classic" in src:
                matches.append(str(path))
        assert not matches, f"'_invoke_classic' still referenced in: {matches}"


# ---------------------------------------------------------------------------
# Stage A-8..A-10: tool count and schema checks
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_ctx(tmp_path):
    """Minimal ToolContext for create_tools() calls."""
    from adversary_pursuit.agent.tools import ToolContext

    return ToolContext(workspace_dir=tmp_path / "workspaces")


class TestToolCatalogPostM8:
    """create_tools() returns 28 tools with correct generate_dossier_report schema."""

    def test_tool_count_is_28(self, tmp_ctx):
        """create_tools returns exactly 28 tools (was 31 before M-8)."""
        from adversary_pursuit.agent.tools import create_tools

        tools = create_tools(tmp_ctx)
        assert len(tools) == 28, (
            f"Expected 28 tools, got {len(tools)}. "
            "M-8 removed start_report_interview, answer_report_question, generate_report."
        )

    def test_generate_dossier_report_parameterless(self, tmp_ctx):
        """generate_dossier_report tool has empty properties and empty required."""
        from adversary_pursuit.agent.tools import create_tools

        tools = create_tools(tmp_ctx)
        tool = next(t for t in tools if t["function"]["name"] == "generate_dossier_report")
        params = tool["function"]["parameters"]
        assert params.get("properties", {}) == {}, (
            f"generate_dossier_report should have no properties, got: {params['properties']}"
        )
        assert params.get("required", []) == [], (
            f"generate_dossier_report should have no required params, got: {params['required']}"
        )

    def test_classic_tools_absent_from_catalog(self, tmp_ctx):
        """start_report_interview, answer_report_question, generate_report not in tool list."""
        from adversary_pursuit.agent.tools import create_tools

        tools = create_tools(tmp_ctx)
        names = {t["function"]["name"] for t in tools}
        for classic_name in ("start_report_interview", "answer_report_question", "generate_report"):
            assert classic_name not in names, (
                f"Classic tool '{classic_name}' still in create_tools() output."
            )

    def test_tool_schema_is_json_serializable(self, tmp_ctx):
        """Tool list serialises to JSON and back with 28 entries."""
        from adversary_pursuit.agent.tools import create_tools

        tools = create_tools(tmp_ctx)
        roundtripped = json.loads(json.dumps(tools))
        assert len(roundtripped) == 28

    def test_execute_generate_dossier_report_no_style_param(self, tmp_ctx):
        """_execute_generate_dossier_report(ctx) call signature is (ctx,) only."""
        from adversary_pursuit.agent.tools import _execute_generate_dossier_report

        sig = inspect.signature(_execute_generate_dossier_report)
        params = list(sig.parameters.keys())
        assert params == ["ctx"], (
            f"Expected only 'ctx', got: {params}. style= must not exist post-M-8."
        )
        # Confirm TypeError when style= is passed
        with pytest.raises(TypeError):
            _execute_generate_dossier_report(tmp_ctx, style="dossier")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Stage A: compound integration — dossier render still works after cleanup
# ---------------------------------------------------------------------------


class TestDossierReportStillWorks:
    """Dossier renderer produces valid output after classic-shim removal."""

    def test_generate_dossier_report_produces_markdown(self, tmp_path):
        """generate_dossier_report() returns non-empty dossier Markdown."""
        from adversary_pursuit.core.dossier_report import generate_dossier_report
        from adversary_pursuit.core.workspace import WorkspaceManager

        wm = WorkspaceManager(workspace_dir=tmp_path / "ws")
        wm.create("audit")
        wm.switch("audit")
        result = generate_dossier_report(wm)
        assert isinstance(result, str)
        assert "## Dossier State" in result
        assert "## Predictions" in result
