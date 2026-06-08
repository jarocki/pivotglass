"""Dossier-aware candidate ranker for the auto-pivot cascade (M-6).

This module is the SOLE authority for the dossier-aware ranking layer
(DEC-M6-PIVOT-002).  It provides a pure-function API that sits ABOVE the F60
3-gate pivot policy engine — it orders candidates before they reach the gates;
it does NOT add a 4th gate, and it does NOT modify PivotPolicy.evaluate.

Public API
----------
make_dossier_pivot_ranker(dossier_state) → Callable[[list[dict], str], list[dict]]
    Returns a closure that re-orders a results list by descending slot-fill score,
    with tie-breaking by x_abuse_confidence_score (higher first).  Stable: ties
    preserve original input order (Python's sort is stable).

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
  The ranker never calls load_dossier_state() — it consumes the snapshot that
  agent/tools.py already loaded once per hunt (DEC-M6-PIVOT-009).

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
@status accepted
@rationale The ranker consumes the same snapshot that M-4's hunt-site code already
           loaded once per hunt.  Mid-pass re-ranking is explicitly out of scope
           (DEC-M4-PERSIST-001 hunt-boundary semantics inherited as canon).
"""

from __future__ import annotations

from typing import Callable

from adversary_pursuit.dossier.slot_inference import DossierState
from adversary_pursuit.dossier.slots import SLOT_EVIDENCE_TYPES, SLOT_WEIGHTS, SlotStatus

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
# Ranker factory
# ---------------------------------------------------------------------------


def make_dossier_pivot_ranker(
    dossier_state: DossierState,
) -> Callable[[list[dict], str], list[dict]]:
    """Return a ranker closure that sorts candidate SCOs by descending slot-fill score.

    The returned callable has the signature::

        ranker(results: list[dict], source_module: str) -> list[dict]

    It returns a NEW list (input is not mutated).  Sort is stable (Python's
    ``sorted()`` is stable) so ties in slot-fill score fall back to the original
    input order, with a secondary tie-break on ``x_abuse_confidence_score``
    (higher = better; missing field treated as -1) per DEC-M6-PIVOT-006.

    The closure also populates a ``_dossier_weights`` side-channel dict keyed by
    ``(sco_id, sco_value)`` so ``EventBus.publish`` can attach ``dossier_weight``
    to each ``DecisionLogEntry`` without re-computing scores (DEC-M6-PIVOT-007).

    Parameters
    ----------
    dossier_state:
        The M-4 pre_dossier snapshot.  Captured once per hunt by agent/tools.py
        and treated as immutable within the pass (DEC-M6-PIVOT-009).

    Returns
    -------
    Callable[[list[dict], str], list[dict]]
        A closure that accepts (results, source_module) and returns a ranked list.
    """
    # Pre-compute scores per SCO type for the snapshot — amortises repeated
    # lookups when a source module returns many SCOs of the same type.
    _score_cache: dict[str, float] = {}

    def _score(sco_type: str) -> float:
        if sco_type not in _score_cache:
            _score_cache[sco_type] = compute_slot_fill_score(sco_type, dossier_state)
        return _score_cache[sco_type]

    def ranker(results: list[dict], source_module: str) -> list[dict]:  # noqa: ARG001
        """Rank results by descending dossier slot-fill score.

        Parameters
        ----------
        results:
            Raw SCO dicts from a hunt() call.  Each dict may contain ``type``,
            ``value``, ``id``, and ``x_abuse_confidence_score``.
        source_module:
            Module that produced the results (unused in ranking; present for
            interface parity with EventBus.process_results callers).

        Returns
        -------
        list[dict]
            New list ordered by (slot_fill_score DESC, confidence DESC, original_idx ASC).
            Empty input → empty output.
        """
        if not results:
            return []

        def sort_key(item: tuple[int, dict]) -> tuple[float, float]:
            idx, sco = item
            sco_type = sco.get("type", "")
            slot_score = _score(sco_type)
            # Secondary tie-break: x_abuse_confidence_score descending
            # Missing field → -1 so scored items sort before unscored ones.
            raw_conf = sco.get("x_abuse_confidence_score")
            try:
                confidence = float(raw_conf) if raw_conf is not None else -1.0
            except (TypeError, ValueError):
                confidence = -1.0
            # Negate for descending sort; Python stable sort preserves original
            # order when both keys are equal (idx tie-break is implicit).
            return (-slot_score, -confidence)

        ranked_pairs = sorted(enumerate(results), key=sort_key)
        return [sco for _, sco in ranked_pairs]

    # Attach the score function as a side-channel so EventBus.publish can
    # retrieve dossier_weight values without re-importing dossier_pivot.
    # EventBus reads ranker._score_for_type(sco_type) → float.
    ranker._score_for_type = _score  # type: ignore[attr-defined]

    return ranker
