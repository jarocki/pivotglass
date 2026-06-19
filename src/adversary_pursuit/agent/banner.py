"""ASCII art boot banner and ANSI animation helpers for AP chat.

Provides:
  - ``render_boot_banner(console)`` — figlet wordmark + reticle motif + metadata
    strip on boot.  Skipped entirely when ``AP_NO_BANNER=1`` (CI).
  - ``get_mode_color(mode_name)`` — mode-specific colour string for the prompt
    prefix so every character mode has its own visual identity.
  - ``thinking_status(console)`` — context-manager wrapping Rich Status spinner
    shown while the LLM is thinking.

Design constraints
------------------
* Total boot animation ≤ 500 ms (sub-second is non-negotiable for UX).
* ``AP_NO_BANNER=1`` disables all output including the animation so CI tests
  produce clean stdout.
* No external dependencies beyond Rich (already a core dep) and pyfiglet
  (pure-Python figlet renderer, added Phase 17Q — DEC-AGENT-BANNER-002).
* Wordmark is pre-rendered at module import time so the 500 ms budget is
  preserved — no per-call figlet cost.

@decision DEC-AGENT-BANNER-001
@title Rich-based boot banner with figlet wordmark, reticle motif, and metadata strip
@status accepted
@rationale Phase 17Q replaces the previous radar-dish ASCII art block (lines
           49-57, containing a cluttered [AP] + [*] clip-art that read as
           redundant double-naming with the Rich Panel title) with a 3-column
           layout: (1) figlet 'ap' wordmark in ansi_shadow font, gradient-
           coloured row-by-row using Rich named-color strings; (2) a 5-row box-
           drawing crosshair/reticle motif (CTI reticle aesthetic); (3) a
           metadata strip showing title, tagline, version, IOC count, and
           active streak.  Deep-research session 2026-06-17 evaluated four
           options and the user approved Option 1.  All output goes through the
           caller-supplied Rich Console so tests can capture it via
           Console(file=StringIO).  The AP_NO_BANNER env guard, Rich named-
           color discipline, streak integration (DEC-62-STREAK-006), and
           typewriter tagline are all preserved from the prior design.  Width
           fallback: when console.size.width < 60 the compact variant renders
           just the figlet 'small' wordmark with no reticle so the banner stays
           usable in narrow tmux panes.
           Research dir: .claude/research/DeepResearch_AP_AdversaryPursuit_Logo_2026-06-17/

@decision DEC-AGENT-BANNER-002
@title pyfiglet>=1.0 as the figlet rendering dependency
@status accepted
@rationale pyfiglet is pure-Python (no native dependencies), ships ~419 bundled
           fonts including ansi_shadow and small used here, and is the standard
           CLI figlet renderer (used by the Metasploit / Recon-ng pattern and
           countless security tools).  Rendering is performed ONCE at module
           import time (constants _WORDMARK_DEFAULT and _WORDMARK_COMPACT) so
           the per-call path is just a string lookup — preserving the 500 ms
           boot budget mandated by DEC-AGENT-BANNER-001.  The dependency is
           pure-Python and adds no C-extension complexity to the build.
"""

from __future__ import annotations

import importlib.metadata
import os
import time
from contextlib import contextmanager
from typing import Generator

import pyfiglet
from rich.console import Console
from rich.panel import Panel
from rich.style import Style
from rich.text import Text

# ---------------------------------------------------------------------------
# Pre-rendered figlet wordmarks (module-load time — keeps per-call cost O(1))
# ---------------------------------------------------------------------------

# ansi_shadow render of "ap" — used in the default (wide) layout.
# Pre-rendered once at import to honour the ≤500 ms boot budget.
_WORDMARK_DEFAULT: str = pyfiglet.figlet_format("ap", font="ansi_shadow")

# small render of "ap" — used in the compact (narrow, width < 60) layout.
_WORDMARK_COMPACT: str = pyfiglet.figlet_format("ap", font="small")

# ---------------------------------------------------------------------------
# Reticle motif
# ---------------------------------------------------------------------------

# 5-row × 7-col crosshair box in box-drawing characters and Unicode symbols.
# Outer brackets rendered dim; crosshair symbols rendered bold yellow.
_RETICLE_ROWS: list[tuple[str, str, str]] = [
    # (left-bracket, symbol, right-bracket) — styled separately
    ("┌─", "⊕", "─┐"),
    ("│ ", "╳", " │"),
    ("├─", "◎", "─┤"),
    ("│ ", "╳", " │"),
    ("└─", "⊕", "─┘"),
]

_TITLE = "Adversary Pursuit"
_TAGLINE = "Conversational CTI — Gamified Threat Intelligence"
_SUBTITLE = "Type 'help' for commands  |  'quit' to exit"

# ---------------------------------------------------------------------------
# Wordmark colour map — one colour per line of the ansi_shadow render
# ---------------------------------------------------------------------------

# ansi_shadow "ap" renders as 6 content lines (+ 1 trailing blank).
# Row-by-row gradient: green → bright_green → bold cyan → bright_green → green.
_WORDMARK_COLORS: list[str] = [
    "green",  # row 1: " █████╗ ██████╗ "
    "green",  # row 2: "██╔══██╗██╔══██╗"
    "bright_green",  # row 3: "███████║██████╔╝"
    "bold cyan",  # row 4: "██╔══██║██╔═══╝ "
    "bright_green",  # row 5: "██║  ██║██║     "
    "green",  # row 6: "╚═╝  ╚═╝╚═╝     "
]

# ---------------------------------------------------------------------------
# Mode → colour mapping
# ---------------------------------------------------------------------------

#: Maps character mode name → Rich colour string used for the prompt prefix.
#: Covers all 10 DEFAULT_MODES entries.  Falls back to "cyan" for unknown modes.
MODE_COLORS: dict[str, str] = {
    "default": "bold cyan",
    "ninja": "dim white",
    "full_troll": "bold magenta",
    "drunken_master": "bold yellow",
    "sun_tzu": "cyan",
    "chuck_norris": "bold red",
    "bureaucrat": "white",
    "bobby_hill": "bold green",
    "bruce_lee": "bold blue",
    "columbo": "bold yellow",
}

_FALLBACK_COLOR = "cyan"


def get_mode_color(mode_name: str) -> str:
    """Return the Rich colour string for *mode_name*.

    Parameters
    ----------
    mode_name:
        The ``CharacterMode.name`` value (e.g. ``"ninja"``, ``"full_troll"``).

    Returns
    -------
    str
        A Rich colour/style string (e.g. ``"bold magenta"``).  Falls back to
        ``"cyan"`` for unrecognised modes so new modes added to gamification
        degrade gracefully.
    """
    return MODE_COLORS.get(mode_name, _FALLBACK_COLOR)


# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------


def _get_version() -> str:
    """Return the installed package version string, e.g. ``'v0.1.0'``.

    Falls back to ``'v?.?.?'`` when the package is not installed (local dev
    without a ``pip install -e .`` / ``uv sync``).
    """
    try:
        return "v" + importlib.metadata.version("adversary-pursuit")
    except Exception:  # noqa: BLE001
        return "v?.?.?"


def _get_ioc_count() -> str:
    """Return a string IOC count from the active workspace, or ``'--'``.

    Calls ``WorkspaceManager().get_stix_objects()`` on a default-directory
    manager.  The banner renders at boot before the chat session creates its
    own workspace manager instance, so we construct a temporary read-only
    instance here.  If the workspace has never been initialised or errors for
    any reason, we return ``'--'`` so the banner never crashes boot.
    """
    try:
        from adversary_pursuit.core.workspace import WorkspaceManager

        wm = WorkspaceManager()
        # Try to switch to the default workspace.  If the file doesn't exist
        # yet (first boot), switch() raises ValueError — we catch and return --.
        wm.switch("default")
        objects = wm.get_stix_objects()
        return str(len(objects))
    except Exception:  # noqa: BLE001
        return "--"


# ---------------------------------------------------------------------------
# Layout builders
# ---------------------------------------------------------------------------


def _build_wordmark_text() -> Text:
    """Return a Rich Text object for the ansi_shadow 'ap' wordmark.

    Strips the trailing blank line pyfiglet appends and applies the
    per-row gradient colours from ``_WORDMARK_COLORS``.
    """
    text = Text()
    lines = _WORDMARK_DEFAULT.rstrip("\n").splitlines()
    for i, line in enumerate(lines):
        color = _WORDMARK_COLORS[i % len(_WORDMARK_COLORS)]
        text.append(line + "\n", style=Style.parse(color))
    return text


def _build_reticle_text() -> Text:
    """Return a Rich Text object for the 5-row crosshair reticle motif."""
    text = Text()
    for left, symbol, right in _RETICLE_ROWS:
        text.append(left, style="bright_black")
        text.append(symbol, style="bold yellow")
        text.append(right + "\n", style="bright_black")
    return text


def _build_metadata_strip(version: str, ioc_count: str, streak_line: str) -> Text:
    """Return a Rich Text with title, rule, tagline, and metadata rows.

    Parameters
    ----------
    version:
        Formatted version string, e.g. ``'v0.1.0'``.
    ioc_count:
        String IOC count or ``'--'`` placeholder.
    streak_line:
        One-line streak string from ``StreakManager.format_banner_line()``, or
        empty string if no active streak.
    """
    text = Text()
    text.append("ADVERSARY PURSUIT\n", style="bright_white")
    text.append("─" * 20 + "\n", style="bright_black")
    text.append("Conversational CTI\n", style="cyan")
    text.append(f"{version} · {ioc_count} IOCs\n", style="dim")
    if streak_line:
        text.append(streak_line + "\n", style="dim")
    return text


def _render_default_layout(
    console: Console, version: str, ioc_count: str, streak_line: str
) -> Text:
    """Build the full 3-column layout as a single Text for the Panel body.

    Three columns are assembled side-by-side using manual string alignment:
    - Column 1 (wordmark): ~16 chars wide, 6 rows
    - Column 2 (reticle): ~9 chars wide, 5 rows (padded to 6 via top blank)
    - Column 3 (metadata): variable width

    We compose them row-by-row into a single Text so Rich Panel can render
    without needing Columns (which can produce unexpected width behaviour
    inside panels).
    """
    # Collect each column's lines
    wordmark_lines = _WORDMARK_DEFAULT.rstrip("\n").splitlines()
    # Pad wordmark to consistent width
    wm_width = max(len(ln) for ln in wordmark_lines) if wordmark_lines else 16
    wordmark_padded = [ln.ljust(wm_width) for ln in wordmark_lines]

    # Reticle lines (5 rows — shift down by 1 blank row to center against 6-row wordmark)
    reticle_lines_raw = []
    for left, symbol, right in _RETICLE_ROWS:
        reticle_lines_raw.append((left, symbol, right))
    # Pad reticle to 6 rows by prepending a blank
    reticle_pad_top = ("   ", " ", "   ")  # blank spacer
    reticle_6 = [reticle_pad_top] + reticle_lines_raw  # type: ignore[list-item]

    # Metadata lines as plain strings for row-by-row composition
    metadata_plain = [
        "ADVERSARY PURSUIT",
        "─" * 20,
        "Conversational CTI",
        f"{version} · {ioc_count} IOCs",
    ]
    if streak_line:
        metadata_plain.append(streak_line)

    result = Text()
    for row_idx in range(len(wordmark_padded)):
        # Wordmark column
        color = _WORDMARK_COLORS[row_idx % len(_WORDMARK_COLORS)]
        result.append(wordmark_padded[row_idx], style=Style.parse(color))
        result.append("  ")  # inter-column gap

        # Reticle column
        if row_idx < len(reticle_6):
            left_str, sym_str, right_str = reticle_6[row_idx]
            result.append(left_str, style="bright_black")
            result.append(sym_str, style="bold yellow")
            result.append(right_str, style="bright_black")
        else:
            result.append("         ")  # empty placeholder

        result.append("  ")  # inter-column gap

        # Metadata column
        if row_idx < len(metadata_plain):
            meta = metadata_plain[row_idx]
            if row_idx == 0:
                result.append(meta, style="bright_white")
            elif row_idx == 1:
                result.append(meta, style="bright_black")
            elif row_idx == 2:
                result.append(meta, style="cyan")
            else:
                result.append(meta, style="dim")

        result.append("\n")

    return result


def _render_compact_layout(console: Console) -> Text:
    """Build the compact layout (narrow terminal, width < 60).

    Renders just the pyfiglet 'small' font wordmark for 'ap' with no
    reticle and no metadata strip — usable in 40-col tmux panes.
    """
    text = Text()
    lines = _WORDMARK_COMPACT.rstrip("\n").splitlines()
    for i, line in enumerate(lines):
        color = _WORDMARK_COLORS[i % len(_WORDMARK_COLORS)]
        text.append(line + "\n", style=Style.parse(color))
    return text


# ---------------------------------------------------------------------------
# Boot banner
# ---------------------------------------------------------------------------


def render_boot_banner(console: Console, streak_path=None) -> None:
    """Render the colourful figlet + reticle boot banner.

    Respects ``AP_NO_BANNER=1`` — returns immediately without any output when
    that variable is set (CI / scripted environments).

    The animation consists of:
    1. 3-column figlet wordmark + reticle + metadata strip (or compact
       variant when console width < 60).
    2. A staggered typewriter effect on the tagline (~300 ms total).
    3. A streak banner line if the analyst has an active streak
       (DEC-62-STREAK-006).

    Parameters
    ----------
    console:
        Rich Console to write to.  Pass ``Console(file=StringIO())`` in tests
        to capture output without touching stdout.
    streak_path:
        Override path for StreakManager. Pass tmp_path/streak.json in tests
        to avoid touching ~/.ap/streak.json (DEC-62-STREAK-001).
    """
    if os.environ.get("AP_NO_BANNER"):
        return

    # --- Collect metadata (must not crash) ---
    version = _get_version()
    ioc_count = _get_ioc_count()

    # --- Streak line (DEC-62-STREAK-006) ---
    # StreakManager is the single authority for streak display. Imported here
    # (inside the function body) to avoid a top-level circular import risk since
    # banner.py is imported at agent session startup before all core modules
    # are guaranteed to be initialised.
    streak_line = ""
    try:
        from adversary_pursuit.core.streak import StreakManager

        streak_mgr = StreakManager(path=streak_path)
        streak_line = streak_mgr.format_banner_line() or ""
    except Exception:  # noqa: BLE001
        pass  # streak display must never crash the boot banner

    # --- Width check: default vs compact layout ---
    try:
        width = console.size.width
    except Exception:  # noqa: BLE001
        width = 80  # safe fallback

    if width < 60:
        body = _render_compact_layout(console)
    else:
        body = _render_default_layout(console, version, ioc_count, streak_line)

    console.print(
        Panel(
            body,
            title=f"[bold green]{_TITLE}[/bold green]",
            subtitle=f"[dim]{_SUBTITLE}[/dim]",
            border_style="green",
            padding=(0, 2),
        )
    )

    # --- Typewriter animation on tagline ---
    _typewriter(console, _TAGLINE, style="bold cyan", delay=0.012)

    # --- Streak line (rendered separately below panel when present) ---
    if streak_line and width >= 60:
        # In default layout the streak appears inside the metadata strip.
        # Below-panel rendering is omitted to avoid duplication.
        pass
    elif streak_line and width < 60:
        # In compact layout the streak is not inside the panel body; render it here.
        console.print(f"[bold yellow]{streak_line}[/bold yellow]")

    console.print()  # trailing newline


def _typewriter(
    console: Console,
    text: str,
    style: str = "bold cyan",
    delay: float = 0.015,
) -> None:
    """Print *text* character-by-character with a short *delay* between chars.

    Uses ``console.print`` with ``end=""`` so the cursor advances inline.
    Total animation time = len(text) × delay ≈ 500 ms for a 40-char tagline
    at 12 ms/char.

    When ``AP_NO_BANNER`` is set this function is a no-op (guard already
    applied in ``render_boot_banner``, but callers may call directly).
    """
    if os.environ.get("AP_NO_BANNER"):
        return
    styled_chars: list[str] = []
    for char in text:
        styled_chars.append(char)
        console.print(f"[{style}]{char}[/{style}]", end="", highlight=False)
        console.file.flush() if hasattr(console, "file") else None
        time.sleep(delay)
    console.print()  # newline after last char


# ---------------------------------------------------------------------------
# Thinking spinner
# ---------------------------------------------------------------------------


@contextmanager
def thinking_status(console: Console, message: str = "Thinking...") -> Generator[None, None, None]:
    """Context manager that shows a Rich Status spinner while the LLM is busy.

    Usage::

        with thinking_status(console):
            response = runner.chat(user_input)

    Parameters
    ----------
    console:
        Rich Console for rendering the spinner.
    message:
        Status label shown next to the spinner.

    Yields
    ------
    None
    """
    with console.status(f"[bold cyan]{message}[/bold cyan]"):
        yield
