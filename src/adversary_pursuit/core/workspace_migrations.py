"""Versioned, backup-first migrations for Pivotglass workspace databases.

This module is the sole authority for workspace schema versions.  It does not
own investigation data semantics; it only moves durable databases forward and
records a receipt.  Existing v0.7 and earlier databases are treated as schema
version 1 because they predate an explicit version row.

@decision DEC-WORKSPACE-MIGRATIONS-001
@title Workspace migrations are versioned, forward-only, and backup-first
@status accepted
@rationale Investigation databases contain analyst work that cannot be assumed
           reproducible. Every schema-changing path therefore has one version
           authority, creates a recoverable sibling backup before mutation, and
           rejects unknown future versions instead of guessing compatibility.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.orm import Session

from adversary_pursuit.models.database import (
    AnalyticAssertion,
    AnalyticHypothesis,
    AnalyticInvestigation,
    AnalyticLifecycleItem,
    AnalyticMethodRun,
    Base,
    EvidenceObservation,
    EvidenceSource,
    InvestigationQuestion,
    Relationship,
    ScoreEvent,
    StixObject,
    WorkspaceSchemaVersion,
)

CURRENT_WORKSPACE_SCHEMA_VERSION = 4
LEGACY_WORKSPACE_SCHEMA_VERSION = 1
_VERSION_ROW_ID = 1


@dataclass(frozen=True)
class MigrationReceipt:
    """Result of checking or upgrading one workspace database."""

    from_version: int
    to_version: int
    migrated: bool
    backup_path: Path | None = None
    observations_backfilled: int = 0


@dataclass(frozen=True)
class MigrationPlan:
    """Read-only description of the migration that would run."""

    from_version: int
    to_version: int
    requires_migration: bool
    supported: bool
    backup_path: Path | None
    steps: tuple[str, ...]


@dataclass(frozen=True)
class SchemaValidation:
    """Integrity and contract check for an already-migrated workspace."""

    valid: bool
    version: int
    sqlite_integrity: str
    missing_tables: tuple[str, ...]


def sanitize_endpoint(value: str | None) -> str | None:
    """Return a source endpoint without query parameters, fragments, or credentials."""

    if value is None:
        return None
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname or ""
        port = parsed.port
    except ValueError:
        return None
    if not parsed.scheme or not parsed.netloc:
        return value.split("?", 1)[0].split("#", 1)[0]
    if port is not None:
        hostname = f"{hostname}:{port}"
    return urlunsplit((parsed.scheme, hostname, parsed.path, "", ""))


def source_identity(
    name: str,
    endpoint: str | None,
    api_version: str | None,
    collector_version: str | None,
    dependence_group: str | None = None,
) -> str:
    """Create a stable, non-secret source identity from sanitized metadata."""

    payload = json.dumps(
        {
            "name": name,
            "endpoint": sanitize_endpoint(endpoint),
            "api_version": api_version,
            "collector_version": collector_version,
            "dependence_group": dependence_group,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"source-{hashlib.sha256(payload.encode()).hexdigest()[:24]}"


def initialize_workspace_schema(engine: Engine) -> None:
    """Create a new workspace at the current schema version."""

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        row = session.get(WorkspaceSchemaVersion, _VERSION_ROW_ID)
        if row is None:
            session.add(
                WorkspaceSchemaVersion(
                    id=_VERSION_ROW_ID,
                    version=CURRENT_WORKSPACE_SCHEMA_VERSION,
                )
            )
        else:
            row.version = CURRENT_WORKSPACE_SCHEMA_VERSION
            row.migrated_at = datetime.now(timezone.utc)
        session.commit()


def ensure_workspace_schema(engine: Engine, db_path: Path) -> MigrationReceipt:
    """Upgrade an existing workspace and return a durable migration receipt.

    A sibling backup is created before the first schema-changing operation.
    Unknown future schema versions fail loudly instead of being opened by older
    code.  The v1 -> v2 migration creates epistemic tables and backfills one
    legacy observation for every existing STIX object and relationship. The
    v2 -> v3 step adds persisted hunt challenges and badge reward metadata. The
    v3 -> v4 step adds the scientific-investigation root and links existing
    analytic records and legacy predictions into one lifecycle.
    """

    tables = set(inspect(engine).get_table_names())
    if not tables:
        initialize_workspace_schema(engine)
        return MigrationReceipt(0, CURRENT_WORKSPACE_SCHEMA_VERSION, True)

    current = _read_schema_version(engine, tables)
    if current > CURRENT_WORKSPACE_SCHEMA_VERSION:
        raise RuntimeError(
            f"Workspace schema v{current} is newer than this Pivotglass build "
            f"(supports through v{CURRENT_WORKSPACE_SCHEMA_VERSION})."
        )
    if current == CURRENT_WORKSPACE_SCHEMA_VERSION:
        return MigrationReceipt(current, current, False)

    backup_path = _backup_path(db_path, current)
    if not backup_path.exists():
        _create_sqlite_backup(db_path, backup_path)

    original_version = current
    observations_backfilled = 0
    if current == LEGACY_WORKSPACE_SCHEMA_VERSION:
        observations_backfilled = _migrate_v1_to_v2(engine)
        current = 2
    if current == 2:  # noqa: PLR2004
        _migrate_v2_to_v3(engine)
        current = 3
    if current == 3:  # noqa: PLR2004
        _migrate_v3_to_v4(engine)
        current = 4

    if current != CURRENT_WORKSPACE_SCHEMA_VERSION:
        raise RuntimeError(
            f"No migration path from workspace schema v{current} "
            f"to v{CURRENT_WORKSPACE_SCHEMA_VERSION}."
        )

    return MigrationReceipt(
        from_version=original_version,
        to_version=current,
        migrated=True,
        backup_path=backup_path,
        observations_backfilled=observations_backfilled,
    )


def plan_workspace_migration(engine: Engine, db_path: Path) -> MigrationPlan:
    """Inspect a workspace without changing it and describe the forward path."""

    tables = set(inspect(engine).get_table_names())
    if not tables:
        return MigrationPlan(
            from_version=0,
            to_version=CURRENT_WORKSPACE_SCHEMA_VERSION,
            requires_migration=True,
            supported=True,
            backup_path=None,
            steps=("initialize current schema", "write schema-version receipt"),
        )
    current = _read_schema_version(engine, tables)
    if current == CURRENT_WORKSPACE_SCHEMA_VERSION:
        return MigrationPlan(current, current, False, True, None, ())
    supported = current in {LEGACY_WORKSPACE_SCHEMA_VERSION, 2, 3}
    steps = ["create sibling backup"]
    if current == LEGACY_WORKSPACE_SCHEMA_VERSION:
        steps.extend(
            (
                "create epistemic-ledger tables",
                "backfill legacy STIX observations",
                "write schema-version 2 receipt",
            )
        )
    if current <= 2:  # noqa: PLR2004
        steps.extend(
            (
                "add persisted hunt challenges and badge artwork metadata",
                "write schema-version 3 receipt",
            )
        )
    if current <= 3:  # noqa: PLR2004
        steps.extend(
            (
                "add scientific-investigation lifecycle tables",
                "link existing questions, hypotheses, assertions, and method runs",
                "bridge the legacy Predictions Log without deleting its source record",
                "write schema-version 4 receipt",
            )
        )
    return MigrationPlan(
        from_version=current,
        to_version=CURRENT_WORKSPACE_SCHEMA_VERSION,
        requires_migration=True,
        supported=supported,
        backup_path=_backup_path(db_path, current),
        steps=tuple(steps) if supported else (),
    )


def validate_workspace_schema(engine: Engine) -> SchemaValidation:
    """Run SQLite integrity and required-table checks without mutating data."""

    tables = set(inspect(engine).get_table_names())
    version = _read_schema_version(engine, tables)
    required_tables = set(Base.metadata.tables)
    missing = tuple(sorted(required_tables - tables))
    with engine.connect() as connection:
        integrity = str(connection.execute(text("PRAGMA quick_check")).scalar_one())
    return SchemaValidation(
        valid=(
            version == CURRENT_WORKSPACE_SCHEMA_VERSION
            and integrity.casefold() == "ok"
            and not missing
        ),
        version=version,
        sqlite_integrity=integrity,
        missing_tables=missing,
    )


def get_workspace_schema_version(engine: Engine) -> int:
    """Return the detected schema version without mutating the workspace."""

    return _read_schema_version(engine, set(inspect(engine).get_table_names()))


def _read_schema_version(engine: Engine, tables: set[str]) -> int:
    if "workspace_schema_version" not in tables:
        return LEGACY_WORKSPACE_SCHEMA_VERSION
    with Session(engine) as session:
        row = session.get(WorkspaceSchemaVersion, _VERSION_ROW_ID)
        if row is None:
            raise RuntimeError("Workspace schema table exists without its required version row.")
        return int(row.version)


def _backup_path(db_path: Path, version: int) -> Path:
    return db_path.with_name(f"{db_path.name}.pre-v{version}-backup")


def _create_sqlite_backup(db_path: Path, backup_path: Path) -> None:
    """Create a consistent backup, including committed WAL content."""

    try:
        with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as destination:
            source.backup(destination)
        shutil.copystat(db_path, backup_path)
    except Exception:
        backup_path.unlink(missing_ok=True)
        raise


def _migrate_v1_to_v2(engine: Engine) -> int:
    # create_all is intentionally scoped to this migration step. Future changes
    # that alter existing columns require a new explicit migration function.
    Base.metadata.create_all(engine)
    backfilled = 0
    with Session(engine) as session:
        for row in session.execute(select(StixObject).order_by(StixObject.id)).scalars():
            backfilled += _backfill_observation(
                session,
                entity_ref=row.id,
                entity_type=row.type,
                entity_value=row.value,
                blob=dict(row.json_blob),
                created_at=row.created_at,
            )
        for row in session.execute(select(Relationship).order_by(Relationship.id)).scalars():
            backfilled += _backfill_observation(
                session,
                entity_ref=row.id,
                entity_type="relationship",
                entity_value=row.relationship_type,
                blob=dict(row.json_blob),
                created_at=row.created_at,
            )

        session.add(
            WorkspaceSchemaVersion(
                id=_VERSION_ROW_ID,
                version=2,
                migrated_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
    return backfilled


def _migrate_v2_to_v3(engine: Engine) -> None:
    """Add persisted hunt challenges and self-describing badge awards."""

    Base.metadata.create_all(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("badge_events")}
    additions = {
        "badge_description": "TEXT",
        "badge_rarity": "VARCHAR",
        "badge_artwork": "VARCHAR",
        "badge_glyph": "VARCHAR",
        "challenge_id": "VARCHAR",
    }
    with engine.begin() as connection:
        for name, sql_type in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE badge_events ADD COLUMN {name} {sql_type}"))
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_badge_events_challenge_id "
                "ON badge_events (challenge_id)"
            )
        )
    with Session(engine) as session:
        row = session.get(WorkspaceSchemaVersion, _VERSION_ROW_ID)
        if row is None:
            raise RuntimeError("Schema v2 workspace is missing its version receipt.")
        row.version = 3
        row.migrated_at = datetime.now(timezone.utc)
        session.commit()


def _migrate_v3_to_v4(engine: Engine) -> None:
    """Add one scientific lifecycle around existing analytic records.

    The migration is additive. Existing questions, hypotheses, assertions,
    method runs, and the legacy Predictions Log remain untouched. Lifecycle
    items point to those records, so schema v4 organizes prior work without
    rewriting its content or provenance.
    """

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        questions = list(
            session.execute(
                select(InvestigationQuestion).order_by(InvestigationQuestion.created_at)
            ).scalars()
        )
        assertions = list(
            session.execute(
                select(AnalyticAssertion).order_by(AnalyticAssertion.created_at)
            ).scalars()
        )
        hypotheses = list(
            session.execute(
                select(AnalyticHypothesis).order_by(AnalyticHypothesis.created_at)
            ).scalars()
        )
        method_runs = list(
            session.execute(
                select(AnalyticMethodRun).order_by(AnalyticMethodRun.created_at)
            ).scalars()
        )
        prediction_entries, prediction_error = _legacy_prediction_entries(session)
        has_analytic_work = any(
            (
                questions,
                assertions,
                hypotheses,
                method_runs,
                prediction_entries,
                prediction_error,
            )
        )

        investigation = session.execute(
            select(AnalyticInvestigation).order_by(AnalyticInvestigation.created_at).limit(1)
        ).scalar_one_or_none()
        if has_analytic_work and investigation is None:
            primary_question = questions[0] if questions else None
            investigation = AnalyticInvestigation(
                id=f"investigation-{uuid.uuid4()}",
                title=(
                    primary_question.text
                    if primary_question is not None
                    else "Migrated workspace investigation"
                ),
                purpose="Preserve and continue analytic work created before schema v4.",
                scope="Migrated workspace records; analyst review is required before publication.",
                status="analyzing",
                primary_question_id=(primary_question.id if primary_question is not None else None),
                created_by="system",
            )
            session.add(investigation)
            session.flush()

        if investigation is not None:
            for question in questions:
                _link_lifecycle_record(
                    session, investigation.id, "question", "question", question.id
                )
            for assertion in assertions:
                item_type = "assumption" if assertion.assertion_type == "assumed" else "assertion"
                _link_lifecycle_record(
                    session,
                    investigation.id,
                    item_type,
                    "assertion",
                    assertion.id,
                )
            for hypothesis in hypotheses:
                _link_lifecycle_record(
                    session,
                    investigation.id,
                    "hypothesis",
                    "hypothesis",
                    hypothesis.id,
                )
            for method_run in method_runs:
                _link_lifecycle_record(
                    session,
                    investigation.id,
                    "method_run",
                    "method_run",
                    method_run.id,
                    status=method_run.status,
                    analyst_disposition=method_run.analyst_disposition,
                )
            for entry in prediction_entries:
                prediction_id = str(entry.get("prediction_id") or f"legacy-{uuid.uuid4()}")
                status = {
                    "validated": "satisfied",
                    "falsified": "rejected",
                }.get(str(entry.get("status")), "open")
                criteria = {
                    "slot": entry.get("slot"),
                    "expected_evidence": entry.get("expected_evidence") or {},
                    "falsification_evidence": entry.get("falsification_evidence"),
                    "created_at": entry.get("created_at"),
                    "validated_at": entry.get("validated_at"),
                    "validated_by_sco_id": entry.get("validated_by_sco_id"),
                    "created_at_hunt_count": entry.get("created_at_hunt_count", 0),
                }
                _link_lifecycle_record(
                    session,
                    investigation.id,
                    "prediction",
                    "legacy_prediction",
                    prediction_id,
                    statement=str(entry.get("text") or "Legacy prediction"),
                    status=status,
                    criteria=criteria,
                )
            if prediction_error:
                error_id = f"legacy-prediction-error-{hashlib.sha256(prediction_error.encode()).hexdigest()[:16]}"
                _link_lifecycle_record(
                    session,
                    investigation.id,
                    "knowledge_gap",
                    "legacy_prediction_log",
                    error_id,
                    statement="The legacy Predictions Log could not be parsed during migration.",
                    status="open",
                    criteria={"error": prediction_error},
                )

        row = session.get(WorkspaceSchemaVersion, _VERSION_ROW_ID)
        if row is None:
            raise RuntimeError("Schema v3 workspace is missing its version receipt.")
        row.version = 4
        row.migrated_at = datetime.now(timezone.utc)
        session.commit()


def _legacy_prediction_entries(session: Session) -> tuple[list[dict], str | None]:
    row = session.execute(
        select(ScoreEvent)
        .where(ScoreEvent.action == "_predictions_log")
        .order_by(ScoreEvent.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None or not row.indicator:
        return [], None
    try:
        payload = json.loads(row.indicator)
        entries = payload.get("predictions", [])
        if not isinstance(entries, list):
            raise ValueError("predictions must be a list")
        return [entry for entry in entries if isinstance(entry, dict)], None
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        return [], str(exc)


def _link_lifecycle_record(
    session: Session,
    investigation_id: str,
    item_type: str,
    record_kind: str,
    record_id: str,
    *,
    statement: str | None = None,
    status: str = "open",
    criteria: dict | None = None,
    analyst_disposition: str = "accepted",
) -> None:
    digest = hashlib.sha256(
        f"{investigation_id}\0{item_type}\0{record_kind}\0{record_id}".encode()
    ).hexdigest()[:24]
    item_id = f"lifecycle-{digest}"
    if session.get(AnalyticLifecycleItem, item_id) is not None:
        return
    session.add(
        AnalyticLifecycleItem(
            id=item_id,
            investigation_id=investigation_id,
            item_type=item_type,
            record_kind=record_kind,
            record_id=record_id,
            statement=statement,
            status=status,
            criteria=criteria or {},
            evidence_refs=[],
            author_kind="system" if record_kind.startswith("legacy_") else "human",
            analyst_disposition=analyst_disposition,
        )
    )


def _backfill_observation(
    session: Session,
    *,
    entity_ref: str,
    entity_type: str,
    entity_value: str | None,
    blob: dict,
    created_at: datetime,
) -> int:
    source_name = str(blob.get("x_ap_source_module") or "legacy/unknown")
    endpoint = sanitize_endpoint(blob.get("x_ap_source_url"))
    api_version = blob.get("x_ap_api_version")
    source_id = source_identity(source_name, endpoint, api_version, "legacy")
    if session.get(EvidenceSource, source_id) is None:
        session.add(
            EvidenceSource(
                id=source_id,
                name=source_name,
                source_type="legacy",
                endpoint=endpoint,
                api_version=api_version,
                collector_version="legacy",
            )
        )

    fetched_at = str(
        blob.get("x_ap_fetched_at")
        or created_at.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    )
    digest_input = f"{entity_ref}\0{source_id}\0{fetched_at}".encode()
    observation_id = f"observation-legacy-{hashlib.sha256(digest_input).hexdigest()[:24]}"
    if session.get(EvidenceObservation, observation_id) is not None:
        return 0
    session.add(
        EvidenceObservation(
            id=observation_id,
            entity_ref=entity_ref,
            entity_type=entity_type,
            entity_value=entity_value,
            source_id=source_id,
            module_run_id=None,
            fetched_at=fetched_at,
            response_sha256=blob.get("x_ap_response_sha256"),
            observed_blob=blob,
            created_at=created_at,
        )
    )
    return 1
