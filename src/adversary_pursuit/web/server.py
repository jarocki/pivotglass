"""Loopback-only HTTP adapter for the Pivotglass web cockpit.

The adapter deliberately exposes existing domain authorities instead of
reimplementing tools or workspace behavior in JavaScript.
"""

from __future__ import annotations

import json
import logging
import threading
import webbrowser
from dataclasses import asdict
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from rich.text import Text

from adversary_pursuit.agent.battery_registry import dispatch_batteries
from adversary_pursuit.agent.enrichment_briefings import BRIEFINGS
from adversary_pursuit.agent.tools import ToolContext, create_tools, execute_tool
from adversary_pursuit.agent.tui.themes import (
    COCKPIT_PROFILES,
    DEFAULT_THEMES,
    PURSUIT_TITLES,
)
from adversary_pursuit.core.investigation import (
    ContentClass,
    EventClass,
    InvestigationStore,
    LifecycleState,
    utc_now,
)
from adversary_pursuit.core.ioc_types import detect_ioc_type
from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus
from adversary_pursuit.dossier.state import load_dossier_state
from adversary_pursuit.gamification.modes import DEFAULT_MODES, ModeManager

_LOG = logging.getLogger(__name__)
_SOURCE_WEB_ROOT = Path(__file__).parents[3] / "web" / "out"
_PACKAGED_WEB_ROOT = Path(__file__).with_name("static")
_WEB_ROOT = _SOURCE_WEB_ROOT if _SOURCE_WEB_ROOT.exists() else _PACKAGED_WEB_ROOT
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


class WebCockpitService:
    """JSON-facing adapter around the existing deterministic tool context."""

    def __init__(self, ctx: ToolContext | None = None) -> None:
        self.ctx = ctx or ToolContext()
        self._investigation_lock = threading.Lock()
        self.investigations = InvestigationStore()
        self.mode_mgr = ModeManager()
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
        dossier_state = load_dossier_state(self.ctx.workspace_mgr)
        dossier_slots = []
        for slot_name in DossierSlotName:
            slot = dossier_state.slots.get(slot_name) if dossier_state is not None else None
            dossier_slots.append(
                {
                    "name": slot_name.value,
                    "status": slot.status.value if slot is not None else SlotStatus.EMPTY.value,
                    "evidence_count": slot.evidence_count if slot is not None else 0,
                }
            )
        modes = []
        for entry in self.mode_mgr.list_modes():
            name = entry["name"]
            modes.append(
                {
                    **entry,
                    "greeting": Text.from_markup(DEFAULT_MODES[name].greeting).plain,
                    "theme": asdict(DEFAULT_THEMES[name]),
                    "cockpit": asdict(COCKPIT_PROFILES[name]),
                    "pursuit_title": PURSUIT_TITLES[name],
                }
            )
        return {
            "workspace": "default",
            "stats": self.ctx.workspace_mgr.get_workspace_stats(),
            "objects": objects,
            "briefings": {name: asdict(value) for name, value in BRIEFINGS.items()},
            "character": self.mode_mgr.active.name,
            "modes": modes,
            "dossier_slots": dossier_slots,
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
        self.mode_mgr.switch(name)
        return self.state()

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
            summary=f"Planned {len(tools)} deterministic probes.",
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
        """Request cancellation; the active probe completes before shutdown."""
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
                summary="Cancellation received; the active probe will finish safely.",
            )
        return self.investigations.snapshot(investigation_id)

    def _run_investigation(
        self,
        investigation_id: str,
        target: str,
        target_type: str,
        tools: list[str],
    ) -> None:
        """Execute probes sequentially while publishing incremental transitions."""
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
                    "kind": "probe",
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
                    "kind": "probe",
                    "tool": tool_name,
                    "source": briefing.source if briefing else tool_name,
                    "briefing": asdict(briefing) if briefing else None,
                }
            )
        return {"target": target, "target_type": target_type, "events": events}


def _handler(service: WebCockpitService, web_root: Path):
    class CockpitHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(web_root), **kwargs)

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
            host = self.headers.get("Host", "").split(":", 1)[0].lower()
            return host in {"127.0.0.1", "localhost", "[::1]"}

        def do_GET(self) -> None:  # noqa: N802
            if not self._host_allowed():
                self._json({"error": "loopback host required"}, HTTPStatus.FORBIDDEN)
                return
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                self._json({"status": "ok", "interface": "pivotglass-web"})
                return
            if parsed.path == "/api/state":
                self._json(service.state())
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
            if parsed.path.startswith("/api/investigations/") and parsed.path.endswith(
                "/events"
            ):
                try:
                    investigation_id = parsed.path.split("/")[3]
                    raw_cursor = parse_qs(parsed.query).get("cursor", ["0"])[0]
                    self._json(service.investigation_events(investigation_id, int(raw_cursor)))
                except (ValueError, IndexError) as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            if not self._host_allowed():
                self._json({"error": "loopback host required"}, HTTPStatus.FORBIDDEN)
                return
            parsed = urlparse(self.path)
            is_cancel = parsed.path.startswith("/api/investigations/") and parsed.path.endswith(
                "/cancel"
            )
            if parsed.path not in {"/api/investigate", "/api/mode"} and not is_cancel:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 16_384:
                    raise ValueError("request too large")
                payload = json.loads(self.rfile.read(length) or b"{}")
                if parsed.path == "/api/mode":
                    name = str(payload.get("name", "")).strip()
                    if not name:
                        raise ValueError("mode name is required")
                    self._json(service.switch_mode(name))
                    return
                if is_cancel:
                    investigation_id = parsed.path.split("/")[3]
                    self._json(service.cancel_investigation(investigation_id))
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
    if not _WEB_ROOT.joinpath("index.html").exists():
        raise RuntimeError("Web cockpit is not built. Run `npm ci && npm run build` in web/.")
    service = WebCockpitService()
    server = ThreadingHTTPServer((host, port), _handler(service, _WEB_ROOT))
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
