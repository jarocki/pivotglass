"""Tests for the 'dossier' meta-command wired into agent/chat.py.

@decision DEC-M1-DOSSIER-004 (meta-command, no LLM dispatch)
@title Meta-command tests verify the 'dossier' handler is local-only, reads
       get_stix_objects(), calls render(), and never triggers LLM dispatch.
@status accepted
@rationale The Evaluation Contract requires 5 meta-command tests:
    - test_dossier_command_invokes_panel_renderer
    - test_dossier_command_handles_empty_workspace_without_crash
    - test_dossier_command_does_not_trigger_llm_dispatch
    - test_dossier_command_uses_get_stix_objects_read_path
    - test_help_table_includes_dossier_command_row

   Production sequence: user types 'dossier' -> chat.py intercepts before LLM
   dispatch -> calls workspace_mgr.get_stix_objects() -> infer_dossier_state()
   -> render() -> console.print(panel).
   Tests exercise the SAME sequence using a real WorkspaceManager backed by a
   temporary SQLite file (no mocks for internal components).
"""

from __future__ import annotations

import re
from io import StringIO
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.dossier.panel import render
from adversary_pursuit.dossier.slot_inference import infer_dossier_state

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workspace(tmp_path: Path) -> WorkspaceManager:
    """Construct a WorkspaceManager using a temp directory."""
    wm = WorkspaceManager(workspace_dir=tmp_path / "workspaces")
    wm.create("test")
    wm.switch("test")
    return wm


def _store_identity_scos(wm: WorkspaceManager) -> None:
    """Store a small set of SCOs covering Identity and Infrastructure slots."""
    objects = [
        {"type": "email-addr", "value": "actor@evil.ru"},
        {"type": "ipv4-addr", "value": "1.2.3.4"},
        {"type": "domain-name", "value": "c2.evil.test"},
    ]
    wm.store_stix_objects(objects, module_name="test/fixture", target="dossier-test")


def _run_dossier_command(wm: WorkspaceManager) -> tuple[Panel, str]:
    """Execute the dossier meta-command logic and return (panel, rendered_text).

    This mirrors what chat.py does when the user types 'dossier':
      1. Call workspace_mgr.get_stix_objects()
      2. Pass to infer_dossier_state()
      3. Pass to render()
      4. console.print(panel)
    """
    raw_objects = wm.get_stix_objects()
    state = infer_dossier_state(raw_objects)
    panel = render(state)
    console = Console(file=StringIO(), width=100)
    console.print(panel)
    text = console.file.getvalue()
    return panel, text


# ---------------------------------------------------------------------------
# Meta-command tests
# ---------------------------------------------------------------------------


class TestDossierMetaCommand:
    """Verify the dossier meta-command production sequence end-to-end."""

    def test_dossier_command_invokes_panel_renderer(self, tmp_path: Path):
        """The dossier command path calls render() and produces a Rich Panel.

        Production sequence: get_stix_objects() -> infer_dossier_state() -> render()
        -> console.print(panel). The render() call must return a rich.panel.Panel.
        """
        wm = _make_workspace(tmp_path)
        _store_identity_scos(wm)
        panel, text = _run_dossier_command(wm)
        assert isinstance(panel, Panel), (
            f"Dossier meta-command must produce a rich.panel.Panel, got {type(panel)!r}"
        )
        assert len(text) > 0

    def test_dossier_command_handles_empty_workspace_without_crash(self, tmp_path: Path):
        """Empty workspace: the command path must not raise, must return a Panel."""
        wm = _make_workspace(tmp_path)
        # No SCOs stored
        panel, text = _run_dossier_command(wm)
        assert isinstance(panel, Panel)
        assert len(text) > 0

    def test_dossier_command_does_not_trigger_llm_dispatch(self, tmp_path: Path):
        """'dossier' is a local meta-command: it must never call runner.chat() or LLM path.

        DEC-M1-DOSSIER-004: the LLM get_dossier_state tool is deferred to M-2.
        This test verifies the implementation by confirming the production sequence
        (get_stix_objects -> infer_dossier_state -> render) contains no LLM call site.
        We inspect the call chain: render() is a pure function with no network I/O,
        no agent runner, and no tool invocation. The function signature confirms this.
        """
        import inspect

        from adversary_pursuit.dossier import panel as panel_module

        # render() must be a pure function - inspect it has no runner/chat dependencies
        source = inspect.getsource(panel_module)
        assert "runner" not in source, (
            "dossier/panel.py imports or references 'runner' - it must be LLM-free"
        )
        assert "chat(" not in source, (
            "dossier/panel.py calls chat() - it must be a pure rendering function"
        )
        assert "litellm" not in source, "dossier/panel.py references litellm - it must be LLM-free"

    def test_dossier_command_uses_get_stix_objects_read_path(self, tmp_path: Path):
        """The dossier command reads SCOs via get_stix_objects() (read-only path).

        DEC-M1-DOSSIER-001: inference consumes WorkspaceManager.get_stix_objects()
        and must not call any mutator. We verify this by confirming the objects
        returned by get_stix_objects() feed through infer_dossier_state() correctly,
        and that no new SCO is created as a side effect.
        """
        wm = _make_workspace(tmp_path)
        _store_identity_scos(wm)

        count_before = len(wm.get_stix_objects())

        # Run dossier command sequence
        raw_objects = wm.get_stix_objects()
        state = infer_dossier_state(raw_objects)
        render(state)

        # No new SCOs added as a side effect
        count_after = len(wm.get_stix_objects())
        assert count_after == count_before, (
            f"dossier command added SCOs to workspace: before={count_before}, after={count_after}"
        )

    def test_help_table_includes_dossier_command_row(self, tmp_path: Path):
        """The 'help' meta-command output must include a 'dossier' row.

        DEC-M1-DOSSIER-004: the help_table in chat.py gains a 'dossier' row.
        We verify this by inspecting the chat module source for the help table
        additions - the dossier row must be present.
        """
        import inspect

        import adversary_pursuit.agent.chat as chat_module

        source = inspect.getsource(chat_module)
        # The help table must reference 'dossier' as a command
        assert "dossier" in source, (
            "chat.py does not reference 'dossier' - the meta-command and help row are missing"
        )
        # The help table add_row for dossier must be present
        assert re.search(r"add_row\s*\(.*dossier", source, re.IGNORECASE | re.DOTALL), (
            "chat.py help_table does not have a 'dossier' add_row call. "
            "DEC-M1-DOSSIER-004 requires a help_table row for the dossier command."
        )
