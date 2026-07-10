"""Tests for dossier/slot_glyphs.py — slot glyph mapping (C-6, C-7).

@decision DEC-TEST-SLOT-GLYPHS-001
@title Tests verify glyph vocabulary and weight-tier authority from slot_glyphs.py
@status accepted
@rationale slot_glyphs.py is the single authority for glyph vocabulary (DEC-SLOT-GLYPHS-001)
           and weight tier classification (DEC-SLOT-FILL-AMPLITUDE-001). Tests exercise
           all four glyph values, all three tier bands, SLOT_ORDER completeness, and
           render_slot_strip edge cases (None state, all-same-status states).
"""

from __future__ import annotations

from adversary_pursuit.dossier.slot_glyphs import (
    SLOT_ORDER,
    render_slot_strip,
    slot_to_glyph,
    weight_tier,
)
from adversary_pursuit.dossier.slot_inference import DossierState, SlotState
from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(status: SlotStatus) -> DossierState:
    slots = {slot: SlotState(name=slot, status=status) for slot in DossierSlotName}
    return DossierState(slots=slots, total_sco_count=0)


# ---------------------------------------------------------------------------
# slot_to_glyph
# ---------------------------------------------------------------------------


def test_glyph_empty():
    assert slot_to_glyph(SlotStatus.EMPTY) == "·"


def test_glyph_partial():
    assert slot_to_glyph(SlotStatus.PARTIAL) == "▪"


def test_glyph_filled():
    assert slot_to_glyph(SlotStatus.FILLED) == "▮"


def test_glyph_deferred():
    assert slot_to_glyph(SlotStatus.DEFERRED) == "∅"


# ---------------------------------------------------------------------------
# weight_tier
# ---------------------------------------------------------------------------


def test_weight_tier_identity_high():
    """IDENTITY weight is 5.0 — should be 'high'."""
    assert weight_tier(DossierSlotName.IDENTITY) == "high"


def test_weight_tier_predictions_high():
    """PREDICTIONS weight is 4.0 — should be 'high'."""
    assert weight_tier(DossierSlotName.PREDICTIONS) == "high"


def test_weight_tier_capability_mid():
    """CAPABILITY weight is 3.5 — should be 'mid'."""
    assert weight_tier(DossierSlotName.CAPABILITY) == "mid"


def test_weight_tier_ttps_mid():
    """TTPS weight is 3.0 — should be 'mid'."""
    assert weight_tier(DossierSlotName.TTPS) == "mid"


def test_weight_tier_infrastructure_low():
    """INFRASTRUCTURE weight is 2.0 — should be 'low'."""
    assert weight_tier(DossierSlotName.INFRASTRUCTURE) == "low"


def test_weight_tier_timing_low():
    """TIMING weight is 2.0 — should be 'low'."""
    assert weight_tier(DossierSlotName.TIMING) == "low"


# ---------------------------------------------------------------------------
# SLOT_ORDER completeness
# ---------------------------------------------------------------------------


def test_slot_order_has_nine_elements():
    assert len(SLOT_ORDER) == 9


def test_slot_order_covers_all_slot_names():
    assert set(SLOT_ORDER) == set(DossierSlotName)


# ---------------------------------------------------------------------------
# render_slot_strip
# ---------------------------------------------------------------------------


def test_render_strip_none_state():
    """None dossier state renders all-empty strip."""
    result = render_slot_strip(None)
    assert result == "· · · · · · · · ·"


def test_render_strip_all_empty():
    state = _make_state(SlotStatus.EMPTY)
    result = render_slot_strip(state)
    assert result == "· · · · · · · · ·"


def test_render_strip_all_filled():
    state = _make_state(SlotStatus.FILLED)
    result = render_slot_strip(state)
    assert result == "▮ ▮ ▮ ▮ ▮ ▮ ▮ ▮ ▮"


def test_render_strip_all_partial():
    state = _make_state(SlotStatus.PARTIAL)
    result = render_slot_strip(state)
    assert result == "▪ ▪ ▪ ▪ ▪ ▪ ▪ ▪ ▪"


def test_render_strip_all_deferred():
    state = _make_state(SlotStatus.DEFERRED)
    result = render_slot_strip(state)
    assert result == "∅ ∅ ∅ ∅ ∅ ∅ ∅ ∅ ∅"


def test_render_strip_nine_glyphs():
    """Output always has exactly 9 space-separated glyph characters."""
    state = _make_state(SlotStatus.EMPTY)
    glyphs = render_slot_strip(state).split(" ")
    assert len(glyphs) == 9
