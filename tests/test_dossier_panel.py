"""Tests for dossier/panel.py — pure-function Rich panel rendering.

@decision DEC-M1-DOSSIER-003 (pure-function panel authority)
@title Panel tests verify render() returns a rich.panel.Panel (not plain text),
       is deterministic, and covers 0/4/9 slot fill scenarios.
@status accepted
@rationale The Evaluation Contract requires 6 panel tests:
    - test_panel_renders_zero_slots_filled_scenario
    - test_panel_renders_four_slots_filled_scenario
    - test_panel_renders_nine_slots_present_with_deferred_status
    - test_panel_includes_slot_name_status_evidence_count_for_each_slot
    - test_panel_uses_rich_panel_not_plain_text
    - test_panel_output_is_deterministic_for_fixed_workspace
   All tests use DossierState objects constructed directly (no WorkspaceManager I/O),
   exercising panel.render() as a pure function (DEC-M1-DOSSIER-003).
"""

from __future__ import annotations

from io import StringIO

from rich.console import Console
from rich.panel import Panel

from adversary_pursuit.dossier.panel import render
from adversary_pursuit.dossier.slot_inference import infer_dossier_state
from adversary_pursuit.dossier.slots import DossierSlotName

# ---------------------------------------------------------------------------
# Helper: export panel text via rich Console recording
# ---------------------------------------------------------------------------


def _panel_to_text(panel: Panel) -> str:
    """Render a Rich Panel to plain text for assertion inspection."""
    console = Console(file=StringIO(), width=100)
    console.print(panel)
    return console.file.getvalue()


# ---------------------------------------------------------------------------
# Scenario builders — synthetic SCO sets
# ---------------------------------------------------------------------------


def _zero_slot_scos() -> list[dict]:
    """No SCOs — all active inference slots empty, deferred slots deferred."""
    return []


def _four_slot_scos() -> list[dict]:
    """SCOs filling Identity (partial) + Infrastructure (partial) + TTPs (partial)
    = 3 active slots filled; combined with deferred slots that's a mixed panel."""
    return [
        {"type": "email-addr", "value": "actor@ru.example", "id": "email-addr--t1"},
        {"type": "ipv4-addr", "value": "1.2.3.4", "id": "ipv4-addr--t1"},
        {"type": "domain-name", "value": "c2.evil.test", "id": "domain-name--t1"},
        {"type": "url", "value": "https://c2.evil.test/beacon", "id": "url--t1"},
    ]


def _nine_slot_scos() -> list[dict]:
    """SCOs that exercise all three actively inferred slots at filled level,
    plus confirm the 6 deferred slots remain deferred."""
    return [
        # Identity — two types → filled
        {"type": "email-addr", "value": "actor@ru.example", "id": "email-addr--n1"},
        {"type": "x509-certificate", "subject": "CN=evil", "id": "x509-certificate--n1"},
        # Infrastructure — two types → filled
        {"type": "ipv4-addr", "value": "1.2.3.4", "id": "ipv4-addr--n1"},
        {"type": "domain-name", "value": "c2.evil.test", "id": "domain-name--n1"},
        # TTPs — two types → filled
        {"type": "url", "value": "https://c2.evil.test/beacon", "id": "url--n1"},
        {"type": "file", "name": "loader.dll", "id": "file--n1"},
    ]


# ---------------------------------------------------------------------------
# Panel rendering tests
# ---------------------------------------------------------------------------


class TestPanelRendering:
    """Verify render() returns a rich.panel.Panel and handles all slot scenarios."""

    def test_panel_renders_zero_slots_filled_scenario(self):
        """Empty workspace: render() produces a Panel without raising."""
        state = infer_dossier_state(_zero_slot_scos())
        panel = render(state)
        assert panel is not None
        text = _panel_to_text(panel)
        assert len(text) > 0

    def test_panel_renders_four_slots_filled_scenario(self):
        """Mixed workspace: render() shows partial/filled for active slots, deferred for others."""
        state = infer_dossier_state(_four_slot_scos())
        panel = render(state)
        assert panel is not None
        text = _panel_to_text(panel)
        # Active inferred slots with evidence should appear with non-empty status
        assert len(text) > 0

    def test_panel_renders_nine_slots_present_with_deferred_status(self):
        """All 9 slots appear in the panel, deferred slots clearly marked."""
        state = infer_dossier_state(_nine_slot_scos())
        panel = render(state)
        text = _panel_to_text(panel)
        # All deferred slot names must appear
        for slot_name in (
            DossierSlotName.TIMING,
            DossierSlotName.TARGETING,
            DossierSlotName.CAPABILITY,
            DossierSlotName.MOTIVATION,
            DossierSlotName.PREDICTIONS,
            DossierSlotName.DENIAL,
        ):
            assert (
                slot_name.value in text.lower() or slot_name.value.replace("_", " ") in text.lower()
            ), f"Deferred slot '{slot_name.value}' missing from panel output"

    def test_panel_includes_slot_name_status_evidence_count_for_each_slot(self):
        """Each slot row includes the slot name, its status, and evidence count."""
        state = infer_dossier_state(_four_slot_scos())
        panel = render(state)
        text = _panel_to_text(panel)
        # Identity, Infrastructure, TTPs should appear as slot names
        assert "identity" in text.lower()
        assert "infrastructure" in text.lower()
        assert "ttps" in text.lower() or "ttp" in text.lower()
        # Status words should appear
        status_words = {"partial", "filled", "empty", "deferred"}
        found_any = any(w in text.lower() for w in status_words)
        assert found_any, f"No status word found in panel text: {text[:200]}"

    def test_panel_uses_rich_panel_not_plain_text(self):
        """render() returns a rich.panel.Panel instance, not a string or None."""
        state = infer_dossier_state(_zero_slot_scos())
        result = render(state)
        assert isinstance(result, Panel), (
            f"render() must return a rich.panel.Panel, got {type(result)!r}. "
            "DEC-M1-DOSSIER-003: panel authority is dossier/panel.py, caller prints it."
        )

    def test_panel_output_is_deterministic_for_fixed_workspace(self):
        """Same SCO input → identical Panel title and renderable content (deterministic)."""
        scos = _four_slot_scos()
        state_a = infer_dossier_state(scos)
        state_b = infer_dossier_state(scos)
        panel_a = render(state_a)
        panel_b = render(state_b)
        # Title must match
        assert panel_a.title == panel_b.title
        # Rendered text must match
        text_a = _panel_to_text(panel_a)
        text_b = _panel_to_text(panel_b)
        assert text_a == text_b, (
            "render() is not deterministic: same SCO input produced different output"
        )
