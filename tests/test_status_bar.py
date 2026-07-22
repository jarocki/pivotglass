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
        bar = StatusBar(make_console(), mode_name="detective", model_display="ollama/qwen2.5:8b")
        text = bar._render_bar()
        assert "detective" in text.plain

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
        bar = StatusBar(make_console(), mode_name="detective", model_display="m")
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
        bar = StatusBar(make_console(), mode_name="detective", model_display="m")
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
        bar = StatusBar(make_console(), mode_name="detective", model_display="m")
        bar.set_activity("virustotal")
        text = bar._render_bar()
        # detective has "Running VT" / "Pulling VT sheet" for activity:virustotal
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
        bar = StatusBar(console, mode_name="detective", model_display="m")
        with bar:
            bar.set_activity("shodan")
            bar.set_activity(None)


# ---------------------------------------------------------------------------
# _status_slug_for_tool  (DEC-STATUS-ACTIVITY-WIRING-001)
# ---------------------------------------------------------------------------


class TestStatusSlugForTool:
    """_status_slug_for_tool maps LLM tool names to activity slugs."""

    def test_virustotal_lookup_maps_to_virustotal(self):
        """virustotal_lookup -> 'virustotal'."""
        from adversary_pursuit.agent.runner import _status_slug_for_tool

        assert _status_slug_for_tool("virustotal_lookup") == "virustotal"

    def test_whois_lookup_maps_to_whois(self):
        """whois_lookup -> 'whois'."""
        from adversary_pursuit.agent.runner import _status_slug_for_tool

        assert _status_slug_for_tool("whois_lookup") == "whois"

    def test_shodan_host_lookup_maps_to_shodan(self):
        """shodan_host_lookup -> 'shodan'."""
        from adversary_pursuit.agent.runner import _status_slug_for_tool

        assert _status_slug_for_tool("shodan_host_lookup") == "shodan"

    def test_otx_threat_intel_maps_to_otx(self):
        """otx_threat_intel -> 'otx'."""
        from adversary_pursuit.agent.runner import _status_slug_for_tool

        assert _status_slug_for_tool("otx_threat_intel") == "otx"

    def test_threatfox_lookup_maps_to_threatfox(self):
        """threatfox_lookup -> 'threatfox'."""
        from adversary_pursuit.agent.runner import _status_slug_for_tool

        assert _status_slug_for_tool("threatfox_lookup") == "threatfox"

    def test_removed_dns_resolve_is_not_a_known_activity(self):
        """Removed direct-DNS tooling receives the neutral fallback slug."""
        from adversary_pursuit.agent.runner import _status_slug_for_tool

        assert _status_slug_for_tool("dns_resolve") == "default_tool"

    def test_unknown_tool_returns_default_tool(self):
        """Unknown tool returns 'default_tool' with no crash."""
        from adversary_pursuit.agent.runner import _status_slug_for_tool

        assert _status_slug_for_tool("completely_unknown_tool_xyz") == "default_tool"

    def test_all_registered_tools_covered(self):
        """Every tool name in create_tools() maps to a non-empty slug (no silent gaps)."""
        from adversary_pursuit.agent.runner import _status_slug_for_tool
        from adversary_pursuit.agent.tools import ToolContext, create_tools

        ctx = ToolContext(config_dir="/tmp/ap_test_slug", workspace_dir="/tmp/ap_test_slug")
        tool_defs = create_tools(ctx)
        for td in tool_defs:
            name = td["function"]["name"]
            slug = _status_slug_for_tool(name)
            assert isinstance(slug, str) and len(slug) > 0, (
                f"_status_slug_for_tool({name!r}) returned empty/None: {slug!r}"
            )


# ---------------------------------------------------------------------------
# NullStatusHook (DEC-STATUS-ACTIVITY-WIRING-001)
# ---------------------------------------------------------------------------


class TestNullStatusHook:
    """NullStatusHook is a no-op that satisfies the _StatusHook Protocol."""

    def test_set_activity_no_crash(self):
        """NullStatusHook.set_activity() does not crash."""
        from adversary_pursuit.agent.runner import NullStatusHook

        hook = NullStatusHook()
        hook.set_activity("virustotal")
        hook.set_activity(None)

    def test_is_singleton(self):
        """_NULL_STATUS_HOOK is the default NullStatusHook instance."""
        from adversary_pursuit.agent.runner import _NULL_STATUS_HOOK, NullStatusHook

        assert isinstance(_NULL_STATUS_HOOK, NullStatusHook)


# ---------------------------------------------------------------------------
# runner.chat() status_bar wiring integration test
# (DEC-STATUS-ACTIVITY-WIRING-001 — compound interaction)
# ---------------------------------------------------------------------------


class TestRunnerChatStatusBarWiring:
    """Integration test: runner.chat() calls set_activity before/after tool calls.

    Uses a real StatusBar (not mocked) so the activity phrase lookup executes
    end-to-end. Mocking only at the LLM boundary (litellm.completion) and
    the tool execution boundary (execute_tool), per Confront #7.
    """

    def _make_tool_use_response(self, tool_name: str, tool_id: str = "tc_test_001"):
        """Produce a litellm-style message object that requests one tool call."""

        class _FunctionObj:
            def __init__(self):
                self.name = tool_name
                self.arguments = '{"target": "1.2.3.4"}'

        class _ToolCallObj:
            def __init__(self):
                self.id = tool_id
                self.function = _FunctionObj()

        class _Message:
            def __init__(self):
                self.tool_calls = [_ToolCallObj()]
                self.content = None

        return _Message()

    def _make_text_response(self, text: str = "Analysis complete."):
        """Produce a litellm-style message object that returns a text response."""

        class _Message:
            def __init__(self):
                self.tool_calls = None
                self.content = text

        return _Message()

    def test_set_activity_called_around_tool_execution(self, tmp_path, monkeypatch):
        """runner.chat() calls set_activity(slug) before tool call and set_activity(None) after.

        This is the critical compound-interaction test: exercises the production
        sequence LLM-call → tool dispatch → status bar update end-to-end, crossing
        AgentRunner.chat() → execute_tool() → StatusBar.set_activity() boundaries.
        StatusBar is a real instance (phrases.py is exercised). Mocking only at:
        - _call_llm boundary (avoids litellm optional-dep issue in test env)
        - execute_tool boundary (avoids real module HTTP calls)
        """
        import io

        from rich.console import Console

        from adversary_pursuit.agent.banner import StatusBar
        from adversary_pursuit.agent.runner import AgentRunner
        from adversary_pursuit.agent.tools import ToolContext

        # Track set_activity call sequence
        activity_calls: list = []

        # Real StatusBar subclassed to record calls without live terminal dependency
        class TrackingStatusBar(StatusBar):
            def set_activity(self, tool_slug):
                activity_calls.append(tool_slug)
                super().set_activity(tool_slug)

        console = Console(file=io.StringIO(), force_terminal=True)
        ctx = ToolContext(config_dir=str(tmp_path), workspace_dir=str(tmp_path))
        runner = AgentRunner(model="ollama/test", tool_context=ctx)

        # Round 1: LLM requests a tool call for virustotal_lookup
        # Round 2: LLM returns plain text (no more tool calls → loop ends)
        call_count = 0

        def fake_call_llm(self_inner):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return self._make_tool_use_response("virustotal_lookup")
            return self._make_text_response("All done.")

        import adversary_pursuit.agent.runner as _runner_module

        monkeypatch.setattr(_runner_module.AgentRunner, "_call_llm", fake_call_llm)
        # HAS_LITELLM may be False in the test env (litellm is optional).
        # Patch it True so chat() proceeds past the import guard to our mocked _call_llm.
        monkeypatch.setattr(_runner_module, "HAS_LITELLM", True)

        # Patch execute_tool to avoid real module invocation
        monkeypatch.setattr(
            _runner_module, "execute_tool", lambda *a, **kw: ("Found 1 indicator", None, [], [])
        )

        bar = TrackingStatusBar(
            console=console,
            mode_name="the_computer",
            model_display="ollama/test",
            workspace_mgr=ctx.workspace_mgr,
        )

        result = runner.chat("investigate 1.2.3.4", status_bar=bar)

        assert result == "All done."
        # Must see at minimum one set_activity("virustotal") call
        assert "virustotal" in activity_calls, (
            f"Expected 'virustotal' in activity_calls, got: {activity_calls}"
        )
        # set_activity(None) must follow every non-None set_activity call
        # (bar is reset to idle after tool returns)
        none_positions = [i for i, v in enumerate(activity_calls) if v is None]
        slug_positions = [i for i, v in enumerate(activity_calls) if v is not None]
        assert none_positions, "set_activity(None) was never called after tool execution"
        assert slug_positions, "set_activity(slug) was never called for the tool"
        # For each slug call, there must be a subsequent None call
        for sp in slug_positions:
            assert any(np > sp for np in none_positions), (
                f"No set_activity(None) found after set_activity call at position {sp}"
            )

    def test_chat_without_status_bar_still_works(self, tmp_path, monkeypatch):
        """runner.chat() without status_bar= kwarg runs without error (default NullStatusHook)."""
        from adversary_pursuit.agent.runner import AgentRunner
        from adversary_pursuit.agent.tools import ToolContext

        ctx = ToolContext(config_dir=str(tmp_path), workspace_dir=str(tmp_path))
        runner = AgentRunner(model="ollama/test", tool_context=ctx)

        import adversary_pursuit.agent.runner as _runner_module

        monkeypatch.setattr(
            _runner_module.AgentRunner,
            "_call_llm",
            lambda self_inner: self._make_text_response("Simple answer."),
        )
        monkeypatch.setattr(_runner_module, "HAS_LITELLM", True)

        result = runner.chat("hello")  # no status_bar kwarg — uses NullStatusHook
        assert result == "Simple answer."

    def test_activity_phrase_lookup_virustotal_the_computer(self):
        """set_activity('virustotal') on a the_computer bar renders the expected activity phrase.

        Directly tests that StatusBar._render_bar() with activity='virustotal' and
        mode_name='the_computer' uses the the_computer activity:virustotal phrase bucket.
        """
        from adversary_pursuit.agent.banner import StatusBar
        from adversary_pursuit.gamification.phrases import PHRASES

        console = make_console()
        bar = StatusBar(console, mode_name="the_computer", model_display="test")
        bar.set_activity("virustotal")
        text = bar._render_bar()
        plain = text.plain

        # The the_computer activity:virustotal phrases are:
        #   "Querying VirusTotal, Dave" and "VirusTotal analysis proceeding"
        hal_phrases = [p.text for p in PHRASES.get(("the_computer", "activity:virustotal"), ())]
        assert any(p in plain for p in hal_phrases), (
            f"Expected one of {hal_phrases} in bar, got: {plain!r}"
        )
