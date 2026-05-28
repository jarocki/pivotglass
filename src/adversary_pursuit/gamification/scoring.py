"""Parabolic decay scoring engine (CTFd model).

Formula: value = ((minimum - initial) / decay^2) * solve_count^2 + initial

Points decrease as more analysts find the same indicator (dynamic scoring).
For v1, solve_count tracks how many times the same STIX type has been discovered
in the current workspace.

@decision DEC-SCORING-001
@title CTFd parabolic decay formula for dynamic scoring
@status accepted
@rationale Proven formula from CTFd that self-balances difficulty valuation.
           Common indicators (IPs) lose value as more are found. Rare discoveries
           (campaigns, tools) maintain high value. The three parameters (initial,
           minimum, decay) are configurable per action type. The formula is clamped
           to [minimum, initial] to prevent underflow or negative points.

@decision DEC-SCORING-002
@title solve_count uses per-STIX-type workspace counts, not per-indicator counts
@status accepted
@rationale Counting per-indicator (e.g., this exact IP) would never decay — each
           new IP would always score at initial. Counting per-type (all IPs in
           workspace) models the real game mechanic: as you accumulate more of a
           type, each additional discovery is worth less. This incentivizes pivot
           diversity (finding new types) over depth (more of the same type).

@decision DEC-63-STREAK-SCORE-001
@title streak_continued ScoreEvent with three-tier step decay; prevents farming
@status accepted
@rationale A flat per-day bonus would be farmable (many short sessions to keep
           a streak running). Three tiers (10pts days 1-7, 5pts days 8-30, 2pts
           day 31+) reward early streak building but plateau quickly so grinding
           the streak for points becomes uneconomical. current_streak is the post-
           update value returned by StreakManager.update() (StreakUpdate.current_streak).
           Callers emit the event only when StreakUpdate.incremented=True so same-day
           idempotency and backward-clock clamp paths produce no event.
           StreakManager remains the sole ~/.ap/streak.json authority (DEC-62-STREAK-001);
           this file only defines the scoring calculation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScoringRule:
    """Defines scoring for an action type.

    Parameters
    ----------
    action:
        Canonical action key (e.g. "new_ip", "adversary_linked").
    initial:
        Starting point value awarded at solve_count=0.
    minimum:
        Floor value — points never fall below this.
    decay:
        Controls how quickly value decays. At solve_count == decay,
        points reach minimum exactly (via the parabolic formula).
    description:
        Human-readable label shown in score displays.
    """

    action: str
    initial: int
    minimum: int
    decay: int
    description: str


# Default scoring rules from MASTER_PLAN.md scoring table.
# Ordered from common (low value) to rare (high value).
DEFAULT_RULES: list[ScoringRule] = [
    ScoringRule("new_ip", initial=100, minimum=10, decay=10, description="New IP discovered"),
    ScoringRule(
        "new_domain", initial=100, minimum=10, decay=10, description="New domain discovered"
    ),
    ScoringRule("new_url", initial=50, minimum=5, decay=10, description="New URL discovered"),
    ScoringRule("new_email", initial=50, minimum=5, decay=10, description="New email discovered"),
    ScoringRule(
        "adversary_mistake", initial=10, minimum=5, decay=5, description="Adversary mistake found"
    ),
    ScoringRule(
        "deception_uncovered", initial=200, minimum=50, decay=5, description="Deception uncovered"
    ),
    ScoringRule(
        "adversary_linked", initial=500, minimum=100, decay=3, description="Adversary linked"
    ),
    ScoringRule("new_tool", initial=500, minimum=100, decay=3, description="New tool discovered"),
    ScoringRule(
        "campaign_described",
        initial=1000,
        minimum=200,
        decay=2,
        description="Campaign described with IOCs and TTPs",
    ),
]


def calculate_points(rule: ScoringRule, solve_count: int) -> int:
    """Calculate points using the CTFd parabolic decay formula.

    Formula::

        value = ((minimum - initial) / decay^2) * solve_count^2 + initial

    The result is clamped to [minimum, initial] to prevent going below the
    floor or above the starting value.

    Parameters
    ----------
    rule:
        The ScoringRule defining initial, minimum, and decay parameters.
    solve_count:
        How many times this type has been found in the workspace.
        Values <= 0 return the initial (maximum) value.

    Returns
    -------
    int
        Points awarded — always in [rule.minimum, rule.initial].
    """
    if solve_count <= 0:
        return rule.initial
    value = ((rule.minimum - rule.initial) / (rule.decay**2)) * (solve_count**2) + rule.initial
    return max(rule.minimum, min(rule.initial, int(value)))


# Maps STIX 2.1 SCO types to scoring action names.
_STIX_TYPE_TO_ACTION: dict[str, str] = {
    "ipv4-addr": "new_ip",
    "ipv6-addr": "new_ip",
    "domain-name": "new_domain",
    "url": "new_url",
    "email-addr": "new_email",
}


class ScoringEngine:
    """Tracks scores per workspace session.

    Observes module results and awards points based on what was discovered.
    Score events are persisted in the workspace database (score_events table)
    via WorkspaceManager.store_score_events().

    Usage
    -----
    engine = ScoringEngine()
    stats = workspace_mgr.get_stix_type_counts()
    events = engine.score_results(hunt_results, stats)
    total = engine.total_score(events)
    workspace_mgr.store_score_events(events)
    """

    def __init__(self, rules: list[ScoringRule] | None = None) -> None:
        """Initialise with optional custom rules (defaults to DEFAULT_RULES).

        Parameters
        ----------
        rules:
            Override the default scoring rules. Pass None to use DEFAULT_RULES.
            Rules are indexed by action name for O(1) lookup.
        """
        self.rules: dict[str, ScoringRule] = {r.action: r for r in (rules or DEFAULT_RULES)}

    def score_results(self, results: list[dict], workspace_stats: dict[str, int]) -> list[dict]:
        """Score a list of STIX result dicts from a module hunt() call.

        Maps each result's STIX type to a scoring action, computes points
        using parabolic decay with the current workspace type counts, and
        returns a list of scoring event dicts ready for persistence.

        Parameters
        ----------
        results:
            STIX dicts from a module hunt() call.
            Each dict must have a "type" key (e.g. "ipv4-addr") and optionally
            a "value" key for the indicator string.
        workspace_stats:
            Dict mapping STIX types to their current count in the workspace.
            e.g., {"ipv4-addr": 15, "domain-name": 8}. Obtained via
            WorkspaceManager.get_stix_type_counts(). Types not present are
            treated as 0 (no prior discoveries).

        Returns
        -------
        list[dict]
            Scoring events, one per recognized result::

                [
                    {
                        "action": "new_ip",
                        "points": 95,
                        "indicator": "1.2.3.4",
                        "rule_description": "New IP discovered",
                    },
                    ...
                ]
        """
        events = []
        for result in results:
            stix_type = result.get("type", "")
            indicator = result.get("value", "")
            action = _STIX_TYPE_TO_ACTION.get(stix_type)
            if action is None or action not in self.rules:
                continue
            rule = self.rules[action]
            count = workspace_stats.get(stix_type, 0)
            points = calculate_points(rule, count)
            events.append(
                {
                    "action": action,
                    "points": points,
                    "indicator": indicator,
                    "rule_description": rule.description,
                }
            )
        return events

    def total_score(self, scoring_events: list[dict]) -> int:
        """Sum points from a list of scoring events.

        Parameters
        ----------
        scoring_events:
            List of dicts with a "points" key, as returned by score_results().

        Returns
        -------
        int
            Total points.
        """
        return sum(e.get("points", 0) for e in scoring_events)

    def get_rules(self) -> list[ScoringRule]:
        """Return all configured scoring rules.

        Returns
        -------
        list[ScoringRule]
            All rules this engine knows about.
        """
        return list(self.rules.values())


def streak_continued_points(current_streak: int) -> int:
    """Return the streak_continued bonus points for the given streak day.

    Three-tier step decay (DEC-63-STREAK-SCORE-001):
    - Days 1-7:  10 points  (early streak building — highest reward)
    - Days 8-30: 5 points   (sustained engagement — moderate reward)
    - Day 31+:   2 points   (long-term habit — minimal to prevent farming)

    Parameters
    ----------
    current_streak:
        The current_streak value from StreakUpdate after a successful hunt.
        Must be >= 1 (callers only invoke this when incremented=True).

    Returns
    -------
    int
        Points to award for the streak_continued event.
    """
    if current_streak <= 7:
        return 10
    if current_streak <= 30:
        return 5
    return 2


def make_streak_continued_event(current_streak: int) -> dict:
    """Build a streak_continued score event dict ready for store_score_events().

    Parameters
    ----------
    current_streak:
        Current streak length after the successful hunt.

    Returns
    -------
    dict
        Score event with keys: action, points, indicator, rule_description.
    """
    points = streak_continued_points(current_streak)
    return {
        "action": "streak_continued",
        "points": points,
        "indicator": f"day-{current_streak}",
        "rule_description": f"Streak continued (day {current_streak})",
    }
