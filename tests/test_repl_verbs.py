"""Tests for agent/repl_verbs.py — local verb parser and dispatcher.

Covers:
  P-1:  parse_repl_verb — zero-arg verbs
  P-2:  parse_repl_verb — use <ioc> (domain / IP / hash / email / URL)
  P-3:  parse_repl_verb — use gibberish → None (routes to LLM)
  P-4:  parse_repl_verb — mode <name> (known and unknown)
  P-5:  parse_repl_verb — extra tokens → None (routes to LLM)
  D-1:  dispatch_repl_verb quit → raises _FarewellExit (SystemExit subclass)
  D-2:  dispatch_repl_verb clear → calls scrollback_clear callable
  D-3:  dispatch_repl_verb use → publishes TargetChanged, calls record_pivot
  D-4:  dispatch_repl_verb mode → switches active mode via mode_mgr
  D-5:  dispatch_repl_verb output comes from pick() (PHRASES), not hardcoded strings

Production sequence:
  user types text
  → TuiApplication._on_input_accepted
  → runner.handle_input(text, status_bar=live_pane)
  → parse_repl_verb(text) → ReplVerb or None
  → dispatch_repl_verb(verb, ctx, mode_mgr, workspace_mgr, …) → str
  → TUI emits to scrollback

@decision DEC-TEST-REPL-VERBS-001
@title Tests exercise the parse→dispatch contract via real parsers + mocked boundaries
@status accepted
@rationale parse_repl_verb and dispatch_repl_verb are pure Python with two genuine
           external boundaries: the phrase cache (covered separately by
           test_phrases_repl_verbs.py) and EventBus/workspace_mgr (mocked here to
           isolate routing from DB/TUI deps). @mock-exempt annotations mark each mock.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from adversary_pursuit.agent.repl_verbs import (
    ReplVerb,
    _FarewellExit,
    dispatch_repl_verb,
    parse_repl_verb,
)
from adversary_pursuit.gamification.modes import DEFAULT_MODES

# ---------------------------------------------------------------------------
# P-1: zero-argument verbs
# ---------------------------------------------------------------------------


class TestParseZeroArgVerbs:
    """Zero-arg verbs: help, ?, status, clear, quit, exit, q."""

    @pytest.mark.parametrize("text", ["help", "HELP", "Help", " help "])
    def test_parse_help(self, text: str):
        verb = parse_repl_verb(text)
        assert verb is not None
        assert verb.name == "help"
        assert verb.args == ()

    def test_parse_question_mark(self):
        """'?' is normalised to 'help'."""
        verb = parse_repl_verb("?")
        assert verb is not None
        assert verb.name == "help"

    def test_parse_status(self):
        verb = parse_repl_verb("status")
        assert verb is not None
        assert verb.name == "status"
        assert verb.args == ()

    def test_parse_clear(self):
        verb = parse_repl_verb("clear")
        assert verb is not None
        assert verb.name == "clear"

    @pytest.mark.parametrize("text", ["quit", "exit", "q"])
    def test_parse_quit_verbs(self, text: str):
        verb = parse_repl_verb(text)
        assert verb is not None
        assert verb.name == text

    def test_parse_empty_returns_none(self):
        assert parse_repl_verb("") is None
        assert parse_repl_verb("   ") is None

    def test_parse_zero_arg_with_trailing_tokens_returns_none(self):
        """'help me please' has trailing tokens → routes to LLM."""
        assert parse_repl_verb("help me please") is None
        assert parse_repl_verb("status now") is None
        assert parse_repl_verb("clear screen") is None


# ---------------------------------------------------------------------------
# P-2: use <ioc> — IOC shapes that should match
# ---------------------------------------------------------------------------


class TestParseUseIoc:
    """'use <ioc>' — matches only when ioc looks like a real IOC."""

    def test_parse_use_domain_matches(self):
        verb = parse_repl_verb("use suspicious.example.com")
        assert verb is not None
        assert verb.name == "use"
        assert verb.args == ("suspicious.example.com",)

    def test_parse_use_ip_matches(self):
        verb = parse_repl_verb("use 8.8.8.8")
        assert verb is not None
        assert verb.name == "use"
        assert verb.args == ("8.8.8.8",)

    def test_parse_use_hash_matches_md5(self):
        md5 = "d41d8cd98f00b204e9800998ecf8427e"
        verb = parse_repl_verb(f"use {md5}")
        assert verb is not None
        assert verb.name == "use"
        assert verb.args == (md5,)

    def test_parse_use_hash_matches_sha256(self):
        sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        verb = parse_repl_verb(f"use {sha256}")
        assert verb is not None
        assert verb.name == "use"
        assert verb.args == (sha256,)

    def test_parse_use_email_matches(self):
        verb = parse_repl_verb("use bad@evil.example")
        assert verb is not None
        assert verb.name == "use"
        assert verb.args == ("bad@evil.example",)

    def test_parse_use_url_matches(self):
        verb = parse_repl_verb("use http://evil.example/payload")
        assert verb is not None
        assert verb.name == "use"
        assert verb.args == ("http://evil.example/payload",)


# ---------------------------------------------------------------------------
# P-3: use <gibberish> → None (route to LLM)
# ---------------------------------------------------------------------------


class TestParseUseGibberish:
    """'use' with a token that is NOT an IOC shape returns None."""

    def test_parse_use_plain_word_returns_none(self):
        """'use notarealhost' — no TLD, no valid IOC shape → LLM."""
        assert parse_repl_verb("use notarealhost") is None

    def test_parse_use_multi_token_returns_none(self):
        """'use foo com bar' — three tokens after 'use' → None (LLM)."""
        assert parse_repl_verb("use foo com bar") is None

    def test_parse_use_alone_returns_none(self):
        """'use' with no argument → None (routes to LLM)."""
        assert parse_repl_verb("use") is None


# ---------------------------------------------------------------------------
# P-4: mode <name>
# ---------------------------------------------------------------------------


class TestParseMode:
    """'mode <name>' is always a local verb; dispatch handles unknown names."""

    def test_parse_mode_known_matches(self):
        verb = parse_repl_verb("mode ninja")
        assert verb is not None
        assert verb.name == "mode"
        assert verb.args == ("ninja",)

    def test_parse_mode_unknown_still_matches(self):
        """Even unknown mode names are dispatched locally (character-voiced error)."""
        verb = parse_repl_verb("mode xyzzy")
        assert verb is not None
        assert verb.name == "mode"
        assert verb.args == ("xyzzy",)

    @pytest.mark.parametrize("text", ["mode", "mode list", "MODE LIST"])
    def test_parse_mode_catalogue_matches(self, text: str):
        """Both documented catalogue forms use one deterministic local verb."""
        assert parse_repl_verb(text) == ReplVerb(name="mode_list", args=())

    def test_parse_mode_multi_token_returns_none(self):
        """'mode ninja list' — two arg tokens → None (routes to LLM)."""
        assert parse_repl_verb("mode ninja list") is None


# ---------------------------------------------------------------------------
# D-1: dispatch quit → raises _FarewellExit
# ---------------------------------------------------------------------------


class TestDispatchQuit:
    """quit / exit / q dispatch raises _FarewellExit (a SystemExit subclass)."""

    @pytest.mark.parametrize("verb_name", ["quit", "exit", "q"])
    def test_dispatch_quit_raises_farewell_exit(self, verb_name: str):
        verb = ReplVerb(name=verb_name, args=())
        with pytest.raises(_FarewellExit) as exc_info:
            dispatch_repl_verb(verb, ctx=None, mode_mgr=None, workspace_mgr=None)
        # _FarewellExit is a SystemExit subclass
        assert isinstance(exc_info.value, SystemExit)
        # carries a non-empty farewell phrase from pick()
        assert isinstance(exc_info.value.phrase, str)
        assert len(exc_info.value.phrase) > 0

    def test_farewell_exit_is_system_exit_subclass(self):
        """_FarewellExit must be catchable as SystemExit by the TUI loop."""
        verb = ReplVerb(name="quit", args=())
        with pytest.raises(SystemExit):
            dispatch_repl_verb(verb, ctx=None, mode_mgr=None, workspace_mgr=None)


# ---------------------------------------------------------------------------
# D-2: dispatch clear → calls scrollback_clear callable
# ---------------------------------------------------------------------------


class TestDispatchClear:
    """clear verb invokes the scrollback_clear callable exactly once."""

    def test_dispatch_clear_calls_scrollback_clear(self):
        clear_fn = MagicMock()  # @mock-exempt: callable provided by TUI caller
        verb = ReplVerb(name="clear", args=())
        result = dispatch_repl_verb(
            verb,
            ctx=None,
            mode_mgr=None,
            workspace_mgr=None,
            scrollback_clear=clear_fn,
        )
        clear_fn.assert_called_once()
        # clear returns empty string
        assert result == ""

    def test_dispatch_clear_without_callable_is_noop(self):
        """When scrollback_clear is None, clear must not raise."""
        verb = ReplVerb(name="clear", args=())
        result = dispatch_repl_verb(
            verb,
            ctx=None,
            mode_mgr=None,
            workspace_mgr=None,
            scrollback_clear=None,
        )
        assert result == ""


# ---------------------------------------------------------------------------
# D-3: dispatch use → publishes TargetChanged, calls record_pivot
# ---------------------------------------------------------------------------


class TestDispatchUse:
    """'use <ioc>' publishes TargetChanged and calls workspace_mgr.record_pivot."""

    def _make_workspace_mgr(self):
        """Minimal workspace_mgr duck-type stub."""
        mgr = MagicMock()  # @mock-exempt: WorkspaceManager (SQLite DB boundary)
        mgr.active = "default"
        return mgr

    def test_dispatch_use_publishes_target_changed_event(self):
        verb = ReplVerb(name="use", args=("8.8.8.8",))
        event_bus = MagicMock()  # @mock-exempt: EventBus (TUI event system boundary)
        workspace_mgr = self._make_workspace_mgr()

        dispatch_repl_verb(
            verb,
            ctx=None,
            mode_mgr=None,
            workspace_mgr=workspace_mgr,
            event_bus=event_bus,
        )

        # EventBus.publish must have been called with a TargetChanged event
        assert event_bus.publish.called
        published_event = event_bus.publish.call_args[0][0]
        assert hasattr(published_event, "target")
        assert published_event.target == "8.8.8.8"
        assert published_event.target_type == "ipv4-addr"

    def test_dispatch_use_calls_record_pivot(self):
        verb = ReplVerb(name="use", args=("evil.example.com",))
        workspace_mgr = self._make_workspace_mgr()

        dispatch_repl_verb(
            verb,
            ctx=None,
            mode_mgr=None,
            workspace_mgr=workspace_mgr,
        )

        workspace_mgr.record_pivot.assert_called_once_with("evil.example.com")

    def test_dispatch_use_returns_non_empty_string(self):
        verb = ReplVerb(name="use", args=("evil.example.com",))
        workspace_mgr = self._make_workspace_mgr()

        result = dispatch_repl_verb(
            verb,
            ctx=None,
            mode_mgr=None,
            workspace_mgr=workspace_mgr,
        )

        assert isinstance(result, str)
        assert len(result) > 0

    def test_dispatch_use_without_event_bus_does_not_crash(self):
        """When event_bus is None, use verb must not crash."""
        verb = ReplVerb(name="use", args=("evil.example.com",))
        workspace_mgr = self._make_workspace_mgr()

        result = dispatch_repl_verb(
            verb,
            ctx=None,
            mode_mgr=None,
            workspace_mgr=workspace_mgr,
            event_bus=None,
        )
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# D-4: dispatch mode → switches active mode
# ---------------------------------------------------------------------------


class TestDispatchMode:
    """mode <name> switches mode via mode_mgr for known names; character-voiced error for unknown."""

    def _make_mode_mgr(self, active_name: str = "default"):
        from adversary_pursuit.gamification.modes import ModeManager

        mgr = ModeManager()
        if active_name != "default":
            mgr.switch(active_name)
        return mgr

    def test_dispatch_mode_switches_active_mode(self):
        mgr = self._make_mode_mgr("default")
        verb = ReplVerb(name="mode", args=("ninja",))

        result = dispatch_repl_verb(verb, ctx=None, mode_mgr=mgr, workspace_mgr=None)

        assert mgr.active.name == "ninja"
        assert isinstance(result, str)
        assert len(result) > 0
        assert result.startswith("Mode switched: ninja\n")

    @pytest.mark.parametrize("mode_name", sorted(DEFAULT_MODES))
    def test_dispatch_mode_acknowledges_exact_selected_mode(self, mode_name: str):
        mgr = self._make_mode_mgr("default")
        result = dispatch_repl_verb(
            ReplVerb(name="mode", args=(mode_name,)),
            ctx=None,
            mode_mgr=mgr,
            workspace_mgr=None,
        )
        assert result.splitlines()[0] == f"Mode switched: {mode_name}"
        assert mgr.active.name == mode_name

    def test_dispatch_mode_list_is_stable_and_marks_active(self):
        mgr = self._make_mode_mgr("trinity")
        verb = ReplVerb(name="mode_list", args=())
        first = dispatch_repl_verb(verb, ctx=None, mode_mgr=mgr, workspace_mgr=None)
        second = dispatch_repl_verb(verb, ctx=None, mode_mgr=mgr, workspace_mgr=None)
        assert first == second
        assert first.startswith("Character modes (* active)\n")
        assert "* trinity" in first

    def test_dispatch_unknown_mode_returns_voiced_error(self):
        mgr = self._make_mode_mgr("default")
        verb = ReplVerb(name="mode", args=("xyzzy",))

        result = dispatch_repl_verb(verb, ctx=None, mode_mgr=mgr, workspace_mgr=None)

        # Mode must NOT have switched
        assert mgr.active.name == "default"
        # Result must mention the unknown mode name
        assert "xyzzy" in result
        assert isinstance(result, str)

    def test_dispatch_mode_without_mode_mgr_returns_unknown_voiced_error(self):
        """When mode_mgr is None, unknown mode returns voiced fallback without crash."""
        verb = ReplVerb(name="mode", args=("xyzzy",))
        result = dispatch_repl_verb(verb, ctx=None, mode_mgr=None, workspace_mgr=None)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# D-5: narrative dispatch output comes from PHRASES via pick()
# ---------------------------------------------------------------------------


class TestDispatchUsesPickForOutput:
    """Narrative dispatch output comes from PHRASES via pick().

    Mode control output is deliberately structural and deterministic.
    """

    def test_dispatch_help_uses_pick(self):
        verb = ReplVerb(name="help", args=())
        with patch(
            "adversary_pursuit.agent.repl_verbs.pick", return_value="[help text]"
        ) as mock_pick:
            result = dispatch_repl_verb(verb, ctx=None, mode_mgr=None, workspace_mgr=None)
        mock_pick.assert_called_once_with("default", "help:tui_overview")
        assert result == "[help text]"

    def test_dispatch_status_uses_pick(self):
        verb = ReplVerb(name="status", args=())
        with patch("adversary_pursuit.agent.repl_verbs.pick", return_value="[status]") as mock_pick:
            result = dispatch_repl_verb(verb, ctx=None, mode_mgr=None, workspace_mgr=None)
        # pick is called for the status_intro line
        mock_pick.assert_called_with("default", "status_intro")
        assert "[status]" in result

    def test_dispatch_farewell_uses_pick(self):
        verb = ReplVerb(name="quit", args=())
        with patch("adversary_pursuit.agent.repl_verbs.pick", return_value="[bye]"):
            with pytest.raises(_FarewellExit) as exc_info:
                dispatch_repl_verb(verb, ctx=None, mode_mgr=None, workspace_mgr=None)
        assert exc_info.value.phrase == "[bye]"

    def test_dispatch_use_uses_pick(self):
        verb = ReplVerb(name="use", args=("8.8.8.8",))
        workspace_mgr = MagicMock()  # @mock-exempt: WorkspaceManager boundary
        workspace_mgr.active = "default"
        with patch(
            "adversary_pursuit.agent.repl_verbs.pick",
            return_value="On it — {target}",
        ) as mock_pick:
            result = dispatch_repl_verb(
                verb,
                ctx=None,
                mode_mgr=None,
                workspace_mgr=workspace_mgr,
            )
        mock_pick.assert_called_with("default", "target_set:acknowledged")
        assert "8.8.8.8" in result

    def test_dispatch_mode_switch_is_deterministic_not_random_phrase(self):
        from adversary_pursuit.gamification.modes import ModeManager

        mgr = ModeManager()
        verb = ReplVerb(name="mode", args=("ninja",))
        with patch("adversary_pursuit.agent.repl_verbs.pick") as mock_pick:
            result = dispatch_repl_verb(verb, ctx=None, mode_mgr=mgr, workspace_mgr=None)
        mock_pick.assert_not_called()
        assert result.startswith("Mode switched: ninja\n")

    def test_dispatch_unknown_mode_is_deterministic_not_random_phrase(self):
        verb = ReplVerb(name="mode", args=("xyzzy",))
        with patch("adversary_pursuit.agent.repl_verbs.pick") as mock_pick:
            result = dispatch_repl_verb(verb, ctx=None, mode_mgr=None, workspace_mgr=None)
        mock_pick.assert_not_called()
        assert result.startswith("Unknown mode: xyzzy\nAvailable modes:")


# ---------------------------------------------------------------------------
# Compound: parse → dispatch round-trip
# ---------------------------------------------------------------------------


class TestParseDispatchRoundTrip:
    """End-to-end: parse text, then dispatch the resulting verb."""

    def test_help_round_trip(self):
        verb = parse_repl_verb("help")
        assert verb is not None
        result = dispatch_repl_verb(verb, ctx=None, mode_mgr=None, workspace_mgr=None)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_use_domain_round_trip_publishes_event(self):
        verb = parse_repl_verb("use evil.example.com")
        assert verb is not None
        bus = MagicMock()  # @mock-exempt: EventBus boundary
        ws = MagicMock()  # @mock-exempt: WorkspaceManager boundary
        ws.active = "default"
        result = dispatch_repl_verb(
            verb,
            ctx=None,
            mode_mgr=None,
            workspace_mgr=ws,
            event_bus=bus,
        )
        assert isinstance(result, str)
        assert bus.publish.called

    def test_mode_ninja_round_trip_switches(self):
        from adversary_pursuit.gamification.modes import ModeManager

        verb = parse_repl_verb("mode ninja")
        assert verb is not None
        mgr = ModeManager()
        dispatch_repl_verb(verb, ctx=None, mode_mgr=mgr, workspace_mgr=None)
        assert mgr.active.name == "ninja"
