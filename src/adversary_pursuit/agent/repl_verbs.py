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

from dataclasses import dataclass
from typing import Callable

from adversary_pursuit.core.ioc_types import detect_ioc_type
from adversary_pursuit.gamification.modes import (
    DEFAULT_MODES,
    LEGACY_MODE_ALIASES,
    RETIRED_MODES,
)
from adversary_pursuit.gamification.phrases import pick

# ---------------------------------------------------------------------------
# Verb registry
# ---------------------------------------------------------------------------

# Zero-argument verbs
_NO_ARG_VERBS: frozenset[str] = frozenset({"help", "?", "status", "clear", "quit", "exit", "q"})

# One-argument verbs
_ONE_ARG_VERBS: frozenset[str] = frozenset({"mode", "use"})

_ALL_VERBS: frozenset[str] = _NO_ARG_VERBS | _ONE_ARG_VERBS

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

    if len(tokens) > 2:  # noqa: PLR2004
        # Multiple tokens after the verb — route to LLM.
        # "use foo com bar" is probably a natural-language query.
        return None

    arg = tokens[1]

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

    # --- quit / exit / q ---
    if name in ("quit", "exit", "q"):
        farewell = pick(character, "farewell")
        # Print farewell before raising so the caller can emit it first
        raise _FarewellExit(farewell)

    # --- use <target> ---
    if name == "use":
        target = verb.args[0]
        # Record the pivot in workspace_mgr (best-effort — don't crash if unavailable)
        if _workspace_mgr is not None:
            try:
                _workspace_mgr.record_pivot(target)
                _workspace_mgr.switch(target)
            except Exception:  # noqa: BLE001
                # Workspace may not exist; try to create it first
                try:
                    _workspace_mgr.create(target)
                    _workspace_mgr.switch(target)
                except Exception:  # noqa: BLE001
                    pass
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
                return f"Mode switched: {new_mode.name}\n{new_mode.greeting}"
            except ValueError as exc:
                return str(exc)
        available = ", ".join(sorted(_KNOWN_MODES))
        return f"Unknown mode: {mode_name}\nAvailable modes: {available}"

    # --- mode / mode list ---
    if name == "mode_list":
        active_name = character
        entries = _mode_mgr.list_modes() if _mode_mgr is not None else []
        lines = ["Character modes (* active)"]
        for entry in entries:
            marker = "*" if entry["name"] == active_name else " "
            lines.append(f"{marker} {entry['name']}")
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
