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
    "framework",
    "integration",
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
            "relation ",
            "relation-retract ",
            "relation-revise ",
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
    elif command == "framework":
        choices = [
            "list",
            "list attack",
            "list kill_chain",
            "list diamond",
            "manifest",
            "show attack",
            "show kill_chain",
            "show diamond",
            "map attack ",
            "map kill_chain ",
            "map diamond ",
            "require attack ",
            "require kill_chain ",
            "require diamond ",
            "gaps",
            "accept ",
            "reject ",
            "revoke ",
            "navigator",
        ]
    elif command == "integration":
        choices = [
            "status",
            "proposals",
            "review ",
            "materialize ",
            "synapse status",
            "synapse shadow-preview",
            "synapse cutover-readiness",
            "synapse model-contract",
            "synapse model-deploy-plan",
            "synapse model-deploy-execute ",
            "synapse model-deploy-receipt ",
            "synapse migration-plan",
            "synapse shadow-execute ",
            "synapse shadow-receipt ",
            "synapse views",
            "synapse model ",
            "synapse lookup ",
            "synapse query ",
            "scot status",
            "scot publish-preview",
            "scot publication-readiness ",
            "scot publish-plan ",
            "scot publish-execute ",
            "scot publication-receipt ",
            "scot pivot-preview ",
            "scot pivot-inbox",
            "scot pivot-accept ",
            "scot pivot-reject ",
            "scot pivot-queue",
            "scot pivot-enqueue ",
            "scot get ",
            "scot search ",
            "scot entries ",
            "scot entities ",
            "roast status",
            "roast decode ",
            "roast record ",
            "roast analyze ",
            "roast correlations",
            "nucleotide status",
            "nucleotide lookup-info",
            "nucleotide lookup ",
            "nucleotide lookup-strict ",
            "nucleotide lookup-record ",
            "nucleotide fingerprint-preview ",
            "nucleotide fingerprint-record ",
            "nucleotide fingerprint-history ",
            "nucleotide fingerprint-compare ",
        ]
    elif command == "graph":
        choices = [
            "layers",
            "clusters",
            "snapshot list",
            "snapshot capture ",
            "snapshot diff ",
            "export json all",
            "export json entity",
            "export json epistemic",
            "export json bridge",
            "export csv all",
            "export gexf all",
            "layout list",
            "layout show ",
            "layout delete ",
            "annotate ",
            "annotations",
            "annotations ",
        ]
    elif command == "autopivot":
        choices = ["on", "off"]
    elif command == "workspace":
        subcommands = [
            "list",
            "learn ",
            "create ",
            "switch ",
            "schema",
            "schema ",
            "export ",
            "merge ",
            "clear ",
            "delete ",
        ]
        choices = list(subcommands)
        for action in ("switch", "schema", "export"):
            choices.extend(f"{action} {name}" for name in workspace_names)
        choices.extend(f"merge {name} " for name in workspace_names)
        choices.extend(f"clear {name} --confirm {name}" for name in workspace_names)
        choices.extend(f"delete {name} --confirm {name}" for name in workspace_names)
    else:
        return []

    return [
        f"{command} {choice}"
        for choice in dict.fromkeys(choices)
        if choice.casefold().startswith(prefix)
    ]
