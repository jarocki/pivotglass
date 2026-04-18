"""Entry point for `python -m adversary_pursuit` and the `ap` CLI script."""
import sys


def main() -> None:
    """Launch Adversary Pursuit.

    If --version is passed, print the version and exit.
    Otherwise, launch the interactive REPL.
    """
    if "--version" in sys.argv:
        from adversary_pursuit import __version__
        print(f"adversary-pursuit {__version__}")
        return

    from adversary_pursuit.core.console import APConsole
    console = APConsole()
    console.cmdloop()


if __name__ == "__main__":
    main()
