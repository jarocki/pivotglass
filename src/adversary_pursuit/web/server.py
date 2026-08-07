"""Loopback-only HTTP adapter for the Pivotglass web cockpit.

The adapter deliberately exposes existing domain authorities instead of
reimplementing tools or workspace behavior in JavaScript.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import threading
import webbrowser
from dataclasses import asdict
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
from adversary_pursuit.core.error_interpreter import DEBUG_LOG_PATH
from adversary_pursuit.core.evidence_detail import evidence_ref, list_evidence, project_evidence
from adversary_pursuit.core.graph import RelationshipGraph, persisted_relationships
from adversary_pursuit.core.information_requirements import build_information_requirements
from adversary_pursuit.core.investigation import (
    ContentClass,
    EventClass,
    InvestigationStore,
    LifecycleState,
    utc_now,
)
from adversary_pursuit.core.ioc_types import detect_ioc_type
from adversary_pursuit.core.operational_status import build_authority_registry
from adversary_pursuit.core.visualization import build_visualization_intents
from adversary_pursuit.core.workspace_admin import (
    export_workspace,
    merge_workspaces,
)
from adversary_pursuit.dossier.slot_inference import infer_dossier_state
from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus
from adversary_pursuit.dossier.state import load_dossier_state
from adversary_pursuit.gamification.modes import DEFAULT_MODES, display_mode_name

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
    source_files = (
        *(_SOURCE_WEB_DIR / "app").glob("**/*.ts"),
        *(_SOURCE_WEB_DIR / "app").glob("**/*.tsx"),
        *(_SOURCE_WEB_DIR / "app").glob("**/*.css"),
        *(_SOURCE_WEB_DIR / "app").glob("**/*.json"),
        _SOURCE_WEB_DIR / "next.config.ts",
        _SOURCE_WEB_DIR / "package.json",
    )
    return any(
        source.is_file() and source.stat().st_mtime_ns > exported_at for source in source_files
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
        visualizations = build_visualization_intents(
            workspace=self.ctx.workspace_mgr.active,
            objects=objects,
            dossier_slots=dossier_slots,
            graph=relationship_graph.to_dict(),
            investigations=self.investigations.snapshots(),
        )
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
        analysis = AnalyticLedger(self.ctx.workspace_mgr).snapshot()
        analysis["information_requirements"] = build_information_requirements(analysis)
        analysis["rigor"] = build_analytic_rigor(analysis)
        return {
            "workspace": self.ctx.workspace_mgr.active,
            "stats": self.ctx.workspace_mgr.get_workspace_stats(),
            "objects": list_evidence(objects),
            "briefings": {name: asdict(value) for name, value in BRIEFINGS.items()},
            "character": self.mode_mgr.active.name,
            "modes": modes,
            "dossier_slots": dossier_slots,
            "visualizations": [intent.model_dump(mode="json") for intent in visualizations],
            "analysis": analysis,
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
                "command": "workspace delete <name> --confirm <name>",
                "purpose": "Delete an inactive workspace after explicit confirmation",
            },
            {"command": "graph", "purpose": "Render the relationship graph"},
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
                sub == "delete"
                and len(parts) == 4
                and parts[2] == "--confirm"
                and parts[1] == parts[3]
            ):
                if parts[1] == self.ctx.workspace_mgr.active:
                    raise ValueError("cannot delete the active workspace; switch first")
                self.ctx.workspace_mgr.delete(parts[1])
                return {"kind": "text", "title": "Workspace deleted", "text": parts[1]}
            raise ValueError(
                "usage: workspace list|create <name>|switch <name>|schema [name]|export <name>|merge <source> <destination>|delete <name> --confirm <name>"
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

    def start_investigation(self, target: str) -> dict[str, Any]:
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
        threading.Thread(
            target=self._run_investigation,
            args=(record.investigation_id, target, target_type, tools),
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
            event
            for snapshot in self.investigations.snapshots()
            for event in snapshot["events"]
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
                "component": context.get("tool") or context.get("component") or context.get("surface"),
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
    ) -> None:
        """Execute enrichments sequentially while publishing incremental transitions."""
        with self._investigation_lock:
            self.investigations.transition(investigation_id, LifecycleState.RUNNING)
            any_results = False
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
            final_state = LifecycleState.SUCCEEDED if any_results else LifecycleState.EMPTY
            self.investigations.transition(investigation_id, final_state)

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
                }
                and not is_cancel
                and not is_ack
            ):
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 16_384:
                    raise ValueError("request too large")
                payload = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(payload, dict):
                    raise ValueError("request body must be an object")
                if parsed.path == "/api/configuration/check":
                    self._json(service.check_configuration(payload))
                    return
                if parsed.path == "/api/configuration/update":
                    self._json(service.update_configuration(payload))
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
