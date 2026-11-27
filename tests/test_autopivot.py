"""Autopivot is a depth-1 pivot run over an enrichment's results (DEC-PIVOT-AUTOPIVOT-001).

Stub modules are registered in the context's plugin manager and subscribed via
a patched subscription map, so enrichments and their autopivot runs execute
through the real evidence path (``ToolContext.run_module``) with no network.
Bare steering verbs route to the battery, else the pivot run (DEC-YIELD-ROUTING-001).
"""

from __future__ import annotations

import pytest

import pivotglass.modules.pivoting.run as run_module
from pivotglass.agent.tools import ToolContext
from pivotglass.agent.yield_commands import NOTHING_TO_STEER, YieldCommand, route_yield
from pivotglass.core.document_library import PivotTrailAuthority
from pivotglass.modules.pivoting.run import ModuleOutcome, PivotRun

TARGET = "198.51.100.1"
GRAPH: dict[str, list[dict]] = {}
CALLS: list[str] = []


class StubModule:
    name = "stub"
    requires_api_key = False

    def initialize(self, config):
        pass

    async def hunt(self, target, options):
        CALLS.append(target)
        return [dict(item) for item in GRAPH.get(target, [])]


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    CALLS.clear()
    GRAPH.clear()
    GRAPH.update({
        TARGET: [
            {"type": "domain-name", "value": "a.pivot-test.net"},
            {"type": "ipv4-addr", "value": "203.0.113.1"},
            {"type": "email-addr", "value": "ops@pivot-test.net"},
        ],
        "a.pivot-test.net": [{"type": "ipv4-addr", "value": "203.0.113.2"}],
        "203.0.113.2": [{"type": "domain-name", "value": "deep.pivot-test.net"}],
    })
    context = ToolContext(config_dir=tmp_path / "config", workspace_dir=tmp_path / "ws",
                          streak_path=tmp_path / "streak.json")
    context.workspace_mgr.create("case")
    context.workspace_mgr.switch("case")
    for path in ("stub/enrich", "stub/ip", "stub/domain"):
        context.plugin_mgr.register_module(path, StubModule)
    monkeypatch.setattr(run_module, "DEFAULT_SUBSCRIPTIONS", {
        "stub/ip": ["ipv4-addr"], "stub/domain": ["domain-name"],
    })
    return context


def policy(ctx, **update):
    general = ctx.config.general
    general.auto_pivot_policy = general.auto_pivot_policy.model_copy(update=update)


def test_autopivot_off_runs_the_enrichment_alone(ctx):
    result = ctx.run_module("stub/enrich", TARGET)
    assert CALLS == [TARGET]
    assert result["autopivot"] is None and result["decision_log"] == []
    assert "Autopivot" not in result["summary"]


def test_autopivot_seeds_with_results_not_the_target_and_stores_evidence(ctx):
    policy(ctx, max_per_cascade=10)
    ctx.set_autopivot(True)
    result = ctx.run_module("stub/enrich", TARGET)
    snapshot = result["autopivot"]
    assert snapshot["seeds"] == ["a.pivot-test.net", "203.0.113.1", "ops@pivot-test.net"]
    assert snapshot["origin"] == TARGET and snapshot["depth_limit"] == 1
    # Depth 1: the results, then what they returned; depth 2 is discovered, not expanded.
    assert CALLS == [TARGET, "a.pivot-test.net", "203.0.113.1", "203.0.113.2"]
    assert snapshot["state"] == "completed" and snapshot["requests_used"] == 3
    reasons = {item["value"]: item["reason"] for item in snapshot["not_expanded"]}
    assert reasons == {"ops@pivot-test.net": "no module pivots on email-addr",
                       "deep.pivot-test.net": "beyond depth limit 1"}
    # The seeds are module output: attributed to the enrichment's module and fully gated.
    assert {d["reason"] for d in snapshot["decisions"]} == {"passed all gates"}
    assert result["decision_log"] == snapshot["decisions"]
    assert "Autopivot: Pivot run" in result["summary"] and "3 requests" in result["summary"]
    stored = {obj.get("value") for obj in ctx.workspace_mgr.get_stix_objects()}
    assert {"203.0.113.2", "deep.pivot-test.net"} <= stored
    trail = PivotTrailAuthority(ctx.workspace_mgr).list()
    seed_entries = [e for e in trail if e["to_label"] == "a.pivot-test.net"]
    assert seed_entries and seed_entries[0]["action"] == "auto_pivoted"
    assert seed_entries[0]["created_by"] == "system" and seed_entries[0]["from_label"] == TARGET
    assert not any(e["to_label"] == TARGET for e in trail), "the enrichment target is not a pivot seed"
    assert ctx.pivot_runs.latest("case").run_id == snapshot["run_id"]
    assert ctx.autopivot_requests_used == 3


def test_a_result_echoing_the_target_is_not_a_seed(ctx):
    GRAPH[TARGET] = [{"type": "ipv4-addr", "value": TARGET}, {"type": "domain-name", "value": "a.pivot-test.net"}]
    ctx.set_autopivot(True)
    snapshot = ctx.run_module("stub/enrich", TARGET)["autopivot"]
    assert snapshot["seeds"] == ["a.pivot-test.net"]
    GRAPH[TARGET] = [{"type": "ipv4-addr", "value": TARGET}]
    result = ctx.run_module("stub/enrich", TARGET)
    assert result["autopivot"] is None and "Autopivot" not in result["summary"]


def test_autopivot_seeds_pass_the_popularity_gate(ctx):
    GRAPH[TARGET] = [{"type": "domain-name", "value": "youtube.com"}]
    ctx.set_autopivot(True)
    snapshot = ctx.run_module("stub/enrich", TARGET)["autopivot"]
    assert CALLS == [TARGET]
    [decision] = snapshot["decisions"]
    assert decision["verdict"] == "skip" and "top-1k" in decision["reason"]


def test_budget_is_max_per_cascade_capped_by_the_session(ctx):
    policy(ctx, max_per_cascade=2, max_per_session=3)
    ctx.set_autopivot(True)
    first = ctx.run_module("stub/enrich", TARGET)["autopivot"]
    assert first["budget"] == 2 and first["requests_used"] == 2 and first["state"] == "budget_exhausted"
    second = ctx.run_module("stub/enrich", TARGET)["autopivot"]
    assert second["budget"] == 1 and second["requests_used"] == 1
    third = ctx.run_module("stub/enrich", TARGET)
    assert third["autopivot"] is None
    assert "session's autopivot budget of 3 requests is spent" in third["summary"]


def test_zero_per_enrichment_budget_starts_no_run(ctx):
    policy(ctx, max_per_cascade=0)
    ctx.set_autopivot(True)
    result = ctx.run_module("stub/enrich", TARGET)
    assert result["autopivot"] is None and CALLS == [TARGET]
    assert "max_per_cascade is 0" in result["summary"]


def test_dry_run_is_a_plan_that_executes_nothing(ctx):
    policy(ctx, max_per_cascade=1)
    before = len(ctx.workspace_mgr.get_module_runs())
    result = ctx.run_module("stub/enrich", TARGET, {"dry_run": True})
    plan = result["autopivot"]
    assert CALLS == [TARGET], "nothing beyond the enrichment itself was queried"
    assert len(ctx.workspace_mgr.get_module_runs()) == before + 1
    assert plan["plan_only"] and plan["requests_used"] == 0 and plan["requests_planned"] == 1
    assert [r["status"] for r in plan["requests"]] == ["planned"]
    gates = [(d["value"], d["verdict"], d["gate"]) for d in result["decision_log"]]
    assert gates == [("a.pivot-test.net", "allow", "allow"), ("203.0.113.1", "skip", "budget")]
    assert "Autopivot plan: Pivot plan" in result["summary"] and "Nothing was executed" in result["summary"]
    assert ctx.pivot_runs.latest("case") is None, "a plan is not registered as a run"
    assert ctx.autopivot_requests_used == 0


def test_an_active_pivot_run_blocks_autopivot(ctx):
    waiting = PivotRun(["198.51.100.9"], executor=lambda *_: ModuleOutcome([]), workspace="case")
    ctx.pivot_runs.register(waiting)
    ctx.set_autopivot(True)
    result = ctx.run_module("stub/enrich", TARGET)
    assert result["autopivot"] is None and CALLS == [TARGET]
    assert f"pivot run {waiting.run_id} is active" in result["summary"]


@pytest.mark.parametrize("ranking", [True, False])
def test_dossier_ranking_records_dossier_weight_only_when_on(ctx, ranking):
    policy(ctx, dossier_aware_ranking=ranking, max_per_cascade=10)
    ctx.set_autopivot(True)
    decisions = ctx.run_module("stub/enrich", TARGET)["decision_log"]
    assert decisions
    assert all(("dossier_weight" in d) is ranking for d in decisions)


# ---------------------------------------------------------------------------
# Bare steering verbs (DEC-YIELD-ROUTING-001)
# ---------------------------------------------------------------------------


class Battery:
    def __init__(self):
        self.applied: list[YieldCommand] = []

    def apply_yield(self, cmd):
        self.applied.append(cmd)


class Bus:
    def publish(self, event):
        pass


def test_bare_verb_with_nothing_active_says_so(ctx):
    assert route_yield(YieldCommand("stop", None), battery_run=None, ctx=ctx, bus=Bus()) == NOTHING_TO_STEER


def test_bare_verb_targets_the_active_pivot_run_when_no_battery_runs(ctx):
    run = PivotRun(["198.51.100.9"], executor=lambda *_: ModuleOutcome([]), workspace="case")
    ctx.pivot_runs.register(run)
    reply = route_yield(YieldCommand("skip", "198.51.100.9"), battery_run=None, ctx=ctx, bus=Bus())
    assert reply.startswith("Skipping 198.51.100.9")
    assert "Stopping" in route_yield(YieldCommand("stop", None), battery_run=None, ctx=ctx, bus=Bus())
    assert run.state == "queued" and run.snapshot()["controls"][-1]["action"] == "stop"


def test_bare_verb_targets_the_battery_first(ctx):
    run = PivotRun(["198.51.100.9"], executor=lambda *_: ModuleOutcome([]), workspace="case")
    ctx.pivot_runs.register(run)
    battery = Battery()
    route_yield(YieldCommand("stop", None), battery_run=battery, ctx=ctx, bus=Bus())
    assert [cmd.primitive for cmd in battery.applied] == ["stop"]
    assert run.snapshot()["controls"] == [], "the pivot run was not touched"


def test_runner_routes_bare_stop_to_the_pivot_run(ctx):
    from pivotglass.agent.runner import AgentRunner

    runner = AgentRunner(model="test/model")
    runner.ctx = ctx
    run = PivotRun(["198.51.100.9"], executor=lambda *_: ModuleOutcome([]), workspace="case")
    ctx.pivot_runs.register(run)
    assert runner.handle_input("stop").startswith("Stopping after the current request.")
    assert ctx.pivot_runs.active("case") is run and run.run()["state"] == "stopped"
