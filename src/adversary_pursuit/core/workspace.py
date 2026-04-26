"""Workspace/investigation isolation manager.

Each workspace is an independent SQLite database file. Switching workspaces
means switching which database file the session connects to. This mirrors
Metasploit's workspace model — investigations are fully isolated at the
storage layer.

@decision DEC-WS-001
@title One SQLite file per workspace, no shared database
@status accepted
@rationale Isolation by file makes workspaces trivially portable (copy the .db
           file), deletable (rm the file), and independently queryable. A shared
           database with a workspace_id discriminator column would require more
           complex queries and risks cross-workspace data leaks from missing WHERE
           clauses. SQLite's file-per-database model is the right fit.

@decision DEC-WS-002
@title Active workspace tracked in memory only (no persistence file)
@status accepted
@rationale The active workspace is a session concept, not a persistent preference.
           Persisting it to a file adds complexity without user value -- the console
           always starts in the configured default_workspace (from ConfigManager).
           A future "ap workspace switch" command updates ConfigManager, not a
           separate state file.

@decision DEC-WS-003
@title store_stix_objects accepts both plain dicts and python-stix2 objects
@status accepted
@rationale The production call chain sends plain dicts from module.hunt(). But
           helper functions (create_ipv4 etc.) return python-stix2 objects. Both
           forms must be accepted so callers don't need to pre-convert. Detection
           logic: if the object has a .serialize() method, it's a stix2 object;
           otherwise treat it as a dict and pass through dict_to_stix.

@decision DEC-WS-004
@title Deduplication by STIX ID using ORM session.get() before insert
@status accepted
@rationale STIX SCO IDs are deterministic (content-based). The same observable
           stored twice has the same ID. Using session.get(Model, pk) before
           inserting leverages the SQLAlchemy identity map (O(1) for already-seen
           objects in the same session) and fires Python-side column defaults
           (created_at). Raw SQL INSERT OR IGNORE was attempted but silently dropped
           rows because the NOT NULL created_at column has no SQLite-level DEFAULT.

@decision DEC-WS-005
@title get_workspace_stats uses multiple scalar queries, not a single aggregation join
@status accepted
@rationale Each stat (total_indicators, domain_count, ip_count, module_run_count,
           total_score, note_count) requires a different query against different tables
           or filtered subsets. A single UNION or CTE would be harder to read, debug,
           and extend. SQLite is fast for small workspace databases (< 100k rows), so
           6 small scalar queries run in negligible time. Clarity over micro-optimization.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from adversary_pursuit.models.database import (
    AnalystNote,
    BadgeEvent,
    Base,
    ModuleRun,
    Relationship as RelationshipModel,
    ScoreEvent,
    StixObject,
)
from adversary_pursuit.models.stix import dict_to_stix

# Default workspace directory
_DEFAULT_WORKSPACE_DIR = Path.home() / ".ap" / "workspaces"


class WorkspaceManager:
    """Manages investigation workspaces.

    Each workspace is a SQLite file at <workspace_dir>/<name>.db.
    The default workspace directory is ~/.ap/workspaces/.

    Usage
    -----
    wm = WorkspaceManager()           # uses ~/.ap/workspaces/
    wm.create("apt41")                # creates apt41.db with full schema
    wm.switch("apt41")                # point active session at apt41
    wm.store_stix_objects(            # store module output
        module_output,
        module_name="osint/whois_lookup",
        target="198.51.100.1",
    )
    objects = wm.get_stix_objects(type_filter="ipv4-addr")
    """

    def __init__(self, workspace_dir: Path | None = None) -> None:
        """Initialise with optional workspace directory override.

        Parameters
        ----------
        workspace_dir:
            Directory where .db files are stored. Defaults to ~/.ap/workspaces/.
            Pass ``tmp_path`` in tests to avoid touching the real user directory.
        """
        self._workspace_dir = Path(workspace_dir) if workspace_dir is not None else _DEFAULT_WORKSPACE_DIR
        self._active: str | None = None
        self._engine = None

    # ------------------------------------------------------------------
    # Workspace lifecycle
    # ------------------------------------------------------------------

    def create(self, name: str) -> None:
        """Create a new workspace (creates SQLite DB with full schema).

        Parameters
        ----------
        name:
            Workspace name. Must be unique within this workspace directory.

        Raises
        ------
        ValueError
            If a workspace with this name already exists.
        """
        db_path = self._db_path(name)
        if db_path.exists():
            raise ValueError(f"Workspace '{name}' already exists at {db_path}")
        self._workspace_dir.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        engine.dispose()

    def delete(self, name: str) -> None:
        """Delete a workspace and its SQLite database file.

        Parameters
        ----------
        name:
            Workspace name to delete.

        Raises
        ------
        ValueError
            If the workspace does not exist.
        """
        db_path = self._db_path(name)
        if not db_path.exists():
            raise ValueError(f"Workspace '{name}' does not exist")
        # Dispose engine if we're deleting the active workspace
        if self._active == name and self._engine is not None:
            self._engine.dispose()
            self._engine = None
            self._active = None
        db_path.unlink()

    def list_workspaces(self) -> list[str]:
        """List all workspace names in the workspace directory.

        Returns
        -------
        list[str]
            Sorted list of workspace names (without the .db extension).
        """
        if not self._workspace_dir.exists():
            return []
        return sorted(p.stem for p in self._workspace_dir.glob("*.db"))

    def switch(self, name: str) -> None:
        """Switch the active workspace.

        Parameters
        ----------
        name:
            Workspace name to switch to.

        Raises
        ------
        ValueError
            If the workspace does not exist.
        """
        db_path = self._db_path(name)
        if not db_path.exists():
            raise ValueError(f"Workspace '{name}' does not exist")
        if self._engine is not None:
            self._engine.dispose()
        self._engine = create_engine(f"sqlite:///{db_path}")
        self._active = name

    @property
    def active(self) -> str:
        """Current active workspace name.

        Raises
        ------
        RuntimeError
            If no workspace is active and no default exists.
        """
        if self._active is None:
            raise RuntimeError("No active workspace. Call switch() or get_session() first.")
        return self._active

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Context manager yielding a SQLAlchemy Session for the active workspace.

        If no workspace is active, auto-creates and switches to "default".
        The session is committed on clean exit and rolled back on exception.

        Yields
        ------
        Session
            A SQLAlchemy 2.0 Session bound to the active workspace database.
        """
        self._ensure_active()
        with Session(self._engine) as session:
            yield session

    # ------------------------------------------------------------------
    # Data operations
    # ------------------------------------------------------------------

    def store_stix_objects(
        self,
        objects: list,
        module_name: str,
        target: str,
    ) -> int:
        """Store STIX objects from a module run.

        Accepts both plain dicts (from module.hunt()) and python-stix2 objects.
        Plain dicts are converted via dict_to_stix(). Unrecognized types are
        skipped. Relationships are stored in the relationships table; SCOs go
        to stix_objects. Deduplication is by STIX ID (INSERT OR IGNORE).

        Parameters
        ----------
        objects:
            List of plain dicts or python-stix2 objects to persist.
        module_name:
            Canonical module name for the audit log (e.g. "osint/whois_lookup").
        target:
            The hunt() target string for the audit log.

        Returns
        -------
        int
            Count of objects stored (after conversion; excludes skipped dicts).
        """
        stored_count = 0

        with Session(self._engine) as session:
            for obj in objects:
                # Convert plain dicts to stix2 objects
                if isinstance(obj, dict):
                    obj = dict_to_stix(obj)
                    if isinstance(obj, dict):
                        # dict_to_stix returned the original dict — unrecognized type
                        continue

                # Dispatch on STIX object type
                obj_type = getattr(obj, "type", None)
                if obj_type == "relationship":
                    self._store_relationship(session, obj)
                else:
                    self._store_sco(session, obj)
                stored_count += 1

            # Log the module run
            run = ModuleRun(
                module_name=module_name,
                target=target,
                result_count=stored_count,
            )
            session.add(run)
            session.commit()

        return stored_count

    def get_stix_objects(self, type_filter: str | None = None) -> list[dict]:
        """Retrieve STIX objects from the active workspace.

        Parameters
        ----------
        type_filter:
            If provided, return only objects of this STIX type
            (e.g. "ipv4-addr", "domain-name"). Returns all objects if None.

        Returns
        -------
        list[dict]
            List of plain dicts (the json_blob column contents) for each object.
        """
        with Session(self._engine) as session:
            stmt = select(StixObject)
            if type_filter is not None:
                stmt = stmt.where(StixObject.type == type_filter)
            rows = session.execute(stmt).scalars().all()
            return [row.json_blob for row in rows]

    def get_module_runs(self) -> list[dict]:
        """Get module execution history for the active workspace.

        Returns
        -------
        list[dict]
            List of dicts with keys: module_name, target, timestamp, result_count.
            Ordered by insertion order (id ascending).
        """
        with Session(self._engine) as session:
            rows = session.execute(
                select(ModuleRun).order_by(ModuleRun.id)
            ).scalars().all()
            return [
                {
                    "module_name": row.module_name,
                    "target": row.target,
                    "timestamp": row.timestamp,
                    "result_count": row.result_count,
                }
                for row in rows
            ]

    def get_stix_type_counts(self) -> dict[str, int]:
        """Get count of STIX objects by type in the active workspace.

        Auto-creates the default workspace if none is active (same lazy-init
        semantics as get_session / store_stix_objects).

        Returns
        -------
        dict[str, int]
            Maps STIX type strings to their object count.
            e.g., {"ipv4-addr": 5, "domain-name": 3}. Only types with at
            least one object are included.
        """
        self._ensure_active()
        with Session(self._engine) as session:
            rows = session.execute(
                select(StixObject.type, func.count(StixObject.id).label("cnt"))
                .group_by(StixObject.type)
            ).all()
            return {row.type: row.cnt for row in rows}

    def store_score_events(
        self,
        events: list[dict],
        module_run_id: int | None = None,
    ) -> int:
        """Persist scoring events and return total points awarded.

        Parameters
        ----------
        events:
            List of scoring event dicts as returned by ScoringEngine.score_results().
            Each dict must have "action" and "points" keys. "indicator" is optional.
        module_run_id:
            Optional ID of the ModuleRun that produced these events.
            Stored for attribution; no FK constraint is enforced (DEC-DB-002).

        Returns
        -------
        int
            Sum of all points in the provided events.
        """
        self._ensure_active()
        total = 0
        with Session(self._engine) as session:
            for event in events:
                row = ScoreEvent(
                    action=event.get("action", ""),
                    points=event.get("points", 0),
                    indicator=event.get("indicator"),
                    module_run_id=module_run_id,
                )
                session.add(row)
                total += event.get("points", 0)
            session.commit()
        return total

    def get_total_score(self) -> int:
        """Get the total accumulated score for the active workspace.

        Auto-creates the default workspace if none is active.

        Returns
        -------
        int
            Sum of points from all score events in this workspace, or 0 if none.
        """
        self._ensure_active()
        with Session(self._engine) as session:
            result = session.execute(
                select(func.sum(ScoreEvent.points))
            ).scalar()
            return result if result is not None else 0

    def get_recent_scores(self, limit: int = 10) -> list[dict]:
        """Get the most recent scoring events, newest first.

        Auto-creates the default workspace if none is active.

        Parameters
        ----------
        limit:
            Maximum number of events to return (default: 10).

        Returns
        -------
        list[dict]
            List of event dicts with keys: action, points, indicator, timestamp.
            Ordered by insertion order descending (most recent first).
        """
        self._ensure_active()
        with Session(self._engine) as session:
            rows = session.execute(
                select(ScoreEvent)
                .order_by(ScoreEvent.id.desc())
                .limit(limit)
            ).scalars().all()
            return [
                {
                    "action": row.action,
                    "points": row.points,
                    "indicator": row.indicator,
                    "timestamp": row.timestamp,
                }
                for row in rows
            ]

    def add_note(self, content: str, stix_object_id: str | None = None) -> None:
        """Add an analyst note to the active workspace.

        Parameters
        ----------
        content:
            Free-text note content.
        stix_object_id:
            Optional STIX ID to link this note to a specific observable.
        """
        with Session(self._engine) as session:
            note = AnalystNote(content=content, stix_object_id=stix_object_id)
            session.add(note)
            session.commit()

    def store_badge_event(self, badge_id: str, badge_name: str) -> None:
        """Persist a badge award to the active workspace.

        Does NOT enforce uniqueness at the DB layer — callers are responsible
        for checking get_awarded_badges() first (DEC-DB-005). Idempotency is
        enforced at the application layer by APConsole._check_badges_after_run()
        which builds the already_awarded set before calling BadgeManager.check_all().

        Parameters
        ----------
        badge_id:
            Stable badge slug (e.g. "badge-first-blood").
        badge_name:
            Display name snapshot at award time (e.g. "First Blood").
        """
        self._ensure_active()
        with Session(self._engine) as session:
            event = BadgeEvent(badge_id=badge_id, badge_name=badge_name)
            session.add(event)
            session.commit()

    def get_awarded_badges(self) -> list[dict]:
        """Return all badges earned in the active workspace.

        Returns
        -------
        list[dict]
            Each dict has: badge_id (str), badge_name (str), awarded_at (datetime).
            Ordered by awarded_at ascending (oldest first).
        """
        self._ensure_active()
        with Session(self._engine) as session:
            rows = session.execute(
                select(BadgeEvent).order_by(BadgeEvent.awarded_at)
            ).scalars().all()
            return [
                {
                    "badge_id": row.badge_id,
                    "badge_name": row.badge_name,
                    "awarded_at": row.awarded_at,
                }
                for row in rows
            ]

    def get_workspace_stats(self) -> dict:
        """Return aggregated stats for badge/achievement evaluation.

        Collects all metrics needed by BadgeManager.check_all() in a single
        method to keep APConsole wiring simple. Stats are computed from live
        workspace data (not cached).

        Returns
        -------
        dict
            Keys and sources:
            - total_indicators (int): count of all stix_objects rows
            - domain_count (int): count of stix_objects where type = "domain-name"
            - ip_count (int): count of stix_objects where type IN ("ipv4-addr", "ipv6-addr")
            - module_run_count (int): count of module_runs rows
            - total_score (int): sum of score_events.points (0 if none)
            - note_count (int): count of notes rows
        """
        self._ensure_active()
        with Session(self._engine) as session:
            total_indicators = session.execute(
                select(func.count(StixObject.id))
            ).scalar() or 0

            domain_count = session.execute(
                select(func.count(StixObject.id)).where(
                    StixObject.type == "domain-name"
                )
            ).scalar() or 0

            ip_count = session.execute(
                select(func.count(StixObject.id)).where(
                    StixObject.type.in_(["ipv4-addr", "ipv6-addr"])
                )
            ).scalar() or 0

            module_run_count = session.execute(
                select(func.count(ModuleRun.id))
            ).scalar() or 0

            total_score = session.execute(
                select(func.sum(ScoreEvent.points))
            ).scalar() or 0

            note_count = session.execute(
                select(func.count(AnalystNote.id))
            ).scalar() or 0

        return {
            "total_indicators": total_indicators,
            "domain_count": domain_count,
            "ip_count": ip_count,
            "module_run_count": module_run_count,
            "total_score": total_score,
            "note_count": note_count,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _db_path(self, name: str) -> Path:
        """Return the Path for a workspace's SQLite file."""
        return self._workspace_dir / f"{name}.db"

    def _ensure_active(self) -> None:
        """Auto-create and switch to 'default' if no active workspace."""
        if self._active is None:
            default_path = self._db_path("default")
            self._workspace_dir.mkdir(parents=True, exist_ok=True)
            if not default_path.exists():
                self.create("default")
            self.switch("default")

    def _store_sco(self, session: Session, obj) -> None:
        """Insert a STIX SCO into stix_objects, ignoring duplicate IDs.

        Uses ORM session.get() for deduplication: if a row with this STIX ID
        already exists, skip the insert. STIX SCO IDs are deterministic, so the
        same observable always has the same ID (DEC-WS-004). Using the ORM
        (not raw SQL) ensures the Python-side created_at default fires correctly.
        """
        existing = session.get(StixObject, obj.id)
        if existing is not None:
            return  # already stored — deduplicated
        json_dict = json.loads(obj.serialize())
        row = StixObject(
            id=obj.id,
            type=obj.type,
            value=json_dict.get("value"),
            json_blob=json_dict,
        )
        session.add(row)

    def _store_relationship(self, session: Session, obj) -> None:
        """Insert a STIX Relationship SRO into relationships, ignoring duplicates."""
        existing = session.get(RelationshipModel, obj.id)
        if existing is not None:
            return  # already stored
        json_dict = json.loads(obj.serialize())
        row = RelationshipModel(
            id=obj.id,
            source_ref=obj.source_ref,
            target_ref=obj.target_ref,
            relationship_type=obj.relationship_type,
            json_blob=json_dict,
        )
        session.add(row)
