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
from adversary_pursuit.integrations.scot_execution import (
    ScotPublicationJournal,
    ScotRestPublisher,
    approve_scot_publication,
    execute_scot_publication,
)
from adversary_pursuit.integrations.scot_publication import (
    build_scot_publication_manifest,
    compile_scot_write_plan,
    validate_scot_pivot_request,
)
from adversary_pursuit.integrations.synapse import SynapseMcpAdapter
from adversary_pursuit.integrations.synapse_execution import (
    SynapseShadowExecutor,
    SynapseShadowJournal,
    approve_synapse_shadow_load,
)
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
            raise ValueError("usage: integration review <proposal-id> <accept|reject> | <reason>")
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
    if args[0].casefold() == "materialize" and len(args) >= 4:
        proposal_id, separator, rationale = " ".join(args[1:]).partition(" | ")
        if not separator or len(proposal_id.split()) != 1:
            raise ValueError("usage: integration materialize <proposal-id> | <rationale>")
        data = AnalyticLedger(
            _require_workspace(workspace_mgr)
        ).materialize_external_analysis_proposal(
            proposal_id,
            rationale=rationale,
        )
        return {"title": "External analysis assertion materialized", "data": data}
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
    status["scot"]["publication_endpoint"] = (
        "configured" if config_mgr.get_scot_api_url() else "missing"
    )
    status["synapse"]["mode"] = "read-only exploration; approved shadow-view loads"
    status["scot"]["mode"] = "read-only exploration; approved publication"
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
    if action == "shadow-receipt" and len(args) == 2:
        data = SynapseShadowJournal(_require_workspace(workspace_mgr)).get(args[1])
        return {"title": "Vertex Synapse shadow-load receipt", "data": data}
    if action == "shadow-execute" and len(args) >= 6:
        head, separator, confirmation = " ".join(args[1:]).partition(" | ")
        fields = head.split()
        if not separator or len(fields) != 4:
            raise ValueError(
                "usage: integration synapse shadow-execute <parent-view> <plan-digest> "
                "<backup-receipt-sha256> <approved-by> | <confirmation>"
            )
        parent_view, supplied_digest, backup_receipt, approved_by = fields
        snapshot = WorkspaceGraphRepository(_require_workspace(workspace_mgr)).snapshot()
        plan = compile_synapse_migration_plan(build_synapse_shadow_manifest(snapshot))
        if supplied_digest != plan.digest_sha256:
            raise ValueError("Synapse migration plan digest is stale or does not match")
        approval = approve_synapse_shadow_load(
            plan,
            parent_view=parent_view,
            backup_receipt_sha256=backup_receipt,
            approved_by=approved_by,
            confirmation=confirmation,
        )
        url, key, options = _connection(config_mgr, "synapse")
        executor = SynapseShadowExecutor(url, key, **options)
        data = executor.execute(
            plan,
            approval,
            journal=SynapseShadowJournal(_require_workspace(workspace_mgr)),
        )
        return {"title": "Vertex Synapse isolated shadow load reconciled", "data": data}
    adapter = _synapse_adapter(config_mgr)
    if action == "status" and len(args) == 1:
        data = adapter.status()
    elif action == "model" and len(args) >= 2:
        data = adapter.model_find(" ".join(args[1:]))
    elif action == "views" and len(args) == 1:
        data = adapter.views()
    elif action == "lookup" and len(args) >= 3:
        data = adapter.lookup(args[1], " ".join(args[2:]))
    elif action == "query" and len(args) >= 2:
        data = adapter.query(" ".join(args[1:]))
    else:
        raise ValueError(
            "usage: integration synapse shadow-preview|model-contract|migration-plan|"
            "shadow-receipt <plan-digest>|shadow-execute <parent-view> <plan-digest> "
            "<backup-receipt-sha256> <approved-by> | <confirmation>|"
            "status|views|model <pattern>|"
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
        data = compile_scot_write_plan(manifest, owner=" ".join(args[1:])).model_dump(mode="json")
        return {"title": "SCOT4 review-only write plan", "data": data}
    if action == "publication-receipt" and len(args) == 2:
        data = ScotPublicationJournal(_require_workspace(workspace_mgr)).get(args[1])
        return {"title": "SCOT4 publication receipt", "data": data}
    if action == "publish-execute" and len(args) >= 5:
        head, separator, confirmation = " ".join(args[1:]).partition(" | ")
        fields = head.split()
        if not separator or len(fields) != 3:
            raise ValueError(
                "usage: integration scot publish-execute <owner> <plan-digest> "
                "<approved-by> | <confirmation>"
            )
        owner, supplied_digest, approved_by = fields
        snapshot = WorkspaceGraphRepository(_require_workspace(workspace_mgr)).snapshot()
        manifest = build_scot_publication_manifest(snapshot)
        plan = compile_scot_write_plan(manifest, owner=owner)
        if supplied_digest != plan.digest_sha256:
            raise ValueError("SCOT publication plan digest is stale or does not match")
        approval = approve_scot_publication(
            plan,
            approved_by=approved_by,
            confirmation=confirmation,
        )
        api_url = config_mgr.get_scot_api_url()
        api_key = config_mgr.get_api_key("scot")
        if not api_url or not api_key:
            raise ValueError("SCOT publication requires its REST API URL and API key")
        cfg = config_mgr.load().integrations
        with ScotRestPublisher(
            api_url,
            api_key,
            timeout_seconds=cfg.timeout_seconds,
            allow_insecure_http=cfg.allow_insecure_http,
        ) as publisher:
            data = execute_scot_publication(
                plan,
                approval,
                publisher=publisher,
                journal=ScotPublicationJournal(_require_workspace(workspace_mgr)),
            )
        return {"title": "SCOT4 publication reconciled", "data": data}
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
    if action == "pivot-queue" and len(args) == 1:
        data = AnalyticLedger(_require_workspace(workspace_mgr)).enrichment_requests()
        return {"title": "SCOT4 enrichment queue", "data": data}
    if action == "pivot-enqueue" and len(args) >= 5:
        structured = " ".join(args[1:]).split(" | ", 3)
        if len(structured) != 4:
            raise ValueError(
                "usage: integration scot pivot-enqueue <type> <id> <indicator> | "
                "<requester> | <reason> | <approved-by>"
            )
        head = structured[0].split(maxsplit=2)
        if len(head) != 3:
            raise ValueError("SCOT pivot enqueue requires type, ID, and indicator")
        request = validate_scot_pivot_request(
            workspace=_require_workspace(workspace_mgr).active,
            scot_object_type=head[0],
            scot_object_id=int(head[1]),
            indicator=head[2],
            requested_by=structured[1],
            requested_at=datetime.now(UTC),
            reason=structured[2],
        )
        queue_item, created = AnalyticLedger(
            _require_workspace(workspace_mgr)
        ).enqueue_scot_pivot_request(
            request.model_dump(mode="json"),
            approved_by=structured[3],
        )
        queued_request = queue_item["criteria"]["request"]
        data = {
            "request": queued_request,
            "queue_item": queue_item,
            "created": created,
            "start_enrichment": queue_item["criteria"]["queue_state"] == "queued",
        }
        return {"title": "SCOT4 pivot accepted into enrichment queue", "data": data}
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
            "publish-preview|publish-plan <owner>|publication-receipt <plan-digest>|"
            "publish-execute <owner> <plan-digest> "
            "<approved-by> | <confirmation>|"
            "pivot-preview <type> <id> <indicator> | <requester> | <reason>|"
            "pivot-queue|pivot-enqueue <type> <id> <indicator> | <requester> | "
            "<reason> | <approved-by>"
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
    if action == "fingerprint-history" and len(args) == 2:
        ledger = AnalyticLedger(_require_workspace(workspace_mgr))
        data = _nucleotide_fingerprint_history(ledger, args[1])
        return {"title": "Nucleotide fingerprint history", "data": data}
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
            "recorded": _record_nucleotide_fingerprint_proposal(ledger, structured[0], preview),
            "analyst_disposition": "pending",
        }
    elif action == "fingerprint-compare" and len(args) == 3:
        ledger = AnalyticLedger(_require_workspace(workspace_mgr))
        left = _nucleotide_fingerprint_proposal(ledger, args[1])
        right = _nucleotide_fingerprint_proposal(ledger, args[2])
        left_details = left["criteria"]["details"]
        right_details = right["criteria"]["details"]
        data = adapter.compare(
            left_details["fingerprint"],
            right_details["fingerprint"],
            left_proposal_id=left["record_id"],
            right_proposal_id=right["record_id"],
            left_lookup_sha256=left_details["lookup_sha256"],
            right_lookup_sha256=right_details["lookup_sha256"],
        ).model_dump(mode="json")
    else:
        raise ValueError(
            "usage: integration nucleotide status|lookup-info|lookup <url>...|"
            "lookup-strict <url>...|lookup-record <url>...|"
            "fingerprint-preview <actor-id> | <events-json>|"
            "fingerprint-record <actor-id> | <events-json>|"
            "fingerprint-history <actor-id>|"
            "fingerprint-compare <left-proposal-id> <right-proposal-id>"
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
    return (
        url,
        key,
        {
            "timeout_seconds": cfg.timeout_seconds,
            "max_pages": cfg.max_pages,
            "max_records": cfg.max_records,
            "max_elapsed_seconds": cfg.max_elapsed_seconds,
            "allow_insecure_http": cfg.allow_insecure_http,
        },
    )


def _usage() -> str:
    return (
        "usage: integration status|proposals|review <proposal-id> <accept|reject> | "
        "<reason>|materialize <proposal-id> | <rationale>|synapse ...|scot ...|"
        "roast ...|nucleotide ..."
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
        "fingerprint": preview.fingerprint,
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


def _nucleotide_fingerprint_proposal(ledger: AnalyticLedger, proposal_id: str) -> dict[str, Any]:
    row = next(
        (item for item in ledger.external_analysis_proposals() if item["record_id"] == proposal_id),
        None,
    )
    if row is None:
        raise ValueError(f"Unknown external analysis proposal: {proposal_id}")
    criteria = row.get("criteria") if isinstance(row.get("criteria"), dict) else {}
    details = criteria.get("details") if isinstance(criteria.get("details"), dict) else {}
    if (
        criteria.get("provider") != "nucleotide"
        or criteria.get("operation") != "actor-behavior-fingerprint"
    ):
        raise ValueError("Nucleotide comparison requires two fingerprint proposals")
    if not isinstance(details.get("fingerprint"), dict):
        raise ValueError(
            "Nucleotide proposal predates stored fingerprint artifacts; record it again"
        )
    return row


def _nucleotide_fingerprint_history(
    ledger: AnalyticLedger, analyst_grouped_batch: str
) -> list[dict[str, Any]]:
    normalized_batch = analyst_grouped_batch.strip()
    if not normalized_batch:
        raise ValueError("Nucleotide fingerprint history requires an analyst-grouped batch")
    history: list[dict[str, Any]] = []
    for row in ledger.external_analysis_proposals():
        criteria = row.get("criteria") if isinstance(row.get("criteria"), dict) else {}
        details = criteria.get("details") if isinstance(criteria.get("details"), dict) else {}
        if (
            criteria.get("provider") != "nucleotide"
            or criteria.get("operation") != "actor-behavior-fingerprint"
            or details.get("analyst_grouped_batch") != normalized_batch
        ):
            continue
        fingerprint = details.get("fingerprint")
        actor_fingerprint = (
            fingerprint.get("actor_fingerprint") if isinstance(fingerprint, dict) else {}
        )
        history.append(
            {
                "proposal_id": row["record_id"],
                "created_at": row["created_at"],
                "analyst_disposition": row["analyst_disposition"],
                "lookup_sha256": details.get("lookup_sha256"),
                "fingerprint_sha256": details.get("fingerprint_sha256"),
                "structural_hash": (
                    actor_fingerprint.get("structural_hash")
                    if isinstance(actor_fingerprint, dict)
                    else None
                ),
                "event_count": details.get("event_count"),
                "artifact_available": isinstance(fingerprint, dict),
            }
        )
    return history


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
