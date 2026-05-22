"""Friendly error rendering for the AP chat REPL.

Intercepts exceptions raised during the LLM loop, classifies them via local
pattern matching, and — for unknown errors — asks the configured LLM to
produce a one-line summary + one-line fix.  The result is always a Rich Panel
with no raw stack trace visible to the user.

Three-stage pipeline
--------------------
1. ``classify_error(exc)`` — instant, local, pattern-based classification.
   Returns ``FriendlyError`` for known error shapes, ``None`` for unknown.
   Stage 1 **delegates** to ``core.error_interpreter.interpret()`` as the sole
   catalog authority (DEC-ERROR-INTERPRETER-001).  This keeps the three-stage
   pipeline intact while removing the parallel inline catalog.
2. ``debug_llm_explain(exc, ...)`` — one LLM round-trip for unknown errors.
   Wrapped in its own try/except so a broken LLM layer never leaks raw errors.
3. ``handle_error(exc, console, runner, config_mgr)`` — orchestrates (1) and
   (2), renders the result as a Rich Panel, and returns a recoverable flag.

@decision DEC-AGENT-ERROR-HANDLER-001
@title Three-stage classify→LLM-explain→canned-fallback error pipeline
@status accepted
@rationale Raw stack traces breaking REPL immersion is a UX anti-pattern.
           Local classification handles common errors (network, auth, import)
           instantly with no LLM round-trip.  Unknown errors get a debug-LLM
           call so the explanation is context-specific rather than generic.
           The debug call has a 5-second timeout and its own exception guard so
           a broken LLM (the very thing that may have raised the error) cannot
           produce a secondary failure visible to the user.  If all else fails,
           a canned message is shown — the REPL never crashes due to error
           rendering.  ``recoverable`` lets callers decide whether to continue
           the loop or exit cleanly.

@decision DEC-ERROR-INTERPRETER-001
@title classify_error() delegates to core.error_interpreter — sole catalog authority
@status accepted (supersedes: inline catalog body in this module)
@rationale The inline catalog body has been relocated to core/error_interpreter.py
           so that cmd2 console, smoke_test, and agent chat share one catalog
           without a litellm transitive dependency in core/.  classify_error()
           now adapts ErrorInterpretation → FriendlyError so the three-stage
           pipeline and all call sites remain unchanged.  The "Unknown" category
           from the interpreter maps to None so stage 2 (LLM explain) still fires
           for unrecognised errors, preserving the original chat-specific behavior.
"""

from __future__ import annotations

import concurrent.futures
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel

if TYPE_CHECKING:
    from adversary_pursuit.core.config import ConfigManager

# litellm is an optional dependency ([agent] extra).  Import it at module level
# so that tests can patch 'adversary_pursuit.agent.error_handler.litellm' cleanly.
# The actual import is guarded so this module loads fine without litellm installed.
try:
    import litellm as litellm  # noqa: PLC0414 — re-export for patch target
except ImportError:
    litellm = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class FriendlyError:
    """User-facing error representation: one-line problem + one-line fix.

    Attributes
    ----------
    summary:
        A single sentence describing what went wrong.
    suggestion:
        A single sentence telling the user what to do next.
    recoverable:
        When ``True`` the REPL should continue after displaying this error.
        When ``False`` the REPL should exit (fatal error).
    """

    summary: str
    suggestion: str
    recoverable: bool = True
    # Internal: raw exception stored for debug-LLM call; never shown to user
    _exc: BaseException | None = field(default=None, repr=False, compare=False)


# ---------------------------------------------------------------------------
# Canned fallback (used when the debug LLM call itself fails)
# ---------------------------------------------------------------------------

_CANNED_FALLBACK = FriendlyError(
    summary="Something unexpected went wrong.",
    suggestion=("Try 'model show' to verify your setup, or rerun the wizard with 'model select'."),
    recoverable=True,
)

# ---------------------------------------------------------------------------
# Local pattern-based classifier
# ---------------------------------------------------------------------------


def classify_error(exc: BaseException) -> FriendlyError | None:
    """Classify *exc* against known error patterns.

    Delegates to ``core.error_interpreter.interpret()`` as the sole catalog
    authority (DEC-ERROR-INTERPRETER-001).  Adapts ``ErrorInterpretation`` to
    ``FriendlyError`` so the three-stage pipeline and all call sites remain
    unchanged.

    Returns ``None`` for the "Unknown" category so that stage 2
    (``debug_llm_explain``) still fires for unrecognised errors — preserving
    the original chat-specific LLM-explain behavior.

    Additional chat-specific classification not in the shared catalog:
    - ``ImportError`` for missing agent extras → fatal (not recoverable)
    - Ollama-specific connection-refused with localhost hint
    - ``FileNotFoundError``/``PermissionError`` on ``~/.ap/`` paths

    Parameters
    ----------
    exc:
        The exception to classify.

    Returns
    -------
    FriendlyError | None
        A pre-built friendly error for known patterns, or ``None``.
    """
    # ----------------------------------------------------------------
    # Chat-specific pre-checks that are NOT in the shared catalog:
    # ImportError (agent extras) and Ollama localhost connection.
    # These are handled here because they are agent/chat-only concerns;
    # the shared catalog is for module/console/smoke surfaces.
    # ----------------------------------------------------------------
    exc_type = type(exc).__name__
    exc_str = str(exc).lower()

    # ImportError — litellm not installed (fatal; not in shared catalog)
    if isinstance(exc, ImportError):
        if "litellm" in exc_str or "litellm" in exc_type.lower():
            return FriendlyError(
                summary="The agent extras are not installed.",
                suggestion="Install them with: uv sync --all-extras",
                recoverable=False,
            )
        return FriendlyError(
            summary=f"A required package is missing: {exc}",
            suggestion="Run 'uv sync --all-extras' to install all optional dependencies.",
            recoverable=False,
        )

    # Connection / network errors — chat-specific LLM-provider path.
    # Covers both Ollama-specific (localhost hint) and generic provider errors.
    # The shared catalog covers httpx.ConnectError and similar by class hierarchy;
    # here we handle by class NAME (for litellm wrapper classes) and stdlib.
    _conn_names = {
        "APIConnectionError",
        "ConnectionError",
        "ConnectError",
        "ProviderConnectionError",
        "ServiceUnavailableError",
        "Timeout",
        "TimeoutError",
        "ReadTimeout",
        "ConnectTimeout",
    }
    if exc_type in _conn_names or any(n in exc_type for n in _conn_names):
        if "ollama" in exc_str or "localhost" in exc_str or "127.0.0.1" in exc_str:
            return FriendlyError(
                summary="Ollama isn't running (connection refused).",
                suggestion=(
                    "Start it with 'ollama serve', or run 'model select' to switch providers."
                ),
                recoverable=True,
            )
        return FriendlyError(
            summary="The LLM provider is unreachable (network error).",
            suggestion="Check your network connection, then try again or run 'model select'.",
            recoverable=True,
        )

    # stdlib ConnectionError / TimeoutError (includes ConnectionRefusedError etc.)
    if isinstance(exc, (ConnectionError, TimeoutError)):
        if "ollama" in exc_str or "localhost" in exc_str or "127.0.0.1" in exc_str:
            return FriendlyError(
                summary="Ollama isn't running (connection refused).",
                suggestion=(
                    "Start it with 'ollama serve', or run 'model select' to switch providers."
                ),
                recoverable=True,
            )
        return FriendlyError(
            summary="Provider unreachable — network error.",
            suggestion="Check your network connection and retry.",
            recoverable=True,
        )

    # Auth errors by message content — covers generic Exception raised by LLM providers
    if "invalid api key" in exc_str or "authentication" in exc_str:
        return FriendlyError(
            summary="Your API key was rejected by the provider.",
            suggestion="Run 'model select' to re-enter your API key.",
            recoverable=True,
        )

    # File system errors relating to ~/.ap/ (chat-specific path)
    if isinstance(exc, (FileNotFoundError, PermissionError)):
        if ".ap" in exc_str or "chat_history" in exc_str or "config.toml" in exc_str:
            return FriendlyError(
                summary=f"Cannot access AP data directory: {exc.filename if hasattr(exc, 'filename') else ''}",
                suggestion="Check permissions on ~/.ap/ or delete the directory to reset.",
                recoverable=True,
            )

    # ----------------------------------------------------------------
    # Delegate to the shared catalog (DEC-ERROR-INTERPRETER-001)
    # core.error_interpreter has no litellm dependency; safe to import here.
    # ----------------------------------------------------------------
    from adversary_pursuit.core.error_interpreter import interpret  # noqa: PLC0415

    interp = interpret(exc)

    # "Unknown" category means no catalog match → return None so stage 2 fires.
    if interp.category == "Unknown":
        return None

    # Adapt ErrorInterpretation → FriendlyError.
    # recoverable = True for warn/info; False only for errors that are fatal
    # (none in the shared catalog are fatal — only the chat-specific ImportError above).
    return FriendlyError(
        summary=interp.summary,
        suggestion=interp.suggested_fix,
        recoverable=True,
        _exc=exc,
    )


# ---------------------------------------------------------------------------
# LLM-based explainer (for unknown errors)
# ---------------------------------------------------------------------------


def debug_llm_explain(
    exc: BaseException,
    model: str,
    api_key: str | None,
    config_mgr: "ConfigManager | None" = None,
) -> FriendlyError:
    """Ask the configured LLM to explain *exc* in user-friendly terms.

    Calls litellm with a short system prompt instructing the model to produce
    exactly two lines: one describing the problem, one suggesting a fix.  The
    entire call runs inside a ``concurrent.futures`` thread with a 5-second
    timeout so it never blocks the REPL for long.

    If the LLM call fails (for any reason, including the LLM itself being down),
    the canned fallback ``_CANNED_FALLBACK`` is returned instead.

    Parameters
    ----------
    exc:
        The exception to explain.
    model:
        litellm model string to call.
    api_key:
        Provider API key, if available.
    config_mgr:
        Optional ConfigManager; used to resolve the API key if ``api_key`` is None.

    Returns
    -------
    FriendlyError
        Always returns a FriendlyError — never raises.
    """
    # Use the module-level litellm (may be None when not installed)
    if litellm is None:
        return _CANNED_FALLBACK

    system_prompt = (
        "You are a concise error-explainer for a CLI tool called 'ap'.\n"
        "The user encountered an exception. Reply with EXACTLY two lines:\n"
        "Line 1: One sentence describing what went wrong (start with 'Problem:').\n"
        "Line 2: One sentence telling them the simplest fix (start with 'Fix:').\n"
        "Do not include any other text, code blocks, or bullet points."
    )
    user_prompt = (
        f"Exception type: {type(exc).__name__}\n"
        f"Exception message: {exc!s}\n"
        "Please explain this to the user."
    )

    # Resolve API key from config_mgr if not supplied directly
    resolved_key = api_key
    if resolved_key is None and config_mgr is not None:
        provider_id = config_mgr.get_agent_provider()
        if provider_id:
            resolved_key = config_mgr.get_provider_api_key(provider_id)

    def _call() -> FriendlyError:
        kwargs: dict = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 120,
            "temperature": 0.2,
        }
        if resolved_key:
            kwargs["api_key"] = resolved_key

        response = litellm.completion(**kwargs)
        raw = (response.choices[0].message.content or "").strip()

        # Parse the two-line response
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        summary = _strip_prefix(lines[0] if lines else "", "Problem:").strip()
        suggestion = _strip_prefix(lines[1] if len(lines) > 1 else "", "Fix:").strip()

        if not summary:
            summary = "An unexpected error occurred."
        if not suggestion:
            suggestion = "Run 'model show' to verify your setup."

        return FriendlyError(summary=summary, suggestion=suggestion, recoverable=True)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call)
            return future.result(timeout=5.0)
    except Exception:
        return _CANNED_FALLBACK


def _strip_prefix(text: str, prefix: str) -> str:
    """Remove *prefix* from the start of *text* (case-insensitive, colon optional)."""
    pattern = re.compile(r"^" + re.escape(prefix) + r"\s*", re.IGNORECASE)
    return pattern.sub("", text)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def handle_error(
    exc: BaseException,
    console: Console,
    runner: object,
    config_mgr: "ConfigManager | None" = None,
) -> bool:
    """Classify, explain, and render *exc* as a user-friendly Rich Panel.

    Pipeline:
      1. ``classify_error`` — instant local classification.
      2. ``debug_llm_explain`` — LLM call for unknown errors (5-second timeout).
      3. Canned fallback — if (2) also fails.
    Then render as an amber/yellow Rich Panel and return the recoverable flag.

    Parameters
    ----------
    exc:
        The exception that was raised.
    console:
        Rich Console to render the panel on.
    runner:
        The active AgentRunner (used to read model and config for the debug call).
    config_mgr:
        ConfigManager for API key resolution.

    Returns
    -------
    bool
        ``True`` if the REPL should continue (recoverable error),
        ``False`` if the REPL should exit (fatal error).
    """
    # Stage 1: local classifier
    friendly = classify_error(exc)

    # Stage 2: LLM explainer for unknown errors
    if friendly is None:
        model = getattr(runner, "model", None) or "ollama/qwen2.5:8b"
        api_key: str | None = None
        if config_mgr is not None:
            provider_id = config_mgr.get_agent_provider()
            if provider_id:
                api_key = config_mgr.get_provider_api_key(provider_id)
        friendly = debug_llm_explain(exc, model=model, api_key=api_key, config_mgr=config_mgr)

    # Stage 3: render
    body = f"[bold]Problem:[/bold] {friendly.summary}\n[bold]Fix:[/bold] {friendly.suggestion}"
    console.print(
        Panel(
            body,
            title="[bold yellow]What happened[/bold yellow]",
            style="yellow",
            border_style="yellow",
        )
    )

    return friendly.recoverable
