"""Approval-gated SCOT4 REST publication with mandatory reconciliation."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, ConfigDict

from adversary_pursuit.integrations.execution_journal import IntegrationExecutionJournal
from adversary_pursuit.integrations.scot_publication import (
    ScotWriteOperation,
    ScotWritePlan,
)

_PATH_REFERENCE = re.compile(r"\{result:([A-Za-z0-9-]+):([A-Za-z0-9_-]+)\}")


class ScotPublicationApproval(BaseModel):
    """Short-lived approval bound to one exact publication plan digest."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-scot-approval-1.0"] = "pivotglass-scot-approval-1.0"
    plan_digest_sha256: str
    approved_by: str
    approved_at: datetime
    expires_at: datetime
    confirmation_sha256: str


class ScotOperationReceipt(BaseModel):
    """Secret-safe receipt for one remote write or readback."""

    model_config = ConfigDict(frozen=True)

    operation_id: str
    phase: Literal["write", "readback"]
    method: Literal["GET", "POST"]
    path_template: str
    status_code: int
    response_sha256: str
    remote_id: str | None = None
    reconciled: bool | None = None


class ScotPublicationReceipt(BaseModel):
    """Authoritative completion receipt emitted only after every readback matches."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-scot-publication-receipt-1.0"] = (
        "pivotglass-scot-publication-receipt-1.0"
    )
    publication_id: str
    workspace: str
    plan_digest_sha256: str
    approved_by: str
    started_at: datetime
    completed_at: datetime
    operations: tuple[ScotOperationReceipt, ...]
    complete: Literal[True] = True
    reconciled: Literal[True] = True


def scot_confirmation(plan: ScotWritePlan) -> str:
    """Return the exact human confirmation phrase for one plan."""
    return f"APPROVE SCOT PUBLICATION {plan.digest_sha256[:16]}"


def approve_scot_publication(
    plan: ScotWritePlan,
    *,
    approved_by: str,
    confirmation: str,
    now: datetime | None = None,
) -> ScotPublicationApproval:
    """Create a short-lived approval only after exact phrase confirmation."""
    normalized_approver = approved_by.strip()
    if not normalized_approver or len(normalized_approver) > 254:
        raise ValueError("SCOT approval requires a bounded human identity")
    if confirmation != scot_confirmation(plan):
        raise ValueError("SCOT publication confirmation did not match the current plan")
    approved_at = now or datetime.now(UTC)
    if approved_at.utcoffset() is None:
        raise ValueError("SCOT approval time must include a timezone")
    return ScotPublicationApproval(
        plan_digest_sha256=plan.digest_sha256,
        approved_by=normalized_approver,
        approved_at=approved_at,
        expires_at=approved_at + timedelta(minutes=15),
        confirmation_sha256=hashlib.sha256(confirmation.encode()).hexdigest(),
    )


def validate_scot_approval(
    plan: ScotWritePlan,
    approval: ScotPublicationApproval,
    *,
    now: datetime | None = None,
) -> datetime:
    """Validate that an approval is current and bound to this exact plan."""
    current_time = now or datetime.now(UTC)
    if current_time.utcoffset() is None:
        raise ValueError("SCOT publication time must include a timezone")
    if approval.plan_digest_sha256 != plan.digest_sha256:
        raise ValueError("SCOT approval is bound to a different publication plan")
    if current_time > approval.expires_at:
        raise ValueError("SCOT publication approval has expired")
    if len(plan.operations) > 10_000:
        raise ValueError("SCOT publication plan exceeds the operation safety limit")
    return current_time


class ScotPublicationJournal(IntegrationExecutionJournal):
    """Workspace-owned one-shot claim and receipt authority for SCOT writes."""

    def __init__(self, workspace_manager: Any) -> None:
        super().__init__(workspace_manager, system="scot", operation="publish")

    def claim(
        self,
        plan: ScotWritePlan,
        approval: ScotPublicationApproval,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Atomically claim an exact plan before its first remote mutation."""
        started_at = validate_scot_approval(plan, approval, now=now)
        return super().claim(
            plan.digest_sha256,
            approved_by=approval.approved_by,
            started_at=started_at,
        )

    def complete(self, receipt: ScotPublicationReceipt) -> dict[str, Any]:
        """Persist the reconciled receipt for an existing one-shot claim."""
        return super().complete(
            receipt.plan_digest_sha256,
            receipt=receipt.model_dump(mode="json"),
            completed_at=receipt.completed_at,
        )

    def mark_uncertain(self, plan_digest_sha256: str, error: BaseException) -> None:
        """Block replay when a remote mutation may have partially completed."""
        self.fail(plan_digest_sha256, error)


def execute_scot_publication(
    plan: ScotWritePlan,
    approval: ScotPublicationApproval,
    *,
    publisher: ScotRestPublisher,
    journal: ScotPublicationJournal,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Claim, execute once, reconcile, and durably receipt one publication."""
    current_time = validate_scot_approval(plan, approval, now=now)
    journal.claim(plan, approval, now=current_time)
    try:
        receipt = publisher.publish(plan, approval, now=current_time)
    except BaseException as exc:
        journal.mark_uncertain(plan.digest_sha256, exc)
        raise
    return journal.complete(receipt)


class ScotRestPublisher:
    """Execute one approved plan once; never retries remote mutations."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 20.0,
        max_response_bytes: int = 4_000_000,
        allow_insecure_http: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_url = _validated_api_url(api_url, allow_insecure_http=allow_insecure_http).rstrip(
            "/"
        )
        self.max_response_bytes = max_response_bytes
        self._client = httpx.Client(
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ScotRestPublisher:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def publish(
        self,
        plan: ScotWritePlan,
        approval: ScotPublicationApproval,
        *,
        now: datetime | None = None,
    ) -> ScotPublicationReceipt:
        """Execute once and fail closed on any response or reconciliation mismatch."""
        current_time = validate_scot_approval(plan, approval, now=now)

        started_at = current_time
        results: dict[str, dict[str, Any]] = {}
        operations_by_id = {operation.operation_id: operation for operation in plan.operations}
        receipts: list[ScotOperationReceipt] = []
        for operation in plan.operations:
            missing = [item for item in operation.depends_on if item not in results]
            if missing:
                raise ValueError(f"SCOT operation {operation.operation_id} has unmet dependencies")
            path = _resolve_path(operation.path_template, results)
            body = _resolve_value(operation.body, results) if operation.body is not None else None
            status_code, response = self._request(operation, path, body)
            reconciled: bool | None = None
            if operation.phase == "readback":
                write = operations_by_id[operation.depends_on[0]]
                reconciled = _reconcile(write, response, results)
                if not reconciled:
                    raise RuntimeError(f"SCOT readback did not reconcile for {write.operation_id}")
            results[operation.operation_id] = response
            receipts.append(
                ScotOperationReceipt(
                    operation_id=operation.operation_id,
                    phase=operation.phase,
                    method=operation.method,
                    path_template=operation.path_template,
                    status_code=status_code,
                    response_sha256=_digest(response),
                    remote_id=str(response.get("id")) if response.get("id") is not None else None,
                    reconciled=reconciled,
                )
            )
        return ScotPublicationReceipt(
            publication_id=plan.publication_id,
            workspace=plan.workspace,
            plan_digest_sha256=plan.digest_sha256,
            approved_by=approval.approved_by,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            operations=tuple(receipts),
        )

    def _request(
        self,
        operation: ScotWriteOperation,
        path: str,
        body: dict[str, Any] | None,
    ) -> tuple[int, dict[str, Any]]:
        url = f"{self.api_url}{path}"
        try:
            kwargs = {"json": body} if body is not None else {}
            response = self._client.request(operation.method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"SCOT publication transport failed for {operation.operation_id} "
                f"({type(exc).__name__})"
            ) from None
        if response.status_code not in operation.expected_status:
            raise RuntimeError(
                f"SCOT publication operation {operation.operation_id} returned "
                f"HTTP {response.status_code}"
            )
        if len(response.content) > self.max_response_bytes:
            raise RuntimeError("SCOT publication response exceeded the configured size limit")
        try:
            value = response.json()
        except (json.JSONDecodeError, ValueError):
            raise RuntimeError("SCOT publication returned malformed JSON") from None
        if not isinstance(value, dict):
            raise RuntimeError("SCOT publication response was not an object")
        return response.status_code, value


def _validated_api_url(url: str, *, allow_insecure_http: bool) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("SCOT API URL must be an absolute http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("SCOT API URL cannot contain credentials, a query, or a fragment")
    if parsed.scheme == "http" and not allow_insecure_http:
        if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("unencrypted SCOT publication is restricted to loopback")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))


def _resolve_path(path: str, results: dict[str, dict[str, Any]]) -> str:
    def replace(match: re.Match[str]) -> str:
        value = _result_field(results, match.group(1), match.group(2))
        if not isinstance(value, (str, int)) or not str(value).isdigit():
            raise ValueError("SCOT path result reference did not resolve to a numeric ID")
        return str(value)

    resolved = _PATH_REFERENCE.sub(replace, path)
    if "{" in resolved or "}" in resolved or not resolved.startswith("/"):
        raise ValueError("SCOT publication path contains an unresolved reference")
    return resolved


def _resolve_value(value: Any, results: dict[str, dict[str, Any]]) -> Any:
    if isinstance(value, dict):
        if set(value) == {"$result"}:
            reference = value["$result"]
            if not isinstance(reference, dict):
                raise ValueError("invalid SCOT result reference")
            return _result_field(
                results,
                str(reference.get("operation_id", "")),
                str(reference.get("field", "")),
            )
        return {key: _resolve_value(item, results) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_value(item, results) for item in value]
    return value


def _result_field(results: dict[str, dict[str, Any]], operation_id: str, field: str) -> Any:
    response = results.get(operation_id)
    if response is None or field not in response:
        raise ValueError(f"unresolved SCOT result reference: {operation_id}.{field}")
    return response[field]


def _reconcile(
    write: ScotWriteOperation,
    observed: dict[str, Any],
    results: dict[str, dict[str, Any]],
) -> bool:
    expected = _resolve_value(write.body, results) if write.body is not None else {}
    if write.path_template == "/tag/tag_by_name":
        expected_name = expected.get("tag_name")
        tags = observed.get("tags", [])
        names = {str(item.get("name")) if isinstance(item, dict) else str(item) for item in tags}
        return expected_name in names
    if write.path_template == "/entity/":
        expected = expected.get("entity", {})
    comparable = {
        key: value
        for key, value in expected.items()
        if key not in {"permissions", "create_flair_regex"} and value is not None
    }
    return all(
        _normalized_json(observed.get(key)) == _normalized_json(value)
        for key, value in comparable.items()
    )


def _normalized_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
