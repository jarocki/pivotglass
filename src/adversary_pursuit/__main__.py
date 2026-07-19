"""Entry point for ``python -m adversary_pursuit`` and the ``ap`` CLI."""
import sys

_HELP = """Adversary Pursuit — AI-augmented threat hunting

Usage:
  ap                    Launch the AI cyberdeck (default)
  ap chat               Launch the AI cyberdeck (compatibility alias)
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

    Bare ``ap`` launches the primary AI-augmented cyberdeck. The classic
    cmd2 console remains available through ``ap basic`` and ``ap repl``.

    The ``chat`` subcommand requires the optional ``[agent]`` dependency group:
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

    command = args[0].lower() if args else "chat"
    if command in {"basic", "repl"}:
        # cmd2 inspects argv during construction. Remove our routing token so
        # it never mistakes ``basic`` / ``repl`` for one of its own options.
        sys.argv = [sys.argv[0], *args[1:]]
        _run_basic()
        return

    if command == "chat":
        if args:
            sys.argv = [sys.argv[0], *args[1:]]
        from adversary_pursuit.agent.chat import run_chat
        run_chat()
        return

    print(f"Unknown command: {args[0]}", file=sys.stderr)
    print("Run `ap --help` for available interfaces.", file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
