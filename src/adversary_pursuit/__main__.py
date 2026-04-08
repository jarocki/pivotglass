"""Entry point for `python -m adversary_pursuit`."""
import sys


def main() -> None:
    """Launch Adversary Pursuit."""
    from rich.console import Console
    from adversary_pursuit import __version__
    console = Console()
    console.print(f"[bold green]Adversary Pursuit[/bold green] v{__version__}")
    console.print("[dim]Type 'help' for available commands.[/dim]")
    # Console REPL will be wired in Issue #2
    console.print("[yellow]Console not yet implemented. Coming in Issue #2.[/yellow]")


if __name__ == "__main__":
    main()
