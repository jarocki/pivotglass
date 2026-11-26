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
