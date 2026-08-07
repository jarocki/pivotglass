"""Tests for the loopback Pivotglass API adapter."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from adversary_pursuit.agent.tools import ToolContext
from adversary_pursuit.core.investigation import (
    ContentClass,
    EventClass,
    LifecycleState,
)
from adversary_pursuit.web.server import WebCockpitService, _tool_failure


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
    assert {intent["question"] for intent in state["visualizations"]} == {
        "when_was_activity_concentrated",
        "how_complete_is_this_dossier",
        "how_complete_are_indicator_investigations",
        "which_evidence_types_are_stored",
        "which_entities_relate",
        "which_indicator_enrichment_work_is_pending",
    }
    assert all(intent["schema_version"] == "1.0" for intent in state["visualizations"])
    assert state["analysis"]["information_requirements"]["policy"]["id"] == (
        "pivotglass-information-value-v1"
    )
    assert state["analysis"]["information_requirements"]["requirements"] == []
    assert len(state["modes"]) == 7
    assert {mode["display_name"] for mode in state["modes"]} == {
        "Default (Analyst)",
        "Chuck Norris",
        "HAL9000",
        "Troll",
        "Sherlock Holmes",
        "Neuromancer",
        "The Matrix",
    }
    m4tr1x = next(mode for mode in state["modes"] if mode["name"] == "m4tr1x")
    assert m4tr1x["theme"]["heading_color"] == "#00ff5f"
    assert m4tr1x["cockpit"]["vehicle"] == "NEBUCHADNEZZAR"


def test_switch_mode_reuses_canonical_character_and_cockpit_authorities(tmp_path):
    service = _service(tmp_path)

    state = service.switch_mode("hal9000")

    assert state["character"] == "the_computer"
    active = next(mode for mode in state["modes"] if mode["name"] == "the_computer")
    assert active["theme"]["heading_color"] == "#ff5555"
    assert active["cockpit"]["hud_title"] == "HAL OPTICS"


def test_completions_match_public_modes_and_workspace_context(tmp_path):
    service = _service(tmp_path)
    service.ctx.workspace_mgr.create("case-red")

    assert service.completions("mode neuro") == ["mode Neuromancer"]
    assert "workspace switch case-red" in service.completions("workspace switch c")
    assert "model check" in service.completions("model ch")
    assert "config disable " in service.completions("config dis")
    assert "analysis priorities" in service.completions("analysis pr")


def test_model_show_and_config_show_are_deterministic_local_commands(tmp_path):
    service = _service(tmp_path)

    model = service.execute_command("model show")
    configuration = service.execute_command("config show")

    assert model["title"] == "Model configuration"
    assert "MODEL CONFIGURATION" in model["text"]
    assert configuration["kind"] == "configuration"
    assert "INTELLIGENCE API CONFIGURATION" in configuration["text"]
    assert service._runner is None


def test_configuration_payload_is_masked(tmp_path):
    service = _service(tmp_path)
    service.config_mgr.set_provider_api_key("openai", "never-return-this")
    service.config_mgr.set("api_keys.virustotal", "also-never-return-this")

    payload = service.configuration()

    assert "never-return-this" not in repr(payload)
    assert "also-never-return-this" not in repr(payload)
    assert next(
        item for item in payload["providers"] if item["id"] == "openai"
    )["credential_source"] == "config"
    assert next(
        item for item in payload["services"] if item["id"] == "virustotal"
    )["credential_source"] == "config"


def test_configuration_update_enables_and_disables_without_deleting_key(tmp_path):
    service = _service(tmp_path)
    service.config_mgr.set("api_keys.virustotal", "stored-key")

    result = service.update_configuration(
        {"action": "service-enabled", "id": "virustotal", "enabled": False}
    )

    assert result["saved"] is True
    assert service.config_mgr.is_service_enabled("virustotal") is False
    assert service.config_mgr.get_api_key("virustotal") == "stored-key"


def test_model_catalog_returns_live_models_with_capability_caveats(
    tmp_path, monkeypatch
):
    service = _service(tmp_path)
    monkeypatch.setattr(
        "adversary_pursuit.agent.model_control.list_models",
        lambda provider, key: ["local-test:8b"],
    )
    monkeypatch.setattr(
        "adversary_pursuit.agent.model_control._capability_info",
        lambda model: {},
    )

    catalog = service.model_catalog("ollama")

    assert catalog["models"][0]["model_id"] == "local-test:8b"
    assert "does not prove" in catalog["models"][0]["limitations"][0]
    assert "not quality rankings" in catalog["notice"]


def test_configuration_advisor_is_character_voice_not_evidence(tmp_path):
    service = _service(tmp_path)
    service.switch_mode("hal9000")

    advisory = service.configuration_advisory()

    assert advisory is not None
    assert advisory["character"] == "the_computer"
    assert advisory["content_class"] == "narration"
    assert advisory["evidence"] is False


def test_switch_mode_synchronizes_existing_agent_runner_persona(tmp_path):
    service = _service(tmp_path)
    service._runner = MagicMock()

    state = service.switch_mode("hal9000")

    mode = service.mode_mgr.active
    service._runner.set_character.assert_called_once_with(mode)
    assert state["character"] == "the_computer"


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

    assert [event["kind"] for event in result["events"]] == ["enrichment", "evidence"]
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


def test_web_activity_turns_tool_failure_receipt_into_sanitized_event(tmp_path):
    service = _service(tmp_path)
    record = service.investigations.create("suspect.test", "domain-name")
    service._tool_schemas = {
        "example_lookup": {
            "name": "example_lookup",
            "parameters": {
                "properties": {"domain": {"type": "string"}},
                "required": ["domain"],
            },
        }
    }
    receipt = (
        "[USER_SAW_PANEL] [API key] Configure the source credential, then retry. "
        "(diag cafe1234)"
    )
    with patch("adversary_pursuit.web.server.execute_tool", return_value=(receipt, None, [], [])):
        service._run_investigation(
            record.investigation_id,
            "suspect.test",
            "domain-name",
            ["example_lookup"],
        )

    activity = service.activity()
    fault = next(event for event in activity["events"] if event["event_class"] == "source_fault")
    assert fault["diagnostic_id"] == "cafe1234"
    assert fault["diagnostic_category"] == "API key"
    assert fault["next_action"] == "Configure the source credential, then retry."
    assert fault["reason"] == "API key failure"
    assert activity["registry"]["authorities"][0]["authority"] == (
        "Pivotglass workspace database"
    )


def test_diagnostic_detail_reads_only_sanitized_fields_from_fixed_log(tmp_path):
    service = _service(tmp_path)
    debug_log = tmp_path / "debug.log"
    debug_log.write_text(
        json.dumps(
            {
                "diagnostic_id": "abcd1234",
                "category": "Network",
                "summary": "The source could not be reached.",
                "exc_type": "ConnectError",
                "exc_str": "https://user:secret@example.test/?token=private",
                "traceback": "/Users/analyst/private/file.py secret",
                "context": {
                    "surface": "agent_execute_tool",
                    "tool": "example_lookup",
                    "target": "private-target.example",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with patch("adversary_pursuit.web.server.DEBUG_LOG_PATH", debug_log):
        detail = service.diagnostic_detail("abcd1234")

    assert detail["log_name"] == "debug.log"
    assert detail["component"] == "example_lookup"
    rendered = json.dumps(detail)
    assert "user:secret" not in rendered
    assert "token=private" not in rendered
    assert "/Users/analyst" not in rendered
    assert "private-target.example" not in rendered
    assert "traceback" not in detail
    with pytest.raises(ValueError, match="invalid diagnostic reference"):
        service.diagnostic_detail("../../debug.log")


def test_tool_failure_parser_rejects_unmarked_results():
    assert _tool_failure("ordinary evidence summary") is None
    assert _tool_failure("Error: provider response was malformed") == {
        "category": "Source",
        "next_action": "provider response was malformed",
        "diagnostic_id": "",
    }


def test_web_command_router_accepts_iocs_commands_and_workspace_queries(tmp_path):
    service = _service(tmp_path)
    battery = type("Battery", (), {"tools": ()})()
    with patch("adversary_pursuit.web.server.dispatch_batteries", return_value=[battery]):
        investigation = service.execute_command("198.51.100.10")

    assert investigation["kind"] == "investigation"
    assert investigation["snapshot"]["target"] == "198.51.100.10"
    help_result = service.execute_command("help")
    assert help_result["kind"] == "commands"
    assert {item["command"] for item in help_result["commands"]} >= {
        "use <indicator>",
        "graph",
        "dossier",
        "timeline",
        "export <json|csv|stix|gexf>",
    }


def test_web_command_router_saves_linkable_notes_and_exports_csv(tmp_path):
    service = _service(tmp_path)
    service.ctx.workspace_mgr.store_stix_objects(
        [{"type": "domain-name", "value": "suspect.test"}],
        module_name="osint/test",
        target="suspect.test",
    )

    note = service.execute_command("note review this pivot")
    exported = service.execute_command("export csv")

    assert note["kind"] == "text"
    assert exported["kind"] == "download"
    assert exported["mime"] == "text/csv"
    assert "suspect.test" in exported["content"]


def test_workspace_commands_create_export_merge_and_confirm_delete(tmp_path):
    service = _service(tmp_path)
    service.execute_command("workspace create source")
    service.ctx.workspace_mgr.store_stix_objects(
        [{"type": "domain-name", "value": "merge.test"}],
        module_name="osint/test",
        target="merge.test",
    )
    service.execute_command("workspace create destination")

    merged = service.execute_command("workspace merge source destination")
    exported = service.execute_command("workspace export destination")
    service.execute_command("workspace switch default")
    deleted = service.execute_command("workspace delete source --confirm source")

    assert merged["data"]["inserted"]["stix_objects"] == 1
    assert "merge.test" in exported["content"]
    assert deleted["title"] == "Workspace deleted"


def test_workspace_switch_is_blocked_while_investigation_is_active(tmp_path):
    service = _service(tmp_path)
    service.ctx.workspace_mgr.create("other")
    service.investigations.create("198.51.100.8", "ipv4-addr")

    with pytest.raises(ValueError, match="investigation is active"):
        service.execute_command("workspace switch other")

    assert service.ctx.workspace_mgr.active == "default"
