"""Celebration system — ASCII art and milestone messages for achievements.

Provides visual celebrations when analysts discover indicators, reach
score milestones, or earn their first discovery in a workspace.

@decision DEC-CELEBRATION-001
@title Four-level ASCII art system keyed on points earned per action
@status accepted
@rationale Points earned in a single run determine celebration intensity:
           small (<50), medium (50-199), large (200-499), epic (500+).
           This maps naturally to the scoring rules — a single IP discovery
           (100pts base) gets medium, a campaign description (1000pts) gets epic.
           ASCII art is randomized within each level to avoid repetition.

@decision DEC-CELEBRATION-002
@title Exact-threshold milestone fire — milestones triggered only at exact score match
@status superseded
@rationale Superseded by DEC-63-MILESTONE-CATCHUP-001 (cross-threshold + idempotency).
           Original rationale: milestones (First Century, etc.) fired only at exact
           thresholds — jumping 99→105 silently skipped First Century forever.
           DEC-63 replaced this with cross-threshold checks and a last_milestone_announced
           sentinel persistence. See MASTER_PLAN.md Phase 12C for the supersession record.

@decision DEC-63-MILESTONE-CATCHUP-001
@title Cross-threshold milestone semantics with idempotent last_announced sentinel
@status accepted
@rationale DEC-CELEBRATION-002 (exact-score-only check) is superseded. The old
           design silently skipped milestones when a run's points jumped past a
           threshold (e.g. score went 80 → 620 in one run — the 100 and 500
           milestones were never announced). The new design uses check_milestones()
           which evaluates ALL milestones in ascending order and returns every
           milestone whose threshold <= total_score AND whose id > last_announced.
           The caller persists last_announced via WorkspaceManager.set_last_milestone_id()
           so the check is idempotent across calls — a milestone never fires twice.
           Milestones are stored as a list[MilestoneSpec] with stable integer IDs so
           WorkspaceManager can persist a single integer sentinel (no schema change).
           Quiet-start migration: callers with an existing score and null
           last_announced_id should initialise last_announced_id to the highest
           already-crossed milestone (suppresses retroactive announcements that
           would lie about WHEN milestones were earned). See DEC-63-MIGRATION-001.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class MilestoneSpec:
    """A single score milestone definition.

    Parameters
    ----------
    id:
        Stable integer identifier. IDs are assigned in ascending threshold
        order so ``id > last_announced_id`` is the correct catch-up predicate.
        See DEC-63-MILESTONE-CATCHUP-001.
    threshold:
        Total workspace score at which this milestone activates.
    message:
        Human-readable announcement string shown to the analyst.
    """

    id: int
    threshold: int
    message: str


CELEBRATION_ART: dict[str, list[str]] = {
    "small": [
        # Bug 5 fix (Phase 18 Slice 4): add description text below each ASCII art box so
        # the achievement panel body is not just a bare title frame.
        (
            "  ╔═══════════════════╗\n"
            "  ║   Nice find! 🎯   ║\n"
            "  ╚═══════════════════╝\n"
            "\nFound actionable intelligence in a hunt result."
        ),
        (
            "  ┌───────────────────┐\n"
            "  │  Target acquired  │\n"
            "  └───────────────────┘\n"
            "\nFirst data returned for a new target."
        ),
    ],
    "medium": [
        (
            "  ╔══════════════════════════╗\n"
            "  ║  🔥 EXCELLENT WORK! 🔥  ║\n"
            "  ║  You're on fire!         ║\n"
            "  ╚══════════════════════════╝"
        ),
        (
            "  ┌──────────────────────────┐\n"
            "  │      GREAT FIND!         │\n"
            "  │      Keep going!  ⭐     │\n"
            "  └──────────────────────────┘"
        ),
    ],
    "large": [
        (
            "  ╔═══════════════════════════════════════╗\n"
            "  ║                                       ║\n"
            "  ║   🏆 OUTSTANDING DISCOVERY! 🏆        ║\n"
            "  ║                                       ║\n"
            "  ║   You've uncovered something big.     ║\n"
            "  ╚═══════════════════════════════════════╝"
        ),
    ],
    "epic": [
        (
            "  ██████╗ ██████╗ ██╗ ██████╗\n"
            "  ██╔═══╝ ██╔══██╗██║██╔════╝\n"
            "  █████╗  ██████╔╝██║██║     \n"
            "  ██╔══╝  ██╔═══╝ ██║██║     \n"
            "  ██████╗ ██║     ██║╚██████╗\n"
            "  ╚═════╝ ╚═╝     ╚═╝ ╚═════╝\n"
            "\n"
            "  🎆 LEGENDARY DISCOVERY! 🎆"
        ),
    ],
}

# Ordered list of milestones, ascending by threshold.
# IDs are stable integers (1-based) so WorkspaceManager can persist a
# single integer sentinel (last_announced_id) without a schema change.
# DEC-63-MILESTONE-CATCHUP-001: IDs are assigned in threshold order so
# ``milestone.id > last_announced_id`` is the correct catch-up predicate.
MILESTONES: list[MilestoneSpec] = [
    MilestoneSpec(id=1, threshold=100, message="🌟 First Century! 100 points reached!"),
    MilestoneSpec(id=2, threshold=500, message="⚡ Half a Grand! You're getting dangerous."),
    MilestoneSpec(id=3, threshold=1000, message="🏆 Grand Master! 1000 points!"),
    MilestoneSpec(
        id=4, threshold=5000, message="🔥 LEGENDARY! 5000 points! The adversary fears you."
    ),
    MilestoneSpec(
        id=5, threshold=10000, message="👑 SUPREME HUNTER! 10,000 points! You ARE the threat."
    ),
]

# Highest milestone ID in MILESTONES — used for quiet-start migration.
# DEC-63-MIGRATION-001: callers initialise last_announced_id to
# _highest_crossed_milestone_id(total_score) when last_announced_id is None
# on workspace load, suppressing retroactive announcements.
_MAX_MILESTONE_ID: int = max(m.id for m in MILESTONES)


def highest_crossed_milestone_id(total_score: int) -> int | None:
    """Return the highest milestone ID already crossed at *total_score*.

    Returns None when total_score is below all milestones (no migration needed).
    Used by the quiet-start migration in WorkspaceManager to initialise
    last_announced_id on first access so retroactive announcements are
    suppressed (DEC-63-MIGRATION-001).

    Parameters
    ----------
    total_score:
        Current accumulated workspace score.

    Returns
    -------
    int | None
        Highest milestone ID whose threshold <= total_score, or None.
    """
    result: int | None = None
    for ms in MILESTONES:
        if total_score >= ms.threshold:
            result = ms.id
    return result


class CelebrationEngine:
    """Generates celebration messages for achievements and milestones."""

    def __init__(self, bell_enabled: bool = False) -> None:
        self.bell_enabled = bell_enabled
        self._first_blood_used = False

    def celebrate(self, points: int, action: str = "") -> str:
        """Return celebration ASCII art based on points earned.

        Thresholds:
        - <50: small
        - 50-199: medium
        - 200-499: large
        - 500+: epic
        """
        if points >= 500:
            level = "epic"
        elif points >= 200:
            level = "large"
        elif points >= 50:
            level = "medium"
        else:
            level = "small"

        # @decision DEC-62-CELEBRATIONS-001
        # @title Fix random.choice bug: was CELEBRATION_ART[level][0] (first char of first string)
        # @status accepted
        # @rationale CELEBRATION_ART[level] is a list[str]. random.choice(list)[0] picks
        #            the first character of the chosen string, not the string itself. The
        #            correct call is random.choice(CELEBRATION_ART[level]) which returns the
        #            full art string. The [0] indexing was a silent bug — all callers received
        #            a single character (e.g. " ") instead of the ASCII art panel.
        art = random.choice(CELEBRATION_ART[level])
        bell = "\a" if self.bell_enabled else ""
        return bell + art

    def check_milestones(
        self, total_score: int, last_announced_id: int | None
    ) -> list[MilestoneSpec]:
        """Return all milestones that should be announced now.

        Evaluates every milestone in MILESTONES in ascending threshold order
        and returns the subset where:
        - milestone.threshold <= total_score  (analyst has crossed it)
        - milestone.id > last_announced_id    (not yet announced)

        When last_announced_id is None (fresh workspace) all crossed
        milestones are returned — callers must suppress retroactive
        announcements themselves via the quiet-start migration
        (DEC-63-MIGRATION-001): initialise last_announced_id to
        highest_crossed_milestone_id(total_score) before calling this
        method for workspaces where the analyst already has a score.

        Parameters
        ----------
        total_score:
            Current accumulated workspace score (post-storage).
        last_announced_id:
            The highest milestone ID already announced in this workspace,
            or None if no milestones have been announced yet. Persisted by
            WorkspaceManager as a sentinel score_event row.

        Returns
        -------
        list[MilestoneSpec]
            Milestones to announce, in ascending threshold order.
            Empty list when no new milestones were crossed.

        @decision DEC-63-MILESTONE-CATCHUP-001 (implementation site)
        @title Cross-threshold check with id-based idempotency
        @status accepted
        @rationale See module-level DEC-63-MILESTONE-CATCHUP-001.
        """
        threshold_id = last_announced_id if last_announced_id is not None else 0
        return [ms for ms in MILESTONES if ms.threshold <= total_score and ms.id > threshold_id]

    def first_blood_message(self) -> str | None:
        """Return the first-discovery celebration message, or None if already fired.

        Fires at most once per CelebrationEngine instance (i.e. once per session).
        Callers should check for None and skip rendering when it is returned.

        The ``"first_blood"`` badge is awarded by BadgeManager when the workspace
        gains its first indicator. _execute_hunt / run_module call this method
        immediately after the badge check so the message appears exactly once —
        on the same run that earned the badge.

        @decision DEC-62-CELEBRATIONS-001 (wire site)
        @title _first_blood_used guards the message to one firing per session
        @status accepted
        @rationale _first_blood_used was already declared on __init__ but never
                   consulted. Wiring the guard here means callers don't need to
                   track the flag themselves — the engine is the authority on
                   whether first blood has already been celebrated this session.
        """
        if self._first_blood_used:
            return None
        self._first_blood_used = True
        return (
            "  ╔══════════════════════════╗\n"
            "  ║   🩸 FIRST BLOOD! 🩸     ║\n"
            "  ║   The hunt has begun.    ║\n"
            "  ╚══════════════════════════╝"
        )
