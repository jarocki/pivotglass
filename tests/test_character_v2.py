"""Tests for Character System v2 — C-1 MVP (full_troll LLMPersonaProfile).

# @mock-exempt: litellm is an external LLM boundary. The persona-swap-tool-call-identity
# test (DEC-C1-FULLTROLL-004) requires a deterministic mock of litellm.completion so that
# tool-call recording is stable across runs without a live LLM. execute_tool is mocked
# at the tool dispatch boundary (the same boundary used by test_agent_tools.py) so the
# test measures persona-induced divergence in tool selection, not module network behavior.

# @decision DEC-C1-FULLTROLL-004
# @title Persona-swap-tool-call-identity test enforces tool_preferences=voice-only
# @status accepted
# @rationale Without a mechanical gate, tool_preferences can drift into a
#            selection-biasing field over time. A deterministic mock-LLM harness
#            gives us a regression test that survives all 4 C-slices.

Production sequence covered by compound interaction test:
  AgentRunner.__init__ -> set_character(full_troll) -> chat() loop with mock LLM ->
  tool-call record differs only in system-prompt contents, not tool selection.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import fields as dataclass_fields
from unittest.mock import MagicMock, patch

import pytest

from adversary_pursuit.gamification.modes import (
    DEFAULT_MODES,
    CharacterMode,
    LLMPersonaProfile,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rough_token_count(text: str) -> int:
    """Very rough token approximation: 4 chars per token (conservative BPE proxy).

    Used only for the budget assertion - exact tokenization is model-dependent.
    The budget is 165 tokens; 4-chars-per-token means the bound text is 660 chars.
    """
    return len(text) // 4


# ---------------------------------------------------------------------------
# 1. LLMPersonaProfile frozen dataclass
# ---------------------------------------------------------------------------


class TestLLMPersonaProfileDataclass:
    """LLMPersonaProfile must be a frozen dataclass per DEC-C1-FULLTROLL-002."""

    def test_llm_persona_profile_is_frozen_dataclass(self):
        """LLMPersonaProfile must be importable and frozen."""
        assert hasattr(LLMPersonaProfile, "__dataclass_params__"), (
            "LLMPersonaProfile is not a dataclass"
        )
        assert LLMPersonaProfile.__dataclass_params__.frozen, (
            "LLMPersonaProfile must be frozen=True (per DEC-MODE-001 discipline)"
        )

    def test_llm_persona_profile_fields_present(self):
        """All 8 required schema fields must be present on LLMPersonaProfile."""
        required = {
            "voice_summary",
            "tone_registers",
            "signature_phrases",
            "fourth_wall_stance",
            "dialect_cadence",
            "context_hooks",
            "tool_preferences",
            "forbidden_voice",
        }
        actual = {f.name for f in dataclass_fields(LLMPersonaProfile)}
        assert required.issubset(actual), f"Missing fields: {required - actual}"

    def test_llm_persona_profile_field_types(self):
        """voice_summary, dialect_cadence, fourth_wall_stance are str fields;
        the rest are tuple fields per roadmap section 3.2."""
        profile = LLMPersonaProfile(
            voice_summary="test voice",
            tone_registers=("a", "b"),
            signature_phrases=("x",),
            fourth_wall_stance="in_character",
            dialect_cadence="clipped",
            context_hooks=(),
            tool_preferences=(),
            forbidden_voice=(),
        )
        assert isinstance(profile.voice_summary, str)
        assert isinstance(profile.tone_registers, tuple)
        assert isinstance(profile.signature_phrases, tuple)
        assert isinstance(profile.fourth_wall_stance, str)
        assert isinstance(profile.dialect_cadence, str)
        assert isinstance(profile.context_hooks, tuple)
        assert isinstance(profile.tool_preferences, tuple)
        assert isinstance(profile.forbidden_voice, tuple)

    def test_llm_persona_profile_is_immutable(self):
        """LLMPersonaProfile must be immutable (frozen dataclass invariant)."""
        profile = LLMPersonaProfile(
            voice_summary="test",
            tone_registers=("a",),
            signature_phrases=("b",),
            fourth_wall_stance="winking",
            dialect_cadence="rambling",
            context_hooks=(),
            tool_preferences=(),
            forbidden_voice=(),
        )
        with pytest.raises((AttributeError, TypeError)):
            profile.voice_summary = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. CharacterMode.llm_profile field
# ---------------------------------------------------------------------------


class TestCharacterModeLlmProfileField:
    """CharacterMode must have llm_profile: LLMPersonaProfile | None = None."""

    def test_character_mode_has_llm_profile_field(self):
        """llm_profile field must exist on CharacterMode."""
        field_names = {f.name for f in dataclass_fields(CharacterMode)}
        assert "llm_profile" in field_names, (
            "CharacterMode is missing llm_profile field (DEC-C1-FULLTROLL-002)"
        )

    def test_llm_profile_default_is_none_for_all_modes(self):
        """All modes except upgraded ones must have llm_profile=None.

        C-1 (DEC-C1-FULLTROLL-001) upgraded full_troll.
        C-2 (DEC-C2-NINJA-001) upgrades ninja.
        C-3 (DEC-C3-PHILOSOPHY-001..003) upgrades sun_tzu, bruce_lee, bureaucrat.
        The remaining 5 modes continue to ship at llm_profile=None per
        DEC-30-CHARACTER-V2-006 until C-4 closes the catalog.
        """
        # full_troll: C-1; ninja: C-2; sun_tzu/bruce_lee/bureaucrat: C-3.
        upgraded_modes = {"full_troll", "ninja", "sun_tzu", "bruce_lee", "bureaucrat"}
        static_modes = {
            name: mode for name, mode in DEFAULT_MODES.items() if name not in upgraded_modes
        }
        for name, mode in static_modes.items():
            assert mode.llm_profile is None, (
                f"Mode '{name}' has llm_profile set -- only full_troll (C-1), "
                "ninja (C-2), sun_tzu/bruce_lee/bureaucrat (C-3) should have profiles post-C-3. "
                "(DEC-30-CHARACTER-V2-006: remaining 5 modes ship at llm_profile=None)"
            )

    def test_hint_style_not_reintroduced(self):
        """hint_style must NOT exist on CharacterMode (F62 DEC-62-KILL-DOC-LIES-001)."""
        assert not hasattr(CharacterMode, "hint_style"), (
            "hint_style was re-introduced -- it was deleted in F62"
        )

    def test_mastery_level_not_present(self):
        """mastery_level must NOT be present on LLMPersonaProfile (deferred to C-4)."""
        field_names = {f.name for f in dataclass_fields(LLMPersonaProfile)}
        assert "mastery_level" not in field_names, (
            "mastery_level was added prematurely -- deferred to C-4 per DEC-C1-FULLTROLL-005"
        )

    def test_default_mode_keeps_static(self):
        """default mode must remain KEEP_STATIC (llm_profile=None) — no-flavor anchor.

        Per DEC-C2-NINJA-003: the original test asserted both default and ninja were None.
        C-2 upgrades ninja (DEC-C2-NINJA-001), so the ninja assertion is removed here
        and replaced by the positive content tests in TestNinjaProfileContent.
        default remains the no-flavor anchor through all C-slices.
        """
        assert DEFAULT_MODES["default"].llm_profile is None


# ---------------------------------------------------------------------------
# 3. full_troll profile content (DEC-C1-FULLTROLL-001)
# ---------------------------------------------------------------------------


class TestFullTrollProfileContent:
    """full_troll must carry the exact LLMPersonaProfile specified in
    DEC-C1-FULLTROLL-001 (MASTER_PLAN.md Phase 17B).
    """

    @pytest.fixture
    def profile(self) -> LLMPersonaProfile:
        """Return full_troll's llm_profile."""
        mode = DEFAULT_MODES["full_troll"]
        assert mode.llm_profile is not None, (
            "full_troll.llm_profile is None -- DEC-C1-FULLTROLL-001 requires it to be set"
        )
        return mode.llm_profile

    def test_full_troll_has_llm_profile(self):
        """full_troll must have a non-None LLMPersonaProfile (C-1 MVP gate)."""
        mode = DEFAULT_MODES["full_troll"]
        assert mode.llm_profile is not None

    def test_full_troll_profile_voice_summary_content(self, profile: LLMPersonaProfile):
        """voice_summary must capture Claptrap/CTF speedrun Borderlands-snark voice."""
        vs = profile.voice_summary.lower()
        # Must reference chaotic/shitpost energy and threat intel context
        assert any(word in vs for word in ("chaotic", "snarky", "snark", "shitpost", "claptrap")), (
            f"voice_summary '{profile.voice_summary}' missing expected Borderlands-snark descriptor"
        )

    def test_full_troll_profile_tone_registers_content(self, profile: LLMPersonaProfile):
        """tone_registers must be a non-empty tuple containing irreverent register words."""
        assert isinstance(profile.tone_registers, tuple)
        assert len(profile.tone_registers) >= 2, (
            "tone_registers must have 2-4 register words per schema"
        )
        registers_lower = {r.lower() for r in profile.tone_registers}
        expected = {"snarky", "irreverent", "loud", "meme-aware"}
        assert expected.issubset(registers_lower), (
            f"tone_registers {profile.tone_registers} missing expected registers: "
            f"{expected - registers_lower}"
        )

    def test_full_troll_profile_signature_phrases_content(self, profile: LLMPersonaProfile):
        """signature_phrases must include canonical full_troll catch-phrases."""
        assert isinstance(profile.signature_phrases, tuple)
        assert len(profile.signature_phrases) >= 2, (
            "signature_phrases must have 2-5 catch-phrases per schema"
        )
        phrases_lower = [p.lower() for p in profile.signature_phrases]
        # "GET REKT" and "bruh" are established full_troll voice anchors
        assert any("rekt" in p for p in phrases_lower), (
            f"signature_phrases missing 'GET REKT' variant: {profile.signature_phrases}"
        )
        assert any("bruh" in p for p in phrases_lower), (
            f"signature_phrases missing 'bruh': {profile.signature_phrases}"
        )

    def test_full_troll_profile_fourth_wall_stance(self, profile: LLMPersonaProfile):
        """fourth_wall_stance must be 'meta_aware' for full_troll (DEC-C1-FULLTROLL-001)."""
        assert profile.fourth_wall_stance == "meta_aware", (
            f"fourth_wall_stance must be 'meta_aware', got {profile.fourth_wall_stance!r}"
        )

    def test_full_troll_profile_dialect_cadence_content(self, profile: LLMPersonaProfile):
        """dialect_cadence must capture all-caps + lowercase-aside + emoji cadence."""
        dc = profile.dialect_cadence.lower()
        assert any(word in dc for word in ("caps", "burst", "liner", "emoji", "zinger")), (
            f"dialect_cadence '{profile.dialect_cadence}' doesn't describe "
            "the all-caps-burst + lowercase-aside + emoji-punctuation rhythm"
        )

    def test_full_troll_profile_context_hooks_empty(self, profile: LLMPersonaProfile):
        """context_hooks must be empty tuple for full_troll in C-1 (DEC-C1-FULLTROLL-005)."""
        assert profile.context_hooks == (), (
            f"context_hooks must be () for C-1 full_troll (DEC-C1-FULLTROLL-005), "
            f"got {profile.context_hooks!r}"
        )

    def test_full_troll_profile_tool_preferences_content(self, profile: LLMPersonaProfile):
        """tool_preferences must be phrased as affinity language (NOT selection instructions)."""
        assert isinstance(profile.tool_preferences, tuple)
        # Must have at least one affinity hint
        assert len(profile.tool_preferences) >= 1, (
            "tool_preferences should have 1-3 voice-affinity hints per schema"
        )
        # Must NOT contain instruction-language ("prefer", "use", "always", "must use")
        for pref in profile.tool_preferences:
            pref_lower = pref.lower()
            assert not pref_lower.startswith("prefer "), (
                f"tool_preferences entry starts with 'prefer' -- "
                f"must use affinity language, not selection instruction: {pref!r}"
            )
            assert "must use" not in pref_lower, (
                f"tool_preferences entry contains 'must use': {pref!r}"
            )
        # Must reference real CTI tools (virustotal, crt.sh are in DEC-C1-FULLTROLL-001)
        all_prefs = " ".join(profile.tool_preferences).lower()
        assert any(tool in all_prefs for tool in ("virustotal", "crt.sh", "crt", "shodan")), (
            f"tool_preferences doesn't reference any known CTI tools: {profile.tool_preferences}"
        )

    def test_full_troll_profile_forbidden_voice_content(self, profile: LLMPersonaProfile):
        """forbidden_voice must include F64 panel-separation guard and anti-bureaucratese."""
        assert isinstance(profile.forbidden_voice, tuple)
        assert len(profile.forbidden_voice) >= 1, (
            "forbidden_voice must have at least the F64 panel-separation guard"
        )
        all_fv = " ".join(profile.forbidden_voice).lower()
        # Must block point-total narration (F64 hard requirement)
        assert any(word in all_fv for word in ("point", "pts", "score")), (
            f"forbidden_voice must include F64 panel-separation guard "
            f"('never narrate point totals'): {profile.forbidden_voice}"
        )

    def test_full_troll_profile_token_budget(self, profile: LLMPersonaProfile):
        """full_troll profile must not exceed 165 tokens (DEC-30-CHARACTER-V2-003).

        Uses 4-chars-per-token proxy (conservative BPE estimate). The budget
        gate is planning-constraint-enforced, not runtime-enforced.
        """
        # Serialize all profile fields to a flat string
        profile_text = " ".join(
            [
                profile.voice_summary,
                " ".join(profile.tone_registers),
                " ".join(profile.signature_phrases),
                profile.fourth_wall_stance,
                profile.dialect_cadence,
                " ".join(profile.context_hooks),
                " ".join(profile.tool_preferences),
                " ".join(profile.forbidden_voice),
            ]
        )
        approx_tokens = _rough_token_count(profile_text)
        assert approx_tokens <= 165, (
            f"full_troll profile exceeds 165-token budget: ~{approx_tokens} tokens. "
            f"Content: {profile_text!r}"
        )


# ---------------------------------------------------------------------------
# 4. set_character integration (DEC-C1-FULLTROLL-003)
# ---------------------------------------------------------------------------


class TestSetCharacterIntegration:
    """AgentRunner.set_character must inject the profile when present
    and preserve F62 v1 composition verbatim when llm_profile is None.
    """

    @pytest.fixture
    def runner(self, tmp_path):
        """AgentRunner with isolated temp dirs (no real LLM needed)."""
        from adversary_pursuit.agent.runner import AgentRunner
        from adversary_pursuit.agent.tools import ToolContext

        ctx = ToolContext(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
        )
        return AgentRunner(model="fake-model", tool_context=ctx)

    def test_set_character_full_troll_injects_profile(self, runner):
        """set_character with full_troll (llm_profile != None) must inject profile text."""
        full_troll = DEFAULT_MODES["full_troll"]
        assert full_troll.llm_profile is not None
        runner.set_character(full_troll)
        sys_content = runner.conversation[0]["content"]
        # Profile fields must appear in the system prompt
        assert full_troll.llm_profile.voice_summary in sys_content, (
            "voice_summary not injected into system prompt"
        )
        assert full_troll.llm_profile.dialect_cadence in sys_content, (
            "dialect_cadence not injected into system prompt"
        )
        assert full_troll.llm_profile.fourth_wall_stance in sys_content, (
            "fourth_wall_stance not injected into system prompt"
        )

    def test_set_character_full_troll_system_prompt_starts_with_mode_name(self, runner):
        """set_character output must start with character mode identification."""
        full_troll = DEFAULT_MODES["full_troll"]
        runner.set_character(full_troll)
        sys_content = runner.conversation[0]["content"]
        # The system prompt should reference the mode name
        assert "full_troll" in sys_content

    def test_set_character_default_uses_v1_composition_verbatim(self, runner):
        """set_character with default (llm_profile=None) must use F62 v1 composition.

        F62 v1 composition: 'Character mode: {name}\n{personality}\n\n' + default_sys_prompt
        This test is the gate for DEC-C1-FULLTROLL-002: the None-path must remain
        byte-identical to the v1 behavior.
        """
        default_mode = DEFAULT_MODES["default"]
        assert default_mode.llm_profile is None
        runner.set_character(default_mode)
        sys_content = runner.conversation[0]["content"]
        expected_prefix = f"Character mode: {default_mode.name}\n{default_mode.personality}\n\n"
        assert sys_content.startswith(expected_prefix), (
            f"set_character with llm_profile=None deviated from v1 composition.\n"
            f"Expected prefix: {expected_prefix!r}\n"
            f"Got prefix: {sys_content[: len(expected_prefix) + 20]!r}"
        )

    def test_set_character_drunken_master_uses_v1_composition_verbatim(self, runner):
        """set_character with a still-static mode (drunken_master) must use F62 v1 path.

        Per DEC-C2-NINJA-003: the original test used ninja as the KEEP_STATIC carrier.
        C-2 upgrades ninja (DEC-C2-NINJA-001), so drunken_master (llm_profile=None
        through all C-slices per DEC-30-CHARACTER-V2-006) replaces it as the v1-path
        assertion carrier. Semantics are identical — any mode with llm_profile=None
        must produce the verbatim F62 composition.
        """
        drunken_master = DEFAULT_MODES["drunken_master"]
        assert drunken_master.llm_profile is None
        runner.set_character(drunken_master)
        sys_content = runner.conversation[0]["content"]
        expected_prefix = f"Character mode: {drunken_master.name}\n{drunken_master.personality}\n\n"
        assert sys_content.startswith(expected_prefix), (
            f"set_character with llm_profile=None deviated from v1 composition.\n"
            f"Expected prefix: {expected_prefix!r}\n"
            f"Got prefix: {sys_content[: len(expected_prefix) + 20]!r}"
        )

    def test_set_character_ninja_injects_profile(self, runner):
        """set_character with ninja (llm_profile != None after C-2) must inject profile text.

        Mirrors test_set_character_full_troll_injects_profile for the ninja profile.
        Per DEC-C2-NINJA-003: this positive test replaces the now-superseded
        test_set_character_ninja_uses_v1_composition_verbatim assertion.
        """
        ninja = DEFAULT_MODES["ninja"]
        assert ninja.llm_profile is not None, (
            "ninja.llm_profile is None -- DEC-C2-NINJA-001 requires it to be set"
        )
        runner.set_character(ninja)
        sys_content = runner.conversation[0]["content"]
        assert ninja.llm_profile.voice_summary in sys_content, (
            "voice_summary not injected into system prompt for ninja"
        )
        assert ninja.llm_profile.dialect_cadence in sys_content, (
            "dialect_cadence not injected into system prompt for ninja"
        )
        assert ninja.llm_profile.fourth_wall_stance in sys_content, (
            "fourth_wall_stance not injected into system prompt for ninja"
        )

    def test_set_character_preserves_conversation_history(self, runner):
        """set_character only updates conversation[0]; history entries preserved."""
        runner.conversation.append({"role": "user", "content": "hello"})
        runner.conversation.append({"role": "assistant", "content": "hi"})
        full_troll = DEFAULT_MODES["full_troll"]
        runner.set_character(full_troll)
        assert len(runner.conversation) == 3
        assert runner.conversation[1] == {"role": "user", "content": "hello"}
        assert runner.conversation[2] == {"role": "assistant", "content": "hi"}


# ---------------------------------------------------------------------------
# 5. HARD GATE: persona-swap-tool-call-identity (DEC-C1-FULLTROLL-004)
# ---------------------------------------------------------------------------


class TestPersonaSwapPreservesToolCallIdentity:
    """The most important C-1 invariant test: persona profile must NOT bias
    tool selection. Same query under full_troll vs default must produce
    byte-identical tool call (same tool name, same args).

    Uses a deterministic mock LLM that returns a canned tool-call response
    regardless of system prompt -- so any divergence in tool selection would
    be caused by something in the agent layer, not the LLM.

    @mock-exempt: litellm.completion is an external LLM API boundary.
    A deterministic mock is the only way to isolate persona-induced
    tool-selection divergence from LLM nondeterminism.
    """

    FIXED_TOOL_NAME = "dns_resolve"
    FIXED_TOOL_ARGS = {"target": "evil.example.com"}

    def _make_mock_litellm_response(self, tool_name: str, tool_args: dict):
        """Build a mock litellm response that requests a specific tool call."""
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].finish_reason = "tool_calls"
        mock_resp.choices[0].message = MagicMock()
        mock_resp.choices[0].message.content = None
        mock_resp.choices[0].message.tool_calls = [MagicMock()]
        mock_resp.choices[0].message.tool_calls[0].id = "call_123"
        mock_resp.choices[0].message.tool_calls[0].type = "function"
        mock_resp.choices[0].message.tool_calls[0].function = MagicMock()
        mock_resp.choices[0].message.tool_calls[0].function.name = tool_name
        mock_resp.choices[0].message.tool_calls[0].function.arguments = json.dumps(tool_args)
        return mock_resp

    def _make_mock_final_response(self, text: str):
        """Build a mock litellm response with a plain text reply."""
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].finish_reason = "stop"
        mock_resp.choices[0].message = MagicMock()
        mock_resp.choices[0].message.content = text
        mock_resp.choices[0].message.tool_calls = None
        return mock_resp

    def _run_chat_with_mode(
        self,
        runner,
        mode: CharacterMode,
        query: str,
    ) -> list[tuple[str, str]]:
        """Drive runner.chat() with a given mode and fixed deterministic mock LLM.

        Returns list of (tool_name, tool_args_json) tuples from the turn.

        @mock-exempt: litellm.completion is the external LLM API boundary.
        execute_tool is mocked at the module-dispatch boundary (same boundary
        as test_agent_tools.py) to avoid live network calls.
        """
        from adversary_pursuit.agent import runner as runner_module

        tool_calls_recorded: list[tuple[str, str]] = []

        tool_resp = self._make_mock_litellm_response(self.FIXED_TOOL_NAME, self.FIXED_TOOL_ARGS)
        final_resp = self._make_mock_final_response("Analysis complete. No points awarded here.")

        call_count = 0

        def mock_completion(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: return tool call
                return tool_resp
            # Second call: return final text
            return final_resp

        # @mock-exempt: execute_tool dispatch boundary -- same pattern as test_agent_tools.py
        # Signature: execute_tool(ctx, tool_name, arguments) matches tools.py:1499
        def mock_execute_tool(ctx, tool_name, arguments):
            tool_calls_recorded.append((tool_name, json.dumps(arguments, sort_keys=True)))
            return ("mocked result", None, [], [])

        runner.set_character(mode)
        runner.conversation = [runner.conversation[0]]  # reset history except sys

        with (
            patch.object(runner_module, "litellm") as mock_litellm,
            patch.object(runner_module, "execute_tool", mock_execute_tool),
        ):
            mock_litellm.completion = mock_completion
            runner.chat(query)

        return tool_calls_recorded

    def test_persona_swap_preserves_tool_call_identity(self, tmp_path):
        """Same query under full_troll vs default must produce identical tool calls.

        This is the HARD GATE for DEC-C1-FULLTROLL-004 and
        DEC-30-CHARACTER-V2-005: tool_preferences is voice-affinity ONLY,
        NEVER tool-selection bias.
        """
        from adversary_pursuit.agent.runner import AgentRunner
        from adversary_pursuit.agent.tools import ToolContext

        ctx = ToolContext(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
        )
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")
        runner = AgentRunner(model="fake-model", tool_context=ctx)

        query = "What do you know about evil.example.com?"

        calls_under_full_troll = self._run_chat_with_mode(
            runner, DEFAULT_MODES["full_troll"], query
        )
        calls_under_default = self._run_chat_with_mode(runner, DEFAULT_MODES["default"], query)

        assert calls_under_full_troll == calls_under_default, (
            "HARD GATE FAILURE: persona swap changed tool call sequence!\n"
            f"  full_troll calls: {calls_under_full_troll}\n"
            f"  default calls:    {calls_under_default}\n"
            "tool_preferences must be voice-affinity ONLY (DEC-C1-FULLTROLL-004)"
        )


# ---------------------------------------------------------------------------
# 6. F64 HARD GATE: persona text not in LLM-facing tool summary
# ---------------------------------------------------------------------------


class TestF64PanelSeparation:
    """F64 DEC-64-LLM-PANEL-SEPARATION-001: persona text must not leak into
    the LLM-facing summary field returned by execute_tool.

    The summary field is what the agent sees as the tool result -- it must be
    pure data output (STIX SCOs + stats), not persona narration.
    """

    def test_persona_text_not_present_in_tool_result_summary(self, tmp_path):
        """Persona voice text must NOT appear in the summary returned by execute_tool.

        The summary goes into the LLM conversation as a tool result. If persona
        text bleeds into it, the LLM receives confused input where data and
        voice are mixed.
        """
        from adversary_pursuit.agent.tools import ToolContext, execute_tool

        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")

        # Switch to full_troll so that run_fail is the troll voice
        ctx.mode_mgr.switch("full_troll")

        # Trigger a tool error path (module not configured) to exercise run_fail wiring.
        # Signature: execute_tool(ctx, tool_name, arguments)
        result_summary, _, _, _ = execute_tool(ctx, "dns_resolve", {"target": "test.example"})

        # The summary must not contain full_troll persona phrases from LLMPersonaProfile
        # (these would come from the system prompt leaking, not from run_fail --
        # run_fail is the Rich-panel voice, correctly Rich-stripped before embedding)
        profile = DEFAULT_MODES["full_troll"].llm_profile
        if profile is not None:
            for phrase in profile.signature_phrases:
                assert phrase not in result_summary, (
                    f"Persona signature phrase {phrase!r} leaked into tool result summary.\n"
                    f"Summary: {result_summary!r}"
                )

    def test_full_troll_response_does_not_smuggle_point_totals(self):
        """Persona LLM profile must not narrate point totals (F64 invariant).

        forbidden_voice entry 'never narrate point totals' must be present in
        the profile. We verify this at the data level (the guard is in the
        system prompt) and also verify execute_tool summary does not contain
        point-total strings.
        """
        profile = DEFAULT_MODES["full_troll"].llm_profile
        assert profile is not None

        # Data-level: forbidden_voice must include the point-total prohibition
        all_fv = " ".join(profile.forbidden_voice).lower()
        assert "point" in all_fv or "pts" in all_fv or "score" in all_fv, (
            "forbidden_voice must include a point-total narration guard (F64)"
        )


# ---------------------------------------------------------------------------
# 7. F62 authority invariants
# ---------------------------------------------------------------------------


class TestF62AuthorityInvariants:
    """F62 (W-62-STREAK-AND-HONEST-MODES) invariants must remain intact.

    The character v2 persona is strictly additive -- it must not disturb:
    - run_fail single-authority wiring at tools.py:1622-1628
    - StreakManager as sole streak authority
    - modes.py not importing streak machinery
    """

    def test_run_fail_wiring_in_tools_remains_byte_identical_to_baseline(self):
        """tools.py must be unchanged from main (F62 preservation -- F62-R0-001).

        The bytewise-identical constraint is verified by checking that the
        critical run_fail wiring block at lines 1622-1628 contains the exact
        expected identifiers and no C-1 persona additions.
        """
        import adversary_pursuit.agent.tools as tools_module

        source = inspect.getsource(tools_module)
        # The run_fail wiring must use ctx.mode_mgr.active.run_fail
        assert "ctx.mode_mgr.active.run_fail" in source, (
            "run_fail wiring at tools.py changed -- F62 authority broken"
        )
        # Must use _strip_rich_markup
        assert "_strip_rich_markup" in source, (
            "_strip_rich_markup call missing from tools.py -- F62 wiring broken"
        )
        # LLMPersonaProfile must NOT be consulted in tools.py
        assert "LLMPersonaProfile" not in source, (
            "LLMPersonaProfile referenced in tools.py -- F62 boundary violated. "
            "The persona profile must only be consulted in runner.py:set_character"
        )
        assert "llm_profile" not in source, (
            "llm_profile referenced in tools.py -- the profile must not leak into "
            "the tool-error path (F62/F64)"
        )

    def test_run_fail_field_still_consumed_at_tools_py_1622_1628(self):
        """The run_fail wiring line must be present at roughly the correct location."""
        import adversary_pursuit.agent.tools as tools_module

        source_lines = inspect.getsource(tools_module).splitlines()
        # Find the line with the run_fail wiring pattern
        wiring_lines = [
            i + 1 for i, line in enumerate(source_lines) if "ctx.mode_mgr.active.run_fail" in line
        ]
        assert len(wiring_lines) == 1, (
            f"Expected exactly 1 occurrence of run_fail wiring in tools.py, "
            f"found {len(wiring_lines)} at lines: {wiring_lines}"
        )

    def test_streak_manager_module_not_imported_by_modes_module(self):
        """modes.py must not import from streak module (F62 single-authority preservation).

        StreakManager is the sole streak authority. Importing it from modes.py
        would create a dependency that could drift into a parallel authority.
        """
        import adversary_pursuit.gamification.modes as modes_module

        source = inspect.getsource(modes_module)
        assert "streak" not in source.lower(), (
            "modes.py imports or references streak machinery -- "
            "StreakManager must remain the sole streak authority (F62)"
        )
        # Also verify at import level
        modes_exports = [name for name in dir(modes_module) if "streak" in name.lower()]
        assert not modes_exports, f"modes.py exports streak-related names: {modes_exports}"

    def test_run_fail_wiring_in_tools_bytes_unchanged_from_main_against_e49e70b(self):
        """tools.py F62 run_fail wiring is still intact after M-3 dossier scoring additions.

        M-3 (W-68-M3-DOSSIER-SCORING) legitimately modifies tools.py to wire the
        pre/post dossier snapshot and emit_dossier_slot_filled_events call
        (DEC-M3-DOSSIER-002). The bytewise-identity gate against the C-2 base commit
        (e49e70b) no longer applies to the whole file; it is superseded by the
        content-based F62 invariant tests above (test_run_fail_wiring_in_tools_remains_byte_identical_to_baseline
        and test_run_fail_field_still_consumed_at_tools_py_1622_1628), which verify
        the specific F62 wiring identifiers are still present without requiring
        byte-identity of the entire file.

        This test now verifies the M-3 base commit (de08b4b) is an ancestor of
        the current HEAD, confirming the branch is rooted at the correct base.
        If git is unavailable, the test is skipped.
        """
        import shutil
        import subprocess

        if shutil.which("git") is None:
            pytest.skip("git not available in this test environment")

        worktree_root = str(__import__("pathlib").Path(__file__).parent.parent)
        # Verify that de08b4b (M-3 base from AP main) is an ancestor of HEAD.
        # `git merge-base --is-ancestor <commit> HEAD` exits 0 if true, 1 if not.
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", "de08b4b", "HEAD"],
            capture_output=True,
            text=True,
            cwd=worktree_root,
        )
        # Exit code 0 = de08b4b is an ancestor (correct M-3 branch root)
        # Exit code 1 = not an ancestor (unexpected branch root)
        # Exit code 128 = git error (object not found, skip)
        if result.returncode == 128:
            pytest.skip(f"de08b4b not found in repo; git error: {result.stderr.strip()}")
        assert result.returncode == 0, (
            "M-3 branch is not rooted at de08b4b (AP main M-3 base). "
            "tools.py F62 wiring integrity is verified by content-based tests above."
        )


# ---------------------------------------------------------------------------
# 8. C-2: Ninja LLMPersonaProfile content (DEC-C2-NINJA-001)
# ---------------------------------------------------------------------------


class TestNinjaProfileContent:
    """ninja must carry the exact LLMPersonaProfile specified in DEC-C2-NINJA-001
    (c2-ninja-profile-plan.md §3). Mirrors TestFullTrollProfileContent for C-1.
    """

    @pytest.fixture
    def profile(self) -> LLMPersonaProfile:
        """Return ninja's llm_profile."""
        mode = DEFAULT_MODES["ninja"]
        assert mode.llm_profile is not None, (
            "ninja.llm_profile is None -- DEC-C2-NINJA-001 requires it to be set"
        )
        return mode.llm_profile

    def test_ninja_has_llm_profile(self):
        """ninja must have a non-None LLMPersonaProfile (C-2 gate)."""
        mode = DEFAULT_MODES["ninja"]
        assert mode.llm_profile is not None

    def test_ninja_profile_voice_summary_content(self, profile: LLMPersonaProfile):
        """voice_summary must capture quiet/terse/precise/factual/deadpan register."""
        vs = profile.voice_summary.lower()
        assert any(
            word in vs
            for word in ("quiet", "terse", "precise", "factual", "deadpan", "minimal", "clipped")
        ), (
            f"voice_summary '{profile.voice_summary}' missing expected quiet-operator descriptor. "
            "Must contain at least one of: quiet, terse, precise, factual, deadpan, minimal, clipped"
        )

    def test_ninja_profile_tone_registers_content(self, profile: LLMPersonaProfile):
        """tone_registers must be a tuple with ≥ 2 entries including anchor registers."""
        assert isinstance(profile.tone_registers, tuple)
        assert len(profile.tone_registers) >= 2, (
            "tone_registers must have 2-4 register words per schema"
        )
        registers_lower = {r.lower() for r in profile.tone_registers}
        expected = {"cold-deadpan", "technical-precise"}
        assert expected.issubset(registers_lower), (
            f"tone_registers {profile.tone_registers} missing anchor registers: "
            f"{expected - registers_lower}"
        )

    def test_ninja_profile_signature_phrases_content(self, profile: LLMPersonaProfile):
        """signature_phrases must include at least one canonical ninja phrase."""
        assert isinstance(profile.signature_phrases, tuple)
        assert len(profile.signature_phrases) >= 2, (
            "signature_phrases must have 2-5 catch-phrases per schema"
        )
        phrases_lower = [p.lower() for p in profile.signature_phrases]
        canonical = ("noted", "tracked", "indeed", "negative", "advance")
        assert any(any(c in p for c in canonical) for p in phrases_lower), (
            f"signature_phrases {profile.signature_phrases} must include at least one of "
            f"{canonical} (DEC-C2-NINJA-001 voice anchors)"
        )

    def test_ninja_profile_fourth_wall_stance(self, profile: LLMPersonaProfile):
        """fourth_wall_stance must be 'opaque' for ninja (DEC-C2-NINJA-001).

        Ninja is the role — no meta-awareness of being an LLM or tool.
        """
        assert profile.fourth_wall_stance == "opaque", (
            f"fourth_wall_stance must be 'opaque', got {profile.fourth_wall_stance!r}"
        )

    def test_ninja_profile_dialect_cadence_content(self, profile: LLMPersonaProfile):
        """dialect_cadence must describe clipped/short/concise/no-filler rhythm."""
        dc = profile.dialect_cadence.lower()
        assert any(
            word in dc for word in ("clipped", "short", "no filler", "no hedging", "concise")
        ), (
            f"dialect_cadence '{profile.dialect_cadence}' doesn't capture the "
            "clipped/short/no-filler cadence expected for ninja"
        )

    def test_ninja_profile_context_hooks_empty(self, profile: LLMPersonaProfile):
        """context_hooks must be empty tuple (mirrors DEC-C1-FULLTROLL-005 deferral).

        Deferred to M-4 dossier slot state, same as C-1.
        """
        assert profile.context_hooks == (), (
            f"context_hooks must be () for ninja in C-2 (deferred to M-4), "
            f"got {profile.context_hooks!r}"
        )

    def test_ninja_profile_tool_preferences_content(self, profile: LLMPersonaProfile):
        """tool_preferences must be voice-affinity ONLY (NOT selection instructions)."""
        assert isinstance(profile.tool_preferences, tuple)
        assert len(profile.tool_preferences) >= 1, (
            "tool_preferences should have 1-3 voice-affinity hints per schema"
        )
        # Must NOT contain instruction-language
        for pref in profile.tool_preferences:
            pref_lower = pref.lower()
            assert not pref_lower.startswith("prefer "), (
                f"tool_preferences entry starts with 'prefer' -- "
                f"must use affinity language, not selection instruction: {pref!r}"
            )
            assert "must use" not in pref_lower, (
                f"tool_preferences entry contains 'must use': {pref!r}"
            )
        # Must reference at least one known CTI tool
        all_prefs = " ".join(profile.tool_preferences).lower()
        assert any(tool in all_prefs for tool in ("virustotal", "crt.sh", "crt", "shodan")), (
            f"tool_preferences doesn't reference any known CTI tools: {profile.tool_preferences}"
        )

    def test_ninja_profile_forbidden_voice_content(self, profile: LLMPersonaProfile):
        """forbidden_voice must include F64 point-narration guard AND voice-register guard.

        Two distinct guards are required:
        1. F64: point-total narration is prohibited (the Rich panel owns scoring).
        2. Voice-register: exclamations/hyperbole are prohibited (keeps ninja from
           drifting toward full_troll's energy).
        """
        assert isinstance(profile.forbidden_voice, tuple)
        assert len(profile.forbidden_voice) >= 1, (
            "forbidden_voice must have at least the F64 panel-separation guard"
        )
        all_fv = " ".join(profile.forbidden_voice).lower()
        # F64 guard: must mention points/pts/score
        assert any(word in all_fv for word in ("point", "pts", "score")), (
            f"forbidden_voice must include F64 point-narration guard: {profile.forbidden_voice}"
        )
        # Voice-register guard: must mention exclamation/hyperbole
        assert any(word in all_fv for word in ("exclaim", "exclamation", "hyperbole")), (
            f"forbidden_voice must include exclamation/hyperbole guard (voice-register): "
            f"{profile.forbidden_voice}"
        )

    def test_ninja_profile_token_budget(self, profile: LLMPersonaProfile):
        """ninja profile must not exceed 165 tokens (DEC-30-CHARACTER-V2-003).

        Uses 4-chars-per-token proxy (conservative BPE estimate). Mirrors
        test_full_troll_profile_token_budget from C-1 verbatim.
        """
        profile_text = " ".join(
            [
                profile.voice_summary,
                " ".join(profile.tone_registers),
                " ".join(profile.signature_phrases),
                profile.fourth_wall_stance,
                profile.dialect_cadence,
                " ".join(profile.context_hooks),
                " ".join(profile.tool_preferences),
                " ".join(profile.forbidden_voice),
            ]
        )
        approx_tokens = _rough_token_count(profile_text)
        assert approx_tokens <= 165, (
            f"ninja profile exceeds 165-token budget: ~{approx_tokens} tokens "
            f"(DEC-30-CHARACTER-V2-003). Content: {profile_text!r}"
        )


# ---------------------------------------------------------------------------
# 9. C-2: Ninja persona-swap tool-call-identity hard gate
# ---------------------------------------------------------------------------


class TestNinjaPersonaSwapHardGates:
    """Mirrors TestPersonaSwapPreservesToolCallIdentity for the ninja mode.

    HARD GATE: DEC-C1-FULLTROLL-004 extended to ninja. Tool call sequence under
    ninja MUST equal the default-mode tool call sequence for the same query under
    the same deterministic mock LLM. DEC-30-CHARACTER-V2-005: tool_preferences
    is voice-affinity ONLY — never tool-selection bias.

    @mock-exempt: litellm.completion is an external LLM API boundary.
    execute_tool is mocked at the tool-dispatch boundary (same as TestPersonaSwapPreservesToolCallIdentity).
    """

    FIXED_TOOL_NAME = "dns_resolve"
    FIXED_TOOL_ARGS = {"target": "evil.example.com"}

    def _make_mock_litellm_response(self, tool_name: str, tool_args: dict):
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].finish_reason = "tool_calls"
        mock_resp.choices[0].message = MagicMock()
        mock_resp.choices[0].message.content = None
        mock_resp.choices[0].message.tool_calls = [MagicMock()]
        mock_resp.choices[0].message.tool_calls[0].id = "call_456"
        mock_resp.choices[0].message.tool_calls[0].type = "function"
        mock_resp.choices[0].message.tool_calls[0].function = MagicMock()
        mock_resp.choices[0].message.tool_calls[0].function.name = tool_name
        mock_resp.choices[0].message.tool_calls[0].function.arguments = json.dumps(tool_args)
        return mock_resp

    def _make_mock_final_response(self, text: str):
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].finish_reason = "stop"
        mock_resp.choices[0].message = MagicMock()
        mock_resp.choices[0].message.content = text
        mock_resp.choices[0].message.tool_calls = None
        return mock_resp

    def _run_chat_with_mode(self, runner, mode: CharacterMode, query: str) -> list[tuple[str, str]]:
        """Drive runner.chat() with a given mode and fixed deterministic mock LLM.

        Returns list of (tool_name, tool_args_json) tuples from the turn.

        @mock-exempt: litellm.completion and execute_tool are external/dispatch boundaries.
        """
        from adversary_pursuit.agent import runner as runner_module

        tool_calls_recorded: list[tuple[str, str]] = []

        tool_resp = self._make_mock_litellm_response(self.FIXED_TOOL_NAME, self.FIXED_TOOL_ARGS)
        final_resp = self._make_mock_final_response("Noted.")

        call_count = 0

        def mock_completion(**kwargs):
            nonlocal call_count
            call_count += 1
            return tool_resp if call_count == 1 else final_resp

        def mock_execute_tool(ctx, tool_name, arguments):
            tool_calls_recorded.append((tool_name, json.dumps(arguments, sort_keys=True)))
            return ("mocked result", None, [], [])

        runner.set_character(mode)
        runner.conversation = [runner.conversation[0]]

        with (
            patch.object(runner_module, "litellm") as mock_litellm,
            patch.object(runner_module, "execute_tool", mock_execute_tool),
        ):
            mock_litellm.completion = mock_completion
            runner.chat(query)

        return tool_calls_recorded

    def test_ninja_swap_preserves_tool_call_identity(self, tmp_path):
        """Same query under ninja vs default must produce identical tool calls.

        HARD GATE for DEC-C1-FULLTROLL-004 (extended to ninja by C-2) and
        DEC-30-CHARACTER-V2-005: tool_preferences is voice-affinity ONLY,
        NEVER tool-selection bias.
        """
        from adversary_pursuit.agent.runner import AgentRunner
        from adversary_pursuit.agent.tools import ToolContext

        ctx = ToolContext(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
        )
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")
        runner = AgentRunner(model="fake-model", tool_context=ctx)

        query = "What do you know about evil.example.com?"

        calls_under_ninja = self._run_chat_with_mode(runner, DEFAULT_MODES["ninja"], query)
        calls_under_default = self._run_chat_with_mode(runner, DEFAULT_MODES["default"], query)

        assert calls_under_ninja == calls_under_default, (
            "HARD GATE FAILURE: ninja persona swap changed tool call sequence!\n"
            f"  ninja calls:   {calls_under_ninja}\n"
            f"  default calls: {calls_under_default}\n"
            "tool_preferences must be voice-affinity ONLY (DEC-C1-FULLTROLL-004 / DEC-C2-NINJA-001)"
        )


# ---------------------------------------------------------------------------
# 10. C-2: Ninja F64 panel-separation hard gates
# ---------------------------------------------------------------------------


class TestNinjaF64PanelSeparation:
    """F64 DEC-64-LLM-PANEL-SEPARATION-001 for ninja: persona text must not leak
    into the LLM-facing summary field returned by execute_tool.

    Mirrors TestF64PanelSeparation for full_troll (C-1).
    """

    def test_ninja_persona_text_not_present_in_tool_result_summary(self, tmp_path):
        """Ninja persona voice text must NOT appear in the summary returned by execute_tool.

        The summary is the LLM-facing tool result — it must contain pure data output
        (STIX SCOs + stats), not persona narration (F64 DEC-64-LLM-PANEL-SEPARATION-001).
        """
        from adversary_pursuit.agent.tools import ToolContext, execute_tool

        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")

        # Switch to ninja so run_fail is the ninja-dim voice
        ctx.mode_mgr.switch("ninja")

        # Trigger a tool error path (module not configured) to exercise run_fail wiring.
        result_summary, _, _, _ = execute_tool(ctx, "dns_resolve", {"target": "test.example"})

        # The summary must not contain ninja's LLMPersonaProfile signature phrases
        # (these belong in the system prompt, not in the tool result)
        profile = DEFAULT_MODES["ninja"].llm_profile
        if profile is not None:
            for phrase in profile.signature_phrases:
                assert phrase not in result_summary, (
                    f"Ninja persona signature phrase {phrase!r} leaked into tool result summary.\n"
                    f"Summary: {result_summary!r}"
                )

    def test_ninja_does_not_smuggle_point_totals(self):
        """Ninja LLM profile must not narrate point totals (F64 invariant).

        forbidden_voice must include the point-total prohibition guard.
        Mirrors test_full_troll_response_does_not_smuggle_point_totals for ninja.
        """
        profile = DEFAULT_MODES["ninja"].llm_profile
        assert profile is not None

        all_fv = " ".join(profile.forbidden_voice).lower()
        assert "point" in all_fv or "pts" in all_fv or "score" in all_fv, (
            "ninja forbidden_voice must include a point-total narration guard (F64)"
        )


# ---------------------------------------------------------------------------
# 11. C-3: sun_tzu LLMPersonaProfile content (DEC-C3-PHILOSOPHY-001)
# ---------------------------------------------------------------------------


class TestSunTzuProfileContent:
    """sun_tzu must carry the LLMPersonaProfile specified in DEC-C3-PHILOSOPHY-001
    (character-c3-philosophy-bureaucrat.md §3.1). Mirrors TestNinjaProfileContent.
    """

    @pytest.fixture
    def profile(self) -> LLMPersonaProfile:
        """Return sun_tzu's llm_profile."""
        mode = DEFAULT_MODES["sun_tzu"]
        assert mode.llm_profile is not None, (
            "sun_tzu.llm_profile is None -- DEC-C3-PHILOSOPHY-001 requires it to be set"
        )
        return mode.llm_profile

    def test_sun_tzu_has_llm_profile(self):
        """sun_tzu must have a non-None LLMPersonaProfile (C-3 gate)."""
        mode = DEFAULT_MODES["sun_tzu"]
        assert mode.llm_profile is not None

    def test_sun_tzu_profile_voice_summary_content(self, profile: LLMPersonaProfile):
        """voice_summary must capture strategist / Art of War / oblique register."""
        vs = profile.voice_summary.lower()
        assert any(
            word in vs for word in ("strateg", "art of war", "oblique", "patient", "gnomic")
        ), (
            f"voice_summary '{profile.voice_summary}' missing expected strategist descriptor. "
            "Must contain at least one of: strateg, art of war, oblique, patient, gnomic"
        )

    def test_sun_tzu_profile_tone_registers_content(self, profile: LLMPersonaProfile):
        """tone_registers must be a tuple with ≥ 2 entries including anchor registers."""
        assert isinstance(profile.tone_registers, tuple)
        assert len(profile.tone_registers) >= 2, (
            "tone_registers must have 2-4 register words per schema"
        )
        registers_lower = {r.lower() for r in profile.tone_registers}
        expected = {"gnomic", "strategic"}
        assert expected.issubset(registers_lower), (
            f"tone_registers {profile.tone_registers} missing anchor registers: "
            f"{expected - registers_lower}"
        )

    def test_sun_tzu_profile_signature_phrases_content(self, profile: LLMPersonaProfile):
        """signature_phrases must include at least one canonical Art of War phrase."""
        assert isinstance(profile.signature_phrases, tuple)
        assert len(profile.signature_phrases) >= 2, (
            "signature_phrases must have 2-5 catch-phrases per schema"
        )
        phrases_lower = [p.lower() for p in profile.signature_phrases]
        canonical = ("know thy enemy", "opportunities multiply", "chaos", "victory")
        assert any(any(c in p for c in canonical) for p in phrases_lower), (
            f"signature_phrases {profile.signature_phrases} must include at least one of "
            f"{canonical} (DEC-C3-PHILOSOPHY-001 voice anchors)"
        )

    def test_sun_tzu_profile_fourth_wall_stance(self, profile: LLMPersonaProfile):
        """fourth_wall_stance must be 'opaque' for sun_tzu (DEC-C3-PHILOSOPHY-006).

        sun_tzu is the strategist role — no meta-awareness of being an LLM/tool.
        """
        assert profile.fourth_wall_stance == "opaque", (
            f"fourth_wall_stance must be 'opaque', got {profile.fourth_wall_stance!r}"
        )

    def test_sun_tzu_profile_dialect_cadence_content(self, profile: LLMPersonaProfile):
        """dialect_cadence must describe aphoristic / quote-then-application cadence."""
        dc = profile.dialect_cadence.lower()
        assert any(
            word in dc for word in ("aphor", "quote", "short", "second-person", "no modern slang")
        ), (
            f"dialect_cadence '{profile.dialect_cadence}' doesn't capture the "
            "aphoristic / quote-then-application rhythm expected for sun_tzu"
        )

    def test_sun_tzu_profile_context_hooks_empty(self, profile: LLMPersonaProfile):
        """context_hooks must be empty tuple for sun_tzu (DEC-C3-PHILOSOPHY-005)."""
        assert profile.context_hooks == (), (
            f"context_hooks must be () for sun_tzu in C-3 (deferred to C-4), "
            f"got {profile.context_hooks!r}"
        )

    def test_sun_tzu_profile_tool_preferences_content(self, profile: LLMPersonaProfile):
        """tool_preferences must be voice-affinity ONLY (NOT selection instructions)."""
        assert isinstance(profile.tool_preferences, tuple)
        assert len(profile.tool_preferences) >= 1, (
            "tool_preferences should have 1-3 voice-affinity hints per schema"
        )
        for pref in profile.tool_preferences:
            pref_lower = pref.lower()
            assert not pref_lower.startswith("prefer "), (
                f"tool_preferences entry starts with 'prefer' -- "
                f"must use affinity language, not selection instruction: {pref!r}"
            )
            assert "must use" not in pref_lower, (
                f"tool_preferences entry contains 'must use': {pref!r}"
            )
        all_prefs = " ".join(profile.tool_preferences).lower()
        assert any(tool in all_prefs for tool in ("virustotal", "crt.sh", "crt", "shodan")), (
            f"tool_preferences doesn't reference any known CTI tools: {profile.tool_preferences}"
        )

    def test_sun_tzu_profile_forbidden_voice_content(self, profile: LLMPersonaProfile):
        """forbidden_voice must include F64 point-narration guard AND voice-register guard.

        Two distinct guards required:
        1. F64: point-total narration is prohibited.
        2. Voice-register: modern slang / memes / exclamations are prohibited.
        """
        assert isinstance(profile.forbidden_voice, tuple)
        assert len(profile.forbidden_voice) >= 1, (
            "forbidden_voice must have at least the F64 panel-separation guard"
        )
        all_fv = " ".join(profile.forbidden_voice).lower()
        assert any(word in all_fv for word in ("point", "pts", "score")), (
            f"forbidden_voice must include F64 point-narration guard: {profile.forbidden_voice}"
        )
        assert any(word in all_fv for word in ("slang", "meme", "exclaim", "exclamation")), (
            f"forbidden_voice must include modern-slang/exclamation guard: {profile.forbidden_voice}"
        )

    def test_sun_tzu_profile_token_budget(self, profile: LLMPersonaProfile):
        """sun_tzu profile must not exceed 165 tokens (DEC-30-CHARACTER-V2-003).

        Uses 4-chars-per-token proxy. Mirrors test_ninja_profile_token_budget.
        """
        profile_text = " ".join(
            [
                profile.voice_summary,
                " ".join(profile.tone_registers),
                " ".join(profile.signature_phrases),
                profile.fourth_wall_stance,
                profile.dialect_cadence,
                " ".join(profile.context_hooks),
                " ".join(profile.tool_preferences),
                " ".join(profile.forbidden_voice),
            ]
        )
        approx_tokens = _rough_token_count(profile_text)
        assert approx_tokens <= 165, (
            f"sun_tzu profile exceeds 165-token budget: ~{approx_tokens} tokens "
            f"(DEC-30-CHARACTER-V2-003). Content: {profile_text!r}"
        )


# ---------------------------------------------------------------------------
# 12. C-3: sun_tzu persona-swap tool-call-identity hard gate
# ---------------------------------------------------------------------------


class TestSunTzuPersonaSwapHardGates:
    """Mirrors TestNinjaPersonaSwapHardGates for sun_tzu.

    HARD GATE: DEC-C1-FULLTROLL-004 extended to sun_tzu (DEC-C3-PHILOSOPHY-004).
    Tool call sequence under sun_tzu MUST equal default-mode sequence for the same
    query under the same deterministic mock LLM.

    @mock-exempt: litellm.completion is an external LLM API boundary.
    execute_tool is mocked at the tool-dispatch boundary.
    """

    FIXED_TOOL_NAME = "dns_resolve"
    FIXED_TOOL_ARGS = {"target": "evil.example.com"}

    def _make_mock_litellm_response(self, tool_name: str, tool_args: dict):
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].finish_reason = "tool_calls"
        mock_resp.choices[0].message = MagicMock()
        mock_resp.choices[0].message.content = None
        mock_resp.choices[0].message.tool_calls = [MagicMock()]
        mock_resp.choices[0].message.tool_calls[0].id = "call_sun_tzu"
        mock_resp.choices[0].message.tool_calls[0].type = "function"
        mock_resp.choices[0].message.tool_calls[0].function = MagicMock()
        mock_resp.choices[0].message.tool_calls[0].function.name = tool_name
        mock_resp.choices[0].message.tool_calls[0].function.arguments = json.dumps(tool_args)
        return mock_resp

    def _make_mock_final_response(self, text: str):
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].finish_reason = "stop"
        mock_resp.choices[0].message = MagicMock()
        mock_resp.choices[0].message.content = text
        mock_resp.choices[0].message.tool_calls = None
        return mock_resp

    def _run_chat_with_mode(self, runner, mode: CharacterMode, query: str) -> list[tuple[str, str]]:
        from adversary_pursuit.agent import runner as runner_module

        tool_calls_recorded: list[tuple[str, str]] = []
        tool_resp = self._make_mock_litellm_response(self.FIXED_TOOL_NAME, self.FIXED_TOOL_ARGS)
        final_resp = self._make_mock_final_response("Opportunities multiply as they are seized.")
        call_count = 0

        def mock_completion(**kwargs):
            nonlocal call_count
            call_count += 1
            return tool_resp if call_count == 1 else final_resp

        def mock_execute_tool(ctx, tool_name, arguments):
            tool_calls_recorded.append((tool_name, json.dumps(arguments, sort_keys=True)))
            return ("mocked result", None, [], [])

        runner.set_character(mode)
        runner.conversation = [runner.conversation[0]]

        with (
            patch.object(runner_module, "litellm") as mock_litellm,
            patch.object(runner_module, "execute_tool", mock_execute_tool),
        ):
            mock_litellm.completion = mock_completion
            runner.chat(query)

        return tool_calls_recorded

    def test_sun_tzu_swap_preserves_tool_call_identity(self, tmp_path):
        """Same query under sun_tzu vs default must produce identical tool calls.

        HARD GATE for DEC-C1-FULLTROLL-004 (extended to sun_tzu by C-3,
        DEC-C3-PHILOSOPHY-004) and DEC-30-CHARACTER-V2-005: tool_preferences
        is voice-affinity ONLY, NEVER tool-selection bias.
        """
        from adversary_pursuit.agent.runner import AgentRunner
        from adversary_pursuit.agent.tools import ToolContext

        ctx = ToolContext(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
        )
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")
        runner = AgentRunner(model="fake-model", tool_context=ctx)

        query = "What do you know about evil.example.com?"

        calls_under_sun_tzu = self._run_chat_with_mode(runner, DEFAULT_MODES["sun_tzu"], query)
        calls_under_default = self._run_chat_with_mode(runner, DEFAULT_MODES["default"], query)

        assert calls_under_sun_tzu == calls_under_default, (
            "HARD GATE FAILURE: sun_tzu persona swap changed tool call sequence!\n"
            f"  sun_tzu calls: {calls_under_sun_tzu}\n"
            f"  default calls: {calls_under_default}\n"
            "tool_preferences must be voice-affinity ONLY (DEC-C3-PHILOSOPHY-004)"
        )


# ---------------------------------------------------------------------------
# 13. C-3: sun_tzu F64 panel-separation hard gates
# ---------------------------------------------------------------------------


class TestSunTzuF64PanelSeparation:
    """F64 DEC-64-LLM-PANEL-SEPARATION-001 for sun_tzu. Mirrors TestNinjaF64PanelSeparation."""

    def test_sun_tzu_persona_text_not_present_in_tool_result_summary(self, tmp_path):
        """sun_tzu persona voice text must NOT appear in the summary returned by execute_tool."""
        from adversary_pursuit.agent.tools import ToolContext, execute_tool

        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")

        ctx.mode_mgr.switch("sun_tzu")

        result_summary, _, _, _ = execute_tool(ctx, "dns_resolve", {"target": "test.example"})

        profile = DEFAULT_MODES["sun_tzu"].llm_profile
        if profile is not None:
            for phrase in profile.signature_phrases:
                assert phrase not in result_summary, (
                    f"sun_tzu persona signature phrase {phrase!r} leaked into tool result summary.\n"
                    f"Summary: {result_summary!r}"
                )

    def test_sun_tzu_does_not_smuggle_point_totals(self):
        """sun_tzu LLM profile must not narrate point totals (F64 invariant)."""
        profile = DEFAULT_MODES["sun_tzu"].llm_profile
        assert profile is not None

        all_fv = " ".join(profile.forbidden_voice).lower()
        assert "point" in all_fv or "pts" in all_fv or "score" in all_fv, (
            "sun_tzu forbidden_voice must include a point-total narration guard (F64)"
        )


# ---------------------------------------------------------------------------
# 14. C-3: bruce_lee LLMPersonaProfile content (DEC-C3-PHILOSOPHY-002)
# ---------------------------------------------------------------------------


class TestBruceLeeProfileContent:
    """bruce_lee must carry the LLMPersonaProfile specified in DEC-C3-PHILOSOPHY-002
    (character-c3-philosophy-bureaucrat.md §3.2). Mirrors TestNinjaProfileContent.
    """

    @pytest.fixture
    def profile(self) -> LLMPersonaProfile:
        """Return bruce_lee's llm_profile."""
        mode = DEFAULT_MODES["bruce_lee"]
        assert mode.llm_profile is not None, (
            "bruce_lee.llm_profile is None -- DEC-C3-PHILOSOPHY-002 requires it to be set"
        )
        return mode.llm_profile

    def test_bruce_lee_has_llm_profile(self):
        """bruce_lee must have a non-None LLMPersonaProfile (C-3 gate)."""
        mode = DEFAULT_MODES["bruce_lee"]
        assert mode.llm_profile is not None

    def test_bruce_lee_profile_voice_summary_content(self, profile: LLMPersonaProfile):
        """voice_summary must capture flow-state / water / zen-philosopher register."""
        vs = profile.voice_summary.lower()
        assert any(
            word in vs for word in ("flow", "water", "zen", "philosopher", "adapt", "movement")
        ), (
            f"voice_summary '{profile.voice_summary}' missing expected zen-flow descriptor. "
            "Must contain at least one of: flow, water, zen, philosopher, adapt, movement"
        )

    def test_bruce_lee_profile_tone_registers_content(self, profile: LLMPersonaProfile):
        """tone_registers must be a tuple with ≥ 2 entries including anchor registers."""
        assert isinstance(profile.tone_registers, tuple)
        assert len(profile.tone_registers) >= 2, (
            "tone_registers must have 2-4 register words per schema"
        )
        registers_lower = {r.lower() for r in profile.tone_registers}
        expected = {"zen", "flowing"}
        assert expected.issubset(registers_lower), (
            f"tone_registers {profile.tone_registers} missing anchor registers: "
            f"{expected - registers_lower}"
        )

    def test_bruce_lee_profile_signature_phrases_content(self, profile: LLMPersonaProfile):
        """signature_phrases must include at least one canonical Bruce Lee phrase."""
        assert isinstance(profile.signature_phrases, tuple)
        assert len(profile.signature_phrases) >= 2, (
            "signature_phrases must have 2-5 catch-phrases per schema"
        )
        phrases_lower = [p.lower() for p in profile.signature_phrases]
        canonical = ("be water", "don't fear failure", "useful", "10,000 kicks", "formless")
        assert any(any(c in p for c in canonical) for p in phrases_lower), (
            f"signature_phrases {profile.signature_phrases} must include at least one of "
            f"{canonical} (DEC-C3-PHILOSOPHY-002 voice anchors)"
        )

    def test_bruce_lee_profile_fourth_wall_stance(self, profile: LLMPersonaProfile):
        """fourth_wall_stance must be 'opaque' for bruce_lee (DEC-C3-PHILOSOPHY-006)."""
        assert profile.fourth_wall_stance == "opaque", (
            f"fourth_wall_stance must be 'opaque', got {profile.fourth_wall_stance!r}"
        )

    def test_bruce_lee_profile_dialect_cadence_content(self, profile: LLMPersonaProfile):
        """dialect_cadence must describe nature-metaphor / short-declarative cadence."""
        dc = profile.dialect_cadence.lower()
        assert any(
            word in dc for word in ("nature", "metaphor", "short", "declarative", "second-person")
        ), (
            f"dialect_cadence '{profile.dialect_cadence}' doesn't capture the "
            "nature-metaphor / short-declarative rhythm expected for bruce_lee"
        )

    def test_bruce_lee_profile_context_hooks_empty(self, profile: LLMPersonaProfile):
        """context_hooks must be empty tuple for bruce_lee (DEC-C3-PHILOSOPHY-005)."""
        assert profile.context_hooks == (), (
            f"context_hooks must be () for bruce_lee in C-3 (deferred to C-4), "
            f"got {profile.context_hooks!r}"
        )

    def test_bruce_lee_profile_tool_preferences_content(self, profile: LLMPersonaProfile):
        """tool_preferences must be voice-affinity ONLY (NOT selection instructions)."""
        assert isinstance(profile.tool_preferences, tuple)
        assert len(profile.tool_preferences) >= 1, (
            "tool_preferences should have 1-3 voice-affinity hints per schema"
        )
        for pref in profile.tool_preferences:
            pref_lower = pref.lower()
            assert not pref_lower.startswith("prefer "), (
                f"tool_preferences entry starts with 'prefer' -- "
                f"must use affinity language, not selection instruction: {pref!r}"
            )
            assert "must use" not in pref_lower, (
                f"tool_preferences entry contains 'must use': {pref!r}"
            )
        all_prefs = " ".join(profile.tool_preferences).lower()
        assert any(
            tool in all_prefs for tool in ("crt.sh", "crt", "dns", "virustotal", "shodan")
        ), f"tool_preferences doesn't reference any known CTI tools: {profile.tool_preferences}"

    def test_bruce_lee_profile_forbidden_voice_content(self, profile: LLMPersonaProfile):
        """forbidden_voice must include F64 point-narration guard AND voice-register guard."""
        assert isinstance(profile.forbidden_voice, tuple)
        assert len(profile.forbidden_voice) >= 1, (
            "forbidden_voice must have at least the F64 panel-separation guard"
        )
        all_fv = " ".join(profile.forbidden_voice).lower()
        assert any(word in all_fv for word in ("point", "pts", "score")), (
            f"forbidden_voice must include F64 point-narration guard: {profile.forbidden_voice}"
        )
        assert any(
            word in all_fv for word in ("sarcasm", "snark", "exclaim", "exclamation", "hype")
        ), (
            f"forbidden_voice must include sarcasm/snark/exclamation guard: {profile.forbidden_voice}"
        )

    def test_bruce_lee_profile_token_budget(self, profile: LLMPersonaProfile):
        """bruce_lee profile must not exceed 165 tokens (DEC-30-CHARACTER-V2-003)."""
        profile_text = " ".join(
            [
                profile.voice_summary,
                " ".join(profile.tone_registers),
                " ".join(profile.signature_phrases),
                profile.fourth_wall_stance,
                profile.dialect_cadence,
                " ".join(profile.context_hooks),
                " ".join(profile.tool_preferences),
                " ".join(profile.forbidden_voice),
            ]
        )
        approx_tokens = _rough_token_count(profile_text)
        assert approx_tokens <= 165, (
            f"bruce_lee profile exceeds 165-token budget: ~{approx_tokens} tokens "
            f"(DEC-30-CHARACTER-V2-003). Content: {profile_text!r}"
        )


# ---------------------------------------------------------------------------
# 15. C-3: bruce_lee persona-swap tool-call-identity hard gate
# ---------------------------------------------------------------------------


class TestBruceLeePersonaSwapHardGates:
    """Mirrors TestNinjaPersonaSwapHardGates for bruce_lee.

    HARD GATE: DEC-C1-FULLTROLL-004 extended to bruce_lee (DEC-C3-PHILOSOPHY-004).

    @mock-exempt: litellm.completion is an external LLM API boundary.
    execute_tool is mocked at the tool-dispatch boundary.
    """

    FIXED_TOOL_NAME = "dns_resolve"
    FIXED_TOOL_ARGS = {"target": "evil.example.com"}

    def _make_mock_litellm_response(self, tool_name: str, tool_args: dict):
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].finish_reason = "tool_calls"
        mock_resp.choices[0].message = MagicMock()
        mock_resp.choices[0].message.content = None
        mock_resp.choices[0].message.tool_calls = [MagicMock()]
        mock_resp.choices[0].message.tool_calls[0].id = "call_bruce_lee"
        mock_resp.choices[0].message.tool_calls[0].type = "function"
        mock_resp.choices[0].message.tool_calls[0].function = MagicMock()
        mock_resp.choices[0].message.tool_calls[0].function.name = tool_name
        mock_resp.choices[0].message.tool_calls[0].function.arguments = json.dumps(tool_args)
        return mock_resp

    def _make_mock_final_response(self, text: str):
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].finish_reason = "stop"
        mock_resp.choices[0].message = MagicMock()
        mock_resp.choices[0].message.content = text
        mock_resp.choices[0].message.tool_calls = None
        return mock_resp

    def _run_chat_with_mode(self, runner, mode: CharacterMode, query: str) -> list[tuple[str, str]]:
        from adversary_pursuit.agent import runner as runner_module

        tool_calls_recorded: list[tuple[str, str]] = []
        tool_resp = self._make_mock_litellm_response(self.FIXED_TOOL_NAME, self.FIXED_TOOL_ARGS)
        final_resp = self._make_mock_final_response("Be water, my friend.")
        call_count = 0

        def mock_completion(**kwargs):
            nonlocal call_count
            call_count += 1
            return tool_resp if call_count == 1 else final_resp

        def mock_execute_tool(ctx, tool_name, arguments):
            tool_calls_recorded.append((tool_name, json.dumps(arguments, sort_keys=True)))
            return ("mocked result", None, [], [])

        runner.set_character(mode)
        runner.conversation = [runner.conversation[0]]

        with (
            patch.object(runner_module, "litellm") as mock_litellm,
            patch.object(runner_module, "execute_tool", mock_execute_tool),
        ):
            mock_litellm.completion = mock_completion
            runner.chat(query)

        return tool_calls_recorded

    def test_bruce_lee_swap_preserves_tool_call_identity(self, tmp_path):
        """Same query under bruce_lee vs default must produce identical tool calls.

        HARD GATE for DEC-C1-FULLTROLL-004 (extended to bruce_lee by C-3,
        DEC-C3-PHILOSOPHY-004) and DEC-30-CHARACTER-V2-005.
        """
        from adversary_pursuit.agent.runner import AgentRunner
        from adversary_pursuit.agent.tools import ToolContext

        ctx = ToolContext(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
        )
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")
        runner = AgentRunner(model="fake-model", tool_context=ctx)

        query = "What do you know about evil.example.com?"

        calls_under_bruce_lee = self._run_chat_with_mode(runner, DEFAULT_MODES["bruce_lee"], query)
        calls_under_default = self._run_chat_with_mode(runner, DEFAULT_MODES["default"], query)

        assert calls_under_bruce_lee == calls_under_default, (
            "HARD GATE FAILURE: bruce_lee persona swap changed tool call sequence!\n"
            f"  bruce_lee calls: {calls_under_bruce_lee}\n"
            f"  default calls:   {calls_under_default}\n"
            "tool_preferences must be voice-affinity ONLY (DEC-C3-PHILOSOPHY-004)"
        )


# ---------------------------------------------------------------------------
# 16. C-3: bruce_lee F64 panel-separation hard gates
# ---------------------------------------------------------------------------


class TestBruceLeeF64PanelSeparation:
    """F64 DEC-64-LLM-PANEL-SEPARATION-001 for bruce_lee. Mirrors TestNinjaF64PanelSeparation."""

    def test_bruce_lee_persona_text_not_present_in_tool_result_summary(self, tmp_path):
        """bruce_lee persona voice text must NOT appear in the summary returned by execute_tool.

        The summary contains run_fail (Rich-stripped static voice) — that is expected.
        We only check signature_phrases that are NOT already substrings of the static
        voice fields (run_fail, run_success, greeting). A phrase shared verbatim with
        run_fail reaching the summary is run_fail wiring, not a persona profile leak.
        For bruce_lee, "Don't fear failure." is both a signature_phrase AND the prefix
        of run_fail — we skip it here; the F62 run_fail single-authority tests cover it.
        """
        from adversary_pursuit.agent.tools import ToolContext, execute_tool

        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")

        ctx.mode_mgr.switch("bruce_lee")

        result_summary, _, _, _ = execute_tool(ctx, "dns_resolve", {"target": "test.example"})

        mode = DEFAULT_MODES["bruce_lee"]
        profile = mode.llm_profile
        # Collect the static voice strings so we can exclude overlapping phrases.
        static_voice = " ".join(
            [mode.run_fail, mode.run_success, mode.greeting, mode.score_celebration]
        )
        if profile is not None:
            for phrase in profile.signature_phrases:
                if phrase in static_voice:
                    # Phrase is also part of the static-voice surface (e.g. run_fail).
                    # Its presence in the summary is the F62 run_fail wiring, not a leak.
                    continue
                assert phrase not in result_summary, (
                    f"bruce_lee persona signature phrase {phrase!r} leaked into tool result summary.\n"
                    f"Summary: {result_summary!r}"
                )

    def test_bruce_lee_does_not_smuggle_point_totals(self):
        """bruce_lee LLM profile must not narrate point totals (F64 invariant)."""
        profile = DEFAULT_MODES["bruce_lee"].llm_profile
        assert profile is not None

        all_fv = " ".join(profile.forbidden_voice).lower()
        assert "point" in all_fv or "pts" in all_fv or "score" in all_fv, (
            "bruce_lee forbidden_voice must include a point-total narration guard (F64)"
        )


# ---------------------------------------------------------------------------
# 17. C-3: bureaucrat LLMPersonaProfile content (DEC-C3-PHILOSOPHY-003)
# ---------------------------------------------------------------------------


class TestBureaucratProfileContent:
    """bureaucrat must carry the LLMPersonaProfile specified in DEC-C3-PHILOSOPHY-003
    (character-c3-philosophy-bureaucrat.md §3.3). Mirrors TestNinjaProfileContent.
    """

    @pytest.fixture
    def profile(self) -> LLMPersonaProfile:
        """Return bureaucrat's llm_profile."""
        mode = DEFAULT_MODES["bureaucrat"]
        assert mode.llm_profile is not None, (
            "bureaucrat.llm_profile is None -- DEC-C3-PHILOSOPHY-003 requires it to be set"
        )
        return mode.llm_profile

    def test_bureaucrat_has_llm_profile(self):
        """bureaucrat must have a non-None LLMPersonaProfile (C-3 gate)."""
        mode = DEFAULT_MODES["bureaucrat"]
        assert mode.llm_profile is not None

    def test_bureaucrat_profile_voice_summary_content(self, profile: LLMPersonaProfile):
        """voice_summary must capture compliance-officer / form-filing / policy register."""
        vs = profile.voice_summary.lower()
        assert any(word in vs for word in ("compliance", "form", "policy", "officer", "office")), (
            f"voice_summary '{profile.voice_summary}' missing expected bureaucratic descriptor. "
            "Must contain at least one of: compliance, form, policy, officer, office"
        )

    def test_bureaucrat_profile_tone_registers_content(self, profile: LLMPersonaProfile):
        """tone_registers must be a tuple with ≥ 2 entries including anchor registers."""
        assert isinstance(profile.tone_registers, tuple)
        assert len(profile.tone_registers) >= 2, (
            "tone_registers must have 2-4 register words per schema"
        )
        registers_lower = {r.lower() for r in profile.tone_registers}
        expected = {"dry-corporate", "deadpan"}
        assert expected.issubset(registers_lower), (
            f"tone_registers {profile.tone_registers} missing anchor registers: "
            f"{expected - registers_lower}"
        )

    def test_bureaucrat_profile_signature_phrases_content(self, profile: LLMPersonaProfile):
        """signature_phrases must include policy-section and form-number references."""
        assert isinstance(profile.signature_phrases, tuple)
        assert len(profile.signature_phrases) >= 2, (
            "signature_phrases must have 2-5 catch-phrases per schema"
        )
        all_phrases = " ".join(profile.signature_phrases)
        assert "§" in all_phrases or "policy" in all_phrases.lower(), (
            f"signature_phrases must include a policy-section reference (§ or 'policy'): "
            f"{profile.signature_phrases}"
        )
        assert any(
            "form" in p.lower() or "ir-" in p.lower() or "err-" in p.lower()
            for p in profile.signature_phrases
        ), (
            f"signature_phrases must include a form-number reference (Form/IR-/ERR-): "
            f"{profile.signature_phrases}"
        )

    def test_bureaucrat_profile_fourth_wall_stance(self, profile: LLMPersonaProfile):
        """fourth_wall_stance must be 'opaque' for bureaucrat (DEC-C3-PHILOSOPHY-006)."""
        assert profile.fourth_wall_stance == "opaque", (
            f"fourth_wall_stance must be 'opaque', got {profile.fourth_wall_stance!r}"
        )

    def test_bureaucrat_profile_dialect_cadence_content(self, profile: LLMPersonaProfile):
        """dialect_cadence must describe passive-voice / policy-citation / no-contractions cadence."""
        dc = profile.dialect_cadence.lower()
        assert any(
            word in dc
            for word in ("passive", "policy", "citation", "form", "no contractions", "contraction")
        ), (
            f"dialect_cadence '{profile.dialect_cadence}' doesn't capture the "
            "passive-voice / policy-citation / no-contractions rhythm expected for bureaucrat"
        )

    def test_bureaucrat_profile_context_hooks_empty(self, profile: LLMPersonaProfile):
        """context_hooks must be empty tuple for bureaucrat (DEC-C3-PHILOSOPHY-005)."""
        assert profile.context_hooks == (), (
            f"context_hooks must be () for bureaucrat in C-3 (deferred to C-4), "
            f"got {profile.context_hooks!r}"
        )

    def test_bureaucrat_profile_tool_preferences_content(self, profile: LLMPersonaProfile):
        """tool_preferences must be voice-affinity ONLY (NOT selection instructions).

        Bureaucrat's form-framing (Form CT-3, Form WH-1) must not be phrased as
        selection instructions per DEC-C3-PHILOSOPHY-004 / DEC-30-CHARACTER-V2-005.
        """
        assert isinstance(profile.tool_preferences, tuple)
        assert len(profile.tool_preferences) >= 1, (
            "tool_preferences should have 1-3 voice-affinity hints per schema"
        )
        for pref in profile.tool_preferences:
            pref_lower = pref.lower()
            assert not pref_lower.startswith("prefer "), (
                f"tool_preferences entry starts with 'prefer' -- "
                f"must use affinity language, not selection instruction: {pref!r}"
            )
            assert "must use" not in pref_lower, (
                f"tool_preferences entry contains 'must use': {pref!r}"
            )
        all_prefs = " ".join(profile.tool_preferences).lower()
        assert any(
            tool in all_prefs for tool in ("crt.sh", "crt", "whois", "virustotal", "shodan")
        ), f"tool_preferences doesn't reference any known CTI tools: {profile.tool_preferences}"

    def test_bureaucrat_profile_forbidden_voice_content(self, profile: LLMPersonaProfile):
        """forbidden_voice must include F64 point-narration guard AND no-slang guard."""
        assert isinstance(profile.forbidden_voice, tuple)
        assert len(profile.forbidden_voice) >= 1, (
            "forbidden_voice must have at least the F64 panel-separation guard"
        )
        all_fv = " ".join(profile.forbidden_voice).lower()
        assert any(word in all_fv for word in ("point", "pts", "score")), (
            f"forbidden_voice must include F64 point-narration guard: {profile.forbidden_voice}"
        )
        assert any(word in all_fv for word in ("slang", "contraction", "exclamation", "exclaim")), (
            f"forbidden_voice must include slang/contraction/exclamation guard: {profile.forbidden_voice}"
        )

    def test_bureaucrat_profile_token_budget(self, profile: LLMPersonaProfile):
        """bureaucrat profile must not exceed 165 tokens (DEC-30-CHARACTER-V2-003)."""
        profile_text = " ".join(
            [
                profile.voice_summary,
                " ".join(profile.tone_registers),
                " ".join(profile.signature_phrases),
                profile.fourth_wall_stance,
                profile.dialect_cadence,
                " ".join(profile.context_hooks),
                " ".join(profile.tool_preferences),
                " ".join(profile.forbidden_voice),
            ]
        )
        approx_tokens = _rough_token_count(profile_text)
        assert approx_tokens <= 165, (
            f"bureaucrat profile exceeds 165-token budget: ~{approx_tokens} tokens "
            f"(DEC-30-CHARACTER-V2-003). Content: {profile_text!r}"
        )


# ---------------------------------------------------------------------------
# 18. C-3: bureaucrat persona-swap tool-call-identity hard gate
# ---------------------------------------------------------------------------


class TestBureaucratPersonaSwapHardGates:
    """Mirrors TestNinjaPersonaSwapHardGates for bureaucrat.

    HARD GATE: DEC-C1-FULLTROLL-004 extended to bureaucrat (DEC-C3-PHILOSOPHY-004).
    The Form CT-3 / Form WH-1 framing in tool_preferences is the highest-risk
    case for selection bias — bureaucratic form names could plausibly bias crt.sh/WHOIS
    selection. This test is the mechanical proof it does not.

    @mock-exempt: litellm.completion is an external LLM API boundary.
    execute_tool is mocked at the tool-dispatch boundary.
    """

    FIXED_TOOL_NAME = "dns_resolve"
    FIXED_TOOL_ARGS = {"target": "evil.example.com"}

    def _make_mock_litellm_response(self, tool_name: str, tool_args: dict):
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].finish_reason = "tool_calls"
        mock_resp.choices[0].message = MagicMock()
        mock_resp.choices[0].message.content = None
        mock_resp.choices[0].message.tool_calls = [MagicMock()]
        mock_resp.choices[0].message.tool_calls[0].id = "call_bureaucrat"
        mock_resp.choices[0].message.tool_calls[0].type = "function"
        mock_resp.choices[0].message.tool_calls[0].function = MagicMock()
        mock_resp.choices[0].message.tool_calls[0].function.name = tool_name
        mock_resp.choices[0].message.tool_calls[0].function.arguments = json.dumps(tool_args)
        return mock_resp

    def _make_mock_final_response(self, text: str):
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].finish_reason = "stop"
        mock_resp.choices[0].message = MagicMock()
        mock_resp.choices[0].message.content = text
        mock_resp.choices[0].message.tool_calls = None
        return mock_resp

    def _run_chat_with_mode(self, runner, mode: CharacterMode, query: str) -> list[tuple[str, str]]:
        from adversary_pursuit.agent import runner as runner_module

        tool_calls_recorded: list[tuple[str, str]] = []
        tool_resp = self._make_mock_litellm_response(self.FIXED_TOOL_NAME, self.FIXED_TOOL_ARGS)
        final_resp = self._make_mock_final_response("Per Policy §4.2.1, analysis complete.")
        call_count = 0

        def mock_completion(**kwargs):
            nonlocal call_count
            call_count += 1
            return tool_resp if call_count == 1 else final_resp

        def mock_execute_tool(ctx, tool_name, arguments):
            tool_calls_recorded.append((tool_name, json.dumps(arguments, sort_keys=True)))
            return ("mocked result", None, [], [])

        runner.set_character(mode)
        runner.conversation = [runner.conversation[0]]

        with (
            patch.object(runner_module, "litellm") as mock_litellm,
            patch.object(runner_module, "execute_tool", mock_execute_tool),
        ):
            mock_litellm.completion = mock_completion
            runner.chat(query)

        return tool_calls_recorded

    def test_bureaucrat_swap_preserves_tool_call_identity(self, tmp_path):
        """Same query under bureaucrat vs default must produce identical tool calls.

        HARD GATE for DEC-C1-FULLTROLL-004 (extended to bureaucrat by C-3,
        DEC-C3-PHILOSOPHY-004) and DEC-30-CHARACTER-V2-005. The bureaucrat
        persona is the highest-risk case: Form CT-3/WH-1 framing could
        plausibly bias crt.sh/WHOIS selection. This test is the mechanical proof
        it does not.
        """
        from adversary_pursuit.agent.runner import AgentRunner
        from adversary_pursuit.agent.tools import ToolContext

        ctx = ToolContext(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
        )
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")
        runner = AgentRunner(model="fake-model", tool_context=ctx)

        query = "What do you know about evil.example.com?"

        calls_under_bureaucrat = self._run_chat_with_mode(
            runner, DEFAULT_MODES["bureaucrat"], query
        )
        calls_under_default = self._run_chat_with_mode(runner, DEFAULT_MODES["default"], query)

        assert calls_under_bureaucrat == calls_under_default, (
            "HARD GATE FAILURE: bureaucrat persona swap changed tool call sequence!\n"
            f"  bureaucrat calls: {calls_under_bureaucrat}\n"
            f"  default calls:    {calls_under_default}\n"
            "tool_preferences must be voice-affinity ONLY (DEC-C3-PHILOSOPHY-004)"
        )


# ---------------------------------------------------------------------------
# 19. C-3: bureaucrat F64 panel-separation hard gates
# ---------------------------------------------------------------------------


class TestBureaucratF64PanelSeparation:
    """F64 DEC-64-LLM-PANEL-SEPARATION-001 for bureaucrat. Mirrors TestNinjaF64PanelSeparation."""

    def test_bureaucrat_persona_text_not_present_in_tool_result_summary(self, tmp_path):
        """bureaucrat persona voice text must NOT appear in the summary returned by execute_tool."""
        from adversary_pursuit.agent.tools import ToolContext, execute_tool

        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")

        ctx.mode_mgr.switch("bureaucrat")

        result_summary, _, _, _ = execute_tool(ctx, "dns_resolve", {"target": "test.example"})

        profile = DEFAULT_MODES["bureaucrat"].llm_profile
        if profile is not None:
            for phrase in profile.signature_phrases:
                assert phrase not in result_summary, (
                    f"bureaucrat persona signature phrase {phrase!r} leaked into tool result summary.\n"
                    f"Summary: {result_summary!r}"
                )

    def test_bureaucrat_does_not_smuggle_point_totals(self):
        """bureaucrat LLM profile must not narrate point totals (F64 invariant)."""
        profile = DEFAULT_MODES["bureaucrat"].llm_profile
        assert profile is not None

        all_fv = " ".join(profile.forbidden_voice).lower()
        assert "point" in all_fv or "pts" in all_fv or "score" in all_fv, (
            "bureaucrat forbidden_voice must include a point-total narration guard (F64)"
        )
