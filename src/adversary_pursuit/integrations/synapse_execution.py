"""Approval-gated Synapse migration execution in isolated shadow views."""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict

from adversary_pursuit.integrations.execution_journal import IntegrationExecutionJournal
from adversary_pursuit.integrations.mcp import StreamableHttpMcpClient
from adversary_pursuit.integrations.synapse import _storm_page, _validation_ok
from adversary_pursuit.integrations.synapse_migration import (
    SynapseMigrationPlan,
    SynapseStormOperation,
    pivotglass_synapse_model_contract,
)

_SYNAPSE_IDEN = re.compile(r"[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_REQUIRED_TOOLS = frozenset(
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


class SynapseShadowApproval(BaseModel):
    """Short-lived approval bound to a plan, parent view, and backup receipt."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-synapse-shadow-approval-1.0"] = (
        "pivotglass-synapse-shadow-approval-1.0"
    )
    plan_digest_sha256: str
    parent_view: str
    backup_receipt_sha256: str
    approved_by: str
    approved_at: datetime
    expires_at: datetime
    confirmation_sha256: str


class SynapseOperationReceipt(BaseModel):
    """Secret-safe receipt for one validated Storm operation."""

    model_config = ConfigDict(frozen=True)

    operation_id: str
    phase: Literal["write", "readback"]
    manifest_ref: str
    messages: int
    response_sha256: str
    reconciled: bool | None = None


class SynapseShadowReceipt(BaseModel):
    """Completed isolated load receipt; it never authorizes a parent merge."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-synapse-shadow-receipt-1.0"] = (
        "pivotglass-synapse-shadow-receipt-1.0"
    )
    workspace: str
    plan_digest_sha256: str
    manifest_digest_sha256: str
    model_digest_sha256: str
    parent_view: str
    shadow_view: str
    backup_receipt_sha256: str
    approved_by: str
    started_at: datetime
    completed_at: datetime
    operations: tuple[SynapseOperationReceipt, ...]
    model_verified: Literal[True] = True
    complete: Literal[True] = True
    reconciled: Literal[True] = True
    merged: Literal[False] = False


class SynapseShadowJournal(IntegrationExecutionJournal):
    """Workspace-owned one-shot journal for isolated Synapse shadow loads."""

    def __init__(self, workspace_manager: Any) -> None:
        super().__init__(workspace_manager, system="synapse", operation="shadow_load")


def synapse_shadow_confirmation(plan: SynapseMigrationPlan, parent_view: str) -> str:
    """Return the exact confirmation phrase for one plan and parent view."""
    _validate_view(parent_view)
    return f"APPROVE SYNAPSE SHADOW LOAD {plan.digest_sha256[:16]} INTO FORK OF {parent_view}"


def approve_synapse_shadow_load(
    plan: SynapseMigrationPlan,
    *,
    parent_view: str,
    backup_receipt_sha256: str,
    approved_by: str,
    confirmation: str,
    now: datetime | None = None,
) -> SynapseShadowApproval:
    """Create a short-lived approval for an exact isolated-view load."""
    _validate_view(parent_view)
    if _SHA256.fullmatch(backup_receipt_sha256) is None:
        raise ValueError("Synapse shadow load requires a SHA-256 backup receipt")
    normalized_approver = approved_by.strip()
    if not normalized_approver or len(normalized_approver) > 254:
        raise ValueError("Synapse shadow approval requires a bounded human identity")
    expected = synapse_shadow_confirmation(plan, parent_view)
    if confirmation != expected:
        raise ValueError("Synapse shadow confirmation did not match the current plan")
    approved_at = now or datetime.now(UTC)
    if approved_at.utcoffset() is None:
        raise ValueError("Synapse shadow approval time must include a timezone")
    return SynapseShadowApproval(
        plan_digest_sha256=plan.digest_sha256,
        parent_view=parent_view,
        backup_receipt_sha256=backup_receipt_sha256,
        approved_by=normalized_approver,
        approved_at=approved_at,
        expires_at=approved_at + timedelta(minutes=15),
        confirmation_sha256=hashlib.sha256(confirmation.encode()).hexdigest(),
    )


class SynapseShadowExecutor:
    """Validate and load one plan into a new fork without merging it."""

    def __init__(
        self,
        url: str,
        api_key: str,
        *,
        timeout_seconds: float = 20.0,
        max_pages: int = 10,
        max_records: int = 1000,
        max_elapsed_seconds: float = 30.0,
        allow_insecure_http: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.url = url
        self.max_pages = max_pages
        self.max_records = max_records
        self.max_elapsed_seconds = max_elapsed_seconds
        self._client_args = {
            "headers": {"X-API-KEY": api_key},
            "timeout_seconds": timeout_seconds,
            "allow_insecure_http": allow_insecure_http,
            "transport": transport,
        }

    def execute(
        self,
        plan: SynapseMigrationPlan,
        approval: SynapseShadowApproval,
        *,
        journal: SynapseShadowJournal,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Claim, fork, load, reconcile, and retain an unmerged shadow view."""
        started_at = _validate_approval(plan, approval, now=now)
        shadow_view: str | None = None
        operation_receipts: list[SynapseOperationReceipt] = []
        with StreamableHttpMcpClient(self.url, **self._client_args) as client:
            tools = {str(item.get("name")) for item in client.list_tools()}
            missing_tools = sorted(_REQUIRED_TOOLS - tools)
            if missing_tools:
                raise RuntimeError(
                    "Synapse MCP is missing required shadow-load tools: " + ", ".join(missing_tools)
                )
            verify_synapse_model(client.call_tool("model_find", {"pattern": "^pivotglass:"}))
            journal.claim(
                plan.digest_sha256,
                approved_by=approval.approved_by,
                started_at=started_at,
            )
            try:
                fork = client.call_tool(
                    "view_fork",
                    {
                        "view": approval.parent_view,
                        "name": f"pivotglass-{plan.workspace}-{plan.digest_sha256[:12]}",
                    },
                )
                shadow_view = _fork_view(fork, approval.parent_view)
                completed: set[str] = set()
                operations_by_id = {
                    operation.operation_id: operation for operation in plan.operations
                }
                for operation in plan.operations:
                    if not set(operation.depends_on) <= completed:
                        raise RuntimeError(
                            f"Synapse operation {operation.operation_id} has unmet dependencies"
                        )
                    validation = client.call_tool("storm_validate", {"query": operation.query})
                    if not _validation_ok(validation):
                        raise RuntimeError(f"Synapse rejected operation {operation.operation_id}")
                    messages = self._run_operation(client, operation, shadow_view)
                    reconciled: bool | None = None
                    if operation.phase == "readback":
                        write = operations_by_id[operation.depends_on[0]]
                        reconciled = reconcile_synapse_readback(write, messages)
                        if not reconciled:
                            raise RuntimeError(
                                f"Synapse readback did not reconcile for {write.operation_id}"
                            )
                    operation_receipts.append(
                        SynapseOperationReceipt(
                            operation_id=operation.operation_id,
                            phase=operation.phase,
                            manifest_ref=operation.manifest_ref,
                            messages=len(messages),
                            response_sha256=_digest(messages),
                            reconciled=reconciled,
                        )
                    )
                    completed.add(operation.operation_id)
            except BaseException as exc:
                deleted = False
                if shadow_view is not None:
                    try:
                        result = client.call_tool("view_del", {"view": shadow_view})
                        deleted = isinstance(result, dict) and result.get("deleted") == shadow_view
                    except Exception:
                        deleted = False
                journal.fail(
                    plan.digest_sha256,
                    exc,
                    state="failed_view_removed" if deleted else "outcome_uncertain",
                    receipt={
                        "shadow_view": shadow_view,
                        "view_removed": deleted,
                        "layer_deletion_verified": False,
                        "completed_operation_ids": [
                            item.operation_id for item in operation_receipts
                        ],
                    },
                )
                raise

        if shadow_view is None:
            raise RuntimeError("Synapse shadow load completed without a fork view")
        receipt = SynapseShadowReceipt(
            workspace=plan.workspace,
            plan_digest_sha256=plan.digest_sha256,
            manifest_digest_sha256=plan.manifest_digest_sha256,
            model_digest_sha256=plan.model_digest_sha256,
            parent_view=approval.parent_view,
            shadow_view=shadow_view,
            backup_receipt_sha256=approval.backup_receipt_sha256,
            approved_by=approval.approved_by,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            operations=tuple(operation_receipts),
        )
        return journal.complete(
            plan.digest_sha256,
            receipt=receipt.model_dump(mode="json"),
            completed_at=receipt.completed_at,
        )

    def _run_operation(
        self,
        client: StreamableHttpMcpClient,
        operation: SynapseStormOperation,
        shadow_view: str,
    ) -> list[Any]:
        started = time.monotonic()
        opts = {**operation.opts, "view": shadow_view, "vars": operation.variables}
        result = client.call_tool("storm", {"query": operation.query, "opts": opts})
        pages = 0
        messages: list[Any] = []
        cursor: str | None = None
        try:
            while True:
                pages += 1
                page, cursor = _storm_page(result)
                messages.extend(page)
                if len(messages) > self.max_records:
                    raise RuntimeError("Synapse shadow operation exceeded its record budget")
                if pages > self.max_pages:
                    raise RuntimeError("Synapse shadow operation exceeded its page budget")
                if time.monotonic() - started > self.max_elapsed_seconds:
                    raise RuntimeError("Synapse shadow operation exceeded its time budget")
                if not cursor:
                    return messages
                result = client.call_tool("storm_continue", {"cursor": cursor})
        finally:
            if cursor:
                try:
                    client.call_tool("storm_cancel", {"cursor": cursor})
                except Exception:
                    pass


def _validate_approval(
    plan: SynapseMigrationPlan,
    approval: SynapseShadowApproval,
    *,
    now: datetime | None,
) -> datetime:
    current_time = now or datetime.now(UTC)
    if current_time.utcoffset() is None:
        raise ValueError("Synapse shadow execution time must include a timezone")
    if approval.plan_digest_sha256 != plan.digest_sha256:
        raise ValueError("Synapse approval is bound to a different migration plan")
    if current_time > approval.expires_at:
        raise ValueError("Synapse shadow approval has expired")
    if len(plan.operations) > 10_000:
        raise ValueError("Synapse migration plan exceeds the operation safety limit")
    return current_time


def _validate_view(view: str) -> None:
    if _SYNAPSE_IDEN.fullmatch(view) is None:
        raise ValueError("Synapse view must be a 32-character lowercase hex iden")


def _fork_view(result: Any, parent_view: str) -> str:
    if not isinstance(result, dict) or result.get("parent") != parent_view:
        raise RuntimeError("Synapse returned an invalid fork result")
    view = result.get("view")
    if not isinstance(view, str):
        raise RuntimeError("Synapse fork result did not include a view iden")
    _validate_view(view)
    if view == parent_view:
        raise RuntimeError("Synapse fork did not create an isolated child view")
    return view


def verify_synapse_model(value: Any) -> None:
    """Verify the deployed model exposes every required custom form property."""
    if not isinstance(value, dict) or not isinstance(value.get("forms"), dict):
        raise RuntimeError("Synapse did not return a model definition")
    actual_forms = value["forms"]
    contract = pivotglass_synapse_model_contract()
    for form_name, _form_info, properties in contract.model_definition["forms"]:
        actual = actual_forms.get(form_name)
        if not isinstance(actual, dict) or not isinstance(actual.get("props"), dict):
            raise RuntimeError(f"Synapse model is missing required form {form_name}")
        actual_props = actual["props"]
        for prop_name, *_definition in properties:
            if prop_name not in actual_props:
                raise RuntimeError(
                    f"Synapse model form {form_name} is missing property {prop_name}"
                )


def reconcile_synapse_readback(write: SynapseStormOperation, messages: list[Any]) -> bool:
    """Compare one readback node and its properties with the exact write."""
    nodes = [node for message in messages if (node := _node(message)) is not None]
    expected_form, expected_value = _expected_ndef(write)
    matching = [
        metadata
        for form, value, metadata in nodes
        if form == expected_form and _normalized(value) == _normalized(expected_value)
    ]
    if len(matching) != 1:
        return False
    if expected_form not in {"pivotglass:record", "pivotglass:edge"}:
        return True
    props = matching[0].get("props", {})
    if not isinstance(props, dict):
        return False
    for variable, property_name in _property_mapping(expected_form).items():
        if variable not in write.variables:
            continue
        if _normalized(props.get(property_name)) != _normalized(write.variables[variable]):
            return False
    return True


def _node(message: Any) -> tuple[str, Any, dict[str, Any]] | None:
    if not isinstance(message, (list, tuple)) or len(message) != 2 or message[0] != "node":
        return None
    info = message[1]
    if not isinstance(info, (list, tuple)) or len(info) != 2:
        return None
    ndef, metadata = info
    if not isinstance(ndef, (list, tuple)) or len(ndef) != 2 or not isinstance(metadata, dict):
        return None
    return str(ndef[0]), ndef[1], metadata


def _expected_ndef(write: SynapseStormOperation) -> tuple[str, Any]:
    if write.operation_id.startswith("synapse-native-"):
        form = write.query.lstrip("[ ").split("=", 1)[0].strip()
        return form, write.variables["pivotglass_value"]
    if write.operation_id.startswith("synapse-record-"):
        return "pivotglass:record", write.variables["record_id"]
    if write.operation_id.startswith("synapse-edge-"):
        return "pivotglass:edge", write.variables["edge_guid"]
    raise ValueError("unsupported Synapse write operation")


def _property_mapping(form: str) -> dict[str, str]:
    common = {
        "workspace": "workspace",
        "source_snapshot": "source:snapshot",
    }
    if form == "pivotglass:record":
        return {
            **common,
            "source_value": "source:value",
            "source_node": "node",
            "layers": "layers",
            "kinds": "kinds",
            "labels": "labels",
            "record_refs": "record:refs",
            "states": "states",
            "source_node_ids": "source:node:ids",
        }
    return {
        **common,
        "manifest_ref": "manifest:ref",
        "source": "source",
        "target": "target",
        "relationship": "relationship",
        "truth_kind": "truth:kind",
        "provenance_refs": "provenance:refs",
        "rationale": "rationale",
        "directed": "directed",
    }


def _normalized(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_normalized(item) for item in value]
    if isinstance(value, list):
        return [_normalized(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalized(item) for key, item in value.items()}
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
