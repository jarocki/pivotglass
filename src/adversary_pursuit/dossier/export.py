"""Dossier STIX 2.1 bundle export + public library helpers.

This module is the SOLE authority for:
  - Serializing a workspace DossierState + PredictionsLog + AnalystNotes to a
    STIX 2.1 bundle JSON string (``export_dossier``).
  - Local dossier library management (``publish_to_library``, ``list_library``,
    ``load_from_library``, ``library_root``, ``library_publish_enabled``).
  - ``actor_identifier`` filesystem-safety validation (``_validate_actor_identifier``).

The export path is a READ-ONLY consumer of:
  - M-4 ``load_dossier_state`` / ``default_deferred_state``
  - M-4 ``load_predictions_log``
  - M-5 analyst notes via the ``_read_analyst_notes`` query pattern from tools.py
  - ``core/graph.py::RelationshipGraph.export_stix_bundle`` (F59 SCOs + SROs)

No workspace mutation occurs. ``core/workspace.py`` is BYTEWISE UNCHANGED.
``models/database.py`` is BYTEWISE UNCHANGED (library files are plain JSON on disk).

@decision DEC-M9-STIX-MAPPING-001
@title Slot-to-STIX mapping: STIX-native fields for slots 1/6/7; x_ap_* for the rest
@status accepted
@rationale Using STIX-native aliases/resource_level/roles maximises interop with
    OpenCTI/MISP. Custom x_ap_dossier_* props carry the remaining slots
    deterministically so the import path can reconstruct slot_states without
    ambiguity. Placing all dossier metadata on the synthesized threat-actor SDO
    (not the bundle root) is required because python-stix2's Bundle class strips
    unknown top-level keys (DEC-M9-STIX-MAPPING-002 explains the payload shape).

@decision DEC-M9-STIX-MAPPING-002
@title x_ap_predictions and x_ap_analyst_notes are custom props on the threat-actor SDO
@status accepted
@rationale python-stix2 Bundle strips unknown top-level keys; SDOs carry custom
    props losslessly with allow_custom=True. One-to-one envelope shape removes
    ambiguity between authoring and consuming code paths.

@decision DEC-M9-ACTOR-ID-001
@title actor_identifier is an explicit user-provided string; default = workspace_mgr.active
@status accepted
@rationale Explicit string + safe-default keeps the LLM tool surface trivially testable
    and the library file-name space mechanically safe. Filesystem-safety regex blocks
    path traversal at the smallest abstraction.

@decision DEC-M9-LIBRARY-LOCATION-001
@title Default library root ~.ap/dossier_library/; override AP_DOSSIER_LIBRARY
@status accepted
@rationale Mirrors the M-8 ~/.ap/dossier_novelty.sqlite cross-workspace location
    pattern. 0o700 is the AP cross-workspace permission floor for IOC content files.

@decision DEC-M9-LIBRARY-OPTIN-001
@title Library WRITES require AP_DOSSIER_PUBLISH=on; reads unconditional
@status accepted
@rationale Two-step consent. Loud-fail rather than silent skip honors Sacred Practice 5.

@decision DEC-M9-PRIVACY-001
@title Bundles contain raw IOCs verbatim; no PII redaction layer
@status accepted
@rationale A redaction layer would invent a parallel "trusted vs untrusted IOC"
    authority contradicting F59's single-authority-for-x_ap_* invariant. The opt-in
    env var is the consent gate. Publishing a dossier means publishing the underlying
    IOCs verbatim -- user responsibility.

Privacy note: bundles published to the library contain raw IOCs from the user's
workspace (IP addresses, domain names, email addresses, file hashes, etc.).
Publishing a dossier via AP_DOSSIER_PUBLISH=on means you accept responsibility
for the disclosure of those IOCs. No automatic redaction or sanitization occurs.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adversary_pursuit.core.workspace import WorkspaceManager

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ACTOR_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
"""Filesystem-safe actor identifier pattern (DEC-M9-ACTOR-ID-001).

Accepts 1-128 characters of alphanumeric, dot, underscore, or hyphen.
Rejects empty strings, slashes (path traversal), NUL bytes, and oversized names.
"""

_DOSSIER_BUNDLE_SCHEMA_VERSION: int = 1
"""Schema version embedded in every bundle as x_ap_dossier_schema_version.

Increment when the STIX mapping table (§3.2 of the plan) changes in a
backward-incompatible way (import path raises RuntimeError on mismatch).
"""

_LIBRARY_ENV_VAR = "AP_DOSSIER_LIBRARY"
"""Environment variable that overrides the default library root path."""

_PUBLISH_ENV_VAR = "AP_DOSSIER_PUBLISH"
"""Environment variable that gates library writes (must equal 'on', case-insensitive)."""

_DEFAULT_LIBRARY_NAME = "dossier_library"
"""Subdirectory name under ~/.ap/ for the default library root."""


# ---------------------------------------------------------------------------
# Library location + opt-in helpers (DEC-M9-LIBRARY-LOCATION-001 /
#                                     DEC-M9-LIBRARY-OPTIN-001)
# ---------------------------------------------------------------------------


def library_root() -> Path:
    """Return the absolute Path to the dossier library directory.

    Consults ``AP_DOSSIER_LIBRARY`` first; falls back to ``~/.ap/dossier_library/``.
    The directory is NOT created here — creation happens on first publish so that
    read-only operations never require the directory to exist.

    Returns
    -------
    Path
        Absolute path to the library root (may or may not exist yet).
    """
    override = os.environ.get(_LIBRARY_ENV_VAR, "").strip()
    if override:
        return Path(override)
    return Path.home() / ".ap" / _DEFAULT_LIBRARY_NAME


def library_publish_enabled() -> bool:
    """Return True iff the ``AP_DOSSIER_PUBLISH`` env var is set to ``"on"`` (case-insensitive).

    Reads the env var on every call so that test-time monkeypatching of the
    environment is respected without module-level caching.

    Returns
    -------
    bool
        True when AP_DOSSIER_PUBLISH == "on" (case-insensitive), False otherwise.
    """
    return os.environ.get(_PUBLISH_ENV_VAR, "").strip().lower() == "on"


# ---------------------------------------------------------------------------
# Actor identifier validation (DEC-M9-ACTOR-ID-001)
# ---------------------------------------------------------------------------


def _validate_actor_identifier(actor_identifier: str) -> None:
    """Raise ValueError if actor_identifier is not filesystem-safe.

    Enforces the ``^[A-Za-z0-9._-]{1,128}$`` pattern from DEC-M9-ACTOR-ID-001.
    Called at both export and library boundaries so callers never need to
    repeat the check.

    Parameters
    ----------
    actor_identifier:
        The identifier to validate.

    Raises
    ------
    ValueError
        When the identifier is empty, too long, or contains unsafe characters.
    """
    if not actor_identifier:
        raise ValueError(
            "actor_identifier must be non-empty. "
            "It will be used as a filename in the dossier library."
        )
    if not _ACTOR_ID_RE.match(actor_identifier):
        raise ValueError(
            f"actor_identifier {actor_identifier!r} contains invalid characters or "
            "exceeds 128 characters. Allowed pattern: ^[A-Za-z0-9._-]{1,128}$. "
            "This restriction prevents path traversal and filesystem-unsafe names."
        )


# ---------------------------------------------------------------------------
# Internal STIX assembly helpers
# ---------------------------------------------------------------------------


def _get_analyst_notes_for_export(workspace_mgr: "WorkspaceManager") -> list[str]:
    """Read analyst notes from the workspace as a list of content strings.

    Mirrors ``tools.py::_read_analyst_notes`` pattern (DEC-M9-NO-WORKSPACE-EDIT-001:
    no new workspace method added). Returns empty list on any error.

    Parameters
    ----------
    workspace_mgr:
        Active WorkspaceManager with a live ``_engine``.

    Returns
    -------
    list[str]
        Note content strings ordered by id ascending.
    """
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from adversary_pursuit.models.database import AnalystNote

        with Session(workspace_mgr._engine) as session:
            rows = session.scalars(select(AnalystNote).order_by(AnalystNote.id)).all()
            return [r.content for r in rows]
    except Exception:  # noqa: BLE001
        return []


def _capability_to_resource_level(slot_status: str) -> str | None:
    """Map Capability slot status to STIX threat-actor resource_level value.

    Per DEC-M9-STIX-MAPPING-001:
      filled   -> 'organization'
      partial  -> 'club'
      empty / deferred -> omitted (return None)

    Parameters
    ----------
    slot_status:
        SlotStatus.value string ('filled', 'partial', 'empty', 'deferred').

    Returns
    -------
    str | None
        STIX resource_level value or None to omit the field.
    """
    mapping = {
        "filled": "organization",
        "partial": "club",
    }
    return mapping.get(slot_status)


def _motivation_to_roles(slot_status: str) -> list[str] | None:
    """Map Motivation slot status to a default STIX threat-actor roles list.

    Per DEC-M9-STIX-MAPPING-001: deferred status -> roles omitted.
    For filled/partial: we emit a placeholder 'unknown' roles list since the
    actual motivation values are not yet inferred from text in M-9.
    The import path reconstructs the slot_status from role list presence, not content.

    Parameters
    ----------
    slot_status:
        SlotStatus.value string.

    Returns
    -------
    list[str] | None
        List of STIX role strings or None to omit the field entirely.
    """
    if slot_status in ("empty", "deferred"):
        return None
    # filled or partial: emit non-empty roles to signal slot has been touched
    return ["unknown"]


def _identity_to_aliases(scos: list[dict]) -> list[str]:
    """Extract distinct identity-related values from SCOs for threat-actor aliases.

    Per DEC-M9-STIX-MAPPING-001: aliases sourced from email-addr, user-account,
    x509-certificate SCO values. Deduped, sorted.

    Parameters
    ----------
    scos:
        List of STIX SCO dicts from workspace_mgr.get_stix_objects().

    Returns
    -------
    list[str]
        Sorted, deduplicated list of identity-contributing SCO values.
    """
    identity_types = {"email-addr", "user-account", "x509-certificate"}
    seen: set[str] = set()
    aliases: list[str] = []

    for sco in scos:
        sco_type = sco.get("type", "")
        if sco_type not in identity_types:
            continue
        value: str | None = None
        if sco_type == "email-addr":
            value = sco.get("value")
        elif sco_type == "user-account":
            value = sco.get("user_id") or sco.get("value")
        elif sco_type == "x509-certificate":
            value = sco.get("subject") or sco.get("issuer") or sco.get("value")
        if value and value not in seen:
            seen.add(value)
            aliases.append(value)

    return sorted(aliases)


def _build_slot_custom_props(
    dossier_state: object,  # DossierState
    scos: list[dict],
) -> dict:
    """Build the x_ap_dossier_* custom properties for the threat-actor SDO.

    Covers slots 2 (TTPs), 3 (Infrastructure), 4 (Timing), 5 (Targeting), 9 (Denial)
    plus the metadata props that don't map to STIX-native fields.

    Slots 1/6/7 are handled by caller (_identity_to_aliases, _capability_to_resource_level,
    _motivation_to_roles) because they map to STIX-native fields.
    Slot 8 (Predictions) is handled separately via x_ap_predictions.

    Parameters
    ----------
    dossier_state:
        DossierState instance (frozen dataclass).
    scos:
        Raw workspace SCO dicts (for evidence count computation).

    Returns
    -------
    dict
        Custom property dict ready to be spread into the threat-actor SDO kwargs.
    """
    from adversary_pursuit.dossier.slots import DossierSlotName

    props: dict = {}
    slots = dossier_state.slots

    def _slot_status(name: "DossierSlotName") -> str:
        return slots[name].status.value if name in slots else "deferred"

    def _slot_evidence_count(name: "DossierSlotName") -> int:
        return slots[name].evidence_count if name in slots else 0

    # Slot 2: TTPs — count by SCO type
    ttp_types_in_workspace: dict[str, int] = {}
    for sco in scos:
        sco_type = sco.get("type", "")
        if sco_type in ("url", "file"):
            ttp_types_in_workspace[sco_type] = ttp_types_in_workspace.get(sco_type, 0) + 1
    props["x_ap_dossier_ttps"] = {
        "status": _slot_status(DossierSlotName.TTPS),
        "distinct_sco_type_count": len(ttp_types_in_workspace),
        "evidence_count": _slot_evidence_count(DossierSlotName.TTPS),
    }

    # Slot 3: Infrastructure
    infra_types_in_workspace: dict[str, int] = {}
    for sco in scos:
        sco_type = sco.get("type", "")
        if sco_type in ("domain-name", "ipv4-addr", "ipv6-addr", "autonomous-system"):
            infra_types_in_workspace[sco_type] = infra_types_in_workspace.get(sco_type, 0) + 1
    props["x_ap_dossier_infrastructure"] = {
        "status": _slot_status(DossierSlotName.INFRASTRUCTURE),
        "distinct_sco_type_count": len(infra_types_in_workspace),
        "evidence_count": _slot_evidence_count(DossierSlotName.INFRASTRUCTURE),
    }

    # Slot 4: Timing
    props["x_ap_dossier_timing"] = {
        "status": _slot_status(DossierSlotName.TIMING),
        "evidence_count": _slot_evidence_count(DossierSlotName.TIMING),
    }

    # Slot 5: Targeting
    props["x_ap_dossier_targeting"] = {
        "status": _slot_status(DossierSlotName.TARGETING),
        "evidence_count": _slot_evidence_count(DossierSlotName.TARGETING),
    }

    # Slot 9: Denial
    props["x_ap_dossier_denial"] = {
        "status": _slot_status(DossierSlotName.DENIAL),
        "evidence_count": _slot_evidence_count(DossierSlotName.DENIAL),
    }

    return props


def _serialize_prediction(pred: object) -> dict:
    """Serialize one PersistedPrediction to the x_ap_predictions envelope dict.

    Mirrors the PersistedPrediction shape one-to-one (DEC-M9-STIX-MAPPING-002)
    so import is lossless. Works with the M-4/M-5 PersistedPrediction dataclass.

    Parameters
    ----------
    pred:
        PersistedPrediction instance.

    Returns
    -------
    dict
        JSON-serializable dict matching the §3.3 PredictionEnvelope schema.
    """
    ee = pred.expected_evidence
    fe = pred.falsification_evidence
    fe_dict: dict | None = None
    if fe is not None:
        fe_dict = {
            "contradiction_keyword_any": fe.contradiction_keyword_any,
            "negative_asn_in": fe.negative_asn_in,
            "negative_sco_type": fe.negative_sco_type,
            "negative_value_regex": fe.negative_value_regex,
            "stale_after_n_hunts": fe.stale_after_n_hunts,
        }
    return {
        "created_at": pred.created_at,
        "created_at_hunt_count": getattr(pred, "created_at_hunt_count", 0),
        "expected_evidence": {
            "asn_in": ee.asn_in,
            "note_keyword_any": ee.note_keyword_any,
            "sco_type": ee.sco_type,
            "value_regex": ee.value_regex,
        },
        "falsification_evidence": fe_dict,
        "prediction_id": pred.prediction_id,
        "slot": pred.slot,
        "status": pred.status,
        "text": pred.text,
        "validated_at": pred.validated_at,
        "validated_by_sco_id": pred.validated_by_sco_id,
    }


def _synthesize_threat_actor_sdo(
    actor_identifier: str,
    dossier_state: object,  # DossierState
    predictions: list,  # list[PersistedPrediction]
    analyst_notes: list[str],
    workspace_id: str,
    scos: list[dict],
) -> dict:
    """Build the threat-actor SDO dict carrying all M-9 dossier metadata.

    This SDO is in-process only — it is NEVER round-tripped through
    store_stix_objects (DEC-M9-NO-WORKSPACE-EDIT-001 / F59 sole authority).

    The assembled dict is later parsed through stix2.parse(..., allow_custom=True)
    to guarantee spec compliance and deterministic id derivation.

    Parameters
    ----------
    actor_identifier:
        Validated actor identifier string.
    dossier_state:
        DossierState from load_dossier_state or default_deferred_state.
    predictions:
        PersistedPrediction list from load_predictions_log.
    analyst_notes:
        Raw content strings from _get_analyst_notes_for_export.
    workspace_id:
        Active workspace name string from workspace_mgr.active.
    scos:
        All SCO dicts from workspace_mgr.get_stix_objects().

    Returns
    -------
    dict
        Partially-assembled threat-actor SDO dict with all x_ap_* custom props.
    """
    import adversary_pursuit as _ap_pkg
    from adversary_pursuit.dossier.slots import DossierSlotName

    slots = dossier_state.slots

    def _slot_status(name: "DossierSlotName") -> str:
        return slots[name].status.value if name in slots else "deferred"

    # Slot 1: Identity -> threat-actor.aliases
    aliases = _identity_to_aliases(scos)

    # Slot 6: Capability -> threat-actor.resource_level
    resource_level = _capability_to_resource_level(_slot_status(DossierSlotName.CAPABILITY))

    # Slot 7: Motivation -> threat-actor.roles
    roles = _motivation_to_roles(_slot_status(DossierSlotName.MOTIVATION))

    # x_ap_dossier_* custom props for slots 2/3/4/5/9
    custom_slot_props = _build_slot_custom_props(dossier_state, scos)

    # x_ap_predictions: list of PredictionEnvelope (§3.3)
    x_ap_predictions = [_serialize_prediction(p) for p in predictions]

    # x_ap_analyst_notes: list of {content: str}
    x_ap_analyst_notes = [{"content": note} for note in analyst_notes]

    # Bundle metadata (DEC-M9-STIX-MAPPING-001: on the threat-actor SDO)
    ap_version = getattr(_ap_pkg, "__version__", "unknown")
    exported_at = datetime.now(timezone.utc).isoformat()

    sdo: dict = {
        "type": "threat-actor",
        "spec_version": "2.1",
        "name": actor_identifier,
        "threat_actor_types": ["unknown"],
        # Slot 1: identity aliases
        **({"aliases": aliases} if aliases else {}),
        # Slot 7: motivation roles
        **({"roles": roles} if roles is not None else {}),
        # Slot 6: capability resource_level
        **({"resource_level": resource_level} if resource_level is not None else {}),
        # Slot 8: predictions log
        "x_ap_predictions": x_ap_predictions,
        # Analyst notes
        "x_ap_analyst_notes": x_ap_analyst_notes,
        # Per-slot custom props (slots 2/3/4/5/9)
        **custom_slot_props,
        # Bundle metadata
        "x_ap_version": ap_version,
        "x_ap_exported_at": exported_at,
        "x_ap_workspace_id": workspace_id,
        "x_ap_dossier_schema_version": _DOSSIER_BUNDLE_SCHEMA_VERSION,
        "x_ap_actor_identifier": actor_identifier,
        # Slot 1 status (for round-trip reconstruction)
        "x_ap_dossier_identity_status": _slot_status(DossierSlotName.IDENTITY),
    }
    return sdo


# ---------------------------------------------------------------------------
# Public API — export_dossier
# ---------------------------------------------------------------------------


def export_dossier(
    workspace_mgr: "WorkspaceManager",
    actor_identifier: str | None = None,
) -> str:
    """Serialize the active workspace's dossier to a STIX 2.1 bundle JSON string.

    This is the SOLE authority for ``dossier_bundle_exporter`` (DEC-M9-STIX-MAPPING-001).
    Read-only consumer of M-4 state. Never calls store_stix_objects or any workspace
    mutator. ``core/workspace.py`` remains BYTEWISE UNCHANGED.

    Bundle composition:
      - All SCOs from workspace_mgr.get_stix_objects() (F59 provenance preserved).
      - All SROs from RelationshipGraph (existing core/graph.py path).
      - A synthesized threat-actor SDO with DossierState metadata + predictions +
        analyst notes in x_ap_* custom properties.

    The returned string is parseable by ``stix2.parse(bundle_json, allow_custom=True)``.

    Parameters
    ----------
    workspace_mgr:
        Active WorkspaceManager instance. Must have an active workspace.
    actor_identifier:
        Actor identifier string. Defaults to ``workspace_mgr.active`` when None.
        Must match ``^[A-Za-z0-9._-]{1,128}$`` (DEC-M9-ACTOR-ID-001).

    Returns
    -------
    str
        STIX 2.1 bundle JSON string. Keys sorted alphabetically; compact form.

    Raises
    ------
    ValueError
        When actor_identifier is invalid (DEC-M9-ACTOR-ID-001).
    RuntimeError
        When workspace_mgr has no active workspace.
    """
    import stix2

    from adversary_pursuit.core.graph import RelationshipGraph
    from adversary_pursuit.dossier.predictions import load_predictions_log
    from adversary_pursuit.dossier.state import default_deferred_state, load_dossier_state

    # Resolve and validate actor_identifier
    if actor_identifier is None:
        actor_identifier = workspace_mgr.active
    _validate_actor_identifier(actor_identifier)

    workspace_id = workspace_mgr.active

    # Step 1: collect SCOs + build base bundle via RelationshipGraph (F59 path)
    scos = workspace_mgr.get_stix_objects()
    graph = RelationshipGraph()
    graph.build_from_workspace(scos)
    base_bundle_dict = graph.export_stix_bundle()

    # Step 2: load M-4 dossier state (read-only)
    local_state = load_dossier_state(workspace_mgr) or default_deferred_state()

    # Step 3: load M-4 predictions log (read-only)
    predictions = load_predictions_log(workspace_mgr)

    # Step 4: load M-5 analyst notes (read-only, mirrors tools.py pattern)
    analyst_notes = _get_analyst_notes_for_export(workspace_mgr)

    # Step 5: synthesize threat-actor SDO with all dossier metadata
    ta_dict = _synthesize_threat_actor_sdo(
        actor_identifier=actor_identifier,
        dossier_state=local_state,
        predictions=predictions,
        analyst_notes=analyst_notes,
        workspace_id=workspace_id,
        scos=scos,
    )

    # Step 6: parse threat-actor SDO through stix2 for spec compliance + id derivation
    ta_obj = stix2.parse(ta_dict, allow_custom=True)

    # Step 7: reconstruct bundle with existing SCO/SRO objects + the new threat-actor
    existing_objects: list = []
    for obj_dict in base_bundle_dict.get("objects", []):
        try:
            parsed = stix2.parse(obj_dict, allow_custom=True)
            existing_objects.append(parsed)
        except Exception:  # noqa: BLE001
            _LOG.warning(
                "export_dossier: could not re-parse SCO/SRO; skipping: %s", obj_dict.get("id")
            )

    all_objects = existing_objects + [ta_obj]
    bundle = stix2.v21.Bundle(objects=all_objects, allow_custom=True)
    bundle_dict = json.loads(bundle.serialize())
    bundle_dict.setdefault("objects", [])

    return json.dumps(bundle_dict, sort_keys=True)


# ---------------------------------------------------------------------------
# Public API — library helpers (DEC-M9-LIBRARY-LOCATION-001)
# ---------------------------------------------------------------------------


def publish_to_library(
    bundle_json: str,
    actor_identifier: str,
) -> Path:
    """Write a STIX bundle JSON string to the local dossier library.

    Requires ``AP_DOSSIER_PUBLISH=on`` (DEC-M9-LIBRARY-OPTIN-001). Creates the
    library directory with 0o700 permissions on first use. Overwrites any existing
    file for the same actor_identifier (idempotent).

    Privacy note (DEC-M9-PRIVACY-001): the bundle contains raw IOCs verbatim.
    Publishing means the IOCs are written to disk at library_root(). The user
    is responsible for controlling access to that directory.

    Parameters
    ----------
    bundle_json:
        STIX bundle JSON string (e.g. from export_dossier).
    actor_identifier:
        Validated actor identifier used as the filename stem.

    Returns
    -------
    Path
        Absolute path to the written library file.

    Raises
    ------
    RuntimeError
        When AP_DOSSIER_PUBLISH is not 'on' (DEC-M9-LIBRARY-OPTIN-001).
    ValueError
        When actor_identifier is invalid.
    """
    if not library_publish_enabled():
        raise RuntimeError(
            "Publishing to the dossier library requires AP_DOSSIER_PUBLISH=on. "
            "Set this environment variable to enable publishing. "
            "Warning: publishing a dossier bundle writes raw IOCs to disk. "
            "See DEC-M9-LIBRARY-OPTIN-001 and DEC-M9-PRIVACY-001."
        )
    _validate_actor_identifier(actor_identifier)

    root = library_root()
    # Create directory with 0o700 permissions; chmod explicitly for pre-existing dirs
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)

    dest = root / f"{actor_identifier}.json"
    dest.write_text(bundle_json, encoding="utf-8")
    _LOG.debug("publish_to_library: wrote %d bytes to %s", len(bundle_json), dest)
    return dest


def list_library() -> list[Path]:
    """List all dossier bundle files in the local library.

    Returns an empty list when the library directory does not exist or is empty.
    Reads are unconditional — no AP_DOSSIER_PUBLISH gate (DEC-M9-LIBRARY-OPTIN-001).

    Returns
    -------
    list[Path]
        Sorted list of absolute Paths to ``*.json`` files in library_root().
    """
    root = library_root()
    if not root.exists():
        return []
    return sorted(root.glob("*.json"))


def load_from_library(actor_identifier: str) -> str:
    """Read and return the STIX bundle JSON string for actor_identifier from the library.

    Reads are unconditional — no AP_DOSSIER_PUBLISH gate (DEC-M9-LIBRARY-OPTIN-001).

    Parameters
    ----------
    actor_identifier:
        Actor identifier string. Must match the filesystem-safe pattern.

    Returns
    -------
    str
        Raw bundle JSON string from the library file.

    Raises
    ------
    ValueError
        When actor_identifier is invalid.
    FileNotFoundError
        When no library file exists for this actor_identifier.
    """
    _validate_actor_identifier(actor_identifier)
    root = library_root()
    path = root / f"{actor_identifier}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No dossier bundle found for actor '{actor_identifier}' in library at {root}. "
            f"Expected file: {path}"
        )
    return path.read_text(encoding="utf-8")
