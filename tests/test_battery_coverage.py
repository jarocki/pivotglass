"""C-3 acceptance tests: every dossier slot must have battery coverage.

Verifies the C-3 commitment: "every slot has at least one battery that can
contribute evidence." Also verifies synthesis_battery sentinel properties
(C-11: batteries deterministic, LLM synthesizes non-tool slots).

@decision DEC-TEST-BATTERY-COVERAGE-001
@title C-3 coverage test asserts no orphaned dossier slots; synthesis sentinel guarded
@status accepted
@rationale Reviewer round 2 (Blocker 1): the original Round 1 implementation left
    CAPABILITY, TARGETING, MOTIVATION, DENIAL, and PREDICTIONS without battery
    coverage because Battery.target_slot was singular. The C-3 acceptance test below
    was the missing proof. With the multi-slot fix (target_slots tuple) and
    synthesis_battery sentinel, all 9 slots are covered. This test locks the invariant
    so regressions are caught immediately.
"""

from __future__ import annotations

from adversary_pursuit.agent.battery_registry import (
    _SYNTHESIS_TRIGGER_THRESHOLD,
    DEFAULT_BATTERIES,
    dispatch_batteries,
)
from adversary_pursuit.dossier.slot_inference import DossierState, SlotState
from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus

# ---------------------------------------------------------------------------
# C-3 acceptance: every slot has ≥1 battery
# ---------------------------------------------------------------------------


def test_every_dossier_slot_has_coverage():
    """C-3 acceptance: every dossier slot is covered by ≥1 battery in DEFAULT_BATTERIES.

    A slot is 'covered' if at least one Battery in DEFAULT_BATTERIES lists it in
    its target_slots tuple. This includes the synthesis_battery sentinel which covers
    MOTIVATION, DENIAL, and PREDICTIONS via LLM synthesis (C-11).
    """
    covered: set[DossierSlotName] = set()
    for battery in DEFAULT_BATTERIES.values():
        covered.update(battery.target_slots)

    uncovered = set(DossierSlotName) - covered
    assert not uncovered, (
        f"C-3 violation: these dossier slots have no battery coverage: "
        f"{[s.value for s in uncovered]}. "
        "Add a battery entry or extend an existing battery's target_slots."
    )


def test_all_nine_slots_covered():
    """All 9 DossierSlotName values must appear in the coverage set."""
    covered: set[DossierSlotName] = set()
    for battery in DEFAULT_BATTERIES.values():
        covered.update(battery.target_slots)
    assert len(covered) == 9, (
        f"Expected 9 slots covered; got {len(covered)}: {[s.value for s in covered]}"
    )


# ---------------------------------------------------------------------------
# Multi-slot battery properties (reputation and behavioral cross-cutting)
# ---------------------------------------------------------------------------


def test_reputation_battery_covers_ttps_and_capability():
    """reputation_battery must cover both TTPS and CAPABILITY (C-3 cross-cutting)."""
    battery = DEFAULT_BATTERIES["reputation_battery"]
    assert DossierSlotName.TTPS in battery.target_slots
    assert DossierSlotName.CAPABILITY in battery.target_slots


def test_behavioral_battery_covers_timing_and_targeting():
    """behavioral_battery must cover both TIMING and TARGETING (C-3 cross-cutting)."""
    battery = DEFAULT_BATTERIES["behavioral_battery"]
    assert DossierSlotName.TIMING in battery.target_slots
    assert DossierSlotName.TARGETING in battery.target_slots


# ---------------------------------------------------------------------------
# synthesis_battery sentinel invariants (C-11)
# ---------------------------------------------------------------------------


def test_synthesis_battery_present():
    """synthesis_battery must exist in DEFAULT_BATTERIES."""
    assert "synthesis_battery" in DEFAULT_BATTERIES


def test_synthesis_battery_has_empty_tools():
    """synthesis_battery sentinel has tools=() — it is NOT a tool dispatcher (C-11).

    Any code path that iterates battery.tools for tool calls must first check
    tools == () and route to LLM synthesis instead. This test enforces that
    contract at the registry level.
    """
    battery = DEFAULT_BATTERIES["synthesis_battery"]
    assert battery.tools == (), (
        "synthesis_battery.tools must be () — it dispatches LLM synthesis, "
        "not tool calls. A non-empty tools tuple would cause dispatch code to "
        "attempt tool calls for LLM-only slots (C-11 violation)."
    )


def test_synthesis_battery_covers_motivation_denial_predictions():
    """synthesis_battery covers the 3 LLM-synthesised slots."""
    battery = DEFAULT_BATTERIES["synthesis_battery"]
    assert DossierSlotName.MOTIVATION in battery.target_slots
    assert DossierSlotName.DENIAL in battery.target_slots
    assert DossierSlotName.PREDICTIONS in battery.target_slots


def test_synthesis_battery_not_dispatched_without_threshold():
    """synthesis_battery must NOT be dispatched when tool-driven slots < threshold."""
    # dossier_state=None means 0 filled slots < threshold
    batteries = dispatch_batteries("domain-name", None)
    names = {b.name for b in batteries}
    assert "synthesis_battery" not in names, (
        "synthesis_battery must not dispatch without sufficient tool-driven evidence "
        f"(threshold={_SYNTHESIS_TRIGGER_THRESHOLD})"
    )


def test_synthesis_battery_not_dispatched_below_threshold():
    """synthesis_battery is withheld when filled tool slots < threshold (N=3)."""
    # Build a state with only 2 filled tool-driven slots
    slots = {
        slot: SlotState(
            name=slot,
            status=SlotStatus.FILLED
            if slot in (DossierSlotName.IDENTITY, DossierSlotName.INFRASTRUCTURE)
            else SlotStatus.EMPTY,
        )
        for slot in DossierSlotName
    }
    state = DossierState(slots=slots, total_sco_count=5)
    batteries = dispatch_batteries("domain-name", state)
    names = {b.name for b in batteries}
    assert "synthesis_battery" not in names, (
        "synthesis_battery must not dispatch with only 2 filled tool slots "
        f"(threshold={_SYNTHESIS_TRIGGER_THRESHOLD})"
    )


def test_synthesis_battery_dispatched_at_threshold():
    """synthesis_battery IS dispatched when ≥N tool-driven slots are filled."""
    # Fill exactly _SYNTHESIS_TRIGGER_THRESHOLD tool-driven slots
    tool_slots_to_fill = [
        DossierSlotName.IDENTITY,
        DossierSlotName.INFRASTRUCTURE,
        DossierSlotName.TTPS,
    ]
    assert len(tool_slots_to_fill) >= _SYNTHESIS_TRIGGER_THRESHOLD

    slots = {
        slot: SlotState(
            name=slot,
            status=SlotStatus.FILLED if slot in tool_slots_to_fill else SlotStatus.EMPTY,
        )
        for slot in DossierSlotName
    }
    state = DossierState(slots=slots, total_sco_count=10)
    batteries = dispatch_batteries("domain-name", state)
    names = {b.name for b in batteries}
    assert "synthesis_battery" in names, (
        f"synthesis_battery must dispatch when {_SYNTHESIS_TRIGGER_THRESHOLD} "
        "tool-driven slots are filled"
    )


# ---------------------------------------------------------------------------
# Multi-slot dispatch filtering: battery skipped only when ALL target_slots filled
# ---------------------------------------------------------------------------


def _make_state_with_filled(*filled_slots: DossierSlotName) -> DossierState:
    """Return a DossierState with exactly the named slots FILLED."""
    slots = {
        slot: SlotState(
            name=slot,
            status=SlotStatus.FILLED if slot in filled_slots else SlotStatus.EMPTY,
        )
        for slot in DossierSlotName
    }
    return DossierState(slots=slots, total_sco_count=3)


def test_reputation_battery_dispatches_when_only_ttps_filled():
    """reputation_battery is NOT skipped when only TTPS is filled — CAPABILITY still needs it."""
    state = _make_state_with_filled(DossierSlotName.TTPS)
    batteries = dispatch_batteries("domain-name", state)
    names = {b.name for b in batteries}
    assert "reputation_battery" in names, (
        "reputation_battery covers (TTPS, CAPABILITY); skipping it when only TTPS is "
        "filled would leave CAPABILITY without coverage (C-3 violation)."
    )


def test_reputation_battery_skipped_when_all_its_slots_filled():
    """reputation_battery IS skipped when BOTH TTPS and CAPABILITY are filled."""
    state = _make_state_with_filled(DossierSlotName.TTPS, DossierSlotName.CAPABILITY)
    batteries = dispatch_batteries("domain-name", state)
    names = {b.name for b in batteries}
    assert "reputation_battery" not in names, (
        "reputation_battery should be skipped when all its target_slots are filled."
    )


def test_behavioral_battery_dispatches_when_only_timing_filled():
    """behavioral_battery is NOT skipped when only TIMING is filled — TARGETING still needs it."""
    state = _make_state_with_filled(DossierSlotName.TIMING)
    batteries = dispatch_batteries("domain-name", state)
    names = {b.name for b in batteries}
    assert "behavioral_battery" in names, (
        "behavioral_battery covers (TIMING, TARGETING); skipping it when only TIMING is "
        "filled would leave TARGETING without coverage (C-3 violation)."
    )


def test_behavioral_battery_skipped_when_all_its_slots_filled():
    """behavioral_battery IS skipped when BOTH TIMING and TARGETING are filled."""
    state = _make_state_with_filled(DossierSlotName.TIMING, DossierSlotName.TARGETING)
    batteries = dispatch_batteries("domain-name", state)
    names = {b.name for b in batteries}
    assert "behavioral_battery" not in names, (
        "behavioral_battery should be skipped when all its target_slots are filled."
    )
