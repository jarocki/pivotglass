"""Tests for Phase 18 Slice 7A: banner.py MODE_COLORS unification with themes.py.

Verifies DEC-BANNER-MODE-COLOR-UNIFIED-001: the old MODE_COLORS dict in
banner.py has been deleted and get_mode_color() now delegates to
theme_for(name).heading_color, making DEFAULT_THEMES in themes.py the single
authority for all character color strings (Sacred Practice 12).

@decision DEC-TEST-BANNER-UNIFIED-001
@title Assert no parallel MODE_COLORS authority in banner.py
@status accepted
@rationale The reviewer flagged banner.py:MODE_COLORS as a dual-authority
           violation of Sacred Practice 12. These tests provide the mechanical
           guard: test_no_parallel_mode_color_authority fails if any future
           implementer reintroduces a module-scope color dict in banner.py.
           test_banner_mode_color_reads_from_theme enforces that get_mode_color()
           returns what theme_for().heading_color returns — catching any
           divergence between the function and the theme data layer.
"""

from __future__ import annotations

import inspect

import adversary_pursuit.agent.banner as banner_module
from adversary_pursuit.agent.banner import get_mode_color
from adversary_pursuit.agent.tui.themes import theme_for
from adversary_pursuit.gamification.modes import DEFAULT_MODES

# ---------------------------------------------------------------------------
# Authority invariant: no parallel color dict at module scope
# ---------------------------------------------------------------------------


class TestNoParallelModeColorAuthority:
    """banner.py must NOT define a MODE_COLORS dict (or equivalent) at module scope."""

    def test_mode_colors_not_defined_in_banner_module(self) -> None:
        """banner.MODE_COLORS must not exist — it was the old parallel authority.

        DEC-BANNER-MODE-COLOR-UNIFIED-001: the dict was deleted in Slice 7A
        Round 3. This test catches any re-introduction.
        """
        assert not hasattr(banner_module, "MODE_COLORS"), (
            "banner.py still defines MODE_COLORS — this is a dual-authority "
            "violation of Sacred Practice 12. Delete it and delegate to "
            "theme_for(name).heading_color instead (DEC-BANNER-MODE-COLOR-UNIFIED-001)."
        )

    def test_no_module_level_character_color_dict_in_banner(self) -> None:
        """banner.py must not define any module-level dict mapping mode names to color strings.

        Checks that no dict at module scope contains mode names as keys and
        color strings as values — which would re-create the parallel authority
        under a different name.
        """
        mode_names = set(DEFAULT_MODES.keys())
        for attr_name in dir(banner_module):
            obj = getattr(banner_module, attr_name, None)
            if not isinstance(obj, dict):
                continue
            # Check if it looks like a mode→color mapping: keys overlap with mode names
            overlap = set(obj.keys()) & mode_names
            if len(overlap) >= 3:  # 3+ mode names as keys is a strong signal
                # Confirm values are strings (color-like)
                values_are_strings = all(isinstance(v, str) for v in obj.values())
                assert not values_are_strings, (
                    f"banner.py defines a module-level dict '{attr_name}' that maps "
                    f"mode names to strings — this looks like a parallel color authority. "
                    f"Delete it and delegate to theme_for(name).heading_color "
                    f"(DEC-BANNER-MODE-COLOR-UNIFIED-001 / Sacred Practice 12). "
                    f"Overlapping keys: {overlap}"
                )

    def test_banner_source_does_not_contain_mode_colors_assignment(self) -> None:
        """The banner.py source must not contain 'MODE_COLORS' as a name."""
        source = inspect.getsource(banner_module)
        # Allow it in comments/docstrings that reference the old name historically,
        # but not as a Python assignment target (i.e. "MODE_COLORS = " or "MODE_COLORS:")
        assert "MODE_COLORS =" not in source, (
            "banner.py source contains 'MODE_COLORS =' — the parallel color dict "
            "has been reintroduced. Remove it (DEC-BANNER-MODE-COLOR-UNIFIED-001)."
        )
        assert "MODE_COLORS:" not in source, (
            "banner.py source contains 'MODE_COLORS:' (type-annotated assignment) — "
            "the parallel color dict has been reintroduced. Remove it."
        )


# ---------------------------------------------------------------------------
# get_mode_color() delegates to theme_for().heading_color
# ---------------------------------------------------------------------------


class TestBannerModeColorReadsFromTheme:
    """get_mode_color() must return the same value as theme_for(name).heading_color."""

    def test_get_mode_color_matches_theme_heading_color_for_all_modes(self) -> None:
        """get_mode_color(name) == theme_for(name).heading_color for every known mode."""
        for mode_name in DEFAULT_MODES:
            expected = theme_for(mode_name).heading_color
            actual = get_mode_color(mode_name)
            assert actual == expected, (
                f"get_mode_color('{mode_name}') returned '{actual}' but "
                f"theme_for('{mode_name}').heading_color is '{expected}'. "
                f"banner.get_mode_color() must delegate to themes.py "
                f"(DEC-BANNER-MODE-COLOR-UNIFIED-001)."
            )

    def test_get_mode_color_the_sprawl_is_bright_magenta_hex(self) -> None:
        """the_sprawl heading_color is '#ff5fff' (bright_magenta hex, PTK-compatible).

        Updated in Slice 7Ah2: bold modifier removed from stored value; hex replaces
        Rich color name (DEC-TUI-PTK-COLOR-COMPAT-001). get_mode_color() callers
        (e.g. chat.py _mode_prompt) apply bold in their own markup wrappers.
        """
        result = get_mode_color("the_sprawl")
        assert result == "#ff5fff", f"the_sprawl mode color should be '#ff5fff', got '{result}'"

    def test_get_mode_color_the_computer_is_bright_red_hex(self) -> None:
        """the_computer heading_color is '#ff5555' (bright_red hex, PTK-compatible).

        Updated in Slice 7Ah2: bold modifier removed from stored value; hex replaces
        Rich color name (DEC-TUI-PTK-COLOR-COMPAT-001).
        """
        result = get_mode_color("the_computer")
        assert result == "#ff5555", f"the_computer mode color should be '#ff5555', got '{result}'"

    def test_get_mode_color_sensei_is_bright_magenta_hex(self) -> None:
        """sensei heading_color is '#ff5fff' (bright_magenta hex, neon storyboard palette).

        Updated in Slice 7Ah2: bold modifier removed from stored value; hex replaces
        Rich color name (DEC-TUI-PTK-COLOR-COMPAT-001).
        """
        result = get_mode_color("sensei")
        assert result == "#5f5fff", f"sensei mode color should be '#5f5fff', got '{result}'"

    def test_get_mode_color_default_contains_cyan_hex(self) -> None:
        """default heading_color is '#00d7d7' (cyan hex, PTK-compatible).

        Updated in Slice 7Ah2: hex replaces Rich color name (DEC-TUI-PTK-COLOR-COMPAT-001).
        """
        result = get_mode_color("default")
        assert result == "#00d7d7", f"default mode color should be '#00d7d7', got '{result}'"

    def test_get_mode_color_unknown_returns_fallback(self) -> None:
        """Unknown mode returns the fallback color, not a KeyError."""
        result = get_mode_color("not_a_real_character_xyz")
        # The fallback is the default theme's heading_color (since theme_for falls
        # back to the default theme for unknown names)
        expected = theme_for("default").heading_color
        assert result == expected, (
            f"Unknown mode should return default theme heading_color '{expected}', got '{result}'"
        )

    def test_get_mode_color_always_returns_str(self) -> None:
        """get_mode_color() must always return a str, including for unknown modes."""
        for mode_name in list(DEFAULT_MODES.keys()) + ["bogus", "", "NINJA", "X"]:
            result = get_mode_color(mode_name)
            assert isinstance(result, str), (
                f"get_mode_color('{mode_name}') returned {type(result).__name__}, expected str"
            )
            assert len(result) > 0, f"get_mode_color('{mode_name}') returned an empty string"


# ---------------------------------------------------------------------------
# StatusBar uses theme-derived color (compound interaction test)
# ---------------------------------------------------------------------------


class TestStatusBarUsesThemeColor:
    """StatusBar._render_bar() must ultimately use theme-derived colors.

    StatusBar calls get_mode_color() (via _render_bar → no, it doesn't call
    get_mode_color directly). What it does: it uses dim cyan for the bar text.
    The key invariant is that get_mode_color() is the function callers use
    for the prompt prefix color, and it now reads from themes.py.

    This compound test exercises the full sequence:
      chat.py calls get_mode_color(mode.name) for the prompt prefix
      → get_mode_color delegates to theme_for(name).heading_color
      → heading_color comes from DEFAULT_THEMES (themes.py, single authority)
    """

    def test_compound_prompt_prefix_color_sequence(self) -> None:
        """Simulate chat.py's _mode_prompt() color lookup via get_mode_color."""
        # This mirrors the production sequence in chat.py:
        #   color = get_mode_color(mode.name)
        #   return f"{prefix}[{color}]ap>[/{color}] "
        for mode_name in DEFAULT_MODES:
            color = get_mode_color(mode_name)
            # The color must be valid for Rich markup — non-empty, string
            assert isinstance(color, str) and color, (
                f"get_mode_color('{mode_name}') returned invalid color for prompt prefix"
            )
            # The color must match what themes.py says
            assert color == theme_for(mode_name).heading_color, (
                f"Prompt prefix color for '{mode_name}' diverged from theme authority. "
                f"get_mode_color='{color}', theme.heading_color='{theme_for(mode_name).heading_color}'"
            )
