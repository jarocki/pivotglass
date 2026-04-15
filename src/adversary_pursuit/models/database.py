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
