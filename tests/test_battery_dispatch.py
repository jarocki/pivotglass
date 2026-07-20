"""Tests for battery dispatch — deterministic dispatch (C-1, C-11).

@decision DEC-TEST-BATTERY-DISPATCH-001
@title Tests verify DEFAULT_BATTERIES catalogue, dispatch_batteries() filtering,
       BatteryRun event sequence, and real tool name cross-check
@status accepted
@rationale DEC-BATTERY-DISPATCH-001 and DEC-BATTERY-REGISTRY-001 establish that
           batteries are deterministically selected by target type and dossier slot
           fill status. Tests verify the 5-battery catalogue is complete, dispatch
           filtering handles all STIX types specified in the battery registry, and
           BatteryRun publishes the correct sequence of typed events. The real-tool
           cross-check ensures battery tool names exist in create_tools() so runtime
           dispatch never fails due to an unknown tool name.
"""

from __future__ import annotations

import pytest

from adversary_pursuit.agent.battery import BatteryRun
from adversary_pursuit.agent.battery_registry import DEFAULT_BATTERIES, dispatch_batteries
from adversary_pursuit.agent.tools import ToolContext, create_tools
from adversary_pursuit.dossier.slot_inference import DossierState, SlotState
from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_filled_state(filled_slot: DossierSlotName) -> DossierState:
    """Return a DossierState with one slot FILLED and all others EMPTY."""
    slots = {
        slot: SlotState(
            name=slot,
            status=SlotStatus.FILLED if slot == filled_slot else SlotStatus.EMPTY,
        )
        for slot in DossierSlotName
    }
    return DossierState(slots=slots, total_sco_count=1)


def _all_tool_names() -> set[str]:
    """Return the set of all tool names registered via create_tools()."""
    tools = create_tools(ToolContext())
    return {t["function"]["name"] for t in tools}


# ---------------------------------------------------------------------------
# DEFAULT_BATTERIES catalogue
# ---------------------------------------------------------------------------


def test_default_batteries_count():
    # 5 tool-driven batteries + 1 synthesis sentinel (DEC-BATTERY-REGISTRY-001)
    assert len(DEFAULT_BATTERIES) == 6


def test_identity_battery_present():
    assert "identity_battery" in DEFAULT_BATTERIES


def test_infrastructure_battery_present():
    assert "infrastructure_battery" in DEFAULT_BATTERIES


def test_reputation_battery_present():
    assert "reputation_battery" in DEFAULT_BATTERIES


def test_payload_battery_present():
    assert "payload_battery" in DEFAULT_BATTERIES


def test_behavioral_battery_present():
    assert "behavioral_battery" in DEFAULT_BATTERIES


# ---------------------------------------------------------------------------
# dispatch_batteries — type-based filtering
# ---------------------------------------------------------------------------


def test_dispatch_domain_name_includes_identity():
    names = {b.name for b in dispatch_batteries("domain-name", None)}
    assert "identity_battery" in names


def test_dispatch_domain_name_excludes_direct_infrastructure_probes():
    names = {b.name for b in dispatch_batteries("domain-name", None)}
    assert "infrastructure_battery" not in names


def test_dispatch_ipv4_includes_infrastructure_reputation_behavioral():
    names = {b.name for b in dispatch_batteries("ipv4-addr", None)}
    assert "infrastructure_battery" in names
    assert "reputation_battery" in names
    assert "behavioral_battery" in names


def test_dispatch_ipv4_excludes_identity():
    names = {b.name for b in dispatch_batteries("ipv4-addr", None)}
    assert "identity_battery" not in names


def test_dispatch_file_includes_reputation_payload():
    names = {b.name for b in dispatch_batteries("file", None)}
    assert "reputation_battery" in names
    assert "payload_battery" in names


def test_dispatch_file_excludes_identity_infrastructure():
    names = {b.name for b in dispatch_batteries("file", None)}
    assert "identity_battery" not in names
    assert "infrastructure_battery" not in names


def test_dispatch_email_addr_returns_identity_only():
    result = dispatch_batteries("email-addr", None)
    assert len(result) == 1
    assert result[0].name == "identity_battery"


def test_dispatch_url_includes_reputation_payload_behavioral():
    names = {b.name for b in dispatch_batteries("url", None)}
    assert "reputation_battery" in names
    assert "payload_battery" in names
    assert "behavioral_battery" in names


# ---------------------------------------------------------------------------
# dispatch_batteries — dossier state filtering
# ---------------------------------------------------------------------------


def test_dispatch_domain_skips_identity_when_identity_filled():
    state = _make_filled_state(DossierSlotName.IDENTITY)
    names = {b.name for b in dispatch_batteries("domain-name", state)}
    assert "identity_battery" not in names


def test_dispatch_domain_skips_infrastructure_when_infrastructure_filled():
    state = _make_filled_state(DossierSlotName.INFRASTRUCTURE)
    names = {b.name for b in dispatch_batteries("domain-name", state)}
    assert "infrastructure_battery" not in names


def test_dispatch_domain_includes_identity_when_only_infra_filled():
    state = _make_filled_state(DossierSlotName.INFRASTRUCTURE)
    names = {b.name for b in dispatch_batteries("domain-name", state)}
    assert "identity_battery" in names


# ---------------------------------------------------------------------------
# Real tool name cross-check
# ---------------------------------------------------------------------------


def test_all_battery_tools_exist_in_create_tools():
    """Every tool name declared in DEFAULT_BATTERIES must exist in create_tools()."""
    registered = _all_tool_names()
    missing = []
    for battery_name, battery in DEFAULT_BATTERIES.items():
        for tool_name in battery.tools:
            if tool_name not in registered:
                missing.append(f"{battery_name}.{tool_name}")
    assert not missing, f"Battery tools not in create_tools(): {missing}"


# ---------------------------------------------------------------------------
# Full matrix parametrize: target_type × battery × expected presence
# ---------------------------------------------------------------------------

_DISPATCH_MATRIX = [
    # (target_type, battery_name, in_result)
    ("domain-name", "identity_battery", True),
    ("domain-name", "infrastructure_battery", False),
    ("domain-name", "reputation_battery", True),
    ("domain-name", "payload_battery", False),
    ("domain-name", "behavioral_battery", True),
    ("ipv4-addr", "identity_battery", False),
    ("ipv4-addr", "infrastructure_battery", True),
    ("ipv4-addr", "reputation_battery", True),
    ("ipv4-addr", "payload_battery", False),
    ("ipv4-addr", "behavioral_battery", True),
    ("email-addr", "identity_battery", True),
    ("email-addr", "infrastructure_battery", False),
    ("email-addr", "reputation_battery", False),
    ("email-addr", "payload_battery", False),
    ("email-addr", "behavioral_battery", False),
    ("file", "identity_battery", False),
    ("file", "infrastructure_battery", False),
    ("file", "reputation_battery", True),
    ("file", "payload_battery", True),
    ("file", "behavioral_battery", False),
    ("url", "identity_battery", False),
    ("url", "infrastructure_battery", False),
    ("url", "reputation_battery", True),
    ("url", "payload_battery", True),
    ("url", "behavioral_battery", True),
]


@pytest.mark.parametrize("target_type,battery_name,expected", _DISPATCH_MATRIX)
def test_dispatch_matrix(target_type: str, battery_name: str, expected: bool):
    names = {b.name for b in dispatch_batteries(target_type, None)}
    if expected:
        assert battery_name in names, f"{battery_name} should be dispatched for {target_type}"
    else:
        assert battery_name not in names, (
            f"{battery_name} should NOT be dispatched for {target_type}"
        )


# ---------------------------------------------------------------------------
# BatteryRun compound integration test — EventBus → events → tool execution
# ---------------------------------------------------------------------------


def test_battery_run_fires_events():
    """BatteryRun fires BatteryStarted, BatteryToolStarted, BatteryToolFinished, BatteryFinished."""
    from adversary_pursuit.agent.tui.events import (
        BatteryFinished,
        BatteryStarted,
        BatteryToolFinished,
        BatteryToolStarted,
        EventBus,
    )

    bus = EventBus()
    events: list = []
    bus.subscribe(BatteryStarted, events.append)
    bus.subscribe(BatteryToolStarted, events.append)
    bus.subscribe(BatteryToolFinished, events.append)
    bus.subscribe(BatteryFinished, events.append)

    battery = DEFAULT_BATTERIES["identity_battery"]  # has 3 tools
    calls: list[str] = []

    def fake_executor(tool_name: str, target: str) -> str:
        calls.append(tool_name)
        return f"result for {tool_name}"

    run = BatteryRun(battery, bus, fake_executor)
    run.run("suspicious.example")

    started = [e for e in events if isinstance(e, BatteryStarted)]
    tool_started = [e for e in events if isinstance(e, BatteryToolStarted)]
    tool_finished = [e for e in events if isinstance(e, BatteryToolFinished)]
    finished = [e for e in events if isinstance(e, BatteryFinished)]

    assert len(started) == 1
    assert len(tool_started) == 3, f"identity_battery has 3 tools; got {len(tool_started)}"
    assert len(tool_finished) == 3
    assert len(finished) == 1

    # All 3 tools were executed
    assert set(calls) == set(battery.tools)

    # Final BatteryFinished reports success
    assert finished[0].success is True
