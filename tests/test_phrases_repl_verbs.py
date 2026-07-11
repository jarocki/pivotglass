"""Coverage: all characters have repl_verb phrase categories (DEC-PHRASES-REPL-VERBS-001).

Verifies every character in DEFAULT_MODES has at least one phrase per new
category family introduced in Slice 6L:
  - help:tui_overview
  - status_intro
  - farewell
  - target_set:acknowledged  (must contain {target} placeholder)
  - mode_switched
  - unknown_mode              (must contain {name} placeholder)
  - unknown_verb

@decision DEC-TEST-PHRASES-REPL-VERBS-001
@title Tests verify every character × repl_verb category has ≥1 phrase
@status accepted
@rationale Mirrors test_phrases_battery_yield.py pattern (DEC-TEST-PHRASES-BATTERY-YIELD-001).
           Parametrised so new characters added to DEFAULT_MODES automatically get
           coverage without test changes. Spot-checks template placeholders in
           target_set:acknowledged ({target}) and unknown_mode ({name}) so dispatch
           can safely call .format(target=...) and .format(name=...) on every phrase.
"""

from __future__ import annotations

import pytest

from adversary_pursuit.gamification.modes import DEFAULT_MODES
from adversary_pursuit.gamification.phrases import pick

# All active characters
ALL_CHARACTERS = list(DEFAULT_MODES.keys())

# New category families for Slice 6L
REPL_VERB_SINGLETON_CATEGORIES = [
    "status_intro",
    "farewell",
    "mode_switched",
    "unknown_mode",
    "unknown_verb",
]


# ---------------------------------------------------------------------------
# Every character has a phrase for each singleton category
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("character", ALL_CHARACTERS)
@pytest.mark.parametrize("category", REPL_VERB_SINGLETON_CATEGORIES)
def test_repl_verb_singleton_phrase_exists(character: str, category: str):
    """pick(char, category) must return a non-empty string for every character."""
    result = pick(character, category)
    assert isinstance(result, str)
    assert len(result) > 0, f"Empty phrase for ({character!r}, {category!r})"


@pytest.mark.parametrize("character", ALL_CHARACTERS)
def test_help_tui_overview_phrase_exists(character: str):
    """pick(char, 'help:tui_overview') must return a non-empty multi-word string."""
    result = pick(character, "help:tui_overview")
    assert isinstance(result, str)
    assert len(result) > 0, f"Empty phrase for ({character!r}, 'help:tui_overview')"


@pytest.mark.parametrize("character", ALL_CHARACTERS)
def test_target_set_acknowledged_phrase_exists(character: str):
    """pick(char, 'target_set:acknowledged') must return a non-empty string."""
    result = pick(character, "target_set:acknowledged")
    assert isinstance(result, str)
    assert len(result) > 0, f"Empty phrase for ({character!r}, 'target_set:acknowledged')"


# ---------------------------------------------------------------------------
# Template placeholder checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("character", ALL_CHARACTERS)
def test_target_set_acknowledged_has_target_placeholder(character: str):
    """Every target_set:acknowledged phrase must have a {target} placeholder.

    dispatch_repl_verb calls phrase.format(target=...) so every phrase in this
    category must be a valid format string with {target}.
    """
    from adversary_pursuit.gamification.phrases import PHRASES, _weighted_choice

    # Check all phrases for this character (or default fallback)
    pool = PHRASES.get((character, "target_set:acknowledged")) or PHRASES.get(
        ("default", "target_set:acknowledged")
    )
    assert pool, f"No phrases found for ({character!r}, 'target_set:acknowledged')"
    for phrase in pool:
        # Must be formattable with target= without raising KeyError
        try:
            rendered = phrase.text.format(target="test.example.com")
        except KeyError as exc:
            pytest.fail(
                f"Phrase {phrase.text!r} for ({character!r}, 'target_set:acknowledged') "
                f"is missing placeholder: {exc}"
            )
        assert "test.example.com" in rendered, (
            f"Phrase {phrase.text!r} did not render target placeholder: {rendered!r}"
        )


@pytest.mark.parametrize("character", ALL_CHARACTERS)
def test_unknown_mode_has_name_placeholder(character: str):
    """Every unknown_mode phrase must have a {name} placeholder.

    dispatch_repl_verb calls phrase.format(name=...) so every phrase in this
    category must be a valid format string with {name}.
    """
    from adversary_pursuit.gamification.phrases import PHRASES

    pool = PHRASES.get((character, "unknown_mode")) or PHRASES.get(("default", "unknown_mode"))
    assert pool, f"No phrases found for ({character!r}, 'unknown_mode')"
    for phrase in pool:
        try:
            rendered = phrase.text.format(name="xyzzy")
        except KeyError as exc:
            pytest.fail(
                f"Phrase {phrase.text!r} for ({character!r}, 'unknown_mode') "
                f"is missing placeholder: {exc}"
            )
        assert "xyzzy" in rendered, (
            f"Phrase {phrase.text!r} did not render name placeholder: {rendered!r}"
        )


# ---------------------------------------------------------------------------
# Spot-checks for specific characters
# ---------------------------------------------------------------------------


def test_default_farewell_is_non_empty():
    result = pick("default", "farewell")
    assert isinstance(result, str) and len(result) > 0


def test_hal9000_farewell_mentions_dave():
    from adversary_pursuit.gamification.phrases import PHRASES

    pool = PHRASES.get(("hal9000", "farewell"))
    assert pool, "hal9000 farewell phrases missing"
    # At least one phrase should mention Dave
    texts = [p.text for p in pool]
    assert any("Dave" in t or "dave" in t for t in texts), (
        f"hal9000 farewell phrases don't mention Dave: {texts}"
    )


def test_hal9000_target_set_acknowledged_has_dave():
    from adversary_pursuit.gamification.phrases import PHRASES

    pool = PHRASES.get(("hal9000", "target_set:acknowledged"))
    assert pool, "hal9000 target_set:acknowledged phrases missing"
    texts = [p.text for p in pool]
    assert any("Dave" in t or "dave" in t for t in texts), (
        f"hal9000 target_set:acknowledged doesn't mention Dave: {texts}"
    )


def test_hal9000_status_intro_has_dave():
    from adversary_pursuit.gamification.phrases import PHRASES

    pool = PHRASES.get(("hal9000", "status_intro"))
    assert pool, "hal9000 status_intro phrases missing"
    texts = [p.text for p in pool]
    assert any("Dave" in t or "dave" in t for t in texts), (
        f"hal9000 status_intro doesn't mention Dave: {texts}"
    )


def test_deckard_farewell_is_terse():
    """Deckard's farewell should be short (film-noir terse style)."""
    from adversary_pursuit.gamification.phrases import PHRASES

    pool = PHRASES.get(("deckard", "farewell"))
    assert pool, "deckard farewell phrases missing"
    # At least one phrase should be short (≤ 40 chars)
    assert any(len(p.text) <= 40 for p in pool), (  # noqa: PLR2004
        f"deckard farewell phrases are all too long: {[p.text for p in pool]}"
    )


def test_ninja_phrases_use_dim_markup():
    """Ninja zero-arg categories should use [dim]...[/dim] Rich markup."""
    from adversary_pursuit.gamification.phrases import PHRASES

    for cat in ["farewell", "status_intro"]:
        pool = PHRASES.get(("ninja", cat))
        assert pool, f"ninja {cat!r} phrases missing"
        texts = [p.text for p in pool]
        assert any("[dim]" in t for t in texts), (
            f"ninja {cat!r} phrases don't use [dim] markup: {texts}"
        )


def test_pick_target_set_acknowledged_is_formattable():
    """pick('default', 'target_set:acknowledged').format(target=...) must work."""
    phrase = pick("default", "target_set:acknowledged")
    rendered = phrase.format(target="8.8.8.8")
    assert "8.8.8.8" in rendered


def test_pick_unknown_mode_is_formattable():
    """pick('default', 'unknown_mode').format(name=...) must work."""
    phrase = pick("default", "unknown_mode")
    rendered = phrase.format(name="badmode")
    assert "badmode" in rendered
