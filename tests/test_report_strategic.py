"""Domain 1 report types (#53): Executive Briefing, Landscape Forecast, Risk Assessment."""

from __future__ import annotations

import pytest

from pivotglass.core.workspace import WorkspaceManager
from pivotglass.reports.commands import execute_report_command
from pivotglass.reports.contract import unreserved_values
from pivotglass.reports.engine import build_report
from pivotglass.reports.registry import get_report_type
from tests.report_fixtures import build_strategic_workspace

TYPES = ("executive-threat-briefing", "strategic-threat-landscape", "threat-informed-risk-assessment")


@pytest.fixture(scope="module")
def wm(tmp_path_factory) -> WorkspaceManager:
    return build_strategic_workspace(tmp_path_factory.mktemp("strategic"))


@pytest.mark.parametrize("type_id", TYPES)
def test_types_render_complete(wm, type_id):
    assert get_report_type(type_id).available
    for output in get_report_type(type_id).formats:
        result = execute_report_command(f"{type_id} {output.value}", wm)
        assert result["complete"], result["missing_required"]
    assert unreserved_values(execute_report_command(type_id, wm)["text"]) == []


def test_executive_briefing_states_risk_and_confidence_separately(wm):
    report = build_report(wm, "executive-threat-briefing")
    risk = report.element("risk_rating").content
    assert (risk["severity"], risk["confidence"]) == ("high", "moderate")
    assert report.element("bluf").status.value == "complete"


def test_landscape_scenarios_use_icd_203_terms(wm):
    report = build_report(wm, "strategic-threat-landscape")
    kinds = {s["kind"]: s for s in report.element("scenarios").content["scenarios"]}
    assert set(kinds) == {"most-likely", "worst", "best"} and kinds["best"]["likelihood"] == "roughly_even_chance"
    markdown = execute_report_command("strategic-threat-landscape", wm)["text"]
    assert "Roughly even chance (45%–55%)" in markdown
    targeting = report.element("sector_targeting").content["rows"]
    assert any(r["value"] == "healthcare" and r["ours"] for r in targeting)


def test_risk_assessment_matches_owned_assets_and_actors(wm):
    report = build_report(wm, "threat-informed-risk-assessment")
    surface = report.element("attack_surface").content["exposures"]
    assert surface == [{"value": "198.51.100.5", "type": "ipv4-addr", "ports": [443, 8443], "vulns": ["CVE-2024-0001"], "source": "osint/shodan_internetdb"}]
    actor = report.element("actor_matrix").content["actors"][0]
    assert actor["intent"].startswith("high") and actor["capability"] == pytest.approx(10 / 3)
    assert report.element("risk_scenarios").content["scenarios"][0]["control_status"] == "missed"


@pytest.mark.parametrize(
    "command",
    ["risk extreme high | x", "scenario likely likely high | a | b", "scenario worst probable high | a | b",
     "risk-scenario likely critical stopped | a | b | c", "risk-scenario likely critical missed | a | b"],
)
def test_judgment_commands_validate(wm, command):
    with pytest.raises(ValueError, match="Usage"):
        execute_report_command(command, wm)
