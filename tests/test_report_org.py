"""Organisation input (#59): import, validation, sections, and withholding from the model."""

from __future__ import annotations

from pathlib import Path

import pytest

from pivotglass.reports.commands import execute_report_command
from pivotglass.reports.engine import build_report
from pivotglass.reports.org import OrgInputs, execute_org_command
from tests.report_fixtures import build_operational_workspace

FIXTURES = Path(__file__).parent / "fixtures" / "reports"
CVE = "CVE-2024-0001"


@pytest.fixture()
def wm(tmp_path):
    manager = build_operational_workspace(tmp_path)
    execute_org_command(f"import {FIXTURES / 'org.yaml'}", manager)
    execute_org_command(f"telemetry {FIXTURES / 'telemetry.csv'}", manager)
    for module, obj in (
        ("cti/cisa_kev", {"type": "vulnerability", "name": CVE, "x_kev_listed": True, "x_kev_catalog_version": "2026.11.20",
                          "x_kev_catalog_released": "2026-11-20T00:00:00Z", "x_kev_date_added": "2026-01-10",
                          "x_kev_due_date": "2026-01-31", "x_kev_vendor": "Example", "x_kev_product": "Gateway",
                          "x_kev_known_ransomware": "Unknown", "x_kev_required_action": "Apply the update."}),
        ("cti/first_epss", {"type": "vulnerability", "name": CVE, "x_epss_score": 0.5, "x_epss_percentile": 0.9, "x_epss_date": "2026-11-25"}),
        ("cti/nvd_cve", {"type": "vulnerability", "name": CVE, "description": "Command injection in Example Gateway.",
                         "x_nvd_cwes": ["CWE-78"], "x_nvd_cvss": [],
                         "x_nvd_configurations": [{"criteria": "cpe:2.3:o:example:gateway:*:*:*:*:*:*:*:*",
                                                   "version_start_including": "9.0", "version_end_excluding": "9.1.2"}],
                         "x_nvd_references": [{"url": "https://vendor.example/a", "source": "v", "tags": ["Patch"]}]}),
    ):
        manager.store_stix_objects([obj], module_name=module, target=CVE)
    from pivotglass.core.analytic_ledger import AnalyticLedger, AssertionType

    AnalyticLedger(manager).create_assertion(
        "Seen in the actor's 2026 intrusions.", assertion_type=AssertionType.JUDGMENT,
        subject_ref="actor:Example-Spider", predicate="exploits", object_value=CVE,
    )
    execute_report_command("write technical_mechanism | Unauthenticated command injection in the web UI.", manager)
    execute_report_command("write remediation_notes | Restrict the web UI to the management VLAN until patched.", manager)
    return manager


def test_import_records_each_kind_and_summary(wm):
    summary = execute_org_command("show", wm)["data"]
    assert {"profile", "controls", "environment", "telemetry"} <= set(summary)
    assert summary["telemetry"]["rows"] == 5 and summary["share_with_model"] is False
    events = OrgInputs(wm).telemetry()
    assert events[-1].timestamp.isoformat() == "2026-11-21T09:00:00+00:00"  # +01:00 normalised to UTC


@pytest.mark.parametrize(
    "content, message",
    [
        ("profile: {capability_benchmark: {magic: 3}}", "unknown capability axes"),
        ("controls: [{technique: T1071.001, control: x, visibility: 3, alerting: 0, prevention: 0}]", "less than or equal to 2"),
        ("controls: [{technique: X1, control: x, visibility: 0, alerting: 0, prevention: 0}]", "pattern"),
        ("environment: {nodes: [{id: a, label: A}], edges: [{source: a, target: b}]}", "unknown nodes: b"),
        ("unexpected: 1", "Extra inputs"),
        ("{}", "no profile, controls or environment"),
    ],
)
def test_import_rejects_invalid_input(tmp_path, wm, content, message):
    path = tmp_path / "bad.yaml"
    path.write_text(content)
    with pytest.raises(ValueError, match=message):
        execute_org_command(f"import {path}", wm)


def test_telemetry_without_a_time_zone_is_refused(tmp_path, wm):
    path = tmp_path / "t.csv"
    path.write_text("timestamp,host,source,summary\n2026-11-20 08:14:22,h,s,x\n")
    with pytest.raises(ValueError, match="(?s)event 1: .*time zone"):
        execute_org_command(f"telemetry {path}", wm)


def test_vulnerability_brief_builds_and_checks_our_versions(wm):
    report = build_report(wm, "vulnerability-exploitation-brief")
    assert report.complete, report.missing_required
    exposure = report.element("org_exposure").content
    gateway = next(t for t in exposure["technology"] if t["product"] == "Example Gateway")
    assert gateway["affected"] is True  # 9.1.0 is inside [9.0, 9.1.2)
    assert {"technique": "T1071.001", "control": "Web proxy", "gap_status": "moderate"} in exposure["controls"]
    assert exposure["targeting"][0]["value"] == "healthcare"


def test_controls_benchmark_objective_and_timeline_sections(wm):
    radar = build_report(wm, "actor-capability-radar")
    bench = {r["axis"]: r for r in radar.element("defense_benchmark").content["axes"]}
    assert (bench["malware"]["actor"], bench["malware"]["ours"]) == (4, 3)
    from pivotglass.reports.elements import (
        ELEMENTS,
        ReportContext,
        build_element,
        load_builtin_elements,
    )

    load_builtin_elements()
    context = ReportContext(wm)
    controls = build_element(ELEMENTS["control_matrix"], context)
    assert {r["technique"]: r["gap_status"] for r in controls.content["controls"]} == {"T1071.001": "moderate", "T1190": "critical"}
    assert "Never tested: T1190." in controls.gaps
    assert build_element(ELEMENTS["objective"], context).content["objectives"][0]["protects"] == "ERP database"
    timeline = build_element(ELEMENTS["forensic_timeline"], context).content
    assert len(timeline["events"]) == 5 and timeline["hosts"]["ws-fin-04.corp.example"] == 3


def test_organisation_input_is_withheld_from_the_model_until_allowed(wm):
    from pivotglass.agent.tools import ToolContext, execute_tool

    ctx = ToolContext(workspace_dir=wm._workspace_dir)
    ctx.workspace_mgr = wm
    withheld, *_ = execute_tool(ctx, "preview_report", {"report_type": "vulnerability-exploitation-brief"})
    assert "Example Gateway" not in withheld.split("## Organisational exposure")[1].split("##")[0]
    assert "org share-with-model on" in withheld
    execute_org_command("share-with-model on", wm)
    shared, *_ = execute_tool(ctx, "preview_report", {"report_type": "vulnerability-exploitation-brief"})
    assert "Example Gateway" in shared
    # The analyst's own view is never withheld.
    assert "Example Gateway" in execute_report_command("vulnerability-exploitation-brief", wm)["text"]


def test_org_command_usage(wm):
    with pytest.raises(ValueError, match="Usage: org"):
        execute_org_command("share-with-model maybe", wm)
    with pytest.raises(ValueError, match="no such file"):
        execute_org_command("import /nonexistent/org.yaml", wm)
