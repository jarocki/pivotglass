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

@decision DEC-AGENT-CHAT-002
@title mode meta-command mirrors APConsole.do_mode — parsed before LLM dispatch
@status accepted
@rationale Character mode switching must be handled locally (not sent to the
           LLM) so the mode state change is immediate and deterministic. The
           command surface matches cmd2 APConsole.do_mode: 'mode' alone lists
           available modes with the active one marked; 'mode list' is an alias;
           'mode <name>' switches via ModeManager.switch(name) and then calls
           runner.set_character(active_mode) to update the LLM system prompt.
           Unknown names show an error without changing state. The prompt prefix
           reflects the active mode's prompt_prefix so the user sees the persona
           in every input line. Mirrors DEC-CONSOLE-004 for the agent path.
"""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table


def run_chat() -> None:
    """Run the conversational CTI interface.

    Starts an interactive terminal chat session using AgentRunner.
    Prints a welcome banner, then loops reading user input until the user
    types 'quit', 'exit', or sends EOF (Ctrl+D).

    Meta-commands (handled locally, not sent to the LLM):
      workspace <name>         -- switch active workspace
      mode                     -- list available character modes
      mode list                -- list available character modes
      mode <name>              -- switch to named character mode
    """
    console = Console()

    console.print(
        Panel.fit(
            "[bold green]Adversary Pursuit[/bold green] v2 — Conversational CTI",
            subtitle="Type 'quit' to exit | 'workspace <name>' | 'mode <name>'",
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

    def _mode_prompt() -> str:
        """Return a prompt string reflecting the active mode's prefix."""
        prefix = runner.ctx.mode_mgr.active.prompt_prefix
        return f"{prefix}[bold cyan]ap>[/bold cyan] "

    while True:
        try:
            user_input = console.input(_mode_prompt())
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

        # Mode meta-command — mirrors APConsole.do_mode (DEC-AGENT-CHAT-002)
        lower = stripped.lower()
        if lower == "mode" or lower == "mode list":
            # List all available modes, mark the active one
            mode_mgr = runner.ctx.mode_mgr
            current = mode_mgr.active
            table = Table(title="Character Modes", show_header=True)
            table.add_column("", style="bold green", width=2)
            table.add_column("Mode", style="cyan")
            table.add_column("Personality")
            for entry in mode_mgr.list_modes():
                marker = "*" if entry["name"] == current.name else ""
                table.add_row(marker, entry["name"], entry["personality"])
            console.print(table)
            console.print(f"\n[dim]Active: [bold]{current.name}[/bold][/dim]")
            continue

        if lower.startswith("mode "):
            mode_name = stripped[5:].strip()
            if mode_name:
                mode_mgr = runner.ctx.mode_mgr
                try:
                    new_mode = mode_mgr.switch(mode_name)
                except ValueError as e:
                    console.print(f"[yellow]Error: {e}[/yellow]")
                    continue
                # Update the LLM system prompt with the new persona
                runner.set_character(new_mode)
                console.print(
                    Panel(
                        f"[bold]{new_mode.name}[/bold]\n{new_mode.greeting}\n\n"
                        f"[dim]{new_mode.personality}[/dim]",
                        title=f"[bold green]Mode switched: {new_mode.name}[/bold green]",
                        style="green",
                    )
                )
            continue

        # Normal chat — send to LLM
        try:
            with console.status("[bold green]Thinking...[/bold green]"):
                response = runner.chat(stripped)
            console.print(Markdown(response))
            console.print()
            # Render celebration panels after the LLM response — one per tool
            # call that awarded points. The celebration is for the user, not
            # the LLM, so it is displayed here (outside the tool result loop)
            # mirroring cmd2's _execute_hunt() pattern where Rich panels appear
            # after results are displayed and stored. Silent when no points
            # were awarded (runner.last_celebrations will be empty).
            for celebration_art in getattr(runner, "last_celebrations", []):
                console.print(
                    Panel(
                        celebration_art,
                        title="[bold yellow]Achievement Unlocked[/bold yellow]",
                        style="yellow",
                        width=60,
                    )
                )
            # Render badge panels after celebrations — one per newly-earned badge.
            # Mirrors cmd2 APConsole._check_badges_after_run() rarity-styled panels.
            # Silent when no new badges earned (runner.last_badges will be empty).
            _BADGE_RARITY_COLORS = {
                "common": "white",
                "uncommon": "green",
                "rare": "blue",
                "epic": "magenta",
                "legendary": "bold yellow",
            }
            for badge in getattr(runner, "last_badges", []):
                color = _BADGE_RARITY_COLORS.get(badge.rarity.value, "white")
                console.print(
                    Panel(
                        f"[bold]{badge.name}[/bold] [{color}]({badge.rarity.value.upper()})[/{color}]\n"
                        f"{badge.description}",
                        title="[bold yellow]Badge Earned![/bold yellow]",
                        style="yellow",
                    )
                )
        except ImportError as e:
            console.print(f"[red]Missing dependency: {e}[/red]")
            console.print(
                "[yellow]Install with: uv pip install 'adversary-pursuit[agent]'[/yellow]"
            )
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
