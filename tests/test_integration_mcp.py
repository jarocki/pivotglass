"""Protocol and policy tests for the optional Synapse and SCOT4 MCP adapters."""

from __future__ import annotations

import json

import httpx
import pytest

from adversary_pursuit.integrations.mapping import synapse_lift
from adversary_pursuit.integrations.mcp import (
    McpError,
    StreamableHttpMcpClient,
    validated_mcp_url,
)
from adversary_pursuit.integrations.scot import ScotMcpAdapter
from adversary_pursuit.integrations.synapse import SynapseMcpAdapter


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


class _CountingStream(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.yielded = 0
        self.closed = False

    def __iter__(self):
        for chunk in self.chunks:
            self.yielded += 1
            yield chunk

    def close(self) -> None:
        self.closed = True


def test_mcp_url_rejects_credentials_and_public_cleartext():
    with pytest.raises(ValueError):
        validated_mcp_url("https://user:secret@example.test/mcp")
    with pytest.raises(ValueError):
        validated_mcp_url("http://example.test/mcp")
    assert validated_mcp_url("http://127.0.0.1:9999/mcp") == "http://127.0.0.1:9999/mcp"


def test_client_initializes_session_and_reads_structured_tool_result():
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content) if request.content else {}
        requests.append(payload)
        if payload.get("method") == "tools/call":
            return _response(request, {"structuredContent": {"answer": 42}})
        return _response(request)

    with StreamableHttpMcpClient(
        "https://synapse.test/api/v1/mcp", transport=httpx.MockTransport(handler)
    ) as client:
        assert client.call_tool("example", {}) == {"answer": 42}

    assert requests[0]["method"] == "initialize"
    assert requests[1]["method"] == "notifications/initialized"
    assert requests[2]["params"]["name"] == "example"


def test_client_stops_reading_before_oversized_response_is_fully_buffered():
    stream = _CountingStream([b"x" * 700, b"y" * 700, b"z" * 700])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            stream=stream,
        )

    client = StreamableHttpMcpClient(
        "https://synapse.test/api/v1/mcp",
        max_response_bytes=1_000,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(McpError, match="size limit"):
            client.request("tools/list")
    finally:
        client.close()

    assert stream.yielded == 2
    assert stream.closed is True


def test_client_rejects_compressed_response_before_expansion_and_cleans_session():
    stream = _CountingStream([b"compressed-body-must-not-be-read"])
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "DELETE":
            return httpx.Response(204)
        assert request.headers["Accept-Encoding"] == "identity"
        return httpx.Response(
            200,
            headers={
                "content-type": "application/json",
                "content-encoding": "gzip",
                "Mcp-Session-Id": "session-oversized",
            },
            stream=stream,
        )

    with pytest.raises(McpError, match="size limit"):
        with StreamableHttpMcpClient(
            "https://synapse.test/api/v1/mcp",
            max_response_bytes=1_000,
            transport=httpx.MockTransport(handler),
        ):
            pass

    assert stream.yielded == 0
    assert stream.closed is True
    assert methods == ["POST", "DELETE"]


def test_synapse_queries_are_validated_readonly_and_cancelled_at_budget():
    calls: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content) if request.content else {}
        if payload.get("method") != "tools/call":
            return _response(request)
        params = payload["params"]
        calls.append((params["name"], params["arguments"]))
        if params["name"] == "storm_validate":
            result = {"valid": True}
        elif params["name"] == "storm":
            result = {
                "messages": [
                    ["node", [["inet:fqdn", "example.test"], {"iden": "node-1", "props": {}}]]
                ],
                "cursor": "cursor-1",
            }
        elif params["name"] == "storm_cancel":
            result = {"cancelled": True}
        else:
            raise AssertionError(params["name"])
        return _response(request, {"structuredContent": result})

    adapter = SynapseMcpAdapter(
        "https://synapse.test/api/v1/mcp",
        "secret",
        max_pages=1,
        transport=httpx.MockTransport(handler),
    )
    result = adapter.query("inet:fqdn=example.test")

    storm_args = dict(calls)["storm"]
    assert storm_args["opts"] == {"readonly": True, "vars": {}}
    assert [name for name, _ in calls] == ["storm_validate", "storm", "storm_cancel"]
    assert result["authority"] == "remote-preview"
    assert result["receipt"]["cancelled"] is True
    assert result["receipt"]["boundary_reason"] == "page_budget"
    assert result["records"][0]["external_id"] == "synapse:node-1"


def test_synapse_indicator_mapping_normalizes_and_uses_bound_variables():
    lift = synapse_lift("domain-name", "Exämple.COM.")

    assert lift.form == "inet:fqdn"
    assert lift.value == "xn--exmple-cua.com"
    assert lift.query == "inet:fqdn=$pivotglass_value"
    assert lift.value not in lift.query
    assert lift.variables == {"pivotglass_value": "xn--exmple-cua.com"}

    with pytest.raises(ValueError):
        synapse_lift("sha256", "not-a-digest")


def test_synapse_views_returns_default_and_readable_views():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content) if request.content else {}
        if payload.get("method") != "tools/call":
            return _response(request)
        name = payload["params"]["name"]
        calls.append(name)
        result = (
            {"view": "a" * 32}
            if name == "view_get"
            else {"views": [{"iden": "a" * 32, "name": "main", "parent": None}]}
        )
        return _response(request, {"structuredContent": result})

    adapter = SynapseMcpAdapter(
        "https://synapse.test/api/v1/mcp",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    result = adapter.views()

    assert result["default_view"] == "a" * 32
    assert result["views"][0]["name"] == "main"
    assert calls == ["view_get", "view_list"]


def test_scot_search_is_bounded_and_preserves_revision_permissions():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content) if request.content else {}
        if payload.get("method") != "tools/call":
            return _response(request)
        arguments = payload["params"]["arguments"]
        calls.append(arguments)
        result = {
            "totalCount": 2,
            "resultCount": 1,
            "result": [
                {
                    "id": arguments["skip"] + 10,
                    "subject": "Example incident",
                    "data_ver": arguments["skip"] + 3,
                    "permissions": ["analysts"],
                    "tags": [{"name": "apt"}],
                }
            ],
        }
        return _response(request, {"structuredContent": result})

    adapter = ScotMcpAdapter(
        "https://scot.test/mcp",
        "secret",
        max_pages=1,
        transport=httpx.MockTransport(handler),
    )
    result = adapter.search("incident", filters={"modified": "2026-08-01"}, page_size=1)

    assert calls[0]["object_type"] == "incident"
    assert result["receipt"]["complete"] is False
    assert result["receipt"]["boundary_reason"] == "page_budget"
    record = result["records"][0]
    assert record["conflict_key"] == "sandia-scot4:incident:10:3"
    assert record["references"][0]["permissions"] == ["analysts"]
    assert "permissions" not in record["properties"]


def test_scot_related_content_has_parent_provenance_and_receipt():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content) if request.content else {}
        if payload.get("method") != "tools/call":
            return _response(request)
        return _response(
            request,
            {"structuredContent": {"totalCount": 1, "resultCount": 1, "result": [{"id": 7}]}},
        )

    adapter = ScotMcpAdapter(
        "https://scot.test/mcp",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    result = adapter.entities("incident", "12")

    assert result["authority"] == "remote-preview"
    assert result["parent_reference"]["object_type"] == "incident"
    assert result["parent_reference"]["object_id"] == "12"
    assert result["receipt"]["operation"] == "read_entities"
    assert result["receipt"]["records"] == 1
