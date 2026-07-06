"""Tests for Phase 18 Slice 5: WorkspaceManager pivot tracking and session timing.

Covers:
- record_pivot on fresh workspace (no active) → pivot_count stays 0
- record_pivot after switch to target-a, then record_pivot(target-b) → pivot_count == 1
- Repeated record_pivot(same target) doesn't increment
- elapsed_seconds >= 0 in stats
- Uses REAL SQLite workspace (tmp_path), not mocks

@decision DEC-TEST-WORKSPACE-PIVOTS-001
@title Pivot tests use real SQLite workspaces in tmp_path for integration fidelity
@status accepted
@rationale WorkspaceManager.switch() touches SQLite (creates engine, verifies .db path).
           Using real tmp_path workspaces instead of mocks ensures the pivot counter
           integrates correctly with the actual switch() path (DEC-WORKSPACE-PIVOTS-001).
           Pivot count and elapsed_seconds are in-memory session metrics — tests verify
           the invariant that record_pivot() must be called BEFORE switch() to correctly
           compare new_target against the still-current _active value.
"""

from __future__ import annotations

import time

import pytest

from adversary_pursuit.core.workspace import WorkspaceManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def wm(tmp_path):
    """Fresh WorkspaceManager with isolated tmp_path workspace directory."""
    manager = WorkspaceManager(workspace_dir=tmp_path / "workspaces")
    return manager


# ---------------------------------------------------------------------------
# record_pivot semantics
# ---------------------------------------------------------------------------


class TestRecordPivot:
    """record_pivot() increments _pivot_count only on actual workspace changes."""

    def test_record_pivot_on_fresh_manager_no_increment(self, wm):
        """record_pivot on fresh manager (no active workspace) does not increment."""
        wm.record_pivot("target-a")
        assert wm._pivot_count == 0, (
            "First record_pivot with no active workspace must not increment pivot_count"
        )

    def test_record_pivot_after_switch_increments(self, wm):
        """record_pivot(new) after switch(old) → pivot_count == 1."""
        wm.create("target-a")
        wm.create("target-b")
        # First: no active, no increment
        wm.record_pivot("target-a")
        wm.switch("target-a")
        assert wm._pivot_count == 0

        # Second: active=target-a, new=target-b → increment
        wm.record_pivot("target-b")
        assert wm._pivot_count == 1

    def test_record_pivot_same_target_no_increment(self, wm):
        """Repeated record_pivot with same target as active does not increment."""
        wm.create("target-a")
        wm.switch("target-a")
        wm.record_pivot("target-a")  # same as active
        assert wm._pivot_count == 0

    def test_multiple_pivots_accumulate(self, wm):
        """Multiple distinct pivots accumulate correctly."""
        wm.create("ws-1")
        wm.create("ws-2")
        wm.create("ws-3")

        wm.record_pivot("ws-1")
        wm.switch("ws-1")
        assert wm._pivot_count == 0  # first target, not a pivot

        wm.record_pivot("ws-2")
        wm.switch("ws-2")
        assert wm._pivot_count == 1

        wm.record_pivot("ws-3")
        wm.switch("ws-3")
        assert wm._pivot_count == 2

    def test_pivot_count_in_stats(self, wm):
        """get_workspace_stats() returns the current pivot_count."""
        wm.create("alpha")
        wm.create("beta")

        wm.record_pivot("alpha")
        wm.switch("alpha")
        wm.record_pivot("beta")
        wm.switch("beta")

        stats = wm.get_workspace_stats()
        assert stats["pivot_count"] == 1

    def test_no_pivot_increment_without_prior_switch(self, wm):
        """record_pivot before any switch leaves count at 0."""
        wm.record_pivot("never-switched")
        wm.record_pivot("also-never")
        assert wm._pivot_count == 0


# ---------------------------------------------------------------------------
# Session timing
# ---------------------------------------------------------------------------


class TestSessionTiming:
    """_session_started_at and elapsed_seconds work correctly."""

    def test_elapsed_zero_before_any_switch(self, wm):
        """elapsed_seconds is 0 when no workspace has been switched to yet."""
        # Can't call get_workspace_stats without an active workspace in most cases,
        # but we can check the raw attribute
        assert wm._session_started_at == 0.0
        assert wm._pivot_count == 0

    def test_elapsed_nonnegative_after_switch(self, wm):
        """elapsed_seconds >= 0 after first switch."""
        wm.create("timing-test")
        wm.switch("timing-test")
        stats = wm.get_workspace_stats()
        assert stats["elapsed_seconds"] >= 0

    def test_session_started_at_set_on_first_switch(self, wm):
        """_session_started_at is set to a positive value after first switch."""
        wm.create("timing-test")
        before = time.time()
        wm.switch("timing-test")
        after = time.time()
        assert wm._session_started_at >= before
        assert wm._session_started_at <= after

    def test_session_started_at_not_reset_on_second_switch(self, wm):
        """_session_started_at is NOT reset on subsequent switches."""
        wm.create("ws-a")
        wm.create("ws-b")
        wm.switch("ws-a")
        first_started = wm._session_started_at

        time.sleep(0.01)  # small delay to ensure time difference is detectable
        wm.switch("ws-b")
        assert wm._session_started_at == first_started, (
            "_session_started_at must not be reset on subsequent switches"
        )

    def test_elapsed_seconds_increases_over_time(self, wm):
        """elapsed_seconds in stats increases after a small time delay."""
        wm.create("elapsed-test")
        wm.switch("elapsed-test")
        stats_before = wm.get_workspace_stats()
        time.sleep(0.05)
        stats_after = wm.get_workspace_stats()
        # elapsed_seconds is an integer so it may not change in 50ms,
        # but it should be >= the first reading
        assert stats_after["elapsed_seconds"] >= stats_before["elapsed_seconds"]

    def test_stats_keys_include_elapsed_and_pivots(self, wm):
        """get_workspace_stats() dict includes 'elapsed_seconds' and 'pivot_count' keys."""
        wm.create("keys-test")
        wm.switch("keys-test")
        stats = wm.get_workspace_stats()
        assert "elapsed_seconds" in stats, "elapsed_seconds missing from get_workspace_stats()"
        assert "pivot_count" in stats, "pivot_count missing from get_workspace_stats()"
        assert isinstance(stats["elapsed_seconds"], int)
        assert isinstance(stats["pivot_count"], int)
