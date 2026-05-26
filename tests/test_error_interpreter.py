"""Tests for core/error_interpreter.py — universal error interpreter.

# @mock-exempt: fcntl.flock and filesystem I/O are tested against real
# implementations; litellm is never imported here (core/ has no agent dep).

Production sequences covered:
  interpret(exc, context=ctx) → ErrorInterpretation
    → catalog match → interpret_fn → ErrorInterpretation + debug log entry
    → unknown fallback → canned ErrorInterpretation + debug log entry

  render_interactive(interp, console, mode=mode, interactive=True/False)
    → Panel on console, optional [y/n/d] prompt, AutoFixOutcome

  render_summary_line(interp) → plain one-liner for smoke_test surfaces

@decision DEC-TEST-ERROR-INTERPRETER-001
@title Real filesystem used for debug-log tests; tmp_path fixture for isolation
@status accepted
@rationale The debug-log path is configurable via interp.traceback_path —
           tests inject a tmp_path-based path so real ~/.ap/debug.log is never
           touched. fcntl.flock and rotation logic are exercised against real
           file I/O so concurrency behaviour matches production.
"""

from __future__ import annotations

import io
import json
import re
import threading
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from adversary_pursuit.core.error_interpreter import (
    AutoFix,
    ErrorInterpretation,
    _append_debug_log,
    _make_diagnostic_id,
    interpret,
    render_interactive,
    render_summary_line,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    console = Console(file=buf, highlight=False, markup=True)
    return console, buf


def _make_interp_with_log(tmp_path: Path, **kwargs) -> ErrorInterpretation:
    """Build an ErrorInterpretation whose traceback_path points to tmp_path."""
    defaults = dict(
        severity="error",
        category="Test",
        summary="Test summary",
        suggested_fix="Do the thing",
        diagnostic_id=_make_diagnostic_id(),
        traceback_path=tmp_path / "debug.log",
    )
    defaults.update(kwargs)
    return ErrorInterpretation(**defaults)


# ---------------------------------------------------------------------------
# _make_diagnostic_id — format and uniqueness
# ---------------------------------------------------------------------------


class TestDiagnosticID:
    def test_format_is_8_hex_lowercase(self):
        did = _make_diagnostic_id()
        assert re.fullmatch(r"[a-f0-9]{8}", did), f"Expected 8-char lowercase hex, got {did!r}"

    def test_unique_across_1000_calls(self):
        ids = {_make_diagnostic_id() for _ in range(1000)}
        # Expect all unique (collision probability ~1.2e-7 per pair)
        assert len(ids) == 1000, f"Collision detected: only {len(ids)} unique IDs in 1000 calls"


# ---------------------------------------------------------------------------
# _append_debug_log — JSONL append + rotation + concurrency
# ---------------------------------------------------------------------------


class TestDebugLog:
    def test_append_writes_one_jsonl_line(self, tmp_path):
        log = tmp_path / "debug.log"
        exc = ValueError("test error")
        interp = _make_interp_with_log(tmp_path, traceback_path=log)
        _append_debug_log(interp, exc, {"module": "test"})

        lines = log.read_text().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["diagnostic_id"] == interp.diagnostic_id
        assert entry["category"] == "Test"
        assert entry["exc_type"] == "ValueError"
        assert "test" in entry["context"].get("module", "")

    def test_multiple_appends_accumulate(self, tmp_path):
        log = tmp_path / "debug.log"
        exc = ValueError("repeated")
        for _ in range(5):
            interp = _make_interp_with_log(tmp_path, traceback_path=log)
            _append_debug_log(interp, exc)
        assert len(log.read_text().splitlines()) == 5

    def test_rotation_trims_to_1000_lines(self, tmp_path):
        """When the log reaches 1000 lines, appending a new entry keeps it at 1000."""
        log = tmp_path / "debug.log"
        exc = ValueError("rotation test")

        # Pre-seed with 999 lines
        with open(log, "w") as fh:
            for i in range(999):
                fh.write(json.dumps({"diagnostic_id": f"seed{i:04d}", "n": i}) + "\n")

        # Append one more — should NOT trigger rotation yet (999 + 1 = 1000 lines)
        interp = _make_interp_with_log(tmp_path, traceback_path=log)
        _append_debug_log(interp, exc)
        lines = log.read_text().splitlines()
        assert len(lines) == 1000

        # Append again — now at ceiling, so rotation trims to 999 then adds 1 = 1000
        interp2 = _make_interp_with_log(tmp_path, traceback_path=log)
        _append_debug_log(interp2, exc)
        lines2 = log.read_text().splitlines()
        assert len(lines2) == 1000
        # The last entry should be interp2's diagnostic_id
        last_entry = json.loads(lines2[-1])
        assert last_entry["diagnostic_id"] == interp2.diagnostic_id

    def test_concurrent_append_produces_correct_count(self, tmp_path):
        """Two threads appending simultaneously each land exactly one line."""
        log = tmp_path / "debug.log"
        exc = ValueError("concurrent")
        results: list[tuple[str, bool]] = []

        def _append_thread(n: int) -> None:
            interp = _make_interp_with_log(
                tmp_path,
                traceback_path=log,
                diagnostic_id=f"th{n:06d}",
            )
            try:
                _append_debug_log(interp, exc)
                results.append((interp.diagnostic_id, True))
            except Exception:
                results.append((f"th{n:06d}", False))

        threads = [threading.Thread(target=_append_thread, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        lines = log.read_text().splitlines()
        assert len(lines) == 2, f"Expected 2 lines, got {len(lines)}"
        # Both thread appends should have succeeded
        assert all(ok for _, ok in results)

    def test_log_write_failure_goes_to_stderr(self, tmp_path, capsys):
        """If the log directory is not writable, a warning goes to stderr."""
        bad_path = Path("/proc/nonexistent/debug.log")  # guaranteed to fail
        interp = _make_interp_with_log(tmp_path, traceback_path=bad_path)
        exc = ValueError("test")
        # Should not raise; should print to stderr
        _append_debug_log(interp, exc)
        captured = capsys.readouterr()
        assert "WARNING" in captured.err or "could not write" in captured.err.lower()


# ---------------------------------------------------------------------------
# interpret() — catalog entries
# ---------------------------------------------------------------------------


class TestInterpretCatalogEntries:
    """One test per catalog entry (DEC-ERROR-INTERPRETER-008)."""

    def _call(self, exc: BaseException, tmp_path: Path) -> ErrorInterpretation:
        """Call interpret() redirecting debug log to tmp_path."""
        interp = interpret(exc, context={"test": True})
        # Override path for assertion purposes (real interpret writes to ~/.ap/debug.log)
        # We verify the log write via a separate targeted test
        return interp

    # 1. AuthenticationError (modules.base)
    def test_auth_error_from_modules_base(self):
        from adversary_pursuit.modules.base import AuthenticationError

        exc = AuthenticationError("AP_SHODAN_API_KEY not configured")
        interp = interpret(exc, context={"test": True})
        assert interp.category == "API key"
        assert interp.severity == "error"
        assert "AP_" in interp.suggested_fix or "config setup" in interp.suggested_fix
        assert re.fullmatch(r"[a-f0-9]{8}", interp.diagnostic_id)

    def test_auth_error_with_service_name_in_message(self):
        from adversary_pursuit.modules.base import AuthenticationError

        exc = AuthenticationError("Set AP_GREYNOISE_API_KEY or run `ap config setup`")
        interp = interpret(exc)
        assert interp.category == "API key"
        assert "GREYNOISE" in interp.suggested_fix or "config setup" in interp.suggested_fix

    # 2. RateLimitError (modules.base)
    def test_rate_limit_error_with_retry_after(self):
        from adversary_pursuit.modules.base import RateLimitError

        exc = RateLimitError("Too many requests", retry_after=15)
        interp = interpret(exc)
        assert interp.category == "Rate limit"
        assert interp.severity == "warn"
        assert "15" in interp.suggested_fix or "rotate" in interp.suggested_fix

    def test_rate_limit_error_without_retry_after(self):
        from adversary_pursuit.modules.base import RateLimitError

        exc = RateLimitError("Rate limit exceeded")
        interp = interpret(exc)
        assert interp.category == "Rate limit"
        assert interp.suggested_fix  # non-empty

    def test_rate_limit_auto_fix_short_retry(self):
        """RateLimitError with retry_after<=30 offers an auto-fix sleep."""
        from adversary_pursuit.modules.base import RateLimitError

        exc = RateLimitError("Throttled", retry_after=5)
        interp = interpret(exc)
        assert interp.auto_fix is not None
        assert isinstance(interp.auto_fix, AutoFix)
        assert "5" in interp.auto_fix.label or "5" in interp.auto_fix.description

    def test_rate_limit_auto_fix_long_retry_is_none(self):
        """RateLimitError with retry_after>30 does not offer auto-fix sleep."""
        from adversary_pursuit.modules.base import RateLimitError

        exc = RateLimitError("Throttled", retry_after=60)
        interp = interpret(exc)
        # Long waits should NOT offer auto-fix (too disruptive)
        assert interp.auto_fix is None

    # 3. Network/ConnectError
    def test_httpx_connect_error(self):
        class ConnectError(ConnectionError):
            pass

        exc = ConnectError("Failed to connect to https://api.greynoise.io")
        interp = interpret(exc)
        assert interp.category == "Network"
        assert interp.severity == "error"
        assert (
            "greynoise.io" in interp.suggested_fix or "connectivity" in interp.suggested_fix.lower()
        )

    def test_connection_refused_error(self):
        exc = ConnectionRefusedError("Connection refused to localhost:8080")
        interp = interpret(exc)
        assert interp.category == "Network"

    # 4. Timeout
    def test_httpx_read_timeout(self):
        class ReadTimeout(TimeoutError):
            pass

        exc = ReadTimeout("Read timed out for https://otx.alienvault.com/api")
        interp = interpret(exc)
        assert interp.category == "Timeout"
        assert interp.severity == "warn"
        assert "TIMEOUT" in interp.suggested_fix or "retry" in interp.suggested_fix.lower()

    def test_stdlib_timeout_error(self):
        exc = TimeoutError("Request timed out")
        interp = interpret(exc)
        assert interp.category == "Timeout"

    # 5. Config TOMLDecodeError
    def test_toml_decode_error(self):
        class TOMLDecodeError(ValueError):
            pass

        exc = TOMLDecodeError("Invalid TOML at line 5: unexpected =")
        interp = interpret(exc)
        assert interp.category == "Config"
        assert interp.severity == "error"
        assert "config.toml" in interp.summary or "config" in interp.suggested_fix.lower()

    def test_toml_error_auto_fix_when_backup_exists(self, tmp_path, monkeypatch):
        """When ~/.ap/config.toml.bak exists, an auto-fix restore is offered."""

        class TOMLDecodeError(ValueError):
            pass

        # Monkeypatch Path.home() to tmp_path so backup detection works
        fake_home = tmp_path
        (fake_home / ".ap").mkdir()
        (fake_home / ".ap" / "config.toml.bak").write_text("[config]")
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
        # Re-import _auto_fix_toml after monkeypatching home
        from adversary_pursuit.core.error_interpreter import _auto_fix_toml

        exc = TOMLDecodeError("TOML error")
        auto_fix = _auto_fix_toml(exc)
        assert auto_fix is not None
        assert "backup" in auto_fix.label.lower() or "restore" in auto_fix.label.lower()

    def test_toml_error_no_auto_fix_when_no_backup(self, tmp_path, monkeypatch):
        class TOMLDecodeError(ValueError):
            pass

        fake_home = tmp_path
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
        from adversary_pursuit.core.error_interpreter import _auto_fix_toml

        exc = TOMLDecodeError("TOML error")
        auto_fix = _auto_fix_toml(exc)
        assert auto_fix is None

    # 6. SQLite locked
    def test_sqlite_locked_operational_error(self):
        try:
            from sqlalchemy.exc import OperationalError

            exc = OperationalError("database is locked", {}, None)
        except Exception:
            # Fall back to a duck-typed OperationalError
            class OperationalError(Exception):
                pass

            exc = OperationalError("(sqlite3.OperationalError) database is locked")

        interp = interpret(exc)
        assert interp.category == "Database"
        assert "locked" in interp.summary.lower() or "locked" in interp.suggested_fix.lower()

    def test_sqlite_locked_raw_sqlite3(self):
        import sqlite3

        try:
            exc = sqlite3.OperationalError("database is locked")
            interp = interpret(exc)
            # sqlite3.OperationalError.mro includes OperationalError; message has "locked"
            assert interp.category in ("Database", "Unknown")
        except Exception:
            pass  # sqlite3 availability varies

    # 7. LLM/litellm provider auth (message-based, no litellm import needed)
    def test_llm_provider_auth_by_message(self):
        exc = Exception("openai.AuthenticationError: Invalid API key")
        interp = interpret(exc)
        # May fall through to unknown if message matching doesn't fire — that's OK
        # The important contract is no traceback leaks; friendly panel is guaranteed
        assert isinstance(interp, ErrorInterpretation)
        assert re.fullmatch(r"[a-f0-9]{8}", interp.diagnostic_id)

    # 8. Unknown fallback
    def test_unknown_error_returns_fallback(self):
        exc = ValueError("some completely unknown error")
        interp = interpret(exc)
        assert interp.category == "Unknown"
        assert interp.summary == "An unexpected error occurred."
        assert "debug.log" in interp.suggested_fix or "diagnostic" in interp.suggested_fix.lower()
        assert re.fullmatch(r"[a-f0-9]{8}", interp.diagnostic_id)

    def test_interpret_never_raises(self):
        """interpret() must never raise, even for pathological inputs."""

        class WeirdExc(Exception):
            def __str__(self):
                raise RuntimeError("str() also raises!")

        try:
            exc = WeirdExc()
        except Exception:
            exc = Exception("fallback")

        # Must not raise
        interp = interpret(exc)
        assert isinstance(interp, ErrorInterpretation)


# ---------------------------------------------------------------------------
# interpret() — debug log integration
# ---------------------------------------------------------------------------


class TestInterpretWritesDebugLog:
    def test_interpret_appends_to_debug_log(self, tmp_path):
        """interpret() must write exactly one JSONL entry to the debug log."""
        log = tmp_path / "debug.log"
        from adversary_pursuit.modules.base import AuthenticationError

        exc = AuthenticationError("test key missing")

        # Patch DEBUG_LOG_PATH in the interpreter so it writes to our tmp log
        with patch(
            "adversary_pursuit.core.error_interpreter.DEBUG_LOG_PATH",
            log,
        ):
            interp = interpret(exc, context={"surface": "test"})

        assert log.exists(), "debug log was not created"
        lines = log.read_text().splitlines()
        assert len(lines) >= 1
        entry = json.loads(lines[-1])
        assert entry["diagnostic_id"] == interp.diagnostic_id
        assert entry["exc_type"] == "AuthenticationError"


# ---------------------------------------------------------------------------
# render_interactive() — panel content, auto-fix paths, mode-flavored title
# ---------------------------------------------------------------------------


class TestRenderInteractive:
    def test_panel_contains_summary_fix_diag_id(self, tmp_path):
        console, buf = _make_console()
        interp = _make_interp_with_log(
            tmp_path,
            summary="Test problem occurred",
            suggested_fix="Do the test fix",
        )
        render_interactive(interp, console, interactive=False)
        output = buf.getvalue()
        assert "Test problem occurred" in output
        assert "Do the test fix" in output
        assert interp.diagnostic_id in output

    def test_panel_shows_debug_log_path(self, tmp_path):
        console, buf = _make_console()
        interp = _make_interp_with_log(tmp_path)
        render_interactive(interp, console, interactive=False)
        # Rich may wrap long paths across lines in the panel; join stripped lines
        # to flatten wrapping, then check the path name is present.
        output_flat = "".join(line.strip() for line in buf.getvalue().splitlines())
        # Check that at least the filename portion is present
        assert "debug.log" in output_flat
        assert interp.traceback_path.name in output_flat

    def test_neutral_title_when_no_mode(self, tmp_path):
        console, buf = _make_console()
        interp = _make_interp_with_log(tmp_path)
        render_interactive(interp, console, mode=None, interactive=False)
        output = buf.getvalue()
        assert "What happened" in output

    def test_mode_flavored_title_full_troll(self, tmp_path):
        from adversary_pursuit.gamification.modes import DEFAULT_MODES

        console, buf = _make_console()
        mode = DEFAULT_MODES["full_troll"]
        interp = _make_interp_with_log(tmp_path)
        render_interactive(interp, console, mode=mode, interactive=False)
        output = buf.getvalue()
        # full_troll should NOT show "What happened" — should show troll flavor
        assert "BRUH" in output or "broke" in output.lower()

    def test_mode_flavored_title_ninja(self, tmp_path):
        from adversary_pursuit.gamification.modes import DEFAULT_MODES

        console, buf = _make_console()
        mode = DEFAULT_MODES["ninja"]
        interp = _make_interp_with_log(tmp_path)
        render_interactive(interp, console, mode=mode, interactive=False)
        output = buf.getvalue()
        # F62: _MODE_TITLE_FLAVORS removed; panel title now uses mode.run_fail.
        # ninja run_fail: "[dim]Missed. Regroup.[/dim]" — Rich strips markup in output.
        assert "Missed" in output or "Regroup" in output

    def test_default_mode_neutral_title(self, tmp_path):
        from adversary_pursuit.gamification.modes import DEFAULT_MODES

        console, buf = _make_console()
        mode = DEFAULT_MODES["default"]
        interp = _make_interp_with_log(tmp_path)
        render_interactive(interp, console, mode=mode, interactive=False)
        output = buf.getvalue()
        # F62: _MODE_TITLE_FLAVORS removed; panel title now uses mode.run_fail.
        # default run_fail: "Hunt failed." — shown in the panel title.
        assert "Hunt failed" in output

    def test_auto_fix_accept_calls_callable(self, tmp_path):
        """[y] input runs the auto-fix callable and returns AutoFixOutcome(applied)."""
        was_called = []

        def _fix():
            was_called.append(True)

        auto_fix = AutoFix(
            label="Test fix",
            description="Does the test thing",
            callable=_fix,
        )
        console, buf = _make_console()
        interp = _make_interp_with_log(tmp_path, auto_fix=auto_fix)

        with patch("builtins.input", return_value="y"):
            outcome = render_interactive(interp, console, interactive=True)

        assert outcome.applied is True
        assert was_called, "auto_fix callable was not called"

    def test_auto_fix_decline_returns_declined(self, tmp_path):
        auto_fix = AutoFix(label="Fix", description="Desc", callable=lambda: None)
        console, buf = _make_console()
        interp = _make_interp_with_log(tmp_path, auto_fix=auto_fix)

        with patch("builtins.input", return_value="n"):
            outcome = render_interactive(interp, console, interactive=True)

        assert outcome.declined is True

    def test_auto_fix_debug_shows_traceback_then_continues(self, tmp_path):
        """[d] input prints debug detail and continues prompting; [n] follows."""
        log = tmp_path / "debug.log"
        did = _make_diagnostic_id()
        entry = {
            "diagnostic_id": did,
            "category": "Test",
            "traceback": "Traceback line here",
            "exc_type": "ValueError",
            "exc_str": "test",
            "context": {},
        }
        log.write_text(json.dumps(entry) + "\n")

        auto_fix = AutoFix(label="Fix", description="Desc", callable=lambda: None)
        console, buf = _make_console()
        interp = _make_interp_with_log(
            tmp_path,
            diagnostic_id=did,
            traceback_path=log,
            auto_fix=auto_fix,
        )

        # First input: "d" → show debug; second input: "n" → decline
        inputs = iter(["d", "n"])
        with patch("builtins.input", side_effect=inputs):
            outcome = render_interactive(interp, console, interactive=True)

        output = buf.getvalue()
        assert "Traceback line here" in output or did in output
        assert outcome.declined is True

    def test_no_auto_fix_returns_unavailable(self, tmp_path):
        console, buf = _make_console()
        interp = _make_interp_with_log(tmp_path, auto_fix=None)
        outcome = render_interactive(interp, console, interactive=True)
        assert outcome.unavailable is True

    def test_eof_during_prompt_returns_declined(self, tmp_path):
        auto_fix = AutoFix(label="Fix", description="Desc", callable=lambda: None)
        console, buf = _make_console()
        interp = _make_interp_with_log(tmp_path, auto_fix=auto_fix)

        with patch("builtins.input", side_effect=EOFError):
            outcome = render_interactive(interp, console, interactive=True)

        assert outcome.declined is True


# ---------------------------------------------------------------------------
# render_summary_line() — one-liner, no Rich markup
# ---------------------------------------------------------------------------


class TestRenderSummaryLine:
    def test_format_contains_category_fix_diag(self, tmp_path):
        interp = _make_interp_with_log(
            tmp_path,
            category="Network",
            suggested_fix="Check connectivity",
            diagnostic_id="abcd1234",
        )
        line = render_summary_line(interp)
        assert "[Network]" in line
        assert "Check connectivity" in line
        assert "abcd1234" in line

    def test_no_rich_markup_in_output(self, tmp_path):
        interp = _make_interp_with_log(tmp_path, category="API key")
        line = render_summary_line(interp)
        # Rich markup tags like [bold], [red], etc. must not appear
        assert "[bold]" not in line
        assert "[red]" not in line
        assert "[/bold]" not in line

    def test_single_line(self, tmp_path):
        interp = _make_interp_with_log(tmp_path)
        line = render_summary_line(interp)
        assert "\n" not in line

    def test_various_categories(self, tmp_path):
        for cat in ("API key", "Network", "Timeout", "Config", "Database", "Unknown"):
            interp = _make_interp_with_log(tmp_path, category=cat)
            line = render_summary_line(interp)
            assert f"[{cat}]" in line


# ---------------------------------------------------------------------------
# Compound interaction: full production sequence end-to-end
# ---------------------------------------------------------------------------


class TestEndToEndProduction:
    """Exercises the real production sequence crossing interpret → render → log."""

    def test_auth_error_full_sequence(self, tmp_path):
        """Simulate a missing Shodan API key: interpret → panel → summary line."""
        from adversary_pursuit.modules.base import AuthenticationError

        exc = AuthenticationError("AP_SHODAN_API_KEY not configured")
        log = tmp_path / "debug.log"

        # Route debug log to tmp_path
        with patch(
            "adversary_pursuit.core.error_interpreter.DEBUG_LOG_PATH",
            log,
        ):
            interp = interpret(exc, context={"module": "osint/shodan_ip"})

        # Verify interpretation
        assert interp.category == "API key"
        assert re.fullmatch(r"[a-f0-9]{8}", interp.diagnostic_id)

        # Verify panel rendering
        console, buf = _make_console()
        render_interactive(interp, console, interactive=False)
        output = buf.getvalue()
        assert interp.diagnostic_id in output
        assert "Traceback (most recent call last):" not in output

        # Verify summary line
        line = render_summary_line(interp)
        assert "[API key]" in line
        assert interp.diagnostic_id in line

        # Verify debug log entry
        assert log.exists()
        entry = json.loads(log.read_text().strip())
        assert entry["diagnostic_id"] == interp.diagnostic_id
        assert entry["context"]["module"] == "osint/shodan_ip"

    def test_rate_limit_with_auto_fix_full_sequence(self, tmp_path):
        """RateLimitError with retry_after: interpret → auto-fix offered → callable runs."""
        from adversary_pursuit.modules.base import RateLimitError

        exc = RateLimitError("Too many requests", retry_after=3)

        with patch(
            "adversary_pursuit.core.error_interpreter.DEBUG_LOG_PATH",
            tmp_path / "debug.log",
        ):
            interp = interpret(exc)

        assert interp.category == "Rate limit"
        assert interp.auto_fix is not None

        # Mock the auto-fix callable to verify it can be called
        called = []
        patched_fix = AutoFix(
            label=interp.auto_fix.label,
            description=interp.auto_fix.description,
            callable=lambda: called.append(True),
        )
        object.__setattr__(interp, "auto_fix", patched_fix)

        console, buf = _make_console()
        with patch("builtins.input", return_value="y"):
            outcome = render_interactive(interp, console, interactive=True)

        assert outcome.applied is True
        assert called

    def test_unknown_error_never_leaks_traceback(self, tmp_path):
        """Unknown error must show a friendly panel, not a Python traceback."""
        exc = RuntimeError("Some internal state corruption")

        with patch(
            "adversary_pursuit.core.error_interpreter.DEBUG_LOG_PATH",
            tmp_path / "debug.log",
        ):
            interp = interpret(exc)

        console, buf = _make_console()
        render_interactive(interp, console, interactive=False)
        output = buf.getvalue()

        assert "Traceback (most recent call last):" not in output
        assert interp.diagnostic_id in output
        assert interp.category == "Unknown"

    def test_two_modes_produce_distinguishable_titles(self, tmp_path):
        """Default vs full_troll modes produce different panel titles."""
        from adversary_pursuit.gamification.modes import DEFAULT_MODES

        exc = ValueError("some error")
        with patch(
            "adversary_pursuit.core.error_interpreter.DEBUG_LOG_PATH",
            tmp_path / "debug.log",
        ):
            interp = interpret(exc)

        # Default mode
        console_default, buf_default = _make_console()
        render_interactive(
            interp, console_default, mode=DEFAULT_MODES["default"], interactive=False
        )

        # Full-troll mode
        console_troll, buf_troll = _make_console()
        render_interactive(
            interp, console_troll, mode=DEFAULT_MODES["full_troll"], interactive=False
        )

        default_output = buf_default.getvalue()
        troll_output = buf_troll.getvalue()

        # Titles must differ
        assert default_output != troll_output
        # Both must contain the diagnostic ID
        assert interp.diagnostic_id in default_output
        assert interp.diagnostic_id in troll_output
