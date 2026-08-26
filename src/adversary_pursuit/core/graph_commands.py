"""Shared graph-workspace command adapter for terminal and web interfaces."""

from __future__ import annotations

import json
from typing import Any

from adversary_pursuit.core.investigation_graph import (
    GraphPresentationAuthority,
    build_investigation_graph,
)

_USAGE = (
    "usage: graph layers|layout list|layout show <name>|"
    "layout save <name> | <layout-json>|layout delete <name> --confirm <name>|"
    "annotate <node-id> | <text>|annotations [node-id]"
)


def execute_graph_command(args: tuple[str, ...], workspace_manager: Any) -> dict[str, Any]:
    """Execute one deterministic graph workspace command."""

    if not args:
        raise ValueError(_USAGE)
    command = args[0].casefold()
    authority = GraphPresentationAuthority(workspace_manager)
    if command == "layers" and len(args) == 1:
        return {
            "action": "layers",
            "graph": build_investigation_graph(workspace_manager).model_dump(mode="json"),
        }
    if command == "layout":
        return _execute_layout(tuple(args[1:]), authority)
    if command == "annotate":
        payload = " ".join(args[1:])
        node_id, separator, content = payload.partition("|")
        if not separator:
            raise ValueError("usage: graph annotate <node-id> | <text>")
        record = authority.annotate(node_id.strip(), content.strip())
        return {"action": "annotated", "annotation": record.model_dump(mode="json")}
    if command == "annotations":
        if len(args) > 2:
            raise ValueError("usage: graph annotations [node-id]")
        records = authority.annotations(args[1] if len(args) == 2 else None)
        return {
            "action": "annotations",
            "annotations": [record.model_dump(mode="json") for record in records],
        }
    raise ValueError(_USAGE)


def _execute_layout(
    args: tuple[str, ...],
    authority: GraphPresentationAuthority,
) -> dict[str, Any]:
    if args == ("list",):
        return {
            "action": "layout-list",
            "layouts": [record.model_dump(mode="json") for record in authority.list()],
        }
    if len(args) >= 2 and args[0].casefold() == "show":
        name = " ".join(args[1:])
        return {
            "action": "layout-show",
            "layout": authority.get(name).model_dump(mode="json"),
        }
    if len(args) >= 2 and args[0].casefold() == "save":
        payload = " ".join(args[1:])
        name, separator, encoded = payload.partition("|")
        if not separator:
            raise ValueError("usage: graph layout save <name> | <layout-json>")
        try:
            draft = json.loads(encoded)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid graph layout JSON: {exc.msg}") from exc
        if not isinstance(draft, dict):
            raise ValueError("graph layout JSON must be an object")
        record = authority.save(name.strip(), draft)
        return {"action": "layout-saved", "layout": record.model_dump(mode="json")}
    if len(args) >= 4 and args[0].casefold() == "delete":
        lowered = [part.casefold() for part in args]
        try:
            marker = lowered.index("--confirm")
        except ValueError as exc:
            raise ValueError("usage: graph layout delete <name> --confirm <name>") from exc
        name = " ".join(args[1:marker])
        confirm = " ".join(args[marker + 1 :])
        if not name or not confirm:
            raise ValueError("usage: graph layout delete <name> --confirm <name>")
        authority.delete(name, confirm=confirm)
        return {"action": "layout-deleted", "name": name}
    raise ValueError(
        "usage: graph layout list|show <name>|save <name> | <layout-json>|"
        "delete <name> --confirm <name>"
    )
