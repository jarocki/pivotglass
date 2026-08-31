"""The no-key learning workspace exercises the real investigation loop offline."""

from __future__ import annotations

import io
import json
import shutil
import socket
from types import SimpleNamespace

from rich.console import Console

from adversary_pursuit.agent.chat import _chat_handle_workspace
from adversary_pursuit.agent.repl_verbs import ReplVerb, dispatch_repl_verb
from adversary_pursuit.agent.tools import ToolContext
from adversary_pursuit.core.analytic_ledger import AnalyticLedger
from adversary_pursuit.core.command_completion import command_completions
from adversary_pursuit.core.console import APConsole
from adversary_pursuit.core.learning_workspace import create_learning_workspace
from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.core.workspace_admin import export_workspace
from adversary_pursuit.web.server import WebCockpitService


def test_learning_workspace_is_offline_source_grounded_and_complete(tmp_path, monkeypatch) -> None:
    manager = WorkspaceManager(tmp_path / "workspaces")
    manager.create("default")
    manager.switch("default")

    def reject_network(*_args, **_kwargs):
        raise AssertionError("the learning workspace must not open a network connection")

    monkeypatch.setattr(socket.socket, "connect", reject_network)
    receipt = create_learning_workspace(manager, "learning")

    assert receipt["workspace"] == manager.active == "learning"
    assert receipt["synthetic"] is True
    assert receipt["network_requests"] == receipt["model_requests"] == 0
    assert receipt["entities"] == 4
    assert receipt["relationships"] == 3
    assert receipt["observations"] == 8

    observations = manager.get_observations()
    assert {row["source_module"] for row in observations} == {
        "learning/source-a",
        "learning/source-b",
    }
    assert {row["source_dependence_group"] for row in observations} == {
        "synthetic-source-a",
        "synthetic-source-b",
    }
    assert all(row["response_sha256"] for row in observations)
    assert all(row["raw_artifact_ref"].startswith("artifact://sha256/") for row in observations)
    assert all("SYNTHETIC TRAINING DATA" in row["handling_marking"] for row in observations)

    snapshot = AnalyticLedger(manager).snapshot()
    assert len(snapshot["investigations"]) == 1
    assert snapshot["investigations"][0]["status"] == "analyzing"
    assert len(snapshot["questions"]) == 1
    assert len(snapshot["hypotheses"]) == 2
    assert len(snapshot["assertions"]) == 2
    assert len(snapshot["evidence_links"]) == 8
    assert snapshot["confidence"][0]["level"] == "low"
    assert snapshot["likelihood"][0]["term"] == "roughly_even_chance"
    assert snapshot["contradictions"][0]["status"] == "unresolved"
    assert snapshot["contradictions"][0]["materiality"] == "high"
    open_items = {
        item["item_type"] for item in snapshot["lifecycle_items"] if item["status"] == "open"
    }
    assert {"knowledge_gap", "collection_requirement", "prediction", "stop_condition"} <= (
        open_items
    )

    exported = export_workspace(manager, "learning")
    assert len(exported["tables"]["relationships"]) == 3
    assert len(exported["tables"]["evidence_observations"]) == 8
    assert len(exported["tables"]["analytic_contradictions"]) == 1


def test_learning_workspace_survives_restart_and_database_recovery(tmp_path) -> None:
    source_dir = tmp_path / "source"
    manager = WorkspaceManager(source_dir)
    create_learning_workspace(manager, "learning")
    before = export_workspace(manager, "learning")

    restarted = WorkspaceManager(source_dir)
    restarted.switch("learning")
    assert export_workspace(restarted, "learning") == before

    manager._engine.dispose()
    restarted._engine.dispose()
    recovery_dir = tmp_path / "recovered"
    recovery_dir.mkdir()
    shutil.copy2(source_dir / "learning.db", recovery_dir / "learning.db")
    recovered = WorkspaceManager(recovery_dir)
    recovered.switch("learning")
    assert export_workspace(recovered, "learning") == before


def test_learning_workspace_failure_removes_partial_case_and_restores_active(
    tmp_path, monkeypatch
) -> None:
    manager = WorkspaceManager(tmp_path)
    manager.create("current")
    manager.switch("current")

    def fail_store(*_args, **_kwargs):
        raise RuntimeError("fixture write failed")

    monkeypatch.setattr(manager, "store_stix_objects", fail_store)
    try:
        create_learning_workspace(manager, "partial")
    except RuntimeError as exc:
        assert str(exc) == "fixture write failed"
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected the synthetic fixture failure")

    assert manager.active == "current"
    assert manager.list_workspaces() == ["current"]


def test_learning_workspace_command_has_web_tui_basic_and_completion_parity(tmp_path) -> None:
    service = WebCockpitService(
        ToolContext(
            config_dir=tmp_path / "web-config",
            workspace_dir=tmp_path / "web-workspaces",
        )
    )
    web_result = service.execute_command("workspace learn web-learning")
    assert web_result["kind"] == "json"
    assert web_result["data"]["synthetic"] is True
    assert service.ctx.workspace_mgr.active == "web-learning"

    tui_manager = WorkspaceManager(tmp_path / "tui-workspaces")
    tui_result = dispatch_repl_verb(
        ReplVerb(name="workspace", args=("learn", "tui-learning")),
        ctx=None,
        mode_mgr=None,
        workspace_mgr=tui_manager,
    )
    assert json.loads(tui_result)["synthetic"] is True
    assert tui_manager.active == "tui-learning"

    chat_manager = WorkspaceManager(tmp_path / "chat-workspaces")
    chat_output = io.StringIO()
    _chat_handle_workspace(
        "workspace learn chat-learning",
        SimpleNamespace(ctx=SimpleNamespace(workspace_mgr=chat_manager)),
        Console(file=chat_output, force_terminal=False, color_system=None),
    )
    assert '"synthetic": true' in chat_output.getvalue()
    assert chat_manager.active == "chat-learning"

    basic = APConsole(
        config_dir=tmp_path / "basic-config",
        workspace_dir=tmp_path / "basic-workspaces",
    )
    basic.stdout = io.StringIO()
    basic.rich_console = basic._make_rich_console()
    basic.onecmd_plus_hooks("workspace learn basic-learning")
    assert '"synthetic": true' in basic.stdout.getvalue()
    assert basic.workspace_mgr.active == "basic-learning"

    assert "workspace learn " in command_completions("workspace le")
