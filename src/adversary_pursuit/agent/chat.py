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
      workspace <name>              -- switch active workspace
      mode                          -- list available character modes
      mode list                     -- list available character modes
      mode <name>                   -- switch to named character mode
      hint                          -- get next free hint (general)
      hint <module>                 -- get next free hint for a specific module
      hint buy                      -- buy the next paid hint (costs score points)
      hint buy <module>             -- buy the next paid module-specific hint
      report                        -- show interview status (auto-starts if not started)
      report answer <idx> <text>    -- record answer for question index 0-4
      report generate               -- generate and display Markdown report
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

        # Hint meta-command — mirrors APConsole.do_hint (DEC-AGENT-HINTS-001).
        # Handled locally so hint state changes are immediate and deterministic.
        # Shares the same HintProvider instance on runner.ctx so revealed-ID set
        # is consistent with the LLM tool path (DEC-HINT-002).
        #
        # Supported forms:
        #   hint                 → next free general hint
        #   hint <module>        → next free hint for that module
        #   hint buy             → next paid general hint (deducts score)
        #   hint buy <module>    → next paid hint for that module
        if lower == "hint" or lower.startswith("hint "):
            hint_mgr = runner.ctx.hint_mgr
            workspace_mgr = runner.ctx.workspace_mgr
            rest = stripped[4:].strip() if len(stripped) > 4 else ""

            buy_mode = rest.lower().startswith("buy")
            if buy_mode:
                # "hint buy" or "hint buy <module>"
                module_arg = rest[3:].strip() or None
                try:
                    current_score = workspace_mgr.get_total_score()
                except Exception as e:
                    console.print(f"[red]Error reading score: {e}[/red]")
                    continue
                try:
                    from adversary_pursuit.gamification.hints import (
                        InsufficientBalanceError,
                    )

                    result = hint_mgr.buy_hint(
                        current_score=current_score, module=module_arg
                    )
                except InsufficientBalanceError as exc:
                    console.print(
                        f"[yellow]Not enough points: need {exc.required} pts "
                        f"but have {exc.available} pts.[/yellow]"
                    )
                    continue
                except Exception as e:
                    console.print(f"[red]Error buying hint: {e}[/red]")
                    continue

                if result is None:
                    ctx_label = f" for '{module_arg}'" if module_arg else ""
                    console.print(
                        f"[dim]No more paid hints available{ctx_label}.[/dim]"
                    )
                    continue

                # Persist score deduction (DEC-HINT-001: caller owns deduction)
                try:
                    workspace_mgr.store_score_events(
                        [
                            {
                                "action": "hint",
                                "points": -result.cost_paid,
                                "indicator": module_arg or "general",
                                "rule_description": f"Paid hint: {result.hint.id}",
                            }
                        ]
                    )
                except Exception as e:
                    console.print(
                        f"[yellow]Warning: score deduction failed: {e}[/yellow]"
                    )

                # Render with mode-flavored header
                mode_name = runner.ctx.mode_mgr.active.name
                panel_title = f"[bold cyan]Hint (-{result.cost_paid} pts)[/bold cyan]"
                console.print(
                    Panel(
                        result.hint.text,
                        title=panel_title,
                        subtitle=f"[dim]{mode_name}[/dim]",
                        style="cyan",
                    )
                )
            else:
                # Free hint: "hint" or "hint <module>"
                module_arg = rest or None
                result = hint_mgr.get_next_hint(module=module_arg)
                if result is None:
                    ctx_label = f" for '{module_arg}'" if module_arg else ""
                    console.print(
                        f"[dim]No more free hints available{ctx_label}. "
                        f"Try 'hint buy' for paid hints.[/dim]"
                    )
                    continue

                mode_name = runner.ctx.mode_mgr.active.name
                console.print(
                    Panel(
                        result.hint.text,
                        title="[bold cyan]Hint (free)[/bold cyan]",
                        subtitle=f"[dim]{mode_name}[/dim]",
                        style="cyan",
                    )
                )
            continue

        # Autopivot meta-command — mirrors DEC-EVENTBUS-002 opt-in toggle.
        # Handled locally (not sent to LLM) so state changes are immediate.
        # Supported forms:
        #   autopivot          → show current state
        #   autopivot on       → enable EventBus cascade execution
        #   autopivot off      → disable EventBus cascade execution
        if lower == "autopivot" or lower.startswith("autopivot "):
            sub = stripped[9:].strip().lower() if len(stripped) > 9 else ""
            if sub == "on":
                runner.ctx.set_autopivot(True)
                console.print(
                    "[green]Auto-pivot enabled.[/green] Cascading modules will fire on discoveries."
                )
            elif sub == "off":
                runner.ctx.set_autopivot(False)
                console.print(
                    "[yellow]Auto-pivot disabled.[/yellow] Running modules manually only."
                )
            else:
                # Status display
                state = "on" if runner.ctx.autopivot_enabled else "off"
                color = "green" if runner.ctx.autopivot_enabled else "yellow"
                console.print(
                    f"Auto-pivot is [{color}]{state}[/{color}]. "
                    f"Use [bold]autopivot on[/bold] or [bold]autopivot off[/bold] to toggle."
                )
            continue

        # Challenges meta-command — mirrors APConsole.do_challenges (DEC-AGENT-CHALLENGES-001).
        # Handled locally (not sent to LLM) so the list is always deterministic and fast.
        # Shares the same ChallengeManager instance on runner.ctx so completion state
        # is consistent with the LLM tool path and the auto-check in run_module().
        #
        # Supported form:
        #   challenges           → list all challenges with current status
        if lower == "challenges":
            items = runner.ctx.challenge_mgr.list_challenges()
            table = Table(title="Challenges", show_header=True)
            table.add_column("ID", style="cyan")
            table.add_column("Name", style="bold")
            table.add_column("Type", style="yellow")
            table.add_column("Points", style="green", justify="right")
            table.add_column("Status", style="white")
            table.add_column("Description")
            for item in items:
                status = item["status"]
                if status == "completed":
                    status_str = "[green]completed[/green]"
                elif status == "expired":
                    status_str = "[red]expired[/red]"
                else:
                    status_str = "[blue]active[/blue]"
                table.add_row(
                    item["id"],
                    item["name"],
                    item["challenge_type"],
                    str(item["points"]),
                    status_str,
                    item["description"],
                )
            console.print(table)
            continue

        # Graph meta-command — mirrors APConsole.do_graph (DEC-AGENT-GRAPH-EXPORT-001).
        # Handled locally (not sent to LLM) for immediate, deterministic output.
        # Shares ToolContext.workspace_mgr so the graph reflects the live workspace.
        #
        # Supported form:
        #   graph            → render workspace relationship graph as Rich Tree
        if lower == "graph":
            from adversary_pursuit.core.graph import RelationshipGraph

            try:
                raw_objects = runner.ctx.workspace_mgr.get_stix_objects()
            except Exception as e:
                console.print(f"[red]Error reading workspace: {e}[/red]")
                continue
            g = RelationshipGraph()
            g.build_from_workspace(raw_objects)
            if g.node_count == 0:
                console.print("[dim]No objects in workspace. Run a module first.[/dim]")
            else:
                tree = g.render_tree()
                console.print(tree)
                stats = g.get_stats()
                console.print(
                    f"\n[dim]{stats['node_count']} nodes, {stats['edge_count']} edges[/dim]"
                )
            continue

        # Export meta-command — mirrors APConsole.do_export (DEC-AGENT-GRAPH-EXPORT-001).
        # Handled locally for deterministic output, no LLM involvement.
        #
        # Supported forms:
        #   export gexf      → print GEXF 1.2 XML to terminal
        #   export stix      → print STIX 2.1 bundle JSON to terminal
        if lower == "export gexf" or lower == "export stix":
            from adversary_pursuit.core.graph import RelationshipGraph

            fmt = stripped.split()[-1].lower()  # "gexf" or "stix"
            try:
                raw_objects = runner.ctx.workspace_mgr.get_stix_objects()
            except Exception as e:
                console.print(f"[red]Error reading workspace: {e}[/red]")
                continue
            if not raw_objects:
                console.print(
                    "[dim]No objects in workspace to export. Run a module first.[/dim]"
                )
                continue
            g = RelationshipGraph()
            g.build_from_workspace(raw_objects)
            if fmt == "gexf":
                console.print(g.export_gexf())
            else:
                import json as _json

                bundle = g.export_stix_bundle()
                console.print(_json.dumps(bundle, indent=2))
            continue

        # Report meta-command — mirrors APConsole.do_report (DEC-AGENT-REPORT-001).
        # Handled locally (not sent to LLM) for deterministic, immediate output.
        # Shares the same ReportGenerator instance on runner.ctx so answers set here
        # are visible to the LLM tool path (start_report_interview / answer_report_question
        # / generate_report) and vice versa.
        #
        # Supported forms:
        #   report                         → show current interview status (questions + answers)
        #   report answer <idx> <text>     → set answer for question index idx (0-4)
        #   report generate                → generate and print the Markdown report
        if lower == "report" or lower.startswith("report "):
            from adversary_pursuit.agent.tools import (
                _execute_answer_report_question,
                _execute_generate_report,
                _execute_start_report_interview,
            )

            rest = stripped[6:].strip() if len(stripped) > 6 else ""
            rest_lower = rest.lower()

            if rest_lower == "generate":
                # Generate and render the Markdown report
                report_md = _execute_generate_report(runner.ctx)
                if report_md.startswith("Report interview") or report_md.startswith(
                    "Error"
                ):
                    console.print(f"[yellow]{report_md}[/yellow]")
                else:
                    console.print(
                        Panel(
                            Markdown(report_md),
                            title="[bold green]Investigation Report[/bold green]",
                            style="green",
                        )
                    )

            elif rest_lower.startswith("answer "):
                # 'report answer <idx> <text>'
                args_str = rest[7:].strip()  # everything after "answer "
                parts = args_str.split(None, 1)
                if len(parts) < 2:
                    console.print(
                        "[yellow]Usage: report answer <index> <answer text>[/yellow]"
                    )
                else:
                    try:
                        idx = int(parts[0])
                    except ValueError:
                        console.print(
                            f"[yellow]Invalid index '{parts[0]}': must be 0-4[/yellow]"
                        )
                    else:
                        # Lazily initialise if not yet started
                        if runner.ctx.report_generator is None:
                            _execute_start_report_interview(runner.ctx)
                        result = _execute_answer_report_question(
                            runner.ctx, idx, parts[1]
                        )
                        console.print(f"[green]{result}[/green]")

            else:
                # 'report' with no subcommand — show interview status
                rg = runner.ctx.report_generator
                if rg is None:
                    # Auto-start interview on bare 'report' command (mirrors do_report)
                    _execute_start_report_interview(runner.ctx)
                    rg = runner.ctx.report_generator

                table = Table(
                    title="Report Interview",
                    show_header=True,
                    show_lines=True,
                )
                table.add_column("#", style="cyan", width=3)
                table.add_column("Question", style="bold", ratio=2)
                table.add_column("Answer", ratio=3)
                for i, section in enumerate(rg.sections):
                    answer_display = (
                        section.answer.strip()
                        if section.answer.strip()
                        else "[dim]_not answered_[/dim]"
                    )
                    table.add_row(str(i), section.question, answer_display)
                console.print(table)
                console.print(
                    "[dim]Use [bold]report answer <idx> <text>[/bold] to set answers, "
                    "then [bold]report generate[/bold] to produce the report.[/dim]"
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
