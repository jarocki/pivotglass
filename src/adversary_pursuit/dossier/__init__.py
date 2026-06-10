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

Public API additions (M-4, DEC-M4-PERSIST-001..003 / DEC-M4-PRED-001..006):
  - state.load_dossier_state(workspace_mgr) -> DossierState | None
  - state.save_dossier_state(workspace_mgr, state) -> None
  - state.default_deferred_state() -> DossierState
  - state.apply_predictions_overlay(state, predictions) -> DossierState
  - predictions.load_predictions_log(workspace_mgr) -> list[PersistedPrediction]
  - predictions.save_predictions_log(workspace_mgr, predictions) -> None
  - predictions.validate_predictions(predictions, new_scos, new_notes) -> list[ValidationResult]
  - predictions.PersistedPrediction — full lifecycle dataclass
  - predictions.ExpectedEvidence — typed match-pattern dataclass
  - predictions.ValidationResult — result of one prediction check

Public API additions (M-5, DEC-M5-DENIAL-001..003 / DEC-M5-NOTE-001..003 /
                         DEC-M5-FALSIFY-001..008):
  - slot_inference._is_dga_shaped(label) -> bool  (exported for unit testing)
  - predictions.FalsificationEvidence — typed contradiction-pattern dataclass
  - predictions.FalsificationResult — result of one falsification check
  - predictions.falsify_predictions(predictions, new_scos, new_notes, hunt_count)
  - predictions.mark_confirmed_or_falsified(predictions, vr_list, fr_list)
  - predictions.manual_falsify(predictions, prediction_id, reason)
  - scoring.emit_dossier_prediction_falsified_event(prediction, reason) -> dict

Public API additions (M-8, DEC-M8-NOVELTY-001..010):
  - novelty.compute_novelty_hash(slot, extractor_name, sco_types) -> str
  - novelty.novelty_enabled() -> bool
  - novelty.NoveltyCache(path=None) — global cross-workspace novelty registry
  - novelty.detect_novelty(slot, extractor_name, sco_types, cache) -> bool
  - novelty.emit_dossier_novelty_recognized_event(slot, extractor_name, sco_types) -> dict
  - novelty._SLOT_EXTRACTOR_NAMES — slot -> extractor name constant map

Public API additions (M-9, DEC-M9-STIX-MAPPING-001..002 / DEC-M9-COMPLETION-001 /
                         DEC-M9-LIBRARY-LOCATION-001 / DEC-M9-LIBRARY-OPTIN-001):
  - export.export_dossier(workspace_mgr, actor_identifier) -> str
  - export.publish_to_library(bundle_json, actor_identifier) -> Path
  - export.list_library() -> list[Path]
  - export.load_from_library(actor_identifier) -> str
  - export.library_root() -> Path
  - export.library_publish_enabled() -> bool
  - import_.import_dossier(bundle_json) -> ImportedDossier
  - import_.ImportedDossier — read-only in-memory dossier value object
  - comparison.compare_dossiers(local, remote) -> ComparisonReport
  - comparison.ComparisonReport — slot-by-slot diff value object
  - comparison.format_comparison_report(report) -> str
"""

from adversary_pursuit.dossier.comparison import (
    ComparisonReport,
    compare_dossiers,
    format_comparison_report,
)
from adversary_pursuit.dossier.export import (
    export_dossier,
    library_publish_enabled,
    library_root,
    list_library,
    load_from_library,
    publish_to_library,
)
from adversary_pursuit.dossier.import_ import (
    ImportedDossier,
    import_dossier,
)
from adversary_pursuit.dossier.novelty import (
    _SLOT_EXTRACTOR_NAMES,
    NoveltyCache,
    compute_novelty_hash,
    detect_novelty,
    emit_dossier_novelty_recognized_event,
    novelty_enabled,
)
from adversary_pursuit.dossier.predictions import (
    ExpectedEvidence,
    FalsificationEvidence,
    FalsificationResult,
    PersistedPrediction,
    ValidationResult,
    falsify_predictions,
    load_predictions_log,
    manual_falsify,
    mark_confirmed,
    mark_confirmed_or_falsified,
    save_predictions_log,
    validate_predictions,
)
from adversary_pursuit.dossier.scoring import (
    emit_dossier_prediction_falsified_event,
    emit_dossier_prediction_validated_event,
    emit_dossier_slot_filled_events,
)
from adversary_pursuit.dossier.slot_inference import (
    _is_dga_shaped,
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
from adversary_pursuit.dossier.state import (
    apply_predictions_overlay,
    default_deferred_state,
    load_dossier_state,
    save_dossier_state,
)

__all__ = [
    "DossierSlotName",
    "SlotStatus",
    "SLOT_WEIGHTS",
    "infer_dossier_state",
    "infer_dossier_state_full",
    "_is_dga_shaped",
    "PredictionRecord",
    "DenialStrategyRecord",
    "emit_dossier_slot_filled_events",
    "emit_dossier_prediction_validated_event",
    # M-4 state persistence
    "load_dossier_state",
    "save_dossier_state",
    "default_deferred_state",
    "apply_predictions_overlay",
    # M-4 predictions lifecycle
    "load_predictions_log",
    "save_predictions_log",
    "validate_predictions",
    "mark_confirmed",
    "PersistedPrediction",
    "ExpectedEvidence",
    "ValidationResult",
    # M-5 falsification engine
    "FalsificationEvidence",
    "FalsificationResult",
    "falsify_predictions",
    "mark_confirmed_or_falsified",
    "manual_falsify",
    "emit_dossier_prediction_falsified_event",
    # M-8 novelty detection (DEC-M8-NOVELTY-001..010)
    "compute_novelty_hash",
    "novelty_enabled",
    "NoveltyCache",
    "detect_novelty",
    "emit_dossier_novelty_recognized_event",
    "_SLOT_EXTRACTOR_NAMES",
    # M-9 export / import / comparison / library (DEC-M9-STIX-MAPPING-001..002 /
    #   DEC-M9-COMPLETION-001 / DEC-M9-LIBRARY-LOCATION-001 / DEC-M9-LIBRARY-OPTIN-001)
    "export_dossier",
    "publish_to_library",
    "list_library",
    "load_from_library",
    "library_root",
    "library_publish_enabled",
    "import_dossier",
    "ImportedDossier",
    "compare_dossiers",
    "ComparisonReport",
    "format_comparison_report",
]
