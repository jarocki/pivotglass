"""SQLAlchemy ORM models for workspace storage.

Each workspace is a separate SQLite file. This module defines the shared schema
that WorkspaceManager applies to every workspace database.

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
@title Versioned, backup-first workspace migrations begin in v0.8
@status superseded
@rationale The pre-1.0 assumption that investigation databases could always be
           recreated ceased to be true once analyst notes, predictions, annotations,
           and imported evidence became durable user work. Workspace migrations are
           now explicit and versioned; existing databases are backed up before the
           first schema-changing step. See core/workspace_migrations.py.

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

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text, UniqueConstraint
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


class WorkspaceSchemaVersion(Base):
    """Single-row authority for the workspace schema version."""

    __tablename__ = "workspace_schema_version"

    id = Column(Integer, primary_key=True)
    version = Column(Integer, nullable=False)
    migrated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


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

    badge_description = Column(Text, nullable=True)
    badge_rarity = Column(String, nullable=True)
    badge_artwork = Column(String, nullable=True)
    badge_glyph = Column(String, nullable=True)
    challenge_id = Column(String, nullable=True, index=True)

    awarded_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    """UTC timestamp when this badge was first earned."""


class HuntChallengeRecord(Base):
    """Persisted, evidence-scoped challenge and its badge reward contract."""

    __tablename__ = "hunt_challenges"

    id = Column(String, primary_key=True)
    origin = Column(String, nullable=False, default="hunt", index=True)
    subject_ref = Column(String, nullable=True, index=True)
    subject_type = Column(String, nullable=True, index=True)
    subject_value = Column(Text, nullable=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    challenge_type = Column(String, nullable=False, index=True)
    points = Column(Integer, nullable=False, default=0)
    verification = Column(JSON, nullable=False)
    hints = Column(JSON, nullable=False, default=list)
    evidence_basis = Column(JSON, nullable=False, default=list)
    badge_id = Column(String, nullable=False, index=True)
    badge_name = Column(String, nullable=False)
    badge_description = Column(Text, nullable=False)
    badge_rarity = Column(String, nullable=False)
    badge_artwork = Column(String, nullable=False)
    badge_glyph = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active", index=True)
    progress_current = Column(Integer, nullable=False, default=0)
    progress_target = Column(Integer, nullable=False, default=1)
    progress_label = Column(String, nullable=False, default="requirements met")
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at = Column(DateTime, nullable=True)


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


class EvidenceSource(Base):
    """A stable collection-source identity, separate from any observation."""

    __tablename__ = "evidence_sources"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, index=True)
    source_type = Column(String, nullable=False, default="provider")
    endpoint = Column(Text, nullable=True)
    api_version = Column(String, nullable=True)
    collector_version = Column(String, nullable=True)
    dependence_group = Column(String, nullable=True, index=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class EvidenceObservation(Base):
    """Immutable record that a source observed an entity or relationship.

    Normalized STIX objects remain deduplicated. Observations deliberately do
    not: two sources seeing the same entity are two analytically meaningful
    records, as are two observations by one source at different times.
    """

    __tablename__ = "evidence_observations"

    id = Column(String, primary_key=True)
    entity_ref = Column(String, nullable=False, index=True)
    entity_type = Column(String, nullable=False, index=True)
    entity_value = Column(Text, nullable=True)
    source_id = Column(String, nullable=False, index=True)
    module_run_id = Column(Integer, nullable=True, index=True)
    fetched_at = Column(String, nullable=False, index=True)
    response_sha256 = Column(String, nullable=True)
    response_media_type = Column(String, nullable=True)
    handling_marking = Column(String, nullable=True)
    transformation_id = Column(String, nullable=True)
    raw_artifact_ref = Column(String, nullable=True)
    retained_until = Column(DateTime, nullable=True)
    observed_blob = Column(JSON, nullable=False)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class EvidenceObservationDisposition(Base):
    """Append-only correction, retraction, or supersession of an observation.

    The observation itself is never edited. This event records what changed,
    why, by whom, and—when applicable—which immutable observation replaces it.
    """

    __tablename__ = "evidence_observation_dispositions"

    id = Column(String, primary_key=True)
    observation_id = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False, index=True)
    replacement_observation_id = Column(String, nullable=True, index=True)
    reason = Column(Text, nullable=False)
    recorded_by = Column(String, nullable=False, default="human")
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class InvestigationQuestion(Base):
    """The explicit question an investigation is attempting to answer."""

    __tablename__ = "investigation_questions"

    id = Column(String, primary_key=True)
    text = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="open", index=True)
    created_by = Column(String, nullable=False, default="human")
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    closed_at = Column(DateTime, nullable=True)


class AnalyticAssertion(Base):
    """A contestable statement distinguished from its supporting evidence."""

    __tablename__ = "analytic_assertions"

    id = Column(String, primary_key=True)
    statement = Column(Text, nullable=False)
    assertion_type = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="active", index=True)
    subject_ref = Column(String, nullable=True, index=True)
    predicate = Column(String, nullable=True)
    object_ref = Column(String, nullable=True, index=True)
    object_value = Column(Text, nullable=True)
    author_kind = Column(String, nullable=False, default="human")
    method = Column(String, nullable=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class AnalyticHypothesis(Base):
    """A falsifiable candidate answer to an investigation question."""

    __tablename__ = "analytic_hypotheses"

    id = Column(String, primary_key=True)
    question_id = Column(String, nullable=False, index=True)
    statement = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="proposed", index=True)
    author_kind = Column(String, nullable=False, default="human")
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class AnalyticEvidenceLink(Base):
    """A typed support or contradiction link in the epistemic graph."""

    __tablename__ = "analytic_evidence_links"
    __table_args__ = (
        UniqueConstraint(
            "source_kind",
            "source_id",
            "target_kind",
            "target_id",
            "stance",
            name="uq_analytic_evidence_link",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_kind = Column(String, nullable=False)
    source_id = Column(String, nullable=False, index=True)
    target_kind = Column(String, nullable=False)
    target_id = Column(String, nullable=False, index=True)
    stance = Column(String, nullable=False, index=True)
    rationale = Column(Text, nullable=False)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class AnalyticConfidenceAssessment(Base):
    """Confidence in the evidentiary and logical basis of a judgment.

    Likelihood is intentionally not stored here. A separate table prevents a
    provider score, probability estimate, completeness score, and analytic
    confidence from silently becoming one overloaded number.
    """

    __tablename__ = "analytic_confidence_assessments"

    id = Column(String, primary_key=True)
    target_kind = Column(String, nullable=False)
    target_id = Column(String, nullable=False, index=True)
    level = Column(String, nullable=False, index=True)
    rationale = Column(Text, nullable=False)
    factors = Column(JSON, nullable=False, default=dict)
    assessed_by = Column(String, nullable=False, default="human")
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class LikelihoodAssessment(Base):
    """Probability language for a future event, separate from confidence."""

    __tablename__ = "likelihood_assessments"

    id = Column(String, primary_key=True)
    target_kind = Column(String, nullable=False)
    target_id = Column(String, nullable=False, index=True)
    term = Column(String, nullable=False, index=True)
    probability_min = Column(Float, nullable=False)
    probability_max = Column(Float, nullable=False)
    rationale = Column(Text, nullable=False)
    assessed_by = Column(String, nullable=False, default="human")
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class AnalyticContradiction(Base):
    """A first-class unresolved or resolved conflict between analytic records."""

    __tablename__ = "analytic_contradictions"

    id = Column(String, primary_key=True)
    left_kind = Column(String, nullable=False)
    left_id = Column(String, nullable=False, index=True)
    right_kind = Column(String, nullable=False)
    right_id = Column(String, nullable=False, index=True)
    summary = Column(Text, nullable=False)
    materiality = Column(String, nullable=False, default="medium", index=True)
    status = Column(String, nullable=False, default="unresolved", index=True)
    resolution_required = Column(Text, nullable=False)
    resolution_note = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    resolved_at = Column(DateTime, nullable=True)


class AnalyticMethodRun(Base):
    """Versioned execution record for a Structured Analytic Technique."""

    __tablename__ = "analytic_method_runs"

    id = Column(String, primary_key=True)
    question_id = Column(String, nullable=False, index=True)
    technique = Column(String, nullable=False, index=True)
    technique_version = Column(String, nullable=False)
    status = Column(String, nullable=False, default="draft", index=True)
    input_blob = Column(JSON, nullable=False)
    output_blob = Column(JSON, nullable=True)
    created_by = Column(String, nullable=False, default="human")
    analyst_disposition = Column(String, nullable=False, default="pending", index=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at = Column(DateTime, nullable=True)


class AnalyticInvestigation(Base):
    """Root record for one persisted scientific investigation lifecycle.

    The root organizes existing epistemic records without replacing them.
    Questions, hypotheses, assertions, observations, and method runs remain
    authoritative in their existing tables and are connected through
    :class:`AnalyticLifecycleItem` records.
    """

    __tablename__ = "analytic_investigations"

    id = Column(String, primary_key=True)
    title = Column(Text, nullable=False)
    purpose = Column(Text, nullable=False)
    scope = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="framing", index=True)
    primary_question_id = Column(String, nullable=True, index=True)
    created_by = Column(String, nullable=False, default="human")
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    concluded_at = Column(DateTime, nullable=True)


class AnalyticLifecycleItem(Base):
    """One typed component of a scientific investigation lifecycle.

    ``record_kind`` and ``record_id`` point to an existing authoritative
    epistemic record when one exists. Native planning records such as
    collection requirements, stop conditions, limitations, and knowledge gaps
    store their statement directly. The table therefore organizes the method
    without duplicating observations or judgments.
    """

    __tablename__ = "analytic_lifecycle_items"
    __table_args__ = (
        UniqueConstraint(
            "investigation_id",
            "item_type",
            "record_kind",
            "record_id",
            name="uq_analytic_lifecycle_record_link",
        ),
    )

    id = Column(String, primary_key=True)
    investigation_id = Column(String, nullable=False, index=True)
    item_type = Column(String, nullable=False, index=True)
    record_kind = Column(String, nullable=True)
    record_id = Column(String, nullable=True, index=True)
    statement = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="open", index=True)
    priority = Column(Integer, nullable=False, default=0)
    criteria = Column(JSON, nullable=False, default=dict)
    evidence_refs = Column(JSON, nullable=False, default=list)
    author_kind = Column(String, nullable=False, default="human")
    analyst_disposition = Column(String, nullable=False, default="accepted", index=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    resolved_at = Column(DateTime, nullable=True)
