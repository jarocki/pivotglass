"""Tests for the loopback Pivotglass API adapter."""

import time
from unittest.mock import patch

import pytest

from adversary_pursuit.agent.tools import ToolContext
from adversary_pursuit.core.investigation import (
    ContentClass,
    EventClass,
    LifecycleState,
)
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


def test_async_investigation_streams_lifecycle_events(tmp_path):
    service = _service(tmp_path)
    battery = type("Battery", (), {"tools": ("virustotal_lookup",)})()
    with (
        patch("adversary_pursuit.web.server.dispatch_batteries", return_value=[battery]),
        patch(
            "adversary_pursuit.web.server.execute_tool",
            return_value=("No new service artifacts", None, [], []),
        ),
    ):
        started = service.start_investigation("198.51.100.10")
        cursor = 0
        observed = []
        snapshot = started
        for _ in range(100):
            snapshot = service.investigation_events(started["investigation_id"], cursor)
            cursor = snapshot["cursor"]
            observed.extend(snapshot["events"])
            if snapshot["lifecycle"] in {"succeeded", "empty", "failed", "cancelled"}:
                break
            time.sleep(0.01)

    assert snapshot["lifecycle"] == "empty"
    assert {event["lifecycle"] for event in observed} >= {
        "planned",
        "queued",
        "running",
        "empty",
    }
    assert observed[-1]["reason"] == "no new artifacts stored"


def test_state_labels_instrument_authorities_truthfully(tmp_path):
    instruments = _service(tmp_path).state()["instruments"]

    assert instruments["local_api"]["available"] is True
    assert instruments["sources"]["configured"] > 0
    assert instruments["model_tokens"] == {
        "available": False,
        "reason": "no synthesis requested",
    }


def test_evidence_detail_uses_stored_projection_and_redacts_secrets(tmp_path):
    service = _service(tmp_path)
    service.ctx.workspace_mgr.store_stix_objects(
        [{"type": "domain-name", "value": "suspect.test", "api_token": "secret"}],
        module_name="osint/test",
        target="suspect.test",
        source_url="https://source.test/suspect.test",
    )
    reference = service.state()["objects"][0]["reference"]

    detail = service.evidence_detail(reference)

    assert detail["value"] == "suspect.test"
    assert detail["provenance"]["source_url"] == "https://source.test/suspect.test"
    assert detail["raw"]["api_token"] == "[REDACTED]"


def test_attention_records_can_be_acknowledged_without_deletion(tmp_path):
    service = _service(tmp_path)
    record = service.investigations.create("suspect.test", "domain-name")
    event = service.investigations.append(
        record.investigation_id,
        event_class=EventClass.SOURCE_FAULT,
        severity="warning",
        lifecycle=LifecycleState.FAILED,
        content_class=ContentClass.SYSTEM,
        reason="source timed out",
    )

    assert service.alerts()["unread_count"] == 1
    service.acknowledge_alert(event.event_id)
    alerts = service.alerts()

    assert alerts["unread_count"] == 0
    assert len(alerts["alerts"]) == 1
    assert alerts["alerts"][0]["acknowledged"] is True
