"""Shared deterministic commands for optional Synapse and SCOT4 MCP reads."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from adversary_pursuit.core.config import ConfigManager
from adversary_pursuit.core.graph_repository import WorkspaceGraphRepository
from adversary_pursuit.integrations.local_tool import local_tool_status
from adversary_pursuit.integrations.nucleotide import NucleotideAdapter
from adversary_pursuit.integrations.roast import RoastAdapter
from adversary_pursuit.integrations.scot import ScotMcpAdapter
from adversary_pursuit.integrations.scot_publication import (
    build_scot_publication_manifest,
    compile_scot_write_plan,
    validate_scot_pivot_request,
)
from adversary_pursuit.integrations.synapse import SynapseMcpAdapter
from adversary_pursuit.integrations.synapse_graph import build_synapse_shadow_manifest


def execute_integration_command(
    args: tuple[str, ...],
    config_mgr: ConfigManager,
    workspace_mgr: Any | None = None,
) -> dict[str, Any]:
    """Execute one explicitly requested, read-only integration operation."""
    if not args or args == ("status",):
        return {
            "title": "External integrations",
            "data": _configuration_status(config_mgr),
        }
    system = args[0].casefold()
    if system == "synapse":
        return _synapse(args[1:], config_mgr, workspace_mgr)
    if system == "scot":
        return _scot(args[1:], config_mgr, workspace_mgr)
    if system in {"roast", "go-roast"}:
        return _roast(args[1:], config_mgr)
    if system == "nucleotide":
        return _nucleotide(args[1:], config_mgr)
    raise ValueError(_usage())


def _configuration_status(config_mgr: ConfigManager) -> dict[str, Any]:
    status = {
        name: {
            "endpoint": "configured" if config_mgr.get_integration_url(name) else "missing",
            "credential": config_mgr.get_api_key_source(name),
            "mode": "read-only",
            "authority": "remote-preview",
        }
        for name in ("synapse", "scot")
    }
    roast_executable = config_mgr.get_local_integration_setting("go_roast_executable") or "roast"
    nucleotide_executable = (
        config_mgr.get_local_integration_setting("nucleotide_executable") or "nucleotide"
    )
    status["go-roast"] = {
        **local_tool_status(roast_executable),
        "mode": "read-only analysis preview",
        "authority": "external-derived-proposal",
    }
    status["nucleotide"] = {
        **local_tool_status(nucleotide_executable),
        "lookup": (
            "configured"
            if config_mgr.get_local_integration_setting("nucleotide_lookup_path")
            else "missing"
        ),
        "mode": "read-only analysis preview",
        "authority": "external-derived-proposal",
    }
    return status


def _synapse(
    args: tuple[str, ...],
    config_mgr: ConfigManager,
    workspace_mgr: Any | None,
) -> dict[str, Any]:
    action = args[0].casefold() if args else "status"
    if action == "shadow-preview" and len(args) == 1:
        snapshot = WorkspaceGraphRepository(_require_workspace(workspace_mgr)).snapshot()
        data = build_synapse_shadow_manifest(snapshot).model_dump(mode="json")
        return {"title": "Vertex Synapse shadow manifest", "data": data}
    adapter = _synapse_adapter(config_mgr)
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
            "usage: integration synapse shadow-preview|status|model <pattern>|"
            "lookup <type> <value>|query <Storm>"
        )
    return {"title": "Vertex Synapse (read-only)", "data": data}


def _scot(
    args: tuple[str, ...],
    config_mgr: ConfigManager,
    workspace_mgr: Any | None,
) -> dict[str, Any]:
    action = args[0].casefold() if args else "status"
    if action == "publish-preview" and len(args) == 1:
        snapshot = WorkspaceGraphRepository(_require_workspace(workspace_mgr)).snapshot()
        data = build_scot_publication_manifest(snapshot).model_dump(mode="json")
        return {"title": "SCOT4 hunt publication preview", "data": data}
    if action == "publish-plan" and len(args) >= 2:
        snapshot = WorkspaceGraphRepository(_require_workspace(workspace_mgr)).snapshot()
        manifest = build_scot_publication_manifest(snapshot)
        data = compile_scot_write_plan(manifest, owner=" ".join(args[1:])).model_dump(
            mode="json"
        )
        return {"title": "SCOT4 review-only write plan", "data": data}
    if action == "pivot-preview" and len(args) >= 4:
        structured = " ".join(args[1:]).split(" | ", 2)
        if len(structured) != 3:
            raise ValueError(
                "usage: integration scot pivot-preview <type> <id> <indicator> | "
                "<requester> | <reason>"
            )
        head = structured[0].split(maxsplit=2)
        if len(head) != 3:
            raise ValueError("SCOT pivot preview requires type, ID, and indicator")
        request = validate_scot_pivot_request(
            workspace=_require_workspace(workspace_mgr).active,
            scot_object_type=head[0],
            scot_object_id=int(head[1]),
            indicator=head[2],
            requested_by=structured[1],
            requested_at=datetime.now(UTC),
            reason=structured[2],
        )
        return {"title": "SCOT4 pivot request preview", "data": request.model_dump(mode="json")}
    adapter = _scot_adapter(config_mgr)
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
            "entries <type> <id> [plain|flaired|all]|entities <type> <id>|"
            "publish-preview|publish-plan <owner>|"
            "pivot-preview <type> <id> <indicator> | <requester> | <reason>"
        )
    return {"title": "Sandia SCOT4 (read-only)", "data": data}


def _roast(args: tuple[str, ...], config_mgr: ConfigManager) -> dict[str, Any]:
    action = args[0].casefold() if args else "status"
    executable = config_mgr.get_local_integration_setting("go_roast_executable") or "roast"
    if action == "status" and len(args) == 1:
        return {"title": "go-roast", "data": local_tool_status(executable)}
    adapter = _roast_adapter(config_mgr)
    if action == "decode" and len(args) >= 2:
        data = adapter.decode(list(args[1:])).model_dump(mode="json")
    elif action == "analyze" and len(args) >= 2:
        data = adapter.analyze(list(args[1:]))
    else:
        raise ValueError("usage: integration roast status|decode <domain>...|analyze <domain>...")
    return {"title": "go-roast OAST analysis preview", "data": data}


def _nucleotide(args: tuple[str, ...], config_mgr: ConfigManager) -> dict[str, Any]:
    action = args[0].casefold() if args else "status"
    executable = config_mgr.get_local_integration_setting("nucleotide_executable") or "nucleotide"
    if action == "status" and len(args) == 1:
        return {
            "title": "Nucleotide",
            "data": {
                **local_tool_status(executable),
                "lookup": (
                    "configured"
                    if config_mgr.get_local_integration_setting("nucleotide_lookup_path")
                    else "missing"
                ),
            },
        }
    adapter = _nucleotide_adapter(config_mgr)
    if action == "lookup-info" and len(args) == 1:
        data = adapter.lookup_info()
    elif action in {"lookup", "lookup-strict"} and len(args) >= 2:
        data = adapter.lookup(list(args[1:]), strict=action == "lookup-strict").model_dump(
            mode="json"
        )
    elif action == "fingerprint-preview" and len(args) >= 2:
        structured = " ".join(args[1:]).split(" | ", 1)
        if len(structured) != 2:
            raise ValueError(
                "usage: integration nucleotide fingerprint-preview <actor-id> | <events-json>"
            )
        payload = json.loads(structured[1])
        events = payload if isinstance(payload, list) else [payload]
        if not all(isinstance(item, dict) for item in events):
            raise ValueError("Nucleotide events JSON must be an object or array of objects")
        data = adapter.fingerprint(structured[0], events).model_dump(mode="json")
    else:
        raise ValueError(
            "usage: integration nucleotide status|lookup-info|lookup <url>...|"
            "lookup-strict <url>...|fingerprint-preview <actor-id> | <events-json>"
        )
    return {"title": "Nucleotide analysis preview", "data": data}


def _synapse_adapter(config_mgr: ConfigManager) -> SynapseMcpAdapter:
    url, key, options = _connection(config_mgr, "synapse")
    return SynapseMcpAdapter(url, key, **options)


def _scot_adapter(config_mgr: ConfigManager) -> ScotMcpAdapter:
    url, key, options = _connection(config_mgr, "scot")
    options.pop("max_elapsed_seconds")
    return ScotMcpAdapter(url, key, **options)


def _roast_adapter(config_mgr: ConfigManager) -> RoastAdapter:
    cfg = config_mgr.load().integrations
    executable = config_mgr.get_local_integration_setting("go_roast_executable") or "roast"
    return RoastAdapter(
        executable,
        timeout_seconds=cfg.timeout_seconds,
        max_output_bytes=cfg.max_local_output_bytes,
        max_records=cfg.max_records,
    )


def _nucleotide_adapter(config_mgr: ConfigManager) -> NucleotideAdapter:
    cfg = config_mgr.load().integrations
    executable = config_mgr.get_local_integration_setting("nucleotide_executable") or "nucleotide"
    lookup = config_mgr.get_local_integration_setting("nucleotide_lookup_path")
    if not lookup:
        raise ValueError(
            "Nucleotide lookup is missing; set integrations.nucleotide_lookup_path or "
            "AP_NUCLEOTIDE_LOOKUP"
        )
    return NucleotideAdapter(
        executable,
        lookup,
        timeout_seconds=cfg.timeout_seconds,
        max_output_bytes=cfg.max_local_output_bytes,
        max_records=cfg.max_records,
    )


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
    return "usage: integration status|synapse ...|scot ...|roast ...|nucleotide ..."


def _require_workspace(workspace_mgr: Any | None) -> Any:
    if workspace_mgr is None:
        raise ValueError("active workspace is required for this integration preview")
    return workspace_mgr
