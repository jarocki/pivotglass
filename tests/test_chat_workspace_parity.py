"""Phase 17P: chat workspace subcommand parity + db_status meta-command tests.

Tests that the ``ap chat`` workspace dispatcher matches cmd2 APConsole.do_workspace
parity (DEC-WORKSPACE-DB-003: legacy shorthand warns and still switches; new
subcommands list / create / switch / delete / clear all work) and that the
db_status meta-command renders the same enhanced table as do_db_status.

All tests call ``_chat_handle_workspace`` and the ``db_status`` branch directly
via a lightweight mock of ``runner`` rather than starting the full REPL loop,
so no LLM connection is required and tests are always deterministic.

@decision DEC-TEST-17P-CHAT-001
@title Chat workspace parity tests use a stub AgentRunner context to avoid LLM
@status accepted
@rationale The chat workspace dispatcher only reads/writes ``runner.ctx.workspace_mgr``.
           A minimal stub that exposes ``ctx.workspace_mgr`` is sufficient to exercise
           all code paths deterministically without a live LLM backend.
"""

from __future__ import annotations

import io

from rich.console import Console

from adversary_pursuit.agent.chat import _chat_handle_workspace
from adversary_pursuit.core.console import _render_db_status_table
from adversary_pursuit.core.workspace import WorkspaceManager

# ---------------------------------------------------------------------------
# Stub: lightweight AgentRunner-like object for chat tests
# ---------------------------------------------------------------------------


class _StubCtx:
    """Minimal stand-in for AgentRunner.ctx, exposing workspace_mgr only."""

    def __init__(self, workspace_mgr: WorkspaceManager) -> None:
        self.workspace_mgr = workspace_mgr


class _StubRunner:
    """Minimal stand-in for AgentRunner with a ToolContext."""

    def __init__(self, workspace_mgr: WorkspaceManager) -> None:
        self.ctx = _StubCtx(workspace_mgr)


def _make_console() -> tuple[Console, io.StringIO]:
    """Return a StringIO-backed Rich Console and its underlying buffer."""
    buf = io.StringIO()
    con = Console(file=buf, highlight=False, markup=False)
    return con, buf


# ---------------------------------------------------------------------------
# Workspace list
# ---------------------------------------------------------------------------


def test_chat_workspace_bare_lists(tmp_path):
    """``workspace`` with no subcommand lists workspaces."""
    wm = WorkspaceManager(workspace_dir=tmp_path)
    wm.create("alpha")
    wm.switch("alpha")
    runner = _StubRunner(wm)
    con, buf = _make_console()

    _chat_handle_workspace("workspace", runner, con)
    out = buf.getvalue()
    assert "alpha" in out


def test_chat_workspace_list_explicit(tmp_path):
    """``workspace list`` shows all workspaces."""
    wm = WorkspaceManager(workspace_dir=tmp_path)
    wm.create("ws1")
    wm.create("ws2")
    wm.switch("ws1")
    runner = _StubRunner(wm)
    con, buf = _make_console()

    _chat_handle_workspace("workspace list", runner, con)
    out = buf.getvalue()
    assert "ws1" in out
    assert "ws2" in out


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_chat_workspace_create_calls_manager(tmp_path):
    """``workspace create <name>`` creates the workspace via WorkspaceManager."""
    wm = WorkspaceManager(workspace_dir=tmp_path)
    runner = _StubRunner(wm)
    con, buf = _make_console()

    _chat_handle_workspace("workspace create newws", runner, con)
    out = buf.getvalue()

    assert "newws" in wm.list_workspaces()
    assert "newws" in out.lower() or "created" in out.lower()


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------


def test_chat_workspace_switch_calls_manager(tmp_path):
    """``workspace switch <name>`` switches the active workspace."""
    wm = WorkspaceManager(workspace_dir=tmp_path)
    wm.create("ws_a")
    wm.create("ws_b")
    wm.switch("ws_a")
    runner = _StubRunner(wm)
    con, buf = _make_console()

    _chat_handle_workspace("workspace switch ws_b", runner, con)
    out = buf.getvalue()

    assert wm.active == "ws_b"
    assert "ws_b" in out.lower() or "switched" in out.lower()


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_chat_workspace_delete_prompts_then_calls(tmp_path, monkeypatch):
    """``workspace delete <name>`` prompts and deletes when user confirms."""
    wm = WorkspaceManager(workspace_dir=tmp_path)
    wm.create("todelete")
    wm.create("keep")
    wm.switch("keep")
    runner = _StubRunner(wm)
    con, buf = _make_console()

    monkeypatch.setattr("adversary_pursuit.agent.chat._confirm", lambda prompt: True)

    _chat_handle_workspace("workspace delete todelete", runner, con)
    out = buf.getvalue()

    assert "todelete" not in wm.list_workspaces()
    assert "todelete" in out.lower() or "deleted" in out.lower()


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------


def test_chat_workspace_clear_no_arg_prompts_then_calls_active(tmp_path, monkeypatch):
    """``workspace clear`` with no arg prompts and clears the active workspace."""
    wm = WorkspaceManager(workspace_dir=tmp_path)
    wm.create("ws")
    wm.switch("ws")
    wm.store_stix_objects(
        [{"type": "ipv4-addr", "value": "1.1.1.1"}],
        module_name="t",
        target="1.1.1.1",
    )
    runner = _StubRunner(wm)
    con, buf = _make_console()

    monkeypatch.setattr("adversary_pursuit.agent.chat._confirm", lambda prompt: True)

    _chat_handle_workspace("workspace clear", runner, con)
    out = buf.getvalue()

    assert wm.get_stix_objects() == []
    assert "cleared" in out.lower() or "removed" in out.lower() or "ws" in out.lower()


def test_chat_workspace_clear_with_name_prompts_then_calls_named(tmp_path, monkeypatch):
    """``workspace clear <name>`` prompts and clears the named workspace."""
    wm = WorkspaceManager(workspace_dir=tmp_path)
    wm.create("active")
    wm.create("target")
    wm.switch("target")
    wm.store_stix_objects(
        [{"type": "domain-name", "value": "evil.com"}],
        module_name="t",
        target="evil.com",
    )
    wm.switch("active")
    runner = _StubRunner(wm)
    con, buf = _make_console()

    monkeypatch.setattr("adversary_pursuit.agent.chat._confirm", lambda prompt: True)

    _chat_handle_workspace("workspace clear target", runner, con)
    out = buf.getvalue()

    # target should be empty; active is untouched
    wm.switch("target")
    assert wm.get_stix_objects() == []
    assert "target" in out.lower() or "cleared" in out.lower()


# ---------------------------------------------------------------------------
# Legacy shorthand deprecation
# ---------------------------------------------------------------------------


def test_chat_workspace_legacy_shorthand_warns_and_still_switches(tmp_path):
    """``workspace <name>`` (no subcommand keyword) warns and switches (DEC-WORKSPACE-DB-003)."""
    wm = WorkspaceManager(workspace_dir=tmp_path)
    wm.create("legacy")
    wm.create("current")
    wm.switch("current")
    runner = _StubRunner(wm)
    con, buf = _make_console()

    # No monkeypatching — legacy path must switch even without a mock
    _chat_handle_workspace("workspace legacy", runner, con)
    out = buf.getvalue()

    # Must have actually switched
    assert wm.active == "legacy"
    # Must contain deprecation hint
    assert "deprecated" in out.lower() or "workspace switch" in out.lower()


# ---------------------------------------------------------------------------
# Unknown subcommand
# ---------------------------------------------------------------------------


def test_chat_workspace_unknown_subcommand_shows_usage(tmp_path):
    """``workspace frobnicate`` (unknown subcommand) shows a usage message."""
    wm = WorkspaceManager(workspace_dir=tmp_path)
    wm.create("ws")
    wm.switch("ws")
    runner = _StubRunner(wm)
    con, buf = _make_console()

    _chat_handle_workspace("workspace frobnicate", runner, con)
    out = buf.getvalue()

    # Should show "Unknown" or usage guidance without crashing
    assert "unknown" in out.lower() or "usage" in out.lower() or "frobnicate" in out.lower()


# ---------------------------------------------------------------------------
# db_status
# ---------------------------------------------------------------------------


def test_chat_db_status_renders_enhanced_table(tmp_path):
    """The shared ``_render_db_status_table`` helper renders the full enhanced table.

    This exercises the production sequence: chat db_status calls
    ``_render_db_status_table(runner.ctx.workspace_mgr, console)`` —
    the same helper called by ``APConsole.do_db_status``. Both surfaces
    render identical output for the same workspace state (DEC-WORKSPACE-DB-005).
    """
    wm = WorkspaceManager(workspace_dir=tmp_path)
    wm.create("default")
    wm.switch("default")

    # Populate data so non-zero counts and last-event rows appear
    wm.store_stix_objects(
        [{"type": "ipv4-addr", "value": "8.8.8.8"}],
        module_name="osint/test",
        target="8.8.8.8",
    )
    wm.add_note("test note for db_status")
    wm.store_badge_event("badge-first-blood", "First Blood")

    buf = io.StringIO()
    con = Console(file=buf, highlight=False, markup=False)

    _render_db_status_table(wm, con)
    out = buf.getvalue()

    # Active workspace row
    assert "default" in out
    # DB path row
    assert "default.db" in out or "DB file path" in out
    # Per-table count rows
    for label in (
        "STIX objects",
        "Relationships",
        "Module runs",
        "Score events",
        "Analyst notes",
        "Badge events",
    ):
        assert label in out, f"Missing row '{label}' in _render_db_status_table output"
    # Last-event rows
    assert "Last run" in out
    assert "Last note" in out
    assert "Last badge" in out
    # Size row
    assert "KB" in out or " B" in out or "DB file size" in out
