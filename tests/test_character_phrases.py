"""Tests for Phase 18 Slice 5: phrases.py character phrase cache.

Covers:
- Every active character in DEFAULT_MODES has ≥3 phrases per core category
- Every active character has ≥1 phrase per required activity category
- pick() returns a string from the pool
- pick() falls back to default for unknown character
- pick() raises ValueError for unknown category
- drunken_master NOT in DEFAULT_MODES (retired)
- detective and the_computer present with valid LLMPersonaProfile

@decision DEC-TEST-PHRASES-001
@title Phrase-cache tests verify coverage, fallback ladder, and error contract
@status accepted
@rationale Three verification levels: (1) PHRASES dict completeness — every active
           character × core and activity category has the minimum phrase count;
           (2) pick() API contract — fallback ladder (char → default → FALLBACK),
           unknown category raises ValueError per Sacred Practice 5; (3) retirement
           gate — drunken_master absent from DEFAULT_MODES, archived key present.
           Parametrize over DEFAULT_MODES.keys() so new characters added in future
           slices are automatically tested without editing this file.
"""

from __future__ import annotations

import pytest

from adversary_pursuit.gamification.modes import DEFAULT_MODES
from adversary_pursuit.gamification.phrases import PHRASES, has_phrases, pick

# Core categories every active character must cover
CORE_CATEGORIES = ("greeting", "run_success", "run_fail", "score_celebration")

# Activity categories every active character must cover (at least 1 phrase each)
REQUIRED_ACTIVITY_CATEGORIES = (
    "activity:virustotal",
    "activity:whois",
    "activity:shodan",
    "activity:otx",
    "activity:threatfox",
    "activity:thinking",
    "activity:composing",
)


# ---------------------------------------------------------------------------
# Core category coverage — ≥3 phrases per character × core category
# ---------------------------------------------------------------------------


class TestCorePhraseCoverage:
    """Every active character in DEFAULT_MODES must have ≥3 phrases per core category."""

    @pytest.mark.parametrize("char_name", list(DEFAULT_MODES.keys()))
    @pytest.mark.parametrize("category", CORE_CATEGORIES)
    def test_three_phrases_per_core_category(self, char_name: str, category: str):
        """Each active character must have ≥3 phrases for each core category."""
        pool = PHRASES.get((char_name, category), ())
        assert len(pool) >= 3, (
            f"Character '{char_name}' has only {len(pool)} phrase(s) for '{category}' — need ≥3"
        )


# ---------------------------------------------------------------------------
# Activity category coverage — ≥1 phrase per character × activity category
# ---------------------------------------------------------------------------


class TestActivityPhraseCoverage:
    """Every active character must have ≥1 phrase per required activity category."""

    @pytest.mark.parametrize("char_name", list(DEFAULT_MODES.keys()))
    @pytest.mark.parametrize("category", REQUIRED_ACTIVITY_CATEGORIES)
    def test_one_phrase_per_activity_category(self, char_name: str, category: str):
        """Each active character must have ≥1 phrase for each activity category."""
        # Allow fallback to default — check combined coverage
        has_own = has_phrases(char_name, category)
        has_default = has_phrases("default", category)
        assert has_own or has_default, (
            f"Character '{char_name}' has no phrases for '{category}' "
            f"and neither does 'default' — no fallback available"
        )


# ---------------------------------------------------------------------------
# pick() API
# ---------------------------------------------------------------------------


class TestPickAPI:
    """pick() returns correct strings and handles fallback/error cases."""

    @pytest.mark.parametrize("char_name", list(DEFAULT_MODES.keys()))
    @pytest.mark.parametrize("category", CORE_CATEGORIES)
    def test_pick_returns_string(self, char_name: str, category: str):
        """pick(char, cat) returns a non-empty string."""
        result = pick(char_name, category)
        assert isinstance(result, str)
        assert result.strip()

    def test_pick_unknown_character_falls_back_to_default_greeting(self):
        """pick('unknown_char_xyz', 'greeting') falls back to default greeting pool."""
        result = pick("unknown_char_xyz", "greeting")
        assert isinstance(result, str)
        assert result.strip()
        # Result should be one of the default greeting phrases
        default_pool = {p.text for p in PHRASES[("default", "greeting")]}
        assert result in default_pool, (
            f"Expected fallback to default greeting pool, got: {result!r}"
        )

    def test_pick_unknown_category_raises_value_error(self):
        """pick(char, 'unknown_category_xyz') raises ValueError."""
        with pytest.raises(ValueError, match="Unknown phrase category"):
            pick("default", "unknown_category_xyz")

    def test_pick_unknown_category_error_includes_category_name(self):
        """ValueError message includes the unknown category name."""
        with pytest.raises(ValueError) as exc_info:
            pick("detective", "totally_bogus_cat")
        assert "totally_bogus_cat" in str(exc_info.value)

    def test_pick_activity_virustotal_returns_string_for_all_modes(self):
        """pick(char, 'activity:virustotal') works for all active modes."""
        for char_name in DEFAULT_MODES:
            result = pick(char_name, "activity:virustotal")
            assert isinstance(result, str)
            assert result.strip()

    def test_pick_score_celebration_contains_points_placeholder(self):
        """score_celebration phrases must contain {points} placeholder."""
        for char_name in DEFAULT_MODES:
            pool = PHRASES.get((char_name, "score_celebration"), ())
            if not pool:
                pool = PHRASES.get(("default", "score_celebration"), ())
            for phrase in pool:
                assert "{points}" in phrase.text, (
                    f"Character '{char_name}' score_celebration phrase missing "
                    f"{{points}} placeholder: {phrase.text!r}"
                )


# ---------------------------------------------------------------------------
# drunken_master compatibility
# ---------------------------------------------------------------------------


class TestDrunkenMasterDeprecated:
    """Historical phrases remain readable while the mode is retired."""

    def test_drunken_master_not_in_default_modes(self):
        assert "drunken_master" not in DEFAULT_MODES

    def test_drunken_master_phrases_exist(self):
        assert len(PHRASES[("drunken_master", "greeting")]) >= 3


# ---------------------------------------------------------------------------
# detective and the_computer presence and profile validity
# ---------------------------------------------------------------------------


class TestDeckardHal9000Presence:
    """detective and the_computer must be in DEFAULT_MODES with valid LLMPersonaProfile."""

    def test_detective_in_default_modes(self):
        """detective must be in DEFAULT_MODES."""
        assert "detective" in DEFAULT_MODES, "detective not found in DEFAULT_MODES"

    def test_the_computer_in_default_modes(self):
        """the_computer must be in DEFAULT_MODES."""
        assert "the_computer" in DEFAULT_MODES, "the_computer not found in DEFAULT_MODES"

    def test_detective_has_llm_profile(self):
        """detective must have a non-None LLMPersonaProfile."""
        assert DEFAULT_MODES["detective"].llm_profile is not None, (
            "detective.llm_profile is None — expected LLMPersonaProfile"
        )

    def test_the_computer_has_llm_profile(self):
        """the_computer must have a non-None LLMPersonaProfile."""
        assert DEFAULT_MODES["the_computer"].llm_profile is not None, (
            "the_computer.llm_profile is None — expected LLMPersonaProfile"
        )

    def test_detective_profile_fields_non_empty(self):
        """detective LLMPersonaProfile must have all required fields non-empty."""
        profile = DEFAULT_MODES["detective"].llm_profile
        assert profile.voice_summary
        assert profile.tone_registers
        assert profile.signature_phrases
        assert profile.fourth_wall_stance
        assert profile.dialect_cadence

    def test_the_computer_profile_fields_non_empty(self):
        """the_computer LLMPersonaProfile must have all required fields non-empty."""
        profile = DEFAULT_MODES["the_computer"].llm_profile
        assert profile.voice_summary
        assert profile.tone_registers
        assert profile.signature_phrases
        assert profile.fourth_wall_stance
        assert profile.dialect_cadence
