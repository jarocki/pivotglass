"""Report elements that are specified but not yet built (#52).

Each entry fixes an element's id, title, provenance, authorities and meaning,
so the 18 report-type definitions can be complete and validated before every
builder exists. The issue named is the one that builds it. A report type that
uses a planned element is listed as planned and cannot be rendered: Pivotglass
never fills a section it cannot build.

When a builder lands it registers with ``@element`` under the same id, and its
entry here is deleted in the same change; ``tests/test_report_types.py``
fails if an id is both planned and built.
"""

from __future__ import annotations

from dataclasses import dataclass

from pivotglass.reports.contract import ProvenanceClass

E = ProvenanceClass.EVIDENCE
M = ProvenanceClass.METHOD
A = ProvenanceClass.ANALYST
D = ProvenanceClass.MODEL_DRAFT
O = ProvenanceClass.ORG_INPUT  # noqa: E741 - one letter, like the others


@dataclass(frozen=True)
class PlannedElement:
    id: str
    title: str
    provenance: tuple[ProvenanceClass, ...]
    authorities: tuple[str, ...]
    description: str
    issue: int


_PLANNED = (
    # --- Domain 3: analytical and attribution (#55) --------------------------
    PlannedElement(
        "key_judgments", "Key judgments", (A, D), ("analytic ledger assertions and hypotheses",),
        "Numbered judgments, each with an ICD 203 likelihood term, a separate confidence level, "
        "the reasoning in one sentence, and citations. Model drafts stay labelled until accepted.", 55,
    ),
    PlannedElement(
        "actor_identity", "Actor identity", (E, A), ("dossier Identity slot", "Nucleotide aliases"),
        "The tracked name, every alias with the organisation that uses it, the MITRE group ID when one "
        "exists, and any sponsorship or origin assessment stated as a judgment, not a fact.", 55,
    ),
    PlannedElement(
        "motivation", "Motivation and objectives", (E, A), ("dossier Motivation slot",),
        "What the actor is trying to achieve (financial, espionage, disruption, ideology), with the "
        "evidence for it and the alternative motivations considered.", 55,
    ),
    PlannedElement(
        "victimology", "Victimology", (E, A), ("dossier Targeting slot",),
        "Targeted sectors, regions, organisation sizes and roles, each with its source and period.", 55,
    ),
    PlannedElement(
        "historical_timeline", "Historical timeline", (E,), ("dossier Timing slot", "observations"),
        "Dated campaigns, tooling changes and disruptions, oldest first, each with a citation.", 55,
    ),
    PlannedElement(
        "arsenal", "Arsenal and tooling", (E,), ("dossier Capability slot", "malware and tool observations"),
        "Custom malware, dual-use and living-off-the-land tools, with first and last observed use.", 55,
    ),
    PlannedElement(
        "infra_opsec", "Infrastructure and OPSEC patterns", (E, M),
        ("registration, hosting, certificate and naming observations",),
        "Repeated choices in registration, hosting, certificates, naming and timing, and the OPSEC "
        "mistakes that make the infrastructure trackable; each pattern names how often it was seen.", 55,
    ),
    PlannedElement(
        "attack_matrix", "ATT&CK techniques and procedures", (E,),
        ("accepted framework mappings", "pinned ATT&CK Enterprise v19.2"),
        "Tactic, technique ID and name, and the observed procedure, from accepted mappings only, "
        "against the pinned ATT&CK release.", 55,
    ),
    PlannedElement(
        "diamond_events", "Diamond events", (E, A), ("Diamond framework projection",),
        "Each event's four vertices (adversary operator and customer, capability and capacity, "
        "type 1 and type 2 infrastructure, victim persona and assets), each with its evidence and "
        "confidence, plus the meta-features: timestamp, phase, result, direction, methodology, "
        "resources, social-political and technology.", 55,
    ),
    PlannedElement(
        "activity_threads", "Activity threads", (E, M), ("Diamond framework projection",),
        "How events connect: the analytic pivot between each pair, whether it is an observed link or "
        "an inference, and the resulting activity group.", 55,
    ),
    PlannedElement(
        "ach_hypotheses", "Competing hypotheses", (A,), ("analytic ledger hypotheses",),
        "The full hypothesis set, always including an unattributed or new actor and a deception "
        "(false-flag) hypothesis, each stated so evidence can be inconsistent with it.", 55,
    ),
    PlannedElement(
        "ach_matrix", "ACH matrix", (A, M), ("analysis_of_competing_hypotheses method runs",),
        "Evidence rows with source rating (Admiralty), diagnosticity, and a consistency score per "
        "hypothesis (CC, C, N, I, II), with the weighted inconsistency tally per hypothesis.", 55,
    ),
    PlannedElement(
        "ach_judgment", "ACH judgment", (A, M), ("analysis_of_competing_hypotheses method runs",),
        "The least-inconsistent hypothesis with likelihood and confidence, why each alternative was "
        "rejected, and a sensitivity check naming the evidence that would change the result if it "
        "were wrong or deceptive.", 55,
    ),
    PlannedElement(
        "signposts", "Signposts", (A,), ("indicators_and_signposts method runs", "signpost lifecycle items"),
        "Observable future developments that would raise or lower a judgment, with who watches for them.", 55,
    ),
    PlannedElement(
        "capability_rubric", "Capability rubric", (M,), ("reports/rubrics",),
        "The axes and the definition of each level 1 to 5 on each axis, so scores are comparable "
        "between actors and analysts.", 55,
    ),
    PlannedElement(
        "capability_radar", "Capability scores", (A,), ("analyst scores against the rubric",),
        "One score per axis with its citations and confidence, rendered as a radar chart and a table.", 55,
    ),
    PlannedElement(
        "defense_benchmark", "Defence benchmark", (O,), ("organisation profile (#59)",),
        "The organisation's self-assessed level on the same axes, shown against the actor's scores. "
        "Absent until supplied; never estimated.", 59,
    ),
    PlannedElement(
        "infra_graph", "Infrastructure graph", (E, M), ("investigation graph", "evidence clusters"),
        "Nodes (type, value, first and last seen, source), edges (relationship, time bounds, evidence, "
        "confidence) and cluster boundaries with the clustering method.", 55,
    ),
    PlannedElement(
        "pivot_points", "Pivot points", (M,), ("investigation graph",),
        "The shared attributes (certificate, registrant, name server, hosting, naming pattern) that "
        "join nodes into clusters, ranked by how many nodes each joins and how distinctive it is.", 55,
    ),
    # --- Domain 2: operational and incident (#54, #58) ------------------------
    PlannedElement(
        "threat_summary", "Threat summary", (D, A), ("cited observations",),
        "Two or three sentences: what is happening, who is targeted, how it arrives, and why it "
        "matters now, with the severity and its confidence.", 54,
    ),
    PlannedElement(
        "delivery_vector", "Delivery and initial access", (E,), ("Initial Access mappings", "observations"),
        "How the activity reaches the target and gains a foothold, with ATT&CK IDs and citations.", 54,
    ),
    PlannedElement(
        "technique_list", "Techniques observed", (E,), ("accepted framework mappings",),
        "ATT&CK technique IDs and names observed in this activity, pinned to v19.2.", 54,
    ),
    PlannedElement(
        "triage_actions", "Triage and containment actions", (M, A), ("IOC-type playbook templates",),
        "Block, search (with a lookback window) and isolate steps generated from the indicator types "
        "present, edited by the analyst, each with an owner.", 54,
    ),
    PlannedElement(
        "detection_pointers", "Detection and hunt pointers", (M,), ("issued reports",),
        "References to issued detection bundles, hunting packages and Navigator layers for this activity.", 54,
    ),
    PlannedElement(
        "campaign_timeline", "Campaign timeline", (E, M), ("observations",),
        "First and last observed activity and the phases in between, computed from sourced observations.", 54,
    ),
    PlannedElement(
        "attack_narrative", "Attack narrative", (D, A), ("collection timeline", "framework mappings"),
        "The intrusion told end to end by phase, each step with ATT&CK IDs and citations; gaps in the "
        "chain are stated, not bridged.", 54,
    ),
    PlannedElement(
        "infrastructure_breakdown", "Infrastructure", (E,), ("ASN, hosting, certificate and passive DNS observations",),
        "Hosting providers and ASNs, certificate traits, resolution history and the role of each "
        "component (delivery, staging, C2, exfiltration).", 54,
    ),
    PlannedElement(
        "recommendations", "Recommendations", (A,), ("analyst",),
        "Numbered actions, each with an owner, a due date, the expected outcome and what it addresses "
        "(a gap, scenario, phase or finding), in priority order.", 54,
    ),
    PlannedElement(
        "vuln_metadata", "Vulnerability metadata", (E,), ("NVD", "EPSS", "CISA KEV"),
        "CVE, CWE, affected products and versions, CVSS score with version and vector, EPSS score with "
        "its date, and KEV status with date added and remediation due date.", 58,
    ),
    PlannedElement(
        "exploitation_status", "Exploitation status", (E,), ("CISA KEV", "CTI feeds"),
        "Whether exploitation is confirmed, suspected or not observed, with the source and date; "
        "whether public exploit code exists; KEV known-ransomware use.", 58,
    ),
    PlannedElement(
        "adversary_adoption", "Adversary adoption", (E, A), ("ThreatFox and OTX tags", "hypotheses"),
        "Which actors or ransomware operations use the vulnerability, each with its source.", 54,
    ),
    PlannedElement(
        "technical_mechanism", "Technical mechanism", (A, D), ("NVD description and references",),
        "The flaw in plain terms and the preconditions an attacker needs (network position, "
        "authentication, configuration).", 54,
    ),
    PlannedElement(
        "patch_guidance", "Patch, mitigation and detection", (E, A), ("NVD references", "vendor advisory"),
        "The fixed versions and advisory, compensating controls if patching is delayed, and the log "
        "artifacts or rules that show exploitation attempts.", 58,
    ),
    PlannedElement(
        "org_exposure", "Organisational exposure", (O, E), ("organisation profile (#59)", "observations"),
        "Whether the organisation's sector and regions are targeted, whether it runs the affected "
        "technology, and the status of the relevant controls. Absent organisation data is shown as "
        "missing, never estimated.", 59,
    ),
    # --- Domain 5: detection, hunting and posture (#57) -----------------------
    PlannedElement(
        "hunt_hypothesis", "Hunt hypothesis", (A,), ("analytic ledger hypotheses",),
        "A testable statement of adversary behaviour in this environment, with the ATT&CK technique "
        "and what result would refute it.", 57,
    ),
    PlannedElement(
        "threat_context", "Threat context", (E, A), ("observations", "actor profiles"),
        "Who uses the behaviour, recently, and why existing alerts may miss it.", 57,
    ),
    PlannedElement(
        "hunt_data_sources", "Required data sources", (M,), ("ATT&CK v19.2 data components",),
        "The data components the techniques need and example log sources for each.", 57,
    ),
    PlannedElement(
        "hunt_queries", "Hunt queries", (M,), ("indicators", "techniques"),
        "SPL, KQL and EQL queries generated from the indicators and techniques, marked untested until "
        "the analyst records a test.", 57,
    ),
    PlannedElement(
        "baseline_false_positives", "Expected baseline and false positives", (A,), ("analyst",),
        "Legitimate activity that matches the queries and how to exclude it without blinding the hunt.", 57,
    ),
    PlannedElement(
        "triage_playbook", "Triage and escalation", (A,), ("analyst",),
        "What to check for each hit and the threshold for escalating to incident response.", 57,
    ),
    PlannedElement(
        "hunt_outcome", "Hunt outcome", (A,), ("analyst",),
        "Whether the hypothesis was supported, refuted or inconclusive, what was found, detections "
        "created, and data gaps that limited the hunt.", 57,
    ),
    PlannedElement(
        "pyramid_of_pain", "Pyramid of Pain", (M,), ("indicator types",),
        "Each indicator and behaviour placed on the Pyramid of Pain, with the response suited to its level.", 57,
    ),
    PlannedElement(
        "sigma_rules", "Sigma rules", (M,), ("indicators", "techniques"),
        "Sigma rules generated from host and process artifacts, status experimental until validated.", 57,
    ),
    PlannedElement(
        "suricata_rules", "Suricata rules", (M,), ("network indicators",),
        "Suricata rules for network artifacts, sid in the local range 1000000-1999999, with metadata "
        "and reference.", 57,
    ),
    PlannedElement(
        "yara_rules", "YARA rules", (A,), ("analyst-supplied strings or sample features",),
        "YARA rules written by the analyst from sample features, with sample hash and reference, "
        "marked untested until validated.", 57,
    ),
    PlannedElement(
        "validation_notes", "Validation", (A,), ("analyst",),
        "For each rule: what it was tested against, the result, and what was not tested.", 57,
    ),
    PlannedElement(
        "technique_scope", "Techniques in scope", (E, M), ("accepted mappings", "actor profiles"),
        "The ATT&CK techniques assessed and why each is in scope (observed, or attributed to an actor "
        "of concern).", 57,
    ),
    PlannedElement(
        "control_matrix", "Control coverage", (O,), ("control inventory (#59)",),
        "Per technique: the primary control, and visibility, alerting and prevention scores (0-2) with "
        "the date and evidence of the last test.", 59,
    ),
    PlannedElement(
        "gap_list", "Coverage gaps", (M,), ("control matrix", "gap rule (reports/contract.py)"),
        "Each technique's gap status derived by the stated rule, critical first.", 57,
    ),
    PlannedElement(
        "emulation_plan", "Adversary emulation plan", (M,), ("pinned Atomic Red Team index",),
        "Per gap, the Atomic Red Team test ID, the telemetry it should produce and the pass criteria.", 57,
    ),
    # --- Domain 1: strategic and executive (#53) ------------------------------
    PlannedElement(
        "bluf", "Bottom line up front", (D, A), ("cited evidence", "key judgments"),
        "At most two sentences: what happened or is expected, whether the organisation is affected, "
        "and the decision leadership must make.", 53,
    ),
    PlannedElement(
        "risk_rating", "Overall risk", (A,), ("analyst",),
        "The overall risk to the organisation on the severity scale, with the reason and the confidence.", 53,
    ),
    PlannedElement(
        "situational_overview", "Situational overview", (D, A), ("cited evidence",),
        "The actor, event or vulnerability in non-technical terms, with what is known and what is not.", 53,
    ),
    PlannedElement(
        "period_scope", "Period and coverage", (M,), ("module runs", "observations"),
        "The reporting window, the sources collected in it and what they cannot see.", 53,
    ),
    PlannedElement(
        "macro_trends", "Macro trends", (A, D, E), ("framework mappings over the period",),
        "Shifts in motivation, initial access and tooling over the period, each supported by counts "
        "or cited cases.", 53,
    ),
    PlannedElement(
        "sector_targeting", "Sector and regional targeting", (O, E), ("organisation profile (#59)", "victimology"),
        "Activity against the organisation's sectors and regions in the period, with sources.", 53,
    ),
    PlannedElement(
        "emerging_ttps", "Emerging techniques", (A, E), ("framework mappings",),
        "Techniques newly observed or rising in the period, with first-seen dates.", 53,
    ),
    PlannedElement(
        "scenarios", "Forward-looking scenarios", (A,), ("analyst", "signposts"),
        "Most likely, worst and best cases for the period ahead, each with an ICD 203 likelihood, "
        "impact on the severity scale, and the signposts that would show it unfolding.", 53,
    ),
    PlannedElement(
        "asset_profile", "Scope and assets", (O,), ("organisation profile (#59)",),
        "What is assessed and its critical assets and data. Absent until supplied; never estimated.", 59,
    ),
    PlannedElement(
        "actor_matrix", "Relevant threat actors", (E, A), ("hypotheses", "Nucleotide aliases", "dossier Capability slot"),
        "Actors relevant to the scope with motivation, intent to target, capability (rubric level) and "
        "cited precedent.", 53,
    ),
    PlannedElement(
        "attack_surface", "Attack surface", (E, O), ("Shodan, Censys and InternetDB observations", "organisation assets (#59)"),
        "Externally visible services and exposures matched to the organisation's assets.", 53,
    ),
    PlannedElement(
        "risk_scenarios", "Risk scenarios", (A,), ("analyst",),
        "Prioritised scenarios, each with likelihood (ICD 203), impact (severity), current control "
        "status, recommended control and residual risk.", 53,
    ),
    # --- Domain 4: attack flow and behavioural (#56) --------------------------
    PlannedElement(
        "kill_chain_table", "Kill chain", (E, O), ("Kill Chain projection", "control status (#59)"),
        "For each of the seven phases: the observed action with citations, ATT&CK IDs, the telemetry "
        "source and the control status from the shared vocabulary.", 56,
    ),
    PlannedElement(
        "navigator_layer", "ATT&CK Navigator layer", (M,), ("accepted mappings", "pinned ATT&CK v19.2"),
        "A layer 4.5 file for Navigator 5.3.2 and ATT&CK 19.2: score is the number of independently "
        "sourced procedures, colour is a single gradient, and each comment carries the procedure and "
        "its citation.", 56,
    ),
    PlannedElement(
        "objective", "Objective", (O,), ("environment model (#59)",),
        "The asset or outcome the attack paths lead to and why it matters.", 59,
    ),
    PlannedElement(
        "attack_tree", "Attack tree", (O, M), ("environment model (#59)",),
        "Paths from entry points to the objective with explicit AND and OR gates; each edge names the "
        "technique, its precondition and whether it is observed or assumed.", 56,
    ),
    PlannedElement(
        "choke_points", "Choke points", (M,), ("attack tree",),
        "Nodes every path (or most paths) must cross, computed from the tree, with the share of paths "
        "each one severs.", 56,
    ),
    PlannedElement(
        "forensic_timeline", "Forensic timeline", (O, M), ("telemetry import (#59)",),
        "Events in UTC: host, telemetry source, ATT&CK technique, summary and a reference to the raw "
        "artifact.", 59,
    ),
    PlannedElement(
        "dwell_metrics", "Dwell and response times", (M,), ("forensic timeline",),
        "First malicious event, detection, containment, and the dwell and response intervals computed "
        "from them.", 56,
    ),
)

PLANNED: dict[str, PlannedElement] = {item.id: item for item in _PLANNED}
if len(PLANNED) != len(_PLANNED):  # pragma: no cover - guards the table above
    raise RuntimeError("a planned report element is declared twice")
