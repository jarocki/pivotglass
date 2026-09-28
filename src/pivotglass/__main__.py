"""Entry point for ``python -m pivotglass`` and the ``pivotglass`` CLI."""
import sys

_HELP = """Pivotglass — AI-augmented threat hunting

Usage:
  pivotglass                    Launch the local Pivotglass web cockpit (default)
  pivotglass web                Launch the local Pivotglass web cockpit
  pivotglass chat               Launch the terminal AI cyberdeck
  pivotglass tui                Launch the terminal AI cyberdeck
  pivotglass basic              Launch the classic Metasploit-like REPL
  pivotglass repl               Launch the classic Metasploit-like REPL
  pivotglass migrate-home --from PATH --confirm-stopped
                        Copy a previous installation home, preserving the source
  pivotglass --version          Show the installed version
  pivotglass --help             Show this help

The AI cyberdeck combines deterministic local/API collection with LLM
synthesis. Use `pivotglass basic` or `pivotglass repl` for direct use/set/run workflows.
"""


def _run_basic() -> None:
    """Launch the classic cmd2 console."""
    from pivotglass.core.console import PivotglassConsole

    console = PivotglassConsole()
    console.cmdloop()


def main() -> None:
    """Launch Pivotglass.

    Bare ``pivotglass`` launches the primary local Pivotglass web cockpit. The terminal
    AI cyberdeck remains available through ``pivotglass chat`` / ``pivotglass tui`` and the
    classic cmd2 console through ``pivotglass basic`` / ``pivotglass repl``.

    The ``chat`` and ``tui`` subcommands require the optional ``[agent]`` dependency group:
    ``uv pip install 'pivotglass[agent]'``
    """
    args = sys.argv[1:]

    if "--version" in args:
        from pivotglass import __version__
        print(f"pivotglass {__version__}")
        return

    if any(arg in {"-h", "--help"} for arg in args):
        print(_HELP)
        return

    command = args[0].lower() if args else "web"
    if command == "migrate-home":
        import argparse
        from pathlib import Path

        from pivotglass.core.legacy_migration import migrate_home

        parser = argparse.ArgumentParser(prog="pivotglass migrate-home")
        parser.add_argument("--from", dest="source", type=Path, required=True)
        parser.add_argument("--to", dest="destination", type=Path, default=Path.home() / ".pivotglass")
        parser.add_argument("--confirm-stopped", action="store_true", required=True,
                            help="Confirm all processes using the source are stopped")
        options = parser.parse_args(args[1:])
        try:
            destination = migrate_home(options.source, options.destination)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        print(f"Copied local data to {destination}. The source was preserved.")
        return

    if command in {"basic", "repl"}:
        # cmd2 inspects argv during construction. Remove our routing token so
        # it never mistakes ``basic`` / ``repl`` for one of its own options.
        sys.argv = [sys.argv[0], *args[1:]]
        _run_basic()
        return

    if command in {"chat", "tui"}:
        if args:
            sys.argv = [sys.argv[0], *args[1:]]
        from pivotglass.agent.chat import run_chat
        run_chat()
        return

    if command == "web":
        if args:
            sys.argv = [sys.argv[0], *args[1:]]
        from pivotglass.web.server import run_web

        run_web()
        return

    print(f"Unknown command: {args[0]}", file=sys.stderr)
    print("Run `pivotglass --help` for available interfaces.", file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
