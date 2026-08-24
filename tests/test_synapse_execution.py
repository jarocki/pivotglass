"""Approval and isolated-view execution contracts for Synapse migration."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.integrations.synapse_execution import (
    SynapseShadowExecutor,
    SynapseShadowJournal,
    approve_synapse_shadow_load,
    synapse_shadow_confirmation,
)
from adversary_pursuit.integrations.synapse_graph import (
    SynapseManifestNode,
    SynapseShadowManifest,
)
from adversary_pursuit.integrations.synapse_migration import (
    compile_synapse_migration_plan,
    pivotglass_synapse_model_contract,
)
from adversary_pursuit.integrations.synapse_model import (
    PIVOTGLASS_RECORD_FORM,
)

_PARENT = "a" * 32
_FORK = "b" * 32
_BACKUP = "c" * 64


def _plan():
    manifest = SynapseShadowManifest(
        workspace="case",
        source_snapshot_sha256="1" * 64,
        nodes=(
            SynapseManifestNode(
                id="synapse-node-test",
                form="inet:fqdn",
                value="example.test",
                source_node_ids=("domain-name--test",),
                properties={
                    "pivotglass:layers": ["entity"],
                    "pivotglass:kinds": ["domain-name"],
                    "pivotglass:labels": ["example.test"],
                    "pivotglass:record_refs": ["domain-name--test"],
                    "pivotglass:states": [],
                },
            ),
        ),
        edges=(),
        digest_sha256="2" * 64,
    )
    return compile_synapse_migration_plan(manifest)


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


def _node_for(arguments: dict, stored_nodes: dict[tuple[str, str], list]) -> list:
    query = arguments["query"]
    variables = arguments["opts"]["vars"]
    if PIVOTGLASS_RECORD_FORM in query:
        key = (PIVOTGLASS_RECORD_FORM, variables["record_id"])
        if "workspace" not in variables:
            return stored_nodes[key]
        props = {
            "workspace": variables["workspace"],
            "source:snapshot": variables["source_snapshot"],
            "source:value": variables["source_value"],
            "node": variables["source_node"],
            "layers": variables["layers"],
            "kinds": variables["kinds"],
            "labels": variables["labels"],
            "record:refs": variables["record_refs"],
            "states": variables["states"],
            "source:node:ids": variables["source_node_ids"],
        }
        node = ["node", [[PIVOTGLASS_RECORD_FORM, variables["record_id"]], {"props": props}]]
        stored_nodes[key] = node
        return node
    return [
        "node",
        [["inet:fqdn", variables["pivotglass_value"]], {"props": {}}],
    ]


def _approval(plan, now):
    return approve_synapse_shadow_load(
        plan,
        parent_view=_PARENT,
        backup_receipt_sha256=_BACKUP,
        approved_by="analyst@example.test",
        confirmation=synapse_shadow_confirmation(plan, _PARENT),
        now=now,
    )


def test_synapse_shadow_load_is_isolated_reconciled_and_never_merged(tmp_path):
    plan = _plan()
    now = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
    calls: list[tuple[str, dict]] = []
    stored_nodes: dict[tuple[str, str], list] = {}
    tools = sorted(
        {
            "model_find",
            "storm",
            "storm_cancel",
            "storm_continue",
            "storm_validate",
            "view_del",
            "view_fork",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content) if request.content else {}
        if payload.get("method") == "tools/list":
            return _response(request, {"tools": [{"name": item} for item in tools]})
        if payload.get("method") != "tools/call":
            return _response(request)
        name = payload["params"]["name"]
        arguments = payload["params"]["arguments"]
        calls.append((name, arguments))
        if name == "model_find":
            result = _model_result()
        elif name == "view_fork":
            result = {"view": _FORK, "parent": _PARENT}
        elif name == "storm_validate":
            result = {"valid": True}
        elif name == "storm":
            result = {"messages": [_node_for(arguments, stored_nodes)], "cursor": None}
        else:
            raise AssertionError(name)
        return _response(request, {"structuredContent": result})

    manager = WorkspaceManager(tmp_path)
    manager.create("case")
    manager.switch("case")
    executor = SynapseShadowExecutor(
        "https://synapse.test/api/v1/mcp",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    stored = executor.execute(
        plan,
        _approval(plan, now),
        journal=SynapseShadowJournal(manager),
        now=now,
    )

    assert stored["state"] == "complete"
    assert stored["receipt"]["shadow_view"] == _FORK
    assert stored["receipt"]["merged"] is False
    assert stored["receipt"]["reconciled"] is True
    assert "view_merge" not in [name for name, _arguments in calls]
    storm_calls = [arguments for name, arguments in calls if name == "storm"]
    assert all(arguments["opts"]["view"] == _FORK for arguments in storm_calls)
    assert any(arguments["opts"]["readonly"] is False for arguments in storm_calls)
    assert any(arguments["opts"]["readonly"] is True for arguments in storm_calls)

    restarted = WorkspaceManager(tmp_path)
    restarted.switch("case")
    with pytest.raises(ValueError, match="already claimed"):
        executor.execute(
            plan,
            _approval(plan, now),
            journal=SynapseShadowJournal(restarted),
            now=now,
        )


def test_synapse_shadow_failure_removes_fork_and_blocks_replay(tmp_path):
    plan = _plan()
    now = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
    calls: list[str] = []
    tools = [
        "model_find",
        "storm",
        "storm_cancel",
        "storm_continue",
        "storm_validate",
        "view_del",
        "view_fork",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content) if request.content else {}
        if payload.get("method") == "tools/list":
            return _response(request, {"tools": [{"name": item} for item in tools]})
        if payload.get("method") != "tools/call":
            return _response(request)
        name = payload["params"]["name"]
        calls.append(name)
        if name == "model_find":
            result = _model_result()
        elif name == "view_fork":
            result = {"view": _FORK, "parent": _PARENT}
        elif name == "storm_validate":
            result = {"valid": False, "mesg": "invalid"}
        elif name == "view_del":
            result = {"deleted": _FORK, "parent": _PARENT}
        else:
            raise AssertionError(name)
        return _response(request, {"structuredContent": result})

    manager = WorkspaceManager(tmp_path)
    manager.create("case")
    manager.switch("case")
    journal = SynapseShadowJournal(manager)
    executor = SynapseShadowExecutor(
        "https://synapse.test/api/v1/mcp",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RuntimeError, match="rejected operation"):
        executor.execute(plan, _approval(plan, now), journal=journal, now=now)
    stored = journal.get(plan.digest_sha256)
    assert stored["state"] == "failed_view_removed"
    assert stored["receipt"]["view_removed"] is True
    assert stored["receipt"]["layer_deletion_verified"] is False
    assert "view_del" in calls
    with pytest.raises(ValueError, match="failed_view_removed"):
        executor.execute(plan, _approval(plan, now), journal=journal, now=now)


def test_synapse_shadow_approval_is_exact_and_requires_backup_receipt():
    plan = _plan()
    now = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="confirmation"):
        approve_synapse_shadow_load(
            plan,
            parent_view=_PARENT,
            backup_receipt_sha256=_BACKUP,
            approved_by="analyst",
            confirmation="yes",
            now=now,
        )
    with pytest.raises(ValueError, match="backup receipt"):
        approve_synapse_shadow_load(
            plan,
            parent_view=_PARENT,
            backup_receipt_sha256="missing",
            approved_by="analyst",
            confirmation=synapse_shadow_confirmation(plan, _PARENT),
            now=now,
        )
