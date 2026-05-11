"""ASCII art boot banner and ANSI animation helpers for AP chat.

Provides:
  - ``render_boot_banner(console)`` — colourful ASCII art + brief typewriter
    animation on the tagline.  Skipped entirely when ``AP_NO_BANNER=1`` (CI).
  - ``get_mode_color(mode_name)`` — mode-specific colour string for the prompt
    prefix so every character mode has its own visual identity.
  - ``thinking_status(console)`` — context-manager wrapping Rich Status spinner
    shown while the LLM is thinking.

Design constraints
------------------
* Total boot animation ≤ 500 ms (sub-second is non-negotiable for UX).
* ``AP_NO_BANNER=1`` disables all output including the animation so CI tests
  produce clean stdout.
* No external dependencies beyond Rich (already a core dep).

@decision DEC-AGENT-BANNER-001
@title Rich-based boot banner with typewriter animation and mode colour map
@status accepted
@rationale The previous banner was a single Plain Panel line — functional but
           not engaging.  This module replaces it with a radar-dish ASCII art
           block (tasteful, CTI-themed), a gradient title, and a 500 ms
           staggered typewriter animation on the tagline.  All output goes
           through the caller-supplied Rich Console so tests can capture it
           via Console(file=StringIO).  The AP_NO_BANNER env guard means CI
           is never impacted.  Mode colours use Rich's built-in named colour
           strings — no ANSI escape codes written directly.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Generator

from rich.console import Console
from rich.panel import Panel
from rich.style import Style
from rich.text import Text

# ---------------------------------------------------------------------------
# ASCII art
# ---------------------------------------------------------------------------

# Radar-dish / signal tower art — CTI-themed, 7 lines wide enough for a standard
# terminal (80 cols).  Kept at ~60 chars wide so it fits inside a Rich Panel.
_ART = r"""
   .  *   .  *   .  *   .
    \  |  /   \  |  /
     \ | /     \ | /
  ----[AP]-------[*]----
     / | \     / | \
    /  |  \   /  |  \
  ~~ ADVERSARY PURSUIT ~~
"""

_TITLE = "Adversary Pursuit"
_TAGLINE = "Conversational CTI — Gamified Threat Intelligence"
_SUBTITLE = "Type 'help' for commands  |  'quit' to exit"

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
# Boot banner
# ---------------------------------------------------------------------------


def render_boot_banner(console: Console) -> None:
    """Render the colourful ASCII art boot banner.

    Respects ``AP_NO_BANNER=1`` — returns immediately without any output when
    that variable is set (CI / scripted environments).

    The animation consists of:
    1. Printing the ASCII art art block with gradient colours.
    2. A staggered typewriter effect on the tagline (~300 ms total).

    Parameters
    ----------
    console:
        Rich Console to write to.  Pass ``Console(file=StringIO())`` in tests
        to capture output without touching stdout.
    """
    if os.environ.get("AP_NO_BANNER"):
        return

    # --- ASCII art block ---
    art_text = Text()
    # Colour the art lines with a gradient from green → cyan → blue
    _ART_COLORS = [
        "bright_black",  # spacer line
        "green",
        "bright_green",
        "bold cyan",
        "bright_green",
        "green",
        "bold yellow",
    ]
    art_lines = [ln for ln in _ART.splitlines() if ln.strip() or ln == ""]
    for i, line in enumerate(art_lines):
        if not line.strip():
            art_text.append("\n")
            continue
        color = _ART_COLORS[i % len(_ART_COLORS)]
        art_text.append(line + "\n", style=Style.parse(color))

    # Bold title text
    title_text = Text()
    title_text.append(f"  {_TITLE}\n", style="bold green")

    console.print(
        Panel(
            art_text,
            title=f"[bold green]{_TITLE}[/bold green]",
            subtitle=f"[dim]{_SUBTITLE}[/dim]",
            border_style="green",
            padding=(0, 2),
        )
    )

    # --- Typewriter animation on tagline ---
    _typewriter(console, _TAGLINE, style="bold cyan", delay=0.012)
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
def thinking_status(
    console: Console, message: str = "Thinking..."
) -> Generator[None, None, None]:
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
