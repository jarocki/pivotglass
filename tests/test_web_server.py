"""Tests for the loopback Pivotglass API adapter."""

from unittest.mock import patch

import pytest

from adversary_pursuit.agent.tools import ToolContext
from adversary_pursuit.web.server import WebCockpitService


def _service(tmp_path) -> WebCockpitService:
    ctx = ToolContext(
        config_dir=tmp_path / "config",
        workspace_dir=tmp_path / "workspaces",
    )
    return WebCockpitService(ctx)


def test_state_exposes_workspace_objects_and_teaching_briefings(tmp_path):
    state = _service(tmp_path).state()
    assert state["workspace"] == "default"
    assert state["objects"] == []
    assert "virustotal_lookup" in state["briefings"]
    assert state["briefings"]["passivetotal_lookup"]["artifacts"].startswith("passive-DNS")
    assert state["character"] == "default"
    assert len(state["dossier_slots"]) == 9
    assert {slot["status"] for slot in state["dossier_slots"]} == {"empty"}
    assert len(state["modes"]) == 14
    trinity = next(mode for mode in state["modes"] if mode["name"] == "trinity")
    assert trinity["theme"]["heading_color"] == "#00ff5f"
    assert trinity["cockpit"]["vehicle"] == "NEBUCHADNEZZAR"


def test_switch_mode_reuses_canonical_character_and_cockpit_authorities(tmp_path):
    service = _service(tmp_path)

    state = service.switch_mode("hal9000")

    assert state["character"] == "hal9000"
    active = next(mode for mode in state["modes"] if mode["name"] == "hal9000")
    assert active["theme"]["heading_color"] == "#ff5555"
    assert active["cockpit"]["hud_title"] == "HAL OPTICS"


def test_investigate_rejects_non_indicator(tmp_path):
    with pytest.raises(ValueError, match="recognized indicator"):
        _service(tmp_path).investigate("not an indicator")


def test_investigate_uses_existing_dispatch_and_execution_authorities(tmp_path):
    service = _service(tmp_path)
    battery = type("Battery", (), {"tools": ("virustotal_lookup",)})()
    with (
        patch("adversary_pursuit.web.server.dispatch_batteries", return_value=[battery]),
        patch(
            "adversary_pursuit.web.server.execute_tool",
            return_value=("Observed service response", None, [], []),
        ) as execute,
    ):
        result = service.investigate("198.51.100.10")

    assert [event["kind"] for event in result["events"]] == ["probe", "evidence"]
    assert result["events"][0]["briefing"]["source"] == "VirusTotal"
    assert result["events"][1]["summary"] == "Observed service response"
    execute.assert_called_once()


def test_plan_payload_teaches_only_applicable_services(tmp_path):
    service = _service(tmp_path)
    battery = type("Battery", (), {"tools": ("passivetotal_lookup",)})()
    with patch("adversary_pursuit.web.server.dispatch_batteries", return_value=[battery]):
        plan = service.plan_payload("suspect.test")

    assert [event["tool"] for event in plan["events"]] == ["passivetotal_lookup"]
    assert "without querying DNS" in plan["events"][0]["briefing"]["purpose"]
