"""Dossier comparison — sole authority for slot-by-slot dossier diffing.

This module is the SOLE authority for ``dossier_comparison``.

``compare_dossiers(local, remote)`` is a PURE FUNCTION:
  - No I/O.
  - No LLM calls.
  - No workspace mutation.
  - No ``dossier/state.py`` write.
  - No global state read beyond the ``SLOT_WEIGHTS`` constant.

The function returns a ``ComparisonReport`` dataclass that captures:
  - Slot-by-slot status deltas (``slot_diff``).
  - Weighted completion ratios (``completion_local``, ``completion_remote``).
  - Unique-slot-fill lists per side.
  - Validated-prediction ratios per side.
  - A plain-ASCII one-line summary (F64-compliant).

@decision DEC-M9-COMPLETION-001
@title Completion math: filled=1.0, partial=0.5, empty=0.0, deferred=0.0; weighted by SLOT_WEIGHTS
@status accepted
@rationale Strict 0/1 discards the partial-evidence signal already exposed by M-1's panel
    surface. Weighting by SLOT_WEIGHTS ties the comparison metric to the same authority
    M-3 already uses for slot-fill scoring (Sacred Practice 12). deferred=0 because
    deferred is a milestone-scoping marker, not a confidence claim.

@decision DEC-M9-PRED-RATIO-001
@title prediction_validation_ratio = validated / (validated + pending + falsified); 0.0 for empty
@status accepted
@rationale Mirrors F63 milestone catch-up math discipline (safe-default-zero).
    validated-over-all-known framing matches roadmap §7.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Slot-status -> completion factor mapping (DEC-M9-COMPLETION-001)
# ---------------------------------------------------------------------------

_STATUS_COMPLETION_FACTOR: dict[str, float] = {
    "filled": 1.0,
    "partial": 0.5,
    "empty": 0.0,
    "deferred": 0.0,
}
"""Per-status completion weight factors (DEC-M9-COMPLETION-001).

Applied to each slot's SLOT_WEIGHTS entry and averaged across all 9 slots.
'deferred' maps to 0.0 because it is a milestone-scoping marker, not
a confidence claim about real evidence.
"""


# ---------------------------------------------------------------------------
# ComparisonReport shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComparisonReport:
    """Slot-by-slot comparison of two ImportedDossier instances.

    Produced by ``compare_dossiers``; pure value object (no I/O).

    Fields
    ------
    actor_identifier:
        Actor identifier from the local dossier (used as the shared subject).
    slot_diff:
        Mapping from DossierSlotName -> (local_status, remote_status) tuples.
        All 9 slots are always present. When both sides are equal the tuple is
        (x, x); differences are slots where the tuple contains distinct values.
    completion_local:
        Weighted completion score for the local dossier in [0.0, 1.0].
        Computed per DEC-M9-COMPLETION-001.
    completion_remote:
        Weighted completion score for the remote dossier in [0.0, 1.0].
    unique_to_local:
        DossierSlotName list where local is filled/partial and remote is empty/deferred.
    unique_to_remote:
        DossierSlotName list where remote is filled/partial and local is empty/deferred.
    prediction_validation_ratio_local:
        validated / total predictions for the local side; 0.0 when total == 0.
    prediction_validation_ratio_remote:
        validated / total predictions for the remote side; 0.0 when total == 0.
    summary_line:
        Plain ASCII one-liner summarizing the comparison (F64-compliant).
    """

    actor_identifier: str
    slot_diff: dict  # dict[DossierSlotName, tuple[SlotStatus, SlotStatus]]
    completion_local: float
    completion_remote: float
    unique_to_local: list  # list[DossierSlotName]
    unique_to_remote: list  # list[DossierSlotName]
    prediction_validation_ratio_local: float
    prediction_validation_ratio_remote: float
    summary_line: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_completion(slot_states: dict, slot_weights: dict) -> float:
    """Compute weighted completion score from slot_states and SLOT_WEIGHTS.

    Per DEC-M9-COMPLETION-001:
      completion = sum(weight_i * factor_i for all slots) / sum(all weights)

    Parameters
    ----------
    slot_states:
        dict[DossierSlotName, SlotStatus] — imported or local slot states.
    slot_weights:
        SLOT_WEIGHTS dict from dossier/slots.py.

    Returns
    -------
    float
        Completion score in [0.0, 1.0]. Returns 0.0 when total weight is zero
        (defensive; SLOT_WEIGHTS always has 9 positive entries in practice).
    """
    total_weight = sum(slot_weights.values())
    if total_weight == 0.0:
        return 0.0

    weighted_sum = 0.0
    for slot_name, weight in slot_weights.items():
        status_obj = slot_states.get(slot_name)
        if status_obj is None:
            factor = 0.0
        else:
            # SlotStatus is a str Enum — .value gives the lowercase string key
            status_str = status_obj.value if hasattr(status_obj, "value") else str(status_obj)
            factor = _STATUS_COMPLETION_FACTOR.get(status_str, 0.0)
        weighted_sum += weight * factor

    return weighted_sum / total_weight


def _compute_prediction_ratio(predictions: list) -> float:
    """Compute the validated-prediction ratio for a predictions list.

    Per DEC-M9-PRED-RATIO-001:
      ratio = validated / (validated + pending + falsified)
      when denominator == 0: return 0.0

    Parameters
    ----------
    predictions:
        list[PersistedPrediction] from ImportedDossier.

    Returns
    -------
    float
        Ratio in [0.0, 1.0]. Returns 0.0 for an empty predictions list.
    """
    if not predictions:
        return 0.0
    validated = sum(1 for p in predictions if getattr(p, "status", "") == "validated")
    total = len(predictions)
    return validated / total if total > 0 else 0.0


def _is_substantive(status_obj: object) -> bool:
    """Return True when a slot status represents meaningful evidence (filled or partial)."""
    status_str = status_obj.value if hasattr(status_obj, "value") else str(status_obj)
    return status_str in ("filled", "partial")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compare_dossiers(local: object, remote: object) -> ComparisonReport:
    """Compare two ImportedDossier instances slot-by-slot.

    Pure function: no I/O, no LLM calls, no workspace mutation
    (DEC-M9-CONFLICT-001 / Sacred Practice 12).

    Parameters
    ----------
    local:
        ImportedDossier representing the analyst's own workspace dossier.
    remote:
        ImportedDossier representing a peer's dossier (from library or file).

    Returns
    -------
    ComparisonReport
        Slot-by-slot diff, completion ratios, prediction validation ratios,
        unique-slot-fill lists, and a plain-ASCII summary line.
    """
    from adversary_pursuit.dossier.slots import SLOT_WEIGHTS, DossierSlotName, SlotStatus

    local_slots: dict = local.slot_states
    remote_slots: dict = remote.slot_states

    # Build slot_diff: all 9 slots always present
    slot_diff: dict = {}
    unique_to_local: list = []
    unique_to_remote: list = []

    for slot_name in DossierSlotName:
        local_status = local_slots.get(slot_name, SlotStatus.DEFERRED)
        remote_status = remote_slots.get(slot_name, SlotStatus.DEFERRED)
        slot_diff[slot_name] = (local_status, remote_status)

        local_sub = _is_substantive(local_status)
        remote_sub = _is_substantive(remote_status)
        if local_sub and not remote_sub:
            unique_to_local.append(slot_name)
        elif remote_sub and not local_sub:
            unique_to_remote.append(slot_name)

    # Completion ratios (DEC-M9-COMPLETION-001)
    completion_local = _compute_completion(local_slots, SLOT_WEIGHTS)
    completion_remote = _compute_completion(remote_slots, SLOT_WEIGHTS)

    # Prediction validation ratios (DEC-M9-PRED-RATIO-001)
    pred_ratio_local = _compute_prediction_ratio(local.predictions)
    pred_ratio_remote = _compute_prediction_ratio(remote.predictions)

    # Plain-ASCII summary line (F64 — no Rich markup)
    local_pct = round(completion_local * 100, 1)
    remote_pct = round(completion_remote * 100, 1)
    n_diffs = sum(1 for loc, rem in slot_diff.values() if loc != rem)
    summary_line = (
        f"Actor: {local.actor_identifier} | "
        f"Local: {local_pct}% complete ({len(unique_to_local)} unique slots) | "
        f"Remote: {remote_pct}% complete ({len(unique_to_remote)} unique slots) | "
        f"Slots differing: {n_diffs}/9"
    )

    return ComparisonReport(
        actor_identifier=local.actor_identifier,
        slot_diff=slot_diff,
        completion_local=completion_local,
        completion_remote=completion_remote,
        unique_to_local=unique_to_local,
        unique_to_remote=unique_to_remote,
        prediction_validation_ratio_local=pred_ratio_local,
        prediction_validation_ratio_remote=pred_ratio_remote,
        summary_line=summary_line,
    )


def format_comparison_report(report: ComparisonReport) -> str:
    """Render a ComparisonReport as a plain-ASCII multi-line string.

    F64-compliant: no Rich markup, no score-event narration.
    Used by the LLM tool ``compare_dossier`` and the chat meta-command.

    Parameters
    ----------
    report:
        ComparisonReport from compare_dossiers.

    Returns
    -------
    str
        Human-readable plain-ASCII comparison output.
    """
    lines: list[str] = []
    lines.append(f"=== Dossier Comparison: {report.actor_identifier} ===")
    lines.append("")
    lines.append(
        f"Completion:  Local {round(report.completion_local * 100, 1)}%  |  "
        f"Remote {round(report.completion_remote * 100, 1)}%"
    )
    lines.append(
        f"Predictions: Local {round(report.prediction_validation_ratio_local * 100, 1)}% validated  |  "
        f"Remote {round(report.prediction_validation_ratio_remote * 100, 1)}% validated"
    )
    lines.append("")
    lines.append("Slot-by-slot diff:")
    lines.append(f"  {'Slot':<20}  {'Local':<12}  {'Remote':<12}  Status")
    lines.append(f"  {'-' * 20}  {'-' * 12}  {'-' * 12}  ------")

    for slot_name, (local_status, remote_status) in sorted(
        report.slot_diff.items(), key=lambda x: x[0].value
    ):
        local_str = local_status.value if hasattr(local_status, "value") else str(local_status)
        remote_str = remote_status.value if hasattr(remote_status, "value") else str(remote_status)
        diff_marker = "DIFFERS" if local_status != remote_status else "same"
        lines.append(f"  {slot_name.value:<20}  {local_str:<12}  {remote_str:<12}  {diff_marker}")

    lines.append("")
    if report.unique_to_local:
        slot_names = ", ".join(s.value for s in report.unique_to_local)
        lines.append(f"Unique to local:  {slot_names}")
    if report.unique_to_remote:
        slot_names = ", ".join(s.value for s in report.unique_to_remote)
        lines.append(f"Unique to remote: {slot_names}")
    if not report.unique_to_local and not report.unique_to_remote:
        lines.append("No unique slots (both sides have the same substantive coverage).")

    lines.append("")
    lines.append(report.summary_line)
    return "\n".join(lines)
