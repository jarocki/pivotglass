"""Domain 4 report types (#56): kill chain, Navigator layer, attack tree, forensic timeline."""

from __future__ import annotations

import json

import pytest

from pivotglass.core.workspace import WorkspaceManager
from pivotglass.reports.commands import execute_report_command
from pivotglass.reports.contract import unreserved_values
from pivotglass.reports.engine import build_report
from pivotglass.reports.registry import get_report_type
from tests.report_fixtures import build_behavioral_workspace

TYPES = ("kill-chain-mapping", "attack-navigator-layer", "attack-graph-tree", "forensic-intrusion-timeline")


@pytest.fixture(scope="module")
def wm(tmp_path_factory) -> WorkspaceManager:
    return build_behavioral_workspace(tmp_path_factory.mktemp("behavioral"))


@pytest.mark.parametrize("type_id", TYPES)
def test_types_render_complete_in_every_format(wm, type_id):
    assert get_report_type(type_id).available
    for output in get_report_type(type_id).formats:
        result = execute_report_command(f"{type_id} {output.value}", wm)
        assert result["complete"], result["missing_required"]
    assert unreserved_values(execute_report_command(type_id, wm)["text"]) == []


def test_kill_chain_uses_mappings_and_recorded_control_status(wm):
    phases = {p["phase_id"]: p for p in build_report(wm, "kill-chain-mapping").element("kill_chain_table").content["phases"]}
    assert phases["delivery"]["actions"] == ["Phishing link to the login URL."]
    assert phases["delivery"]["status"] == "detected" and phases["command-and-control"]["status"] == "blocked"
    assert phases["delivery"]["techniques"] == ["T1071.001"]
    assert phases["delivery"]["telemetry"] == "Proxy"  # an imported event carries the same technique
    assert phases["reconnaissance"]["actions"] == [] and phases["reconnaissance"]["status"] is None


def test_navigator_layer_matches_the_pinned_versions_and_scores_independent_sources(wm):
    layer = json.loads(execute_report_command("attack-navigator-layer navigator", wm)["text"])
    assert layer["versions"] == {"attack": "19.2", "navigator": "5.3.2", "layer": "4.5"}
    assert layer["domain"] == "enterprise-attack"
    technique = layer["techniques"][0]
    assert technique["techniqueID"] == "T1071.001" and technique["score"] == 1 and "color" not in technique
    assert layer["gradient"]["colors"] == ["#ffffff", "#e8613c"]


def test_attack_tree_honours_and_gates_and_finds_choke_points(wm):
    report = build_report(wm, "attack-graph-tree")
    scenarios = report.element("attack_tree").content["scenarios"]["erp"]
    # ERP is an AND gate: both the domain-controller step and the jump-host step are required.
    assert all({"jump", "dc", "erp"} <= set(s) for s in scenarios)
    assert ["dc", "erp", "jump", "vpn"] in scenarios and ["dc", "erp", "jump", "phish"] in scenarios
    chokes = {c["node"]: c["share"] for c in report.element("choke_points").content["choke_points"]}
    assert chokes == {"jump": 1.0, "dc": 1.0}
    mermaid = execute_report_command("attack-graph-tree mermaid", wm)["text"]
    assert "[AND]" in mermaid and "-.->" in mermaid and "-->" in mermaid


def test_forensic_timeline_and_dwell_times(wm):
    report = build_report(wm, "forensic-intrusion-timeline")
    dwell = report.element("dwell_metrics").content
    assert dwell["first_malicious"] == "2026-11-20 08:14:22"
    assert dwell["dwell"] == "1d 0h 45m" and dwell["time_to_contain"] == "2h 30m"
    assert dwell["coarse"] == 2  # detection and containment are minute-precision
    assert len(report.element("forensic_timeline").content["events"]) == 6


def test_control_command_validates(wm):
    with pytest.raises(ValueError, match="Usage: report control"):
        execute_report_command("control delivery stopped | x", wm)


def test_attack_scenarios_stay_bounded_on_a_wide_and_gate():
    import time

    from pivotglass.reports.elements.behavioral import MAX_SCENARIOS, attack_scenarios
    from pivotglass.reports.org import Environment

    entries = [{"id": f"e{i}", "label": f"e{i}", "kind": "entry"} for i in range(30)]
    mids = [{"id": f"m{j}", "label": f"m{j}"} for j in range(6)]
    env = Environment.model_validate({
        "nodes": [*entries, *mids, {"id": "goal", "label": "goal", "kind": "objective", "gate": "AND"}],
        "edges": [{"source": f"e{i}", "target": f"m{j}"} for i in range(30) for j in range(6)]
        + [{"source": f"m{j}", "target": "goal"} for j in range(6)],
    })
    started = time.monotonic()
    found = attack_scenarios(env, "goal")
    assert len(found) <= MAX_SCENARIOS and time.monotonic() - started < 5  # 30**6 combinations uncapped
