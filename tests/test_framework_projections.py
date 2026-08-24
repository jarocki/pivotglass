"""Contracts for the v0.9 framework projection authority."""

from __future__ import annotations

import pytest

from adversary_pursuit.agent.repl_verbs import parse_repl_verb
from adversary_pursuit.core.analytic_ledger import ConfidenceLevel
from adversary_pursuit.core.command_completion import command_completions
from adversary_pursuit.core.framework_projections import (
    Framework,
    FrameworkMapping,
    FrameworkProjectionAuthority,
    MappingOrigin,
    MappingState,
)
from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.core.workspace_migrations import (
    CURRENT_WORKSPACE_SCHEMA_VERSION,
    get_workspace_schema_version,
)


def _workspace(tmp_path) -> WorkspaceManager:
    manager = WorkspaceManager(tmp_path)
    manager.create("case")
    manager.switch("case")
    return manager


def _observation(manager: WorkspaceManager, value: str) -> str:
    manager.store_stix_objects(
        [{"type": "domain-name", "value": value}],
        module_name="test/source",
        target=value,
    )
    return manager.get_observations()[-1]["id"]


def test_framework_mapping_requires_evidence_and_pinned_content() -> None:
    with pytest.raises(ValueError, match="evidence reference"):
        FrameworkMapping(
            id="mapping-1",
            framework=Framework.ATTACK,
            framework_version="test-1",
            content_id="T1003",
            content_label="OS Credential Dumping",
            evidence_refs=(),
            basis="unsupported",
            mapper="test",
            mapper_version="1",
            origin=MappingOrigin.AUTOMATED,
            confidence=ConfidenceLevel.LOW,
            confidence_rationale="not enough evidence",
        )


def test_mapping_lifecycle_and_gap_projection_are_deterministic(tmp_path) -> None:
    manager = _workspace(tmp_path)
    authority = FrameworkProjectionAuthority(manager)
    observation_id = _observation(manager, "credential-dumping.example")
    mapping = authority.propose(
        framework=Framework.ATTACK,
        framework_version="enterprise-15.1",
        content_id="T1003",
        content_label="OS Credential Dumping",
        evidence_refs=(observation_id,),
        basis="The observation records a credential-dumping command line.",
        mapper="analyst",
        mapper_version="1.0",
        origin=MappingOrigin.HUMAN,
        confidence=ConfidenceLevel.MODERATE,
        confidence_rationale="One source-backed observation; independent corroboration is missing.",
    )
    assert authority.disposition(mapping.id, MappingState.ACCEPTED).state is MappingState.ACCEPTED

    projection = authority.projection(
        Framework.ATTACK,
        framework_version="enterprise-15.1",
        required_content=(
            ("T1003", "OS Credential Dumping"),
            ("T1059", "Command and Scripting Interpreter"),
        ),
    )
    assert [item.content_id for item in projection.mappings] == ["T1003"]
    assert [gap.content_id for gap in projection.gaps] == ["T1059"]
    assert authority.export()["schema_version"] == "framework-mappings-1.0"


def test_model_mapping_cannot_be_accepted_without_human_override(tmp_path) -> None:
    manager = _workspace(tmp_path)
    authority = FrameworkProjectionAuthority(manager)
    observation_id = _observation(manager, "model-proposal.example")
    mapping = authority.propose(
        framework=Framework.DIAMOND,
        framework_version="1.0",
        content_id="capability:credential-access",
        content_label="Credential access",
        evidence_refs=(observation_id,),
        basis="A model proposed this mapping from the source-backed observation.",
        mapper="local-model",
        mapper_version="2026-08",
        origin=MappingOrigin.MODEL,
        confidence=ConfidenceLevel.LOW,
        confidence_rationale="Proposal requires analyst review.",
    )
    with pytest.raises(ValueError, match="analyst override"):
        authority.disposition(mapping.id, MappingState.ACCEPTED)
    accepted = authority.disposition(
        mapping.id,
        MappingState.ACCEPTED,
        analyst_override="Reviewed the observation and accept the mapping.",
    )
    assert accepted.state is MappingState.ACCEPTED


def test_framework_mapping_rejects_unknown_observation_reference(tmp_path) -> None:
    authority = FrameworkProjectionAuthority(_workspace(tmp_path))
    with pytest.raises(ValueError, match="unknown observation IDs: observation-missing"):
        authority.propose(
            framework=Framework.ATTACK,
            framework_version="19.2",
            content_id="T1003",
            content_label="OS Credential Dumping",
            evidence_refs=("observation-missing",),
            basis="The claimed evidence does not exist.",
            mapper="test",
            mapper_version="1.0",
            origin=MappingOrigin.HUMAN,
            confidence=ConfidenceLevel.LOW,
            confidence_rationale="This proposal must be rejected.",
        )


def test_fresh_workspace_has_current_schema(tmp_path) -> None:
    assert (
        get_workspace_schema_version(_workspace(tmp_path)._engine)
        == CURRENT_WORKSPACE_SCHEMA_VERSION
    )


def test_framework_is_shared_by_command_parser_and_completion() -> None:
    assert parse_repl_verb("framework list").name == "framework"
    assert "framework" in command_completions("frame")
    assert "framework show attack" in command_completions("framework s")
    assert "framework require attack " in command_completions("framework req")
    assert "framework gaps" in command_completions("framework g")
