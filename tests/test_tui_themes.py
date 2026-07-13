"""Tests for Phase 18 Slice 7A: TUI character theme system.

Covers:
- Every mode in DEFAULT_MODES has a matching theme in DEFAULT_THEMES
- theme_for() returns correct theme for known characters
- theme_for() falls back to "default" theme for unknown characters
- AP_TUI_HIGH_CONTRAST=1 → resolved_border_color returns high_contrast_border
- AP_TUI_HIGH_CONTRAST=0 / unset → returns normal border_color
- Neuromancer theme has expected colors (bright_magenta border, cyberpunk palette)

@decision DEC-TEST-TUI-THEMES-001
@title Theme coverage test: every DEFAULT_MODES character must have a DEFAULT_THEMES entry
@status accepted
@rationale Sacred Practice 12 (single authority): DEFAULT_THEMES is the sole
           authority for character visual themes. This test enforces the invariant
           that every active character in DEFAULT_MODES has an explicit theme entry
           so no character falls through to the generic "default" fallback silently.
           Parametrize over DEFAULT_MODES.keys() so new characters added in future
           slices automatically require a theme entry (test fails loudly — Sacred
           Practice 5).
"""

from __future__ import annotations

import pytest

from adversary_pursuit.agent.tui.themes import (
    DEFAULT_THEMES,
    CharacterTheme,
    is_high_contrast_mode,
    resolved_border_color,
    theme_for,
)
from adversary_pursuit.gamification.modes import DEFAULT_MODES


class TestThemeCoverage:
    """Every active character in DEFAULT_MODES must have an entry in DEFAULT_THEMES."""

    @pytest.mark.parametrize("char_name", list(DEFAULT_MODES.keys()))
    def test_every_mode_has_theme(self, char_name: str) -> None:
        """Each character in DEFAULT_MODES must have an explicit theme in DEFAULT_THEMES."""
        assert char_name in DEFAULT_THEMES, (
            f"Character '{char_name}' has no entry in DEFAULT_THEMES — "
            f"add a CharacterTheme for it (DEC-TUI-THEME-001 / Sacred Practice 12)"
        )

    @pytest.mark.parametrize("char_name", list(DEFAULT_MODES.keys()))
    def test_theme_is_character_theme_instance(self, char_name: str) -> None:
        """Each theme must be a CharacterTheme frozen dataclass."""
        assert isinstance(DEFAULT_THEMES[char_name], CharacterTheme)

    @pytest.mark.parametrize("char_name", list(DEFAULT_MODES.keys()))
    def test_theme_name_matches_key(self, char_name: str) -> None:
        """theme.name must match the dict key."""
        theme = DEFAULT_THEMES[char_name]
        assert theme.name == char_name, (
            f"Theme name mismatch: DEFAULT_THEMES['{char_name}'].name == '{theme.name}'"
        )

    @pytest.mark.parametrize("char_name", list(DEFAULT_MODES.keys()))
    def test_all_theme_fields_non_empty(self, char_name: str) -> None:
        """All CharacterTheme string fields must be non-empty."""
        theme = DEFAULT_THEMES[char_name]
        for field_name in (
            "border_color",
            "accent_color",
            "heading_color",
            "text_color",
            "dim_color",
            "high_contrast_border",
        ):
            value = getattr(theme, field_name)
            assert value, f"DEFAULT_THEMES['{char_name}'].{field_name} is empty"


class TestThemeFor:
    """theme_for() API contract."""

    def test_theme_for_neuromancer(self) -> None:
        """neuromancer theme has bright_magenta border (cyberpunk storyboard palette)."""
        theme = theme_for("neuromancer")
        assert theme.border_color == "bright_magenta"

    def test_theme_for_hal9000(self) -> None:
        """hal9000 theme has bright_red border (storyboard red palette)."""
        theme = theme_for("hal9000")
        assert theme.border_color == "bright_red"

    def test_theme_for_chuck_norris(self) -> None:
        """chuck_norris theme has bright_magenta border (storyboard neon palette)."""
        theme = theme_for("chuck_norris")
        assert theme.border_color == "bright_magenta"

    def test_theme_for_default(self) -> None:
        """default theme has cyan border."""
        theme = theme_for("default")
        assert theme.border_color == "cyan"

    def test_theme_for_unknown_falls_back_to_default(self) -> None:
        """Unknown character falls back to the 'default' theme (not a KeyError)."""
        theme = theme_for("totally_unknown_character_xyz")
        assert theme == DEFAULT_THEMES["default"]

    def test_theme_for_returns_frozen_dataclass(self) -> None:
        """theme_for() always returns a CharacterTheme instance."""
        assert isinstance(theme_for("ninja"), CharacterTheme)

    def test_neuromancer_accent_bright_cyan(self) -> None:
        """neuromancer accent color is bright_cyan (cyberpunk palette)."""
        assert theme_for("neuromancer").accent_color == "bright_cyan"

    def test_neuromancer_text_yellow(self) -> None:
        """neuromancer text color is yellow (matches storyboard yellow-on-purple content)."""
        assert theme_for("neuromancer").text_color == "yellow"


class TestHighContrastMode:
    """AP_TUI_HIGH_CONTRAST=1 env var switches border to high_contrast_border."""

    def test_high_contrast_env_1_returns_high_contrast_border(self, monkeypatch) -> None:
        """AP_TUI_HIGH_CONTRAST=1 → resolved_border_color returns high_contrast_border."""
        monkeypatch.setenv("AP_TUI_HIGH_CONTRAST", "1")
        theme = theme_for("neuromancer")
        result = resolved_border_color(theme)
        assert result == theme.high_contrast_border

    def test_high_contrast_env_0_returns_normal_border(self, monkeypatch) -> None:
        """AP_TUI_HIGH_CONTRAST=0 → resolved_border_color returns border_color."""
        monkeypatch.setenv("AP_TUI_HIGH_CONTRAST", "0")
        theme = theme_for("neuromancer")
        result = resolved_border_color(theme)
        assert result == theme.border_color

    def test_high_contrast_env_unset_returns_normal_border(self, monkeypatch) -> None:
        """Unset AP_TUI_HIGH_CONTRAST → resolved_border_color returns border_color."""
        monkeypatch.delenv("AP_TUI_HIGH_CONTRAST", raising=False)
        theme = theme_for("hal9000")
        result = resolved_border_color(theme)
        assert result == theme.border_color

    def test_is_high_contrast_mode_true_when_set(self, monkeypatch) -> None:
        """is_high_contrast_mode() returns True when AP_TUI_HIGH_CONTRAST=1."""
        monkeypatch.setenv("AP_TUI_HIGH_CONTRAST", "1")
        assert is_high_contrast_mode() is True

    def test_is_high_contrast_mode_false_when_unset(self, monkeypatch) -> None:
        """is_high_contrast_mode() returns False when AP_TUI_HIGH_CONTRAST is not set."""
        monkeypatch.delenv("AP_TUI_HIGH_CONTRAST", raising=False)
        assert is_high_contrast_mode() is False

    def test_high_contrast_border_is_bright_white_for_all_themes(self) -> None:
        """Every character theme has bright_white as the high_contrast_border."""
        for char_name, theme in DEFAULT_THEMES.items():
            assert theme.high_contrast_border == "bright_white", (
                f"DEFAULT_THEMES['{char_name}'].high_contrast_border != 'bright_white'"
            )
