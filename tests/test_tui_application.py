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

from unittest.mock import MagicMock, patch  # @mock-exempt: sys.stdin.isatty is OS/TTY boundary

import pytest

from adversary_pursuit.agent.tui.application import NotATTYError, TuiApplication
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


# ---------------------------------------------------------------------------
# LivePane render contract — independent of TuiApplication
# ---------------------------------------------------------------------------


def test_live_pane_renders_six_rows():
    """LivePane.render() always returns exactly 6 rows (DEC-TUI-LIVE-PANE-001)."""
    bus = EventBus()
    pane = LivePane(bus=bus, mode_name="default", model_display="test")
    lines = pane.render()
    assert len(lines) == 6
