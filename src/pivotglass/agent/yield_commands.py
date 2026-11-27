"""Yield command parser and dispatcher for the TUI.

Yield commands let the analyst interrupt or steer a running battery mid-flight
by typing short imperative verbs into the input field. The parser is verb-first:
input is only interpreted as a yield command when it matches the grammar exactly.
Unknown or ambiguous input is routed to the LLM instead.

@decision DEC-YIELD-COMMANDS-001
@title verb-first parser; unknown verb routes to LLM
@status accepted
@rationale Yield commands occupy a reserved prefix namespace ("stop", "focus",
           "add", "skip"). The parser returns None for any input that does not
           exactly match the grammar so callers can route non-matching input to
           the LLM without ambiguity. This keeps the yield surface minimal and
           predictable: analysts who know the verbs get deterministic steering;
           analysts who type natural language get LLM interpretation.

           Grammar:
             stop              → YieldCommand("stop", None)
             focus <arg>       → YieldCommand("focus", arg)
             add <arg>         → YieldCommand("add", arg)
             skip <arg>        → YieldCommand("skip", arg)

           "stop" alone is a yield; "stop that guy" is NOT (routes to LLM).
           "focus" alone (no arg) is NOT a yield (routes to LLM).
           Argument is a single whitespace-delimited token; multi-token
           arguments are NOT supported (the second token onward is ignored
           and the parse returns None for safety).

@decision DEC-YIELD-ROUTING-001
@title A bare steering verb targets the battery run, else the active pivot run, else says nothing is active
@status accepted
@rationale The cyberdeck has two steerable things: the foreground battery run
           (bare ``stop|focus|add|skip``) and the workspace's pivot run (``pivot
           stop|focus|add|skip``, DEC-PIVOT-RUN-001). Requiring the ``pivot``
           prefix for one and not the other made the bare verbs silently do
           nothing whenever only a pivot run (an analyst's, or autopivot's) was
           active. Rule: ``pivot <verb>`` always targets the pivot run; a bare
           verb targets the battery run when one is active, otherwise the active
           pivot run; with neither, the reply says so rather than acknowledging a
           no-op. Batteries keep priority because they are the foreground work the
           analyst just started with ``use``. ``route_yield`` is the only place
           that applies the rule.

Character voice text for battery yields is sourced from phrases.py via pick()
(DEC-PHRASE-CACHE-001); pivot-run replies are the pivot grammar's own plain text.
"""

from __future__ import annotations

from dataclasses import dataclass

from pivotglass.gamification.phrases import pick

# ---------------------------------------------------------------------------
# Yield verb registry
# ---------------------------------------------------------------------------

# Verbs that take no argument
_NO_ARG_VERBS: frozenset[str] = frozenset({"stop"})

# Verbs that require exactly one argument token
_ONE_ARG_VERBS: frozenset[str] = frozenset({"focus", "add", "skip"})

_ALL_VERBS: frozenset[str] = _NO_ARG_VERBS | _ONE_ARG_VERBS


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class YieldCommand:
    """A parsed yield command.

    Parameters
    ----------
    primitive:
        One of "stop", "focus", "add", "skip".
    argument:
        The single argument token for focus/add/skip; None for stop.
    """

    primitive: str  # "stop", "focus", "add", "skip"
    argument: str | None  # for focus/add/skip; None for stop


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_yield(text: str) -> YieldCommand | None:
    """Parse *text* as a yield command.

    Returns a YieldCommand when *text* matches the yield grammar exactly.
    Returns None when *text* should be routed to the LLM.

    Grammar (DEC-YIELD-COMMANDS-001):
    - "stop"         → YieldCommand("stop", None)
    - "focus <tok>"  → YieldCommand("focus", tok)
    - "add <tok>"    → YieldCommand("add", tok)
    - "skip <tok>"   → YieldCommand("skip", tok)

    Rejection cases (returns None):
    - "stop that guy"      — "stop" with trailing tokens
    - "focus"              — one-arg verb with no argument
    - "focus a b"          — one-arg verb with more than one argument token
    - any unrecognised verb

    Parameters
    ----------
    text:
        Raw input string from the TUI input field, already stripped.

    Returns
    -------
    YieldCommand | None
    """
    stripped = text.strip()
    if not stripped:
        return None

    tokens = stripped.split()
    verb = tokens[0].lower()

    if verb not in _ALL_VERBS:
        return None

    if verb in _NO_ARG_VERBS:
        # "stop" must appear alone — any trailing tokens route to LLM
        if len(tokens) == 1:
            return YieldCommand(primitive=verb, argument=None)
        return None

    # One-arg verbs: require exactly one argument token
    if verb in _ONE_ARG_VERBS:
        if len(tokens) == 2:  # noqa: PLR2004
            return YieldCommand(primitive=verb, argument=tokens[1])
        return None

    return None  # unreachable; defensive


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def dispatch_yield(
    cmd: YieldCommand,
    battery_run,  # BatteryRun | None  (avoid circular import; typed at runtime)
    bus,  # EventBus
    character: str = "default",
) -> str:
    """Execute a yield command and return a character-voiced feedback string.

    Publishes a YieldReceived event on *bus* and, when a *battery_run* is
    active, calls battery_run.apply_yield(cmd) to mutate the pending tool
    queue.

    All voice strings come from phrases.py via pick() so the character voice
    is consistent with the rest of the session (DEC-PHRASE-CACHE-001).
    The phrase category ``"yield:<primitive>"`` is used; when no phrase exists
    for the character, the default fallback ladder in pick() applies.

    Parameters
    ----------
    cmd:
        The parsed YieldCommand to execute.
    battery_run:
        The currently active BatteryRun, or None when no battery is running.
        When None, "stop"/"focus"/"skip" are no-ops; "add" is also a no-op.
    bus:
        The session EventBus. A YieldReceived event is always published.
    character:
        Active character name for pick() voice selection.

    Returns
    -------
    str
        A character-voiced one-liner confirming the action.
    """
    from pivotglass.agent.tui.events import YieldReceived

    # Publish the event unconditionally so the live pane can update
    bus.publish(YieldReceived(primitive=cmd.primitive, argument=cmd.argument))

    # Apply the command to the active battery run (if any)
    if battery_run is not None:
        battery_run.apply_yield(cmd)

    # Return character-voiced feedback
    # Category format: "yield:<primitive>" — pick() raises ValueError for
    # unknown categories, but "yield:" is an activity-prefix pattern and
    # will degrade gracefully via the fallback ladder.
    try:
        return pick(character, f"yield:{cmd.primitive}")
    except ValueError:
        # Unknown category: return a safe generic acknowledgement
        return f"[{cmd.primitive}]"


NOTHING_TO_STEER = (
    "Nothing to steer: no battery or pivot run is active. "
    "Bare stop/focus/add/skip steer a running battery, otherwise the active pivot run."
)


def active_pivot_run(ctx):  # ToolContext | None -> PivotRun | None
    """The workspace's unfinished pivot run, or None."""

    registry = getattr(ctx, "pivot_runs", None)
    if registry is None:
        return None
    try:
        workspace = str(ctx.workspace_mgr.active)
    except RuntimeError:
        workspace = "default"
    return registry.active(workspace)


def route_yield(cmd: YieldCommand, *, battery_run, ctx, bus, character: str = "default") -> str:
    """Send a bare steering verb to its target (DEC-YIELD-ROUTING-001).

    The battery run when one is active (``dispatch_yield``); otherwise the active
    pivot run, through the shared ``pivot`` grammar; otherwise a reply saying
    nothing is active.
    """

    if battery_run is not None:
        return dispatch_yield(cmd, battery_run, bus, character)
    if active_pivot_run(ctx) is None:
        return NOTHING_TO_STEER
    from pivotglass.modules.pivoting.commands import execute_pivot_command

    words = [cmd.primitive] + ([cmd.argument] if cmd.argument else [])
    try:
        return str(execute_pivot_command(words, ctx)["text"])
    except ValueError as exc:
        return str(exc)
