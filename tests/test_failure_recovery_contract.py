"""Operational failures remain truthful and leave the local case usable."""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

from adversary_pursuit.agent.tools import ToolContext
from adversary_pursuit.core.workspace_admin import export_workspace
from adversary_pursuit.web.server import WebCockpitService


def _service(tmp_path) -> WebCockpitService:
    return WebCockpitService(
        ToolContext(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
        )
    )


def _wait_for_terminal(service: WebCockpitService, investigation_id: str) -> dict:
    for _ in range(500):
        snapshot = service.investigation_events(investigation_id)
        if snapshot["lifecycle"] in {"succeeded", "empty", "failed", "cancelled"}:
            return snapshot
        time.sleep(0.005)
    raise AssertionError("investigation did not reach a terminal state")


def test_network_failure_is_failed_retryable_and_does_not_damage_local_evidence(tmp_path) -> None:
    service = _service(tmp_path)
    service.ctx.workspace_mgr.store_stix_objects(
        [{"type": "domain-name", "value": "preserved.example"}],
        module_name="local/preexisting",
        target="preserved.example",
    )
    battery = type("Battery", (), {"tools": ("virustotal_lookup",)})()

    with (
        patch("adversary_pursuit.web.server.dispatch_batteries", return_value=[battery]),
        patch(
            "adversary_pursuit.web.server.execute_tool",
            side_effect=ConnectionError("provider network unavailable"),
        ),
    ):
        started = service.start_investigation("198.51.100.44")
        failed = _wait_for_terminal(service, started["investigation_id"])

    assert failed["lifecycle"] == "failed"
    source_fault = next(
        event for event in failed["events"] if event["event_class"] == "source_fault"
    )
    assert source_fault["retryable"] is True
    assert source_fault["actions"] == ("retry", "details")
    assert "network unavailable" in source_fault["reason"]
    assert [item["value"] for item in service.ctx.workspace_mgr.get_stix_objects()] == [
        "preserved.example"
    ]

    service.ctx.workspace_mgr.add_note("Local analysis continued after provider loss.")
    portable = export_workspace(service.ctx.workspace_mgr, "default")
    assert portable["tables"]["notes"][0]["content"] == (
        "Local analysis continued after provider loss."
    )
    assert service.state()["workspace"] == "default"

    with (
        patch("adversary_pursuit.web.server.dispatch_batteries", return_value=[battery]),
        patch(
            "adversary_pursuit.web.server.execute_tool",
            return_value=("No new provider artifacts", None, [], []),
        ),
    ):
        retried = service.start_investigation("198.51.100.44")
        recovered = _wait_for_terminal(service, retried["investigation_id"])
    assert recovered["lifecycle"] == "empty"


def test_cancellation_during_final_active_enrichment_finishes_cancelled(tmp_path) -> None:
    service = _service(tmp_path)
    battery = type("Battery", (), {"tools": ("virustotal_lookup",)})()
    active = threading.Event()
    release = threading.Event()

    def controlled_enrichment(*_args, **_kwargs):
        active.set()
        assert release.wait(timeout=5)
        return "No new provider artifacts", None, [], []

    with (
        patch("adversary_pursuit.web.server.dispatch_batteries", return_value=[battery]),
        patch("adversary_pursuit.web.server.execute_tool", side_effect=controlled_enrichment),
    ):
        started = service.start_investigation("198.51.100.45")
        assert active.wait(timeout=5)
        acknowledged = service.cancel_investigation(started["investigation_id"])
        assert acknowledged["lifecycle"] == "running"
        assert acknowledged["cancel_requested"] is True
        release.set()
        cancelled = _wait_for_terminal(service, started["investigation_id"])

    assert cancelled["lifecycle"] == "cancelled"
    assert any(
        event["summary"] == "Cancellation received; the active enrichment will finish safely."
        for event in cancelled["events"]
    )
