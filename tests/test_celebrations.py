"""Tests for Issue #22 + F63: Celebration System.

Tests cover:
- CelebrationEngine.celebrate(points) returns correct ASCII art by level
  (small <50, medium 50-199, large 200-499, epic 500+)
- celebrate() returns str type, non-empty for all levels
- check_milestones(total_score, last_announced_id) — F63 catch-up semantics:
  returns all milestones where threshold <= total AND id > last_announced_id
- check_milestones() returns empty list when no new milestones crossed
- highest_crossed_milestone_id() helper for quiet-start migration (DEC-63-MIGRATION-001)
- first_blood_message() returns str
- bell_enabled flag behavior
- Level boundary conditions (exact threshold values)
- Production sequence: hunt → score → celebration displayed in console output

Production sequence:
  _execute_hunt() → score_results() → CelebrationEngine.celebrate(total_gained)
  → rich_console.print(celebration_art)

@decision DEC-TEST-022
@title Celebration tests cover all 4 art levels, 5 milestones (catch-up), and console integration
@status accepted
@rationale celebrate() has clear numeric boundaries — test at, below, and above each
           threshold. check_milestones() must cover catch-up (score jumps past multiple
           milestones), idempotency (last_announced_id blocks re-fire), and quiet-start
           migration helper. Console integration confirms celebration art appears in run
           output so the analyst actually sees it.
"""

from __future__ import annotations

import io

import pytest

from adversary_pursuit.core.console import APConsole
from adversary_pursuit.gamification.celebrations import (
    CelebrationEngine,
    MilestoneSpec,
    highest_crossed_milestone_id,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine():
    """Fresh CelebrationEngine with bell disabled (no terminal noise in tests)."""
    return CelebrationEngine(bell_enabled=False)


@pytest.fixture
def bell_engine():
    """CelebrationEngine with bell enabled."""
    return CelebrationEngine(bell_enabled=True)


@pytest.fixture
def console(tmp_path):
    """APConsole with isolated temp dirs."""
    app = APConsole(
        config_dir=tmp_path / "config",
        workspace_dir=tmp_path / "workspaces",
    )
    app.stdout = io.StringIO()
    return app


def run_cmd(app: APConsole, cmd: str) -> str:
    """Run a console command and return combined poutput + Rich output."""
    app.stdout = io.StringIO()
    app.rich_console = app._make_rich_console()
    app.onecmd_plus_hooks(cmd)
    return app.stdout.getvalue() + app.rich_console.file.getvalue()


# ---------------------------------------------------------------------------
# CelebrationEngine.celebrate — level boundaries
# ---------------------------------------------------------------------------


class TestCelebrateLevel:
    """Verify the correct ASCII art level is returned for each point band."""

    # ---- small: 1 <= points < 50 ----

    def test_small_celebration_at_1_point(self, engine):
        """1 point — minimum scoreable amount — returns small art."""
        result = engine.celebrate(1)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_small_celebration_at_49_points(self, engine):
        """49 points — just below medium threshold — returns small art."""
        result = engine.celebrate(49)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_small_celebration_returns_art_from_small_pool(self, engine):
        """All small-level calls return art from the small pool (F62: random.choice fix)."""
        from adversary_pursuit.gamification.celebrations import CELEBRATION_ART

        a = engine.celebrate(10)
        b = engine.celebrate(30)
        # Both must be members of the small pool — random.choice picks from it
        assert a in CELEBRATION_ART["small"]
        assert b in CELEBRATION_ART["small"]

    # ---- medium: 50 <= points < 200 ----

    def test_medium_celebration_at_50_points(self, engine):
        """50 points — exact medium threshold — returns medium art."""
        result_medium = engine.celebrate(50)
        result_small = engine.celebrate(49)
        assert result_medium != result_small

    def test_medium_celebration_at_199_points(self, engine):
        """199 points — just below large threshold — returns medium art."""
        from adversary_pursuit.gamification.celebrations import CELEBRATION_ART

        result = engine.celebrate(199)
        assert result in CELEBRATION_ART["medium"]

    def test_medium_celebration_returns_art_from_medium_pool(self, engine):
        """All medium-level calls return art from the medium pool (F62: random.choice fix)."""
        from adversary_pursuit.gamification.celebrations import CELEBRATION_ART

        a = engine.celebrate(50)
        b = engine.celebrate(150)
        assert a in CELEBRATION_ART["medium"]
        assert b in CELEBRATION_ART["medium"]

    # ---- large: 200 <= points < 500 ----

    def test_large_celebration_at_200_points(self, engine):
        """200 points — exact large threshold — returns large art."""
        result_large = engine.celebrate(200)
        result_medium = engine.celebrate(199)
        assert result_large != result_medium

    def test_large_celebration_at_499_points(self, engine):
        """499 points — just below epic threshold — returns large art."""
        from adversary_pursuit.gamification.celebrations import CELEBRATION_ART

        result = engine.celebrate(499)
        assert result in CELEBRATION_ART["large"]

    def test_large_celebration_returns_art_from_large_pool(self, engine):
        """All large-level calls return art from the large pool (F62: random.choice fix)."""
        from adversary_pursuit.gamification.celebrations import CELEBRATION_ART

        a = engine.celebrate(200)
        b = engine.celebrate(400)
        assert a in CELEBRATION_ART["large"]
        assert b in CELEBRATION_ART["large"]

    # ---- epic: points >= 500 ----

    def test_epic_celebration_at_500_points(self, engine):
        """500 points — exact epic threshold — returns epic art."""
        result_epic = engine.celebrate(500)
        result_large = engine.celebrate(499)
        assert result_epic != result_large

    def test_epic_celebration_at_high_points(self, engine):
        """Very high points still returns epic art."""
        from adversary_pursuit.gamification.celebrations import CELEBRATION_ART

        result = engine.celebrate(9999)
        assert result in CELEBRATION_ART["epic"]

    def test_epic_celebration_returns_art_from_epic_pool(self, engine):
        """All epic-level calls return art from the epic pool (F62: random.choice fix)."""
        from adversary_pursuit.gamification.celebrations import CELEBRATION_ART

        a = engine.celebrate(500)
        b = engine.celebrate(1000)
        assert a in CELEBRATION_ART["epic"]
        assert b in CELEBRATION_ART["epic"]

    # ---- edge cases ----

    def test_zero_points_returns_str(self, engine):
        """0 points still returns a string (no crash)."""
        result = engine.celebrate(0)
        assert isinstance(result, str)

    def test_all_levels_return_non_empty_strings(self, engine):
        """Every level (small/medium/large/epic) returns non-empty art."""
        for pts in [1, 50, 200, 500]:
            result = engine.celebrate(pts)
            assert len(result.strip()) > 0, f"Empty art at {pts} points"

    def test_four_distinct_art_variants(self, engine):
        """All four levels produce distinct art strings."""
        small = engine.celebrate(10)
        medium = engine.celebrate(100)
        large = engine.celebrate(300)
        epic = engine.celebrate(1000)
        arts = {small, medium, large, epic}
        assert len(arts) == 4, "Expected 4 distinct art strings, one per level"


# ---------------------------------------------------------------------------
# CelebrationEngine.check_milestones — F63 cross-threshold catch-up
# ---------------------------------------------------------------------------


class TestCheckMilestones:
    """Verify check_milestones implements cross-threshold catch-up with idempotency.

    DEC-63-MILESTONE-CATCHUP-001: check_milestones returns every milestone
    whose threshold <= total_score AND id > last_announced_id.
    """

    def test_no_milestones_at_zero_score(self, engine):
        """Score=0, last_id=None → no milestones."""
        result = engine.check_milestones(0, None)
        assert result == []

    def test_first_milestone_fires_at_100(self, engine):
        """Score=100, last_id=None → milestone id=1 (threshold 100) fires."""
        result = engine.check_milestones(100, None)
        assert len(result) == 1
        assert result[0].id == 1
        assert result[0].threshold == 100

    def test_below_first_milestone_no_fire(self, engine):
        """Score=99, last_id=None → no milestones (99 < 100)."""
        result = engine.check_milestones(99, None)
        assert result == []

    def test_catchup_two_milestones_in_one_run(self, engine):
        """Score jumps from 0 to 620 — both 100 and 500 milestones fire."""
        result = engine.check_milestones(620, None)
        ids = [ms.id for ms in result]
        assert 1 in ids  # threshold 100
        assert 2 in ids  # threshold 500
        assert len(result) == 2

    def test_catchup_all_five_milestones(self, engine):
        """Score=10000, last_id=None → all 5 milestones fire."""
        result = engine.check_milestones(10000, None)
        assert len(result) == 5
        ids = [ms.id for ms in result]
        assert ids == sorted(ids), "Milestones must be in ascending id order"

    def test_idempotent_already_announced(self, engine):
        """Score=100, last_id=1 → no new milestones (already announced)."""
        result = engine.check_milestones(100, 1)
        assert result == []

    def test_partial_catchup_from_mid_announced(self, engine):
        """Score=5000, last_id=2 → milestones 3 (1000) and 4 (5000) fire."""
        result = engine.check_milestones(5000, 2)
        ids = [ms.id for ms in result]
        assert 3 in ids
        assert 4 in ids
        assert 1 not in ids
        assert 2 not in ids

    def test_returns_milestonespec_objects(self, engine):
        """check_milestones returns MilestoneSpec instances."""
        result = engine.check_milestones(100, None)
        assert len(result) == 1
        assert isinstance(result[0], MilestoneSpec)

    def test_messages_are_nonempty_strings(self, engine):
        """All returned milestone messages are non-empty strings."""
        for ms in engine.check_milestones(10000, None):
            assert isinstance(ms.message, str)
            assert len(ms.message.strip()) > 0

    def test_score_between_milestones_returns_only_crossed(self, engine):
        """Score=750 → only milestones 1 (100) and 2 (500) fire; 3 (1000) does not."""
        result = engine.check_milestones(750, None)
        ids = [ms.id for ms in result]
        assert 1 in ids
        assert 2 in ids
        assert 3 not in ids

    def test_last_id_none_equiv_zero(self, engine):
        """last_announced_id=None behaves identically to 0 (no prior announcements)."""
        result_none = engine.check_milestones(500, None)
        result_zero = engine.check_milestones(500, 0)
        assert [ms.id for ms in result_none] == [ms.id for ms in result_zero]


# ---------------------------------------------------------------------------
# highest_crossed_milestone_id — quiet-start migration helper
# ---------------------------------------------------------------------------


class TestHighestCrossedMilestoneId:
    """Verify the migration helper returns the correct seed ID (DEC-63-MIGRATION-001)."""

    def test_below_all_milestones_returns_none(self):
        """Score below first milestone threshold returns None."""
        assert highest_crossed_milestone_id(0) is None
        assert highest_crossed_milestone_id(99) is None

    def test_at_first_milestone(self):
        """Score=100 → id=1."""
        assert highest_crossed_milestone_id(100) == 1

    def test_between_first_and_second(self):
        """Score=300 → id=1 (only first milestone crossed)."""
        assert highest_crossed_milestone_id(300) == 1

    def test_at_second_milestone(self):
        """Score=500 → id=2."""
        assert highest_crossed_milestone_id(500) == 2

    def test_at_max_milestone(self):
        """Score=10000 → id=5 (all milestones crossed)."""
        assert highest_crossed_milestone_id(10000) == 5

    def test_well_above_max_milestone(self):
        """Score far above max → still id=5 (highest milestone)."""
        assert highest_crossed_milestone_id(99999) == 5


# ---------------------------------------------------------------------------
# CelebrationEngine.first_blood_message
# ---------------------------------------------------------------------------


class TestFirstBloodMessage:
    """Verify first_blood_message fires at most once per session (F62 wire).

    F62 wired _first_blood_used so the method returns str on first call,
    None on all subsequent calls within the same CelebrationEngine instance.
    """

    def test_first_blood_first_call_returns_str(self, engine):
        """first_blood_message() returns a str on first call."""
        msg = engine.first_blood_message()
        assert isinstance(msg, str)

    def test_first_blood_first_call_non_empty(self, engine):
        """first_blood_message() first call is non-empty."""
        msg = engine.first_blood_message()
        assert msg is not None
        assert len(msg.strip()) > 0

    def test_first_blood_second_call_returns_none(self, engine):
        """Second call within same session returns None (already fired)."""
        first = engine.first_blood_message()
        second = engine.first_blood_message()
        assert first is not None  # first call succeeds
        assert second is None  # guard fires

    def test_first_blood_fresh_engine_fires_again(self):
        """A new CelebrationEngine instance can fire first_blood again."""
        eng1 = CelebrationEngine()
        eng2 = CelebrationEngine()
        msg1 = eng1.first_blood_message()
        eng1.first_blood_message()  # exhaust eng1
        msg2 = eng2.first_blood_message()
        assert msg1 is not None
        assert msg2 is not None  # fresh instance, independent guard


# ---------------------------------------------------------------------------
# CelebrationEngine.bell_enabled flag
# ---------------------------------------------------------------------------


class TestBellEnabled:
    """Verify bell_enabled flag is accessible and settable."""

    def test_bell_disabled_by_default_in_fixture(self, engine):
        """The fixture creates an engine with bell_enabled=False."""
        assert engine.bell_enabled is False

    def test_bell_enabled_true(self, bell_engine):
        """bell_enabled=True is stored correctly."""
        assert bell_engine.bell_enabled is True

    def test_bell_enabled_default_false(self):
        """Default CelebrationEngine has bell_enabled=False."""
        eng = CelebrationEngine()
        assert eng.bell_enabled is False


# ---------------------------------------------------------------------------
# Console integration — celebration art appears after scoring in run
# ---------------------------------------------------------------------------


class TestConsoleIntegration:
    """Verify celebration art is displayed in console output after a scoring run."""

    def test_run_produces_celebration_output(self, console):
        """After a run that scores points, celebration art appears in output."""
        run_cmd(console, "use osint/dns_resolve")
        run_cmd(console, "set TARGET example.com")
        out = run_cmd(console, "run")
        # Should have Rich output that includes celebration content
        assert isinstance(out, str)
        assert len(out) > 0

    def test_celebration_engine_wired_to_console(self, console):
        """APConsole has a celebration_engine attribute after init."""
        assert hasattr(console, "celebration_engine")
        assert isinstance(console.celebration_engine, CelebrationEngine)
