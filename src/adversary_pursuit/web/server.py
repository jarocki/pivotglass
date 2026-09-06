"""Loopback-only HTTP adapter for the Pivotglass web cockpit.

The adapter deliberately exposes existing domain authorities instead of
reimplementing tools or workspace behavior in JavaScript.
"""

from __future__ import annotations

import base64
import binascii
import csv
import io
import json
import logging
import re
import threading
import webbrowser
from dataclasses import asdict
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from rich.console import Console
from rich.text import Text

from adversary_pursuit.agent.battery_registry import dispatch_batteries
from adversary_pursuit.agent.configuration_advisor import ConfigurationAdvisor
from adversary_pursuit.agent.enrichment_briefings import BRIEFINGS
from adversary_pursuit.agent.model_control import (
    ModelControl,
    execute_configuration_command,
    execute_model_command,
)
from adversary_pursuit.agent.provider_setup import CTI_SERVICES
from adversary_pursuit.agent.tools import ToolContext, create_tools, execute_tool
from adversary_pursuit.agent.tui.themes import (
    COCKPIT_PROFILES,
    DEFAULT_THEMES,
    PURSUIT_TITLES,
)
from adversary_pursuit.core.analytic_commands import execute_analysis_command
from adversary_pursuit.core.analytic_ledger import AnalyticLedger
from adversary_pursuit.core.analytic_rigor import build_analytic_rigor
from adversary_pursuit.core.command_completion import command_completions
from adversary_pursuit.core.document_entity_extraction import (
    EntityExtractionLimits,
    extract_entity_candidates,
)
from adversary_pursuit.core.document_ingestion import DocumentIntakeService, DocumentLimits
from adversary_pursuit.core.error_interpreter import DEBUG_LOG_PATH
from adversary_pursuit.core.evidence_cluster_history import EvidenceClusterHistory
from adversary_pursuit.core.evidence_clusters import build_evidence_clusters
from adversary_pursuit.core.evidence_detail import evidence_ref, list_evidence, project_evidence
from adversary_pursuit.core.framework_commands import execute_framework_command
from adversary_pursuit.core.framework_perspectives import (
    ATTACK_ENTERPRISE_V19_2,
    DIAMOND_VERSION,
    KILL_CHAIN_VERSION,
)
from adversary_pursuit.core.framework_projections import FrameworkProjectionAuthority
from adversary_pursuit.core.graph import RelationshipGraph, persisted_relationships
from adversary_pursuit.core.graph_presentation import GraphPresentationAuthority
from adversary_pursuit.core.information_requirements import build_information_requirements
from adversary_pursuit.core.integration_commands import execute_integration_command
from adversary_pursuit.core.investigation import (
    ContentClass,
    EventClass,
    InvestigationStore,
    LifecycleState,
    utc_now,
)
from adversary_pursuit.core.investigation_graph import build_investigation_graph
from adversary_pursuit.core.ioc_types import detect_ioc_type
from adversary_pursuit.core.learning_workspace import create_learning_workspace
from adversary_pursuit.core.operational_status import build_authority_registry
from adversary_pursuit.core.pursuit_brief import build_pursuit_brief
from adversary_pursuit.core.visualization import build_visualization_intents
from adversary_pursuit.core.workspace_admin import (
    export_workspace,
    merge_workspaces,
)
from adversary_pursuit.dossier.slot_inference import infer_dossier_state
from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus
from adversary_pursuit.dossier.state import load_dossier_state
from adversary_pursuit.gamification.modes import DEFAULT_MODES, display_mode_name
from adversary_pursuit.integrations.scot_pivot_intake import (
    ScotPivotAuthenticationError,
    ScotPivotAuthenticationReceipt,
    authenticate_scot_pivot_request,
)
from adversary_pursuit.integrations.scot_publication import validate_scot_pivot_request

_LOG = logging.getLogger(__name__)
_SOURCE_WEB_DIR = Path(__file__).parents[3] / "web"
_SOURCE_WEB_ROOT = _SOURCE_WEB_DIR / "out"
_PACKAGED_WEB_ROOT = Path(__file__).with_name("static")
_TYPE_MAP = {
    "ipv4": "ipv4-addr",
    "ipv6": "ipv6-addr",
    "domain": "domain-name",
    "url": "url",
    "email": "email-addr",
    "md5": "file",
    "sha1": "file",
    "sha256": "file",
}
_DIAGNOSTIC_SUMMARY = re.compile(
    r"^\[USER_SAW_PANEL\]\s+\[(?P<category>[^\]]+)]\s+"
    r"(?P<action>.+?)\s+\(diag\s+(?P<diagnostic_id>[a-f0-9]{8})\)$"
)


def _web_root() -> Path:
    """Resolve the cockpit assets at launch rather than module-import time.

    Editable installs must serve the current checkout's export.  Wheels do not
    contain ``web/`` and therefore fall back to the force-included packaged
    assets.
    """

    if _SOURCE_WEB_ROOT.joinpath("index.html").is_file():
        return _SOURCE_WEB_ROOT
    return _PACKAGED_WEB_ROOT


def _tool_failure(summary: str) -> dict[str, str] | None:
    """Decode the shared tool boundary's sanitized failure receipt."""

    match = _DIAGNOSTIC_SUMMARY.fullmatch(summary.strip())
    if match is not None:
        return {
            "category": match.group("category"),
            "next_action": match.group("action"),
            "diagnostic_id": match.group("diagnostic_id"),
        }
    if summary.startswith("Error:"):
        return {
            "category": "Source",
            "next_action": summary.removeprefix("Error:").strip(),
            "diagnostic_id": "",
        }
    return None


def _source_web_build_is_stale(web_root: Path) -> bool:
    """Return whether an editable checkout's source is newer than its export."""

    if web_root != _SOURCE_WEB_ROOT:
        return False
    index = web_root / "index.html"
    if not index.is_file():
        return True
    exported_at = index.stat().st_mtime_ns
    # Git restores tracked source and export files sequentially during checkout.
    # Their timestamps can therefore differ by a few milliseconds even though
    # they came from the same commit. Ignore sub-second restoration skew while
    # continuing to reject source files that were edited after the export.
    checkout_mtime_skew_ns = 1_000_000_000
    source_files = (
        *(_SOURCE_WEB_DIR / "app").glob("**/*.ts"),
        *(_SOURCE_WEB_DIR / "app").glob("**/*.tsx"),
        *(_SOURCE_WEB_DIR / "app").glob("**/*.css"),
        *(_SOURCE_WEB_DIR / "app").glob("**/*.json"),
        _SOURCE_WEB_DIR / "next.config.ts",
        _SOURCE_WEB_DIR / "package.json",
    )
    return any(
        source.is_file()
        and source.stat().st_mtime_ns > exported_at + checkout_mtime_skew_ns
        for source in source_files
    )


class WebCockpitService:
    """JSON-facing adapter around the existing deterministic tool context."""

    def __init__(self, ctx: ToolContext | None = None) -> None:
        self._web_console_buffer = io.StringIO() if ctx is None else None
        self.ctx = ctx or ToolContext(
            console=Console(file=self._web_console_buffer, force_terminal=False)
        )
        self.config_mgr = self.ctx.config_mgr
        self.model_control = ModelControl(self.config_mgr)
        self.configuration_advisor = ConfigurationAdvisor(self.model_control)
        self._investigation_lock = threading.Lock()
        self.investigations = InvestigationStore()
        self.mode_mgr = self.ctx.mode_mgr
        self._command_lock = threading.RLock()
        self._runner: Any | None = None
        workspaces = self.ctx.workspace_mgr.list_workspaces()
        if "default" not in workspaces:
            self.ctx.workspace_mgr.create("default")
        self.ctx.workspace_mgr.switch("default")
        self._tool_schemas = {
            item["function"]["name"]: item["function"] for item in create_tools(self.ctx)
        }

    def state(self) -> dict[str, Any]:
        """Return the current workspace snapshot for the cockpit."""
        objects = self.ctx.workspace_mgr.get_stix_objects()
        runs = self.ctx.workspace_mgr.get_module_runs()
        latest_target = str(runs[-1]["target"]) if runs else None
        challenges = self.ctx.challenge_mgr.refresh_for_hunt(latest_target)
        badges = self.ctx.workspace_mgr.get_awarded_badges()
        dossier_state = load_dossier_state(self.ctx.workspace_mgr)
        slot_evidence: dict[DossierSlotName, list[dict[str, str]]] = {
            slot_name: [] for slot_name in DossierSlotName
        }
        for item in objects:
            stix_id = str(item.get("id", ""))
            if not stix_id:
                continue
            try:
                contribution = infer_dossier_state([item])
            except (AttributeError, KeyError, TypeError, ValueError):
                continue
            value = str(
                item.get(
                    "value",
                    item.get("x_indicator_value", item.get("name", "unavailable")),
                )
            )
            for slot_name, slot in contribution.slots.items():
                if slot.evidence_count:
                    slot_evidence[slot_name].append(
                        {
                            "reference": evidence_ref(stix_id),
                            "value": value,
                            "type": str(item.get("type", "unknown")),
                        }
                    )
        dossier_slots = []
        for slot_name in DossierSlotName:
            slot = dossier_state.slots.get(slot_name) if dossier_state is not None else None
            dossier_slots.append(
                {
                    "name": slot_name.value,
                    "status": slot.status.value if slot is not None else SlotStatus.EMPTY.value,
                    "evidence_count": slot.evidence_count if slot is not None else 0,
                    "evidence": slot_evidence[slot_name][:8],
                }
            )
        relationship_graph = RelationshipGraph()
        relationship_graph.build_from_workspace(
            objects,
            persisted_relationships(self.ctx.workspace_mgr),
        )
        ledger = AnalyticLedger(self.ctx.workspace_mgr)
        analysis = ledger.snapshot()
        analysis["enrichment_queue"] = ledger.enrichment_requests()
        analysis["information_requirements"] = build_information_requirements(analysis)
        analysis["rigor"] = build_analytic_rigor(analysis)
        visualization_analysis = {
            **analysis,
            "observations": self.ctx.workspace_mgr.get_observations(),
        }
        investigation_snapshots = self.investigations.snapshots()
        visualizations = build_visualization_intents(
            workspace=self.ctx.workspace_mgr.active,
            objects=objects,
            dossier_slots=dossier_slots,
            graph=relationship_graph.to_dict(),
            investigations=investigation_snapshots,
            analysis=visualization_analysis,
        )
        graph_layouts = GraphPresentationAuthority(self.ctx.workspace_mgr).list()
        modes = []
        for entry in self.mode_mgr.list_modes(public_only=True):
            name = entry["name"]
            modes.append(
                {
                    **entry,
                    "display_name": display_mode_name(name),
                    "greeting": Text.from_markup(DEFAULT_MODES[name].greeting).plain,
                    "theme": asdict(DEFAULT_THEMES[name]),
                    "cockpit": asdict(COCKPIT_PROFILES[name]),
                    "pursuit_title": PURSUIT_TITLES[name],
                }
            )
        framework_mappings = FrameworkProjectionAuthority(self.ctx.workspace_mgr).list()
        framework_counts: dict[str, dict[str, int]] = {}
        for mapping in framework_mappings:
            states = framework_counts.setdefault(mapping.framework.value, {})
            states[mapping.state.value] = states.get(mapping.state.value, 0) + 1
        pursuit_brief = build_pursuit_brief(
            analysis=analysis,
            dossier_slots=dossier_slots,
            framework_counts=framework_counts,
            investigations=investigation_snapshots,
            object_count=len(objects),
            latest_target=latest_target,
        )
        return {
            "workspace": self.ctx.workspace_mgr.active,
            "stats": self.ctx.workspace_mgr.get_workspace_stats(),
            "objects": list_evidence(objects),
            "briefings": {name: asdict(value) for name, value in BRIEFINGS.items()},
            "character": self.mode_mgr.active.name,
            "modes": modes,
            "dossier_slots": dossier_slots,
            "visualizations": [intent.model_dump(mode="json") for intent in visualizations],
            "graph_layouts": [
                {
                    "id": layout["id"],
                    "name": layout["name"],
                    "graph_fingerprint": layout["graph_fingerprint"],
                    "updated_at": layout["updated_at"],
                }
                for layout in graph_layouts
            ],
            "analysis": analysis,
            "pursuit_brief": pursuit_brief,
            "frameworks": {
                "versions": {
                    "attack": ATTACK_ENTERPRISE_V19_2.version,
                    "kill_chain": KILL_CHAIN_VERSION,
                    "diamond": DIAMOND_VERSION,
                },
                "counts": framework_counts,
                "principles": {
                    "attack": "Version-pinned ATT&CK technique perspective.",
                    "kill_chain": "Non-linear phase perspective; sequence requires evidence.",
                    "diamond": "Unknown core vertices stay explicitly unknown.",
                },
            },
            "challenges": challenges,
            "badges": badges,
            "badge_summary": {
                "count": len(badges),
                "latest": badges[-1] if badges else None,
            },
            "processed_targets": sorted(
                {
                    str(run["target"])
                    for run in self.ctx.workspace_mgr.get_module_runs()
                    if run.get("target")
                }
            ),
            "instruments": {
                "local_api": {"available": True, "checked_at": utc_now()},
                "sources": {
                    "configured": len(self._tool_schemas),
                    "queued": 0,
                },
                "model_tokens": {"available": False, "reason": "no synthesis requested"},
                "active_investigations": self.investigations.active_count(),
            },
        }

    def switch_mode(self, name: str) -> dict[str, Any]:
        """Switch the web cockpit using the canonical character authority."""
        mode = self.mode_mgr.switch(name)
        if self._runner is not None:
            self._runner.set_character(mode)
        return self.state()

    def _graph_presentation_scope(self) -> tuple[set[str], set[str]]:
        graph = RelationshipGraph()
        graph.build_from_workspace(
            self.ctx.workspace_mgr.get_stix_objects(),
            persisted_relationships(self.ctx.workspace_mgr),
        )
        payload = graph.to_dict()
        node_refs = {str(node["id"]) for node in payload.get("nodes", ())}
        edge_keys = {
            f"{edge['source']}>{edge['target']}:{edge.get('relationship', 'related-to')}:{edge.get('basis', '')}"
            for edge in payload.get("edges", ())
        }
        return node_refs, edge_keys

    def graph_layout(self, name: str) -> dict[str, Any]:
        """Resolve one saved layout against the current evidence graph."""

        node_refs, edge_keys = self._graph_presentation_scope()
        return GraphPresentationAuthority(self.ctx.workspace_mgr).resolve(
            name,
            current_node_refs=node_refs,
            current_edge_keys=edge_keys,
        )

    def update_graph_layout(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist or delete presentation state without touching graph truth."""

        action = str(payload.get("action", "save")).strip().casefold()
        name = str(payload.get("name", "")).strip()
        authority = GraphPresentationAuthority(self.ctx.workspace_mgr)
        if action == "delete":
            confirmation = str(payload.get("confirmation", "")).strip()
            if confirmation != name:
                raise ValueError("deleting a graph layout requires its exact name as confirmation")
            return {"deleted": authority.delete(name), "name": name}
        if action != "save":
            raise ValueError("graph layout action must be save or delete")
        node_refs, edge_keys = self._graph_presentation_scope()
        return authority.save(
            name,
            node_positions=payload.get("node_positions", {}),
            viewport=payload.get("viewport", {}),
            filter_text=str(payload.get("filter_text", "")),
            labels=payload.get("labels", {}),
            pinned_refs=payload.get("pinned_refs", []),
            current_node_refs=node_refs,
            current_edge_keys=edge_keys,
        )

    def graph_annotations(self, node_ref: str | None = None) -> dict[str, Any]:
        """Return analyst-authored notes attached to current graph nodes."""

        node_refs, _edge_keys = self._graph_presentation_scope()
        return {
            "workspace": self.ctx.workspace_mgr.active,
            "annotations": GraphPresentationAuthority(self.ctx.workspace_mgr).annotations(
                current_node_refs=node_refs,
                node_ref=node_ref,
            ),
        }

    def annotate_graph(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Attach one analyst note to a current graph node."""

        node_refs, _edge_keys = self._graph_presentation_scope()
        annotation = GraphPresentationAuthority(self.ctx.workspace_mgr).annotate(
            str(payload.get("node_ref", "")),
            str(payload.get("text", "")),
            current_node_refs=node_refs,
        )
        return {"saved": True, "annotation": annotation}

    def preview_document(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Preview explicitly uploaded bytes locally without persisting them."""

        encoded = payload.get("content_base64")
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("document content is required")
        limits = DocumentLimits(max_output_chars=100_000)
        maximum_encoded_length = ((limits.max_bytes + 2) // 3) * 4
        if len(encoded) > maximum_encoded_length:
            raise ValueError("document content exceeds the configured preview limit")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("document content is not valid base64") from exc
        preview = DocumentIntakeService(self.ctx.workspace_mgr).preview_bytes(
            data,
            filename=str(payload.get("filename") or "document.bin"),
            supplied_media_type=(str(payload["media_type"]) if payload.get("media_type") else None),
            limits=limits,
        )
        candidates = extract_entity_candidates(
            preview.output_text,
            occurrence_id=f"preview:{preview.content_sha256}",
            parser_receipt_id=f"preview:{preview.output_sha256}",
            input_sha256=preview.output_sha256,
            limits=EntityExtractionLimits(max_candidates=2_000, context_chars=60),
        )
        return {
            **preview.model_dump(mode="json"),
            "entity_extraction": {
                "state": candidates.state,
                "warnings": list(candidates.warnings),
                "candidate_count": len(candidates.candidates),
                "candidates": [item.model_dump(mode="json") for item in candidates.candidates],
                "truth_boundary": (
                    "Candidates are temporary text matches. They are not stored evidence, "
                    "admitted entities, graph nodes, relationships, verdicts, or attribution."
                ),
            },
        }

    def command_catalog(self) -> list[dict[str, str]]:
        """Return the shared analyst command surface exposed by Pivotglass."""
        return [
            {"command": "use <indicator>", "purpose": "Investigate and pivot to an indicator"},
            {
                "command": "search [STIX type]",
                "purpose": "Search evidence already in this workspace",
            },
            {"command": "status", "purpose": "Show workspace and model status"},
            {"command": "mode [name]", "purpose": "List or switch character mode"},
            {"command": "workspace list", "purpose": "List investigation workspaces"},
            {
                "command": "workspace create <name>",
                "purpose": "Create and switch to an isolated workspace",
            },
            {"command": "workspace switch <name>", "purpose": "Switch the active workspace"},
            {
                "command": "workspace schema [name]",
                "purpose": "Validate integrity and preview any required migration",
            },
            {
                "command": "workspace export <name>",
                "purpose": "Download a portable workspace archive",
            },
            {
                "command": "workspace merge <source> <destination>",
                "purpose": "Merge evidence transactionally without changing the source",
            },
            {
                "command": "workspace clear <name> --confirm <name>",
                "purpose": "Reset investigation data while preserving the workspace",
            },
            {
                "command": "workspace delete <name> --confirm <name>",
                "purpose": "Delete an inactive workspace after explicit confirmation",
            },
            {"command": "graph", "purpose": "Render the relationship graph"},
            {
                "command": "graph layers",
                "purpose": "Inspect entity and epistemic nodes with provenance-bearing edges",
            },
            {
                "command": "graph clusters",
                "purpose": "Summarize connected evidence without implying common control or attribution",
            },
            {
                "command": "graph snapshot list|capture <analyst>|diff <before> <after>",
                "purpose": "Record and compare exact graph-cluster change without rewriting evidence",
            },
            {
                "command": "graph export <json|csv|gexf> [all|entity|epistemic|bridge]",
                "purpose": "Download the exact governed graph with layer, truth type, provenance, and rationale",
            },
            {
                "command": "graph layout list|show <name>|delete <name> --confirm <name>",
                "purpose": "Manage presentation-only saved graph layouts",
            },
            {
                "command": "graph annotate <node-id> | <text>",
                "purpose": "Attach an analyst note to a real graph node without changing evidence",
            },
            {"command": "dossier", "purpose": "Show dossier details and intelligence gaps"},
            {"command": "timeline", "purpose": "Show the ordered collection timeline"},
            {"command": "note <text>", "purpose": "Save an analyst annotation"},
            {"command": "report", "purpose": "Generate the evidence-grounded Markdown report"},
            {
                "command": "analysis show",
                "purpose": "Show questions, hypotheses, assertions, confidence, likelihood, and contradictions",
            },
            {
                "command": "analysis lifecycle",
                "purpose": "Show the scientific investigation lifecycle and unresolved work",
            },
            {
                "command": "analysis methods",
                "purpose": "List the supported structured analytic techniques and their required records",
            },
            {
                "command": "analysis priorities",
                "purpose": "Rank recorded intelligence requirements and show method-derived next-information suggestions",
            },
            {
                "command": "framework show <attack|kill_chain|diamond>",
                "purpose": "View versioned, evidence-backed framework mappings and gaps",
            },
            {
                "command": "framework manifest|navigator",
                "purpose": "Inspect the pinned ATT&CK content or export a Navigator layer",
            },
            {
                "command": "framework require <framework> <version> <content-id> | <label> | <requirement> | <factor-json>",
                "purpose": "Record an unsupported framework item as a scored intelligence requirement",
            },
            {
                "command": "framework gaps",
                "purpose": "List framework-linked intelligence requirements",
            },
            {
                "command": "integration status",
                "purpose": "Show local Synapse and SCOT4 MCP configuration without connecting",
            },
            {
                "command": "integration synapse shadow-preview|cutover-readiness|model-contract|model-deploy-plan|model-deploy-execute|model-deploy-receipt|migration-plan|shadow-execute|shadow-receipt|views|status|model|lookup|query",
                "purpose": "Preview governed graph state, inspect current cutover blockers and receipts, compile a disabled shadow migration, or run explicit read-only MCP operations",
            },
            {
                "command": "integration scot publish-preview|publication-readiness|publish-plan|publish-execute|publication-receipt|pivot-preview|pivot-inbox|pivot-accept|pivot-reject|pivot-queue|pivot-enqueue|status|get|search|entries|entities",
                "purpose": "Preview or evaluate a current publication, review authenticated SCOT pivot requests, approve exact-digest write/readback, accept a pivot into enrichment, or perform bounded SCOT4 reads",
            },
            {
                "command": "integration roast status|decode|record|analyze",
                "purpose": "Decode Interactsh OAST domains and optionally record sourced proposals for human review",
            },
            {
                "command": "integration nucleotide status|lookup-info|lookup|lookup-strict|lookup-record|fingerprint-preview|fingerprint-record|fingerprint-history|fingerprint-compare",
                "purpose": "Attribute URLs or fingerprint grouped activity, with optional governed proposal recording and no control deployment",
            },
            {
                "command": "integration proposals|review <proposal-id> <accept|reject> | <reason>|materialize <proposal-id> | <rationale>",
                "purpose": "Inspect and explicitly disposition external-derived analysis without turning it into observed evidence",
            },
            {
                "command": "analysis question <text>",
                "purpose": "Record the investigation question the evidence must answer",
            },
            {
                "command": "analysis assumption <text>",
                "purpose": "Expose a key assumption for later testing",
            },
            {
                "command": "analysis claim <type> <subject> <predicate> <value> | <statement>",
                "purpose": "Record a structured value or interval claim for deterministic conflict review",
            },
            {
                "command": "analysis hypothesis <question-id> <text>",
                "purpose": "Propose a competing explanation without treating it as fact",
            },
            {
                "command": "analysis prediction <text>",
                "purpose": "Record an observable prediction that could support or weaken the explanation",
            },
            {
                "command": "analysis signpost <text>",
                "purpose": "Record a development that should change the judgment",
            },
            {
                "command": "analysis collect <text>",
                "purpose": "Record an unscored bounded collection requirement",
            },
            {
                "command": "analysis requirement <text> | <factor-json>",
                "purpose": "Record a requirement with explicit decision, discrimination, urgency, and feasibility factors",
            },
            {
                "command": "analysis prioritize <item-id> <0-100>",
                "purpose": "Set or clear the analyst-owned priority for one information requirement",
            },
            {"command": "analysis stop <text>", "purpose": "Record when collection should stop"},
            {
                "command": "analysis limitation <text>",
                "purpose": "Preserve a known limitation in the final analytic record",
            },
            {
                "command": "analysis gap <text>",
                "purpose": "Record an intelligence gap without inventing an answer",
            },
            {
                "command": "challenges",
                "purpose": "Show hunt-specific challenges, progress, evidence basis, and rewards",
            },
            {
                "command": "badges",
                "purpose": "Show earned badges and their challenge-linked artwork",
            },
            {"command": "export <json|csv|stix|gexf>", "purpose": "Download workspace data"},
            {"command": "help", "purpose": "Show this command reference"},
            {
                "command": "model show",
                "purpose": "Show the effective provider, model, credential source, and enabled state",
            },
            {
                "command": "model list",
                "purpose": "Fetch account-visible models and evidence-based capability notes",
            },
            {
                "command": "model check",
                "purpose": "Test provider authentication and selected-model visibility",
            },
            {
                "command": "model select [provider] <model-id>",
                "purpose": "Select a model returned by the provider",
            },
            {"command": "model repair", "purpose": "Show a non-destructive model repair plan"},
            {"command": "config show", "purpose": "Show masked intelligence API configuration"},
            {
                "command": "config check <service>",
                "purpose": "Test one configured intelligence API",
            },
            {
                "command": "config enable|disable <service>",
                "purpose": "Enable or disable one intelligence source without deleting its key",
            },
            {
                "command": "<natural-language question>",
                "purpose": "Ask AP; local tools run first and the configured model synthesizes only when needed",
            },
        ]

    def completions(self, text: str) -> list[str]:
        """Return the same contextual command completions used by the TUI."""
        mode_names = [
            str(entry["display_name"]) for entry in self.mode_mgr.list_modes(public_only=True)
        ]
        return command_completions(
            text,
            mode_names=mode_names,
            workspace_names=self.ctx.workspace_mgr.list_workspaces(),
        )

    def execute_command(self, text: str) -> dict[str, Any]:
        """Route Pivotglass input local-first, then to the configured model."""
        stripped = text.strip()
        if not stripped:
            raise ValueError("command is required")
        detected = detect_ioc_type(stripped)
        if detected:
            return {"kind": "investigation", "snapshot": self.start_investigation(stripped)}

        tokens = stripped.split()
        command = tokens[0].lower()
        rest = stripped[len(tokens[0]) :].strip()
        if command in {"use", "hunt"} and rest and detect_ioc_type(rest):
            return {"kind": "investigation", "snapshot": self.start_investigation(rest)}
        if command in {"help", "?"}:
            return {"kind": "commands", "commands": self.command_catalog()}
        if command == "model":
            return {
                "kind": "text",
                "title": "Model configuration",
                "text": execute_model_command(
                    tuple(rest.split()),
                    self.model_control,
                    self._runner,
                ),
            }
        if command in {"config", "configuration"}:
            return {
                "kind": "configuration" if not rest or rest in {"show", "configure"} else "text",
                "title": "API configuration",
                "text": execute_configuration_command(
                    tuple(rest.split()),
                    self.model_control,
                ),
                "configuration": self.configuration(),
            }
        if command == "mode":
            if rest and rest != "list":
                return {
                    "kind": "state",
                    "text": f"Mode switched to {rest}.",
                    "state": self.switch_mode(rest),
                }
            lines = [
                f"{'*' if item['name'] == self.mode_mgr.active.name else ' '} "
                f"{item['display_name']}: {item['personality']}"
                for item in self.mode_mgr.list_modes(public_only=True)
            ]
            return {"kind": "text", "title": "Character modes", "text": "\n".join(lines)}
        if command == "workspace":
            parts = rest.split()
            sub = parts[0].lower() if parts else "list"
            if sub == "list":
                active = self.ctx.workspace_mgr.active
                lines = [
                    f"{'*' if name == active else ' '} {name}"
                    for name in self.ctx.workspace_mgr.list_workspaces()
                ]
                return {"kind": "text", "title": "Workspaces", "text": "\n".join(lines)}
            if sub in {"create", "switch"} and len(parts) == 2:
                if self.investigations.active_count():
                    raise ValueError("cannot change workspace while an investigation is active")
                if sub == "create":
                    self.ctx.workspace_mgr.create(parts[1])
                self.ctx.workspace_mgr.switch(parts[1])
                return {
                    "kind": "state",
                    "text": f"Workspace active: {parts[1]}",
                    "state": self.state(),
                }
            if sub == "learn" and len(parts) == 2:
                if self.investigations.active_count():
                    raise ValueError("cannot change workspace while an investigation is active")
                receipt = create_learning_workspace(self.ctx.workspace_mgr, parts[1])
                return {
                    "kind": "json",
                    "title": "Offline learning investigation ready",
                    "data": receipt,
                    "state": self.state(),
                }
            if sub == "schema" and len(parts) <= 2:
                workspace_name = parts[1] if len(parts) == 2 else None
                return {
                    "kind": "json",
                    "title": "Workspace schema and integrity",
                    "data": self.ctx.workspace_mgr.get_workspace_schema_status(workspace_name),
                }
            if sub == "export" and len(parts) == 2:
                content = json.dumps(
                    export_workspace(self.ctx.workspace_mgr, parts[1]), indent=2, default=str
                )
                return {
                    "kind": "download",
                    "filename": f"{parts[1]}-workspace.ap.json",
                    "mime": "application/json",
                    "content": content,
                }
            if sub == "merge" and len(parts) == 3:
                counts = merge_workspaces(self.ctx.workspace_mgr, parts[1], parts[2])
                if parts[2] == self.ctx.workspace_mgr.active:
                    self.ctx.workspace_mgr.switch(parts[2])
                return {
                    "kind": "json",
                    "title": "Workspace merge complete",
                    "data": {"source": parts[1], "destination": parts[2], "inserted": counts},
                }
            if (
                sub == "clear"
                and len(parts) == 4
                and parts[2] == "--confirm"
                and parts[1] == parts[3]
            ):
                cleared = self.ctx.workspace_mgr.clear(name=parts[1])
                return {
                    "kind": "json",
                    "title": "Workspace cleared",
                    "data": {"workspace": parts[1], "cleared": cleared},
                }
            if (
                sub == "delete"
                and len(parts) == 4
                and parts[2] == "--confirm"
                and parts[1] == parts[3]
            ):
                if parts[1] == self.ctx.workspace_mgr.active:
                    raise ValueError("cannot delete the active workspace; switch first")
                deleted = self.ctx.workspace_mgr.delete(parts[1])
                return {
                    "kind": "json",
                    "title": "Workspace deleted",
                    "data": {"workspace": parts[1], "deleted": deleted},
                }
            raise ValueError(
                "usage: workspace list|learn <name>|create <name>|switch <name>|schema [name]|export <name>|merge <source> <destination>|clear <name> --confirm <name>|delete <name> --confirm <name>"
            )
        if command in {"status", "show"} and (command == "status" or rest in {"", "status"}):
            summary, *_ = execute_tool(self.ctx, "get_workspace_summary", {})
            return {"kind": "text", "title": "Workspace status", "text": str(summary)}
        if command == "search":
            summary, *_ = execute_tool(self.ctx, "search_workspace", {"type_filter": rest or None})
            return {"kind": "text", "title": "Workspace search", "text": str(summary)}
        if command == "challenges":
            runs = self.ctx.workspace_mgr.get_module_runs()
            latest_target = str(runs[-1]["target"]) if runs else None
            return {
                "kind": "challenges",
                "title": "Hunt challenges",
                "data": self.ctx.challenge_mgr.refresh_for_hunt(latest_target),
            }
        if command == "badges":
            return {
                "kind": "badges",
                "title": "Earned badges",
                "data": self.ctx.workspace_mgr.get_awarded_badges(),
            }
        if command == "graph":
            if rest:
                if rest.casefold() == "layers":
                    return {
                        "kind": "json",
                        "title": "Entity and epistemic graph",
                        "data": build_investigation_graph(self.ctx.workspace_mgr).model_dump(
                            mode="json"
                        ),
                    }
                if rest.casefold() == "clusters":
                    return {
                        "kind": "json",
                        "title": "Evidence clusters",
                        "data": [
                            cluster.model_dump(mode="json")
                            for cluster in build_evidence_clusters(self.ctx.workspace_mgr)
                        ],
                    }
                parts = rest.split()
                if [item.casefold() for item in parts] == ["snapshot", "list"]:
                    return {
                        "kind": "json",
                        "title": "Evidence-cluster snapshots",
                        "data": [
                            item.model_dump(mode="json")
                            for item in EvidenceClusterHistory(self.ctx.workspace_mgr).list()
                        ],
                    }
                if len(parts) >= 3 and [item.casefold() for item in parts[:2]] == [
                    "snapshot",
                    "capture",
                ]:
                    result = EvidenceClusterHistory(self.ctx.workspace_mgr).capture(
                        captured_by=" ".join(parts[2:])
                    )
                    return {
                        "kind": "json",
                        "title": "Evidence-cluster snapshot captured",
                        "data": result.model_dump(mode="json"),
                    }
                if len(parts) == 4 and [item.casefold() for item in parts[:2]] == [
                    "snapshot",
                    "diff",
                ]:
                    result = EvidenceClusterHistory(self.ctx.workspace_mgr).diff(parts[2], parts[3])
                    return {
                        "kind": "json",
                        "title": "Evidence-cluster change",
                        "data": result.model_dump(mode="json"),
                    }
                if len(parts) in {2, 3} and parts[0].casefold() == "export":
                    from adversary_pursuit.core.investigation_graph_export import (
                        export_investigation_graph,
                    )

                    artifact = export_investigation_graph(
                        build_investigation_graph(self.ctx.workspace_mgr),
                        format=parts[1],
                        layer=parts[2] if len(parts) == 3 else "all",
                    )
                    return {
                        "kind": "download",
                        "title": "Investigation graph export",
                        "filename": artifact.filename,
                        "mime": artifact.mime,
                        "content": artifact.content,
                    }
                if len(parts) >= 2 and parts[0].casefold() == "layout":
                    action = parts[1].casefold()
                    authority = GraphPresentationAuthority(self.ctx.workspace_mgr)
                    if action == "list" and len(parts) == 2:
                        return {
                            "kind": "json",
                            "title": "Saved graph layouts",
                            "data": authority.list(),
                        }
                    if action == "show" and len(parts) >= 3:
                        return {
                            "kind": "json",
                            "title": "Saved graph layout",
                            "data": self.graph_layout(" ".join(parts[2:])),
                        }
                    if action == "delete" and "--confirm" in parts:
                        marker = parts.index("--confirm")
                        name = " ".join(parts[2:marker])
                        confirmation = " ".join(parts[marker + 1 :])
                        if not name or name != confirmation:
                            raise ValueError(
                                "deleting a graph layout requires its exact name after --confirm"
                            )
                        return {
                            "kind": "json",
                            "title": "Graph layout deleted",
                            "data": {"name": name, "deleted": authority.delete(name)},
                        }
                if parts and parts[0].casefold() == "annotate":
                    payload = rest.removeprefix(parts[0]).strip()
                    node_ref, separator, text = payload.partition("|")
                    if not separator:
                        raise ValueError("usage: graph annotate <node-id> | <text>")
                    return {
                        "kind": "json",
                        "title": "Graph annotation saved",
                        "data": self.annotate_graph(
                            {"node_ref": node_ref.strip(), "text": text.strip()}
                        ),
                    }
                if parts and parts[0].casefold() == "annotations" and len(parts) <= 2:
                    return {
                        "kind": "json",
                        "title": "Graph annotations",
                        "data": self.graph_annotations(parts[1] if len(parts) == 2 else None),
                    }
                raise ValueError(
                    "usage: graph [layers|clusters|export <json|csv|gexf> [all|entity|epistemic|bridge]|layout list|layout show <name>|layout delete <name> --confirm <name>]"
                )
            graph = RelationshipGraph()
            graph.build_from_workspace(
                self.ctx.workspace_mgr.get_stix_objects(),
                persisted_relationships(self.ctx.workspace_mgr),
            )
            return {"kind": "graph", "title": "Threat graph", "data": graph.to_dict()}
        if command in {"dossier", "gaps"}:
            summary, *_ = execute_tool(self.ctx, "get_dossier_state", {})
            return {"kind": "json", "title": "Dossier and intelligence gaps", "data": summary}
        if command == "timeline":
            return {
                "kind": "json",
                "title": "Collection timeline",
                "data": self.ctx.workspace_mgr.get_module_runs(),
            }
        if command == "note":
            if not rest:
                raise ValueError("usage: note <text>")
            self.ctx.workspace_mgr.add_note(rest)
            return {"kind": "text", "title": "Annotation saved", "text": rest}
        if command == "report":
            summary, *_ = execute_tool(self.ctx, "generate_dossier_report", {})
            return {
                "kind": "text",
                "title": "Dossier report",
                "text": str(summary),
                "printable": True,
            }
        if command == "analysis":
            result = execute_analysis_command(tuple(rest.split()), self.ctx.workspace_mgr)
            return {"kind": "json", **result, "state": self.state()}
        if command == "framework":
            result = execute_framework_command(tuple(rest.split()), self.ctx.workspace_mgr)
            if "filename" in result:
                return {
                    "kind": "download",
                    "filename": result["filename"],
                    "mime": result["mime"],
                    "content": json.dumps(result["data"], indent=2, default=str),
                }
            return {"kind": "json", **result, "state": self.state()}
        if command == "integration":
            result = execute_integration_command(
                tuple(rest.split()), self.config_mgr, self.ctx.workspace_mgr
            )
            data = result.get("data")
            if isinstance(data, dict) and data.get("start_enrichment") is True:
                request = data.get("request") if isinstance(data.get("request"), dict) else {}
                request_id = str(request.get("request_id") or "")
                target = str(request.get("indicator") or "")
                started = self.start_investigation(
                    target,
                    origin_request_id=request_id,
                )
                queue_item = next(
                    item
                    for item in AnalyticLedger(self.ctx.workspace_mgr).enrichment_requests()
                    if item["record_id"] == request_id
                )
                result["data"] = {
                    **data,
                    "start_enrichment": False,
                    "queue_item": queue_item,
                    "investigation": started,
                }
            return {"kind": "json", **result}
        if command == "export":
            return self.export_payload(rest or "stix")
        if command in {"clear", "quit", "exit", "q"}:
            return {"kind": "client", "action": command}

        # Questions and creative analyst hypotheses use the same AgentRunner
        # authority as the TUI. Its router intercepts local verbs and tools
        # before asking the configured LLM to synthesize.
        with self._command_lock:
            if self._runner is None:
                from adversary_pursuit.agent.runner import AgentRunner

                self._runner = AgentRunner(
                    tool_context=self.ctx,
                    config_mgr=self.config_mgr,
                )
            response = self._runner.handle_input(stripped)
        return {"kind": "text", "title": "AP analysis", "text": response, "synthesized": True}

    def configuration(self) -> dict[str, Any]:
        """Return masked provider and intelligence-service configuration."""
        return self.model_control.configuration_summary(getattr(self._runner, "model", None))

    def model_catalog(self, provider: str | None = None) -> dict[str, Any]:
        """Return the live account-visible catalogue with bounded capability notes."""
        profiles = self.model_control.list_models(provider)
        selected = provider or str(self.model_control.status()["provider"])
        return {
            "provider": selected,
            "models": [profile.to_dict() for profile in profiles],
            "notice": (
                "Availability comes from the provider. Strengths and limitations use "
                "local capability metadata when present; they are not quality rankings."
            ),
        }

    def configuration_advisory(self) -> dict[str, Any] | None:
        """Return one due character advisory without calling a model or provider."""
        advisory = self.configuration_advisor.poll(self.mode_mgr.active.name)
        return advisory.to_dict() if advisory is not None else None

    def check_configuration(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Test one provider or service and return only sanitized diagnostics."""
        kind = str(payload.get("kind", "")).strip().lower()
        target = str(payload.get("id", "")).strip().lower()
        if kind == "provider":
            secret = str(payload.get("secret", "")) or None
            return self.model_control.check_provider(target or None, secret).to_dict()
        if kind == "service":
            values = payload.get("values")
            secrets = (
                [str(value) for value in values] if isinstance(values, list) and values else None
            )
            return self.model_control.check_service(target, secrets).to_dict()
        raise ValueError("kind must be provider or service")

    def update_configuration(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Apply one explicit configuration mutation and return masked state."""
        action = str(payload.get("action", "")).strip().lower()
        target = str(payload.get("id", "")).strip().lower()
        if action == "model-enabled":
            self.config_mgr.set_agent_enabled(bool(payload.get("enabled")))
        elif action == "advisor-enabled":
            self.config_mgr.set_configuration_advisor_enabled(bool(payload.get("enabled")))
        elif action == "service-enabled":
            self.config_mgr.set_service_enabled(target, bool(payload.get("enabled")))
        elif action == "provider-credential":
            result = self.model_control.set_provider_credential(
                target,
                str(payload.get("secret", "")),
                verify=bool(payload.get("verify", True)),
            )
            if result.state != "ready" and bool(payload.get("verify", True)):
                return {"saved": False, "health": result.to_dict()}
            return {
                "saved": True,
                "health": result.to_dict(),
                "configuration": self.configuration(),
            }
        elif action == "service-credentials":
            values = payload.get("values")
            if not isinstance(values, list):
                raise ValueError("credential values are required")
            result = self.model_control.set_service_credentials(
                target,
                [str(value) for value in values],
                verify=bool(payload.get("verify", True)),
            )
            if result.state != "ready" and bool(payload.get("verify", True)):
                return {"saved": False, "health": result.to_dict()}
            return {
                "saved": True,
                "health": result.to_dict(),
                "configuration": self.configuration(),
            }
        elif action == "select-model":
            selected = self.model_control.select_model(
                str(payload.get("model_id", "")),
                target or None,
            )
            if self._runner is not None:
                self._runner.model = selected["runtime_model"]
        elif action == "remove-provider-credential":
            self.config_mgr.remove_provider_api_key(target)
        elif action == "remove-service-credentials":
            service = next(
                (item for item in CTI_SERVICES if item.id == target),
                None,
            )
            if service is None:
                raise ValueError(f"Unknown intelligence service: {target}")
            for key in service.config_keys:
                self.config_mgr.remove_api_key(key)
        else:
            raise ValueError("unknown configuration action")
        return {"saved": True, "configuration": self.configuration()}

    def export_payload(self, format_name: str) -> dict[str, Any]:
        """Return a browser-downloadable export without writing outside the workspace."""
        fmt = format_name.lower().removeprefix("--format").strip() or "stix"
        objects = self.ctx.workspace_mgr.get_stix_objects()
        workspace = self.ctx.workspace_mgr.active
        if fmt == "json":
            content = json.dumps(
                export_workspace(self.ctx.workspace_mgr, workspace),
                indent=2,
                default=str,
            )
            mime, suffix = "application/json", "json"
        elif fmt == "csv":
            fields = sorted(
                {
                    str(key)
                    for item in objects
                    for key in item
                    if not isinstance(item.get(key), (dict, list))
                }
            )
            stream = io.StringIO()
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(objects)
            content, mime, suffix = stream.getvalue(), "text/csv", "csv"
        elif fmt in {"stix", "gexf"}:
            summary, *_ = execute_tool(self.ctx, "export_workspace", {"format": fmt})
            content = (
                summary if isinstance(summary, str) else json.dumps(summary, indent=2, default=str)
            )
            mime, suffix = (
                ("application/xml", "gexf") if fmt == "gexf" else ("application/json", "stix.json")
            )
        else:
            raise ValueError("supported export formats: json, csv, stix, gexf")
        return {
            "kind": "download",
            "filename": f"{workspace}-pivotglass.{suffix}",
            "mime": mime,
            "content": content,
        }

    def evidence_detail(self, identifier: str) -> dict[str, Any]:
        """Return a deterministic detail projection for stored evidence."""
        return project_evidence(
            self.ctx.workspace_mgr.get_stix_objects(),
            identifier,
            persisted_relationships(self.ctx.workspace_mgr),
            self.ctx.workspace_mgr.get_module_runs(),
        )

    def investigate(self, target: str) -> dict[str, Any]:
        """Run deterministic applicable batteries and return grounded events."""
        with self._investigation_lock:
            return self._investigate_locked(target)

    def start_investigation(
        self,
        target: str,
        *,
        origin_request_id: str | None = None,
    ) -> dict[str, Any]:
        """Start an investigation and return immediately with a resumable cursor."""
        target_type, tools = self.plan(target)
        record = self.investigations.create(target, target_type)
        self.investigations.append(
            record.investigation_id,
            event_class=EventClass.SYSTEM,
            severity="info",
            lifecycle=LifecycleState.PLANNED,
            content_class=ContentClass.SYSTEM,
            summary=f"Planned {len(tools)} deterministic enrichments.",
            actions=("cancel",),
        )
        for position, tool_name in enumerate(tools, start=1):
            briefing = BRIEFINGS.get(tool_name)
            self.investigations.append(
                record.investigation_id,
                event_class=EventClass.SYSTEM,
                severity="info",
                lifecycle=LifecycleState.QUEUED,
                content_class=ContentClass.SYSTEM,
                tool=tool_name,
                source=briefing.source if briefing else tool_name,
                queue_position=position,
                briefing=asdict(briefing) if briefing else None,
                actions=("skip", "cancel"),
            )
        self.investigations.transition(record.investigation_id, LifecycleState.QUEUED)
        if origin_request_id:
            AnalyticLedger(self.ctx.workspace_mgr).transition_enrichment_request(
                origin_request_id,
                "running",
                investigation_id=record.investigation_id,
            )
        threading.Thread(
            target=self._run_investigation,
            args=(record.investigation_id, target, target_type, tools, origin_request_id),
            name=f"pivotglass-{record.investigation_id[:8]}",
            daemon=True,
        ).start()
        return self.investigations.snapshot(record.investigation_id)

    def investigation_events(self, investigation_id: str, cursor: int = 0) -> dict[str, Any]:
        """Return events after *cursor* and the authoritative current state."""
        try:
            return self.investigations.snapshot(investigation_id, cursor)
        except KeyError as exc:
            raise ValueError("unknown investigation") from exc

    def cancel_investigation(self, investigation_id: str) -> dict[str, Any]:
        """Request cancellation; the active enrichment completes before shutdown."""
        try:
            accepted = self.investigations.request_cancel(investigation_id)
        except KeyError as exc:
            raise ValueError("unknown investigation") from exc
        if accepted:
            self.investigations.append(
                investigation_id,
                event_class=EventClass.OPERATOR_ACTION,
                severity="caution",
                lifecycle=LifecycleState.RUNNING,
                content_class=ContentClass.SYSTEM,
                summary="Cancellation received; the active enrichment will finish safely.",
            )
        return self.investigations.snapshot(investigation_id)

    def alerts(self) -> dict[str, Any]:
        """Return all attention records plus unread summary."""
        alerts = self.investigations.alerts()
        unread = [item for item in alerts if not item["acknowledged"]]
        severity_rank = {"critical": 4, "error": 3, "warning": 2, "caution": 1, "info": 0}
        highest = max(
            (str(item["severity"]) for item in unread),
            key=lambda value: severity_rank.get(value, 0),
            default="clear",
        )
        return {"alerts": alerts, "unread_count": len(unread), "highest_unread": highest}

    def activity(self) -> dict[str, Any]:
        """Return bounded event history and masked operational authority state."""

        events = [
            event for snapshot in self.investigations.snapshots() for event in snapshot["events"]
        ]
        events.sort(key=lambda event: (str(event["created_at"]), str(event["event_id"])))
        events = events[-500:]
        configuration = self.configuration()
        registry = build_authority_registry(
            configuration,
            sorted(self._tool_schemas),
            events,
        )
        return {
            "events": events,
            "event_limit": 500,
            "registry": registry,
            "notice": (
                "Activity contains deterministic lifecycle and sanitized failure summaries. "
                "Narration and evidence remain separately labeled."
            ),
        }

    def diagnostic_detail(self, diagnostic_id: str) -> dict[str, Any]:
        """Return one sanitized diagnostic from the fixed Pivotglass debug log."""

        if re.fullmatch(r"[a-f0-9]{8}", diagnostic_id) is None:
            raise ValueError("invalid diagnostic reference")
        if not DEBUG_LOG_PATH.is_file():
            raise ValueError("diagnostic detail is unavailable")
        for line in reversed(DEBUG_LOG_PATH.read_text(encoding="utf-8").splitlines()[-1000:]):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("diagnostic_id") != diagnostic_id:
                continue
            context = entry.get("context") if isinstance(entry.get("context"), dict) else {}
            return {
                "diagnostic_id": diagnostic_id,
                "log_name": DEBUG_LOG_PATH.name,
                "category": str(entry.get("category") or "Unknown"),
                "summary": str(entry.get("summary") or "No sanitized summary is available."),
                "exception_type": str(entry.get("exc_type") or "Unknown"),
                "component": context.get("tool")
                or context.get("component")
                or context.get("surface"),
                "detail_scope": (
                    "Sanitized browser detail. Raw exception text, traceback, credentials, "
                    "query strings, and private file contents remain local and are not returned."
                ),
            }
        raise ValueError("diagnostic detail is unavailable")

    def acknowledge_alert(self, event_id: str) -> dict[str, Any]:
        """Acknowledge one attention record without deleting it."""
        return self.investigations.acknowledge_alert(event_id)

    def _run_investigation(
        self,
        investigation_id: str,
        target: str,
        target_type: str,
        tools: list[str],
        origin_request_id: str | None = None,
    ) -> None:
        """Execute enrichments sequentially while publishing incremental transitions."""
        with self._investigation_lock:
            self.investigations.transition(investigation_id, LifecycleState.RUNNING)
            any_results = False
            any_failures = False
            for index, tool_name in enumerate(tools):
                briefing = BRIEFINGS.get(tool_name)
                source = briefing.source if briefing else tool_name
                if self.investigations.cancellation_requested(investigation_id):
                    for skipped_tool in tools[index:]:
                        skipped_briefing = BRIEFINGS.get(skipped_tool)
                        self.investigations.append(
                            investigation_id,
                            event_class=EventClass.OPERATOR_ACTION,
                            severity="info",
                            lifecycle=LifecycleState.CANCELLED,
                            content_class=ContentClass.SYSTEM,
                            tool=skipped_tool,
                            source=(skipped_briefing.source if skipped_briefing else skipped_tool),
                            reason="operator cancellation",
                        )
                    self.investigations.transition(investigation_id, LifecycleState.CANCELLED)
                    if origin_request_id:
                        AnalyticLedger(self.ctx.workspace_mgr).transition_enrichment_request(
                            origin_request_id,
                            "cancelled",
                            investigation_id=investigation_id,
                        )
                    return
                schema = self._tool_schemas.get(tool_name)
                if schema is None:
                    self.investigations.append(
                        investigation_id,
                        event_class=EventClass.SOURCE_FAULT,
                        severity="warning",
                        lifecycle=LifecycleState.SKIPPED,
                        content_class=ContentClass.SYSTEM,
                        tool=tool_name,
                        source=source,
                        reason="tool schema unavailable",
                    )
                    continue
                self.investigations.append(
                    investigation_id,
                    event_class=EventClass.SYSTEM,
                    severity="info",
                    lifecycle=LifecycleState.RUNNING,
                    content_class=ContentClass.SYSTEM,
                    tool=tool_name,
                    source=source,
                    queue_position=index + 1,
                    briefing=asdict(briefing) if briefing else None,
                    actions=("cancel",),
                )
                before = {
                    str(item.get("id"))
                    for item in self.ctx.workspace_mgr.get_stix_objects()
                    if item.get("id")
                }
                try:
                    parameters = schema.get("parameters", {})
                    properties = parameters.get("properties", {})
                    required = parameters.get("required", ())
                    argument_name = required[0] if required else next(iter(properties), "target")
                    summary, celebration, _badges, _challenges = execute_tool(
                        self.ctx, tool_name, {argument_name: target}
                    )
                    failure = _tool_failure(summary)
                    if failure is not None:
                        any_failures = True
                        self.investigations.append(
                            investigation_id,
                            event_class=EventClass.SOURCE_FAULT,
                            severity="warning",
                            lifecycle=LifecycleState.FAILED,
                            content_class=ContentClass.SYSTEM,
                            tool=tool_name,
                            source=source,
                            reason=f"{failure['category']} failure",
                            retryable=True,
                            actions=("retry", "details"),
                            diagnostic_id=failure["diagnostic_id"] or None,
                            diagnostic_category=failure["category"],
                            next_action=failure["next_action"],
                            log_name=(DEBUG_LOG_PATH.name if failure["diagnostic_id"] else None),
                        )
                        continue
                    after_objects = self.ctx.workspace_mgr.get_stix_objects()
                    artifact_ids = tuple(
                        str(item["id"])
                        for item in after_objects
                        if item.get("id") and str(item["id"]) not in before
                    )
                    result_count = len(artifact_ids)
                    any_results = any_results or result_count > 0
                    state = LifecycleState.SUCCEEDED if result_count else LifecycleState.EMPTY
                    self.investigations.append(
                        investigation_id,
                        event_class=(EventClass.DISCOVERY if result_count else EventClass.SYSTEM),
                        severity="info",
                        lifecycle=state,
                        content_class=ContentClass.EVIDENCE,
                        tool=tool_name,
                        source=source,
                        result_count=result_count,
                        artifact_ids=artifact_ids,
                        summary=summary,
                        reason=(None if result_count else "no new artifacts stored"),
                        actions=(("details",) if result_count else ("retry",)),
                    )
                    if celebration:
                        self.investigations.append(
                            investigation_id,
                            event_class=EventClass.SYSTEM,
                            severity="info",
                            lifecycle=state,
                            content_class=ContentClass.NARRATION,
                            tool=tool_name,
                            source=source,
                            summary=str(celebration),
                        )
                except Exception as exc:  # noqa: BLE001
                    any_failures = True
                    self.investigations.append(
                        investigation_id,
                        event_class=EventClass.SOURCE_FAULT,
                        severity="warning",
                        lifecycle=LifecycleState.FAILED,
                        content_class=ContentClass.SYSTEM,
                        tool=tool_name,
                        source=source,
                        reason=str(exc),
                        retryable=True,
                        actions=("retry", "details"),
                    )
                if self.investigations.cancellation_requested(investigation_id):
                    for skipped_tool in tools[index + 1 :]:
                        skipped_briefing = BRIEFINGS.get(skipped_tool)
                        self.investigations.append(
                            investigation_id,
                            event_class=EventClass.OPERATOR_ACTION,
                            severity="info",
                            lifecycle=LifecycleState.CANCELLED,
                            content_class=ContentClass.SYSTEM,
                            tool=skipped_tool,
                            source=(skipped_briefing.source if skipped_briefing else skipped_tool),
                            reason="operator cancellation",
                        )
                    self.investigations.transition(investigation_id, LifecycleState.CANCELLED)
                    if origin_request_id:
                        AnalyticLedger(self.ctx.workspace_mgr).transition_enrichment_request(
                            origin_request_id,
                            "cancelled",
                            investigation_id=investigation_id,
                        )
                    return
            final_state = (
                LifecycleState.SUCCEEDED
                if any_results
                else LifecycleState.FAILED
                if any_failures
                else LifecycleState.EMPTY
            )
            self.investigations.transition(investigation_id, final_state)
            if origin_request_id:
                AnalyticLedger(self.ctx.workspace_mgr).transition_enrichment_request(
                    origin_request_id,
                    final_state.value,
                    investigation_id=investigation_id,
                )

    def _investigate_locked(self, target: str) -> dict[str, Any]:
        """Execute one investigation while holding the service mutation lock."""
        target_type, tools = self.plan(target)

        events: list[dict[str, Any]] = []
        for tool_name in tools:
            schema = self._tool_schemas.get(tool_name)
            if schema is None:
                continue
            parameters = schema.get("parameters", {})
            properties = parameters.get("properties", {})
            required = parameters.get("required", ())
            argument_name = required[0] if required else next(iter(properties), "target")
            briefing = BRIEFINGS.get(tool_name)
            events.append(
                {
                    "kind": "enrichment",
                    "tool": tool_name,
                    "source": briefing.source if briefing else tool_name,
                    "briefing": asdict(briefing) if briefing else None,
                }
            )
            summary, celebration, _badges, _challenges = execute_tool(
                self.ctx, tool_name, {argument_name: target}
            )
            events.append(
                {
                    "kind": "evidence",
                    "tool": tool_name,
                    "source": briefing.source if briefing else tool_name,
                    "summary": summary,
                    "celebration": celebration,
                }
            )

        return {"target": target, "target_type": target_type, "events": events}

    def plan(self, target: str) -> tuple[str, list[str]]:
        """Return the deterministic service plan without executing tools."""
        detected = detect_ioc_type(target)
        target_type = _TYPE_MAP.get(detected or "")
        if target_type is None:
            raise ValueError("Target is not a recognized indicator type")

        tools: list[str] = []
        for battery in dispatch_batteries(target_type, None):
            tools.extend(battery.tools)
        return target_type, list(dict.fromkeys(tools))

    def plan_payload(self, target: str) -> dict[str, Any]:
        """Render the service plan as teaching cards for the web client."""
        target_type, tools = self.plan(target)
        events = []
        for tool_name in tools:
            briefing = BRIEFINGS.get(tool_name)
            events.append(
                {
                    "kind": "enrichment",
                    "tool": tool_name,
                    "source": briefing.source if briefing else tool_name,
                    "briefing": asdict(briefing) if briefing else None,
                }
            )
        return {"target": target, "target_type": target_type, "events": events}

    def receive_scot_pivot_request(
        self,
        payload: dict[str, Any],
        authentication: ScotPivotAuthenticationReceipt,
    ) -> dict[str, Any]:
        """Validate and retain one authenticated request without enqueueing it."""
        requested_at_raw = str(payload.get("requested_at") or "").strip()
        try:
            requested_at = datetime.fromisoformat(requested_at_raw.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("SCOT pivot requested_at must be an ISO-8601 timestamp") from None
        raw_object_id = payload.get("scot_object_id")
        if isinstance(raw_object_id, bool):
            raise ValueError("SCOT pivot object ID must be an integer")
        try:
            scot_object_id = int(raw_object_id or 0)
        except (TypeError, ValueError):
            raise ValueError("SCOT pivot object ID must be an integer") from None
        request = validate_scot_pivot_request(
            workspace=str(payload.get("workspace") or ""),
            scot_object_type=str(payload.get("scot_object_type") or ""),
            scot_object_id=scot_object_id,
            scot_revision=(
                str(payload["scot_revision"]) if payload.get("scot_revision") is not None else None
            ),
            indicator=str(payload.get("indicator") or ""),
            requested_by=str(payload.get("requested_by") or ""),
            requested_at=requested_at,
            reason=str(payload.get("reason") or ""),
        )
        canonical = request.model_dump(mode="json")
        for field in (
            "schema_version",
            "request_id",
            "indicator_type",
            "disposition",
            "enqueue_requires_analyst_action",
        ):
            if payload.get(field) != canonical[field]:
                raise ValueError(f"SCOT pivot {field} does not match the validated request")
        if request.workspace != self.ctx.workspace_mgr.active:
            raise ValueError("SCOT pivot workspace does not match the active workspace")
        inbox_item, created = AnalyticLedger(self.ctx.workspace_mgr).record_scot_pivot_request(
            canonical,
            authentication=authentication.model_dump(mode="json"),
        )
        return {
            "request": canonical,
            "inbox_item": inbox_item,
            "created": created,
            "enqueued": False,
            "next_action": (
                f"integration scot pivot-accept {request.request_id} | <approved-by> | <reason>"
            ),
        }

def _request_json_object(raw_body: bytes) -> dict[str, Any]:
    """Decode one bounded request body without leaking decoder recursion."""

    try:
        payload = json.loads(raw_body)
    except RecursionError as exc:
        raise ValueError("request JSON exceeds the supported nesting depth") from exc
    if not isinstance(payload, dict):
        raise ValueError("request body must be an object")
    return payload


def _handler(
    service: WebCockpitService,
    web_root: Path,
    *,
    allowed_hosts: frozenset[str] | None = None,
):
    host_allowlist = allowed_hosts or frozenset({"127.0.0.1", "localhost", "[::1]"})

    class CockpitHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(web_root), **kwargs)

        def end_headers(self) -> None:
            # Pivotglass is a local live cockpit.  Never let a browser reuse an
            # earlier export after the process or source checkout has changed.
            # API responses already set the same policy explicitly.
            if not self.path.startswith("/api/"):
                self.send_header("Cache-Control", "no-store, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
            super().end_headers()

        def _json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "connect-src 'self'; img-src 'self' data:; font-src 'self'",
            )
            self.end_headers()
            self.wfile.write(body)

        def _host_allowed(self) -> bool:
            raw_host = self.headers.get("Host", "").strip().lower()
            if raw_host.startswith("["):
                closing = raw_host.find("]")
                host = raw_host[: closing + 1] if closing >= 0 else raw_host
            else:
                host = raw_host.rsplit(":", 1)[0] if raw_host.count(":") == 1 else raw_host
            return host in host_allowlist

        def _browser_mutation_allowed(self) -> bool:
            if self.headers.get_content_type() != "application/json":
                return False
            if self.headers.get("Sec-Fetch-Site", "").strip().casefold() == "cross-site":
                return False
            raw_origin = self.headers.get("Origin", "").strip()
            if not raw_origin:
                return True
            origin = urlparse(raw_origin)
            raw_host = self.headers.get("Host", "").strip().casefold()
            return (
                origin.scheme.casefold() == "http"
                and origin.netloc.casefold() == raw_host
                and not origin.username
                and not origin.password
            )

        def do_GET(self) -> None:  # noqa: N802
            if not self._host_allowed():
                self._json({"error": "configured host required"}, HTTPStatus.FORBIDDEN)
                return
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                self._json({"status": "ok", "interface": "pivotglass-web"})
                return
            if parsed.path == "/api/state":
                self._json(service.state())
                return
            if parsed.path == "/api/graph-layouts":
                name = parse_qs(parsed.query).get("name", [""])[0].strip()
                try:
                    if name:
                        self._json(service.graph_layout(name))
                    else:
                        self._json(
                            {
                                "layouts": GraphPresentationAuthority(
                                    service.ctx.workspace_mgr
                                ).list()
                            }
                        )
                except ValueError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
                return
            if parsed.path == "/api/graph-annotations":
                node_ref = parse_qs(parsed.query).get("node_ref", [""])[0].strip()
                try:
                    self._json(service.graph_annotations(node_ref or None))
                except ValueError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
                return
            if parsed.path == "/api/completions":
                text = parse_qs(parsed.query).get("text", [""])[0]
                self._json({"completions": service.completions(text)})
                return
            if parsed.path == "/api/configuration":
                self._json(service.configuration())
                return
            if parsed.path == "/api/models":
                provider = parse_qs(parsed.query).get("provider", [""])[0].strip()
                try:
                    self._json(service.model_catalog(provider or None))
                except ValueError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if parsed.path == "/api/advisories":
                self._json({"advisory": service.configuration_advisory()})
                return
            if parsed.path == "/api/plan":
                try:
                    target = parse_qs(parsed.query).get("target", [""])[0].strip()
                    if not target:
                        raise ValueError("target is required")
                    self._json(service.plan_payload(target))
                except ValueError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if parsed.path.startswith("/api/investigations/") and parsed.path.endswith("/events"):
                try:
                    investigation_id = parsed.path.split("/")[3]
                    raw_cursor = parse_qs(parsed.query).get("cursor", ["0"])[0]
                    self._json(service.investigation_events(investigation_id, int(raw_cursor)))
                except (ValueError, IndexError) as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if parsed.path.startswith("/api/evidence/"):
                try:
                    identifier = parsed.path.removeprefix("/api/evidence/").strip()
                    if not identifier:
                        raise ValueError("evidence reference is required")
                    self._json(service.evidence_detail(identifier))
                except ValueError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
                return
            if parsed.path == "/api/alerts":
                self._json(service.alerts())
                return
            if parsed.path == "/api/activity":
                self._json(service.activity())
                return
            if parsed.path.startswith("/api/diagnostics/"):
                try:
                    diagnostic_id = parsed.path.removeprefix("/api/diagnostics/").strip()
                    self._json(service.diagnostic_detail(diagnostic_id))
                except ValueError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
                return
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            if not self._host_allowed():
                self._json({"error": "configured host required"}, HTTPStatus.FORBIDDEN)
                return
            parsed = urlparse(self.path)
            is_cancel = parsed.path.startswith("/api/investigations/") and parsed.path.endswith(
                "/cancel"
            )
            is_ack = parsed.path.startswith("/api/alerts/") and parsed.path.endswith("/acknowledge")
            if (
                parsed.path
                not in {
                    "/api/investigate",
                    "/api/mode",
                    "/api/command",
                    "/api/annotate",
                    "/api/configuration/check",
                    "/api/configuration/update",
                    "/api/graph-layouts",
                    "/api/graph-annotations",
                    "/api/documents/preview",
                    "/api/integrations/scot/pivot-request",
                }
                and not is_cancel
                and not is_ack
            ):
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            if (
                parsed.path != "/api/integrations/scot/pivot-request"
                and not self._browser_mutation_allowed()
            ):
                status = (
                    HTTPStatus.UNSUPPORTED_MEDIA_TYPE
                    if self.headers.get_content_type() != "application/json"
                    else HTTPStatus.FORBIDDEN
                )
                self._json({"error": "same-origin application/json required"}, status)
                return
            try:
                content_lengths = self.headers.get_all("Content-Length", [])
                if len(content_lengths) > 1:
                    raise ValueError("invalid Content-Length")
                content_length = (content_lengths[0] if content_lengths else "0").strip(" \t")
                if not content_length.isascii() or not content_length.isdecimal():
                    raise ValueError("invalid Content-Length")
                length = int(content_length)
                request_limit = (
                    14 * 1024 * 1024 if parsed.path == "/api/documents/preview" else 16_384
                )
                if length > request_limit:
                    raise ValueError("request too large")
                raw_body = self.rfile.read(length) or b"{}"
                if parsed.path == "/api/integrations/scot/pivot-request":
                    if self.headers.get_content_type() != "application/json":
                        raise ValueError("SCOT pivot request requires application/json")
                    authentication = authenticate_scot_pivot_request(
                        service.config_mgr.get_scot_pivot_secret(),
                        key_id=self.headers.get("X-Pivotglass-Key-Id", ""),
                        timestamp=self.headers.get("X-Pivotglass-Timestamp", ""),
                        nonce=self.headers.get("X-Pivotglass-Nonce", ""),
                        signature=self.headers.get("X-Pivotglass-Signature", ""),
                        body=raw_body,
                    )
                    pivot_payload = _request_json_object(raw_body)
                    result = service.receive_scot_pivot_request(pivot_payload, authentication)
                    self._json(
                        result,
                        HTTPStatus.CREATED if result["created"] else HTTPStatus.OK,
                    )
                    return
                payload = _request_json_object(raw_body)
                if parsed.path == "/api/configuration/check":
                    self._json(service.check_configuration(payload))
                    return
                if parsed.path == "/api/configuration/update":
                    self._json(service.update_configuration(payload))
                    return
                if parsed.path == "/api/graph-layouts":
                    self._json(service.update_graph_layout(payload))
                    return
                if parsed.path == "/api/graph-annotations":
                    self._json(service.annotate_graph(payload))
                    return
                if parsed.path == "/api/documents/preview":
                    self._json(service.preview_document(payload))
                    return
                if parsed.path == "/api/mode":
                    name = str(payload.get("name", "")).strip()
                    if not name:
                        raise ValueError("mode name is required")
                    self._json(service.switch_mode(name))
                    return
                if parsed.path == "/api/command":
                    command = str(payload.get("command", "")).strip()
                    expected_workspace = str(payload.get("workspace", "")).strip()
                    with service._command_lock:
                        if (
                            expected_workspace
                            and expected_workspace != service.ctx.workspace_mgr.active
                        ):
                            raise ValueError("workspace changed; queue item was not executed")
                        self._json(service.execute_command(command), HTTPStatus.ACCEPTED)
                    return
                if parsed.path == "/api/annotate":
                    text = str(payload.get("text", "")).strip()
                    stix_id = str(payload.get("stix_id", "")).strip() or None
                    if not text:
                        raise ValueError("annotation text is required")
                    service.ctx.workspace_mgr.add_note(text, stix_id)
                    self._json({"saved": True})
                    return
                if is_cancel:
                    investigation_id = parsed.path.split("/")[3]
                    self._json(service.cancel_investigation(investigation_id))
                    return
                if is_ack:
                    event_id = parsed.path.removeprefix("/api/alerts/").removesuffix("/acknowledge")
                    self._json(service.acknowledge_alert(event_id))
                    return
                target = str(payload.get("target", "")).strip()
                if not target:
                    raise ValueError("target is required")
                self._json(service.start_investigation(target), HTTPStatus.ACCEPTED)
            except ScotPivotAuthenticationError as exc:
                status = (
                    HTTPStatus.SERVICE_UNAVAILABLE
                    if "not configured" in str(exc) or "at least 32 bytes" in str(exc)
                    else HTTPStatus.UNAUTHORIZED
                )
                self._json({"error": str(exc)}, status)
            except (ValueError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

        def log_message(self, format: str, *args: object) -> None:
            _LOG.debug("web cockpit: " + format, *args)

    return CockpitHandler


def run_web(*, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    """Serve the built cockpit locally and optionally open the default browser."""
    normalized_host = host.strip().lower()
    if normalized_host in {"", "0.0.0.0", "::"}:
        raise ValueError(
            "Pivotglass requires an explicit loopback or LAN address; "
            "wildcard interface binding is not allowed."
        )
    web_root = _web_root()
    if not web_root.joinpath("index.html").exists():
        raise RuntimeError("Web cockpit is not built. Run `npm ci && npm run build` in web/.")
    if _source_web_build_is_stale(web_root):
        raise RuntimeError(
            "Web cockpit export is older than its source. Run `npm run build` in web/ "
            "before launching `ap`."
        )
    service = WebCockpitService()
    allowed_hosts = frozenset({"127.0.0.1", "localhost", "[::1]", normalized_host})
    server = ThreadingHTTPServer(
        (host, port),
        _handler(service, web_root, allowed_hosts=allowed_hosts),
    )
    url = f"http://{host}:{server.server_port}"
    print(f"Pivotglass cockpit: {url}")
    if open_browser:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
