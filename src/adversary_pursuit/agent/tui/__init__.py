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
"""

from adversary_pursuit.agent.tui.application import TuiApplication

__all__ = ["TuiApplication"]
