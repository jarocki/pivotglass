"""Entry point for `python -m adversary_pursuit` and the `ap` CLI script."""
import sys


def main() -> None:
    """Launch Adversary Pursuit.

    Dispatch table:
    - ``--version``: print version and exit
    - ``chat``: launch the conversational CTI interface (requires litellm)
    - (default): launch the interactive cmd2 REPL

    The ``chat`` subcommand requires the optional ``[agent]`` dependency group:
    ``uv pip install 'adversary-pursuit[agent]'``
    """
    if "--version" in sys.argv:
        from adversary_pursuit import __version__
        print(f"adversary-pursuit {__version__}")
        return

    if len(sys.argv) > 1 and sys.argv[1] == "chat":
        from adversary_pursuit.agent.chat import run_chat
        run_chat()
        return

    # Default: legacy cmd2 console
    from adversary_pursuit.core.console import APConsole
    console = APConsole()
    console.cmdloop()


if __name__ == "__main__":
    main()
