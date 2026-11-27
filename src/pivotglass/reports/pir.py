"""Priority Intelligence Requirement categories, tiers, and the answer verdict (#60).

@decision DEC-PIR-001
@title A PIR is a typed input whose category shapes collection, reports, and "answered"
@status accepted
@rationale A free-text question did not change what Pivotglass collected, what
           it reported, or when the hunt was finished. The analyst now states a
           category and an intelligence tier on the investigation. This table is
           the single definition of each category: the dossier slots and sources
           that matter, the stop conditions seeded into the existing lifecycle
           (so the Pursuit Brief and lifecycle measure progress without a second
           tracker), and the report types suggested per tier. Each category
           states its collection fit honestly. A weak fit still runs, but its
           report says Pivotglass collection cannot answer the question; a model
           is never asked to fill that gap. The verdict is deterministic and is
           computed from lifecycle records only. Priority ranking remains
           DEC-INFORMATION-REQUIREMENTS-001.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable

UNSPECIFIED = "unspecified"
PIR_SEED_KEY = "pir_seed"


class RequirementCategory(StrEnum):
    THREAT_ACTOR_CAMPAIGN = "threat_actor_campaign"
    VULNERABILITY_EXPLOITATION = "vulnerability_exploitation"
    TTPS = "ttps"
    THIRD_PARTY_SUPPLY_CHAIN = "third_party_supply_chain"
    BRAND_VIP_FOOTPRINT = "brand_vip_footprint"
    GEOPOLITICAL_REGULATORY = "geopolitical_regulatory"
    STRATEGIC_MNA = "strategic_mna"


class IntelligenceLevel(StrEnum):
    TACTICAL = "tactical"
    OPERATIONAL = "operational"
    STRATEGIC = "strategic"


class CollectionFit(StrEnum):
    STRONG = "strong"
    GOOD = "good"
    PARTIAL = "partial"
    WEAK = "weak"


class PirVerdict(StrEnum):
    NO_PIR = "no_pir"
    ANSWERED = "answered"
    PARTIALLY_ANSWERED = "partially_answered"
    NOT_ANSWERED = "not_answered"


VERDICT_LABELS: dict[PirVerdict, str] = {
    PirVerdict.NO_PIR: "No PIR recorded",
    PirVerdict.ANSWERED: "Answered",
    PirVerdict.PARTIALLY_ANSWERED: "Partially answered",
    PirVerdict.NOT_ANSWERED: "Not answered by available collection",
}


@dataclass(frozen=True)
class LevelDefinition:
    label: str
    audience: str
    focus: str


LEVELS: dict[IntelligenceLevel, LevelDefinition] = {
    IntelligenceLevel.TACTICAL: LevelDefinition(
        "Tactical",
        "SOC analysts and incident responders",
        "Immediate indicators, active phishing lures, malware hashes, blocking and triage.",
    ),
    IntelligenceLevel.OPERATIONAL: LevelDefinition(
        "Operational",
        "Threat hunters and vulnerability management",
        "Actor TTPs, active exploitation, and campaign infrastructure.",
    ),
    IntelligenceLevel.STRATEGIC: LevelDefinition(
        "Strategic",
        "CISO, executive leadership and the board",
        "Long-term threat trends, geopolitical shifts, supply-chain and M&A risk.",
    ),
}


@dataclass(frozen=True)
class CategoryDefinition:
    label: str
    focus: str
    example: str
    collection_fit: CollectionFit
    fit_note: str
    default_level: IntelligenceLevel
    dossier_slots: tuple[str, ...]
    preferred_sources: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    report_types: dict[IntelligenceLevel, tuple[str, ...]]


CATEGORIES: dict[RequirementCategory, CategoryDefinition] = {
    RequirementCategory.THREAT_ACTOR_CAMPAIGN: CategoryDefinition(
        label="Threat actor and campaign tracking",
        focus="Which adversaries are targeting the organisation's industry, region, or technology, "
        "and with what infrastructure.",
        example="Which ransomware groups are actively targeting mid-sized financial institutions "
        "in North America?",
        collection_fit=CollectionFit.STRONG,
        fit_note="Infrastructure pivots (passive DNS, certificates, registration, hosting) and CTI "
        "feeds tie indicators to campaigns. Naming the actor behind them is still an analyst "
        "judgment.",
        default_level=IntelligenceLevel.OPERATIONAL,
        dossier_slots=("identity", "infrastructure", "capability", "ttps", "targeting", "timing"),
        preferred_sources=(
            "cti/threatfox", "cti/otx", "osint/mnemonic_pdns", "osint/crtsh", "osint/rdap",
            "osint/urlscan_search", "cti/malwarebazaar",
        ),
        stop_conditions=(
            "Infrastructure linked to the activity is enumerated, and each link cites its source "
            "(passive DNS, certificate, registration, or hosting).",
            "At least two competing explanations of who operates the infrastructure have been "
            "tested against the evidence.",
            "The campaign's first and last observed activity are established from sourced "
            "observations.",
            "The attribution judgment states its likelihood and confidence, or records why the "
            "evidence does not support attribution.",
        ),
        report_types={
            IntelligenceLevel.TACTICAL: ("threat-activity-alert",),
            IntelligenceLevel.OPERATIONAL: (
                "campaign-intrusion-analysis", "infrastructure-clustering-graph",
                "diamond-model-analysis",
            ),
            IntelligenceLevel.STRATEGIC: ("threat-actor-profile", "executive-threat-briefing"),
        },
    ),
    RequirementCategory.VULNERABILITY_EXPLOITATION: CategoryDefinition(
        label="Vulnerability and exploitation intelligence",
        focus="Newly disclosed or zero-day vulnerabilities being exploited in the wild, to "
        "prioritise patching.",
        example="Are any vulnerabilities in our edge firewall appliances currently being exploited "
        "by initial access brokers?",
        collection_fit=CollectionFit.PARTIAL,
        fit_note="Shodan and InternetDB report CVEs on exposed hosts, and CTI feeds can tie "
        "exploitation infrastructure to a CVE. Exploitation status, EPSS and CVSS sources are "
        "not yet collected (#58).",
        default_level=IntelligenceLevel.OPERATIONAL,
        dossier_slots=("capability", "ttps", "infrastructure", "timing"),
        preferred_sources=(
            "osint/shodan_ip", "osint/shodan_internetdb", "osint/censys_host", "cti/threatfox",
            "osint/greynoise",
        ),
        stop_conditions=(
            "The vulnerability is identified by CVE, with the affected products and versions.",
            "Exploitation status is established from a cited source: exploited in the wild, "
            "public proof of concept, or none observed.",
            "Exposure of the assets in scope is checked, or recorded as unknown.",
            "Patch or mitigation guidance is cited from the vendor or another source.",
        ),
        report_types={
            IntelligenceLevel.TACTICAL: ("threat-activity-alert", "detection-signature-bundle"),
            IntelligenceLevel.OPERATIONAL: (
                "vulnerability-exploitation-brief", "threat-hunting-package",
            ),
            IntelligenceLevel.STRATEGIC: (
                "executive-threat-briefing", "threat-informed-risk-assessment",
            ),
        },
    ),
    RequirementCategory.TTPS: CategoryDefinition(
        label="Tactics, techniques, and procedures",
        focus="How attackers operate, mapped to ATT&CK, to improve detection engineering and "
        "threat hunting.",
        example="What post-exploitation techniques are adversaries using to bypass endpoint "
        "detection in cloud environments?",
        collection_fit=CollectionFit.STRONG,
        fit_note="ATT&CK mappings carry their evidence, mapper and analyst disposition, and "
        "export to Navigator from the pinned ATT&CK content. Procedure detail is limited to "
        "what collection and documents reveal.",
        default_level=IntelligenceLevel.OPERATIONAL,
        dossier_slots=("ttps", "capability", "denial"),
        preferred_sources=("cti/malwarebazaar", "cti/virustotal", "osint/urlscan", "cti/otx"),
        stop_conditions=(
            "Each observed behaviour is mapped to an ATT&CK technique with a cited observation "
            "and an analyst disposition.",
            "Procedure-level detail (command line, tooling, or protocol) is recorded for the "
            "techniques that matter to detection.",
            "Detection or hunting opportunities are identified for the mapped techniques, or "
            "recorded as a gap.",
        ),
        report_types={
            IntelligenceLevel.TACTICAL: ("detection-signature-bundle",),
            IntelligenceLevel.OPERATIONAL: (
                "attack-navigator-layer", "threat-hunting-package", "kill-chain-mapping",
            ),
            IntelligenceLevel.STRATEGIC: (
                "actor-capability-radar", "defensive-coverage-assessment",
            ),
        },
    ),
    RequirementCategory.THIRD_PARTY_SUPPLY_CHAIN: CategoryDefinition(
        label="Third-party and supply-chain risk",
        focus="Breaches, compromises, or threat activity affecting critical vendors, software "
        "providers, or business partners.",
        example="Have any of our Tier-1 managed service providers suffered a breach or credential "
        "leak in the last 30 days?",
        collection_fit=CollectionFit.PARTIAL,
        fit_note="Pivotglass can examine a vendor's internet exposure, breach records, and "
        "malicious infrastructure that names it. It cannot see compromise inside a vendor's "
        "network.",
        default_level=IntelligenceLevel.OPERATIONAL,
        dossier_slots=("targeting", "infrastructure", "timing"),
        preferred_sources=(
            "osint/shodan_ip", "osint/censys_host", "osint/hibp", "osint/crtsh",
            "osint/urlscan_search", "osint/rdap",
        ),
        stop_conditions=(
            "The vendors in scope and their internet-facing assets are listed.",
            "Breach, credential-exposure and malicious-infrastructure findings for each vendor "
            "are recorded with sources, or recorded as none found.",
            "The time window searched is stated.",
            "Impact on the organisation is assessed, or recorded as needing organisation input.",
        ),
        report_types={
            IntelligenceLevel.TACTICAL: ("threat-activity-alert",),
            IntelligenceLevel.OPERATIONAL: ("campaign-intrusion-analysis",),
            IntelligenceLevel.STRATEGIC: (
                "threat-informed-risk-assessment", "executive-threat-briefing",
            ),
        },
    ),
    RequirementCategory.BRAND_VIP_FOOTPRINT: CategoryDefinition(
        label="Brand, VIP, and digital-footprint protection",
        focus="Leaked credentials, executive impersonation, domain spoofing, or underground "
        "chatter targeting the organisation.",
        example="Are corporate credentials or source code for our flagship product being sold on "
        "underground marketplaces?",
        collection_fit=CollectionFit.GOOD,
        fit_note="Certificate transparency, urlscan, registration data and passive DNS find "
        "lookalike domains and phishing infrastructure, and HIBP finds breached accounts. "
        "Underground markets and dark-web forums are not collected.",
        default_level=IntelligenceLevel.TACTICAL,
        dossier_slots=("targeting", "infrastructure", "timing"),
        preferred_sources=(
            "osint/crtsh", "osint/urlscan_search", "osint/rdap", "osint/whois_lookup",
            "osint/mnemonic_pdns", "osint/hibp", "cti/urlhaus",
        ),
        stop_conditions=(
            "The protected names, domains and people in scope are listed.",
            "Lookalike domains, certificates and phishing pages found are recorded with sources "
            "and first-seen dates.",
            "Credential exposure for the domains in scope is checked, or recorded as not checked.",
            "Each finding has a recommended action (monitor, block, or take down), or a reason "
            "for none.",
        ),
        report_types={
            IntelligenceLevel.TACTICAL: ("threat-activity-alert", "detection-signature-bundle"),
            IntelligenceLevel.OPERATIONAL: (
                "infrastructure-clustering-graph", "campaign-intrusion-analysis",
            ),
            IntelligenceLevel.STRATEGIC: ("executive-threat-briefing",),
        },
    ),
    RequirementCategory.GEOPOLITICAL_REGULATORY: CategoryDefinition(
        label="Geopolitical and regulatory risk",
        focus="How regional conflict, sanctions, elections, or new regulation could trigger "
        "attacks or disrupt operations.",
        example="How might escalating regional tensions affect the cyber threat landscape for our "
        "manufacturing plants in Eastern Europe?",
        collection_fit=CollectionFit.WEAK,
        fit_note="Pivotglass collects infrastructure and indicator evidence, not geopolitical "
        "reporting. It can show whether technical activity linked to an event touches the "
        "organisation; the geopolitical assessment needs the analyst's own sources.",
        default_level=IntelligenceLevel.STRATEGIC,
        dossier_slots=("motivation", "targeting", "timing"),
        preferred_sources=("cti/otx", "cti/threatfox"),
        stop_conditions=(
            "The event, its region, and the organisation's assets or operations there are stated.",
            "The sources for the geopolitical assessment are cited with reliability ratings.",
            "Technical activity linked to the event that touches the organisation is recorded, "
            "or recorded as none found.",
            "The assessment states its likelihood and confidence, and what would change it.",
        ),
        report_types={
            IntelligenceLevel.TACTICAL: (),
            IntelligenceLevel.OPERATIONAL: ("strategic-threat-landscape",),
            IntelligenceLevel.STRATEGIC: (
                "executive-threat-briefing", "strategic-threat-landscape",
            ),
        },
    ),
    RequirementCategory.STRATEGIC_MNA: CategoryDefinition(
        label="Strategic and M&A risk",
        focus="Decisions about mergers, acquisitions, new market entry, or major technology "
        "investment.",
        example="Does the acquisition target have undisclosed breaches or active threat-actor "
        "persistence in its network?",
        collection_fit=CollectionFit.WEAK,
        fit_note="Pivotglass can review a target's external exposure, breach records, and "
        "malicious infrastructure that names it. It cannot see undisclosed breaches or "
        "persistence inside the target's network.",
        default_level=IntelligenceLevel.STRATEGIC,
        dossier_slots=("targeting", "infrastructure", "timing"),
        preferred_sources=(
            "osint/shodan_ip", "osint/censys_host", "osint/hibp", "osint/crtsh", "osint/rdap",
            "osint/urlscan_search",
        ),
        stop_conditions=(
            "The subject (acquisition target, market, or investment) and its internet-facing "
            "assets are stated.",
            "External exposure, breach history and malicious-infrastructure findings are "
            "recorded with sources, or recorded as none found.",
            "What this collection cannot establish, such as internal compromise, is recorded as "
            "a limitation.",
            "The risk judgment states its likelihood and confidence.",
        ),
        report_types={
            IntelligenceLevel.TACTICAL: (),
            IntelligenceLevel.OPERATIONAL: ("threat-informed-risk-assessment",),
            IntelligenceLevel.STRATEGIC: (
                "threat-informed-risk-assessment", "executive-threat-briefing",
            ),
        },
    ),
}

ACH_REPORT_TYPE = "ach-attribution-matrix"
_RESOLVED = {"satisfied", "resolved"}
_WITHDRAWN = {"deferred", "rejected"}


def parse_category(value: str) -> RequirementCategory:
    """Accept a category id, with hyphens or underscores, in any case."""

    cleaned = value.strip().casefold().replace("-", "_")
    for category in RequirementCategory:
        if cleaned == category.value:
            return category
    raise ValueError(
        f"Unknown PIR category: {value}. Choose one of: "
        + ", ".join(category.value for category in RequirementCategory)
    )


def parse_level(value: str) -> IntelligenceLevel:
    cleaned = value.strip().casefold()
    for level in IntelligenceLevel:
        if cleaned == level.value:
            return level
    raise ValueError("Intelligence tier must be tactical, operational, or strategic.")


def suggested_report_types(
    category: RequirementCategory, level: IntelligenceLevel, *, hypothesis_count: int = 0
) -> list[str]:
    """Report types suggested for the PIR; ACH joins once two hypotheses compete."""

    suggestions = list(CATEGORIES[category].report_types[level])
    if hypothesis_count >= 2 and ACH_REPORT_TYPE not in suggestions:  # noqa: PLR2004
        suggestions.append(ACH_REPORT_TYPE)
    return suggestions


def _titled(type_ids: list[str]) -> list[dict[str, Any]]:
    """Suggested report types with their registry titles."""

    from pivotglass.reports.registry import get_report_type  # the registry imports this module

    return [
        {"id": t.id, "title": t.title}
        for t in (get_report_type(type_id) for type_id in type_ids)
    ]


def seeded_items(items: Iterable[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    """Stop conditions this category seeded (and that the analyst has not withdrawn)."""

    return [
        item
        for item in items
        if item.get("item_type") == "stop_condition"
        and (item.get("criteria") or {}).get(PIR_SEED_KEY) == category
        and item.get("status") not in _WITHDRAWN
    ]


def build_pir_state(investigation: dict[str, Any] | None, snapshot: dict[str, Any]) -> dict[str, Any]:
    """The PIR, its definition, stop-condition progress, and the deterministic verdict."""

    if investigation is None:
        return {"verdict": PirVerdict.NO_PIR.value, "verdict_label": VERDICT_LABELS[PirVerdict.NO_PIR]}
    raw_category = str(investigation.get("requirement_category") or UNSPECIFIED)
    raw_level = str(investigation.get("intelligence_level") or UNSPECIFIED)
    question = next(
        (
            row.get("text")
            for row in snapshot.get("questions", [])
            if row.get("id") == investigation.get("primary_question_id")
        ),
        None,
    )
    base = {
        "investigation_id": investigation.get("id"),
        "question": question,
        "category": raw_category,
        "level": raw_level,
    }
    if raw_category == UNSPECIFIED:
        return {
            **base,
            "verdict": PirVerdict.NO_PIR.value,
            "verdict_label": VERDICT_LABELS[PirVerdict.NO_PIR],
            "next_step": "Choose a PIR category and tier with `analysis pir <category> [tier]`.",
        }
    category = RequirementCategory(raw_category)
    definition = CATEGORIES[category]
    level = IntelligenceLevel(raw_level) if raw_level != UNSPECIFIED else definition.default_level
    items = [
        item
        for item in snapshot.get("lifecycle_items", [])
        if item.get("investigation_id") == investigation.get("id")
    ]
    stops = seeded_items(items, category.value)
    resolved = [item for item in stops if item.get("status") in _RESOLVED]
    conclusions = [
        item
        for item in items
        if item.get("item_type") == "conclusion"
        and item.get("analyst_disposition") == "accepted"
        and item.get("status") not in _WITHDRAWN
    ]
    open_gaps = [
        item
        for item in items
        if item.get("item_type") == "knowledge_gap" and item.get("status") == "open"
    ]
    if stops and len(resolved) == len(stops) and conclusions:
        verdict = PirVerdict.ANSWERED
    elif resolved or conclusions:
        verdict = PirVerdict.PARTIALLY_ANSWERED
    else:
        verdict = PirVerdict.NOT_ANSWERED
    hypothesis_count = sum(
        1 for row in snapshot.get("hypotheses", []) if row.get("status") != "rejected"
    )
    return {
        **base,
        "level": level.value,
        "category_label": definition.label,
        "level_label": LEVELS[level].label,
        "audience": LEVELS[level].audience,
        "collection_fit": definition.collection_fit.value,
        "fit_note": definition.fit_note,
        "verdict": verdict.value,
        "verdict_label": VERDICT_LABELS[verdict],
        "stop_conditions": [
            {"id": item.get("id"), "statement": item.get("statement"), "status": item.get("status")}
            for item in stops
        ],
        "resolved_count": len(resolved),
        "conclusion_count": len(conclusions),
        "open_gaps": [item.get("statement") for item in open_gaps],
        "dossier_slots": list(definition.dossier_slots),
        "preferred_sources": list(definition.preferred_sources),
        "report_types": _titled(suggested_report_types(category, level, hypothesis_count=hypothesis_count)),
    }


def catalogue() -> dict[str, Any]:
    """The category and tier definitions, for pickers and help text."""

    return {
        "categories": [
            {
                "id": category.value,
                "label": definition.label,
                "focus": definition.focus,
                "example": definition.example,
                "collection_fit": definition.collection_fit.value,
                "fit_note": definition.fit_note,
                "default_level": definition.default_level.value,
            }
            for category, definition in CATEGORIES.items()
        ],
        "levels": [
            {"id": level.value, "label": d.label, "audience": d.audience, "focus": d.focus}
            for level, d in LEVELS.items()
        ],
    }


def pir_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    """PIR state for the snapshot's active investigation."""

    from pivotglass.core.information_requirements import active_investigation_row

    return build_pir_state(active_investigation_row(snapshot), snapshot)
