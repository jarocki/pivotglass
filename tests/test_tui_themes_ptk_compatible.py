"""PTK-format canary for TUI themes (DEC-TUI-PTK-COLOR-COMPAT-001).

Prevents the recurrence of the Slice 7Ah2 bug where Rich color names like
'bright_red' were populated into PTK FormattedText and crashed at render time
with ``ValueError: Wrong color format 'bright_red'``.

This test directly invokes prompt_toolkit's parse_color to assert every theme
color field would be accepted by PTK's parser. It bypasses the TTY-required
render path so it runs cleanly in CI.

Why parse_color is the right canary:
- PTK's render pipeline calls parse_color on every style token before painting.
- If parse_color raises, the entire render frame fails — the crash users saw.
- parse_color accepts: hex codes (#rrggbb), basic CSS names (red, white, cyan…),
  and ansi<name> variants. It rejects Rich-specific names (bright_red, grey50,
  dark_orange3) and composite strings (bold cyan, dim white).
- Storing only hex codes in DEFAULT_THEMES (DEC-TUI-PTK-COLOR-COMPAT-001) is
  the fix: hex is accepted by BOTH Rich and PTK with no translation layer.

@decision DEC-TUI-PTK-COLOR-COMPAT-001
@title All theme color fields store hex-only strings (no modifiers, no Rich names)
@status accepted
@rationale See themes.py for the full rationale. This canary is the enforcement
           mechanism: any future theme entry that adds a Rich color name or a
           modifier-embedded color string will immediately fail this test.
"""

from __future__ import annotations

import pytest
from prompt_toolkit.styles.style import parse_color

from adversary_pursuit.agent.tui.themes import DEFAULT_THEMES

# Every field that is used as a PTK color value (fed to fg: or as a bare style
# token in FormattedText). bold/dim modifiers are applied at injection sites and
# never stored here, so all these fields must be parse_color-clean.
_THEME_COLOR_FIELDS = (
    "border_color",
    "accent_color",
    "heading_color",
    "text_color",
    "dim_color",
    "high_contrast_border",
)


@pytest.mark.parametrize(
    "character,field",
    [(char, field) for char in DEFAULT_THEMES for field in _THEME_COLOR_FIELDS],
)
def test_theme_color_is_ptk_parseable(character: str, field: str) -> None:
    """Every theme color field must be accepted by prompt_toolkit's parse_color.

    If this test fails for a new theme entry, the color value in DEFAULT_THEMES
    is not PTK-compatible. Convert it to a hex code (#rrggbb) to fix.
    Reference: DEC-TUI-PTK-COLOR-COMPAT-001 in themes.py.
    """
    theme = DEFAULT_THEMES[character]
    color_value = getattr(theme, field, None)
    if color_value is None or color_value == "":
        pytest.skip(f"{character}.{field} is empty; nothing to parse")

    # parse_color raises ValueError for invalid color strings.
    # This is the exact function PTK's render pipeline calls.
    try:
        result = parse_color(color_value)
    except ValueError as exc:
        pytest.fail(
            f"DEFAULT_THEMES['{character}'].{field} = {color_value!r} is not "
            f"accepted by prompt_toolkit's parse_color: {exc}\n"
            f"Fix: convert to a hex code (e.g. '#ff5555') so it is accepted by "
            f"both Rich and PTK (DEC-TUI-PTK-COLOR-COMPAT-001)."
        )

    # parse_color returns the normalised color string (e.g. 'ff5555' for '#ff5555').
    # A non-None result confirms PTK accepted the value.
    assert result is not None, f"parse_color({color_value!r}) returned None for {character}.{field}"


def test_all_theme_color_fields_are_hex(character: str = "default") -> None:
    """Spot-check: default theme colors are all hex strings starting with '#'.

    This complements the parametrized canary: it checks the invariant that
    DEFAULT_THEMES stores hex codes (not named colors) for every field.
    A hex-only policy is the simplest guarantee of PTK compatibility because
    parse_color unconditionally accepts #rrggbb (DEC-TUI-PTK-COLOR-COMPAT-001).
    """
    for char_name, theme in DEFAULT_THEMES.items():
        for field in _THEME_COLOR_FIELDS:
            value = getattr(theme, field)
            assert value.startswith("#"), (
                f"DEFAULT_THEMES['{char_name}'].{field} = {value!r} is not a hex "
                f"color. All theme color fields must be hex strings (#rrggbb) for "
                f"PTK compatibility (DEC-TUI-PTK-COLOR-COMPAT-001). Convert to hex."
            )
            assert len(value) == 7, (
                f"DEFAULT_THEMES['{char_name}'].{field} = {value!r} is not a valid "
                f"6-digit hex color (expected '#rrggbb', 7 chars)."
            )
