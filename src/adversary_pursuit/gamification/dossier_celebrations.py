"""LLM-narrated celebration policy for high-weight dossier slot-fill events.

M-7 sub-slice 2: when a dossier slot-fill event has a slot weight >= 2.5
(Identity / Predictions / Capability / TTPs / Motivation / Targeting / Denial),
this module produces a short LLM-narrated celebration text rendered through the
existing Rich panel pipeline (``runner.last_celebrations`` sidecar -> chat.py
celebration-panel loop). F64 invariant preserved: narration rides the celebration
sidecar, NOT the LLM-facing summary.

Routine events (slot weight < 2.5: Infrastructure / Timing, plus all per-IOC
discovery events) keep the v1 ASCII-art CelebrationEngine.celebrate() path
byte-identical. ``dossier_prediction_falsified`` events are explicitly excluded
from narration eligibility (DEC-M7-CELEB-005); the Skeptic badge surface is the
recognition channel for those.

@decision DEC-M7-CELEB-001
@title AgentRunner.narrate helper owns the LLM call; dossier_celebrations calls it
@status accepted
@rationale Single source of truth for the LLM client lives in AgentRunner already.
           narrate() reuses active model, active persona system prompt, active API-key
           resolution, and the active litellm import. No parallel client introduced.
           (DEC-M7-CELEB-001, option a -- accepted.)

@decision DEC-M7-CELEB-002
@title High-weight narration threshold: slot weight >= 2.5
@status accepted
@rationale Captures Identity / Predictions / Capability / TTPs / Motivation /
           Targeting / Denial (7 of 9 slots). Routine: Infrastructure / Timing (2 of 9).
           Cut matches natural break in the weight distribution.

@decision DEC-M7-CELEB-003
@title Per-narration token cap: 80 tokens
@status accepted
@rationale 2-3 short sentences of in-character voice. 3 narrations per hunt =
           <= 240 narration tokens — cheap relative to chat round-trip cost.
           Module-level constant (no config field) per minimal-codebase principle.
           DEC-M7-CELEB-007 defers config promotion to a future slice.

@decision DEC-M7-CELEB-004
@title Per-hunt narration budget: 3 narrations per run_module() call
@status accepted
@rationale Realistic hunts produce 1-3 high-weight slot fills. Budget = 3 lets all
           realistic events be narrated; caps worst-case at ~240 tokens.
           HuntNarrationBudget is a per-invocation counter (resets each hunt, not per session).
           DEC-M7-CELEB-007 defers config promotion to a future slice.

@decision DEC-M7-CELEB-005
@title dossier_prediction_falsified events excluded from narration
@status accepted
@rationale Falsification events are contradiction signals, not achievement signals.
           They would be tone-mismatched if rendered as a celebration. The Skeptic
           badge (badge-skeptic) is the prestige recognition surface for falsifications.

@decision DEC-M7-CELEB-006
@title LLM failure -> silent None return at runtime; loud re-raise in tests
@status accepted
@rationale Runtime: narrate_celebration() wraps LLM call in try/except; returns None
           on any failure; caller skips append. ASCII art already in celebration string.
           Tests: _NARRATION_TESTING_RAISE_ON_FAILURE flag converts the silent path to
           a loud re-raise so tests can assert exact failure modes (Sacred Practice 5).

Public API:
  - HIGH_WEIGHT_NARRATION_THRESHOLD: float = 2.5
  - PER_NARRATION_TOKEN_CAP: int = 80
  - PER_HUNT_NARRATION_BUDGET: int = 3
  - HuntNarrationBudget (dataclass) -- per-hunt counter
  - is_high_weight_event(event: dict) -> bool
  - build_narration_prompt(event: dict, dossier_state) -> str
  - narrate_celebration(runner, event, dossier_state, budget) -> str | None
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adversary_pursuit.agent.runner import AgentRunner

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants (DEC-M7-CELEB-002, DEC-M7-CELEB-003, DEC-M7-CELEB-004)
# ---------------------------------------------------------------------------

HIGH_WEIGHT_NARRATION_THRESHOLD: float = 2.5
"""Slot weight threshold above which an event earns LLM narration.

Slots at or above this weight: Identity (5.0), Predictions (4.0), Capability (3.5),
TTPs (3.0), Motivation (3.0), Targeting (2.5), Denial (2.5).
Slots below: Infrastructure (2.0), Timing (2.0). (DEC-M7-CELEB-002.)
"""

PER_NARRATION_TOKEN_CAP: int = 80
"""Hard token ceiling per LLM narration call (DEC-M7-CELEB-003).

Enforced via litellm max_tokens parameter — the model cannot exceed it.
Sufficient for 2-3 short in-character sentences.
"""

PER_HUNT_NARRATION_BUDGET: int = 3
"""Maximum narrations per single run_module() invocation (DEC-M7-CELEB-004).

Realistic hunts produce 1-3 high-weight slot fills. Budget = 3 ensures all
realistic hunts are fully narrated. When exhausted, remaining eligible events
fall back to ASCII art silently.
"""

# ---------------------------------------------------------------------------
# Test-only flag (DEC-M7-CELEB-006)
# ---------------------------------------------------------------------------

_NARRATION_TESTING_RAISE_ON_FAILURE: bool = False
"""When True, narrate_celebration() re-raises exceptions instead of returning None.

Set this in test fixtures to convert the silent runtime fallback path into a loud
test failure. NEVER set to True in production code (DEC-M7-CELEB-006 / Sacred Practice 5).

Example test usage::

    import adversary_pursuit.gamification.dossier_celebrations as dc
    dc._NARRATION_TESTING_RAISE_ON_FAILURE = True
    try:
        narrate_celebration(runner, event, state, budget)  # will raise
    finally:
        dc._NARRATION_TESTING_RAISE_ON_FAILURE = False
"""

# ---------------------------------------------------------------------------
# Per-hunt budget counter (DEC-M7-CELEB-004)
# ---------------------------------------------------------------------------


@dataclass
class HuntNarrationBudget:
    """Per-hunt narration budget counter.

    Created fresh for each run_module() invocation. Not shared across hunts.
    Mutable: ``used`` increments on each successful narration call.

    Parameters
    ----------
    limit:
        Maximum narrations allowed this hunt (default: PER_HUNT_NARRATION_BUDGET).
    used:
        Number of narrations already consumed this hunt (starts at 0).
    """

    limit: int = field(default_factory=lambda: PER_HUNT_NARRATION_BUDGET)
    used: int = 0

    @property
    def remaining(self) -> int:
        """Number of narrations remaining in this hunt's budget."""
        return max(0, self.limit - self.used)

    @property
    def exhausted(self) -> bool:
        """True when no narration budget remains."""
        return self.used >= self.limit

    def consume(self) -> None:
        """Consume one narration from the budget."""
        self.used += 1


# ---------------------------------------------------------------------------
# Core policy functions
# ---------------------------------------------------------------------------


def is_high_weight_event(event: dict) -> bool:
    """Return True when ``event`` is eligible for LLM narration.

    Eligibility rules (DEC-M7-CELEB-002, DEC-M7-CELEB-005):
    - action must be ``dossier_slot_filled`` or ``dossier_prediction_validated``
    - ``dossier_prediction_falsified`` is ALWAYS ineligible (wrong tone for celebration)
    - slot weight (from event["indicator"] slot key via SLOT_WEIGHTS) must be
      >= HIGH_WEIGHT_NARRATION_THRESHOLD

    Parameters
    ----------
    event:
        Score event dict with keys: action, points, indicator, rule_description, etc.

    Returns
    -------
    bool
        True if the event qualifies for LLM narration.
    """
    action = event.get("action", "")

    # DEC-M7-CELEB-005: falsified events are never narrated
    if action == "dossier_prediction_falsified":
        return False

    # Only slot-fill and prediction-validated events are narrated
    if action not in ("dossier_slot_filled", "dossier_prediction_validated"):
        return False

    # Check slot weight against threshold
    weight = _get_event_slot_weight(event)
    return weight >= HIGH_WEIGHT_NARRATION_THRESHOLD


def build_narration_prompt(event: dict, dossier_state: object | None) -> str:
    """Build the LLM narration prompt for a high-weight dossier event.

    The prompt is fed as the ``user`` message to ``AgentRunner.narrate()``.
    The persona system prompt is injected by ``narrate()`` itself (reusing the
    active ``self.system_prompt``), so this function does NOT include system
    instructions in the returned string — only the user-facing prompt.

    Parameters
    ----------
    event:
        The qualifying score event dict (action, points, indicator, etc.).
    dossier_state:
        Current DossierState (may be None for fresh workspaces).

    Returns
    -------
    str
        User prompt for the narration LLM call (max ~50 tokens — the model
        response is what's capped at PER_NARRATION_TOKEN_CAP).
    """
    action = event.get("action", "")
    indicator = event.get("indicator", "")
    points = event.get("points", 0)
    rule_desc = event.get("rule_description", "")

    if action == "dossier_slot_filled":
        # Extract slot name from rule_description or indicator field
        slot_name = _extract_slot_name_from_event(event)
        weight = _get_event_slot_weight(event)
        prompt = (
            f"The analyst just filled the {slot_name} dossier slot "
            f"(importance weight: {weight:.1f}, +{points} pts). "
            f"Evidence indicator: {indicator}. "
            f"In 1-2 short sentences, celebrate this dossier breakthrough "
            f"in character. Be evocative, not generic. No markdown, no lists. "
            f"Max 2 sentences."
        )
    elif action == "dossier_prediction_validated":
        prompt = (
            f"The analyst's prediction was just validated (+{points} pts). "
            f"Prediction context: {rule_desc or indicator}. "
            f"In 1-2 short sentences, celebrate this analytical win "
            f"in character. Be precise and evocative. No markdown, no lists. "
            f"Max 2 sentences."
        )
    else:
        # Fallback — shouldn't be reached if is_high_weight_event was checked
        prompt = (
            f"The analyst made a significant dossier discovery (+{points} pts). "
            f"In 1 short sentence, celebrate this in character."
        )

    return prompt


def narrate_celebration(
    runner: "AgentRunner",
    event: dict,
    dossier_state: object | None,
    budget: HuntNarrationBudget,
) -> str | None:
    """Produce LLM narration text for a high-weight dossier event.

    Calls ``runner.narrate()`` with the narration prompt and returns the
    narration text. Returns ``None`` when:
    - ``budget.exhausted`` (budget already consumed this hunt)
    - ``runner.narrate()`` raises or returns an unusable value
    - narration text fails validation (contains Rich markup or is empty)

    When ``_NARRATION_TESTING_RAISE_ON_FAILURE`` is True, any underlying
    exception is re-raised instead of returning None (DEC-M7-CELEB-006).

    Parameters
    ----------
    runner:
        AgentRunner with an active LLM session. ``runner.narrate()`` is the
        single LLM call authority (DEC-M7-CELEB-001).
    event:
        The qualifying score event dict.
    dossier_state:
        Current DossierState or None.
    budget:
        Per-hunt narration budget counter. Consumed on success.

    Returns
    -------
    str | None
        Narration text ready to append to the celebration string, or None
        when narration could not be produced.
    """
    if budget.exhausted:
        return None

    prompt = build_narration_prompt(event, dossier_state)

    try:
        raw = runner.narrate(prompt, max_tokens=PER_NARRATION_TOKEN_CAP)
    except Exception as exc:  # noqa: BLE001
        _LOG.debug("LLM narration call failed: %s", exc)
        if _NARRATION_TESTING_RAISE_ON_FAILURE:
            raise
        return None

    # Validate the returned text
    if raw is None:
        if _NARRATION_TESTING_RAISE_ON_FAILURE:
            raise RuntimeError("narrate() returned None — LLM narration failure")
        return None

    narration = _validate_narration_text(raw)
    if narration is None:
        if _NARRATION_TESTING_RAISE_ON_FAILURE:
            raise RuntimeError(f"narration text failed validation: {raw!r}")
        return None

    budget.consume()
    return narration


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _get_event_slot_weight(event: dict) -> float:
    """Extract the slot weight for a dossier event.

    Reads the slot name from the event and looks up the weight from
    SLOT_WEIGHTS (DEC-M1-SLOTS-WEIGHT-AUTHORITY-001 — read-only consumer).

    For ``dossier_prediction_validated`` events, uses the Predictions slot
    weight (4.0) since a validated prediction advances the Predictions slot.

    Parameters
    ----------
    event:
        Score event dict.

    Returns
    -------
    float
        Slot weight (0.0 if slot cannot be determined).
    """
    try:
        from adversary_pursuit.dossier.slots import SLOT_WEIGHTS, DossierSlotName

        action = event.get("action", "")

        if action == "dossier_prediction_validated":
            return SLOT_WEIGHTS.get(DossierSlotName.PREDICTIONS, 0.0)

        # For slot_filled events: slot name encoded in rule_description or indicator
        slot_name = _extract_slot_name_from_event(event)
        if not slot_name:
            return 0.0

        try:
            slot_enum = DossierSlotName(slot_name.lower())
            return SLOT_WEIGHTS.get(slot_enum, 0.0)
        except ValueError:
            return 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def _extract_slot_name_from_event(event: dict) -> str:
    """Extract the slot name string from a dossier_slot_filled event.

    The slot name is encoded in ``rule_description`` (e.g.
    ``"identity slot filled"`` or ``"dossier slot identity filled"``) or in
    the ``indicator`` field (e.g. ``"identity"``) depending on M-3 emission
    format. Returns empty string if not found.

    Parameters
    ----------
    event:
        Score event dict with action == ``dossier_slot_filled``.

    Returns
    -------
    str
        Slot name string (e.g. ``"identity"``), or empty string.
    """
    # Try rule_description first — M-3 emits "dossier slot {name} filled"
    rule_desc = event.get("rule_description", "")
    if rule_desc:
        # Pattern: "dossier slot <name> filled" or "<name> slot filled"
        parts = rule_desc.lower().split()
        # Find the slot name by checking each word against DossierSlotName
        try:
            from adversary_pursuit.dossier.slots import DossierSlotName

            valid_slots = {s.value for s in DossierSlotName}
            for word in parts:
                if word in valid_slots:
                    return word
        except Exception:  # noqa: BLE001
            pass

    # Fall back to indicator field
    indicator = event.get("indicator", "")
    if indicator:
        try:
            from adversary_pursuit.dossier.slots import DossierSlotName

            valid_slots = {s.value for s in DossierSlotName}
            if indicator.lower() in valid_slots:
                return indicator.lower()
        except Exception:  # noqa: BLE001
            pass

    return ""


def _validate_narration_text(text: str) -> str | None:
    """Validate and clean narration text from the LLM.

    Rejects text that:
    - Is empty or whitespace-only
    - Contains Rich markup characters ``[`` / ``]`` (would break Rich panel rendering)

    On rejection returns None. On acceptance returns stripped text.

    Parameters
    ----------
    text:
        Raw LLM response string.

    Returns
    -------
    str | None
        Cleaned narration text, or None if text is invalid.
    """
    stripped = text.strip()
    if not stripped:
        return None

    # Reject if Rich markup characters are present (DEC-M7-CELEB-006)
    if "[" in stripped or "]" in stripped:
        _LOG.debug("Narration text rejected: contains Rich markup characters: %r", stripped)
        return None

    return stripped
