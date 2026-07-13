"""Tests for Phase 18 Slice 7A: neuromancer phrase coverage.

Mirrors test_character_phrases.py structure for neuromancer specifically.
Verifies that neuromancer has ≥1 phrase in every required category so the
fallback ladder never silently degrades to "default" voice for key surfaces.

Required categories tested:
- Core: greeting, run_success, run_fail, score_celebration (≥3 each)
- Activity: virustotal, whois, shodan, otx, threatfox, thinking, composing
- Battery: identity, infrastructure, reputation, payload, behavioral
- Yield: stop, focus, add, skip
- Badge: common, uncommon, rare, epic, legendary
- REPL verbs: help:tui_overview, status_intro, farewell,
              target_set:acknowledged, mode_switched, unknown_mode, unknown_verb

@decision DEC-TEST-PHRASES-NEUROMANCER-001
@title Neuromancer phrase coverage: ≥1 per required category
@status accepted
@rationale Mirrors the parametrized structure in test_character_phrases.py
           (DEC-TEST-PHRASES-001) for neuromancer specifically. pick() falls
           through to "default" for missing categories — which produces correct
           output for fallback paths but masks missing neuromancer voice. These
           tests enforce that neuromancer has OWN phrases in every required
           category so the second-person Gibson register is used consistently.
           Parametrize each family so adding new tools to the tool registry
           fails loudly here before reaching the reviewer.
"""

from __future__ import annotations

import pytest

from adversary_pursuit.gamification.phrases import PHRASES, has_phrases

# ---------------------------------------------------------------------------
# Category lists
# ---------------------------------------------------------------------------

CORE_CATEGORIES = [
    "greeting",
    "run_success",
    "run_fail",
    "score_celebration",
]

ACTIVITY_CATEGORIES = [
    "activity:virustotal",
    "activity:whois",
    "activity:shodan",
    "activity:otx",
    "activity:threatfox",
    "activity:thinking",
    "activity:composing",
]

BATTERY_CATEGORIES = [
    "battery:identity",
    "battery:infrastructure",
    "battery:reputation",
    "battery:payload",
    "battery:behavioral",
]

YIELD_CATEGORIES = [
    "yield:stop",
    "yield:focus",
    "yield:add",
    "yield:skip",
]

BADGE_CATEGORIES = [
    "badge_earned:common",
    "badge_earned:uncommon",
    "badge_earned:rare",
    "badge_earned:epic",
    "badge_earned:legendary",
]

REPL_VERB_CATEGORIES = [
    "help:tui_overview",
    "status_intro",
    "farewell",
    "target_set:acknowledged",
    "mode_switched",
    "unknown_mode",
    "unknown_verb",
]

CHARACTER = "neuromancer"


# ---------------------------------------------------------------------------
# Core categories — ≥3 phrases each (mirrors test_character_phrases.py)
# ---------------------------------------------------------------------------


class TestNeuromancerCorePhraseCoverage:
    """neuromancer must have ≥3 phrases per core category."""

    @pytest.mark.parametrize("category", CORE_CATEGORIES)
    def test_three_phrases_per_core_category(self, category: str) -> None:
        pool = PHRASES.get((CHARACTER, category), ())
        assert len(pool) >= 3, (
            f"neuromancer has only {len(pool)} phrase(s) for '{category}' — need ≥3"
        )


# ---------------------------------------------------------------------------
# Activity categories — ≥1 own phrase each
# ---------------------------------------------------------------------------


class TestNeuromancerActivityPhraseCoverage:
    """neuromancer must have ≥1 own phrase per required activity category."""

    @pytest.mark.parametrize("category", ACTIVITY_CATEGORIES)
    def test_own_phrase_per_activity_category(self, category: str) -> None:
        assert has_phrases(CHARACTER, category), (
            f"neuromancer has no own phrases for '{category}' — "
            f"add at least one to ensure Gibson voice is used"
        )


# ---------------------------------------------------------------------------
# Battery categories — ≥1 own phrase each
# ---------------------------------------------------------------------------


class TestNeuromancerBatteryPhraseCoverage:
    """neuromancer must have ≥1 own phrase per battery category."""

    @pytest.mark.parametrize("category", BATTERY_CATEGORIES)
    def test_own_phrase_per_battery_category(self, category: str) -> None:
        assert has_phrases(CHARACTER, category), f"neuromancer has no own phrases for '{category}'"


# ---------------------------------------------------------------------------
# Yield categories — ≥1 own phrase each
# ---------------------------------------------------------------------------


class TestNeuromancerYieldPhraseCoverage:
    """neuromancer must have ≥1 own phrase per yield category."""

    @pytest.mark.parametrize("category", YIELD_CATEGORIES)
    def test_own_phrase_per_yield_category(self, category: str) -> None:
        assert has_phrases(CHARACTER, category), f"neuromancer has no own phrases for '{category}'"


# ---------------------------------------------------------------------------
# Badge earned categories — ≥1 own phrase each
# ---------------------------------------------------------------------------


class TestNeuromancerBadgePhraseCoverage:
    """neuromancer must have ≥1 own phrase per badge_earned category."""

    @pytest.mark.parametrize("category", BADGE_CATEGORIES)
    def test_own_phrase_per_badge_category(self, category: str) -> None:
        assert has_phrases(CHARACTER, category), f"neuromancer has no own phrases for '{category}'"


# ---------------------------------------------------------------------------
# REPL verb categories — ≥1 own phrase each
# ---------------------------------------------------------------------------


class TestNeuromancerReplVerbPhraseCoverage:
    """neuromancer must have ≥1 own phrase per REPL verb category."""

    @pytest.mark.parametrize("category", REPL_VERB_CATEGORIES)
    def test_own_phrase_per_repl_verb_category(self, category: str) -> None:
        assert has_phrases(CHARACTER, category), (
            f"neuromancer has no own phrases for '{category}' — "
            f"Gibson voice will fall back to 'default' silently"
        )


# ---------------------------------------------------------------------------
# Placeholder validation
# ---------------------------------------------------------------------------


class TestNeuromancerPlaceholderValidity:
    """Phrases with format placeholders must be correctly formattable."""

    def test_score_celebration_has_points_placeholder(self) -> None:
        """All score_celebration phrases must have {points} placeholder."""
        pool = PHRASES.get((CHARACTER, "score_celebration"), ())
        assert pool, "neuromancer score_celebration pool is empty"
        for phrase in pool:
            assert "{points}" in phrase.text, (
                f"score_celebration phrase missing {{points}}: {phrase.text!r}"
            )

    def test_target_set_acknowledged_has_target_placeholder(self) -> None:
        """All target_set:acknowledged phrases must have {target} placeholder."""
        pool = PHRASES.get((CHARACTER, "target_set:acknowledged"), ())
        assert pool, "neuromancer target_set:acknowledged pool is empty"
        for phrase in pool:
            assert "{target}" in phrase.text, (
                f"target_set:acknowledged phrase missing {{target}}: {phrase.text!r}"
            )

    def test_unknown_mode_has_name_placeholder(self) -> None:
        """All unknown_mode phrases must have {name} placeholder."""
        pool = PHRASES.get((CHARACTER, "unknown_mode"), ())
        assert pool, "neuromancer unknown_mode pool is empty"
        for phrase in pool:
            assert "{name}" in phrase.text, f"unknown_mode phrase missing {{name}}: {phrase.text!r}"
