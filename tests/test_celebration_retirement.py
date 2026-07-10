"""C-9-A: quiet celebration cadence — loud Achievement Unlocked panels retired.

@decision DEC-TEST-CELEBRATION-RETIREMENT-001
@title Tests verify quiet_celebrate/quiet_badge_earned methods and no ASCII-art boxes in TUI path
@status accepted
@rationale DEC-CELEBRATION-UNIFY-QUIET-001 retires loud Achievement Unlocked panels
           from the TUI chat path. Tests verify that quiet_celebrate() and
           quiet_badge_earned() return plain one-liner strings free of box-drawing
           characters (╔, ═══), and that _run_tui_chat source code contains no
           'Achievement Unlocked' string. Badge-earned phrase coverage for all 5
           rarities is verified via pick() as required by C-9-A.
"""

from __future__ import annotations

import inspect

import pytest

from adversary_pursuit.gamification.celebrations import CelebrationEngine
from adversary_pursuit.gamification.phrases import pick

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def engine() -> CelebrationEngine:
    return CelebrationEngine(bell_enabled=False)


# ---------------------------------------------------------------------------
# quiet_celebrate method exists and returns correct types
# ---------------------------------------------------------------------------


def test_quiet_celebrate_method_exists(engine: CelebrationEngine):
    assert callable(getattr(engine, "quiet_celebrate", None))


def test_quiet_celebrate_returns_string_for_nonzero_points(engine: CelebrationEngine):
    result = engine.quiet_celebrate("default", 100)
    assert isinstance(result, str)
    assert len(result) > 0


def test_quiet_celebrate_returns_none_for_zero_points(engine: CelebrationEngine):
    result = engine.quiet_celebrate("default", 0)
    assert result is None


def test_quiet_celebrate_character_voiced_hal9000(engine: CelebrationEngine):
    result = engine.quiet_celebrate("hal9000", 500)
    assert isinstance(result, str)
    assert len(result) > 0


def test_quiet_celebrate_no_ascii_box_characters(engine: CelebrationEngine):
    """quiet_celebrate must NOT produce ASCII art boxes (╔, ═══)."""
    result = engine.quiet_celebrate("default", 100)
    assert result is not None
    assert "═══" not in result, f"ASCII art box found in quiet_celebrate output: {result!r}"
    assert "╔" not in result, f"Box-drawing char found in quiet_celebrate output: {result!r}"


def test_quiet_celebrate_substitutes_points(engine: CelebrationEngine):
    """The {points} placeholder must be substituted in the returned string."""
    result = engine.quiet_celebrate("default", 250)
    assert result is not None
    assert "250" in result, f"Points value not substituted in: {result!r}"


# ---------------------------------------------------------------------------
# quiet_badge_earned method exists and returns correct types
# ---------------------------------------------------------------------------


def test_quiet_badge_earned_method_exists(engine: CelebrationEngine):
    assert callable(getattr(engine, "quiet_badge_earned", None))


def test_quiet_badge_earned_common(engine: CelebrationEngine):
    result = engine.quiet_badge_earned("default", "First Blood", "common", "🩸")
    assert isinstance(result, str)
    assert len(result) > 0


def test_quiet_badge_earned_legendary(engine: CelebrationEngine):
    result = engine.quiet_badge_earned("default", "Legendary Analyst", "legendary", "👑")
    assert isinstance(result, str)
    assert len(result) > 0


def test_quiet_badge_earned_includes_emoji_prefix(engine: CelebrationEngine):
    result = engine.quiet_badge_earned("default", "First Blood", "common", "🩸")
    assert "🩸" in result, f"Emoji prefix not in result: {result!r}"


def test_quiet_badge_earned_includes_badge_name(engine: CelebrationEngine):
    result = engine.quiet_badge_earned("default", "First Blood", "common", "🩸")
    assert "First Blood" in result, f"Badge name not in result: {result!r}"


def test_quiet_badge_earned_no_ascii_box_common(engine: CelebrationEngine):
    result = engine.quiet_badge_earned("default", "First Blood", "common", "🩸")
    assert "═══" not in result
    assert "╔" not in result


def test_quiet_badge_earned_no_ascii_box_legendary(engine: CelebrationEngine):
    result = engine.quiet_badge_earned("default", "Legendary Analyst", "legendary", "👑")
    assert "═══" not in result
    assert "╔" not in result


def test_quiet_badge_earned_empty_emoji(engine: CelebrationEngine):
    """quiet_badge_earned with no emoji still returns a non-empty string."""
    result = engine.quiet_badge_earned("default", "Silent Badge", "rare", "")
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# badge_earned phrases exist for all 5 rarities in PHRASES
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rarity", ["common", "uncommon", "rare", "epic", "legendary"])
def test_badge_earned_phrase_exists_in_phrases(rarity: str):
    """pick('default', 'badge_earned:<rarity>') must return a non-empty string."""
    result = pick("default", f"badge_earned:{rarity}")
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# C-9-A assertion: _run_tui_chat source has no 'Achievement Unlocked' text
# ---------------------------------------------------------------------------


def test_tui_path_has_no_achievement_unlocked_panel():
    """_run_tui_chat does not render Achievement Unlocked panels (C-9-A)."""
    import adversary_pursuit.agent.chat as chat_module

    source = inspect.getsource(chat_module._run_tui_chat)
    assert "Achievement Unlocked" not in source, (
        "Found 'Achievement Unlocked' in _run_tui_chat source — C-9-A violation. "
        "Loud panels must not appear in the TUI chat path."
    )
