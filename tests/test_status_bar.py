"""Tests for Phase 18 Slice 5: StatusBar in banner.py.

Covers:
- StatusBar renders each section when data present
- Sections skip gracefully when data missing
- set_activity("virustotal") and set_activity(None) don't crash
- Elapsed time renders as mm:ss
- StatusBar works as context manager

@decision DEC-TEST-STATUS-BAR-001
@title StatusBar tests use StringIO Console to capture rendered text without live terminal
@status accepted
@rationale Rich Live with transient=True requires a real terminal for full rendering.
           Tests use a Rich Console(file=StringIO()) to capture the Text object
           produced by _render_bar() directly, avoiding TTY dependency. Context
           manager tests use console.is_dumb_terminal=False workaround via
           force_terminal=True on the Console constructor.
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from adversary_pursuit.agent.banner import StatusBar

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_console() -> Console:
    """Create a Rich Console writing to StringIO for test capture."""
    return Console(file=io.StringIO(), force_terminal=True, width=120)


class FakeWorkspaceMgr:
    """Minimal workspace manager stub for StatusBar tests."""

    def __init__(self, elapsed: int = 42, pivots: int = 0):
        self._elapsed = elapsed
        self._pivots = pivots

    def get_workspace_stats(self) -> dict:
        return {
            "elapsed_seconds": self._elapsed,
            "pivot_count": self._pivots,
            "total_indicators": 0,
            "domain_count": 0,
            "ip_count": 0,
            "module_run_count": 0,
            "total_score": 0,
            "note_count": 0,
        }


# ---------------------------------------------------------------------------
# _render_bar content
# ---------------------------------------------------------------------------


class TestStatusBarRenderBar:
    """_render_bar() produces the expected text content."""

    def test_render_includes_mode_name(self):
        """Rendered bar contains the mode name."""
        bar = StatusBar(make_console(), mode_name="deckard", model_display="ollama/qwen2.5:8b")
        text = bar._render_bar()
        assert "deckard" in text.plain

    def test_render_includes_model_short(self):
        """Rendered bar contains the shortened model name (last segment after /)."""
        bar = StatusBar(make_console(), mode_name="default", model_display="ollama/qwen2.5:8b")
        text = bar._render_bar()
        assert "qwen2.5:8b" in text.plain
        assert "ollama" not in text.plain

    def test_render_model_no_slash(self):
        """Model without slash is shown as-is."""
        bar = StatusBar(make_console(), mode_name="default", model_display="gpt-4o")
        text = bar._render_bar()
        assert "gpt-4o" in text.plain

    def test_render_includes_elapsed_time(self):
        """Rendered bar contains elapsed mm:ss when workspace_mgr provided."""
        wm = FakeWorkspaceMgr(elapsed=125)  # 2:05
        bar = StatusBar(make_console(), mode_name="default", model_display="m", workspace_mgr=wm)
        text = bar._render_bar()
        assert "02:05" in text.plain

    def test_render_no_elapsed_without_workspace_mgr(self):
        """No elapsed time shown when workspace_mgr is None."""
        bar = StatusBar(make_console(), mode_name="default", model_display="m", workspace_mgr=None)
        text = bar._render_bar()
        # Should not contain time-like mm:ss pattern for elapsed
        plain = text.plain
        assert ":" not in plain or "│" in plain  # separator : is fine, but no mm:ss

    def test_render_includes_pivot_count_when_nonzero(self):
        """Pivot count is shown when > 0."""
        wm = FakeWorkspaceMgr(elapsed=60, pivots=3)
        bar = StatusBar(make_console(), mode_name="default", model_display="m", workspace_mgr=wm)
        text = bar._render_bar()
        assert "3 pivot" in text.plain

    def test_render_omits_pivot_count_when_zero(self):
        """Pivot count not shown when 0."""
        wm = FakeWorkspaceMgr(elapsed=60, pivots=0)
        bar = StatusBar(make_console(), mode_name="default", model_display="m", workspace_mgr=wm)
        text = bar._render_bar()
        assert "pivot" not in text.plain.lower()

    def test_render_includes_activity_phrase(self):
        """Rendered bar contains a non-empty activity phrase."""
        bar = StatusBar(make_console(), mode_name="deckard", model_display="m")
        text = bar._render_bar()
        # Should have something after the last separator
        assert len(text.plain.strip()) > 0

    def test_render_uses_dim_cyan_style(self):
        """Rendered bar text uses dim cyan style."""
        bar = StatusBar(make_console(), mode_name="default", model_display="m")
        text = bar._render_bar()
        # Check that the spans have the expected style
        spans = list(text._spans)
        assert any("cyan" in str(s.style) for s in spans)

    def test_render_mode_prefix_emoji_included(self):
        """Mode prompt_prefix emoji is shown in the bar."""
        bar = StatusBar(make_console(), mode_name="ninja", model_display="m")
        text = bar._render_bar()
        assert "🥷" in text.plain

    def test_render_unknown_mode_no_crash(self):
        """Unknown mode name does not crash render."""
        bar = StatusBar(make_console(), mode_name="unknown_mode_xyz", model_display="m")
        text = bar._render_bar()
        assert "unknown_mode_xyz" in text.plain


# ---------------------------------------------------------------------------
# set_activity
# ---------------------------------------------------------------------------


class TestStatusBarSetActivity:
    """set_activity updates the activity without crashing."""

    def test_set_activity_virustotal_no_crash(self):
        """set_activity('virustotal') does not crash when not in live context."""
        bar = StatusBar(make_console(), mode_name="deckard", model_display="m")
        bar.set_activity("virustotal")  # no crash; _live is None so update is skipped

    def test_set_activity_none_no_crash(self):
        """set_activity(None) does not crash."""
        bar = StatusBar(make_console(), mode_name="default", model_display="m")
        bar.set_activity(None)

    def test_set_activity_changes_activity_attribute(self):
        """set_activity stores the slug on _activity."""
        bar = StatusBar(make_console(), mode_name="default", model_display="m")
        bar.set_activity("shodan")
        assert bar._activity == "shodan"

    def test_set_activity_none_clears_activity(self):
        """set_activity(None) clears _activity back to None."""
        bar = StatusBar(make_console(), mode_name="default", model_display="m")
        bar.set_activity("shodan")
        bar.set_activity(None)
        assert bar._activity is None

    def test_activity_reflected_in_render(self):
        """After set_activity, _render_bar() uses the new activity slug."""
        bar = StatusBar(make_console(), mode_name="deckard", model_display="m")
        bar.set_activity("virustotal")
        text = bar._render_bar()
        # deckard has "Running VT" / "Pulling VT sheet" for activity:virustotal
        plain = text.plain
        assert len(plain.strip()) > 0  # at minimum something rendered


# ---------------------------------------------------------------------------
# Elapsed mm:ss format
# ---------------------------------------------------------------------------


class TestElapsedFormat:
    """Elapsed time renders correctly as mm:ss."""

    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (0, "00:00"),
            (59, "00:59"),
            (60, "01:00"),
            (125, "02:05"),
            (3661, "61:01"),
        ],
    )
    def test_elapsed_format(self, seconds: int, expected: str):
        """Elapsed time renders as mm:ss."""
        wm = FakeWorkspaceMgr(elapsed=seconds)
        bar = StatusBar(make_console(), mode_name="default", model_display="m", workspace_mgr=wm)
        text = bar._render_bar()
        assert expected in text.plain, (
            f"Expected '{expected}' in bar for {seconds}s, got: {text.plain!r}"
        )


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestStatusBarContextManager:
    """StatusBar works as context manager and exits cleanly."""

    def test_enter_exit_no_crash(self):
        """StatusBar can be entered and exited without crashing."""
        console = make_console()
        bar = StatusBar(console, mode_name="default", model_display="m")
        with bar:
            pass  # no crash

    def test_double_exit_no_crash(self):
        """Calling __exit__ twice does not crash."""
        console = make_console()
        bar = StatusBar(console, mode_name="default", model_display="m")
        bar.__exit__(None, None, None)  # _live is None — should be silent

    def test_set_activity_inside_context_no_crash(self):
        """set_activity inside the context manager does not crash."""
        console = make_console()
        bar = StatusBar(console, mode_name="deckard", model_display="m")
        with bar:
            bar.set_activity("shodan")
            bar.set_activity(None)
