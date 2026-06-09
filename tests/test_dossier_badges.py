"""Tests for dossier_badges.py and BadgeMetric enum extension (M-7).

Stage C tests covering:
- Five new BadgeMetric enum values are present with correct string keys
- DOSSIER_BADGES list: 5 entries with correct ids/rarities/thresholds
- build_dossier_stats() with None dossier_state returns zeroed dict
- build_dossier_stats() with stubbed DossierState computes correct counts
- _DEFAULT_BADGES now has 15 entries (10 original + 5 new)
- Badge manager check_all() correctly awards dossier badges given dossier stats

@decision DEC-TEST-M7-BADGE-001
@title Test suite for dossier_badges module and BadgeMetric enum extension
@status accepted
@rationale Covers the five new badge specs (DEC-M7-BADGE-001..005), the build_dossier_stats
           helper, and verifies _DEFAULT_BADGES counts 15 after the M-7 splice
           (DEC-M7-BADGE-006). Compound-interaction test exercises BadgeManager.check_all()
           with real dossier stats to confirm end-to-end badge award.
           No external services used; all stubs are internal state factories
           (SimpleNamespace objects with the .status/.slots interface required by
           build_dossier_stats). No mocks are used.
"""

from __future__ import annotations

from types import SimpleNamespace

from adversary_pursuit.gamification.badges import (
    _DEFAULT_BADGES,
    BadgeMetric,
    BadgeRarity,
)
from adversary_pursuit.gamification.dossier_badges import (
    DOSSIER_BADGES,
    build_dossier_stats,
)

# ---------------------------------------------------------------------------
# Slot/prediction stub factories
# These are SimpleNamespace objects — not mocks — that satisfy the
# .status attribute interface required by build_dossier_stats().
# The real DossierSlotName enum is imported from the live package.
# ---------------------------------------------------------------------------


def _make_slot(status_value: str = "empty") -> SimpleNamespace:
    """Create a minimal slot stub with .status attribute."""
    from adversary_pursuit.dossier.slots import SlotStatus

    return SimpleNamespace(status=SlotStatus(status_value))


def _make_dossier_state(
    filled: list[str] | None = None,
    partial: list[str] | None = None,
) -> SimpleNamespace:
    """Create a minimal DossierState stub using real DossierSlotName enum keys."""
    from adversary_pursuit.dossier.slots import DossierSlotName

    filled = filled or []
    partial = partial or []

    slots: dict = {}
    for slot_name in DossierSlotName:
        if slot_name.value in filled:
            slots[slot_name] = _make_slot("filled")
        elif slot_name.value in partial:
            slots[slot_name] = _make_slot("partial")
        else:
            slots[slot_name] = _make_slot("empty")

    return SimpleNamespace(slots=slots)


def _make_prediction(status: str) -> SimpleNamespace:
    return SimpleNamespace(status=status)


# ---------------------------------------------------------------------------
# Stage C1: BadgeMetric enum extension (DEC-M7-BADGE-001..005)
# ---------------------------------------------------------------------------


class TestBadgeMetricExtension:
    """Five new DOSSIER_* enum values present with correct string keys."""

    def test_dossier_slots_filled_value(self) -> None:
        assert BadgeMetric.DOSSIER_SLOTS_FILLED.value == "dossier_slots_filled"

    def test_dossier_identity_first_value(self) -> None:
        assert BadgeMetric.DOSSIER_IDENTITY_FIRST.value == "dossier_identity_first"

    def test_dossier_predictions_validated_value(self) -> None:
        assert BadgeMetric.DOSSIER_PREDICTIONS_VALIDATED.value == "dossier_predictions_validated"

    def test_dossier_predictions_falsified_value(self) -> None:
        assert BadgeMetric.DOSSIER_PREDICTIONS_FALSIFIED.value == "dossier_predictions_falsified"

    def test_dossier_denial_filled_value(self) -> None:
        assert BadgeMetric.DOSSIER_DENIAL_FILLED.value == "dossier_denial_filled"

    def test_all_five_new_values_in_enum(self) -> None:
        new_values = {
            "dossier_slots_filled",
            "dossier_identity_first",
            "dossier_predictions_validated",
            "dossier_predictions_falsified",
            "dossier_denial_filled",
        }
        enum_values = {m.value for m in BadgeMetric}
        assert new_values.issubset(enum_values)


# ---------------------------------------------------------------------------
# Stage C2: DOSSIER_BADGES list (DEC-M7-BADGE-001..005)
# ---------------------------------------------------------------------------


class TestDossierBadgesList:
    """Five badge instances with correct ids, rarities, thresholds, metrics."""

    def test_list_has_five_entries(self) -> None:
        assert len(DOSSIER_BADGES) == 5

    def test_badge_ids_are_unique(self) -> None:
        ids = [b.id for b in DOSSIER_BADGES]
        assert len(ids) == len(set(ids))

    def test_dossier_complete_badge_is_legendary(self) -> None:
        badge = next(b for b in DOSSIER_BADGES if b.id == "badge-dossier-complete")
        assert badge.rarity == BadgeRarity.LEGENDARY
        assert badge.metric == BadgeMetric.DOSSIER_SLOTS_FILLED
        assert badge.threshold == 9

    def test_identity_first_badge_is_rare(self) -> None:
        badge = next(b for b in DOSSIER_BADGES if b.id == "badge-identity-first")
        assert badge.rarity == BadgeRarity.RARE
        assert badge.metric == BadgeMetric.DOSSIER_IDENTITY_FIRST
        assert badge.threshold == 1

    def test_predictor_badge_is_uncommon(self) -> None:
        badge = next(b for b in DOSSIER_BADGES if b.id == "badge-predictor")
        assert badge.rarity == BadgeRarity.UNCOMMON
        assert badge.metric == BadgeMetric.DOSSIER_PREDICTIONS_VALIDATED
        assert badge.threshold == 3

    def test_skeptic_badge_is_uncommon(self) -> None:
        badge = next(b for b in DOSSIER_BADGES if b.id == "badge-skeptic")
        assert badge.rarity == BadgeRarity.UNCOMMON
        assert badge.metric == BadgeMetric.DOSSIER_PREDICTIONS_FALSIFIED
        assert badge.threshold == 3

    def test_deception_spotter_badge_is_rare(self) -> None:
        badge = next(b for b in DOSSIER_BADGES if b.id == "badge-deception-spotter")
        assert badge.rarity == BadgeRarity.RARE
        assert badge.metric == BadgeMetric.DOSSIER_DENIAL_FILLED
        assert badge.threshold == 1

    def test_all_badges_have_nonempty_descriptions(self) -> None:
        for badge in DOSSIER_BADGES:
            assert badge.description, f"Badge {badge.id} has empty description"


# ---------------------------------------------------------------------------
# Stage C3: _DEFAULT_BADGES count (DEC-M7-BADGE-006)
# ---------------------------------------------------------------------------


class TestDefaultBadgesCount:
    """_DEFAULT_BADGES must have 15 entries after the M-7 splice."""

    def test_default_badges_has_15_entries(self) -> None:
        assert len(_DEFAULT_BADGES) == 15, (
            f"Expected 15 badges (10 original + 5 M-7 dossier), got {len(_DEFAULT_BADGES)}. "
            f"IDs: {[b.id for b in _DEFAULT_BADGES]}"
        )

    def test_all_dossier_badge_ids_present_in_default(self) -> None:
        dossier_ids = {b.id for b in DOSSIER_BADGES}
        default_ids = {b.id for b in _DEFAULT_BADGES}
        assert dossier_ids.issubset(default_ids)

    def test_original_badge_ids_preserved(self) -> None:
        """Original 10 badges must be unchanged (DEC-M7-BADGE-006: additive only)."""
        expected_original = {
            "badge-first-blood",
            "badge-data-hoarder",
            "badge-pivot-master",
            "badge-century",
            "badge-grand-master",
            "badge-domain-hunter",
            "badge-ip-collector",
            "badge-note-taker",
            "badge-persistent",
            "badge-supreme-hunter",
        }
        default_ids = {b.id for b in _DEFAULT_BADGES}
        missing = expected_original - default_ids
        assert not missing, f"Original badge IDs missing from _DEFAULT_BADGES: {missing}"


# ---------------------------------------------------------------------------
# Stage C4: build_dossier_stats() — None dossier_state
# ---------------------------------------------------------------------------


class TestBuildDossierStatsNone:
    """build_dossier_stats(None, []) returns zeroed stats without raising."""

    def test_returns_dict(self) -> None:
        result = build_dossier_stats(None, [])
        assert isinstance(result, dict)

    def test_all_keys_present(self) -> None:
        result = build_dossier_stats(None, [])
        expected_keys = {
            "dossier_slots_filled",
            "dossier_identity_first",
            "dossier_predictions_validated",
            "dossier_predictions_falsified",
            "dossier_denial_filled",
        }
        assert expected_keys == set(result.keys())

    def test_all_values_zero(self) -> None:
        result = build_dossier_stats(None, [])
        for key, val in result.items():
            assert val == 0, f"Expected 0 for {key}, got {val}"


# ---------------------------------------------------------------------------
# Stage C5: build_dossier_stats() — with dossier state
# ---------------------------------------------------------------------------


class TestBuildDossierStatsWithState:
    """build_dossier_stats() computes correct counts from stub DossierState."""

    def test_filled_slot_count(self) -> None:
        state = _make_dossier_state(filled=["identity", "ttps", "infrastructure"])
        result = build_dossier_stats(state, [])
        assert result["dossier_slots_filled"] == 3

    def test_all_9_slots_filled(self) -> None:
        all_slots = [
            "identity",
            "ttps",
            "infrastructure",
            "timing",
            "targeting",
            "capability",
            "motivation",
            "predictions",
            "denial",
        ]
        state = _make_dossier_state(filled=all_slots)
        result = build_dossier_stats(state, [])
        assert result["dossier_slots_filled"] == 9

    def test_partial_slots_not_counted_as_filled(self) -> None:
        state = _make_dossier_state(filled=["identity"], partial=["ttps", "capability"])
        result = build_dossier_stats(state, [])
        assert result["dossier_slots_filled"] == 1

    def test_identity_first_flag_identity_only(self) -> None:
        """Identity FILLED, no other slots filled — identity_first = 1."""
        state = _make_dossier_state(filled=["identity"])
        result = build_dossier_stats(state, [])
        assert result["dossier_identity_first"] == 1

    def test_identity_first_flag_identity_plus_one_other(self) -> None:
        """Identity + exactly one other FILLED — still qualifies (DEC-M7-BADGE-007)."""
        state = _make_dossier_state(filled=["identity", "ttps"])
        result = build_dossier_stats(state, [])
        assert result["dossier_identity_first"] == 1

    def test_identity_first_flag_identity_plus_two_others(self) -> None:
        """Identity + two others FILLED — does NOT qualify (>= 3 total filled)."""
        state = _make_dossier_state(filled=["identity", "ttps", "infrastructure"])
        result = build_dossier_stats(state, [])
        assert result["dossier_identity_first"] == 0

    def test_identity_first_flag_identity_not_filled(self) -> None:
        state = _make_dossier_state(filled=["ttps"])
        result = build_dossier_stats(state, [])
        assert result["dossier_identity_first"] == 0

    def test_denial_filled_when_denial_slot_filled(self) -> None:
        state = _make_dossier_state(filled=["denial"])
        result = build_dossier_stats(state, [])
        assert result["dossier_denial_filled"] == 1

    def test_denial_not_filled_when_denial_slot_partial(self) -> None:
        state = _make_dossier_state(partial=["denial"])
        result = build_dossier_stats(state, [])
        assert result["dossier_denial_filled"] == 0

    def test_empty_dossier_all_zeros(self) -> None:
        state = _make_dossier_state()
        result = build_dossier_stats(state, [])
        for key, val in result.items():
            assert val == 0, f"Expected 0 for {key} with empty dossier, got {val}"


# ---------------------------------------------------------------------------
# Stage C6: build_dossier_stats() — prediction counts
# ---------------------------------------------------------------------------


class TestBuildDossierStatsPredictions:
    """build_dossier_stats() counts validated and falsified predictions."""

    def test_validated_predictions_counted(self) -> None:
        preds = [
            _make_prediction("validated"),
            _make_prediction("validated"),
            _make_prediction("validated"),
        ]
        result = build_dossier_stats(None, preds)
        assert result["dossier_predictions_validated"] == 3

    def test_falsified_predictions_counted(self) -> None:
        preds = [_make_prediction("falsified"), _make_prediction("falsified")]
        result = build_dossier_stats(None, preds)
        assert result["dossier_predictions_falsified"] == 2

    def test_pending_predictions_not_counted(self) -> None:
        preds = [_make_prediction("pending"), _make_prediction("active")]
        result = build_dossier_stats(None, preds)
        assert result["dossier_predictions_validated"] == 0
        assert result["dossier_predictions_falsified"] == 0

    def test_mixed_predictions(self) -> None:
        preds = [
            _make_prediction("validated"),
            _make_prediction("falsified"),
            _make_prediction("pending"),
            _make_prediction("validated"),
        ]
        result = build_dossier_stats(None, preds)
        assert result["dossier_predictions_validated"] == 2
        assert result["dossier_predictions_falsified"] == 1


# ---------------------------------------------------------------------------
# Stage C7: Compound interaction — BadgeManager awards dossier badges
# ---------------------------------------------------------------------------


class TestDossierBadgeCompoundInteraction:
    """End-to-end: BadgeManager.check_all() correctly awards dossier badges.

    This is the compound-interaction test: exercises real production sequence
    from dossier state through build_dossier_stats through BadgeManager.check_all()
    to verify badge award crossing module boundaries (dossier_badges +
    badges + BadgeManager).
    """

    def _make_manager(self):
        from adversary_pursuit.gamification.badges import BadgeManager

        return BadgeManager()  # uses _DEFAULT_BADGES (15 entries including M-7)

    def _base_stats(self) -> dict:
        return {
            "total_iocs": 0,
            "modules_used": 0,
            "total_score": 0,
            "days_active": 0,
            "unique_ioc_types": 0,
            "session_count": 0,
            "morning_hunts": 0,
        }

    def test_dossier_complete_badge_awarded_when_all_9_filled(self) -> None:
        all_slots = [
            "identity",
            "ttps",
            "infrastructure",
            "timing",
            "targeting",
            "capability",
            "motivation",
            "predictions",
            "denial",
        ]
        state = _make_dossier_state(filled=all_slots)
        stats = {**self._base_stats(), **build_dossier_stats(state, [])}
        manager = self._make_manager()
        awarded_ids = {b.id for b in manager.check_all(stats, already_awarded=set())}
        assert "badge-dossier-complete" in awarded_ids

    def test_predictor_badge_awarded_when_3_validated(self) -> None:
        preds = [_make_prediction("validated")] * 3
        stats = {**self._base_stats(), **build_dossier_stats(None, preds)}
        manager = self._make_manager()
        awarded_ids = {b.id for b in manager.check_all(stats, already_awarded=set())}
        assert "badge-predictor" in awarded_ids

    def test_skeptic_badge_awarded_when_3_falsified(self) -> None:
        preds = [_make_prediction("falsified")] * 3
        stats = {**self._base_stats(), **build_dossier_stats(None, preds)}
        manager = self._make_manager()
        awarded_ids = {b.id for b in manager.check_all(stats, already_awarded=set())}
        assert "badge-skeptic" in awarded_ids

    def test_deception_spotter_badge_awarded_when_denial_filled(self) -> None:
        state = _make_dossier_state(filled=["denial"])
        stats = {**self._base_stats(), **build_dossier_stats(state, [])}
        manager = self._make_manager()
        awarded_ids = {b.id for b in manager.check_all(stats, already_awarded=set())}
        assert "badge-deception-spotter" in awarded_ids

    def test_no_dossier_badges_awarded_for_empty_state(self) -> None:
        stats = {**self._base_stats(), **build_dossier_stats(None, [])}
        manager = self._make_manager()
        dossier_badge_ids = {b.id for b in DOSSIER_BADGES}
        awarded_ids = {b.id for b in manager.check_all(stats, already_awarded=set())}
        awarded_dossier = awarded_ids & dossier_badge_ids
        assert not awarded_dossier, f"No dossier badges should be awarded: {awarded_dossier}"
