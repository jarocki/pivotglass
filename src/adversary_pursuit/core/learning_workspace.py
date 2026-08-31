"""Deterministic, offline investigation fixture for the no-key learning path.

The fixture exercises Pivotglass's real evidence and analytic authorities.  It
never calls a provider, model, or network service, and every value is reserved
for documentation or testing.  Synthetic observations remain visibly distinct
from hypotheses and assertions in the analytic ledger.

@decision DEC-LEARNING-WORKSPACE-001
@title The learning path is a real, explicitly synthetic workspace
@status accepted
@rationale A canned UI tour cannot prove persistence, provenance, graph, export,
           or recovery behavior.  A bounded offline fixture can exercise those
           authorities without API keys or claims about real infrastructure.
"""

from __future__ import annotations

import hashlib
from typing import Any

from stix2 import URL, DomainName, File, IPv4Address, Relationship

from adversary_pursuit.core.analytic_ledger import (
    AnalyticLedger,
    AssertionType,
    AuthorKind,
    ConfidenceLevel,
    EvidenceStance,
    InvestigationStatus,
    LifecycleItemType,
    LikelihoodTerm,
    Materiality,
)

LEARNING_TARGET = "beacon-check.example"
LEARNING_FETCHED_AT = "2026-01-15T03:14:15Z"
LEARNING_MARKING = "TLP:CLEAR // SYNTHETIC TRAINING DATA"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _relationship(
    relationship_id: str,
    source_ref: str,
    target_ref: str,
    relationship_type: str,
) -> Relationship:
    return Relationship(
        id=relationship_id,
        source_ref=source_ref,
        target_ref=target_ref,
        relationship_type=relationship_type,
        created=LEARNING_FETCHED_AT,
        modified=LEARNING_FETCHED_AT,
    )


def create_learning_workspace(manager: Any, name: str) -> dict[str, Any]:
    """Create and activate one complete, offline learning investigation.

    The name must be new.  On failure the partially created workspace is
    removed and the previously active workspace is restored.
    """

    previous = getattr(manager, "_active", None)
    manager.create(name)
    try:
        manager.switch(name)

        domain = DomainName(value=LEARNING_TARGET)
        address = IPv4Address(value="198.51.100.42")
        sample = File(
            hashes={"SHA-256": "2f9fda9b7f2f8fbe17dfd11b5e47d351dcbcc7b11f22ce776e173f32526b938d"},
            name="invoice-viewer.bin",
        )
        landing = URL(value=f"https://{LEARNING_TARGET}/account/verify")

        resolves = _relationship(
            "relationship--1069d44e-9270-4a69-87d7-79d7519fe94c",
            domain.id,
            address.id,
            "resolves-to",
        )
        contacts = _relationship(
            "relationship--20f59960-9221-4c8e-849d-cbb45abb441b",
            sample.id,
            domain.id,
            "communicates-with",
        )
        hosts = _relationship(
            "relationship--3ae78310-a1d6-4e1c-b836-2bdf7a84860a",
            domain.id,
            landing.id,
            "hosts",
        )

        source_a = "pivotglass-learning-source-a-v1"
        source_b = "pivotglass-learning-source-b-v1"
        manager.store_stix_objects(
            [domain, address, resolves, landing, hosts],
            module_name="learning/source-a",
            target=LEARNING_TARGET,
            response_sha256=_digest(source_a),
            fetched_at=LEARNING_FETCHED_AT,
            collector_version="pivotglass-learning-v1",
            response_media_type="application/vnd.pivotglass.learning+json",
            handling_marking=LEARNING_MARKING,
            transformation_id="learning-fixture-v1",
            raw_artifact_ref=f"artifact://sha256/{_digest(source_a)}",
            source_dependence_group="synthetic-source-a",
        )
        manager.store_stix_objects(
            [domain, sample, contacts],
            module_name="learning/source-b",
            target=LEARNING_TARGET,
            response_sha256=_digest(source_b),
            fetched_at="2026-01-15T03:19:15Z",
            collector_version="pivotglass-learning-v1",
            response_media_type="application/vnd.pivotglass.learning+json",
            handling_marking=LEARNING_MARKING,
            transformation_id="learning-fixture-v1",
            raw_artifact_ref=f"artifact://sha256/{_digest(source_b)}",
            source_dependence_group="synthetic-source-b",
        )

        observations = manager.get_observations()
        observation_by_ref: dict[str, list[str]] = {}
        for observation in observations:
            observation_by_ref.setdefault(str(observation["entity_ref"]), []).append(
                str(observation["id"])
            )

        ledger = AnalyticLedger(manager)
        investigation_id = ledger.create_investigation(
            "Offline infrastructure-reuse learning case",
            purpose=(
                "Practice a source-grounded assessment of whether observed infrastructure "
                "reuse supports common control."
            ),
            scope=(
                "Reserved synthetic domain, address, URL, file, and relationships supplied "
                "by the local Pivotglass learning fixture."
            ),
            created_by=AuthorKind.SYSTEM,
        )
        question_id = ledger.create_question(
            "Does the observed reuse indicate one operator or shared infrastructure?",
            created_by=AuthorKind.SYSTEM,
            investigation_id=investigation_id,
        )
        common_control = ledger.create_hypothesis(
            question_id,
            "One operator controls the observed file, domain, URL, and address cluster.",
            author_kind=AuthorKind.SYSTEM,
        )
        shared_service = ledger.create_hypothesis(
            question_id,
            "The observed overlap is explained by shared or repurposed infrastructure.",
            author_kind=AuthorKind.SYSTEM,
        )

        reuse_assertion = ledger.create_assertion(
            "Two independent synthetic sources observed the same domain in the training window.",
            assertion_type=AssertionType.INFERRED,
            author_kind=AuthorKind.SYSTEM,
            subject_ref=domain.id,
            predicate="independently-observed-by",
            object_value="2 synthetic source groups",
            method="deterministic-observation-count",
            investigation_id=investigation_id,
        )
        cluster_assertion = ledger.create_assertion(
            "The synthetic relationship records connect the file, domain, URL, and address.",
            assertion_type=AssertionType.INFERRED,
            author_kind=AuthorKind.SYSTEM,
            subject_ref=domain.id,
            predicate="appears-in-connected-cluster",
            object_value="file, URL, and IPv4 address",
            method="persisted-relationship-traversal",
            investigation_id=investigation_id,
        )

        for observation_id in observation_by_ref[domain.id]:
            ledger.link_evidence(
                source_kind="observation",
                source_id=observation_id,
                target_kind="assertion",
                target_id=reuse_assertion,
                stance=EvidenceStance.SUPPORTS,
                rationale="This immutable observation records the domain under one source group.",
            )
        for relationship in (resolves, contacts, hosts):
            ledger.link_evidence(
                source_kind="observation",
                source_id=observation_by_ref[relationship.id][0],
                target_kind="assertion",
                target_id=cluster_assertion,
                stance=EvidenceStance.SUPPORTS,
                rationale="This observed relationship supplies one edge in the connected cluster.",
            )
        ledger.link_evidence(
            source_kind="assertion",
            source_id=reuse_assertion,
            target_kind="hypothesis",
            target_id=common_control,
            stance=EvidenceStance.SUPPORTS,
            rationale="Independent observation reduces the chance of a single-source artifact.",
        )
        ledger.link_evidence(
            source_kind="assertion",
            source_id=cluster_assertion,
            target_kind="hypothesis",
            target_id=common_control,
            stance=EvidenceStance.SUPPORTS,
            rationale="A connected cluster is consistent with common control but is not proof.",
        )
        ledger.link_evidence(
            source_kind="assertion",
            source_id=cluster_assertion,
            target_kind="hypothesis",
            target_id=shared_service,
            stance=EvidenceStance.SUPPORTS,
            rationale="The same topology can also arise from shared or repurposed services.",
        )

        contradiction_id = ledger.record_contradiction(
            left_kind="hypothesis",
            left_id=common_control,
            right_kind="hypothesis",
            right_id=shared_service,
            summary="Common control and shared infrastructure remain competing explanations.",
            resolution_required=(
                "Collect independently sourced ownership, tenancy, and temporal-allocation evidence."
            ),
            materiality=Materiality.HIGH,
        )
        gap_id = ledger.add_lifecycle_item(
            investigation_id,
            LifecycleItemType.KNOWLEDGE_GAP,
            "Hosting tenancy and control during the observed interval are unknown.",
            criteria={
                "needed": "contemporaneous ownership or tenancy evidence",
                "why": "topology alone does not establish operator control",
            },
            priority=100,
            author_kind=AuthorKind.SYSTEM,
        )
        ledger.add_lifecycle_item(
            investigation_id,
            LifecycleItemType.COLLECTION_REQUIREMENT,
            "Seek a second independent source for historical tenancy and certificate ownership.",
            criteria={"minimum_independent_sources": 2, "timebox_minutes": 20},
            priority=90,
            author_kind=AuthorKind.SYSTEM,
        )
        ledger.add_lifecycle_item(
            investigation_id,
            LifecycleItemType.PREDICTION,
            "If one operator controls the cluster, independent history should show overlapping control.",
            criteria={"observable": "overlapping ownership, certificate, or allocation interval"},
            priority=70,
            author_kind=AuthorKind.SYSTEM,
        )
        ledger.add_lifecycle_item(
            investigation_id,
            LifecycleItemType.STOP_CONDITION,
            "Pause attribution if the collection timebox expires without independent control evidence.",
            criteria={"timebox_minutes": 20},
            priority=80,
            author_kind=AuthorKind.SYSTEM,
        )
        ledger.assess_confidence(
            target_kind="hypothesis",
            target_id=common_control,
            level=ConfidenceLevel.LOW,
            rationale=(
                "The synthetic sources corroborate topology, but neither establishes ownership "
                "or exclusive control."
            ),
            factors={
                "source_quality": "two immutable synthetic observation sets",
                "source_independence": "two explicit dependence groups",
                "corroboration": "topology corroborated; control not corroborated",
                "assumptions": ["connected infrastructure may indicate common control"],
                "knowledge_gaps": ["historical tenancy", "operator identity"],
                "analytic_rigor": "competing explanation and stop condition retained",
            },
            assessed_by=AuthorKind.SYSTEM,
        )
        ledger.assess_likelihood(
            target_kind="hypothesis",
            target_id=common_control,
            term=LikelihoodTerm.ROUGHLY_EVEN_CHANCE,
            rationale=(
                "The fixture intentionally leaves common control and shared service as viable "
                "explanations."
            ),
            assessed_by=AuthorKind.SYSTEM,
        )
        ledger.set_investigation_status(investigation_id, InvestigationStatus.ANALYZING)

        snapshot = ledger.snapshot()
        return {
            "workspace": name,
            "synthetic": True,
            "network_requests": 0,
            "model_requests": 0,
            "entities": len(manager.get_stix_objects()),
            "relationships": 3,
            "observations": len(observations),
            "investigation_id": investigation_id,
            "question_id": question_id,
            "hypotheses": len(snapshot["hypotheses"]),
            "open_contradiction_id": contradiction_id,
            "priority_gap_id": gap_id,
            "next": [
                "graph clusters",
                "analysis lifecycle",
                "analysis contradictions",
                "report generate",
                f"workspace export {name}",
            ],
            "notice": (
                "Reserved synthetic training data only. No entity or judgment represents "
                "real threat intelligence."
            ),
        }
    except Exception:
        try:
            manager.delete(name)
        finally:
            if previous is not None:
                manager.switch(previous)
        raise
