"""Prompt-toolkit-based REPL input wrapper for AP chat.

Replaces bare ``input()`` / Rich ``console.input()`` with a fully-featured
prompt session that provides:
  - Tab-completion of meta-commands and context-sensitive arguments
  - Persistent ``FileHistory`` at ``~/.ap/chat_history`` (navigable via arrow keys)
  - Vi or Emacs editing mode selectable per session or via environment variable /
    config field ``general.editing_mode``

This module is the single authority for readline-equivalent UX in the chat REPL.
``chat.py`` imports ``prompt_user()`` and calls it instead of ``console.input()``.

@decision DEC-AGENT-REPL-INPUT-001
@title prompt_toolkit PromptSession as REPL input authority
@status accepted
@rationale prompt_toolkit (already a transitive dep via cmd2) provides
           tab-completion, file-based persistent history, vi/emacs editing
           modes, and syntax highlighting — capabilities unavailable via
           Rich's console.input() or Python's built-in input(). Centralising
           all input handling here means chat.py does not need to know about
           readline, curses, or terminal escapes. The class is designed to be
           mockable in tests: callers pass a prompt string; the PromptSession
           is lazy-initialised so unit tests that never call .prompt() don't
           need prompt_toolkit at all.
"""

from __future__ import annotations

import os
import re as _re
from pathlib import Path
from typing import Iterable

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.history import FileHistory, InMemoryHistory

from adversary_pursuit.core.command_completion import (
    MODULE_NAMES,
    TOP_LEVEL_COMMANDS,
    command_completions,
)
from adversary_pursuit.gamification.modes import (
    MODE_DISPLAY_NAMES,
    PUBLIC_MODE_ORDER,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default history file location.
HISTORY_PATH: Path = Path.home() / ".ap" / "chat_history"

#: All top-level meta-commands recognised by the AP chat REPL.
_TOP_LEVEL_COMMANDS: list[str] = list(TOP_LEVEL_COMMANDS)

#: Public character names come from the same authority as ``mode list``.
#: Historical identifiers remain accepted by ModeManager but no longer crowd
#: the primary completion surface.
_MODE_NAMES: list[str] = [MODE_DISPLAY_NAMES[name] for name in PUBLIC_MODE_ORDER]

#: CTI module names for hint completion.
_MODULE_NAMES: list[str] = list(MODULE_NAMES)

#: Export format choices.
_EXPORT_FORMATS: list[str] = ["json", "csv", "gexf", "stix"]

#: Model sub-commands. Completion is owned by ``command_completion``.
_MODEL_SUBCMDS: list[str] = [
    "show",
    "providers",
    "list",
    "check",
    "select",
    "enable",
    "disable",
    "repair",
    "configure",
    "advisor",
]

#: Report sub-commands.
_REPORT_SUBCMDS: list[str] = ["answer", "generate"]

#: Autopivot sub-commands.
_AUTOPIVOT_SUBCMDS: list[str] = ["on", "off"]


# ---------------------------------------------------------------------------
# Context-sensitive completer
# ---------------------------------------------------------------------------


class APCompleter(Completer):
    """Context-sensitive completer for AP chat meta-commands.

    Rules:
      * Empty input / partial first word → complete against _TOP_LEVEL_COMMANDS
      * ``mode <TAB>`` or ``mode <partial><TAB>`` → complete against mode names
      * ``hint <TAB>`` → complete against module names + "buy"
      * ``export <TAB>`` → complete against "gexf" / "stix"
      * ``model <TAB>`` → complete against the shared model-control commands
      * ``report <TAB>`` → complete against "answer" / "generate"
      * ``autopivot <TAB>`` → complete against "on" / "off"
      * Anything else → no completions (let the LLM handle it)
    """

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        text = document.text_before_cursor
        for candidate in command_completions(text, mode_names=_MODE_NAMES):
            if " " in text:
                _command, remainder = text.lstrip().split(" ", 1)
                replacement = candidate.split(" ", 1)[1]
                yield Completion(replacement, start_position=-len(remainder))
            else:
                yield Completion(candidate, start_position=-len(text))


def _match(prefix: str, candidates: list[str]) -> Iterable[Completion]:
    """Yield Completion objects whose text starts with *prefix* (case-insensitive)."""
    lower = prefix.lower()
    for candidate in candidates:
        if candidate.lower().startswith(lower):
            yield Completion(candidate, start_position=-len(prefix))


# ---------------------------------------------------------------------------
# Session class
# ---------------------------------------------------------------------------


class ChatPromptSession:
    """Wraps a prompt_toolkit PromptSession for AP chat.

    Parameters
    ----------
    history_path:
        Path to the persistent history file.  Defaults to ``~/.ap/chat_history``.
        Pass ``None`` to use in-memory history only (for tests / CI).
    editing_mode:
        ``"vi"`` (default) or ``"emacs"``.  Can be overridden at runtime via the
        ``AP_EDITING_MODE`` environment variable.

    Usage
    -----
    >>> session = ChatPromptSession()
    >>> user_input = session.prompt("[bold cyan]ap>[/bold cyan] ")
    """

    def __init__(
        self,
        history_path: Path | None = HISTORY_PATH,
        editing_mode: str = "vi",
    ) -> None:
        # Environment variable takes precedence over the argument
        env_mode = os.environ.get("AP_EDITING_MODE", "").lower()
        if env_mode in ("vi", "emacs"):
            editing_mode = env_mode

        self._editing_mode: EditingMode = (
            EditingMode.VI if editing_mode.lower() == "vi" else EditingMode.EMACS
        )

        # Build history — FileHistory when a path is given, in-memory fallback
        if history_path is not None:
            try:
                history_path.parent.mkdir(parents=True, exist_ok=True)
                history = FileHistory(str(history_path))
            except OSError:
                # Fall back to in-memory if the history file can't be created
                history = InMemoryHistory()
        else:
            history = InMemoryHistory()

        self._session: PromptSession = PromptSession(
            history=history,
            completer=APCompleter(),
            auto_suggest=AutoSuggestFromHistory(),
            editing_mode=self._editing_mode,
            # Keep completion UI clean — don't complete on every keystroke
            complete_while_typing=False,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def prompt(self, prefix: str = "ap> ") -> str:
        """Read a line of input from the terminal.

        Parameters
        ----------
        prefix:
            The prompt prefix displayed to the user.  Rich markup is stripped
            to a plain string before passing to prompt_toolkit (prompt_toolkit
            uses its own ANSI/HTML rendering, not Rich).

        Returns
        -------
        str
            The raw input string (not stripped — callers decide).

        Raises
        ------
        EOFError:
            Propagated from prompt_toolkit when Ctrl+D is pressed.
        KeyboardInterrupt:
            Propagated when Ctrl+C is pressed.
        """
        # Strip Rich markup tags for a plain prompt string
        plain_prefix = _strip_rich_markup(prefix)
        return self._session.prompt(plain_prefix)

    @property
    def editing_mode(self) -> str:
        """Return the active editing mode name (``"vi"`` or ``"emacs"``)."""
        return "vi" if self._editing_mode == EditingMode.VI else "emacs"

    @property
    def history_path(self) -> Path | None:
        """Return the history file path, or None for in-memory history."""
        h = self._session.history
        if isinstance(h, FileHistory):
            return Path(h.filename)
        return None


# ---------------------------------------------------------------------------
# Module-level convenience function used by chat.py
# ---------------------------------------------------------------------------


def prompt_user(
    prefix: str = "ap> ",
    editing_mode: str = "vi",
    _session: ChatPromptSession | None = None,
) -> str:
    """Read a line of input from the user, with history and completion.

    This is a stateless convenience wrapper around ``ChatPromptSession`` for
    callers that don't want to manage session lifetime.  For production use
    inside ``run_chat()``, the session is created once and reused across the
    loop — pass it as ``_session`` to avoid re-building the session on every
    call.

    Parameters
    ----------
    prefix:
        The prompt prefix string (Rich markup is stripped automatically).
    editing_mode:
        Default editing mode (``"vi"`` or ``"emacs"``).  Overridden by the
        ``AP_EDITING_MODE`` env var.
    _session:
        An existing ``ChatPromptSession`` to use.  When provided, ``editing_mode``
        is ignored (the session already has a fixed mode).

    Returns
    -------
    str
        Raw user input line.

    Raises
    ------
    EOFError, KeyboardInterrupt:
        Propagated so callers can handle Ctrl+D and Ctrl+C cleanly.
    """
    session = _session or ChatPromptSession(editing_mode=editing_mode)
    return session.prompt(prefix)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


_RICH_TAG_PATTERN = _re.compile(r"\[/?[a-zA-Z0-9 _#:,!]+\]")


def _strip_rich_markup(text: str) -> str:
    """Remove Rich markup tags from *text*, leaving plain text."""
    return _RICH_TAG_PATTERN.sub("", text)
