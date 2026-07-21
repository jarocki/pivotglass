"""TuiApplication — prompt_toolkit Application wrapper for the AP TUI.

Provides a split-pane terminal UI: scrollable history above, single-line
input in the middle, and a fixed 6-row live status pane at the bottom.
A background thread refreshes the live pane at the character-specific Hz
cadence.

@decision DEC-TUI-APPLICATION-001
@title HSplit layout; live_pane always exactly 6 rows; input at row H-7
@status accepted
@rationale prompt_toolkit HSplit stacks windows vertically. Placing the
           live pane last with height=6 (fixed) and the input above it
           with height=1 (fixed) leaves the remainder for the scrollback
           window. This gives the analyst maximum history context while
           keeping the status pane and input always on screen. The live
           pane height never changes — content that doesn't fit is clipped
           rather than reflowing, which keeps the 6-row contract stable for
           snapshot tests.
"""

from __future__ import annotations

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from pathlib import Path

from prompt_toolkit import Application
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.data_structures import Point
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import (
    ConditionalContainer,
    Float,
    FloatContainer,
    HSplit,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.margins import ScrollbarMargin
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from prompt_toolkit.widgets import Box, Frame
from rich.console import Console

from adversary_pursuit.agent.enrichment_briefings import render_briefing
from adversary_pursuit.agent.repl_input import APCompleter
from adversary_pursuit.agent.tui.events import EventBus
from adversary_pursuit.agent.tui.header import HeaderPane
from adversary_pursuit.agent.tui.live_pane import LivePane
from adversary_pursuit.agent.tui.scrollback import ScrollbackBuffer
from adversary_pursuit.agent.tui.themes import (  # character theme dispatch
    cockpit_for,
    is_high_contrast_mode,
    pursuit_title_for,
    resolved_border_color,
    theme_for,
)


class NotATTYError(RuntimeError):
    """Raised when TuiApplication is constructed outside a real TTY.

    Callers should catch this and fall back to the legacy Rich REPL.
    """


class _DraggableScrollbarMargin(ScrollbarMargin):
    """Visible PTK scrollbar whose track supports click-and-drag navigation."""

    def __init__(self, on_fraction) -> None:  # type: ignore[no-untyped-def]
        super().__init__(display_arrows=True, up_arrow_symbol="▲", down_arrow_symbol="▼")
        self._on_fraction = on_fraction
        self._dragging = False

    def create_margin(self, window_render_info, width: int, height: int):  # type: ignore[no-untyped-def]
        rendered = super().create_margin(window_render_info, width, height)
        row = 0
        result = []

        def handler_for(bound_row: int):  # type: ignore[no-untyped-def]
            def handle(mouse_event: MouseEvent):
                if mouse_event.event_type == MouseEventType.MOUSE_DOWN:
                    self._dragging = True
                elif mouse_event.event_type == MouseEventType.MOUSE_UP:
                    self._dragging = False
                elif mouse_event.event_type != MouseEventType.MOUSE_MOVE or not self._dragging:
                    return NotImplemented
                usable = max(1, height - 1)
                self._on_fraction(min(1.0, max(0.0, bound_row / usable)), window_render_info)
                return None

            return handle

        for style, text, *rest in rendered:
            result.append((style, text, handler_for(row)))
            row += text.count("\n")
        return result


_HELP_TEXT = """QUICK CONTROL

  use <ioc>        Set or pivot the active target
  investigate ... Ask AP to hunt or explain
  stop             Halt the active battery
  focus <tool>     Prioritize one source
  add <tool>       Add a source to the hunt
  skip <tool>      Skip a queued source

DECK

  status           Investigation snapshot
  mode / mode list List character modes
  mode <name>      Change character and cockpit
  workspace ...    Manage investigation spaces
  clear            Clear the intelligence feed

KEYS

  Tab              Complete commands and arguments
  [ / ]            Older / newer intelligence (works on every keyboard)
  Drag scrollbar   Jump through the intelligence feed
  Trackpad/wheel   Scroll the intelligence feed under the pointer
  PageUp/PageDown  Terminal paging alternative
  Esc >            Jump to newest activity
  ?                Open or close this help deck

Press Esc, ?, q, or Enter to return to the hunt."""


class _TuiConsole:
    """Small Rich-console adapter that routes panels into TUI scrollback."""

    def __init__(self, emit) -> None:  # type: ignore[no-untyped-def]
        self._emit = emit

    def print(self, *objects, **kwargs) -> None:  # type: ignore[no-untyped-def]
        stream = StringIO()
        console = Console(file=stream, color_system=None, width=96, highlight=False)
        console.print(*objects, **kwargs)
        rendered = stream.getvalue().rstrip()
        # The diagnostic remains recorded, but normal flow should present the
        # recovery action rather than assign log-reading homework to the user.
        lines = []
        for line in rendered.splitlines():
            if "Debug log:" in line:
                line = line.split("Debug log:", 1)[0].rstrip() + "  Details retained automatically"
            lines.append(line)
        if lines:
            self._emit("\n".join(lines))


class TuiApplication:
    """prompt_toolkit Application wrapper for the AP TUI.

    Parameters
    ----------
    runner:
        The AgentRunner (or compatible duck-type). Called when the analyst
        submits input that is not a yield command.
    workspace_mgr:
        WorkspaceManager instance for elapsed-time display in the live pane.
    mode_mgr:
        ModeManager instance. Used to read the active character name for
        the live pane and refresh-cadence selection.
    event_bus:
        The session EventBus shared with battery runs and the live pane.

    Raises
    ------
    NotATTYError
        When sys.stdin is not a TTY (e.g. in a pipe, test harness, or
        non-interactive shell). Callers must catch this and degrade to the
        legacy REPL.
    """

    def __init__(
        self,
        runner,
        workspace_mgr,
        mode_mgr,
        event_bus: EventBus,
    ) -> None:
        if not sys.stdin.isatty():
            raise NotATTYError(
                "TuiApplication requires an interactive TTY. "
                "Use the legacy REPL when stdin is not a TTY."
            )

        self._runner = runner
        self._workspace_mgr = workspace_mgr
        self._mode_mgr = mode_mgr
        self._event_bus = event_bus
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ap-command")
        self._chat_lock = threading.Lock()
        self._scroll_offset = 0
        self._scrollback_window: Window | None = None
        self._help_visible = False
        self._prompt_phase = False

        # Shared scrollback buffer written by all session output paths
        self._scrollback = ScrollbackBuffer()

        # Live pane — subscribes to all event types on construction
        mode_name = mode_mgr.active.name if mode_mgr is not None else "default"
        model_display = self._resolve_model_display()
        self._live_pane = LivePane(
            bus=event_bus,
            mode_name=mode_name,
            model_display=model_display,
            workspace_mgr=workspace_mgr,
            feed_emit=self._emit_agent_trace,
        )

        # Header pane — top-anchored 3-row strip (DEC-TUI-HEADER-001).
        # Subscribes to TargetChanged events to maintain CURRENT / PRIOR breadcrumb.
        #
        # @decision DEC-TUI-COLD-START-HARDENING-001
        # @title TuiApplication.__init__ tolerates workspace_mgr.active raising on cold start
        # @status accepted
        # @rationale WorkspaceManager.active is a property that raises RuntimeError when
        #            _active is None (intentional fail-loud design — callers that assume an
        #            active workspace should fail immediately). However, TuiApplication.__init__
        #            is a "may not be active yet" caller: on cold start / first launch, no
        #            workspace has been switched to, so the property raises before the header
        #            pane is constructed. The fix wraps the .active call in try/except
        #            RuntimeError and falls back to "default". WorkspaceManager.get_session()
        #            auto-switches to "default" on first DB access, so the header will display
        #            the correct name once any DB interaction occurs. Catching only RuntimeError
        #            (the specific type workspace.py raises) preserves fail-loud behavior for
        #            all other exception types (Sacred Practice 5).
        if workspace_mgr is None:
            workspace_name = "default"
        else:
            try:
                workspace_name = workspace_mgr.active
            except RuntimeError:
                # Cold start: no workspace switched to yet. WorkspaceManager.get_session()
                # will auto-switch to "default" on first DB access, so "default" is the
                # accurate name to render in the header until that happens.
                workspace_name = "default"
        self._header_pane = HeaderPane(
            bus=event_bus,
            workspace_name=workspace_name,
        )

        # Build prompt_toolkit layout
        self._input_buffer = Buffer(
            name="input",
            multiline=False,
            accept_handler=self._on_input_accepted,
            completer=APCompleter(),
            history=self._build_history(),
            auto_suggest=AutoSuggestFromHistory(),
            complete_while_typing=False,
        )
        self._app = self._build_app()

        # Tool failures previously rendered to the underlying Rich console,
        # outside the full-screen deck. Route them into the investigation feed.
        ctx = getattr(self._runner, "ctx", None)
        if ctx is not None:
            ctx.console = _TuiConsole(self.emit_scrollback)

        # Background refresh thread state
        self._refresh_thread: threading.Thread | None = None
        self._stop_refresh = threading.Event()

    # ------------------------------------------------------------------
    # Layout construction
    # ------------------------------------------------------------------

    def _build_app(self) -> Application:
        """Construct the prompt_toolkit Application."""
        kb = KeyBindings()

        @kb.add("c-c")
        @kb.add("c-d")
        def _exit(event) -> None:  # type: ignore[no-untyped-def]
            event.app.exit()

        @kb.add("pageup")
        def _page_up(event) -> None:  # type: ignore[no-untyped-def]
            self._scroll_older()
            event.app.invalidate()

        @kb.add("pagedown")
        def _page_down(event) -> None:  # type: ignore[no-untyped-def]
            self._scroll_newer()
            event.app.invalidate()

        # Laptop-friendly aliases. Alt+Arrow arrives as Escape followed by
        # Arrow in ordinary terminal emulators and does not steal editing keys.
        @kb.add("escape", "up")
        def _laptop_page_up(event) -> None:  # type: ignore[no-untyped-def]
            self._scroll_older()
            event.app.invalidate()

        @kb.add("escape", "down")
        def _laptop_page_down(event) -> None:  # type: ignore[no-untyped-def]
            self._scroll_newer()
            event.app.invalidate()

        @kb.add("c-up")
        def _control_page_up(event) -> None:  # type: ignore[no-untyped-def]
            self._scroll_older()
            event.app.invalidate()

        @kb.add("c-down")
        def _control_page_down(event) -> None:  # type: ignore[no-untyped-def]
            self._scroll_newer()
            event.app.invalidate()

        @kb.add("[")
        def _universal_page_up(event) -> None:  # type: ignore[no-untyped-def]
            if self._input_buffer.text:
                self._input_buffer.insert_text("[")
            else:
                self._scroll_older()
            event.app.invalidate()

        @kb.add("]")
        def _universal_page_down(event) -> None:  # type: ignore[no-untyped-def]
            if self._input_buffer.text:
                self._input_buffer.insert_text("]")
            else:
                self._scroll_newer()
            event.app.invalidate()

        @kb.add("<scroll-up>")
        def _wheel_up(event) -> None:  # type: ignore[no-untyped-def]
            self._scroll_older(lines=4)
            event.app.invalidate()

        @kb.add("<scroll-down>")
        def _wheel_down(event) -> None:  # type: ignore[no-untyped-def]
            self._scroll_newer(lines=4)
            event.app.invalidate()

        @kb.add("escape", "<")
        def _oldest(event) -> None:  # type: ignore[no-untyped-def]
            self._scroll_offset = 10**9
            event.app.invalidate()

        @kb.add("escape", ">")
        def _newest(event) -> None:  # type: ignore[no-untyped-def]
            self._scroll_offset = 0
            event.app.invalidate()

        help_closed = Condition(lambda: not self._help_visible)
        help_open = Condition(lambda: self._help_visible)

        @kb.add("?", filter=help_closed)
        def _show_help(event) -> None:  # type: ignore[no-untyped-def]
            # A question mark inside a sentence remains ordinary input. An
            # empty command line makes '?' the instant help instrument.
            if self._input_buffer.text:
                self._input_buffer.insert_text("?")
                return
            self._help_visible = True
            event.app.invalidate()

        @kb.add("escape", filter=help_open)
        @kb.add("?", filter=help_open)
        @kb.add("q", filter=help_open)
        @kb.add("enter", filter=help_open)
        def _hide_help(event) -> None:  # type: ignore[no-untyped-def]
            self._help_visible = False
            event.app.invalidate()

        # Header pane — fixed 3 rows at the top (DEC-TUI-HEADER-001)
        header_control = FormattedTextControl(
            text=self._get_header_formatted,
            focusable=False,
        )
        header_window = Window(
            content=header_control,
            height=3,
            dont_extend_height=True,
        )

        scrollback_control = FormattedTextControl(
            text=self._get_scrollback_formatted,
            focusable=False,
            get_cursor_position=self._get_scrollback_cursor_position,
        )
        scrollback_window = Window(
            content=scrollback_control,
            dont_extend_height=False,
            wrap_lines=False,
            always_hide_cursor=True,
            get_vertical_scroll=self._get_scrollback_vertical_scroll,
            right_margins=[_DraggableScrollbarMargin(self._drag_scrollback)],
        )
        self._scrollback_window = scrollback_window

        prompt_window = Window(
            content=FormattedTextControl(self._get_prompt_formatted),
            width=2,
            dont_extend_width=True,
        )
        input_window = Window(
            content=BufferControl(buffer=self._input_buffer, focusable=True),
            height=1,
            dont_extend_height=True,
        )
        input_row = VSplit([prompt_window, input_window], height=1)
        command_deck = Frame(
            body=input_row,
            title=self._get_command_title_formatted,
        )

        live_pane_control = FormattedTextControl(
            text=self._get_live_pane_formatted,
            focusable=False,
        )
        live_pane_window = Window(
            content=live_pane_control,
            height=6,
            dont_extend_height=True,
        )
        hud_window = Window(
            content=FormattedTextControl(self._get_hud_formatted),
            width=34,
            height=6,
            dont_extend_height=True,
        )
        instruments = Frame(
            body=VSplit([live_pane_window, Window(width=1, char="│"), hud_window]),
            title=self._get_instruments_title_formatted,
        )

        feed = Frame(
            body=scrollback_window,
            title=self._get_pursuit_title_formatted,
        )
        # Storyboard hierarchy: identity band, dominant intelligence field,
        # explicit command deck, then a dense analyst instrument cluster.
        base = HSplit([header_window, feed, command_deck, instruments])
        help_window = ConditionalContainer(
            content=Box(
                body=Frame(
                    body=Window(
                        content=FormattedTextControl(self._get_help_formatted),
                        wrap_lines=False,
                    ),
                    title=" ?  OPERATOR HELP ",
                ),
                padding=1,
            ),
            filter=Condition(lambda: self._help_visible),
        )
        root = FloatContainer(
            content=base,
            floats=[Float(content=help_window, width=70, height=27)],
        )

        layout = Layout(
            root,
            focused_element=input_window,
        )

        return Application(
            layout=layout,
            key_bindings=kb,
            full_screen=True,
            mouse_support=True,
            editing_mode=self._editing_mode(),
        )

    def _get_prompt_formatted(self) -> FormattedText:
        mode_name = self._mode_mgr.active.name if self._mode_mgr is not None else "default"
        theme = theme_for(mode_name)
        glyph = "▶" if self._prompt_phase else ">"
        return FormattedText(
            [
                (f"blink bold reverse fg:{theme.accent_color}", glyph),
                ("", " "),
            ]
        )

    def _get_help_formatted(self) -> FormattedText:
        mode_name = self._mode_mgr.active.name if self._mode_mgr is not None else "default"
        theme = theme_for(mode_name)
        parts: list[tuple[str, str]] = []
        for line in _HELP_TEXT.splitlines():
            if line in {"QUICK CONTROL", "DECK", "KEYS"}:
                parts.append((f"bold fg:{theme.accent_color}", line + "\n"))
            elif line.startswith("Press "):
                parts.append((f"bold reverse fg:{theme.accent_color}", line))
            else:
                parts.append((f"fg:{theme.text_color}", line + "\n"))
        return FormattedText(parts)

    def _get_pursuit_title_formatted(self) -> FormattedText:
        mode_name = self._mode_mgr.active.name if self._mode_mgr is not None else "default"
        theme = theme_for(mode_name)
        profile = cockpit_for(mode_name)
        title = pursuit_title_for(mode_name)
        return FormattedText(
            [
                (f"fg:{theme.dim_color}", f" {profile.left_rail}━━ "),
                (f"bold fg:{theme.heading_color}", f"{title} // {profile.vehicle}"),
                (f"fg:{theme.dim_color}", f" ━━{profile.right_rail} "),
            ]
        )

    def _get_command_title_formatted(self) -> FormattedText:
        """Return the storyboard-inspired command-deck label."""
        mode_name = self._mode_mgr.active.name if self._mode_mgr is not None else "default"
        theme = theme_for(mode_name)
        return FormattedText(
            [
                (f"bold fg:{theme.accent_color}", " COMMAND DECK "),
                (f"fg:{theme.dim_color}", "  natural language + local controls "),
            ]
        )

    def _get_instruments_title_formatted(self) -> FormattedText:
        """Return the label for activity, dossier, model, and mode telemetry."""
        mode_name = self._mode_mgr.active.name if self._mode_mgr is not None else "default"
        theme = theme_for(mode_name)
        profile = cockpit_for(mode_name)
        return FormattedText(
            [
                (f"bold fg:{theme.heading_color}", f" {profile.deck_name} "),
                (f"fg:{theme.dim_color}", f"  {profile.hud_title} · live instruments "),
            ]
        )

    def _get_hud_formatted(self) -> FormattedText:
        """Render six active, functional cockpit instruments."""
        mode_name = self._mode_mgr.active.name if self._mode_mgr is not None else "default"
        theme = theme_for(mode_name)
        profile = cockpit_for(mode_name)
        state = self._live_pane.hud_state()
        feed_state = "LIVE" if self._scroll_offset == 0 else f"-{self._scroll_offset} lines"
        active = "ACTIVE" if state["active"] else "STANDBY"
        rows = [
            f"{profile.left_rail} {profile.hud_title} {profile.right_rail}",
            f"LOCK   {str(state['target'])[:23]}",
            f"CLASS  {str(state['target_type'])[:23]}",
            f"PROBE  {str(state['activity'])[:17]}  q:{state['queued']}",
            f"DOSSIER {state['slots']}/9   FEED {feed_state}",
            f"{active}   [ older · ] newer",
        ]
        parts: list[tuple[str, str]] = []
        for index, row in enumerate(rows):
            color = theme.heading_color if index in {0, 5} else theme.text_color
            weight = "bold " if index in {0, 5} else ""
            parts.append((f"{weight}fg:{color}", row))
            if index < len(rows) - 1:
                parts.append(("", "\n"))
        return FormattedText(parts)

    def _get_header_formatted(self) -> FormattedText:
        """Return the header pane as FormattedText for PTK.

        Applies the active character's border color to every row of the header
        (DEC-TUI-THEME-001 / DEC-TUI-HEADER-001). The render_header() function
        returns plain-text strings; style tokens are injected here at the PTK
        FormattedText layer so the renderer stays markup-free and measurable.

        @decision DEC-TUI-APP-THEME-INJECT-001
        @title Theme colors are applied at the FormattedText layer in TuiApplication
        @status accepted
        @rationale render_header / LivePane.render return plain strings so they
                   can be width-measured without stripping escape codes. The PTK
                   FormattedText style token is the correct injection point — it
                   is applied by PTK's renderer without polluting the string
                   length invariants. All three pane builders (header, live pane,
                   scrollback) apply fg:<border_color> so the single authority
                   for color (DEFAULT_THEMES in themes.py) is read once per render
                   cycle and applied uniformly (Sacred Practice 12).
        """
        mode_name = self._mode_mgr.active.name if self._mode_mgr is not None else "default"
        active_theme = theme_for(mode_name)
        border_color = resolved_border_color(active_theme)
        rows = self._header_pane.render(theme=active_theme)
        parts: list[tuple[str, str]] = []
        for i, row in enumerate(rows):
            parts.append((f"fg:{border_color}", row))
            if i < len(rows) - 1:
                parts.append(("", "\n"))
        return FormattedText(parts)

    def _get_scrollback_formatted(self) -> FormattedText:
        """Return the scrollback buffer as FormattedText for PTK.

        Scrollback lines are emitted as terminal-default text (style ``""``).
        The scrollback buffer stores plain strings that may contain Rich markup
        stripped by emit_line; we do not re-apply character theme colors here
        because the scrollback content is heterogeneous (user input, tool output,
        error panels) and does not belong to any single character's palette.
        Character-themed borders are applied only to the header and live pane
        (DEC-TUI-APP-THEME-INJECT-001).
        """
        # A bounded render window is essential: the live pane refreshes while
        # tools run, and rebuilding an unbounded transcript made long sessions
        # progressively slower.
        lines = self._scrollback.get_window(limit=5000)
        parts: list[tuple[str, str]] = []
        for line in lines:
            parts.append(("", line + "\n"))
        return FormattedText(parts)

    def _get_scrollback_cursor_position(self) -> Point:
        """Anchor PTK's viewport at the requested distance from live output."""
        line_count = min(5000, len(self._scrollback.get_lines()))
        return Point(x=0, y=max(0, line_count - 1 - self._scroll_offset))

    def _get_scrollback_vertical_scroll(self, window: Window) -> int:
        """Translate live-relative scroll state into a real PTK viewport row."""
        line_count = min(5000, len(self._scrollback.get_lines()))
        height = window.render_info.window_height if window.render_info is not None else 1
        return max(0, line_count - height - self._scroll_offset)

    def _drag_scrollback(self, fraction: float, render_info) -> None:  # type: ignore[no-untyped-def]
        """Move the intelligence feed from a scrollbar track position."""
        maximum = max(0, render_info.content_height - render_info.window_height)
        desired_from_top = round(maximum * fraction)
        self._scroll_offset = maximum - desired_from_top
        self._app.invalidate()

    def _get_live_pane_formatted(self) -> FormattedText:
        """Return the live pane as FormattedText for PTK.

        Applies the active character's border color to the live pane rows so
        the pane participates in the per-character visual identity system
        (DEC-TUI-THEME-001 / DEC-TUI-APP-THEME-INJECT-001).

        Row 1 (character identity line) uses ``heading_color`` for bold accent.
        Rows 2–6 (target, hypothesis, dossier, activity, yield hint) use
        ``fg:<border_color>`` so the pane frame is character-colored throughout.
        The theme is resolved fresh on every render call so a mode change takes
        effect on the next refresh cycle without any additional cache invalidation.
        """
        mode_name = self._mode_mgr.active.name if self._mode_mgr is not None else "default"
        active_theme = theme_for(mode_name)
        border_color = resolved_border_color(active_theme)
        # heading_color stores hex only (DEC-TUI-PTK-COLOR-COMPAT-001).
        # bold is a separate PTK modifier token, not embedded in the color value.
        heading_style = f"bold fg:{active_theme.heading_color}"
        rows = self._live_pane.render()
        parts: list[tuple[str, str]] = []
        for i, row in enumerate(rows):
            # The storyboard uses a multi-color instrument cluster: identity,
            # evidence state, dossier progress, and live activity each need a
            # distinct glanceable channel while retaining one persona palette.
            if i == 0:
                style = heading_style
            elif is_high_contrast_mode():
                style = f"fg:{border_color}"
            elif i in {1, 2}:
                style = f"fg:{active_theme.text_color}"
            elif i == 3:
                style = f"bold fg:{active_theme.accent_color}"
            elif i == 4:
                style = f"bold fg:{border_color}"
            else:
                style = f"fg:{active_theme.accent_color}"
            parts.append((style, row))
            if i < len(rows) - 1:
                parts.append(("", "\n"))
        return FormattedText(parts)

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def _scroll_older(self, lines: int = 10) -> None:
        """Move the intelligence viewport toward older evidence."""
        self._scroll_offset += max(1, lines)

    def _scroll_newer(self, lines: int = 10) -> None:
        """Move the intelligence viewport toward live evidence."""
        self._scroll_offset = max(0, self._scroll_offset - max(1, lines))

    def _on_input_accepted(self, buffer: Buffer) -> None:
        """Handle Enter key — route all input through handle_input priority chain.

        All three dispatch layers (REPL verbs → yield commands → LLM chat)
        are handled inside runner.handle_input (DEC-RUNNER-INPUT-PRIORITY-001).
        The TUI wires two callables onto the runner before dispatch so the verb
        dispatcher can access TUI-specific behaviour:

        - ``_scrollback_clear``: callable that clears the scrollback buffer
          (invoked by the ``clear`` verb).
        - ``_event_bus``: EventBus for publishing TargetChanged events
          (invoked by the ``use <ioc>`` verb).

        LivePane satisfies ``_StatusHook`` so tool-activity phrases flow to the
        live pane during LLM tool calls without the runner importing Rich.
        """
        text = buffer.text.strip()
        buffer.reset()

        if not text:
            return

        self.emit_scrollback(f"> {text}")

        if self._runner is None:
            return

        # Inject TUI-specific callables onto the runner so verb dispatch
        # can clear scrollback and publish events without importing TUI modules.
        # These are ephemeral attributes — set before the call, not stored
        # permanently on the runner class (duck-typed injection pattern).
        self._runner._scrollback_clear = self._scrollback.clear  # type: ignore[attr-defined]
        self._runner._event_bus = self._event_bus  # type: ignore[attr-defined]

        # Never run network/LLM work on prompt_toolkit's render thread. Apart
        # from freezing repaint and completion, the old synchronous call made
        # the advertised yield controls unusable while a hunt was active.
        self._executor.submit(self._process_input, text)

    def _process_input(self, text: str) -> None:
        """Dispatch one command away from the render thread.

        Natural-language chat mutations are serialized because AgentRunner's
        conversation is ordered state. Local/yield commands remain concurrent
        so ``stop``, ``focus``, ``add`` and ``skip`` work during a slow hunt.
        """
        from adversary_pursuit.agent.repl_verbs import _FarewellExit, parse_repl_verb
        from adversary_pursuit.agent.yield_commands import parse_yield

        try:
            verb = parse_repl_verb(text)
            yield_command = parse_yield(text)
            if yield_command is not None:
                # Yield controls must remain available while another command
                # owns the serialized conversation/state mutation lane.
                result = self._runner.handle_input(text, status_bar=self._live_pane)
            else:
                if verb is None:
                    self._live_pane.set_activity("thinking")
                    self._append_rule("ANALYSIS CHANNEL OPEN")
                    self.emit_scrollback(
                        "◇ Reasoning over the current evidence and selecting justified probes…"
                    )
                with self._chat_lock:
                    result = self._runner.handle_input(text, status_bar=self._live_pane)
            if result:
                self.emit_scrollback(result)
            if verb is not None and verb.name == "clear":
                self._scroll_offset = 0
            if verb is not None and verb.name == "use":
                self._run_target_batteries(verb.args[0])
        except _FarewellExit as exc:
            if exc.phrase:
                self.emit_scrollback(exc.phrase)
            self._app.exit()
        except SystemExit:
            self._app.exit()
        except Exception as exc:  # noqa: BLE001
            self._emit_error_card(exc, text)
        finally:
            self._live_pane.set_activity(None)

    def _run_target_batteries(self, target: str) -> None:
        """Run deterministic local/API batteries, then synthesize once.

        Target classification and tool selection do not spend tokens. The LLM
        sees only the aggregated evidence and is called at most once, where its
        reasoning adds value: synthesis, hypotheses, and the next pivot.
        """
        from adversary_pursuit.agent.battery import BatteryRun
        from adversary_pursuit.agent.battery_registry import dispatch_batteries
        from adversary_pursuit.agent.tools import execute_tool
        from adversary_pursuit.core.ioc_types import detect_ioc_type

        ioc_type = detect_ioc_type(target)
        stix_types = {
            "ipv4": "ipv4-addr",
            "ipv6": "ipv6-addr",
            "domain": "domain-name",
            "url": "url",
            "email": "email-addr",
            "sha256": "file",
            "sha1": "file",
            "md5": "file",
        }
        target_type = stix_types.get(ioc_type or "", "unrecognized-type")
        batteries = dispatch_batteries(target_type, dossier_state=None)
        if not batteries:
            self.emit_scrollback(f"No local hunting battery matches {target_type} yet.")
            return

        schemas = {
            schema.get("function", {}).get("name"): schema.get("function", {})
            for schema in getattr(self._runner, "tools", ())
            if isinstance(schema, dict)
        }
        evidence: list[str] = []

        def run_tool(tool_name: str, value: str) -> None:
            function = schemas.get(tool_name)
            if function is None:
                self.emit_scrollback(f"◇ {tool_name}: unavailable — continuing")
                return
            parameters = function.get("parameters", {})
            properties = parameters.get("properties", {})
            required = parameters.get("required", ())
            argument_name = required[0] if required else next(iter(properties), "target")
            self._append_panel(
                f"PROBE · {tool_name.upper().replace('_', ' ')}",
                render_briefing(tool_name, value),
            )
            self._app.invalidate()
            summary, celebration, _badges, _challenges = execute_tool(
                self._runner.ctx, tool_name, {argument_name: value}
            )
            evidence.append(f"[{tool_name}]\n{summary}")
            snippet = self._interesting_snippet(summary)
            self._append_panel(
                f"EVIDENCE · {tool_name.upper().replace('_', ' ')}",
                f"OBSERVED\n{snippet}\n\nPROVENANCE  {tool_name} · stored in workspace",
            )
            if celebration:
                self.emit_scrollback(celebration)

        try:
            for battery in batteries:
                if not battery.tools:
                    continue
                run = BatteryRun(battery, self._event_bus, run_tool)
                self._runner._active_battery_run = run  # type: ignore[attr-defined]
                run.run(target)
        finally:
            self._runner._active_battery_run = None  # type: ignore[attr-defined]

        if not evidence:
            return
        narrate = getattr(self._runner, "narrate", None)
        if not callable(narrate):
            return
        prompt = (
            "Synthesize this deterministic threat-hunting evidence in the active character "
            "voice. Do not reveal hidden chain-of-thought. Give one brief ANALYST INTUITION "
            "line that externalizes the useful hunch, then label EVIDENCE, INFERENCE, "
            "UNCERTAINTY, and NEXT PIVOT. Treat only tool output as observed evidence. "
            f"Be concise and do not repeat raw fields. Target: {target}\n\n"
            + "\n\n".join(evidence)
        )
        self._live_pane.set_activity("composing")
        synthesis = narrate(prompt, max_tokens=300)
        self._live_pane.set_activity(None)
        if synthesis:
            character = getattr(self._mode_mgr.active, "name", "default").upper()
            self._append_panel(f"EPIPHANY · {character} · INFERENCE", synthesis)
            self._app.invalidate()

    @staticmethod
    def _interesting_snippet(summary: str, *, max_lines: int = 4, width: int = 66) -> str:
        """Return a compact, deterministic evidence preview for the live feed."""
        lines = [line.strip() for line in summary.splitlines() if line.strip()]
        selected = lines[:max_lines] or ["No printable fields returned."]
        return "\n".join(line[:width] for line in selected)

    def _emit_agent_trace(self, kind: str, tool_name: str, payload) -> None:  # type: ignore[no-untyped-def]
        """Render LLM-selected tool work without confusing it with synthesis."""
        display = tool_name.upper().replace("_", " ")
        if kind == "probe":
            target = next(iter(payload.values()), "unspecified")
            body = render_briefing(tool_name, str(target))
            self._append_panel(f"PROBE · {display}", body)
        else:
            snippet = self._interesting_snippet(str(payload))
            self._append_panel(
                f"EVIDENCE · {display}",
                f"OBSERVED\n{snippet}\n\nPROVENANCE  {tool_name} · stored in workspace",
            )
        self._app.invalidate()

    def _emit_error_card(self, exc: BaseException, command: str) -> None:
        """Turn an exception into an in-context recovery card."""
        from adversary_pursuit.core.error_interpreter import interpret

        interp = interpret(exc, context={"surface": "tui", "command": command[:200]})
        body = (
            f"{interp.summary}\n\n"
            f"NEXT  {interp.suggested_fix}\n"
            f"RETRY Re-run the command when ready\n"
            f"REF   {interp.diagnostic_id} (details retained automatically)"
        )
        self._append_panel(f"{interp.category.upper()} · RECOVERY", body)
        self._app.invalidate()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def emit_scrollback(self, text: str) -> None:
        """Append *text* to the scrollback buffer (thread-safe).

        Parameters
        ----------
        text:
            Plain-text string. Multi-line strings are split on newlines.
        """
        self._append_feed(lambda: self._scrollback.emit_line(text))
        # Invalidate the PTK app so the new line is rendered promptly
        try:
            self._app.invalidate()
        except Exception:  # noqa: BLE001
            pass  # app may not be running yet during early setup

    def _append_feed(self, writer) -> None:  # type: ignore[no-untyped-def]
        """Append output without stealing an analyst's historical viewport."""
        was_reviewing_history = self._scroll_offset > 0
        before = len(self._scrollback.get_lines())
        writer()
        if was_reviewing_history:
            added = max(0, len(self._scrollback.get_lines()) - before)
            self._scroll_offset += added

    def _append_panel(self, title: str, body: str) -> None:
        self._append_feed(lambda: self._scrollback.emit_panel(title, body))

    def _append_rule(self, title: str = "") -> None:
        self._append_feed(lambda: self._scrollback.emit_rule(title))

    def run(self) -> None:
        """Start the TUI application.

        Launches the background live-pane refresh thread, then enters the
        prompt_toolkit event loop (blocking until Ctrl-C/Ctrl-D).
        """
        self._stop_refresh.clear()
        self._refresh_thread = threading.Thread(
            target=self._refresh_loop,
            daemon=True,
            name="tui-live-pane-refresh",
        )
        self._refresh_thread.start()
        try:
            self._app.run()
        finally:
            self._stop_refresh.set()
            self._executor.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------
    # Background refresh loop
    # ------------------------------------------------------------------

    def _refresh_loop(self) -> None:
        """Background thread: invalidate the app at the live pane cadence."""
        while not self._stop_refresh.is_set():
            # Faster redraws do not make network work faster. Two frames per
            # second keeps activity feeling live without continuously repainting
            # the terminal while the operator is typing.
            hz = min(self._live_pane.refresh_hz, 2.0)
            interval = 1.0 / max(hz, 0.1)
            time.sleep(interval)
            self._prompt_phase = not self._prompt_phase
            try:
                self._app.invalidate()
            except Exception:  # noqa: BLE001
                pass  # app may have exited

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_model_display(self) -> str:
        """Return a short model display string from runner config, or ''."""
        try:
            if self._runner is not None and hasattr(self._runner, "model"):
                return str(self._runner.model)
        except Exception:  # noqa: BLE001
            pass
        return ""

    def _editing_mode(self) -> EditingMode:
        config = getattr(self._runner, "_config_mgr", None)
        configured = config.get_editing_mode() if config is not None else "vi"
        env = __import__("os").environ.get("AP_EDITING_MODE", configured).lower()
        return EditingMode.EMACS if env == "emacs" else EditingMode.VI

    @staticmethod
    def _build_history():
        history_path = Path.home() / ".ap" / "chat_history"
        try:
            history_path.parent.mkdir(parents=True, exist_ok=True)
            return FileHistory(str(history_path))
        except OSError:
            return InMemoryHistory()

    @property
    def scrollback(self) -> ScrollbackBuffer:
        """The shared scrollback buffer."""
        return self._scrollback

    @property
    def live_pane(self) -> LivePane:
        """The live pane instance."""
        return self._live_pane

    @property
    def header_pane(self) -> HeaderPane:
        """The header pane instance (DEC-TUI-HEADER-001)."""
        return self._header_pane
