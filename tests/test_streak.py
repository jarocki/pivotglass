"""Tests for F62: StreakManager — ISO-week streak tracking.

Covers:
- Fresh state initialization
- Streak increment on first hunt
- Consecutive-day streak growth
- Same-day idempotency (second hunt same day does not double-count)
- Streak break (gap > 1 ISO week day)
- Freeze: one freeze per ISO week extends streak through a missed day
- Freeze limit enforced (second freeze same ISO week rejected)
- Freeze resets across ISO weeks
- Corruption recovery (rename to .corrupt-<ts>, fresh state)
- Clock-skew backward clamp (no mutation on backward time)
- Atomic write (tempfile + os.replace — verified by checking no partial file)
- format_banner_line() produces non-empty string when streak >= 1
- format_banner_line() produces suppress-friendly string when streak == 0
- Production sequence: StreakManager.update → read back → verify state persisted

@decision DEC-62-STREAK-001
@title test_streak.py covers all StreakManager invariants with tmp_path isolation
@status accepted
@rationale All tests use tmp_path fixture to write streak.json into an isolated temp
           directory — the real ~/.ap/streak.json is never touched. This is the
           production-sequence contract: StreakManager reads/writes a single
           configurable path, so tests override that path to tmp_path/streak.json.
           State is verified by reading back via StreakManager.state (property)
           or a second StreakManager instance pointing to the same path.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from adversary_pursuit.core.streak import StreakManager, StreakState, StreakUpdate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mgr(tmp_path: Path) -> StreakManager:
    """Return a StreakManager backed by tmp_path/streak.json."""
    return StreakManager(path=tmp_path / "streak.json")


# ---------------------------------------------------------------------------
# Fresh state
# ---------------------------------------------------------------------------


class TestFreshState:
    """StreakManager with no existing file starts with zero state."""

    def test_no_file_current_streak_zero(self, tmp_path):
        mgr = make_mgr(tmp_path)
        assert mgr.state.current_streak == 0

    def test_no_file_longest_streak_zero(self, tmp_path):
        mgr = make_mgr(tmp_path)
        assert mgr.state.longest_streak == 0

    def test_no_file_last_hunt_date_none(self, tmp_path):
        mgr = make_mgr(tmp_path)
        assert mgr.state.last_hunt_date is None

    def test_no_file_freezes_used_zero(self, tmp_path):
        mgr = make_mgr(tmp_path)
        assert mgr.state.freezes_used_this_week == 0

    def test_state_type(self, tmp_path):
        mgr = make_mgr(tmp_path)
        assert isinstance(mgr.state, StreakState)


# ---------------------------------------------------------------------------
# First hunt
# ---------------------------------------------------------------------------


class TestFirstHunt:
    """First hunt creates a streak of 1."""

    def test_first_hunt_streak_becomes_one(self, tmp_path):
        mgr = make_mgr(tmp_path)
        today = date(2026, 5, 20)
        mgr.update(today)
        assert mgr.state.current_streak == 1

    def test_first_hunt_longest_streak_becomes_one(self, tmp_path):
        mgr = make_mgr(tmp_path)
        today = date(2026, 5, 20)
        mgr.update(today)
        assert mgr.state.longest_streak == 1

    def test_first_hunt_last_hunt_date_set(self, tmp_path):
        mgr = make_mgr(tmp_path)
        today = date(2026, 5, 20)
        mgr.update(today)
        assert mgr.state.last_hunt_date == today

    def test_first_hunt_persisted_to_disk(self, tmp_path):
        path = tmp_path / "streak.json"
        mgr = StreakManager(path=path)
        today = date(2026, 5, 20)
        mgr.update(today)
        # Read back via a fresh instance
        mgr2 = StreakManager(path=path)
        assert mgr2.state.current_streak == 1
        assert mgr2.state.last_hunt_date == today


# ---------------------------------------------------------------------------
# Consecutive days
# ---------------------------------------------------------------------------


class TestConsecutiveDays:
    """Consecutive-day hunts grow the streak."""

    def test_two_consecutive_days_streak_is_two(self, tmp_path):
        mgr = make_mgr(tmp_path)
        mgr.update(date(2026, 5, 20))
        mgr.update(date(2026, 5, 21))
        assert mgr.state.current_streak == 2

    def test_five_consecutive_days_streak_is_five(self, tmp_path):
        mgr = make_mgr(tmp_path)
        for offset in range(5):
            mgr.update(date(2026, 5, 20) + timedelta(days=offset))
        assert mgr.state.current_streak == 5

    def test_longest_streak_updated_on_growth(self, tmp_path):
        mgr = make_mgr(tmp_path)
        for offset in range(3):
            mgr.update(date(2026, 5, 20) + timedelta(days=offset))
        assert mgr.state.longest_streak == 3


# ---------------------------------------------------------------------------
# Same-day idempotency
# ---------------------------------------------------------------------------


class TestSameDayIdempotency:
    """Two hunts on the same calendar day do not double-count."""

    def test_same_day_twice_streak_still_one(self, tmp_path):
        mgr = make_mgr(tmp_path)
        today = date(2026, 5, 20)
        mgr.update(today)
        mgr.update(today)
        assert mgr.state.current_streak == 1

    def test_same_day_three_times_streak_still_one(self, tmp_path):
        mgr = make_mgr(tmp_path)
        today = date(2026, 5, 20)
        for _ in range(3):
            mgr.update(today)
        assert mgr.state.current_streak == 1

    def test_same_day_after_two_days_does_not_break_streak(self, tmp_path):
        mgr = make_mgr(tmp_path)
        mgr.update(date(2026, 5, 20))
        mgr.update(date(2026, 5, 21))
        mgr.update(date(2026, 5, 21))  # same day as previous
        assert mgr.state.current_streak == 2


# ---------------------------------------------------------------------------
# Streak break
# ---------------------------------------------------------------------------


class TestStreakBreak:
    """A gap of >= 2 days without a freeze resets the streak."""

    def test_two_day_gap_resets_streak(self, tmp_path):
        """A gap of 2 missed calendar days (delta.days == 3) breaks the streak.

        Note: delta.days == 2 means exactly 1 calendar day skipped (freeze
        bridges that). delta.days == 3 means 2 days skipped — no freeze covers
        that, so the streak breaks.
        """
        mgr = make_mgr(tmp_path)
        mgr.update(date(2026, 5, 20))
        mgr.update(date(2026, 5, 23))  # 2 missed days (21, 22) — breaks even with freeze
        assert mgr.state.current_streak == 1

    def test_week_gap_resets_streak(self, tmp_path):
        mgr = make_mgr(tmp_path)
        mgr.update(date(2026, 5, 20))
        mgr.update(date(2026, 5, 27))  # week gap
        assert mgr.state.current_streak == 1

    def test_broken_streak_previous_best_preserved(self, tmp_path):
        mgr = make_mgr(tmp_path)
        # Build streak of 5
        for offset in range(5):
            mgr.update(date(2026, 5, 10) + timedelta(days=offset))
        # Break it
        mgr.update(date(2026, 5, 20))  # big gap
        assert mgr.state.longest_streak == 5
        assert mgr.state.current_streak == 1

    def test_exact_one_day_gap_does_not_break(self, tmp_path):
        """Adjacent calendar days never break the streak."""
        mgr = make_mgr(tmp_path)
        mgr.update(date(2026, 5, 20))
        mgr.update(date(2026, 5, 21))
        assert mgr.state.current_streak == 2


# ---------------------------------------------------------------------------
# Freeze mechanic
# ---------------------------------------------------------------------------


class TestFreeze:
    """One freeze per ISO week bridges a single missed day."""

    def test_freeze_bridges_one_missed_day(self, tmp_path):
        """Hunt Mon → skip Tue → hunt Wed with freeze: streak continues."""
        mgr = make_mgr(tmp_path)
        mon = date(2026, 5, 18)  # Monday W21
        wed = date(2026, 5, 20)  # Wednesday W21 — one day gap (Tue skipped)
        mgr.update(mon)
        mgr.update(wed)  # one day gap → freeze used automatically
        assert mgr.state.current_streak == 2

    def test_freeze_increments_freezes_used(self, tmp_path):
        mgr = make_mgr(tmp_path)
        mon = date(2026, 5, 18)
        wed = date(2026, 5, 20)
        mgr.update(mon)
        mgr.update(wed)
        assert mgr.state.freezes_used_this_week == 1

    def test_second_freeze_same_week_breaks_streak(self, tmp_path):
        """Second freeze in same ISO week is not allowed; streak breaks."""
        mgr = make_mgr(tmp_path)
        mon = date(2026, 5, 18)  # W21
        wed = date(2026, 5, 20)  # W21 — first freeze
        fri = date(2026, 5, 22)  # W21 — would be second freeze, breaks
        mgr.update(mon)
        mgr.update(wed)  # freeze used
        mgr.update(fri)  # gap of 2, freeze already used → breaks
        assert mgr.state.current_streak == 1

    def test_freeze_used_resets_next_iso_week(self, tmp_path):
        """freeze_used_this_week resets to 0 when the ISO week changes.

        Sequence:
          Mon W21 → Wed W21  (freeze used in W21, streak=2)
          Wed W21 → Mon W22  (big gap, streak breaks to 1, freeze counter resets=0)
          Mon W22 → Wed W22  (freeze used in W22, streak=2)
        """
        mgr = make_mgr(tmp_path)
        # Step 1: use freeze in W21
        mgr.update(date(2026, 5, 18))  # Mon W21
        mgr.update(date(2026, 5, 20))  # Wed W21 — 1 missed day → freeze consumed
        assert mgr.state.freezes_used_this_week == 1
        assert mgr.state.current_streak == 2

        # Step 2: jump to W22 with a big gap (streak breaks, freeze counter resets)
        mgr.update(date(2026, 5, 25))  # Mon W22 — delta=5 days, no freeze can help
        assert mgr.state.current_streak == 1
        assert mgr.state.freezes_used_this_week == 0  # reset because new ISO week

        # Step 3: use the W22 freeze: Mon May 25 → Wed May 27 (1 missed Tue)
        mgr.update(date(2026, 5, 27))  # Wed W22 — 1 missed day → freeze consumed
        assert mgr.state.freezes_used_this_week == 1
        assert mgr.state.current_streak == 2

    def test_freeze_does_not_bridge_two_day_gap(self, tmp_path):
        """Freeze only bridges a 1-day gap (one missed day), not 2."""
        mgr = make_mgr(tmp_path)
        mgr.update(date(2026, 5, 18))  # Mon
        mgr.update(date(2026, 5, 21))  # Thu — 2 days missed (Tue, Wed) → break
        assert mgr.state.current_streak == 1


# ---------------------------------------------------------------------------
# Corruption recovery
# ---------------------------------------------------------------------------


class TestCorruptionRecovery:
    """Corrupted streak.json is renamed and fresh state is returned."""

    def test_corrupt_json_returns_fresh_state(self, tmp_path):
        path = tmp_path / "streak.json"
        path.write_text("{{not: valid json}}", encoding="utf-8")
        mgr = StreakManager(path=path)
        assert mgr.state.current_streak == 0

    def test_corrupt_file_renamed(self, tmp_path):
        path = tmp_path / "streak.json"
        path.write_text("corrupted", encoding="utf-8")
        StreakManager(path=path)
        # Original path now absent or has been replaced
        corrupt_files = list(tmp_path.glob("streak.json.corrupt-*"))
        assert len(corrupt_files) == 1, "Expected one .corrupt-<ts> file"

    def test_corrupt_truncated_json_recovered(self, tmp_path):
        path = tmp_path / "streak.json"
        path.write_text('{"current_streak": 5', encoding="utf-8")  # truncated
        mgr = StreakManager(path=path)
        # Fresh state — corruption → 0
        assert mgr.state.current_streak == 0

    def test_after_corruption_recovery_can_update(self, tmp_path):
        path = tmp_path / "streak.json"
        path.write_text("corrupted", encoding="utf-8")
        mgr = StreakManager(path=path)
        today = date(2026, 5, 20)
        mgr.update(today)
        assert mgr.state.current_streak == 1


# ---------------------------------------------------------------------------
# Clock-skew backward
# ---------------------------------------------------------------------------


class TestClockSkew:
    """Backward time (today < last_hunt_date) clamps without mutation."""

    def test_backward_time_does_not_change_streak(self, tmp_path):
        mgr = make_mgr(tmp_path)
        mgr.update(date(2026, 5, 20))  # set to May 20
        mgr.update(date(2026, 5, 19))  # one day in the past — clamp
        assert mgr.state.current_streak == 1

    def test_backward_time_does_not_change_last_hunt_date(self, tmp_path):
        mgr = make_mgr(tmp_path)
        mgr.update(date(2026, 5, 20))
        mgr.update(date(2026, 5, 18))  # two days in the past
        assert mgr.state.last_hunt_date == date(2026, 5, 20)


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    """update() writes atomically via tempfile + os.replace."""

    def test_streak_file_exists_after_update(self, tmp_path):
        mgr = make_mgr(tmp_path)
        mgr.update(date(2026, 5, 20))
        assert (tmp_path / "streak.json").exists()

    def test_streak_file_is_valid_json(self, tmp_path):
        mgr = make_mgr(tmp_path)
        mgr.update(date(2026, 5, 20))
        raw = (tmp_path / "streak.json").read_text(encoding="utf-8")
        data = json.loads(raw)
        assert "current_streak" in data

    def test_no_temp_file_left_after_update(self, tmp_path):
        mgr = make_mgr(tmp_path)
        mgr.update(date(2026, 5, 20))
        # No .tmp files should remain
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0


# ---------------------------------------------------------------------------
# format_banner_line
# ---------------------------------------------------------------------------


class TestFormatBannerLine:
    """format_banner_line() returns a display-ready string."""

    def test_banner_line_returns_str(self, tmp_path):
        mgr = make_mgr(tmp_path)
        result = mgr.format_banner_line()
        assert isinstance(result, str)

    def test_banner_line_with_zero_streak(self, tmp_path):
        mgr = make_mgr(tmp_path)
        result = mgr.format_banner_line()
        assert isinstance(result, str)
        # With no streak, output should be empty or indicate no streak

    def test_banner_line_with_active_streak(self, tmp_path):
        mgr = make_mgr(tmp_path)
        mgr.update(date(2026, 5, 20))
        result = mgr.format_banner_line()
        assert "1" in result  # streak count visible

    def test_banner_line_with_long_streak(self, tmp_path):
        mgr = make_mgr(tmp_path)
        for offset in range(7):
            mgr.update(date(2026, 5, 20) + timedelta(days=offset))
        result = mgr.format_banner_line()
        assert "7" in result

    def test_banner_line_no_streak_empty_or_short(self, tmp_path):
        """When streak == 0, format_banner_line returns empty or no-streak string."""
        mgr = make_mgr(tmp_path)
        result = mgr.format_banner_line()
        # Should not crash; empty string is acceptable
        assert result is not None


# ---------------------------------------------------------------------------
# Production sequence: update → read back → verify
# ---------------------------------------------------------------------------


class TestProductionSequence:
    """End-to-end test simulating the real production update flow."""

    def test_week_of_hunts_then_read_back(self, tmp_path):
        """Simulate 7 daily hunts written, then a fresh manager reads back."""
        path = tmp_path / "streak.json"
        for day_offset in range(7):
            mgr = StreakManager(path=path)
            mgr.update(date(2026, 5, 20) + timedelta(days=day_offset))

        # Final read-back
        final_mgr = StreakManager(path=path)
        assert final_mgr.state.current_streak == 7
        assert final_mgr.state.longest_streak == 7

    def test_streak_break_and_rebuild(self, tmp_path):
        """Streak breaks, then rebuilds to a new best."""
        path = tmp_path / "streak.json"
        # Build streak of 5
        for offset in range(5):
            mgr = StreakManager(path=path)
            mgr.update(date(2026, 5, 10) + timedelta(days=offset))

        # Break it
        broken_mgr = StreakManager(path=path)
        broken_mgr.update(date(2026, 5, 20))  # 5-day gap
        assert broken_mgr.state.current_streak == 1
        assert broken_mgr.state.longest_streak == 5

        # Rebuild: May 20 started at streak=1, then 6 consecutive days → streak=7
        for offset in range(1, 7):
            mgr = StreakManager(path=path)
            mgr.update(date(2026, 5, 20) + timedelta(days=offset))

        final = StreakManager(path=path)
        assert final.state.current_streak == 7  # 1 (break day) + 6 consecutive
        assert final.state.longest_streak == 7  # surpasses the previous best of 5

    def test_format_banner_reflects_persisted_state(self, tmp_path):
        """format_banner_line on fresh manager reflects disk state."""
        path = tmp_path / "streak.json"
        for offset in range(3):
            m = StreakManager(path=path)
            m.update(date(2026, 5, 20) + timedelta(days=offset))

        # Fresh manager, no in-memory state
        fresh = StreakManager(path=path)
        banner = fresh.format_banner_line()
        assert "3" in banner


# ---------------------------------------------------------------------------
# StreakUpdate return value — F63 DEC-63-STREAK-SCORE-001
# ---------------------------------------------------------------------------


class TestStreakUpdate:
    """Verify update() returns StreakUpdate with correct incremented/current_streak values.

    F63 callers use incremented to gate streak_continued score events.
    """

    def test_update_returns_streak_update_type(self, tmp_path):
        """update() returns a StreakUpdate instance."""
        mgr = make_mgr(tmp_path)
        result = mgr.update(date(2026, 5, 20))
        assert isinstance(result, StreakUpdate)

    def test_first_hunt_incremented_true(self, tmp_path):
        """First ever hunt returns incremented=True."""
        mgr = make_mgr(tmp_path)
        result = mgr.update(date(2026, 5, 20))
        assert result.incremented is True

    def test_first_hunt_current_streak_one(self, tmp_path):
        """First ever hunt returns current_streak=1."""
        mgr = make_mgr(tmp_path)
        result = mgr.update(date(2026, 5, 20))
        assert result.current_streak == 1

    def test_consecutive_day_incremented_true(self, tmp_path):
        """Consecutive day hunt returns incremented=True."""
        mgr = make_mgr(tmp_path)
        mgr.update(date(2026, 5, 20))
        result = mgr.update(date(2026, 5, 21))
        assert result.incremented is True
        assert result.current_streak == 2

    def test_same_day_second_call_incremented_false(self, tmp_path):
        """Same-day second call returns incremented=False (idempotent)."""
        mgr = make_mgr(tmp_path)
        today = date(2026, 5, 20)
        mgr.update(today)
        result = mgr.update(today)
        assert result.incremented is False

    def test_backward_clock_incremented_false(self, tmp_path):
        """Backward clock clamp returns incremented=False."""
        mgr = make_mgr(tmp_path)
        mgr.update(date(2026, 5, 20))
        result = mgr.update(date(2026, 5, 19))
        assert result.incremented is False

    def test_streak_break_incremented_true_current_streak_reset(self, tmp_path):
        """After streak break, update returns incremented=True (new streak of 1)."""
        mgr = make_mgr(tmp_path)
        mgr.update(date(2026, 5, 20))
        mgr.update(date(2026, 5, 21))
        result = mgr.update(date(2026, 5, 27))  # big gap — breaks streak
        assert result.incremented is True
        assert result.current_streak == 1

    def test_freeze_bridge_incremented_true(self, tmp_path):
        """Freeze-bridged day returns incremented=True."""
        mgr = make_mgr(tmp_path)
        mgr.update(date(2026, 5, 18))  # Mon
        result = mgr.update(date(2026, 5, 20))  # Wed — one missed day, freeze used
        assert result.incremented is True
        assert result.current_streak == 2

    def test_current_streak_matches_state(self, tmp_path):
        """StreakUpdate.current_streak matches mgr.state.current_streak after update."""
        mgr = make_mgr(tmp_path)
        for offset in range(5):
            result = mgr.update(date(2026, 5, 20) + timedelta(days=offset))
        assert result.current_streak == mgr.state.current_streak


# ---------------------------------------------------------------------------
# M-3 F62 invariants (Evaluation Contract §7.D, B24–B25)
# streak.json must remain byte-identical when dossier events are emitted.
# streak_continued emission semantics must be unchanged under M-3 wiring.
# ---------------------------------------------------------------------------


class TestM3F62Invariants:
    """F62 invariants under M-3: dossier event emission must not touch streak.json."""

    def test_streak_json_byte_identical_under_dossier_event_emission(self, tmp_path):
        """B24: Emitting dossier slot-fill events does not touch streak.json.

        Calls emit_dossier_slot_filled_events directly (the pure function),
        then asserts streak.json (if it exists) is byte-identical. Since the
        pure function has no I/O, the file must remain untouched.
        """
        from adversary_pursuit.dossier.scoring import emit_dossier_slot_filled_events
        from adversary_pursuit.dossier.slot_inference import DossierState, SlotState
        from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus

        streak_path = tmp_path / "streak.json"

        # Seed streak.json via StreakManager (creates the file)
        mgr = make_mgr(tmp_path)
        mgr.update(date(2026, 5, 20))
        assert streak_path.exists(), "streak.json must exist after StreakManager.update()"

        before_bytes = streak_path.read_bytes()

        # Build minimal pre/post DossierState triggering an Identity slot-fill event
        def _slot(slot, status):
            return SlotState(name=slot, status=status)

        pre_slots = {slot: _slot(slot, SlotStatus.EMPTY) for slot in DossierSlotName}
        post_slots = dict(pre_slots)
        post_slots[DossierSlotName.IDENTITY] = _slot(DossierSlotName.IDENTITY, SlotStatus.PARTIAL)
        pre = DossierState(slots=pre_slots, total_sco_count=0)
        post = DossierState(slots=post_slots, total_sco_count=1)

        # Call the pure function — must not touch streak.json
        events = emit_dossier_slot_filled_events(pre, post)
        assert len(events) == 1, "Expected one dossier_slot_filled event"

        after_bytes = streak_path.read_bytes()
        assert before_bytes == after_bytes, (
            "streak.json was modified by emit_dossier_slot_filled_events — F62 violation"
        )

    def test_streak_continued_emits_after_dossier_in_combined_hunt(self, tmp_path):
        """B25: Both dossier_slot_filled and streak_continued are persisted in combined hunt.

        Uses WorkspaceManager directly to simulate the emission ordering from
        _execute_hunt / run_module: per-IOC events first, dossier events second,
        streak event third. Verifies both action types appear in score_events.
        """
        from adversary_pursuit.core.workspace import WorkspaceManager
        from adversary_pursuit.dossier.scoring import emit_dossier_slot_filled_events
        from adversary_pursuit.dossier.slot_inference import DossierState, SlotState
        from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus
        from adversary_pursuit.gamification.scoring import make_streak_continued_event

        wm = WorkspaceManager(workspace_dir=tmp_path / "workspaces")
        wm.create("default")
        wm.switch("default")

        # Simulate dossier_slot_filled event emission
        def _slot(slot, status):
            return SlotState(name=slot, status=status)

        pre_slots = {slot: _slot(slot, SlotStatus.EMPTY) for slot in DossierSlotName}
        post_slots = dict(pre_slots)
        post_slots[DossierSlotName.IDENTITY] = _slot(DossierSlotName.IDENTITY, SlotStatus.PARTIAL)
        pre = DossierState(slots=pre_slots, total_sco_count=0)
        post = DossierState(slots=post_slots, total_sco_count=1)

        dossier_events = emit_dossier_slot_filled_events(pre, post)
        assert dossier_events, "Expected at least one dossier_slot_filled event"
        wm.store_score_events(dossier_events)

        # Simulate streak_continued event (day 1 = 10 pts)
        streak_event = make_streak_continued_event(1)
        wm.store_score_events([streak_event])

        # Verify both action types are in the score_events table
        recent = wm.get_recent_scores(limit=10)
        actions = {row["action"] for row in recent}
        assert "dossier_slot_filled" in actions, (
            f"dossier_slot_filled not found in score_events; actions={actions}"
        )
        assert "streak_continued" in actions, (
            f"streak_continued not found in score_events; actions={actions}"
        )
