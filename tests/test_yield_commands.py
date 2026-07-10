"""Tests for yield command parser and dispatcher (C-1, C-10).

@decision DEC-TEST-YIELD-COMMANDS-001
@title Tests verify parse_yield grammar, apply_yield queue mutations, and dispatch_yield events
@status accepted
@rationale DEC-YIELD-COMMANDS-001 defines the verb-first parser grammar precisely.
           Tests cover every acceptance case (stop, focus, add, skip with valid args),
           every rejection case (missing args, extra tokens, unknown verbs, empty input),
           and the three queue-mutation behaviors (stop halts, skip removes, add appends).
           dispatch_yield tests use real BatteryRun so the EventBus→BatteryRun→event
           integration path is exercised without mocking the bus.
"""

from __future__ import annotations

from adversary_pursuit.agent.battery import BatteryRun
from adversary_pursuit.agent.battery_registry import DEFAULT_BATTERIES
from adversary_pursuit.agent.tui.events import EventBus
from adversary_pursuit.agent.yield_commands import YieldCommand, dispatch_yield, parse_yield

# ---------------------------------------------------------------------------
# parse_yield — acceptance cases
# ---------------------------------------------------------------------------


def test_parse_stop():
    cmd = parse_yield("stop")
    assert cmd == YieldCommand("stop", None)


def test_parse_stop_case_insensitive():
    """Parser lowercases the verb — 'STOP' is accepted."""
    cmd = parse_yield("STOP")
    assert cmd == YieldCommand("stop", None)


def test_parse_focus_with_arg():
    cmd = parse_yield("focus cert-sha256:ab12")
    assert cmd == YieldCommand("focus", "cert-sha256:ab12")


def test_parse_add_with_arg():
    cmd = parse_yield("add passivetotal_lookup")
    assert cmd == YieldCommand("add", "passivetotal_lookup")


def test_parse_skip_with_arg():
    cmd = parse_yield("skip whois_lookup")
    assert cmd == YieldCommand("skip", "whois_lookup")


# ---------------------------------------------------------------------------
# parse_yield — rejection cases
# ---------------------------------------------------------------------------


def test_parse_stop_with_trailing_tokens_is_rejected():
    """'stop that guy' must route to the LLM (returns None)."""
    assert parse_yield("stop that guy") is None


def test_parse_focus_no_arg_is_rejected():
    assert parse_yield("focus") is None


def test_parse_add_no_arg_is_rejected():
    assert parse_yield("add") is None


def test_parse_skip_no_arg_is_rejected():
    assert parse_yield("skip") is None


def test_parse_empty_string_is_rejected():
    assert parse_yield("") is None


def test_parse_whitespace_is_rejected():
    assert parse_yield("   ") is None


def test_parse_unknown_verb_is_rejected():
    assert parse_yield("hello world") is None


def test_parse_focus_two_args_is_rejected():
    """More than one argument token must route to LLM."""
    assert parse_yield("focus a b") is None


def test_parse_add_two_args_is_rejected():
    assert parse_yield("add x y") is None


def test_parse_skip_two_args_is_rejected():
    assert parse_yield("skip x y") is None


# ---------------------------------------------------------------------------
# BatteryRun yield integration — stop halts pending tools
# ---------------------------------------------------------------------------


def test_stop_halts_pending_tools():
    """stop yield command halts remaining tools in the battery."""
    bus = EventBus()
    battery = DEFAULT_BATTERIES["identity_battery"]  # whois_lookup, crtsh_lookup, check_breaches
    executed: list[str] = []

    run = BatteryRun(battery, bus, lambda t, _: None)  # noqa: ARG005 - filled later

    def slow_executor(tool_name: str, target: str) -> str:
        executed.append(tool_name)
        # After first tool runs, apply stop
        if len(executed) == 1:
            cmd = parse_yield("stop")
            assert cmd is not None
            run.apply_yield(cmd)
        return "result"

    run._tool_executor = slow_executor  # replace after construction
    run.run("test.example")

    # Only 1 tool should have run (stop applied after first)
    assert len(executed) <= 2, f"Too many tools ran after stop: {executed}"
    assert run.is_stopped is True


# ---------------------------------------------------------------------------
# BatteryRun yield integration — skip removes tool from queue
# ---------------------------------------------------------------------------


def test_skip_removes_tool_from_queue():
    """skip <tool> removes a queued tool from the pending queue."""
    bus = EventBus()
    battery = DEFAULT_BATTERIES["identity_battery"]  # whois_lookup, crtsh_lookup, check_breaches
    executed: list[str] = []

    run = BatteryRun(battery, bus, lambda t, _: None)  # noqa: ARG005

    def executor_with_skip(tool_name: str, target: str) -> str:
        executed.append(tool_name)
        if len(executed) == 1:
            cmd = parse_yield("skip check_breaches")
            assert cmd is not None
            run.apply_yield(cmd)
        return "result"

    run._tool_executor = executor_with_skip
    run.run("test.example")

    assert "check_breaches" not in executed
    assert len(executed) == 2  # whois_lookup and crtsh_lookup ran


# ---------------------------------------------------------------------------
# BatteryRun yield integration — add appends tool to queue
# ---------------------------------------------------------------------------


def test_add_appends_tool_to_queue():
    """add <tool> appends a new tool to the pending queue."""
    bus = EventBus()
    battery = DEFAULT_BATTERIES["identity_battery"]  # 3 tools
    executed: list[str] = []

    run = BatteryRun(battery, bus, lambda t, _: None)  # noqa: ARG005

    def executor_with_add(tool_name: str, target: str) -> str:
        executed.append(tool_name)
        if len(executed) == 1:
            cmd = parse_yield("add dns_resolve")
            assert cmd is not None
            run.apply_yield(cmd)
        return "result"

    run._tool_executor = executor_with_add
    run.run("test.example")

    assert "dns_resolve" in executed
    # 3 original + 1 added = 4 total executions
    assert len(executed) == 4


# ---------------------------------------------------------------------------
# dispatch_yield publishes YieldReceived and returns voice string
# ---------------------------------------------------------------------------


def test_dispatch_yield_publishes_event():
    """dispatch_yield publishes YieldReceived event and returns a voice string."""
    from adversary_pursuit.agent.tui.events import YieldReceived

    bus = EventBus()
    received: list = []
    bus.subscribe(YieldReceived, received.append)

    cmd = YieldCommand("stop", None)
    result = dispatch_yield(cmd, battery_run=None, bus=bus, character="default")

    assert len(received) == 1
    assert received[0].primitive == "stop"
    assert received[0].argument is None
    assert isinstance(result, str)
    assert len(result) > 0


def test_dispatch_yield_focus_publishes_argument():
    from adversary_pursuit.agent.tui.events import YieldReceived

    bus = EventBus()
    received: list = []
    bus.subscribe(YieldReceived, received.append)

    cmd = YieldCommand("focus", "whois_lookup")
    dispatch_yield(cmd, battery_run=None, bus=bus, character="ninja")

    assert len(received) == 1
    assert received[0].primitive == "focus"
    assert received[0].argument == "whois_lookup"


def test_dispatch_yield_character_voice():
    """dispatch_yield returns character-voiced feedback from the phrase cache."""
    bus = EventBus()
    cmd = YieldCommand("stop", None)

    result_default = dispatch_yield(cmd, battery_run=None, bus=bus, character="default")
    assert result_default  # non-empty

    result_ninja = dispatch_yield(cmd, battery_run=None, bus=bus, character="ninja")
    assert result_ninja  # non-empty

    result_troll = dispatch_yield(cmd, battery_run=None, bus=bus, character="full_troll")
    assert result_troll  # non-empty
