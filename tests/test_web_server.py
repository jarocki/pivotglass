"""Tests for the loopback Pivotglass API adapter."""

import base64
import json
import socket
import threading
import time
from datetime import UTC, datetime
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import MagicMock, patch

import pytest

from adversary_pursuit.agent.tools import ToolContext
from adversary_pursuit.core.analytic_ledger import AnalyticLedger
from adversary_pursuit.core.investigation import (
    ContentClass,
    EventClass,
    LifecycleState,
)
from adversary_pursuit.integrations.scot_pivot_intake import ScotPivotAuthenticationReceipt
from adversary_pursuit.integrations.scot_publication import validate_scot_pivot_request
from adversary_pursuit.web.server import WebCockpitService, _handler, _tool_failure


def _service(tmp_path) -> WebCockpitService:
    ctx = ToolContext(
        config_dir=tmp_path / "config",
        workspace_dir=tmp_path / "workspaces",
    )
    return WebCockpitService(ctx)


def _post_json(
    server: ThreadingHTTPServer,
    path: str,
    payload: dict,
    *,
    content_type: str = "application/json",
    origin: str | None = None,
    sec_fetch_site: str | None = None,
) -> tuple[int, dict]:
    body = json.dumps(payload).encode()
    headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
    if origin is not None:
        headers["Origin"] = origin
    if sec_fetch_site is not None:
        headers["Sec-Fetch-Site"] = sec_fetch_site
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request("POST", path, body, headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def _post_raw_json(
    server: ThreadingHTTPServer,
    path: str,
    body: bytes,
) -> tuple[int, dict]:
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request(
            "POST",
            path,
            body,
            {"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def _raw_post_status(
    server: ThreadingHTTPServer, *content_lengths: str, body: bytes = b""
) -> int:
    length_headers = "".join(
        f"Content-Length: {content_length}\r\n" for content_length in content_lengths
    )
    request = (
        "POST /api/command HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{server.server_port}\r\n"
        "Content-Type: application/json\r\n"
        f"{length_headers}"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")
    with socket.create_connection(("127.0.0.1", server.server_port), timeout=2) as client:
        client.settimeout(2)
        client.sendall(request + body)
        status_line = client.recv(256).split(b"\r\n", 1)[0]
    return int(status_line.split()[1])


@pytest.mark.parametrize(
    "command",
    [
        "integration synapse model-deploy-execute plan backup analyst | APPROVE",
        "integration synapse shadow-execute parent plan backup analyst | APPROVE",
        "integration scot publish-execute owner plan analyst | APPROVE",
    ],
)
def test_browser_command_endpoint_rejects_cross_site_remote_mutations(tmp_path, command):
    service = _service(tmp_path)
    service.execute_command = MagicMock(return_value={"ok": True})
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(service, tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    payload = {"command": command, "workspace": "default"}

    try:
        status, error = _post_json(
            server,
            "/api/command",
            payload,
            content_type="text/plain",
            origin="https://attacker.example",
        )
        assert status == 415
        assert error == {"error": "same-origin application/json required"}

        status, error = _post_json(
            server,
            "/api/command",
            payload,
            origin="https://attacker.example",
        )
        assert status == 403
        assert error == {"error": "same-origin application/json required"}

        status, error = _post_json(
            server,
            "/api/command",
            payload,
            sec_fetch_site="cross-site",
        )
        assert status == 403
        assert error == {"error": "same-origin application/json required"}
        service.execute_command.assert_not_called()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_browser_command_endpoint_preserves_same_origin_and_native_json_clients(tmp_path):
    service = _service(tmp_path)
    service.execute_command = MagicMock(return_value={"ok": True})
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(service, tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    payload = {"command": "model show", "workspace": "default"}

    try:
        status, result = _post_json(
            server,
            "/api/command",
            payload,
            origin=f"http://127.0.0.1:{server.server_port}",
        )
        assert status == 202
        assert result == {"ok": True}

        status, result = _post_json(server, "/api/command", payload)
        assert status == 202
        assert result == {"ok": True}
        assert service.execute_command.call_count == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("content_lengths", [("-1",), ("+1",), ("1.0",), ("0", "0")])
def test_web_endpoint_rejects_invalid_content_length_without_waiting_for_eof(
    tmp_path, content_lengths
):
    service = _service(tmp_path)
    service.execute_command = MagicMock(return_value={"ok": True})
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(service, tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        assert _raw_post_status(server, *content_lengths) == 400
        status, result = _post_json(
            server,
            "/api/command",
            {"command": "model show", "workspace": "default"},
        )
        assert status == 202
        assert result == {"ok": True}
        service.execute_command.assert_called_once()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_web_endpoint_preserves_valid_content_length_with_optional_whitespace(tmp_path):
    service = _service(tmp_path)
    service.execute_command = MagicMock(return_value={"ok": True})
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(service, tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        assert _raw_post_status(server, "2 \t", body=b"{}") == 202
        service.execute_command.assert_called_once_with("")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_document_preview_endpoint_is_local_bounded_and_non_mutating(tmp_path):
    service = _service(tmp_path)
    html = b"<h1>Source report</h1><script>exfiltrate()</script><p>198.51.100.8</p>"

    result = service.preview_document(
        {
            "filename": "../report.html",
            "media_type": "text/html",
            "content_base64": base64.b64encode(html).decode(),
        }
    )

    assert result["filename"] == "report.html"
    assert result["state"] == "parsed"
    assert "198.51.100.8" in result["output_text"]
    assert "exfiltrate" not in result["output_text"]
    assert "not proof" in result["truth_boundary"]
    assert result["entity_extraction"]["candidate_count"] == 1
    candidate = result["entity_extraction"]["candidates"][0]
    assert candidate["normalized_value"] == "198.51.100.8"
    assert candidate["start_line"] == 2
    assert "not stored evidence" in result["entity_extraction"]["truth_boundary"]
    assert service.ctx.workspace_mgr.get_workspace_table_counts()["document_occurrences"] == 0


@pytest.mark.parametrize("filename", ["deep.json", "deep.jsonl"])
def test_document_preview_endpoint_bounds_deep_json_and_remains_available(
    tmp_path, filename
):
    service = _service(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(service, tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    deep_document = b"[" * 2_000 + b"0" + b"]" * 2_000

    try:
        status, result = _post_json(
            server,
            "/api/documents/preview",
            {
                "filename": filename,
                "content_base64": base64.b64encode(deep_document).decode(),
            },
        )
        assert status == 200
        assert result["state"] == "failed"
        assert result["output_text"] == ""
        assert any("nesting-depth limit" in error for error in result["errors"])

        status, control = _post_json(
            server,
            "/api/documents/preview",
            {
                "filename": "ordinary.json",
                "content_base64": base64.b64encode(b'{"ip":"198.51.100.8"}').decode(),
            },
        )
        assert status == 200
        assert control["state"] == "parsed"
        assert control["entity_extraction"]["candidate_count"] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_document_preview_endpoint_bounds_deep_request_envelope_and_recovers(tmp_path):
    service = _service(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(service, tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # Python 3.14's JSON decoder tolerates substantially deeper input than
    # earlier supported runtimes. This remains below the route's byte cap while
    # crossing the decoder's own stack boundary on every supported runtime.
    deep_envelope = (
        b'{"unused":' + b"[" * 1_000_000 + b"0" + b"]" * 1_000_000 + b"}"
    )

    try:
        status, error = _post_raw_json(
            server,
            "/api/documents/preview",
            deep_envelope,
        )
        assert status == 400
        assert error == {"error": "request JSON exceeds the supported nesting depth"}

        status, control = _post_json(
            server,
            "/api/documents/preview",
            {
                "filename": "ordinary.json",
                "content_base64": base64.b64encode(b'{"domain":"example.test"}').decode(),
            },
        )
        assert status == 200
        assert control["state"] == "parsed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_document_preview_endpoint_rejects_invalid_base64(tmp_path):
    service = _service(tmp_path)

    with pytest.raises(ValueError, match="not valid base64"):
        service.preview_document(
            {
                "filename": "report.txt",
                "content_base64": "this is not base64",
            }
        )


def test_graph_annotation_service_requires_current_node_and_preserves_truth_class(tmp_path):
    service = _service(tmp_path)
    service.ctx.workspace_mgr.store_stix_objects(
        [{"type": "ipv4-addr", "value": "198.51.100.77"}],
        module_name="test/graph-annotation",
        target="198.51.100.77",
    )
    node_ref = next(iter(service._graph_presentation_scope()[0]))

    result = service.annotate_graph(
        {"node_ref": node_ref, "text": "Compare this address with prior incidents."}
    )

    assert result["saved"] is True
    assert result["annotation"]["node_ref"] == node_ref
    assert result["annotation"]["evidence"] is False
    assert service.graph_annotations(node_ref)["annotations"] == [result["annotation"]]


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
        "how_are_values_distributed",
        "are_numeric_features_correlated",
        "how_does_this_hierarchy_divide",
        "what_likelihood_and_confidence_are_recorded",
        "which_evidence_supports_or_contradicts_hypotheses",
        "which_evidence_types_are_stored",
        "which_entities_relate",
        "which_indicator_enrichment_work_is_pending",
    }
    assert all(intent["schema_version"] == "1.0" for intent in state["visualizations"])
    assert state["analysis"]["information_requirements"]["policy"]["id"] == (
        "pivotglass-information-value-v1"
    )
    assert state["analysis"]["information_requirements"]["requirements"] == []
    assert state["analysis"]["rigor"]["policy"]["id"] == "analytic-rigor-v1"
    assert state["analysis"]["rigor"]["contradiction_candidates"] == []
    assert state["pursuit_brief"]["policy"]["id"] == "pivotglass-pursuit-brief-v1"
    assert state["pursuit_brief"]["next_action"]["id"] == "frame_question"
    assert state["pursuit_brief"]["progress"][0]["label"] == "Evidence coverage"
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
    assert (
        next(item for item in payload["providers"] if item["id"] == "openai")["credential_source"]
        == "config"
    )
    assert (
        next(item for item in payload["services"] if item["id"] == "virustotal")[
            "credential_source"
        ]
        == "config"
    )


def test_configuration_update_enables_and_disables_without_deleting_key(tmp_path):
    service = _service(tmp_path)
    service.config_mgr.set("api_keys.virustotal", "stored-key")

    result = service.update_configuration(
        {"action": "service-enabled", "id": "virustotal", "enabled": False}
    )

    assert result["saved"] is True
    assert service.config_mgr.is_service_enabled("virustotal") is False
    assert service.config_mgr.get_api_key("virustotal") == "stored-key"


def test_model_catalog_returns_live_models_with_capability_caveats(tmp_path, monkeypatch):
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


def test_scot_pivot_enqueue_uses_shared_enrichment_lifecycle(tmp_path):
    service = _service(tmp_path)
    command = (
        "integration scot pivot-enqueue event 42 198.51.100.42 | "
        "scot-analyst@example.test | Follow the event relationship. | local-analyst"
    )
    with patch("adversary_pursuit.web.server.dispatch_batteries", return_value=[]):
        result = service.execute_command(command)

    assert result["data"]["created"] is True
    assert result["data"]["start_enrichment"] is False
    assert result["data"]["investigation"]["target"] == "198.51.100.42"
    request_id = result["data"]["request"]["request_id"]
    queue_item = next(
        item
        for item in AnalyticLedger(service.ctx.workspace_mgr).enrichment_requests()
        if item["record_id"] == request_id
    )
    for _ in range(100):
        if queue_item["criteria"]["queue_state"] == "empty":
            break
        time.sleep(0.01)
        queue_item = next(
            item
            for item in AnalyticLedger(service.ctx.workspace_mgr).enrichment_requests()
            if item["record_id"] == request_id
        )

    assert queue_item["criteria"]["queue_state"] == "empty"
    assert [event["state"] for event in queue_item["criteria"]["history"]] == [
        "queued",
        "running",
        "empty",
    ]
    assert queue_item["evidence_refs"] == [{"kind": "scot-object", "ref": "event:42"}]
    listed = service.execute_command("integration scot pivot-queue")["data"]
    assert [item["record_id"] for item in listed] == [request_id]
    assert service.state()["analysis"]["enrichment_queue"][0]["record_id"] == request_id
    assert service.execute_command(command)["data"]["created"] is False


def test_authenticated_scot_inbox_acceptance_starts_shared_lifecycle_once(tmp_path):
    service = _service(tmp_path)
    now = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    request = validate_scot_pivot_request(
        workspace="default",
        scot_object_type="event",
        scot_object_id=42,
        scot_revision="7",
        indicator="198.51.100.42",
        requested_by="scot-analyst@example.test",
        requested_at=now,
        reason="Follow the event relationship.",
    )
    received = service.receive_scot_pivot_request(
        request.model_dump(mode="json"),
        ScotPivotAuthenticationReceipt(
            key_id="scot4-primary",
            signed_at=now,
            authenticated_at=now,
            body_sha256="a" * 64,
            nonce_sha256="b" * 64,
            maximum_clock_skew_seconds=300,
        ),
    )
    command = (
        f"integration scot pivot-accept {received['request']['request_id']} | "
        "local-analyst | In scope for this hunt."
    )

    with patch("adversary_pursuit.web.server.dispatch_batteries", return_value=[]):
        accepted = service.execute_command(command)
        repeated = service.execute_command(command)

    assert received["created"] is True
    assert received["enqueued"] is False
    assert accepted["data"]["created"] is True
    assert accepted["data"]["start_enrichment"] is False
    assert accepted["data"]["investigation"]["target"] == "198.51.100.42"
    assert repeated["data"]["created"] is False
    assert repeated["data"]["start_enrichment"] is False
    assert "investigation" not in repeated["data"]
    assert len(AnalyticLedger(service.ctx.workspace_mgr).enrichment_requests()) == 1


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
        "[USER_SAW_PANEL] [API key] Configure the source credential, then retry. (diag cafe1234)"
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
    assert activity["registry"]["authorities"][0]["authority"] == ("Pivotglass workspace database")


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
    assert any(item["command"].startswith("framework show") for item in help_result["commands"])
    assert any(item["command"].startswith("framework require") for item in help_result["commands"])
    assert any(item["command"] == "framework gaps" for item in help_result["commands"])


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


def test_web_framework_lens_polls_counts_and_requires_explicit_detail(tmp_path):
    service = _service(tmp_path)
    service.ctx.workspace_mgr.store_stix_objects(
        [{"type": "domain-name", "value": "framework.test"}],
        module_name="osint/test",
        target="framework.test",
    )
    observation_id = service.ctx.workspace_mgr.get_observations()[0]["id"]
    proposed = service.execute_command(
        f"framework map attack 19.2 T1003 {observation_id} | OS Credential Dumping | "
        "Source-backed behavior. | moderate | One source; corroboration remains open."
    )

    assert proposed["kind"] == "json"
    assert proposed["data"]["evidence_refs"] == [observation_id]
    state = service.state()
    assert state["frameworks"]["counts"]["attack"] == {"proposed": 1}
    assert "mappings" not in state["frameworks"]
    shown = service.execute_command("framework show attack")
    assert shown["data"]["mappings"][0]["content_id"] == "T1003"


def test_web_records_framework_gap_through_shared_requirement_authority(tmp_path):
    service = _service(tmp_path)
    result = service.execute_command(
        "framework require attack 19.2 T1059 | Command and Scripting Interpreter | "
        "Collect evidence relevant to command execution. | "
        '{"decision_impact":4,"discriminating_power":3,'
        '"time_sensitivity":2,"feasibility":3}'
    )
    priorities = service.execute_command("analysis priorities")
    gaps = service.execute_command("framework gaps")

    assert result["kind"] == "json"
    assert result["data"]["created"] is True
    assert priorities["data"]["requirements"][0]["id"] == result["data"]["item_id"]
    assert (
        priorities["data"]["requirements"][0]["criteria"]["addresses"][0]["id"]
        == "attack:19.2:T1059"
    )
    assert gaps["data"]["requirements"][0]["record_kind"] == "framework_gap"


def test_web_exposes_two_layer_graph_only_on_explicit_command(tmp_path):
    service = _service(tmp_path)
    service.ctx.workspace_mgr.store_stix_objects(
        [{"type": "domain-name", "value": "layers.test"}],
        module_name="osint/test",
        target="layers.test",
    )

    result = service.execute_command("graph layers")
    assert result["kind"] == "json"
    assert result["data"]["schema_version"] == "investigation-graph-1.0"
    assert result["data"]["counts"]["nodes"] == {"entity": 1, "epistemic": 1}
    assert all(edge["provenance_refs"] for edge in result["data"]["edges"])


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
    assert deleted["data"] == {
        "workspace": "source",
        "deleted": {"sqlite_files": 1, "raw_document_files": 0},
    }


def test_workspace_clear_requires_exact_confirmation_and_preserves_workspace(tmp_path):
    service = _service(tmp_path)
    service.ctx.workspace_mgr.store_stix_objects(
        [{"type": "domain-name", "value": "clear.test"}],
        module_name="osint/test",
        target="clear.test",
    )

    with pytest.raises(ValueError, match="clear <name> --confirm <name>"):
        service.execute_command("workspace clear default")

    result = service.execute_command("workspace clear default --confirm default")

    assert result["title"] == "Workspace cleared"
    assert result["data"]["workspace"] == "default"
    assert result["data"]["cleared"]["stix_objects"] == 1
    assert service.ctx.workspace_mgr.list_workspaces() == ["default"]
    assert service.ctx.workspace_mgr.get_stix_objects() == []


def test_workspace_switch_is_blocked_while_investigation_is_active(tmp_path):
    service = _service(tmp_path)
    service.ctx.workspace_mgr.create("other")
    service.investigations.create("198.51.100.8", "ipv4-addr")

    with pytest.raises(ValueError, match="investigation is active"):
        service.execute_command("workspace switch other")

    assert service.ctx.workspace_mgr.active == "default"
