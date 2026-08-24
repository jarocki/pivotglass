"""Shared command-surface tests for the Synapse and SCOT4 adapters."""

from adversary_pursuit.agent.repl_verbs import dispatch_repl_verb, parse_repl_verb
from adversary_pursuit.agent.tools import ToolContext
from adversary_pursuit.core.command_completion import command_completions
from adversary_pursuit.core.config import ConfigManager
from adversary_pursuit.core.integration_commands import execute_integration_command
from adversary_pursuit.web.server import WebCockpitService


def test_integration_status_is_local_masked_and_shared(tmp_path):
    config_mgr = ConfigManager(tmp_path / "config")
    config_mgr.set("integrations.synapse_mcp_url", "https://synapse.test/api/v1/mcp")
    config_mgr.set("api_keys.synapse", "never-display-this")

    result = execute_integration_command(("status",), config_mgr)

    assert result["data"]["synapse"] == {
        "endpoint": "configured",
        "credential": "config",
        "mode": "read-only exploration; approved shadow-view loads",
        "authority": "remote-preview",
    }
    assert "never-display-this" not in repr(result)


def test_tui_and_web_route_integration_status_without_a_model(tmp_path):
    ctx = ToolContext(
        config_dir=tmp_path / "config",
        workspace_dir=tmp_path / "workspaces",
    )
    verb = parse_repl_verb("integration status")
    assert verb is not None
    tui = dispatch_repl_verb(
        verb,
        ctx,
        ctx.mode_mgr,
        ctx.workspace_mgr,
        config_mgr=ctx.config_mgr,
    )
    web_service = WebCockpitService(ctx)
    web = web_service.execute_command("integration status")

    assert "External integrations" in tui
    assert web["kind"] == "json"
    assert web["data"]["scot"]["authority"] == "remote-preview"
    assert web_service._runner is None


def test_web_previews_synapse_shadow_and_scot_publication_from_same_workspace(tmp_path):
    ctx = ToolContext(
        config_dir=tmp_path / "config",
        workspace_dir=tmp_path / "workspaces",
    )
    ctx.workspace_mgr.store_stix_objects(
        [{"type": "domain-name", "value": "preview.example"}],
        module_name="test/source",
        target="preview.example",
    )
    service = WebCockpitService(ctx)

    synapse = service.execute_command("integration synapse shadow-preview")
    synapse_model = service.execute_command("integration synapse model-contract")
    synapse_plan = service.execute_command("integration synapse migration-plan")
    scot = service.execute_command("integration scot publish-preview")
    scot_plan = service.execute_command("integration scot publish-plan analyst")

    assert synapse["data"]["source_snapshot_sha256"] == scot["data"]["source_snapshot_sha256"]
    assert synapse["data"]["nodes"]
    assert synapse_model["data"]["model_version"] == "1.0.0"
    assert synapse_plan["data"]["manifest_digest_sha256"] == synapse["data"]["digest_sha256"]
    assert synapse_plan["data"]["execution_enabled"] is False
    assert scot["data"]["approval_required"] is True
    assert scot["data"]["published"] is False
    assert scot_plan["data"]["manifest_digest_sha256"] == scot["data"]["digest_sha256"]
    assert scot_plan["data"]["execution_enabled"] is False
    assert service._runner is None


def test_integration_completions_cover_read_operations():
    assert "integration" in command_completions("integ")
    assert "integration synapse query " in command_completions("integration synapse q")
    assert "integration synapse lookup " in command_completions("integration synapse l")
    assert "integration synapse shadow-preview" in command_completions("integration synapse s")
    assert "integration synapse model-contract" in command_completions("integration synapse m")
    assert "integration synapse migration-plan" in command_completions("integration synapse m")
    assert "integration synapse shadow-execute " in command_completions("integration synapse s")
    assert "integration synapse shadow-receipt " in command_completions("integration synapse s")
    assert "integration synapse views" in command_completions("integration synapse v")
    assert "integration scot search " in command_completions("integration scot s")
    assert "integration scot publish-preview" in command_completions("integration scot p")
    assert "integration scot publish-plan " in command_completions("integration scot p")
    assert "integration scot publish-execute " in command_completions("integration scot p")
    assert "integration scot publication-receipt " in command_completions("integration scot p")
    assert "integration scot pivot-queue" in command_completions("integration scot pivot-q")
    assert "integration scot pivot-enqueue " in command_completions("integration scot pivot-e")
