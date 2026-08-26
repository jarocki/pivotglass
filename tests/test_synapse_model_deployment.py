"""Approval, replay, and readback tests for Synapse model deployment."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime

import httpx
import pytest

from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.integrations.synapse_migration import (
    pivotglass_synapse_model_contract,
)
from adversary_pursuit.integrations.synapse_model_deployment import (
    SynapseModelDeployer,
    SynapseModelDeploymentJournal,
    approve_synapse_model_deployment,
    compile_synapse_model_deployment_plan,
    extended_model_contains,
    synapse_model_deployment_confirmation,
)

_BACKUP = "c" * 64


def _response(request: httpx.Request, result: dict | None = None) -> httpx.Response:
    if request.method == "DELETE":
        return httpx.Response(204)
    payload = json.loads(request.content)
    if "id" not in payload:
        return httpx.Response(202, headers={"Mcp-Session-Id": "session-1"})
    return httpx.Response(
        200,
        headers={"content-type": "application/json", "Mcp-Session-Id": "session-1"},
        json={"jsonrpc": "2.0", "id": payload["id"], "result": result or {}},
    )


def _model_result() -> dict:
    contract = pivotglass_synapse_model_contract().model_definition
    forms = {definition[0]: {"props": {}} for definition in contract["forms"]}
    for form_name, prop_name, *_definition in contract["props"]:
        forms[form_name]["props"][prop_name] = {}
    return {"forms": forms}


def _approval(plan, now):
    return approve_synapse_model_deployment(
        plan,
        backup_receipt_sha256=_BACKUP,
        approved_by="analyst@example.test",
        confirmation=synapse_model_deployment_confirmation(plan),
        now=now,
    )


def test_model_deployment_is_exact_approved_read_back_and_replay_protected(tmp_path):
    plan = compile_synapse_model_deployment_plan()
    now = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
    deployed = False
    calls: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal deployed
        payload = json.loads(request.content) if request.content else {}
        if payload.get("method") == "tools/list":
            tools = ["call_storm", "model_find", "storm_validate"]
            return _response(request, {"tools": [{"name": item} for item in tools]})
        if payload.get("method") != "tools/call":
            return _response(request)
        name = payload["params"]["name"]
        arguments = payload["params"]["arguments"]
        calls.append((name, arguments))
        if name == "storm_validate":
            result = {"valid": True}
        elif name == "call_storm" and "model.ext.add" in arguments["query"]:
            deployed = True
            result = {"added": True}
        elif name == "call_storm":
            result = (
                copy.deepcopy(pivotglass_synapse_model_contract().model_definition)
                if deployed
                else {"version": [1, 0]}
            )
        elif name == "model_find":
            result = _model_result()
        else:
            raise AssertionError(name)
        return _response(request, {"structuredContent": result})

    manager = WorkspaceManager(tmp_path)
    manager.create("case")
    manager.switch("case")
    deployer = SynapseModelDeployer(
        "https://synapse.test/api/v1/mcp",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    stored = deployer.execute(
        plan,
        _approval(plan, now),
        journal=SynapseModelDeploymentJournal(manager),
        now=now,
    )

    assert stored["state"] == "complete"
    assert stored["receipt"]["changed"] is True
    assert stored["receipt"]["exact_readback"] is True
    assert len([call for call in calls if call[0] == "call_storm"]) == len(plan.operations) + 2
    with pytest.raises(ValueError, match="already claimed"):
        deployer.execute(
            plan,
            _approval(plan, now),
            journal=SynapseModelDeploymentJournal(manager),
            now=now,
        )


def test_model_deployment_plan_and_approval_reject_drift():
    first = compile_synapse_model_deployment_plan()
    second = compile_synapse_model_deployment_plan()
    assert first == second
    assert first.execution_enabled is False
    assert first.global_model_mutation is True
    assert first.backup_required is True
    assert first.operations[0].expected_item[0].startswith("_")
    assert extended_model_contains(
        pivotglass_synapse_model_contract().model_definition,
        pivotglass_synapse_model_contract(),
    )

    with pytest.raises(ValueError, match="confirmation"):
        approve_synapse_model_deployment(
            first,
            backup_receipt_sha256=_BACKUP,
            approved_by="analyst",
            confirmation="yes",
        )
    with pytest.raises(ValueError, match="backup receipt"):
        approve_synapse_model_deployment(
            first,
            backup_receipt_sha256="missing",
            approved_by="analyst",
            confirmation=synapse_model_deployment_confirmation(first),
        )


def test_model_deployment_failure_is_non_replayable(tmp_path):
    plan = compile_synapse_model_deployment_plan()
    now = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content) if request.content else {}
        if payload.get("method") == "tools/list":
            tools = ["call_storm", "model_find", "storm_validate"]
            return _response(request, {"tools": [{"name": item} for item in tools]})
        if payload.get("method") != "tools/call":
            return _response(request)
        name = payload["params"]["name"]
        arguments = payload["params"]["arguments"]
        if name == "storm_validate":
            result = {"valid": True}
        elif name == "call_storm" and "model.ext.add" in arguments["query"]:
            result = {"added": True}
        elif name == "call_storm":
            result = {"version": [1, 0]}
        else:
            raise AssertionError(name)
        return _response(request, {"structuredContent": result})

    manager = WorkspaceManager(tmp_path)
    manager.create("case")
    manager.switch("case")
    journal = SynapseModelDeploymentJournal(manager)
    deployer = SynapseModelDeployer(
        "https://synapse.test/api/v1/mcp",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RuntimeError, match="readback"):
        deployer.execute(plan, _approval(plan, now), journal=journal, now=now)
    assert journal.get(plan.digest_sha256)["state"] == "outcome_uncertain"
