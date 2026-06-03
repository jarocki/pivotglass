"""Tests for Issue #4: Workspace & STIX 2.1 Data Model.

@decision DEC-TEST-004
@title Test suite covers STIX helpers, DB schema, WorkspaceManager CRUD, and production sequence
@status accepted
@rationale The production call chain (module.hunt() → store_stix_objects → get_stix_objects)
           is tested end-to-end in TestProductionSequence. This prevents the failure mode
           where unit tests pass but the integrated flow is broken. All workspace tests
           use tmp_path to avoid touching ~/.ap/.

Tests verify:
- STIX helper layer (stix.py): creation of each SCO type, relationships, bundles
- dict_to_stix conversion for all supported types and unrecognized types
- Database schema creation (all four tables)
- WorkspaceManager CRUD (create, list, switch, delete, default auto-creation)
- store_stix_objects: plain-dict conversion, STIX deduplication, module run logging
- get_stix_objects: retrieval, type filtering
- get_module_runs: execution history
- add_note: with and without stix_object_id linkage
- Workspace isolation: objects in workspace A not visible in workspace B

Production sequence coverage: modules return plain dicts → store_stix_objects
converts them → they appear in get_stix_objects. This mirrors the actual
production call chain: hunt() → workspace.store_stix_objects() → get_stix_objects().
"""

from __future__ import annotations

import pytest

from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.models.database import (
    AnalystNote,
    Base,
)
from adversary_pursuit.models.stix import (
    create_bundle,
    create_domain,
    create_email,
    create_ipv4,
    create_ipv6,
    create_relationship,
    create_url,
    dict_to_stix,
)

# ---------------------------------------------------------------------------
# STIX helper layer tests
# ---------------------------------------------------------------------------


class TestStixHelpers:
    """Unit tests for the STIX 2.1 helper functions."""

    def test_create_ipv4(self):
        obj = create_ipv4("1.2.3.4")
        assert obj.type == "ipv4-addr"
        assert obj.value == "1.2.3.4"
        assert obj.id.startswith("ipv4-addr--")

    def test_create_ipv4_deterministic(self):
        """Same value → same STIX ID (content-based ID)."""
        a = create_ipv4("10.0.0.1")
        b = create_ipv4("10.0.0.1")
        assert a.id == b.id

    def test_create_ipv6(self):
        obj = create_ipv6("::1")
        assert obj.type == "ipv6-addr"
        assert obj.value == "::1"
        assert obj.id.startswith("ipv6-addr--")

    def test_create_domain(self):
        obj = create_domain("example.com")
        assert obj.type == "domain-name"
        assert obj.value == "example.com"
        assert obj.id.startswith("domain-name--")

    def test_create_url(self):
        obj = create_url("https://example.com/path")
        assert obj.type == "url"
        assert obj.value == "https://example.com/path"
        assert obj.id.startswith("url--")

    def test_create_email(self):
        obj = create_email("user@example.com")
        assert obj.type == "email-addr"
        assert obj.value == "user@example.com"
        assert obj.id.startswith("email-addr--")

    def test_create_relationship(self):
        ip = create_ipv4("192.168.1.1")
        dom = create_domain("malware.com")
        rel = create_relationship(dom.id, ip.id, "resolves-to")
        assert rel.type == "relationship"
        assert rel.relationship_type == "resolves-to"
        assert rel.source_ref == dom.id
        assert rel.target_ref == ip.id
        assert rel.id.startswith("relationship--")

    def test_create_bundle(self):
        ip = create_ipv4("8.8.8.8")
        dom = create_domain("google.com")
        bundle = create_bundle([ip, dom])
        assert bundle.type == "bundle"
        assert len(bundle.objects) == 2

    def test_create_bundle_empty(self):
        """Empty bundle is valid STIX."""
        bundle = create_bundle([])
        assert bundle.type == "bundle"


class TestDictToStix:
    """Tests for dict_to_stix conversion (the bridge from module output to STIX)."""

    def test_ipv4_dict(self):
        obj = dict_to_stix({"type": "ipv4-addr", "value": "1.2.3.4"})
        assert obj.type == "ipv4-addr"
        assert obj.value == "1.2.3.4"

    def test_ipv6_dict(self):
        obj = dict_to_stix({"type": "ipv6-addr", "value": "2001:db8::1"})
        assert obj.type == "ipv6-addr"
        assert obj.value == "2001:db8::1"

    def test_domain_dict(self):
        obj = dict_to_stix({"type": "domain-name", "value": "evil.com"})
        assert obj.type == "domain-name"
        assert obj.value == "evil.com"

    def test_url_dict(self):
        obj = dict_to_stix({"type": "url", "value": "https://malware.example/payload"})
        assert obj.type == "url"
        assert obj.value == "https://malware.example/payload"

    def test_email_dict(self):
        obj = dict_to_stix({"type": "email-addr", "value": "threat@actor.io"})
        assert obj.type == "email-addr"
        assert obj.value == "threat@actor.io"

    def test_unrecognized_type_returns_original_dict(self):
        """Unrecognized STIX types pass through untouched — future module compat."""
        d = {"type": "x-custom-indicator", "value": "something", "extra": 42}
        result = dict_to_stix(d)
        assert result is d  # same object, not a copy

    def test_missing_type_returns_original_dict(self):
        d = {"value": "no type field"}
        result = dict_to_stix(d)
        assert result is d

    def test_deterministic_id_from_dict(self):
        """dict_to_stix produces deterministic IDs (same input → same STIX object ID)."""
        a = dict_to_stix({"type": "ipv4-addr", "value": "5.5.5.5"})
        b = dict_to_stix({"type": "ipv4-addr", "value": "5.5.5.5"})
        assert a.id == b.id

    def test_custom_x_fields_no_error(self):
        """dict_to_stix handles x_ prefixed custom fields (e.g. whois_lookup output).

        whois_lookup returns dicts like:
          {"type": "ipv4-addr", "value": "1.2.3.4", "x_creation_date": "2020-01-01", "x_org": "Acme"}
        Before the fix, python-stix2 raised ExtraPropertiesError for these fields.
        allow_custom=True permits them.
        """
        obj = dict_to_stix(
            {
                "type": "ipv4-addr",
                "value": "203.0.113.42",
                "x_creation_date": "2020-06-15",
                "x_org": "Example Corp",
            }
        )
        assert obj.type == "ipv4-addr"
        assert obj.value == "203.0.113.42"
        # Custom fields are preserved on the STIX object
        assert obj.x_creation_date == "2020-06-15"
        assert obj.x_org == "Example Corp"

    def test_custom_x_fields_domain(self):
        """Custom x_ fields work for domain-name type (whois_lookup common case)."""
        obj = dict_to_stix(
            {
                "type": "domain-name",
                "value": "threat-actor.example",
                "x_registrar": "Evil Registrar Inc",
                "x_expiry": "2025-12-31",
            }
        )
        assert obj.type == "domain-name"
        assert obj.value == "threat-actor.example"
        assert obj.x_registrar == "Evil Registrar Inc"


# ---------------------------------------------------------------------------
# Database schema tests
# ---------------------------------------------------------------------------


class TestDatabaseSchema:
    """Verify all four tables are created with correct columns."""

    def test_all_tables_created(self, tmp_path):
        from sqlalchemy import create_engine, inspect

        engine = create_engine(f"sqlite:///{tmp_path / 'schema_test.db'}")
        Base.metadata.create_all(engine)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert "stix_objects" in tables
        assert "relationships" in tables
        assert "module_runs" in tables
        assert "notes" in tables

    def test_stix_objects_columns(self, tmp_path):
        from sqlalchemy import create_engine, inspect

        engine = create_engine(f"sqlite:///{tmp_path / 'cols_test.db'}")
        Base.metadata.create_all(engine)
        inspector = inspect(engine)
        cols = {c["name"] for c in inspector.get_columns("stix_objects")}
        assert {"id", "type", "value", "json_blob", "created_at"}.issubset(cols)

    def test_relationships_columns(self, tmp_path):
        from sqlalchemy import create_engine, inspect

        engine = create_engine(f"sqlite:///{tmp_path / 'rel_test.db'}")
        Base.metadata.create_all(engine)
        inspector = inspect(engine)
        cols = {c["name"] for c in inspector.get_columns("relationships")}
        assert {
            "id",
            "source_ref",
            "target_ref",
            "relationship_type",
            "json_blob",
            "created_at",
        }.issubset(cols)

    def test_module_runs_columns(self, tmp_path):
        from sqlalchemy import create_engine, inspect

        engine = create_engine(f"sqlite:///{tmp_path / 'runs_test.db'}")
        Base.metadata.create_all(engine)
        inspector = inspect(engine)
        cols = {c["name"] for c in inspector.get_columns("module_runs")}
        assert {"id", "module_name", "target", "timestamp", "result_count"}.issubset(cols)

    def test_notes_columns(self, tmp_path):
        from sqlalchemy import create_engine, inspect

        engine = create_engine(f"sqlite:///{tmp_path / 'notes_test.db'}")
        Base.metadata.create_all(engine)
        inspector = inspect(engine)
        cols = {c["name"] for c in inspector.get_columns("notes")}
        assert {"id", "stix_object_id", "content", "created_at"}.issubset(cols)


# ---------------------------------------------------------------------------
# WorkspaceManager CRUD tests
# ---------------------------------------------------------------------------


class TestWorkspaceManagerCRUD:
    """Test workspace lifecycle: create, list, switch, delete."""

    def test_create_makes_db_file(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("alpha")
        assert (tmp_path / "alpha.db").exists()

    def test_list_workspaces_empty(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        assert wm.list_workspaces() == []

    def test_list_workspaces_returns_created(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("alpha")
        wm.create("beta")
        names = wm.list_workspaces()
        assert "alpha" in names
        assert "beta" in names
        assert len(names) == 2

    def test_switch_changes_active(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("alpha")
        wm.create("beta")
        wm.switch("alpha")
        assert wm.active == "alpha"
        wm.switch("beta")
        assert wm.active == "beta"

    def test_switch_nonexistent_raises(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        with pytest.raises(ValueError, match="does not exist"):
            wm.switch("ghost")

    def test_delete_removes_db_file(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("alpha")
        assert (tmp_path / "alpha.db").exists()
        wm.delete("alpha")
        assert not (tmp_path / "alpha.db").exists()

    def test_delete_nonexistent_raises(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        with pytest.raises(ValueError, match="does not exist"):
            wm.delete("ghost")

    def test_default_workspace_auto_created_on_get_session(self, tmp_path):
        """First call to get_session() on a fresh WorkspaceManager creates 'default'."""
        wm = WorkspaceManager(workspace_dir=tmp_path)
        # Should not raise; creates default workspace automatically
        with wm.get_session() as session:
            assert session is not None
        assert wm.active == "default"
        assert (tmp_path / "default.db").exists()

    def test_create_duplicate_raises(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("alpha")
        with pytest.raises(ValueError, match="already exists"):
            wm.create("alpha")


# ---------------------------------------------------------------------------
# WorkspaceManager data operations
# ---------------------------------------------------------------------------


class TestStoreAndRetrieve:
    """Test store_stix_objects, get_stix_objects, and get_module_runs."""

    def test_store_plain_dicts_returns_count(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")
        dicts = [
            {"type": "ipv4-addr", "value": "1.2.3.4"},
            {"type": "domain-name", "value": "evil.com"},
        ]
        count = wm.store_stix_objects(dicts, module_name="osint/test", target="1.2.3.4")
        assert count == 2

    def test_stored_objects_retrievable(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")
        wm.store_stix_objects(
            [{"type": "ipv4-addr", "value": "1.2.3.4"}],
            module_name="osint/test",
            target="1.2.3.4",
        )
        objects = wm.get_stix_objects()
        assert len(objects) == 1
        assert objects[0]["type"] == "ipv4-addr"
        assert objects[0]["value"] == "1.2.3.4"

    def test_get_stix_objects_type_filter(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")
        wm.store_stix_objects(
            [
                {"type": "ipv4-addr", "value": "5.6.7.8"},
                {"type": "domain-name", "value": "filter-test.com"},
            ],
            module_name="osint/test",
            target="5.6.7.8",
        )
        ips = wm.get_stix_objects(type_filter="ipv4-addr")
        assert len(ips) == 1
        assert ips[0]["type"] == "ipv4-addr"

        domains = wm.get_stix_objects(type_filter="domain-name")
        assert len(domains) == 1
        assert domains[0]["value"] == "filter-test.com"

    def test_deduplication_by_stix_id(self, tmp_path):
        """Storing the same observable twice keeps only one copy (STIX ID dedup)."""
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")
        same = {"type": "ipv4-addr", "value": "9.9.9.9"}
        wm.store_stix_objects([same], module_name="osint/first", target="9.9.9.9")
        wm.store_stix_objects([same], module_name="osint/second", target="9.9.9.9")
        objects = wm.get_stix_objects()
        assert len(objects) == 1  # deduplicated

    def test_module_run_logged(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")
        wm.store_stix_objects(
            [{"type": "ipv4-addr", "value": "10.0.0.1"}],
            module_name="osint/whois_lookup",
            target="10.0.0.1",
        )
        runs = wm.get_module_runs()
        assert len(runs) == 1
        assert runs[0]["module_name"] == "osint/whois_lookup"
        assert runs[0]["target"] == "10.0.0.1"
        assert runs[0]["result_count"] == 1

    def test_multiple_module_runs_logged(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")
        wm.store_stix_objects(
            [{"type": "ipv4-addr", "value": "1.1.1.1"}],
            module_name="osint/whois_lookup",
            target="1.1.1.1",
        )
        wm.store_stix_objects(
            [
                {"type": "domain-name", "value": "cloudflare.com"},
                {"type": "ipv4-addr", "value": "1.0.0.1"},
            ],
            module_name="osint/dns_resolve",
            target="cloudflare.com",
        )
        runs = wm.get_module_runs()
        assert len(runs) == 2
        module_names = {r["module_name"] for r in runs}
        assert "osint/whois_lookup" in module_names
        assert "osint/dns_resolve" in module_names

    def test_unrecognized_type_not_stored_in_stix_objects(self, tmp_path):
        """Unrecognized dict types (pass-through from dict_to_stix) are skipped."""
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")
        count = wm.store_stix_objects(
            [{"type": "x-unknown", "value": "mystery"}],
            module_name="osint/test",
            target="mystery",
        )
        assert count == 0
        assert wm.get_stix_objects() == []

    def test_store_relationships(self, tmp_path):
        """Relationship SROs from module output are stored in relationships table."""
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")
        ip = create_ipv4("192.168.0.1")
        dom = create_domain("internal.corp")
        rel = create_relationship(dom.id, ip.id, "resolves-to")
        count = wm.store_stix_objects(
            [ip, dom, rel],
            module_name="osint/dns_resolve",
            target="192.168.0.1",
        )
        assert count == 3

    def test_get_stix_objects_returns_dicts(self, tmp_path):
        """get_stix_objects returns plain dicts, not SQLAlchemy model instances."""
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")
        wm.store_stix_objects(
            [{"type": "domain-name", "value": "dict-check.com"}],
            module_name="osint/test",
            target="dict-check.com",
        )
        objects = wm.get_stix_objects()
        assert isinstance(objects[0], dict)


# ---------------------------------------------------------------------------
# Analyst notes
# ---------------------------------------------------------------------------


class TestAnalystNotes:
    """Test add_note with and without stix_object_id linkage."""

    def test_add_note_standalone(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")
        # Should not raise
        wm.add_note("This IP belongs to Acme Corp.")

    def test_add_note_linked_to_stix_object(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")
        ip = create_ipv4("203.0.113.1")
        wm.store_stix_objects([ip], module_name="osint/test", target="203.0.113.1")
        # Link note to the stored object
        wm.add_note("Observed in APT campaign.", stix_object_id=ip.id)

    def test_notes_persisted(self, tmp_path):
        """Notes round-trip through the database."""
        from sqlalchemy import select

        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")
        wm.add_note("Investigation note #1")
        wm.add_note("Investigation note #2")
        # Query directly to verify persistence
        with wm.get_session() as session:
            notes = session.execute(select(AnalystNote)).scalars().all()
            assert len(notes) == 2
            contents = {n.content for n in notes}
            assert "Investigation note #1" in contents
            assert "Investigation note #2" in contents


# ---------------------------------------------------------------------------
# Workspace isolation
# ---------------------------------------------------------------------------


class TestWorkspaceIsolation:
    """Verify objects stored in workspace A are not visible in workspace B."""

    def test_isolation_between_workspaces(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("alpha")
        wm.create("beta")

        # Store in alpha
        wm.switch("alpha")
        wm.store_stix_objects(
            [{"type": "ipv4-addr", "value": "10.10.10.10"}],
            module_name="osint/test",
            target="10.10.10.10",
        )

        # Store in beta (different object)
        wm.switch("beta")
        wm.store_stix_objects(
            [{"type": "domain-name", "value": "beta-only.com"}],
            module_name="osint/test",
            target="beta-only.com",
        )

        # Alpha only has its IP
        wm.switch("alpha")
        alpha_objects = wm.get_stix_objects()
        assert len(alpha_objects) == 1
        assert alpha_objects[0]["value"] == "10.10.10.10"

        # Beta only has its domain
        wm.switch("beta")
        beta_objects = wm.get_stix_objects()
        assert len(beta_objects) == 1
        assert beta_objects[0]["value"] == "beta-only.com"

    def test_module_runs_isolated(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("alpha")
        wm.create("beta")

        wm.switch("alpha")
        wm.store_stix_objects(
            [{"type": "ipv4-addr", "value": "1.1.1.1"}],
            module_name="osint/alpha_module",
            target="1.1.1.1",
        )

        wm.switch("beta")
        runs = wm.get_module_runs()
        assert len(runs) == 0  # beta has no runs


# ---------------------------------------------------------------------------
# Production sequence: module hunt() output -> workspace storage -> retrieval
# ---------------------------------------------------------------------------


class TestProductionSequence:
    """
    Tests that exercise the real production call chain:
    module.hunt() returns plain dicts -> workspace.store_stix_objects() converts
    and stores them -> workspace.get_stix_objects() retrieves them.

    This is the scenario that would have caught the missing test coverage
    described in the implementer prompt.
    """

    def test_full_module_output_flow(self, tmp_path):
        """Simulates a module hunt() -> workspace store -> retrieve cycle."""
        # Simulate what whois_lookup or dns_resolve returns
        module_output = [
            {"type": "ipv4-addr", "value": "185.220.101.1"},
            {"type": "domain-name", "value": "tor-exit.example.com"},
            {"type": "ipv4-addr", "value": "185.220.101.2"},
        ]

        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")

        count = wm.store_stix_objects(
            module_output,
            module_name="osint/whois_lookup",
            target="185.220.101.1",
        )
        assert count == 3

        # Retrieve and verify
        all_objects = wm.get_stix_objects()
        assert len(all_objects) == 3

        ips = wm.get_stix_objects(type_filter="ipv4-addr")
        assert len(ips) == 2

        domains = wm.get_stix_objects(type_filter="domain-name")
        assert len(domains) == 1
        assert domains[0]["value"] == "tor-exit.example.com"

        runs = wm.get_module_runs()
        assert len(runs) == 1
        assert runs[0]["result_count"] == 3

    def test_two_modules_sequential_on_same_workspace(self, tmp_path):
        """Two sequential module runs (like auto-pivoting) share the workspace."""
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")

        # First module run
        wm.store_stix_objects(
            [{"type": "ipv4-addr", "value": "8.8.8.8"}],
            module_name="osint/dns_resolve",
            target="google.com",
        )

        # Second module run -- same IP, new domain (dedup + new)
        wm.store_stix_objects(
            [
                {"type": "ipv4-addr", "value": "8.8.8.8"},  # duplicate
                {"type": "domain-name", "value": "google.com"},  # new
            ],
            module_name="osint/whois_lookup",
            target="8.8.8.8",
        )

        # Only 2 unique objects (deduplication works across runs)
        all_objects = wm.get_stix_objects()
        assert len(all_objects) == 2

        # But both module runs are logged
        runs = wm.get_module_runs()
        assert len(runs) == 2


# ---------------------------------------------------------------------------
# Regression tests for Bug 1: UnboundExecutionError when no workspace active
# ---------------------------------------------------------------------------


class TestWorkspaceBindRegression:
    """Regression tests for the SQLAlchemy UnboundExecutionError bug.

    Root cause: store_stix_objects() and add_note() opened Session(self._engine)
    without first calling _ensure_active(), so self._engine remained None when
    no workspace had been explicitly switched to. This caused SQLAlchemy to raise
    UnboundExecutionError on session.get() / session.add().

    Fix: _ensure_active() is now called at the top of both methods, auto-creating
    and switching to the 'default' workspace when none is active (same lazy-init
    semantics already used by all other data methods).

    See DEC-WS-006.
    """

    def test_store_stix_objects_does_not_raise_unbound_execution_error(self, tmp_path):
        """store_stix_objects() must not raise UnboundExecutionError with a fresh
        WorkspaceManager that has never had switch() called.

        This reproduces the user's exact bug: the production agent creates a fresh
        WorkspaceManager, calls store_stix_objects() without an explicit switch(),
        and gets UnboundExecutionError because self._engine is None.
        """
        from sqlalchemy.exc import UnboundExecutionError

        wm = WorkspaceManager(workspace_dir=tmp_path)
        # Deliberately do NOT call wm.create() or wm.switch() — this is the
        # production failure mode. _ensure_active() must auto-create 'default'.
        objects = [
            {"type": "ipv4-addr", "value": "72.62.35.76"},
            {"type": "domain-name", "value": "example.com"},
        ]
        try:
            count = wm.store_stix_objects(
                objects,
                module_name="osint/censys_host",
                target="72.62.35.76",
            )
        except UnboundExecutionError as exc:
            pytest.fail(
                f"store_stix_objects raised UnboundExecutionError — "
                f"_ensure_active() was not called before opening the Session: {exc}"
            )
        # Auto-created default workspace and stored both objects
        assert count == 2
        assert wm.active == "default"

    def test_get_stix_objects_returns_persisted_objects_round_trip(self, tmp_path):
        """Round-trip: store via a fresh manager, retrieve from the same manager.

        Verifies that the auto-created default workspace persists objects that can
        subsequently be retrieved with get_stix_objects().
        """
        wm = WorkspaceManager(workspace_dir=tmp_path)
        # Fresh manager — no explicit create/switch
        wm.store_stix_objects(
            [
                {"type": "ipv4-addr", "value": "1.1.1.1"},
                {"type": "domain-name", "value": "cloudflare.com"},
            ],
            module_name="cti/otx",
            target="1.1.1.1",
        )
        objects = wm.get_stix_objects()
        assert len(objects) == 2
        types = {o["type"] for o in objects}
        assert "ipv4-addr" in types
        assert "domain-name" in types

    def test_add_note_does_not_raise_unbound_execution_error_on_fresh_manager(self, tmp_path):
        """add_note() must not raise UnboundExecutionError on a fresh WorkspaceManager.

        add_note() had the same missing _ensure_active() call as store_stix_objects().
        """
        from sqlalchemy.exc import UnboundExecutionError

        wm = WorkspaceManager(workspace_dir=tmp_path)
        try:
            wm.add_note("Investigation note — no UnboundExecutionError expected.")
        except UnboundExecutionError as exc:
            pytest.fail(
                f"add_note raised UnboundExecutionError — _ensure_active() was not called: {exc}"
            )

    def test_get_stix_objects_on_fresh_manager_returns_empty_list(self, tmp_path):
        """get_stix_objects() must not raise UnboundExecutionError on a fresh WorkspaceManager.

        Regression for M-3's pre-hunt SCO id capture (tools.py:443-445) which calls
        get_stix_objects() BEFORE store_stix_objects() on a brand-new ap chat session.
        Previously self._engine was None at that point -> UnboundExecutionError crash.
        Fix: _ensure_active() added at the top of get_stix_objects() (DEC-WS-006).
        """
        from sqlalchemy.exc import UnboundExecutionError

        wm = WorkspaceManager(workspace_dir=tmp_path)
        # Deliberately do NOT call create() or switch() — this is the M-3 failure mode.
        try:
            result = wm.get_stix_objects()
        except UnboundExecutionError as exc:
            pytest.fail(
                f"get_stix_objects raised UnboundExecutionError on fresh manager — "
                f"_ensure_active() was not called before opening the Session: {exc}"
            )
        assert result == [], f"Expected empty list on fresh workspace, got {result!r}"
        assert wm.active == "default", (
            f"Expected 'default' workspace to be auto-created, got {wm.active!r}"
        )

    def test_get_module_runs_on_fresh_manager_returns_empty_list(self, tmp_path):
        """get_module_runs() must not raise UnboundExecutionError on a fresh WorkspaceManager.

        Regression for M-2's Timing extractor path which calls get_module_runs()
        BEFORE store_stix_objects() on a fresh session.
        Previously self._engine was None -> UnboundExecutionError crash.
        Fix: _ensure_active() added at the top of get_module_runs() (DEC-WS-006).
        """
        from sqlalchemy.exc import UnboundExecutionError

        wm = WorkspaceManager(workspace_dir=tmp_path)
        # Deliberately do NOT call create() or switch().
        try:
            result = wm.get_module_runs()
        except UnboundExecutionError as exc:
            pytest.fail(
                f"get_module_runs raised UnboundExecutionError on fresh manager — "
                f"_ensure_active() was not called before opening the Session: {exc}"
            )
        assert result == [], f"Expected empty list on fresh workspace, got {result!r}"
        assert wm.active == "default", (
            f"Expected 'default' workspace to be auto-created, got {wm.active!r}"
        )

    def test_get_stix_objects_before_store_mirrors_production_m3_sequence(self, tmp_path):
        """Integration: get_stix_objects() → store_stix_objects() → get_stix_objects() succeeds.

        This reproduces the exact M-3 production sequence: capture pre-hunt SCO ids
        (get_stix_objects before any store), run the tool (store_stix_objects), then
        capture post-hunt SCO ids (get_stix_objects again). The pre-hunt call is the
        one that previously crashed on fresh sessions.

        Crosses WorkspaceManager._ensure_active(), _create_workspace(), and the
        SQLAlchemy Session open, verifying the full state-transition path.
        """
        wm = WorkspaceManager(workspace_dir=tmp_path)

        # Step 1: pre-hunt id capture (the previously-crashing M-3 call)
        scos_before = wm.get_stix_objects()
        scos_before_ids = {s["id"] for s in scos_before if s.get("id")}
        assert scos_before_ids == set(), "Fresh workspace must have no pre-existing SCOs"

        # Step 2: tool execution stores new SCOs
        wm.store_stix_objects(
            [
                {"type": "ipv4-addr", "value": "8.8.8.8"},
                {"type": "domain-name", "value": "greynoise.io"},
            ],
            module_name="osint/greynoise_lookup",
            target="8.8.8.8",
        )

        # Step 3: post-hunt id capture — new SCOs visible
        scos_after = wm.get_stix_objects()
        new_ids = {s["id"] for s in scos_after if s.get("id")} - scos_before_ids
        assert len(new_ids) == 2, f"Expected 2 new SCOs after store, got {len(new_ids)}"

        # Workspace auto-created and stable across all three calls
        assert wm.active == "default"


# ---------------------------------------------------------------------------
# Provenance augmentation tests (DEC-59-STIX-PROVENANCE-001..004, #59)
# ---------------------------------------------------------------------------


class TestProvenanceAugmentation:
    """Tests for store_stix_objects() provenance kwargs (Evaluation Contract #59).

    Covers:
    - Evaluation Contract test 6: test_workspace_rejects_caller_supplied_x_ap_fields
    - Provenance kwargs persist into json_blob
    - x_ap_fetched_at always populated (even without kwargs)
    - Legacy call (no kwargs) produces x_ap_fetched_at only
    - Caller-supplied x_ap_* keys stripped with a warning (DEC-59-STIX-PROVENANCE-001)
    """

    def _make_wm(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")
        return wm

    def test_provenance_kwargs_persist_into_json_blob(self, tmp_path):
        """All four provenance kwargs survive into the stored json_blob."""
        wm = self._make_wm(tmp_path)
        wm.store_stix_objects(
            [{"type": "ipv4-addr", "value": "1.2.3.4"}],
            module_name="test/mod",
            target="1.2.3.4",
            source_url="https://api.example/ip/1.2.3.4",
            api_version="v2",
            response_sha256="d" * 64,
            fetched_at="2025-01-15T09:00:00Z",
        )

        objects = wm.get_stix_objects()
        assert len(objects) == 1
        obj = objects[0]
        assert obj["x_ap_source_url"] == "https://api.example/ip/1.2.3.4"
        assert obj["x_ap_api_version"] == "v2"
        assert obj["x_ap_response_sha256"] == "d" * 64
        assert obj["x_ap_fetched_at"] == "2025-01-15T09:00:00Z"

    def test_x_ap_fetched_at_always_populated(self, tmp_path):
        """x_ap_fetched_at is always present even when no kwargs supplied."""
        wm = self._make_wm(tmp_path)
        wm.store_stix_objects(
            [{"type": "domain-name", "value": "always-ts.example.com"}],
            module_name="test/mod",
            target="always-ts.example.com",
        )
        objects = wm.get_stix_objects()
        assert len(objects) == 1
        assert "x_ap_fetched_at" in objects[0]
        assert objects[0]["x_ap_fetched_at"] is not None
        # Must be a non-empty string ending in Z (RFC 3339)
        ts = objects[0]["x_ap_fetched_at"]
        assert isinstance(ts, str) and ts.endswith("Z")

    def test_legacy_call_produces_fetched_at_only(self, tmp_path):
        """Legacy call (no provenance kwargs) only adds x_ap_fetched_at."""
        wm = self._make_wm(tmp_path)
        wm.store_stix_objects(
            [{"type": "ipv4-addr", "value": "5.6.7.8"}],
            module_name="test/legacy",
            target="5.6.7.8",
        )
        obj = wm.get_stix_objects()[0]
        # fetched_at is always present
        assert "x_ap_fetched_at" in obj
        # The other three must be absent (not null — absent from dict entirely)
        assert "x_ap_source_url" not in obj
        assert "x_ap_api_version" not in obj
        assert "x_ap_response_sha256" not in obj

    def test_workspace_rejects_caller_supplied_x_ap_fields(self, tmp_path):
        """Evaluation Contract test 6: caller-supplied x_ap_* keys are stripped.

        DEC-59-STIX-PROVENANCE-001: the workspace is the sole x_ap_* authority.
        When a module dict contains x_ap_* keys, the workspace strips them and
        emits a UserWarning. The stored object uses the workspace-supplied
        provenance values, not the caller's.
        """
        wm = self._make_wm(tmp_path)

        bad_dict = {
            "type": "ipv4-addr",
            "value": "9.8.7.6",
            "x_ap_source_url": "https://caller-injected.bad/endpoint",
            "x_ap_api_version": "evil-v999",
            "x_ap_response_sha256": "e" * 64,
            "x_ap_fetched_at": "1970-01-01T00:00:00Z",
        }

        # The workspace must emit a UserWarning about the stripped keys
        with pytest.warns(UserWarning, match="x_ap_"):
            wm.store_stix_objects(
                [bad_dict],
                module_name="osint/bad_module",
                target="9.8.7.6",
                # Workspace-authoritative provenance
                source_url="https://workspace-real.example/endpoint",
                api_version="v1",
                response_sha256="f" * 64,
            )

        objects = wm.get_stix_objects()
        assert len(objects) == 1
        obj = objects[0]

        # The caller's injected values must NOT appear in the stored blob
        assert obj.get("x_ap_source_url") != "https://caller-injected.bad/endpoint", (
            "Caller-injected x_ap_source_url was not stripped"
        )
        assert obj.get("x_ap_api_version") != "evil-v999", (
            "Caller-injected x_ap_api_version was not stripped"
        )
        assert obj.get("x_ap_response_sha256") != "e" * 64, (
            "Caller-injected x_ap_response_sha256 was not stripped"
        )

        # The workspace-supplied provenance must appear
        assert obj.get("x_ap_source_url") == "https://workspace-real.example/endpoint"
        assert obj.get("x_ap_api_version") == "v1"
        assert obj.get("x_ap_response_sha256") == "f" * 64

    def test_caller_supplied_x_ap_without_workspace_kwargs(self, tmp_path):
        """Caller-supplied x_ap_* stripped even when workspace supplies no kwargs.

        The warning is still emitted; the stored blob gets only the workspace
        default x_ap_fetched_at (not the caller's injected timestamp).
        """
        wm = self._make_wm(tmp_path)

        bad_dict = {
            "type": "domain-name",
            "value": "stripped-only.example.com",
            "x_ap_fetched_at": "1970-01-01T00:00:00Z",  # injected by caller
        }

        with pytest.warns(UserWarning, match="x_ap_"):
            wm.store_stix_objects(
                [bad_dict],
                module_name="test/bad",
                target="stripped-only.example.com",
                # No workspace kwargs — defaults apply
            )

        obj = wm.get_stix_objects()[0]
        # The workspace-default fetched_at must NOT be the caller's epoch value
        assert obj["x_ap_fetched_at"] != "1970-01-01T00:00:00Z", (
            "Caller-injected x_ap_fetched_at was not replaced by workspace default"
        )
        # But x_ap_fetched_at must still be present (workspace default)
        assert obj["x_ap_fetched_at"] is not None

    def test_fetched_at_caller_override_accepted(self, tmp_path):
        """Caller-supplied fetched_at kwarg overrides the workspace default."""
        wm = self._make_wm(tmp_path)
        custom_ts = "2024-06-15T08:30:00Z"
        wm.store_stix_objects(
            [{"type": "url", "value": "https://custom-ts.example/path"}],
            module_name="test/mod",
            target="custom-ts.example",
            fetched_at=custom_ts,
        )
        obj = wm.get_stix_objects()[0]
        assert obj["x_ap_fetched_at"] == custom_ts


# ---------------------------------------------------------------------------
# Milestone sentinel — F63 DEC-63-MILESTONE-CATCHUP-001
# ---------------------------------------------------------------------------


class TestMilestoneSentinel:
    """Verify get_last_milestone_id / set_last_milestone_id round-trip correctly.

    The sentinel uses a score_events row with action="_milestone_sentinel"
    (no schema change). Points=0 so it does not affect get_total_score().
    get_recent_scores() excludes the sentinel row.
    """

    def _make_wm(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")
        return wm

    def test_get_last_milestone_id_fresh_workspace_returns_none(self, tmp_path):
        """Fresh workspace has no milestone sentinel → returns None."""
        wm = self._make_wm(tmp_path)
        assert wm.get_last_milestone_id() is None

    def test_set_then_get_round_trips(self, tmp_path):
        """set_last_milestone_id then get returns the same value."""
        wm = self._make_wm(tmp_path)
        wm.set_last_milestone_id(2)
        assert wm.get_last_milestone_id() == 2

    def test_set_overwrites_previous(self, tmp_path):
        """Second set_last_milestone_id replaces the first (idempotent upsert)."""
        wm = self._make_wm(tmp_path)
        wm.set_last_milestone_id(1)
        wm.set_last_milestone_id(3)
        assert wm.get_last_milestone_id() == 3

    def test_sentinel_does_not_affect_total_score(self, tmp_path):
        """Sentinel row has points=0; get_total_score() is unaffected."""
        wm = self._make_wm(tmp_path)
        wm.store_score_events([{"action": "new_ip", "points": 100, "indicator": "1.2.3.4"}])
        wm.set_last_milestone_id(1)
        assert wm.get_total_score() == 100

    def test_sentinel_excluded_from_recent_scores(self, tmp_path):
        """get_recent_scores() does not include the sentinel row."""
        wm = self._make_wm(tmp_path)
        wm.store_score_events([{"action": "new_ip", "points": 100, "indicator": "1.2.3.4"}])
        wm.set_last_milestone_id(1)
        recent = wm.get_recent_scores(limit=10)
        actions = [r["action"] for r in recent]
        assert "_milestone_sentinel" not in actions

    def test_only_one_sentinel_row_after_multiple_sets(self, tmp_path):
        """Multiple set calls leave exactly one sentinel row (no accumulation)."""
        wm = self._make_wm(tmp_path)
        for i in range(1, 6):
            wm.set_last_milestone_id(i)
        # get_last_milestone_id should return 5, not some earlier value
        assert wm.get_last_milestone_id() == 5


# ---------------------------------------------------------------------------
# M-4 reserved actions filter — DEC-M4-PERSIST-002
# ---------------------------------------------------------------------------


class TestReservedActionsFilter:
    """Verify that M-4 sentinel rows are excluded from get_recent_scores().

    DEC-M4-PERSIST-002: _RESERVED_ACTIONS frozenset covers all three reserved
    actions; get_recent_scores() uses .notin_(_RESERVED_ACTIONS).

    Evaluation Contract gates:
      W1  _dossier_state_snapshot row excluded from get_recent_scores()
      W2  _predictions_log row excluded from get_recent_scores()
      W3  _RESERVED_ACTIONS constant covers all three reserved actions (regression guard)
    """

    def _make_wm(self, tmp_path):
        wm = WorkspaceManager(workspace_dir=tmp_path)
        wm.create("default")
        wm.switch("default")
        return wm

    def test_dossier_state_snapshot_excluded_from_recent_scores(self, tmp_path):
        """W1: _dossier_state_snapshot rows are excluded from get_recent_scores()."""
        from adversary_pursuit.dossier.state import (
            DOSSIER_STATE_SENTINEL_ACTION,
            default_deferred_state,
            save_dossier_state,
        )

        wm = self._make_wm(tmp_path)
        wm.store_score_events([{"action": "new_ip", "points": 5, "indicator": "1.2.3.4"}])
        save_dossier_state(wm, default_deferred_state())

        recent = wm.get_recent_scores(limit=50)
        actions = {e["action"] for e in recent}
        assert DOSSIER_STATE_SENTINEL_ACTION not in actions
        assert "new_ip" in actions

    def test_predictions_log_excluded_from_recent_scores(self, tmp_path):
        """W2: _predictions_log rows are excluded from get_recent_scores()."""
        from adversary_pursuit.dossier.predictions import (
            PREDICTIONS_LOG_SENTINEL_ACTION,
            ExpectedEvidence,
            PersistedPrediction,
            save_predictions_log,
        )

        wm = self._make_wm(tmp_path)
        wm.store_score_events([{"action": "new_domain", "points": 3, "indicator": "evil.com"}])
        pred = PersistedPrediction(
            prediction_id="pred-00000001",
            text="Test prediction",
            slot="infrastructure",
            status="pending",
            expected_evidence=ExpectedEvidence(sco_type="domain-name"),
            created_at="2026-06-01T00:00:00+00:00",
        )
        save_predictions_log(wm, [pred])

        recent = wm.get_recent_scores(limit=50)
        actions = {e["action"] for e in recent}
        assert PREDICTIONS_LOG_SENTINEL_ACTION not in actions
        assert "new_domain" in actions

    def test_reserved_actions_constant_covers_all_three(self, tmp_path):
        """W3: _RESERVED_ACTIONS frozenset contains exactly the three documented actions.

        This is a regression guard: forces a code change if a future implementer
        adds a fourth reserved action without updating the constant.
        """
        wm = self._make_wm(tmp_path)
        reserved = wm._RESERVED_ACTIONS
        assert "_milestone_sentinel" in reserved, (
            "_milestone_sentinel missing from _RESERVED_ACTIONS"
        )
        assert "_dossier_state_snapshot" in reserved, (
            "_dossier_state_snapshot missing from _RESERVED_ACTIONS"
        )
        assert "_predictions_log" in reserved, "_predictions_log missing from _RESERVED_ACTIONS"
        assert len(reserved) == 3, (
            f"_RESERVED_ACTIONS has {len(reserved)} entries; expected 3. "
            "Adding a fourth reserved action requires a planner re-stage and updating this test."
        )

    def test_total_score_unaffected_by_sentinel_rows(self, tmp_path):
        """All sentinel rows have points=0 so get_total_score() is not inflated."""
        from adversary_pursuit.dossier.predictions import (
            ExpectedEvidence,
            PersistedPrediction,
            save_predictions_log,
        )
        from adversary_pursuit.dossier.state import default_deferred_state, save_dossier_state

        wm = self._make_wm(tmp_path)
        wm.store_score_events([{"action": "new_ip", "points": 42, "indicator": "1.2.3.4"}])
        save_dossier_state(wm, default_deferred_state())
        pred = PersistedPrediction(
            prediction_id="pred-00000001",
            text="Test",
            slot="infrastructure",
            status="pending",
            expected_evidence=ExpectedEvidence(sco_type="ipv4-addr"),
            created_at="2026-06-01T00:00:00+00:00",
        )
        save_predictions_log(wm, [pred])
        wm.set_last_milestone_id(1)

        assert wm.get_total_score() == 42
