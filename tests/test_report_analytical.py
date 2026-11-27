"""Domain 3 report types (#55): actor profile, Diamond Model, ACH, capability radar, infrastructure graph."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import stix2

from pivotglass.core.workspace import WorkspaceManager
from pivotglass.reports.commands import execute_report_command
from pivotglass.reports.contract import unreserved_values
from pivotglass.reports.engine import build_report, issue_report
from pivotglass.reports.registry import get_report_type
from tests.report_fixtures import ACTOR, build_analytical_workspace

DOMAIN_3 = (
    "threat-actor-profile",
    "diamond-model-analysis",
    "ach-attribution-matrix",
    "actor-capability-radar",
    "infrastructure-clustering-graph",
)


@pytest.fixture(scope="module")
def wm(tmp_path_factory) -> WorkspaceManager:
    return build_analytical_workspace(tmp_path_factory.mktemp("analytical"))


@pytest.fixture()
def empty(tmp_path: Path) -> WorkspaceManager:
    manager = WorkspaceManager(workspace_dir=tmp_path / "ws")
    manager.create("blank")
    manager.switch("blank")
    return manager


@pytest.mark.parametrize("type_id", DOMAIN_3)
def test_each_type_is_built_and_renders_in_every_declared_format(wm, type_id):
    report_type = get_report_type(type_id)
    for output in report_type.formats:
        result = execute_report_command(f"{type_id} {output.value}", wm)
        assert result["complete"], (type_id, result["missing_required"])
        assert result["text"].strip()
        if output.value == "json":
            payload = json.loads(result["text"])
            assert [e["element_id"] for e in payload["elements"]] == [
                item.id for item in report_type.elements
            ]
        if output.value == "stix":
            stix2.parse(json.loads(result["text"]), allow_custom=True)


@pytest.mark.parametrize("type_id", DOMAIN_3)
def test_an_empty_workspace_is_incomplete_and_names_what_is_missing(empty, type_id):
    report = build_report(empty, type_id)
    assert not report.complete and report.missing_required
    gaps = report.element("gaps_limitations").content["report_gaps"]
    for element_id in report.missing_required:
        assert any(g["element"] == element_id for g in gaps), element_id


def test_actor_profile_is_about_the_named_actor_and_keeps_claims_out_of_key_judgments(wm):
    report = build_report(wm, "threat-actor-profile")
    assert report.subject == ACTOR and report.header.title == "Threat Actor Profile: Example Spider"
    identity = report.element("actor_identity").content
    assert [a["value"] for a in identity["aliases"]] == ["Example Spider"]
    assert identity["origin"][0]["likelihood"] == "unlikely"
    judgments = [j["statement"] for j in report.element("key_judgments").content["judgments"]]
    assert "The certificate was supplied by shared hosting." in judgments
    assert "Ransom notes and a leak site." not in judgments  # a motivation claim, shown under Motivation
    assert [r["value"] for r in report.element("victimology").content["rows"]] == ["healthcare", "Western Europe"]
    patterns = {(p["attribute"], p["value"]) for p in report.element("infra_opsec").content["patterns"]}
    assert ("registrar", "example registrar") in patterns and ("TLD", ".net") in patterns
    technique = report.element("attack_matrix").content["techniques"][0]
    assert technique["technique_id"] == "T1071.001" and technique["procedure"] == "HTTPS beacon to the C2 URL."


def test_several_actors_require_a_named_subject(wm, tmp_path):
    from pivotglass.core.analytic_ledger import AnalyticLedger, AssertionType

    other = build_analytical_workspace(tmp_path)
    AnalyticLedger(other).create_assertion(
        "A second tracked actor.", assertion_type=AssertionType.JUDGMENT,
        subject_ref="actor:Other-Bear", predicate="alias", object_value="Other Bear",
    )
    with pytest.raises(ValueError, match="several actors"):
        build_report(other, "threat-actor-profile")
    assert build_report(other, "threat-actor-profile", subject="actor:Other-Bear").subject == "actor:Other-Bear"
    with pytest.raises(ValueError, match="no claims about actor:Nobody"):
        execute_report_command("threat-actor-profile actor:Nobody", other)


def test_ach_scores_diagnosticity_tally_and_sensitivity(wm):
    report = build_report(wm, "ach-attribution-matrix")
    matrix = report.element("ach_matrix").content
    by_value = {row["evidence"]: row for row in matrix["rows"]}
    assert by_value["c2.example.net"]["diagnosticity"] == "high"  # C for H1, I for H2
    assert by_value["192.0.2.44"]["diagnosticity"] == "low"  # C for every hypothesis
    assert matrix["tally"] == {"H1": 0.0, "H2": 2.0, "H3": 1.0}
    judgment = report.element("ach_judgment").content
    assert judgment["leaders"] == ["H1"] and judgment["sensitive_rows"]
    assert len(report.element("ach_hypotheses").content["hypotheses"]) == 3
    markdown = execute_report_command("ach-attribution-matrix", wm)["text"]
    assert "c2[.]example[.]net" in markdown and "| **Weighted inconsistency** |" in markdown


def test_diamond_events_group_by_shared_evidence_and_threads_link_shared_values(wm):
    report = build_report(wm, "diamond-model-analysis")
    events = report.element("diamond_events").content["events"]
    assert len(events) == 2
    first = next(e for e in events if e["vertices"]["victim"])
    assert first["unknown_vertices"] == ["adversary", "capability"]
    assert first["meta_features"]["timestamp"] is not None
    other = next(e for e in events if e is not first)
    assert other["meta_features"]["phase"] == "Command and Control"  # from the accepted Kill Chain mapping
    mermaid = execute_report_command("diamond-model-analysis mermaid", wm)["text"]
    assert mermaid.startswith("flowchart TB") and "stroke-dasharray" in mermaid and "c2[.]example[.]net" in mermaid


def test_capability_radar_scores_against_the_rubric_and_states_a_missing_benchmark(wm):
    report = build_report(wm, "actor-capability-radar")
    scores = {s["axis"]: s["score"] for s in report.element("capability_radar").content["scores"]}
    assert scores == {"access": 3, "malware": 4, "evasion": 3, "movement": None, "infrastructure": None}
    assert report.complete  # the benchmark is optional
    assert report.element("defense_benchmark").status.value == "empty"
    gaps = [g["gap"] for g in report.element("gaps_limitations").content["report_gaps"]]
    assert "Defence benchmark: No capability benchmark in the organisation profile." in gaps
    assert any("is not scored" in g for g in gaps)


def test_infrastructure_graph_has_clusters_time_bounds_and_pivots(wm):
    report = build_report(wm, "infrastructure-clustering-graph")
    graph = report.element("infra_graph").content
    assert any(len(c["nodes"]) == 3 for c in graph["clusters"])
    assert all(e["first_seen"] and e["truth_kind"] for e in graph["edges"])
    pivot = report.element("pivot_points").content["pivots"][0]
    assert (pivot["value"], pivot["degree"]) == ("192.0.2.44", 2)
    mermaid = execute_report_command("infrastructure-clustering-graph mermaid", wm)["text"]
    assert "subgraph c0" in mermaid and "192[.]0[.]2[.]44" in mermaid


def test_actor_reports_reissue_per_actor(wm):
    first = issue_report(wm, "threat-actor-profile")
    again = issue_report(wm, "threat-actor-profile")
    assert again.header.report_id == first.header.report_id and again.header.version == 2


@pytest.mark.parametrize("type_id", DOMAIN_3)
def test_rendered_examples_use_reserved_values_only(wm, type_id):
    assert unreserved_values(execute_report_command(type_id, wm)["text"]) == []


def test_ach_summary_reads_the_same_matrix_as_the_report(wm):
    """#32: the cockpit's ACH line and the report agree."""
    from pivotglass.reports.elements import ReportContext
    from pivotglass.reports.elements.analytical import ach_summary

    summary = ach_summary(ReportContext(wm))
    report = build_report(wm, "ach-attribution-matrix")
    assert summary["hypotheses"] == len(report.element("ach_hypotheses").content["hypotheses"]) == 3
    assert [leader["label"] for leader in summary["leaders"]] == report.element("ach_judgment").content["leaders"]
    assert summary["strongest_disconfirming"] is None  # nothing is scored inconsistent with H1
