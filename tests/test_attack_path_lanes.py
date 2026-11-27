"""Attack-path lanes and technique-level tags (#31)."""

from __future__ import annotations

import pytest

from pivotglass.core.indicator_tags import IndicatorTagAuthority
from pivotglass.core.visualization import VisualizationView, attack_path_lanes_intent
from pivotglass.core.workspace import WorkspaceManager
from tests.test_framework_perspectives import _catalog


@pytest.fixture()
def wm(tmp_path, monkeypatch) -> WorkspaceManager:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))  # no installed ATT&CK content
    manager = WorkspaceManager(workspace_dir=tmp_path / "ws")
    manager.create("case")
    manager.switch("case")
    manager.store_stix_objects([{"type": "domain-name", "value": "c2.example.net"}], module_name="t", target="x")
    return manager


def _tag(wm, value, dimension, tag_value, entity_type="domain-name"):
    IndicatorTagAuthority(wm).apply(
        [{"entity_type": entity_type, "normalized_value": value, "dimension": dimension, "value": tag_value}],
        operator="local analyst",
    )


def test_technique_ids_are_tactic_tags_and_bad_values_name_the_choice(wm):
    _tag(wm, "c2.example.net", "tactic", "T1003")
    assert {t["value"] for t in IndicatorTagAuthority(wm).current()} == {"t1003"}
    with pytest.raises(ValueError, match="technique ID such as T1071.001"):
        _tag(wm, "c2.example.net", "tactic", "not-a-tactic")


def test_lanes_place_by_tactic_technique_and_inferred_role(wm, tmp_path):
    _tag(wm, "c2.example.net", "tactic", "command-and-control")
    _tag(wm, "drop.example.org", "role", "delivery")
    _tag(wm, "dump.example.org", "tactic", "t1003")
    _tag(wm, "noise.example.org", "role", "benign")
    _tag(wm, "noise.example.org", "tactic", "impact")
    tags = IndicatorTagAuthority(wm).current()
    objects = wm.get_stix_objects()

    without = attack_path_lanes_intent("case", objects, tags)
    assert without.view == VisualizationView.ATTACK_LANES
    rows = {(r["label"], r["tactic_id"], r["basis"]) for r in without.data.rows}
    assert rows == {
        ("drop.example.org", "TA0001", "role tag, inferred"),
        ("c2.example.net", "TA0011", "tactic tag"),
    }
    assert without.missing_data.omitted_count == 1 and "T1003" in without.missing_data.explanation
    c2 = next(r for r in without.data.rows if r["label"] == "c2.example.net")
    assert c2["reference"].startswith("ev-") or c2["reference"]  # stored indicator links to evidence

    with_catalog = attack_path_lanes_intent("case", objects, tags, _catalog(tmp_path))
    dumped = next(r for r in with_catalog.data.rows if r["label"] == "dump.example.org")
    assert (dumped["tactic_id"], dumped["technique"], dumped["basis"]) == ("TA0006", "T1003", "technique tag")
    assert [r["lane_order"] for r in with_catalog.data.rows] == sorted(r["lane_order"] for r in with_catalog.data.rows)
