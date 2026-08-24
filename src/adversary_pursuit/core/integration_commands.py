"""Shared deterministic commands for optional Synapse and SCOT4 MCP reads."""

from __future__ import annotations

import json
from typing import Any

from adversary_pursuit.core.config import ConfigManager
from adversary_pursuit.integrations.scot import ScotMcpAdapter
from adversary_pursuit.integrations.synapse import SynapseMcpAdapter


def execute_integration_command(args: tuple[str, ...], config_mgr: ConfigManager) -> dict[str, Any]:
    """Execute one explicitly requested, read-only integration operation."""
    if not args or args == ("status",):
        return {
            "title": "External integrations",
            "data": _configuration_status(config_mgr),
        }
    system = args[0].casefold()
    if system == "synapse":
        return _synapse(args[1:], config_mgr)
    if system == "scot":
        return _scot(args[1:], config_mgr)
    raise ValueError(_usage())


def _configuration_status(config_mgr: ConfigManager) -> dict[str, Any]:
    return {
        name: {
            "endpoint": "configured" if config_mgr.get_integration_url(name) else "missing",
            "credential": config_mgr.get_api_key_source(name),
            "mode": "read-only",
            "authority": "remote-preview",
        }
        for name in ("synapse", "scot")
    }


def _synapse(args: tuple[str, ...], config_mgr: ConfigManager) -> dict[str, Any]:
    adapter = _synapse_adapter(config_mgr)
    action = args[0].casefold() if args else "status"
    if action == "status" and len(args) == 1:
        data = adapter.status()
    elif action == "model" and len(args) >= 2:
        data = adapter.model_find(" ".join(args[1:]))
    elif action == "lookup" and len(args) >= 3:
        data = adapter.lookup(args[1], " ".join(args[2:]))
    elif action == "query" and len(args) >= 2:
        data = adapter.query(" ".join(args[1:]))
    else:
        raise ValueError(
            "usage: integration synapse status|model <pattern>|lookup <type> <value>|query <Storm>"
        )
    return {"title": "Vertex Synapse (read-only)", "data": data}


def _scot(args: tuple[str, ...], config_mgr: ConfigManager) -> dict[str, Any]:
    adapter = _scot_adapter(config_mgr)
    action = args[0].casefold() if args else "status"
    if action == "status" and len(args) == 1:
        data = adapter.status()
    elif action == "get" and len(args) == 3:
        data = adapter.get(args[1], args[2])
    elif action == "search" and len(args) >= 2:
        filters = json.loads(" ".join(args[2:])) if len(args) > 2 else {}
        if not isinstance(filters, dict):
            raise ValueError("SCOT search filters must be a JSON object")
        data = adapter.search(args[1], filters=filters)
    elif action == "entries" and len(args) in {3, 4}:
        data = adapter.entries(args[1], args[2], entry_type=args[3] if len(args) == 4 else "all")
    elif action == "entities" and len(args) == 3:
        data = adapter.entities(args[1], args[2])
    else:
        raise ValueError(
            "usage: integration scot status|get <type> <id>|search <type> [filters-json]|"
            "entries <type> <id> [plain|flaired|all]|entities <type> <id>"
        )
    return {"title": "Sandia SCOT4 (read-only)", "data": data}


def _synapse_adapter(config_mgr: ConfigManager) -> SynapseMcpAdapter:
    url, key, options = _connection(config_mgr, "synapse")
    return SynapseMcpAdapter(url, key, **options)


def _scot_adapter(config_mgr: ConfigManager) -> ScotMcpAdapter:
    url, key, options = _connection(config_mgr, "scot")
    options.pop("max_elapsed_seconds")
    return ScotMcpAdapter(url, key, **options)


def _connection(config_mgr: ConfigManager, system: str) -> tuple[str, str, dict[str, Any]]:
    url = config_mgr.get_integration_url(system)
    key = config_mgr.get_api_key(system)
    if not url:
        raise ValueError(
            f"{system.title()} MCP endpoint is missing; set integrations.{system}_mcp_url"
        )
    if not key:
        raise ValueError(f"{system.title()} API key is missing; set api_keys.{system}")
    cfg = config_mgr.load().integrations
    return url, key, {
        "timeout_seconds": cfg.timeout_seconds,
        "max_pages": cfg.max_pages,
        "max_records": cfg.max_records,
        "max_elapsed_seconds": cfg.max_elapsed_seconds,
        "allow_insecure_http": cfg.allow_insecure_http,
    }


def _usage() -> str:
    return "usage: integration status|synapse ...|scot ..."
