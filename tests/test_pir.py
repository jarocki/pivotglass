"""PIR category and tier on the investigation (#60, DEC-PIR-001)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pivotglass.core.analytic_commands import execute_analysis_command
from pivotglass.core.analytic_ledger import AnalyticLedger, LifecycleItemStatus, LifecycleItemType
from pivotglass.core.workspace import WorkspaceManager
from pivotglass.core.workspace_migrations import (
    CURRENT_WORKSPACE_SCHEMA_VERSION,
    get_workspace_schema_version,
)
from pivotglass.reports.pir import (
    CATEGORIES,
    IntelligenceLevel,
    RequirementCategory,
    pir_state,
    suggested_report_types,
)

REPORT_TYPE_IDS = {  # the 18 types of #52; the report-type registry replaces this set
    "executive-threat-briefing", "strategic-threat-landscape", "threat-informed-risk-assessment",
    "threat-activity-alert", "campaign-intrusion-analysis", "vulnerability-exploitation-brief",
    "threat-actor-profile", "diamond-model-analysis", "ach-attribution-matrix",
    "actor-capability-radar", "infrastructure-clustering-graph", "kill-chain-mapping",
    "attack-navigator-layer", "attack-graph-tree", "forensic-intrusion-timeline",
    "threat-hunting-package", "detection-signature-bundle", "defensive-coverage-assessment",
}


@pytest.fixture()
def ledger(tmp_path: Path) -> AnalyticLedger:
    manager = WorkspaceManager(tmp_path)
    manager.create("pir")
    manager.switch("pir")
    return AnalyticLedger(manager)


def _stops(ledger: AnalyticLedger) -> list[dict]:
    return [i for i in ledger.snapshot()["lifecycle_items"] if i["item_type"] == "stop_condition"]


def test_every_category_is_complete_and_names_real_slots_sources_and_report_types():
    from pivotglass.core.plugin_mgr import PluginManager
    from pivotglass.dossier.slots import DossierSlotName

    plugins = PluginManager()
    plugins.load_plugins()
    modules = set(plugins._modules)  # noqa: SLF001
    slots = {s.value for s in DossierSlotName}
    assert set(CATEGORIES) == set(RequirementCategory)
    for category, d in CATEGORIES.items():
        assert d.label and d.focus and d.example.endswith("?") and d.fit_note
        assert len(d.stop_conditions) >= 3, category
        assert set(d.dossier_slots) <= slots, category
        assert set(d.preferred_sources) <= modules, (category, set(d.preferred_sources) - modules)
        assert set(d.report_types) == set(IntelligenceLevel)
        for types in d.report_types.values():
            assert set(types) <= REPORT_TYPE_IDS, category


def test_choosing_a_category_seeds_its_stop_conditions_once(ledger: AnalyticLedger):
    ledger.create_question("Which infrastructure does the phishing campaign share?")
    receipt = ledger.set_requirement("threat_actor_campaign")
    assert receipt["level"] == "operational"  # the category's default tier
    assert receipt["stop_conditions_seeded"] == 4
    assert ledger.set_requirement("threat-actor-campaign", "tactical")["stop_conditions_seeded"] == 0
    stops = _stops(ledger)
    assert len(stops) == 4
    assert {s["author_kind"] for s in stops} == {"system"}
    assert {s["analyst_disposition"] for s in stops} == {"accepted"}


def test_switching_category_defers_open_seeds_and_switching_back_reopens_only_those(ledger: AnalyticLedger):
    ledger.create_question("q")
    ledger.set_requirement("ttps")
    first, second, *_ = _stops(ledger)
    ledger.update_lifecycle_item(first["id"], status=LifecycleItemStatus.SATISFIED)
    ledger.update_lifecycle_item(second["id"], status=LifecycleItemStatus.DEFERRED)  # analyst's choice
    switch = ledger.set_requirement("brand_vip_footprint")
    assert switch["stop_conditions_deferred"] == 1  # the one still open; satisfied is kept
    back = ledger.set_requirement("ttps")
    assert back["stop_conditions_seeded"] == 0 and back["stop_conditions_reopened"] == 1
    by_id = {s["id"]: s for s in _stops(ledger)}
    assert by_id[first["id"]]["status"] == "satisfied"
    assert by_id[second["id"]]["status"] == "deferred"  # the analyst's deferral survives
    state = pir_state(ledger.snapshot())
    assert state["category"] == "ttps" and len(state["stop_conditions"]) == 2


def test_verdict_moves_from_not_answered_to_partial_to_answered(ledger: AnalyticLedger):
    assert pir_state(ledger.snapshot())["verdict"] == "no_pir"
    ledger.create_question("Are our edge appliances being exploited?")
    assert pir_state(ledger.snapshot())["verdict"] == "no_pir"
    ledger.set_requirement("vulnerability_exploitation", "operational")
    state = pir_state(ledger.snapshot())
    assert state["verdict"] == "not_answered"
    assert state["verdict_label"] == "Not answered by available collection"
    assert state["question"] == "Are our edge appliances being exploited?"
    stops = state["stop_conditions"]
    ledger.update_lifecycle_item(stops[0]["id"], status=LifecycleItemStatus.SATISFIED)
    assert pir_state(ledger.snapshot())["verdict"] == "partially_answered"
    for stop in stops[1:]:
        ledger.update_lifecycle_item(stop["id"], status=LifecycleItemStatus.RESOLVED)
    assert pir_state(ledger.snapshot())["verdict"] == "partially_answered"  # no conclusion yet
    investigation = ledger.active_investigation()
    ledger.add_lifecycle_item(investigation["id"], LifecycleItemType.CONCLUSION, "No exploitation observed.")
    assert pir_state(ledger.snapshot())["verdict"] == "answered"


def test_ach_joins_the_suggestions_once_two_hypotheses_compete():
    base = suggested_report_types(RequirementCategory.TTPS, IntelligenceLevel.OPERATIONAL)
    assert "ach-attribution-matrix" not in base
    assert suggested_report_types(
        RequirementCategory.TTPS, IntelligenceLevel.OPERATIONAL, hypothesis_count=2
    )[-1] == "ach-attribution-matrix"


def test_weak_fit_categories_say_what_collection_cannot_do():
    for category in (RequirementCategory.GEOPOLITICAL_REGULATORY, RequirementCategory.STRATEGIC_MNA):
        assert CATEGORIES[category].collection_fit.value == "weak"
        assert "cannot" in CATEGORIES[category].fit_note or "not" in CATEGORIES[category].fit_note


def test_analysis_pir_command(ledger: AnalyticLedger):
    manager = ledger._workspace  # noqa: SLF001
    shown = execute_analysis_command(("pir",), manager)
    assert shown["data"]["verdict"] == "no_pir"
    assert len(execute_analysis_command(("pir", "categories"), manager)["data"]["categories"]) == 7
    recorded = execute_analysis_command(("pir", "brand_vip_footprint", "strategic"), manager)
    assert recorded["data"]["pir"]["level"] == "strategic"
    assert recorded["data"]["pir"]["report_types"] == ["executive-threat-briefing"]
    with pytest.raises(ValueError, match="Unknown PIR category"):
        execute_analysis_command(("pir", "espionage"), manager)
    with pytest.raises(ValueError, match="tactical, operational, or strategic"):
        execute_analysis_command(("pir", "ttps", "board"), manager)


def test_v13_workspace_migrates_with_unspecified_pir(tmp_path: Path):
    manager = WorkspaceManager(tmp_path)
    manager.create("old")
    manager.switch("old")
    AnalyticLedger(manager).create_question("legacy question")
    db = tmp_path / "old.db"
    manager._engine.dispose()  # noqa: SLF001
    with sqlite3.connect(db) as conn:  # rebuild the v13 shape: drop the two columns
        conn.execute("ALTER TABLE analytic_investigations DROP COLUMN requirement_category")
        conn.execute("ALTER TABLE analytic_investigations DROP COLUMN intelligence_level")
        conn.execute("UPDATE workspace_schema_version SET version = 13")
    migrated = WorkspaceManager(tmp_path)
    migrated.switch("old")
    assert get_workspace_schema_version(migrated._engine) == CURRENT_WORKSPACE_SCHEMA_VERSION == 14  # noqa: SLF001
    investigation = AnalyticLedger(migrated).active_investigation()
    assert investigation["requirement_category"] == "unspecified"
    assert investigation["intelligence_level"] == "unspecified"
    assert (tmp_path / "old.db.pre-v13-backup").is_file()


def test_report_opens_with_the_pir_and_its_verdict(ledger: AnalyticLedger):
    from pivotglass.core.dossier_report import generate_dossier_report

    manager = ledger._workspace  # noqa: SLF001
    report = generate_dossier_report(manager)
    assert "## Priority Intelligence Requirement" in report and "No PIR recorded" in report
    ledger.create_question("Who operates the lookalike domains?")
    ledger.set_requirement("brand_vip_footprint")
    report = generate_dossier_report(manager)
    section = report.split("## Overview")[0]
    assert "**Question:** Who operates the lookalike domains?" in section
    assert "Brand, VIP, and digital-footprint protection · **Tier:** Tactical" in section
    assert "**Verdict:** Not answered by available collection" in section
    assert "Stop conditions met:** 0 of 4" in section
    assert "Still needed for an answer:" in section
