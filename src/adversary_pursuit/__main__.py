"""Entry point for ``python -m adversary_pursuit`` and the ``ap`` CLI."""
import sys

_HELP = """Pivotglass — AI-augmented threat hunting

Usage:
  ap                    Launch the local Pivotglass web cockpit (default)
  ap web                Launch the local Pivotglass web cockpit
  ap chat               Launch the terminal AI cyberdeck
  ap tui                Launch the terminal AI cyberdeck
  ap basic              Launch the classic Metasploit-like REPL
  ap repl               Launch the classic Metasploit-like REPL
  ap --version          Show the installed version
  ap --help             Show this help

The AI cyberdeck combines deterministic local/API collection with LLM
synthesis. Use `ap basic` or `ap repl` for direct use/set/run workflows.
"""


def _run_basic() -> None:
    """Launch the classic cmd2 console."""
    from adversary_pursuit.core.console import APConsole

    console = APConsole()
    console.cmdloop()


def main() -> None:
    """Launch Adversary Pursuit.

    Bare ``ap`` launches the primary local Pivotglass web cockpit. The terminal
    AI cyberdeck remains available through ``ap chat`` / ``ap tui`` and the
    classic cmd2 console through ``ap basic`` / ``ap repl``.

    The ``chat`` and ``tui`` subcommands require the optional ``[agent]`` dependency group:
    ``uv pip install 'adversary-pursuit[agent]'``
    """
    args = sys.argv[1:]

    if "--version" in args:
        from adversary_pursuit import __version__
        print(f"adversary-pursuit {__version__}")
        return

    if any(arg in {"-h", "--help"} for arg in args):
        print(_HELP)
        return

    command = args[0].lower() if args else "web"
    if command in {"basic", "repl"}:
        # cmd2 inspects argv during construction. Remove our routing token so
        # it never mistakes ``basic`` / ``repl`` for one of its own options.
        sys.argv = [sys.argv[0], *args[1:]]
        _run_basic()
        return

    if command in {"chat", "tui"}:
        if args:
            sys.argv = [sys.argv[0], *args[1:]]
        from adversary_pursuit.agent.chat import run_chat
        run_chat()
        return

    if command == "web":
        if args:
            sys.argv = [sys.argv[0], *args[1:]]
        from adversary_pursuit.web.server import run_web

        run_web()
        return

    print(f"Unknown command: {args[0]}", file=sys.stderr)
    print("Run `ap --help` for available interfaces.", file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
