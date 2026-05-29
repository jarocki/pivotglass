"""Dossier slot schema v1.0 — vocabulary, weights, status enum, and M-2 scaffold types.

This module is the SOLE authority for the 9-slot vocabulary and per-slot
importance weights defined in the Phase 16 strategic scoping
(.claude/plans/dossier-reframe-v2-roadmap.md §3).

@decision DEC-M1-DOSSIER-002
@title 9-slot vocabulary unchanged; status enum widened to {empty, partial, filled, deferred}
@status accepted
@rationale DEC-68-DOSSIER-REFRAME-010 grants M-1 a ±2-slot refinement window.
    This module exercises that window conservatively: the 9-slot vocabulary is
    unchanged from Phase 16 §3. The presentational status enum adds 'deferred'
    to signal that a slot exists in the v2 vocabulary but its inference path
    lands in a later milestone (M-2 / M-4 / M-5). 'deferred' is NOT a schema
    mutation — it is a read-side status value that is reversible at the per-slot
    level when M-2 lands. Further vocabulary changes require a planner re-stage
    and a successor DEC-ID.

@decision DEC-M1-SLOTS-WEIGHT-AUTHORITY-001
@title SLOT_WEIGHTS is the single source of truth for per-slot importance weights
@status accepted
@rationale Sacred Practice 12. The Phase 16 §3 table defines weights
    (Identity=5.0, Predictions=4.0, Capability=3.5, TTPs=3.0, Motivation=3.0,
    Targeting=2.5, Denial=2.5, Infrastructure=2.0, Timing=2.0). Any change to
    weights requires M-3 Evaluation Contract and a successor DEC-ID; they must
    not be adjusted in M-1. The SLOT_WEIGHTS dict lives here and is the only
    place weights are defined — callers import from this module.

@decision DEC-M2-DOSSIER-004
@title PredictionRecord / DenialStrategyRecord are typed scaffold dataclasses; always DEFERRED in M-2
@status accepted
@rationale M-2 ships typed shapes for slot 8 (Predictions Log) and slot 9
    (Denial/Deception Strategies). The actual inference for these slots is deferred
    to M-4 (persistent prediction records) and M-5 (user-note surface). Having typed
    dataclasses here (a) gives callers a concrete import surface now, (b) prevents
    future implementers from inventing incompatible shapes, and (c) is testable
    without any new persistence. Both dataclasses use field(default_factory=list)
    for list fields to avoid mutable default argument problems (PEP 557).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DossierSlotName(str, Enum):
    """The 9 canonical dossier slot names (Phase 16 §3, DEC-68-DOSSIER-REFRAME-010).

    Values are lowercase strings suitable for display and JSON serialisation.
    Each member corresponds to one row in the roadmap §3 table.
    """

    IDENTITY = "identity"
    """Slot 1: Identity / Attribution — who is this actor?"""

    TTPS = "ttps"
    """Slot 2: TTPs and Tradecraft — preferred CVEs, loaders, C2 frameworks."""

    INFRASTRUCTURE = "infrastructure"
    """Slot 3: Infrastructure Habits — hosting preferences, registrar, TLS cert reuse."""

    TIMING = "timing"
    """Slot 4: Timing / Behavioral — working hours, weekday cadence. (deferred M-1)"""

    TARGETING = "targeting"
    """Slot 5: Targeting Profile — industries, geographies, victim selection. (deferred M-1)"""

    CAPABILITY = "capability"
    """Slot 6: Capability Ceiling — sophistication ceiling, tool gaps. (deferred M-1)"""

    MOTIVATION = "motivation"
    """Slot 7: Motivation Indicators — financial / hacktivist / nation-state. (deferred M-1)"""

    PREDICTIONS = "predictions"
    """Slot 8: Predictions Log — past AP-generated predictions. (deferred M-1; M-4 persistence)"""

    DENIAL = "denial"
    """Slot 9: Denial / Deception Strategies — countermeasures. (deferred M-1; M-5 user notes)"""


class SlotStatus(str, Enum):
    """Presentational fill status for a dossier slot (DEC-M1-DOSSIER-002).

    The four values are:
      empty    — no SCO evidence for this slot in the current workspace.
      partial  — some evidence present (one distinct SCO type contributing).
      filled   — multiple distinct evidence types present; slot is substantively filled.
      deferred — slot is part of the v2 vocabulary but its inference path lands in
                 a later milestone (M-2/M-4/M-5). Renders as a placeholder so the
                 user sees the full 9-slot puzzle shape.

    'deferred' is NOT a confidence level — it is a milestone-scoping marker.
    Slots 4–9 are deferred in M-1; they transition to real statuses as later
    milestones supply inference paths.
    """

    EMPTY = "empty"
    PARTIAL = "partial"
    FILLED = "filled"
    DEFERRED = "deferred"


# ---------------------------------------------------------------------------
# Per-slot importance weights (Phase 16 §3, DEC-M1-SLOTS-WEIGHT-AUTHORITY-001)
# ---------------------------------------------------------------------------
# Routine per-IOC lookup with no slot impact = 1.0 (v1 baseline, DEC-68-DOSSIER-REFRAME-002).
# These weights drive M-3 scoring; they are READ ONLY in M-1 (no ScoreEvents emitted).

SLOT_WEIGHTS: dict[DossierSlotName, float] = {
    DossierSlotName.IDENTITY: 5.0,  # highest — Identity is the puzzle keystone
    DossierSlotName.PREDICTIONS: 4.0,  # deep analytic signal
    DossierSlotName.CAPABILITY: 3.5,  # rare and predictive
    DossierSlotName.TTPS: 3.0,  # analytic-value backbone
    DossierSlotName.MOTIVATION: 3.0,  # analytic-value backbone
    DossierSlotName.TARGETING: 2.5,  # downstream-derivable
    DossierSlotName.DENIAL: 2.5,  # downstream-derivable
    DossierSlotName.INFRASTRUCTURE: 2.0,  # baseline-above-routine
    DossierSlotName.TIMING: 2.0,  # baseline-above-routine
}


# ---------------------------------------------------------------------------
# Evidence type mapping (DEC-M1-DOSSIER-001 forbidden shortcut guard)
# ---------------------------------------------------------------------------
# Explicit mapping from STIX SCO type string to the slot(s) it contributes to.
# NO auto-discovery from the python-stix2 library — new types must be added here
# deliberately (single-authority discipline). Unknown types fall through silently.
#
# M-1 covers Identity / TTPs / Infrastructure.
# Slots 4–9 have no entry here; they are deferred and inferred as DEFERRED status.

SLOT_EVIDENCE_TYPES: dict[str, list[DossierSlotName]] = {
    # Identity (slot 1) — persona fingerprints, attribution artifacts
    "email-addr": [DossierSlotName.IDENTITY],
    "user-account": [DossierSlotName.IDENTITY],
    "x509-certificate": [DossierSlotName.IDENTITY],
    # TTPs (slot 2) — payload / C2 / tradecraft artifacts
    "url": [DossierSlotName.TTPS],
    "file": [DossierSlotName.TTPS],
    # Infrastructure (slot 3) — hosting, registrar, network patterns
    "domain-name": [DossierSlotName.INFRASTRUCTURE],
    "ipv4-addr": [DossierSlotName.INFRASTRUCTURE],
    "ipv6-addr": [DossierSlotName.INFRASTRUCTURE],
    "autonomous-system": [DossierSlotName.INFRASTRUCTURE],
}

# Slots with active M-1 inference (all others are deferred)
M1_ACTIVE_SLOTS: frozenset[DossierSlotName] = frozenset(
    {DossierSlotName.IDENTITY, DossierSlotName.TTPS, DossierSlotName.INFRASTRUCTURE}
)


# ---------------------------------------------------------------------------
# M-2 scaffold dataclasses — DEC-M2-DOSSIER-004
# ---------------------------------------------------------------------------
# These types give callers a typed import surface for slots 8 and 9 now, before
# the M-4/M-5 persistence and user-note surfaces land. The actual inference for
# both slots returns DEFERRED in M-2; these dataclasses are the shape contract
# that M-4 and M-5 implementers must honour.


@dataclass
class PredictionRecord:
    """Typed scaffold for a single Predictions Log entry (slot 8, DEC-M2-DOSSIER-004).

    M-4 will persist these to the ``dossier_prediction`` SQLite table.
    In M-2 the inference always returns DEFERRED — this dataclass defines the
    shape so M-4 implementers have a stable contract.

    Parameters
    ----------
    text:
        The prediction text as authored by the AP agent or the analyst.
    status:
        Lifecycle status: 'pending' (default), 'validated', or 'falsified'.
        DEC-68-DOSSIER-REFRAME-007: falsified predictions contribute 0 to slot
        weight (not negative). Whether they should deduct score is deferred to M-3.
    """

    text: str
    status: str = "pending"


@dataclass
class DenialStrategyRecord:
    """Typed scaffold for a Denial / Deception Strategy entry (slot 9, DEC-M2-DOSSIER-004).

    M-5 will provide a user-note surface and an ``add_dossier_strategy`` LLM tool
    that creates and links these records. In M-2 the inference always returns
    DEFERRED — this dataclass defines the shape so M-5 implementers have a stable
    contract.

    Parameters
    ----------
    strategy:
        Free-text description of the countermeasure or deception tactic.
    linked_evidence:
        List of STIX object IDs this strategy is grounded in. Empty by default
        until the M-5 evidence-linkage surface is implemented.
    """

    strategy: str
    linked_evidence: list[str] = field(default_factory=list)
