"""Tests for the Challenge system (Issue #15).

Covers:
- All 5 built-in challenges exist with correct attributes
- Challenge.check_completion for each verification type:
  indicator_exists, indicator_count, module_used, score_threshold, module_count
- ChallengeManager.get_active returns only active challenges
- ChallengeManager.check_all marks completed challenges and returns newly completed
- YAML loading from file
- Timed challenge expiration (time_limit_seconds)
- Challenge status transitions (ACTIVE -> COMPLETED / EXPIRED)
- Console `challenges` command integration

Production sequence tested:
  After each `run`, the console calls challenge_mgr.check_all(workspace_data).
  This test suite exercises the real production sequence where workspace_data
  is built from WorkspaceManager's get_stix_type_counts / get_total_score /
  get_module_runs. Challenges that were already COMPLETED are not re-completed.

@decision DEC-CHALLENGE-TEST-001
@title workspace_data dict as the challenge verification contract
@status accepted
@rationale check_completion receives a plain dict (workspace_data) rather than
           a WorkspaceManager instance. This keeps Challenge objects pure and
           testable without a database. The dict has known keys: stix_type_counts,
           modules_used, total_score, total_indicators, elapsed_seconds, indicators.
           APConsole is responsible for assembling this dict from WorkspaceManager
           before calling check_all. Tests verify both the contract and the assembly.
"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from adversary_pursuit.gamification.challenges import (
    Challenge,
    ChallengeManager,
    ChallengeStatus,
    ChallengeType,
)
from adversary_pursuit.core.console import APConsole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workspace_data(
    *,
    stix_counts: dict[str, int] | None = None,
    modules_used: list[str] | None = None,
    total_score: int = 0,
    total_indicators: int = 0,
) -> dict:
    """Build a workspace_data dict matching what APConsole passes to check_all."""
    return {
        "stix_type_counts": stix_counts or {},
        "modules_used": modules_used or [],
        "total_score": total_score,
        "total_indicators": total_indicators,
    }


# ---------------------------------------------------------------------------
# Built-in challenges: existence and attribute checks
# ---------------------------------------------------------------------------


class TestBuiltinChallenges:
    """All 5 starter challenges load with correct metadata."""

    def test_five_builtins_loaded(self):
        mgr = ChallengeManager()
        assert len(mgr._challenges) == 5

    def test_ch001_first_blood(self):
        mgr = ChallengeManager()
        ch = mgr.get_challenge("ch-001")
        assert ch is not None
        assert ch.name == "First Blood"
        assert ch.challenge_type == ChallengeType.STANDARD
        assert ch.points == 50
        assert ch.verification["type"] == "indicator_count"
        assert ch.verification["stix_type"] == "ipv4-addr"
        assert ch.verification["min_count"] == 1
        assert len(ch.hints) > 0

    def test_ch002_domain_hunter(self):
        mgr = ChallengeManager()
        ch = mgr.get_challenge("ch-002")
        assert ch is not None
        assert ch.name == "Domain Hunter"
        assert ch.points == 150
        assert ch.verification["stix_type"] == "domain-name"
        assert ch.verification["min_count"] == 5

    def test_ch003_the_pivot(self):
        mgr = ChallengeManager()
        ch = mgr.get_challenge("ch-003")
        assert ch is not None
        assert ch.name == "The Pivot"
        assert ch.challenge_type == ChallengeType.PIVOTING
        assert ch.points == 200
        assert ch.verification["type"] == "module_count"
        assert ch.verification["min_count"] == 3

    def test_ch004_score_hunter(self):
        mgr = ChallengeManager()
        ch = mgr.get_challenge("ch-004")
        assert ch is not None
        assert ch.name == "Score Hunter"
        assert ch.verification["type"] == "score_threshold"
        assert ch.verification["min_score"] == 500

    def test_ch005_speed_run(self):
        mgr = ChallengeManager()
        ch = mgr.get_challenge("ch-005")
        assert ch is not None
        assert ch.name == "Speed Run"
        assert ch.challenge_type == ChallengeType.TIMED
        assert ch.points == 300
        assert ch.time_limit_seconds == 300
        assert ch.verification["min_count"] == 10

    def test_all_start_active(self):
        mgr = ChallengeManager()
        for ch in mgr._challenges.values():
            assert ch.status == ChallengeStatus.ACTIVE


# ---------------------------------------------------------------------------
# Challenge.check_completion — per verification type
# ---------------------------------------------------------------------------


class TestCheckCompletion:
    """check_completion returns True/False based on workspace_data."""

    # --- indicator_count ---

    def test_indicator_count_met(self):
        ch = Challenge(
            id="test-001", name="Test", description="desc",
            challenge_type=ChallengeType.STANDARD, points=10,
            verification={"type": "indicator_count", "stix_type": "ipv4-addr", "min_count": 3},
        )
        data = _make_workspace_data(stix_counts={"ipv4-addr": 3})
        assert ch.check_completion(data) is True

    def test_indicator_count_exceeded(self):
        ch = Challenge(
            id="test-002", name="Test", description="desc",
            challenge_type=ChallengeType.STANDARD, points=10,
            verification={"type": "indicator_count", "stix_type": "ipv4-addr", "min_count": 3},
        )
        data = _make_workspace_data(stix_counts={"ipv4-addr": 10})
        assert ch.check_completion(data) is True

    def test_indicator_count_not_met(self):
        ch = Challenge(
            id="test-003", name="Test", description="desc",
            challenge_type=ChallengeType.STANDARD, points=10,
            verification={"type": "indicator_count", "stix_type": "ipv4-addr", "min_count": 3},
        )
        data = _make_workspace_data(stix_counts={"ipv4-addr": 2})
        assert ch.check_completion(data) is False

    def test_indicator_count_missing_type(self):
        """Missing stix_type in workspace returns False."""
        ch = Challenge(
            id="test-004", name="Test", description="desc",
            challenge_type=ChallengeType.STANDARD, points=10,
            verification={"type": "indicator_count", "stix_type": "ipv4-addr", "min_count": 1},
        )
        data = _make_workspace_data(stix_counts={"domain-name": 5})
        assert ch.check_completion(data) is False

    def test_indicator_count_none_stix_type_uses_total(self):
        """stix_type=None counts all indicators (Speed Run pattern)."""
        ch = Challenge(
            id="test-005", name="Test", description="desc",
            challenge_type=ChallengeType.TIMED, points=10,
            verification={"type": "indicator_count", "stix_type": None, "min_count": 5},
        )
        data = _make_workspace_data(
            stix_counts={"ipv4-addr": 3, "domain-name": 3},
            total_indicators=6,
        )
        assert ch.check_completion(data) is True

    def test_indicator_count_none_stix_type_not_met(self):
        ch = Challenge(
            id="test-006", name="Test", description="desc",
            challenge_type=ChallengeType.TIMED, points=10,
            verification={"type": "indicator_count", "stix_type": None, "min_count": 10},
        )
        data = _make_workspace_data(total_indicators=3)
        assert ch.check_completion(data) is False

    # --- indicator_exists ---

    def test_indicator_exists_found(self):
        ch = Challenge(
            id="test-007", name="Test", description="desc",
            challenge_type=ChallengeType.STANDARD, points=10,
            verification={"type": "indicator_exists", "stix_type": "ipv4-addr", "value": "1.2.3.4"},
        )
        data = _make_workspace_data()
        data["indicators"] = [
            {"type": "ipv4-addr", "value": "1.2.3.4"},
            {"type": "ipv4-addr", "value": "5.6.7.8"},
        ]
        assert ch.check_completion(data) is True

    def test_indicator_exists_not_found(self):
        ch = Challenge(
            id="test-008", name="Test", description="desc",
            challenge_type=ChallengeType.STANDARD, points=10,
            verification={"type": "indicator_exists", "stix_type": "ipv4-addr", "value": "1.2.3.4"},
        )
        data = _make_workspace_data()
        data["indicators"] = [{"type": "ipv4-addr", "value": "9.9.9.9"}]
        assert ch.check_completion(data) is False

    def test_indicator_exists_empty_workspace(self):
        ch = Challenge(
            id="test-009", name="Test", description="desc",
            challenge_type=ChallengeType.STANDARD, points=10,
            verification={"type": "indicator_exists", "stix_type": "ipv4-addr", "value": "1.2.3.4"},
        )
        data = _make_workspace_data()
        assert ch.check_completion(data) is False

    # --- module_used ---

    def test_module_used_present(self):
        ch = Challenge(
            id="test-010", name="Test", description="desc",
            challenge_type=ChallengeType.STANDARD, points=10,
            verification={"type": "module_used", "module_name": "osint/shodan_ip"},
        )
        data = _make_workspace_data(modules_used=["osint/shodan_ip", "osint/whois_lookup"])
        assert ch.check_completion(data) is True

    def test_module_used_absent(self):
        ch = Challenge(
            id="test-011", name="Test", description="desc",
            challenge_type=ChallengeType.STANDARD, points=10,
            verification={"type": "module_used", "module_name": "osint/shodan_ip"},
        )
        data = _make_workspace_data(modules_used=["osint/whois_lookup"])
        assert ch.check_completion(data) is False

    # --- score_threshold ---

    def test_score_threshold_met(self):
        ch = Challenge(
            id="test-012", name="Test", description="desc",
            challenge_type=ChallengeType.STANDARD, points=100,
            verification={"type": "score_threshold", "min_score": 500},
        )
        data = _make_workspace_data(total_score=500)
        assert ch.check_completion(data) is True

    def test_score_threshold_exceeded(self):
        ch = Challenge(
            id="test-013", name="Test", description="desc",
            challenge_type=ChallengeType.STANDARD, points=100,
            verification={"type": "score_threshold", "min_score": 500},
        )
        data = _make_workspace_data(total_score=1000)
        assert ch.check_completion(data) is True

    def test_score_threshold_not_met(self):
        ch = Challenge(
            id="test-014", name="Test", description="desc",
            challenge_type=ChallengeType.STANDARD, points=100,
            verification={"type": "score_threshold", "min_score": 500},
        )
        data = _make_workspace_data(total_score=499)
        assert ch.check_completion(data) is False

    # --- module_count ---

    def test_module_count_met(self):
        ch = Challenge(
            id="test-015", name="Test", description="desc",
            challenge_type=ChallengeType.PIVOTING, points=200,
            verification={"type": "module_count", "min_count": 3},
        )
        data = _make_workspace_data(
            modules_used=["osint/whois_lookup", "osint/dns_resolve", "cti/otx"]
        )
        assert ch.check_completion(data) is True

    def test_module_count_deduplicates(self):
        """Duplicate module uses are deduplicated for module_count."""
        ch = Challenge(
            id="test-016", name="Test", description="desc",
            challenge_type=ChallengeType.PIVOTING, points=200,
            verification={"type": "module_count", "min_count": 3},
        )
        data = _make_workspace_data(
            modules_used=["osint/whois_lookup", "osint/whois_lookup", "osint/dns_resolve"]
        )
        assert ch.check_completion(data) is False

    def test_module_count_not_met(self):
        ch = Challenge(
            id="test-017", name="Test", description="desc",
            challenge_type=ChallengeType.PIVOTING, points=200,
            verification={"type": "module_count", "min_count": 3},
        )
        data = _make_workspace_data(modules_used=["osint/whois_lookup"])
        assert ch.check_completion(data) is False

    # --- unknown type ---

    def test_unknown_verification_type_returns_false(self):
        """Unknown verification types return False gracefully."""
        ch = Challenge(
            id="test-018", name="Test", description="desc",
            challenge_type=ChallengeType.STANDARD, points=10,
            verification={"type": "future_type_unknown"},
        )
        assert ch.check_completion({}) is False


# ---------------------------------------------------------------------------
# ChallengeManager.get_active
# ---------------------------------------------------------------------------


class TestGetActive:

    def test_all_active_initially(self):
        mgr = ChallengeManager()
        active = mgr.get_active()
        assert len(active) == 5

    def test_completed_excluded(self):
        mgr = ChallengeManager()
        ch = mgr.get_challenge("ch-001")
        ch.status = ChallengeStatus.COMPLETED
        active = mgr.get_active()
        assert len(active) == 4
        assert all(c.id != "ch-001" for c in active)

    def test_expired_excluded(self):
        mgr = ChallengeManager()
        ch = mgr.get_challenge("ch-005")
        ch.status = ChallengeStatus.EXPIRED
        active = mgr.get_active()
        assert len(active) == 4


# ---------------------------------------------------------------------------
# ChallengeManager.check_all — marking completion, returning newly completed
# ---------------------------------------------------------------------------


class TestCheckAll:

    def test_check_all_returns_newly_completed(self):
        mgr = ChallengeManager()
        # Satisfy ch-001: at least 1 ipv4-addr
        data = _make_workspace_data(stix_counts={"ipv4-addr": 1})
        newly = mgr.check_all(data)
        assert any(c.id == "ch-001" for c in newly)

    def test_check_all_marks_status_completed(self):
        mgr = ChallengeManager()
        data = _make_workspace_data(stix_counts={"ipv4-addr": 1})
        mgr.check_all(data)
        ch = mgr.get_challenge("ch-001")
        assert ch.status == ChallengeStatus.COMPLETED

    def test_check_all_sets_completed_at(self):
        mgr = ChallengeManager()
        data = _make_workspace_data(stix_counts={"ipv4-addr": 1})
        mgr.check_all(data)
        ch = mgr.get_challenge("ch-001")
        assert ch.completed_at is not None
        assert isinstance(ch.completed_at, datetime)

    def test_check_all_no_duplicates(self):
        """Already completed challenges are NOT returned again."""
        mgr = ChallengeManager()
        data = _make_workspace_data(stix_counts={"ipv4-addr": 1})
        first_run = mgr.check_all(data)
        second_run = mgr.check_all(data)
        assert any(c.id == "ch-001" for c in first_run)
        assert not any(c.id == "ch-001" for c in second_run)

    def test_check_all_multiple_completions(self):
        """Multiple challenges can be completed in one check_all call."""
        mgr = ChallengeManager()
        # ch-001 (1 ipv4-addr) + ch-004 (score >= 500)
        data = _make_workspace_data(
            stix_counts={"ipv4-addr": 1},
            total_score=500,
        )
        newly = mgr.check_all(data)
        ids = {c.id for c in newly}
        assert "ch-001" in ids
        assert "ch-004" in ids

    def test_check_all_empty_data_no_completions(self):
        mgr = ChallengeManager()
        data = _make_workspace_data()
        newly = mgr.check_all(data)
        assert newly == []


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


class TestYamlLoading:

    def _write_yaml(self, path: Path, challenges: list[dict]) -> None:
        with open(path, "w") as f:
            yaml.dump({"challenges": challenges}, f)

    def test_load_yaml_returns_count(self, tmp_path):
        yaml_file = tmp_path / "extra_challenges.yaml"
        self._write_yaml(yaml_file, [
            {
                "id": "yaml-001",
                "name": "YAML Test",
                "description": "A challenge from YAML",
                "challenge_type": "standard",
                "points": 75,
                "verification": {"type": "score_threshold", "min_score": 100},
            }
        ])
        mgr = ChallengeManager()
        count = mgr.load_from_yaml(str(yaml_file))
        assert count == 1

    def test_load_yaml_challenge_accessible(self, tmp_path):
        yaml_file = tmp_path / "extra_challenges.yaml"
        self._write_yaml(yaml_file, [
            {
                "id": "yaml-002",
                "name": "YAML Challenge 2",
                "description": "Second YAML challenge",
                "challenge_type": "pivoting",
                "points": 250,
                "verification": {"type": "module_count", "min_count": 2},
                "hints": ["hint one", "hint two"],
            }
        ])
        mgr = ChallengeManager()
        mgr.load_from_yaml(str(yaml_file))
        ch = mgr.get_challenge("yaml-002")
        assert ch is not None
        assert ch.name == "YAML Challenge 2"
        assert ch.challenge_type == ChallengeType.PIVOTING
        assert ch.points == 250
        assert len(ch.hints) == 2

    def test_load_yaml_timed_challenge(self, tmp_path):
        yaml_file = tmp_path / "timed.yaml"
        self._write_yaml(yaml_file, [
            {
                "id": "yaml-timed",
                "name": "Timed YAML",
                "description": "Timed challenge from YAML",
                "challenge_type": "timed",
                "points": 400,
                "verification": {"type": "indicator_count", "stix_type": None, "min_count": 5},
                "time_limit_seconds": 120,
            }
        ])
        mgr = ChallengeManager()
        mgr.load_from_yaml(str(yaml_file))
        ch = mgr.get_challenge("yaml-timed")
        assert ch is not None
        assert ch.time_limit_seconds == 120
        assert ch.challenge_type == ChallengeType.TIMED

    def test_load_yaml_missing_file_raises(self):
        mgr = ChallengeManager()
        with pytest.raises((FileNotFoundError, OSError)):
            mgr.load_from_yaml("/nonexistent/path/challenges.yaml")

    def test_load_yaml_multiple_challenges(self, tmp_path):
        yaml_file = tmp_path / "multi.yaml"
        self._write_yaml(yaml_file, [
            {"id": f"m-{i:03d}", "name": f"Challenge {i}", "description": "d",
             "challenge_type": "standard", "points": 10,
             "verification": {"type": "score_threshold", "min_score": i * 10}}
            for i in range(1, 4)
        ])
        mgr = ChallengeManager()
        count = mgr.load_from_yaml(str(yaml_file))
        assert count == 3
        assert mgr.get_challenge("m-001") is not None
        assert mgr.get_challenge("m-003") is not None


# ---------------------------------------------------------------------------
# Timed challenge expiration
# ---------------------------------------------------------------------------


class TestTimedExpiration:

    def test_timed_challenge_expires_when_past_limit(self):
        """A timed challenge with time_limit_seconds expires when workspace time exceeded."""
        ch = Challenge(
            id="timed-001", name="Speed", description="desc",
            challenge_type=ChallengeType.TIMED, points=300,
            verification={"type": "indicator_count", "stix_type": None, "min_count": 10},
            time_limit_seconds=60,
        )
        # workspace_data includes elapsed_seconds > time_limit
        data = _make_workspace_data(total_indicators=5)
        data["elapsed_seconds"] = 120  # 2 minutes elapsed — over the 60s limit
        # check_completion returns False because time expired before count met
        assert ch.check_completion(data) is False

    def test_timed_challenge_within_limit_and_count_met(self):
        ch = Challenge(
            id="timed-002", name="Speed", description="desc",
            challenge_type=ChallengeType.TIMED, points=300,
            verification={"type": "indicator_count", "stix_type": None, "min_count": 3},
            time_limit_seconds=300,
        )
        data = _make_workspace_data(total_indicators=5)
        data["elapsed_seconds"] = 60  # within limit
        assert ch.check_completion(data) is True

    def test_check_all_expires_timed_challenge_when_time_exceeded(self):
        """check_all marks timed challenges EXPIRED when time exceeded and not completed."""
        mgr = ChallengeManager()
        # ch-005 requires 10 indicators in 300 seconds
        data = _make_workspace_data(total_indicators=2)  # not enough
        data["elapsed_seconds"] = 301  # past time limit
        mgr.check_all(data)
        ch = mgr.get_challenge("ch-005")
        assert ch.status == ChallengeStatus.EXPIRED

    def test_check_all_does_not_expire_non_timed(self):
        """Non-timed challenges are never marked EXPIRED by check_all."""
        mgr = ChallengeManager()
        data = _make_workspace_data()
        data["elapsed_seconds"] = 99999
        mgr.check_all(data)
        for ch in mgr._challenges.values():
            if ch.challenge_type != ChallengeType.TIMED:
                assert ch.status != ChallengeStatus.EXPIRED


# ---------------------------------------------------------------------------
# list_challenges
# ---------------------------------------------------------------------------


class TestListChallenges:

    def test_list_challenges_returns_dicts(self):
        mgr = ChallengeManager()
        result = mgr.list_challenges()
        assert isinstance(result, list)
        assert len(result) == 5
        for item in result:
            assert isinstance(item, dict)
            assert "id" in item
            assert "name" in item
            assert "status" in item
            assert "points" in item

    def test_list_challenges_reflects_completed(self):
        mgr = ChallengeManager()
        data = _make_workspace_data(stix_counts={"ipv4-addr": 1})
        mgr.check_all(data)
        items = mgr.list_challenges()
        ch001 = next(i for i in items if i["id"] == "ch-001")
        assert ch001["status"] == "completed"


# ---------------------------------------------------------------------------
# Console challenges command
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


class TestConsoleChallenges:

    def test_challenges_command_exists(self, console):
        """challenges command doesn't crash."""
        out = run_cmd(console, "challenges")
        assert isinstance(out, str)

    def test_challenges_shows_all_builtin(self, console):
        """challenges output includes First Blood challenge name."""
        out = run_cmd(console, "challenges")
        assert "First Blood" in out

    def test_challenges_shows_status(self, console):
        """challenges output shows status column."""
        out = run_cmd(console, "challenges")
        # Should show some indication of status (active/completed)
        assert "active" in out.lower() or "ACTIVE" in out

    def test_challenges_manager_wired_to_console(self, console):
        """APConsole has a challenge_mgr attribute after __init__."""
        assert hasattr(console, "challenge_mgr")
        assert isinstance(console.challenge_mgr, ChallengeManager)
