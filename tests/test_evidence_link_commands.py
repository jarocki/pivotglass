"""Evidence-link authoring through the shared operator command path."""

from __future__ import annotations

import json

import pytest

from pivotglass.agent.repl_verbs import dispatch_repl_verb, parse_repl_verb
from pivotglass.core.analytic_commands import ANALYSIS_USAGE, execute_analysis_command
from pivotglass.core.analytic_ledger import AnalyticLedger, AssertionType
from pivotglass.core.command_completion import command_completions
from pivotglass.core.workspace import WorkspaceManager


@pytest.fixture
def case(tmp_path):
    manager = WorkspaceManager(workspace_dir=tmp_path)
    manager.create("link-case")
    manager.switch("link-case")
    manager.store_stix_objects(
        [{"type": "domain-name", "value": "investigation.example"}],
        module_name="test/offline-fixture",
        target="investigation.example",
    )
    ledger = AnalyticLedger(manager)
    question = ledger.create_question("Which explanation fits the record?")
    hypothesis = ledger.create_hypothesis(question, "The service is authorized.")
    assertion = ledger.create_assertion(
        "The service changed owner.", assertion_type=AssertionType.INFERRED
    )
    observation = manager.get_observations()[0]["id"]
    return manager, ledger, observation, assertion, hypothesis, question


def command(
    source_kind,
    source_id,
    target_kind,
    target_id,
    stance="supports",
    rationale="This record is consistent with the explanation.",
):
    return ("link", source_kind, source_id, target_kind, target_id, stance, "|", rationale)


@pytest.mark.parametrize("source_kind", ["observation", "assertion"])
@pytest.mark.parametrize("target_kind", ["assertion", "hypothesis"])
@pytest.mark.parametrize("stance", ["supports", "contradicts"])
def test_valid_links_persist_without_changing_evidence_or_judgments(
    case, source_kind, target_kind, stance
):
    manager, ledger, observation, assertion, hypothesis, _question = case
    source_id = observation if source_kind == "observation" else assertion
    target_id = hypothesis if target_kind == "hypothesis" else assertion
    original = ledger.snapshot()
    observations = json.dumps(manager.get_observations(), sort_keys=True, default=str)
    objects = json.dumps(manager.get_stix_objects(), sort_keys=True, default=str)
    runs = json.dumps(manager.get_module_runs(), sort_keys=True, default=str)
    result = execute_analysis_command(
        command(source_kind, source_id, target_kind, target_id, stance), manager
    )
    snapshot = ledger.snapshot()
    assert len(snapshot["evidence_links"]) == 1
    assert snapshot["evidence_links"][0]["created_at"] is not None
    assert [
        {key: value for key, value in row.items() if key != "created_at"}
        for row in snapshot["evidence_links"]
    ] == [
        {
            "id": result["data"]["link_id"],
            "source_kind": source_kind,
            "source_id": source_id,
            "target_kind": target_kind,
            "target_id": target_id,
            "stance": stance,
            "rationale": "This record is consistent with the explanation.",
        }
    ]
    assert {key: value for key, value in snapshot.items() if key != "evidence_links"} == {
        key: value for key, value in original.items() if key != "evidence_links"
    }
    assert json.dumps(manager.get_observations(), sort_keys=True, default=str) == observations
    assert json.dumps(manager.get_stix_objects(), sort_keys=True, default=str) == objects
    assert json.dumps(manager.get_module_runs(), sort_keys=True, default=str) == runs


@pytest.mark.parametrize(
    "failure",
    [
        "source-id",
        "target-id",
        "wrong-id-type",
        "source-kind",
        "target-kind",
        "stance",
        "rationale",
        "separator",
        "missing-rationale",
    ],
)
def test_invalid_links_fail_without_partial_ledger_writes(case, failure):
    manager, ledger, observation, assertion, hypothesis, question = case
    args = list(command("observation", observation, "hypothesis", hypothesis))
    if failure == "source-id":
        args[2] = "observation-missing"
    elif failure == "target-id":
        args[4] = "hypothesis-missing"
    elif failure == "wrong-id-type":
        args[4] = assertion
    elif failure == "source-kind":
        args[1] = "question"
        args[2] = question
    elif failure == "target-kind":
        args[3] = "observation"
        args[4] = observation
    elif failure == "stance":
        args[5] = "proves"
    elif failure == "rationale":
        args[7] = "   "
    elif failure == "separator":
        args[6] = ":"
    elif failure == "missing-rationale":
        args = args[:7]
    before = ledger.snapshot()
    with pytest.raises(ValueError):
        execute_analysis_command(tuple(args), manager)
    assert ledger.snapshot() == before


def test_repl_routes_authoring_and_help_completes_link(case):
    manager, ledger, observation, _assertion, hypothesis, _question = case
    verb = parse_repl_verb(
        f"analysis link observation {observation} hypothesis {hypothesis} contradicts | Operator rationale with spaces."
    )
    assert verb is not None
    result = dispatch_repl_verb(verb, None, None, manager)
    assert '"stance": "contradicts"' in result
    assert ledger.snapshot()["evidence_links"][0]["rationale"] == "Operator rationale with spaces."
    assert "analysis link " in command_completions("analysis li")
    assert "link <observation|assertion>" in ANALYSIS_USAGE


def test_web_routes_link_locally_and_exposes_operator_help(tmp_path, case):
    from pivotglass.agent.tools import ToolContext
    from pivotglass.web.server import WebCockpitService

    manager, ledger, observation, _assertion, hypothesis, _question = case
    context = ToolContext(config_dir=tmp_path / "config", workspace_dir=tmp_path / "web-workspaces")
    context.workspace_mgr = manager
    service = WebCockpitService(context)
    manager.switch("link-case")
    before = manager.get_observations()
    result = service.execute_command(
        f"analysis link observation {observation} hypothesis {hypothesis} supports | Analyst interpretation."
    )
    assert result["kind"] == "json"
    assert result["data"]["stance"] == "supports"
    assert service._runner is None
    assert manager.get_observations() == before
    assert ledger.snapshot()["evidence_links"][0]["rationale"] == "Analyst interpretation."
    assert any(row["command"].startswith("analysis link ") for row in service.command_catalog())
