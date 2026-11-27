"""Report system (#50): elements, registry, renderers, issuing, and the migrated investigation report.

The golden test holds the ``investigation-report`` type to the facts the
deleted ``core/dossier_report.py`` produced for the same workspace
(``tests/fixtures/reports/investigation-report.legacy.md``, captured from that
generator before it was removed).
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
import stix2

from pivotglass.core.workspace import WorkspaceManager
from pivotglass.reports import registry
from pivotglass.reports.commands import execute_report_command
from pivotglass.reports.contract import OutputFormat, ReportStatus, Tlp, unreserved_values
from pivotglass.reports.elements import ELEMENTS, ElementStatus, load_builtin_elements
from pivotglass.reports.engine import build_report, issue_report, list_issues, load_issue
from pivotglass.reports.render import TLP2_MARKING_IDS, render
from tests.report_fixtures import build_rich_workspace

LEGACY = Path(__file__).parent / "fixtures" / "reports" / "investigation-report.legacy.md"
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def rich(tmp_path: Path) -> WorkspaceManager:
    return build_rich_workspace(tmp_path)


@pytest.fixture()
def empty(tmp_path: Path) -> WorkspaceManager:
    wm = WorkspaceManager(workspace_dir=tmp_path / "workspaces")
    wm.create("blank")
    wm.switch("blank")
    return wm


def _refang(text: str) -> str:
    text = text.replace("[.]", ".").replace("[:]", ":").replace("[@]", "@").replace("hxxp", "http")
    text = re.sub(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", "<time>", text)
    return re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<uuid>", text)


def test_the_investigation_report_carries_every_fact_of_the_report_it_replaced(rich):
    markdown = _refang(render(build_report(rich)))
    skipped = {"# Threat Actor Dossier Report"}  # the title is now the type's title
    missing = [
        line
        for line in LEGACY.read_text(encoding="utf-8").splitlines()
        if line.strip() and line not in skipped and not line.startswith("- **Date:**")
        and _refang(line) not in markdown
    ]
    assert missing == []


def test_the_replaced_generator_is_gone():
    root = Path(__file__).parent.parent / "src" / "pivotglass"
    assert not (root / "core" / "dossier_report.py").exists()
    offenders = [p for p in root.rglob("*.py") if "generate_dossier_report(" in p.read_text(encoding="utf-8")]
    assert offenders == []


def test_every_section_states_its_provenance_and_the_report_ends_with_gaps_and_sources(rich):
    markdown = render(build_report(rich))
    assert markdown.startswith("# Investigation Report\n")
    assert "**Preview — not issued.**" in markdown
    assert markdown.count("<sub>Provenance:") == len(registry.get_report_type("investigation-report").elements) - 1
    assert markdown.index("## Gaps and Limitations") < markdown.index("## Sources")
    assert "Only one passive DNS provider was queried." in markdown.split("## Gaps and Limitations")[1]
    assert "F6" in markdown.split("## Sources")[1]


def test_markdown_defangs_but_json_and_stix_carry_values_unchanged(rich):
    report = build_report(rich)
    markdown = render(report, OutputFormat.MARKDOWN)
    assert "hxxps[:]//login[.]example[.]com/c2" in markdown
    assert "on `c2[.]example[.]net`" in markdown
    assert "https://login.example.com/c2" not in markdown
    for output in (OutputFormat.JSON, OutputFormat.STIX):
        text = render(report, output)
        assert "https://login.example.com/c2" in text
        assert "[.]" not in text


def test_stix_bundle_is_valid_and_marked_with_tlp_2(rich):
    report = build_report(rich, tlp=Tlp.AMBER_STRICT)
    bundle = json.loads(render(report, OutputFormat.STIX))
    stix2.parse(bundle, allow_custom=True)
    marking, identity, sdo, *observables = bundle["objects"]
    assert marking["id"] == TLP2_MARKING_IDS[Tlp.AMBER_STRICT]
    assert marking["extensions"][next(iter(marking["extensions"]))]["tlp_2_0"] == "amber+strict"
    assert sdo["type"] == "report" and sdo["object_marking_refs"] == [marking["id"]]
    assert sdo["x_pivotglass_pap"] == "AMBER"
    assert {o["type"] for o in observables} == {"email-addr", "url", "ipv4-addr", "domain-name", "ipv6-addr", "file"}
    assert set(sdo["object_refs"]) == {o["id"] for o in observables}


def test_an_empty_workspace_reports_incomplete_and_says_why(empty):
    report = build_report(empty)
    assert not report.complete
    assert "ioc_table" in report.missing_required and "collection_timeline" in report.missing_required
    markdown = render(report)
    assert "**Incomplete:** no content for" in markdown
    gaps = markdown.split("## Gaps and Limitations")[1]
    assert "No indicators have been collected." in gaps
    assert "No PIR category and tier are recorded" in gaps
    assert "analysis prediction <text>" in markdown and "note <text>" in markdown


def test_a_failing_authority_is_reported_not_hidden(rich, monkeypatch):
    def broken():
        raise RuntimeError("disk read error")

    monkeypatch.setattr(rich, "get_module_runs", broken)
    report = build_report(rich)
    gaps = report.element("gaps_limitations").content
    assert gaps["load_errors"] == ["module runs could not be read: disk read error"]
    assert report.element("collection_timeline").status is ElementStatus.EMPTY


def test_a_failing_element_becomes_an_empty_result_with_its_error(rich, monkeypatch):
    spec = ELEMENTS["overview"]

    def broken(context):
        raise RuntimeError("bad slot")

    monkeypatch.setitem(ELEMENTS, "overview", type(spec)(**{**spec.__dict__, "build": broken}))
    result = build_report(rich).element("overview")
    assert result.status is ElementStatus.EMPTY
    assert result.gaps == ("Overview could not be built: bad slot",)


def test_issuing_versions_the_report_and_reads_it_back_exactly(rich):
    first = issue_report(rich, summary="First look", tlp=Tlp.GREEN, now=NOW)
    assert first.header.report_id == "PG-INV-2026-0001" and first.header.version == 1
    rich.add_note("A later note")
    second = issue_report(rich, status=ReportStatus.FINAL, summary="Added a note", now=NOW)
    assert second.header.report_id == first.header.report_id
    assert [r.version for r in second.header.revision_history] == [1, 2]
    assert second.header.tlp is Tlp.GREEN  # the marking carries over unless changed
    assert "A later note" in render(second) and "A later note" not in render(load_issue(rich, "PG-INV-2026-0001", 1))
    assert load_issue(rich, "pg-inv-2026-0001") == second
    history = list_issues(rich)
    assert [(h["version"], h["status"]) for h in history] == [(2, "FINAL"), (1, "DRAFT")]


def test_tampering_with_an_issued_report_is_detected(rich):
    report = issue_report(rich, now=NOW)
    db = rich._workspace_dir / f"{rich.active}.db"
    with sqlite3.connect(db) as connection:
        payload = json.loads(connection.execute("SELECT payload FROM report_issues").fetchone()[0])
        payload["complete"] = not payload["complete"]
        connection.execute("UPDATE report_issues SET payload = ?", (json.dumps(payload),))
    with pytest.raises(ValueError, match="content hash"):
        load_issue(rich, report.header.report_id)


def test_final_is_refused_while_model_drafts_are_pending(rich, monkeypatch):
    spec = ELEMENTS["analyst_notes"]
    original = spec.build

    def with_draft(context):
        return original(context).model_copy(update={"pending_model_drafts": 1})

    monkeypatch.setitem(ELEMENTS, "analyst_notes", type(spec)(**{**spec.__dict__, "build": with_draft}))
    with pytest.raises(ValueError, match="pending analyst review"):
        issue_report(rich, status=ReportStatus.FINAL)
    assert issue_report(rich).header.status is ReportStatus.DRAFT


def test_the_report_command_grammar(rich):
    assert execute_report_command("", rich)["format"] == "markdown"
    assert execute_report_command("generate", rich)["title"] == "Investigation Report · preview"
    assert [t["id"] for t in execute_report_command("types", rich)["data"]][0] == "investigation-report"
    preview = execute_report_command("investigation-report json tlp:clear", rich)
    assert json.loads(preview["text"])["header"]["tlp"] == "CLEAR"
    assert preview["filename"].endswith("-investigation-report-preview.json")
    issued = execute_report_command("issue investigation-report final pap:green | Reviewed", rich)
    assert issued["title"] == "Issued PG-INV-2026-0001 v1 (FINAL)" and "PAP:GREEN" in issued["marking"]
    assert execute_report_command("open PG-INV-2026-0001 stix", rich)["filename"] == "PG-INV-2026-0001-v1.stix.json"
    assert len(execute_report_command("history investigation-report", rich)["data"]) == 1
    for bad, message in (
        ("nope", "unknown report type"),
        ("investigation-report tlp:white", "TLP must be one of"),
        ("investigation-report final", "Usage"),
        ("open", "Usage"),
        ("open PG-INV-2026-0099", "no issued report"),
    ):
        with pytest.raises(ValueError, match=message):
            execute_report_command(bad, rich)


def test_report_types_are_validated_at_load():
    load_builtin_elements()
    good = (Path(registry.__file__).parent / "types" / "investigation-report.yaml").read_text()
    assert registry._parse("investigation-report.yaml", good).code == "INV"
    cases = {
        "undefined elements: nonsense": good.replace("{id: statistics}", "{id: nonsense}"),
        "must require: sources": good.replace("{id: sources}", "{id: sources, required: false}"),
        "listed twice": good.replace("{id: statistics}", "{id: overview}"),
        "header must be the first": good.replace("  - {id: header}\n", "").replace("  - {id: sources}", "  - {id: sources}\n  - {id: header}"),
        "markdown and json": good.replace("[markdown, json, stix]", "[markdown, stix]"),
        "tlp": good.replace("tlp: AMBER", "tlp: WHITE"),
        "file name must be": good,
    }
    for message, text in cases.items():
        name = "other.yaml" if message == "file name must be" else "investigation-report.yaml"
        with pytest.raises(ValueError, match=message):
            registry._parse(name, text)


def test_every_registered_element_is_documented():
    for spec in load_builtin_elements().values():
        assert spec.description and spec.authorities and spec.provenance, spec.id


def test_reserved_examples_only_in_report_fixtures_and_type_definitions():
    texts = [LEGACY.read_text(encoding="utf-8")]
    texts += [p.read_text(encoding="utf-8") for p in (Path(registry.__file__).parent / "types").glob("*.yaml")]
    assert [unreserved_values(text) for text in texts] == [[] for _ in texts]


def test_v14_workspace_migrates_to_v15_with_report_issues(tmp_path):
    from sqlalchemy import create_engine, inspect, text

    from pivotglass.core.workspace_migrations import (
        CURRENT_WORKSPACE_SCHEMA_VERSION,
        ensure_workspace_schema,
    )

    wm = WorkspaceManager(workspace_dir=tmp_path / "ws")
    wm.create("old")
    db = tmp_path / "ws" / "old.db"
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE report_issues"))
        connection.execute(text("UPDATE workspace_schema_version SET version = 14"))
    receipt = ensure_workspace_schema(engine, db)
    assert (receipt.from_version, receipt.to_version) == (14, CURRENT_WORKSPACE_SCHEMA_VERSION)
    assert receipt.backup_path and receipt.backup_path.exists()
    assert "report_issues" in inspect(engine).get_table_names()
    engine.dispose()


def test_issued_reports_export_and_survive_clear(rich):
    from pivotglass.core.workspace_admin import export_workspace

    issue_report(rich, now=NOW)
    exported = export_workspace(rich, rich.active)
    assert exported["tables"]["report_issues"][0]["report_id"] == "PG-INV-2026-0001"
    rich.clear()
    assert [h["report_id"] for h in list_issues(rich)] == ["PG-INV-2026-0001"]
