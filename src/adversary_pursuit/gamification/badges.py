"""Achievement/badge system for Adversary Pursuit.

Badges are permanent recognition for reaching milestones in a workspace.
Unlike challenges (which expire or have time limits), badges persist as
awards once earned and cannot be un-earned.

@decision DEC-BADGE-001
@title workspace_stats dict contract for badge evaluation
@status accepted
@rationale Badge.check_award receives a plain stats dict rather than a
           WorkspaceManager instance. This keeps Badge dataclasses pure,
           database-free, and trivially testable. APConsole assembles the
           dict from WorkspaceManager.get_workspace_stats() before calling
           BadgeManager.check_all(). Mirrors DEC-CHALLENGE-001 for consistency
           across the gamification subsystem.

           Stats dict keys:
             total_indicators (int): all STIX objects in workspace
             domain_count (int): count of domain-name STIX objects
             ip_count (int): count of ipv4-addr + ipv6-addr STIX objects
             module_run_count (int): count of module_runs rows
             total_score (int): sum of score_events.points
             note_count (int): count of analyst notes

@decision DEC-BADGE-002
@title Badge already_awarded set passed into check_all (stateless BadgeManager)
@status accepted
@rationale BadgeManager is stateless about which badges were already awarded —
           the caller passes an already_awarded set of badge IDs. This means
           APConsole queries WorkspaceManager.get_awarded_badges() to build
           the set, then passes it. The BadgeManager doesn't own persistence.
           This mirrors the ChallengeManager pattern (DEC-CHALLENGE-002) but
           with an explicit ID set rather than in-memory status flags, because
           badges are workspace-persistent (BadgeEvent table in SQLite) while
           challenges are session-scoped.

@decision DEC-BADGE-003
@title BadgeMetric enum selects the stat key each badge evaluates
@status accepted
@rationale Each badge evaluates a single numeric stat against a threshold.
           A BadgeMetric enum maps badge IDs to stat dict keys, keeping the
           badge definition self-contained and the evaluation logic to a single
           comparison. Adding a new badge requires only a new Badge instance
           with the correct metric — no new evaluation logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class BadgeRarity(Enum):
    """Visual/prestige tier for a badge.

    Used for display styling (color, icon) and future leaderboard weighting.
    """

    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class BadgeMetric(Enum):
    """Which workspace stat a badge evaluates.

    Each value maps to a key in the workspace_stats dict passed to
    Badge.check_award(). See DEC-BADGE-003.

    M-7 adds five new DOSSIER_* metrics. These keys are produced by
    gamification/dossier_badges.py::build_dossier_stats() and merged
    into the badge_stats dict before BadgeManager.check_all() is called.
    (DEC-M7-BADGE-001..005.)
    """

    TOTAL_INDICATORS = "total_indicators"
    DOMAIN_COUNT = "domain_count"
    IP_COUNT = "ip_count"
    MODULE_RUN_COUNT = "module_run_count"
    TOTAL_SCORE = "total_score"
    NOTE_COUNT = "note_count"
    # M-7 dossier-aware metrics (DEC-M7-BADGE-001..005)
    DOSSIER_SLOTS_FILLED = "dossier_slots_filled"
    DOSSIER_IDENTITY_FIRST = "dossier_identity_first"
    DOSSIER_PREDICTIONS_VALIDATED = "dossier_predictions_validated"
    DOSSIER_PREDICTIONS_FALSIFIED = "dossier_predictions_falsified"
    DOSSIER_DENIAL_FILLED = "dossier_denial_filled"
    # M-8 novelty metric (DEC-M8-NOVELTY-010)
    DOSSIER_NOVELTY_RECOGNIZED = "dossier_novelty_recognized"


@dataclass
class Badge:
    """A single achievement badge with a verifiable award condition.

    Parameters
    ----------
    id:
        Unique identifier (e.g. "badge-first-blood"). Stable across sessions.
    name:
        Short display name shown in the badges table.
    description:
        What the analyst must achieve to earn this badge.
    rarity:
        BadgeRarity tier controlling display styling.
    metric:
        Which workspace stat to compare against the threshold.
    threshold:
        The stat value that must be reached or exceeded to earn the badge.
    artwork:
        Stable visual family used by Pivotglass and other rich clients.
    glyph:
        Short redundant mark shown inside the artwork.
    """

    id: str
    name: str
    description: str
    rarity: BadgeRarity
    metric: BadgeMetric
    threshold: int
    artwork: str = "field-mark"
    glyph: str = "◆"

    def check_award(self, workspace_stats: dict) -> bool:
        """Check if this badge is earned given the current workspace stats.

        Parameters
        ----------
        workspace_stats:
            Dict assembled by WorkspaceManager.get_workspace_stats().
            Keys: total_indicators, domain_count, ip_count,
            module_run_count, total_score, note_count.

        Returns
        -------
        bool
            True if the stat value meets or exceeds the threshold.
        """
        stat_value = workspace_stats.get(self.metric.value, 0)
        return stat_value >= self.threshold


@dataclass
class AwardedBadge:
    """Record of a badge awarded in a specific workspace.

    Returned by WorkspaceManager.get_awarded_badges(). Constructed from
    BadgeEvent rows — not from Badge objects directly. Provides a
    serializable view of an earned badge.

    Parameters
    ----------
    badge_id:
        The Badge.id that was earned.
    badge_name:
        Snapshot of Badge.name at award time (defensive copy).
    workspace_name:
        Workspace in which the badge was earned.
    awarded_at:
        UTC datetime when the badge was first recorded.
    """

    badge_id: str
    badge_name: str
    workspace_name: str
    awarded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# Default badge definitions matching the spec from Issue #17.
# See DEC-BADGE-003 for the metric/threshold pattern.
_DEFAULT_BADGES: list[Badge] = [
    Badge(
        id="badge-first-blood",
        name="First Blood",
        description="Discover your first indicator",
        rarity=BadgeRarity.COMMON,
        metric=BadgeMetric.TOTAL_INDICATORS,
        threshold=1,
        artwork="first-signal",
        glyph="1",
    ),
    Badge(
        id="badge-data-hoarder",
        name="Data Hoarder",
        description="Accumulate 1000 indicators in a workspace",
        rarity=BadgeRarity.EPIC,
        metric=BadgeMetric.TOTAL_INDICATORS,
        threshold=1000,
        artwork="archive-stack",
        glyph="1K",
    ),
    Badge(
        id="badge-pivot-master",
        name="Pivot Master",
        description="Execute 5 or more module runs in a workspace",
        rarity=BadgeRarity.UNCOMMON,
        metric=BadgeMetric.MODULE_RUN_COUNT,
        threshold=5,
        artwork="pivot-nodes",
        glyph="5",
    ),
    Badge(
        id="badge-century",
        name="Century",
        description="Earn 100 points in a single workspace",
        rarity=BadgeRarity.COMMON,
        metric=BadgeMetric.TOTAL_SCORE,
        threshold=100,
        artwork="score-star",
        glyph="100",
    ),
    Badge(
        id="badge-grand-master",
        name="Grand Master",
        description="Earn 1000 points in a single workspace",
        rarity=BadgeRarity.RARE,
        metric=BadgeMetric.TOTAL_SCORE,
        threshold=1000,
        artwork="grand-crown",
        glyph="1K",
    ),
    Badge(
        id="badge-domain-hunter",
        name="Domain Hunter",
        description="Discover 50 unique domains",
        rarity=BadgeRarity.UNCOMMON,
        metric=BadgeMetric.DOMAIN_COUNT,
        threshold=50,
        artwork="constellation",
        glyph="50",
    ),
    Badge(
        id="badge-ip-collector",
        name="IP Collector",
        description="Discover 50 unique IP addresses",
        rarity=BadgeRarity.UNCOMMON,
        metric=BadgeMetric.IP_COUNT,
        threshold=50,
        artwork="network-grid",
        glyph="50",
    ),
    Badge(
        id="badge-note-taker",
        name="Note Taker",
        description="Write 10 analyst notes",
        rarity=BadgeRarity.COMMON,
        metric=BadgeMetric.NOTE_COUNT,
        threshold=10,
        artwork="public-record",
        glyph="10",
    ),
    Badge(
        id="badge-persistent",
        name="Persistent",
        description="Execute 10 or more module runs in a workspace",
        rarity=BadgeRarity.UNCOMMON,
        metric=BadgeMetric.MODULE_RUN_COUNT,
        threshold=10,
        artwork="persistence-loop",
        glyph="10",
    ),
    Badge(
        id="badge-supreme-hunter",
        name="Supreme Hunter",
        description="Earn 10000 points — the pinnacle of adversary pursuit",
        rarity=BadgeRarity.LEGENDARY,
        metric=BadgeMetric.TOTAL_SCORE,
        threshold=10000,
        artwork="trophy",
        glyph="10K",
    ),
]

# v0.8: graduated milestones give analysts frequent, legible recognition
# across collection, enrichment, documentation, and dossier construction.
# They reuse the deterministic BadgeMetric contract; no award depends on a
# character line, model judgment, or decorative UI state.
PROGRESSION_BADGES: list[Badge] = [
    Badge(
        "badge-signal-trace",
        "Signal Trace",
        "Map 5 indicators",
        BadgeRarity.COMMON,
        BadgeMetric.TOTAL_INDICATORS,
        5,
        "evidence-lens",
        "5",
    ),
    Badge(
        "badge-evidence-cache",
        "Evidence Cache",
        "Map 25 indicators",
        BadgeRarity.COMMON,
        BadgeMetric.TOTAL_INDICATORS,
        25,
        "archive-stack",
        "25",
    ),
    Badge(
        "badge-field-atlas",
        "Field Atlas",
        "Map 100 indicators",
        BadgeRarity.UNCOMMON,
        BadgeMetric.TOTAL_INDICATORS,
        100,
        "route-map",
        "100",
    ),
    Badge(
        "badge-deep-archive",
        "Deep Archive",
        "Map 500 indicators",
        BadgeRarity.RARE,
        BadgeMetric.TOTAL_INDICATORS,
        500,
        "source-layers",
        "500",
    ),
    Badge(
        "badge-domain-scout",
        "Domain Scout",
        "Map 10 unique domains",
        BadgeRarity.COMMON,
        BadgeMetric.DOMAIN_COUNT,
        10,
        "domain-orbit",
        "10",
    ),
    Badge(
        "badge-zone-mapper",
        "Zone Mapper",
        "Map 100 unique domains",
        BadgeRarity.RARE,
        BadgeMetric.DOMAIN_COUNT,
        100,
        "route-map",
        "100",
    ),
    Badge(
        "badge-domain-atlas",
        "Domain Atlas",
        "Map 250 unique domains",
        BadgeRarity.EPIC,
        BadgeMetric.DOMAIN_COUNT,
        250,
        "domain-orbit",
        "250",
    ),
    Badge(
        "badge-network-scout",
        "Network Scout",
        "Map 10 unique IP addresses",
        BadgeRarity.COMMON,
        BadgeMetric.IP_COUNT,
        10,
        "network-grid",
        "10",
    ),
    Badge(
        "badge-subnet-cartographer",
        "Subnet Cartographer",
        "Map 100 unique IP addresses",
        BadgeRarity.RARE,
        BadgeMetric.IP_COUNT,
        100,
        "infrastructure-tower",
        "100",
    ),
    Badge(
        "badge-address-space-atlas",
        "Address Space Atlas",
        "Map 250 unique IP addresses",
        BadgeRarity.EPIC,
        BadgeMetric.IP_COUNT,
        250,
        "route-map",
        "250",
    ),
    Badge(
        "badge-first-enrichment",
        "First Enrichment",
        "Complete the first enrichment run",
        BadgeRarity.COMMON,
        BadgeMetric.MODULE_RUN_COUNT,
        1,
        "public-record",
        "1",
    ),
    Badge(
        "badge-source-mixer",
        "Source Mixer",
        "Complete 3 enrichment runs",
        BadgeRarity.COMMON,
        BadgeMetric.MODULE_RUN_COUNT,
        3,
        "source-layers",
        "3",
    ),
    Badge(
        "badge-long-watch",
        "Long Watch",
        "Complete 25 enrichment runs",
        BadgeRarity.RARE,
        BadgeMetric.MODULE_RUN_COUNT,
        25,
        "time-watch",
        "25",
    ),
    Badge(
        "badge-marathon-analyst",
        "Marathon Analyst",
        "Complete 50 enrichment runs",
        BadgeRarity.EPIC,
        BadgeMetric.MODULE_RUN_COUNT,
        50,
        "lightning-map",
        "50",
    ),
    Badge(
        "badge-working-theory",
        "Working Theory",
        "Earn 250 evidence points",
        BadgeRarity.UNCOMMON,
        BadgeMetric.TOTAL_SCORE,
        250,
        "prediction-prism",
        "250",
    ),
    Badge(
        "badge-evidence-architect",
        "Evidence Architect",
        "Earn 2500 evidence points",
        BadgeRarity.EPIC,
        BadgeMetric.TOTAL_SCORE,
        2500,
        "dossier-prism",
        "2.5K",
    ),
    Badge(
        "badge-signal-sovereign",
        "Signal Sovereign",
        "Earn 5000 evidence points",
        BadgeRarity.EPIC,
        BadgeMetric.TOTAL_SCORE,
        5000,
        "trophy",
        "5K",
    ),
    Badge(
        "badge-first-annotation",
        "First Annotation",
        "Write the first analyst note",
        BadgeRarity.COMMON,
        BadgeMetric.NOTE_COUNT,
        1,
        "notebook",
        "1",
    ),
    Badge(
        "badge-case-journal",
        "Case Journal",
        "Write 5 analyst notes",
        BadgeRarity.COMMON,
        BadgeMetric.NOTE_COUNT,
        5,
        "notebook",
        "5",
    ),
    Badge(
        "badge-analyst-ledger",
        "Analyst Ledger",
        "Write 25 analyst notes",
        BadgeRarity.RARE,
        BadgeMetric.NOTE_COUNT,
        25,
        "source-layers",
        "25",
    ),
    Badge(
        "badge-chronicle-keeper",
        "Chronicle Keeper",
        "Write 100 analyst notes",
        BadgeRarity.EPIC,
        BadgeMetric.NOTE_COUNT,
        100,
        "archive-stack",
        "100",
    ),
    Badge(
        "badge-facet-finder",
        "Facet Finder",
        "Fill the first dossier facet",
        BadgeRarity.COMMON,
        BadgeMetric.DOSSIER_SLOTS_FILLED,
        1,
        "evidence-lens",
        "1",
    ),
    Badge(
        "badge-half-the-picture",
        "Half the Picture",
        "Fill 5 dossier facets",
        BadgeRarity.UNCOMMON,
        BadgeMetric.DOSSIER_SLOTS_FILLED,
        5,
        "dossier-prism",
        "5",
    ),
    Badge(
        "badge-dossier-architect",
        "Dossier Architect",
        "Fill 7 dossier facets",
        BadgeRarity.RARE,
        BadgeMetric.DOSSIER_SLOTS_FILLED,
        7,
        "dossier-prism",
        "7",
    ),
]

# Extend _DEFAULT_BADGES with the dossier-aware badge family.
# gamification/dossier_badges.py is the authority for those badge specs;
# _DEFAULT_BADGES is the splice site (Sacred Practice 12, DEC-M7-BADGE-006).
# Import is deferred to module tail to avoid a circular import: dossier_badges.py
# imports Badge and BadgeMetric from this file, so this module must define both
# before the import runs.
from adversary_pursuit.gamification.dossier_badges import DOSSIER_BADGES  # noqa: E402

_DEFAULT_BADGES = _DEFAULT_BADGES + PROGRESSION_BADGES + DOSSIER_BADGES


class BadgeManager:
    """Manages badge definitions and evaluation.

    Holds Badge definitions in memory. Stateless about which badges have
    been awarded — the caller provides an already_awarded set of badge IDs
    (from WorkspaceManager.get_awarded_badges()) each time check_all is
    called. See DEC-BADGE-002.

    Usage::

        mgr = BadgeManager()
        awarded_ids = {row["badge_id"] for row in workspace_mgr.get_awarded_badges()}
        stats = workspace_mgr.get_workspace_stats()
        newly = mgr.check_all(stats, already_awarded=awarded_ids)
        for badge in newly:
            workspace_mgr.store_badge_event(badge.id, badge.name)
            console.print(f"Badge earned: {badge.name}!")
    """

    def __init__(self, badges: list[Badge] | None = None) -> None:
        """Initialise with optional custom badge list (defaults to _DEFAULT_BADGES).

        Parameters
        ----------
        badges:
            Override the default badge definitions. Pass None to use the
            built-in badge catalog. Useful for tests that need isolated badges.
        """
        self._badges: dict[str, Badge] = {
            b.id: b for b in (badges if badges is not None else _DEFAULT_BADGES)
        }

    def get_badge(self, badge_id: str) -> Badge | None:
        """Return a Badge by its ID, or None if not found.

        Parameters
        ----------
        badge_id:
            The Badge.id to look up (e.g. "badge-first-blood").
        """
        return self._badges.get(badge_id)

    def check_all(self, workspace_stats: dict, already_awarded: set[str]) -> list[Badge]:
        """Check all badges against the workspace stats and return newly earned ones.

        Badges whose IDs are in already_awarded are skipped (idempotent).
        Returns only badges where check_award() returns True and the badge
        has not already been awarded.

        Parameters
        ----------
        workspace_stats:
            Dict from WorkspaceManager.get_workspace_stats().
            Keys: total_indicators, domain_count, ip_count,
            module_run_count, total_score, note_count.
        already_awarded:
            Set of badge IDs already awarded in this workspace. Obtained
            from {row["badge_id"] for row in workspace_mgr.get_awarded_badges()}.

        Returns
        -------
        list[Badge]
            Badges newly earned in this check (not in already_awarded).
        """
        newly: list[Badge] = []
        for badge in self._badges.values():
            if badge.id in already_awarded:
                continue
            if badge.check_award(workspace_stats):
                newly.append(badge)
        return newly

    def list_badges(self) -> list[dict]:
        """Return all badge definitions as serializable dicts.

        Returns
        -------
        list[dict]
            Each dict has: id, name, description, rarity, metric, threshold,
            artwork, and glyph.
        """
        return [
            {
                "id": b.id,
                "name": b.name,
                "description": b.description,
                "rarity": b.rarity.value,
                "metric": b.metric.value,
                "threshold": b.threshold,
                "artwork": b.artwork,
                "glyph": b.glyph,
            }
            for b in self._badges.values()
        ]
