"""Small Streamable HTTP MCP client for trusted local integrations."""

from __future__ import annotations

import ipaddress
import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx


class McpError(RuntimeError):
    """Sanitized MCP transport or protocol failure."""


def validated_mcp_url(url: str, *, allow_insecure_http: bool = False) -> str:
    """Validate an MCP endpoint without retaining credentials or query data."""
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("MCP URL must be an absolute http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("MCP URL cannot contain credentials, a query, or a fragment")
    if parsed.scheme == "http" and not allow_insecure_http:
        host = parsed.hostname.casefold()
        loopback = host == "localhost"
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            pass
        if not loopback:
            raise ValueError("unencrypted MCP is restricted to loopback unless explicitly enabled")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))


class StreamableHttpMcpClient:
    """Synchronous MCP session with bounded responses and no secret echoing."""

    def __init__(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float = 20.0,
        max_response_bytes: int = 4_000_000,
        allow_insecure_http: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.url = validated_mcp_url(url, allow_insecure_http=allow_insecure_http)
        self._max_response_bytes = max_response_bytes
        base_headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        base_headers.update(headers or {})
        self._client = httpx.Client(
            timeout=timeout_seconds,
            headers=base_headers,
            transport=transport,
        )
        self._session_id: str | None = None
        self._next_id = 1

    def __enter__(self) -> StreamableHttpMcpClient:
        self.initialize()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def initialize(self) -> dict[str, Any]:
        result = self.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "pivotglass", "version": "0.9"},
            },
        )
        self.notify("notifications/initialized", {})
        return result

    def request(self, method: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = dict(params)
        response = self._post(payload)
        if response.get("id") != request_id:
            raise McpError("MCP response id did not match the request")
        error = response.get("error")
        if error:
            message = error.get("message") if isinstance(error, dict) else None
            raise McpError(str(message or "MCP request failed")[:500])
        result = response.get("result", {})
        if not isinstance(result, dict):
            raise McpError("MCP result was not an object")
        return result

    def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = dict(params)
        self._post(payload, notification=True)

    def list_tools(self) -> list[dict[str, Any]]:
        tools = self.request("tools/list").get("tools", [])
        return [item for item in tools if isinstance(item, dict)]

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Any:
        result = self.request(
            "tools/call",
            {"name": name, "arguments": dict(arguments)},
        )
        if result.get("isError"):
            raise McpError(_tool_text(result) or f"MCP tool {name!r} failed")
        structured = result.get("structuredContent")
        if structured is not None:
            return structured
        text = _tool_text(result)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        return result.get("content", [])

    def close(self) -> None:
        if self._session_id:
            try:
                self._client.delete(
                    self.url,
                    headers={"Mcp-Session-Id": self._session_id},
                )
            except httpx.HTTPError:
                pass
        self._client.close()

    def _post(self, payload: dict[str, Any], *, notification: bool = False) -> dict[str, Any]:
        headers = {"Mcp-Session-Id": self._session_id} if self._session_id else None
        try:
            response = self._client.post(self.url, json=payload, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise McpError(f"MCP transport failed ({type(exc).__name__})") from None
        session_id = response.headers.get("Mcp-Session-Id")
        if session_id:
            self._session_id = session_id
        if len(response.content) > self._max_response_bytes:
            raise McpError("MCP response exceeded the configured size limit")
        if notification and not response.content.strip():
            return {}
        return _decode_response(response)


def _decode_response(response: httpx.Response) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "").casefold()
    try:
        if "text/event-stream" in content_type:
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    value = json.loads(line[5:].strip())
                    if isinstance(value, dict):
                        return value
            raise ValueError("missing data event")
        value = response.json()
        if isinstance(value, dict):
            return value
    except (json.JSONDecodeError, ValueError):
        pass
    raise McpError("MCP server returned an invalid response")


def _tool_text(result: Mapping[str, Any]) -> str:
    parts: list[str] = []
    content = result.get("content", [])
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
    return "\n".join(parts).strip()
