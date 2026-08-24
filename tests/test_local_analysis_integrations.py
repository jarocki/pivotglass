"""Contract and command tests for go-roast and Nucleotide previews."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from adversary_pursuit.agent.tools import ToolContext
from adversary_pursuit.core.analytic_ledger import (
    AnalystDisposition,
    AnalyticLedger,
)
from adversary_pursuit.core.command_completion import command_completions
from adversary_pursuit.core.config import ConfigManager
from adversary_pursuit.core.integration_commands import execute_integration_command
from adversary_pursuit.core.investigation_graph import build_investigation_graph
from adversary_pursuit.integrations.nucleotide import NucleotideAdapter
from adversary_pursuit.integrations.roast import RoastAdapter
from adversary_pursuit.web.server import WebCockpitService


def _tool(tmp_path: Path, body: str) -> str:
    path = tmp_path / "fake-tool"
    path.write_text(f"#!{sys.executable}\n{body}")
    path.chmod(0o700)
    return str(path)


def _lookup(tmp_path: Path) -> str:
    path = tmp_path / "lookup.json"
    path.write_text(
        json.dumps(
            {
                "metadata": {"commit": "abc123", "template_count": 1},
                "templates": {"template-1": {}},
                "snippet_index": {"/admin": "template-1"},
                "signatures": {"snort": {}, "sigma": {}},
            }
        )
    )
    return str(path)


def test_roast_decode_is_a_reviewable_graph_proposal(tmp_path):
    executable = _tool(
        tmp_path,
        """import json, sys
json.dump([{
    "original": "c58bduhe008dovpvhvugcfemp9yyyyyyn.oast.pro",
    "timestamp": "2021-09-26T18:07:54Z",
    "machine_id": "2e:00:10",
    "pid": 56447,
    "counter": 4165629,
    "campaign": "he008",
    "valid": True,
    "classification": {"confidence": "high"}
}], sys.stdout)
""",
    )
    adapter = RoastAdapter(executable, timeout_seconds=2, max_output_bytes=100_000, max_records=10)

    preview = adapter.decode(["c58bduhe008dovpvhvugcfemp9yyyyyyn.oast.pro"])

    assert preview.disposition == "preview"
    assert preview.import_requires_analyst_action is True
    assert {node.kind for node in preview.nodes} == {
        "oast-domain",
        "oast-campaign-fragment",
        "oast-machine-fragment",
        "oast-process-fragment",
    }
    assert {edge.relationship for edge in preview.relationships} == {
        "encodes-campaign-fragment",
        "encodes-machine-fragment",
        "encodes-process-fragment",
    }
    assert any("not operator identity" in caveat for caveat in preview.caveats)
    assert preview.receipt.complete is True


def test_roast_rejects_output_beyond_budget(tmp_path):
    executable = _tool(tmp_path, "import sys\nsys.stdout.write('x' * 5000)\n")
    adapter = RoastAdapter(executable, timeout_seconds=2, max_output_bytes=4096, max_records=10)

    with pytest.raises(ValueError, match="output budget"):
        adapter.decode(["safe.oast.pro"])


def test_roast_rejects_shell_metacharacters_as_invalid_domains(tmp_path):
    executable = _tool(tmp_path, "raise SystemExit('must not execute')\n")
    adapter = RoastAdapter(executable, timeout_seconds=2, max_output_bytes=4096, max_records=10)

    with pytest.raises(ValueError, match="invalid OAST domain"):
        adapter.decode(["safe.oast.pro;touch-danger"])


def test_nucleotide_lookup_preserves_ambiguity_and_corpus_digest(tmp_path):
    executable = _tool(
        tmp_path,
        """import sys
for value in sys.argv[3:]:
    if value.startswith('--'):
        continue
    print(f"{value}\\tAMBIGUOUS\\ttemplate-1\\t/admin\\thigh\\tAdmin check")
""",
    )
    adapter = NucleotideAdapter(
        executable,
        _lookup(tmp_path),
        timeout_seconds=2,
        max_output_bytes=100_000,
        max_records=10,
    )

    preview = adapter.lookup(["https://victim.example/admin"])

    assert preview.matches[0].attribution == "AMBIGUOUS"
    assert len(preview.lookup_sha256) == 64
    assert preview.disposition == "preview"
    assert preview.import_requires_analyst_action is True


def test_nucleotide_fingerprint_surfaces_signals_and_contradictions(tmp_path):
    executable = _tool(
        tmp_path,
        """print('''actor_fingerprint:
  id: actor-1
  structural_hash: sha256:abc
  tool_inference:
    likely_tool: nuclei
    confidence: 0.7
    signals:
      - matched a known template
    contradictions:
      - user agent differed
  inferred_cli_options: {}
  template_preference:
    matched: [template-1]
''')
""",
    )
    adapter = NucleotideAdapter(
        executable,
        _lookup(tmp_path),
        timeout_seconds=2,
        max_output_bytes=100_000,
        max_records=10,
    )

    preview = adapter.fingerprint("actor-1", [{"uri": "/admin"}])

    assert preview.supporting_signals == ("matched a known template",)
    assert preview.contradictions == ("user agent differed",)
    assert preview.generated_controls_are_review_only is True
    assert preview.event_count == 1


def test_shared_commands_and_completion_expose_local_analysis(tmp_path):
    roast = _tool(
        tmp_path,
        "import json, sys\njson.dump([{'original': 'x.oast.pro', 'valid': True}], sys.stdout)\n",
    )
    config_mgr = ConfigManager(tmp_path / "config")
    config_mgr.set("integrations.go_roast_executable", roast)
    config_mgr.set("integrations.nucleotide_lookup_path", _lookup(tmp_path))

    local = execute_integration_command(("roast", "decode", "x.oast.pro"), config_mgr)
    ctx = ToolContext(config_dir=tmp_path / "config", workspace_dir=tmp_path / "workspaces")
    web = WebCockpitService(ctx).execute_command("integration roast decode x.oast.pro")

    assert local["data"]["records"][0]["original"] == "x.oast.pro"
    assert web["data"]["disposition"] == "preview"
    assert "integration roast decode " in command_completions("integration roast d")
    assert "integration nucleotide fingerprint-preview " in command_completions(
        "integration nucleotide f"
    )


def test_roast_record_and_human_review_use_governed_analytic_lifecycle(tmp_path):
    roast = _tool(
        tmp_path,
        """import json, sys
json.dump([{
    "original": "c58bduhe008dovpvhvugcfemp9yyyyyyn.oast.pro",
    "machine_id": "2e:00:10",
    "pid": 56447,
    "campaign": "he008",
    "valid": True,
    "classification": {"confidence": "high"}
}], sys.stdout)
""",
    )
    ctx = ToolContext(config_dir=tmp_path / "config", workspace_dir=tmp_path / "workspaces")
    ctx.config_mgr.set("integrations.go_roast_executable", roast)

    result = execute_integration_command(
        (
            "roast",
            "record",
            "c58bduhe008dovpvhvugcfemp9yyyyyyn.oast.pro",
        ),
        ctx.config_mgr,
        ctx.workspace_mgr,
    )
    repeated = execute_integration_command(
        (
            "roast",
            "record",
            "c58bduhe008dovpvhvugcfemp9yyyyyyn.oast.pro",
        ),
        ctx.config_mgr,
        ctx.workspace_mgr,
    )

    assert len(result["data"]["recorded"]) == 3
    assert all(item["created"] is True for item in result["data"]["recorded"])
    assert all(item["created"] is False for item in repeated["data"]["recorded"])
    proposal_id = result["data"]["recorded"][0]["proposal_id"]
    observations_before = len(ctx.workspace_mgr.get_observations())
    proposals = execute_integration_command(("proposals",), ctx.config_mgr, ctx.workspace_mgr)[
        "data"
    ]
    assert all(item["analyst_disposition"] == "pending" for item in proposals)
    assert all(item["criteria"]["truth_kind"] == "external-derived-proposal" for item in proposals)
    with pytest.raises(ValueError, match="explicitly accepted"):
        execute_integration_command(
            ("materialize", proposal_id, "|", "Premature promotion."),
            ctx.config_mgr,
            ctx.workspace_mgr,
        )

    review = execute_integration_command(
        (
            "review",
            proposal_id,
            "accept",
            "|",
            "Corroborated against independently collected traffic.",
        ),
        ctx.config_mgr,
        ctx.workspace_mgr,
    )

    assert review["data"]["analyst_disposition"] == "accepted"
    assert review["data"]["criteria"]["reviews"][0]["decided_by"] == "human"
    materialized = execute_integration_command(
        (
            "materialize",
            proposal_id,
            "|",
            "Promote as an inference with the decoder caveats intact.",
        ),
        ctx.config_mgr,
        ctx.workspace_mgr,
    )["data"]
    repeated_materialization = execute_integration_command(
        ("materialize", proposal_id, "|", "This must remain idempotent."),
        ctx.config_mgr,
        ctx.workspace_mgr,
    )["data"]

    assert materialized["created"] is True
    assert repeated_materialization["created"] is False
    assert materialized["assertion"]["assertion_type"] == "inferred"
    assert materialized["assertion"]["author_kind"] == "external_tool"
    assert materialized["assertion"]["predicate"] == "encodes-campaign-fragment"
    assert materialized["lifecycle_item"]["analyst_disposition"] == "accepted"
    assert materialized["lifecycle_item"]["criteria"]["truth_kind"] == (
        "external-derived-assertion"
    )
    assert materialized["lifecycle_item"]["evidence_refs"][-1] == {
        "kind": "external-analysis-proposal",
        "ref": proposal_id,
    }
    assert len(ctx.workspace_mgr.get_observations()) == observations_before
    graph_node = next(
        node
        for node in build_investigation_graph(ctx.workspace_mgr).nodes
        if node.record_ref == proposal_id
    )
    assert graph_node.kind == "external_analysis"
    assert graph_node.state == "accepted"
    assert graph_node.attributes["truth_kind"] == "external-derived-proposal"
    graph = build_investigation_graph(ctx.workspace_mgr)
    assertion_id = materialized["assertion"]["id"]
    assertion_node = next(node for node in graph.nodes if node.record_ref == assertion_id)
    assert assertion_node.attributes["assertion_type"] == "inferred"
    assert assertion_node.attributes["truth_kind"] == "external-derived-assertion"
    assert assertion_node.attributes["source_proposal_id"] == proposal_id
    assert any(
        edge.source == f"epistemic:assertion:{assertion_id}"
        and edge.target == f"epistemic:external_analysis:{proposal_id}"
        and edge.relationship == "materialized-from"
        for edge in graph.edges
    )


def test_nucleotide_lookup_record_preserves_no_match_as_pending_analysis(tmp_path):
    nucleotide = _tool(
        tmp_path,
        """import sys
for value in sys.argv[3:]:
    print(f"{value}\\tNO_MATCH")
""",
    )
    ctx = ToolContext(config_dir=tmp_path / "config", workspace_dir=tmp_path / "workspaces")
    ctx.config_mgr.set("integrations.nucleotide_executable", nucleotide)
    ctx.config_mgr.set("integrations.nucleotide_lookup_path", _lookup(tmp_path))

    result = execute_integration_command(
        ("nucleotide", "lookup-record", "https://victim.example/unmatched"),
        ctx.config_mgr,
        ctx.workspace_mgr,
    )

    assert result["data"]["preview"]["matches"][0]["attribution"] == "NO_MATCH"
    assert result["data"]["recorded"][0]["created"] is True
    proposals = execute_integration_command(("proposals",), ctx.config_mgr, ctx.workspace_mgr)[
        "data"
    ]
    assert proposals[0]["criteria"]["provider"] == "nucleotide"
    assert proposals[0]["analyst_disposition"] == "pending"


def test_external_analysis_completion_includes_record_and_review_paths():
    assert "integration proposals" in command_completions("integration pro")
    assert "integration review " in command_completions("integration rev")
    assert "integration materialize " in command_completions("integration mat")
    assert "integration roast record " in command_completions("integration roast r")
    assert "integration nucleotide lookup-record " in command_completions(
        "integration nucleotide lookup-r"
    )


@pytest.mark.parametrize(
    ("operation", "details", "predicate", "object_value"),
    [
        (
            "url-template-lookup",
            {
                "url": "https://victim.example/admin",
                "attribution": "UNIQUE",
                "template_id": "template-1",
            },
            "has-nucleotide-template-attribution",
            "template-1",
        ),
        (
            "actor-behavior-fingerprint",
            {
                "analyst_grouped_batch": "batch-1",
                "fingerprint_sha256": "b" * 64,
            },
            "has-nucleotide-behavior-fingerprint",
            "b" * 64,
        ),
    ],
)
def test_accepted_nucleotide_proposals_materialize_as_inferences(
    tmp_path, operation, details, predicate, object_value
):
    ctx = ToolContext(config_dir=tmp_path / "config", workspace_dir=tmp_path / "workspaces")
    ledger = AnalyticLedger(ctx.workspace_mgr)
    proposal, _ = ledger.record_external_analysis_proposal(
        provider="nucleotide",
        operation=operation,
        statement="Nucleotide produced reviewable derived analysis.",
        payload_sha256="a" * 64,
        provenance_refs=("nucleotide:receipt",),
        caveats=("This is derived analysis, not observed telemetry.",),
        details=details,
    )
    ledger.review_external_analysis_proposal(
        proposal["record_id"],
        disposition=AnalystDisposition.ACCEPTED,
        reason="The analyst accepts this bounded inference for further analysis.",
    )

    result = ledger.materialize_external_analysis_proposal(
        proposal["record_id"],
        rationale="Keep the external receipt and caveats with the inference.",
    )

    assert result["assertion"]["predicate"] == predicate
    assert result["assertion"]["object_value"] == object_value
    assert result["lifecycle_item"]["criteria"]["caveats"] == [
        "This is derived analysis, not observed telemetry."
    ]
    assert ctx.workspace_mgr.get_observations() == []


def test_local_tool_environment_does_not_forward_secrets(tmp_path, monkeypatch):
    executable = _tool(
        tmp_path,
        "import json, os, sys\njson.dump([{'original': os.getenv('AP_TEST_SECRET', 'absent'), 'valid': True}], sys.stdout)\n",
    )
    monkeypatch.setenv("AP_TEST_SECRET", "do-not-forward")
    adapter = RoastAdapter(executable, timeout_seconds=2, max_output_bytes=100_000, max_records=10)

    preview = adapter.decode(["x.oast.pro"])

    assert preview.records[0].original == "absent"
