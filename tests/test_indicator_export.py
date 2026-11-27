"""Focus-mode export of the filtered set (#33, DEC-INDICATOR-EXPORT-001)."""

from __future__ import annotations

import csv
import io
import json

import pytest
import stix2

from pivotglass.core.indicator_context import IndicatorContextAuthority
from pivotglass.core.indicator_export import CSV_COLUMNS, export_indicators
from pivotglass.core.indicator_tags import IndicatorTagAuthority
from pivotglass.core.workspace import WorkspaceManager

SET = [
    ("domain-name", "c2.example.net"),
    ("url", "https://login.example.com/c2"),
    ("file-hash-sha256", "a" * 64),
    ("vulnerability", "CVE-2024-0001"),
    ("attack-pattern", "T1071.001"),
    ("ipv4-addr", "=1+2"),  # hostile cell content: never stored, still exported safely
]


@pytest.fixture()
def wm(tmp_path) -> WorkspaceManager:
    manager = WorkspaceManager(workspace_dir=tmp_path / "ws")
    manager.create("case")
    manager.switch("case")
    manager.store_stix_objects(
        [{"type": "domain-name", "value": "c2.example.net"}], module_name="osint/dns_lookup", target="c2.example.net"
    )
    IndicatorTagAuthority(manager).apply(
        [
            {"dimension": "role", "entity_type": "domain-name", "normalized_value": "c2.example.net", "value": "c2"},
            {"dimension": "tactic", "entity_type": "domain-name", "normalized_value": "c2.example.net",
             "value": "command-and-control"},
            {"dimension": "cluster", "entity_type": "url", "normalized_value": "https://login.example.com/c2",
             "value": "kit-a"},
        ],
        operator="local analyst",
    )
    return manager


def test_csv_has_the_tag_source_and_first_seen_columns_and_a_defang_choice(wm):
    plain = export_indicators(wm, SET, output="csv", source_label="report.pdf")
    rows = {row["value"]: row for row in csv.DictReader(io.StringIO(plain["text"]))}
    assert tuple(next(csv.reader(io.StringIO(plain["text"])))) == CSV_COLUMNS
    domain = rows["c2.example.net"]
    assert (domain["role"], domain["tactic"], domain["source_document"]) == ("c2", "command-and-control", "report.pdf")
    assert domain["observed_by"] == "osint/dns_lookup"
    first_seen = IndicatorContextAuthority(wm).context([("domain-name", "c2.example.net")])["domain-name|c2.example.net"]["first_seen"]
    assert first_seen and domain["first_seen"] == first_seen
    assert rows["https://login.example.com/c2"]["cluster"] == "kit-a"
    assert rows["https://login.example.com/c2"]["first_seen"] == ""  # never collected: no first-seen time
    assert "'=1+2" in rows  # formula neutralised
    assert rows["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]["type"] == "file"

    defanged = export_indicators(wm, SET, output="csv", defanged=True)["text"]
    assert "c2[.]example[.]net" in defanged and "hxxps[:]//login[.]example[.]com/c2" in defanged


def test_stix_bundle_validates_keeps_real_values_and_reports_what_it_skipped(wm):
    result = export_indicators(wm, SET, output="stix", defanged=True, source_label="report.pdf")
    bundle = stix2.parse(json.loads(result["text"]), allow_custom=True)
    by_type = {obj.type: obj for obj in bundle.objects}
    assert by_type["domain-name"].value == "c2.example.net"  # defang never applies to STIX
    assert sorted(by_type["domain-name"].x_pivotglass_tags) == ["role:c2", "tactic:command-and-control"]
    assert by_type["file"].hashes["SHA-256"] == "a" * 64
    assert by_type["vulnerability"].name == "CVE-2024-0001"
    assert by_type["attack-pattern"].external_references[0].external_id == "T1071.001"
    assert result["skipped"] == ["ipv4-addr|=1+2"]  # not a valid address, so no STIX object
    assert result["count"] == 5


def test_export_rejects_unknown_formats_and_oversized_sets(wm):
    with pytest.raises(ValueError, match="csv or stix"):
        export_indicators(wm, SET, output="xlsx")
    with pytest.raises(ValueError, match="at most"):
        export_indicators(wm, [("domain-name", f"h{n}.example") for n in range(2_001)], output="csv")
