"""Shared command-surface tests for the Synapse and SCOT4 adapters."""

from datetime import UTC, datetime

from adversary_pursuit.agent.repl_verbs import dispatch_repl_verb, parse_repl_verb
from adversary_pursuit.agent.tools import ToolContext
from adversary_pursuit.core.analytic_ledger import AnalyticLedger
from adversary_pursuit.core.command_completion import command_completions
from adversary_pursuit.core.config import ConfigManager
from adversary_pursuit.core.graph_repository import WorkspaceGraphRepository
from adversary_pursuit.core.integration_commands import execute_integration_command
from adversary_pursuit.integrations.scot_execution import (
    ScotPublicationJournal,
    ScotPublicationReceipt,
    approve_scot_publication,
    scot_confirmation,
)
from adversary_pursuit.integrations.scot_publication import (
    build_scot_publication_manifest,
    compile_scot_write_plan,
    validate_scot_pivot_request,
)
from adversary_pursuit.integrations.synapse_execution import SynapseShadowJournal
from adversary_pursuit.integrations.synapse_graph import build_synapse_shadow_manifest
from adversary_pursuit.integrations.synapse_migration import compile_synapse_migration_plan
from adversary_pursuit.integrations.synapse_model_deployment import (
    SynapseModelDeploymentJournal,
    compile_synapse_model_deployment_plan,
)
from adversary_pursuit.web.server import WebCockpitService


def test_integration_status_is_local_masked_and_shared(tmp_path):
    config_mgr = ConfigManager(tmp_path / "config")
    config_mgr.set("integrations.synapse_mcp_url", "https://synapse.test/api/v1/mcp")
    config_mgr.set("api_keys.synapse", "never-display-this")

    result = execute_integration_command(("status",), config_mgr)

    assert result["data"]["synapse"] == {
        "endpoint": "configured",
        "credential": "config",
        "mode": "read-only exploration; approved model deployment and shadow-view loads",
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
    synapse_model_plan = service.execute_command("integration synapse model-deploy-plan")
    synapse_plan = service.execute_command("integration synapse migration-plan")
    scot = service.execute_command("integration scot publish-preview")
    synapse_readiness = service.execute_command("integration synapse cutover-readiness")
    scot_readiness = service.execute_command("integration scot publication-readiness analyst")
    scot_plan = service.execute_command("integration scot publish-plan analyst")

    assert synapse["data"]["source_snapshot_sha256"] == scot["data"]["source_snapshot_sha256"]
    assert synapse["data"]["nodes"]
    assert synapse_model["data"]["model_version"] == "2.0.0"
    assert synapse_model["data"]["deployment_method"] == "synapse-extended-model"
    assert synapse_model_plan["data"]["model_digest_sha256"] == synapse_model["data"][
        "digest_sha256"
    ]
    assert synapse_model_plan["data"]["global_model_mutation"] is True
    assert synapse_model_plan["data"]["execution_enabled"] is False
    assert synapse_plan["data"]["manifest_digest_sha256"] == synapse["data"]["digest_sha256"]
    assert synapse_plan["data"]["execution_enabled"] is False
    assert scot["data"]["approval_required"] is True
    assert scot["data"]["published"] is False
    assert scot_plan["data"]["manifest_digest_sha256"] == scot["data"]["digest_sha256"]
    assert scot_plan["data"]["execution_enabled"] is False
    assert synapse_readiness["data"]["cutover_authorized"] is False
    assert synapse_readiness["data"]["eligible_for_cutover_review"] is False
    assert scot_readiness["data"]["current_graph_published"] is False
    assert scot_readiness["data"]["scot_side_pivot_trigger_implemented"] is True
    assert scot_readiness["data"]["scot_side_pivot_trigger_configured"] is False
    assert service._runner is None


def test_integration_readiness_requires_exact_current_receipts(tmp_path):
    ctx = ToolContext(
        config_dir=tmp_path / "config",
        workspace_dir=tmp_path / "workspaces",
    )
    ctx.config_mgr.set("integrations.synapse_mcp_url", "https://synapse.test/api/v1/mcp")
    ctx.config_mgr.set("integrations.scot_api_url", "https://scot.test/api")
    ctx.config_mgr.set("api_keys.synapse", "masked-in-output")
    ctx.config_mgr.set("api_keys.scot", "masked-in-output")
    ctx.workspace_mgr.store_stix_objects(
        [{"type": "domain-name", "value": "readiness.example"}],
        module_name="test/source",
        target="readiness.example",
    )
    snapshot = WorkspaceGraphRepository(ctx.workspace_mgr).snapshot()
    model_plan = compile_synapse_model_deployment_plan()
    migration_plan = compile_synapse_migration_plan(build_synapse_shadow_manifest(snapshot))
    scot_manifest = build_scot_publication_manifest(snapshot)
    scot_plan = compile_scot_write_plan(scot_manifest, owner="analyst")
    now = datetime.now(UTC)

    model_journal = SynapseModelDeploymentJournal(ctx.workspace_mgr)
    model_journal.claim(model_plan.digest_sha256, approved_by="analyst", started_at=now)
    model_journal.complete(
        model_plan.digest_sha256,
        receipt={
            "plan_digest_sha256": model_plan.digest_sha256,
            "model_digest_sha256": model_plan.model_digest_sha256,
            "exact_readback": True,
            "runtime_model_verified": True,
        },
        completed_at=now,
    )
    shadow_journal = SynapseShadowJournal(ctx.workspace_mgr)
    shadow_journal.claim(migration_plan.digest_sha256, approved_by="analyst", started_at=now)
    shadow_journal.complete(
        migration_plan.digest_sha256,
        receipt={
            "plan_digest_sha256": migration_plan.digest_sha256,
            "manifest_digest_sha256": migration_plan.manifest_digest_sha256,
            "model_digest_sha256": migration_plan.model_digest_sha256,
            "complete": True,
            "reconciled": True,
            "merged": False,
        },
        completed_at=now,
    )
    scot_journal = ScotPublicationJournal(ctx.workspace_mgr)
    scot_approval = approve_scot_publication(
        scot_plan,
        approved_by="analyst",
        confirmation=scot_confirmation(scot_plan),
        now=now,
    )
    scot_journal.claim(scot_plan, scot_approval, now=now)
    scot_journal.complete(
        ScotPublicationReceipt(
            publication_id=scot_manifest.publication_id,
            workspace=snapshot.workspace,
            plan_digest_sha256=scot_plan.digest_sha256,
            approved_by="analyst",
            started_at=now,
            completed_at=now,
            operations=(),
        )
    )

    synapse = execute_integration_command(
        ("synapse", "cutover-readiness"), ctx.config_mgr, ctx.workspace_mgr
    )["data"]
    scot = execute_integration_command(
        ("scot", "publication-readiness", "analyst"), ctx.config_mgr, ctx.workspace_mgr
    )["data"]

    assert synapse["eligible_for_cutover_review"] is True
    assert synapse["cutover_authorized"] is False
    assert synapse["cutover_implemented"] is False
    assert scot["current_graph_published"] is True
    assert scot["scot_side_pivot_trigger_implemented"] is True
    assert scot["scot_side_pivot_trigger_configured"] is False
    assert "masked-in-output" not in repr((synapse, scot))


def test_integration_completions_cover_read_operations():
    assert "integration" in command_completions("integ")
    assert "integration synapse query " in command_completions("integration synapse q")
    assert "integration synapse lookup " in command_completions("integration synapse l")
    assert "integration synapse shadow-preview" in command_completions("integration synapse s")
    assert "integration synapse cutover-readiness" in command_completions(
        "integration synapse c"
    )
    assert "integration synapse model-contract" in command_completions("integration synapse m")
    assert "integration synapse model-deploy-plan" in command_completions("integration synapse m")
    assert "integration synapse model-deploy-execute " in command_completions(
        "integration synapse m"
    )
    assert "integration synapse model-deploy-receipt " in command_completions(
        "integration synapse m"
    )
    assert "integration synapse migration-plan" in command_completions("integration synapse m")
    assert "integration synapse shadow-execute " in command_completions("integration synapse s")
    assert "integration synapse shadow-receipt " in command_completions("integration synapse s")
    assert "integration synapse views" in command_completions("integration synapse v")
    assert "integration scot search " in command_completions("integration scot s")
    assert "integration scot publish-preview" in command_completions("integration scot p")
    assert "integration scot publication-readiness " in command_completions(
        "integration scot publication-r"
    )
    assert "integration scot publish-plan " in command_completions("integration scot p")
    assert "integration scot publish-execute " in command_completions("integration scot p")
    assert "integration scot publication-receipt " in command_completions("integration scot p")
    assert "integration scot pivot-inbox" in command_completions("integration scot pivot-i")
    assert "integration scot pivot-accept " in command_completions("integration scot pivot-a")
    assert "integration scot pivot-reject " in command_completions("integration scot pivot-r")
    assert "integration scot pivot-queue" in command_completions("integration scot pivot-q")
    assert "integration scot pivot-enqueue " in command_completions("integration scot pivot-e")


def test_scot_pivot_inbox_accept_and_reject_commands_preserve_human_gate(tmp_path):
    ctx = ToolContext(
        config_dir=tmp_path / "config",
        workspace_dir=tmp_path / "workspaces",
    )
    ledger = AnalyticLedger(ctx.workspace_mgr)
    now = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    first = validate_scot_pivot_request(
        workspace="default",
        scot_object_type="event",
        scot_object_id=42,
        indicator="198.51.100.42",
        requested_by="scot-analyst",
        requested_at=now,
        reason="Follow the event relationship.",
    )
    second = validate_scot_pivot_request(
        workspace="default",
        scot_object_type="event",
        scot_object_id=73,
        indicator="203.0.113.73",
        requested_by="scot-analyst",
        requested_at=now,
        reason="Review the related address.",
    )
    authentication = {
        "scheme": "hmac-sha256-v1",
        "key_id": "scot4-primary",
        "body_sha256": "a" * 64,
        "nonce_sha256": "b" * 64,
    }
    ledger.record_scot_pivot_request(
        first.model_dump(mode="json"), authentication=authentication
    )
    ledger.record_scot_pivot_request(
        second.model_dump(mode="json"), authentication=authentication
    )

    inbox = execute_integration_command(
        ("scot", "pivot-inbox"), ctx.config_mgr, ctx.workspace_mgr
    )["data"]
    accepted = execute_integration_command(
        (
            "scot",
            "pivot-accept",
            first.request_id,
            "|",
            "local-analyst",
            "|",
            "In",
            "scope.",
        ),
        ctx.config_mgr,
        ctx.workspace_mgr,
    )["data"]
    accepted_retry = execute_integration_command(
        (
            "scot",
            "pivot-accept",
            first.request_id,
            "|",
            "local-analyst",
            "|",
            "Retry.",
        ),
        ctx.config_mgr,
        ctx.workspace_mgr,
    )["data"]
    rejected = execute_integration_command(
        (
            "scot",
            "pivot-reject",
            second.request_id,
            "|",
            "local-analyst",
            "|",
            "Outside",
            "scope.",
        ),
        ctx.config_mgr,
        ctx.workspace_mgr,
    )["data"]

    assert len(inbox) == 2
    assert accepted["created"] is True
    assert accepted["start_enrichment"] is True
    assert accepted_retry["created"] is False
    assert accepted_retry["start_enrichment"] is False
    assert rejected["analyst_disposition"] == "rejected"
    assert len(ledger.enrichment_requests()) == 1
