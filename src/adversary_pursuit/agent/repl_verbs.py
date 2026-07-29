"""REPL verb parser and dispatcher — local-first TUI terminal commands.

Local verbs intercept user input BEFORE any LLM roundtrip. They handle
canonical terminal operations (help, status, clear, quit, exit, q, mode,
use) deterministically and instantly, with character voice provided by the
phrase cache (DEC-PHRASE-CACHE-001).

Only genuinely investigation-scoped natural language falls through to the
LLM. This module is the single authority for local verb dispatch
(DEC-REPL-VERBS-AUTHORITY-001).

Parse contract mirrors yield_commands.py: verb-first, returns None for
anything that is not a recognised local verb pattern, so callers can route
None to yield_commands → LLM without ambiguity.

@decision DEC-REPL-VERBS-AUTHORITY-001
@title repl_verbs.py is the single authority for local terminal verb dispatch
@status accepted
@rationale The operator directive "all commands should run locally unless they
           must use an LLM" requires a clean intercept layer before the LLM
           roundtrip boundary. Placing this logic in a dedicated module mirrors
           yield_commands.py (DEC-YIELD-COMMANDS-001) and keeps the runner.py
           priority order explicit: verb → yield → LLM (DEC-RUNNER-INPUT-PRIORITY-001).
           Character narration comes from phrases.py via pick(). Control-plane
           mode output is intentionally deterministic: exact state must not
           vary with persona phrase selection.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from adversary_pursuit.core.ioc_types import detect_ioc_type
from adversary_pursuit.gamification.modes import (
    DEFAULT_MODES,
    LEGACY_MODE_ALIASES,
    PUBLIC_MODE_ORDER,
    RETIRED_MODES,
    display_mode_name,
)
from adversary_pursuit.gamification.phrases import pick

# ---------------------------------------------------------------------------
# Verb registry
# ---------------------------------------------------------------------------

# Zero-argument verbs
_NO_ARG_VERBS: frozenset[str] = frozenset({"help", "?", "status", "clear", "quit", "exit", "q"})

# One-argument verbs
_ONE_ARG_VERBS: frozenset[str] = frozenset({"mode", "use"})
_FREE_ARG_VERBS: frozenset[str] = frozenset(
    {
        "workspace",
        "search",
        "graph",
        "export",
        "report",
        "dossier",
        "gaps",
        "timeline",
        "note",
        "hint",
        "challenges",
        "autopivot",
        "model",
        "theme",
    }
)

_ALL_VERBS: frozenset[str] = _NO_ARG_VERBS | _ONE_ARG_VERBS | _FREE_ARG_VERBS

# Known mode names (from DEFAULT_MODES — single authority)
_KNOWN_MODES: frozenset[str] = frozenset(DEFAULT_MODES.keys())
_ACCEPTED_MODE_NAMES: frozenset[str] = frozenset(
    {*DEFAULT_MODES, *LEGACY_MODE_ALIASES, *RETIRED_MODES}
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplVerb:
    """A parsed REPL verb.

    Parameters
    ----------
    name:
        Canonical verb name (e.g. "help", "quit", "mode", "use").
    args:
        Positional args after the verb. Empty tuple for zero-arg verbs;
        single-element tuple for one-arg verbs.
    """

    name: str
    args: tuple[str, ...]


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_repl_verb(text: str) -> ReplVerb | None:
    """Parse *text* as a local REPL verb.

    Verb-first parse — returns a ReplVerb when *text* matches a known
    verb pattern exactly. Returns None for anything that should route to
    yield_commands or the LLM.

    Grammar:
        help, ?, status, clear, quit, exit, q  → ReplVerb(name, ())
        mode, mode list                         → ReplVerb("mode_list", ())
        mode <name>                             → ReplVerb("mode", (name,))
        use <ioc>                               → ReplVerb("use", (ioc,))
                                                  only when ioc looks like an
                                                  IOC (domain/IP/hash/email/URL).
                                                  Otherwise returns None so
                                                  natural-language falls to LLM.

    Rejection cases (returns None — these fall through to yield or LLM):
        help me please            — extra tokens after zero-arg verb
        use foo com bar           — multi-token argument after "use"
        use notareal              — single token after "use" but no IOC shape
        quit please               — "quit" with trailing tokens

    Parameters
    ----------
    text:
        Raw input string, already stripped.

    Returns
    -------
    ReplVerb | None
    """
    stripped = text.strip()
    if not stripped:
        return None

    tokens = stripped.split()
    verb_raw = tokens[0]
    verb = verb_raw.lower()

    if verb not in _ALL_VERBS:
        return None

    if verb in _FREE_ARG_VERBS:
        return ReplVerb(name=verb, args=tuple(tokens[1:]))

    # ``mode`` and ``mode list`` are deterministic local catalogue commands.
    if verb == "mode" and (len(tokens) == 1 or (len(tokens) == 2 and tokens[1].lower() == "list")):
        return ReplVerb(name="mode_list", args=())

    # --- Zero-argument verbs ---
    if verb in _NO_ARG_VERBS:
        # Must appear alone — any trailing tokens mean it is not a local verb
        # (e.g. "help me please" should go to the LLM).
        if len(tokens) == 1:
            # Normalise "?" to "help" for dispatch simplicity
            canonical = "help" if verb == "?" else verb
            return ReplVerb(name=canonical, args=())
        return None

    # --- One-argument verbs ---
    if verb not in _ONE_ARG_VERBS:
        return None  # unreachable; defensive

    if len(tokens) < 2:  # noqa: PLR2004
        # "use" alone — no argument → route to LLM
        return None

    if len(tokens) > 2 and verb != "mode":  # noqa: PLR2004
        # Multiple tokens after the verb — route to LLM.
        # "use foo com bar" is probably a natural-language query.
        return None

    arg = " ".join(tokens[1:]) if verb == "mode" else tokens[1]

    if verb == "use":
        # Only dispatch locally if the argument looks like an IOC.
        # detect_ioc_type returns None for plain words that aren't IOCs.
        if detect_ioc_type(arg) is None:
            return None
        return ReplVerb(name="use", args=(arg,))

    if verb == "mode":
        # Always recognise "mode <something>" as a local verb — even when the
        # mode name is unknown, we dispatch locally and return a character-voiced
        # "unknown mode: <name>" response (rather than sending it to the LLM).
        if len(tokens) > 2 and arg.lower() not in _ACCEPTED_MODE_NAMES:
            return None
        return ReplVerb(name="mode", args=(arg,))

    return None  # unreachable; defensive


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def dispatch_repl_verb(
    verb: ReplVerb,
    ctx,  # ToolContext — avoid circular import; duck-typed at runtime
    mode_mgr,  # ModeManager | None
    workspace_mgr,  # WorkspaceManager | None
    status_bar=None,  # _StatusHook | None
    scrollback_clear: Callable[[], None] | None = None,
    event_bus=None,  # EventBus | None
) -> str:
    """Dispatch a parsed REPL verb locally.

    All character-voiced output comes from PHRASES via pick(). Structural
    status labels remain fixed for scanability (DEC-PHRASE-CACHE-001,
    DEC-PHRASES-REPL-VERBS-001).

    Parameters
    ----------
    verb:
        Parsed ReplVerb from parse_repl_verb().
    ctx:
        ToolContext — used to read workspace_mgr, mode_mgr if not explicitly
        passed. May be None in tests.
    mode_mgr:
        ModeManager instance. Falls back to ctx.mode_mgr when None.
    workspace_mgr:
        WorkspaceManager instance. Falls back to ctx.workspace_mgr when None.
    status_bar:
        Optional _StatusHook. Not used by most local verbs; reserved for
        future status-pane updates.
    scrollback_clear:
        Callable invoked for the "clear" verb. If None, clear is a no-op.
    event_bus:
        EventBus for "use" verb to publish TargetChanged. When None the
        event is skipped silently (no crash).

    Returns
    -------
    str
        Character-voiced response to emit to scrollback.

    Raises
    ------
    SystemExit
        When the verb is "quit", "exit", or "q".
    """
    # Resolve mode_mgr and workspace_mgr from ctx as fallback
    _mode_mgr = mode_mgr
    _workspace_mgr = workspace_mgr
    if _mode_mgr is None and ctx is not None:
        _mode_mgr = getattr(ctx, "mode_mgr", None)
    if _workspace_mgr is None and ctx is not None:
        _workspace_mgr = getattr(ctx, "workspace_mgr", None)

    # Determine active character name for pick()
    character = "default"
    if _mode_mgr is not None:
        try:
            character = _mode_mgr.active.name
        except Exception:  # noqa: BLE001
            character = "default"

    name = verb.name

    # --- help ---
    if name == "help":
        return pick(character, "help:tui_overview")

    # --- status ---
    if name == "status":
        intro = pick(character, "status_intro")
        lines = [intro]
        # Workspace state
        if _workspace_mgr is not None:
            try:
                active_ws = _workspace_mgr.active
            except RuntimeError:
                active_ws = "(none)"
            lines.append(f"  workspace : {active_ws}")
        # Character / mode
        if _mode_mgr is not None:
            try:
                active_mode = _mode_mgr.active
                lines.append(f"  mode      : {active_mode.name}")
            except Exception:  # noqa: BLE001
                pass
        return "\n".join(lines)

    # --- clear ---
    if name == "clear":
        if scrollback_clear is not None:
            try:
                scrollback_clear()
            except Exception:  # noqa: BLE001
                pass
        return ""

    # --- restored deterministic analyst commands ---
    if name in {"search", "graph", "dossier", "gaps", "report", "hint", "challenges"}:
        if ctx is None:
            return "Command context unavailable."
        from adversary_pursuit.agent.tools import execute_tool

        tool_and_args = {
            "search": ("search_workspace", {"type_filter": verb.args[0] if verb.args else None}),
            "graph": ("render_graph", {}),
            "dossier": ("get_dossier_state", {}),
            "gaps": ("get_dossier_state", {}),
            "report": ("generate_dossier_report", {}),
            "hint": ("get_next_hint", {"module": verb.args[0] if verb.args else None}),
            "challenges": ("list_challenges", {}),
        }
        tool, arguments = tool_and_args[name]
        summary, *_ = execute_tool(ctx, tool, arguments)
        return str(summary)

    if name == "timeline":
        if _workspace_mgr is None:
            return "Workspace unavailable."
        runs = _workspace_mgr.get_module_runs()
        if not runs:
            return "No collection events in the active workspace."
        return "\n".join(
            f"{run['timestamp']} · {run['module_name']} · {run['target']} · "
            f"{run['result_count']} results"
            for run in runs
        )

    if name == "note":
        if _workspace_mgr is None or not verb.args:
            return "Usage: note <text>"
        text = " ".join(verb.args)
        _workspace_mgr.add_note(text)
        return "Analyst note saved."

    if name == "export":
        if ctx is None:
            return "Command context unavailable."
        from adversary_pursuit.agent.tools import execute_tool

        fmt = verb.args[0].lower() if verb.args else "stix"
        if fmt not in {"json", "csv", "stix", "gexf"}:
            return "Export formats: json, csv, stix, gexf."
        summary, *_ = execute_tool(ctx, "export_workspace", {"format": fmt})
        return str(summary)

    if name == "theme":
        import os

        choice = verb.args[0].lower() if len(verb.args) == 1 else ""
        if choice not in {"light", "dark", "high"}:
            return "Usage: theme light|dark|high"
        if choice == "high":
            os.environ["AP_TUI_COLOR_SCHEME"] = "dark"
            os.environ["AP_TUI_HIGH_CONTRAST"] = "1"
            label = "High contrast"
        else:
            os.environ["AP_TUI_COLOR_SCHEME"] = choice
            os.environ.pop("AP_TUI_HIGH_CONTRAST", None)
            label = choice.title()
        invalidate = getattr(status_bar, "invalidate", None)
        if callable(invalidate):
            invalidate()
        return f"Display theme: {label}"

    if name == "workspace":
        if _workspace_mgr is None:
            return "Workspace unavailable."
        sub = verb.args[0].lower() if verb.args else "list"
        if sub == "list":
            return "\n".join(_workspace_mgr.list_workspaces())
        if sub in {"create", "switch"} and len(verb.args) == 2:
            if sub == "create":
                _workspace_mgr.create(verb.args[1])
            _workspace_mgr.switch(verb.args[1])
            return f"Workspace active: {verb.args[1]}"
        if sub == "export" and len(verb.args) == 2:
            from adversary_pursuit.core.workspace_admin import export_workspace

            return json.dumps(
                export_workspace(_workspace_mgr, verb.args[1]),
                indent=2,
                default=str,
            )
        if sub == "merge" and len(verb.args) == 3:
            from adversary_pursuit.core.workspace_admin import merge_workspaces

            counts = merge_workspaces(_workspace_mgr, verb.args[1], verb.args[2])
            return json.dumps(
                {
                    "source": verb.args[1],
                    "destination": verb.args[2],
                    "inserted": counts,
                },
                indent=2,
            )
        if (
            sub == "delete"
            and len(verb.args) == 4
            and verb.args[2] == "--confirm"
            and verb.args[1] == verb.args[3]
        ):
            if verb.args[1] == _workspace_mgr.active:
                return "Cannot delete the active workspace; switch first."
            _workspace_mgr.delete(verb.args[1])
            return f"Workspace deleted: {verb.args[1]}"
        return (
            "Usage: workspace list|create <name>|switch <name>|export <name>|"
            "merge <source> <destination>|delete <name> --confirm <name>"
        )

    if name == "autopivot":
        if ctx is None or not verb.args or verb.args[0].lower() not in {"on", "off"}:
            return "Usage: autopivot on|off"
        enabled = verb.args[0].lower() == "on"
        ctx.set_autopivot(enabled)
        return f"Auto-pivot {'enabled' if enabled else 'disabled'}."

    if name == "model":
        runner_model = getattr(ctx, "model", None) if ctx is not None else None
        return f"Configured model: {runner_model or 'managed by AgentRunner/configuration'}"

    # --- quit / exit / q ---
    if name in ("quit", "exit", "q"):
        farewell = pick(character, "farewell")
        # Print farewell before raising so the caller can emit it first
        raise _FarewellExit(farewell)

    # --- use <target> ---
    if name == "use":
        target = verb.args[0]
        # A target pivot remains inside the active investigation workspace.
        # Workspace lifecycle is controlled only by the explicit ``workspace``
        # command; treating an IOC as a workspace name fragments one case graph
        # and makes ``use`` disagree with Pivotglass.
        # Publish TargetChanged event (best-effort)
        if event_bus is not None:
            try:
                from adversary_pursuit.agent.tui.events import TargetChanged
                from adversary_pursuit.core.ioc_types import detect_ioc_type

                ioc_type = detect_ioc_type(target)
                _stix_type = _ioc_to_stix_type(ioc_type)
                event_bus.publish(TargetChanged(target=target, target_type=_stix_type))
            except Exception:  # noqa: BLE001
                pass
        phrase = pick(character, "target_set:acknowledged")
        return phrase.format(target=target)

    # --- mode <name> ---
    if name == "mode":
        mode_name = verb.args[0].lower()
        if _mode_mgr is not None and mode_name in _ACCEPTED_MODE_NAMES:
            try:
                new_mode = _mode_mgr.switch(mode_name)
                return f"Mode switched: {display_mode_name(new_mode.name)}\n{new_mode.greeting}"
            except ValueError as exc:
                return str(exc)
        available = ", ".join(display_mode_name(item) for item in PUBLIC_MODE_ORDER)
        return f"Unknown mode: {mode_name}\nAvailable modes: {available}"

    # --- mode / mode list ---
    if name == "mode_list":
        active_name = character
        entries = _mode_mgr.list_modes(public_only=True) if _mode_mgr is not None else []
        lines = ["Character modes (* active)"]
        for entry in entries:
            marker = "*" if entry["name"] == active_name else " "
            lines.append(f"{marker} {entry['display_name']}")
        return "\n".join(lines)

    # Unreachable — all verb names handled above
    return pick(character, "unknown_verb")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _FarewellExit(SystemExit):
    """SystemExit subclass carrying the farewell phrase.

    dispatch_repl_verb raises this for quit/exit/q so the caller can
    emit the farewell string to scrollback before the process exits.

    Parameters
    ----------
    phrase:
        Character-voiced farewell string to display before exit.
    """

    def __init__(self, phrase: str) -> None:
        self.phrase = phrase
        super().__init__(0)


def _ioc_to_stix_type(ioc_type: str | None) -> str:
    """Map detect_ioc_type() result to a STIX SCO type string.

    Parameters
    ----------
    ioc_type:
        Result from detect_ioc_type(), or None.

    Returns
    -------
    str
        STIX type string.
    """
    _MAP = {
        "ipv4": "ipv4-addr",
        "ipv6": "ipv6-addr",
        "domain": "domain-name",
        "url": "url",
        "email": "email-addr",
        "sha256": "file",
        "sha1": "file",
        "md5": "file",
    }
    return _MAP.get(ioc_type or "", "unrecognized-type")
