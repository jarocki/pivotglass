"""Top-anchored TUI header renderer for Adversary Pursuit.

Renders a fixed 3-row header at the top of the TUI layout showing the
application version, current target, workspace name, and a PRIOR breadcrumb
(the previous target before the last ``use`` command pivot).

Layout (80-column example):

    ╭─ ADVERSARY PURSUIT v0.4 ─── CURRENT: evil.com ─── WORKSPACE: default ─╮
    │ PRIOR: prev.example.com                                                  │
    ╰──────────────────────────────────────────────────────────────────────────╯

The PRIOR row is always present (renders "—" when no prior target exists) so
the scrollback window height never jumps between 2-row and 3-row layouts.

@decision DEC-TUI-HEADER-001
@title Fixed 3-row header with PRIOR breadcrumb tracked locally in HeaderPane
@status accepted
@rationale The storyboard mockups establish a top information bar showing
           ADVERSARY PURSUIT v0.4 | CURRENT: <target> | WORKSPACE: <name>
           plus a PRIOR: <prev> breadcrumb (visible in all three mockups).
           Fixed 3 rows (always) is non-negotiable: a variable-height header
           causes the scrollback window to shift height mid-session, which
           confuses layout tests and produces visual jitter. "—" placeholder
           for missing PRIOR keeps the row present without meaningful content.
           PRIOR is tracked in HeaderPane by listening to TargetChanged events
           and remembering the previous value — no events.py schema change
           required (dispatch directive in Slice 7A scope notes). This keeps
           events.py unchanged (it is in the forbidden list for this slice).
           Border color is pulled from the active CharacterTheme via
           resolved_border_color() so the header participates in the
           per-character visual identity system (DEC-TUI-THEME-001).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from adversary_pursuit.agent.tui.themes import CharacterTheme, resolved_border_color

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class HeaderState:
    """Immutable snapshot of header display data.

    Parameters
    ----------
    version:
        Application version string shown in the title bar (e.g. ``"v0.4"``).
    current_target:
        Current investigation target, or ``"—"`` when unset.
    workspace_name:
        Active workspace name (e.g. ``"default"``).
    prior_target:
        Previous investigation target before the last pivot, or ``"—"``.
    """

    version: str = "v0.4"
    current_target: str = "—"
    workspace_name: str = "default"
    prior_target: str = "—"


# ---------------------------------------------------------------------------
# Pure renderer — no state, no side effects
# ---------------------------------------------------------------------------


def render_header(state: HeaderState, theme: CharacterTheme, width: int = 80) -> list[str]:
    """Render the 3-row header as plain-text strings.

    Always returns exactly 3 elements regardless of content length. Content
    is truncated (not wrapped) when it exceeds ``width``.

    Parameters
    ----------
    state:
        Current HeaderState snapshot.
    theme:
        Active CharacterTheme (from ``theme_for(character_name)``).
    width:
        Terminal width in columns. Defaults to 80. Used to pad/truncate
        border lines so they reach the right edge.

    Returns
    -------
    list[str]
        Exactly 3 plain-text strings: top border, prior row, bottom border.
        Rich markup is NOT included — callers may wrap these in styled
        FormattedText segments using theme colors.

    Notes
    -----
    The border color is available via ``resolved_border_color(theme)`` for
    callers that want to style the output. The raw strings are markup-free
    so they can be measured for width without stripping escape codes.
    """
    _ = resolved_border_color(theme)  # available for styled callers; not applied here

    # Build the title bar content: "ADVERSARY PURSUIT v0.4 ─── CURRENT: X ─── WORKSPACE: Y"
    title_parts = [
        f"ADVERSARY PURSUIT {state.version}",
        f"CURRENT: {state.current_target}",
        f"WORKSPACE: {state.workspace_name}",
    ]
    title_content = " ─── ".join(title_parts)

    # Inner width (between the ╭ and ╮ corners)
    inner = width - 2

    # Row 1: top border with embedded title
    title_padded = f" {title_content} "
    pad_total = max(0, inner - len(title_padded))
    pad_left = pad_total // 2
    pad_right = pad_total - pad_left
    row1_inner = "─" * pad_left + title_padded + "─" * pad_right
    # Truncate if title is too wide for the terminal
    row1_inner = row1_inner[:inner]
    row1 = "╭" + row1_inner + "╮"

    # Row 2: PRIOR breadcrumb
    prior_content = f" PRIOR: {state.prior_target}"
    # Pad to fill the inner width (border characters are │ on both sides)
    row2_body = prior_content.ljust(inner)[:inner]
    row2 = "│" + row2_body + "│"

    # Row 3: bottom border
    row3 = "╰" + "─" * inner + "╯"

    return [row1, row2, row3]


# ---------------------------------------------------------------------------
# HeaderPane — stateful subscriber for TuiApplication
# ---------------------------------------------------------------------------


class HeaderPane:
    """Stateful TUI header that tracks target changes and renders on demand.

    Subscribes to TargetChanged events on the EventBus and maintains its own
    PRIOR breadcrumb by remembering the previous target value when a new one
    arrives. This approach requires no changes to events.py (forbidden in this
    slice) and keeps the breadcrumb logic entirely within the header layer.

    Parameters
    ----------
    bus:
        Session EventBus. HeaderPane subscribes to TargetChanged events.
    workspace_name:
        Initial workspace name (e.g. ``"default"``). May be updated via
        ``set_workspace_name()``.
    version:
        Application version string (e.g. ``"v0.4"``).
    """

    def __init__(
        self,
        bus,
        workspace_name: str = "default",
        version: str = "v0.4",
    ) -> None:
        self._lock = threading.Lock()
        self._version = version
        self._workspace_name = workspace_name
        self._current_target: str = "—"
        self._prior_target: str = "—"

        # Subscribe to target changes; bus may be None in unit tests
        if bus is not None:
            from adversary_pursuit.agent.tui.events import TargetChanged

            bus.subscribe(TargetChanged, self._on_target_changed)

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    def _on_target_changed(self, event) -> None:
        """Handle TargetChanged — update PRIOR then CURRENT atomically."""
        with self._lock:
            # The current target becomes PRIOR before we overwrite it
            if self._current_target != "—":
                self._prior_target = self._current_target
            self._current_target = event.target or "—"

    # ------------------------------------------------------------------
    # Public state mutators
    # ------------------------------------------------------------------

    def set_workspace_name(self, name: str) -> None:
        """Update the workspace name shown in the header title bar.

        Parameters
        ----------
        name:
            New workspace name string.
        """
        with self._lock:
            self._workspace_name = name

    def set_version(self, version: str) -> None:
        """Update the version string shown in the header title bar.

        Parameters
        ----------
        version:
            Version string (e.g. ``"v0.4"``).
        """
        with self._lock:
            self._version = version

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(self, theme: CharacterTheme, width: int = 80) -> list[str]:
        """Render the header as exactly 3 plain-text lines.

        Parameters
        ----------
        theme:
            Active character theme from ``theme_for(character_name)``.
        width:
            Terminal width in columns.

        Returns
        -------
        list[str]
            Always exactly 3 elements.
        """
        with self._lock:
            state = HeaderState(
                version=self._version,
                current_target=self._current_target,
                workspace_name=self._workspace_name,
                prior_target=self._prior_target,
            )
        return render_header(state, theme, width=width)

    # ------------------------------------------------------------------
    # Read-only accessors (for tests)
    # ------------------------------------------------------------------

    @property
    def current_target(self) -> str:
        """Current investigation target string."""
        with self._lock:
            return self._current_target

    @property
    def prior_target(self) -> str:
        """Previous investigation target string (PRIOR breadcrumb)."""
        with self._lock:
            return self._prior_target
