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

from sqlalchemy import create_engine

from adversary_pursuit.core.workspace_migrations import (
    ensure_workspace_schema,
    get_workspace_schema_version,
)

_EXPORT_TABLES = (
    "workspace_schema_version",
    "stix_objects",
    "relationships",
    "module_runs",
    "score_events",
    "badge_events",
    "notes",
    "evidence_sources",
    "evidence_observations",
    "evidence_observation_dispositions",
    "investigation_questions",
    "analytic_assertions",
    "analytic_hypotheses",
    "analytic_evidence_links",
    "analytic_method_runs",
    "analytic_confidence_assessments",
    "likelihood_assessments",
    "analytic_contradictions",
)
_JSON_COLUMNS = {"json_blob", "observed_blob", "factors", "input_blob", "output_blob"}
_STRING_KEY_TABLES = (
    "stix_objects",
    "relationships",
    "evidence_sources",
    "investigation_questions",
    "analytic_assertions",
    "analytic_hypotheses",
    "analytic_method_runs",
    "analytic_confidence_assessments",
    "likelihood_assessments",
    "analytic_contradictions",
    "evidence_observation_dispositions",
)


def _path(manager: Any, name: str) -> Path:
    # _db_path performs the manager's canonical name validation.
    return manager._db_path(name)


def export_workspace(manager: Any, name: str) -> dict[str, Any]:
    """Return a portable, deterministic JSON projection of one workspace."""
    path = _path(manager, name)
    if not path.exists():
        raise ValueError(f"workspace does not exist: {name}")
    engine = create_engine(f"sqlite:///{path}")
    try:
        ensure_workspace_schema(engine, path)
        schema_version = get_workspace_schema_version(engine)
    finally:
        engine.dispose()
    result: dict[str, Any] = {
        "format": "pivotglass-workspace-v2",
        "workspace": name,
        "schema_version": schema_version,
        "tables": {},
    }
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        for table in _EXPORT_TABLES:
            rows = [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY rowid")]  # noqa: S608
            for row in rows:
                for column in _JSON_COLUMNS & row.keys():
                    if isinstance(row[column], str):
                        row[column] = json.loads(row[column])
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

    for path in (source_path, destination_path):
        engine = create_engine(f"sqlite:///{path}")
        try:
            ensure_workspace_schema(engine, path)
        finally:
            engine.dispose()

    counts: dict[str, int] = {}
    with sqlite3.connect(destination_path) as db:
        db.execute("ATTACH DATABASE ? AS source_workspace", (str(source_path),))
        try:
            db.execute("BEGIN IMMEDIATE")
            for table in _STRING_KEY_TABLES:
                before = db.total_changes
                db.execute(f"INSERT OR IGNORE INTO main.{table} SELECT * FROM source_workspace.{table}")  # noqa: S608
                counts[table] = db.total_changes - before

            module_run_map: dict[int, int] = {}
            module_columns = [
                row[1]
                for row in db.execute("PRAGMA main.table_info(module_runs)")
                if row[1] != "id"
            ]
            module_names = ", ".join(module_columns)
            before = db.total_changes
            for row in db.execute(
                f"SELECT id, {module_names} FROM source_workspace.module_runs ORDER BY id"  # noqa: S608
            ).fetchall():
                cursor = db.execute(
                    f"INSERT INTO main.module_runs ({module_names}) "  # noqa: S608
                    f"VALUES ({', '.join('?' for _ in module_columns)})",
                    tuple(row[1:]),
                )
                module_run_map[int(row[0])] = int(cursor.lastrowid)
            counts["module_runs"] = db.total_changes - before

            observation_columns = [
                row[1] for row in db.execute("PRAGMA main.table_info(evidence_observations)")
            ]
            observation_names = ", ".join(observation_columns)
            observation_placeholders = ", ".join("?" for _ in observation_columns)
            module_index = observation_columns.index("module_run_id")
            before = db.total_changes
            for row in db.execute(
                f"SELECT {observation_names} "  # noqa: S608
                "FROM source_workspace.evidence_observations ORDER BY rowid"
            ).fetchall():
                values = list(row)
                old_run_id = values[module_index]
                if old_run_id is not None:
                    values[module_index] = module_run_map[int(old_run_id)]
                db.execute(
                    f"INSERT OR IGNORE INTO main.evidence_observations ({observation_names}) "  # noqa: S608
                    f"VALUES ({observation_placeholders})",
                    values,
                )
            counts["evidence_observations"] = db.total_changes - before

            score_columns = [
                row[1]
                for row in db.execute("PRAGMA main.table_info(score_events)")
                if row[1] != "id"
            ]
            score_names = ", ".join(score_columns)
            score_placeholders = ", ".join("?" for _ in score_columns)
            score_run_index = score_columns.index("module_run_id")
            before = db.total_changes
            for row in db.execute(
                f"SELECT {score_names} FROM source_workspace.score_events ORDER BY id"  # noqa: S608
            ).fetchall():
                values = list(row)
                old_run_id = values[score_run_index]
                if old_run_id is not None:
                    values[score_run_index] = module_run_map.get(int(old_run_id))
                db.execute(
                    f"INSERT INTO main.score_events ({score_names}) VALUES ({score_placeholders})",  # noqa: S608
                    values,
                )
            counts["score_events"] = db.total_changes - before

            for table in ("badge_events", "notes", "analytic_evidence_links"):
                columns = [
                    row[1]
                    for row in db.execute(f"PRAGMA main.table_info({table})")  # noqa: S608
                    if row[1] != "id"
                ]
                names = ", ".join(columns)
                before = db.total_changes
                insert_clause = "INSERT OR IGNORE" if table == "analytic_evidence_links" else "INSERT"
                db.execute(
                    f"{insert_clause} INTO main.{table} ({names}) "  # noqa: S608
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
