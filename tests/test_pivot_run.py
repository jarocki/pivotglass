"""PivotRun: the bounded multi-hop pivot authority (DEC-PIVOT-RUN-001, #22).

Modules are stubs keyed by (module, value); nothing touches the network.
Documentation addresses (198.51.100.0/24, 203.0.113.0/24) pass the value gate.
"""

from __future__ import annotations

import threading

import pytest

from pivotglass.core.config import AutoPivotPolicyConfig
from pivotglass.modules.pivoting.run import (
    BUDGET_EXHAUSTED,
    COMPLETED,
    STOPPED,
    ModuleOutcome,
    PivotRun,
    PivotRunRegistry,
)

SUBS = {"stub/ip": ["ipv4-addr"], "stub/domain": ["domain-name"]}


def ip(value: str, **extra) -> dict:
    return {"type": "ipv4-addr", "value": value, **extra}


def dom(value: str) -> dict:
    return {"type": "domain-name", "value": value}


class Stub:
    """Executor returning canned results and recording call order."""

    def __init__(self, graph: dict[tuple[str, str], list[dict]], *, hooks=None):
        self.graph = graph
        self.calls: list[tuple[str, str]] = []
        self.hooks = hooks or {}

    def __call__(self, module: str, value: str) -> ModuleOutcome:
        self.calls.append((module, value))
        hook = self.hooks.get((module, value))
        if hook:
            hook()
        return ModuleOutcome(self.graph.get((module, value), []))


def make(seeds, stub, **kwargs) -> PivotRun:
    kwargs.setdefault("subscriptions", SUBS)
    kwargs.setdefault("policy_config", AutoPivotPolicyConfig(allowlist_path="/nonexistent", denylist_path="/nonexistent"))
    return PivotRun(seeds, executor=stub, **kwargs)


# A two-level tree: seed → two domains → each one IP.
TREE = {
    ("stub/ip", "198.51.100.1"): [dom("a.pivot-test.net"), dom("b.pivot-test.net")],
    ("stub/domain", "a.pivot-test.net"): [ip("203.0.113.1")],
    ("stub/domain", "b.pivot-test.net"): [ip("203.0.113.2")],
    ("stub/ip", "203.0.113.1"): [dom("c.pivot-test.net")],
}


def test_breadth_first_order_and_depth_limit():
    stub = Stub(TREE)
    snapshot = make(["198.51.100.1"], stub, depth=2).run()
    assert stub.calls == [
        ("stub/ip", "198.51.100.1"),
        ("stub/domain", "a.pivot-test.net"),
        ("stub/domain", "b.pivot-test.net"),
        ("stub/ip", "203.0.113.1"),
        ("stub/ip", "203.0.113.2"),
    ]
    assert snapshot["state"] == COMPLETED
    assert snapshot["depth_reached"] == 2
    # c.pivot-test.net is depth 3: discovered, recorded, not expanded.
    assert [(item["value"], item["reason"]) for item in snapshot["not_expanded"]] == [
        ("c.pivot-test.net", "beyond depth limit 2")
    ]
    assert snapshot["requests_used"] == 5


def test_default_depth_is_seed_plus_one_pivot():
    stub = Stub(TREE)
    snapshot = make(["198.51.100.1"], stub).run()
    assert snapshot["depth_limit"] == 1
    assert [value for _, value in stub.calls] == ["198.51.100.1", "a.pivot-test.net", "b.pivot-test.net"]
    assert {item["value"] for item in snapshot["not_expanded"]} == {"203.0.113.1", "203.0.113.2"}


def test_duplicates_are_expanded_once():
    graph = {
        ("stub/ip", "198.51.100.1"): [dom("a.pivot-test.net"), ip("198.51.100.1")],
        ("stub/domain", "a.pivot-test.net"): [ip("198.51.100.1")],
    }
    stub = Stub(graph)
    make(["198.51.100.1"], stub, depth=3).run()
    assert stub.calls == [("stub/ip", "198.51.100.1"), ("stub/domain", "a.pivot-test.net")]


def test_budget_exhaustion_is_the_policy_budget_gate():
    stub = Stub(TREE)
    snapshot = make(["198.51.100.1"], stub, depth=3, budget=2).run()
    assert len(stub.calls) == 2
    assert snapshot["state"] == BUDGET_EXHAUSTED
    assert snapshot["requests_used"] == 2 and snapshot["requests_remaining"] == 0
    budget = [item for item in snapshot["decisions"] if item["gate"] == "budget"]
    assert budget and "per-cascade budget exhausted: 2/2" in budget[0]["reason"]
    assert [item["value"] for item in snapshot["skipped"]] == ["b.pivot-test.net", "203.0.113.1"]
    assert {item["gate"] for item in snapshot["skipped"]} == {"budget"}


def test_policy_rejection_is_recorded_and_costs_nothing():
    graph = {("stub/ip", "198.51.100.1"): [ip("10.0.0.5"), dom("example.com"), ip("203.0.113.9")]}
    stub = Stub(graph)
    snapshot = make(["198.51.100.1"], stub, depth=1).run()
    assert stub.calls == [("stub/ip", "198.51.100.1"), ("stub/ip", "203.0.113.9")]
    rejected = {item["value"]: item for item in snapshot["decisions"] if item["verdict"] == "skip"}
    assert rejected["10.0.0.5"]["gate"] == "ioc_value" and "RFC1918" in rejected["10.0.0.5"]["reason"]
    assert rejected["example.com"]["gate"] == "ioc_value" and "RFC6761" in rejected["example.com"]["reason"]
    assert snapshot["requests_used"] == 2


def test_confidence_gate_applies_to_module_output():
    graph = {("stub/ip", "198.51.100.1"): [ip("203.0.113.7", x_abuse_confidence_score=10)]}
    stub = Stub(graph)
    snapshot = make(["198.51.100.1"], stub).run()
    assert stub.calls == [("stub/ip", "198.51.100.1")]
    assert any(item["gate"] == "confidence" for item in snapshot["decisions"])


def test_readiness_skip_records_reason_without_spending_budget():
    stub = Stub(TREE)
    snapshot = make(
        ["198.51.100.1"], stub, readiness=lambda module: "not configured (no credential)" if module == "stub/domain" else None,
    ).run()
    assert stub.calls == [("stub/ip", "198.51.100.1")]
    assert snapshot["requests_used"] == 1
    skipped = [item for item in snapshot["decisions"] if item["gate"] == "readiness"]
    assert {item["value"] for item in skipped} == {"a.pivot-test.net", "b.pivot-test.net"}


def test_failed_request_counts_and_run_continues():
    def boom():
        raise ConnectionError("down")

    stub = Stub(TREE, hooks={("stub/domain", "a.pivot-test.net"): boom})
    snapshot = make(["198.51.100.1"], stub).run()
    assert snapshot["state"] == COMPLETED
    statuses = [(item["value"], item["status"]) for item in snapshot["requests"]]
    assert statuses == [("198.51.100.1", "ok"), ("a.pivot-test.net", "failed"), ("b.pivot-test.net", "ok")]
    assert snapshot["requests"][1]["reason"] == "ConnectionError"
    assert snapshot["requests_used"] == 3


def test_stop_mid_run_finishes_current_request_then_halts():
    run_ref: list[PivotRun] = []
    stub = Stub(TREE, hooks={("stub/domain", "a.pivot-test.net"): lambda: run_ref[0].stop()})
    run = make(["198.51.100.1"], stub, depth=3)
    run_ref.append(run)
    snapshot = run.run()
    assert snapshot["state"] == STOPPED
    assert stub.calls[-1] == ("stub/domain", "a.pivot-test.net")
    assert snapshot["requests"][-1]["value"] == "a.pivot-test.net"  # its evidence was kept
    assert {item["value"] for item in snapshot["skipped"]} == {"b.pivot-test.net", "203.0.113.1"}
    assert all(item["reason"] == "stopped by analyst" for item in snapshot["skipped"])


def test_skip_prunes_unexpanded_descendants():
    run_ref: list[PivotRun] = []
    calls: list[str] = []

    def executor(module, value):
        outcome = Stub(TREE)(module, value)
        calls.append(value)
        if value == "198.51.100.1":
            run_ref[0].skip("a.pivot-test.net")
        return outcome

    run = PivotRun(["198.51.100.1"], executor=executor, subscriptions=SUBS, depth=3)
    run_ref.append(run)
    snapshot = run.run()
    assert calls == ["198.51.100.1", "b.pivot-test.net", "203.0.113.2"]
    assert [(item["value"], item["reason"]) for item in snapshot["skipped"]] == [
        ("a.pivot-test.net", "skipped by analyst")
    ]


def test_skip_of_expanded_indicator_drops_its_children():
    run_ref: list[PivotRun] = []

    def executor(module, value):
        outcome = Stub(TREE)(module, value)
        calls.append(value)
        if value == "a.pivot-test.net":
            run_ref[0].skip("198.51.100.1")  # skip the seed after its children are queued
        return outcome

    calls: list[str] = []
    run = PivotRun(["198.51.100.1"], executor=executor, subscriptions=SUBS, depth=3)
    run_ref.append(run)
    snapshot = run.run()
    assert calls == ["198.51.100.1", "a.pivot-test.net"]
    reasons = {item["value"]: item["reason"] for item in snapshot["skipped"]}
    assert reasons["b.pivot-test.net"] == "skipped by analyst (descendant of 198.51.100.1)"
    assert reasons["203.0.113.1"] == "skipped by analyst (descendant of 198.51.100.1)"


def test_focus_restricts_expansion_and_defers_the_rest():
    run_ref: list[PivotRun] = []

    def executor(module, value):
        outcome = Stub(TREE)(module, value)
        calls.append(value)
        if value == "a.pivot-test.net":
            run_ref[0].focus("b.pivot-test.net")  # a's children are now out of focus
        return outcome

    calls: list[str] = []
    run = PivotRun(["198.51.100.1"], executor=executor, subscriptions=SUBS, depth=3)
    run_ref.append(run)
    snapshot = run.run()
    assert calls == ["198.51.100.1", "a.pivot-test.net", "b.pivot-test.net", "203.0.113.2"]
    assert snapshot["focus"] == ["b.pivot-test.net"]
    assert {(item["value"], item["gate"]) for item in snapshot["skipped"]} == {("203.0.113.1", "focus")}


def test_focus_rejects_unknown_indicator():
    run = make(["198.51.100.1"], Stub(TREE))
    with pytest.raises(ValueError, match="not in this pivot run"):
        run.focus("nowhere.pivot-test.net")


def test_add_enqueues_new_seed_at_depth_zero_before_deeper_items():
    run_ref: list[PivotRun] = []

    def executor(module, value):
        outcome = Stub(TREE)(module, value)
        calls.append(value)
        if value == "198.51.100.1":
            run_ref[0].add("198.51.100.200")
        return outcome

    calls: list[str] = []
    run = PivotRun(["198.51.100.1"], executor=executor, subscriptions=SUBS, depth=2)
    run_ref.append(run)
    snapshot = run.run()
    assert calls[:2] == ["198.51.100.1", "198.51.100.200"]
    assert snapshot["seeds"] == ["198.51.100.1", "198.51.100.200"]
    with pytest.raises(ValueError, match="finished"):
        run.add("198.51.100.201")


def test_add_rejects_non_indicator_and_duplicates():
    run = make(["198.51.100.1"], Stub(TREE))
    with pytest.raises(ValueError, match="not a recognized indicator"):
        run.add("not an indicator")
    with pytest.raises(ValueError, match="already in this pivot run"):
        run.add("198.51.100.1")


def test_depth_and_budget_bounds():
    with pytest.raises(ValueError, match="depth"):
        make(["198.51.100.1"], Stub({}), depth=4)
    with pytest.raises(ValueError, match="budget"):
        make(["198.51.100.1"], Stub({}), budget=201)


def test_controls_are_thread_safe_while_running():
    gate = threading.Event()
    release = threading.Event()
    wide = {("stub/ip", "198.51.100.1"): [dom(f"h{i}.pivot-test.net") for i in range(40)]}

    def executor(module, value):
        if value == "h0.pivot-test.net":
            gate.set()
            release.wait(5)
        return ModuleOutcome(wide.get((module, value), []))

    run = PivotRun(["198.51.100.1"], executor=executor, subscriptions=SUBS, depth=2, budget=200)
    worker = threading.Thread(target=run.run)
    worker.start()
    assert gate.wait(5)
    errors: list[Exception] = []

    def hammer(index: int):
        try:
            for step in range(20):
                run.skip(f"h{(index * 20 + step) % 40}.pivot-test.net")
                run.snapshot()
                run.add(f"203.0.113.{index * 20 + step + 1}")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=hammer, args=(index,)) for index in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    release.set()
    worker.join(10)
    assert not errors
    snapshot = run.snapshot()
    assert snapshot["state"] == COMPLETED
    assert len(snapshot["seeds"]) == 81
    assert len({item["value"] for item in snapshot["requests"]}) == len(snapshot["requests"])


def test_registry_allows_one_active_run_per_workspace():
    registry = PivotRunRegistry()
    first = make(["198.51.100.1"], Stub({}), workspace="case")
    registry.register(first)
    with pytest.raises(ValueError, match="already active"):
        registry.register(make(["198.51.100.2"], Stub({}), workspace="case"))
    registry.register(make(["198.51.100.3"], Stub({}), workspace="other"))
    first.run()
    second = make(["198.51.100.2"], Stub({}), workspace="case")
    registry.register(second)
    assert registry.latest("case") is second


def test_listener_failure_never_stops_the_run():
    def broken(_event):
        raise RuntimeError("display gone")

    snapshot = make(["198.51.100.1"], Stub(TREE), listener=broken).run()
    assert snapshot["state"] == COMPLETED


def test_vulnerability_outputs_pivot_by_cve_name():
    subs = {"stub/ip": ["ipv4-addr"], "stub/cve": ["vulnerability"]}
    graph = {("stub/ip", "198.51.100.1"): [{"type": "vulnerability", "name": "cve-2024-0001"}]}
    stub = Stub(graph)
    PivotRun(["198.51.100.1"], executor=stub, subscriptions=subs).run()
    assert stub.calls == [("stub/ip", "198.51.100.1"), ("stub/cve", "CVE-2024-0001")]
