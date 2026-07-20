"""Tests for Phase 18 Slice 7A (updated Slice 7Ah2): TUI application theme color injection.

Verifies that TuiApplication injects character theme colors into the PTK
FormattedText tuples returned by _get_header_formatted() and
_get_live_pane_formatted() (DEC-TUI-APP-THEME-INJECT-001 /
DEC-TUI-THEME-001).

Production sequence (what these tests cover):
  1. TuiApplication constructs with a ModeManager (or stub).
  2. On each PTK render cycle, _get_header_formatted() and
     _get_live_pane_formatted() call theme_for(active_mode_name) to get the
     CharacterTheme, then resolved_border_color(theme) to get the border color.
  3. They build FormattedText with style tokens like ``fg:#ff5fff``
     (hex, PTK-compatible) so PTK's renderer applies the character color to
     every border row. Row 0 of the live pane uses ``bold fg:#ff5fff`` so
     the heading is bold without embedding the modifier in the color value
     (DEC-TUI-PTK-COLOR-COMPAT-001).
  4. When the active mode changes, the next render cycle automatically picks
     up the new theme — no explicit cache invalidation is required.

@decision DEC-TEST-TUI-APP-THEME-001
@title Test that FormattedText style tokens are non-empty and match active theme
@status accepted
@rationale Reviewers flagged that prior to Slice 7A Round 3, all three pane
           builders used ("", row) — the style token was always empty, so no
           character color was applied despite the theme data layer existing.
           These tests catch that regression: they assert that the style tokens
           in FormattedText are non-empty and contain the expected color string
           for the active character mode. If a future refactor accidentally
           reverts to ("", ...) style tokens, these tests fail immediately.
           Slice 7Ah2: color strings updated to hex values; heading row style
           updated to ``bold fg:#xxxxxx`` form (DEC-TUI-PTK-COLOR-COMPAT-001).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch  # @mock-exempt: sys.stdin.isatty is OS/TTY boundary

from adversary_pursuit.agent.tui.application import TuiApplication
from adversary_pursuit.agent.tui.events import EventBus
from adversary_pursuit.agent.tui.themes import (
    COCKPIT_PROFILES,
    cockpit_for,
    resolved_border_color,
    theme_for,
)

# ---------------------------------------------------------------------------
# Test stubs
# ---------------------------------------------------------------------------


class _FakeMode:
    """Minimal duck-type for a CharacterMode."""

    def __init__(self, name: str) -> None:
        self.name = name


class _FakeModeManager:
    """Minimal duck-type for ModeManager with a switchable active mode."""

    def __init__(self, name: str = "default") -> None:
        self.active = _FakeMode(name)

    def switch(self, name: str) -> None:
        self.active = _FakeMode(name)


class _FakeRunner:
    model = "test/model"


def test_every_mode_has_a_distinct_cockpit_identity() -> None:
    assert len(COCKPIT_PROFILES) == 14
    assert len({profile.vehicle for profile in COCKPIT_PROFILES.values()}) == 14
    assert cockpit_for("hal9000").vehicle == "DISCOVERY ONE"
    assert cockpit_for("neuromancer").vehicle == "ONO-SENDAI VII"


def _make_app(mode_name: str = "default") -> TuiApplication:
    """Construct a TuiApplication with the given initial mode, all PTK stubs."""
    bus = EventBus()
    runner = _FakeRunner()
    mode_mgr = _FakeModeManager(mode_name)

    # @mock-exempt: sys.stdin.isatty is OS/TTY boundary; _build_app needs a real terminal
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch.object(TuiApplication, "_build_app", return_value=MagicMock()),
    ):
        app = TuiApplication(
            runner=runner,
            workspace_mgr=None,
            mode_mgr=mode_mgr,
            event_bus=bus,
        )
    return app


# ---------------------------------------------------------------------------
# Header FormattedText — style tokens must carry the border color
# ---------------------------------------------------------------------------


class TestHeaderFormattedTextHasThemeColor:
    """_get_header_formatted() must inject fg:<border_color> style tokens."""

    def test_header_formatted_text_has_theme_color_neuromancer(self, monkeypatch) -> None:
        """With neuromancer mode active, header style tokens contain '#ff5fff' (bright_magenta hex)."""
        monkeypatch.delenv("AP_TUI_HIGH_CONTRAST", raising=False)
        app = _make_app("neuromancer")
        theme = theme_for("neuromancer")
        expected_color = resolved_border_color(theme)  # "#ff5fff"

        ft = app._get_header_formatted()
        style_tokens = [style for style, _ in ft]

        # At least one row must carry fg:<border_color>
        assert any(expected_color in tok for tok in style_tokens), (
            f"Expected 'fg:{expected_color}' in FormattedText style tokens for neuromancer. "
            f"Got: {style_tokens}"
        )

    def test_header_formatted_text_has_theme_color_hal9000(self, monkeypatch) -> None:
        """With hal9000 mode active, header style tokens contain '#ff5555' (bright_red hex)."""
        monkeypatch.delenv("AP_TUI_HIGH_CONTRAST", raising=False)
        app = _make_app("hal9000")
        theme = theme_for("hal9000")
        expected_color = resolved_border_color(theme)  # "#ff5555"

        ft = app._get_header_formatted()
        style_tokens = [style for style, _ in ft]

        assert any(expected_color in tok for tok in style_tokens), (
            f"Expected '{expected_color}' in header style tokens for hal9000. Got: {style_tokens}"
        )

    def test_header_formatted_text_no_empty_style_on_border_rows(self, monkeypatch) -> None:
        """Border rows must NOT use the empty style ('') — that was the pre-Slice-7A bug."""
        monkeypatch.delenv("AP_TUI_HIGH_CONTRAST", raising=False)
        app = _make_app("neuromancer")

        ft = app._get_header_formatted()
        # Filter out the newline separator tuples (which may legitimately be "")
        border_row_styles = [style for style, text in ft if text.strip()]

        assert all(style != "" for style in border_row_styles), (
            "Border row style tokens must not be empty — style injection regression detected. "
            f"Offending tokens: {[(s, t[:20]) for s, t in ft if not t.strip() == '' and s == '']}"
        )

    def test_header_returns_exactly_three_content_rows(self, monkeypatch) -> None:
        """_get_header_formatted() must produce exactly 3 text content rows."""
        monkeypatch.delenv("AP_TUI_HIGH_CONTRAST", raising=False)
        app = _make_app("default")

        ft = app._get_header_formatted()
        # Count non-newline content parts
        content_rows = [text for _, text in ft if text != "\n"]
        assert len(content_rows) == 3, (
            f"Expected 3 content rows in header FormattedText, got {len(content_rows)}"
        )


# ---------------------------------------------------------------------------
# Live pane FormattedText — style tokens must carry the border color
# ---------------------------------------------------------------------------


class TestLivePaneFormattedTextHasThemeColor:
    """_get_live_pane_formatted() must inject character theme colors into style tokens."""

    def test_live_pane_formatted_text_has_theme_color_neuromancer(self, monkeypatch) -> None:
        """With neuromancer mode active, live pane style tokens contain '#ff5fff' (bright_magenta hex)."""
        monkeypatch.delenv("AP_TUI_HIGH_CONTRAST", raising=False)
        app = _make_app("neuromancer")
        theme = theme_for("neuromancer")
        expected_color = resolved_border_color(theme)  # "#ff5fff"

        ft = app._get_live_pane_formatted()
        style_tokens = [style for style, _ in ft]

        assert any(expected_color in tok for tok in style_tokens), (
            f"Expected '{expected_color}' in live pane style tokens for neuromancer. "
            f"Got: {style_tokens}"
        )

    def test_live_pane_formatted_text_has_theme_color_hal9000(self, monkeypatch) -> None:
        """With hal9000 mode active, live pane style tokens contain '#ff5555' (bright_red hex)."""
        monkeypatch.delenv("AP_TUI_HIGH_CONTRAST", raising=False)
        app = _make_app("hal9000")
        theme = theme_for("hal9000")
        expected_color = resolved_border_color(theme)  # "#ff5555"

        ft = app._get_live_pane_formatted()
        style_tokens = [style for style, _ in ft]

        assert any(expected_color in tok for tok in style_tokens), (
            f"Expected '{expected_color}' in live pane style tokens for hal9000. "
            f"Got: {style_tokens}"
        )

    def test_live_pane_returns_exactly_six_content_rows(self, monkeypatch) -> None:
        """_get_live_pane_formatted() must produce exactly 6 content rows."""
        monkeypatch.delenv("AP_TUI_HIGH_CONTRAST", raising=False)
        app = _make_app("default")

        ft = app._get_live_pane_formatted()
        content_rows = [text for _, text in ft if text != "\n"]
        assert len(content_rows) == 6, (
            f"Expected 6 content rows in live pane FormattedText, got {len(content_rows)}"
        )

    def test_live_pane_row1_uses_bold_heading_color(self, monkeypatch) -> None:
        """Row 1 of live pane (character identity) must use 'bold fg:<heading_color>'.

        Slice 7Ah2: heading_color stores hex only; bold is prepended at injection
        site in application.py (DEC-TUI-PTK-COLOR-COMPAT-001). The row1 style
        token must be 'bold fg:#xxxxxx', not the bare heading_color hex string.
        """
        monkeypatch.delenv("AP_TUI_HIGH_CONTRAST", raising=False)
        app = _make_app("neuromancer")
        theme = theme_for("neuromancer")

        ft = app._get_live_pane_formatted()
        content_parts = [(style, text) for style, text in ft if text != "\n"]
        row1_style = content_parts[0][0]

        expected_style = f"bold fg:{theme.heading_color}"
        assert row1_style == expected_style, (
            f"Row 1 style should be '{expected_style}', got '{row1_style}'. "
            f"The bold modifier must be prepended at the PTK injection site "
            f"(DEC-TUI-PTK-COLOR-COMPAT-001), not stored in heading_color."
        )


# ---------------------------------------------------------------------------
# Mode switch — style tokens change when mode changes
# ---------------------------------------------------------------------------


class TestSwitchingCharacterUpdatesStyleTokens:
    """When the mode changes, the next render cycle applies the new theme colors."""

    def test_switching_character_updates_header_style_tokens(self, monkeypatch) -> None:
        """Switch from default to hal9000; header style tokens must reflect the new color."""
        monkeypatch.delenv("AP_TUI_HIGH_CONTRAST", raising=False)
        app = _make_app("default")

        # Capture style tokens for default mode
        ft_default = app._get_header_formatted()
        default_tokens = {style for style, _ in ft_default if style}

        # Switch the mode manager to hal9000
        app._mode_mgr.switch("hal9000")

        ft_hal = app._get_header_formatted()
        hal_tokens = {style for style, _ in ft_hal if style}

        # The token sets must differ
        assert default_tokens != hal_tokens, (
            "Style tokens did not change after mode switch from default to hal9000. "
            f"default: {default_tokens}, hal9000: {hal_tokens}"
        )
        # hal9000 border color must appear
        hal_border = resolved_border_color(theme_for("hal9000"))
        assert any(hal_border in tok for tok in hal_tokens), (
            f"Expected '{hal_border}' in hal9000 header tokens. Got: {hal_tokens}"
        )

    def test_switching_character_updates_live_pane_style_tokens(self, monkeypatch) -> None:
        """Switch from default to hal9000; live pane style tokens must change."""
        monkeypatch.delenv("AP_TUI_HIGH_CONTRAST", raising=False)
        app = _make_app("default")

        ft_default = app._get_live_pane_formatted()
        default_tokens = {style for style, _ in ft_default if style}

        app._mode_mgr.switch("hal9000")

        ft_hal = app._get_live_pane_formatted()
        hal_tokens = {style for style, _ in ft_hal if style}

        assert default_tokens != hal_tokens, (
            "Live pane style tokens did not change after mode switch. "
            f"default: {default_tokens}, hal9000: {hal_tokens}"
        )


# ---------------------------------------------------------------------------
# High-contrast env var — style tokens swap to #ffffff (white hex)
# ---------------------------------------------------------------------------


class TestHighContrastEnvSwapsStyleTokens:
    """AP_TUI_HIGH_CONTRAST=1 must switch style tokens to the high_contrast_border color (#ffffff)."""

    def test_high_contrast_header_style_is_white_hex(self, monkeypatch) -> None:
        """With AP_TUI_HIGH_CONTRAST=1, header style tokens use #ffffff (white hex).

        Updated in Slice 7Ah2: high_contrast_border is now '#ffffff' (PTK-compatible)
        instead of 'bright_white' (DEC-TUI-PTK-COLOR-COMPAT-001).
        """
        monkeypatch.setenv("AP_TUI_HIGH_CONTRAST", "1")
        app = _make_app("neuromancer")

        ft = app._get_header_formatted()
        style_tokens = [style for style, text in ft if text.strip()]

        assert all("#ffffff" in tok for tok in style_tokens), (
            f"Expected '#ffffff' in all border style tokens with AP_TUI_HIGH_CONTRAST=1. "
            f"Got: {style_tokens}"
        )

    def test_high_contrast_live_pane_style_contains_white_hex(self, monkeypatch) -> None:
        """With AP_TUI_HIGH_CONTRAST=1, live pane rows 2–6 use #ffffff border.

        Updated in Slice 7Ah2: high_contrast_border is now '#ffffff' (PTK-compatible)
        instead of 'bright_white' (DEC-TUI-PTK-COLOR-COMPAT-001).
        """
        monkeypatch.setenv("AP_TUI_HIGH_CONTRAST", "1")
        app = _make_app("neuromancer")

        ft = app._get_live_pane_formatted()
        content_parts = [(style, text) for style, text in ft if text != "\n"]
        # Rows 2–6 (index 1–5) should use fg:#ffffff
        border_row_tokens = [style for style, _ in content_parts[1:]]

        assert all("#ffffff" in tok for tok in border_row_tokens), (
            f"Expected '#ffffff' in live pane rows 2-6 with AP_TUI_HIGH_CONTRAST=1. "
            f"Got: {border_row_tokens}"
        )

    def test_normal_mode_without_high_contrast_uses_character_color(self, monkeypatch) -> None:
        """Without AP_TUI_HIGH_CONTRAST, neuromancer gets #ff5fff (bright_magenta hex), not #ffffff.

        Updated in Slice 7Ah2: hex codes replace Rich color names
        (DEC-TUI-PTK-COLOR-COMPAT-001).
        """
        monkeypatch.delenv("AP_TUI_HIGH_CONTRAST", raising=False)
        app = _make_app("neuromancer")

        ft = app._get_header_formatted()
        style_tokens = [style for style, text in ft if text.strip()]

        assert any("#ff5fff" in tok for tok in style_tokens), (
            f"Expected '#ff5fff' in header tokens without high-contrast. Got: {style_tokens}"
        )
        assert not any(tok == "fg:#ffffff" for tok in style_tokens), (
            f"Did not expect 'fg:#ffffff' without high-contrast. Got: {style_tokens}"
        )


# ---------------------------------------------------------------------------
# Compound interaction — end-to-end render sequence across pane boundaries
# ---------------------------------------------------------------------------


class TestEndToEndRenderSequence:
    """Compound test: header + live pane both carry theme colors simultaneously.

    This is the production sequence: on each PTK render cycle both pane
    builders are called in sequence. They must both resolve the same theme
    and apply consistent color tokens.
    """

    def test_header_and_live_pane_use_same_border_color(self, monkeypatch) -> None:
        """Header and live pane must use the same resolved border color for a given mode."""
        monkeypatch.delenv("AP_TUI_HIGH_CONTRAST", raising=False)
        app = _make_app("chuck_norris")
        theme = theme_for("chuck_norris")
        expected_color = resolved_border_color(theme)  # "#ff5fff" (bright_magenta hex)

        header_ft = app._get_header_formatted()
        live_ft = app._get_live_pane_formatted()

        header_has_color = any(expected_color in style for style, text in header_ft if text.strip())
        live_has_color = any(expected_color in style for style, text in live_ft if text != "\n")

        assert header_has_color, (
            f"Header does not contain '{expected_color}' for chuck_norris. "
            f"Tokens: {[s for s, _ in header_ft]}"
        )
        assert live_has_color, (
            f"Live pane does not contain '{expected_color}' for chuck_norris. "
            f"Tokens: {[s for s, _ in live_ft]}"
        )
