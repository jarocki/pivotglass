"""Shared deterministic completion grammar for AP command surfaces."""

from __future__ import annotations

from collections.abc import Iterable

TOP_LEVEL_COMMANDS: tuple[str, ...] = (
    "workspace",
    "mode",
    "hint",
    "autopivot",
    "challenges",
    "badges",
    "search",
    "graph",
    "dossier",
    "gaps",
    "timeline",
    "note",
    "export",
    "report",
    "analysis",
    "help",
    "model",
    "config",
    "theme",
    "status",
    "clear",
    "use",
    "stop",
    "focus",
    "add",
    "skip",
    "quit",
    "exit",
    "?",
)

MODULE_NAMES: tuple[str, ...] = (
    "shodan",
    "abuseipdb",
    "virustotal",
    "censys",
    "urlscan",
    "hibp",
    "otx",
    "passivetotal",
    "greynoise",
    "urlhaus",
    "threatfox",
    "malwarebazaar",
    "crtsh",
)


def command_completions(
    text: str,
    *,
    mode_names: Iterable[str] = (),
    workspace_names: Iterable[str] = (),
) -> list[str]:
    """Return full command-line candidates matching *text*.

    The result is intentionally UI-agnostic: prompt_toolkit replaces the
    current line, while Pivotglass displays the same strings in a listbox.
    """
    leading = text.lstrip()
    normalized = leading.casefold()
    if " " not in leading:
        return [
            command for command in TOP_LEVEL_COMMANDS if command.casefold().startswith(normalized)
        ]

    command, remainder = leading.split(" ", 1)
    command = command.casefold()
    prefix = remainder.casefold()
    choices: list[str]
    if command == "mode":
        choices = ["list", *mode_names]
    elif command == "hint":
        choices = [*MODULE_NAMES, "buy"]
    elif command == "export":
        choices = ["json", "csv", "gexf", "stix"]
    elif command == "model":
        choices = [
            "show",
            "providers",
            "list",
            "check",
            "select",
            "enable",
            "disable",
            "repair",
            "configure",
            "advisor on",
            "advisor off",
        ]
    elif command == "config":
        choices = [
            "show",
            "check ",
            "enable ",
            "disable ",
            "repair",
            "configure",
        ]
    elif command == "theme":
        choices = ["light", "dark", "high"]
    elif command == "report":
        choices = ["answer", "generate"]
    elif command == "analysis":
        choices = [
            "show",
            "lifecycle",
            "methods",
            "contradictions",
            "priorities",
            "question ",
            "assertion ",
            "assumption ",
            "hypothesis ",
            "prediction ",
            "signpost ",
            "collect ",
            "requirement ",
            "prioritize ",
            "stop ",
            "limitation ",
            "gap ",
            "conclude ",
            "status ",
            "item ",
            "contradiction ",
            "resolve ",
            "method list",
            "method start ",
            "method complete ",
            "method accept ",
            "method reject ",
            "method revise ",
            "accept ",
            "reject ",
            "suspend ",
            "confidence ",
            "likelihood ",
        ]
    elif command == "autopivot":
        choices = ["on", "off"]
    elif command == "workspace":
        subcommands = [
            "list",
            "create ",
            "switch ",
            "schema",
            "schema ",
            "export ",
            "merge ",
            "delete ",
        ]
        choices = list(subcommands)
        for action in ("switch", "schema", "export"):
            choices.extend(f"{action} {name}" for name in workspace_names)
        choices.extend(f"merge {name} " for name in workspace_names)
        choices.extend(f"delete {name} --confirm {name}" for name in workspace_names)
    else:
        return []

    return [
        f"{command} {choice}"
        for choice in dict.fromkeys(choices)
        if choice.casefold().startswith(prefix)
    ]
