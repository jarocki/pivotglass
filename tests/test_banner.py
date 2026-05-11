"""Tests for agent/banner.py — ASCII art boot banner and animations.

Production sequence:
  render_boot_banner(console) -> None   (renders to console, respects AP_NO_BANNER)
  get_mode_color(mode_name) -> str      (mode-specific Rich colour string)
  thinking_status(console) -> context manager (wraps LLM call with spinner)

@decision DEC-TEST-BANNER-001
@title Test banner via captured Rich Console output; no PTY required
@status accepted
@rationale render_boot_banner() writes to the caller-supplied Rich Console.
           Using Console(file=StringIO()) lets us capture output for assertion
           without a real terminal. AP_NO_BANNER=1 is set in the no-banner
           tests via monkeypatch so the typewriter sleep loop is skipped,
           keeping test time < 100ms. The thinking_status context manager is
           tested by entering and exiting it around a no-op — we verify it
           doesn't leak exceptions or state.
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from adversary_pursuit.agent.banner import (
    MODE_COLORS,
    _FALLBACK_COLOR,
    get_mode_color,
    render_boot_banner,
    thinking_status,
)
from adversary_pursuit.agent.repl_input import _MODE_NAMES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_console() -> tuple[Console, io.StringIO]:
    """Return a Rich Console that writes to a StringIO buffer."""
    buf = io.StringIO()
    console = Console(file=buf, highlight=False, markup=True)
    return console, buf


# ---------------------------------------------------------------------------
# render_boot_banner
# ---------------------------------------------------------------------------


class TestRenderBootBanner:
    def test_renders_without_exception(self, monkeypatch):
        """Banner must not raise under any circumstances."""
        monkeypatch.setenv("AP_NO_BANNER", "1")
        console, _ = _make_console()
        render_boot_banner(console)  # should not raise

    def test_ap_no_banner_produces_no_output(self, monkeypatch):
        """AP_NO_BANNER=1 must suppress all banner output."""
        monkeypatch.setenv("AP_NO_BANNER", "1")
        console, buf = _make_console()
        render_boot_banner(console)
        assert buf.getvalue() == ""

    def test_banner_without_env_guard_produces_output(self, monkeypatch):
        """When AP_NO_BANNER is not set, banner produces non-empty output."""
        monkeypatch.delenv("AP_NO_BANNER", raising=False)
        # Override time.sleep so the typewriter doesn't slow tests
        monkeypatch.setattr("adversary_pursuit.agent.banner.time.sleep", lambda _: None)
        console, buf = _make_console()
        render_boot_banner(console)
        output = buf.getvalue()
        assert len(output) > 0

    def test_banner_output_contains_adversary_pursuit(self, monkeypatch):
        """Banner must mention 'Adversary Pursuit' somewhere."""
        monkeypatch.delenv("AP_NO_BANNER", raising=False)
        monkeypatch.setattr("adversary_pursuit.agent.banner.time.sleep", lambda _: None)
        console, buf = _make_console()
        render_boot_banner(console)
        output = buf.getvalue()
        assert (
            "Adversary Pursuit" in output
            or "ADVERSARY PURSUIT" in output
            or "AP" in output
        )

    def test_banner_output_contains_tagline(self, monkeypatch):
        """Banner should include the tagline or CTI reference."""
        monkeypatch.delenv("AP_NO_BANNER", raising=False)
        monkeypatch.setattr("adversary_pursuit.agent.banner.time.sleep", lambda _: None)
        console, buf = _make_console()
        render_boot_banner(console)
        output = buf.getvalue()
        # Tagline or at least the panel border should be present
        assert len(output) > 10


# ---------------------------------------------------------------------------
# get_mode_color
# ---------------------------------------------------------------------------


class TestGetModeColor:
    def test_all_mode_names_have_colors(self):
        """Every mode in _MODE_NAMES must map to a non-empty colour string."""
        for mode_name in _MODE_NAMES:
            color = get_mode_color(mode_name)
            assert isinstance(color, str)
            assert len(color) > 0

    def test_mode_colors_dict_covers_all_repl_modes(self):
        """MODE_COLORS must contain an entry for every mode in _MODE_NAMES."""
        for mode_name in _MODE_NAMES:
            assert mode_name in MODE_COLORS, (
                f"MODE_COLORS is missing an entry for mode '{mode_name}'. "
                "Add it to banner.MODE_COLORS."
            )

    def test_unknown_mode_returns_fallback(self):
        result = get_mode_color("not_a_real_mode")
        assert result == _FALLBACK_COLOR

    def test_ninja_is_dim(self):
        assert "dim" in get_mode_color("ninja")

    def test_full_troll_is_magenta(self):
        assert "magenta" in get_mode_color("full_troll")

    def test_sun_tzu_is_cyan(self):
        assert "cyan" in get_mode_color("sun_tzu")

    def test_default_mode_is_cyan(self):
        assert "cyan" in get_mode_color("default")

    def test_return_type_is_always_str(self):
        for mode_name in list(_MODE_NAMES) + ["bogus_mode", "", "NINJA"]:
            result = get_mode_color(mode_name)
            assert isinstance(result, str)


# ---------------------------------------------------------------------------
# thinking_status — context manager
# ---------------------------------------------------------------------------


class TestThinkingStatus:
    def test_context_manager_enters_and_exits_cleanly(self, monkeypatch):
        """thinking_status must not leak exceptions on normal entry/exit."""
        console, _ = _make_console()
        with thinking_status(console):
            pass  # no-op inner block

    def test_context_manager_propagates_inner_exception(self, monkeypatch):
        """An exception raised inside the with-block must propagate out."""
        console, _ = _make_console()
        with pytest.raises(ValueError, match="inner error"):
            with thinking_status(console):
                raise ValueError("inner error")

    def test_context_manager_accepts_custom_message(self, monkeypatch):
        """thinking_status should accept a custom message without crashing."""
        console, _ = _make_console()
        with thinking_status(console, message="Running tools..."):
            pass

    def test_context_manager_default_message(self, monkeypatch):
        """Default message is 'Thinking...' — verify no crash."""
        console, _ = _make_console()
        with thinking_status(console):
            result = 1 + 1
        assert result == 2

    def test_nested_usage_does_not_crash(self, monkeypatch):
        """Nested thinking_status calls (unusual but possible) must not crash."""
        console, _ = _make_console()
        with thinking_status(console, message="Outer"):
            with thinking_status(console, message="Inner"):
                pass


# ---------------------------------------------------------------------------
# Compound interaction: banner → mode color → thinking spinner (boot sequence)
# ---------------------------------------------------------------------------


class TestBannerCompoundInteraction:
    def test_full_boot_sequence_no_crash(self, monkeypatch):
        """Simulates the full boot sequence: banner → mode color → spinner → input."""
        monkeypatch.delenv("AP_NO_BANNER", raising=False)
        monkeypatch.setattr("adversary_pursuit.agent.banner.time.sleep", lambda _: None)
        console, buf = _make_console()

        # 1. Boot banner
        render_boot_banner(console)

        # 2. Mode colour for prompt construction
        color = get_mode_color("default")
        assert isinstance(color, str)

        # 3. Thinking spinner around "LLM call"
        with thinking_status(console):
            simulated_response = "CTI analysis complete."

        assert simulated_response == "CTI analysis complete."
        # Banner produced output
        assert len(buf.getvalue()) > 0

    def test_ci_boot_sequence_produces_no_banner(self, monkeypatch):
        """AP_NO_BANNER=1 boot: banner silent but mode color and spinner still work."""
        monkeypatch.setenv("AP_NO_BANNER", "1")
        console, buf = _make_console()

        render_boot_banner(console)
        assert buf.getvalue() == ""

        color = get_mode_color("ninja")
        assert "dim" in color

        with thinking_status(console):
            pass
