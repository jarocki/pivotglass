"""Smoke test: TuiApplication FormattedText style tokens survive PTK's style parser.

Instead of requiring a full TTY, this test feeds every style token from
_get_header_formatted() and _get_live_pane_formatted() through
prompt_toolkit.styles.style._parse_style_str — the same internal parser PTK
uses when painting cells. If any style token is invalid (e.g. 'fg:bright_red'),
_parse_style_str raises ValueError — exactly the crash operators hit in Slice 7Ah2.

This is the compound-interaction test that crosses the boundary between:
  - themes.py (DEFAULT_THEMES, resolved_border_color)
  - application.py (_get_header_formatted, _get_live_pane_formatted)
  - prompt_toolkit style parsing

Together these prove the full PTK render sequence works for every character mode.

@decision DEC-TUI-PTK-COLOR-COMPAT-001
@title All theme color fields store hex-only strings (no modifiers, no Rich names)
@status accepted
@rationale See themes.py. This smoke test is the end-to-end enforcement that the
           hex-only invariant is correctly wired through application.py's style
           token assembly and survives PTK's internal style parser.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch  # @mock-exempt: sys.stdin.isatty is OS/TTY boundary

import pytest
from prompt_toolkit.styles.style import _parse_style_str  # type: ignore[attr-defined]

from adversary_pursuit.agent.tui.application import TuiApplication
from adversary_pursuit.agent.tui.events import EventBus
from adversary_pursuit.agent.tui.themes import DEFAULT_THEMES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL_CHARACTERS = list(DEFAULT_THEMES.keys())


class _FakeMode:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeModeManager:
    def __init__(self, name: str) -> None:
        self.active = _FakeMode(name)


def _make_app(mode_name: str) -> TuiApplication:
    """Construct a TuiApplication stub for the given character mode."""
    bus = EventBus()

    # @mock-exempt: sys.stdin.isatty is OS/TTY boundary (no TTY in CI)
    # @mock-exempt: _build_app creates a real PTK Application which requires a terminal
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch.object(TuiApplication, "_build_app", return_value=MagicMock()),
    ):
        app = TuiApplication(
            runner=None,
            workspace_mgr=None,
            mode_mgr=_FakeModeManager(mode_name),
            event_bus=bus,
        )
    return app


def _assert_all_style_tokens_parseable(formatted_text, pane_name: str, mode_name: str) -> None:
    """Assert every non-empty style token parses cleanly via PTK's _parse_style_str.

    _parse_style_str is the internal function PTK's render engine calls when
    building cell attributes from FormattedText style strings. It raises
    ValueError for invalid color names (the Slice 7Ah2 crash class).
    """
    for style_str, text in formatted_text:
        if not style_str:
            continue  # empty style token is always valid
        try:
            _parse_style_str(style_str)
        except Exception as exc:
            pytest.fail(
                f"[{mode_name}] {pane_name}: style token {style_str!r} for "
                f"text {text[:30]!r} failed PTK _parse_style_str: {exc}\n"
                f"This is the Slice 7Ah2 bug class — a Rich color name or modifier "
                f"was embedded in a PTK style string. Fix: use hex codes only in "
                f"DEFAULT_THEMES and assemble 'bold fg:#xxxxxx' at the injection "
                f"site (DEC-TUI-PTK-COLOR-COMPAT-001)."
            )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode_name", _ALL_CHARACTERS)
def test_header_formatted_text_style_tokens_ptk_parseable(mode_name: str) -> None:
    """_get_header_formatted() style tokens must survive PTK's parser for every character.

    This is the compound-interaction test that catches the Slice 7Ah2 crash class:
    theme_for(mode) → resolved_border_color → 'fg:<color>' token → PTK parser.
    All three steps must agree on valid hex colors (DEC-TUI-PTK-COLOR-COMPAT-001).
    """
    app = _make_app(mode_name)
    ft = app._get_header_formatted()
    _assert_all_style_tokens_parseable(ft, "header", mode_name)


@pytest.mark.parametrize("mode_name", _ALL_CHARACTERS)
def test_live_pane_formatted_text_style_tokens_ptk_parseable(mode_name: str) -> None:
    """_get_live_pane_formatted() style tokens must survive PTK's parser for every character.

    Row 0 uses 'bold fg:<heading_color>' (modifier-outside-fg: form).
    Rows 1–5 use 'fg:<border_color>'.
    Both forms must be accepted by PTK (DEC-TUI-PTK-COLOR-COMPAT-001).
    """
    app = _make_app(mode_name)
    ft = app._get_live_pane_formatted()
    _assert_all_style_tokens_parseable(ft, "live_pane", mode_name)


def test_heading_row_uses_bold_fg_hex_form() -> None:
    """Live pane row 0 must use 'bold fg:#xxxxxx', not 'fg:bold ...' or bare heading_color.

    PTK accepts 'bold fg:#ff5555' (modifier + color as separate tokens)
    but rejects 'fg:bold #ff5555' (modifier inside fg:). Verify the correct form
    is assembled by application.py (DEC-TUI-PTK-COLOR-COMPAT-001).
    """
    from adversary_pursuit.agent.tui.themes import theme_for

    app = _make_app("hal9000")
    ft = app._get_live_pane_formatted()
    content_parts = [(style, text) for style, text in ft if text != "\n"]

    row0_style = content_parts[0][0]
    theme = theme_for("hal9000")

    # Must be 'bold fg:#ff5555' — not 'fg:bold ...' or bare '#ff5555'
    expected = f"bold fg:{theme.heading_color}"
    assert row0_style == expected, (
        f"Live pane row 0 style is {row0_style!r}, expected {expected!r}. "
        f"The bold modifier must be a separate PTK token before fg:, not embedded "
        f"inside it (DEC-TUI-PTK-COLOR-COMPAT-001)."
    )
    # Assert the assembled form is also PTK-parseable
    try:
        _parse_style_str(row0_style)
    except Exception as exc:
        pytest.fail(f"Heading row style {row0_style!r} failed PTK _parse_style_str: {exc}")
