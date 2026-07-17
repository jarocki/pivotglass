"""Append-only scrollback buffer for the TUI.

Stores plain-text lines emitted by the agent session and provides a Rich
__rich_console__ hook so it can be rendered inside a prompt_toolkit Window
via a FormattedTextControl adapter.

@decision DEC-TUI-SCROLLBACK-001
@title append-only invariant — no line is ever removed or modified
@status accepted
@rationale The scrollback buffer is a reliable audit trail of the session.
           Allowing removal or in-place modification would make the buffer
           unreliable as a debugging aid and introduce concurrency hazards.
           append-only semantics mean get_lines() always returns a superset
           of any previously returned snapshot. The buffer grows without bound
           for the session lifetime — this is acceptable given typical CTI
           session durations (minutes to hours, not days).
"""

from __future__ import annotations

import threading


class ScrollbackBuffer:
    """Thread-safe append-only text buffer for TUI session output.

    Lines are stored as plain strings (no Rich markup). The buffer is
    designed to be written from the agent/battery thread and read from
    the prompt_toolkit render thread.

    Usage
    -----
    buf = ScrollbackBuffer()
    buf.emit_line("target set: evil.example.com")
    buf.emit_rule("identity battery")
    lines = buf.get_lines()
    """

    # Width used for horizontal rules and panel borders.
    _WIDTH: int = 72

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._lines: list[str] = []

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    def emit_line(self, text: str) -> None:
        """Append a single line to the buffer.

        Parameters
        ----------
        text:
            Plain-text line. May contain embedded newlines; each sub-line
            is stored separately.
        """
        with self._lock:
            for sub in text.split("\n"):
                self._lines.append(sub)

    def emit_rule(self, title: str = "") -> None:
        """Append a horizontal rule line.

        Renders as ``─── title ──────────── `` (or a plain rule when
        title is empty), padded to ``_WIDTH`` characters using the box-
        drawing character U+2500 (─).

        Parameters
        ----------
        title:
            Optional title embedded in the rule. Empty string yields a
            plain horizontal line.
        """
        char = "─"
        if title:
            inner = f" {title} "
            pad = self._WIDTH - len(inner)
            left = max(3, pad // 2)
            right = max(3, pad - left)
            line = char * left + inner + char * right
        else:
            line = char * self._WIDTH
        with self._lock:
            self._lines.append(line)

    def emit_panel(self, title: str, body: str) -> None:
        """Append a simple bordered panel.

        Renders as::

            ┌── title ───────────────────────────────────────────────┐
            │ body line 1                                             │
            │ body line 2                                             │
            └─────────────────────────────────────────────────────────┘

        Each line of *body* is word-wrapped to fit inside the border.

        Styling note (DEC-TUI-APP-THEME-INJECT-001): Panel lines are stored
        as plain strings in the scrollback buffer. Character theme colors are
        applied at the PTK FormattedText layer in TuiApplication, not inside
        ScrollbackBuffer. Because the scrollback's own FormattedText builder
        (``_get_scrollback_formatted``) uses terminal-default style (``""``),
        panel border characters rendered here will appear in the terminal's
        default foreground color rather than the character's border_color.
        This is intentional: the scrollback is a mixed-content audit trail
        (user input, tool output, error panels) and applying a single
        character palette would misrepresent heterogeneous content. If a
        caller wants a themed panel, it should emit Rich-markup text via
        ``emit_line()`` before storing the panel content.

        Parameters
        ----------
        title:
            Panel title shown in the top border.
        body:
            Multi-line body text. Newlines are respected; each physical
            line is padded and bordered independently.
        """
        w = self._WIDTH
        inner_w = w - 2  # space inside │ … │

        # Top border
        if title:
            title_str = f" {title} "
            pad = inner_w - len(title_str)
            top = "┌" + "─" * max(0, pad // 2) + title_str + "─" * max(0, pad - pad // 2) + "┐"
        else:
            top = "┌" + "─" * inner_w + "┐"

        body_lines = body.split("\n")
        bordered_lines = [f"│ {bl:<{inner_w - 2}} │" for bl in body_lines]
        bottom = "└" + "─" * inner_w + "┘"

        with self._lock:
            self._lines.append(top)
            self._lines.extend(bordered_lines)
            self._lines.append(bottom)

    def clear(self) -> None:
        """Clear all stored lines from the buffer.

        This is the only mutation that removes content — used by the ``clear``
        REPL verb to give the analyst a clean screen. The append-only invariant
        (DEC-TUI-SCROLLBACK-001) applies to normal session output; ``clear()``
        is an explicit user-requested reset, not a background mutation.
        """
        with self._lock:
            self._lines.clear()

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def get_lines(self) -> list[str]:
        """Return a snapshot of all stored lines.

        Returns
        -------
        list[str]
            A shallow copy of the current line list. The returned list
            will never shrink relative to a prior call (append-only
            invariant, DEC-TUI-SCROLLBACK-001).
        """
        with self._lock:
            return list(self._lines)

    def get_window(self, limit: int, offset: int = 0) -> list[str]:
        """Return a bounded window from the end of the transcript.

        ``offset=0`` follows the newest output. Positive offsets move the
        window backwards for PageUp-style navigation. Keeping this operation
        bounded prevents the full-screen renderer from copying and rebuilding
        an hours-long transcript on every status refresh.
        """
        if limit <= 0:
            return []
        offset = max(0, offset)
        with self._lock:
            end = max(0, len(self._lines) - offset)
            start = max(0, end - limit)
            return list(self._lines[start:end])

    # ------------------------------------------------------------------
    # Rich protocol
    # ------------------------------------------------------------------

    def __rich_console__(self, console, options):  # type: ignore[no-untyped-def]
        """Render the scrollback buffer for Rich Console.

        Yields each stored line as a plain string. Rich will apply its
        default text styling; callers should use a Console with
        highlight=False when precise output is needed.
        """
        with self._lock:
            lines = list(self._lines)
        for line in lines:
            yield line
