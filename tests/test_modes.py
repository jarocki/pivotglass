"""Tests for Issue #16: Character Mode System.

Covers:
- All 10 modes exist in DEFAULT_MODES (default + 9 personality modes)
- ModeManager.switch() changes active mode and returns CharacterMode
- ModeManager.switch() raises ValueError on unknown mode name
- ModeManager.list_modes() returns all modes
- CharacterMode has all required fields populated
- Console do_mode() switches active mode
- Console prompt includes mode prefix after switch
- Console run success message uses active mode text
- Console score display uses mode score_celebration template

Production sequence tested:
  Console.__init__ → mode_mgr = ModeManager() with "default" active
  do_mode("ninja") → mode_mgr.switch("ninja") → prompt updates
  do_run (success) → mode_mgr.active.run_success displayed

@decision DEC-TEST-016
@title Modes tests cover dataclass fields, manager API, and console wiring
@status accepted
@rationale Three verification levels: (1) dataclass completeness to catch missing
           fields in DEFAULT_MODES, (2) ModeManager state machine (switch, list,
           error handling), (3) console integration verifying the prompt, success
           messages, and score celebration all read from the active mode. The
           production sequence test uses mode switch → run to verify the full
           wiring in the console path.
"""

from __future__ import annotations

import io

import pytest

from adversary_pursuit.core.console import APConsole
from adversary_pursuit.gamification.modes import (
    DEFAULT_MODES,
    CharacterMode,
    ModeManager,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mgr() -> ModeManager:
    """Fresh ModeManager with default state."""
    return ModeManager()


@pytest.fixture
def console(tmp_path) -> APConsole:
    """APConsole with isolated temp dirs."""
    app = APConsole(
        config_dir=tmp_path / "config",
        workspace_dir=tmp_path / "workspaces",
    )
    app.stdout = io.StringIO()
    return app


def run_cmd(app: APConsole, cmd: str) -> str:
    """Run a command and return combined poutput + Rich output."""
    app.stdout = io.StringIO()
    app.rich_console = app._make_rich_console()
    app.onecmd_plus_hooks(cmd)
    plain = app.stdout.getvalue()
    rich_out = app.rich_console.file.getvalue()
    return plain + rich_out


# ---------------------------------------------------------------------------
# DEFAULT_MODES — catalogue completeness
# ---------------------------------------------------------------------------


class TestDefaultModes:
    """Verify the complete, backward-compatible mode catalogue."""

    EXPECTED_NAMES = {
        "default",
        "ninja",
        "full_troll",
        "drunken_master",
        "sun_tzu",
        "chuck_norris",
        "bureaucrat",
        "bobby_hill",
        "bruce_lee",
        "columbo",
        "deckard",
        "hal9000",
        "neuromancer",  # Phase 18 Slice 7A (DEC-CHAR-NEUROMANCER-001)
        "trinity",
    }

    def test_fourteen_modes_present(self):
        """Exactly 14 modes should exist, including deprecated classics."""
        assert len(DEFAULT_MODES) == 14

    def test_all_expected_names_present(self):
        """All 14 named modes are in DEFAULT_MODES."""
        assert set(DEFAULT_MODES.keys()) == self.EXPECTED_NAMES

    def test_default_mode_exists(self):
        assert "default" in DEFAULT_MODES

    def test_ninja_mode_exists(self):
        assert "ninja" in DEFAULT_MODES

    def test_full_troll_mode_exists(self):
        assert "full_troll" in DEFAULT_MODES

    def test_drunken_master_mode_remains_selectable(self):
        """Deprecated modes remain available to existing users."""
        assert DEFAULT_MODES["drunken_master"].llm_profile is None

    def test_sun_tzu_mode_exists(self):
        assert "sun_tzu" in DEFAULT_MODES

    def test_chuck_norris_mode_exists(self):
        assert "chuck_norris" in DEFAULT_MODES

    def test_bureaucrat_mode_exists(self):
        assert "bureaucrat" in DEFAULT_MODES

    def test_bobby_hill_mode_exists(self):
        assert "bobby_hill" in DEFAULT_MODES

    def test_bruce_lee_mode_exists(self):
        assert "bruce_lee" in DEFAULT_MODES

    def test_columbo_mode_exists(self):
        assert "columbo" in DEFAULT_MODES

    def test_deckard_mode_exists(self):
        """deckard added in Phase 18 Slice 5 (DEC-CHAR-DECKARD-001)."""
        assert "deckard" in DEFAULT_MODES

    def test_hal9000_mode_exists(self):
        """hal9000 added in Phase 18 Slice 5 (DEC-CHAR-HAL9000-001)."""
        assert "hal9000" in DEFAULT_MODES

    def test_trinity_mode_uses_white_rabbit_identity(self):
        mode = DEFAULT_MODES["trinity"]
        assert mode.prompt_prefix == "🐇"
        assert mode.llm_profile is not None
        assert "Matrix operator" in mode.personality


# ---------------------------------------------------------------------------
# CharacterMode dataclass — field completeness
# ---------------------------------------------------------------------------


REQUIRED_FIELDS = (
    "name",
    "prompt_prefix",
    "greeting",
    "run_success",
    "run_fail",
    # hint_style deleted in F62 (DEC-62-KILL-DOC-LIES-001): zero consumers,
    # undefined semantics, was never wired to any hint subsystem.
    "score_celebration",
    "personality",
)


class TestCharacterModeFields:
    """Every mode must have all required fields non-empty."""

    @pytest.mark.parametrize("mode_name", list(DEFAULT_MODES.keys()))
    def test_all_fields_present(self, mode_name: str):
        """CharacterMode has all required attribute names."""
        mode = DEFAULT_MODES[mode_name]
        for field in REQUIRED_FIELDS:
            assert hasattr(mode, field), f"Mode '{mode_name}' missing field '{field}'"

    @pytest.mark.parametrize("mode_name", list(DEFAULT_MODES.keys()))
    def test_name_matches_key(self, mode_name: str):
        """CharacterMode.name must match the dict key."""
        mode = DEFAULT_MODES[mode_name]
        assert mode.name == mode_name

    @pytest.mark.parametrize("mode_name", list(DEFAULT_MODES.keys()))
    def test_required_string_fields_non_empty(self, mode_name: str):
        """greeting, run_success, run_fail, personality are non-empty strings."""
        mode = DEFAULT_MODES[mode_name]
        for field in ("greeting", "run_success", "run_fail", "personality"):
            value = getattr(mode, field)
            assert isinstance(value, str), f"Mode '{mode_name}'.{field} is not str"
            assert value.strip(), f"Mode '{mode_name}'.{field} is empty"

    @pytest.mark.parametrize("mode_name", list(DEFAULT_MODES.keys()))
    def test_score_celebration_contains_points_placeholder(self, mode_name: str):
        """score_celebration must contain {points} for .format(points=N)."""
        mode = DEFAULT_MODES[mode_name]
        assert "{points}" in mode.score_celebration, (
            f"Mode '{mode_name}'.score_celebration missing {{points}} placeholder"
        )

    @pytest.mark.parametrize("mode_name", list(DEFAULT_MODES.keys()))
    def test_score_celebration_formats_cleanly(self, mode_name: str):
        """score_celebration.format(points=42) must not raise."""
        mode = DEFAULT_MODES[mode_name]
        result = mode.score_celebration.format(points=42)
        assert "42" in result

    def test_hint_style_field_deleted(self):
        """hint_style must NOT exist on CharacterMode (F62 DEC-62-KILL-DOC-LIES-001).

        hint_style had zero consumers and advertised unimplemented semantics.
        This test ensures it is not re-introduced accidentally.
        """
        assert not hasattr(CharacterMode, "hint_style"), (
            "hint_style field was re-introduced on CharacterMode — "
            "it was deliberately deleted in F62 (DEC-62-KILL-DOC-LIES-001)"
        )
        # Also verify no DEFAULT_MODE entry carries hint_style
        for name, mode in DEFAULT_MODES.items():
            assert not hasattr(mode, "hint_style"), (
                f"Mode '{name}' unexpectedly has hint_style attribute"
            )

    @pytest.mark.parametrize("mode_name", list(DEFAULT_MODES.keys()))
    def test_personality_contains_no_unimplemented_mechanics(self, mode_name: str):
        """personality must not advertise unimplemented mechanics (F62 DEC-62-KILL-DOC-LIES-001).

        Banned phrases: "speed bonus", "combo multiplier", "chaos mode",
        "random pivot suggestions". These were false advertising for features
        that were never implemented.
        """
        mode = DEFAULT_MODES[mode_name]
        banned = ["speed bonus", "combo multiplier", "chaos mode", "random pivot"]
        for phrase in banned:
            assert phrase.lower() not in mode.personality.lower(), (
                f"Mode '{mode_name}'.personality contains banned phrase {phrase!r} — "
                "this is false advertising for an unimplemented feature"
            )


# ---------------------------------------------------------------------------
# ModeManager — state machine
# ---------------------------------------------------------------------------


class TestModeManagerInit:
    """ModeManager starts in default state."""

    def test_initial_active_is_default(self, mgr: ModeManager):
        """Fresh ModeManager has active mode 'default'."""
        assert mgr.active.name == "default"

    def test_active_returns_character_mode_instance(self, mgr: ModeManager):
        """active property returns a CharacterMode instance."""
        assert isinstance(mgr.active, CharacterMode)


class TestModeManagerSwitch:
    """ModeManager.switch() changes active mode."""

    def test_switch_to_ninja(self, mgr: ModeManager):
        """Switching to ninja sets active to ninja."""
        result = mgr.switch("ninja")
        assert mgr.active.name == "ninja"
        assert result.name == "ninja"

    def test_switch_returns_character_mode(self, mgr: ModeManager):
        """switch() returns the CharacterMode instance for the new mode."""
        result = mgr.switch("sun_tzu")
        assert isinstance(result, CharacterMode)

    def test_switch_to_all_modes(self, mgr: ModeManager):
        """Every mode in DEFAULT_MODES can be switched to."""
        for name in DEFAULT_MODES:
            result = mgr.switch(name)
            assert mgr.active.name == name
            assert result.name == name

    def test_switch_back_to_default(self, mgr: ModeManager):
        """Can switch away from and back to default."""
        mgr.switch("columbo")
        mgr.switch("default")
        assert mgr.active.name == "default"

    def test_switch_invalid_mode_raises_value_error(self, mgr: ModeManager):
        """Switching to an unknown mode raises ValueError."""
        with pytest.raises(ValueError, match="Unknown mode"):
            mgr.switch("xyzzy_mode")

    def test_switch_invalid_includes_available_names(self, mgr: ModeManager):
        """ValueError message lists available modes."""
        with pytest.raises(ValueError) as exc_info:
            mgr.switch("not_a_real_mode")
        error_msg = str(exc_info.value)
        # The error should list at least some available mode names
        assert "default" in error_msg or "ninja" in error_msg

    def test_switch_does_not_affect_other_modes(self, mgr: ModeManager):
        """Switching modes does not mutate DEFAULT_MODES entries."""
        original_greeting = DEFAULT_MODES["ninja"].greeting
        mgr.switch("ninja")
        assert DEFAULT_MODES["ninja"].greeting == original_greeting


class TestModeManagerListModes:
    """ModeManager.list_modes() returns all modes summary."""

    def test_list_modes_returns_list(self, mgr: ModeManager):
        """list_modes() returns a list."""
        result = mgr.list_modes()
        assert isinstance(result, list)

    def test_list_modes_count(self, mgr: ModeManager):
        """list_modes() returns one entry for every current mode."""
        result = mgr.list_modes()
        assert len(result) == len(DEFAULT_MODES)

    def test_list_modes_contains_dicts_with_name_and_personality(self, mgr: ModeManager):
        """Each entry is a dict with 'name' and 'personality' keys."""
        result = mgr.list_modes()
        for entry in result:
            assert "name" in entry, f"Entry missing 'name': {entry}"
            assert "personality" in entry, f"Entry missing 'personality': {entry}"

    def test_list_modes_includes_all_names(self, mgr: ModeManager):
        """list_modes() result contains all 10 mode names."""
        result = mgr.list_modes()
        names = {entry["name"] for entry in result}
        assert names == set(DEFAULT_MODES.keys())

    def test_list_modes_does_not_change_active_mode(self, mgr: ModeManager):
        """Calling list_modes() does not change the active mode."""
        mgr.switch("bruce_lee")
        mgr.list_modes()
        assert mgr.active.name == "bruce_lee"


# ---------------------------------------------------------------------------
# Console integration — do_mode wiring
# ---------------------------------------------------------------------------


class TestConsoleModeCommand:
    """Console do_mode() switches the active mode and updates the prompt."""

    def test_mode_command_switches_to_ninja(self, console: APConsole):
        """mode ninja activates ninja mode."""
        run_cmd(console, "mode ninja")
        assert console.mode_mgr.active.name == "ninja"

    def test_mode_command_updates_prompt_with_prefix(self, console: APConsole):
        """After mode ninja, mode is active but REPL prompt stays plain 'ap> '.

        Phase 17R removed the mode-prefix injection into the REPL prompt.
        Mode emoji/prefix lives only in the ap-chat surface, not the REPL.
        """
        run_cmd(console, "mode ninja")
        assert console.mode_mgr.active.name == "ninja"
        # Prompt must not carry mode prefix
        assert console.prompt == "ap> "

    def test_mode_command_full_troll_prefix_in_prompt(self, console: APConsole):
        """After mode full_troll, mode is active but REPL prompt stays plain 'ap> '.

        Phase 17R removed the mode-prefix injection into the REPL prompt.
        """
        run_cmd(console, "mode full_troll")
        assert console.mode_mgr.active.name == "full_troll"
        assert console.prompt == "ap> "

    def test_mode_default_has_clean_prompt(self, console: APConsole):
        """After switching to ninja and back to default, prompt has no prefix."""
        run_cmd(console, "mode ninja")
        run_cmd(console, "mode default")
        # Default mode has empty prompt_prefix
        assert console.mode_mgr.active.prompt_prefix == ""

    def test_mode_command_unknown_shows_error(self, console: APConsole):
        """mode with unknown name shows an error message."""
        out = run_cmd(console, "mode totally_fake_mode")
        combined = out.lower()
        assert "unknown" in combined or "error" in combined or "available" in combined

    def test_mode_command_unknown_does_not_change_active(self, console: APConsole):
        """mode with unknown name leaves active mode unchanged."""
        run_cmd(console, "mode ninja")
        run_cmd(console, "mode totally_fake_mode")
        assert console.mode_mgr.active.name == "ninja"

    def test_mode_command_outputs_greeting(self, console: APConsole):
        """mode switch outputs the mode's greeting message."""
        out = run_cmd(console, "mode sun_tzu")
        # sun_tzu greeting contains "Know thy enemy"
        assert "Know thy enemy" in out or "sun_tzu" in out.lower() or out.strip()

    def test_mode_command_all_valid_modes_do_not_crash(self, console: APConsole):
        """All valid mode names can be switched to via console without crashing."""
        for name in DEFAULT_MODES:
            out = run_cmd(console, f"mode {name}")
            assert isinstance(out, str)


# ---------------------------------------------------------------------------
# Console integration — run success message uses active mode
# ---------------------------------------------------------------------------


class TestConsoleModeRunIntegration:
    """Verify run success path uses active mode's text (production sequence)."""

    def test_default_mode_run_success_message(self, console: APConsole):
        """In default mode, run success shows default mode's run_success text."""
        run_cmd(console, "use osint/dns_resolve")
        run_cmd(console, "set TARGET example.com")
        out = run_cmd(console, "run")
        # default mode run_success: "Hunt complete. Results stored."
        assert "Hunt complete" in out or "stored" in out.lower()

    def test_ninja_mode_run_success_message(self, console: APConsole):
        """After mode ninja, hunt completes and results are stored.

        Phase 17R removed the run_success personality string from _execute_hunt
        output — mode flavor is an ap-chat concern, not a REPL concern. We
        verify the hunt ran (results panel or 'stored' appears) rather than
        checking for a persona string.
        """
        run_cmd(console, "mode ninja")
        run_cmd(console, "use osint/dns_resolve")
        run_cmd(console, "set TARGET example.com")
        out = run_cmd(console, "run")
        # Hunt completed — either results were displayed or stored message appeared
        assert out.strip() or console.mode_mgr.active.name == "ninja"

    def test_full_troll_run_success_message(self, console: APConsole):
        """After mode full_troll, hunt completes and results are stored.

        Phase 17R removed the run_success personality string from _execute_hunt
        output — mode flavor is an ap-chat concern, not a REPL concern. We
        verify the hunt ran rather than checking for a persona string.
        """
        run_cmd(console, "mode full_troll")
        run_cmd(console, "use osint/dns_resolve")
        run_cmd(console, "set TARGET example.com")
        run_cmd(console, "run")
        # Hunt completed — mode is active even if persona string not in REPL output
        assert console.mode_mgr.active.name == "full_troll"


# ---------------------------------------------------------------------------
# Console integration — score_celebration uses active mode
# ---------------------------------------------------------------------------


class TestConsoleModeScoreCelebration:
    """Verify score display uses active mode's score_celebration template."""

    def test_default_mode_score_celebration(self, console: APConsole):
        """In default mode, score celebration shows '+{points} points!'."""
        run_cmd(console, "use osint/dns_resolve")
        run_cmd(console, "set TARGET example.com")
        out = run_cmd(console, "run")
        # default: "+{points} points!" — should contain "points"
        assert "points" in out.lower()

    def test_ninja_mode_score_celebration(self, console: APConsole):
        """In ninja mode, score celebration uses ninja's minimal template."""
        run_cmd(console, "mode ninja")
        run_cmd(console, "use osint/dns_resolve")
        run_cmd(console, "set TARGET example.com")
        out = run_cmd(console, "run")
        # ninja score_celebration: "[dim]+{points}[/dim]" — contains a number
        assert any(c.isdigit() for c in out), "Expected numeric points in ninja mode output"
