"""Dossier panel rendering — pure function returning a rich.panel.Panel.

The caller (agent/chat.py) is responsible for printing the returned panel
via its existing console.print() site. This module performs no I/O.

@decision DEC-M1-DOSSIER-003 (panel rendering authority)
@title render() is a pure function returning rich.panel.Panel; caller prints it
@status accepted
@rationale Mirrors the existing RelationshipGraph.render_tree() pattern used by
    the 'graph' and 'export gexf' meta-commands (chat.py lines 368-416). Pure-
    function rendering: DossierState in -> rich.panel.Panel out. No console.print()
    here; the chat.py caller owns the console singleton and the print site.
    F64 LLM/Panel separation honored: the panel is Rich-only, never enters the
    LLM prompt path. No new helper added to core/console.py (DEC-M1-DOSSIER-003).

@decision DEC-M1-PANEL-STYLE-001
@title Status emoji and color coding for slot rows
@status accepted
@rationale User-facing clarity: the 9-slot puzzle metaphor is clearest when each
    row uses a consistent visual language. Status symbols:
      filled   -> green checkmark [bold green]v[/]
      partial  -> yellow progress  [yellow]~[/]
      empty    -> dim dash         [dim]-[/]
      deferred -> dim clock/defer  [dim]...[/]  (milestone placeholder)
    Color coding is applied via Rich markup; strip_markup() would reduce to plain
    text for export if needed in future (no coupling to color in logic layer).
"""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table

from adversary_pursuit.dossier.slot_inference import DossierState
from adversary_pursuit.dossier.slots import SLOT_WEIGHTS, DossierSlotName, SlotStatus

# ---------------------------------------------------------------------------
# Display metadata — human-readable slot names and milestone notes
# ---------------------------------------------------------------------------

_SLOT_DISPLAY_NAME: dict[DossierSlotName, str] = {
    DossierSlotName.IDENTITY: "Identity / Attribution",
    DossierSlotName.TTPS: "TTPs & Tradecraft",
    DossierSlotName.INFRASTRUCTURE: "Infrastructure Habits",
    DossierSlotName.TIMING: "Timing / Behavioral",
    DossierSlotName.TARGETING: "Targeting Profile",
    DossierSlotName.CAPABILITY: "Capability Ceiling",
    DossierSlotName.MOTIVATION: "Motivation Indicators",
    DossierSlotName.PREDICTIONS: "Predictions Log",
    DossierSlotName.DENIAL: "Denial / Deception",
}

# Milestone label shown for deferred slots
_DEFERRED_MILESTONE: dict[DossierSlotName, str] = {
    DossierSlotName.TIMING: "M-2",
    DossierSlotName.TARGETING: "M-2",
    DossierSlotName.CAPABILITY: "M-2",
    DossierSlotName.MOTIVATION: "M-2",
    DossierSlotName.PREDICTIONS: "M-4",
    DossierSlotName.DENIAL: "M-5",
}

# Canonical slot order for display (matches roadmap §3 table, slot 1 → 9)
_SLOT_ORDER: list[DossierSlotName] = [
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


# ---------------------------------------------------------------------------
# Status rendering helpers (DEC-M1-PANEL-STYLE-001)
# ---------------------------------------------------------------------------


def _status_symbol(status: SlotStatus) -> str:
    """Return a Rich markup string for the slot's fill status indicator."""
    if status == SlotStatus.FILLED:
        return "[bold green]v[/bold green]"
    if status == SlotStatus.PARTIAL:
        return "[yellow]~[/yellow]"
    if status == SlotStatus.DEFERRED:
        return "[dim]...[/dim]"
    # EMPTY
    return "[dim]-[/dim]"


def _status_label(status: SlotStatus) -> str:
    """Return a Rich markup string for the human-readable status label."""
    if status == SlotStatus.FILLED:
        return "[bold green]filled[/bold green]"
    if status == SlotStatus.PARTIAL:
        return "[yellow]partial[/yellow]"
    if status == SlotStatus.DEFERRED:
        return "[dim]deferred[/dim]"
    return "[dim]empty[/dim]"


def _weight_label(slot: DossierSlotName) -> str:
    """Return weight as a formatted string (e.g. '5.0x')."""
    w = SLOT_WEIGHTS.get(slot, 1.0)
    return f"{w:.1f}x"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render(state: DossierState) -> Panel:
    """Render a DossierState as a Rich Panel.

    Pure function: DossierState in -> rich.panel.Panel out. No console.print(),
    no I/O, no LLM calls (DEC-M1-DOSSIER-003, F64).

    Parameters
    ----------
    state:
        DossierState produced by slot_inference.infer_dossier_state().

    Returns
    -------
    rich.panel.Panel
        A Rich Panel containing a 5-column table (symbol, slot name, status,
        evidence count, weight). The caller is responsible for printing it.
    """
    table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
    table.add_column("", width=2, no_wrap=True)
    table.add_column("Slot", style="bold", ratio=3)
    table.add_column("Status", ratio=2)
    table.add_column("Evidence", justify="right", width=10)
    table.add_column("Weight", justify="right", width=7)

    filled_count = 0
    partial_count = 0

    for slot_name in _SLOT_ORDER:
        slot_state = state.slots.get(slot_name)
        if slot_state is None:
            continue

        symbol = _status_symbol(slot_state.status)
        display_name = _SLOT_DISPLAY_NAME.get(slot_name, slot_name.value)
        status_text = _status_label(slot_state.status)
        weight_text = _weight_label(slot_name)

        if slot_state.status == SlotStatus.DEFERRED:
            milestone = _DEFERRED_MILESTONE.get(slot_name, "M-2")
            evidence_text = f"[dim]{milestone}[/dim]"
            display_name_markup = f"[dim]{display_name}[/dim]"
        else:
            evidence_count = slot_state.evidence_count
            evidence_text = (
                f"[green]{evidence_count}[/green]" if evidence_count > 0 else "[dim]0[/dim]"
            )
            display_name_markup = display_name
            if slot_state.status == SlotStatus.FILLED:
                filled_count += 1
            elif slot_state.status == SlotStatus.PARTIAL:
                partial_count += 1

        table.add_row(symbol, display_name_markup, status_text, evidence_text, weight_text)

    # Summary subtitle
    active_slots = 3  # Identity, TTPs, Infrastructure (M-1 inferred)
    total_scos = state.total_sco_count
    subtitle_parts = []
    if filled_count > 0:
        subtitle_parts.append(f"[green]{filled_count} filled[/green]")
    if partial_count > 0:
        subtitle_parts.append(f"[yellow]{partial_count} partial[/yellow]")
    empty_count = active_slots - filled_count - partial_count
    if empty_count > 0:
        subtitle_parts.append(f"[dim]{empty_count} empty[/dim]")
    subtitle_parts.append(f"[dim]{total_scos} SCOs[/dim]")
    subtitle = "  ".join(subtitle_parts) if subtitle_parts else "[dim]no SCOs[/dim]"

    return Panel(
        table,
        title="[bold cyan]Threat Actor Dossier[/bold cyan]",
        subtitle=subtitle,
        border_style="cyan",
    )
