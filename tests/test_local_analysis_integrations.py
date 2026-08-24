"""Contract and command tests for go-roast and Nucleotide previews."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from adversary_pursuit.agent.tools import ToolContext
from adversary_pursuit.core.command_completion import command_completions
from adversary_pursuit.core.config import ConfigManager
from adversary_pursuit.core.integration_commands import execute_integration_command
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
    adapter = RoastAdapter(
        executable, timeout_seconds=2, max_output_bytes=100_000, max_records=10
    )

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
    adapter = RoastAdapter(
        executable, timeout_seconds=2, max_output_bytes=4096, max_records=10
    )

    with pytest.raises(ValueError, match="output budget"):
        adapter.decode(["safe.oast.pro"])


def test_roast_rejects_shell_metacharacters_as_invalid_domains(tmp_path):
    executable = _tool(tmp_path, "raise SystemExit('must not execute')\n")
    adapter = RoastAdapter(
        executable, timeout_seconds=2, max_output_bytes=4096, max_records=10
    )

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


def test_local_tool_environment_does_not_forward_secrets(tmp_path, monkeypatch):
    executable = _tool(
        tmp_path,
        "import json, os, sys\njson.dump([{'original': os.getenv('AP_TEST_SECRET', 'absent'), 'valid': True}], sys.stdout)\n",
    )
    monkeypatch.setenv("AP_TEST_SECRET", "do-not-forward")
    adapter = RoastAdapter(
        executable, timeout_seconds=2, max_output_bytes=100_000, max_records=10
    )

    preview = adapter.decode(["x.oast.pro"])

    assert preview.records[0].original == "absent"
