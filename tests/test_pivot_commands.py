"""The shared ``pivot`` grammar and its ToolContext wiring (#22, DEC-PIVOT-RUN-001).

Stub modules are registered in the context's plugin manager and subscribed via a
patched subscription map, so runs execute through the real evidence path
(``ToolContext.run_module``) without touching the network.
"""

from __future__ import annotations

import _thread
import threading
import time

import pytest

import pivotglass.modules.pivoting.run as run_module
from pivotglass.agent.tools import ToolContext
from pivotglass.core.command_completion import command_completions
from pivotglass.core.document_library import PivotTrailAuthority
from pivotglass.modules.pivoting.commands import (
    PIVOT_USAGE,
    execute_pivot_command,
    format_event,
    parse_pivot_command,
    render_snapshot,
)

GRAPH = {
    "198.51.100.1": [{"type": "domain-name", "value": "a.pivot-test.net"}],
    "a.pivot-test.net": [{"type": "ipv4-addr", "value": "203.0.113.1"}],
}
CALLS: list[str] = []
HOOKS: dict[str, object] = {}


class StubModule:
    name = "stub"
    requires_api_key = False

    def initialize(self, config):
        pass

    async def hunt(self, target, options):
        CALLS.append(target)
        hook = HOOKS.get(target)
        if callable(hook):
            hook()
        return list(GRAPH.get(target, []))


class KeyedStub(StubModule):
    requires_api_key = True


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    CALLS.clear()
    HOOKS.clear()
    context = ToolContext(config_dir=tmp_path / "config", workspace_dir=tmp_path / "ws",
                          streak_path=tmp_path / "streak.json")
    context.workspace_mgr.create("case")
    context.workspace_mgr.switch("case")
    context.plugin_mgr.register_module("stub/ip", StubModule)
    context.plugin_mgr.register_module("stub/domain", StubModule)
    context.plugin_mgr.register_module("stub/keyed", KeyedStub)
    monkeypatch.setattr(run_module, "DEFAULT_SUBSCRIPTIONS", {
        "stub/ip": ["ipv4-addr"], "stub/domain": ["domain-name"], "stub/keyed": ["ipv4-addr"],
    })
    return context


# ---------------------------------------------------------------------------
# Grammar
# ---------------------------------------------------------------------------


def test_parse_start_with_options():
    command = parse_pivot_command("198.51.100.1 a.pivot-test.net depth:2 budget:50")
    assert command.action == "start"
    assert command.indicators == ("198.51.100.1", "a.pivot-test.net")
    assert (command.depth, command.budget) == (2, 50)


def test_parse_defaults_and_controls():
    assert parse_pivot_command("198.51.100.1").depth == 1
    assert parse_pivot_command("198.51.100.1").budget == 20
    assert parse_pivot_command("").action == "status"
    assert parse_pivot_command(("skip", "x.pivot-test.net")).indicators == ("x.pivot-test.net",)
    for action in ("status", "stop", "unfocus"):
        assert parse_pivot_command(action).action == action


@pytest.mark.parametrize("text", ["198.51.100.1 depth:4", "198.51.100.1 budget:0", "198.51.100.1 depth:x",
                                  "not-an-indicator", "stop now", "skip", "add nonsense", "depth:2"])
def test_parse_rejects_bad_input(text):
    with pytest.raises(ValueError):
        parse_pivot_command(text)


def test_completions_offer_pivot_grammar():
    assert "pivot" in command_completions("piv")
    assert {"pivot status", "pivot stop", "pivot skip ", "pivot depth:"} <= set(command_completions("pivot "))


# ---------------------------------------------------------------------------
# Execution through the real evidence path
# ---------------------------------------------------------------------------


def test_foreground_run_stores_evidence_and_records_trail(ctx):
    lines: list[str] = []
    result = execute_pivot_command("198.51.100.1 depth:1", ctx, background=False,
                                   listener=lambda event: lines.append(format_event(event) or ""))
    snapshot = result["data"]
    assert snapshot["state"] == "completed"
    assert CALLS == ["198.51.100.1", "a.pivot-test.net"]
    # The keyed module had no credential: recorded, not requested, no budget spent.
    assert snapshot["requests_used"] == 2
    assert any(d["gate"] == "readiness" and d["module"] == "stub/keyed" for d in snapshot["decisions"])
    stored = {obj["value"]: obj for obj in ctx.workspace_mgr.get_stix_objects() if obj.get("value")}
    assert {"a.pivot-test.net", "203.0.113.1"} <= set(stored)
    runs = {(run["module_name"], run["target"]) for run in ctx.workspace_mgr.get_module_runs()}
    assert ("stub/ip", "198.51.100.1") in runs and ("stub/domain", "a.pivot-test.net") in runs
    trail = PivotTrailAuthority(ctx.workspace_mgr).list()
    assert [(e["to_label"], e["action"], e["created_by"]) for e in trail] == [
        ("198.51.100.1", "investigated", "human"),
        ("a.pivot-test.net", "auto_pivoted", "system"),
    ]
    assert trail[1]["from_label"] == "198.51.100.1"
    assert "not an observed relationship" in trail[1]["basis"]
    assert snapshot["requests"][0]["artifact_ids"], "new workspace objects are attributed to their request"
    text = render_snapshot(snapshot)
    assert "requests 2/20" in text and "not configured" in text
    assert any("Pivot run" in line for line in lines)


def test_run_never_cascades_through_the_event_bus(ctx, monkeypatch):
    ctx.set_autopivot(True)

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("the event bus must not cascade underneath a pivot run")

    monkeypatch.setattr(ctx.event_bus, "process_results", forbidden)
    snapshot = execute_pivot_command("198.51.100.1", ctx, background=False)["data"]
    assert snapshot["state"] == "completed" and snapshot["requests_used"] == 2


def test_background_run_controls_and_one_active_run(ctx):
    release, entered = threading.Event(), threading.Event()
    HOOKS["198.51.100.1"] = lambda: (entered.set(), release.wait(5))
    started = execute_pivot_command("198.51.100.1 depth:2", ctx, background=True)
    assert entered.wait(5)
    assert started["action"] == "start"
    with pytest.raises(ValueError, match="already active"):
        execute_pivot_command("198.51.100.9", ctx)
    assert "Added 198.51.100.7" in execute_pivot_command("add 198.51.100.7", ctx)["text"]
    assert "Stopping" in execute_pivot_command("stop", ctx)["text"]
    release.set()
    run = started["run"]
    for _ in range(200):
        if run.finished:
            break
        time.sleep(0.01)
    snapshot = execute_pivot_command("status", ctx)["data"]
    assert snapshot["state"] == "stopped"
    assert CALLS == ["198.51.100.1"]
    assert {item["value"] for item in snapshot["skipped"]} == {"198.51.100.7", "a.pivot-test.net"}
    with pytest.raises(ValueError, match="No active pivot run"):
        execute_pivot_command("stop", ctx)
    # Finished runs free the workspace for the next one.
    assert execute_pivot_command("198.51.100.9", ctx, background=False)["data"]["state"] == "completed"


def test_status_without_a_run(ctx):
    result = execute_pivot_command("status", ctx)
    assert result["data"] is None and PIVOT_USAGE in result["text"]


def test_keyboard_interrupt_stops_foreground_run_after_current_request(ctx):
    def interrupt_and_wait_for_stop():
        _thread.interrupt_main()  # what Ctrl-C delivers to the REPL thread
        for _ in range(500):
            if ctx.pivot_runs.latest("case").state == "stopping":
                return
            time.sleep(0.01)

    HOOKS["198.51.100.1"] = interrupt_and_wait_for_stop
    result = execute_pivot_command("198.51.100.1 depth:2", ctx, background=False)
    snapshot = result["data"]
    assert snapshot["state"] == "stopped"
    assert CALLS == ["198.51.100.1"]
    assert snapshot["requests"][0]["status"] == "ok"
    assert any(item["value"] == "a.pivot-test.net" for item in ctx.workspace_mgr.get_stix_objects())


# ---------------------------------------------------------------------------
# Surfaces: cyberdeck verbs and the classic console route to the same grammar
# ---------------------------------------------------------------------------


def test_cyberdeck_verb_runs_in_background_with_listener(ctx):
    from pivotglass.agent.repl_verbs import dispatch_repl_verb, parse_repl_verb

    lines: list[str] = []
    runner = type("Runner", (), {"_pivot_listener": lambda self, event: lines.append(format_event(event) or "")})()
    verb = parse_repl_verb("pivot 198.51.100.1")
    assert verb is not None and verb.name == "pivot"
    reply = dispatch_repl_verb(verb, ctx, None, None, runner=runner)
    assert "started" in reply
    run = ctx.pivot_runs.latest("case")
    for _ in range(300):
        if run.finished:
            break
        time.sleep(0.01)
    assert run.state == "completed"
    assert any(line.startswith("◇ Pivot run") for line in lines)
    status = dispatch_repl_verb(parse_repl_verb("pivot status"), ctx, None, None)
    assert "requests 2/20" in status
    assert dispatch_repl_verb(parse_repl_verb("pivot depth:9 198.51.100.1"), ctx, None, None).startswith("depth must be")


def test_classic_console_runs_pivot_in_foreground(tmp_path, monkeypatch):
    import io

    from pivotglass.core.console import PivotglassConsole

    CALLS.clear()
    monkeypatch.setattr(run_module, "DEFAULT_SUBSCRIPTIONS", {"stub/ip": ["ipv4-addr"], "stub/domain": ["domain-name"]})
    app = PivotglassConsole(config_dir=tmp_path / "config", workspace_dir=tmp_path / "ws",
                            streak_path=tmp_path / "streak.json")
    pivot_ctx = app._pivot_context()
    pivot_ctx.plugin_mgr.register_module("stub/ip", StubModule)
    pivot_ctx.plugin_mgr.register_module("stub/domain", StubModule)
    app.stdout = io.StringIO()
    app.onecmd_plus_hooks("pivot 198.51.100.1")
    output = app.stdout.getvalue()
    assert CALLS == ["198.51.100.1", "a.pivot-test.net"]
    assert "completed" in output and "requests 2/20" in output
    app.stdout = io.StringIO()
    app.onecmd_plus_hooks("pivot stop")
    assert "No active pivot run" in app.stdout.getvalue()
    stored = {obj.get("value") for obj in app.workspace_mgr.get_stix_objects()}
    assert "a.pivot-test.net" in stored, "the console's own workspace view sees the run's evidence"
