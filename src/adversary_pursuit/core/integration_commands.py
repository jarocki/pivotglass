"""Shared deterministic commands for governed external-system integration."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from adversary_pursuit.core.analytic_ledger import AnalystDisposition, AnalyticLedger
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
from adversary_pursuit.integrations.synapse_migration import (
    compile_synapse_migration_plan,
    pivotglass_synapse_model_contract,
)


def execute_integration_command(
    args: tuple[str, ...],
    config_mgr: ConfigManager,
    workspace_mgr: Any | None = None,
) -> dict[str, Any]:
    """Execute one explicitly requested integration operation under its authority."""
    if not args or args == ("status",):
        return {
            "title": "External integrations",
            "data": _configuration_status(config_mgr),
        }
    if args[0].casefold() == "proposals" and len(args) == 1:
        ledger = AnalyticLedger(_require_workspace(workspace_mgr))
        return {
            "title": "External analysis proposals",
            "data": ledger.external_analysis_proposals(),
        }
    if args[0].casefold() == "review" and len(args) >= 4:
        head, separator, reason = " ".join(args[1:]).partition(" | ")
        parts = head.split()
        if not separator or len(parts) != 2:
            raise ValueError(
                "usage: integration review <proposal-id> <accept|reject> | <reason>"
            )
        dispositions = {
            "accept": AnalystDisposition.ACCEPTED,
            "reject": AnalystDisposition.REJECTED,
        }
        disposition = dispositions.get(parts[1].casefold())
        if disposition is None:
            raise ValueError("external analysis disposition must be accept or reject")
        data = AnalyticLedger(_require_workspace(workspace_mgr)).review_external_analysis_proposal(
            parts[0], disposition=disposition, reason=reason
        )
        return {"title": "External analysis review recorded", "data": data}
    system = args[0].casefold()
    if system == "synapse":
        return _synapse(args[1:], config_mgr, workspace_mgr)
    if system == "scot":
        return _scot(args[1:], config_mgr, workspace_mgr)
    if system in {"roast", "go-roast"}:
        return _roast(args[1:], config_mgr, workspace_mgr)
    if system == "nucleotide":
        return _nucleotide(args[1:], config_mgr, workspace_mgr)
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
    if action == "model-contract" and len(args) == 1:
        data = pivotglass_synapse_model_contract().model_dump(mode="json")
        return {"title": "Vertex Synapse Pivotglass model contract", "data": data}
    if action == "migration-plan" and len(args) == 1:
        snapshot = WorkspaceGraphRepository(_require_workspace(workspace_mgr)).snapshot()
        manifest = build_synapse_shadow_manifest(snapshot)
        data = compile_synapse_migration_plan(manifest).model_dump(mode="json")
        return {"title": "Vertex Synapse review-only migration plan", "data": data}
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
            "usage: integration synapse shadow-preview|model-contract|migration-plan|"
            "status|model <pattern>|"
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


def _roast(
    args: tuple[str, ...],
    config_mgr: ConfigManager,
    workspace_mgr: Any | None,
) -> dict[str, Any]:
    action = args[0].casefold() if args else "status"
    executable = config_mgr.get_local_integration_setting("go_roast_executable") or "roast"
    if action == "status" and len(args) == 1:
        return {"title": "go-roast", "data": local_tool_status(executable)}
    adapter = _roast_adapter(config_mgr)
    if action == "decode" and len(args) >= 2:
        data = adapter.decode(list(args[1:])).model_dump(mode="json")
    elif action == "record" and len(args) >= 2:
        preview = adapter.decode(list(args[1:]))
        ledger = AnalyticLedger(_require_workspace(workspace_mgr))
        recorded = _record_roast_proposals(ledger, preview)
        data = {
            "preview": preview.model_dump(mode="json"),
            "recorded": recorded,
            "analyst_disposition": "pending",
        }
    elif action == "analyze" and len(args) >= 2:
        data = adapter.analyze(list(args[1:]))
    else:
        raise ValueError(
            "usage: integration roast status|decode <domain>...|record <domain>...|"
            "analyze <domain>..."
        )
    return {"title": "go-roast OAST analysis preview", "data": data}


def _nucleotide(
    args: tuple[str, ...],
    config_mgr: ConfigManager,
    workspace_mgr: Any | None,
) -> dict[str, Any]:
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
    elif action == "lookup-record" and len(args) >= 2:
        preview = adapter.lookup(list(args[1:]))
        ledger = AnalyticLedger(_require_workspace(workspace_mgr))
        data = {
            "preview": preview.model_dump(mode="json"),
            "recorded": _record_nucleotide_lookup_proposals(ledger, preview),
            "analyst_disposition": "pending",
        }
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
    elif action == "fingerprint-record" and len(args) >= 2:
        structured = " ".join(args[1:]).split(" | ", 1)
        if len(structured) != 2:
            raise ValueError(
                "usage: integration nucleotide fingerprint-record <actor-id> | <events-json>"
            )
        payload = json.loads(structured[1])
        events = payload if isinstance(payload, list) else [payload]
        if not all(isinstance(item, dict) for item in events):
            raise ValueError("Nucleotide events JSON must be an object or array of objects")
        preview = adapter.fingerprint(structured[0], events)
        ledger = AnalyticLedger(_require_workspace(workspace_mgr))
        data = {
            "preview": preview.model_dump(mode="json"),
            "recorded": _record_nucleotide_fingerprint_proposal(
                ledger, structured[0], preview
            ),
            "analyst_disposition": "pending",
        }
    else:
        raise ValueError(
            "usage: integration nucleotide status|lookup-info|lookup <url>...|"
            "lookup-strict <url>...|lookup-record <url>...|"
            "fingerprint-preview <actor-id> | <events-json>|"
            "fingerprint-record <actor-id> | <events-json>"
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
    return (
        "usage: integration status|proposals|review <proposal-id> <accept|reject> | "
        "<reason>|synapse ...|scot ...|roast ...|nucleotide ..."
    )


def _require_workspace(workspace_mgr: Any | None) -> Any:
    if workspace_mgr is None:
        raise ValueError("active workspace is required for this integration preview")
    return workspace_mgr


def _record_roast_proposals(ledger: AnalyticLedger, preview: Any) -> list[dict[str, Any]]:
    nodes = {node.id: node.model_dump(mode="json") for node in preview.nodes}
    recorded: list[dict[str, Any]] = []
    for relationship in preview.relationships:
        details = relationship.model_dump(mode="json")
        details["source_node"] = nodes.get(relationship.source)
        details["target_node"] = nodes.get(relationship.target)
        row, created = ledger.record_external_analysis_proposal(
            provider="go-roast",
            operation="decode-relationship",
            statement=(
                f"go-roast proposes that {relationship.source} "
                f"{relationship.relationship} {relationship.target}."
            ),
            payload_sha256=_json_sha256(details),
            provenance_refs=relationship.provenance_refs,
            caveats=tuple((*preview.caveats, *relationship.caveats)),
            details=details,
        )
        recorded.append({"proposal_id": row["record_id"], "created": created})
    return recorded


def _record_nucleotide_lookup_proposals(
    ledger: AnalyticLedger, preview: Any
) -> list[dict[str, Any]]:
    recorded: list[dict[str, Any]] = []
    receipt_ref = f"nucleotide:{preview.receipt.request_sha256}:lookup:{preview.lookup_sha256}"
    for match in preview.matches:
        details = match.model_dump(mode="json")
        row, created = ledger.record_external_analysis_proposal(
            provider="nucleotide",
            operation="url-template-lookup",
            statement=(
                f"Nucleotide classified {match.url} as {match.attribution}"
                + (f" for template {match.template_id}." if match.template_id else ".")
            ),
            payload_sha256=_json_sha256(details),
            provenance_refs=(receipt_ref,),
            caveats=preview.caveats,
            details={**details, "lookup_sha256": preview.lookup_sha256},
        )
        recorded.append({"proposal_id": row["record_id"], "created": created})
    return recorded


def _record_nucleotide_fingerprint_proposal(
    ledger: AnalyticLedger,
    actor_id: str,
    preview: Any,
) -> dict[str, Any]:
    fingerprint_sha256 = _json_sha256(preview.fingerprint)
    details = {
        "analyst_grouped_batch": actor_id.strip(),
        "event_count": preview.event_count,
        "lookup_sha256": preview.lookup_sha256,
        "fingerprint_sha256": fingerprint_sha256,
        "supporting_signals": list(preview.supporting_signals),
        "contradictions": list(preview.contradictions),
    }
    row, created = ledger.record_external_analysis_proposal(
        provider="nucleotide",
        operation="actor-behavior-fingerprint",
        statement=(
            f"Nucleotide produced a behavior fingerprint for analyst-grouped batch "
            f"{actor_id.strip()}; this is not an actor-identity claim."
        ),
        payload_sha256=fingerprint_sha256,
        provenance_refs=(f"nucleotide:{preview.receipt.request_sha256}:fingerprint",),
        caveats=preview.caveats,
        details=details,
    )
    return {"proposal_id": row["record_id"], "created": created}


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
