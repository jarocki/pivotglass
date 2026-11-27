"""Type 18, Defensive Coverage Assessment (#57): scope, derived gaps, and a pinned emulation plan.

The index sample holds rows copied from Atomic Red Team (MIT licence,
redcanaryco/atomic-red-team at 04a53f01) for the techniques the fixture uses.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pivotglass.reports import atomic
from pivotglass.reports.commands import execute_report_command
from pivotglass.reports.engine import build_report
from tests.report_fixtures import build_strategic_workspace

SAMPLE = Path(__file__).parent / "fixtures" / "reports" / "atomic_index_sample.csv"


@pytest.fixture(scope="module")
def wm(tmp_path_factory):
    return build_strategic_workspace(tmp_path_factory.mktemp("coverage"))


@pytest.fixture()
def index(monkeypatch):
    manifest = atomic.AtomicManifest(**{**atomic.ATOMIC_INDEX.__dict__, "sha256": hashlib.sha256(SAMPLE.read_bytes()).hexdigest()})
    monkeypatch.setattr(atomic, "ATOMIC_INDEX", manifest)
    monkeypatch.setattr(atomic, "default_index_path", lambda manifest=manifest: SAMPLE)
    original = atomic.load_index
    monkeypatch.setattr(atomic, "load_index", lambda path, manifest=manifest: original(path, manifest))


def test_coverage_assessment_derives_gaps_and_cites_atomic_tests(wm, index):
    report = build_report(wm, "defensive-coverage-assessment")
    assert report.complete, report.missing_required
    gaps = {g["technique"]: g for g in report.element("gap_list").content["gaps"]}
    assert gaps["T1190"]["gap_status"] == "critical" and gaps["T1071.001"]["gap_status"] == "moderate"
    assert list(gaps) == ["T1190", "T1071.001"]  # critical first
    steps = {s["technique"]: s for s in report.element("emulation_plan").content["steps"]}
    assert steps["T1071.001"]["tests"][0]["guid"] == "81c13829-f6c9-45b8-85a6-053366d55297"
    assert steps["T1071.001"]["pass_criteria"] == "an alert fires for the test; the control blocks the test"
    markdown = execute_report_command("defensive-coverage-assessment", wm)["text"]
    assert "`04a53f01`" in markdown and "powershell.exe" not in markdown  # GUIDs, never inline commands


def test_without_the_index_the_plan_says_so(wm, monkeypatch, tmp_path):
    monkeypatch.setattr(atomic, "default_index_path", lambda manifest=atomic.ATOMIC_INDEX: tmp_path / "absent.csv")
    plan = build_report(wm, "defensive-coverage-assessment").element("emulation_plan")
    assert plan.status.value == "partial" and "not installed" in plan.gaps[0]


def test_a_tampered_index_is_refused(tmp_path):
    bad = tmp_path / "index.csv"
    bad.write_bytes(SAMPLE.read_bytes() + b"x")
    with pytest.raises(ValueError, match="digest mismatch"):
        atomic.load_index(bad)


def test_the_pinned_manifest_is_the_reviewed_one():
    assert atomic.ATOMIC_INDEX.commit.startswith("04a53f01") and atomic.ATOMIC_INDEX.licence == "MIT"
    assert atomic.ATOMIC_INDEX.sha256 == "52b1686589d9ee124165c210e77ff6e41db65b6e6de87611ef2b03d98e0b4256"
