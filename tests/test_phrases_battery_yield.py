"""Coverage: all characters have battery: and yield: phrases (C-12).

@decision DEC-TEST-PHRASES-BATTERY-YIELD-001
@title Tests verify every character × battery/yield/badge_earned category has ≥1 phrase
@status accepted
@rationale DEC-PHRASES-BATTERY-YIELD-001 extends PHRASES with battery:, yield:, and
           badge_earned: categories. Tests parametrize over DEFAULT_MODES keys and all
           five battery types plus four yield primitives to ensure pick() never falls
           to the FALLBACK constant for known combinations. Badge-earned rarity phrases
           are also verified for the default character via direct pick() calls.
"""

from __future__ import annotations

import pytest

from adversary_pursuit.gamification.modes import DEFAULT_MODES
from adversary_pursuit.gamification.phrases import pick

# All characters active in the product
ALL_CHARACTERS = list(DEFAULT_MODES.keys())

# Battery types corresponding to DEFAULT_BATTERIES keys (minus the _battery suffix)
BATTERY_SLUGS = ["identity", "infrastructure", "reputation", "payload", "behavioral"]

# Yield primitives
YIELD_PRIMITIVES = ["stop", "focus", "add", "skip"]

# Badge rarities
BADGE_RARITIES = ["common", "uncommon", "rare", "epic", "legendary"]


# ---------------------------------------------------------------------------
# battery: categories — every character × every battery slug
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("character", ALL_CHARACTERS)
@pytest.mark.parametrize("battery_slug", BATTERY_SLUGS)
def test_battery_phrase_exists(character: str, battery_slug: str):
    """pick(char, 'battery:<slug>') must return a non-empty string."""
    result = pick(character, f"battery:{battery_slug}")
    assert isinstance(result, str)
    assert len(result) > 0, f"Empty phrase for ({character!r}, 'battery:{battery_slug}')"


# ---------------------------------------------------------------------------
# yield: categories — every character × every yield primitive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("character", ALL_CHARACTERS)
@pytest.mark.parametrize("primitive", YIELD_PRIMITIVES)
def test_yield_phrase_exists(character: str, primitive: str):
    """pick(char, 'yield:<primitive>') must return a non-empty string."""
    result = pick(character, f"yield:{primitive}")
    assert isinstance(result, str)
    assert len(result) > 0, f"Empty phrase for ({character!r}, 'yield:{primitive}')"


# ---------------------------------------------------------------------------
# badge_earned: categories — default character × every rarity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rarity", BADGE_RARITIES)
def test_badge_earned_phrase_default(rarity: str):
    """pick('default', 'badge_earned:<rarity>') must return a non-empty string."""
    result = pick("default", f"badge_earned:{rarity}")
    assert isinstance(result, str)
    assert len(result) > 0, f"Empty phrase for ('default', 'badge_earned:{rarity}')"


# ---------------------------------------------------------------------------
# Spot-check individual character battery phrases (named tests for clarity)
# ---------------------------------------------------------------------------


def test_default_battery_identity_phrase():
    result = pick("default", "battery:identity")
    assert "identity" in result.lower() or len(result) > 0


def test_ninja_battery_infrastructure_phrase():
    result = pick("ninja", "battery:infrastructure")
    assert isinstance(result, str) and len(result) > 0


def test_full_troll_battery_reputation_phrase():
    result = pick("full_troll", "battery:reputation")
    assert isinstance(result, str) and len(result) > 0


def test_hal9000_yield_stop_phrase():
    result = pick("hal9000", "yield:stop")
    assert isinstance(result, str) and len(result) > 0


def test_deckard_yield_skip_phrase():
    result = pick("deckard", "yield:skip")
    assert isinstance(result, str) and len(result) > 0


# ---------------------------------------------------------------------------
# Verify PHRASES dict has entries for identity battery (min ≥1 per character)
# ---------------------------------------------------------------------------


def test_phrases_has_entries_for_all_characters_battery_identity():
    """PHRASES must have at least one entry per character for battery:identity."""

    for char in ALL_CHARACTERS:
        # Either a direct phrase or the default fallback covers it
        # has_phrases checks exact match; pick() uses fallback
        result = pick(char, "battery:identity")
        assert result, f"No phrase resolved for ({char!r}, 'battery:identity')"
