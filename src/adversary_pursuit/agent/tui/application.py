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

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout

from adversary_pursuit.agent.tui.events import EventBus
from adversary_pursuit.agent.tui.header import HeaderPane
from adversary_pursuit.agent.tui.live_pane import LivePane
from adversary_pursuit.agent.tui.scrollback import ScrollbackBuffer
from adversary_pursuit.agent.tui.themes import (  # character theme dispatch
    resolved_border_color,
    theme_for,
)


class NotATTYError(RuntimeError):
    """Raised when TuiApplication is constructed outside a real TTY.

    Callers should catch this and fall back to the legacy Rich REPL.
    """


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
        )
        self._app = self._build_app()

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
        )
        scrollback_window = Window(
            content=scrollback_control,
            dont_extend_height=False,
            wrap_lines=True,
        )

        input_window = Window(
            content=BufferControl(buffer=self._input_buffer, focusable=True),
            height=1,
            dont_extend_height=True,
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

        layout = Layout(
            HSplit([header_window, scrollback_window, input_window, live_pane_window]),
            focused_element=input_window,
        )

        return Application(
            layout=layout,
            key_bindings=kb,
            full_screen=True,
            mouse_support=False,
        )

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
        lines = self._scrollback.get_lines()
        parts: list[tuple[str, str]] = []
        for line in lines:
            parts.append(("", line + "\n"))
        return FormattedText(parts)

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
        heading_style = active_theme.heading_color
        rows = self._live_pane.render()
        parts: list[tuple[str, str]] = []
        for i, row in enumerate(rows):
            # Row 0 (index 0) is the character identity line — use heading_color for accent
            style = heading_style if i == 0 else f"fg:{border_color}"
            parts.append((style, row))
            if i < len(rows) - 1:
                parts.append(("", "\n"))
        return FormattedText(parts)

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

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

        try:
            from adversary_pursuit.agent.repl_verbs import _FarewellExit

            # handle_input always returns a str (never None).
            result = self._runner.handle_input(text, status_bar=self._live_pane)
            if result:
                self._scrollback.emit_line(result)
        except _FarewellExit as exc:
            # quit/exit/q — emit farewell phrase then exit the TUI.
            if exc.phrase:
                self._scrollback.emit_line(exc.phrase)
            self._app.exit()
        except SystemExit:
            self._app.exit()
        except Exception as exc:  # noqa: BLE001
            self.emit_scrollback(f"[error] {exc}")

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
        self._scrollback.emit_line(text)
        # Invalidate the PTK app so the new line is rendered promptly
        try:
            self._app.invalidate()
        except Exception:  # noqa: BLE001
            pass  # app may not be running yet during early setup

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

    # ------------------------------------------------------------------
    # Background refresh loop
    # ------------------------------------------------------------------

    def _refresh_loop(self) -> None:
        """Background thread: invalidate the app at the live pane cadence."""
        while not self._stop_refresh.is_set():
            hz = self._live_pane.refresh_hz
            interval = 1.0 / max(hz, 0.1)
            time.sleep(interval)
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
