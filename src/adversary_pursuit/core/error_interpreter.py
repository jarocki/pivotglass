"""Universal error interpreter for Adversary Pursuit.

Provides a data-driven catalog of known error patterns with fix-suggestions,
diagnostic IDs, debug-log persistence, and optional auto-fix prompts. All
user-facing surfaces (cmd2 console, agent chat, smoke_test) converge here for
consistent, friendly error handling with zero raw tracebacks exposed to users.

Key design decisions:

@decision DEC-ERROR-INTERPRETER-001
@title New core/error_interpreter.py as sole catalog authority;
       agent/error_handler.classify_error() delegates
@status accepted
@rationale The existing classify_error is correctly factored for chat-LLM use
           but coupling core/console.py and scripts/smoke_test.py to an agent/
           namespace would pull litellm transitively. Placing the catalog under
           core/ reflects that error interpretation is shared infrastructure.
           Preserves DEC-AGENT-ERROR-HANDLER-001 by extracting only stage 1;
           stages 2 and 3 stay in agent. Single authority avoids the
           parallel-catalog drift CLAUDE.md §12 forbids.

@decision DEC-ERROR-INTERPRETER-002
@title Debug log at user-global ~/.ap/debug.log, not workspace-scoped
@status accepted
@rationale Errors can occur before a workspace is loaded (config corruption,
           plugin discovery failure). The debug log must always have a stable
           target. User-global also keeps the diagnostic ID copy-pasteable in
           bug reports regardless of which workspace was active.

@decision DEC-ERROR-INTERPRETER-003
@title JSONL append with fcntl.flock rotation to most-recent 1000 lines
@status accepted
@rationale Worktree concurrency means two ap processes may interpret errors
           simultaneously. fcntl.flock on the log file makes append atomic.
           Line-count rotation (read-trim-write under lock) bounds disk use
           without external dependencies. 1000 entries ≈ ~500 KB ceiling.

@decision DEC-ERROR-INTERPRETER-004
@title 8-character lowercase hex diagnostic ID (secrets.token_bytes(4).hex())
@status accepted
@rationale Short enough to copy-paste from a terminal without wrapping; long
           enough that collision in a 1000-line log is negligible (~1 in 2^32).
           With 1000 entries, collision probability is ~1.2 × 10⁻⁷.

@decision DEC-ERROR-INTERPRETER-005
@title Auto-fix prompts limited to non-destructive operations behind [y/n]
@status accepted
@rationale Mechanically safe means the operation either touches no user data or
           restores from a known backup. Never auto-key-generate, never
           auto-delete, never auto-edit user files without explicit consent.

@decision DEC-ERROR-INTERPRETER-006
@title Renderer accepts CharacterMode | None for mode-flavored tone
@status accepted
@rationale Mode-flavored panel titles serve the gamification framing without
           coupling. mode=None yields neutral phrasing. No edits to
           DEFAULT_MODES or CharacterMode keep the modes authority unchanged.

@decision DEC-ERROR-INTERPRETER-007
@title Smoke test FAIL summary becomes [CATEGORY] fix-suggestion (diag <id>)
@status accepted
@rationale Concise mode tells the user what to do, not just what broke.
           --verbose retains today's traceback behavior for power-user / CI
           debugging. Signature of _fmt_exc(exc, verbose) is preserved.

@decision DEC-ERROR-INTERPRETER-008
@title Catalog v1 covers 8 known-issue patterns; unknown-fallback is mandatory
@status accepted
@rationale Initial coverage: missing API key, rate limit, network/connection-
           refused, network timeout, config TOML decode error, SQLite locked,
           LiteLLM/provider auth, and a mandatory unknown-fallback. The
           unknown-fallback must produce a friendly panel with a diagnostic ID
           even when no catalog entry matches — no Python traceback ever reaches
           the user without going through the interpreter.
"""

from __future__ import annotations

import fcntl
import json
import re
import secrets
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from rich.console import Console
from rich.panel import Panel

if TYPE_CHECKING:
    from adversary_pursuit.gamification.modes import CharacterMode

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

DEBUG_LOG_PATH = Path.home() / ".ap" / "debug.log"
_DEBUG_LOG_MAX_LINES = 1000

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AutoFix:
    """A safe, user-confirmed remediation callable.

    Attributes
    ----------
    label:
        Short description shown in the prompt: e.g. "Restore config from backup"
    description:
        One-sentence explanation of what the fix does.
    callable:
        Zero-argument callable that performs the fix. Must be idempotent and
        non-destructive (DEC-ERROR-INTERPRETER-005).
    """

    label: str
    description: str
    callable: Callable[[], None] = field(compare=False)


@dataclass
class ErrorInterpretation:
    """Structured result from interpret().

    Attributes
    ----------
    severity:
        "info", "warn", or "error".
    category:
        Short human-readable category, e.g. "API key", "Network", "Config".
    summary:
        Plain-language sentence describing what went wrong.
    suggested_fix:
        Plain-language sentence telling the user what to do.
    auto_fix:
        Optional AutoFix if a safe automated remediation is available.
    diagnostic_id:
        8-hex-char ID for correlating this interpretation with the debug log.
    traceback_path:
        Path to ~/.ap/debug.log for user reference.
    """

    severity: str
    category: str
    summary: str
    suggested_fix: str
    auto_fix: AutoFix | None = None
    diagnostic_id: str = field(default_factory=lambda: _make_diagnostic_id())
    traceback_path: Path = field(default_factory=lambda: DEBUG_LOG_PATH)


# ---------------------------------------------------------------------------
# Diagnostic ID generation (DEC-ERROR-INTERPRETER-004)
# ---------------------------------------------------------------------------


def _make_diagnostic_id() -> str:
    """Return an 8-char lowercase hex diagnostic ID.

    Uses secrets.token_bytes for cryptographic randomness to ensure IDs do
    not collide even in high-throughput error scenarios.
    """
    return secrets.token_bytes(4).hex()


# ---------------------------------------------------------------------------
# Debug log persistence (DEC-ERROR-INTERPRETER-002, DEC-ERROR-INTERPRETER-003)
# ---------------------------------------------------------------------------


def _append_debug_log(
    interp: ErrorInterpretation,
    exc: BaseException,
    context: dict | None = None,
) -> None:
    """Write one JSONL entry to ~/.ap/debug.log.

    Uses fcntl.flock to make concurrent appends safe across multiple ap
    processes in the same worktree session (DEC-ERROR-INTERPRETER-003).

    Rotates the log to the most-recent 1000 entries on overflow. Rotation
    happens atomically: read-trim-write is executed under the same flock
    so a concurrent reader never sees a partially-written file.

    If the log write itself fails (disk full, permission error) the exception
    is written to stderr — loud failure over silent fallback.
    """
    try:
        log_path = interp.traceback_path
        log_path.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "diagnostic_id": interp.diagnostic_id,
            "category": interp.category,
            "summary": interp.summary,
            "exc_type": type(exc).__name__,
            "exc_str": str(exc),
            "traceback": traceback.format_exc(),
            "context": context or {},
        }
        line = json.dumps(entry, default=str)

        # Open in read+write mode, creating if absent, so we can both read
        # existing content and append — all under a single lock.
        with open(log_path, "a+", encoding="utf-8") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX)
                # Seek to start and read all existing lines for rotation check
                fh.seek(0)
                existing_lines = fh.readlines()
                # Trim if we are at or over the ceiling (keep N-1 to make room)
                if len(existing_lines) >= _DEBUG_LOG_MAX_LINES:
                    keep = existing_lines[-(_DEBUG_LOG_MAX_LINES - 1) :]
                    fh.seek(0)
                    fh.truncate()
                    fh.writelines(keep)
                # Append new entry
                fh.seek(0, 2)  # seek to end
                fh.write(line + "\n")
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
    except Exception as log_exc:  # noqa: BLE001
        # Loud failure — never silently swallow debug log errors
        print(
            f"[ap] WARNING: could not write to debug log: {log_exc}",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Error catalog (DEC-ERROR-INTERPRETER-008)
# ---------------------------------------------------------------------------
# Each entry is a 3-tuple:
#   (match_fn, interpret_fn, auto_fix_factory)
# match_fn(exc) -> bool     — True if this entry handles the exception
# interpret_fn(exc) -> dict  — returns kwargs for ErrorInterpretation (no id/path)
# auto_fix_factory(exc) -> AutoFix | None  — optional safe fix callable
#
# Entries are checked in order; first match wins.


def _is_auth_error(exc: BaseException) -> bool:
    """Match AuthenticationError from modules.base or similar auth failures."""
    # Import lazily to avoid circular dep; this module is under core/
    exc_type = type(exc).__name__
    # Matches modules.base.AuthenticationError and any class named similarly
    if exc_type in ("AuthenticationError", "AuthorizationError", "InvalidAPIKeyError"):
        return True
    # Match by inheritance from modules.base.AuthenticationError
    for cls in type(exc).__mro__:
        if cls.__name__ in ("AuthenticationError",):
            return True
    # Match by message content for cases where exception type doesn't match
    msg = str(exc).lower()
    if "api key" in msg and ("invalid" in msg or "missing" in msg or "unauthorized" in msg):
        return True
    return False


def _service_name_from_auth(exc: BaseException) -> str:
    """Extract service name hint from an auth exception's message."""
    msg = str(exc)
    # Try to extract AP_<SERVICE>_API_KEY pattern from message
    m = re.search(r"AP_([A-Z_]+)_API_KEY", msg)
    if m:
        return m.group(1)
    return ""


def _interpret_auth(exc: BaseException) -> dict:
    svc = _service_name_from_auth(exc)
    if svc:
        fix = f"Set AP_{svc}_API_KEY or run `ap config setup`."
    else:
        fix = "Set the relevant AP_<SERVICE>_API_KEY env var or run `ap config setup`."
    return {
        "severity": "error",
        "category": "API key",
        "summary": "An API key is missing or invalid.",
        "suggested_fix": fix,
    }


def _is_rate_limit(exc: BaseException) -> bool:
    exc_type = type(exc).__name__
    if exc_type in ("RateLimitError", "QuotaExceededError", "TooManyRequestsError"):
        return True
    for cls in type(exc).__mro__:
        if cls.__name__ == "RateLimitError":
            return True
    msg = str(exc).lower()
    if "rate limit" in msg or "too many requests" in msg or "quota" in msg:
        return True
    return False


def _interpret_rate_limit(exc: BaseException) -> dict:
    # RateLimitError from modules.base carries retry_after attribute
    retry_after = getattr(exc, "retry_after", None)
    if retry_after:
        fix = f"Wait {retry_after}s or rotate to a higher-tier API key."
    else:
        fix = "Wait a moment and retry, or rotate to a higher-tier API key."
    return {
        "severity": "warn",
        "category": "Rate limit",
        "summary": "The API rate limit was exceeded.",
        "suggested_fix": fix,
    }


def _auto_fix_rate_limit(exc: BaseException) -> AutoFix | None:
    retry_after = getattr(exc, "retry_after", None)
    if retry_after and isinstance(retry_after, (int, float)) and retry_after <= 30:
        seconds = int(retry_after)

        def _sleep_and_retry() -> None:
            import time

            time.sleep(seconds)

        return AutoFix(
            label=f"Wait {seconds}s automatically",
            description=f"Pause for {seconds} seconds (the Retry-After value), then let you retry.",
            callable=_sleep_and_retry,
        )
    return None


def _is_connect_error(exc: BaseException) -> bool:
    """Match httpx.ConnectError and similar connection-refused exceptions."""
    exc_type = type(exc).__name__
    _conn_types = {"ConnectError", "ConnectionRefusedError", "ServiceUnavailableError"}
    if exc_type in _conn_types:
        return True
    # Check inheritance chain for httpx.ConnectError lookalikes
    for cls in type(exc).__mro__:
        if cls.__name__ in _conn_types:
            return True
    return False


def _interpret_connect_error(exc: BaseException) -> dict:
    # Extract hostname hint if available
    msg = str(exc)
    host_m = re.search(r"https?://([^/:\s]+)", msg)
    host = host_m.group(1) if host_m else ""
    if host:
        fix = f"Check connectivity to {host}. If persistent, bump TIMEOUT in options."
    else:
        fix = "Check your network connection or the service endpoint."
    return {
        "severity": "error",
        "category": "Network",
        "summary": "Could not connect to the remote service (connection refused).",
        "suggested_fix": fix,
    }


def _is_timeout_error(exc: BaseException) -> bool:
    """Match httpx.ReadTimeout, ConnectTimeout, and stdlib TimeoutError."""
    exc_type = type(exc).__name__
    _timeout_types = {
        "ReadTimeout",
        "ConnectTimeout",
        "TimeoutError",
        "Timeout",
        "httpx.ReadTimeout",
        "httpx.ConnectTimeout",
    }
    if exc_type in _timeout_types:
        return True
    for cls in type(exc).__mro__:
        if cls.__name__ in _timeout_types:
            return True
    return False


def _interpret_timeout(exc: BaseException) -> dict:
    msg = str(exc)
    host_m = re.search(r"https?://([^/:\s]+)", msg)
    host = host_m.group(1) if host_m else ""
    if host:
        fix = f"Check connectivity to {host}; bump the TIMEOUT option if persistent."
    else:
        fix = "The service took too long to respond. Try again or bump the TIMEOUT option."
    return {
        "severity": "warn",
        "category": "Timeout",
        "summary": "The request timed out waiting for a response.",
        "suggested_fix": fix,
    }


def _is_toml_error(exc: BaseException) -> bool:
    """Match tomllib.TOMLDecodeError and similar config-parse failures."""
    exc_type = type(exc).__name__
    if exc_type in ("TOMLDecodeError",):
        return True
    for cls in type(exc).__mro__:
        if cls.__name__ in ("TOMLDecodeError",):
            return True
    return False


def _interpret_toml(exc: BaseException) -> dict:
    backup = Path.home() / ".ap" / "config.toml.bak"
    if backup.exists():
        fix = f"Restore from backup: `cp {backup} ~/.ap/config.toml`, or run `ap config setup`."
    else:
        fix = "Run `ap config setup` to regenerate a valid config file."
    return {
        "severity": "error",
        "category": "Config",
        "summary": "The config file (~/.ap/config.toml) contains invalid TOML syntax.",
        "suggested_fix": fix,
    }


def _auto_fix_toml(exc: BaseException) -> AutoFix | None:
    """Offer to restore config.toml from .bak if the backup exists."""
    backup = Path.home() / ".ap" / "config.toml.bak"
    config = Path.home() / ".ap" / "config.toml"
    if not backup.exists():
        return None

    def _restore() -> None:
        import shutil

        shutil.copy2(backup, config)

    return AutoFix(
        label="Restore config from backup",
        description=f"Copy {backup} over {config} to restore your last known-good config.",
        callable=_restore,
    )


def _is_sqlite_locked(exc: BaseException) -> bool:
    """Match sqlalchemy.exc.OperationalError when the message contains 'locked'."""
    exc_type = type(exc).__name__
    if exc_type in ("OperationalError",):
        if "locked" in str(exc).lower() or "database is locked" in str(exc).lower():
            return True
    # Also match raw sqlite3.OperationalError
    for cls in type(exc).__mro__:
        if cls.__name__ in ("OperationalError",) and "lock" in str(exc).lower():
            return True
    return False


def _interpret_sqlite_locked(exc: BaseException) -> dict:
    return {
        "severity": "error",
        "category": "Database",
        "summary": "The workspace database is locked.",
        "suggested_fix": (
            "Another `ap` instance has the workspace open. "
            "Close it and retry, or use `workspace switch` to create a new workspace."
        ),
    }


def _is_llm_provider_error(exc: BaseException) -> bool:
    """Match litellm/provider auth failures and API-key-not-found errors."""
    exc_type = type(exc).__name__
    _provider_err_types = {
        "AuthenticationError",
        "InvalidAPIKeyError",
        "PermissionDeniedError",
        "NotFoundError",
        "APIStatusError",
    }
    # Only match these when they are from a provider context (not modules.base)
    # We distinguish by checking module origin or message content
    msg = str(exc).lower()
    if exc_type in _provider_err_types:
        # Distinguish LLM auth errors from module auth errors by message keywords
        if any(kw in msg for kw in ("openai", "anthropic", "provider", "model", "llm", "bearer")):
            return True
        if "api_key" in msg or "api key" in msg or "unauthorized" in msg or "authentication" in msg:
            # If it's from litellm / openai package namespaces
            for cls in type(exc).__mro__:
                mod = getattr(cls, "__module__", "") or ""
                if any(pkg in mod for pkg in ("litellm", "openai", "anthropic")):
                    return True
    # Match by message keywords regardless of class name
    if any(kw in msg for kw in ("litellm", "openai.authenticationerror", "invalid api key")):
        return True
    return False


def _interpret_llm_provider(exc: BaseException) -> dict:
    return {
        "severity": "error",
        "category": "LLM provider",
        "summary": "The LLM provider rejected the API key or configuration.",
        "suggested_fix": (
            "Set AP_AGENT_<PROVIDER>_API_KEY or run `ap config setup --provider` "
            "to reconfigure your AI provider."
        ),
    }


# The catalog: list of (match, interpret, auto_fix_factory) triples.
# First match wins. Order matters: more specific checks before broad ones.
_CatalogEntry = tuple[
    Callable[[BaseException], bool],  # match
    Callable[[BaseException], dict],  # interpret → kwargs
    Callable[[BaseException], AutoFix | None],  # auto_fix_factory
]


def _NO_AUTO_FIX(exc: BaseException) -> AutoFix | None:  # noqa: N802 — named as constant per catalog convention
    """Catalog sentinel: no auto-fix available for this error type."""
    return None


_CATALOG: list[_CatalogEntry] = [
    # 1. API key authentication errors (modules.base.AuthenticationError)
    (_is_auth_error, _interpret_auth, _NO_AUTO_FIX),
    # 2. Rate limit exceeded (modules.base.RateLimitError)
    (_is_rate_limit, _interpret_rate_limit, _auto_fix_rate_limit),
    # 3. Network connect error (httpx.ConnectError, ConnectionRefusedError)
    (_is_connect_error, _interpret_connect_error, _NO_AUTO_FIX),
    # 4. Timeout (httpx.ReadTimeout, ConnectTimeout, stdlib TimeoutError)
    (_is_timeout_error, _interpret_timeout, _NO_AUTO_FIX),
    # 5. Config TOML decode error (tomllib.TOMLDecodeError)
    (_is_toml_error, _interpret_toml, _auto_fix_toml),
    # 6. SQLite database locked (sqlalchemy.exc.OperationalError with "locked")
    (_is_sqlite_locked, _interpret_sqlite_locked, _NO_AUTO_FIX),
    # 7. LLM/litellm provider auth failures (must be checked AFTER modules auth)
    (_is_llm_provider_error, _interpret_llm_provider, _NO_AUTO_FIX),
]

# ---------------------------------------------------------------------------
# Public entry point: interpret()
# ---------------------------------------------------------------------------


def interpret(exc: BaseException, *, context: dict | None = None) -> ErrorInterpretation:
    """Classify *exc* and return a structured ErrorInterpretation.

    Never raises — if the interpreter itself encounters an error, returns the
    unknown-fallback interpretation. All paths produce a debug-log entry.

    Parameters
    ----------
    exc:
        The exception to classify.
    context:
        Optional dict of caller context (e.g. module name, target) stored in
        the debug log alongside the traceback.

    Returns
    -------
    ErrorInterpretation
        Always returns an interpretation. Never raises.
    """
    try:
        # Walk the catalog in declaration order; first match wins
        for match_fn, interpret_fn, auto_fix_factory in _CATALOG:
            try:
                if match_fn(exc):
                    kwargs = interpret_fn(exc)
                    diag_id = _make_diagnostic_id()
                    auto_fix = auto_fix_factory(exc)
                    interp = ErrorInterpretation(
                        **kwargs,
                        auto_fix=auto_fix,
                        diagnostic_id=diag_id,
                        traceback_path=DEBUG_LOG_PATH,
                    )
                    _append_debug_log(interp, exc, context)
                    return interp
            except Exception:  # noqa: BLE001
                # A buggy catalog entry must never poison the whole interpreter
                continue

        # No catalog match → unknown fallback
        return _unknown_fallback(exc, context)

    except Exception:  # noqa: BLE001
        # interpret() itself raised — produce a minimal canned interpretation
        diag_id = _make_diagnostic_id()
        canned = ErrorInterpretation(
            severity="error",
            category="Unknown",
            summary="Something unexpected happened while interpreting the error.",
            suggested_fix=(
                "Check ~/.ap/debug.log for the diagnostic entry, "
                "then file a bug report with the diagnostic ID."
            ),
            diagnostic_id=diag_id,
            traceback_path=DEBUG_LOG_PATH,
        )
        # Best-effort debug log write — don't let this raise either
        try:
            _append_debug_log(canned, exc, context)
        except Exception:  # noqa: BLE001
            pass
        return canned


def _unknown_fallback(exc: BaseException, context: dict | None) -> ErrorInterpretation:
    """Build and log the unknown-error fallback interpretation."""
    diag_id = _make_diagnostic_id()
    interp = ErrorInterpretation(
        severity="error",
        category="Unknown",
        summary="An unexpected error occurred.",
        suggested_fix=(
            "Check ~/.ap/debug.log for the full traceback, then retry. "
            "If the issue persists, file a bug report with the diagnostic ID."
        ),
        diagnostic_id=diag_id,
        traceback_path=DEBUG_LOG_PATH,
    )
    _append_debug_log(interp, exc, context)
    return interp


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

# Severity → icon mapping (DEC-ERROR-INTERPRETER-006)
_SEVERITY_ICON = {
    "info": "✓",
    "warn": "⚠",
    "error": "✗",
}


def _panel_title(interp: ErrorInterpretation, mode: "CharacterMode | None") -> str:
    """Build the Rich-markup panel title string.

    Uses mode.run_fail as the panel title when a CharacterMode is provided.
    This makes run_fail the single authority for mode-flavored failure voice,
    replacing the parallel _MODE_TITLE_FLAVORS dict that was removed in F62
    (DEC-62-KILL-DOC-LIES-001: one authority, no parallel dict drift).

    Falls back to a neutral title when mode is None (e.g. pexcept before
    mode_mgr is initialised) or when run_fail is empty.
    """
    icon = _SEVERITY_ICON.get(interp.severity, "✗")
    if mode is not None and mode.run_fail:
        # Strip Rich markup for the title slot — the panel border already
        # provides the yellow styling context.
        return f"[bold yellow]{icon} {mode.run_fail}[/bold yellow]"
    # Neutral title
    return f"[bold yellow]{icon} What happened[/bold yellow]"


# Sentinel returned from render_interactive to indicate the auto-fix outcome
class AutoFixOutcome:
    """Result of render_interactive() describing auto-fix disposition.

    Attributes
    ----------
    applied:
        True if the user accepted and the auto-fix ran.
    declined:
        True if the user declined the fix.
    unavailable:
        True if no auto-fix was offered.
    """

    __slots__ = ("applied", "declined", "unavailable")

    def __init__(
        self,
        applied: bool = False,
        declined: bool = False,
        unavailable: bool = False,
    ) -> None:
        self.applied = applied
        self.declined = declined
        self.unavailable = unavailable

    def __repr__(self) -> str:
        if self.applied:
            return "AutoFixOutcome(applied)"
        if self.declined:
            return "AutoFixOutcome(declined)"
        return "AutoFixOutcome(unavailable)"


def render_interactive(
    interp: ErrorInterpretation,
    console: Console,
    *,
    mode: "CharacterMode | None" = None,
    interactive: bool = True,
) -> AutoFixOutcome:
    """Render *interp* as a Rich panel on *console*.

    In interactive mode, prompts for [y/n/d] when an auto-fix is available:
    - [y] accept: run the auto-fix callable
    - [n] decline: skip
    - [d] debug: print the full traceback from the debug log

    Parameters
    ----------
    interp:
        The ErrorInterpretation to render.
    console:
        Rich Console for output.
    mode:
        Optional active CharacterMode for tone-flavored title.
    interactive:
        When False, suppress the [y/n/d] prompt (e.g. in tests or CI).

    Returns
    -------
    AutoFixOutcome
        Indicates whether the auto-fix was applied, declined, or unavailable.
    """
    title = _panel_title(interp, mode)
    body_lines = [
        f"[bold]Problem:[/bold] {interp.summary}",
        f"[bold]Fix:[/bold] {interp.suggested_fix}",
        "",
        f"[dim]Diagnostic ID:[/dim] [bold]{interp.diagnostic_id}[/bold]  "
        f"[dim]Debug log:[/dim] [dim]{interp.traceback_path}[/dim]",
    ]
    if interp.auto_fix is not None:
        body_lines.append(
            f"\n[dim]Auto-fix available:[/dim] {interp.auto_fix.label} — "
            f"{interp.auto_fix.description}"
        )

    body = "\n".join(body_lines)
    console.print(
        Panel(
            body,
            title=title,
            style="yellow",
            border_style="yellow",
        )
    )

    # Auto-fix prompt (interactive mode only)
    if not interactive or interp.auto_fix is None:
        return AutoFixOutcome(unavailable=True)

    # Prompt loop — keep asking until valid input
    while True:
        try:
            ans = (
                input(f"Apply fix '{interp.auto_fix.label}'? [y]es / [n]o / [d]ebug detail: ")
                .strip()
                .lower()
            )
        except (EOFError, KeyboardInterrupt):
            return AutoFixOutcome(declined=True)

        if ans in ("y", "yes"):
            try:
                interp.auto_fix.callable()
            except Exception as fix_exc:  # noqa: BLE001
                console.print(
                    f"[yellow]Auto-fix failed: {fix_exc}. Please apply the fix manually.[/yellow]"
                )
            return AutoFixOutcome(applied=True)
        elif ans in ("n", "no"):
            return AutoFixOutcome(declined=True)
        elif ans in ("d", "debug"):
            _show_debug_detail(interp, console)
            # Continue prompt loop after showing debug detail
        else:
            console.print("[dim]Enter y, n, or d.[/dim]")


def _show_debug_detail(interp: ErrorInterpretation, console: Console) -> None:
    """Print the full traceback entry from the debug log for *interp*."""
    try:
        log_path = interp.traceback_path
        if not log_path.exists():
            console.print(f"[dim]Debug log not found at {log_path}[/dim]")
            return
        with open(log_path, encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_SH)
            try:
                lines = fh.readlines()
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

        # Find the matching entry by diagnostic_id
        entry_str: str | None = None
        for raw_line in reversed(lines):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                entry = json.loads(raw_line)
                if entry.get("diagnostic_id") == interp.diagnostic_id:
                    entry_str = entry.get("traceback", "(no traceback recorded)")
                    break
            except json.JSONDecodeError:
                continue

        if entry_str:
            console.print(f"\n[dim]--- Traceback for diag {interp.diagnostic_id} ---[/dim]")
            console.print(entry_str)
        else:
            console.print(
                f"[dim]No debug entry found for diagnostic ID {interp.diagnostic_id}[/dim]"
            )
    except Exception as e:  # noqa: BLE001
        console.print(f"[dim]Could not read debug log: {e}[/dim]")


def render_summary_line(interp: ErrorInterpretation) -> str:
    """Return a single-line plain-text summary for non-interactive surfaces.

    Format: ``[CATEGORY] suggested_fix (diag <id>)``

    No Rich markup — safe for stdout emission in scripts/smoke_test.py.

    Parameters
    ----------
    interp:
        The ErrorInterpretation to summarize.

    Returns
    -------
    str
        A single-line summary with category prefix and diagnostic ID.
    """
    return f"[{interp.category}] {interp.suggested_fix} (diag {interp.diagnostic_id})"
