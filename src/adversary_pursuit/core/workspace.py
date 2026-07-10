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
import logging
import warnings
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from adversary_pursuit.models.database import (
    AnalystNote,
    BadgeEvent,
    Base,
    ModuleRun,
    ScoreEvent,
    StixObject,
)
from adversary_pursuit.models.database import (
    Relationship as RelationshipModel,
)
from adversary_pursuit.models.stix import dict_to_stix

# @decision DEC-WORKSPACE-DB-001
# @title Confirmation lives at UI surface only — WorkspaceManager.clear() is unconditional
# @status accepted
# @rationale The manager is a data-layer authority (Sacred Practice 12: single authority per
#            state domain). Embedding a confirm_token parameter on clear() would create a
#            second policy gate inside the data layer, duplicating the UI-surface gate and
#            violating the single-responsibility contract. The cmd2 and chat surfaces own
#            user interaction; the manager owns data mutation.

# @decision DEC-WORKSPACE-DB-002
# @title 6 ORM models cleared per workspace clear; sentinel rows cleared by side effect
# @status accepted
# @rationale The 6 tables (stix_objects, relationships, module_runs, score_events,
#            analyst_notes, badge_events) together represent all investigation data for
#            a workspace. Sentinel rows in score_events (_milestone_sentinel,
#            _dossier_state_snapshot, _predictions_log) ARE cleared by intentional side
#            effect — "clear workspace data" includes dossier state. This aligns with the
#            user's mental model of "clear this investigation."

# @decision DEC-WORKSPACE-DB-007
# @title Post-clear loud verification — RuntimeError if any table still has rows
# @status accepted
# @rationale Sacred Practice 5 (fail loudly and early, never silently). After committing
#            the bulk DELETE for all 6 tables, the manager re-queries each table and raises
#            RuntimeError if any count != 0. This catches partial-clear bugs (e.g., ORM
#            session not flushing, FK constraints preventing deletion) before the caller
#            reports success to the user.

_LOG = logging.getLogger(__name__)

# Default workspace directory
_DEFAULT_WORKSPACE_DIR = Path.home() / ".ap" / "workspaces"

# ---------------------------------------------------------------------------
# Optional EventBus wiring for TUI TargetChanged notifications (Slice 6)
# ---------------------------------------------------------------------------

# Optional module-level EventBus for TUI TargetChanged events.
# Set via wire_event_bus(). None = no-op (Slice 5 behavior).
_EVENT_BUS: object = None  # EventBus | None


def wire_event_bus(bus: object) -> None:
    """Wire an EventBus for TUI target-change notifications.

    Call this once when the TUI is active (typically in _run_tui_chat before
    TuiApplication.run()). Pass None to disable notifications (restores
    Slice 5 behavior). The bus is stored at module level so
    notify_target_changed() can publish without the caller threading the bus
    through every call site.

    Parameters
    ----------
    bus:
        An EventBus instance (from adversary_pursuit.agent.tui.events), or
        None to unwire.
    """
    global _EVENT_BUS
    _EVENT_BUS = bus


def notify_target_changed(target: str, target_type: str) -> None:
    """Publish a TargetChanged event to the wired EventBus, if any.

    No-op when no bus is wired (_EVENT_BUS is None). Swallows all exceptions
    so TUI notification never crashes the console path (Sacred Practice 5
    applies to the data layer, not the UI notification layer).

    Parameters
    ----------
    target:
        The raw target string (e.g. "evil.example.com").
    target_type:
        STIX SCO type string or "unrecognized-type" when detection fails.
    """
    if _EVENT_BUS is None:
        return
    try:
        from adversary_pursuit.agent.tui.events import TargetChanged

        _EVENT_BUS.publish(TargetChanged(target=target, target_type=target_type))  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        _LOG.debug("notify_target_changed: failed to publish TargetChanged (suppressed)")


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
        self._workspace_dir = (
            Path(workspace_dir) if workspace_dir is not None else _DEFAULT_WORKSPACE_DIR
        )
        self._active: str | None = None
        self._engine = None
        # @decision DEC-WORKSPACE-PIVOTS-001
        # @title Session timing and pivot count are in-memory session metrics
        # @status accepted
        # @rationale elapsed_seconds and pivot_count are session-level metrics —
        #            they reset on each WorkspaceManager instantiation (i.e., each
        #            ap-chat session). Persisting them to SQLite would require a
        #            new table or sentinel row, adding schema complexity with minimal
        #            user value. In-memory tracking is sufficient for the StatusBar
        #            display use case. _session_started_at is set on first switch()
        #            call (not at __init__) so elapsed reflects active investigation
        #            time, not process startup time. record_pivot() must be called
        #            BEFORE switch() so it can compare new_target against the current
        #            _active value.
        self._session_started_at: float = 0.0
        self._pivot_count: int = 0

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
        import time

        db_path = self._db_path(name)
        if not db_path.exists():
            raise ValueError(f"Workspace '{name}' does not exist")
        if self._engine is not None:
            self._engine.dispose()
        self._engine = create_engine(f"sqlite:///{db_path}")
        self._active = name
        # Start session timer on first switch (DEC-WORKSPACE-PIVOTS-001)
        if self._session_started_at == 0.0:
            self._session_started_at = time.time()

    def record_pivot(self, new_target: str) -> None:
        """Record a workspace pivot when the active target changes.

        Must be called BEFORE switch() so the comparison is made against the
        current _active value (DEC-WORKSPACE-PIVOTS-001).

        A pivot is counted only when there is already an active workspace AND
        new_target differs from the current active workspace name. The first
        target selection (when _active is None) is not counted as a pivot.

        Parameters
        ----------
        new_target:
            The workspace name being switched to.
        """
        if self._active is not None and new_target != self._active:
            self._pivot_count += 1

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
        *,
        source_url: str | None = None,
        api_version: str | None = None,
        response_sha256: str | None = None,
        fetched_at: str | None = None,
    ) -> int:
        """Store STIX objects from a module run.

        Accepts both plain dicts (from module.hunt()) and python-stix2 objects.
        Plain dicts are converted via dict_to_stix(). Unrecognized types are
        skipped. Relationships are stored in the relationships table; SCOs go
        to stix_objects. Deduplication is by STIX ID (INSERT OR IGNORE).

        Provenance fields (x_ap_*) are written exclusively by this method —
        callers MUST NOT pre-set x_ap_* keys on their SCO dicts. Any x_ap_*
        key found on an incoming dict is stripped and a warning is emitted.
        See DEC-59-STIX-PROVENANCE-001.

        Parameters
        ----------
        objects:
            List of plain dicts or python-stix2 objects to persist.
        module_name:
            Canonical module name for the audit log (e.g. "osint/whois_lookup").
        target:
            The hunt() target string for the audit log.
        source_url:
            URL of the vendor API endpoint that produced these objects.
            Stored verbatim as x_ap_source_url. Pass None for legacy call sites.
        api_version:
            Vendor API version string (e.g. "v2"). Stored verbatim as
            x_ap_api_version. Pass None for legacy call sites.
        response_sha256:
            SHA-256 hex digest of the raw vendor response bytes, computed by the
            caller. Stored verbatim as x_ap_response_sha256.
            See DEC-59-STIX-PROVENANCE-003.
        fetched_at:
            RFC 3339 / ISO 8601 timestamp string (Z-suffixed) indicating when
            the data was fetched. Defaults to the current UTC wall-clock time
            when not supplied. See DEC-59-STIX-PROVENANCE-004.

        Returns
        -------
        int
            Count of objects stored (after conversion; excludes skipped dicts).

        @decision DEC-59-STIX-PROVENANCE-001
        @title workspace.store_stix_objects() is the sole authority for the x_ap_* namespace
        @status accepted
        @rationale Single-source-of-truth (CLAUDE.md §12). If modules could also emit
                   x_ap_*, two authorities would silently diverge. Caller-supplied dicts
                   that already contain x_ap_* keys are stripped with a warning so the
                   invariant is enforced at the storage boundary, not by convention.

        @decision DEC-59-STIX-PROVENANCE-002
        @title Provenance fields added to json_blob AFTER obj.serialize()
        @status accepted
        @rationale obj.serialize() feeds the python-stix2 deterministic-id derivation.
                   Adding provenance before serialization would make the same observable
                   fetched at two different times produce two different STIX IDs, breaking
                   deduplication (DEC-WS-004). Post-serialization augmentation keeps the
                   ID stable: same SCO content → same ID, regardless of provenance.

        @decision DEC-59-STIX-PROVENANCE-004
        @title Legacy SCOs (no provenance kwargs) get x_ap_fetched_at defaulted to storage-time UTC
        @status accepted
        @rationale x_ap_fetched_at is the only provenance field that the workspace can
                   populate without module cooperation. The other three require the caller
                   to supply them. Defaulting fetched_at here ensures every SCO has at
                   least a storage timestamp, making the minimum provenance record non-null.
        """
        # @decision DEC-WS-006
        # @title _ensure_active() called at top of every public data method
        # @status accepted
        # @rationale Without this call, any public data method opens Session(self._engine)
        #            when self._engine is None (no workspace switched yet), causing
        #            SQLAlchemy UnboundExecutionError on session.get() / session.add().
        #            _ensure_active() auto-creates and switches to the 'default' workspace,
        #            guaranteeing self._engine is bound before the Session is opened.
        #            store_stix_objects, get_stix_objects, and get_module_runs all carry
        #            this call. Previously get_stix_objects and get_module_runs were missing
        #            it — latent because nothing called them before store_stix_objects
        #            (which auto-creates the workspace). M-3's pre-hunt SCO id capture
        #            (tools.py:443-445) and M-2's Timing extractor (get_module_runs) both
        #            run BEFORE store_stix_objects on fresh sessions, triggering the crash.
        self._ensure_active()
        stored_count = 0

        # Resolve fetched_at default once for the entire batch (DEC-59-STIX-PROVENANCE-004)
        effective_fetched_at = fetched_at or datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )

        # Build provenance overlay — only x_ap_fetched_at is always non-null;
        # the other three are omitted from the overlay when None so that the
        # json_blob contains null (absent) rather than the key with a null value.
        provenance: dict = {"x_ap_fetched_at": effective_fetched_at}
        if source_url is not None:
            provenance["x_ap_source_url"] = source_url
        if api_version is not None:
            provenance["x_ap_api_version"] = api_version
        if response_sha256 is not None:
            provenance["x_ap_response_sha256"] = response_sha256

        with Session(self._engine) as session:
            for obj in objects:
                # Strip caller-supplied x_ap_* fields from dicts before conversion
                # (DEC-59-STIX-PROVENANCE-001: workspace is the sole x_ap_* authority)
                if isinstance(obj, dict):
                    x_ap_keys = [k for k in obj if k.startswith("x_ap_")]
                    if x_ap_keys:
                        warnings.warn(
                            f"store_stix_objects: caller-supplied x_ap_* keys stripped "
                            f"({', '.join(sorted(x_ap_keys))}); only the workspace layer "
                            "may set x_ap_* provenance fields (DEC-59-STIX-PROVENANCE-001).",
                            stacklevel=2,
                        )
                        obj = {k: v for k, v in obj.items() if not k.startswith("x_ap_")}

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
                    self._store_sco(session, obj, provenance)
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
        self._ensure_active()  # DEC-WS-006: must bind engine before opening Session
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
        self._ensure_active()  # DEC-WS-006: must bind engine before opening Session
        with Session(self._engine) as session:
            rows = session.execute(select(ModuleRun).order_by(ModuleRun.id)).scalars().all()
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
                select(StixObject.type, func.count(StixObject.id).label("cnt")).group_by(
                    StixObject.type
                )
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
            result = session.execute(select(func.sum(ScoreEvent.points))).scalar()
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
            rows = (
                session.execute(
                    select(ScoreEvent)
                    .where(ScoreEvent.action.notin_(self._RESERVED_ACTIONS))
                    .order_by(ScoreEvent.id.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return [
                {
                    "action": row.action,
                    "points": row.points,
                    "indicator": row.indicator,
                    "timestamp": row.timestamp,
                }
                for row in rows
            ]

    # ------------------------------------------------------------------
    # Reserved sentinel actions — DEC-63-MILESTONE-CATCHUP-001 + DEC-M4-PERSIST-002
    # ------------------------------------------------------------------

    # Sentinel action name used to persist the last announced milestone ID.
    # A single row with this action is maintained in score_events.
    # Using score_events avoids any schema change (DEC-63-MILESTONE-CATCHUP-001).
    _MILESTONE_SENTINEL_ACTION: str = "_milestone_sentinel"

    # @decision DEC-M4-PERSIST-002
    # @title _RESERVED_ACTIONS frozenset enumerates all sentinel actions; get_recent_scores widened
    # @status accepted
    # @rationale DEC-M4-PERSIST-001 picked the F63 sentinel-row pattern for DossierState and
    #     Predictions Log persistence. That mechanically requires hiding the two new sentinel rows
    #     from get_recent_scores() the same way F63 hides _milestone_sentinel. Widening the
    #     existing single-action filter to a frozenset is the smallest honest workspace.py change.
    #     This constant is the SINGLE authority for all reserved score_events actions.
    #     Future reserved actions MUST be added here and require a planner re-stage.
    _RESERVED_ACTIONS: frozenset[str] = frozenset(
        {
            "_milestone_sentinel",  # F63 — last_milestone_id
            "_dossier_state_snapshot",  # M-4 — persistent DossierState
            "_predictions_log",  # M-4 — Predictions Log entries
        }
    )

    def get_last_milestone_id(self) -> int | None:
        """Return the last announced milestone ID for the active workspace.

        Returns None when no milestone has been announced yet (fresh workspace
        or workspace that has never crossed a milestone threshold).

        Uses a sentinel row in score_events with action="_milestone_sentinel"
        to avoid a schema change (DEC-63-MILESTONE-CATCHUP-001).

        Returns
        -------
        int | None
            Last announced milestone ID, or None.
        """
        self._ensure_active()
        with Session(self._engine) as session:
            row = session.execute(
                select(ScoreEvent)
                .where(ScoreEvent.action == self._MILESTONE_SENTINEL_ACTION)
                .order_by(ScoreEvent.id.desc())
                .limit(1)
            ).scalar_one_or_none()
            if row is None or row.indicator is None:
                return None
            try:
                return int(row.indicator)
            except (ValueError, TypeError):
                return None

    def set_last_milestone_id(self, milestone_id: int) -> None:
        """Persist the last announced milestone ID.

        Upserts a sentinel row in score_events: deletes any existing sentinel
        rows, then inserts a fresh one with the new milestone_id.
        This keeps exactly one sentinel row per workspace (idempotent).

        Parameters
        ----------
        milestone_id:
            The highest MilestoneSpec.id announced in this workspace.
            Callers must pass the highest ID when multiple milestones fired
            in a single run (catch-up scenario).

        @decision DEC-63-MILESTONE-CATCHUP-001 (persistence site)
        @title score_events sentinel row for last_announced milestone ID
        @status accepted
        @rationale Using score_events with a reserved action name avoids
                   any schema migration. The sentinel has points=0 so it
                   does not affect get_total_score(). get_recent_scores()
                   may include it but callers only display it as an audit
                   trail entry — the UI ignores unknown action names.
                   A separate workspace_metadata table would be cleaner but
                   requires a migration; the sentinel approach ships in one
                   PR with zero schema changes (F63 constraint).
        """
        self._ensure_active()
        with Session(self._engine) as session:
            # Delete existing sentinel rows (should be 0 or 1)
            existing = (
                session.execute(
                    select(ScoreEvent).where(ScoreEvent.action == self._MILESTONE_SENTINEL_ACTION)
                )
                .scalars()
                .all()
            )
            for row in existing:
                session.delete(row)
            # Insert the fresh sentinel
            sentinel = ScoreEvent(
                action=self._MILESTONE_SENTINEL_ACTION,
                points=0,
                indicator=str(milestone_id),
                module_run_id=None,
            )
            session.add(sentinel)
            session.commit()

    def add_note(self, content: str, stix_object_id: str | None = None) -> None:
        """Add an analyst note to the active workspace.

        Parameters
        ----------
        content:
            Free-text note content.
        stix_object_id:
            Optional STIX ID to link this note to a specific observable.
        """
        self._ensure_active()
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
            rows = (
                session.execute(select(BadgeEvent).order_by(BadgeEvent.awarded_at)).scalars().all()
            )
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
            total_indicators = session.execute(select(func.count(StixObject.id))).scalar() or 0

            domain_count = (
                session.execute(
                    select(func.count(StixObject.id)).where(StixObject.type == "domain-name")
                ).scalar()
                or 0
            )

            ip_count = (
                session.execute(
                    select(func.count(StixObject.id)).where(
                        StixObject.type.in_(["ipv4-addr", "ipv6-addr"])
                    )
                ).scalar()
                or 0
            )

            module_run_count = session.execute(select(func.count(ModuleRun.id))).scalar() or 0

            total_score = session.execute(select(func.sum(ScoreEvent.points))).scalar() or 0

            note_count = session.execute(select(func.count(AnalystNote.id))).scalar() or 0

        import time

        return {
            "total_indicators": total_indicators,
            "domain_count": domain_count,
            "ip_count": ip_count,
            "module_run_count": module_run_count,
            "total_score": total_score,
            "note_count": note_count,
            "elapsed_seconds": int(time.time() - self._session_started_at)
            if self._session_started_at > 0.0
            else 0,
            "pivot_count": self._pivot_count,
        }

    # ------------------------------------------------------------------
    # Workspace clear (DEC-WORKSPACE-DB-001, DEC-WORKSPACE-DB-002, DEC-WORKSPACE-DB-007)
    # ------------------------------------------------------------------

    def clear(self, name: str | None = None) -> dict[str, int]:
        """Clear all data tables in the named workspace (or active if None).

        Deletes all rows from 6 ORM models: ``stix_objects``, ``relationships``,
        ``module_runs``, ``score_events``, ``analyst_notes``, ``badge_events``.
        The SQLite file and schema are preserved; only row data is removed.

        Sentinel rows stored in ``score_events`` (``_milestone_sentinel``,
        ``_dossier_state_snapshot``, ``_predictions_log``) are cleared by
        intentional side effect — "clear workspace data" is a dossier-state
        clear (DEC-WORKSPACE-DB-002).

        The ``clear()`` method is unconditional — confirmation gates live at
        the UI surface only (cmd2 ``_workspace_clear`` / chat workspace handler).
        There is no ``confirm_token`` parameter (DEC-WORKSPACE-DB-001).

        After committing the bulk DELETEs, each table is re-queried; if any
        count != 0 a ``RuntimeError`` is raised immediately (DEC-WORKSPACE-DB-007,
        Sacred Practice 5 — loud failure over silent fallback).

        Parameters
        ----------
        name:
            Workspace name to clear. If ``None``, the active workspace is used.

        Returns
        -------
        dict[str, int]
            Counts of rows deleted per table::

                {
                    "stix_objects": N,
                    "relationships": N,
                    "module_runs": N,
                    "score_events": N,
                    "analyst_notes": N,
                    "badge_events": N,
                }

        Raises
        ------
        RuntimeError
            If ``name`` is ``None`` and no workspace is active.
        ValueError
            If ``name`` is given but does not exist.
        RuntimeError
            If post-clear verification finds any of the 6 tables still non-empty
            (DEC-WORKSPACE-DB-007).
        """
        if name is not None:
            # Named workspace — validate existence without switching active session
            db_path = self._db_path(name)
            if not db_path.exists():
                raise ValueError(f"Workspace '{name}' does not exist")
            from sqlalchemy import create_engine as _ce

            target_engine = _ce(f"sqlite:///{db_path}")
        else:
            # Active workspace — use the `active` property which raises RuntimeError
            # when no workspace has been switched to (DEC-WORKSPACE-DB-001: clear is an
            # intentional destructive operation; auto-creating 'default' and immediately
            # clearing it would silently wipe a workspace the user may not have intended
            # to target — different semantics from read methods that auto-init).
            _ = self.active  # raises RuntimeError if no active workspace
            target_engine = self._engine

        deleted: dict[str, int] = {}

        with Session(target_engine) as session:
            # Delete all rows from each of the 6 ORM data models
            deleted["stix_objects"] = session.query(StixObject).delete()
            deleted["relationships"] = session.query(RelationshipModel).delete()
            deleted["module_runs"] = session.query(ModuleRun).delete()
            deleted["score_events"] = session.query(ScoreEvent).delete()
            deleted["analyst_notes"] = session.query(AnalystNote).delete()
            deleted["badge_events"] = session.query(BadgeEvent).delete()
            session.commit()

            # DEC-WORKSPACE-DB-007: post-clear loud verification
            # Re-query each table; any non-zero count is a partial-clear bug
            remaining = {
                "stix_objects": session.execute(select(func.count(StixObject.id))).scalar() or 0,
                "relationships": session.execute(select(func.count(RelationshipModel.id))).scalar()
                or 0,
                "module_runs": session.execute(select(func.count(ModuleRun.id))).scalar() or 0,
                "score_events": session.execute(select(func.count(ScoreEvent.id))).scalar() or 0,
                "analyst_notes": session.execute(select(func.count(AnalystNote.id))).scalar() or 0,
                "badge_events": session.execute(select(func.count(BadgeEvent.id))).scalar() or 0,
            }

        non_empty = {t: c for t, c in remaining.items() if c != 0}
        if non_empty:
            raise RuntimeError(
                f"Workspace clear verification failed — tables still non-empty: "
                f"{non_empty}. This is a bug; report to maintainers."
            )

        # Dispose named-workspace engine (it was created only for this call)
        if name is not None:
            target_engine.dispose()

        return deleted

    # ------------------------------------------------------------------
    # Status helpers (DEC-WORKSPACE-DB-004, DEC-WORKSPACE-DB-005)
    # ------------------------------------------------------------------

    def get_workspace_db_size(self, name: str | None = None) -> int:
        """Return the SQLite file size in bytes for the named (or active) workspace.

        Uses ``pathlib.Path.stat().st_size`` — no SQLite connection needed.
        Returns 0 if the workspace file does not exist yet (e.g., the default
        workspace has not been created yet).

        Parameters
        ----------
        name:
            Workspace name. If ``None``, uses the active workspace name; raises
            ``RuntimeError`` if no workspace is active.

        Returns
        -------
        int
            File size in bytes, or 0 if the file does not exist.
        """
        if name is None:
            # Will raise RuntimeError when no active workspace (DEC-WS-006 semantics)
            resolved_name = self.active
        else:
            resolved_name = name
        db_path = self._db_path(resolved_name)
        if not db_path.exists():
            return 0
        return db_path.stat().st_size

    def get_workspace_table_counts(self) -> dict[str, int]:
        """Return row counts for all 6 ORM data tables in the active workspace.

        Calls ``_ensure_active()`` so a default workspace is auto-created when
        none is active (same lazy-init semantics as all other data methods).

        Returns
        -------
        dict[str, int]
            Keys: ``stix_objects``, ``relationships``, ``module_runs``,
            ``score_events``, ``analyst_notes``, ``badge_events``.
            All values are non-negative integers.
        """
        self._ensure_active()
        with Session(self._engine) as session:
            return {
                "stix_objects": session.execute(select(func.count(StixObject.id))).scalar() or 0,
                "relationships": session.execute(select(func.count(RelationshipModel.id))).scalar()
                or 0,
                "module_runs": session.execute(select(func.count(ModuleRun.id))).scalar() or 0,
                "score_events": session.execute(select(func.count(ScoreEvent.id))).scalar() or 0,
                "analyst_notes": session.execute(select(func.count(AnalystNote.id))).scalar() or 0,
                "badge_events": session.execute(select(func.count(BadgeEvent.id))).scalar() or 0,
            }

    def get_last_event_timestamps(self) -> dict:
        """Return the most recent event data for key activity categories.

        Calls ``_ensure_active()`` for auto-initialization (DEC-WS-006).

        Returns
        -------
        dict
            Keys and their sources:

            - ``last_run``: ``datetime | None`` — timestamp of the most recent
              ``ModuleRun`` row.
            - ``last_run_module``: ``str | None`` — module_name of the most recent run.
            - ``last_run_target``: ``str | None`` — target of the most recent run.
            - ``last_note``: ``datetime | None`` — ``created_at`` of the most recent
              ``AnalystNote`` row.
            - ``last_note_content``: ``str | None`` — content of the most recent note
              (first 60 chars).
            - ``last_badge``: ``datetime | None`` — ``awarded_at`` of the most recent
              ``BadgeEvent`` row.
            - ``last_badge_name``: ``str | None`` — badge_name of the most recent badge.
            - ``last_score``: ``datetime | None`` — ``timestamp`` of the most recent
              non-sentinel ``ScoreEvent`` row.

            All datetime values are ``None`` when no rows exist for that category.
        """
        self._ensure_active()
        with Session(self._engine) as session:
            # last_run: most recent ModuleRun by id descending
            last_run_row = session.execute(
                select(ModuleRun).order_by(ModuleRun.id.desc()).limit(1)
            ).scalar_one_or_none()
            last_run: datetime | None = last_run_row.timestamp if last_run_row is not None else None
            last_run_module: str | None = (
                last_run_row.module_name if last_run_row is not None else None
            )
            last_run_target: str | None = last_run_row.target if last_run_row is not None else None

            # last_note: most recent AnalystNote by id descending
            last_note_row = session.execute(
                select(AnalystNote).order_by(AnalystNote.id.desc()).limit(1)
            ).scalar_one_or_none()
            last_note: datetime | None = (
                last_note_row.created_at if last_note_row is not None else None
            )
            last_note_content: str | None = (
                last_note_row.content[:60] if last_note_row is not None else None
            )

            # last_badge: most recent BadgeEvent by id descending
            last_badge_row = session.execute(
                select(BadgeEvent).order_by(BadgeEvent.id.desc()).limit(1)
            ).scalar_one_or_none()
            last_badge: datetime | None = (
                last_badge_row.awarded_at if last_badge_row is not None else None
            )
            last_badge_name: str | None = (
                last_badge_row.badge_name if last_badge_row is not None else None
            )

            # last_score: most recent non-sentinel ScoreEvent by id descending
            last_score_row = session.execute(
                select(ScoreEvent)
                .where(ScoreEvent.action.notin_(self._RESERVED_ACTIONS))
                .order_by(ScoreEvent.id.desc())
                .limit(1)
            ).scalar_one_or_none()
            last_score: datetime | None = (
                last_score_row.timestamp if last_score_row is not None else None
            )

        return {
            "last_run": last_run,
            "last_run_module": last_run_module,
            "last_run_target": last_run_target,
            "last_note": last_note,
            "last_note_content": last_note_content,
            "last_badge": last_badge,
            "last_badge_name": last_badge_name,
            "last_score": last_score,
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

    def _store_sco(self, session: Session, obj, provenance: dict | None = None) -> None:
        """Insert a STIX SCO into stix_objects, ignoring duplicate IDs.

        Uses ORM session.get() for deduplication: if a row with this STIX ID
        already exists, skip the insert. STIX SCO IDs are deterministic, so the
        same observable always has the same ID (DEC-WS-004). Using the ORM
        (not raw SQL) ensures the Python-side created_at default fires correctly.

        Provenance fields (x_ap_*) are merged into json_blob AFTER obj.serialize()
        so they do not feed back into the deterministic-id derivation.
        See DEC-59-STIX-PROVENANCE-002.
        """
        existing = session.get(StixObject, obj.id)
        if existing is not None:
            return  # already stored — deduplicated
        # Serialize first so deterministic-id derivation is already complete,
        # then augment the dict with provenance fields (DEC-59-STIX-PROVENANCE-002).
        json_dict = json.loads(obj.serialize())
        if provenance:
            json_dict.update(provenance)
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
