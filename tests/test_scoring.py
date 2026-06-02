"""Tests for Issue #14: Gamification Scoring System (Parabolic Decay).

Tests cover:
- calculate_points formula correctness (edge cases: 0, 1, large, negative)
- Default ScoringRule definitions (all 9 rules present)
- ScoringEngine.score_results: STIX type mapping, unknown types, decay behavior
- ScoringEngine.total_score: summation
- WorkspaceManager score integration: store, retrieve, totals, ordering
- Console integration: score command, run command displays points

Production sequence:
  module.hunt() returns plain dicts → _execute_hunt() calls score_results()
  → store_score_events() → do_score() reads get_total_score().

@decision DEC-TEST-014
@title Scoring tests cover formula, integration, and production console sequence
@status accepted
@rationale The scoring system must be verified at three levels: (1) pure formula
           math to catch off-by-one in the parabolic decay, (2) workspace persistence
           layer to verify score events survive across calls, and (3) console integration
           to confirm the actual user-facing flow works end-to-end.
"""

from __future__ import annotations

import io

import pytest

from adversary_pursuit.core.console import APConsole
from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.gamification.scoring import (
    DEFAULT_RULES,
    ScoringEngine,
    ScoringRule,
    calculate_points,
    make_streak_continued_event,
    streak_continued_points,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine():
    """Fresh ScoringEngine with default rules."""
    return ScoringEngine()


@pytest.fixture
def workspace(tmp_path):
    """WorkspaceManager backed by a temp directory with 'default' active."""
    wm = WorkspaceManager(workspace_dir=tmp_path)
    wm.create("default")
    wm.switch("default")
    return wm


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
# calculate_points — formula tests
# ---------------------------------------------------------------------------


class TestCalculatePoints:
    """Verify the parabolic decay formula: value = ((min - init) / decay^2) * count^2 + init"""

    def test_solve_count_zero_returns_initial(self):
        """At solve_count=0, no decay has occurred — returns initial value."""
        rule = ScoringRule("new_ip", initial=100, minimum=10, decay=10, description="test")
        assert calculate_points(rule, 0) == 100

    def test_solve_count_negative_returns_initial(self):
        """Negative solve_count (invalid) is treated as zero — returns initial."""
        rule = ScoringRule("new_ip", initial=100, minimum=10, decay=10, description="test")
        assert calculate_points(rule, -5) == 100

    def test_solve_count_one_less_than_initial(self):
        """At solve_count=1, value decreases slightly from initial."""
        rule = ScoringRule("new_ip", initial=100, minimum=10, decay=10, description="test")
        pts = calculate_points(rule, 1)
        # Formula: ((10 - 100) / 100) * 1 + 100 = -0.9 + 100 = 99.1 → int = 99
        assert pts < 100
        assert pts >= 10

    def test_solve_count_at_decay_hits_minimum(self):
        """At solve_count == decay, formula reaches minimum exactly."""
        rule = ScoringRule("new_ip", initial=100, minimum=10, decay=10, description="test")
        pts = calculate_points(rule, 10)
        # Formula: ((10 - 100) / 100) * 100 + 100 = -90 + 100 = 10
        assert pts == 10

    def test_large_solve_count_clamps_to_minimum(self):
        """Very high solve_count cannot go below minimum (clamped)."""
        rule = ScoringRule("new_ip", initial=100, minimum=10, decay=10, description="test")
        pts = calculate_points(rule, 1000)
        assert pts == 10

    def test_result_is_always_integer(self):
        """calculate_points always returns an int."""
        rule = ScoringRule("new_ip", initial=100, minimum=10, decay=10, description="test")
        for count in range(0, 15):
            result = calculate_points(rule, count)
            assert isinstance(result, int), f"Expected int at count={count}, got {type(result)}"

    def test_result_always_within_bounds(self):
        """Points always stay in [minimum, initial] regardless of count."""
        rule = ScoringRule("new_ip", initial=100, minimum=10, decay=10, description="test")
        for count in range(0, 50):
            pts = calculate_points(rule, count)
            assert rule.minimum <= pts <= rule.initial, f"Out of bounds at count={count}: {pts}"

    def test_decay_is_monotonically_non_increasing(self):
        """Points never increase as solve_count increases."""
        rule = ScoringRule("new_ip", initial=100, minimum=10, decay=10, description="test")
        prev = calculate_points(rule, 0)
        for count in range(1, 15):
            curr = calculate_points(rule, count)
            assert curr <= prev, f"Points increased at count={count}: {prev} → {curr}"
            prev = curr

    def test_adversary_linked_high_value_slow_decay(self):
        """adversary_linked (500 initial, 100 min, decay=3) decays slowly."""
        rule = ScoringRule(
            "adversary_linked", initial=500, minimum=100, decay=3, description="test"
        )
        pts_at_1 = calculate_points(rule, 1)
        pts_at_3 = calculate_points(rule, 3)
        # At decay=3, count=3 should hit minimum
        assert pts_at_3 == 100
        assert pts_at_1 > 100

    def test_campaign_described_highest_value(self):
        """campaign_described (1000 initial, 200 min, decay=2) floors at 200."""
        rule = ScoringRule(
            "campaign_described", initial=1000, minimum=200, decay=2, description="test"
        )
        pts = calculate_points(rule, 100)
        assert pts == 200


# ---------------------------------------------------------------------------
# DEFAULT_RULES — all 9 rules present
# ---------------------------------------------------------------------------


class TestDefaultRules:
    """Verify all 9 default scoring rules exist with correct parameters."""

    def test_all_nine_rules_present(self):
        """All 9 expected action types are in DEFAULT_RULES."""
        expected_actions = {
            "new_ip",
            "new_domain",
            "new_url",
            "new_email",
            "adversary_mistake",
            "deception_uncovered",
            "adversary_linked",
            "new_tool",
            "campaign_described",
        }
        actual_actions = {r.action for r in DEFAULT_RULES}
        assert expected_actions == actual_actions

    def test_new_ip_parameters(self):
        """new_ip rule has M-3 re-tuned parameters (DEC-M3-DOSSIER-004).

        M-3 re-tune: initial=1, minimum=1, decay=10 (decay preserved for rollback).
        """
        rule = next(r for r in DEFAULT_RULES if r.action == "new_ip")
        assert rule.initial == 1  # M-3: baseline 1.0 per DEC-M3-DOSSIER-004
        assert rule.minimum == 1  # M-3: collapsed to baseline
        assert rule.decay == 10  # preserved: mathematically inert but kept for rollback

    def test_campaign_described_parameters(self):
        """campaign_described rule has M-3 re-tuned parameters (DEC-M3-DOSSIER-004).

        M-3 re-tune: initial=1, minimum=1, decay=2 (decay preserved).
        """
        rule = next(r for r in DEFAULT_RULES if r.action == "campaign_described")
        assert rule.initial == 1  # M-3: baseline 1.0
        assert rule.minimum == 1  # M-3: collapsed to baseline
        assert rule.decay == 2  # preserved: fast decay shape (inert under initial==minimum)

    def test_adversary_linked_parameters(self):
        """adversary_linked rule has M-3 re-tuned parameters (DEC-M3-DOSSIER-004).

        M-3 re-tune: initial=1, minimum=1, decay=3 (decay preserved).
        """
        rule = next(r for r in DEFAULT_RULES if r.action == "adversary_linked")
        assert rule.initial == 1  # M-3: baseline 1.0
        assert rule.minimum == 1  # M-3: collapsed to baseline
        assert rule.decay == 3  # preserved: tight decay shape (inert under initial==minimum)

    def test_all_rules_have_descriptions(self):
        """Every rule must have a non-empty description."""
        for r in DEFAULT_RULES:
            assert r.description, f"Rule '{r.action}' has no description"

    def test_all_rules_have_positive_values(self):
        """All rules must have positive initial, minimum, and decay."""
        for r in DEFAULT_RULES:
            assert r.initial > 0, f"Rule '{r.action}' initial <= 0"
            assert r.minimum > 0, f"Rule '{r.action}' minimum <= 0"
            assert r.decay > 0, f"Rule '{r.action}' decay <= 0"
            assert r.initial >= r.minimum, f"Rule '{r.action}' initial < minimum"


# ---------------------------------------------------------------------------
# ScoringEngine.score_results — STIX type mapping
# ---------------------------------------------------------------------------


class TestScoringEngineScoreResults:
    """Verify score_results maps STIX types → scoring actions correctly."""

    def test_ipv4_addr_scores_as_new_ip(self, engine):
        """ipv4-addr maps to new_ip; M-3 re-tune: points=1 at any solve_count."""
        results = [{"type": "ipv4-addr", "value": "1.2.3.4"}]
        events = engine.score_results(results, {})
        assert len(events) == 1
        assert events[0]["action"] == "new_ip"
        assert events[0]["indicator"] == "1.2.3.4"
        assert events[0]["points"] == 1  # M-3 re-tune: initial=minimum=1

    def test_ipv6_addr_scores_as_new_ip(self, engine):
        results = [{"type": "ipv6-addr", "value": "::1"}]
        events = engine.score_results(results, {})
        assert len(events) == 1
        assert events[0]["action"] == "new_ip"

    def test_domain_name_scores_as_new_domain(self, engine):
        """domain-name maps to new_domain; M-3 re-tune: points=1."""
        results = [{"type": "domain-name", "value": "evil.com"}]
        events = engine.score_results(results, {})
        assert len(events) == 1
        assert events[0]["action"] == "new_domain"
        assert events[0]["points"] == 1  # M-3 re-tune: initial=minimum=1

    def test_url_scores_as_new_url(self, engine):
        """url maps to new_url; M-3 re-tune: points=1."""
        results = [{"type": "url", "value": "https://evil.com/payload"}]
        events = engine.score_results(results, {})
        assert len(events) == 1
        assert events[0]["action"] == "new_url"
        assert events[0]["points"] == 1  # M-3 re-tune: initial=minimum=1

    def test_email_addr_scores_as_new_email(self, engine):
        """email-addr maps to new_email; M-3 re-tune: points=1."""
        results = [{"type": "email-addr", "value": "threat@example.com"}]
        events = engine.score_results(results, {})
        assert len(events) == 1
        assert events[0]["action"] == "new_email"
        assert events[0]["points"] == 1  # M-3 re-tune: initial=minimum=1

    def test_unrecognized_type_produces_no_event(self, engine):
        """STIX types not in the mapping (e.g. relationship) produce no scoring event."""
        results = [{"type": "x-custom-indicator", "value": "something"}]
        events = engine.score_results(results, {})
        assert events == []

    def test_relationship_type_skipped(self, engine):
        """Relationship SROs are not scored."""
        results = [{"type": "relationship", "value": ""}]
        events = engine.score_results(results, {})
        assert events == []

    def test_multiple_results_produce_multiple_events(self, engine):
        """Multiple results produce one event each."""
        results = [
            {"type": "ipv4-addr", "value": "1.1.1.1"},
            {"type": "domain-name", "value": "example.com"},
            {"type": "url", "value": "https://example.com/evil"},
        ]
        events = engine.score_results(results, {})
        assert len(events) == 3

    def test_mixed_recognized_and_unknown_types(self, engine):
        """Only recognized types are scored; unknown types are silently skipped."""
        results = [
            {"type": "ipv4-addr", "value": "1.2.3.4"},
            {"type": "x-unknown", "value": "mystery"},
            {"type": "domain-name", "value": "example.com"},
        ]
        events = engine.score_results(results, {})
        assert len(events) == 2
        actions = {e["action"] for e in events}
        assert actions == {"new_ip", "new_domain"}

    def test_each_event_has_required_fields(self, engine):
        """Every scoring event contains action, points, indicator, rule_description."""
        results = [{"type": "ipv4-addr", "value": "8.8.8.8"}]
        events = engine.score_results(results, {})
        event = events[0]
        assert "action" in event
        assert "points" in event
        assert "indicator" in event
        assert "rule_description" in event

    def test_points_decrease_with_higher_workspace_stats(self, engine):
        """M-3 re-tune: decay is inert (initial == minimum == 1), so points are always 1.

        Under DEC-M3-DOSSIER-004, initial == minimum for all per-IOC rules, making the
        parabolic decay formula mathematically inert — points are always 1 regardless of
        solve_count. This test was updated from the v1 assertion (pts_fresh > pts_saturated)
        to the M-3 invariant (pts_fresh == pts_saturated == 1).

        Use a custom engine with v1 rules to verify the formula still decays if a caller
        ever passes non-baseline rules.
        """
        results = [{"type": "ipv4-addr", "value": "5.5.5.5"}]
        # With M-3 default rules, both calls return 1 (inert decay)
        events_fresh = engine.score_results(results, {"ipv4-addr": 0})
        events_saturated = engine.score_results(results, {"ipv4-addr": 10})
        pts_fresh = events_fresh[0]["points"]
        pts_saturated = events_saturated[0]["points"]
        assert pts_fresh == 1, f"M-3 re-tune: fresh new_ip must be 1; got {pts_fresh}"
        assert pts_saturated == 1, f"M-3 re-tune: saturated new_ip must be 1; got {pts_saturated}"
        # Verify the formula still works with non-baseline rules (v1 values)
        from adversary_pursuit.gamification.scoring import ScoringEngine, ScoringRule

        v1_engine = ScoringEngine(
            rules=[ScoringRule("new_ip", initial=100, minimum=10, decay=10, description="v1")]
        )
        v1_fresh = v1_engine.score_results(results, {"ipv4-addr": 0})[0]["points"]
        v1_saturated = v1_engine.score_results(results, {"ipv4-addr": 10})[0]["points"]
        assert v1_fresh > v1_saturated, "v1 rules must decay (formula test)"

    def test_empty_results_returns_empty_events(self, engine):
        """No results → no scoring events."""
        events = engine.score_results([], {})
        assert events == []


# ---------------------------------------------------------------------------
# ScoringEngine.total_score
# ---------------------------------------------------------------------------


class TestScoringEngineTotalScore:
    """Verify total_score sums scoring event points."""

    def test_total_score_empty(self, engine):
        assert engine.total_score([]) == 0

    def test_total_score_single(self, engine):
        events = [{"action": "new_ip", "points": 95, "indicator": "1.2.3.4"}]
        assert engine.total_score(events) == 95

    def test_total_score_multiple(self, engine):
        events = [
            {"action": "new_ip", "points": 100, "indicator": "1.2.3.4"},
            {"action": "new_domain", "points": 80, "indicator": "evil.com"},
            {"action": "new_url", "points": 50, "indicator": "http://evil.com"},
        ]
        assert engine.total_score(events) == 230

    def test_total_score_via_score_results(self, engine):
        """End-to-end: score_results → total_score gives correct sum (M-3 re-tune).

        M-3 re-tune: new_ip=1, new_domain=1 → total=2 (DEC-M3-DOSSIER-004).
        """
        results = [
            {"type": "ipv4-addr", "value": "1.2.3.4"},
            {"type": "domain-name", "value": "evil.com"},
        ]
        events = engine.score_results(results, {})
        total = engine.total_score(events)
        # M-3 re-tune: new_ip initial=1, new_domain initial=1 → total=2
        assert total == 2


# ---------------------------------------------------------------------------
# ScoringEngine.get_rules
# ---------------------------------------------------------------------------


class TestScoringEngineGetRules:
    """Verify get_rules returns all configured rules."""

    def test_get_rules_returns_list(self, engine):
        rules = engine.get_rules()
        assert isinstance(rules, list)

    def test_get_rules_contains_all_defaults(self, engine):
        rules = engine.get_rules()
        assert len(rules) == len(DEFAULT_RULES)

    def test_custom_rules_respected(self):
        custom = [
            ScoringRule("custom_action", initial=999, minimum=1, decay=5, description="custom")
        ]
        eng = ScoringEngine(rules=custom)
        rules = eng.get_rules()
        assert len(rules) == 1
        assert rules[0].action == "custom_action"


# ---------------------------------------------------------------------------
# WorkspaceManager score integration
# ---------------------------------------------------------------------------


class TestWorkspaceScoreIntegration:
    """Verify score events are persisted in and retrieved from the workspace DB."""

    def test_store_score_events_returns_total_points(self, workspace):
        events = [
            {
                "action": "new_ip",
                "points": 100,
                "indicator": "1.2.3.4",
                "rule_description": "New IP",
            },
            {
                "action": "new_domain",
                "points": 80,
                "indicator": "evil.com",
                "rule_description": "New domain",
            },
        ]
        total = workspace.store_score_events(events)
        assert total == 180

    def test_get_total_score_empty_workspace(self, workspace):
        """Fresh workspace starts at 0."""
        assert workspace.get_total_score() == 0

    def test_get_total_score_after_storing(self, workspace):
        events = [
            {"action": "new_ip", "points": 100, "indicator": "1.2.3.4", "rule_description": "IP"},
        ]
        workspace.store_score_events(events)
        assert workspace.get_total_score() == 100

    def test_get_total_score_accumulates(self, workspace):
        """Multiple store calls accumulate into total score."""
        workspace.store_score_events(
            [
                {
                    "action": "new_ip",
                    "points": 100,
                    "indicator": "1.2.3.4",
                    "rule_description": "IP",
                },
            ]
        )
        workspace.store_score_events(
            [
                {
                    "action": "new_domain",
                    "points": 80,
                    "indicator": "evil.com",
                    "rule_description": "Domain",
                },
            ]
        )
        assert workspace.get_total_score() == 180

    def test_get_recent_scores_returns_events(self, workspace):
        events = [
            {"action": "new_ip", "points": 100, "indicator": "1.2.3.4", "rule_description": "IP"},
            {
                "action": "new_domain",
                "points": 80,
                "indicator": "evil.com",
                "rule_description": "Domain",
            },
        ]
        workspace.store_score_events(events)
        recent = workspace.get_recent_scores()
        assert len(recent) == 2

    def test_get_recent_scores_limit(self, workspace):
        """get_recent_scores respects limit parameter."""
        events = [
            {
                "action": "new_ip",
                "points": i * 10,
                "indicator": f"1.2.3.{i}",
                "rule_description": "IP",
            }
            for i in range(1, 6)
        ]
        workspace.store_score_events(events)
        recent = workspace.get_recent_scores(limit=3)
        assert len(recent) == 3

    def test_get_recent_scores_reverse_chronological(self, workspace):
        """Most recent events appear first in get_recent_scores."""
        workspace.store_score_events(
            [
                {"action": "new_ip", "points": 100, "indicator": "first", "rule_description": "IP"},
            ]
        )
        workspace.store_score_events(
            [
                {
                    "action": "new_domain",
                    "points": 80,
                    "indicator": "second",
                    "rule_description": "Domain",
                },
            ]
        )
        recent = workspace.get_recent_scores()
        # Most recent first
        assert recent[0]["indicator"] == "second"
        assert recent[1]["indicator"] == "first"

    def test_get_stix_type_counts_empty(self, workspace):
        """Fresh workspace returns empty dict from get_stix_type_counts."""
        counts = workspace.get_stix_type_counts()
        assert isinstance(counts, dict)
        # May be empty or have zeros
        assert counts.get("ipv4-addr", 0) == 0

    def test_get_stix_type_counts_after_storing(self, workspace):
        """get_stix_type_counts returns correct counts per STIX type."""
        workspace.store_stix_objects(
            [
                {"type": "ipv4-addr", "value": "1.2.3.4"},
                {"type": "ipv4-addr", "value": "5.6.7.8"},
                {"type": "domain-name", "value": "evil.com"},
            ],
            module_name="osint/test",
            target="1.2.3.4",
        )
        counts = workspace.get_stix_type_counts()
        assert counts["ipv4-addr"] == 2
        assert counts["domain-name"] == 1

    def test_get_stix_type_counts_after_dedup(self, workspace):
        """Deduplication is reflected in STIX type counts."""
        same_ip = {"type": "ipv4-addr", "value": "9.9.9.9"}
        workspace.store_stix_objects([same_ip], module_name="m1", target="9.9.9.9")
        workspace.store_stix_objects([same_ip], module_name="m2", target="9.9.9.9")
        counts = workspace.get_stix_type_counts()
        # Deduplicated — only 1 unique IP stored
        assert counts["ipv4-addr"] == 1

    def test_store_score_events_with_module_run_id(self, workspace):
        """store_score_events accepts optional module_run_id."""
        events = [
            {"action": "new_ip", "points": 100, "indicator": "1.2.3.4", "rule_description": "IP"}
        ]
        total = workspace.store_score_events(events, module_run_id=42)
        assert total == 100

    def test_score_events_isolated_per_workspace(self, tmp_path):
        """Score events are isolated to their workspace."""
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("alpha")
        wm.create("beta")

        wm.switch("alpha")
        wm.store_score_events(
            [{"action": "new_ip", "points": 500, "indicator": "alpha-ip", "rule_description": "IP"}]
        )

        wm.switch("beta")
        assert wm.get_total_score() == 0  # beta untouched


# ---------------------------------------------------------------------------
# Console integration
# ---------------------------------------------------------------------------


class TestConsoleScoreCommand:
    """Verify the score command shows real total score."""

    def test_score_command_shows_zero_on_fresh_workspace(self, console):
        """score command on fresh workspace shows 0."""
        out = run_cmd(console, "score")
        assert "0" in out

    def test_score_command_shows_total_after_run(self, console):
        """After a successful run, score command shows non-zero total."""
        run_cmd(console, "use osint/dns_resolve")
        run_cmd(console, "set TARGET example.com")
        run_cmd(console, "run")
        out = run_cmd(console, "score")
        # Total score should be positive (dns_resolve returns IPs/domains)
        assert out.strip()  # has some output
        # Score increased from 0 — look for a number > 0
        # The output should contain the score table or total
        assert "score" in out.lower() or any(c.isdigit() for c in out)

    def test_score_command_includes_recent_events(self, console):
        """score command output includes recent scoring events."""
        run_cmd(console, "use osint/dns_resolve")
        run_cmd(console, "set TARGET example.com")
        run_cmd(console, "run")
        out = run_cmd(console, "score")
        # Should show some events
        assert out.strip()

    def test_run_command_displays_points(self, console):
        """run command displays points earned after execution."""
        run_cmd(console, "use osint/dns_resolve")
        run_cmd(console, "set TARGET example.com")
        out = run_cmd(console, "run")
        # Should show point gain
        assert "point" in out.lower() or "+" in out

    def test_run_command_without_results_no_crash(self, console):
        """run with a target that returns no results does not crash."""
        run_cmd(console, "use osint/dns_resolve")
        run_cmd(console, "set TARGET 192.0.2.1")  # RFC 5737 — unlikely to resolve
        # Should not raise
        out = run_cmd(console, "run")
        assert isinstance(out, str)


# ---------------------------------------------------------------------------
# streak_continued_points — F63 DEC-63-STREAK-SCORE-001
# ---------------------------------------------------------------------------


class TestStreakContinuedPoints:
    """Verify the three-tier step decay for streak_continued bonus."""

    def test_day_1_returns_10(self):
        """Day 1 is in the 1-7 tier → 10 points."""
        assert streak_continued_points(1) == 10

    def test_day_7_returns_10(self):
        """Day 7 is the boundary of the top tier → still 10 points."""
        assert streak_continued_points(7) == 10

    def test_day_8_returns_5(self):
        """Day 8 crosses into the 8-30 tier → 5 points."""
        assert streak_continued_points(8) == 5

    def test_day_30_returns_5(self):
        """Day 30 is the boundary of the middle tier → 5 points."""
        assert streak_continued_points(30) == 5

    def test_day_31_returns_2(self):
        """Day 31 crosses into the 31+ tier → 2 points."""
        assert streak_continued_points(31) == 2

    def test_day_100_returns_2(self):
        """Very long streak stays at 2 points (anti-farming floor)."""
        assert streak_continued_points(100) == 2

    def test_three_tiers_are_distinct(self):
        """All three tier values are distinct (no accidental collisions)."""
        assert (
            len(
                {
                    streak_continued_points(1),
                    streak_continued_points(8),
                    streak_continued_points(31),
                }
            )
            == 3
        )


# ---------------------------------------------------------------------------
# make_streak_continued_event — F63
# ---------------------------------------------------------------------------


class TestMakeStreakContinuedEvent:
    """Verify make_streak_continued_event builds a well-formed score event dict."""

    def test_action_key(self):
        """Event has action='streak_continued'."""
        evt = make_streak_continued_event(1)
        assert evt["action"] == "streak_continued"

    def test_points_from_decay(self):
        """Points value matches streak_continued_points for the given streak."""
        for day in [1, 7, 8, 30, 31, 50]:
            evt = make_streak_continued_event(day)
            assert evt["points"] == streak_continued_points(day)

    def test_indicator_contains_day(self):
        """Indicator field encodes the streak day for display."""
        evt = make_streak_continued_event(5)
        assert "5" in evt["indicator"]

    def test_rule_description_present(self):
        """rule_description is a non-empty string."""
        evt = make_streak_continued_event(1)
        assert isinstance(evt["rule_description"], str)
        assert len(evt["rule_description"]) > 0

    def test_event_storable_by_workspace(self, tmp_path):
        """Event dict produced by make_streak_continued_event is accepted by store_score_events."""
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")
        evt = make_streak_continued_event(3)
        total = wm.store_score_events([evt])
        assert total == streak_continued_points(3)
        recent = wm.get_recent_scores(limit=1)
        assert recent[0]["action"] == "streak_continued"


# ---------------------------------------------------------------------------
# M-3 per-IOC re-tune assertions (Evaluation Contract §7.C)
# DEC-M3-DOSSIER-004: initial == minimum == 1 for all 9 SCO-mapped action keys.
# decay constants PRESERVED (mathematically inert but kept for clean rollback).
# streak_continued UNCHANGED (F62/F63).
# ---------------------------------------------------------------------------

# The 9 per-IOC SCO-mapped action keys that must be re-tuned to initial=minimum=1
_PER_IOC_ACTIONS = [
    "new_ip",
    "new_domain",
    "new_url",
    "new_email",
    "adversary_mistake",
    "deception_uncovered",
    "adversary_linked",
    "new_tool",
    "campaign_described",
]

# Expected decay constants from the M-3 re-tune table (per-slice plan §4)
_EXPECTED_DECAY: dict[str, int] = {
    "new_ip": 10,
    "new_domain": 10,
    "new_url": 10,
    "new_email": 10,
    "adversary_mistake": 5,
    "deception_uncovered": 5,
    "adversary_linked": 3,
    "new_tool": 3,
    "campaign_described": 2,
}


class TestM3PerIOCRetune:
    """M-3 DEFAULT_RULES re-tune: initial == minimum == 1 for all 9 SCO-mapped types."""

    def _get_rule(self, action: str) -> ScoringRule:
        """Look up a rule by action key from DEFAULT_RULES."""
        rule = next((r for r in DEFAULT_RULES if r.action == action), None)
        assert rule is not None, f"No rule for action {action!r} in DEFAULT_RULES"
        return rule

    def test_new_ip_initial_is_one_post_m3(self):
        """C19: new_ip.initial == 1 after M-3 re-tune."""
        assert self._get_rule("new_ip").initial == 1

    def test_new_ip_minimum_is_one_post_m3(self):
        """C20: new_ip.minimum == 1 after M-3 re-tune."""
        assert self._get_rule("new_ip").minimum == 1

    def test_all_per_ioc_rules_initial_one(self):
        """C21: Every SCO-mapped action key has initial == 1 (DEC-M3-DOSSIER-004)."""
        for action in _PER_IOC_ACTIONS:
            rule = self._get_rule(action)
            assert rule.initial == 1, (
                f"Expected initial=1 for {action!r} after M-3 re-tune; got {rule.initial}"
            )
            assert rule.minimum == 1, (
                f"Expected minimum=1 for {action!r} after M-3 re-tune; got {rule.minimum}"
            )

    def test_decay_constants_preserved_post_m3(self):
        """C22: Decay constants unchanged after M-3 re-tune (DEC-M3-DOSSIER-004)."""
        for action, expected_decay in _EXPECTED_DECAY.items():
            rule = self._get_rule(action)
            assert rule.decay == expected_decay, (
                f"Expected decay={expected_decay} for {action!r}; got {rule.decay}"
            )

    def test_streak_continued_unchanged_post_m3(self):
        """C23: streak_continued step-decay unchanged under M-3 (F62/F63 invariant)."""
        assert streak_continued_points(1) == 10, "Day 1-7 streak: must be 10 pts"
        assert streak_continued_points(7) == 10, "Day 7: must still be 10 pts"
        assert streak_continued_points(8) == 5, "Day 8: drops to 5 pts"
        assert streak_continued_points(30) == 5, "Day 30: must still be 5 pts"
        assert streak_continued_points(31) == 2, "Day 31+: drops to 2 pts"

    def test_per_ioc_score_always_returns_one(self):
        """With initial == minimum == 1, calculate_points returns 1 regardless of solve_count."""
        for action in _PER_IOC_ACTIONS:
            rule = self._get_rule(action)
            # At solve_count 0, 1, decay, 100 — must all return 1
            for count in [0, 1, rule.decay, 100]:
                pts = calculate_points(rule, count)
                assert pts == 1, f"{action!r} at solve_count={count}: expected 1, got {pts}"

    def test_default_rules_contains_all_nine_per_ioc_actions(self):
        """All 9 SCO-mapped action keys are present in DEFAULT_RULES."""
        rule_actions = {r.action for r in DEFAULT_RULES}
        for action in _PER_IOC_ACTIONS:
            assert action in rule_actions, f"Missing rule for {action!r} in DEFAULT_RULES"
