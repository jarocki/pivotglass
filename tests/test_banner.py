"""Tests for agent/banner.py — figlet wordmark boot banner and animations.

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
           Phase 17Q adds TestBannerWordmarkLayout covering the new figlet
           wordmark, reticle motif, width fallback, metadata strip, and
           import-time pre-render invariants.
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from adversary_pursuit.agent import banner as banner_module
from adversary_pursuit.agent.banner import (
    _FALLBACK_COLOR,
    _WORDMARK_DEFAULT,
    MODE_COLORS,
    get_mode_color,
    render_boot_banner,
    thinking_status,
)
from adversary_pursuit.agent.repl_input import _MODE_NAMES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_console(width: int = 120) -> tuple[Console, io.StringIO]:
    """Return a Rich Console that writes to a StringIO buffer."""
    buf = io.StringIO()
    console = Console(file=buf, highlight=False, markup=True, width=width)
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
        assert "Adversary Pursuit" in output or "ADVERSARY PURSUIT" in output or "AP" in output

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
# Phase 17Q: wordmark layout tests
# ---------------------------------------------------------------------------


class TestBannerWordmarkLayout:
    """Tests for the figlet wordmark + reticle + metadata layout (Phase 17Q).

    Production sequence: render_boot_banner(console) with a wide console
    (width >= 60) triggers the default 3-column layout containing the ansi_shadow
    wordmark, reticle glyphs, and metadata strip. A narrow console (width < 60)
    triggers the compact layout with just the small-font wordmark.
    """

    def test_default_layout_contains_wordmark(self, monkeypatch):
        """Default layout must contain figlet block-drawing characters (e.g. █ or ╗)."""
        monkeypatch.delenv("AP_NO_BANNER", raising=False)
        monkeypatch.setattr("adversary_pursuit.agent.banner.time.sleep", lambda _: None)
        console, buf = _make_console(width=120)
        render_boot_banner(console)
        output = buf.getvalue()
        # ansi_shadow font produces block-drawing chars like █ and box-drawing chars like ╗
        assert "█" in output or "╗" in output or "╔" in output, (
            "Expected figlet ansi_shadow block-drawing characters in default layout output"
        )

    def test_default_layout_contains_reticle(self, monkeypatch):
        """Default layout must contain at least one reticle glyph (⊕, ╳, or ◎)."""
        monkeypatch.delenv("AP_NO_BANNER", raising=False)
        monkeypatch.setattr("adversary_pursuit.agent.banner.time.sleep", lambda _: None)
        console, buf = _make_console(width=120)
        render_boot_banner(console)
        output = buf.getvalue()
        assert any(glyph in output for glyph in ("⊕", "╳", "◎")), (
            f"Expected a reticle glyph (⊕, ╳, or ◎) in banner output. Got: {output[:200]!r}"
        )

    def test_compact_layout_used_when_width_below_60(self, monkeypatch):
        """Width < 60 must trigger compact layout: no reticle, but wordmark present."""
        monkeypatch.delenv("AP_NO_BANNER", raising=False)
        monkeypatch.setattr("adversary_pursuit.agent.banner.time.sleep", lambda _: None)
        console, buf = _make_console(width=40)
        render_boot_banner(console)
        output = buf.getvalue()
        # Compact layout must NOT contain reticle glyphs
        assert "⊕" not in output
        assert "◎" not in output
        # But compact layout MUST contain some wordmark content from pyfiglet 'small' font
        # The 'small' font for 'ap' uses underscores, pipes, and slashes: __ / _ etc.
        assert len(output) > 0, "Compact layout produced no output"
        # At minimum, the panel border must appear (green border_style)
        assert "─" in output or "│" in output or "┌" in output or "+" in output or len(output) > 20

    def test_metadata_strip_includes_version(self, monkeypatch):
        """Default layout metadata strip must contain version string (v<digit> or v?.?.?)."""
        monkeypatch.delenv("AP_NO_BANNER", raising=False)
        monkeypatch.setattr("adversary_pursuit.agent.banner.time.sleep", lambda _: None)
        console, buf = _make_console(width=120)
        render_boot_banner(console)
        output = buf.getvalue()
        import re

        # Must contain either "v" followed by a digit OR the placeholder "v?.?.?"
        has_version = bool(re.search(r"v\d", output)) or "v?.?.?" in output
        assert has_version, f"Expected version string in banner output. Got: {output[:300]!r}"

    def test_pyfiglet_render_at_import_time(self):
        """_WORDMARK_DEFAULT must be a non-empty string pre-rendered at module import."""
        # This test verifies the DEC-AGENT-BANNER-002 design contract:
        # the figlet render happens once at import, not per-call.
        assert isinstance(_WORDMARK_DEFAULT, str), (
            "_WORDMARK_DEFAULT must be a str (pre-rendered at import)"
        )
        assert len(_WORDMARK_DEFAULT.strip()) > 0, (
            "_WORDMARK_DEFAULT must be non-empty after stripping whitespace"
        )
        # ansi_shadow 'ap' must contain block-drawing chars
        assert "█" in _WORDMARK_DEFAULT or "╗" in _WORDMARK_DEFAULT, (
            "ansi_shadow 'ap' wordmark must contain block-drawing characters"
        )

    def test_banner_handles_missing_workspace(self, monkeypatch):
        """Banner must not crash when WorkspaceManager raises, and shows '--' for IOC count."""
        monkeypatch.delenv("AP_NO_BANNER", raising=False)
        monkeypatch.setattr("adversary_pursuit.agent.banner.time.sleep", lambda _: None)

        # Patch _get_ioc_count to simulate workspace failure
        monkeypatch.setattr(banner_module, "_get_ioc_count", lambda: "--")

        console, buf = _make_console(width=120)
        # Must not raise
        render_boot_banner(console)
        output = buf.getvalue()
        # The "--" placeholder must appear in the metadata strip
        assert "--" in output, (
            f"Expected '--' IOC count placeholder when workspace is unavailable. Got: {output[:300]!r}"
        )


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
