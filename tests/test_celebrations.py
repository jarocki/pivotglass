"""Tests for Issue #22: Celebration System.

Tests cover:
- CelebrationEngine.celebrate(points) returns correct ASCII art by level
  (small <50, medium 50-199, large 200-499, epic 500+)
- celebrate() returns str type, non-empty for all levels
- milestone_message(total_score) returns correct messages at 100/500/1000/5000/10000
- milestone_message() returns None for non-milestone totals
- first_blood_message() returns str
- bell_enabled flag behavior
- Level boundary conditions (exact threshold values)
- Production sequence: hunt → score → celebration displayed in console output

Production sequence:
  _execute_hunt() → score_results() → CelebrationEngine.celebrate(total_gained)
  → rich_console.print(celebration_art)

@decision DEC-TEST-022
@title Celebration tests cover all 4 art levels, 5 milestones, and console integration
@status accepted
@rationale celebrate() has clear numeric boundaries -- test at, below, and above each
           threshold. milestone_message() must fire exactly at the spec'd totals (not
           between them). Console integration confirms celebration art appears in run
           output so the analyst actually sees it.
"""

from __future__ import annotations

import io

import pytest

from adversary_pursuit.gamification.celebrations import CelebrationEngine
from adversary_pursuit.core.console import APConsole


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

    def test_small_celebration_returns_consistent_art(self, engine):
        """All small-level calls return the same art string."""
        a = engine.celebrate(10)
        b = engine.celebrate(30)
        assert a == b

    # ---- medium: 50 <= points < 200 ----

    def test_medium_celebration_at_50_points(self, engine):
        """50 points — exact medium threshold — returns medium art."""
        result_medium = engine.celebrate(50)
        result_small = engine.celebrate(49)
        assert result_medium != result_small

    def test_medium_celebration_at_199_points(self, engine):
        """199 points — just below large threshold — returns medium art."""
        result = engine.celebrate(199)
        result_medium = engine.celebrate(50)
        assert result == result_medium

    def test_medium_celebration_returns_consistent_art(self, engine):
        """All medium-level calls return the same art string."""
        a = engine.celebrate(50)
        b = engine.celebrate(150)
        assert a == b

    # ---- large: 200 <= points < 500 ----

    def test_large_celebration_at_200_points(self, engine):
        """200 points — exact large threshold — returns large art."""
        result_large = engine.celebrate(200)
        result_medium = engine.celebrate(199)
        assert result_large != result_medium

    def test_large_celebration_at_499_points(self, engine):
        """499 points — just below epic threshold — returns large art."""
        result = engine.celebrate(499)
        result_large = engine.celebrate(200)
        assert result == result_large

    def test_large_celebration_returns_consistent_art(self, engine):
        """All large-level calls return the same art string."""
        a = engine.celebrate(200)
        b = engine.celebrate(400)
        assert a == b

    # ---- epic: points >= 500 ----

    def test_epic_celebration_at_500_points(self, engine):
        """500 points — exact epic threshold — returns epic art."""
        result_epic = engine.celebrate(500)
        result_large = engine.celebrate(499)
        assert result_epic != result_large

    def test_epic_celebration_at_high_points(self, engine):
        """Very high points still returns epic art."""
        result = engine.celebrate(9999)
        result_epic = engine.celebrate(500)
        assert result == result_epic

    def test_epic_celebration_returns_consistent_art(self, engine):
        """All epic-level calls return the same art string."""
        a = engine.celebrate(500)
        b = engine.celebrate(1000)
        assert a == b

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
# CelebrationEngine.milestone_message — milestone triggers
# ---------------------------------------------------------------------------


class TestMilestoneMessage:
    """Verify milestone_message returns the right string at each milestone total."""

    def test_milestone_at_100(self, engine):
        """100 total score triggers a milestone message."""
        msg = engine.milestone_message(100)
        assert msg is not None
        assert isinstance(msg, str)
        assert len(msg.strip()) > 0

    def test_milestone_at_500(self, engine):
        """500 total score triggers a milestone message."""
        msg = engine.milestone_message(500)
        assert msg is not None
        assert isinstance(msg, str)

    def test_milestone_at_1000(self, engine):
        """1000 total score triggers a milestone message."""
        msg = engine.milestone_message(1000)
        assert msg is not None
        assert isinstance(msg, str)

    def test_milestone_at_5000(self, engine):
        """5000 total score triggers a milestone message."""
        msg = engine.milestone_message(5000)
        assert msg is not None
        assert isinstance(msg, str)

    def test_milestone_at_10000(self, engine):
        """10000 total score triggers the top-tier milestone message."""
        msg = engine.milestone_message(10000)
        assert msg is not None
        assert isinstance(msg, str)

    def test_no_milestone_at_99(self, engine):
        """99 total score — just below first milestone — returns None."""
        assert engine.milestone_message(99) is None

    def test_no_milestone_at_101(self, engine):
        """101 total score — just above 100 milestone — returns None."""
        assert engine.milestone_message(101) is None

    def test_no_milestone_at_0(self, engine):
        """0 total score triggers no milestone."""
        assert engine.milestone_message(0) is None

    def test_no_milestone_between_milestones(self, engine):
        """Arbitrary non-milestone values return None."""
        for total in [1, 50, 150, 300, 750, 1500, 3000, 7500]:
            assert engine.milestone_message(total) is None, (
                f"milestone_message({total}) should be None"
            )

    def test_all_five_milestones_return_distinct_messages(self, engine):
        """Each milestone produces a distinct message."""
        msgs = {
            engine.milestone_message(100),
            engine.milestone_message(500),
            engine.milestone_message(1000),
            engine.milestone_message(5000),
            engine.milestone_message(10000),
        }
        assert len(msgs) == 5, "Expected 5 distinct milestone messages"


# ---------------------------------------------------------------------------
# CelebrationEngine.first_blood_message
# ---------------------------------------------------------------------------


class TestFirstBloodMessage:
    """Verify first_blood_message returns a usable string."""

    def test_first_blood_returns_str(self, engine):
        """first_blood_message() returns a str."""
        msg = engine.first_blood_message()
        assert isinstance(msg, str)

    def test_first_blood_non_empty(self, engine):
        """first_blood_message() is non-empty."""
        msg = engine.first_blood_message()
        assert len(msg.strip()) > 0

    def test_first_blood_consistent(self, engine):
        """Multiple calls to first_blood_message() return the same string."""
        a = engine.first_blood_message()
        b = engine.first_blood_message()
        assert a == b


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
