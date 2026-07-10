"""Battery registry — default battery catalogue and dispatch logic.

Defines the five default batteries (C-3 specification) and provides
dispatch_batteries() to select applicable batteries for a given target
type and dossier state.

@decision DEC-BATTERY-REGISTRY-001
@title 5 batteries per C-3 default; deterministic dispatch
@status accepted
@rationale Five batteries cover the primary investigation dimensions:
           identity (WHOIS + crt.sh + breach), infrastructure (Shodan +
           Censys + DNS), reputation (VT + OTX + AbuseIPDB + GreyNoise),
           payload (URLhaus + ThreatFox + MalwareBazaar), and behavioral
           (PassiveTotal + URLscan). Dispatch is deterministic: batteries
           are selected based on (a) target type compatibility and (b)
           dossier slot fill status — batteries whose target slot is
           already FILLED are skipped. This avoids redundant tool calls
           and respects the dossier state as the single source of truth
           for investigation progress.
"""

from __future__ import annotations

from adversary_pursuit.agent.battery import Battery
from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus

# ---------------------------------------------------------------------------
# Default battery catalogue (DEC-BATTERY-REGISTRY-001)
# ---------------------------------------------------------------------------

DEFAULT_BATTERIES: dict[str, Battery] = {
    "identity_battery": Battery(
        name="identity_battery",
        tools=("whois_lookup", "crtsh_lookup", "check_breaches"),
        target_slot=DossierSlotName.IDENTITY,
        applies_to=("domain-name", "email-addr"),
        hypothesis_hint="registrant + certificate + breach exposure",
    ),
    "infrastructure_battery": Battery(
        name="infrastructure_battery",
        tools=("shodan_host_lookup", "censys_host_lookup", "dns_resolve"),
        target_slot=DossierSlotName.INFRASTRUCTURE,
        applies_to=("domain-name", "ipv4-addr", "ipv6-addr"),
        hypothesis_hint="hosted infrastructure fingerprint",
    ),
    "reputation_battery": Battery(
        name="reputation_battery",
        tools=("virustotal_lookup", "otx_threat_intel", "check_ip_reputation", "greynoise_lookup"),
        target_slot=DossierSlotName.TTPS,
        applies_to=("domain-name", "ipv4-addr", "url", "file"),
        hypothesis_hint="community reputation + observed tradecraft",
    ),
    "payload_battery": Battery(
        name="payload_battery",
        tools=("urlhaus_lookup", "threatfox_lookup", "malwarebazaar_lookup"),
        target_slot=DossierSlotName.TTPS,
        applies_to=("file", "url"),
        hypothesis_hint="known-malicious payload family",
    ),
    "behavioral_battery": Battery(
        name="behavioral_battery",
        tools=("passivetotal_lookup", "scan_url"),
        target_slot=DossierSlotName.TIMING,
        applies_to=("domain-name", "ipv4-addr", "url"),
        hypothesis_hint="temporal + interaction telemetry",
    ),
}


# ---------------------------------------------------------------------------
# Dispatch logic
# ---------------------------------------------------------------------------


def dispatch_batteries(
    target_type: str,
    dossier_state=None,  # DossierState | None
) -> list[Battery]:
    """Return applicable batteries for *target_type* whose slot is not yet filled.

    Selection criteria (DEC-BATTERY-REGISTRY-001):
    1. ``target_type in battery.applies_to`` — the battery supports this STIX type.
    2. The dossier slot for ``battery.target_slot`` is NOT ``SlotStatus.FILLED``
       (or *dossier_state* is None, meaning we have no state yet — run all
       applicable batteries).

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
    for battery in DEFAULT_BATTERIES.values():
        # Filter by target type compatibility
        if target_type not in battery.applies_to:
            continue

        # Filter by dossier slot fill status
        if dossier_state is not None:
            slot_state = dossier_state.slots.get(battery.target_slot)
            if slot_state is not None and slot_state.status == SlotStatus.FILLED:
                continue  # slot already filled — skip this battery

        result.append(battery)

    return result
