"""Slot glyph rendering for the TUI dossier strip.

Maps SlotStatus enum values to single Unicode glyph characters and provides
a weight-tier classifier and a 9-glyph strip renderer for the live pane.

@decision DEC-SLOT-GLYPHS-001
@title glyph vocabulary: empty=·, partial=▪, filled=▮, deferred=∅
@status accepted
@rationale Four distinct Unicode glyphs give the analyst an immediate visual
           read of dossier completeness at a glance. The vocabulary is kept
           small and high-contrast so it reads clearly in both light and dark
           terminal themes. Glyph selection follows the progression from
           absence (·) through partial fill (▪) to full block (▮), with ∅
           as a visually distinct deferred marker.

@decision DEC-SLOT-FILL-AMPLITUDE-001
@title weight tiers → rendering primitives: high (≥4.0), mid (2.5–3.9), low (<2.5)
@status accepted
@rationale SLOT_WEIGHTS values cluster naturally into three bands.
           high-tier slots (Identity=5.0, Predictions=4.0) carry the most
           analytic signal and may receive emphasis treatment in future rendering.
           mid-tier (Capability=3.5, TTPs=3.0, Motivation=3.0, Targeting=2.5,
           Denial=2.5) are substantive but not keystones.
           low-tier (Infrastructure=2.0, Timing=2.0) are baseline-above-routine.
           The tier classification is the authority for any future conditional
           rendering (bold glyph, colour accent) — callers must not re-derive
           tiers from raw weight values.
"""

from __future__ import annotations

from adversary_pursuit.dossier.slots import SLOT_WEIGHTS, DossierSlotName, SlotStatus

# ---------------------------------------------------------------------------
# Glyph vocabulary (DEC-SLOT-GLYPHS-001)
# ---------------------------------------------------------------------------

_GLYPH: dict[SlotStatus, str] = {
    SlotStatus.EMPTY: "·",
    SlotStatus.PARTIAL: "▪",
    SlotStatus.FILLED: "▮",
    SlotStatus.DEFERRED: "∅",
}

# ---------------------------------------------------------------------------
# Canonical slot order for the 9-glyph strip
# (matches DossierSlotName declaration order in slots.py)
# ---------------------------------------------------------------------------

SLOT_ORDER: list[DossierSlotName] = [
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
# Weight tier thresholds (DEC-SLOT-FILL-AMPLITUDE-001)
# ---------------------------------------------------------------------------

_HIGH_THRESHOLD: float = 4.0  # weight >= 4.0 → high
_MID_THRESHOLD: float = 2.5  # 2.5 <= weight < 4.0 → mid
# weight < 2.5 → low  (currently none, but future-safe)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def slot_to_glyph(slot_status: SlotStatus) -> str:
    """Return the single-character glyph for the given SlotStatus.

    Parameters
    ----------
    slot_status:
        The fill status of a dossier slot.

    Returns
    -------
    str
        One of: "·" (empty), "▪" (partial), "▮" (filled), "∅" (deferred).

    Raises
    ------
    KeyError
        If slot_status is not a recognised SlotStatus member (loud failure
        per Sacred Practice 5).
    """
    return _GLYPH[slot_status]


def weight_tier(slot_name: DossierSlotName) -> str:
    """Return the weight tier for a slot: 'high', 'mid', or 'low'.

    Tier boundaries (DEC-SLOT-FILL-AMPLITUDE-001):
    - high: SLOT_WEIGHTS[slot_name] >= 4.0  (Identity=5.0, Predictions=4.0)
    - mid:  2.5 <= weight < 4.0             (Capability, TTPs, Motivation, Targeting, Denial)
    - low:  weight < 2.5                    (Infrastructure=2.0, Timing=2.0)

    Parameters
    ----------
    slot_name:
        A DossierSlotName enum member.

    Returns
    -------
    str
        'high', 'mid', or 'low'.
    """
    w = SLOT_WEIGHTS[slot_name]
    if w >= _HIGH_THRESHOLD:
        return "high"
    if w >= _MID_THRESHOLD:
        return "mid"
    return "low"


def render_slot_strip(dossier_state) -> str:
    """Render the 9-glyph dossier strip as a space-separated string.

    Example output: ``"▮ · ▪ · · · · · ·"``

    Slots are rendered in SLOT_ORDER. When *dossier_state* is None, all
    slots render as the empty glyph ("·").

    Parameters
    ----------
    dossier_state:
        A DossierState instance (from slot_inference.py) or None.
        Accessed via ``dossier_state.slots[slot_name].status``.

    Returns
    -------
    str
        Nine glyph characters separated by single spaces.
    """
    if dossier_state is None:
        return " ".join(_GLYPH[SlotStatus.EMPTY] for _ in SLOT_ORDER)

    glyphs: list[str] = []
    for slot_name in SLOT_ORDER:
        slot_state = dossier_state.slots.get(slot_name)
        if slot_state is None:
            glyphs.append(_GLYPH[SlotStatus.EMPTY])
        else:
            glyphs.append(_GLYPH[slot_state.status])
    return " ".join(glyphs)
