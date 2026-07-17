"""Tests for TUI application layout invariants (C-2, C-5).

@decision DEC-TEST-TUI-APPLICATION-001
@title Tests verify TuiApplication layout contract and NotATTYError guard
@status accepted
@rationale DEC-TUI-APPLICATION-001 specifies that TuiApplication raises NotATTYError
           when stdin is not a TTY and provides a fixed 6-row live pane. Tests that
           require TuiApplication instantiation patch only sys.stdin.isatty (not the
           full stdin object) to avoid breaking prompt_toolkit's codec lookup, and also
           patch _build_app to avoid needing a real terminal for the PTK Application.
           ScrollbackBuffer and LivePane are tested directly for the buffer/pane
           contract since those are the testable components without a full PTK session.
           sys.stdin is an OS/external boundary — patching isatty is the minimal safe
           approach for CI environments that have no real TTY.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch  # @mock-exempt: sys.stdin.isatty is OS/TTY boundary

import pytest

from adversary_pursuit.agent.tui.application import (
    NotATTYError,
    TuiApplication,
    _TuiConsole,
)
from adversary_pursuit.agent.tui.events import EventBus
from adversary_pursuit.agent.tui.live_pane import LivePane
from adversary_pursuit.agent.tui.scrollback import ScrollbackBuffer

# ---------------------------------------------------------------------------
# Fake runner — minimal duck-type for TuiApplication.__init__
# ---------------------------------------------------------------------------


class FakeRunner:
    model = "test/model"

    class ctx:
        workspace_mgr = None
        mode_mgr = None


class FakeModeManager:
    class active:
        name = "default"


# ---------------------------------------------------------------------------
# NotATTYError importability
# ---------------------------------------------------------------------------


def test_not_a_tty_error_importable():
    """NotATTYError must be importable from application.py."""
    assert NotATTYError is not None
    assert issubclass(NotATTYError, RuntimeError)


# ---------------------------------------------------------------------------
# NotATTYError raised when stdin is not a TTY
# ---------------------------------------------------------------------------


def test_not_a_tty_error_raised_when_not_tty():
    """TuiApplication.__init__ raises NotATTYError when stdin.isatty() returns False.

    We patch only the isatty method, not the whole stdin object, so prompt_toolkit's
    codec detection (which reads stdin.encoding as a real str) is not disturbed.
    The NotATTYError guard runs before _build_app(), so prompt_toolkit is never reached.
    """
    bus = EventBus()
    runner = FakeRunner()
    mode_mgr = FakeModeManager()

    # @mock-exempt: sys.stdin.isatty is an OS/TTY boundary check
    with patch("sys.stdin.isatty", return_value=False):
        with pytest.raises(NotATTYError):
            TuiApplication(
                runner=runner,
                workspace_mgr=None,
                mode_mgr=mode_mgr,
                event_bus=bus,
            )


# ---------------------------------------------------------------------------
# TuiApplication construction via _build_app stub
# ---------------------------------------------------------------------------


def _make_app() -> TuiApplication:
    """Construct a TuiApplication with isatty=True and _build_app stubbed out.

    prompt_toolkit Application requires a real terminal session. We stub _build_app
    to return a MagicMock so TuiApplication.__init__ completes without a real PTK app.
    This isolates the scrollback buffer and live pane contract tests from PTK internals.
    """
    bus = EventBus()
    runner = FakeRunner()
    mode_mgr = FakeModeManager()

    # @mock-exempt: sys.stdin.isatty is OS/TTY boundary; _build_app needs a real terminal
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch.object(TuiApplication, "_build_app", return_value=MagicMock()),
    ):
        app = TuiApplication(
            runner=runner,
            workspace_mgr=None,
            mode_mgr=mode_mgr,
            event_bus=bus,
        )
    return app


def test_tui_application_instantiates():
    """TuiApplication can be instantiated when TTY is present."""
    app = _make_app()
    assert app is not None


def test_tui_application_has_run_method():
    app = _make_app()
    assert callable(getattr(app, "run", None))


def test_tui_application_has_emit_scrollback():
    app = _make_app()
    assert callable(getattr(app, "emit_scrollback", None))


def test_emit_scrollback_does_not_raise():
    """emit_scrollback must not raise when the PTK app is not running."""
    app = _make_app()
    app.emit_scrollback("hello world")


def test_emit_scrollback_grows_buffer():
    """After calling emit_scrollback, the scrollback buffer has more lines."""
    app = _make_app()
    initial_len = len(app._scrollback.get_lines())

    app.emit_scrollback("line one")
    app.emit_scrollback("line two")

    final_len = len(app._scrollback.get_lines())
    assert final_len == initial_len + 2


def test_emit_scrollback_stores_text():
    app = _make_app()
    app.emit_scrollback("unique-test-string-abc123")
    lines = app._scrollback.get_lines()
    assert any("unique-test-string-abc123" in line for line in lines)


def test_scrollback_property_accessible():
    app = _make_app()
    assert isinstance(app.scrollback, ScrollbackBuffer)


def test_live_pane_property_accessible():
    app = _make_app()
    assert isinstance(app.live_pane, LivePane)


# ---------------------------------------------------------------------------
# ScrollbackBuffer direct tests — independent of TuiApplication
# ---------------------------------------------------------------------------


def test_scrollback_buffer_emit_line_appends():
    buf = ScrollbackBuffer()
    buf.emit_line("hello")
    assert buf.get_lines() == ["hello"]


def test_scrollback_buffer_append_only():
    """get_lines() never shrinks (append-only invariant DEC-TUI-SCROLLBACK-001)."""
    buf = ScrollbackBuffer()
    buf.emit_line("first")
    snap1 = buf.get_lines()
    buf.emit_line("second")
    snap2 = buf.get_lines()
    assert len(snap2) >= len(snap1)
    assert "first" in snap2


def test_scrollback_window_is_bounded_and_supports_page_offset():
    buf = ScrollbackBuffer()
    for number in range(20):
        buf.emit_line(f"line {number}")

    assert buf.get_window(limit=5) == [f"line {number}" for number in range(15, 20)]
    assert buf.get_window(limit=5, offset=5) == [f"line {number}" for number in range(10, 15)]


def test_tui_input_restores_contextual_completer_and_history():
    app = _make_app()
    assert app._input_buffer.completer is not None
    assert app._input_buffer.history is not None


def test_tui_scrollback_renderer_only_requests_bounded_window():
    app = _make_app()
    app._scrollback.get_window = MagicMock(return_value=["recent"])

    rendered = app._get_scrollback_formatted()

    app._scrollback.get_window.assert_called_once_with(limit=500, offset=0)
    assert any("recent" in text for _style, text in rendered)


def test_input_accept_does_not_block_render_thread():
    app = _make_app()
    started = threading.Event()
    release = threading.Event()

    def slow_handle_input(text, status_bar=None):
        started.set()
        release.wait(timeout=2)
        return "done"

    app._runner.handle_input = slow_handle_input
    app._input_buffer.text = "investigate example.com"

    before = time.monotonic()
    app._on_input_accepted(app._input_buffer)
    elapsed = time.monotonic() - before

    assert elapsed < 0.1
    assert started.wait(timeout=1)
    release.set()
    app._executor.shutdown(wait=True)


def test_help_overlay_content_is_immediately_discoverable():
    app = _make_app()
    rendered = app._get_help_formatted()
    text = "".join(fragment for _style, fragment in rendered)

    assert "OPERATOR" not in text  # title belongs to the overlay frame
    assert "use <ioc>" in text
    assert "stop" in text
    assert "Tab" in text
    assert "Press Esc" in text


def test_prompt_marker_is_high_contrast_and_animated():
    app = _make_app()

    first = list(app._get_prompt_formatted())
    app._prompt_phase = True
    second = list(app._get_prompt_formatted())

    assert "blink" in first[0][0]
    assert "reverse" in first[0][0]
    assert first[0][1] == "> "
    assert second[0][1] == "▶ "


def test_pursuit_title_tracks_active_mode():
    app = _make_app()
    app._mode_mgr = MagicMock()
    app._mode_mgr.active.name = "trinity"

    rendered = app._get_pursuit_title_formatted()

    assert any("THE MATRIX" in text for _style, text in rendered)
    assert all("INTELLIGENCE FEED" not in text for _style, text in rendered)


def test_target_hunt_uses_tools_then_one_synthesis_call():
    app = _make_app()
    app._runner.tools = [
        {
            "type": "function",
            "function": {
                "name": "whois_lookup",
                "parameters": {
                    "properties": {"domain": {"type": "string"}},
                    "required": ["domain"],
                },
            },
        }
    ]
    app._runner.narrate = MagicMock(return_value="Synthesized next pivot")

    with patch(
        "adversary_pursuit.agent.tools.execute_tool",
        return_value=("WHOIS evidence", None, [], []),
    ) as tool:
        app._run_target_batteries("example.com")

    tool.assert_called_once_with(app._runner.ctx, "whois_lookup", {"domain": "example.com"})
    app._runner.narrate.assert_called_once()
    assert app._runner.narrate.call_args.kwargs["max_tokens"] == 300


def test_tui_console_keeps_debug_details_out_of_normal_flow():
    emitted = []
    console = _TuiConsole(emitted.append)

    console.print("Diagnostic ID: cafe1234  Debug log: /tmp/debug.log")

    assert len(emitted) == 1
    assert "cafe1234" in emitted[0]
    assert "Details retained automatically" in emitted[0]
    assert "/tmp/debug.log" not in emitted[0]


def test_runner_error_becomes_recovery_card():
    app = _make_app()
    interp = MagicMock(
        category="Network",
        summary="Provider unavailable.",
        suggested_fix="Check the connection.",
        diagnostic_id="cafe1234",
    )

    with patch("adversary_pursuit.core.error_interpreter.interpret", return_value=interp):
        app._emit_error_card(RuntimeError("boom"), "investigate example.com")

    text = "\n".join(app._scrollback.get_lines())
    assert "NETWORK · RECOVERY" in text
    assert "NEXT  Check the connection." in text
    assert "RETRY" in text
    assert "cafe1234" in text
    assert "debug.log" not in text


# ---------------------------------------------------------------------------
# LivePane render contract — independent of TuiApplication
# ---------------------------------------------------------------------------


def test_live_pane_renders_six_rows():
    """LivePane.render() always returns exactly 6 rows (DEC-TUI-LIVE-PANE-001)."""
    bus = EventBus()
    pane = LivePane(bus=bus, mode_name="default", model_display="test")
    lines = pane.render()
    assert len(lines) == 6
