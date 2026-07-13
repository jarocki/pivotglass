"""TUI subpackage for Adversary Pursuit agent.

Provides a prompt_toolkit-based terminal user interface (TUI) that replaces
the legacy Rich REPL with a split-pane layout: scrollback history, input
field, and a live status pane.

@decision DEC-TUI-SUBPACKAGE-001
@title tui/ is a subpackage of agent/; TuiApplication is the public entry point
@status accepted
@rationale Keeps TUI concerns isolated from the rest of the agent package.
           The single public export (TuiApplication) lets chat.py switch to
           TUI mode with a single import and a try/except on NotATTYError.

@decision DEC-TUI-SUBPACKAGE-002
@title Lazy import of TuiApplication — prompt_toolkit is an optional dep
@status accepted
@rationale prompt_toolkit is required by TuiApplication but is not installed in
           all environments (CI, unit test runs without the TUI extra). Eagerly
           importing it at package-init time prevented importing any tui.* submodule
           (themes, header, events, scrollback) in those environments. Moving to
           a lazy __getattr__ import means submodules that do NOT depend on
           prompt_toolkit (themes, header, events, scrollback) import cleanly.
           TuiApplication still fails loudly at the point of first use when
           prompt_toolkit is absent — the error surfaces at the right level.
"""

from __future__ import annotations

__all__ = ["TuiApplication"]


def __getattr__(name: str):
    if name == "TuiApplication":
        from adversary_pursuit.agent.tui.application import TuiApplication

        return TuiApplication
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
