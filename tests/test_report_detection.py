"""Domain 5 report types (#57): Threat Hunting Package and Detection Signature Bundle."""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest
import yaml

from pivotglass.core.workspace import WorkspaceManager
from pivotglass.reports.commands import execute_report_command
from pivotglass.reports.contract import unreserved_values
from pivotglass.reports.engine import build_report
from pivotglass.reports.registry import get_report_type
from tests.report_fixtures import build_detection_workspace

TYPES = ("threat-hunting-package", "detection-signature-bundle")


@pytest.fixture()
def wm(tmp_path) -> WorkspaceManager:
    return build_detection_workspace(tmp_path)


@pytest.mark.parametrize("type_id", TYPES)
def test_types_render_complete_in_every_format(wm, type_id):
    for output in get_report_type(type_id).formats:
        result = execute_report_command(f"{type_id} {output.value}", wm)
        assert result["complete"], result["missing_required"]
        assert result["text"].strip()
    assert unreserved_values(execute_report_command(type_id, wm)["text"]) == []


def test_sigma_rules_follow_the_current_spec_and_stay_experimental_until_validated(wm):
    text = execute_report_command("detection-signature-bundle sigma", wm)["text"]
    rules = list(yaml.safe_load_all(text))
    assert {r["logsource"]["category"] for r in rules} == {"dns", "network_connection", "proxy", "process_creation"}
    for rule in rules:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", rule["date"]) and rule["status"] == "experimental"
        assert re.fullmatch(r"[0-9a-f-]{36}", rule["id"])
    proxy = next(r for r in rules if r["logsource"]["category"] == "proxy")
    assert proxy["tags"] == ["attack.t1071.001"]  # the technique mapped to the URL's evidence
    rule_id = proxy["id"]
    execute_report_command(f"validate {rule_id} passed | Replayed proxy logs with one known hit", wm)
    again = {r["id"]: r for r in yaml.safe_load_all(execute_report_command("detection-signature-bundle sigma", wm)["text"])}
    assert again[rule_id]["status"] == "test"


def test_suricata_sids_are_local_stable_and_rules_carry_metadata(wm):
    text = execute_report_command("detection-signature-bundle suricata", wm)["text"]
    rules = [line for line in text.splitlines() if line.startswith("alert ")]
    sids = [int(m) for m in re.findall(r"sid:(\d+);", text)]
    assert len(sids) == len(rules) == len(set(sids)) and all(1_000_000 <= s <= 1_999_999 for s in sids)
    assert all("metadata:created_at" in r and "rev:1;" in r for r in rules)
    assert text == execute_report_command("detection-signature-bundle suricata", wm)["text"]
    assert "[." not in text  # rule files are never defanged


def test_yara_comes_only_from_supplied_strings_and_compiles(wm, tmp_path):
    text = execute_report_command("detection-signature-bundle yara", wm)["text"]
    assert 'sample_sha256 = "' + "a" * 64 + '"' in text and 'status = "untested draft"' in text
    if shutil.which("yara") is None:
        pytest.skip("yara is not installed; the rule's syntax is not compiled here")
    rule_file, target = tmp_path / "r.yar", tmp_path / "t.bin"
    rule_file.write_text(text)
    target.write_bytes(b"Global\\ExampleMutex ... /api/v2/checkin?build=")
    result = subprocess.run(["yara", str(rule_file), str(target)], capture_output=True, text=True, check=False)
    assert result.returncode == 0 and "PG_sample_" in result.stdout


def test_hunting_package_records_negative_outcomes_and_untested_queries(wm):
    report = build_report(wm, "threat-hunting-package")
    queries = report.element("hunt_queries").content["queries"]
    assert {q["language"] for q in queries} == {"spl", "kql", "eql"}
    assert all(q["status"] == "untested" for q in queries)
    assert "earliest=-30d" in queries[0]["text"] and "operator@mail.example" not in json.dumps(queries)  # victim excluded
    assert report.element("hunt_outcome") is not None and report.element("hunt_outcome").status.value == "empty"
    execute_report_command("outcome refuted | No host resolved the C2 domain in 30 days of DNS logs.", wm)
    outcome = build_report(wm, "threat-hunting-package").element("hunt_outcome").content
    assert outcome["result"] == "refuted"
    markdown = execute_report_command("threat-hunting-package", wm)["text"]
    assert "A refuted or inconclusive hunt is a result" in markdown


def test_pyramid_and_validation_cover_every_generated_rule(wm):
    report = build_report(wm, "detection-signature-bundle")
    levels = {lvl["key"]: lvl["items"] for lvl in report.element("pyramid_of_pain").content["levels"]}
    assert levels["ttp"] == [(None, "T1071.001 Web Protocols")] and ("file", "a" * 64) in levels["hash"]
    assert ("domain-name", "c2.example.net") in levels["domain"]
    assert (None, "ExampleLoader") in levels["tool"]
    validation = report.element("validation_notes").content["rules"]
    kinds = {row["kind"].split("/")[0] for row in validation}
    assert {"sigma", "suricata", "yara", "spl", "kql", "eql"} <= kinds
    assert all(row["result"] == "not tested" for row in validation)


@pytest.mark.parametrize(
    "command",
    ["yara nothex | ref | s", f"yara {'a' * 64} | ref |", "validate x maybe | y", "outcome perhaps | z"],
)
def test_detection_commands_validate(wm, command):
    with pytest.raises(ValueError, match="Usage"):
        execute_report_command(command, wm)


@pytest.mark.parametrize(
    "kind, value, expected",
    [
        ("ip", "192.0.2.7", "192.0.2.7"),
        ("ip", "192.0.2.7] any (msg:\"x\"; sid:1;)", None),
        ("ip", "fe80::1%x] any (msg:\"x\"; sid:1;) #", None),
        ("ip", "fe80::1%eth0", None),
        ("ip", "2001:DB8::0001", "2001:db8::1"),
        ("domain", "C2.Example.NET.", "c2.example.net"),
        ("domain", 'evil.example"; sid:1; content:"x', None),
        ("domain", "bad|7C|.example", None),
        ("url", "https://login.example.com/a?b=c", "https://login.example.com/a?b=c"),
        ("url", "https://login.example.com/a b", None),
        ("url", "https://login.example.com/a\"; sid:1;", None),  # spaces are never part of a URL value
        ("url", "https://login.example.com/a\";sid:1;", "https://login.example.com/a\";sid:1;"),
        ("url", "javascript:alert(1)", None),
        ("sha256", "A" * 64, "a" * 64),
        ("sha256", "a" * 63, None),
    ],
)
def test_only_strictly_parsed_values_reach_rules(kind, value, expected):
    from pivotglass.reports.elements.detection import safe_indicator

    assert safe_indicator(kind, value) == expected


def test_crafted_values_cannot_inject_rule_options(tmp_path):
    from pivotglass.reports.elements import ReportContext, load_builtin_elements
    from pivotglass.reports.elements.detection import (
        _content,
        _yara_string,
        rejected_values,
        suricata_rules,
    )

    manager = WorkspaceManager(workspace_dir=tmp_path / "ws")
    manager.create("x")
    manager.switch("x")
    manager.store_stix_objects(
        [{"type": "url", "value": 'https://drop.example.com/p";sid:1;|41|'},
         {"type": "domain-name", "value": 'evil.example"; sid:1;'}],
        module_name="test/crafted", target="crafted",
    )
    load_builtin_elements()
    context = ReportContext(manager)
    rules = suricata_rules(context, __import__("pivotglass.reports.elements.detection", fromlist=["blockable"]).blockable(context))
    assert len(rules) == 1  # the URL parses; the domain does not
    text = rules[0]["text"]
    assert len(re.findall(r"(?<!\\);\s*sid:", text)) == 1 and '\\"' in text and "\\;" in text and "|7C|41|7C|" in text
    assert any("evil.example" in r for r in rejected_values(context))
    with pytest.raises(ValueError):
        _content("a\nb")
    assert _yara_string('a"b\nc\x01') == 'a\\"b\\nc\\x01'


def test_hunt_data_sources_name_attack_data_components_when_content_is_installed(wm, tmp_path, monkeypatch):
    """The hunt cites ATT&CK data components for mapped techniques, or says the content is missing."""
    from pivotglass.reports.elements import ReportContext
    from tests.test_framework_perspectives import _catalog

    without = build_report(wm, "threat-hunting-package").element("hunt_data_sources")
    techniques = [c["technique_id"] for c in without.content["data_components"]]
    assert techniques == [] and any("not installed" in g for g in without.gaps)

    (tmp_path / "attack").mkdir()
    catalog = _catalog(tmp_path / "attack")
    monkeypatch.setattr(ReportContext, "attack_catalog", property(lambda self: catalog))
    with_catalog = build_report(wm, "threat-hunting-package").element("hunt_data_sources")
    rows = {c["technique_id"]: c["components"] for c in with_catalog.content["data_components"]}
    assert rows and not any("not installed" in g for g in with_catalog.gaps)
    assert all(isinstance(components, list) for components in rows.values())
