"""Autopivot: after an enrichment, a depth-1 pivot run seeded with what it returned.

``ToolContext.run_module`` calls :func:`run_autopivot` after a successful module
call that returned results, when the analyst has turned ``autopivot on`` (a real
run) or the caller asked for ``dry_run`` (a plan-only run). Nothing else in the
codebase chooses automated next hops.

@decision DEC-PIVOT-AUTOPIVOT-001
@title Autopivot is a depth-1 PivotRun seeded with an enrichment's results; dry_run is a plan-only run
@status accepted
@rationale Until v1.5.0 ``autopivot on`` drove a second pivot mechanism, the event
           bus cascade in ``core/event_bus.py``: it called subscribed modules'
           ``hunt()`` directly (so their results were never stored as evidence),
           could not be watched or steered, and kept its own budget counters beside
           PivotRun's (DEC-PIVOT-RUN-001). Two authorities for "what to query next"
           is the drift CLAUDE.md §10 forbids, so the cascade was retired and
           autopivot became a pivot run:

           Seeds. The indicators the enrichment returned, not its target: they are
           module output, so they carry the module as ``source_module`` and every
           gate applies, popularity and confidence included (DEC-PIVOT-SEED-001 is
           for analyst-typed seeds only). A result that echoes the target back
           (many modules return the queried indicator as an object) is dropped,
           and with nothing else to seed no run starts. Results of a type no
           module subscribes to are recorded as not expanded.

           Depth and budget. Depth 1 (PivotRun's meaning: the seeds and one pivot
           from them). The run's budget is ``auto_pivot_policy.max_per_cascade``,
           the field that always meant "requests one enrichment may trigger",
           further capped by what remains of ``max_per_session`` for this
           ToolContext; when either is 0 no run starts and the summary says why.
           Inside the run the policy's budget gate is the only counter.

           Execution. Synchronous inside the enrichment's call, as the cascade was,
           through ``ToolContext.run_module(..., autopivot=False)``, so every hop is
           stored with provenance and records an ``auto_pivoted`` pivot-trail entry
           from the enrichment's target. The run is registered as the workspace's
           pivot run, so ``pivot status`` shows it and ``pivot stop`` (or a bare
           ``stop`` when no battery is running) halts it; if an analyst's run is
           already active, autopivot does not start a second one and says so.

           Preview. ``dry_run`` builds the same run with ``plan_only=True``: readiness
           and policy are evaluated against the run's own budget and recorded,
           nothing is executed, nothing is written, and the run is not registered.
           Its ``decisions`` list is the decision log.

           Ranking. With ``dossier_aware_ranking`` on, the frontier is ordered by the
           dossier ranker from the enrichment's pre-hunt dossier state
           (DEC-M6-PIVOT-009, DEC-M6-PIVOT-010).

@decision DEC-EVENTBUS-001
@title Pub/sub event bus with policy-gated cascading and module whitelist
@status superseded by DEC-PIVOT-AUTOPIVOT-001
@rationale Original (F60): SpiderFoot's pattern of discovered artifacts triggering
           subscribed modules, with per-cascade and per-session budgets owned by
           PivotPolicy and a per-workspace module whitelist selecting candidates.
           Retired in v1.5.0 with ``core/event_bus.py``: PivotRun is the only
           automated-pivot loop, ``DEFAULT_SUBSCRIPTIONS`` moved to
           ``modules/pivoting/subscriptions.py``, and the whitelist, which no
           configuration ever set, was removed rather than carried over.

@decision DEC-EVENTBUS-002
@title EventBus is disabled by default — opt-in via autopivot command
@status superseded by DEC-PIVOT-AUTOPIVOT-001
@rationale Original: automatic pivoting can consume API quotas rapidly, so it was off
           until the analyst ran ``autopivot on``. The opt-in survives unchanged:
           ``ToolContext.autopivot_enabled`` still starts False and ``autopivot
           on|off`` still toggles it; what it starts is now a bounded pivot run.
"""

from __future__ import annotations

from typing import Any

from pivotglass.modules.pivoting.commands import summary_line
from pivotglass.modules.pivoting.run import MAX_BUDGET

AUTOPIVOT_DEPTH = 1


def autopivot_budget(ctx: Any) -> tuple[int, str]:
    """The request budget for the next autopivot run, and why it is 0 when it is."""

    policy = ctx.config.general.auto_pivot_policy
    remaining = policy.max_per_session - ctx.autopivot_requests_used
    budget = min(policy.max_per_cascade, remaining, MAX_BUDGET)
    if policy.max_per_cascade <= 0:
        return 0, "auto_pivot_policy.max_per_cascade is 0"
    if remaining <= 0:
        return 0, f"this session's autopivot budget of {policy.max_per_session} requests is spent"
    return budget, ""


def run_autopivot(
    ctx: Any,
    *,
    source_module: str,
    target: str,
    results: list[dict],
    plan_only: bool,
    dossier_state: Any = None,
) -> tuple[dict[str, Any] | None, str]:
    """Run (or plan) the autopivot for one enrichment; return (snapshot, summary text).

    The snapshot is None when no run started; the text then says why, or is empty
    when there was nothing to pivot on.
    """

    from pivotglass.modules.pivoting.context import build_context_run

    budget, why = autopivot_budget(ctx)
    if budget < 1:
        return None, f"Autopivot did not run: {why}."
    try:
        run = build_context_run(
            ctx, [], depth=AUTOPIVOT_DEPTH, budget=budget,
            listener=getattr(getattr(ctx, "_narration_runner", None), "_pivot_listener", None),
            result_seeds=results, result_source=source_module, origin=target,
            plan_only=plan_only, dossier_state=dossier_state,
        )
    except ValueError:
        return None, ""  # nothing new to pivot on (no typed result, or only the target echoed)
    if not plan_only:
        try:
            ctx.pivot_runs.register(run)
        except ValueError:
            active = ctx.pivot_runs.active(run.workspace)
            ident = active.run_id if active is not None else "?"
            return None, f"Autopivot did not run: pivot run {ident} is active in this workspace."
    snapshot = run.run()
    ctx.autopivot_requests_used += snapshot["requests_used"]
    return snapshot, autopivot_summary(snapshot)


def autopivot_summary(snapshot: dict[str, Any]) -> str:
    """Plain lines for the tool summary the model and the analyst read."""

    decisions = snapshot["decisions"]
    refused = sum(1 for item in decisions if item["verdict"] != "allow")
    lines = [("Autopivot plan: " if snapshot["plan_only"] else "Autopivot: ") + summary_line(snapshot)]
    if snapshot["plan_only"]:
        lines.append(f"  {len(decisions)} gate decisions; {refused} refused. Nothing was executed.")
    else:
        found = sum(item["result_count"] for item in snapshot["requests"])
        failed = sum(1 for item in snapshot["requests"] if item["status"] == "failed")
        lines.append(
            f"  {found} results from {len(snapshot['requests'])} requests"
            + (f" ({failed} failed)" if failed else "")
            + f"; {refused} module requests refused by gates. `pivot status` shows every decision."
        )
    return "\n".join(lines)
