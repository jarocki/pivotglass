"""The ``pivot`` command, shared by the web cockpit, the cyberdeck and the classic REPL (#22).

Grammar::

    pivot <indicator> [<indicator> ...] [depth:N] [budget:N]
                                  start a bounded multi-hop pivot run
    pivot [status]                show the active (or latest) run
    pivot stop                    halt after the current request
    pivot skip <indicator>        drop it and everything it would have led to
    pivot focus <indicator>       expand only that indicator's subtree
    pivot unfocus                 put every queued indicator back in scope
    pivot add <indicator>         add a new seed at depth 0

``depth`` is 1 to 3 (default 1: the seeds and one pivot from them); ``budget`` is
the maximum number of module requests, 1 to 200 (default 20). One run may be
active per workspace. The run itself is ``modules/pivoting/run.py``
(DEC-PIVOT-RUN-001); surfaces differ only in where it executes: the cockpit and
the cyberdeck run it on a background thread and stream its events, the REPL
runs it in the foreground and Ctrl-C stops it after the current request.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from typing import Any

from pivotglass.core.pivot_policy import ANALYST_SEED_REASON
from pivotglass.modules.pivoting.run import (
    DEFAULT_BUDGET,
    DEFAULT_DEPTH,
    MAX_BUDGET,
    MAX_DEPTH,
    Listener,
    PivotRun,
    bounded,
    indicator_type,
)

PIVOT_USAGE = (
    "Usage: pivot <indicator> [<indicator> ...] [depth:1-3] [budget:1-200] | pivot status | "
    "pivot stop | pivot skip <indicator> | pivot focus <indicator> | pivot unfocus | "
    "pivot add <indicator>"
)
CONTROL_ACTIONS = ("status", "stop", "skip", "focus", "unfocus", "add")
COMPLETION_CHOICES = ("status", "stop", "skip ", "focus ", "unfocus", "add ", "depth:", "budget:")


@dataclass(frozen=True)
class PivotCommand:
    action: str  # "start" or one of CONTROL_ACTIONS
    indicators: tuple[str, ...] = ()
    depth: int = DEFAULT_DEPTH
    budget: int = DEFAULT_BUDGET


def _number(word: str, name: str, high: int) -> int:
    raw = word.split(":", 1)[1]
    if not raw.isdigit():
        raise ValueError(f"{name} must be a whole number: {word!r}. {PIVOT_USAGE}")
    return bounded(int(raw), name=name, low=1, high=high)


def parse_pivot_command(text: str | tuple[str, ...] | list[str]) -> PivotCommand:
    """Parse the words after ``pivot``. Raises ValueError with usage on bad input."""

    words = (text.split() if isinstance(text, str) else [str(word) for word in text])
    if not words:
        return PivotCommand("status")
    action = words[0].casefold()
    if action in {"status", "stop", "unfocus"}:
        if len(words) != 1:
            raise ValueError(PIVOT_USAGE)
        return PivotCommand(action)
    if action in {"skip", "focus", "add"}:
        if len(words) != 2:  # noqa: PLR2004
            raise ValueError(PIVOT_USAGE)
        if action == "add":
            indicator_type(words[1])
        return PivotCommand(action, (words[1],))
    depth, budget = DEFAULT_DEPTH, DEFAULT_BUDGET
    indicators: list[str] = []
    for word in words:
        lower = word.casefold()
        if lower.startswith("depth:"):
            depth = _number(word, "depth", MAX_DEPTH)
        elif lower.startswith("budget:"):
            budget = _number(word, "budget", MAX_BUDGET)
        else:
            indicator_type(word)
            indicators.append(word)
    if not indicators:
        raise ValueError(PIVOT_USAGE)
    return PivotCommand("start", tuple(dict.fromkeys(indicators)), depth, budget)


# ---------------------------------------------------------------------------
# Rendering (plain text; every surface prints the same words)
# ---------------------------------------------------------------------------


def summary_line(snapshot: dict[str, Any]) -> str:
    if snapshot.get("plan_only"):
        return (
            f"Pivot plan {snapshot['run_id']} · nothing executed · "
            f"{snapshot['requests_planned']}/{snapshot['budget']} requests would run"
        )
    return (
        f"Pivot run {snapshot['run_id']} · {snapshot['state']} · depth {snapshot['depth_reached']}"
        f"/{snapshot['depth_limit']} · requests {snapshot['requests_used']}/{snapshot['budget']}"
        f" · {len(snapshot['frontier'])} queued"
    )


def render_snapshot(snapshot: dict[str, Any], *, limit: int = 25) -> str:
    seeds = f"Seeds: {', '.join(snapshot['seeds'])}"
    if snapshot.get("origin"):
        seeds += f" (returned for {snapshot['origin']})"
    elif any(item["reason"] == ANALYST_SEED_REASON for item in snapshot["decisions"]):
        seeds += f" ({ANALYST_SEED_REASON})"
    lines = [summary_line(snapshot), seeds]
    current = snapshot.get("current")
    if current:
        lines.append(f"Now: {current['value']} (depth {current['depth']})"
                     + (f" via {current['module']}" if current.get("module") else ""))
    if snapshot["focus"]:
        lines.append(f"Focus: {', '.join(snapshot['focus'])}")
    if snapshot["skip"]:
        lines.append(f"Skip: {', '.join(snapshot['skip'])}")
    if snapshot["requests"]:
        lines.append("Requests:")
        for item in snapshot["requests"][-limit:]:
            if item["status"] == "failed":
                outcome = f"failed — {item['reason']}"
            elif item["status"] == "planned":
                outcome = "would be requested"
            else:
                outcome = f"{item['result_count']} results, {len(item['queued'])} queued"
                if item.get("not_expanded"):
                    outcome += f", {item['not_expanded']} not expanded"
            lines.append(f"  {item['request']:>3}. [d{item['depth']}] {item['value']} → {item['module']}: {outcome}")
    rejected = [item for item in snapshot["decisions"] if item["verdict"] != "allow"]
    if rejected:
        lines.append("Not requested:")
        for item in rejected[-limit:]:
            lines.append(f"  [d{item['depth']}] {item['value']} × {item['module']}: {item['gate']} — {item['reason']}")
    if snapshot["skipped"]:
        lines.append("Not expanded by decision:")
        for item in snapshot["skipped"][-limit:]:
            lines.append(f"  [d{item['depth']}] {item['value']}: {item['reason']}")
    if snapshot["frontier"]:
        queued = ", ".join(f"{item['value']} (d{item['depth']})" for item in snapshot["frontier"][:limit])
        more = len(snapshot["frontier"]) - limit
        lines.append(f"Queued: {queued}" + (f" … and {more} more" if more > 0 else ""))
    if snapshot["not_expanded"]:
        reasons: dict[str, int] = {}
        for item in snapshot["not_expanded"]:
            reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
        lines.append("Discovered, not expanded: " + "; ".join(f"{count} {reason}" for reason, count in reasons.items()))
    lines.append(snapshot["truth_boundary"])
    return "\n".join(lines)


def format_event(event: dict[str, Any]) -> str | None:
    """One progress line for a run event, or None for events not worth a line."""

    kind = event["kind"]
    if kind == "run_started":
        if event.get("plan_only"):
            return f"◇ Pivot plan {event['run_id']}: {', '.join(event['seeds'])} · nothing will be executed."
        label = f"Autopivot run {event['run_id']} (from {event['origin']})" if event.get("origin") else (
            f"Pivot run {event['run_id']}")
        return (f"◇ {label} started: {', '.join(event['seeds'])} · depth limit "
                f"{event['depth_limit']} · budget {event['budget']} requests. `pivot stop` halts it.")
    if kind == "request_started":
        return f"  → [{event['request']}/{event['budget']}] d{event['depth']} {event['value']} · {event['module']}"
    if kind == "request_finished":
        line = f"    {event['result_count']} results, {len(event['queued'])} queued"
        return line + (f", {event['not_expanded']} not expanded" if event.get("not_expanded") else "")
    if kind == "request_planned":
        return f"  ○ [{event['request']}/{event['budget']}] d{event['depth']} {event['value']} · {event['module']}"
    if kind == "request_failed":
        return f"    failed: {event['reason']}"
    if kind == "request_skipped" and event["gate"] not in {"readiness"}:
        return f"  × d{event['depth']} {event['value']} · {event['module']}: {event['reason']}"
    if kind == "indicator_skipped":
        return f"  × d{event['depth']} {event['value']}: {event['reason']}"
    if kind == "control":
        return f"◇ Analyst: pivot {event['action']} {event['detail']}".rstrip()
    if kind == "run_finished":
        return "◇ " + summary_line(event["snapshot"])
    return None


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def _workspace(ctx: Any) -> str:
    try:
        return str(ctx.workspace_mgr.active)
    except RuntimeError:
        return "default"


def _result(action: str, run: PivotRun | None, text: str) -> dict[str, Any]:
    return {
        "action": action,
        "title": "Pivot run",
        "text": text,
        "data": run.snapshot() if run is not None else None,
        "run": run,
    }


def execute_pivot_command(
    text: str | tuple[str, ...] | list[str],
    ctx: Any,
    *,
    listener: Listener | None = None,
    background: bool = True,
    guard: AbstractContextManager[Any] | None = None,
    on_start: Callable[[PivotRun], None] | None = None,
) -> dict[str, Any]:
    """Run one ``pivot`` command (without the leading word) against a ToolContext.

    ``background`` starts a run on a daemon thread and returns at once;
    otherwise the call blocks until the run finishes, and Ctrl-C (KeyboardInterrupt)
    stops it after the current request. ``guard`` is held while the run executes
    (the cockpit passes its investigation lock). ``on_start`` sees the registered
    run before it executes, so a surface can attach its own feed.
    """

    command = parse_pivot_command(text)
    registry = ctx.pivot_runs
    workspace = _workspace(ctx)
    if command.action != "start":
        run = registry.latest(workspace)
        if command.action == "status":
            if run is None:
                return _result("status", None, "No pivot run in this workspace yet. " + PIVOT_USAGE)
            return _result("status", run, render_snapshot(run.snapshot()))
        if run is None or run.finished:
            raise ValueError("No active pivot run in this workspace. Start one with `pivot <indicator>`.")
        if command.action == "stop":
            message = run.stop()
        elif command.action == "unfocus":
            message = run.unfocus()
        else:
            message = getattr(run, command.action)(command.indicators[0])
        return _result(command.action, run, f"{message}\n{summary_line(run.snapshot())}")

    from pivotglass.modules.pivoting.context import build_context_run

    run = build_context_run(ctx, list(command.indicators), depth=command.depth,
                            budget=command.budget, listener=listener)
    registry.register(run)
    if on_start is not None:
        on_start(run)

    def execute() -> None:
        with guard if guard is not None else nullcontext():
            run.run()

    thread = threading.Thread(target=execute, name=f"pivotglass-pivot-{run.run_id}", daemon=True)
    thread.start()
    if background:
        return _result("start", run, f"Pivot run {run.run_id} started. `pivot status` shows progress; "
                       "`pivot stop` halts it after the current request.")
    try:
        while thread.is_alive():
            thread.join(0.2)
    except KeyboardInterrupt:
        run.stop()
        # The current request finishes and its evidence is stored; a second Ctrl-C stops waiting.
        while thread.is_alive():
            thread.join(0.2)
    return _result("start", run, render_snapshot(run.snapshot()))
