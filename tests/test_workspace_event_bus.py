"""Tests for workspace.notify_target_changed — explicit-bus pattern (Blocker 2, Concern 2).

Verifies:
  - notify_target_changed(bus, target, target_type) publishes TargetChanged to the bus
  - notify_target_changed(None, ...) is a no-op (Slice 5 / non-TUI behavior preserved)
  - No module-level singleton leaks between tests (Option B isolation guarantee)
  - Production sequence: TUI creates bus → bus flows to notify_target_changed → LivePane updates

@decision DEC-TEST-WORKSPACE-EVENT-BUS-001
@title Tests verify explicit-bus notify_target_changed pattern (Concern 2 Option B)
@status accepted
@rationale Reviewer round 2 (Blocker 2 + Concern 2): the original implementation used
    a module-level _EVENT_BUS global wired via wire_event_bus(). This created hidden
    state that required explicit teardown in every test. Option B (reviewer recommendation)
    passes bus explicitly so isolation is automatic. These tests prove the explicit-bus
    contract and verify the real production sequence: bus created in _run_tui_chat →
    passed to TuiApplication → LivePane subscribes → notify_target_changed publishes →
    LivePane's target row updates.
"""

from __future__ import annotations

import adversary_pursuit.core.workspace as workspace_mod
from adversary_pursuit.agent.tui.events import EventBus, TargetChanged

# ---------------------------------------------------------------------------
# Unit: notify_target_changed publishes TargetChanged to explicit bus
# ---------------------------------------------------------------------------


def test_notify_target_changed_publishes_to_bus():
    """notify_target_changed(bus, ...) publishes TargetChanged to the provided bus.

    This is Blocker 2's core invariant: the workspace notification helper must
    publish to the supplied bus so the TUI live pane's target row updates.
    """
    bus = EventBus()
    received: list[TargetChanged] = []
    bus.subscribe(TargetChanged, received.append)

    workspace_mod.notify_target_changed(bus, "evil.example.com", "domain-name")

    assert len(received) == 1, "Expected exactly one TargetChanged event"
    assert received[0].target == "evil.example.com"
    assert received[0].target_type == "domain-name"


def test_notify_target_changed_none_bus_is_noop():
    """notify_target_changed(None, ...) is a no-op — no exception, no event published.

    Preserves Slice 5 / cmd2-standalone behavior: when no TUI session is active,
    callers pass bus=None and the call does nothing.
    """
    # Should not raise
    workspace_mod.notify_target_changed(None, "test.example", "domain-name")


def test_notify_target_changed_multiple_events():
    """Multiple notify calls to the same bus accumulate events in order."""
    bus = EventBus()
    received: list[TargetChanged] = []
    bus.subscribe(TargetChanged, received.append)

    workspace_mod.notify_target_changed(bus, "first.example", "domain-name")
    workspace_mod.notify_target_changed(bus, "192.0.2.1", "ipv4-addr")

    assert len(received) == 2
    assert received[0].target == "first.example"
    assert received[1].target == "192.0.2.1"
    assert received[1].target_type == "ipv4-addr"


def test_notify_target_changed_different_buses_isolated():
    """Two separate buses receive independent events — no cross-contamination.

    This verifies the Option B isolation guarantee: each TUI session creates its
    own EventBus and only receives events published to that bus.
    """
    bus_a = EventBus()
    bus_b = EventBus()
    received_a: list[TargetChanged] = []
    received_b: list[TargetChanged] = []
    bus_a.subscribe(TargetChanged, received_a.append)
    bus_b.subscribe(TargetChanged, received_b.append)

    workspace_mod.notify_target_changed(bus_a, "target-for-a.example", "domain-name")
    workspace_mod.notify_target_changed(bus_b, "target-for-b.example", "domain-name")

    assert len(received_a) == 1 and received_a[0].target == "target-for-a.example"
    assert len(received_b) == 1 and received_b[0].target == "target-for-b.example"


# ---------------------------------------------------------------------------
# Integration: real production sequence — bus → TuiApplication → LivePane
# ---------------------------------------------------------------------------


def test_real_production_sequence_bus_wires_live_pane():
    """Real production sequence: bus created → LivePane subscribes → notify → pane updates.

    This is the compound-interaction test that crosses component boundaries.
    The sequence mirrors what _run_tui_chat does:
      1. Create EventBus (in _run_tui_chat scope)
      2. Pass bus to TuiApplication / LivePane (LivePane subscribes to TargetChanged)
      3. Call notify_target_changed(bus, target, type) to publish TargetChanged
      4. LivePane._target state updates → render() shows new target in row 2

    No mocks — real EventBus, real LivePane, real notify_target_changed.
    """
    from adversary_pursuit.agent.tui.live_pane import LivePane

    # Step 1: Create bus (mirrors _run_tui_chat)
    bus = EventBus()

    # Step 2: Wire LivePane to bus (mirrors TuiApplication.__init__)
    pane = LivePane(bus=bus, mode_name="default", model_display="test-model")

    # Verify pre-notify state: target is the default placeholder
    lines_before = pane.render()
    assert "—" in lines_before[1] or "target:" in lines_before[1].lower()

    # Step 3: Publish TargetChanged via notify_target_changed (explicit bus)
    workspace_mod.notify_target_changed(bus, "apt41-infra.evil.example", "domain-name")

    # Step 4: LivePane state updated — render() shows the new target
    lines_after = pane.render()
    assert "apt41-infra.evil.example" in lines_after[1], (
        f"Expected target in live pane row 2 after notify_target_changed, got: {lines_after[1]!r}"
    )


def test_no_module_level_singleton_exists():
    """workspace.py must NOT export wire_event_bus or _EVENT_BUS (Option B: no global).

    This test asserts the Option B architectural contract: no module-level singleton.
    If either symbol reappears (e.g. from a merge conflict), this test fails loudly.
    """
    assert not hasattr(workspace_mod, "wire_event_bus"), (
        "workspace.wire_event_bus must not exist (Option B: explicit bus, no global). "
        "Remove it and update callsites to pass bus explicitly."
    )
    assert not hasattr(workspace_mod, "_EVENT_BUS"), (
        "workspace._EVENT_BUS must not exist (Option B: explicit bus, no global). "
        "Remove it and update callsites to pass bus explicitly."
    )
