"""Tests for character-driven refresh cadence (C-8).

@decision DEC-TEST-CHARACTER-REFRESH-CADENCE-001
@title Tests verify _REFRESH_HZ table completeness and LivePane.refresh_hz property
@status accepted
@rationale DEC-TUI-LIVE-PANE-001 specifies that each character maps to a Hz refresh
           rate: calm characters (hal9000, ninja) at 1 Hz, energetic (full_troll) at
           4 Hz, default at 2 Hz. Tests verify the lookup table values, LivePane
           property returns correct Hz on construction and after set_character(),
           and unknown characters fall back to the default 2.0 Hz without raising.
"""

from __future__ import annotations

from adversary_pursuit.agent.tui.events import EventBus
from adversary_pursuit.agent.tui.live_pane import _REFRESH_HZ, LivePane

# ---------------------------------------------------------------------------
# _REFRESH_HZ table values
# ---------------------------------------------------------------------------


def test_refresh_hz_hal9000():
    assert _REFRESH_HZ["hal9000"] == 1.0


def test_refresh_hz_ninja():
    assert _REFRESH_HZ["ninja"] == 1.0


def test_refresh_hz_full_troll():
    assert _REFRESH_HZ["full_troll"] == 4.0


def test_refresh_hz_default():
    assert _REFRESH_HZ["default"] == 2.0


def test_refresh_hz_sun_tzu():
    assert _REFRESH_HZ["sun_tzu"] == 2.0


def test_refresh_hz_deckard():
    assert _REFRESH_HZ["deckard"] == 2.0


def test_refresh_hz_bruce_lee():
    assert _REFRESH_HZ["bruce_lee"] == 2.0


def test_refresh_hz_bureaucrat():
    assert _REFRESH_HZ["bureaucrat"] == 2.0


def test_refresh_hz_chuck_norris():
    assert _REFRESH_HZ["chuck_norris"] == 2.0


def test_refresh_hz_bobby_hill():
    assert _REFRESH_HZ["bobby_hill"] == 2.0


def test_refresh_hz_table_has_twelve_characters():
    """The _REFRESH_HZ table must have exactly 12 character entries.

    Phase 18 Slice 7A: neuromancer added (3.0 Hz urgent pacing).
    Phase 18 Slice 5: columbo added.
    """
    assert len(_REFRESH_HZ) == 12


def test_refresh_hz_all_values_are_positive_floats():
    for char, hz in _REFRESH_HZ.items():
        assert isinstance(hz, float), f"Hz for {char!r} is not a float: {hz!r}"
        assert hz > 0, f"Hz for {char!r} must be positive: {hz}"


# ---------------------------------------------------------------------------
# LivePane.refresh_hz property
# ---------------------------------------------------------------------------


def test_live_pane_refresh_hz_hal9000_on_construction():
    bus = EventBus()
    pane = LivePane(bus=bus, mode_name="hal9000", model_display="test-model")
    assert pane.refresh_hz == 1.0


def test_live_pane_refresh_hz_full_troll_on_construction():
    bus = EventBus()
    pane = LivePane(bus=bus, mode_name="full_troll", model_display="test-model")
    assert pane.refresh_hz == 4.0


def test_live_pane_refresh_hz_default_on_construction():
    bus = EventBus()
    pane = LivePane(bus=bus, mode_name="default", model_display="test-model")
    assert pane.refresh_hz == 2.0


def test_live_pane_set_character_hal9000():
    bus = EventBus()
    pane = LivePane(bus=bus, mode_name="default", model_display="test-model")
    pane.set_character("hal9000")
    assert pane.refresh_hz == 1.0


def test_live_pane_set_character_full_troll():
    bus = EventBus()
    pane = LivePane(bus=bus, mode_name="default", model_display="test-model")
    pane.set_character("full_troll")
    assert pane.refresh_hz == 4.0


def test_live_pane_set_character_back_to_default():
    bus = EventBus()
    pane = LivePane(bus=bus, mode_name="full_troll", model_display="test-model")
    pane.set_character("default")
    assert pane.refresh_hz == 2.0


def test_live_pane_unknown_character_falls_back_to_default():
    """Unknown character name must not raise; falls back to 2.0 Hz."""
    bus = EventBus()
    pane = LivePane(bus=bus, mode_name="unknown_character_xyz", model_display="test-model")
    assert pane.refresh_hz == 2.0


def test_live_pane_set_unknown_character_falls_back_to_default():
    bus = EventBus()
    pane = LivePane(bus=bus, mode_name="default", model_display="test-model")
    pane.set_character("does_not_exist")
    assert pane.refresh_hz == 2.0
