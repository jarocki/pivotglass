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
from adversary_pursuit.agent.tui.live_pane import LivePane
from adversary_pursuit.agent.tui.scrollback import ScrollbackBuffer


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
            HSplit([scrollback_window, input_window, live_pane_window]),
            focused_element=input_window,
        )

        return Application(
            layout=layout,
            key_bindings=kb,
            full_screen=True,
            mouse_support=False,
        )

    def _get_scrollback_formatted(self) -> FormattedText:
        """Return the scrollback buffer as FormattedText for PTK."""
        lines = self._scrollback.get_lines()
        # Each line followed by a newline; plain style
        parts = []
        for line in lines:
            parts.append(("", line + "\n"))
        return FormattedText(parts)

    def _get_live_pane_formatted(self) -> FormattedText:
        """Return the live pane as FormattedText for PTK."""
        rows = self._live_pane.render()
        parts = []
        for i, row in enumerate(rows):
            parts.append(("", row))
            if i < len(rows) - 1:
                parts.append(("", "\n"))
        return FormattedText(parts)

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def _on_input_accepted(self, buffer: Buffer) -> None:
        """Handle Enter key — route input to yield parser or agent runner."""
        text = buffer.text.strip()
        buffer.reset()

        if not text:
            return

        # Try yield command first
        from adversary_pursuit.agent.yield_commands import parse_yield

        cmd = parse_yield(text)
        if cmd is not None:
            from adversary_pursuit.agent.yield_commands import dispatch_yield

            character = "default"
            if self._mode_mgr is not None:
                character = self._mode_mgr.active.name

            # Active battery run is not held here — dispatch_yield accepts None
            feedback = dispatch_yield(cmd, None, self._event_bus, character)
            self.emit_scrollback(f"> {text}")
            self.emit_scrollback(feedback)
            return

        # Route to agent runner via handle_input — the single TUI entry point
        # (DEC-RUNNER-HANDLE-INPUT-001, Sacred Practice 12).  LivePane satisfies
        # the _StatusHook protocol so tool-activity updates flow to the live pane
        # during LLM tool calls without the runner importing Rich directly.
        self.emit_scrollback(f"> {text}")
        if self._runner is not None:
            try:
                # Runner is expected to be synchronous or to manage its own
                # threading. handle_input always returns a str (never None).
                result = self._runner.handle_input(text, status_bar=self._live_pane)
                if result:
                    self._scrollback.emit_line(result)
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
