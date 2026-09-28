"""Deterministic, evidence-safe teaching cards for enrichment latency."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnrichmentBriefing:
    """Operator-facing explanation of one enrichment tool's analytical role."""

    source: str
    artifacts: str
    purpose: str
    watch_for: str


BRIEFINGS: dict[str, EnrichmentBriefing] = {
    "virustotal_lookup": EnrichmentBriefing(
        "VirusTotal", "vendor detections, submission history, relationships, and community context",
        "Corroborates reputation and exposes linked infrastructure or files.",
        "agreement across independent engines, first/last-seen dates, and useful relations",
    ),
    "otx_threat_intel": EnrichmentBriefing(
        "AlienVault OTX", "pulse membership, tags, references, related indicators, and observation dates",
        "Connects the indicator to community-described campaigns and threat context.",
        "named campaigns, recurring tags, recent sightings, and referenced pivots",
    ),
    "passivetotal_lookup": EnrichmentBriefing(
        "PassiveTotal", "passive-DNS history, co-hosted records, registration context, and temporal links",
        "Reconstructs infrastructure changes without querying DNS from the operator host.",
        "short-lived resolutions, shared infrastructure, and campaign-time changes",
    ),
    "scan_url": EnrichmentBriefing(
        "URLScan", "page requests, redirects, contacted hosts, certificates, screenshots, and technologies",
        "Shows what a browser observed and reveals infrastructure loaded behind a URL.",
        "redirect chains, unexpected third parties, distinctive assets, and contacted domains",
    ),
    "censys_host_lookup": EnrichmentBriefing(
        "Censys", "internet scan observations, services, banners, certificates, and exposure timestamps",
        "Fingerprints externally visible infrastructure from a maintained scan corpus.",
        "rare banners, certificate reuse, unexpected ports, and observation recency",
    ),
    "shodan_host_lookup": EnrichmentBriefing(
        "Shodan", "ports, service banners, products, vulnerabilities, hostnames, and scan timestamps",
        "Builds an exposure profile and suggests service- or certificate-based pivots.",
        "administrative interfaces, obsolete software, unusual services, and stale observations",
    ),
    "check_ip_reputation": EnrichmentBriefing(
        "AbuseIPDB", "abuse confidence, report categories, reporter volume, ISP, and usage type",
        "Adds crowd-reported abuse context while distinguishing reports from direct evidence.",
        "report recency, category consistency, reporter diversity, and shared-hosting caveats",
    ),
    "greynoise_lookup": EnrichmentBriefing(
        "GreyNoise", "internet-scanner classification, actor or tool labels, tags, and observation recency",
        "Separates common background scanning from activity deserving deeper attention.",
        "benign-service labels, spoofability, classification confidence, and last-seen time",
    ),
    "crtsh_lookup": EnrichmentBriefing(
        "Certificate Transparency", "certificate names, issuers, serials, validity windows, and logged subdomains",
        "Finds certificate-backed names and relationships without resolving them.",
        "wildcards, uncommon sibling names, certificate reuse, and issuance timing",
    ),
    "whois_lookup": EnrichmentBriefing(
        "WHOIS", "registrar, registration dates, nameservers, status codes, and redacted ownership fields",
        "Establishes registration chronology and administrative context.",
        "recent creation, registrar changes, unusual status codes, and privacy limitations",
    ),
    "check_breaches": EnrichmentBriefing(
        "Have I Been Pwned", "breach names, exposure dates, compromised data classes, and verification status",
        "Assesses identity exposure without treating breach presence as malicious behavior.",
        "credential exposure, breach chronology, sensitive data classes, and identity ambiguity",
    ),
    "urlhaus_lookup": EnrichmentBriefing(
        "URLhaus", "malware URL status, payload associations, tags, reporters, and timestamps",
        "Tests whether a URL is tied to observed malware delivery infrastructure.",
        "payload hashes, malware families, takedown state, and first/last-seen timing",
    ),
    "threatfox_lookup": EnrichmentBriefing(
        "ThreatFox", "malware-family associations, indicator types, confidence, tags, and sightings",
        "Links indicators to community-curated malware and command-and-control observations.",
        "confidence, family consistency, recent sightings, and corroborating references",
    ),
    "malwarebazaar_lookup": EnrichmentBriefing(
        "MalwareBazaar", "sample hashes, file metadata, signatures, tags, delivery context, and family labels",
        "Enriches a file indicator and exposes related samples for cluster analysis.",
        "signature agreement, family clusters, delivery method, and sample recency",
    ),
}


def render_briefing(tool_name: str, target: str) -> str:
    """Render a learning card without claiming a result before it arrives."""
    briefing = BRIEFINGS.get(tool_name)
    if briefing is None:
        return (
            "SOURCE  deterministic tool/API\n"
            f"TARGET  {target}\n"
            "GATHER  source-specific artifacts for evidence-backed pivots\n"
            "WHY     Adds independently attributable context to the investigation.\n"
            "WATCH   provenance, timestamps, confidence, and useful relationships\n"
            "STATE   querying — findings are not assumed until the service responds"
        )
    return (
        f"SOURCE  {briefing.source}\nTARGET  {target}\n"
        f"GATHER  {briefing.artifacts}\nWHY     {briefing.purpose}\n"
        f"WATCH   {briefing.watch_for}\n"
        "STATE   querying — findings are not assumed until the service responds"
    )
