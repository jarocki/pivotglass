"""Approval-gated deployment of Pivotglass's persistent Synapse model."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict

from adversary_pursuit.integrations.execution_journal import IntegrationExecutionJournal
from adversary_pursuit.integrations.mcp import StreamableHttpMcpClient
from adversary_pursuit.integrations.synapse_execution import verify_synapse_model
from adversary_pursuit.integrations.synapse_migration import (
    SynapseModelContract,
    pivotglass_synapse_model_contract,
)

_SHA256 = re.compile(r"[0-9a-f]{64}")
_REQUIRED_TOOLS = frozenset({"call_storm", "model_find", "storm_validate"})
_READBACK_QUERY = "return($lib.model.ext.getExtModel())"


class SynapseModelDeploymentOperation(BaseModel):
    """One bound-variable extended-model operation and its expected item."""

    model_config = ConfigDict(frozen=True)

    operation_id: str
    category: Literal["forms", "props"]
    query: str
    variables: dict[str, Any]
    expected_item: list[Any]


class SynapseModelDeploymentPlan(BaseModel):
    """Deterministic, reviewable global Synapse model mutation."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-synapse-model-deployment-plan-1.0"] = (
        "pivotglass-synapse-model-deployment-plan-1.0"
    )
    model_name: str
    model_version: str
    model_digest_sha256: str
    operations: tuple[SynapseModelDeploymentOperation, ...]
    readback_query: str
    digest_sha256: str
    approval_required: Literal[True] = True
    execution_enabled: Literal[False] = False
    global_model_mutation: Literal[True] = True
    backup_required: Literal[True] = True
    readback_required: Literal[True] = True


class SynapseModelDeploymentApproval(BaseModel):
    """Short-lived approval bound to one model plan and backup receipt."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-synapse-model-deployment-approval-1.0"] = (
        "pivotglass-synapse-model-deployment-approval-1.0"
    )
    plan_digest_sha256: str
    backup_receipt_sha256: str
    approved_by: str
    approved_at: datetime
    expires_at: datetime
    confirmation_sha256: str


class SynapseModelDeploymentReceipt(BaseModel):
    """Secret-safe receipt proving the exact extended model was read back."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-synapse-model-deployment-receipt-1.0"] = (
        "pivotglass-synapse-model-deployment-receipt-1.0"
    )
    plan_digest_sha256: str
    model_digest_sha256: str
    model_version: str
    backup_receipt_sha256: str
    approved_by: str
    started_at: datetime
    completed_at: datetime
    changed: bool
    exact_readback: Literal[True] = True
    runtime_model_verified: Literal[True] = True
    applied_operation_ids: tuple[str, ...]


class SynapseModelDeploymentJournal(IntegrationExecutionJournal):
    """Workspace-owned replay guard for global model deployment."""

    def __init__(self, workspace_manager: Any) -> None:
        super().__init__(workspace_manager, system="synapse", operation="model_deploy")


def compile_synapse_model_deployment_plan() -> SynapseModelDeploymentPlan:
    """Compile the exact extended-model mutation without executing it."""
    contract = pivotglass_synapse_model_contract()
    operations: list[SynapseModelDeploymentOperation] = []
    for form_name, base_type, type_opts, type_info in contract.model_definition["forms"]:
        operations.append(
            SynapseModelDeploymentOperation(
                operation_id=_operation_id("form", form_name),
                category="forms",
                query=(
                    "$lib.model.ext.addForm($form_name, $base_type, "
                    "$type_opts, $type_info)"
                ),
                variables={
                    "form_name": form_name,
                    "base_type": base_type,
                    "type_opts": type_opts,
                    "type_info": type_info,
                },
                expected_item=[form_name, base_type, type_opts, type_info],
            )
        )
    for form_name, prop_name, type_def, prop_info in contract.model_definition["props"]:
        type_name, type_opts = type_def
        operations.append(
            SynapseModelDeploymentOperation(
                operation_id=_operation_id("prop", f"{form_name}:{prop_name}"),
                category="props",
                query=(
                    "$lib.model.ext.addFormProp($form_name, $prop_name, "
                    "($type_name, $type_opts), $prop_info)"
                ),
                variables={
                    "form_name": form_name,
                    "prop_name": prop_name,
                    "type_name": type_name,
                    "type_opts": type_opts,
                    "prop_info": prop_info,
                },
                expected_item=[form_name, prop_name, type_def, prop_info],
            )
        )
    content = {
        "schema_version": "pivotglass-synapse-model-deployment-plan-1.0",
        "model_name": contract.model_name,
        "model_version": contract.model_version,
        "model_digest_sha256": contract.digest_sha256,
        "operations": [operation.model_dump(mode="json") for operation in operations],
        "readback_query": _READBACK_QUERY,
    }
    return SynapseModelDeploymentPlan(
        **content,
        digest_sha256=_digest(content),
    )


def synapse_model_deployment_confirmation(plan: SynapseModelDeploymentPlan) -> str:
    """Return the exact confirmation phrase for one global model plan."""
    return f"APPROVE SYNAPSE MODEL DEPLOY {plan.digest_sha256[:16]}"


def approve_synapse_model_deployment(
    plan: SynapseModelDeploymentPlan,
    *,
    backup_receipt_sha256: str,
    approved_by: str,
    confirmation: str,
    now: datetime | None = None,
) -> SynapseModelDeploymentApproval:
    """Create a 15-minute approval for one exact model deployment."""
    if _SHA256.fullmatch(backup_receipt_sha256) is None:
        raise ValueError("Synapse model deployment requires a SHA-256 backup receipt")
    normalized_approver = approved_by.strip()
    if not normalized_approver or len(normalized_approver) > 254:
        raise ValueError("Synapse model deployment requires a bounded human identity")
    expected = synapse_model_deployment_confirmation(plan)
    if confirmation != expected:
        raise ValueError("Synapse model deployment confirmation did not match the current plan")
    approved_at = now or datetime.now(UTC)
    if approved_at.utcoffset() is None:
        raise ValueError("Synapse model deployment approval time must include a timezone")
    return SynapseModelDeploymentApproval(
        plan_digest_sha256=plan.digest_sha256,
        backup_receipt_sha256=backup_receipt_sha256,
        approved_by=normalized_approver,
        approved_at=approved_at,
        expires_at=approved_at + timedelta(minutes=15),
        confirmation_sha256=hashlib.sha256(confirmation.encode()).hexdigest(),
    )


class SynapseModelDeployer:
    """Validate, deploy, and read back one persistent extended-model plan."""

    def __init__(
        self,
        url: str,
        api_key: str,
        *,
        timeout_seconds: float = 20.0,
        allow_insecure_http: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.url = url
        self._client_args = {
            "headers": {"X-API-KEY": api_key},
            "timeout_seconds": timeout_seconds,
            "allow_insecure_http": allow_insecure_http,
            "transport": transport,
        }

    def execute(
        self,
        plan: SynapseModelDeploymentPlan,
        approval: SynapseModelDeploymentApproval,
        *,
        journal: SynapseModelDeploymentJournal,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Apply an approved model globally and prove exact readback."""
        started_at = _validate_approval(plan, approval, now=now)
        with StreamableHttpMcpClient(self.url, **self._client_args) as client:
            tools = {str(item.get("name")) for item in client.list_tools()}
            missing_tools = sorted(_REQUIRED_TOOLS - tools)
            if missing_tools:
                raise RuntimeError(
                    "Synapse MCP is missing required model-deployment tools: "
                    + ", ".join(missing_tools)
                )
            queries = [operation.query for operation in plan.operations]
            queries.append(plan.readback_query)
            for query in queries:
                validation = client.call_tool("storm_validate", {"query": query})
                if not isinstance(validation, dict) or validation.get("valid") is not True:
                    raise RuntimeError("Synapse rejected the model deployment plan")

            before = client.call_tool(
                "call_storm",
                {"query": plan.readback_query, "opts": {"readonly": True}},
            )
            already_exact = extended_model_contains(before, pivotglass_synapse_model_contract())
            operation_states = [
                (_model_item_state(before, operation.category, operation.expected_item), operation)
                for operation in plan.operations
            ]
            conflicts = [
                operation.operation_id
                for state, operation in operation_states
                if state == "conflict"
            ]
            if conflicts:
                raise RuntimeError(
                    "Synapse extended model conflicts with the deployment plan: "
                    + ", ".join(conflicts)
                )
            pending = [operation for state, operation in operation_states if state == "missing"]
            journal.claim(
                plan.digest_sha256,
                approved_by=approval.approved_by,
                started_at=started_at,
            )
            try:
                for operation in pending:
                    client.call_tool(
                        "call_storm",
                        {
                            "query": operation.query,
                            "opts": {"vars": operation.variables},
                        },
                    )
                after = client.call_tool(
                    "call_storm",
                    {"query": plan.readback_query, "opts": {"readonly": True}},
                )
                contract = pivotglass_synapse_model_contract()
                if not extended_model_contains(after, contract):
                    raise RuntimeError("Synapse extended-model readback did not match the contract")
                runtime = client.call_tool("model_find", {"pattern": "^_pivotglass:"})
                verify_synapse_model(runtime)
            except BaseException as exc:
                journal.fail(
                    plan.digest_sha256,
                    exc,
                    receipt={
                        "model_digest_sha256": plan.model_digest_sha256,
                        "mutation_attempted": bool(pending),
                        "planned_operation_ids": [item.operation_id for item in pending],
                        "rollback_automatic": False,
                    },
                )
                raise

        completed_at = datetime.now(UTC)
        receipt = SynapseModelDeploymentReceipt(
            plan_digest_sha256=plan.digest_sha256,
            model_digest_sha256=plan.model_digest_sha256,
            model_version=plan.model_version,
            backup_receipt_sha256=approval.backup_receipt_sha256,
            approved_by=approval.approved_by,
            started_at=started_at,
            completed_at=completed_at,
            changed=not already_exact,
            applied_operation_ids=tuple(item.operation_id for item in pending),
        )
        return journal.complete(
            plan.digest_sha256,
            receipt=receipt.model_dump(mode="json"),
            completed_at=completed_at,
        )


def extended_model_contains(value: Any, contract: SynapseModelContract) -> bool:
    """Return whether a Cortex extended model contains the exact contract subset."""
    if not isinstance(value, dict) or _normalized(value.get("version")) != [1, 0]:
        return False
    expected = contract.model_definition
    for category in ("types", "forms", "props", "univs", "tagprops", "edges"):
        actual_items = value.get(category, [])
        desired_items = expected.get(category, [])
        if not isinstance(actual_items, (list, tuple)):
            return False
        actual = {_item_key(category, item): _normalized(item) for item in actual_items}
        for item in desired_items:
            key = _item_key(category, item)
            if actual.get(key) != _normalized(item):
                return False
    return True


def _model_item_state(value: Any, category: str, expected_item: list[Any]) -> str:
    """Classify one desired model item as exact, missing, or conflicting."""
    if not isinstance(value, dict):
        return "missing"
    actual_items = value.get(category, [])
    if not isinstance(actual_items, (list, tuple)):
        return "missing"
    expected_key = _item_key(category, expected_item)
    for item in actual_items:
        if _item_key(category, item) == expected_key:
            return "exact" if _normalized(item) == _normalized(expected_item) else "conflict"
    return "missing"


def _item_key(category: str, item: Any) -> str:
    normalized = _normalized(item)
    if not isinstance(normalized, list) or not normalized:
        return _digest(normalized)
    if category == "props" and len(normalized) >= 2:
        return f"{normalized[0]}:{normalized[1]}"
    if category == "edges" and isinstance(normalized[0], list):
        return json.dumps(normalized[0], sort_keys=True, separators=(",", ":"))
    return str(normalized[0])


def _validate_approval(
    plan: SynapseModelDeploymentPlan,
    approval: SynapseModelDeploymentApproval,
    *,
    now: datetime | None,
) -> datetime:
    current_time = now or datetime.now(UTC)
    if current_time.utcoffset() is None:
        raise ValueError("Synapse model deployment time must include a timezone")
    if approval.plan_digest_sha256 != plan.digest_sha256:
        raise ValueError("Synapse model approval is bound to a different deployment plan")
    if current_time > approval.expires_at:
        raise ValueError("Synapse model deployment approval has expired")
    return current_time


def _normalized(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_normalized(item) for item in value]
    if isinstance(value, list):
        return [_normalized(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalized(item) for key, item in sorted(value.items())}
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _operation_id(category: str, value: str) -> str:
    return f"synapse-model-{category}-{_digest(value)[:24]}"
