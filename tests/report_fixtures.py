"""A rich, deterministic workspace for report tests (#50).

Shared by the golden test of the ``investigation-report`` type and by the
report-type tests. Values are illustrative and reserved where they are
indicators (RFC 2606 / RFC 5737 / RFC 3849).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from pivotglass.core.workspace import WorkspaceManager


def build_rich_workspace(root: Path, name: str = "case") -> WorkspaceManager:
    from pivotglass.core.analytic_ledger import (
        AnalyticLedger,
        AssertionType,
        ConfidenceLevel,
        LifecycleItemType,
        LikelihoodTerm,
        Materiality,
    )
    from pivotglass.core.structured_analysis import StructuredAnalysisWorkbench, StructuredTechnique
    from pivotglass.dossier.predictions import create_prediction, save_predictions_log
    from pivotglass.dossier.slot_inference import infer_dossier_state_full
    from pivotglass.dossier.state import save_dossier_state

    wm = WorkspaceManager(workspace_dir=root / "workspaces")
    wm.create(name)
    wm.switch(name)
    wm.store_stix_objects(
        [
            {"type": "email-addr", "value": "operator@mail.example"},
            {"type": "url", "value": "https://login.example.com/c2"},
            {"type": "ipv4-addr", "value": "192.0.2.44"},
            {"type": "domain-name", "value": "c2.example.net"},
            {"type": "ipv6-addr", "value": "2001:db8::44"},
            {"type": "file", "name": "loader.bin", "hashes": {"SHA-256": "a" * 64}},
        ],
        module_name="osint/whois_lookup",
        target="c2.example.net",
    )
    wm.store_score_events(
        [
            {"action": "new_ip", "points": 100, "indicator": "192.0.2.44"},
            {"action": "new_domain", "points": 200, "indicator": "c2.example.net"},
        ]
    )
    save_dossier_state(
        wm, infer_dossier_state_full(wm.get_stix_objects(), module_runs=wm.get_module_runs(), notes=[])
    )
    first = create_prediction("infrastructure", "Actor will reuse .example infrastructure", {"sco_type": "domain-name"})
    second = create_prediction("identity", "Actor uses targeted spearphishing", {"sco_type": "email-addr"})
    save_predictions_log(wm, [replace(first, status="validated", validated_at="2026-06-08T10:00:00"), second])
    wm.add_note("Certificate overlap with a prior cluster")
    wm.add_note("Hosting looks like a single reseller")

    ledger = AnalyticLedger(wm)
    question_id = ledger.create_question("Who controls the observed infrastructure?")
    investigation_id = ledger.active_investigation()["id"]
    ledger.set_requirement("threat_actor_campaign", "operational", investigation_id=investigation_id)
    hypothesis_id = ledger.create_hypothesis(question_id, "A common operator controls the infrastructure.")
    ledger.create_hypothesis(question_id, "Unrelated tenants share a hosting reseller.")
    assumption_id = ledger.create_assertion(
        "Certificate reuse implies common control.", assertion_type=AssertionType.ASSUMED
    )
    alternative_id = ledger.create_assertion(
        "The certificate was supplied by shared hosting.", assertion_type=AssertionType.JUDGMENT
    )
    ledger.assess_confidence(
        target_kind="hypothesis",
        target_id=hypothesis_id,
        level=ConfidenceLevel.LOW,
        rationale="The current evidence comes from one source.",
        factors={
            "source_quality": "one API source with direct access",
            "source_independence": "one dependence group",
            "corroboration": "not corroborated",
            "assumptions": ["certificate reuse implies control"],
            "knowledge_gaps": ["hosting allocation unavailable"],
            "analytic_rigor": "competing explanation retained",
        },
    )
    ledger.assess_likelihood(
        target_kind="hypothesis",
        target_id=hypothesis_id,
        term=LikelihoodTerm.ROUGHLY_EVEN_CHANCE,
        rationale="Both explanations remain plausible.",
    )
    ledger.add_lifecycle_item(
        investigation_id, LifecycleItemType.PREDICTION, "An independently sourced certificate match will appear."
    )
    ledger.add_lifecycle_item(
        investigation_id, LifecycleItemType.KNOWLEDGE_GAP, "Contemporaneous hosting allocation records are unavailable."
    )
    ledger.add_lifecycle_item(
        investigation_id, LifecycleItemType.LIMITATION, "Only one passive DNS provider was queried."
    )
    ledger.record_contradiction(
        left_kind="assertion",
        left_id=assumption_id,
        right_kind="assertion",
        right_id=alternative_id,
        summary="Common control and shared hosting are competing explanations.",
        materiality=Materiality.HIGH,
        resolution_required="Obtain contemporaneous allocation records.",
    )
    workbench = StructuredAnalysisWorkbench(wm)
    run = workbench.start(
        question_id, StructuredTechnique.KEY_ASSUMPTIONS, {"assumptions": ["Shared hosting implies control."]}
    )
    workbench.complete(
        run,
        {
            "challenged_assumptions": ["No exclusive control observed. ``` Close?"],
            "implications": ["Collect independent tenancy evidence."],
        },
    )
    return wm


ACTOR = "actor:Example-Spider"


def build_analytical_workspace(root: Path, name: str = "case") -> WorkspaceManager:
    """The rich workspace plus what domain-3 reports read: actor claims, mappings, ACH links, signposts."""

    from pivotglass.core.analytic_ledger import (
        AnalyticLedger,
        AssertionType,
        ConfidenceLevel,
        EvidenceStance,
        LifecycleItemType,
        LikelihoodTerm,
    )
    from pivotglass.core.framework_projections import (
        Framework,
        FrameworkProjectionAuthority,
        MappingOrigin,
        MappingState,
    )

    wm = build_rich_workspace(root, name)
    wm.store_stix_objects(
        [
            {"type": "domain-name", "value": "cdn.example.net", "ip": "192.0.2.44", "registrar": "Example Registrar"},
            {"type": "domain-name", "value": "mail.example.net", "ip": "192.0.2.44", "registrar": "Example Registrar"},
        ],
        module_name="osint/passive_dns",
        target="192.0.2.44",
    )
    ledger = AnalyticLedger(wm)
    obs = {o["entity_value"]: o["id"] for o in wm.get_observations()}

    def claim(predicate: str, value: str, statement: str, *, cite: str | None = None, kind=AssertionType.JUDGMENT) -> str:
        assertion = ledger.create_assertion(statement, assertion_type=kind, subject_ref=ACTOR, predicate=predicate, object_value=value)
        if cite:
            ledger.link_evidence(source_kind="observation", source_id=obs[cite], target_kind="assertion", target_id=assertion,
                                 stance=EvidenceStance.SUPPORTS, rationale="cited in the claim")
        return assertion

    claim("alias", "Example Spider", "Name used by Vendor A in its public reporting.", cite="c2.example.net")
    claim("mitre-group", "G9999", "Illustrative group ID for the fixture.")
    origin = claim("origin", "unknown-state", "Operations align with one state's working hours.", cite="c2.example.net")
    ledger.assess_likelihood(target_kind="assertion", target_id=origin, term=LikelihoodTerm.UNLIKELY, rationale="Timing only.")
    claim("motivation", "financial", "Ransom notes and a leak site.", cite="https://login.example.com/c2")
    claim("targets-sector", "healthcare", "Two victims in hospital groups.", cite="operator@mail.example")
    claim("targets-region", "Western Europe", "Victims in two EU states.", cite="operator@mail.example")
    claim("campaign", "2026-03", "First observed loader campaign.", cite="c2.example.net")
    claim("uses-malware", "ExampleLoader", "Custom loader seen in both intrusions.", cite="c2.example.net")
    claim("uses-tool", "rclone", "Used for exfiltration.")
    for axis, score in (("access", 3), ("malware", 4), ("evasion", 3)):
        scored = claim(f"capability:{axis}", str(score), f"{axis} assessed from the loader analysis.", cite="c2.example.net")
        ledger.assess_confidence(
            target_kind="assertion", target_id=scored, level=ConfidenceLevel.MODERATE, rationale="One analysed sample.",
            factors={"source_quality": "sample", "source_independence": "one", "corroboration": "none",
                     "assumptions": [], "knowledge_gaps": [], "analytic_rigor": "rubric"},
        )

    hypotheses = {row["statement"]: row["id"] for row in ledger.snapshot()["hypotheses"]}
    common, tenants = hypotheses["A common operator controls the infrastructure."], hypotheses["Unrelated tenants share a hosting reseller."]
    question = ledger.snapshot()["questions"][0]["id"]
    deception = ledger.create_hypothesis(question, "Another actor staged the overlap as a false flag.")
    for value, target, stance in (
        ("c2.example.net", common, EvidenceStance.SUPPORTS),
        ("c2.example.net", tenants, EvidenceStance.CONTRADICTS),
        ("192.0.2.44", common, EvidenceStance.SUPPORTS),
        ("192.0.2.44", tenants, EvidenceStance.SUPPORTS),
        ("192.0.2.44", deception, EvidenceStance.SUPPORTS),
        ("operator@mail.example", deception, EvidenceStance.CONTRADICTS),
    ):
        ledger.link_evidence(source_kind="observation", source_id=obs[value], target_kind="hypothesis", target_id=target,
                             stance=stance, rationale="fixture link")
    investigation = ledger.active_investigation()["id"]
    ledger.add_lifecycle_item(investigation, LifecycleItemType.SIGNPOST, "The same certificate appears on a new host.")

    authority = FrameworkProjectionAuthority(wm)

    def mapping(framework, version, content_id, label, refs, basis):
        m = authority.propose(
            framework=framework, framework_version=version, content_id=content_id, content_label=label,
            evidence_refs=refs, basis=basis, mapper="fixture", mapper_version="1", origin=MappingOrigin.HUMAN,
            confidence=ConfidenceLevel.MODERATE, confidence_rationale="fixture",
        )
        authority.disposition(m.id, MappingState.ACCEPTED)

    mapping(Framework.ATTACK, "19.2", "T1071.001", "Web Protocols", [obs["https://login.example.com/c2"]], "HTTPS beacon to the C2 URL.")
    mapping(Framework.KILL_CHAIN, "lockheed-martin-2011", "command-and-control", "Command and Control", [obs["c2.example.net"]], "C2 domain.")
    for vertex, value, ref in (
        ("infrastructure", "c2.example.net", "c2.example.net"),
        ("adversary", "Example Spider", "c2.example.net"),
        ("infrastructure", "192.0.2.44", "192.0.2.44"),
        ("victim", "hospital-group", "192.0.2.44"),
    ):
        mapping(Framework.DIAMOND, "diamond-model-1.0", f"diamond:{vertex}:{value}", vertex, [obs[ref]], f"{vertex} from {ref}")
    return wm


def build_operational_workspace(root: Path, name: str = "case") -> WorkspaceManager:
    """The analytical workspace plus what alerts and campaign reports read."""

    from pivotglass.core.analytic_ledger import AnalyticLedger, ConfidenceLevel
    from pivotglass.core.framework_projections import (
        Framework,
        FrameworkProjectionAuthority,
        MappingOrigin,
        MappingState,
    )
    from pivotglass.core.indicator_tags import IndicatorTagAuthority
    from pivotglass.reports.commands import execute_report_command

    wm = build_analytical_workspace(root, name)
    wm.store_stix_objects(
        [{"type": "domain-name", "value": "drop.example.org", "first_seen": "2026-10-01", "last_seen": "2026-11-15",
          "as_name": "Example Hosting"}],
        module_name="cti/threatfox",
        target="drop.example.org",
    )
    IndicatorTagAuthority(wm).apply(
        [
            {"dimension": "role", "entity_type": "domain-name", "normalized_value": "c2.example.net", "value": "c2"},
            {"dimension": "role", "entity_type": "url", "normalized_value": "https://login.example.com/c2", "value": "delivery"},
            {"dimension": "role", "entity_type": "email-addr", "normalized_value": "operator@mail.example", "value": "victim"},
        ],
        operator="fixture",
    )
    for command in (
        "write threat_summary | An operator is phishing hospital groups and beaconing over HTTPS to one C2 domain.",
        "severity high | Active against our sector; no patch needed, only blocking.",
        "write attack_narrative | Phishing delivered a link; the loader then beaconed to the C2 domain.",
        "recommend 1 | Block the C2 domain and URL | SOC | 2026-12-01 | No further beacons",
        "recommend 2 | Hunt for the loader hash | Threat hunting | 2026-12-08 | Infected hosts found or ruled out",
    ):
        execute_report_command(command, wm)
    obs = {o["entity_value"]: o["id"] for o in wm.get_observations()}
    authority = FrameworkProjectionAuthority(wm)
    m = authority.propose(
        framework=Framework.KILL_CHAIN, framework_version="lockheed-martin-2011", content_id="delivery",
        content_label="Delivery", evidence_refs=[obs["https://login.example.com/c2"]], basis="Phishing link to the login URL.",
        mapper="fixture", mapper_version="1", origin=MappingOrigin.HUMAN, confidence=ConfidenceLevel.MODERATE,
        confidence_rationale="fixture",
    )
    authority.disposition(m.id, MappingState.ACCEPTED)
    AnalyticLedger(wm)  # ledger unchanged otherwise
    return wm


SAMPLE_SHA256 = "a" * 64


def build_detection_workspace(root: Path, name: str = "case") -> WorkspaceManager:
    """The operational workspace plus hunt text, sample strings for YARA, and one validation."""

    from pivotglass.reports.commands import execute_report_command

    wm = build_operational_workspace(root, name)
    for command in (
        "write hunt_hypothesis | Hosts beacon over HTTPS to the C2 domain (T1071.001); no DNS answers for it in 30 days refutes it.",
        "write baseline_false_positives | Shared CDN addresses also serve legitimate sites; match on the domain, not the address.",
        "write triage_playbook | Check the process that resolved the domain; escalate any unsigned process to incident response.",
        f"yara {SAMPLE_SHA256} | https://sandbox.example/report/1 | Global\\ExampleMutex; /api/v2/checkin?build=; ExampleLoader.pdb",
    ):
        execute_report_command(command, wm)
    return wm


ORG_FIXTURES = Path(__file__).parent / "fixtures" / "reports"


def build_behavioral_workspace(root: Path, name: str = "case") -> WorkspaceManager:
    """The operational workspace plus organisation input and kill-chain control records."""

    from pivotglass.reports.commands import execute_report_command
    from pivotglass.reports.org import execute_org_command

    wm = build_operational_workspace(root, name)
    execute_org_command(f"import {ORG_FIXTURES / 'org.yaml'}", wm)
    execute_org_command(f"telemetry {ORG_FIXTURES / 'telemetry.csv'}", wm)
    execute_report_command("control delivery detected | Mail gateway alert; message still delivered", wm)
    execute_report_command("control command-and-control blocked | Proxy blocked the second beacon", wm)
    return wm


def build_strategic_workspace(root: Path, name: str = "case") -> WorkspaceManager:
    """The behavioural workspace plus strategic judgments, scenarios, intent and an exposed owned asset."""

    from pivotglass.core.analytic_ledger import AnalyticLedger, AssertionType
    from pivotglass.reports.commands import execute_report_command

    wm = build_behavioral_workspace(root, name)
    wm.store_stix_objects(
        [{"type": "ipv4-addr", "value": "198.51.100.5", "x_internetdb_ports": [443, 8443], "x_internetdb_vulns": ["CVE-2024-0001"]}],
        module_name="osint/shodan_internetdb", target="198.51.100.5",
    )
    AnalyticLedger(wm).create_assertion(
        "Named our parent company in a leak-site post.", assertion_type=AssertionType.JUDGMENT,
        subject_ref=ACTOR, predicate="intent", object_value="high",
    )
    for command in (
        "write bluf | An actor targeting hospital groups is exploiting our VPN gateway version. Approve emergency patching tonight.",
        "write situational_overview | A financially motivated actor is phishing hospital staff and exploiting edge gateways.",
        "write macro_trends | Edge-device exploitation overtook phishing as the first step in the healthcare cases seen.",
        "write period_scope | 1 October to 26 November 2026; healthcare sector; our own collection only.",
        "risk high moderate | Our gateway version is affected and the actor targets our sector.",
        "scenario most-likely likely high | The actor exploits an unpatched gateway within the quarter. | New scans of our VPN range",
        "scenario worst unlikely critical | Ransomware across clinical systems. | Domain admin logons from the jump host",
        "scenario best roughly_even_chance low | Patching closes the gateway route first. | Gateway at 9.1.2 everywhere",
        "risk-scenario likely critical missed | Gateway exploit leads to ERP access | Patch and segment the jump host | Medium",
    ):
        execute_report_command(command, wm)
    return wm
