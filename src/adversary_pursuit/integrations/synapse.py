"""Read-only Vertex Synapse MCP adapter."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from adversary_pursuit.integrations.contracts import (
    ExternalReference,
    IntegrationRecord,
    QueryReceipt,
)
from adversary_pursuit.integrations.mapping import synapse_lift
from adversary_pursuit.integrations.mcp import StreamableHttpMcpClient


class SynapseMcpAdapter:
    """Budgeted Synapse MCP reads; Storm mutations are disabled by policy and opts."""

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

    def status(self) -> dict[str, Any]:
        with StreamableHttpMcpClient(self.url, **self._client_args) as client:
            tools = sorted(str(item.get("name")) for item in client.list_tools())
        return {"system": "vertex-synapse", "connected": True, "tools": tools}

    def model_find(self, pattern: str) -> Any:
        with StreamableHttpMcpClient(self.url, **self._client_args) as client:
            return client.call_tool("model_find", {"pattern": pattern})

    def query(
        self,
        storm: str,
        *,
        variables: dict[str, Any] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        started = datetime.now(UTC)
        monotonic_start = time.monotonic()
        request_basis = json.dumps(
            {"storm": storm, "variables": variables or {}}, sort_keys=True, default=str
        )
        request_hash = hashlib.sha256(request_basis.encode()).hexdigest()
        pages = 0
        messages: list[Any] = []
        cursor: str | None = None
        was_cancelled = False
        boundary_reason: str | None = None
        with StreamableHttpMcpClient(self.url, **self._client_args) as client:
            validation = client.call_tool("storm_validate", {"query": storm})
            if not _validation_ok(validation):
                raise ValueError("Synapse rejected the Storm query during validation")
            result = client.call_tool(
                "storm",
                {"query": storm, "opts": {"readonly": True, "vars": variables or {}}},
            )
            while True:
                pages += 1
                page_messages, cursor = _storm_page(result)
                remaining = self.max_records - len(messages)
                if len(page_messages) > remaining:
                    boundary_reason = "record_budget"
                messages.extend(page_messages[: max(remaining, 0)])
                if boundary_reason:
                    if cursor:
                        client.call_tool("storm_cancel", {"cursor": cursor})
                        was_cancelled = True
                    break
                if not cursor:
                    break
                if cancelled and cancelled():
                    boundary_reason = "operator_cancelled"
                elif pages >= self.max_pages:
                    boundary_reason = "page_budget"
                elif len(messages) >= self.max_records:
                    boundary_reason = "record_budget"
                elif time.monotonic() - monotonic_start >= self.max_elapsed_seconds:
                    boundary_reason = "time_budget"
                if boundary_reason:
                    client.call_tool("storm_cancel", {"cursor": cursor})
                    was_cancelled = True
                    break
                result = client.call_tool("storm_continue", {"cursor": cursor})
        records = [record for message in messages if (record := _node_record(message, self.url))]
        receipt = QueryReceipt(
            system="vertex-synapse",
            operation="readonly_storm",
            request_sha256=request_hash,
            started_at=started,
            completed_at=datetime.now(UTC),
            pages=pages,
            records=len(records),
            validated=True,
            cancelled=was_cancelled,
            complete=boundary_reason is None and cursor is None,
            boundary_reason=boundary_reason,
        )
        return {
            "schema_version": "pivotglass-integration-1.0",
            "authority": "remote-preview",
            "records": [item.model_dump(mode="json") for item in records],
            "receipt": receipt.model_dump(mode="json"),
        }

    def lookup(self, indicator_type: str, value: str) -> dict[str, Any]:
        """Lift one normalized Pivotglass indicator without interpolating it into Storm."""
        lift = synapse_lift(indicator_type, value)
        result = self.query(lift.query, variables=lift.variables)
        result["mapping"] = {
            "source_type": indicator_type,
            "synapse_form": lift.form,
            "normalized_value": lift.value,
        }
        return result


def _validation_ok(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        if value.get("valid") is False or value.get("ok") is False:
            return False
        return not bool(value.get("errors"))
    return True


def _storm_page(value: Any) -> tuple[list[Any], str | None]:
    if not isinstance(value, dict):
        return [], None
    messages = value.get("messages", [])
    return (messages if isinstance(messages, list) else []), value.get("cursor")


def _node_record(message: Any, endpoint: str) -> IntegrationRecord | None:
    if not isinstance(message, (list, tuple)) or len(message) != 2 or message[0] != "node":
        return None
    info = message[1]
    if not isinstance(info, (list, tuple)) or len(info) != 2:
        return None
    node, metadata = info
    if not isinstance(node, (list, tuple)) or len(node) != 2 or not isinstance(metadata, dict):
        return None
    form, value = str(node[0]), node[1]
    rendered = json.dumps(value, sort_keys=True, default=str) if not isinstance(value, str) else value
    node_id = str(metadata.get("iden") or hashlib.sha256(f"{form}:{rendered}".encode()).hexdigest())
    revision = str(metadata.get("props", {}).get(".updated") or "") or None
    tags = sorted(str(tag) for tag in metadata.get("tags", {}))
    return IntegrationRecord(
        external_id=f"synapse:{node_id}",
        entity_type=form,
        value=rendered,
        properties={
            "props": metadata.get("props", {}),
            "tagprops": metadata.get("tagprops", {}),
        },
        tags=tags,
        references=[
            ExternalReference(
                system="vertex-synapse",
                object_type=form,
                object_id=node_id,
                revision=revision,
                endpoint=endpoint,
            )
        ],
        conflict_key=f"vertex-synapse:{node_id}:{revision or 'unversioned'}",
    )
