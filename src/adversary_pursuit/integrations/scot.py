"""Read-only Sandia SCOT4 MCP adapter."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import httpx

from adversary_pursuit.integrations.contracts import (
    ExternalReference,
    IntegrationRecord,
    QueryReceipt,
)
from adversary_pursuit.integrations.mcp import StreamableHttpMcpClient

SCOT_OBJECT_TYPES = frozenset(
    {
        "alert", "alertgroup", "dispatch", "entity", "event", "file", "guide",
        "incident", "intel", "product", "signature", "entity_class", "entity_type",
        "source", "tag", "feed", "pivot", "vuln_feed", "vuln_track",
    }
)


class ScotMcpAdapter:
    """Bounded SCOT4 reads; this adapter intentionally exposes no write call."""

    def __init__(
        self,
        url: str,
        api_key: str,
        *,
        timeout_seconds: float = 20.0,
        max_pages: int = 10,
        max_records: int = 1000,
        allow_insecure_http: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.url = url
        self.max_pages = max_pages
        self.max_records = max_records
        self._client_args = {
            "headers": {"Authorization": f"Bearer {api_key}"},
            "timeout_seconds": timeout_seconds,
            "allow_insecure_http": allow_insecure_http,
            "transport": transport,
        }

    def status(self) -> dict[str, Any]:
        with StreamableHttpMcpClient(self.url, **self._client_args) as client:
            tools = sorted(str(item.get("name")) for item in client.list_tools())
        return {"system": "sandia-scot4", "connected": True, "tools": tools}

    def get(self, object_type: str, object_id: str) -> dict[str, Any]:
        _check_type(object_type)
        numeric_id = _object_id(object_id)
        with StreamableHttpMcpClient(self.url, **self._client_args) as client:
            value = client.call_tool(
                "get_object", {"object_type": object_type, "object_id": numeric_id}
            )
        record = _record(value, object_type, self.url)
        return _envelope(
            [record] if record else [],
            "get_object",
            {"object_type": object_type, "id": numeric_id},
        )

    def search(
        self,
        object_type: str,
        *,
        filters: dict[str, Any] | None = None,
        page_size: int = 100,
        sort: str | None = "-modified",
    ) -> dict[str, Any]:
        _check_type(object_type)
        if page_size < 1 or page_size > 100:
            raise ValueError("SCOT page size must be between 1 and 100")
        started = datetime.now(UTC)
        request_basis = json.dumps(
            {"type": object_type, "filters": filters or {}, "sort": sort}, sort_keys=True
        )
        records: list[IntegrationRecord] = []
        pages = 0
        total: int | None = None
        boundary_reason: str | None = None
        with StreamableHttpMcpClient(self.url, **self._client_args) as client:
            while pages < self.max_pages and len(records) < self.max_records:
                result = client.call_tool(
                    "search_objects",
                    {
                        "object_type": object_type,
                        "filters": filters or {},
                        "skip": pages * page_size,
                        "limit": min(page_size, self.max_records - len(records)),
                        "sort": sort,
                    },
                )
                pages += 1
                if not isinstance(result, dict):
                    break
                total = int(result.get("totalCount", 0))
                items = result.get("result", [])
                if not isinstance(items, list):
                    items = []
                records.extend(
                    record for item in items if (record := _record(item, object_type, self.url))
                )
                if not items or len(records) >= total:
                    break
            if total is not None and len(records) < total:
                boundary_reason = (
                    "record_budget" if len(records) >= self.max_records else "page_budget"
                )
        receipt = QueryReceipt(
            system="sandia-scot4",
            operation="search_objects",
            request_sha256=hashlib.sha256(request_basis.encode()).hexdigest(),
            started_at=started,
            completed_at=datetime.now(UTC),
            pages=pages,
            records=len(records),
            complete=boundary_reason is None,
            boundary_reason=boundary_reason,
        )
        return {
            "schema_version": "pivotglass-integration-1.0",
            "authority": "remote-preview",
            "records": [item.model_dump(mode="json") for item in records],
            "receipt": receipt.model_dump(mode="json"),
        }

    def entries(self, object_type: str, object_id: str, *, entry_type: str = "all") -> Any:
        _check_type(object_type)
        numeric_id = _object_id(object_id)
        if entry_type not in {"plain", "flaired", "all"}:
            raise ValueError("entry type must be plain, flaired, or all")
        with StreamableHttpMcpClient(self.url, **self._client_args) as client:
            result = client.call_tool(
                "get_object_entries",
                {
                    "object_type": object_type,
                    "object_id": numeric_id,
                    "skip": 0,
                    "limit": min(self.max_records, 100),
                    "entry_type": entry_type,
                },
            )
        return _related_envelope("get_object_entries", object_type, numeric_id, self.url, result)

    def entities(self, object_type: str, object_id: str) -> Any:
        _check_type(object_type)
        numeric_id = _object_id(object_id)
        with StreamableHttpMcpClient(self.url, **self._client_args) as client:
            result = client.call_tool(
                "read_entities", {"object_type": object_type, "object_id": numeric_id}
            )
        return _related_envelope("read_entities", object_type, numeric_id, self.url, result)


def _check_type(object_type: str) -> None:
    if object_type not in SCOT_OBJECT_TYPES:
        raise ValueError(f"unsupported SCOT4 object type: {object_type}")


def _object_id(value: str) -> int:
    try:
        object_id = int(value)
    except ValueError:
        raise ValueError("SCOT4 object ID must be an integer") from None
    if object_id < 1:
        raise ValueError("SCOT4 object ID must be positive")
    return object_id


def _record(value: Any, object_type: str, endpoint: str) -> IntegrationRecord | None:
    if not isinstance(value, dict):
        return None
    object_id = str(value.get("id") or value.get("_id") or "")
    if not object_id:
        return None
    revision_value = value.get("data_ver", value.get("modified"))
    revision = str(revision_value) if revision_value is not None else None
    label = value.get("value") or value.get("subject") or value.get("name") or object_id
    tag_values = value.get("tags", [])
    tags = [str(item.get("name", item)) if isinstance(item, dict) else str(item) for item in tag_values]
    permissions = value.get("permissions", [])
    safe_properties = {
        key: item for key, item in value.items()
        if key not in {"permissions", "entries", "body", "content"}
    }
    remote_id = f"scot4:{object_type}:{object_id}"
    return IntegrationRecord(
        external_id=remote_id,
        entity_type=object_type,
        value=str(label),
        properties=safe_properties,
        tags=sorted(set(tags)),
        references=[
            ExternalReference(
                system="sandia-scot4",
                object_type=object_type,
                object_id=object_id,
                revision=revision,
                endpoint=endpoint,
                permissions=[str(item) for item in permissions],
            )
        ],
        conflict_key=f"sandia-scot4:{object_type}:{object_id}:{revision or 'unversioned'}",
    )


def _envelope(records: list[IntegrationRecord], operation: str, request: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(UTC)
    receipt = QueryReceipt(
        system="sandia-scot4",
        operation=operation,
        request_sha256=hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest(),
        started_at=now,
        completed_at=now,
        pages=1,
        records=len(records),
    )
    return {
        "schema_version": "pivotglass-integration-1.0",
        "authority": "remote-preview",
        "records": [item.model_dump(mode="json") for item in records],
        "receipt": receipt.model_dump(mode="json"),
    }


def _related_envelope(
    operation: str,
    object_type: str,
    object_id: int,
    endpoint: str,
    data: Any,
) -> dict[str, Any]:
    """Wrap entry/entity content with its remote parent and read receipt."""
    now = datetime.now(UTC)
    request = {"object_type": object_type, "object_id": object_id}
    result_count = data.get("resultCount", 0) if isinstance(data, dict) else 0
    receipt = QueryReceipt(
        system="sandia-scot4",
        operation=operation,
        request_sha256=hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest(),
        started_at=now,
        completed_at=now,
        pages=1,
        records=int(result_count),
    )
    parent = ExternalReference(
        system="sandia-scot4",
        object_type=object_type,
        object_id=str(object_id),
        endpoint=endpoint,
    )
    return {
        "schema_version": "pivotglass-integration-1.0",
        "authority": "remote-preview",
        "parent_reference": parent.model_dump(mode="json"),
        "data": data,
        "receipt": receipt.model_dump(mode="json"),
    }
