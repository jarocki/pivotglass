"""Per-character visual theme system for the AP TUI.

Maps character mode names to Rich-compatible color strings used for border,
accent, heading, text, and dim surfaces throughout the TUI. The
``AP_TUI_HIGH_CONTRAST=1`` environment variable switches every character's
border color to ``high_contrast_border`` for accessibility.

@decision DEC-TUI-THEME-001
@title Character-driven theme dispatch for TUI rendering
@status accepted
@rationale Storyboard mockups (storyboard/AP-TUI-Chuck-mockup.png,
           AP-TUI-HAL-mockup.png, AP-TUI-neuromancer-mockup.png) established
           that each character has a distinct color palette: Chuck=magenta neon,
           HAL=red, Neuromancer=purple/pink cyberpunk. Rendering via Rich color
           strings is the cheapest terminal-native mechanism — no Textual dep,
           no external CSS. DEFAULT_THEMES is the SINGLE AUTHORITY for all
           character color strings (Sacred Practice 12). Live pane, scrollback
           panels, banner, and celebrations all read from theme_for() — zero
           hardcoded style strings in render code.

@decision DEC-TUI-HIGH-CONTRAST-001
@title AP_TUI_HIGH_CONTRAST=1 env var switches border to high_contrast_border
@status accepted
@rationale Terminal accessibility: some users run in high-contrast modes where
           colored borders are unreadable. AP_TUI_HIGH_CONTRAST=1 replaces the
           per-character border_color with bright_white, which renders as a
           high-contrast monochrome border on every color scheme. The env var
           is read at call time (not import time) so a running TUI can be
           adjusted without restart via the shell environment — useful for
           accessibility tools that set env vars mid-session. resolved_border_color()
           is the single call site that applies this logic; callers never read the
           env var directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CharacterTheme:
    """Per-character visual theme applied to the TUI.

    All fields are Rich color/style strings (e.g. "bright_magenta", "bold cyan").
    Consumers call theme_for(character_name) to get the theme, then use
    resolved_border_color(theme) for the border (respects high-contrast mode).

    Fields
    ------
    name:
        Canonical character name. Matches DEFAULT_MODES key.
    border_color:
        Rich color string for panel/pane borders.
    accent_color:
        Rich color string for secondary highlights (badges, score lines).
    heading_color:
        Rich style string for headings and character name display.
    text_color:
        Rich color string for primary body text.
    dim_color:
        Rich color/style string for secondary/dim text.
    high_contrast_border:
        Accessibility fallback border color when AP_TUI_HIGH_CONTRAST=1.
        Always ``bright_white`` for every character so the result is a
        universal high-contrast monochrome border.
    """

    name: str
    border_color: str
    accent_color: str
    heading_color: str
    text_color: str
    dim_color: str
    high_contrast_border: str


# ---------------------------------------------------------------------------
# DEFAULT_THEMES — single authority for all character visual themes
# (DEC-TUI-THEME-001 / Sacred Practice 12)
# ---------------------------------------------------------------------------

DEFAULT_THEMES: dict[str, CharacterTheme] = {
    "default": CharacterTheme(
        name="default",
        border_color="cyan",
        accent_color="green",
        heading_color="bold cyan",
        text_color="white",
        dim_color="dim white",
        high_contrast_border="bright_white",
    ),
    "ninja": CharacterTheme(
        name="ninja",
        border_color="grey50",
        accent_color="grey70",
        heading_color="bold white",
        text_color="grey85",
        dim_color="grey30",
        high_contrast_border="bright_white",
    ),
    "full_troll": CharacterTheme(
        name="full_troll",
        border_color="bright_yellow",
        accent_color="bright_magenta",
        heading_color="bold bright_yellow",
        text_color="bright_white",
        dim_color="dim yellow",
        high_contrast_border="bright_white",
    ),
    "sun_tzu": CharacterTheme(
        name="sun_tzu",
        border_color="yellow",
        accent_color="gold1",
        heading_color="bold yellow",
        text_color="white",
        dim_color="dim yellow",
        high_contrast_border="bright_white",
    ),
    "chuck_norris": CharacterTheme(
        # Storyboard: magenta neon palette (AP-TUI-Chuck-mockup.png)
        name="chuck_norris",
        border_color="bright_magenta",
        accent_color="cyan",
        heading_color="bold bright_magenta",
        text_color="bright_green",
        dim_color="dim magenta",
        high_contrast_border="bright_white",
    ),
    "bureaucrat": CharacterTheme(
        name="bureaucrat",
        border_color="white",
        accent_color="cyan",
        heading_color="bold white",
        text_color="white",
        dim_color="dim white",
        high_contrast_border="bright_white",
    ),
    "bobby_hill": CharacterTheme(
        name="bobby_hill",
        border_color="bright_green",
        accent_color="yellow",
        heading_color="bold bright_green",
        text_color="bright_white",
        dim_color="dim green",
        high_contrast_border="bright_white",
    ),
    "bruce_lee": CharacterTheme(
        name="bruce_lee",
        border_color="bright_blue",
        accent_color="cyan",
        heading_color="bold bright_blue",
        text_color="white",
        dim_color="dim blue",
        high_contrast_border="bright_white",
    ),
    "columbo": CharacterTheme(
        name="columbo",
        border_color="yellow",
        accent_color="bright_yellow",
        heading_color="bold yellow",
        text_color="white",
        dim_color="dim yellow",
        high_contrast_border="bright_white",
    ),
    "deckard": CharacterTheme(
        name="deckard",
        border_color="dark_orange3",
        accent_color="wheat1",
        heading_color="bold dark_orange3",
        text_color="grey85",
        dim_color="dim orange3",
        high_contrast_border="bright_white",
    ),
    "hal9000": CharacterTheme(
        # Storyboard: red palette (AP-TUI-HAL-mockup.png)
        name="hal9000",
        border_color="bright_red",
        accent_color="yellow",
        heading_color="bold bright_red",
        text_color="cyan",
        dim_color="dim red",
        high_contrast_border="bright_white",
    ),
    "neuromancer": CharacterTheme(
        # Storyboard: purple/pink cyberpunk palette (AP-TUI-neuromancer-mockup.png)
        name="neuromancer",
        border_color="bright_magenta",
        accent_color="bright_cyan",
        heading_color="bold bright_magenta",
        text_color="yellow",
        dim_color="dim magenta",
        high_contrast_border="bright_white",
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def theme_for(character_name: str) -> CharacterTheme:
    """Return the CharacterTheme for *character_name*.

    Falls back to DEFAULT_THEMES["default"] for unknown characters so new
    modes added without a matching theme degrade gracefully instead of raising.

    Parameters
    ----------
    character_name:
        Canonical character mode name (e.g. "neuromancer", "hal9000").

    Returns
    -------
    CharacterTheme
        The theme for the requested character, or the default theme.
    """
    return DEFAULT_THEMES.get(character_name, DEFAULT_THEMES["default"])


def is_high_contrast_mode() -> bool:
    """Return True when AP_TUI_HIGH_CONTRAST=1 is set in the environment.

    Read at call time (not import time) so changes during a session take
    effect on the next render cycle (DEC-TUI-HIGH-CONTRAST-001).

    Returns
    -------
    bool
        True when ``AP_TUI_HIGH_CONTRAST`` env var equals ``"1"``.
    """
    return os.environ.get("AP_TUI_HIGH_CONTRAST") == "1"


def resolved_border_color(theme: CharacterTheme) -> str:
    """Return the effective border color for *theme*, respecting high-contrast mode.

    This is the single call site that applies the AP_TUI_HIGH_CONTRAST override
    (DEC-TUI-HIGH-CONTRAST-001). All renderers must call this function rather
    than reading theme.border_color directly.

    Parameters
    ----------
    theme:
        A CharacterTheme instance from theme_for().

    Returns
    -------
    str
        ``theme.high_contrast_border`` when AP_TUI_HIGH_CONTRAST=1,
        otherwise ``theme.border_color``.
    """
    if is_high_contrast_mode():
        return theme.high_contrast_border
    return theme.border_color
