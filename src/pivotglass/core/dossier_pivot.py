"""Dossier-aware frontier ranker for pivot runs (M-6).

This module is the SOLE authority for the dossier-aware ranking layer
(DEC-M6-PIVOT-002).  It provides a pure-function API that sits ABOVE the F60
3-gate pivot policy engine — it orders candidates before they reach the gates;
it does NOT add a 4th gate, and it does NOT modify PivotPolicy.evaluate.

Public API
----------
make_dossier_pivot_ranker(dossier_state) → DossierPivotRanker
    Returns a ranker whose ``key(sco_type, attrs)`` orders candidates by
    descending slot-fill score, tie-broken by x_abuse_confidence_score (higher
    first).  ``PivotRun`` sorts each depth of its frontier by this key; remaining
    ties keep discovery order (DEC-M6-PIVOT-010).

compute_slot_fill_score(sco_type, dossier_state) → float
    Pure function.  Returns Σ over slots-that-sco_type-could-fill of
    SLOT_WEIGHTS[slot] × STATUS_MULTIPLIERS[slot_status].
    Returns 0.0 for SCO types not in SLOT_EVIDENCE_TYPES, and for types whose
    every contributing slot is already FILLED or DEFERRED.

STATUS_MULTIPLIERS: dict[SlotStatus, float]
    Module-level constant.  Single authority for status-to-weight mapping
    (DEC-M6-PIVOT-003).

Integration points (read-only)
-------------------------------
- dossier/slots.py::SLOT_EVIDENCE_TYPES — SCO-type → slot(s) mapping authority.
  Any future addition to that dict is picked up by this module automatically.
- dossier/slots.py::SLOT_WEIGHTS — per-slot importance weight authority
  (DEC-M1-SLOTS-WEIGHT-AUTHORITY-001).  Never copied or shadowed here.
- dossier/slot_inference.py::DossierState — read-only snapshot from M-4 pre_dossier.
  The ranker never calls load_dossier_state() — it consumes the snapshot its
  caller loaded once: the enrichment's pre-hunt state for autopivot, the state
  at run start for an analyst's ``pivot`` run (DEC-M6-PIVOT-009).

@decision DEC-M6-PIVOT-001
@title Wrap F60 with a new ranker layer above PivotPolicy (do not replace or extend it)
@status accepted
@rationale Single source of truth for the 3-gate engine preserved (Sacred Practice 12).
           The ranker is a pure pre-filter: it changes iteration order, not gate semantics.
           F60 tests stay byte-identical. Opt-out via config flag (DEC-M6-PIVOT-008).

@decision DEC-M6-PIVOT-002
@title New module core/dossier_pivot.py — separate from core/pivot_policy.py
@status accepted
@rationale F60 (pivot_policy.py) owns gate semantics; M-6 (dossier_pivot.py) owns
           ranking semantics.  Co-locating them would blend two independent concerns
           and introduce a new core→dossier import direction in pivot_policy.py where
           none existed before.

@decision DEC-M6-PIVOT-003
@title STATUS_MULTIPLIERS is the single authority for status-to-weight values
@status accepted
@rationale EMPTY=1.0, PARTIAL=0.5, FILLED=0.0, DEFERRED=0.0.  All callers import
           from this dict.  Tests assert the exact values as a regression guard.

@decision DEC-M6-PIVOT-005
@title F60 confidence gate is boolean — M-6 slot-fill score is the sole rank
@status accepted
@rationale F60's confidence gate is a threshold (pass/fail), not a score that can be
           combined with a rank.  The slot-fill score stands alone as the ranking key.
           Tie-break: higher x_abuse_confidence_score first (DEC-M6-PIVOT-006).

@decision DEC-M6-PIVOT-006
@title Tie-break: equal slot-fill scores → higher x_abuse_confidence_score first
@status accepted
@rationale Mirrors F60's preference for high-confidence indicators.  Missing field
           is treated as -1 so scored indicators always beat unscored ones in a tie.
           Further ties fall through to stable sort (original input order).

@decision DEC-M6-PIVOT-009
@title DossierState snapshot is the M-4 pre_dossier — no second load_dossier_state call
@status accepted (amended v1.5.0)
@rationale The ranker consumes the same snapshot that M-4's hunt-site code already
           loaded once per hunt.  Mid-pass re-ranking is explicitly out of scope
           (DEC-M4-PERSIST-001 hunt-boundary semantics inherited as canon).
           v1.5.0: autopivot still ranks with the enrichment's pre_dossier; an
           analyst ``pivot`` run loads the state once when it is built and keeps it
           for the whole run.

@decision DEC-M6-PIVOT-010
@title The dossier ranker orders PivotRun's frontier, within each depth
@status accepted
@rationale Until v1.5.0 the ranker re-ordered one module's result list before the
           event bus cascaded over it. The cascade was retired (DEC-PIVOT-AUTOPIVOT-001)
           and PivotRun owns the order in which indicators are expanded, so the
           ranker moved there with the same semantics: slot-fill score descending,
           then confidence descending, then discovery order. It ranks within a
           depth and never across depths, so breadth-first expansion and the depth
           limit are unchanged; it changes which indicators the budget reaches first,
           never which gates apply. Each decision records the indicator's
           ``dossier_weight`` (DEC-M6-PIVOT-007). ``dossier_aware_ranking = false``
           restores pure discovery order (DEC-M6-PIVOT-008).
"""

from __future__ import annotations

from typing import Any

from pivotglass.dossier.slot_inference import DossierState
from pivotglass.dossier.slots import SLOT_EVIDENCE_TYPES, SLOT_WEIGHTS, SlotStatus

# ---------------------------------------------------------------------------
# Status multipliers (DEC-M6-PIVOT-003)
# ---------------------------------------------------------------------------

STATUS_MULTIPLIERS: dict[SlotStatus, float] = {
    SlotStatus.EMPTY: 1.0,  # max pressure — slot has no evidence yet
    SlotStatus.PARTIAL: 0.5,  # half pressure — slot has some evidence
    SlotStatus.FILLED: 0.0,  # no pressure — slot is already done
    SlotStatus.DEFERRED: 0.0,  # no pressure — inference path not active yet
}


# ---------------------------------------------------------------------------
# Core scoring function
# ---------------------------------------------------------------------------


def compute_slot_fill_score(sco_type: str, dossier_state: DossierState) -> float:
    """Return the dossier-slot-fill score for a single SCO type.

    Formula (DEC-M6-PIVOT-003 / DEC-M6-PIVOT-004)::

        score = Σ_{slot ∈ SLOT_EVIDENCE_TYPES[sco_type]} (
            SLOT_WEIGHTS[slot] × STATUS_MULTIPLIERS[slot_status]
        )

    Returns 0.0 for:
    - SCO types not in SLOT_EVIDENCE_TYPES (unknown types sort to the end but
      are still evaluated by F60 if budget permits)
    - SCO types whose every contributing slot is already FILLED or DEFERRED

    Parameters
    ----------
    sco_type:
        STIX SCO type string, e.g. ``"email-addr"``, ``"ipv4-addr"``.
    dossier_state:
        Current dossier snapshot (M-4 pre_dossier, immutable within a hunt pass).

    Returns
    -------
    float
        Non-negative slot-fill score.  Higher = more dossier pressure to pivot.
    """
    slots = SLOT_EVIDENCE_TYPES.get(sco_type)
    if not slots:
        return 0.0

    total = 0.0
    for slot_name in slots:
        slot_state = dossier_state.slots.get(slot_name)
        if slot_state is None:
            continue
        multiplier = STATUS_MULTIPLIERS.get(slot_state.status, 0.0)
        weight = SLOT_WEIGHTS.get(slot_name, 0.0)
        total += weight * multiplier
    return total


# ---------------------------------------------------------------------------
# Ranker
# ---------------------------------------------------------------------------


class DossierPivotRanker:
    """Frontier ordering for a pivot run from one dossier snapshot (DEC-M6-PIVOT-010).

    ``score(sco_type)`` is the slot-fill score (cached per type for the snapshot);
    ``key(sco_type, attrs)`` is the sort key PivotRun uses within a depth: lower
    sorts first, so it is the negated (slot-fill score, confidence) pair. A
    missing or non-numeric ``x_abuse_confidence_score`` counts as -1 so scored
    indicators beat unscored ones in a tie (DEC-M6-PIVOT-006).
    """

    def __init__(self, dossier_state: DossierState) -> None:
        self._state = dossier_state
        self._scores: dict[str, float] = {}

    def score(self, sco_type: str) -> float:
        if sco_type not in self._scores:
            self._scores[sco_type] = compute_slot_fill_score(sco_type, self._state)
        return self._scores[sco_type]

    def key(self, sco_type: str, attrs: dict[str, Any]) -> tuple[float, float]:
        raw = attrs.get("x_abuse_confidence_score")
        try:
            confidence = float(raw) if raw is not None else -1.0
        except (TypeError, ValueError):
            confidence = -1.0
        return (-self.score(sco_type), -confidence)


def make_dossier_pivot_ranker(dossier_state: DossierState) -> DossierPivotRanker:
    """Return the frontier ranker for *dossier_state* (DEC-M6-PIVOT-001, -010)."""

    return DossierPivotRanker(dossier_state)
