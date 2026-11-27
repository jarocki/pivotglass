"""Bounded multi-hop pivot runs: the one authority every surface uses (#22).

A pivot run starts from one or more analyst-chosen indicators, queries the
modules subscribed to each indicator's STIX type, and expands what those
modules return, breadth first, until the analyst's depth limit or request
budget is reached, the frontier is empty, or the analyst stops it.

@decision DEC-PIVOT-RUN-001
@title PivotRun is the single multi-hop pivot authority for the cockpit, the REPL and the cyberdeck
@status accepted
@rationale Before #22 multi-hop pivoting existed only as the event bus's opt-in
           cascade beneath the agent's tools: unbounded in depth, invisible while
           it ran, and impossible to steer. PivotRun owns the whole loop instead,
           and every surface drives it through one grammar
           (``modules/pivoting/commands.py``).

           Gates. Every (indicator, module) pair passes, in order: readiness (the
           module is installed, enabled and has its credential; no request is
           spent on a module that cannot run), then ``PivotPolicy.evaluate``, the
           sole pivot gate authority (DEC-60-PIVOT-POLICY-001: value, confidence,
           budget). The run constructs its own PivotPolicy from the configured
           ``auto_pivot_policy`` with both budget ceilings set to the run's
           budget, so the policy's budget gate *is* the run's budget and no second
           counter decides anything. The run never resets the cascade counter.

           Budget. One request is one module call. The policy charges the budget
           when it allows a pair, immediately before the call, so a failed call
           still counts: it reached the service. Readiness skips and policy
           rejections cost nothing. The first budget rejection ends the run and
           records every unexpanded indicator as over budget.

           Depth. Seeds are depth 0. An indicator at depth d is expanded only when
           d <= depth limit; its outputs become depth d + 1. Outputs beyond the
           limit, or of a type no module subscribes to, are recorded as
           discovered but not expanded. Depth defaults to 1, meaning the seeds
           and one pivot from them: that already multiplies requests by the
           seed's fan-out, every further level multiplies again, and the analyst
           should see the first ring of results before choosing to spend more.
           The hard maximum is 3 and the hard budget ceiling 200.

           Source of modules. ``DEFAULT_SUBSCRIPTIONS`` (module -> STIX types) is
           the one map of which module answers which indicator type for
           automated pivots; it is keyed by module path, which is what the
           evidence path (``ToolContext.run_module``) executes, so a module added
           to it joins pivot runs with no change here. The cockpit's one-hop
           battery planner is a separate, tool-name catalogue for a single
           indicator and is deliberately not reused.

           Evidence. Modules run through the caller's executor; on every surface
           that is ``ToolContext.run_module(..., cascade=False)``, so evidence and
           provenance are stored exactly as for a one-hop enrichment and the
           event bus cannot cascade underneath the run. The parent-child lineage
           a run records is collection workflow ("this module, asked about X,
           returned Y"), not a claim that X and Y share an operator.

           Controls arrive from other threads. All state is guarded by one lock;
           module calls happen outside it. ``stop`` takes effect after the
           current request; ``skip`` drops an indicator and its unexpanded
           descendants (and the rest of its modules if it is being expanded);
           ``focus`` expands only the focused indicators' subtrees, deferring the
           rest; ``add`` enqueues a new seed at depth 0.
"""

from __future__ import annotations

import itertools
import threading
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pivotglass.core.config import AutoPivotPolicyConfig
from pivotglass.core.event_bus import DEFAULT_SUBSCRIPTIONS
from pivotglass.core.ioc_types import detect_ioc_type, normalize_cve
from pivotglass.core.pivot_policy import PivotPolicy

DEFAULT_DEPTH = 1
MAX_DEPTH = 3
DEFAULT_BUDGET = 20
MAX_BUDGET = 200

ANALYST_SOURCE = "analyst"

STIX_TYPE_BY_IOC: dict[str, str] = {
    "ipv4": "ipv4-addr",
    "ipv6": "ipv6-addr",
    "domain": "domain-name",
    "url": "url",
    "email": "email-addr",
    "md5": "file",
    "sha1": "file",
    "sha256": "file",
    "cve": "vulnerability",
}

TRUTH_BOUNDARY = (
    "A pivot run records which modules were asked about which indicators. Returned "
    "indicators are stored as module evidence with provenance; the parent-child "
    "lineage is collection workflow, not an observed relationship between them."
)

# Run states. ``queued`` until the executing thread starts it.
QUEUED, RUNNING, STOPPING = "queued", "running", "stopping"
COMPLETED, STOPPED, BUDGET_EXHAUSTED, FAILED = "completed", "stopped", "budget_exhausted", "failed"
TERMINAL = frozenset({COMPLETED, STOPPED, BUDGET_EXHAUSTED, FAILED})


@dataclass(frozen=True)
class ModuleOutcome:
    """What one module call returned: raw results and the workspace objects it created."""

    results: list[dict]
    artifact_ids: tuple[str, ...] = ()


Executor = Callable[[str, str], ModuleOutcome]
Readiness = Callable[[str], str | None]
Listener = Callable[[dict[str, Any]], None]


@dataclass
class PivotNode:
    """One indicator in the run's frontier or history."""

    key: str
    value: str
    stix_type: str
    depth: int
    parent: str | None
    source_module: str
    sco_id: str = ""
    attrs: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "type": self.stix_type,
            "depth": self.depth,
            "parent": self.parent,
            "source_module": self.source_module,
        }


def _now() -> str:
    return datetime.now(UTC).isoformat()


def indicator_type(value: str) -> str:
    """Return the STIX type of an analyst-entered indicator or raise ValueError."""

    detected = detect_ioc_type(value.strip())
    stix_type = STIX_TYPE_BY_IOC.get(detected or "")
    if stix_type is None:
        raise ValueError(f"{value!r} is not a recognized indicator")
    return stix_type


def _identity(stix_type: str, value: str) -> tuple[str, str]:
    return stix_type, value.strip().casefold()


def _result_value(result: Mapping[str, Any]) -> str:
    # A vulnerability SDO is named by its CVE; it has no "value" (same rule as the event bus).
    if result.get("type") == "vulnerability":
        return normalize_cve(str(result.get("name") or result.get("value") or ""))
    return str(result.get("value") or "")


def bounded(value: int, *, name: str, low: int, high: int) -> int:
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}, not {value}")
    return value


class PivotRun:
    """A bounded, breadth-first, analyst-steerable multi-hop pivot (DEC-PIVOT-RUN-001)."""

    def __init__(
        self,
        seeds: Sequence[str],
        *,
        executor: Executor,
        subscriptions: Mapping[str, Iterable[str]] | None = None,
        policy_config: AutoPivotPolicyConfig | None = None,
        depth: int = DEFAULT_DEPTH,
        budget: int = DEFAULT_BUDGET,
        readiness: Readiness | None = None,
        listener: Listener | None = None,
        on_expand: Callable[[PivotNode, PivotNode | None], None] | None = None,
        describe_failure: Callable[[Exception, str], str] | None = None,
        workspace: str = "",
    ) -> None:
        if not seeds:
            raise ValueError("a pivot run needs at least one indicator")
        self.run_id = uuid.uuid4().hex[:12]
        self.workspace = workspace
        self.depth_limit = bounded(depth, name="depth", low=1, high=MAX_DEPTH)
        self.budget = bounded(budget, name="budget", low=1, high=MAX_BUDGET)
        self._executor = executor
        self._subscriptions = {
            module: tuple(types)
            for module, types in (DEFAULT_SUBSCRIPTIONS if subscriptions is None else subscriptions).items()
        }
        config = policy_config or AutoPivotPolicyConfig()
        # The policy's budget gate is the run's request budget (see DEC-PIVOT-RUN-001).
        self._policy = PivotPolicy(
            config.model_copy(update={"max_per_cascade": self.budget, "max_per_session": self.budget})
        )
        self._readiness = readiness
        self._listeners: list[Listener] = [listener] if listener else []
        self._on_expand = on_expand
        self._describe_failure = describe_failure or (lambda exc, _module: type(exc).__name__)

        self._lock = threading.RLock()
        self._sequence = itertools.count(1)
        self._nodes: dict[str, PivotNode] = {}
        self._seen: set[tuple[str, str]] = set()
        self._frontier: list[PivotNode] = []
        self._expanded: list[dict[str, Any]] = []
        self._discovered: list[dict[str, Any]] = []
        self._skipped: list[dict[str, Any]] = []
        self._decisions: list[dict[str, Any]] = []
        self._requests: list[dict[str, Any]] = []
        self._controls: list[dict[str, Any]] = []
        self._skip_values: set[str] = set()
        self._focus_keys: set[str] = set()
        self._current: dict[str, Any] | None = None
        self._stop_requested = False
        self._state = QUEUED
        self._started_at: str | None = None
        self._finished_at: str | None = None
        self._depth_reached = 0
        self._budget_reason = "over budget"
        self.seeds: list[str] = []
        for seed in seeds:
            self._add_seed_locked(seed)

    # ------------------------------------------------------------------
    # Listeners
    # ------------------------------------------------------------------

    def add_listener(self, listener: Listener) -> None:
        with self._lock:
            self._listeners.append(listener)

    def _emit(self, kind: str, **payload: Any) -> None:
        event = {"kind": kind, "run_id": self.run_id, "at": _now(), **payload}
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:  # noqa: BLE001 - a broken display must never stop collection
                pass

    # ------------------------------------------------------------------
    # Frontier
    # ------------------------------------------------------------------

    def _new_node(
        self, value: str, stix_type: str, depth: int, parent: str | None, source: str,
        sco_id: str = "", attrs: dict[str, Any] | None = None,
    ) -> PivotNode:
        node = PivotNode(
            key=f"n{next(self._sequence)}", value=value, stix_type=stix_type, depth=depth,
            parent=parent, source_module=source, sco_id=sco_id, attrs=dict(attrs or {}),
        )
        self._nodes[node.key] = node
        self._seen.add(_identity(stix_type, value))
        return node

    def _add_seed_locked(self, raw: str) -> PivotNode:
        value = raw.strip()
        stix_type = indicator_type(value)
        if stix_type == "vulnerability":
            value = normalize_cve(value)
        if _identity(stix_type, value) in self._seen:
            raise ValueError(f"{value} is already in this pivot run")
        node = self._new_node(value, stix_type, 0, None, ANALYST_SOURCE)
        self._frontier.append(node)
        self.seeds.append(value)
        return node

    def _ancestry(self, node: PivotNode) -> list[PivotNode]:
        chain = [node]
        while chain[-1].parent is not None:
            chain.append(self._nodes[chain[-1].parent])
        return chain

    def _skipped_by_analyst(self, node: PivotNode) -> PivotNode | None:
        for ancestor in self._ancestry(node):
            if ancestor.value.casefold() in self._skip_values:
                return ancestor
        return None

    def _in_focus(self, node: PivotNode) -> bool:
        return not self._focus_keys or any(item.key in self._focus_keys for item in self._ancestry(node))

    def _record_skip(self, node: PivotNode, reason: str, gate: str) -> None:
        entry = {**node.describe(), "reason": reason, "gate": gate}
        self._skipped.append(entry)
        self._emit("indicator_skipped", **entry)

    def _next_node_locked(self) -> PivotNode | None:
        self._frontier.sort(key=lambda item: (item.depth, int(item.key[1:])))
        for node in list(self._frontier):
            skipped_via = self._skipped_by_analyst(node)
            if skipped_via is not None:
                self._frontier.remove(node)
                reason = (
                    "skipped by analyst" if skipped_via is node
                    else f"skipped by analyst (descendant of {skipped_via.value})"
                )
                self._record_skip(node, reason, "analyst_skip")
                continue
            if not self._in_focus(node):
                continue  # deferred: may come back into scope on unfocus
            self._frontier.remove(node)
            return node
        return None

    def _drain_frontier_locked(self, reason: str, gate: str) -> None:
        for node in sorted(self._frontier, key=lambda item: (item.depth, int(item.key[1:]))):
            self._record_skip(node, reason, gate)
        self._frontier.clear()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """Execute until finished; return the final snapshot. Call once, from one thread."""

        with self._lock:
            if self._state != QUEUED:
                raise RuntimeError("a pivot run executes once")
            self._state = STOPPING if self._stop_requested else RUNNING
            self._started_at = _now()
        self._emit("run_started", depth_limit=self.depth_limit, budget=self.budget, seeds=list(self.seeds))
        final = COMPLETED
        try:
            while True:
                with self._lock:
                    if self._stop_requested:
                        self._drain_frontier_locked("stopped by analyst", "analyst_stop")
                        final = STOPPED
                        break
                    node = self._next_node_locked()
                    if node is None:
                        if self._frontier:
                            self._drain_frontier_locked("outside the analyst's focus", "focus")
                        break
                    self._current = {**node.describe(), "module": None}
                if not self._expand(node):
                    with self._lock:
                        self._drain_frontier_locked(self._budget_reason, "budget")
                    final = BUDGET_EXHAUSTED
                    break
        except Exception as exc:  # noqa: BLE001 - recorded, then surfaced in the final state
            final = FAILED
            with self._lock:
                self._controls.append({"action": "error", "detail": type(exc).__name__, "at": _now()})
        with self._lock:
            self._state = final
            self._current = None
            self._finished_at = _now()
            snapshot = self._snapshot_locked()
        self._emit("run_finished", state=final, snapshot=snapshot)
        return snapshot

    def _expand(self, node: PivotNode) -> bool:
        """Query every subscribed module for *node*. Return False once the budget is spent."""

        modules = [module for module, types in self._subscriptions.items() if node.stix_type in types]
        with self._lock:
            self._depth_reached = max(self._depth_reached, node.depth)
            self._expanded.append({**node.describe(), "modules": modules})
        if self._on_expand is not None:
            parent = self._nodes.get(node.parent) if node.parent else None
            try:
                self._on_expand(node, parent)
            except Exception:  # noqa: BLE001 - workflow navigation never blocks collection
                pass
        self._emit("indicator_started", **node.describe(), modules=modules)
        requested = False
        for module in modules:
            with self._lock:
                if self._stop_requested:
                    return True  # the loop drains and stops
                skipped_via = self._skipped_by_analyst(node)
                if skipped_via is not None:
                    self._decide(node, module, "skip", "analyst_skip", "skipped by analyst")
                    continue
                self._current = {**node.describe(), "module": module}
            not_ready = self._readiness(module) if self._readiness else None
            if not_ready:
                with self._lock:
                    self._decide(node, module, "skip", "readiness", not_ready)
                continue
            with self._lock:
                decision = self._policy.evaluate(
                    sco_type=node.stix_type, value=node.value, source_module=node.source_module,
                    candidate_module=module, sco_attrs=node.attrs, depth=node.depth, sco_id=node.sco_id,
                )
                self._decide(node, module, decision.verdict, decision.gate, decision.reason)
                if decision.verdict != "allow":
                    if decision.gate == "budget":
                        self._budget_reason = f"over budget ({decision.reason})"
                        if not requested:
                            self._record_skip(node, self._budget_reason, "budget")
                        return False
                    continue
                number = self._policy.session_count
                requested = True
            self._emit("request_started", **node.describe(), module=module, request=number, budget=self.budget)
            try:
                outcome = self._executor(module, node.value)
            except Exception as exc:  # noqa: BLE001 - one failing source never ends the run
                reason = self._describe_failure(exc, module)
                with self._lock:
                    entry = {**node.describe(), "module": module, "request": number, "status": "failed",
                             "reason": reason, "result_count": 0, "queued": [], "artifact_ids": []}
                    self._requests.append(entry)
                self._emit("request_failed", **entry)
                continue
            with self._lock:
                queued, beyond = self._children_locked(node, module, outcome.results)
                entry = {
                    **node.describe(), "module": module, "request": number,
                    "status": "ok" if outcome.results else "empty",
                    "result_count": len(outcome.results), "queued": [child.value for child in queued],
                    "not_expanded": beyond, "artifact_ids": list(outcome.artifact_ids),
                }
                self._requests.append(entry)
            self._emit("request_finished", **entry)
        return True

    def _decide(self, node: PivotNode, module: str, verdict: str, gate: str, reason: str) -> None:
        entry = {"key": node.key, "value": node.value, "depth": node.depth, "module": module,
                 "verdict": verdict, "gate": gate, "reason": reason}
        self._decisions.append(entry)
        if verdict != "allow":
            self._emit("request_skipped", **entry)

    def _children_locked(self, node: PivotNode, module: str, results: list[dict]) -> tuple[list[PivotNode], int]:
        subscribed = {stix_type for types in self._subscriptions.values() for stix_type in types}
        queued: list[PivotNode] = []
        beyond = 0
        for result in results:
            stix_type = str(result.get("type") or "")
            value = _result_value(result)
            if not stix_type or not value or _identity(stix_type, value) in self._seen:
                continue
            attrs = {k: v for k, v in result.items() if k not in ("type", "value", "id")}
            child = self._new_node(value, stix_type, node.depth + 1, node.key, module,
                                   sco_id=str(result.get("id") or ""), attrs=attrs)
            if child.depth > self.depth_limit:
                reason = f"beyond depth limit {self.depth_limit}"
            elif stix_type not in subscribed:
                reason = f"no module pivots on {stix_type}"
            else:
                reason = ""
            if reason:
                beyond += 1
                self._discovered.append({**child.describe(), "reason": reason})
            else:
                self._frontier.append(child)
                queued.append(child)
        return queued, beyond

    # ------------------------------------------------------------------
    # Controls (any thread)
    # ------------------------------------------------------------------

    def _control(self, action: str, detail: str = "") -> None:
        self._controls.append({"action": action, "detail": detail, "at": _now()})

    def _require_live_locked(self) -> None:
        if self._state in TERMINAL:
            raise ValueError("this pivot run has finished; start a new one")

    def stop(self) -> str:
        with self._lock:
            if self._state in TERMINAL:
                return "This pivot run has already finished."
            self._stop_requested = True
            if self._state == RUNNING:
                self._state = STOPPING
            self._control("stop")
        self._emit("control", action="stop", detail="")
        return "Stopping after the current request."

    def _find(self, value: str) -> list[PivotNode]:
        wanted = value.strip().casefold()
        return [node for node in self._nodes.values() if node.value.casefold() == wanted]

    def skip(self, value: str) -> str:
        indicator = value.strip()
        if not indicator:
            raise ValueError("skip needs an indicator")
        with self._lock:
            self._require_live_locked()
            self._skip_values.add(indicator.casefold())
            known = bool(self._find(indicator))
            self._control("skip", indicator)
        self._emit("control", action="skip", detail=indicator)
        if known:
            return f"Skipping {indicator} and anything it would have led to."
        return f"{indicator} is not in this run yet; it will be skipped if a module returns it."

    def focus(self, value: str) -> str:
        indicator = value.strip()
        with self._lock:
            self._require_live_locked()
            nodes = self._find(indicator)
            if not nodes:
                raise ValueError(f"{indicator} is not in this pivot run")
            self._focus_keys = {node.key for node in nodes}
            self._control("focus", indicator)
        self._emit("control", action="focus", detail=indicator)
        return f"Expanding only {indicator} and what it leads to; other indicators wait."

    def unfocus(self) -> str:
        with self._lock:
            self._require_live_locked()
            self._focus_keys = set()
            self._control("unfocus")
        self._emit("control", action="unfocus", detail="")
        return "Focus cleared; every queued indicator is back in scope."

    def add(self, value: str) -> str:
        with self._lock:
            self._require_live_locked()
            node = self._add_seed_locked(value)
            if self._focus_keys:
                # The analyst named it explicitly, so it is in scope even while focused.
                self._focus_keys.add(node.key)
            self._control("add", node.value)
        self._emit("control", action="add", detail=node.value)
        return f"Added {node.value} as a new seed at depth 0."

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def finished(self) -> bool:
        return self.state in TERMINAL

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> dict[str, Any]:
        used = self._policy.session_count
        frontier = sorted(self._frontier, key=lambda item: (item.depth, int(item.key[1:])))
        return {
            "run_id": self.run_id,
            "workspace": self.workspace,
            "state": self._state,
            "seeds": list(self.seeds),
            "depth_limit": self.depth_limit,
            "budget": self.budget,
            "requests_used": used,
            "requests_remaining": max(0, self.budget - used),
            "depth_reached": self._depth_reached,
            "current": dict(self._current) if self._current else None,
            "focus": sorted({self._nodes[key].value for key in self._focus_keys}),
            "skip": sorted(self._skip_values),
            "frontier": [node.describe() for node in frontier],
            "expanded": [dict(item) for item in self._expanded],
            "requests": [dict(item) for item in self._requests],
            "skipped": [dict(item) for item in self._skipped],
            "not_expanded": [dict(item) for item in self._discovered],
            "decisions": [dict(item) for item in self._decisions],
            "controls": [dict(item) for item in self._controls],
            "started_at": self._started_at,
            "finished_at": self._finished_at,
            "truth_boundary": TRUTH_BOUNDARY,
        }


class PivotRunRegistry:
    """At most one unfinished pivot run per workspace; the latest run stays readable."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, PivotRun] = {}

    def latest(self, workspace: str) -> PivotRun | None:
        with self._lock:
            return self._runs.get(workspace)

    def active(self, workspace: str) -> PivotRun | None:
        run = self.latest(workspace)
        return run if run is not None and not run.finished else None

    def register(self, run: PivotRun) -> None:
        with self._lock:
            current = self._runs.get(run.workspace)
            if current is not None and not current.finished:
                raise ValueError(
                    f"a pivot run is already active in workspace {run.workspace!r}; "
                    "use `pivot status`, `pivot add <indicator>` or `pivot stop`"
                )
            self._runs[run.workspace] = run
