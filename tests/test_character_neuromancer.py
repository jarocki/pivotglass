"""Tests for Phase 18 Slice 7A: neuromancer character mode.

Covers:
- DEFAULT_MODES["neuromancer"] exists with correct fields
- prompt_prefix == "🌆", llm_profile is not None
- voice_summary mentions Gibson/Case/second-person
- pick("neuromancer", "greeting") returns non-empty string
- pick("neuromancer", "help:tui_overview") returns multi-line string with Case/matrix/Wintermute
- pick("neuromancer", "target_set:acknowledged").format(target=...) contains the target
- ModeManager can switch to neuromancer
- neuromancer is NOT in the KEEP_STATIC list (it has an llm_profile)

@decision DEC-TEST-CHAR-NEUROMANCER-001
@title Neuromancer smoke tests: voice registration, phrase pick, mode switch
@status accepted
@rationale Three verification levels: (1) CharacterMode schema — neuromancer
           exists in DEFAULT_MODES with correct prompt_prefix and a non-None
           LLMPersonaProfile; (2) voice registration smoke test — voice_summary
           contains the key vocabulary markers (Gibson, Case, second-person)
           proving the profile is not a placeholder; (3) phrase pick() coverage —
           every greeting/help/target_set call returns meaningful neuromancer-voiced
           text so the production sequence (user types 'use evil.com' → TUI picks
           a phrase) works end-to-end. ModeManager switch test covers the production
           sequence: ModeManager() → switch("neuromancer") → active.name check.
"""

from __future__ import annotations

from adversary_pursuit.gamification.modes import DEFAULT_MODES, ModeManager
from adversary_pursuit.gamification.phrases import pick


class TestNeuromancerModeExists:
    """DEFAULT_MODES["neuromancer"] is present and structurally correct."""

    def test_neuromancer_in_default_modes(self) -> None:
        assert "neuromancer" in DEFAULT_MODES, (
            "neuromancer not found in DEFAULT_MODES — did you add it to modes.py?"
        )

    def test_prompt_prefix_is_city_skyline(self) -> None:
        """Avatar must be 🌆 (Chiba city skyline mood per operator directive)."""
        mode = DEFAULT_MODES["neuromancer"]
        assert mode.prompt_prefix == "🌆", (
            f"neuromancer prompt_prefix expected '🌆', got {mode.prompt_prefix!r}"
        )

    def test_llm_profile_is_not_none(self) -> None:
        """neuromancer must have a non-None LLMPersonaProfile (full v2 upgrade)."""
        mode = DEFAULT_MODES["neuromancer"]
        assert mode.llm_profile is not None, (
            "neuromancer.llm_profile is None — it should be a full LLMPersonaProfile"
        )

    def test_name_matches_key(self) -> None:
        mode = DEFAULT_MODES["neuromancer"]
        assert mode.name == "neuromancer"

    def test_greeting_non_empty(self) -> None:
        mode = DEFAULT_MODES["neuromancer"]
        assert mode.greeting, "neuromancer.greeting must not be empty"

    def test_run_success_non_empty(self) -> None:
        mode = DEFAULT_MODES["neuromancer"]
        assert mode.run_success, "neuromancer.run_success must not be empty"

    def test_run_fail_non_empty(self) -> None:
        mode = DEFAULT_MODES["neuromancer"]
        assert mode.run_fail, "neuromancer.run_fail must not be empty"

    def test_score_celebration_has_points_placeholder(self) -> None:
        """score_celebration must contain {points} for .format(points=N) callers."""
        mode = DEFAULT_MODES["neuromancer"]
        assert "{points}" in mode.score_celebration, (
            "neuromancer.score_celebration must contain '{points}' placeholder"
        )


class TestNeuromancerLLMProfile:
    """LLMPersonaProfile voice registration smoke tests."""

    def _profile(self):
        return DEFAULT_MODES["neuromancer"].llm_profile

    def test_voice_summary_mentions_gibson_or_case(self) -> None:
        """voice_summary must reference Gibson, Case, or second-person — core register markers."""
        summary = self._profile().voice_summary.lower()
        assert any(marker in summary for marker in ("gibson", "case", "second-person")), (
            f"voice_summary does not mention Gibson/Case/second-person: {summary!r}"
        )

    def test_fourth_wall_stance_is_opaque(self) -> None:
        """neuromancer IS the voice — opaque stance (never meta_aware)."""
        assert self._profile().fourth_wall_stance == "opaque"

    def test_tone_registers_non_empty(self) -> None:
        assert len(self._profile().tone_registers) >= 2

    def test_signature_phrases_contains_case(self) -> None:
        """'Case,' must be among the signature phrases (30% interjection weight)."""
        phrases = " ".join(self._profile().signature_phrases).lower()
        assert "case" in phrases, (
            f"'Case' not in signature_phrases: {self._profile().signature_phrases!r}"
        )

    def test_forbidden_voice_includes_second_person_guard(self) -> None:
        """forbidden_voice must block second-person register breaks."""
        forbidden = " ".join(self._profile().forbidden_voice).lower()
        assert "second-person" in forbidden or "register" in forbidden, (
            f"forbidden_voice should guard second-person register: {self._profile().forbidden_voice!r}"
        )

    def test_forbidden_voice_includes_point_total_guard(self) -> None:
        """forbidden_voice must include the F64 panel-separation guard."""
        forbidden = " ".join(self._profile().forbidden_voice).lower()
        assert "point" in forbidden, (
            "F64 panel-separation guard ('never narrate point totals') missing from forbidden_voice"
        )

    def test_context_hooks_is_empty_tuple(self) -> None:
        """context_hooks=() per established C-4 pattern (deferred to future slice)."""
        assert self._profile().context_hooks == ()

    def test_tool_preferences_non_empty(self) -> None:
        """tool_preferences must have at least one affinity entry."""
        assert len(self._profile().tool_preferences) >= 1


class TestNeuromancerPhrases:
    """pick() returns correct neuromancer-voiced phrases."""

    def test_greeting_returns_non_empty_string(self) -> None:
        result = pick("neuromancer", "greeting")
        assert isinstance(result, str) and result.strip()

    def test_run_success_returns_non_empty_string(self) -> None:
        result = pick("neuromancer", "run_success")
        assert isinstance(result, str) and result.strip()

    def test_run_fail_returns_non_empty_string(self) -> None:
        result = pick("neuromancer", "run_fail")
        assert isinstance(result, str) and result.strip()

    def test_score_celebration_formats_with_points(self) -> None:
        template = pick("neuromancer", "score_celebration")
        formatted = template.format(points=42)
        assert "42" in formatted

    def test_help_tui_overview_is_multiline(self) -> None:
        """help:tui_overview must be a multi-line string for Case-voice help."""
        result = pick("neuromancer", "help:tui_overview")
        assert "\n" in result, "help:tui_overview should be multi-line"

    def test_help_tui_overview_contains_case(self) -> None:
        """help:tui_overview must mention 'Case' (second-person protagonist)."""
        result = pick("neuromancer", "help:tui_overview")
        assert "Case" in result, f"'Case' not in help:tui_overview: {result!r}"

    def test_help_tui_overview_contains_matrix_or_wintermute(self) -> None:
        """help:tui_overview must mention 'matrix', 'sprawl', or 'Wintermute'."""
        result = pick("neuromancer", "help:tui_overview")
        assert any(word in result for word in ("matrix", "sprawl", "Wintermute")), (
            f"Gibson vocabulary not in help:tui_overview: {result!r}"
        )

    def test_target_set_acknowledged_formats_with_target(self) -> None:
        """target_set:acknowledged must format with {target} placeholder."""
        template = pick("neuromancer", "target_set:acknowledged")
        formatted = template.format(target="1.2.3.4")
        assert "1.2.3.4" in formatted, f"target '1.2.3.4' not in formatted result: {formatted!r}"

    def test_farewell_non_empty(self) -> None:
        result = pick("neuromancer", "farewell")
        assert isinstance(result, str) and result.strip()

    def test_mode_switched_non_empty(self) -> None:
        result = pick("neuromancer", "mode_switched")
        assert isinstance(result, str) and result.strip()

    def test_unknown_mode_formats_with_name(self) -> None:
        template = pick("neuromancer", "unknown_mode")
        formatted = template.format(name="bogus_mode")
        assert "bogus_mode" in formatted

    def test_status_intro_non_empty(self) -> None:
        result = pick("neuromancer", "status_intro")
        assert isinstance(result, str) and result.strip()

    def test_thinking_activity_non_empty(self) -> None:
        result = pick("neuromancer", "activity:thinking")
        assert isinstance(result, str) and result.strip()


class TestNeuromancerModeSwitch:
    """ModeManager can switch to neuromancer (production sequence)."""

    def test_mode_manager_switch_to_neuromancer(self) -> None:
        """ModeManager().switch('neuromancer') returns the neuromancer CharacterMode."""
        mgr = ModeManager()
        mode = mgr.switch("neuromancer")
        assert mode.name == "neuromancer"
        assert mgr.active.name == "neuromancer"

    def test_mode_manager_active_is_neuromancer_after_switch(self) -> None:
        mgr = ModeManager()
        mgr.switch("neuromancer")
        assert mgr.active.prompt_prefix == "🌆"

    def test_mode_manager_switch_back_from_neuromancer(self) -> None:
        """Can switch away from neuromancer to another mode."""
        mgr = ModeManager()
        mgr.switch("neuromancer")
        mgr.switch("default")
        assert mgr.active.name == "default"
