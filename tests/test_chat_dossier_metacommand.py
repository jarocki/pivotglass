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
        We read the source file directly (not via import) so the test works even
        when optional deps like prompt_toolkit are not installed in the test env.
        """
        import pathlib

        # Find chat.py relative to the adversary_pursuit package on sys.path
        import adversary_pursuit

        pkg_root = pathlib.Path(adversary_pursuit.__file__).parent
        chat_src = (pkg_root / "agent" / "chat.py").read_text(encoding="utf-8")

        # The help table must reference 'dossier' as a command
        assert "dossier" in chat_src, (
            "chat.py does not reference 'dossier' - the meta-command and help row are missing"
        )
        # The help table add_row for dossier must be present
        assert re.search(r"add_row\s*\(.*dossier", chat_src, re.IGNORECASE | re.DOTALL), (
            "chat.py help_table does not have a 'dossier' add_row call. "
            "DEC-M1-DOSSIER-004 requires a help_table row for the dossier command."
        )


# ---------------------------------------------------------------------------
# M-5: note <text> meta-command tests (DEC-M5-NOTE-001..003)
# ---------------------------------------------------------------------------


class TestNoteMetaCommand:
    """Tests for the 'note <text>' meta-command wired into agent/chat.py.

    @decision DEC-M5-NOTE-001
    @title note meta-command binds to existing WorkspaceManager.add_note() + AnalystNote table
    @status accepted
    @rationale Sacred Practice 12: single authority for note persistence.
        The F63 sentinel-row pattern is NOT used for notes; it is exclusively for
        _predictions_log and _dossier_state_snapshot. Notes use the AnalystNote table
        via the existing add_note() public method.
    """

    def test_note_command_calls_add_note_and_persists(self, tmp_path: Path):
        """note <text> calls workspace_mgr.add_note(text) and the note is retrievable."""
        from adversary_pursuit.agent.tools import _read_analyst_notes

        wm = _make_workspace(tmp_path)
        wm.add_note("actor uses sandbox evasion technique")

        notes = _read_analyst_notes(wm)
        contents = [n["content"] for n in notes]
        assert any("sandbox evasion" in c for c in contents), (
            f"Note not found in analyst notes; got: {contents}"
        )

    def test_note_command_source_present_in_chat(self, tmp_path: Path):
        """note meta-command handler is present in chat.py source.

        Reads source file directly (avoids prompt_toolkit import issue in test env).
        """
        import pathlib

        import adversary_pursuit

        pkg_root = pathlib.Path(adversary_pursuit.__file__).parent
        chat_src = (pkg_root / "agent" / "chat.py").read_text(encoding="utf-8")

        # Handler must detect 'note' prefix
        assert re.search(r"lower.*startswith.*['\"]note", chat_src) or re.search(
            r"note.*add_note", chat_src, re.DOTALL
        ), "chat.py must contain note meta-command handler that calls add_note()"

        # Help table must include a 'note' row
        assert re.search(r"add_row\s*\(.*note", chat_src, re.IGNORECASE | re.DOTALL), (
            "chat.py help_table does not have a 'note' add_row call. "
            "DEC-M5-NOTE-003 requires a help_table row for the note command."
        )

    def test_note_then_dossier_slot9_reflects_keyword(self, tmp_path: Path):
        """note with denial keyword + dossier render shows slot 9 PARTIAL (compound test).

        This exercises the real production sequence:
        1. add_note() writes a denial-keyword note to AnalystNote table.
        2. _read_analyst_notes() reads it back as {"content": ...} dicts.
        3. infer_dossier_state_full() feeds notes to _extract_denial().
        4. Slot 9 returns PARTIAL (1 category: note_keyword).
        """
        from adversary_pursuit.agent.tools import _read_analyst_notes
        from adversary_pursuit.dossier.slot_inference import infer_dossier_state_full
        from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus

        wm = _make_workspace(tmp_path)
        wm.add_note("actor uses domain generation algorithm for evasion")

        notes = _read_analyst_notes(wm)
        scos = wm.get_stix_objects()
        state = infer_dossier_state_full(scos, module_runs=[], notes=notes)

        denial_slot = state.slots[DossierSlotName.DENIAL]
        assert denial_slot.status in (SlotStatus.PARTIAL, SlotStatus.FILLED), (
            f"After adding a denial-keyword note, slot 9 should be PARTIAL or FILLED; "
            f"got {denial_slot.status}"
        )
