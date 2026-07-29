"""Per-character visual theme system for the AP TUI.

Maps character mode names to hex color strings accepted by BOTH Rich AND
prompt_toolkit. The ``AP_TUI_HIGH_CONTRAST=1`` environment variable switches
every character's border color to ``high_contrast_border`` for accessibility.

@decision DEC-TUI-THEME-001
@title Character-driven theme dispatch for TUI rendering
@status accepted
@rationale Visual design studies established that each character needs a
           distinct palette. Subsequent operator review refined those identities:
           Chuck=leather/burnished gold, HAL=red, Neuromancer=dead-channel
           blue-grey/cyan. Rendering via hex color
           strings is the cheapest terminal-native mechanism accepted by both
           Rich and prompt_toolkit — no Textual dep, no external CSS.
           DEFAULT_THEMES is the SINGLE AUTHORITY for all character color
           strings (Sacred Practice 12). Live pane, scrollback panels, banner,
           and celebrations all read from theme_for() — zero hardcoded style
           strings in render code.

@decision DEC-TUI-HIGH-CONTRAST-001
@title AP_TUI_HIGH_CONTRAST=1 env var switches border to high_contrast_border
@status accepted
@rationale Terminal accessibility: some users run in high-contrast modes where
           colored borders are unreadable. AP_TUI_HIGH_CONTRAST=1 replaces the
           per-character border_color with #ffffff (white), which renders as a
           high-contrast monochrome border on every color scheme. The env var
           is read at call time (not import time) so a running TUI can be
           adjusted without restart via the shell environment — useful for
           accessibility tools that set env vars mid-session. resolved_border_color()
           is the single call site that applies this logic; callers never read the
           env var directly.

@decision DEC-TUI-PTK-COLOR-COMPAT-001
@title All theme color fields store hex-only strings (no modifiers, no Rich names)
@status accepted
@rationale Slice 7Ah2 hotfix: prompt_toolkit's parse_color rejects Rich color
           names (bright_red, bright_magenta, grey50, dark_orange3, etc.) and
           any composite strings containing modifiers (bold, dim). DEFAULT_THEMES
           was originally written with Rich named colors wired into PTK
           FormattedText tuples, causing Wrong color format crashes on the first
           render frame. Fix: all CharacterTheme fields store ONLY hex codes
           (e.g. #ff5555 not bright_red). This is the single authoritative rule:
           every field in CharacterTheme must be parseable by PTK's parse_color
           function. The bold modifier for heading_color is applied at the
           injection site in application.py (bold fg:#xxxxxx) — not stored here.
           Rich accepts hex codes too, so no translation layer is needed.
           The canary test tests/test_tui_themes_ptk_compatible.py runs every
           theme color field through parse_color to enforce this invariant.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

from adversary_pursuit.gamification.modes import canonical_mode_name


@dataclass(frozen=True)
class CharacterTheme:
    """Per-character visual theme applied to the TUI.

    All fields are pure hex color strings (e.g. "#ff5fff", "#ff5555") accepted
    by BOTH Rich and prompt_toolkit's parse_color. Modifiers like ``bold`` or
    ``dim`` are NEVER stored in these fields — they are applied at the injection
    site in application.py (DEC-TUI-PTK-COLOR-COMPAT-001).

    Consumers call theme_for(character_name) to get the theme, then use
    resolved_border_color(theme) for the border (respects high-contrast mode).

    Fields
    ------
    name:
        Canonical character name. Matches DEFAULT_MODES key.
    border_color:
        Hex color string for panel/pane borders (e.g. "#ff5fff").
    accent_color:
        Hex color string for secondary highlights (badges, score lines).
    heading_color:
        Hex color string for headings and character name display. The ``bold``
        modifier is prepended at the PTK injection site, NOT stored here.
    text_color:
        Hex color string for primary body text.
    dim_color:
        Hex color string for secondary/dim text. The ``dim`` visual effect is
        achieved by choosing a darker shade rather than storing "dim ..." here.
    high_contrast_border:
        Accessibility fallback border color when AP_TUI_HIGH_CONTRAST=1.
        Always ``#ffffff`` for every character so the result is a universal
        high-contrast monochrome border (DEC-TUI-HIGH-CONTRAST-001).
    """

    name: str
    border_color: str
    accent_color: str
    heading_color: str
    text_color: str
    dim_color: str
    high_contrast_border: str


@dataclass(frozen=True)
class CockpitProfile:
    """Mode-specific cockpit vocabulary and perspective geometry."""

    deck_name: str
    vehicle: str
    hud_title: str
    left_rail: str
    right_rail: str


@dataclass(frozen=True)
class CharacterPresentation:
    """Reviewed cross-interface contract consumed by TUI and Pivotglass."""

    geometry_family: str
    ambient_layer: str
    motion_language: str
    instrument_vocabulary: tuple[str, ...]
    event_flourish: str
    voice_policy: str
    repetition_budget: int
    music_palette: str


# ---------------------------------------------------------------------------
# DEFAULT_THEMES — single authority for all character visual themes
# (DEC-TUI-THEME-001 / Sacred Practice 12)
# ---------------------------------------------------------------------------

_LEGACY_THEMES: dict[str, CharacterTheme] = {
    # Hex-only colors throughout (DEC-TUI-PTK-COLOR-COMPAT-001).
    # bold / dim modifiers are applied at PTK injection sites, never stored here.
    # high_contrast_border is #ffffff for every character (DEC-TUI-HIGH-CONTRAST-001).
    "default": CharacterTheme(
        name="default",
        border_color="#00d7d7",  # cyan
        accent_color="#00d700",  # green
        heading_color="#00d7d7",  # cyan — bold prepended at PTK injection site
        text_color="#ffffff",  # white
        dim_color="#5f5f5f",  # dim white (dark grey approximation)
        high_contrast_border="#ffffff",
    ),
    "ninja": CharacterTheme(
        name="ninja",
        border_color="#808080",  # grey50
        accent_color="#b3b3b3",  # grey70
        heading_color="#ffffff",  # white — bold prepended at PTK injection site
        text_color="#d9d9d9",  # grey85
        dim_color="#4d4d4d",  # grey30 (dim shade)
        high_contrast_border="#ffffff",
    ),
    "full_troll": CharacterTheme(
        name="full_troll",
        border_color="#ffff5f",  # bright_yellow
        accent_color="#ff5fff",  # bright_magenta
        heading_color="#ffff5f",  # bright_yellow — bold prepended at PTK injection site
        text_color="#ffffff",  # bright_white
        dim_color="#7a7a00",  # dim yellow (dark yellow)
        high_contrast_border="#ffffff",
    ),
    "drunken_master": CharacterTheme(
        name="drunken_master",
        border_color="#d78700",
        accent_color="#ffff5f",
        heading_color="#d78700",
        text_color="#ffffff",
        dim_color="#5f3f00",
        high_contrast_border="#ffffff",
    ),
    "sun_tzu": CharacterTheme(
        name="sun_tzu",
        border_color="#d7d700",  # yellow
        accent_color="#ffd700",  # gold1
        heading_color="#d7d700",  # yellow — bold prepended at PTK injection site
        text_color="#ffffff",  # white
        dim_color="#7a7a00",  # dim yellow (dark yellow)
        high_contrast_border="#ffffff",
    ),
    "chuck_norris": CharacterTheme(
        # Burnished leather, dust, brass, and arena light.
        name="chuck_norris",
        border_color="#d78700",
        accent_color="#ffd75f",
        heading_color="#ffaf5f",
        text_color="#fff4d7",
        dim_color="#875f3f",
        high_contrast_border="#ffffff",
    ),
    "bureaucrat": CharacterTheme(
        name="bureaucrat",
        border_color="#ffffff",  # white
        accent_color="#00d7d7",  # cyan
        heading_color="#ffffff",  # white — bold prepended at PTK injection site
        text_color="#ffffff",  # white
        dim_color="#5f5f5f",  # dim white (dark grey approximation)
        high_contrast_border="#ffffff",
    ),
    "bobby_hill": CharacterTheme(
        name="bobby_hill",
        border_color="#5fff5f",  # bright_green
        accent_color="#d7d700",  # yellow
        heading_color="#5fff5f",  # bright_green — bold prepended at PTK injection site
        text_color="#ffffff",  # bright_white
        dim_color="#005f00",  # dim green (dark green)
        high_contrast_border="#ffffff",
    ),
    "bruce_lee": CharacterTheme(
        name="bruce_lee",
        border_color="#5f5fff",  # bright_blue
        accent_color="#00d7d7",  # cyan
        heading_color="#5f5fff",  # bright_blue — bold prepended at PTK injection site
        text_color="#ffffff",  # white
        dim_color="#00005f",  # dim blue (dark blue)
        high_contrast_border="#ffffff",
    ),
    "columbo": CharacterTheme(
        name="columbo",
        border_color="#d7d700",  # yellow
        accent_color="#ffff5f",  # bright_yellow
        heading_color="#d7d700",  # yellow — bold prepended at PTK injection site
        text_color="#ffffff",  # white
        dim_color="#7a7a00",  # dim yellow (dark yellow)
        high_contrast_border="#ffffff",
    ),
    "deckard": CharacterTheme(
        name="deckard",
        border_color="#d78700",  # dark_orange3
        accent_color="#ffe4b5",  # wheat1
        heading_color="#d78700",  # dark_orange3 — bold prepended at PTK injection site
        text_color="#d9d9d9",  # grey85
        dim_color="#7a5000",  # dim orange3 (dark orange)
        high_contrast_border="#ffffff",
    ),
    "hal9000": CharacterTheme(
        # Storyboard: red palette (AP-TUI-HAL-mockup.png)
        name="hal9000",
        border_color="#ff5555",  # bright_red
        accent_color="#d7d700",  # yellow
        heading_color="#ff5555",  # bright_red — bold prepended at PTK injection site
        text_color="#00d7d7",  # cyan
        dim_color="#7a0000",  # dim red (dark red)
        high_contrast_border="#ffffff",
    ),
    "neuromancer": CharacterTheme(
        # Dead-channel blue-grey with cold deck cyan.
        name="neuromancer",
        border_color="#8787af",
        accent_color="#5fd7d7",
        heading_color="#afbfff",
        text_color="#e4e4e4",
        dim_color="#5f5f87",
        high_contrast_border="#ffffff",
    ),
    "trinity": CharacterTheme(
        name="trinity",
        border_color="#00ff5f",  # matrix green
        accent_color="#ffffff",  # white rabbit
        heading_color="#00ff5f",
        text_color="#d7ffd7",
        dim_color="#005f2f",
        high_contrast_border="#ffffff",
    ),
}

DEFAULT_THEMES: dict[str, CharacterTheme] = {
    "default": _LEGACY_THEMES["default"],
    "ninja": _LEGACY_THEMES["ninja"],
    "full_troll": _LEGACY_THEMES["full_troll"],
    "bureaucrat": _LEGACY_THEMES["bureaucrat"],
    "strategist": replace(_LEGACY_THEMES["sun_tzu"], name="strategist"),
    "sensei": replace(_LEGACY_THEMES["chuck_norris"], name="sensei"),
    "detective": CharacterTheme(
        name="detective",
        border_color="#b8860b",
        accent_color="#d2b48c",
        heading_color="#f0d9b5",
        text_color="#f5eee3",
        dim_color="#a88f73",
        high_contrast_border="#ffffff",
    ),
    "the_computer": replace(_LEGACY_THEMES["hal9000"], name="the_computer"),
    "the_sprawl": replace(_LEGACY_THEMES["neuromancer"], name="the_sprawl"),
    "m4tr1x": replace(_LEGACY_THEMES["trinity"], name="m4tr1x"),
}

_LIGHT_THEMES: dict[str, CharacterTheme] = {
    "default": CharacterTheme("default", "#0b6572", "#17643c", "#064f5b", "#111820", "#45545c", "#000000"),
    "sensei": CharacterTheme("sensei", "#8a3f12", "#765500", "#6f2e0b", "#211a12", "#5d5041", "#000000"),
    "the_computer": CharacterTheme("the_computer", "#a51d29", "#745900", "#86131e", "#201617", "#624b4d", "#000000"),
    "full_troll": CharacterTheme("full_troll", "#526600", "#7b2684", "#425300", "#1c171f", "#594d5d", "#000000"),
    "detective": CharacterTheme("detective", "#754414", "#28604f", "#60340c", "#211b15", "#5c5145", "#000000"),
    "the_sprawl": CharacterTheme("the_sprawl", "#46536f", "#006a68", "#34415c", "#161a22", "#515a6d", "#000000"),
    "m4tr1x": CharacterTheme("m4tr1x", "#116329", "#104e2b", "#0a5220", "#101b13", "#43594a", "#000000"),
}


# Character-specific name for the main investigation surface. This is UI
# vocabulary, so it lives beside the character visual themes rather than in
# the analytical mode/persona schema.
_LEGACY_PURSUIT_TITLES: dict[str, str] = {
    "default": "THE HUNT",
    "ninja": "THE SHADOWS",
    "full_troll": "THE THUNDERDOME",
    "drunken_master": "THE TAVERN",
    "sun_tzu": "THE WAR ROOM",
    "chuck_norris": "THE ARENA",
    "bureaucrat": "THE CASE FILE",
    "bobby_hill": "THE BACK ALLEY",
    "bruce_lee": "THE DOJO",
    "columbo": "THE PRECINCT",
    "deckard": "THE RAIN",
    "hal9000": "DEEP SPACE",
    "neuromancer": "THE SPRAWL",
    "trinity": "THE MATRIX",
}

PURSUIT_TITLES: dict[str, str] = {
    "default": "THE HUNT",
    "ninja": "THE SHADOWS",
    "full_troll": "THE THUNDERDOME",
    "bureaucrat": "THE CASE FILE",
    "strategist": "THE WAR ROOM",
    "sensei": "THE ROUNDHOUSE",
    "detective": "THE DEDUCTION",
    "the_computer": "THE LOGIC CORE",
    "the_sprawl": "THE SPRAWL",
    "m4tr1x": "THE MATRIX",
}


_LEGACY_COCKPIT_PROFILES: dict[str, CockpitProfile] = {
    "default": CockpitProfile("HUNT CONTROL", "AP-01 PURSUIT DECK", "TACTICAL HUD", "╲", "╱"),
    "ninja": CockpitProfile("SHADOW SCOPE", "NIGHT-RUNNER", "SILENT TELEMETRY", "⟍", "⟋"),
    "full_troll": CockpitProfile("THUNDERDOME", "CHAOS WAGON", "HYPE METERS", "⚡", "⚡"),
    "drunken_master": CockpitProfile("TAVERN GYRO", "WOBBLE-CLASS SKIFF", "BALANCE BOARD", "≈", "≈"),
    "sun_tzu": CockpitProfile("WAR TABLE", "COMMAND CHARIOT", "BATTLE MAP", "《", "》"),
    "chuck_norris": CockpitProfile("STRIKE ARENA", "ROUNDHOUSE-1", "THREAT LOCK", "◢", "◣"),
    "bureaucrat": CockpitProfile("CASE FILE", "FORM 27-B/6", "COMPLIANCE HUD", "┏", "┓"),
    "bobby_hill": CockpitProfile("BACK ALLEY", "PURSE DEFENDER", "DANG-IT PANEL", "╱", "╲"),
    "bruce_lee": CockpitProfile("FLOW DECK", "INTERCEPTOR WATER", "FLOW STATE", "〈", "〉"),
    "columbo": CockpitProfile("PRECINCT DESK", "PEUGEOT 403", "ONE MORE THING", "⌜", "⌝"),
    "deckard": CockpitProfile("RAIN SCOPE", "SPINNER 9732", "VOIGHT-KAMPFF HUD", "◥", "◤"),
    "hal9000": CockpitProfile("DEEP SPACE", "DISCOVERY ONE", "HAL OPTICS", "◉", "◉"),
    "neuromancer": CockpitProfile("THE SPRAWL", "ONO-SENDAI VII", "ICE MONITOR", "⟫", "⟪"),
    "trinity": CockpitProfile("THE MATRIX", "NEBUCHADNEZZAR", "OPERATOR LINK", "⧹", "⧸"),
}

COCKPIT_PROFILES: dict[str, CockpitProfile] = {
    "default": _LEGACY_COCKPIT_PROFILES["default"],
    "ninja": _LEGACY_COCKPIT_PROFILES["ninja"],
    "full_troll": _LEGACY_COCKPIT_PROFILES["full_troll"],
    "bureaucrat": _LEGACY_COCKPIT_PROFILES["bureaucrat"],
    "strategist": _LEGACY_COCKPIT_PROFILES["sun_tzu"],
    "sensei": _LEGACY_COCKPIT_PROFILES["chuck_norris"],
    "detective": CockpitProfile("BAKER STREET", "VICTORIAN CASEBOOK", "DEDUCTION ENGINE", "⌜", "⌝"),
    "the_computer": _LEGACY_COCKPIT_PROFILES["hal9000"],
    "the_sprawl": _LEGACY_COCKPIT_PROFILES["neuromancer"],
    "m4tr1x": _LEGACY_COCKPIT_PROFILES["trinity"],
}


PRESENTATION_CONTRACTS: dict[str, CharacterPresentation] = {
    "default": CharacterPresentation("cockpit", "radar", "measured", ("power", "tokens", "dossier"), "sweep", "neutral analyst", 2, "control_room"),
    "ninja": CharacterPresentation("shadow_scope", "mist", "minimal", ("trace", "silence", "lock"), "vanish", "terse and exact", 1, "night_ops"),
    "full_troll": CharacterPresentation("arcade_rig", "glitch", "punchy", ("hype", "combo", "loot"), "screen_shake", "sarcastic sidekick; evidence stays explicit", 3, "chaos_arcade"),
    "bureaucrat": CharacterPresentation("form_terminal", "paper", "procedural", ("forms", "queue", "compliance"), "stamp", "dry procedural deadpan", 2, "office_machine"),
    "strategist": CharacterPresentation("war_table", "ink_map", "deliberate", ("terrain", "initiative", "reserve"), "standard_unfurls", "patient strategic guidance", 2, "war_room"),
    "sensei": CharacterPresentation("action_arena", "impact", "punchy", ("threat", "roundhouse", "proof"), "impact_stamp", "impossible confidence; bounded jokes", 3, "action_brass"),
    "detective": CharacterPresentation("victorian_casebook", "gaslight", "deductive", ("observations", "inferences", "threads"), "deduction_pin", "clever, deductive, slightly too assured", 3, "chamber_mystery"),
    "the_computer": CharacterPresentation("system_core", "lens", "precise", ("logic", "resources", "confidence"), "diagnostic", "calm, exact, dryly sarcastic", 2, "mainframe"),
    "the_sprawl": CharacterPresentation("perspective_grid", "city_noise", "urgent", ("ice", "signal", "deck"), "grid_ripple", "noir-tech second person", 3, "sprawl_night"),
    "m4tr1x": CharacterPresentation("construct", "code_rain", "kinetic", ("signal", "trace", "operator"), "white_rabbit", "kinetic operator; signal first", 2, "construct_rain"),
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
    resolved = canonical_mode_name(character_name, allow_retired=True)
    if os.environ.get("AP_TUI_COLOR_SCHEME", "dark").lower() == "light":
        theme = _LIGHT_THEMES.get(resolved, _LIGHT_THEMES["default"])
    else:
        theme = DEFAULT_THEMES.get(resolved, DEFAULT_THEMES["default"])
    if is_high_contrast_mode():
        light = os.environ.get("AP_TUI_COLOR_SCHEME", "dark").lower() == "light"
        return replace(
            theme,
            border_color="#000000" if light else "#ffffff",
            accent_color="#004f59" if light else "#ffff5f",
            heading_color="#000000" if light else "#ffffff",
            text_color="#000000" if light else "#ffffff",
            dim_color="#303030" if light else "#d9d9d9",
        )
    return theme


def pursuit_title_for(character_name: str) -> str:
    """Return the mode-specific title for the live investigation surface."""
    resolved = canonical_mode_name(character_name, allow_retired=True)
    return PURSUIT_TITLES.get(resolved, PURSUIT_TITLES["default"])


def cockpit_for(character_name: str) -> CockpitProfile:
    """Return the mode's cockpit profile, falling back to hunt control."""
    resolved = canonical_mode_name(character_name, allow_retired=True)
    return COCKPIT_PROFILES.get(resolved, COCKPIT_PROFILES["default"])


def presentation_for(character_name: str) -> CharacterPresentation:
    """Return the canonical cross-interface presentation contract."""
    resolved = canonical_mode_name(character_name, allow_retired=True)
    return PRESENTATION_CONTRACTS.get(resolved, PRESENTATION_CONTRACTS["default"])


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
