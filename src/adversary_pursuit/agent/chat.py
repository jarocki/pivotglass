"""Minimal terminal chat interface for AP agent.

Provides a Rich-based interactive REPL that wraps AgentRunner.
Launched via `ap chat` or `python -m adversary_pursuit chat`.

@decision DEC-AGENT-CHAT-001
@title Minimal Rich REPL — no readline/prompt_toolkit complexity
@status accepted
@rationale The chat interface is a thin shell around AgentRunner. Rich's
           console.input() + status spinner is sufficient for a v1 terminal
           chat. Prompt_toolkit (used by cmd2) would add complexity without
           meaningful benefit at this stage. The existing cmd2 console
           (APConsole) handles the structured `use/set/run` workflow; chat.py
           handles the conversational interface.
"""
from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel


def run_chat() -> None:
    """Run the conversational CTI interface.

    Starts an interactive terminal chat session using AgentRunner.
    Prints a welcome banner, then loops reading user input until the user
    types 'quit', 'exit', or sends EOF (Ctrl+D).

    The user can switch workspaces by typing 'workspace <name>' as a
    meta-command (handled locally, not sent to the LLM).
    """
    console = Console()

    console.print(
        Panel.fit(
            "[bold green]Adversary Pursuit[/bold green] v2 — Conversational CTI",
            subtitle="Type 'quit' to exit, 'workspace <name>' to switch workspace",
        )
    )

    try:
        from adversary_pursuit.agent.runner import AgentRunner
        runner = AgentRunner()
        console.print("[dim]Agent ready. Ask me about any indicator.[/dim]\n")
    except ImportError as e:
        console.print(f"[red]Missing dependency: {e}[/red]")
        console.print(
            "[yellow]Install with: uv pip install 'adversary-pursuit[agent]'[/yellow]"
        )
        return

    while True:
        try:
            user_input = console.input("[bold cyan]ap>[/bold cyan] ")
        except (EOFError, KeyboardInterrupt):
            console.print("\nBye!")
            break

        stripped = user_input.strip()
        if not stripped:
            continue

        # Handle local meta-commands (not sent to LLM)
        if stripped.lower() in ("quit", "exit"):
            console.print("Bye!")
            break

        if stripped.lower().startswith("workspace "):
            workspace_name = stripped[10:].strip()
            if workspace_name:
                try:
                    runner.ctx.workspace_mgr.switch(workspace_name)
                    console.print(
                        f"[green]Switched to workspace: {workspace_name}[/green]"
                    )
                except ValueError as e:
                    console.print(f"[yellow]{e}[/yellow]")
            continue

        # Normal chat — send to LLM
        try:
            with console.status("[bold green]Thinking...[/bold green]"):
                response = runner.chat(stripped)
            console.print(Markdown(response))
            console.print()
        except ImportError as e:
            console.print(f"[red]Missing dependency: {e}[/red]")
            console.print(
                "[yellow]Install with: uv pip install 'adversary-pursuit[agent]'[/yellow]"
            )
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
