"""SQLAlchemy ORM models for workspace storage.

Each workspace is a separate SQLite file. This module defines the shared schema
(Base + four tables) that WorkspaceManager applies to every workspace database.

@decision DEC-DB-001
@title STIX objects stored as JSON blobs, not relational decomposition
@status accepted
@rationale STIX 2.1 objects are complex nested structures with type-specific
           properties. Storing as JSON blobs with type/id/value indexes keeps
           the schema simple and avoids lossy decomposition. The id and type
           columns enable efficient filtering; value covers quick-access lookups.
           SQLite JSON1 extension (bundled in Python's sqlite3) enables querying
           into the blob when needed in future iterations.

@decision DEC-DB-002
@title No Alembic migrations in v1
@status accepted
@rationale Schema is greenfield and evolving rapidly. Workspaces are per-investigation
           SQLite files that can be recreated without data loss concerns (investigation
           data is always re-derivable from module runs). Migration overhead is not
           justified pre-1.0. When schema stabilizes post-1.0, Alembic can be added.

@decision DEC-DB-003
@title SQLAlchemy 2.0 DeclarativeBase, not legacy declarative_base()
@status accepted
@rationale SQLAlchemy 2.0 introduced DeclarativeBase as the preferred declarative
           API. Using it from the start avoids a future migration from the legacy
           declarative_base() function, which is deprecated in 2.0 and may be
           removed in future releases.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase

# @decision DEC-DB-004
# @title ScoreEvent table stores individual scoring events per workspace
# @status accepted
# @rationale Gamification scoring requires persistence across sessions. Storing
#            individual events (not just totals) enables: (1) recent activity feeds
#            in do_score(), (2) per-module attribution via module_run_id FK, (3)
#            future analytics (points over time, per-type breakdowns). A single
#            total column would lose the event history.


class Base(DeclarativeBase):
    """Shared declarative base for all workspace tables."""


class StixObject(Base):
    """Persisted STIX Cyber Observable Objects (SCOs).

    Stores the full STIX JSON blob plus indexed fields for efficient lookup.
    STIX SCO IDs are deterministic (content-based), so deduplication is
    achieved by using the STIX ID as the primary key.
    """

    __tablename__ = "stix_objects"

    id = Column(String, primary_key=True)
    """STIX ID (e.g. "ipv4-addr--uuid"). Primary key enables natural dedup."""

    type = Column(String, index=True, nullable=False)
    """STIX type string (e.g. "ipv4-addr"). Indexed for type-filter queries."""

    value = Column(String, index=True, nullable=True)
    """Quick-access primary value field (e.g. the IP or domain string)."""

    json_blob = Column(JSON, nullable=False)
    """Full STIX 2.1 JSON as a dict. Source of truth for the object."""

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    """UTC timestamp when this record was inserted."""


class Relationship(Base):
    """Persisted STIX Relationship SROs (Subject-Relationship-Object).

    Stored separately from StixObject to allow efficient graph traversal
    (source_ref and target_ref are indexed).
    """

    __tablename__ = "relationships"

    id = Column(String, primary_key=True)
    """STIX Relationship ID. Not content-based — each relationship is unique."""

    source_ref = Column(String, index=True, nullable=False)
    """STIX ID of the source object."""

    target_ref = Column(String, index=True, nullable=False)
    """STIX ID of the target object."""

    relationship_type = Column(String, nullable=False)
    """STIX relationship type (e.g. "resolves-to", "communicates-with")."""

    json_blob = Column(JSON, nullable=False)
    """Full STIX 2.1 Relationship JSON."""

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ModuleRun(Base):
    """Audit log of module executions within this workspace.

    Records which module ran, against which target, when, and how many
    STIX objects were produced. Enables investigation timeline reconstruction.
    """

    __tablename__ = "module_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    """Auto-increment integer PK. Order == execution order."""

    module_name = Column(String, nullable=False)
    """Canonical module name (e.g. "osint/whois_lookup")."""

    target = Column(String, nullable=False)
    """The observable passed as the hunt() target."""

    timestamp = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    result_count = Column(Integer, default=0, nullable=False)
    """Number of STIX objects stored from this run (after deduplication)."""


class ScoreEvent(Base):
    """Individual scoring events from module discoveries.

    Each time a module hunt() discovers a new indicator, one or more ScoreEvent
    rows are inserted. The sum of all rows gives the workspace's total score.
    Individual rows enable recent-activity feeds and future per-module analytics.
    """

    __tablename__ = "score_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    """Auto-increment PK. Order == insertion order (chronological)."""

    action = Column(String, nullable=False)
    """Scoring action key (e.g. 'new_ip', 'new_domain'). See ScoringRule.action."""

    points = Column(Integer, nullable=False)
    """Points awarded for this event. Always >= ScoringRule.minimum."""

    indicator = Column(String, nullable=True)
    """The observable value (e.g. '1.2.3.4', 'evil.com'). For display only."""

    module_run_id = Column(Integer, nullable=True)
    """Optional FK to module_runs.id. No FK constraint (DEC-DB-002 — no migrations)."""

    timestamp = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    """UTC timestamp when the scoring event was recorded."""


# @decision DEC-DB-005
# @title BadgeEvent table stores earned badges per workspace
# @status accepted
# @rationale Badges are workspace-persistent (unlike in-memory challenge state).
#            A separate BadgeEvent table (not reusing ScoreEvent) keeps badge
#            semantics distinct from scoring: badges are identified by badge_id
#            (a stable string slug), have a display name snapshot, and are
#            deduplicated by badge_id so the same badge is never awarded twice
#            in the same workspace. The badge_id is NOT an FK to any catalog
#            table — the catalog lives in memory (BadgeManager). This avoids
#            schema coupling to the badge list and aligns with DEC-DB-002
#            (no migrations in v1).


class BadgeEvent(Base):
    """Persisted record of a badge earned in this workspace.

    Each row represents a unique badge award. badge_id is the stable slug
    from the Badge dataclass (e.g. "badge-first-blood"). Duplicate badge_id
    rows are prevented at the application layer by checking get_awarded_badges()
    before calling store_badge_event().
    """

    __tablename__ = "badge_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    """Auto-increment PK."""

    badge_id = Column(String, nullable=False, index=True)
    """Stable badge slug (e.g. "badge-first-blood"). Not an FK — catalog is in memory."""

    badge_name = Column(String, nullable=False)
    """Snapshot of Badge.name at award time. Survives catalog changes."""

    awarded_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    """UTC timestamp when this badge was first earned."""


class AnalystNote(Base):
    """Free-text analyst annotations, optionally linked to a STIX object.

    Provides an in-workspace notepad. Notes can be standalone or attached to
    a specific SCO/SRO by stix_object_id.
    """

    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, autoincrement=True)

    stix_object_id = Column(String, nullable=True)
    """Optional STIX ID this note is linked to. No FK constraint (DEC-DB-002)."""

    content = Column(Text, nullable=False)
    """The analyst's note text."""

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
