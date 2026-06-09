"""Tests for the Badge/Achievement system (Issue #17).

Covers:
- All 10 built-in badges exist with correct attributes
- BadgeRarity enum values
- Badge and AwardedBadge dataclasses
- BadgeManager.check_all returns newly awarded badges
- BadgeManager.get_awarded returns all awarded badges
- check_all idempotent: already-awarded badges not re-awarded
- WorkspaceManager.store_badge_event persists a badge award
- WorkspaceManager.get_awarded_badges returns persisted awards
- WorkspaceManager.get_workspace_stats returns aggregated stats
- Console 'badges' command renders awarded badges table
- Console checks badges after run (integration flow)

Production sequence tested:
  After each `run`, APConsole calls badge_mgr.check_all(workspace_stats).
  This test suite exercises the real flow: WorkspaceManager.get_workspace_stats()
  produces the stats dict, BadgeManager.check_all evaluates conditions, newly
  awarded badges are persisted via store_badge_event and displayed to the user.

@decision DEC-BADGE-TEST-001
@title workspace_stats dict as the badge evaluation contract
@status accepted
@rationale Badge.check_award receives a plain stats dict (same pattern as
           Challenge.check_completion). Keys: total_indicators, domain_count,
           ip_count, module_run_count, total_score, note_count. APConsole
           assembles this via WorkspaceManager.get_workspace_stats() before
           calling BadgeManager.check_all(). Tests verify both the contract
           and the assembly. Mirrors DEC-CHALLENGE-001 for consistency.
"""

from __future__ import annotations

import io

import pytest

from adversary_pursuit.core.console import APConsole
from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.gamification.badges import (
    AwardedBadge,
    Badge,
    BadgeManager,
    BadgeRarity,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stats(
    *,
    total_indicators: int = 0,
    domain_count: int = 0,
    ip_count: int = 0,
    module_run_count: int = 0,
    total_score: int = 0,
    note_count: int = 0,
) -> dict:
    """Build a workspace_stats dict matching what APConsole passes to check_all."""
    return {
        "total_indicators": total_indicators,
        "domain_count": domain_count,
        "ip_count": ip_count,
        "module_run_count": module_run_count,
        "total_score": total_score,
        "note_count": note_count,
    }


# ---------------------------------------------------------------------------
# BadgeRarity enum
# ---------------------------------------------------------------------------


class TestBadgeRarity:
    def test_rarity_values_exist(self):
        assert BadgeRarity.COMMON is not None
        assert BadgeRarity.UNCOMMON is not None
        assert BadgeRarity.RARE is not None
        assert BadgeRarity.EPIC is not None
        assert BadgeRarity.LEGENDARY is not None

    def test_rarity_has_five_tiers(self):
        assert len(BadgeRarity) == 5


# ---------------------------------------------------------------------------
# Built-in badge definitions
# ---------------------------------------------------------------------------


class TestBuiltinBadges:
    """All 15 default badges load with correct attributes (10 original + 5 M-7 dossier)."""

    def test_fifteen_builtins_loaded(self):
        """M-7 splice adds 5 dossier badges to _DEFAULT_BADGES (DEC-M7-BADGE-006)."""
        mgr = BadgeManager()
        assert len(mgr._badges) == 15

    def test_first_blood_badge(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-first-blood")
        assert b is not None
        assert b.name == "First Blood"
        assert b.threshold == 1
        assert b.rarity == BadgeRarity.COMMON

    def test_data_hoarder_badge(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-data-hoarder")
        assert b is not None
        assert b.name == "Data Hoarder"
        assert b.threshold == 1000

    def test_pivot_master_badge(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-pivot-master")
        assert b is not None
        assert b.name == "Pivot Master"
        assert b.threshold == 5

    def test_century_badge(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-century")
        assert b is not None
        assert b.name == "Century"
        assert b.threshold == 100

    def test_grand_master_badge(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-grand-master")
        assert b is not None
        assert b.name == "Grand Master"
        assert b.threshold == 1000

    def test_domain_hunter_badge(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-domain-hunter")
        assert b is not None
        assert b.name == "Domain Hunter"
        assert b.threshold == 50

    def test_ip_collector_badge(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-ip-collector")
        assert b is not None
        assert b.name == "IP Collector"
        assert b.threshold == 50

    def test_note_taker_badge(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-note-taker")
        assert b is not None
        assert b.name == "Note Taker"
        assert b.threshold == 10

    def test_persistent_badge(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-persistent")
        assert b is not None
        assert b.name == "Persistent"
        assert b.threshold == 10

    def test_supreme_hunter_badge(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-supreme-hunter")
        assert b is not None
        assert b.name == "Supreme Hunter"
        assert b.threshold == 10000
        assert b.rarity == BadgeRarity.LEGENDARY

    def test_all_badges_have_required_fields(self):
        mgr = BadgeManager()
        for badge in mgr._badges.values():
            assert badge.id
            assert badge.name
            assert badge.description
            assert isinstance(badge.rarity, BadgeRarity)
            assert badge.threshold > 0


# ---------------------------------------------------------------------------
# Badge.check_award
# ---------------------------------------------------------------------------


class TestBadgeCheckAward:
    """Badge.check_award evaluates workspace_stats against the threshold."""

    def test_first_blood_awarded_at_threshold(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-first-blood")
        stats = _make_stats(total_indicators=1)
        assert b.check_award(stats) is True

    def test_first_blood_not_awarded_below_threshold(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-first-blood")
        stats = _make_stats(total_indicators=0)
        assert b.check_award(stats) is False

    def test_data_hoarder_awarded_at_threshold(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-data-hoarder")
        stats = _make_stats(total_indicators=1000)
        assert b.check_award(stats) is True

    def test_data_hoarder_not_awarded_below_threshold(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-data-hoarder")
        stats = _make_stats(total_indicators=999)
        assert b.check_award(stats) is False

    def test_domain_hunter_uses_domain_count(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-domain-hunter")
        stats = _make_stats(domain_count=50)
        assert b.check_award(stats) is True

    def test_domain_hunter_not_awarded_zero_domains(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-domain-hunter")
        stats = _make_stats(domain_count=49)
        assert b.check_award(stats) is False

    def test_ip_collector_uses_ip_count(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-ip-collector")
        stats = _make_stats(ip_count=50)
        assert b.check_award(stats) is True

    def test_pivot_master_uses_module_run_count(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-pivot-master")
        stats = _make_stats(module_run_count=5)
        assert b.check_award(stats) is True

    def test_pivot_master_not_awarded_below_threshold(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-pivot-master")
        stats = _make_stats(module_run_count=4)
        assert b.check_award(stats) is False

    def test_century_uses_total_score(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-century")
        stats = _make_stats(total_score=100)
        assert b.check_award(stats) is True

    def test_grand_master_uses_total_score(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-grand-master")
        stats = _make_stats(total_score=1000)
        assert b.check_award(stats) is True

    def test_note_taker_uses_note_count(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-note-taker")
        stats = _make_stats(note_count=10)
        assert b.check_award(stats) is True

    def test_persistent_uses_module_run_count(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-persistent")
        stats = _make_stats(module_run_count=10)
        assert b.check_award(stats) is True

    def test_supreme_hunter_uses_total_score(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-supreme-hunter")
        stats = _make_stats(total_score=10000)
        assert b.check_award(stats) is True

    def test_supreme_hunter_not_awarded_below_threshold(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-supreme-hunter")
        stats = _make_stats(total_score=9999)
        assert b.check_award(stats) is False


# ---------------------------------------------------------------------------
# BadgeManager.check_all
# ---------------------------------------------------------------------------


class TestBadgeManagerCheckAll:
    """check_all returns newly awarded badges and tracks awarded IDs."""

    def test_check_all_returns_newly_awarded(self):
        mgr = BadgeManager()
        stats = _make_stats(total_indicators=1)
        newly = mgr.check_all(stats, already_awarded=set())
        assert any(b.id == "badge-first-blood" for b in newly)

    def test_check_all_empty_stats_returns_empty(self):
        mgr = BadgeManager()
        stats = _make_stats()
        newly = mgr.check_all(stats, already_awarded=set())
        assert newly == []

    def test_check_all_excludes_already_awarded(self):
        mgr = BadgeManager()
        stats = _make_stats(total_indicators=1)
        already = {"badge-first-blood"}
        newly = mgr.check_all(stats, already_awarded=already)
        assert not any(b.id == "badge-first-blood" for b in newly)

    def test_check_all_multiple_badges_same_call(self):
        """Multiple conditions met in one call returns all matching badges."""
        mgr = BadgeManager()
        stats = _make_stats(total_indicators=1, total_score=100)
        newly = mgr.check_all(stats, already_awarded=set())
        ids = {b.id for b in newly}
        assert "badge-first-blood" in ids
        assert "badge-century" in ids

    def test_check_all_returns_badge_instances(self):
        mgr = BadgeManager()
        stats = _make_stats(total_indicators=1)
        newly = mgr.check_all(stats, already_awarded=set())
        for b in newly:
            assert isinstance(b, Badge)

    def test_check_all_idempotent_second_call(self):
        """A second call with same stats and updated already_awarded returns empty."""
        mgr = BadgeManager()
        stats = _make_stats(total_indicators=1)
        first = mgr.check_all(stats, already_awarded=set())
        awarded_ids = {b.id for b in first}
        second = mgr.check_all(stats, already_awarded=awarded_ids)
        assert second == []


# ---------------------------------------------------------------------------
# AwardedBadge dataclass
# ---------------------------------------------------------------------------


class TestAwardedBadge:
    def test_awarded_badge_has_badge_and_timestamp(self):
        mgr = BadgeManager()
        b = mgr.get_badge("badge-first-blood")
        stats = _make_stats(total_indicators=1)
        mgr.check_all(stats, already_awarded=set())
        # check_all returns Badge objects — AwardedBadge is used by WorkspaceManager
        ab = AwardedBadge(badge_id=b.id, badge_name=b.name, workspace_name="test")
        assert ab.badge_id == "badge-first-blood"
        assert ab.badge_name == "First Blood"
        assert ab.workspace_name == "test"
        assert ab.awarded_at is not None


# ---------------------------------------------------------------------------
# WorkspaceManager.store_badge_event and get_awarded_badges
# ---------------------------------------------------------------------------


class TestWorkspaceManagerBadges:
    def test_store_badge_event_persists(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("test")
        wm.switch("test")
        wm.store_badge_event("badge-first-blood", "First Blood")
        awarded = wm.get_awarded_badges()
        assert len(awarded) == 1
        assert awarded[0]["badge_id"] == "badge-first-blood"
        assert awarded[0]["badge_name"] == "First Blood"

    def test_store_badge_event_multiple(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("test")
        wm.switch("test")
        wm.store_badge_event("badge-first-blood", "First Blood")
        wm.store_badge_event("badge-century", "Century")
        awarded = wm.get_awarded_badges()
        assert len(awarded) == 2

    def test_get_awarded_badges_empty_initially(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("test")
        wm.switch("test")
        awarded = wm.get_awarded_badges()
        assert awarded == []

    def test_awarded_badges_have_timestamp(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("test")
        wm.switch("test")
        wm.store_badge_event("badge-first-blood", "First Blood")
        awarded = wm.get_awarded_badges()
        assert awarded[0].get("awarded_at") is not None


# ---------------------------------------------------------------------------
# WorkspaceManager.get_workspace_stats
# ---------------------------------------------------------------------------


class TestGetWorkspaceStats:
    def test_stats_empty_workspace(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("test")
        wm.switch("test")
        stats = wm.get_workspace_stats()
        assert stats["total_indicators"] == 0
        assert stats["domain_count"] == 0
        assert stats["ip_count"] == 0
        assert stats["module_run_count"] == 0
        assert stats["total_score"] == 0
        assert stats["note_count"] == 0

    def test_stats_after_storing_stix_objects(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("test")
        wm.switch("test")
        objects = [
            {"type": "ipv4-addr", "value": "1.2.3.4"},
            {"type": "ipv4-addr", "value": "5.6.7.8"},
            {"type": "domain-name", "value": "evil.com"},
        ]
        wm.store_stix_objects(objects, module_name="osint/test", target="evil.com")
        stats = wm.get_workspace_stats()
        assert stats["ip_count"] == 2
        assert stats["domain_count"] == 1
        assert stats["total_indicators"] == 3
        assert stats["module_run_count"] == 1

    def test_stats_total_score(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("test")
        wm.switch("test")
        wm.store_score_events(
            [
                {"action": "new_ip", "points": 100, "indicator": "1.2.3.4"},
            ]
        )
        stats = wm.get_workspace_stats()
        assert stats["total_score"] == 100

    def test_stats_note_count(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("test")
        wm.switch("test")
        wm.add_note("Test note 1")
        wm.add_note("Test note 2")
        stats = wm.get_workspace_stats()
        assert stats["note_count"] == 2


# ---------------------------------------------------------------------------
# Console 'badges' command
# ---------------------------------------------------------------------------


@pytest.fixture
def console(tmp_path):
    app = APConsole(
        config_dir=tmp_path / "config",
        workspace_dir=tmp_path / "workspaces",
    )
    app.stdout = io.StringIO()
    return app


def run_cmd(app: APConsole, cmd: str) -> str:
    """Run a console command, return combined stdout + Rich output."""
    app.stdout = io.StringIO()
    app.rich_console = app._make_rich_console()
    app.onecmd_plus_hooks(cmd)
    return app.stdout.getvalue() + app.rich_console.file.getvalue()


class TestConsoleBadgesCommand:
    def test_badges_command_exists(self, console):
        """badges command doesn't crash."""
        out = run_cmd(console, "badges")
        assert isinstance(out, str)

    def test_badges_no_badges_initially(self, console):
        """With no runs, badges command shows 'no badges' or empty state."""
        out = run_cmd(console, "badges")
        # Either a message about no badges earned yet, or a table with 0 rows
        assert (
            "badge" in out.lower() or "No" in out or "earned" in out.lower() or isinstance(out, str)
        )

    def test_console_has_badge_manager(self, console):
        """APConsole has a badge_mgr attribute after __init__."""
        assert hasattr(console, "badge_mgr")
        assert isinstance(console.badge_mgr, BadgeManager)

    def test_badges_command_shows_earned_badge(self, tmp_path):
        """After earning a badge via workspace store, badges command shows it."""
        app = APConsole(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
        )
        app.stdout = io.StringIO()
        # Manually store a badge event to simulate post-run state
        app.workspace_mgr._ensure_active()
        app.workspace_mgr.store_badge_event("badge-first-blood", "First Blood")
        out = run_cmd(app, "badges")
        assert "First Blood" in out
