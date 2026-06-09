"""Dossier-style investigation report renderer.

Produces the M-8 actor-dossier Markdown report from the persisted DossierState,
AnalystNote rows, PersistedPrediction log, workspace STIX summary, and module
run history. This is the sole report renderer (classic shim removed at M-8 per
DEC-68-DOSSIER-REFRAME-008 / DEC-M8-CLEANUP-003).

@decision DEC-M7-REPORT-002
@title New core/dossier_report.py module owns the dossier-style report renderer
@status accepted
@rationale Separation of concerns: core/report.py owned the v1 interview-driven
           report; core/dossier_report.py owns the dossier-puzzle report. The two
           reports were not variants of one template — they were different shapes.
           Co-locating them would force every reader to mentally branch on style.
           Mirrors M-6's core/dossier_pivot.py vs core/pivot_policy.py separation.
           M-8's cleanup removes core/report.py outright, leaving this file standing
           on its own — clean removal trail. (DEC-M7-REPORT-002, option a — accepted.)

Public API:
  - generate_dossier_report(workspace_mgr, *, scoring_engine=None) -> str
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adversary_pursuit.core.workspace import WorkspaceManager
    from adversary_pursuit.gamification.scoring import ScoringEngine

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_dossier_report(
    workspace_mgr: "WorkspaceManager",
    *,
    scoring_engine: "ScoringEngine | None" = None,
) -> str:
    """Generate the M-7 actor-dossier investigation report as Markdown.

    Pure renderer: reads from the workspace but never writes. Sections:
      1. Header metadata (workspace name, date, total score)
      2. Dossier State (9-slot grid with status and evidence counts)
      3. Predictions (pending / validated / falsified log)
      4. Analyst Notes (authored via create_dossier_note / console notes)
      5. Indicators of Compromise (shared IOC table — same as v1)
      6. Investigation Timeline (module runs)
      7. Statistics

    Parameters
    ----------
    workspace_mgr:
        Active WorkspaceManager with a live ``_engine``.
    scoring_engine:
        Optional ScoringEngine for score context. Not used in v1 of the
        dossier report (score read directly from workspace). Reserved for
        future enrichment.

    Returns
    -------
    str
        Complete Markdown report string.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    try:
        workspace_name = workspace_mgr.active
    except RuntimeError:
        workspace_name = "(unknown)"

    total_score = workspace_mgr.get_total_score()
    stix_objects = workspace_mgr.get_stix_objects()
    module_runs = workspace_mgr.get_module_runs()
    type_counts = workspace_mgr.get_stix_type_counts()
    total_indicators = len(stix_objects)
    modules_used = len({r["module_name"] for r in module_runs})

    # Load dossier state (M-4 persistence authority)
    dossier_state = _load_dossier_state_safe(workspace_mgr)
    # Load predictions log (M-4 persistence authority)
    predictions = _load_predictions_safe(workspace_mgr)
    # Load analyst notes (M-5 AnalystNote table)
    notes = _load_analyst_notes_safe(workspace_mgr)

    lines: list[str] = []

    # --- Header ---
    lines.append("# Threat Actor Dossier Report")
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    lines.append(f"- **Workspace:** {workspace_name}")
    lines.append(f"- **Date:** {now}")
    lines.append(f"- **Total Score:** {total_score}")
    lines.append(f"- **Modules Used:** {modules_used}")
    lines.append(f"- **Total Indicators:** {total_indicators}")
    lines.append("")

    # --- Executive Summary ---
    lines.append("## Executive Summary")
    lines.append("")
    if total_indicators == 0:
        lines.append("No indicators collected. Investigation workspace is empty.")
    else:
        lines.append(
            f"This investigation collected **{total_indicators} indicator(s)** "
            f"across **{modules_used} module(s)**. "
            f"Total pursuit score: **{total_score} pts**."
        )
        if type_counts:
            breakdown = ", ".join(f"{t}: {c}" for t, c in sorted(type_counts.items()))
            lines.append(f"Indicator types: {breakdown}.")
    lines.append("")

    # --- Dossier State (9-slot grid) ---
    lines.append("## Dossier State")
    lines.append("")
    lines.append(_render_dossier_slots_section(dossier_state))
    lines.append("")

    # --- Predictions ---
    lines.append("## Predictions")
    lines.append("")
    lines.append(_render_predictions_section(predictions))
    lines.append("")

    # --- Analyst Notes ---
    lines.append("## Analyst Notes")
    lines.append("")
    lines.append(_render_analyst_notes_section(notes))
    lines.append("")

    # --- IOC table (same as v1 — content-shared) ---
    lines.append("## Indicators of Compromise")
    lines.append("")
    lines.append(_render_ioc_table(stix_objects))
    lines.append("")

    # --- Timeline ---
    lines.append("## Investigation Timeline")
    lines.append("")
    lines.append(_render_timeline(module_runs))
    lines.append("")

    # --- Statistics ---
    lines.append("## Statistics")
    lines.append("")
    lines.append(f"- Total indicators: {total_indicators}")
    if type_counts:
        lines.append("- By type:")
        for t, c in sorted(type_counts.items()):
            lines.append(f"  - {t}: {c}")
    else:
        lines.append("- By type: (none)")
    lines.append(f"- Total score: {total_score}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Private renderers — one per report section
# ---------------------------------------------------------------------------


def _render_dossier_slots_section(dossier_state: object | None) -> str:
    """Render the 9-slot dossier grid as Markdown.

    Parameters
    ----------
    dossier_state:
        DossierState from load_dossier_state(), or None for a fresh workspace.

    Returns
    -------
    str
        Markdown table rows or a placeholder when state is unavailable.
    """
    if dossier_state is None:
        return "_No dossier state recorded yet. Run a hunt to populate the dossier._"

    from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus

    # Slot display order: canonical 9-slot sequence
    SLOT_ORDER = [
        DossierSlotName.IDENTITY,
        DossierSlotName.TTPS,
        DossierSlotName.INFRASTRUCTURE,
        DossierSlotName.TIMING,
        DossierSlotName.TARGETING,
        DossierSlotName.CAPABILITY,
        DossierSlotName.MOTIVATION,
        DossierSlotName.PREDICTIONS,
        DossierSlotName.DENIAL,
    ]

    STATUS_ICONS = {
        SlotStatus.FILLED: "FILLED",
        SlotStatus.PARTIAL: "PARTIAL",
        SlotStatus.EMPTY: "EMPTY",
        SlotStatus.DEFERRED: "DEFERRED",
    }

    lines: list[str] = []
    lines.append("| Slot | Status | Evidence Count | Contributing Types |")
    lines.append("|------|--------|----------------|--------------------|")

    for slot_name in SLOT_ORDER:
        slot_state = dossier_state.slots.get(slot_name)  # type: ignore[union-attr]
        if slot_state is None:
            status_label = "EMPTY"
            evidence_count = 0
            contributing = ""
        else:
            status_label = STATUS_ICONS.get(slot_state.status, slot_state.status.value.upper())
            evidence_count = slot_state.evidence_count
            contributing = (
                ", ".join(sorted(slot_state.contributing_types))
                if slot_state.contributing_types
                else ""
            )

        display_name = slot_name.value.title()
        lines.append(f"| {display_name} | {status_label} | {evidence_count} | {contributing} |")

    return "\n".join(lines)


def _render_predictions_section(predictions: list) -> str:
    """Render the predictions log as Markdown.

    Parameters
    ----------
    predictions:
        List of PersistedPrediction objects from load_predictions_log().

    Returns
    -------
    str
        Markdown formatted predictions, grouped by status.
    """
    if not predictions:
        return "_No predictions authored yet. Use `create_dossier_prediction` to add predictions._"

    pending = [p for p in predictions if p.status == "pending"]
    validated = [p for p in predictions if p.status == "validated"]
    falsified = [p for p in predictions if p.status == "falsified"]

    lines: list[str] = []

    lines.append(
        f"**Summary:** {len(validated)} validated, "
        f"{len(pending)} pending, "
        f"{len(falsified)} falsified"
    )
    lines.append("")

    if validated:
        lines.append("### Validated Predictions")
        lines.append("")
        for p in validated:
            ts = f" _(validated {p.validated_at[:10] if p.validated_at else 'unknown'})_"
            lines.append(f"- **[{p.slot.title()}]** {p.text}{ts}")
        lines.append("")

    if pending:
        lines.append("### Pending Predictions")
        lines.append("")
        for p in pending:
            lines.append(f"- **[{p.slot.title()}]** {p.text}")
        lines.append("")

    if falsified:
        lines.append("### Falsified Predictions")
        lines.append("")
        for p in falsified:
            lines.append(f"- ~~**[{p.slot.title()}]** {p.text}~~")
        lines.append("")

    return "\n".join(lines).rstrip()


def _render_analyst_notes_section(notes: list[dict]) -> str:
    """Render analyst notes as Markdown.

    Parameters
    ----------
    notes:
        List of ``{"content": str, "created_at": str|None}`` dicts.

    Returns
    -------
    str
        Bullet list of notes or a placeholder when none exist.
    """
    if not notes:
        return "_No analyst notes authored yet. Use `create_dossier_note` to add notes._"

    lines: list[str] = []
    for note in notes:
        content = note.get("content", "")
        ts = note.get("created_at", "")
        ts_display = f"[{str(ts)[:16]}] " if ts else ""
        lines.append(f"- {ts_display}{content}")

    return "\n".join(lines)


def _render_ioc_table(stix_objects: list[dict]) -> str:
    """Generate Markdown IOC table from STIX objects.

    Shared with v1 — content-identical rendering.

    Parameters
    ----------
    stix_objects:
        List of STIX SCO dicts from workspace_mgr.get_stix_objects().

    Returns
    -------
    str
        Markdown table or a placeholder when no objects exist.
    """
    if not stix_objects:
        return "_No indicators collected._"

    rows: list[tuple[str, str, str]] = []
    for obj in stix_objects:
        obj_type = obj.get("type", "")
        value = str(obj.get("value", obj.get("id", "")))
        created = str(obj.get("created", ""))[:10] or "unknown"
        rows.append((obj_type, value, created))

    lines: list[str] = []
    lines.append("| Type | Value | First Seen |")
    lines.append("|------|-------|------------|")
    for obj_type, value, created in rows:
        safe_value = value.replace("|", "\\|")
        lines.append(f"| {obj_type} | {safe_value} | {created} |")

    return "\n".join(lines)


def _render_timeline(module_runs: list[dict]) -> str:
    """Generate chronological timeline from module runs.

    Parameters
    ----------
    module_runs:
        List of module run dicts from workspace_mgr.get_module_runs().

    Returns
    -------
    str
        Markdown bullet timeline or a placeholder when no runs exist.
    """
    if not module_runs:
        return "_No module runs recorded._"

    lines: list[str] = []
    for run in module_runs:
        ts = str(run.get("timestamp", ""))[:16]
        if "T" in ts:
            ts = ts.replace("T", " ")
        ts = ts or "unknown"
        module = run.get("module_name", "unknown")
        target = run.get("target", "unknown")
        count = run.get("result_count", 0)
        lines.append(f"- `{ts}` — **{module}** on `{target}` -> {count} object(s)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Safe data-load helpers — read-only consumers of M-4/M-5 authorities
# ---------------------------------------------------------------------------


def _load_dossier_state_safe(workspace_mgr: "WorkspaceManager") -> object | None:
    """Load dossier state safely; return None on any error.

    Read-only consumer of M-4 authority (DEC-M4-PERSIST-001). Never writes.

    Parameters
    ----------
    workspace_mgr:
        Active WorkspaceManager.

    Returns
    -------
    DossierState | None
        Loaded state, or None when not persisted yet or on error.
    """
    try:
        from adversary_pursuit.dossier.state import default_deferred_state, load_dossier_state

        state = load_dossier_state(workspace_mgr)
        return state if state is not None else default_deferred_state()
    except Exception:  # noqa: BLE001
        _LOG.debug("Could not load dossier state for report", exc_info=True)
        return None


def _load_predictions_safe(workspace_mgr: "WorkspaceManager") -> list:
    """Load predictions log safely; return empty list on any error.

    Read-only consumer of M-4 authority (DEC-M4-PRED-001). Never writes.

    Parameters
    ----------
    workspace_mgr:
        Active WorkspaceManager.

    Returns
    -------
    list[PersistedPrediction]
        Loaded predictions, or empty list on error.
    """
    try:
        from adversary_pursuit.dossier.predictions import load_predictions_log

        return load_predictions_log(workspace_mgr) or []
    except Exception:  # noqa: BLE001
        _LOG.debug("Could not load predictions for report", exc_info=True)
        return []


def _load_analyst_notes_safe(workspace_mgr: "WorkspaceManager") -> list[dict]:
    """Load analyst notes safely; return empty list on any error.

    Mirrors the pattern from core/report.py:_generate_analyst_notes() and
    agent/tools.py:_read_analyst_notes(). Never writes.

    Parameters
    ----------
    workspace_mgr:
        Active WorkspaceManager with a live ``_engine``.

    Returns
    -------
    list[dict]
        List of ``{"content": str, "created_at": str|None}`` dicts, or [].
    """
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from adversary_pursuit.models.database import AnalystNote

        engine = workspace_mgr._engine
        if engine is None:
            return []

        with Session(engine) as session:
            rows = session.scalars(select(AnalystNote).order_by(AnalystNote.id)).all()
            return [
                {
                    "content": r.content,
                    "created_at": str(r.created_at) if r.created_at else None,
                }
                for r in rows
            ]
    except Exception:  # noqa: BLE001
        _LOG.debug("Could not load analyst notes for report", exc_info=True)
        return []
