"""Safe workspace export and merge operations outside the core manager.

WorkspaceManager remains the single authority for lifecycle and active-state
changes.  This module provides transactional administration over its SQLite
files without weakening its deliberately small public contract.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

_TABLES = (
    "stix_objects",
    "relationships",
    "module_runs",
    "score_events",
    "badge_events",
    "notes",
)


def _path(manager: Any, name: str) -> Path:
    # _db_path performs the manager's canonical name validation.
    return manager._db_path(name)


def export_workspace(manager: Any, name: str) -> dict[str, Any]:
    """Return a portable, deterministic JSON projection of one workspace."""
    path = _path(manager, name)
    if not path.exists():
        raise ValueError(f"workspace does not exist: {name}")
    result: dict[str, Any] = {"format": "ap-workspace-v1", "workspace": name, "tables": {}}
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        for table in _TABLES:
            rows = [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY rowid")]  # noqa: S608
            for row in rows:
                if "json_blob" in row and isinstance(row["json_blob"], str):
                    row["json_blob"] = json.loads(row["json_blob"])
            result["tables"][table] = rows
    return result


def merge_workspaces(manager: Any, source: str, destination: str) -> dict[str, int]:
    """Transactionally merge source evidence into destination.

    Natural evidence IDs and relationship IDs are deduplicated. Audit/event
    rows are appended because their local integer IDs have no cross-workspace
    meaning. The source is never modified.
    """
    if source == destination:
        raise ValueError("source and destination workspaces must differ")
    source_path, destination_path = _path(manager, source), _path(manager, destination)
    if not source_path.exists():
        raise ValueError(f"workspace does not exist: {source}")
    if not destination_path.exists():
        raise ValueError(f"workspace does not exist: {destination}")

    counts: dict[str, int] = {}
    with sqlite3.connect(destination_path) as db:
        db.execute("ATTACH DATABASE ? AS source_workspace", (str(source_path),))
        try:
            db.execute("BEGIN IMMEDIATE")
            for table in ("stix_objects", "relationships"):
                before = db.total_changes
                db.execute(f"INSERT OR IGNORE INTO main.{table} SELECT * FROM source_workspace.{table}")  # noqa: S608
                counts[table] = db.total_changes - before
            for table in ("module_runs", "score_events", "badge_events", "notes"):
                columns = [
                    row[1]
                    for row in db.execute(f"PRAGMA main.table_info({table})")  # noqa: S608
                    if row[1] != "id"
                ]
                names = ", ".join(columns)
                before = db.total_changes
                db.execute(
                    f"INSERT INTO main.{table} ({names}) "  # noqa: S608
                    f"SELECT {names} FROM source_workspace.{table}"
                )
                counts[table] = db.total_changes - before
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.execute("DETACH DATABASE source_workspace")
    return counts
