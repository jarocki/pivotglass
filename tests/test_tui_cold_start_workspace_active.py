"""Regression tests for Slice 7Ah: TuiApplication cold-start hardening.

Verifies TuiApplication.__init__ succeeds when workspace_mgr.active raises
RuntimeError (cold-start, no workspace switched yet) — the previous behavior
crashed adversary_pursuit chat before the TUI could open.

@decision DEC-TUI-COLD-START-HARDENING-001
@title TuiApplication.__init__ tolerates workspace_mgr.active raising on cold start
@status accepted
@rationale WorkspaceManager.active raises RuntimeError when _active is None.
           On cold start / first launch, TuiApplication.__init__ called the property
           directly, crashing before the TUI opened. The fix wraps the access in
           try/except RuntimeError and falls back to "default", which is the name
           WorkspaceManager.get_session() auto-switches to on first DB access.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch  # @mock-exempt: sys.stdin.isatty is OS/TTY boundary

from adversary_pursuit.agent.tui.application import TuiApplication
from adversary_pursuit.agent.tui.events import EventBus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class RaisingWorkspaceMgr:
    """Mock WorkspaceManager whose .active property raises RuntimeError.

    Mimics the real workspace.py:324 property behavior when _active is None
    (cold start — no workspace switched to yet).
    """

    @property
    def active(self) -> str:
        raise RuntimeError("No active workspace. Call switch() or get_session() first.")


class _FakeMode:
    name = "default"


class FakeModeMgr:
    active = _FakeMode()


# ---------------------------------------------------------------------------
# Regression: cold-start crash (Slice 7Ah)
# ---------------------------------------------------------------------------


def test_tui_application_cold_start_no_active_workspace_does_not_crash():
    """Regression: TuiApplication.__init__ must succeed when workspace_mgr.active raises.

    This is the exact failure that shipped with Slice 7A: workspace_mgr.active was
    called as a plain attribute lookup at application.py line 109 but the property
    raises RuntimeError on cold start. The TUI crashed before opening.
    """
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch.object(TuiApplication, "_build_app", return_value=MagicMock()),
    ):
        app = TuiApplication(
            runner=None,
            workspace_mgr=RaisingWorkspaceMgr(),
            mode_mgr=FakeModeMgr(),
            event_bus=EventBus(),
        )

    # Header pane must have fallen back to "default"
    assert app._header_pane._workspace_name == "default"


# ---------------------------------------------------------------------------
# Baseline: None workspace_mgr
# ---------------------------------------------------------------------------


def test_tui_application_none_workspace_mgr_uses_default():
    """Baseline: when workspace_mgr is None, header uses 'default' (unchanged behavior)."""
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch.object(TuiApplication, "_build_app", return_value=MagicMock()),
    ):
        app = TuiApplication(
            runner=None,
            workspace_mgr=None,
            mode_mgr=FakeModeMgr(),
            event_bus=EventBus(),
        )

    assert app._header_pane._workspace_name == "default"


# ---------------------------------------------------------------------------
# Baseline: workspace_mgr.active returns a name
# ---------------------------------------------------------------------------


def test_tui_application_active_workspace_uses_that_name():
    """Baseline: when workspace_mgr.active returns a name, header uses it."""
    ws_mgr = MagicMock()
    ws_mgr.active = "my-project-workspace"

    with (
        patch("sys.stdin.isatty", return_value=True),
        patch.object(TuiApplication, "_build_app", return_value=MagicMock()),
    ):
        app = TuiApplication(
            runner=None,
            workspace_mgr=ws_mgr,
            mode_mgr=FakeModeMgr(),
            event_bus=EventBus(),
        )

    assert app._header_pane._workspace_name == "my-project-workspace"


# ---------------------------------------------------------------------------
# Compound-interaction: full production sequence
# ---------------------------------------------------------------------------


def test_tui_application_cold_start_header_renders_correctly():
    """Compound-interaction: cold-start app init + header render produces valid 3-row output.

    Exercises the real production sequence crossing multiple components:
    TuiApplication.__init__ (cold-start fallback) → HeaderPane construction
    → HeaderPane.render() → render_header() → 3-row plain-text output.

    Verifies the workspace name "default" is visible in the rendered header,
    confirming the full pipeline works end-to-end, not just that the attribute
    was set.
    """
    from adversary_pursuit.agent.tui.themes import theme_for

    with (
        patch("sys.stdin.isatty", return_value=True),
        patch.object(TuiApplication, "_build_app", return_value=MagicMock()),
    ):
        app = TuiApplication(
            runner=None,
            workspace_mgr=RaisingWorkspaceMgr(),
            mode_mgr=FakeModeMgr(),
            event_bus=EventBus(),
        )

    theme = theme_for("default")
    rows = app._header_pane.render(theme=theme, width=80)

    # render() always returns exactly 3 rows (DEC-TUI-HEADER-001)
    assert len(rows) == 3

    # "WORKSPACE: default" must appear in the title row (row 0)
    assert "WORKSPACE: default" in rows[0]
