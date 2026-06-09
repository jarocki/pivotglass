"""Dossier-aware badge definitions for M-7 and M-8.

M-7: Five new badges keyed on DossierState + PersistedPrediction log. All five use
new BadgeMetric enum values (DOSSIER_SLOTS_FILLED, DOSSIER_IDENTITY_FIRST,
DOSSIER_PREDICTIONS_VALIDATED, DOSSIER_PREDICTIONS_FALSIFIED,
DOSSIER_DENIAL_FILLED) and a new stats dict produced by build_dossier_stats().

M-8: One new badge (badge-pioneer, RARE, threshold=1) keyed on the
dossier_novelty_recognized score event count (DEC-M8-NOVELTY-010).
build_dossier_stats() extended to return the novelty count from the workspace
score events. BadgeMetric.DOSSIER_NOVELTY_RECOGNIZED added to badges.py enum.

This module is the AUTHORITY for all dossier badge specs. badges.py imports
DOSSIER_BADGES and splices it into _DEFAULT_BADGES at module load time —
single source of truth (Sacred Practice 12, DEC-M7-BADGE-006).

@decision DEC-M7-BADGE-001
@title badge-dossier-complete — LEGENDARY, all 9 slots FILLED
@status accepted
@rationale Apex puzzle-solved achievement. Signature M-7 milestone.

@decision DEC-M7-BADGE-002
@title badge-identity-first — RARE, Identity FILLED with at most 1 other slot FILLED
@status accepted
@rationale Directed achievement: filling Identity before the other slots.
           DEC-M7-BADGE-007: snapshot heuristic used (Identity FILLED while
           at most 1 other non-Identity slot is also FILLED). Temporal "before
           any other" semantic approximated as a snapshot comparison.

@decision DEC-M7-BADGE-003
@title badge-predictor — UNCOMMON, 3 validated predictions
@status accepted
@rationale Three or more PersistedPrediction.status == "validated" in workspace log.

@decision DEC-M7-BADGE-004
@title badge-skeptic — UNCOMMON, 3 falsified predictions
@status accepted
@rationale Three or more PersistedPrediction.status == "falsified". Prestige signal
           for the M-5 active-falsification engine output (DEC-M4-PRED-006: +0 pts).

@decision DEC-M7-BADGE-005
@title badge-deception-spotter — RARE, Denial slot FILLED
@status accepted
@rationale Recognises that the analyst surfaced credible denial/deception evidence
           (M-5 slot 9 inference + analyst note authoring).

@decision DEC-M7-BADGE-006
@title Existing 10 badges byte-identical; new 5 are additive only
@status accepted
@rationale No existing badge ID, name, threshold, rarity, or metric is changed.
           Five new entries are appended to _DEFAULT_BADGES. Rollback requires only
           reverting this module and the badges.py splice.

@decision DEC-M7-BADGE-007
@title badge-identity-first uses snapshot heuristic, not temporal ordering
@status accepted
@rationale Exact "before any other" temporal ordering would require historical
           score event scanning (expensive; no index by slot-fill order).
           Snapshot heuristic: Identity=FILLED AND total slots FILLED <= 2
           (Identity + at most one other). Conservative: may miss the badge if
           the analyst fills two other slots simultaneously with Identity.
           Explicitly recorded as an approximation — future slice can refine.

Public API:
  - DOSSIER_BADGES: list[Badge]  — six badge instances (5 M-7 + 1 M-8 Pioneer)
  - build_dossier_stats(dossier_state, predictions, workspace_mgr=None) -> dict
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adversary_pursuit.gamification.badges import Badge, BadgeMetric, BadgeRarity

if TYPE_CHECKING:
    from adversary_pursuit.dossier.predictions import PersistedPrediction

# ---------------------------------------------------------------------------
# Five new badge definitions (DEC-M7-BADGE-001..005)
# ---------------------------------------------------------------------------

DOSSIER_BADGES: list[Badge] = [
    Badge(
        id="badge-dossier-complete",
        name="Full Dossier",
        description=(
            "Fill all 9 threat actor dossier slots to FILLED status — "
            "the apex M-7 puzzle-solved achievement."
        ),
        rarity=BadgeRarity.LEGENDARY,
        metric=BadgeMetric.DOSSIER_SLOTS_FILLED,
        threshold=9,
    ),
    Badge(
        id="badge-identity-first",
        name="Identity First",
        description=(
            "Fill the Identity slot while at most one other slot is also FILLED — "
            "attribution before enumeration."
        ),
        rarity=BadgeRarity.RARE,
        metric=BadgeMetric.DOSSIER_IDENTITY_FIRST,
        threshold=1,
    ),
    Badge(
        id="badge-predictor",
        name="Predictor",
        description="Have 3 or more of your dossier predictions validated by hunt evidence.",
        rarity=BadgeRarity.UNCOMMON,
        metric=BadgeMetric.DOSSIER_PREDICTIONS_VALIDATED,
        threshold=3,
    ),
    Badge(
        id="badge-skeptic",
        name="Skeptic",
        description=(
            "Have 3 or more of your dossier predictions falsified — epistemic discipline in action."
        ),
        rarity=BadgeRarity.UNCOMMON,
        metric=BadgeMetric.DOSSIER_PREDICTIONS_FALSIFIED,
        threshold=3,
    ),
    Badge(
        id="badge-deception-spotter",
        name="Deception Spotter",
        description=(
            "Fill the Denial / Deception slot — "
            "you surfaced credible evidence of adversary deception strategies."
        ),
        rarity=BadgeRarity.RARE,
        metric=BadgeMetric.DOSSIER_DENIAL_FILLED,
        threshold=1,
    ),
    # M-8: Pioneer badge — first novel slot-fill method (DEC-M8-NOVELTY-010)
    Badge(
        id="badge-pioneer",
        name="Pioneer",
        description=(
            "Discover a novel slot-fill method — a "
            "(slot, evidence-extractor, SCO-type-set) tuple "
            "no prior hunt has produced."
        ),
        rarity=BadgeRarity.RARE,
        metric=BadgeMetric.DOSSIER_NOVELTY_RECOGNIZED,
        threshold=1,
    ),
]


# ---------------------------------------------------------------------------
# Dossier stats builder (DEC-M7-BADGE-001..005 / DEC-M8-NOVELTY-010)
# ---------------------------------------------------------------------------


def build_dossier_stats(
    dossier_state: object | None,
    predictions: "list[PersistedPrediction]",
    workspace_mgr: Any = None,
) -> dict:
    """Build dossier-specific stats for badge evaluation.

    Merges into the existing workspace_stats dict before BadgeManager.check_all()
    is called. The existing 10 badges read their own keys; the new dossier badges
    read these keys.

    Stats contract (DEC-BADGE-003 metric-to-stat-key mapping):
    - ``dossier_slots_filled``          (int): count of slots with status == FILLED
    - ``dossier_identity_first``        (int 0/1): 1 if Identity FILLED with <= 1 other FILLED
    - ``dossier_predictions_validated`` (int): count of validated predictions
    - ``dossier_predictions_falsified`` (int): count of falsified predictions
    - ``dossier_denial_filled``         (int 0/1): 1 if Denial slot FILLED
    - ``dossier_novelty_recognized``    (int): count of novelty events in score_events
      (M-8, DEC-M8-NOVELTY-010 — requires workspace_mgr to be non-None)

    Parameters
    ----------
    dossier_state:
        DossierState from load_dossier_state() + apply_predictions_overlay(),
        or None for a fresh workspace (all counts return 0).
    predictions:
        List of PersistedPrediction from load_predictions_log(), or [].
    workspace_mgr:
        Optional WorkspaceManager used to count dossier_novelty_recognized score
        events (M-8). When None the novelty count defaults to 0.

    Returns
    -------
    dict
        Keys: dossier_slots_filled, dossier_identity_first,
              dossier_predictions_validated, dossier_predictions_falsified,
              dossier_denial_filled, dossier_novelty_recognized.
    """
    # Default all to 0 (fresh workspace)
    stats: dict[str, int] = {
        BadgeMetric.DOSSIER_SLOTS_FILLED.value: 0,
        BadgeMetric.DOSSIER_IDENTITY_FIRST.value: 0,
        BadgeMetric.DOSSIER_PREDICTIONS_VALIDATED.value: 0,
        BadgeMetric.DOSSIER_PREDICTIONS_FALSIFIED.value: 0,
        BadgeMetric.DOSSIER_DENIAL_FILLED.value: 0,
        BadgeMetric.DOSSIER_NOVELTY_RECOGNIZED.value: 0,
    }

    if dossier_state is not None:
        try:
            from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus

            slots = dossier_state.slots  # type: ignore[union-attr]

            # Count FILLED slots
            filled_slots = [
                name for name, slot in slots.items() if slot.status == SlotStatus.FILLED
            ]
            stats[BadgeMetric.DOSSIER_SLOTS_FILLED.value] = len(filled_slots)

            # Identity-first heuristic (DEC-M7-BADGE-007):
            # Identity FILLED AND total FILLED count <= 2
            identity_slot = slots.get(DossierSlotName.IDENTITY)
            identity_filled = (
                identity_slot is not None and identity_slot.status == SlotStatus.FILLED
            )
            if identity_filled and len(filled_slots) <= 2:
                stats[BadgeMetric.DOSSIER_IDENTITY_FIRST.value] = 1

            # Denial slot FILLED
            denial_slot = slots.get(DossierSlotName.DENIAL)
            denial_filled = denial_slot is not None and denial_slot.status == SlotStatus.FILLED
            if denial_filled:
                stats[BadgeMetric.DOSSIER_DENIAL_FILLED.value] = 1

        except Exception:  # noqa: BLE001
            pass  # dossier stats must never block badge check delivery

    # Prediction counts (independent of dossier_state)
    if predictions:
        try:
            validated_count = sum(1 for p in predictions if p.status == "validated")
            falsified_count = sum(1 for p in predictions if p.status == "falsified")
            stats[BadgeMetric.DOSSIER_PREDICTIONS_VALIDATED.value] = validated_count
            stats[BadgeMetric.DOSSIER_PREDICTIONS_FALSIFIED.value] = falsified_count
        except Exception:  # noqa: BLE001
            pass  # prediction stats must never block badge check delivery

    # M-8: novelty count from workspace score_events (DEC-M8-NOVELTY-010).
    # Uses SQLAlchemy direct query — same pattern as console.py::_read_analyst_notes.
    # workspace_mgr is optional; defaults to 0 when absent (no workspace active yet).
    if workspace_mgr is not None:
        try:
            from sqlalchemy import func, select
            from sqlalchemy.orm import Session

            from adversary_pursuit.models.database import ScoreEvent

            with Session(workspace_mgr._engine) as session:
                count_row = session.execute(
                    select(func.count(ScoreEvent.id)).where(
                        ScoreEvent.action == "dossier_novelty_recognized"
                    )
                ).scalar()
                stats[BadgeMetric.DOSSIER_NOVELTY_RECOGNIZED.value] = int(count_row or 0)
        except Exception:  # noqa: BLE001
            pass  # novelty stat must never block badge check delivery

    return stats
