"""Tests for slot-fill amplitude tiers (C-7).

@decision DEC-TEST-SLOT-FILL-AMPLITUDE-001
@title Tests verify weight_tier returns correct band for all 9 dossier slots
@status accepted
@rationale DEC-SLOT-FILL-AMPLITUDE-001 defines high/mid/low tiers keyed on
           SLOT_WEIGHTS values. Tests parametrize over all 9 DossierSlotName
           members to ensure no slot is missing from the tier table and that
           transitions from EMPTY to FILLED are reflected in the rendered strip.
"""

from __future__ import annotations

import pytest

from adversary_pursuit.dossier.slot_glyphs import (
    SLOT_ORDER,
    render_slot_strip,
    weight_tier,
)
from adversary_pursuit.dossier.slot_inference import DossierState, SlotState
from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_state(status: SlotStatus) -> DossierState:
    slots = {slot: SlotState(name=slot, status=status) for slot in DossierSlotName}
    return DossierState(slots=slots, total_sco_count=0)


def _make_state_with_slot(slot_name: DossierSlotName, status: SlotStatus) -> DossierState:
    """Build a DossierState with one slot set to a specific status; rest are EMPTY."""
    slots = {
        slot: SlotState(
            name=slot,
            status=status if slot == slot_name else SlotStatus.EMPTY,
        )
        for slot in DossierSlotName
    }
    return DossierState(slots=slots, total_sco_count=0)


# ---------------------------------------------------------------------------
# High-weight slots
# ---------------------------------------------------------------------------


def test_weight_tier_identity_is_high():
    assert weight_tier(DossierSlotName.IDENTITY) == "high"


def test_weight_tier_predictions_is_high():
    assert weight_tier(DossierSlotName.PREDICTIONS) == "high"


# ---------------------------------------------------------------------------
# Mid-weight slots
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "slot_name",
    [
        DossierSlotName.CAPABILITY,
        DossierSlotName.TTPS,
        DossierSlotName.MOTIVATION,
        DossierSlotName.TARGETING,
        DossierSlotName.DENIAL,
    ],
)
def test_weight_tier_mid_slots(slot_name: DossierSlotName):
    assert weight_tier(slot_name) == "mid"


# ---------------------------------------------------------------------------
# Low-weight slots
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "slot_name",
    [
        DossierSlotName.INFRASTRUCTURE,
        DossierSlotName.TIMING,
    ],
)
def test_weight_tier_low_slots(slot_name: DossierSlotName):
    assert weight_tier(slot_name) == "low"


# ---------------------------------------------------------------------------
# All 9 slots have a valid weight_tier
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slot_name", list(DossierSlotName))
def test_all_slots_have_valid_weight_tier(slot_name: DossierSlotName):
    """Every DossierSlotName must return a recognized tier string."""
    tier = weight_tier(slot_name)
    assert tier in {"high", "mid", "low"}


# ---------------------------------------------------------------------------
# Glyph values in rendered strip
# ---------------------------------------------------------------------------


def test_strip_shows_filled_glyph_for_filled_status():
    state = _make_state(SlotStatus.FILLED)
    strip = render_slot_strip(state)
    for glyph in strip.split(" "):
        assert glyph == "▮"


def test_strip_shows_partial_glyph_for_partial_status():
    state = _make_state(SlotStatus.PARTIAL)
    strip = render_slot_strip(state)
    for glyph in strip.split(" "):
        assert glyph == "▪"


# ---------------------------------------------------------------------------
# Compound integration: IDENTITY transition EMPTY → FILLED
# ---------------------------------------------------------------------------


def test_identity_slot_transition_empty_to_filled():
    """Before: render shows · for IDENTITY position. After: shows ▮."""
    identity_index = SLOT_ORDER.index(DossierSlotName.IDENTITY)

    # Before: all empty
    state_before = _make_state(SlotStatus.EMPTY)
    glyphs_before = render_slot_strip(state_before).split(" ")
    assert glyphs_before[identity_index] == "·"

    # After: IDENTITY is FILLED, others remain EMPTY
    state_after = _make_state_with_slot(DossierSlotName.IDENTITY, SlotStatus.FILLED)
    glyphs_after = render_slot_strip(state_after).split(" ")
    assert glyphs_after[identity_index] == "▮"

    # Non-IDENTITY slots still empty
    for i, slot in enumerate(SLOT_ORDER):
        if slot != DossierSlotName.IDENTITY:
            assert glyphs_after[i] == "·", f"Slot {slot} should still be empty"
