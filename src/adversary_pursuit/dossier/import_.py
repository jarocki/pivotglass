"""Dossier STIX 2.1 bundle import — sole authority for bundle-to-ImportedDossier parsing.

This module is the SOLE authority for ``dossier_bundle_importer``.

``import_dossier(bundle_json)`` parses a STIX 2.1 bundle string into an in-memory
``ImportedDossier`` dataclass.  The result is a READ-ONLY value object — it NEVER
mutates the workspace SQLite (DEC-M9-IMPORT-READONLY-001).  ``compare_dossiers``
in ``dossier/comparison.py`` is the only consumer in M-9.

Import path:
  1. ``stix2.parse(bundle_json, allow_custom=True)`` — validates STIX 2.1 compliance
     and surfaces spec-version regressions at import time.
  2. Locate the threat-actor SDO (there must be exactly one produced by export_dossier).
  3. Reconstruct ``slot_states`` from the inverse of the §3.2 STIX mapping table.
  4. Rehydrate ``predictions`` from ``x_ap_predictions`` custom prop list.
  5. Extract ``analyst_notes`` from ``x_ap_analyst_notes`` custom prop list.
  6. Populate ``metadata`` from the ``x_ap_version`` / ``x_ap_exported_at`` /
     ``x_ap_workspace_id`` / ``x_ap_actor_identifier`` / ``x_ap_dossier_schema_version``
     custom props.

Loud failure contract (Sacred Practice 5):
  - Malformed JSON → ``ValueError`` with diagnostic.
  - Bundle missing ``type`` field → ``ValueError``.
  - Bundle missing threat-actor SDO → ``ValueError``.
  - ``x_ap_dossier_schema_version`` != 1 → ``RuntimeError`` (version mismatch, per
    DEC-M4-PERSIST-003 pattern applied to M-9).

@decision DEC-M9-IMPORT-READONLY-001
@title import_dossier does NOT write to the workspace SQLite
@status accepted
@rationale "Import becomes ingest" is the single largest authority risk: a write-path
    import would create dual authority between WorkspaceManager.store_stix_objects
    (F59 SCO authority) and the importer (DossierState authority). Holding M-9
    strictly read-only preserves F59 by construction. Conflict-resolution resolves
    trivially — read-only import cannot conflict.

@decision DEC-M9-CONFLICT-001
@title Read-only import has no workspace conflict because it never writes
@status accepted
@rationale DEC-M9-IMPORT-READONLY-001 eliminates the entire conflict-resolution surface.
    The imported shape is a value object held in memory and discarded after rendering.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

_LOG = logging.getLogger(__name__)

_BUNDLE_SCHEMA_VERSION: int = 1
"""Expected x_ap_dossier_schema_version in the threat-actor SDO.

Mismatch raises RuntimeError (loud failure, per DEC-M4-PERSIST-003 pattern).
"""


# ---------------------------------------------------------------------------
# ImportedDossier value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImportedDossier:
    """Read-only in-memory representation of a parsed dossier bundle.

    Produced by ``import_dossier``; consumed by ``compare_dossiers``.
    Never written to any SQLite database (DEC-M9-IMPORT-READONLY-001).

    Fields
    ------
    actor_identifier:
        The ``x_ap_actor_identifier`` value from the bundle's threat-actor SDO.
    slot_states:
        Mapping from DossierSlotName -> SlotStatus, reconstructed from the
        inverse of the §3.2 STIX mapping table.
    predictions:
        List of PersistedPrediction instances rehydrated from ``x_ap_predictions``.
    analyst_notes:
        Raw content strings from ``x_ap_analyst_notes``.
    metadata:
        Dict with x_ap_version, x_ap_exported_at, x_ap_workspace_id,
        x_ap_actor_identifier, x_ap_dossier_schema_version.
    """

    actor_identifier: str
    slot_states: dict  # dict[DossierSlotName, SlotStatus]
    predictions: list  # list[PersistedPrediction]
    analyst_notes: list[str]
    metadata: dict[str, str]


# ---------------------------------------------------------------------------
# Internal reconstruction helpers
# ---------------------------------------------------------------------------


def _reconstruct_slot_states(ta_dict: dict) -> dict:
    """Reconstruct slot_states mapping from the threat-actor SDO dict.

    Applies the inverse of the §3.2 STIX mapping table:
      - x_ap_dossier_identity_status  -> IDENTITY slot
      - x_ap_dossier_ttps.status      -> TTPS slot
      - x_ap_dossier_infrastructure.status -> INFRASTRUCTURE slot
      - x_ap_dossier_timing.status    -> TIMING slot
      - x_ap_dossier_targeting.status -> TARGETING slot
      - resource_level presence       -> CAPABILITY slot (filled/partial/deferred)
      - roles presence                -> MOTIVATION slot
      - x_ap_predictions list         -> PREDICTIONS slot
      - x_ap_dossier_denial.status    -> DENIAL slot

    Parameters
    ----------
    ta_dict:
        Threat-actor SDO as a plain dict (already parsed and serialized back).

    Returns
    -------
    dict[DossierSlotName, SlotStatus]
        Complete 9-slot mapping. Missing props default to DEFERRED.
    """
    from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus

    def _status(raw: str | None) -> "SlotStatus":
        if raw is None:
            return SlotStatus.DEFERRED
        try:
            return SlotStatus(raw)
        except ValueError:
            return SlotStatus.DEFERRED

    slot_states: dict = {}

    # Slot 1: IDENTITY — from x_ap_dossier_identity_status
    identity_status_raw = ta_dict.get("x_ap_dossier_identity_status")
    slot_states[DossierSlotName.IDENTITY] = _status(identity_status_raw)

    # Slot 2: TTPS — from x_ap_dossier_ttps.status
    ttps_obj = ta_dict.get("x_ap_dossier_ttps", {})
    slot_states[DossierSlotName.TTPS] = _status(
        ttps_obj.get("status") if isinstance(ttps_obj, dict) else None
    )

    # Slot 3: INFRASTRUCTURE — from x_ap_dossier_infrastructure.status
    infra_obj = ta_dict.get("x_ap_dossier_infrastructure", {})
    slot_states[DossierSlotName.INFRASTRUCTURE] = _status(
        infra_obj.get("status") if isinstance(infra_obj, dict) else None
    )

    # Slot 4: TIMING — from x_ap_dossier_timing.status
    timing_obj = ta_dict.get("x_ap_dossier_timing", {})
    slot_states[DossierSlotName.TIMING] = _status(
        timing_obj.get("status") if isinstance(timing_obj, dict) else None
    )

    # Slot 5: TARGETING — from x_ap_dossier_targeting.status
    targeting_obj = ta_dict.get("x_ap_dossier_targeting", {})
    slot_states[DossierSlotName.TARGETING] = _status(
        targeting_obj.get("status") if isinstance(targeting_obj, dict) else None
    )

    # Slot 6: CAPABILITY — from resource_level (inverse of _capability_to_resource_level)
    resource_level = ta_dict.get("resource_level")
    if resource_level == "organization":
        slot_states[DossierSlotName.CAPABILITY] = SlotStatus.FILLED
    elif resource_level == "club":
        slot_states[DossierSlotName.CAPABILITY] = SlotStatus.PARTIAL
    else:
        # Absent resource_level: was empty or deferred at export time
        # Default to EMPTY (not DEFERRED) because the bundle came from a real workspace
        slot_states[DossierSlotName.CAPABILITY] = SlotStatus.EMPTY

    # Slot 7: MOTIVATION — from roles presence (inverse of _motivation_to_roles)
    roles = ta_dict.get("roles")
    if roles and isinstance(roles, list) and len(roles) > 0:
        # Any non-empty roles list means the slot was filled or partial at export
        # We can't distinguish filled from partial from roles alone; use PARTIAL as
        # the conservative reconstruction (predictions can distinguish via count).
        slot_states[DossierSlotName.MOTIVATION] = SlotStatus.PARTIAL
    else:
        slot_states[DossierSlotName.MOTIVATION] = SlotStatus.EMPTY

    # Slot 8: PREDICTIONS — from x_ap_predictions list length
    predictions_list = ta_dict.get("x_ap_predictions", [])
    if not isinstance(predictions_list, list):
        predictions_list = []
    n_predictions = len(predictions_list)
    n_validated = sum(
        1 for p in predictions_list if isinstance(p, dict) and p.get("status") == "validated"
    )
    if n_predictions == 0:
        slot_states[DossierSlotName.PREDICTIONS] = SlotStatus.EMPTY
    elif n_validated >= 2:
        slot_states[DossierSlotName.PREDICTIONS] = SlotStatus.FILLED
    else:
        slot_states[DossierSlotName.PREDICTIONS] = SlotStatus.PARTIAL

    # Slot 9: DENIAL — from x_ap_dossier_denial.status
    denial_obj = ta_dict.get("x_ap_dossier_denial", {})
    slot_states[DossierSlotName.DENIAL] = _status(
        denial_obj.get("status") if isinstance(denial_obj, dict) else None
    )

    return slot_states


def _rehydrate_predictions(raw_list: list) -> list:
    """Rehydrate a list of prediction envelope dicts into PersistedPrediction instances.

    Mirrors the ``_deserialize_predictions`` helper shape from ``predictions.py``
    without using the sentinel-row schema (which is workspace-stored). Each envelope
    in ``x_ap_predictions`` is the §3.3 PredictionEnvelope shape.

    Parameters
    ----------
    raw_list:
        List of prediction envelope dicts from ``x_ap_predictions``.

    Returns
    -------
    list[PersistedPrediction]
        Rehydrated list; entries with missing required fields are skipped with a warning.
    """
    from adversary_pursuit.dossier.predictions import (
        ExpectedEvidence,
        FalsificationEvidence,
        PersistedPrediction,
    )

    result = []
    for entry in raw_list:
        if not isinstance(entry, dict):
            _LOG.warning("_rehydrate_predictions: skipping non-dict entry: %r", entry)
            continue
        try:
            ee_raw = entry.get("expected_evidence") or {}
            ee = ExpectedEvidence(
                sco_type=ee_raw.get("sco_type"),
                value_regex=ee_raw.get("value_regex"),
                asn_in=ee_raw.get("asn_in"),
                note_keyword_any=ee_raw.get("note_keyword_any"),
            )
            fe: FalsificationEvidence | None = None
            fe_raw = entry.get("falsification_evidence")
            if fe_raw and isinstance(fe_raw, dict):
                fe = FalsificationEvidence(
                    negative_sco_type=fe_raw.get("negative_sco_type"),
                    negative_value_regex=fe_raw.get("negative_value_regex"),
                    negative_asn_in=fe_raw.get("negative_asn_in"),
                    contradiction_keyword_any=fe_raw.get("contradiction_keyword_any"),
                    stale_after_n_hunts=fe_raw.get("stale_after_n_hunts"),
                )
            pred = PersistedPrediction(
                prediction_id=entry["prediction_id"],
                text=entry["text"],
                slot=entry["slot"],
                status=entry.get("status", "pending"),
                expected_evidence=ee,
                created_at=entry.get("created_at", ""),
                validated_at=entry.get("validated_at"),
                validated_by_sco_id=entry.get("validated_by_sco_id"),
                falsification_evidence=fe,
                created_at_hunt_count=entry.get("created_at_hunt_count", 0),
            )
            result.append(pred)
        except (KeyError, TypeError) as exc:
            _LOG.warning("_rehydrate_predictions: skipping malformed entry: %s — %r", exc, entry)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def import_dossier(bundle_json: str) -> ImportedDossier:
    """Parse a STIX 2.1 bundle JSON string into an ImportedDossier value object.

    This is the SOLE authority for ``dossier_bundle_importer``.
    The returned object is read-only and never written to any workspace SQLite
    (DEC-M9-IMPORT-READONLY-001).

    Validation:
      - Malformed JSON → ``ValueError``.
      - Missing ``type`` key → ``ValueError``.
      - Not a bundle (type != 'bundle') → ``ValueError``.
      - Missing threat-actor SDO in objects → ``ValueError``.
      - ``x_ap_dossier_schema_version`` != 1 → ``RuntimeError``.

    Parameters
    ----------
    bundle_json:
        STIX 2.1 bundle JSON string, e.g. from ``export_dossier``.

    Returns
    -------
    ImportedDossier
        In-memory value object with slot_states, predictions, analyst_notes, metadata.

    Raises
    ------
    ValueError
        For malformed or structurally invalid bundles.
    RuntimeError
        For schema version mismatches.
    """
    import stix2

    # Step 1: validate as JSON
    try:
        raw = json.loads(bundle_json)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"import_dossier: bundle_json is not valid JSON — {exc}. "
            "Provide a JSON string produced by export_dossier."
        ) from exc

    # Step 2: basic bundle structure check
    if not isinstance(raw, dict):
        raise ValueError(
            f"import_dossier: bundle_json must be a JSON object (dict), got {type(raw).__name__}."
        )
    if "type" not in raw:
        raise ValueError(
            "import_dossier: bundle missing required 'type' field. "
            "Expected a STIX 2.1 bundle with type='bundle'."
        )
    if raw.get("type") != "bundle":
        raise ValueError(
            f"import_dossier: bundle 'type' is {raw['type']!r}, expected 'bundle'. "
            "Provide a STIX 2.1 bundle produced by export_dossier."
        )

    # Step 3: parse through stix2 for spec compliance
    try:
        parsed_bundle = stix2.parse(bundle_json, allow_custom=True)
    except Exception as exc:
        raise ValueError(
            f"import_dossier: stix2.parse rejected the bundle — {exc}. "
            "The bundle may have been produced by a different tool or schema version."
        ) from exc

    # Step 4: locate the threat-actor SDO
    objects_list = list(getattr(parsed_bundle, "objects", []) or [])
    ta_objects = [obj for obj in objects_list if getattr(obj, "type", None) == "threat-actor"]

    if not ta_objects:
        raise ValueError(
            "import_dossier: bundle contains no threat-actor SDO. "
            "AP dossier bundles must include exactly one threat-actor SDO "
            "produced by export_dossier. This bundle may have been produced "
            "by a different tool."
        )

    # Use the first threat-actor (export_dossier produces exactly one)
    ta_obj = ta_objects[0]

    # Serialize back to dict to access custom props (stix2 object attribute access
    # is limited for unknown custom props; dict form is the safe access pattern)
    ta_dict = json.loads(ta_obj.serialize())

    # Step 5: schema version check (loud failure per DEC-M4-PERSIST-003 pattern)
    schema_version = ta_dict.get("x_ap_dossier_schema_version")
    if schema_version is None:
        raise ValueError(
            "import_dossier: threat-actor SDO is missing 'x_ap_dossier_schema_version'. "
            "This bundle was not produced by export_dossier or predates the M-9 schema."
        )
    if schema_version != _BUNDLE_SCHEMA_VERSION:
        raise RuntimeError(
            f"import_dossier: bundle schema version {schema_version!r} does not match "
            f"runtime schema version {_BUNDLE_SCHEMA_VERSION}. "
            "The bundle was produced by a different AP version. "
            "Upgrade or downgrade AP to match the bundle schema version."
        )

    # Step 6: extract actor_identifier
    actor_identifier = ta_dict.get("x_ap_actor_identifier") or ta_dict.get("name", "unknown")

    # Step 7: reconstruct slot_states from the inverse STIX mapping
    slot_states = _reconstruct_slot_states(ta_dict)

    # Step 8: rehydrate predictions from x_ap_predictions
    raw_predictions = ta_dict.get("x_ap_predictions", [])
    if not isinstance(raw_predictions, list):
        raw_predictions = []
    predictions = _rehydrate_predictions(raw_predictions)

    # Step 9: extract analyst notes
    raw_notes = ta_dict.get("x_ap_analyst_notes", [])
    if not isinstance(raw_notes, list):
        raw_notes = []
    analyst_notes: list[str] = []
    for note_entry in raw_notes:
        if isinstance(note_entry, dict):
            content = note_entry.get("content", "")
            if content:
                analyst_notes.append(content)
        elif isinstance(note_entry, str):
            analyst_notes.append(note_entry)

    # Step 10: build metadata dict
    metadata: dict[str, str] = {
        "x_ap_version": str(ta_dict.get("x_ap_version", "")),
        "x_ap_exported_at": str(ta_dict.get("x_ap_exported_at", "")),
        "x_ap_workspace_id": str(ta_dict.get("x_ap_workspace_id", "")),
        "x_ap_actor_identifier": actor_identifier,
        "x_ap_dossier_schema_version": str(schema_version),
    }

    return ImportedDossier(
        actor_identifier=actor_identifier,
        slot_states=slot_states,
        predictions=predictions,
        analyst_notes=analyst_notes,
        metadata=metadata,
    )
