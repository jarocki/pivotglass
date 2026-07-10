"""Dossier persistent state — sole authority for DossierState persistence across hunts.

This module owns the question: "how do we persist a DossierState snapshot to the
workspace SQLite store and reload it on the next ap chat session?" It is a
pure-data module: no ScoreEvent emission, no validation logic, no LLM-tool surface.

Storage authority: F63 sentinel-row pattern (DEC-M4-PERSIST-001). A single reserved
action row ``_dossier_state_snapshot`` is maintained per workspace in the existing
``score_events`` table. The JSON payload lives in the ``indicator`` column; ``points=0``
so the sentinel never affects ``get_total_score()``.

@decision DEC-M4-PERSIST-001
@title Persistent DossierState storage authority is the F63 sentinel-row pattern
@status accepted
@rationale Zero schema change. Mirrors the landed F63 precedent (DEC-63-MILESTONE-CATCHUP-001,
    merge 8778af3). Persists in workspace SQLite so it survives ap chat restart and
    travels with workspace export. Rejected alternatives documented in per-slice plan §2.2.

@decision DEC-M4-PERSIST-002
@title core/workspace.py gains a _RESERVED_ACTIONS frozenset; get_recent_scores filter widened
@status accepted
@rationale DEC-M4-PERSIST-001 picked sentinel-row; that mechanically requires hiding new
    sentinel rows from get_recent_scores() the same way F63 hides _milestone_sentinel.
    Widening the existing filter from one action to three is the smallest honest change.

@decision DEC-M4-PERSIST-003
@title JSON envelope carries schema_version=1; mismatched versions raise loud RuntimeError
@status accepted
@rationale Future schema evolution needs an explicit handshake; loud failure tells the user
    "you upgraded AP and your workspace pre-dates the change" rather than silently reading
    garbage. Per-module serializers honor Sacred Practice 12.

Public API (M-4):
  - load_dossier_state(workspace_mgr) -> DossierState | None
  - save_dossier_state(workspace_mgr, state) -> None
  - default_deferred_state() -> DossierState
  - apply_predictions_overlay(state, predictions) -> DossierState
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from adversary_pursuit.dossier.slot_inference import DossierState, SlotState
from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus

if TYPE_CHECKING:
    from adversary_pursuit.core.workspace import WorkspaceManager
    from adversary_pursuit.dossier.predictions import PersistedPrediction

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional EventBus wiring for TUI slot-transition notifications (Slice 6)
# ---------------------------------------------------------------------------

# Optional module-level EventBus for TUI slot-transition notifications.
# Set via wire_slot_transition_bus(). None = no-op (Slice 5 behavior).
_SLOT_TRANSITION_BUS: object = None  # EventBus | None


def wire_slot_transition_bus(bus: object) -> None:
    """Wire an EventBus so save_dossier_state emits SlotTransition events.

    Call this once when the TUI is active. Pass None to unwire.
    The bus is stored as a module-level reference so save_dossier_state() can
    publish without requiring callers to thread the bus through every call site.

    Parameters
    ----------
    bus:
        An EventBus instance (from adversary_pursuit.agent.tui.events), or
        None to disable TUI notifications (restores Slice 5 behavior).
    """
    global _SLOT_TRANSITION_BUS
    _SLOT_TRANSITION_BUS = bus


def _emit_slot_transitions(
    old_state: "DossierState", new_state: "DossierState", bus: object
) -> None:
    """Emit SlotTransition events for each slot whose status changed.

    Compares ``old_state`` and ``new_state`` slot-by-slot and publishes one
    ``SlotTransition`` event per changed slot to ``bus``. Skips slots that are
    absent in either state (graceful handling of fresh workspaces).

    Parameters
    ----------
    old_state:
        DossierState before the save.
    new_state:
        DossierState after the save.
    bus:
        EventBus to publish to. Must have a ``publish(event)`` method.
    """
    from adversary_pursuit.agent.tui.events import SlotTransition

    for slot_name in DossierSlotName:
        old_slot = old_state.slots.get(slot_name)
        new_slot = new_state.slots.get(slot_name)
        old_status = old_slot.status if old_slot is not None else None
        new_status = new_slot.status if new_slot is not None else None
        if old_status != new_status and old_status is not None and new_status is not None:
            try:
                bus.publish(  # type: ignore[attr-defined]
                    SlotTransition(
                        slot_name=slot_name.value,
                        old_status=old_status.value,
                        new_status=new_status.value,
                    )
                )
            except Exception:  # noqa: BLE001
                # TUI notification must never crash the persistence path.
                _LOG.debug(
                    "_emit_slot_transitions: failed to publish SlotTransition for slot %s",
                    slot_name.value,
                )


# ---------------------------------------------------------------------------
# Reserved action constant (registered alongside workspace.py _RESERVED_ACTIONS)
# ---------------------------------------------------------------------------

DOSSIER_STATE_SENTINEL_ACTION: str = "_dossier_state_snapshot"
"""Reserved score_events action for persistent DossierState JSON payload.

Part of the three-action _RESERVED_ACTIONS frozenset in workspace.py
(DEC-M4-PERSIST-002). The ``indicator`` column carries the JSON envelope.
``points=0`` so this row never affects get_total_score().
"""

# ---------------------------------------------------------------------------
# Schema versioning (DEC-M4-PERSIST-003)
# ---------------------------------------------------------------------------

_SCHEMA_VERSION: int = 1
"""Current serialization schema version for DossierState JSON envelopes.

Increment this when adding or removing fields from the JSON contract.
A mismatch between _SCHEMA_VERSION and the persisted schema_version raises
a loud RuntimeError — no silent fallback (Sacred Practice 5).
"""


# ---------------------------------------------------------------------------
# Serialization helpers (DEC-M4-PERSIST-003)
# ---------------------------------------------------------------------------


def _serialize_dossier_state(state: DossierState) -> str:
    """Serialize a DossierState to a compact JSON string.

    Produces a stable, deterministic JSON envelope with ``schema_version`` at the
    top level. Keys sorted alphabetically; compact form (no indent) to minimize
    column size. Enum values serialized as their ``.value`` (lowercase strings).
    frozenset contributing_types serialized as sorted lists.

    Parameters
    ----------
    state:
        The DossierState frozen dataclass to serialize.

    Returns
    -------
    str
        Compact, UTF-8 JSON string suitable for storage in the ``indicator`` column.
    """
    slots_dict: dict[str, dict] = {}
    for slot_name, slot_state in state.slots.items():
        slots_dict[slot_name.value] = {
            "contributing_types": sorted(slot_state.contributing_types),
            "evidence_count": slot_state.evidence_count,
            "name": slot_state.name.value,
            "status": slot_state.status.value,
        }

    envelope = {
        "schema_version": _SCHEMA_VERSION,
        "slots": slots_dict,
        "total_sco_count": state.total_sco_count,
    }
    return json.dumps(envelope, sort_keys=True)


def _deserialize_dossier_state(payload: str) -> DossierState:
    """Deserialize a JSON envelope back to a DossierState.

    Raises
    ------
    RuntimeError
        When ``schema_version`` does not match ``_SCHEMA_VERSION``
        (DEC-M4-PERSIST-003 loud failure on version mismatch).
    ValueError
        When the JSON contains an unknown slot key or an invalid SlotStatus value
        (Sacred Practice 5 — loud failure, not silent skip).

    Parameters
    ----------
    payload:
        JSON string previously produced by ``_serialize_dossier_state``.

    Returns
    -------
    DossierState
        Reconstructed frozen dataclass with status enums and slot-name enums
        promoted from string values.
    """
    envelope = json.loads(payload)

    persisted_version = envelope.get("schema_version")
    if persisted_version != _SCHEMA_VERSION:
        raise RuntimeError(
            f"persisted dossier schema version {persisted_version} is newer/older than "
            f"runtime schema version {_SCHEMA_VERSION}; "
            "data was written by a different AP version"
        )

    slots: dict[DossierSlotName, SlotState] = {}
    for slot_key, slot_data in envelope.get("slots", {}).items():
        # Loud failure on unknown slot key (Sacred Practice 5)
        try:
            slot_name = DossierSlotName(slot_key)
        except ValueError:
            raise ValueError(
                f"persisted dossier state contains unknown slot key: {slot_key!r}. "
                "This workspace may have been written by a newer AP version."
            ) from None

        # Loud failure on unknown status value (Sacred Practice 5)
        try:
            status = SlotStatus(slot_data["status"])
        except ValueError:
            raise ValueError(
                f"persisted dossier state contains unknown SlotStatus value: "
                f"{slot_data['status']!r} for slot {slot_key!r}"
            ) from None

        slots[slot_name] = SlotState(
            name=slot_name,
            status=status,
            evidence_count=slot_data.get("evidence_count", 0),
            contributing_types=frozenset(slot_data.get("contributing_types", [])),
        )

    return DossierState(slots=slots, total_sco_count=envelope.get("total_sco_count", 0))


# ---------------------------------------------------------------------------
# Workspace persistence API (DEC-M4-PERSIST-001)
# ---------------------------------------------------------------------------


def load_dossier_state(workspace_mgr: "WorkspaceManager") -> DossierState | None:
    """Load the persisted DossierState snapshot for the active workspace.

    Returns ``None`` when no snapshot exists yet (fresh workspace — caller
    should use ``default_deferred_state()``). Raises ``RuntimeError`` on
    schema version mismatch (DEC-M4-PERSIST-003).

    Uses the F63 sentinel-row pattern: queries ``score_events`` for a row with
    ``action=DOSSIER_STATE_SENTINEL_ACTION`` and deserializes the ``indicator``
    column payload.

    Parameters
    ----------
    workspace_mgr:
        Active WorkspaceManager instance.

    Returns
    -------
    DossierState | None
        Deserialized state or None when no snapshot is present.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from adversary_pursuit.models.database import ScoreEvent

    workspace_mgr._ensure_active()
    with Session(workspace_mgr._engine) as session:
        row = session.execute(
            select(ScoreEvent)
            .where(ScoreEvent.action == DOSSIER_STATE_SENTINEL_ACTION)
            .order_by(ScoreEvent.id.desc())
            .limit(1)
        ).scalar_one_or_none()

        if row is None or row.indicator is None:
            _LOG.debug("load_dossier_state: no persisted snapshot found (fresh workspace)")
            return None

        try:
            state = _deserialize_dossier_state(row.indicator)
            _LOG.debug("load_dossier_state: loaded snapshot with %d SCOs", state.total_sco_count)
            return state
        except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
            _LOG.warning("load_dossier_state: failed to deserialize snapshot: %s", exc)
            raise


def save_dossier_state(
    workspace_mgr: "WorkspaceManager",
    state: DossierState,
    old_state: "DossierState | None" = None,
) -> None:
    """Persist the DossierState snapshot for the active workspace.

    Upserts a sentinel row in ``score_events``: deletes any existing
    ``_dossier_state_snapshot`` rows, then inserts a fresh one with the JSON
    payload in the ``indicator`` column. Keeps exactly one sentinel row per
    workspace (idempotent F63 pattern, DEC-M4-PERSIST-001).

    When ``old_state`` is provided and ``_SLOT_TRANSITION_BUS`` is wired, emits
    ``SlotTransition`` events for each slot whose status changed (Slice 6 TUI
    integration). The emission is best-effort: any error is logged at DEBUG
    and never raises (TUI notification must never crash the persistence path).

    Parameters
    ----------
    workspace_mgr:
        Active WorkspaceManager instance.
    state:
        The DossierState to persist. Must have all 9 slots present.
    old_state:
        Optional previous DossierState for slot-transition diff. When provided
        and ``_SLOT_TRANSITION_BUS`` is set, ``SlotTransition`` events are
        published for changed slots. Pass ``None`` (default) to suppress
        event emission (Slice 5 behavior — no bus, no diff).
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from adversary_pursuit.models.database import ScoreEvent

    payload = _serialize_dossier_state(state)

    workspace_mgr._ensure_active()
    with Session(workspace_mgr._engine) as session:
        existing = (
            session.execute(
                select(ScoreEvent).where(ScoreEvent.action == DOSSIER_STATE_SENTINEL_ACTION)
            )
            .scalars()
            .all()
        )
        for row in existing:
            session.delete(row)

        sentinel = ScoreEvent(
            action=DOSSIER_STATE_SENTINEL_ACTION,
            points=0,
            indicator=payload,
            module_run_id=None,
        )
        session.add(sentinel)
        session.commit()

    _LOG.debug("save_dossier_state: persisted snapshot (%d bytes)", len(payload))

    # Emit SlotTransition events if the TUI bus is wired and old_state was provided.
    # Best-effort: any error is swallowed so TUI notification never crashes the
    # persistence path (Sacred Practice 5 applies to the persistence layer, not the UI).
    if _SLOT_TRANSITION_BUS is not None and old_state is not None:
        try:
            _emit_slot_transitions(old_state, state, _SLOT_TRANSITION_BUS)
        except Exception:  # noqa: BLE001
            _LOG.debug("save_dossier_state: failed to emit slot transition events (suppressed)")


# ---------------------------------------------------------------------------
# Default state constructor
# ---------------------------------------------------------------------------


def default_deferred_state() -> DossierState:
    """Build a DossierState with all 9 slots in DEFERRED status.

    Used by callers when no persisted snapshot exists yet (fresh workspace).
    Provides a valid DossierState instance so the pre/post diff in
    emit_dossier_slot_filled_events sees a clean baseline.

    Returns
    -------
    DossierState
        All 9 slots DEFERRED, evidence_count=0, total_sco_count=0.
    """
    slots = {slot: SlotState(name=slot, status=SlotStatus.DEFERRED) for slot in DossierSlotName}
    return DossierState(slots=slots, total_sco_count=0)


# ---------------------------------------------------------------------------
# Predictions-slot status overlay (DEC-M4-PERSIST-001 / plan §4)
# ---------------------------------------------------------------------------


def apply_predictions_overlay(
    state: DossierState,
    predictions: list["PersistedPrediction"],
) -> DossierState:
    """Return a new DossierState with the Predictions slot status computed from the log.

    M-4 cannot modify slot_inference.py (forbidden list), so the Predictions
    slot status is computed here and overlaid onto the fresh inference result.

    Rules (plan §4):
      - 0 entries => EMPTY
      - >= 1 pending (and fewer than 2 validated) => PARTIAL
      - >= 2 validated => FILLED

    This function does not mutate the input ``state`` (frozen dataclass discipline).
    The Predictions slot in ``state`` is replaced; all other slots are preserved.

    Parameters
    ----------
    state:
        DossierState produced by ``infer_dossier_state_full`` (Predictions slot
        is DEFERRED in M-2/M-3 workspaces with no overlay).
    predictions:
        Current list of PersistedPrediction entries for the active workspace.

    Returns
    -------
    DossierState
        New DossierState with Predictions slot status set per the rules above.
        All other slot states are byte-identical to the input.
    """
    # Compute predictions-slot status from log content
    if not predictions:
        new_predictions_status = SlotStatus.EMPTY
        evidence_count = 0
    else:
        validated_count = sum(1 for p in predictions if p.status == "validated")
        if validated_count >= 2:
            new_predictions_status = SlotStatus.FILLED
        elif len(predictions) >= 1:
            new_predictions_status = SlotStatus.PARTIAL
        else:
            new_predictions_status = SlotStatus.EMPTY
        evidence_count = len(predictions)

    # Build new slots dict with the overlay applied to PREDICTIONS only
    new_slots: dict[DossierSlotName, SlotState] = {}
    for slot_name, slot_state in state.slots.items():
        if slot_name is DossierSlotName.PREDICTIONS:
            new_slots[slot_name] = SlotState(
                name=slot_name,
                status=new_predictions_status,
                evidence_count=evidence_count,
                contributing_types=frozenset({"predictions_log"} if predictions else set()),
            )
        else:
            new_slots[slot_name] = slot_state

    return DossierState(slots=new_slots, total_sco_count=state.total_sco_count)
