"""Battery registry — default battery catalogue and dispatch logic.

Defines the six default batteries (C-3 specification) and provides
dispatch_batteries() to select applicable batteries for a given target
type and dossier state.

@decision DEC-BATTERY-REGISTRY-001
@title 5 tool-batteries + 1 synthesis sentinel per C-3; every slot covered
@status accepted
@rationale C-3 acceptance: "every dossier slot has at least one battery that
           can contribute evidence." Five tool-driven batteries cover 6 of 9
           slots (IDENTITY, INFRASTRUCTURE, TTPS, CAPABILITY, TIMING, TARGETING)
           via multi-slot target_slots tuples. The remaining 3 slots (MOTIVATION,
           DENIAL, PREDICTIONS) are LLM-synthesised rather than tool-callable
           (C-11: batteries deterministic, LLM synthesizes). A synthesis_battery
           sentinel with tools=() covers those 3 slots; dispatch fires it when
           ≥N tool-driven slots are filled (N=3 threshold), triggering a single
           LLM call with the accreted dossier state as context. This sentinel is
           explicitly NOT a tool dispatcher — it carries tools=() and dispatch
           implementations MUST NOT iterate over its empty tools tuple as a tool
           call sequence. Sacred Practice 5 (fail loud): callers that receive a
           synthesis_battery must detect tools==() and route to the LLM synthesis
           path, not silently no-op.

           Multi-slot batteries (C-3 cross-cutting):
             reputation_battery → (TTPS, CAPABILITY)
             behavioral_battery → (TIMING, TARGETING)

           This gives complete 9/9 slot coverage across the registry.

           Dispatch is deterministic: batteries are selected based on
           (a) target type compatibility and (b) whether ANY of the battery's
           target_slots is not yet FILLED in the current dossier state.
           Batteries whose ALL target_slots are already FILLED are skipped.
"""

from __future__ import annotations

from adversary_pursuit.agent.battery import Battery
from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus

# ---------------------------------------------------------------------------
# Default battery catalogue (DEC-BATTERY-REGISTRY-001)
# ---------------------------------------------------------------------------

# Threshold: number of tool-driven slots that must be FILLED before the
# synthesis_battery sentinel is dispatched (C-11 guard).
_SYNTHESIS_TRIGGER_THRESHOLD: int = 3

# Sentinel marker used in synthesis_battery.applies_to to mean "all target types".
_APPLIES_TO_ANY: str = "__any__"

DEFAULT_BATTERIES: dict[str, Battery] = {
    "identity_battery": Battery(
        name="identity_battery",
        tools=("whois_lookup", "crtsh_lookup", "check_breaches"),
        target_slots=(DossierSlotName.IDENTITY,),
        applies_to=("domain-name", "email-addr"),
        hypothesis_hint="registrant + certificate + breach exposure",
    ),
    "infrastructure_battery": Battery(
        name="infrastructure_battery",
        tools=("shodan_host_lookup", "censys_host_lookup"),
        target_slots=(DossierSlotName.INFRASTRUCTURE,),
        applies_to=("ipv4-addr", "ipv6-addr"),
        hypothesis_hint="hosted infrastructure fingerprint",
    ),
    "reputation_battery": Battery(
        name="reputation_battery",
        tools=("virustotal_lookup", "otx_threat_intel", "check_ip_reputation", "greynoise_lookup"),
        # C-3 cross-cutting: covers both TTPs (tool-observable tradecraft) and
        # CAPABILITY (sophistication ceiling derived from observed tool inventory).
        target_slots=(DossierSlotName.TTPS, DossierSlotName.CAPABILITY),
        applies_to=("domain-name", "ipv4-addr", "url", "file"),
        hypothesis_hint="community reputation + observed tradecraft + capability ceiling",
    ),
    "payload_battery": Battery(
        name="payload_battery",
        tools=("urlhaus_lookup", "threatfox_lookup", "malwarebazaar_lookup"),
        target_slots=(DossierSlotName.TTPS,),
        applies_to=("file", "url"),
        hypothesis_hint="known-malicious payload family",
    ),
    "behavioral_battery": Battery(
        name="behavioral_battery",
        # Passive DNS and interaction metadata come from explicit services;
        # AP never issues direct resolver queries from the operator host.
        tools=("passivetotal_lookup", "scan_url"),
        # C-3 cross-cutting: covers both TIMING (when the actor operates) and
        # TARGETING (which assets/geographies the actor targets).
        target_slots=(DossierSlotName.TIMING, DossierSlotName.TARGETING),
        applies_to=("domain-name", "ipv4-addr", "url"),
        hypothesis_hint="temporal + interaction telemetry + targeting profile",
    ),
    "synthesis_battery": Battery(
        name="synthesis_battery",
        # tools=() is intentional and load-bearing. dispatch_batteries() callers
        # MUST detect tools==() and route to LLM synthesis, NOT iterate tools
        # as tool calls (C-11; Sacred Practice 5 — fail loud, never silently no-op).
        # Slice 7 will implement the LLM synthesis call; this sentinel marks the
        # dispatch boundary so the routing contract is established now.
        tools=(),
        # Covers the 3 LLM-synthesised slots: MOTIVATION (why the actor acts),
        # DENIAL (deception strategies, deferred to M-5 user notes), and
        # PREDICTIONS (forward AP-generated predictions, deferred to M-4).
        target_slots=(
            DossierSlotName.MOTIVATION,
            DossierSlotName.DENIAL,
            DossierSlotName.PREDICTIONS,
        ),
        # __any__ sentinel — matches all STIX target types once the synthesis
        # trigger threshold is reached. dispatch_batteries() handles this specially.
        applies_to=(_APPLIES_TO_ANY,),
        hypothesis_hint="LLM synthesis: motivation + denial strategies + predictions",
    ),
}


# ---------------------------------------------------------------------------
# Dispatch logic
# ---------------------------------------------------------------------------


def _tool_driven_slots_filled(dossier_state) -> int:
    """Count tool-driven slots (non-synthesis) that are FILLED.

    Used by the synthesis_battery trigger logic (DEC-BATTERY-REGISTRY-001).
    Returns 0 when dossier_state is None.
    """
    if dossier_state is None:
        return 0
    synthesis_slots = frozenset(DEFAULT_BATTERIES["synthesis_battery"].target_slots)
    count = 0
    for slot_name, slot_state in dossier_state.slots.items():
        if slot_name not in synthesis_slots and slot_state.status == SlotStatus.FILLED:
            count += 1
    return count


def dispatch_batteries(
    target_type: str,
    dossier_state=None,  # DossierState | None
) -> list[Battery]:
    """Return applicable batteries for *target_type* whose slots are not yet all filled.

    Selection criteria (DEC-BATTERY-REGISTRY-001):
    1. Target type compatibility:
       - For regular batteries: ``target_type in battery.applies_to``
       - For synthesis_battery: triggered only when ≥N tool-driven slots are
         FILLED (N=``_SYNTHESIS_TRIGGER_THRESHOLD``), regardless of target type.
    2. Slot fill status:
       - Regular batteries: dispatched when ANY of their target_slots is NOT
         ``SlotStatus.FILLED`` (or dossier_state is None). Batteries whose ALL
         target_slots are FILLED are skipped (no redundant tool calls).
       - synthesis_battery: dispatched when the trigger threshold is met AND
         ANY of (MOTIVATION, DENIAL, PREDICTIONS) is not yet FILLED.

    Batteries are returned in DEFAULT_BATTERIES insertion order.

    Parameters
    ----------
    target_type:
        STIX SCO type string, e.g. "domain-name", "ipv4-addr".
    dossier_state:
        A DossierState instance from slot_inference.py, or None.
        When None, all type-applicable batteries are returned regardless of
        fill status (conservative: run everything on first dispatch).

    Returns
    -------
    list[Battery]
        Ordered list of applicable, non-redundant batteries.
    """
    result: list[Battery] = []
    filled_tool_slots = _tool_driven_slots_filled(dossier_state)

    for battery in DEFAULT_BATTERIES.values():
        # --- synthesis_battery special path (C-11) ---
        if battery.name == "synthesis_battery":
            # Only trigger when enough tool-driven evidence is available
            if filled_tool_slots < _SYNTHESIS_TRIGGER_THRESHOLD:
                continue
            # Check if any synthesis slot still needs filling
            if dossier_state is not None:
                all_filled = all(
                    dossier_state.slots.get(slot) is not None
                    and dossier_state.slots[slot].status == SlotStatus.FILLED
                    for slot in battery.target_slots
                )
                if all_filled:
                    continue
            result.append(battery)
            continue

        # --- Regular batteries ---
        # Filter by target type compatibility
        if target_type not in battery.applies_to:
            continue

        # Filter by dossier slot fill status: skip only if ALL target_slots are filled.
        # If ANY slot is not filled, the battery can still contribute evidence (C-3).
        if dossier_state is not None:
            all_slots_filled = all(
                dossier_state.slots.get(slot) is not None
                and dossier_state.slots[slot].status == SlotStatus.FILLED
                for slot in battery.target_slots
            )
            if all_slots_filled:
                continue  # all slots already filled — skip this battery

        result.append(battery)

    return result
