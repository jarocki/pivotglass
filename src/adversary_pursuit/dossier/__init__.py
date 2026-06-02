"""Dossier package — sole authority for slot inference and panel rendering.

This package is the M-1/M-2 implementation of the Threat Actor Dossier layer
introduced by the Phase 16 strategic scoping (W-68-DOSSIER-REFRAME-SCOPING).

@decision DEC-M1-DOSSIER-001
@title dossier/ is the sole read-only authority for slot inference
@status accepted
@rationale Sacred Practice 12: one authority per operational fact. The question
    "what is the dossier state of this workspace?" gets exactly one owner.
    Putting inference helpers in core/ or gamification/ would split the authority
    across two packages on day one. This package places that authority here and
    nowhere else. It CONSUMES WorkspaceManager.get_stix_objects() and MUST NOT
    call any workspace mutator or set any x_ap_* provenance field
    (DEC-59-STIX-PROVENANCE-001 preserved).

Public API (M-1):
  - slots.DossierSlotName — 9-slot vocabulary enum (Phase 16 §3)
  - slots.SlotStatus — {empty, partial, filled, deferred} status enum
  - slots.SLOT_WEIGHTS — per-slot importance weights from Phase 16 §3
  - slot_inference.infer_dossier_state(scos) -> DossierState
  - panel.render(state) -> rich.panel.Panel

Public API additions (M-2, DEC-M2-DOSSIER-001):
  - slot_inference.infer_dossier_state_full(scos, module_runs, notes) -> DossierState
  - slots.PredictionRecord — typed scaffold dataclass for slot 8 (DEC-M2-DOSSIER-004)
  - slots.DenialStrategyRecord — typed scaffold dataclass for slot 9 (DEC-M2-DOSSIER-004)

Public API additions (M-3, DEC-M3-DOSSIER-001 / DEC-M3-DOSSIER-005):
  - scoring.emit_dossier_slot_filled_events(pre, post) -> list[dict]
  - scoring.emit_dossier_prediction_validated_event(prediction) -> dict
"""

from adversary_pursuit.dossier.scoring import (
    emit_dossier_prediction_validated_event,
    emit_dossier_slot_filled_events,
)
from adversary_pursuit.dossier.slot_inference import (
    infer_dossier_state,
    infer_dossier_state_full,
)
from adversary_pursuit.dossier.slots import (
    SLOT_WEIGHTS,
    DenialStrategyRecord,
    DossierSlotName,
    PredictionRecord,
    SlotStatus,
)

__all__ = [
    "DossierSlotName",
    "SlotStatus",
    "SLOT_WEIGHTS",
    "infer_dossier_state",
    "infer_dossier_state_full",
    "PredictionRecord",
    "DenialStrategyRecord",
    "emit_dossier_slot_filled_events",
    "emit_dossier_prediction_validated_event",
]
