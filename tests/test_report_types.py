"""The 18 CTI report-type definitions (#52): complete, consistent, honest about what is built."""

from __future__ import annotations

from pathlib import Path

import pytest

from pivotglass.reports.contract import unreserved_values
from pivotglass.reports.elements import ELEMENTS, load_builtin_elements
from pivotglass.reports.elements.planned import PLANNED
from pivotglass.reports.pir import CATEGORIES
from pivotglass.reports.registry import ReportDomain, get_report_type, report_types

ROOT = Path(__file__).parent.parent
TYPES_DIR = ROOT / "src" / "pivotglass" / "reports" / "types"
TEMPLATES = {  # number -> source template; the originals stay untracked source material
    1: "01_Executive_Threat_Briefing", 2: "02_Strategic_Threat_Landscape_Forecast",
    3: "03_Threat_Informed_Risk_Assessment", 4: "04_Threat_Activity_Alert_Flash",
    5: "05_Campaign_Intrusion_Analysis_Report", 6: "06_Vulnerability_Exploitation_Brief",
    7: "07_Threat_Actor_Profile_Dossier", 8: "08_Diamond_Model_Intrusion_Analysis",
    9: "09_Known_Actor_Overlap_ACH_Matrix", 10: "10_Actor_Capability_Radar_Plot",
    11: "11_Infrastructure_Clustering_Graph", 12: "12_Cyber_Kill_Chain_Mapping",
    13: "13_MITRE_ATTACK_Navigator_Layer", 14: "14_Attack_Graph_Tree",
    15: "15_Forensic_Intrusion_Timeline", 16: "16_Threat_Hunting_Package",
    17: "17_Detection_Signature_Bundle", 18: "18_Defensive_Coverage_Gap_Assessment",
}
DOMAIN_OF = {**dict.fromkeys(range(1, 4), ReportDomain.STRATEGIC), **dict.fromkeys(range(4, 7), ReportDomain.OPERATIONAL),
             **dict.fromkeys(range(7, 12), ReportDomain.ANALYTICAL), **dict.fromkeys(range(12, 16), ReportDomain.BEHAVIORAL),
             **dict.fromkeys(range(16, 19), ReportDomain.DETECTION)}


def numbered():
    return {t.number: t for t in report_types().values() if t.number}


def test_all_eighteen_types_exist_in_their_domains_with_unique_codes():
    types = numbered()
    assert sorted(types) == list(range(1, 19))
    assert {n: t.domain for n, t in types.items()} == DOMAIN_OF
    codes = [t.code for t in report_types().values()]
    assert len(codes) == len(set(codes))


@pytest.mark.parametrize("number", range(1, 19))
def test_each_definition_names_its_source_template_and_what_changed(number):
    t = numbered()[number]
    text = (TYPES_DIR / f"{t.id}.yaml").read_text(encoding="utf-8")
    assert TEMPLATES[number] in text.split("\nid:")[0]
    assert "Changes:" in text.split("\nid:")[0]
    assert t.tier is not None and t.use_when and t.related


def test_planned_and_built_elements_are_disjoint_and_every_planned_element_is_used():
    built = load_builtin_elements()
    assert not set(PLANNED) & set(built)
    used = {item.id for t in report_types().values() for item in t.elements}
    assert set(PLANNED) - used == set()
    assert all(p.issue in {53, 54, 55, 56, 57, 58, 59} for p in PLANNED.values())


def test_a_planned_type_refuses_to_render_and_names_the_issues(tmp_path):
    from pivotglass.core.workspace import WorkspaceManager
    from pivotglass.reports.commands import execute_report_command

    wm = WorkspaceManager(workspace_dir=tmp_path / "ws")
    wm.create("x")
    wm.switch("x")
    planned = next(t for t in report_types().values() if not t.available)
    with pytest.raises(ValueError, match="not built yet.*#"):
        execute_report_command(planned.id, wm)
    with pytest.raises(ValueError, match="not built yet"):
        execute_report_command(f"issue {planned.id}", wm)
    summary = {row["id"]: row for row in execute_report_command("types", wm)["data"]}
    assert summary[planned.id]["available"] is False and summary[planned.id]["building_issues"]
    assert summary["investigation-report"]["available"] is True


def test_every_pir_suggestion_is_a_defined_type():
    defined = set(report_types())
    for definition in CATEGORIES.values():
        for ids in definition.report_types.values():
            assert set(ids) <= defined


def test_machine_formats_match_the_types_that_produce_them():
    by_format = {f.value: {t.number for t in report_types().values() if f in t.formats}
                 for t in report_types().values() for f in t.formats}
    assert by_format["navigator"] == {13}
    assert by_format["sigma"] == by_format["suricata"] == by_format["yara"] == {17}
    assert by_format["mermaid"] == {8, 11, 14}


def test_attribution_and_internal_reports_default_to_restricted_markings():
    for type_id in ("ach-attribution-matrix", "forensic-intrusion-timeline", "attack-graph-tree"):
        marking = get_report_type(type_id).default_marking
        assert (marking.tlp.value, marking.pap.value) == ("AMBER+STRICT", "RED")


def test_definitions_contain_no_unreserved_example_values():
    for path in TYPES_DIR.glob("*.yaml"):
        assert unreserved_values(path.read_text(encoding="utf-8")) == [], path.name


def test_generated_reference_is_current():
    import importlib.util

    spec = importlib.util.spec_from_file_location("gen_report_docs", ROOT / "scripts" / "gen_report_docs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.stale() == []


def test_element_options_are_rejected_unless_the_element_declares_them():
    from pivotglass.reports import registry

    text = (TYPES_DIR / "threat-activity-alert.yaml").read_text(encoding="utf-8")
    bad = text.replace("  - id: ioc_table\n", "  - id: ioc_table\n    options: {ttl: true}\n")
    with pytest.raises(ValueError, match="does not take options: ttl"):
        registry._parse("threat-activity-alert.yaml", bad)
    assert ELEMENTS  # built elements are registered
