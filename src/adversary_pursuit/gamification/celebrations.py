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
@title Milestone messages fire at exact score thresholds only
@status accepted
@rationale Milestones (100, 500, 1000, 5000, 10000) return a message only
           when total_score exactly equals the threshold. The caller is
           responsible for checking before and after storing score events.
           This prevents double-firing if the score jumps past a milestone.
"""

from __future__ import annotations

import random


CELEBRATION_ART: dict[str, list[str]] = {
    "small": [
        (
            "  ╔═══════════════════╗\n"
            "  ║   Nice find! 🎯   ║\n"
            "  ╚═══════════════════╝"
        ),
        (
            "  ┌───────────────────┐\n"
            "  │  Target acquired  │\n"
            "  └───────────────────┘"
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

MILESTONES: dict[int, str] = {
    100: "🌟 First Century! 100 points reached!",
    500: "⚡ Half a Grand! You're getting dangerous.",
    1000: "🏆 Grand Master! 1000 points!",
    5000: "🔥 LEGENDARY! 5000 points! The adversary fears you.",
    10000: "👑 SUPREME HUNTER! 10,000 points! You ARE the threat.",
}


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

        art = CELEBRATION_ART[level][0]
        bell = "\a" if self.bell_enabled else ""
        return bell + art

    def milestone_message(self, total_score: int) -> str | None:
        """Return milestone message if total_score is exactly a milestone value."""
        return MILESTONES.get(total_score)

    def first_blood_message(self) -> str:
        """Return the first-discovery celebration message."""
        return (
            "  ╔══════════════════════════╗\n"
            "  ║   🩸 FIRST BLOOD! 🩸     ║\n"
            "  ║   The hunt has begun.    ║\n"
            "  ╚══════════════════════════╝"
        )
