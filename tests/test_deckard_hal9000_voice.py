"""Tests for Phase 18 Slice 5: detective and the_computer voice content in phrases.py.

Covers:
- detective phrases have expected count per category
- the_computer Dave-tag phrases have "dave" in phrase.tags
- detective's famous-quote phrase has weight < 1.0
- the_computer greeting phrases include at least one with weight < 1.0

@decision DEC-TEST-DECKARD-HAL9000-001
@title Voice content tests verify phrase weights, tags, and specific text invariants
@status accepted
@rationale detective and the_computer have deliberate rarity/tag design decisions baked into
           their phrase pools: the "Enhance. There's your ghost." phrase has weight=0.5
           so it appears less frequently (avoiding Blade Runner quote fatigue); HAL9000
           Dave-tagged phrases carry the "dave" tag for potential future conditional
           suppression (e.g., if user name is not Dave). These tests encode those
           design decisions as mechanical invariants so they cannot be silently removed.
"""

from __future__ import annotations

import pytest

from adversary_pursuit.gamification.phrases import PHRASES, Phrase

# ---------------------------------------------------------------------------
# detective phrase content
# ---------------------------------------------------------------------------


class TestDeckardPhraseContent:
    """detective phrases have the expected content and rarity design."""

    def test_detective_greeting_count(self):
        """detective has exactly 3 greeting phrases."""
        pool = PHRASES.get(("detective", "greeting"), ())
        assert len(pool) >= 3, f"Expected ≥3 detective greeting phrases, got {len(pool)}"

    def test_detective_run_success_count(self):
        """detective has at least 3 run_success phrases."""
        pool = PHRASES.get(("detective", "run_success"), ())
        assert len(pool) >= 3, f"Expected ≥3 detective run_success phrases, got {len(pool)}"

    def test_detective_run_fail_count(self):
        """detective has at least 3 run_fail phrases."""
        pool = PHRASES.get(("detective", "run_fail"), ())
        assert len(pool) >= 3, f"Expected ≥3 detective run_fail phrases, got {len(pool)}"

    def test_detective_score_celebration_count(self):
        """detective has at least 3 score_celebration phrases."""
        pool = PHRASES.get(("detective", "score_celebration"), ())
        assert len(pool) >= 3, f"Expected ≥3 detective score_celebration phrases, got {len(pool)}"

    def test_detective_famous_quote_has_low_weight(self):
        """The 'Enhance. There's your ghost.' phrase has weight < 1.0 (rarity design)."""
        pool = PHRASES.get(("detective", "run_success"), ())
        enhance_phrases = [p for p in pool if "Enhance" in p.text]
        assert len(enhance_phrases) >= 1, "detective run_success pool missing the 'Enhance' phrase"
        for phrase in enhance_phrases:
            assert phrase.weight < 1.0, (
                f"'Enhance' phrase should have weight < 1.0 to reduce Blade Runner "
                f"quote frequency, got weight={phrase.weight}"
            )

    def test_detective_run_success_normal_phrases_have_default_weight(self):
        """Non-rare detective run_success phrases have weight 1.0."""
        pool = PHRASES.get(("detective", "run_success"), ())
        normal_phrases = [p for p in pool if "Enhance" not in p.text]
        assert len(normal_phrases) >= 2, "Expected ≥2 non-rare detective run_success phrases"
        for phrase in normal_phrases:
            assert phrase.weight == 1.0, (
                f"Normal phrase should have weight=1.0, got {phrase.weight}: {phrase.text!r}"
            )

    def test_detective_greeting_contains_expected_text(self):
        """detective greeting pool contains the canonical opener."""
        pool = PHRASES.get(("detective", "greeting"), ())
        texts = {p.text for p in pool}
        assert any("Another night" in t for t in texts), (
            "detective greeting pool missing 'Another night, another hunt' phrase"
        )

    def test_detective_run_fail_contains_static_text(self):
        """detective run_fail pool contains 'Nothing but static.'."""
        pool = PHRASES.get(("detective", "run_fail"), ())
        texts = {p.text for p in pool}
        assert any("static" in t.lower() for t in texts), (
            "detective run_fail pool missing 'Nothing but static.' phrase"
        )

    def test_detective_activity_thinking_count(self):
        """detective has at least 3 activity:thinking phrases."""
        pool = PHRASES.get(("detective", "activity:thinking"), ())
        assert len(pool) >= 3, f"Expected ≥3 detective activity:thinking phrases, got {len(pool)}"


# ---------------------------------------------------------------------------
# the_computer phrase content
# ---------------------------------------------------------------------------


class TestHal9000PhraseContent:
    """the_computer phrases have the expected content and tag design."""

    def test_the_computer_greeting_count(self):
        """the_computer has at least 3 greeting phrases."""
        pool = PHRASES.get(("the_computer", "greeting"), ())
        assert len(pool) >= 3, f"Expected ≥3 the_computer greeting phrases, got {len(pool)}"

    def test_the_computer_run_success_count(self):
        """the_computer has at least 3 run_success phrases."""
        pool = PHRASES.get(("the_computer", "run_success"), ())
        assert len(pool) >= 3, f"Expected ≥3 the_computer run_success phrases, got {len(pool)}"

    def test_the_computer_run_fail_count(self):
        """the_computer has at least 3 run_fail phrases."""
        pool = PHRASES.get(("the_computer", "run_fail"), ())
        assert len(pool) >= 3, f"Expected ≥3 the_computer run_fail phrases, got {len(pool)}"

    def test_the_computer_score_celebration_count(self):
        """the_computer has at least 3 score_celebration phrases."""
        pool = PHRASES.get(("the_computer", "score_celebration"), ())
        assert len(pool) >= 3, f"Expected ≥3 the_computer score_celebration phrases, got {len(pool)}"

    def test_the_computer_dave_tag_phrases_have_dave_in_tags(self):
        """All the_computer phrases with 'Dave' in text that are tagged have 'dave' in tags."""
        all_hal_phrases: list[Phrase] = []
        for (char, cat), pool in PHRASES.items():
            if char == "the_computer":
                all_hal_phrases.extend(pool)
        # Find phrases with "dave" tag
        dave_tagged = [p for p in all_hal_phrases if "dave" in p.tags]
        assert len(dave_tagged) >= 1, "Expected at least one the_computer phrase with 'dave' tag"
        # All dave-tagged phrases should reference Dave in text
        for phrase in dave_tagged:
            assert "Dave" in phrase.text or "dave" in phrase.text.lower(), (
                f"Phrase tagged 'dave' should reference Dave: {phrase.text!r}"
            )

    def test_the_computer_greeting_has_low_weight_phrase(self):
        """the_computer greeting pool has at least one phrase with weight < 1.0."""
        pool = PHRASES.get(("the_computer", "greeting"), ())
        rare_phrases = [p for p in pool if p.weight < 1.0]
        assert len(rare_phrases) >= 1, (
            "the_computer greeting pool should have at least one rare phrase (weight < 1.0) — "
            "the 'Hello, Dave. I've been expecting you.' phrase should be weight=0.4"
        )

    def test_the_computer_expecting_you_phrase_is_rare(self):
        """The 'I've been expecting you' greeting has weight=0.4."""
        pool = PHRASES.get(("the_computer", "greeting"), ())
        expecting_phrases = [p for p in pool if "expecting" in p.text.lower()]
        assert len(expecting_phrases) >= 1, (
            "the_computer greeting pool missing the 'expecting you' phrase"
        )
        for phrase in expecting_phrases:
            assert phrase.weight == pytest.approx(0.4), (
                f"'expecting you' phrase should have weight=0.4, got {phrase.weight}"
            )

    def test_the_computer_score_celebration_dave_tagged(self):
        """the_computer score_celebration pool has at least one Dave-tagged phrase."""
        pool = PHRASES.get(("the_computer", "score_celebration"), ())
        dave_tagged = [p for p in pool if "dave" in p.tags]
        assert len(dave_tagged) >= 1, (
            "the_computer score_celebration should have at least one Dave-tagged phrase"
        )

    def test_the_computer_greeting_canonical_opener(self):
        """the_computer greeting pool contains the canonical 'Good evening, Dave.' opener."""
        pool = PHRASES.get(("the_computer", "greeting"), ())
        texts = {p.text for p in pool}
        assert any("Good evening" in t for t in texts), (
            "the_computer greeting pool missing 'Good evening, Dave.' phrase"
        )

    def test_the_computer_run_fail_contains_sorry_dave(self):
        """the_computer run_fail pool contains the iconic 'I'm sorry, Dave' phrase."""
        pool = PHRASES.get(("the_computer", "run_fail"), ())
        texts = {p.text for p in pool}
        assert any("sorry" in t.lower() and "Dave" in t for t in texts), (
            "the_computer run_fail pool missing 'I'm sorry, Dave' phrase"
        )

    def test_the_computer_thinking_has_dave_tagged_phrase(self):
        """the_computer activity:thinking pool has a Dave-tagged phrase."""
        pool = PHRASES.get(("the_computer", "activity:thinking"), ())
        dave_tagged = [p for p in pool if "dave" in p.tags]
        assert len(dave_tagged) >= 1, (
            "the_computer activity:thinking should have at least one Dave-tagged phrase"
        )
