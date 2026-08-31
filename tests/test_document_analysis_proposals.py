"""Span-grounded proposal and human-disposition authority."""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import inspect, select
from stix2 import DomainName

from adversary_pursuit.core.analytic_ledger import ConfidenceLevel
from adversary_pursuit.core.document_analysis_proposals import (
    DocumentAnalysisProposalAuthority,
)
from adversary_pursuit.core.document_entity_extraction import (
    DocumentEntityExtractionService,
)
from adversary_pursuit.core.document_ingestion import DocumentIntakeService
from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.models.database import (
    DocumentAnalysisProposal,
    DocumentProposalDisposition,
)


def _workspace(tmp_path):
    manager = WorkspaceManager(tmp_path)
    manager.create("proposals")
    manager.switch("proposals")
    return manager


def _candidates(manager):
    intake = DocumentIntakeService(manager).store_bytes(
        b"The report links alpha.example to 198.51.100.7 using a new loader behavior.",
        filename="report.txt",
        operator="analyst",
    )
    return DocumentEntityExtractionService(manager).extract_parser_receipt(
        intake.parser_receipt_id
    ).candidates


def test_behavior_proposal_cites_exact_spans_and_unmatched_is_not_a_new_ttp(tmp_path) -> None:
    manager = _workspace(tmp_path)
    candidates = _candidates(manager)
    authority = DocumentAnalysisProposalAuthority(manager)

    proposal = authority.propose(
        proposal_kind="behavior",
        statement="The source may describe a loader persistence behavior.",
        candidate_ids=tuple(item.id for item in candidates),
        payload={"behavior": "Loader persists through an unspecified mechanism."},
        proposed_by="model",
        model_provider="test-provider",
        model_id="test-model",
        prompt_sha256="a" * 64,
        response_sha256="b" * 64,
    )

    assert proposal.framework_comparison["state"] == "unmatched_candidate_behavior"
    assert "not an automatically discovered TTP" in proposal.framework_comparison["caveat"]
    assert proposal.source_spans[0]["parser_receipt_id"]
    assert proposal.source_spans[0]["start_byte"] >= 0
    assert "not observed content" in proposal.truth_boundary
    assert manager.get_workspace_table_counts()["stix_objects"] == 0
    assert manager.get_workspace_table_counts()["relationships"] == 0


def test_attack_reference_is_syntax_checked_but_not_claimed_as_verified(tmp_path) -> None:
    manager = _workspace(tmp_path)
    candidate = _candidates(manager)[0]
    authority = DocumentAnalysisProposalAuthority(manager)

    proposal = authority.propose(
        proposal_kind="behavior",
        statement="Candidate behavior may align with acquired infrastructure.",
        candidate_ids=(candidate.id,),
        payload={"behavior": "Acquire a domain", "attack_candidates": ["T1583.001"]},
        proposed_by="human",
    )

    match = proposal.framework_comparison["matches"][0]
    assert match["content_id"] == "T1583.001"
    assert match["state"] == "unverified_candidate_reference"
    with pytest.raises(ValueError, match="Invalid ATT&CK"):
        authority.propose(
            proposal_kind="behavior",
            statement="Invalid model reference must fail.",
            candidate_ids=(candidate.id,),
            payload={"behavior": "Unknown", "attack_candidates": ["NOT-A-TECHNIQUE"]},
            proposed_by="tool",
        )


def test_model_receipt_and_relationship_citations_are_required(tmp_path) -> None:
    manager = _workspace(tmp_path)
    candidates = _candidates(manager)
    authority = DocumentAnalysisProposalAuthority(manager)

    with pytest.raises(ValueError, match="provider and model ID"):
        authority.propose(
            proposal_kind="entity",
            statement="Model proposal without a receipt.",
            candidate_ids=(candidates[0].id,),
            payload={},
            proposed_by="model",
        )
    with pytest.raises(ValueError, match="two distinct cited candidates"):
        authority.propose(
            proposal_kind="relationship",
            statement="Unsupported single-candidate relationship.",
            candidate_ids=(candidates[0].id,),
            payload={
                "source_candidate_id": candidates[0].id,
                "target_candidate_id": candidates[0].id,
                "relationship": "related-to",
                "rationale": "One string cannot establish two endpoints.",
            },
            proposed_by="human",
        )


def test_acceptance_requires_human_evidence_alternatives_and_formal_confidence(tmp_path) -> None:
    manager = _workspace(tmp_path)
    candidate = _candidates(manager)[0]
    authority = DocumentAnalysisProposalAuthority(manager)
    proposal = authority.propose(
        proposal_kind="entity",
        statement="The domain is relevant to this investigation.",
        candidate_ids=(candidate.id,),
        payload={"role": "candidate infrastructure"},
        proposed_by="tool",
    )

    with pytest.raises(ValueError, match="explicit human action"):
        authority.review(
            proposal.id,
            decision="accepted",
            decided_by="model",
            reason="The model agrees.",
            human_decision=False,
        )
    with pytest.raises(ValueError, match="admitted evidence"):
        authority.review(
            proposal.id,
            decision="accepted",
            decided_by="analyst",
            reason="Ready for assessment.",
            human_decision=True,
        )

    domain = DomainName(value="alpha.example")
    manager.store_stix_objects([domain], module_name="source/admitted", target=domain.value)
    evidence_id = next(
        item["id"] for item in manager.get_observations() if item["entity_ref"] == domain.id
    )
    reviewed = authority.review(
        proposal.id,
        decision="accepted",
        decided_by="analyst",
        reason="Cited evidence and a shared-hosting alternative were reviewed.",
        human_decision=True,
        evidence_refs=(evidence_id,),
        alternative_explanations=("The domain may be unrelated text or shared infrastructure.",),
        confidence_level=ConfidenceLevel.LOW,
        confidence_rationale="One admitted observation and one source document.",
    )

    assert reviewed.latest_disposition is not None
    assert reviewed.latest_disposition.decision == "accepted"
    assert reviewed.latest_disposition.confidence_level == ConfidenceLevel.LOW
    assert manager.get_workspace_table_counts()["relationships"] == 0


def test_proposals_are_idempotent_and_dispositions_are_append_only(tmp_path) -> None:
    manager = _workspace(tmp_path)
    candidate = _candidates(manager)[0]
    authority = DocumentAnalysisProposalAuthority(manager)
    kwargs = {
        "proposal_kind": "entity",
        "statement": "Review this entity candidate.",
        "candidate_ids": (candidate.id,),
        "payload": {"role": "unknown"},
        "proposed_by": "human",
    }
    first = authority.propose(**kwargs)
    second = authority.propose(**kwargs)
    authority.review(
        first.id,
        decision="rejected",
        decided_by="analyst",
        reason="The text is an example rather than case evidence.",
        human_decision=True,
    )
    authority.review(
        first.id,
        decision="revised",
        decided_by="analyst",
        reason="Retain only as a training example.",
        human_decision=True,
    )

    assert first.id == second.id
    with manager.get_session() as session:
        assert len(session.execute(select(DocumentAnalysisProposal)).scalars().all()) == 1
        assert len(session.execute(select(DocumentProposalDisposition)).scalars().all()) == 2


def test_schema_v10_migrates_proposal_tables_backup_first(tmp_path) -> None:
    manager = _workspace(tmp_path)
    manager._engine.dispose()
    manager._engine = None
    manager._active = None
    db_path = tmp_path / "proposals.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP TABLE document_proposal_dispositions")
        connection.execute("DROP TABLE document_analysis_proposals")
        connection.execute("UPDATE workspace_schema_version SET version = 10 WHERE id = 1")

    migrated = WorkspaceManager(tmp_path)
    migrated.switch("proposals")
    tables = set(inspect(migrated._engine).get_table_names())
    assert {"document_analysis_proposals", "document_proposal_dispositions"} <= tables
    assert migrated.get_workspace_schema_status()["to_version"] == 11
    assert (tmp_path / "proposals.db.pre-v10-backup").is_file()
