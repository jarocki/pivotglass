"""Dossier slot inference — read-only, pure-function slot fill state computation.

Consumes a list of STIX SCO dicts (as returned by WorkspaceManager.get_stix_objects())
and returns a DossierState value object describing each slot's fill status and
evidence count. No I/O, no workspace mutations, no x_ap_* writes.

@decision DEC-M1-DOSSIER-001 (inference authority)
@title slot_inference.infer_dossier_state() is a pure function; never mutates workspace
@status accepted
@rationale Sacred Practice 12: the question "what is the dossier state of this workspace?"
    has exactly one owner (this module). The function is:
      - Pure: same SCO list -> same DossierState, no hidden state.
      - Read-only: it consumes the SCO list but never calls any WorkspaceManager
        mutator, never sets x_ap_* provenance fields (DEC-59-STIX-PROVENANCE-001
        preserved), and never emits ScoreEvents (DEC-M1-DOSSIER-002 / M-3 scope).
      - Deterministic: iterates SCO types against an explicit SLOT_EVIDENCE_TYPES
        table; unknown types are silently skipped (no auto-discovery).
    The DossierState value object is the handoff point to panel.render().

@decision DEC-M1-DOSSIER-INFERENCE-STATUS-001
@title partial vs filled threshold: 1 distinct SCO type -> partial; 2+ -> filled
@status accepted
@rationale Phase 16 §3 defines confidence levels tied to distinct-source count
    (e.g., Identity high = independently corroborated by >=2 evidence types from
    >=2 modules). M-1 uses distinct SCO TYPE count as the proxy for corroboration:
    one type -> partial (single uncorroborated source class); two or more distinct
    types -> filled (two independent evidence categories). This is a conservative
    mapping; M-2 will refine by adding per-module attribution. The threshold is
    intentionally simple so it is testable with synthetic fixtures.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from adversary_pursuit.dossier.slots import (
    M1_ACTIVE_SLOTS,
    SLOT_EVIDENCE_TYPES,
    DossierSlotName,
    SlotStatus,
)

_LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SlotState:
    """Immutable state for a single dossier slot.

    Parameters
    ----------
    name:
        The DossierSlotName enum member for this slot.
    status:
        Current fill status: empty / partial / filled / deferred.
    evidence_count:
        Number of SCOs that contribute to this slot. Zero when status is
        empty or deferred; >= 1 when partial or filled.
    contributing_types:
        Frozenset of STIX type strings that contributed evidence.
        Used to determine partial vs filled threshold.
    """

    name: DossierSlotName
    status: SlotStatus
    evidence_count: int = 0
    contributing_types: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class DossierState:
    """Immutable snapshot of all 9 slot fill states for the current workspace.

    Produced by infer_dossier_state() and consumed by panel.render().
    Contains no references to WorkspaceManager or any mutable I/O resource.

    Parameters
    ----------
    slots:
        Mapping from DossierSlotName -> SlotState. Always contains all 9 slots.
    total_sco_count:
        Total number of input SCOs that were processed (for panel display).
    """

    slots: dict[DossierSlotName, SlotState]
    total_sco_count: int = 0


# ---------------------------------------------------------------------------
# Inference engine
# ---------------------------------------------------------------------------


def infer_dossier_state(scos: list[dict]) -> DossierState:
    """Infer dossier slot fill state from a list of STIX SCO dicts.

    Pure function: same input -> same output; no side effects; no I/O.
    Consumes WorkspaceManager.get_stix_objects() output directly.

    Parameters
    ----------
    scos:
        List of plain STIX SCO dicts as returned by
        WorkspaceManager.get_stix_objects(). May include x_ap_* provenance
        fields which are read but never modified (DEC-59-STIX-PROVENANCE-001).
        Unknown SCO types are silently skipped (no auto-discovery).

    Returns
    -------
    DossierState
        Immutable snapshot of all 9 slot fill states and total SCO count.

    Notes
    -----
    - Slots 4-9 (Timing / Targeting / Capability / Motivation / Predictions /
      Denial) are always DEFERRED in M-1 — their inference paths land in M-2,
      M-4, and M-5. They appear in DossierState with status=DEFERRED and
      evidence_count=0.
    - Status thresholds: 1 distinct SCO type -> partial; >=2 -> filled
      (DEC-M1-DOSSIER-INFERENCE-STATUS-001).
    - x_ap_* provenance fields on input dicts are not read or written by this
      function; they pass through transparently.
    """
    # Accumulate evidence per slot: slot -> set of contributing STIX types
    slot_type_sets: dict[DossierSlotName, set[str]] = {slot: set() for slot in M1_ACTIVE_SLOTS}
    slot_sco_counts: dict[DossierSlotName, int] = {slot: 0 for slot in M1_ACTIVE_SLOTS}

    for sco in scos:
        sco_type = sco.get("type", "")
        if not sco_type:
            _LOG.debug("infer_dossier_state: SCO missing 'type' field, skipping")
            continue

        target_slots = SLOT_EVIDENCE_TYPES.get(sco_type)
        if target_slots is None:
            # Unknown type — silently skip (DEC-M1-DOSSIER-001 forbidden shortcut:
            # no auto-discovery; future types are added to SLOT_EVIDENCE_TYPES explicitly)
            _LOG.debug("infer_dossier_state: unknown SCO type %r, skipping", sco_type)
            continue

        for slot in target_slots:
            if slot in slot_type_sets:
                slot_type_sets[slot].add(sco_type)
                slot_sco_counts[slot] = slot_sco_counts[slot] + 1

    # Build SlotState for each active slot
    active_slot_states: dict[DossierSlotName, SlotState] = {}
    for slot in M1_ACTIVE_SLOTS:
        types_seen = slot_type_sets[slot]
        count = slot_sco_counts[slot]

        if count == 0:
            status = SlotStatus.EMPTY
        elif len(types_seen) >= 2:
            # Two or more distinct SCO type categories -> filled
            # (DEC-M1-DOSSIER-INFERENCE-STATUS-001)
            status = SlotStatus.FILLED
        else:
            # Exactly one distinct SCO type -> partial
            status = SlotStatus.PARTIAL

        active_slot_states[slot] = SlotState(
            name=slot,
            status=status,
            evidence_count=count,
            contributing_types=frozenset(types_seen),
        )

    # Build deferred SlotState for all non-active slots (Timing through Denial)
    deferred_slot_names = [s for s in DossierSlotName if s not in M1_ACTIVE_SLOTS]
    deferred_states: dict[DossierSlotName, SlotState] = {
        slot: SlotState(
            name=slot,
            status=SlotStatus.DEFERRED,
            evidence_count=0,
            contributing_types=frozenset(),
        )
        for slot in deferred_slot_names
    }

    # Merge: all 9 slots present in result
    all_slots: dict[DossierSlotName, SlotState] = {**active_slot_states, **deferred_states}

    return DossierState(slots=all_slots, total_sco_count=len(scos))
