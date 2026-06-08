"""Dossier slot scoring — pure function event emitter for slot-fill transitions.

This module is the sole authority for ``dossier_slot_filled`` ScoreEvent emission
(Sacred Practice 12). It answers one question: given a ``DossierState`` before a
hunt and a ``DossierState`` after, which slot transitions occurred and what score
events do they imply?

No I/O, no subscribers, no workspace mutations. Callers wire the pre/post snapshots
and persist the returned events via the existing ``workspace_mgr.store_score_events``
API (DEC-M3-DOSSIER-001).

@decision DEC-M3-DOSSIER-001
@title New file dossier/scoring.py; emit_dossier_slot_filled_events is a pure function
@status accepted
@rationale DEC-68-DOSSIER-REFRAME-002 chose option (c) "layer over scoring." Pure
    function honours that layering: this file is the dossier-event-emission authority,
    callers integrate without changing ScoringEngine semantics or workspace persistence
    semantics. Two alternatives were rejected: (a) event-bus subscriber (F60 territory,
    violates forbidden list, couples to dry-run cascade), and (b) ScoringEngine-internal
    computation (forces foreign DossierState inputs into ScoringEngine, breaks Sacred
    Practice 12). See per-slice plan §2.2 for full rationale.

@decision DEC-M3-DOSSIER-005
@title dossier_prediction_validated scaffolded in M-3; NOT emitted during any M-3 hunt
@status accepted
@rationale Predictions slot remains DEFERRED in M-2 (DEC-M2-DOSSIER-004); no persistent
    prediction records exist until M-4. The helper is shipped and tested for shape contract
    so M-4 has a stable target. Zero negative-score logic ships in M-3; DEC-68-DOSSIER-
    REFRAME-007 (falsified-prediction deduction) is deferred to M-4.

@decision DEC-M5-FALSIFY-005
@title Falsification event: action=dossier_prediction_falsified, points=0 (DEC-M4-PRED-006)
@status accepted
@rationale DEC-M4-PRED-006 canon: no negative-points events. Falsification fires at +0.
    The event still flows through store_score_events so F62 streak, F63 milestone,
    and F64 panel-separation all see it as a zero-points event. _DOSSIER_ACTIONS
    filter in agent/tools.py widens to 3-tuple to include this new action (F64).

Public API (M-3 + M-5):
  - emit_dossier_slot_filled_events(pre, post) -> list[dict]
  - emit_dossier_prediction_validated_event(prediction) -> dict
  - emit_dossier_prediction_falsified_event(prediction, reason) -> dict  (M-5 NEW)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from adversary_pursuit.dossier.slot_inference import DossierState
from adversary_pursuit.dossier.slots import (
    SLOT_WEIGHTS,
    DossierSlotName,
    PredictionRecord,
    SlotStatus,
)

if TYPE_CHECKING:
    from adversary_pursuit.dossier.predictions import PersistedPrediction

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Slot display names — used in rule_description (plain ASCII; no Rich markup)
# F64: dossier event text MUST NOT contain Rich markup — rule_description is
# the plain-ASCII field shown in score displays and returned to the LLM as the
# events sidecar (DEC-64-LLM-PANEL-SEPARATION-001).
# ---------------------------------------------------------------------------
_SLOT_DISPLAY_NAMES: dict[DossierSlotName, str] = {
    DossierSlotName.IDENTITY: "Identity",
    DossierSlotName.PREDICTIONS: "Predictions",
    DossierSlotName.CAPABILITY: "Capability",
    DossierSlotName.TTPS: "TTPs",
    DossierSlotName.MOTIVATION: "Motivation",
    DossierSlotName.TARGETING: "Targeting",
    DossierSlotName.DENIAL: "Denial",
    DossierSlotName.INFRASTRUCTURE: "Infrastructure",
    DossierSlotName.TIMING: "Timing",
}

# ---------------------------------------------------------------------------
# Transition detection helpers
# ---------------------------------------------------------------------------

# Valid upward status transitions that trigger a dossier_slot_filled event.
# "Upward" means the slot gained information since the last snapshot.
# Transitions FROM or TO deferred are explicitly excluded per plan §3.1.
_UPWARD_TRANSITIONS: frozenset[tuple[SlotStatus, SlotStatus]] = frozenset(
    {
        (SlotStatus.EMPTY, SlotStatus.PARTIAL),
        (SlotStatus.EMPTY, SlotStatus.FILLED),
        (SlotStatus.PARTIAL, SlotStatus.FILLED),
    }
)


def _is_upward_transition(from_status: SlotStatus, to_status: SlotStatus) -> bool:
    """Return True if from_status -> to_status is a valid slot-fill transition.

    Transitions involving DEFERRED are never upward (DEFERRED is a milestone-
    scoping marker, not a real status; cannot transition into or out of it in M-3).
    A deferred -> real transition is defensive-skipped with a debug log.
    """
    if from_status is SlotStatus.DEFERRED or to_status is SlotStatus.DEFERRED:
        return False
    return (from_status, to_status) in _UPWARD_TRANSITIONS


# ---------------------------------------------------------------------------
# Primary emitter (DEC-M3-DOSSIER-001)
# ---------------------------------------------------------------------------


def emit_dossier_slot_filled_events(
    pre: DossierState,
    post: DossierState,
) -> list[dict]:
    """Compute dossier slot-fill ScoreEvents from a pre/post hunt state diff.

    Compares each slot's status in ``pre`` against ``post`` and emits one
    ``dossier_slot_filled`` event dict per upward transition (empty->partial,
    empty->filled, partial->filled). Downward transitions, same-status, and
    transitions involving DEFERRED are silently ignored (idempotency by design —
    the transition detector IS the idempotency mechanism).

    Points awarded per event: ``int(SLOT_WEIGHTS[slot])`` (floor, not round).
    Skip-step transitions (empty->filled) emit ONE event at the slot weight;
    double-billing is explicitly rejected (per-slice plan §3.1).

    Emission order: slots iterated in DossierSlotName definition order (Identity,
    Predictions, Capability, TTPs, Motivation, Targeting, Denial, Infrastructure,
    Timing). Callers MUST persist dossier events AFTER per-IOC score_results events
    and BEFORE streak_continued — see per-slice plan §3.1 emission ordering.

    Parameters
    ----------
    pre:
        DossierState captured BEFORE store_stix_objects for the current hunt.
    post:
        DossierState captured AFTER store_stix_objects for the current hunt.

    Returns
    -------
    list[dict]
        Zero or more score event dicts, each with keys:
        ``action`` (str), ``points`` (int), ``indicator`` (str),
        ``rule_description`` (str, plain ASCII — no Rich markup).
        Ready for ``workspace_mgr.store_score_events(...)``.

    Notes
    -----
    - Pure function: no I/O, no workspace access, no side effects.
    - ``pre`` and ``post`` are DossierState frozen dataclasses; they are never
      mutated by this function (Sacred Practice 12 / DEC-M3-DOSSIER-001).
    - Callers own the persistence and must avoid double-persisting: either two
      separate store_score_events calls (per-IOC first, dossier second) or a
      single combined call — both are acceptable; this function returns events
      only once per call (DEC-M3-DOSSIER-002).
    """
    events: list[dict] = []

    # Iterate in canonical DossierSlotName definition order for deterministic output
    for slot in DossierSlotName:
        pre_slot = pre.slots.get(slot)
        post_slot = post.slots.get(slot)

        if pre_slot is None or post_slot is None:
            _LOG.debug(
                "emit_dossier_slot_filled_events: slot %r missing from pre or post state, skipping",
                slot,
            )
            continue

        from_status = pre_slot.status
        to_status = post_slot.status

        # Defensive guard: deferred -> real transition (future inference change)
        if from_status is SlotStatus.DEFERRED and to_status is not SlotStatus.DEFERRED:
            _LOG.debug(
                "emit_dossier_slot_filled_events: slot %r transitioned deferred->%s; "
                "skipping (M-4 owns inference for deferred slots)",
                slot,
                to_status.value,
            )
            continue

        if not _is_upward_transition(from_status, to_status):
            continue  # no transition, same status, or downward — no event

        weight = SLOT_WEIGHTS.get(slot, 1.0)
        points = int(weight)  # floor; Weights stay float for future confidence-multiplier
        display_name = _SLOT_DISPLAY_NAMES.get(slot, slot.value)
        rule_description = (
            f"Dossier slot filled: {display_name} ({from_status.value} -> {to_status.value})"
        )

        events.append(
            {
                "action": "dossier_slot_filled",
                "points": points,
                "indicator": slot.value,  # e.g. "identity", "ttps"
                "rule_description": rule_description,
            }
        )

        _LOG.debug(
            "emit_dossier_slot_filled_events: %r %s->%s +%d points",
            slot,
            from_status.value,
            to_status.value,
            points,
        )

    return events


# ---------------------------------------------------------------------------
# Scaffold emitter — DEC-M3-DOSSIER-005 (NOT called in M-3)
# ---------------------------------------------------------------------------


def emit_dossier_prediction_validated_event(prediction: PredictionRecord) -> dict:
    """Build a dossier_prediction_validated ScoreEvent dict (M-3 scaffold).

    This function is scaffolded in M-3 so M-4 implementers have a stable
    contract to target. It is NOT called anywhere in M-3 (Predictions slot
    remains DEFERRED until M-4 ships persistent prediction records).

    M-4 will wire the auto-validation logic: when a PredictionRecord transitions
    from 'pending' to 'validated' (by matching later evidence), this helper is
    called and the returned event is persisted via store_score_events().

    The DEC-68-DOSSIER-REFRAME-007 falsified-prediction-score-deduction question
    remains explicitly deferred to M-4. M-3 ships zero negative-score logic.

    Parameters
    ----------
    prediction:
        The PredictionRecord that was validated by later evidence.
        In M-3 this parameter is accepted for type-contract purposes;
        the returned event dict uses a placeholder indicator since no
        real prediction_id exists until M-4 persistence lands.

    Returns
    -------
    dict
        Score event with keys:
        ``action`` (``"dossier_prediction_validated"``),
        ``points`` (``int(SLOT_WEIGHTS[DossierSlotName.PREDICTIONS])`` == 4),
        ``indicator`` (prediction text hash or placeholder — M-4 will use a
        real prediction_id),
        ``rule_description`` (plain ASCII, non-empty).
    """
    points = int(SLOT_WEIGHTS[DossierSlotName.PREDICTIONS])  # 4
    # M-4 will supply a real prediction_id; M-3 uses a deterministic placeholder
    # derived from the prediction text so the scaffold is testable.
    indicator = f"prediction:{hash(prediction.text) & 0xFFFFFFFF:08x}"
    return {
        "action": "dossier_prediction_validated",
        "points": points,
        "indicator": indicator,
        "rule_description": "Dossier prediction validated by later evidence",
    }


# ---------------------------------------------------------------------------
# M-5 emitter — DEC-M5-FALSIFY-005
# ---------------------------------------------------------------------------


def emit_dossier_prediction_falsified_event(
    prediction: "PersistedPrediction",
    reason: str,
) -> dict:
    """Build a dossier_prediction_falsified ScoreEvent dict (M-5).

    Fires at points=0 per DEC-M4-PRED-006 (no negative-points events).
    The event flows through store_score_events so F62 streak, F63 milestone
    catch-up, and F64 _DOSSIER_ACTIONS filter all see it correctly.

    Parameters
    ----------
    prediction:
        The PersistedPrediction that was falsified.
    reason:
        Plain ASCII explanation of why the prediction is wrong.
        Stored in rule_description. No Rich markup (F64).

    Returns
    -------
    dict
        Score event dict with keys:
        ``action`` (``"dossier_prediction_falsified"``),
        ``points`` (``0`` — DEC-M4-PRED-006),
        ``indicator`` (prediction_id, e.g. ``"pred-3f19d55c"``),
        ``rule_description`` (plain ASCII, non-empty — F64-clean).
    """
    return {
        "action": "dossier_prediction_falsified",
        "points": 0,  # DEC-M4-PRED-006: no negative-points events
        "indicator": prediction.prediction_id,
        "rule_description": f"Dossier prediction falsified: {reason}",
    }
