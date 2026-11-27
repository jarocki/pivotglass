"""Domain 2 report types (#54): Threat Activity Alert, Campaign Analysis, and the vulnerability sections."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import stix2

from pivotglass.core.workspace import WorkspaceManager
from pivotglass.reports.commands import execute_report_command
from pivotglass.reports.contract import unreserved_values
from pivotglass.reports.elements import (
    ELEMENTS,
    ElementStatus,
    ReportContext,
    build_element,
    load_builtin_elements,
)
from pivotglass.reports.engine import build_report
from pivotglass.reports.registry import get_report_type
from tests.report_fixtures import build_operational_workspace

TYPES = ("threat-activity-alert", "campaign-intrusion-analysis")


@pytest.fixture(scope="module")
def wm(tmp_path_factory) -> WorkspaceManager:
    return build_operational_workspace(tmp_path_factory.mktemp("operational"))


@pytest.fixture()
def blank(tmp_path: Path) -> WorkspaceManager:
    manager = WorkspaceManager(workspace_dir=tmp_path / "ws")
    manager.create("blank")
    manager.switch("blank")
    return manager


@pytest.mark.parametrize("type_id", TYPES)
def test_types_render_complete_in_every_format_with_reserved_values(wm, type_id):
    for output in get_report_type(type_id).formats:
        result = execute_report_command(f"{type_id} {output.value}", wm)
        assert result["complete"], result["missing_required"]
        if output.value == "stix":
            stix2.parse(json.loads(result["text"]), allow_custom=True)
    assert unreserved_values(execute_report_command(type_id, wm)["text"]) == []


@pytest.mark.parametrize("type_id", TYPES)
def test_empty_workspace_is_incomplete(blank, type_id):
    report = build_report(blank, type_id)
    assert not report.complete
    assert {"threat_summary", "ioc_table"} <= set(report.missing_required)


def test_alert_blocks_only_suitable_indicators_with_role_and_expiry(wm):
    report = build_report(wm, "threat-activity-alert")
    iocs = report.element("ioc_table").content
    values = {row["value"]: row for row in iocs["indicators"]}
    assert "operator@mail.example" not in values and iocs["excluded"] == 1  # tagged victim
    assert values["c2.example.net"]["role"] == "c2" and values["c2.example.net"]["ttl_days"] == 30
    assert values["drop.example.org"]["first_seen"] == "2026-10-01"  # the source's date, not collection time
    triage = report.element("triage_actions").content["steps"]
    assert "email-addr" not in triage[0]["detail"] and "last 30 days" in triage[1]["detail"]
    summary = report.element("threat_summary").content
    assert summary["severity"]["level"] == "high" and summary["texts"]
    delivery = report.element("delivery_vector").content
    assert delivery["steps"][0]["procedure"] == "Phishing link to the login URL."
    assert delivery["indicators"][0]["role"] == "delivery"


def test_investigation_report_keeps_its_plain_indicator_table(wm):
    markdown = execute_report_command("investigation-report", wm)["text"]
    assert "| Type | Value | First Seen |" in markdown and "Suggested expiry" not in markdown


def test_campaign_timeline_uses_source_dates_and_the_narrative_marks_unobserved_phases(wm):
    report = build_report(wm, "campaign-intrusion-analysis")
    timeline = report.element("campaign_timeline").content
    assert (timeline["first"], timeline["last"]) == ("2026-03", "2026-11-15")
    narrative = report.element("attack_narrative")
    steps = {s["phase"]: s for s in narrative.content["steps"]}
    assert steps["Delivery"]["techniques"] == ["T1071.001"]
    assert "Reconnaissance: not observed." in narrative.gaps
    recs = report.element("recommendations").content["recommendations"]
    assert [(r["priority"], r["owner"]) for r in recs] == [(1, "SOC"), (2, "Threat hunting")]
    infra = {r["value"]: r for r in report.element("infrastructure_breakdown").content["infrastructure"]}
    assert infra["192.0.2.44"]["connected"] == ["cdn.example.net", "mail.example.net"]
    assert infra["drop.example.org"]["hosting"] == "Example Hosting"


@pytest.mark.parametrize(
    "command, message",
    [
        ("write nonsense | text", "Usage: report write"),
        ("severity extreme | why", "Usage: report severity"),
        ("recommend 1 | act | owner | soon | outcome", "Usage: report recommend"),
        ("recommend 0 | act | owner | 2026-12-01 | outcome", "Usage: report recommend"),
    ],
)
def test_analyst_section_commands_validate(blank, command, message):
    with pytest.raises(ValueError, match=message):
        execute_report_command(command, blank)


def _vuln_context(tmp_path: Path, objects: list[tuple[str, dict]]) -> ReportContext:
    wm = WorkspaceManager(workspace_dir=tmp_path / "ws")
    wm.create("vuln")
    wm.switch("vuln")
    for module, obj in objects:
        wm.store_stix_objects([obj], module_name=module, target=obj["name"])
    load_builtin_elements()
    return ReportContext(wm)


CVE = "CVE-2024-0001"
KEV_LISTED = {"type": "vulnerability", "name": CVE, "x_kev_listed": True, "x_kev_catalog_version": "2026.11.20",
              "x_kev_catalog_released": "2026-11-20T00:00:00Z", "x_kev_date_added": "2026-01-10", "x_kev_due_date": "2026-01-31",
              "x_kev_known_ransomware": "Known", "x_kev_vendor": "Example", "x_kev_product": "Gateway",
              "x_kev_required_action": "Apply the vendor update.", "x_kev_cwes": ["CWE-78"]}
EPSS = {"type": "vulnerability", "name": CVE, "x_epss_score": 0.94321, "x_epss_percentile": 0.998, "x_epss_date": "2026-11-25"}
NVD = {"type": "vulnerability", "name": CVE, "description": "OS command injection in the Example Gateway web UI.",
       "x_nvd_cvss": [{"version": "3.1", "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", "base_score": 9.8,
                       "base_severity": "CRITICAL", "source": "nvd@nist.gov", "type": "Primary"}],
       "x_nvd_cwes": ["CWE-78"],
       "x_nvd_configurations": [{"criteria": "cpe:2.3:o:example:gateway:*:*:*:*:*:*:*:*", "version_start_including": None,
                                 "version_start_excluding": None, "version_end_including": None, "version_end_excluding": "9.1.2"}],
       "x_nvd_references": [{"url": "https://vendor.example/advisory/1", "source": "vendor", "tags": ["Vendor Advisory", "Patch"]},
                            {"url": "https://poc.example/exploit", "source": "third", "tags": ["Exploit"]}]}


def test_vulnerability_sections_read_each_source_and_keep_it(tmp_path):
    context = _vuln_context(tmp_path, [("cti/cisa_kev", KEV_LISTED), ("cti/first_epss", EPSS), ("cti/nvd_cve", NVD)])
    meta = build_element(ELEMENTS["vuln_metadata"], context)
    assert meta.status is ElementStatus.COMPLETE
    row = meta.content["vulnerabilities"][0]
    assert row["cvss"][0]["vector"].startswith("CVSS:3.1/") and row["epss"]["date"] == "2026-11-25"
    assert row["kev"] == {"listed": True, "date_added": "2026-01-10", "due_date": "2026-01-31", "catalog_version": "2026.11.20"}
    status = build_element(ELEMENTS["exploitation_status"], context).content["vulnerabilities"][0]
    assert status["status"] == "Exploitation confirmed" and status["ransomware"] == "Known"
    assert status["exploit_refs"] == ["https://poc.example/exploit"]
    patch = build_element(ELEMENTS["patch_guidance"], context).content["vulnerabilities"][0]
    assert patch["fixed_in"] == ["9.1.2"] and patch["required_action"] == "Apply the vendor update."
    adoption = build_element(ELEMENTS["adversary_adoption"], context).content["rows"]
    assert adoption[0]["who"] == "ransomware operators (unnamed)"
    markdown = ELEMENTS["vuln_metadata"].markdown(meta, __import__("pivotglass.reports.contract", fromlist=["OutputFormat"]).OutputFormat.MARKDOWN)
    assert "EPSS** 0.943 (percentile 100%)" in markdown and "remediation due 2026-01-31" in markdown


def test_not_in_kev_is_not_called_unexploited_and_unchecked_sources_are_gaps(tmp_path):
    unlisted = {"type": "vulnerability", "name": CVE, "x_kev_listed": False, "x_kev_catalog_version": "2026.11.20",
                "x_kev_catalog_released": "2026-11-20T00:00:00Z"}
    context = _vuln_context(tmp_path, [("cti/cisa_kev", unlisted)])
    status = build_element(ELEMENTS["exploitation_status"], context).content["vulnerabilities"][0]
    assert status["status"] == "Not confirmed" and "not evidence that exploitation has not happened" in status["basis"]
    meta = build_element(ELEMENTS["vuln_metadata"], context)
    assert meta.status is ElementStatus.PARTIAL
    assert f"{CVE}: not looked up in NVD." in meta.gaps and f"{CVE}: not looked up in FIRST EPSS." in meta.gaps


