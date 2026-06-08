"""Dossier predictions lifecycle — sole authority for Predictions Log persistence and validation.

This module owns the question: "what is a Predictions Log entry's lifecycle and how do we
validate predictions against new evidence?" It is a pure-data module: no ScoreEvent emission
(that belongs to dossier/scoring.py), no workspace schema mutation (DEC-DB-002 preserved).

Storage authority: F63 sentinel-row pattern (DEC-M4-PERSIST-001). A single reserved action
row ``_predictions_log`` is maintained per workspace in the existing ``score_events`` table.
The JSON array of PersistedPrediction entries lives in the ``indicator`` column.

@decision DEC-M4-PRED-001
@title PersistedPrediction is the M-4 richer shape; M-2 PredictionRecord stays BYTEWISE UNCHANGED
@status accepted
@rationale DEC-M2-DOSSIER-004 ratified PredictionRecord as the long-lived scaffold contract.
    Keeping the richer M-4 shape here honors Sacred Practice 12 (the persistence-layer module
    owns the persistence-layer schema). The adapter _to_m2_record() preserves the M-3 helper
    signature so M-3's scaffold is the contract M-4 targets — not an aspirational shape.

@decision DEC-M4-PRED-002
@title expected_evidence vocabulary v1.0: sco_type, value_regex, asn_in, note_keyword_any
@status accepted
@rationale Smallest vocabulary covering the M-4 user story (actor pivot to .ru, ASN reuse,
    keyword in note) without becoming a query DSL. All non-None fields are ANDed.
    Empty expected_evidence rejected with loud ValueError (Sacred Practice 5).

@decision DEC-M4-PRED-003
@title Validation scope = current-hunt evidence only
@status accepted
@rationale Matches M-3's per-hunt diff pattern; avoids accidental re-validation against
    unchanged history. Cross-hunt re-validation is a separate M-5+ tool.

@decision DEC-M4-PRED-005
@title Active falsification implemented in M-5 (DEC-M5-FALSIFY-001..008)
@status superseded
@rationale M-4 deferred falsification. M-5 ships FalsificationEvidence, FalsificationResult,
    falsify_predictions(), mark_confirmed_or_falsified(), and manual_falsify() in this module.
    The M-4 deferral is honoured; this annotation records the resolution.

@decision DEC-M4-PRED-006
@title Confirmation = +N points; falsification = 0 points (no deduction)
@status accepted
@rationale Negative points events would require changes to streak/milestone math;
    M-7 narrative feedback is the right surface for "reckless guessing" feedback.

@decision DEC-M5-FALSIFY-001
@title Falsified-prediction state rides on the existing _predictions_log sentinel row
@status accepted
@rationale No new reserved action, no second authority, no schema migration.
    The existing _predictions_log JSON payload gains "falsified" status entries
    alongside "pending" and "validated". Sacred Practice 12 preserved.

@decision DEC-M5-FALSIFY-002
@title FalsificationEvidence vocabulary v1.0: mirrors ExpectedEvidence in the negative
@status accepted
@rationale Four contradiction-evidence fields plus one temporal rule. All non-None fields
    are ANDed; empty FalsificationEvidence is rejected (loud ValueError) EXCEPT when
    only stale_after_n_hunts is set — a pure temporal rule is a valid falsification criterion.

@decision DEC-M5-FALSIFY-003
@title stale_after_n_hunts uses module_run row count delta (current - created_at_hunt_count)
@status accepted
@rationale Counts rows from workspace_mgr.get_module_runs() at falsify-time minus the
    created_at_hunt_count captured at prediction creation. No historical SCO rescan.

@decision DEC-M5-FALSIFY-004
@title Falsification scope = current-hunt evidence only (same as M-4 validation)
@status accepted
@rationale Mirrors DEC-M4-PRED-003. stale_after_n_hunts is the only cross-hunt signal;
    it counts hunt-count delta rather than rescanning historical SCOs or notes.

@decision DEC-M5-FALSIFY-007
@title PersistedPrediction gains falsification_evidence + created_at_hunt_count fields
@status accepted
@rationale Both fields are appended at the end with defaults so v1 deserialization is
    backward-compatible (falsification_evidence=None, created_at_hunt_count=0).
    The schema_version bumps 1 -> 2 to signal the schema change (DEC-M5-FALSIFY-008).

@decision DEC-M5-FALSIFY-008
@title _predictions_log envelope schema_version bumps 1 -> 2; v1 still reads cleanly
@status accepted
@rationale v1 envelopes deserialize with falsification_evidence=None, created_at_hunt_count=0.
    Serializer always emits v2. v3+ raises RuntimeError (loud-failure pattern preserved from
    DEC-M4-PERSIST-003, bumped one version). This is the canonical handshake for M-5 migration.

Public API (M-4 + M-5):
  - ExpectedEvidence — typed match-pattern dataclass (M-4, FROZEN)
  - FalsificationEvidence — typed contradiction-pattern dataclass (M-5 NEW)
  - FalsificationResult — result of one falsification check (M-5 NEW)
  - PersistedPrediction — full lifecycle dataclass (extended in M-5)
  - ValidationResult — result of one prediction check
  - load_predictions_log(workspace_mgr) -> list[PersistedPrediction]
  - save_predictions_log(workspace_mgr, predictions) -> None
  - create_prediction(slot, text, expected_evidence_dict,
                      falsification_evidence_dict=None) -> PersistedPrediction
  - validate_predictions(predictions, new_scos, new_notes) -> list[ValidationResult]
  - falsify_predictions(predictions, new_scos, new_notes, hunt_count)
      -> list[FalsificationResult]  (M-5 NEW)
  - mark_confirmed_or_falsified(predictions, validation_results,
                                 falsification_results) -> list[PersistedPrediction]  (M-5 NEW)
  - mark_confirmed(predictions, results) -> list[PersistedPrediction]  (DEPRECATED M-5 wrapper)
  - manual_falsify(predictions, prediction_id, reason) -> list[PersistedPrediction]  (M-5 NEW)
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from adversary_pursuit.dossier.slots import DossierSlotName, PredictionRecord

if TYPE_CHECKING:
    from adversary_pursuit.core.workspace import WorkspaceManager

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reserved action constant (registered alongside workspace.py _RESERVED_ACTIONS)
# ---------------------------------------------------------------------------

PREDICTIONS_LOG_SENTINEL_ACTION: str = "_predictions_log"
"""Reserved score_events action for persistent Predictions Log JSON payload.

Part of the three-action _RESERVED_ACTIONS frozenset in workspace.py
(DEC-M4-PERSIST-002). The ``indicator`` column carries the JSON array.
``points=0`` so this row never affects get_total_score().
"""

# ---------------------------------------------------------------------------
# Schema versioning (DEC-M4-PERSIST-003)
# ---------------------------------------------------------------------------

_SCHEMA_VERSION: int = 2
"""Current serialization schema version for Predictions Log JSON envelopes.

M-5 bumps from 1 to 2 to signal the addition of falsification_evidence and
created_at_hunt_count fields to PersistedPrediction (DEC-M5-FALSIFY-008).
v1 envelopes still deserialize (falsification_evidence=None,
created_at_hunt_count=0). v3+ raises RuntimeError (DEC-M4-PERSIST-003 pattern
preserved, bumped one version).
"""

# ---------------------------------------------------------------------------
# Dataclasses — M-4 richer shapes (DEC-M4-PRED-001)
# ---------------------------------------------------------------------------


@dataclass
class FalsificationEvidence:
    """Typed contradiction pattern for prediction falsification (DEC-M5-FALSIFY-002).

    All non-None fields are ANDed together. Empty FalsificationEvidence (all fields
    None) is rejected by create_prediction with a loud ValueError UNLESS only
    stale_after_n_hunts is set — a pure temporal-window rule with no evidence
    criteria is a valid falsification criterion (sentinel exception per plan §2.4).

    Fields
    ------
    negative_sco_type:
        If set, the appearance of a SCO of this type counts as contradicting
        evidence (e.g. 'autonomous-system' with negative_asn_in: actor used a
        different ASN than predicted).
    negative_value_regex:
        If set, an SCO's primary value matching this regex falsifies the prediction
        (e.g. '.*\\.cn$' falsifies a 'pivot to .ru' prediction).
    negative_asn_in:
        For ipv4-addr / ipv6-addr / autonomous-system: appearance of an ASN in
        this list falsifies the prediction.
    contradiction_keyword_any:
        At least one of these substrings appearing in an analyst note falsifies
        the prediction (e.g. note 'actor pivoted to .cn' falsifies a .ru pivot).
    stale_after_n_hunts:
        If set, a still-pending prediction is auto-falsified once the workspace
        has completed N or more hunts since the prediction was created. None = no
        temporal rule. Counted as (current_hunt_count - created_at_hunt_count)
        against module_runs row count at falsify-time (DEC-M5-FALSIFY-003).
        This field MAY be the only non-None field (pure temporal-window rule).
    """

    negative_sco_type: str | None = None
    negative_value_regex: str | None = None
    negative_asn_in: list[int] | None = None
    contradiction_keyword_any: list[str] | None = None
    stale_after_n_hunts: int | None = None


@dataclass
class FalsificationResult:
    """Result of a single prediction falsification check (DEC-M5-FALSIFY-004).

    Fields
    ------
    prediction_id:
        The PersistedPrediction.prediction_id this result refers to.
    falsified:
        True if the prediction's falsification_evidence was satisfied by
        current-hunt evidence or the stale_after_n_hunts threshold was met.
    reason:
        Plain ASCII explanation of the falsification decision. Safe for
        rule_description and LLM-events sidecar (F64).
    """

    prediction_id: str
    falsified: bool
    reason: str


@dataclass
class ExpectedEvidence:
    """Typed match pattern for prediction validation (DEC-M4-PRED-002).

    M-4 vocabulary (minimum viable). M-5+ may extend.

    All non-None fields are ANDed together. Empty expected_evidence (all fields
    None) is rejected by create_prediction with a loud ValueError (Sacred Practice 5).

    Fields
    ------
    sco_type:
        STIX SCO type the evidence must be (e.g., 'domain-name', 'ipv4-addr').
        None = any SCO type matches.
    value_regex:
        Python regex applied via re.search() against the SCO's primary value field.
        None = no value filter.
    asn_in:
        For ipv4-addr / ipv6-addr / autonomous-system: ASN drawn from the SCO must
        be in this list. None = no ASN filter.
    note_keyword_any:
        At least one of these substrings must appear in an analyst note authored
        after the prediction was created. None = no note filter.
    """

    sco_type: str | None = None
    value_regex: str | None = None
    asn_in: list[int] | None = None
    note_keyword_any: list[str] | None = None


@dataclass
class PersistedPrediction:
    """Workspace-persisted Predictions Log entry (DEC-M4-PRED-001).

    Extends M-2's PredictionRecord shape (text + status) with the M-4 lifecycle
    metadata. This is the JSON-serialised shape in the _predictions_log sentinel row.

    Fields
    ------
    prediction_id:
        Stable workspace-unique id, e.g. ``"pred-3f19d55c"``.
    text:
        Free-text prediction statement.
    slot:
        One of DossierSlotName values; the slot this prediction targets.
    status:
        ``"pending"`` | ``"validated"`` | ``"falsified"``.
        M-4 only transitions to ``"validated"``; ``"falsified"`` is M-5 territory
        (DEC-M4-PRED-005). The field exists so M-5 can write it without schema change.
    expected_evidence:
        Typed match pattern used by validate_predictions().
    created_at:
        ISO-8601 UTC timestamp of prediction creation.
    validated_at:
        ISO-8601 UTC timestamp when status transitioned to ``"validated"``.
        None when status is still ``"pending"`` or ``"falsified"``.
    validated_by_sco_id:
        STIX object id of the confirming SCO. None when not yet validated.
    """

    prediction_id: str
    text: str
    slot: str
    status: str
    expected_evidence: ExpectedEvidence
    created_at: str
    validated_at: str | None = None
    validated_by_sco_id: str | None = None
    falsification_evidence: FalsificationEvidence | None = None
    """If set, M-5 falsification engine uses this to detect contradiction evidence.
    Default None means the prediction is never auto-falsified (only the
    stale_after_n_hunts field's presence enables temporal-window auto-falsify).
    M-5 NEW (DEC-M5-FALSIFY-007)."""
    created_at_hunt_count: int = 0
    """Module-run count at prediction creation time. Used by the stale_after_n_hunts
    temporal-window rule. Defaults to 0 for legacy M-4 entries so the falsifier
    treats them as 'unknown creation hunt count — skip stale check'
    (DEC-M5-FALSIFY-004). M-5 NEW."""


@dataclass
class ValidationResult:
    """Result of a single prediction validation check (DEC-M4-PRED-003).

    Fields
    ------
    prediction_id:
        The PersistedPrediction.prediction_id this result refers to.
    confirmed:
        True if the prediction's expected_evidence was satisfied by current-hunt
        evidence.
    matched_sco_id:
        STIX id of the confirming SCO; None if not confirmed.
    rationale:
        Plain ASCII explanation of the validation decision. Safe for
        rule_description and LLM-events sidecar (F64).
    """

    prediction_id: str
    confirmed: bool
    matched_sco_id: str | None
    rationale: str


# ---------------------------------------------------------------------------
# Serialization helpers (DEC-M4-PERSIST-003)
# ---------------------------------------------------------------------------


def _serialize_predictions(predictions: list[PersistedPrediction]) -> str:
    """Serialize a list of PersistedPrediction to a compact JSON string.

    Always emits schema_version=2 (DEC-M5-FALSIFY-008). Includes the new
    falsification_evidence and created_at_hunt_count fields added in M-5.
    Keys sorted alphabetically; compact form (no indent).

    Parameters
    ----------
    predictions:
        List of PersistedPrediction entries to serialize.

    Returns
    -------
    str
        Compact JSON string suitable for the ``indicator`` column.
    """
    entries = []
    for p in predictions:
        ee = p.expected_evidence
        fe = p.falsification_evidence
        fe_dict: dict | None = None
        if fe is not None:
            fe_dict = {
                "contradiction_keyword_any": fe.contradiction_keyword_any,
                "negative_asn_in": fe.negative_asn_in,
                "negative_sco_type": fe.negative_sco_type,
                "negative_value_regex": fe.negative_value_regex,
                "stale_after_n_hunts": fe.stale_after_n_hunts,
            }
        entries.append(
            {
                "created_at": p.created_at,
                "created_at_hunt_count": p.created_at_hunt_count,
                "expected_evidence": {
                    "asn_in": ee.asn_in,
                    "note_keyword_any": ee.note_keyword_any,
                    "sco_type": ee.sco_type,
                    "value_regex": ee.value_regex,
                },
                "falsification_evidence": fe_dict,
                "prediction_id": p.prediction_id,
                "slot": p.slot,
                "status": p.status,
                "text": p.text,
                "validated_at": p.validated_at,
                "validated_by_sco_id": p.validated_by_sco_id,
            }
        )

    envelope = {
        "predictions": entries,
        "schema_version": _SCHEMA_VERSION,
    }
    return json.dumps(envelope, sort_keys=True)


def _deserialize_predictions(payload: str) -> list[PersistedPrediction]:
    """Deserialize a JSON envelope back to a list of PersistedPrediction.

    Accepts both schema_version=1 (M-4 legacy) and schema_version=2 (M-5).
    v1 envelopes deserialize with falsification_evidence=None and
    created_at_hunt_count=0 (DEC-M5-FALSIFY-008 backward-compatibility).
    v3+ raises RuntimeError (loud-failure pattern from DEC-M4-PERSIST-003,
    bumped one version).

    Raises
    ------
    RuntimeError
        When schema_version is not 1 or 2 (DEC-M5-FALSIFY-008 loud failure).

    Parameters
    ----------
    payload:
        JSON string previously produced by ``_serialize_predictions``.

    Returns
    -------
    list[PersistedPrediction]
        Reconstructed list of prediction entries.
    """
    envelope = json.loads(payload)

    persisted_version = envelope.get("schema_version")
    # Accept v1 (M-4 legacy) and v2 (M-5 current). Reject everything else.
    if persisted_version not in (1, 2):
        raise RuntimeError(
            f"persisted predictions schema version {persisted_version!r} is not supported; "
            f"runtime supports versions 1 and 2 (current={_SCHEMA_VERSION}). "
            "Data may have been written by a newer AP version."
        )

    predictions: list[PersistedPrediction] = []
    for entry in envelope.get("predictions", []):
        ee_data = entry.get("expected_evidence", {})
        ee = ExpectedEvidence(
            sco_type=ee_data.get("sco_type"),
            value_regex=ee_data.get("value_regex"),
            asn_in=ee_data.get("asn_in"),
            note_keyword_any=ee_data.get("note_keyword_any"),
        )
        # M-5 fields — default for v1 entries (DEC-M5-FALSIFY-008)
        fe: FalsificationEvidence | None = None
        fe_data = entry.get("falsification_evidence")
        if fe_data is not None:
            fe = FalsificationEvidence(
                negative_sco_type=fe_data.get("negative_sco_type"),
                negative_value_regex=fe_data.get("negative_value_regex"),
                negative_asn_in=fe_data.get("negative_asn_in"),
                contradiction_keyword_any=fe_data.get("contradiction_keyword_any"),
                stale_after_n_hunts=fe_data.get("stale_after_n_hunts"),
            )
        predictions.append(
            PersistedPrediction(
                prediction_id=entry["prediction_id"],
                text=entry["text"],
                slot=entry["slot"],
                status=entry["status"],
                expected_evidence=ee,
                created_at=entry["created_at"],
                validated_at=entry.get("validated_at"),
                validated_by_sco_id=entry.get("validated_by_sco_id"),
                falsification_evidence=fe,
                created_at_hunt_count=entry.get("created_at_hunt_count", 0),
            )
        )
    return predictions


# ---------------------------------------------------------------------------
# Workspace persistence API (DEC-M4-PERSIST-001)
# ---------------------------------------------------------------------------


def load_predictions_log(workspace_mgr: "WorkspaceManager") -> list[PersistedPrediction]:
    """Load the persisted Predictions Log for the active workspace.

    Returns an empty list when no sentinel row exists yet (fresh workspace).
    Raises ``RuntimeError`` on schema version mismatch (DEC-M4-PERSIST-003).

    Parameters
    ----------
    workspace_mgr:
        Active WorkspaceManager instance.

    Returns
    -------
    list[PersistedPrediction]
        Deserialized list, or empty list for fresh workspaces.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from adversary_pursuit.models.database import ScoreEvent

    workspace_mgr._ensure_active()
    with Session(workspace_mgr._engine) as session:
        row = session.execute(
            select(ScoreEvent)
            .where(ScoreEvent.action == PREDICTIONS_LOG_SENTINEL_ACTION)
            .order_by(ScoreEvent.id.desc())
            .limit(1)
        ).scalar_one_or_none()

        if row is None or row.indicator is None:
            _LOG.debug("load_predictions_log: no persisted log found (fresh workspace)")
            return []

        try:
            predictions = _deserialize_predictions(row.indicator)
            _LOG.debug("load_predictions_log: loaded %d predictions", len(predictions))
            return predictions
        except (RuntimeError, json.JSONDecodeError) as exc:
            _LOG.warning("load_predictions_log: failed to deserialize: %s", exc)
            raise


def save_predictions_log(
    workspace_mgr: "WorkspaceManager",
    predictions: list[PersistedPrediction],
) -> None:
    """Persist the Predictions Log for the active workspace.

    Upserts a sentinel row in ``score_events``: deletes any existing
    ``_predictions_log`` rows, then inserts a fresh one with the JSON
    payload in the ``indicator`` column. Keeps exactly one sentinel row per
    workspace (idempotent F63 pattern, DEC-M4-PERSIST-001).

    Parameters
    ----------
    workspace_mgr:
        Active WorkspaceManager instance.
    predictions:
        Full current list of PersistedPrediction entries. Callers pass the
        complete list including any newly-confirmed entries (updated by caller).
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from adversary_pursuit.models.database import ScoreEvent

    payload = _serialize_predictions(predictions)

    workspace_mgr._ensure_active()
    with Session(workspace_mgr._engine) as session:
        existing = (
            session.execute(
                select(ScoreEvent).where(ScoreEvent.action == PREDICTIONS_LOG_SENTINEL_ACTION)
            )
            .scalars()
            .all()
        )
        for row in existing:
            session.delete(row)

        sentinel = ScoreEvent(
            action=PREDICTIONS_LOG_SENTINEL_ACTION,
            points=0,
            indicator=payload,
            module_run_id=None,
        )
        session.add(sentinel)
        session.commit()

    _LOG.debug(
        "save_predictions_log: persisted %d predictions (%d bytes)", len(predictions), len(payload)
    )


# ---------------------------------------------------------------------------
# Prediction factory (for LLM tool — DEC-M4-PRED-001/002)
# ---------------------------------------------------------------------------


def create_prediction(
    slot: str,
    text: str,
    expected_evidence_dict: dict,
    falsification_evidence_dict: dict | None = None,
) -> PersistedPrediction:
    """Create a new PersistedPrediction from LLM-tool arguments.

    Validates slot name, validates that expected_evidence is non-empty,
    and generates a stable workspace-unique prediction_id.

    The created_at_hunt_count field is intentionally NOT set here — the call
    site (_execute_create_dossier_prediction in agent/tools.py) captures it
    from workspace_mgr.get_module_runs() row count and passes it via the
    PersistedPrediction returned here having created_at_hunt_count=0. The
    caller updates it before persisting (DEC-M5-FALSIFY-007 option (a):
    keep create_prediction pure-function; workspace coupling stays in the
    call site).

    Parameters
    ----------
    slot:
        One of the 9 DossierSlotName values (e.g. ``"infrastructure"``).
        Raises ``ValueError`` for unknown slot names.
    text:
        Free-text prediction statement.
    expected_evidence_dict:
        Dict matching the ExpectedEvidence shape. Must have at least one
        non-None field (DEC-M4-PRED-002 loud rejection of empty evidence).
    falsification_evidence_dict:
        Optional dict matching FalsificationEvidence shape. When supplied,
        M-5 auto-falsifies the prediction if contradiction evidence matches.
        If all fields are None, raises ValueError (DEC-M5-FALSIFY-002) UNLESS
        only stale_after_n_hunts is set (sentinel exception).

    Returns
    -------
    PersistedPrediction
        New entry with ``status="pending"`` and a generated ``prediction_id``.

    Raises
    ------
    ValueError
        When ``slot`` is not a valid DossierSlotName value, when all fields in
        ``expected_evidence`` are None, or when ``falsification_evidence`` has
        all fields None without stale_after_n_hunts (DEC-M5-FALSIFY-002).
    """
    # Validate slot name (loud failure, Sacred Practice 5)
    try:
        DossierSlotName(slot)
    except ValueError:
        valid_slots = [s.value for s in DossierSlotName]
        raise ValueError(f"Invalid slot {slot!r}. Must be one of: {valid_slots}") from None

    # Validate text is non-empty
    if not text or not text.strip():
        raise ValueError("Prediction text must be non-empty.")

    ee = ExpectedEvidence(
        sco_type=expected_evidence_dict.get("sco_type"),
        value_regex=expected_evidence_dict.get("value_regex"),
        asn_in=expected_evidence_dict.get("asn_in"),
        note_keyword_any=expected_evidence_dict.get("note_keyword_any"),
    )

    # Loud rejection of empty expected_evidence (DEC-M4-PRED-002)
    if (
        ee.sco_type is None
        and ee.value_regex is None
        and ee.asn_in is None
        and ee.note_keyword_any is None
    ):
        raise ValueError(
            "expected_evidence must have at least one non-None field "
            "(sco_type, value_regex, asn_in, or note_keyword_any). "
            "A prediction with no match criteria can never be validated."
        )

    # M-5: build FalsificationEvidence if provided (DEC-M5-FALSIFY-002)
    fe: FalsificationEvidence | None = None
    if falsification_evidence_dict is not None:
        fe = FalsificationEvidence(
            negative_sco_type=falsification_evidence_dict.get("negative_sco_type"),
            negative_value_regex=falsification_evidence_dict.get("negative_value_regex"),
            negative_asn_in=falsification_evidence_dict.get("negative_asn_in"),
            contradiction_keyword_any=falsification_evidence_dict.get("contradiction_keyword_any"),
            stale_after_n_hunts=falsification_evidence_dict.get("stale_after_n_hunts"),
        )
        # Loud rejection of empty falsification_evidence (DEC-M5-FALSIFY-002)
        # Exception: stale_after_n_hunts alone is valid (sentinel exception)
        all_evidence_none = (
            fe.negative_sco_type is None
            and fe.negative_value_regex is None
            and fe.negative_asn_in is None
            and fe.contradiction_keyword_any is None
            and fe.stale_after_n_hunts is None
        )
        if all_evidence_none:
            raise ValueError(
                "falsification_evidence must have at least one non-None field "
                "(negative_sco_type, negative_value_regex, negative_asn_in, "
                "contradiction_keyword_any, or stale_after_n_hunts)."
            )

    # Generate stable workspace-unique prediction_id
    prediction_id = f"pred-{secrets.token_hex(4)}"
    created_at = datetime.now(tz=timezone.utc).isoformat()

    return PersistedPrediction(
        prediction_id=prediction_id,
        text=text.strip(),
        slot=slot,
        status="pending",
        expected_evidence=ee,
        created_at=created_at,
        falsification_evidence=fe,
    )


# ---------------------------------------------------------------------------
# Validation engine (DEC-M4-PRED-002 / DEC-M4-PRED-003)
# ---------------------------------------------------------------------------


def _get_sco_primary_value(sco: dict) -> str | None:
    """Extract the primary string value from a STIX SCO dict.

    Handles the common STIX SCO types used in AP:
    - ipv4-addr, ipv6-addr: ``value``
    - domain-name: ``value``
    - url: ``value``
    - email-addr: ``value``
    - file: ``name`` (primary identifier for file objects)
    - user-account: ``user_id``
    - x509-certificate: ``subject`` (or ``serial_number`` fallback)
    - autonomous-system: ``name`` (or ``number`` as string fallback)

    Falls back to the ``value`` field for unknown types.
    Returns None if no suitable field is found.
    """
    sco_type = sco.get("type", "")
    if sco_type == "file":
        return sco.get("name")
    if sco_type == "user-account":
        return sco.get("user_id")
    if sco_type == "x509-certificate":
        return sco.get("subject") or sco.get("serial_number")
    if sco_type == "autonomous-system":
        name = sco.get("name")
        if name:
            return name
        number = sco.get("number")
        return str(number) if number is not None else None
    # Default: most types (ipv4-addr, domain-name, url, email-addr, ipv6-addr) use ``value``
    return sco.get("value")


def _extract_asn_from_sco(sco: dict) -> int | None:
    """Extract an ASN integer from a STIX SCO dict.

    Handles:
    - autonomous-system: ``number`` field directly
    - ipv4-addr / ipv6-addr: ``x_autonomous_system.asn`` extension field
      (AP-standard provenance extension from VirusTotal / Shodan modules)

    Returns None when no ASN can be extracted.
    """
    sco_type = sco.get("type", "")
    if sco_type == "autonomous-system":
        number = sco.get("number")
        if number is not None:
            try:
                return int(number)
            except (TypeError, ValueError):
                return None
    if sco_type in ("ipv4-addr", "ipv6-addr"):
        asn_ext = sco.get("x_autonomous_system") or sco.get("x_ap_asn")
        if isinstance(asn_ext, dict):
            asn = asn_ext.get("asn") or asn_ext.get("number")
            if asn is not None:
                try:
                    return int(asn)
                except (TypeError, ValueError):
                    return None
    return None


def _matches_expected_evidence(
    sco: dict,
    ee: ExpectedEvidence,
) -> tuple[bool, str]:
    """Check whether a single SCO satisfies an ExpectedEvidence pattern.

    All non-None fields are ANDed (DEC-M4-PRED-002). Returns a tuple of
    (matches: bool, rationale: str).

    Note: ``note_keyword_any`` is NOT checked here — notes are checked separately
    in ``validate_predictions`` because note matching doesn't depend on individual SCOs.
    """
    # sco_type filter
    if ee.sco_type is not None:
        if sco.get("type") != ee.sco_type:
            return False, f"sco_type {sco.get('type')!r} != expected {ee.sco_type!r}"

    # value_regex filter
    if ee.value_regex is not None:
        primary_value = _get_sco_primary_value(sco)
        if primary_value is None:
            return False, "no primary value to match value_regex against"
        try:
            if not re.search(ee.value_regex, primary_value):
                return False, f"value {primary_value!r} does not match regex {ee.value_regex!r}"
        except re.error as exc:
            return False, f"invalid value_regex {ee.value_regex!r}: {exc}"

    # asn_in filter
    if ee.asn_in is not None:
        asn = _extract_asn_from_sco(sco)
        if asn is None:
            return False, "no ASN extractable from SCO"
        if asn not in ee.asn_in:
            return False, f"ASN {asn} not in expected list {ee.asn_in}"

    return True, "all SCO-level criteria satisfied"


def validate_predictions(
    predictions: list[PersistedPrediction],
    new_scos: list[dict],
    new_notes: list[dict],
) -> list[ValidationResult]:
    """Validate predictions against current-hunt evidence (DEC-M4-PRED-003).

    Iterates ``predictions`` in stable list order. For each ``pending`` prediction,
    applies every non-None ``expected_evidence`` field against ``new_scos`` (and
    ``new_notes`` for ``note_keyword_any``) until one entry matches all non-None
    fields, or all entries have been tried.

    Predictions already ``validated`` or ``falsified`` are skipped (idempotency).
    Scope = current-hunt evidence only (DEC-M4-PRED-003).

    The ``note_keyword_any`` field is checked by scanning all ``new_notes`` for any
    note whose ``content`` contains at least one of the specified keywords. When
    ``note_keyword_any`` is the ONLY non-None field, confirmation is by note-match
    alone (no SCO required). When it is combined with SCO-level fields, BOTH must
    be satisfied by the same hunt's evidence (note match is evaluated independently
    of which SCO matched).

    Parameters
    ----------
    predictions:
        Full predictions list. Only ``pending`` entries are evaluated.
    new_scos:
        SCOs discovered in the current hunt (post-hunt workspace minus pre-hunt).
        In production this is derived from workspace diff; in tests it is supplied
        directly.
    new_notes:
        Analyst notes authored in the current hunt context. List of
        ``{"content": <str>}`` dicts (same shape as _read_analyst_notes output).

    Returns
    -------
    list[ValidationResult]
        One ValidationResult per prediction, in the same order as ``predictions``.
        Skipped (non-pending) predictions have ``confirmed=False``,
        ``matched_sco_id=None``, rationale explains the skip.
    """
    results: list[ValidationResult] = []

    for pred in predictions:
        # Skip non-pending predictions (idempotency — DEC-M4-PRED-003)
        if pred.status != "pending":
            results.append(
                ValidationResult(
                    prediction_id=pred.prediction_id,
                    confirmed=False,
                    matched_sco_id=None,
                    rationale=f"skipped: prediction already {pred.status}",
                )
            )
            continue

        ee = pred.expected_evidence

        # Determine if this is a note-only prediction (no SCO-level criteria)
        has_sco_criteria = (
            ee.sco_type is not None or ee.value_regex is not None or ee.asn_in is not None
        )
        has_note_criteria = ee.note_keyword_any is not None

        if not has_sco_criteria and has_note_criteria:
            # Note-only validation: check all notes for keyword match
            note_matched = _check_note_keywords(new_notes, ee.note_keyword_any)  # type: ignore[arg-type]
            if note_matched:
                results.append(
                    ValidationResult(
                        prediction_id=pred.prediction_id,
                        confirmed=True,
                        matched_sco_id=None,
                        rationale=f"note keyword match: one of {ee.note_keyword_any!r} found in analyst notes",
                    )
                )
            else:
                results.append(
                    ValidationResult(
                        prediction_id=pred.prediction_id,
                        confirmed=False,
                        matched_sco_id=None,
                        rationale=f"no analyst note contained any of {ee.note_keyword_any!r}",
                    )
                )
            continue

        if not has_sco_criteria and not has_note_criteria:
            # Should not happen (create_prediction rejects empty ee) but defensive guard
            results.append(
                ValidationResult(
                    prediction_id=pred.prediction_id,
                    confirmed=False,
                    matched_sco_id=None,
                    rationale="no match criteria defined (all ExpectedEvidence fields are None)",
                )
            )
            continue

        # SCO-level validation (with optional note requirement)
        confirmed = False
        matched_sco_id: str | None = None
        last_rationale = "no matching SCO found in current-hunt evidence"

        for sco in new_scos:
            sco_ok, sco_rationale = _matches_expected_evidence(sco, ee)
            if not sco_ok:
                last_rationale = sco_rationale
                continue

            # SCO criteria satisfied. If note_keyword_any also required, check it too.
            if has_note_criteria:
                note_ok = _check_note_keywords(new_notes, ee.note_keyword_any)  # type: ignore[arg-type]
                if not note_ok:
                    last_rationale = (
                        f"SCO matched but no analyst note contained any of {ee.note_keyword_any!r}"
                    )
                    continue

            # All criteria satisfied
            confirmed = True
            matched_sco_id = sco.get("id")
            last_rationale = f"confirmed by SCO {matched_sco_id!r}: {sco_rationale}"
            break

        results.append(
            ValidationResult(
                prediction_id=pred.prediction_id,
                confirmed=confirmed,
                matched_sco_id=matched_sco_id,
                rationale=last_rationale,
            )
        )

    return results


def _check_note_keywords(notes: list[dict], keywords: list[str]) -> bool:
    """Return True if any note's content contains at least one keyword from the list.

    Parameters
    ----------
    notes:
        List of ``{"content": <str>}`` dicts.
    keywords:
        List of substring strings. Substring matching (not regex).
    """
    for note in notes:
        content = note.get("content", "")
        for kw in keywords:
            if kw in content:
                return True
    return False


# ---------------------------------------------------------------------------
# Adapter — M-4 PersistedPrediction to M-2 PredictionRecord shape (DEC-M4-PRED-001)
# ---------------------------------------------------------------------------


def _to_m2_record(persisted: PersistedPrediction) -> PredictionRecord:
    """Convert a PersistedPrediction to the M-2 PredictionRecord scaffold shape.

    This adapter lets the M-3 scaffolded ``emit_dossier_prediction_validated_event``
    helper accept the M-2 shape without a signature change (DEC-M4-PRED-001).

    Parameters
    ----------
    persisted:
        The validated PersistedPrediction to convert.

    Returns
    -------
    PredictionRecord
        M-2 scaffold shape with text and status from the persisted entry.
    """
    return PredictionRecord(text=persisted.text, status=persisted.status)


# ---------------------------------------------------------------------------
# Confirmation status update helper
# ---------------------------------------------------------------------------


def mark_confirmed(
    predictions: list[PersistedPrediction],
    results: list[ValidationResult],
) -> list[PersistedPrediction]:
    """Return an updated predictions list with confirmed entries status-flipped to 'validated'.

    Produces a new list; does not mutate the input (dataclass discipline).
    Only predictions where the corresponding ValidationResult has ``confirmed=True``
    are updated; others are returned as-is.

    Parameters
    ----------
    predictions:
        Current predictions list (same order as ``results``).
    results:
        List of ValidationResult from ``validate_predictions``, parallel to ``predictions``.

    Returns
    -------
    list[PersistedPrediction]
        Updated predictions list suitable for ``save_predictions_log``.
    """
    updated: list[PersistedPrediction] = []
    now = datetime.now(tz=timezone.utc).isoformat()

    for pred, result in zip(predictions, results):
        if result.confirmed and pred.status == "pending":
            updated.append(
                PersistedPrediction(
                    prediction_id=pred.prediction_id,
                    text=pred.text,
                    slot=pred.slot,
                    status="validated",
                    expected_evidence=pred.expected_evidence,
                    created_at=pred.created_at,
                    validated_at=now,
                    validated_by_sco_id=result.matched_sco_id,
                    falsification_evidence=pred.falsification_evidence,
                    created_at_hunt_count=pred.created_at_hunt_count,
                )
            )
        else:
            updated.append(pred)

    return updated


# ---------------------------------------------------------------------------
# M-5: Falsification engine (DEC-M5-FALSIFY-001..004)
# ---------------------------------------------------------------------------


def _matches_falsification_evidence(
    sco: dict,
    fe: "FalsificationEvidence",
) -> tuple[bool, str]:
    """Check whether a single SCO satisfies a FalsificationEvidence pattern.

    All non-None SCO-level fields are ANDed (DEC-M5-FALSIFY-002). Returns a
    tuple of (matches: bool, rationale: str).

    Note: contradiction_keyword_any and stale_after_n_hunts are NOT checked
    here — notes are checked separately in falsify_predictions and the
    staleness counter is evaluated there too.
    """
    # negative_sco_type filter
    if fe.negative_sco_type is not None:
        if sco.get("type") != fe.negative_sco_type:
            return (
                False,
                f"sco_type {sco.get('type')!r} != negative_sco_type {fe.negative_sco_type!r}",
            )

    # negative_value_regex filter
    if fe.negative_value_regex is not None:
        primary_value = _get_sco_primary_value(sco)
        if primary_value is None:
            return False, "no primary value to match negative_value_regex against"
        try:
            if not re.search(fe.negative_value_regex, primary_value):
                return (
                    False,
                    f"value {primary_value!r} does not match negative_value_regex "
                    f"{fe.negative_value_regex!r}",
                )
        except re.error as exc:
            return False, f"invalid negative_value_regex {fe.negative_value_regex!r}: {exc}"

    # negative_asn_in filter
    if fe.negative_asn_in is not None:
        asn = _extract_asn_from_sco(sco)
        if asn is None:
            return False, "no ASN extractable from SCO for negative_asn_in check"
        if asn not in fe.negative_asn_in:
            return False, f"ASN {asn} not in negative_asn_in list {fe.negative_asn_in}"

    return True, "all SCO-level falsification criteria satisfied"


def falsify_predictions(
    predictions: list["PersistedPrediction"],
    new_scos: list[dict],
    new_notes: list[dict],
    hunt_count: int,
) -> list["FalsificationResult"]:
    """Check predictions for falsification against current-hunt evidence.

    For each ``pending`` prediction that has a ``falsification_evidence`` field,
    evaluates whether current-hunt evidence contradicts the prediction:
    - SCO-level contradiction (negative_sco_type, negative_value_regex, negative_asn_in)
    - Note-level contradiction (contradiction_keyword_any)
    - Temporal staleness (stale_after_n_hunts, evaluated against hunt_count delta)

    Scope = current-hunt evidence only for evidence fields (DEC-M5-FALSIFY-004).
    stale_after_n_hunts is the only cross-hunt signal.

    Predictions without falsification_evidence are returned with falsified=False.
    Already-validated or already-falsified predictions are skipped (idempotency).

    Parameters
    ----------
    predictions:
        Full predictions list. Only ``pending`` entries with non-None
        ``falsification_evidence`` are evaluated.
    new_scos:
        SCOs discovered in the current hunt (post-hunt workspace minus pre-hunt).
    new_notes:
        Analyst notes authored in the current hunt context. List of
        ``{"content": <str>}`` dicts.
    hunt_count:
        Current total module-run count from workspace_mgr.get_module_runs().
        Used to evaluate stale_after_n_hunts temporal rule.

    Returns
    -------
    list[FalsificationResult]
        One FalsificationResult per prediction, in the same order as
        ``predictions``. Non-pending predictions have falsified=False,
        reason explains the skip.
    """
    results: list[FalsificationResult] = []

    for pred in predictions:
        # Skip non-pending predictions (idempotency)
        if pred.status != "pending":
            results.append(
                FalsificationResult(
                    prediction_id=pred.prediction_id,
                    falsified=False,
                    reason=f"skipped: prediction already {pred.status}",
                )
            )
            continue

        fe = pred.falsification_evidence
        if fe is None:
            results.append(
                FalsificationResult(
                    prediction_id=pred.prediction_id,
                    falsified=False,
                    reason="no falsification_evidence defined; prediction cannot be auto-falsified",
                )
            )
            continue

        # -- Staleness check (cross-hunt, temporal counter) --
        if fe.stale_after_n_hunts is not None:
            creation_count = pred.created_at_hunt_count
            # Skip stale check when creation_count is 0 (legacy entry with unknown creation time)
            if creation_count > 0:
                hunts_elapsed = hunt_count - creation_count
                if hunts_elapsed >= fe.stale_after_n_hunts:
                    results.append(
                        FalsificationResult(
                            prediction_id=pred.prediction_id,
                            falsified=True,
                            reason=(
                                f"stale: {hunts_elapsed} hunts elapsed since creation "
                                f"(threshold={fe.stale_after_n_hunts})"
                            ),
                        )
                    )
                    continue

        # -- Evidence-based contradiction check --
        has_sco_criteria = (
            fe.negative_sco_type is not None
            or fe.negative_value_regex is not None
            or fe.negative_asn_in is not None
        )
        has_note_criteria = fe.contradiction_keyword_any is not None

        # SCO-level (with optional note AND)
        if has_sco_criteria:
            matched_sco_id: str | None = None
            match_rationale = ""
            for sco in new_scos:
                sco_ok, sco_rationale = _matches_falsification_evidence(sco, fe)
                if not sco_ok:
                    continue
                # SCO criteria satisfied — also check note criteria if ANDed
                if has_note_criteria:
                    note_ok = _check_note_keywords(
                        new_notes,
                        fe.contradiction_keyword_any,  # type: ignore[arg-type]
                    )
                    if not note_ok:
                        continue
                matched_sco_id = sco.get("id", "unknown")
                match_rationale = sco_rationale
                break

            if matched_sco_id is not None:
                results.append(
                    FalsificationResult(
                        prediction_id=pred.prediction_id,
                        falsified=True,
                        reason=(
                            f"contradiction evidence matched SCO {matched_sco_id!r}: "
                            f"{match_rationale}"
                        ),
                    )
                )
            else:
                results.append(
                    FalsificationResult(
                        prediction_id=pred.prediction_id,
                        falsified=False,
                        reason="no contradicting SCO found in current-hunt evidence",
                    )
                )
            continue

        # Note-only contradiction check (no SCO criteria)
        if has_note_criteria:
            note_ok = _check_note_keywords(
                new_notes,
                fe.contradiction_keyword_any,  # type: ignore[arg-type]
            )
            if note_ok:
                results.append(
                    FalsificationResult(
                        prediction_id=pred.prediction_id,
                        falsified=True,
                        reason=(
                            f"contradiction keyword match: one of "
                            f"{fe.contradiction_keyword_any!r} found in analyst notes"
                        ),
                    )
                )
            else:
                results.append(
                    FalsificationResult(
                        prediction_id=pred.prediction_id,
                        falsified=False,
                        reason=(
                            f"no analyst note contained any of {fe.contradiction_keyword_any!r}"
                        ),
                    )
                )
            continue

        # Only stale_after_n_hunts was set and threshold was NOT met (fell through stale check)
        results.append(
            FalsificationResult(
                prediction_id=pred.prediction_id,
                falsified=False,
                reason="stale_after_n_hunts threshold not yet met",
            )
        )

    return results


def mark_confirmed_or_falsified(
    predictions: list["PersistedPrediction"],
    validation_results: list["ValidationResult"],
    falsification_results: list["FalsificationResult"],
) -> list["PersistedPrediction"]:
    """Return an updated predictions list reflecting both validation and falsification.

    Supersedes mark_confirmed() for M-5 hunt sites. Produces a new list;
    does not mutate input (dataclass discipline).

    Priority: if a prediction is simultaneously confirmed and falsified in the
    same hunt (edge case only possible with manual_falsify), validation takes
    precedence (confirmed is the positive signal).

    Parameters
    ----------
    predictions:
        Current predictions list.
    validation_results:
        List of ValidationResult from validate_predictions(), parallel to predictions.
    falsification_results:
        List of FalsificationResult from falsify_predictions(), parallel to predictions.

    Returns
    -------
    list[PersistedPrediction]
        Updated predictions list suitable for save_predictions_log().
    """
    updated: list[PersistedPrediction] = []
    now = datetime.now(tz=timezone.utc).isoformat()

    for pred, vr, fr in zip(predictions, validation_results, falsification_results):
        if vr.confirmed and pred.status == "pending":
            updated.append(
                PersistedPrediction(
                    prediction_id=pred.prediction_id,
                    text=pred.text,
                    slot=pred.slot,
                    status="validated",
                    expected_evidence=pred.expected_evidence,
                    created_at=pred.created_at,
                    validated_at=now,
                    validated_by_sco_id=vr.matched_sco_id,
                    falsification_evidence=pred.falsification_evidence,
                    created_at_hunt_count=pred.created_at_hunt_count,
                )
            )
        elif fr.falsified and pred.status == "pending":
            updated.append(
                PersistedPrediction(
                    prediction_id=pred.prediction_id,
                    text=pred.text,
                    slot=pred.slot,
                    status="falsified",
                    expected_evidence=pred.expected_evidence,
                    created_at=pred.created_at,
                    validated_at=now,  # reused as conclusion timestamp
                    validated_by_sco_id=None,
                    falsification_evidence=pred.falsification_evidence,
                    created_at_hunt_count=pred.created_at_hunt_count,
                )
            )
        else:
            updated.append(pred)

    return updated


def manual_falsify(
    predictions: list["PersistedPrediction"],
    prediction_id: str,
    reason: str,
) -> tuple[list["PersistedPrediction"], bool]:
    """Mark a specific prediction as falsified by analyst judgment.

    Finds the prediction by prediction_id and transitions it from
    pending -> falsified. Idempotent: already-concluded predictions
    (validated or falsified) are returned unchanged with found=False.

    Parameters
    ----------
    predictions:
        Current predictions list.
    prediction_id:
        The PersistedPrediction.prediction_id to falsify.
    reason:
        Plain-text explanation stored in the conclusion timestamp comment.
        Not persisted in the dataclass (stored in the caller's score event).

    Returns
    -------
    tuple[list[PersistedPrediction], bool]
        Updated predictions list and a bool indicating whether the transition
        actually happened (True = transitioned to falsified; False = no-op
        because prediction was not found or was already concluded).
    """
    updated: list[PersistedPrediction] = []
    transitioned = False
    now = datetime.now(tz=timezone.utc).isoformat()

    for pred in predictions:
        if pred.prediction_id == prediction_id and pred.status == "pending":
            updated.append(
                PersistedPrediction(
                    prediction_id=pred.prediction_id,
                    text=pred.text,
                    slot=pred.slot,
                    status="falsified",
                    expected_evidence=pred.expected_evidence,
                    created_at=pred.created_at,
                    validated_at=now,
                    validated_by_sco_id=None,
                    falsification_evidence=pred.falsification_evidence,
                    created_at_hunt_count=pred.created_at_hunt_count,
                )
            )
            transitioned = True
        else:
            updated.append(pred)

    return updated, transitioned
