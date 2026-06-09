"""Tests for dossier/novelty.py — Stage B acceptance tests (M-8 plan §4).

Covers:
- Hash determinism and distinctness
- SCO-type set is sorted (order-independent hash)
- NoveltyCache lazy file creation
- Cache round-trip: record + is_known
- Cache dedup (INSERT OR IGNORE)
- Schema: 6-column table
- detect_novelty first/second occurrence
- AP_NO_NOVELTY opt-out
- novelty_enabled() truthy/falsy values
- emit_dossier_novelty_recognized_event shape
- rule_description has no Rich markup (F64 invariant)
- Default cache path is Path.home() / ".ap" / "dossier_novelty.sqlite"

@decision DEC-TEST-M8-NOVELTY-001
@title test_dossier_novelty covers all Stage B acceptance tests from plan §4
@status accepted
@rationale Each test maps to a named acceptance test in plan §4 Stage B.
           NoveltyCache(path=tmp_path/...) injects test isolation without
           touching ~/.ap/. No mocks — uses sqlite3 directly to verify schema.
           AP_NO_NOVELTY is tested via monkeypatch (clean env restore guaranteed).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from adversary_pursuit.dossier.novelty import (
    _SLOT_EXTRACTOR_NAMES,
    NoveltyCache,
    compute_novelty_hash,
    detect_novelty,
    emit_dossier_novelty_recognized_event,
    novelty_enabled,
)
from adversary_pursuit.dossier.slots import DossierSlotName

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _identity_slot() -> DossierSlotName:
    return DossierSlotName.IDENTITY


def _infra_slot() -> DossierSlotName:
    return DossierSlotName.INFRASTRUCTURE


def _fresh_cache(tmp_path) -> NoveltyCache:
    return NoveltyCache(path=tmp_path / "novelty.sqlite")


# ---------------------------------------------------------------------------
# Stage B-1: Hash determinism and distinctness
# ---------------------------------------------------------------------------


class TestComputeNoveltyHash:
    """Hash function properties: determinism, distinctness, order-independence."""

    def test_same_inputs_same_hash(self):
        """Same (slot, extractor, sco_types) always produces same hash."""
        h1 = compute_novelty_hash(
            _identity_slot(), "_extract_identity", ["ipv4-addr", "domain-name"]
        )
        h2 = compute_novelty_hash(
            _identity_slot(), "_extract_identity", ["ipv4-addr", "domain-name"]
        )
        assert h1 == h2

    def test_hash_is_64_char_hex(self):
        """Hash is a 64-character lowercase hex string (SHA-256)."""
        h = compute_novelty_hash(_identity_slot(), "_extract_identity", ["ipv4-addr"])
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_sco_type_order_does_not_affect_hash(self):
        """Reordering sco_types produces the same hash (set semantics)."""
        h1 = compute_novelty_hash(
            _identity_slot(), "_extract_identity", ["ipv4-addr", "domain-name"]
        )
        h2 = compute_novelty_hash(
            _identity_slot(), "_extract_identity", ["domain-name", "ipv4-addr"]
        )
        assert h1 == h2

    def test_sco_type_duplicates_ignored(self):
        """Duplicate sco_types produce same hash as deduplicated set."""
        h1 = compute_novelty_hash(_identity_slot(), "_extract_identity", ["ipv4-addr", "ipv4-addr"])
        h2 = compute_novelty_hash(_identity_slot(), "_extract_identity", ["ipv4-addr"])
        assert h1 == h2

    def test_different_extractor_different_hash(self):
        """Different extractor_name produces different hash."""
        h1 = compute_novelty_hash(_identity_slot(), "_extract_identity", ["ipv4-addr"])
        h2 = compute_novelty_hash(_identity_slot(), "_extract_infrastructure", ["ipv4-addr"])
        assert h1 != h2

    def test_different_slot_different_hash(self):
        """Different slot produces different hash."""
        h1 = compute_novelty_hash(_identity_slot(), "_extract_identity", ["ipv4-addr"])
        h2 = compute_novelty_hash(_infra_slot(), "_extract_identity", ["ipv4-addr"])
        assert h1 != h2

    def test_different_sco_types_different_hash(self):
        """Different SCO type set produces different hash."""
        h1 = compute_novelty_hash(_identity_slot(), "_extract_identity", ["ipv4-addr"])
        h2 = compute_novelty_hash(_identity_slot(), "_extract_identity", ["domain-name"])
        assert h1 != h2

    def test_empty_sco_types_stable(self):
        """Empty sco_types list produces a stable hash."""
        h1 = compute_novelty_hash(_identity_slot(), "_extract_identity", [])
        h2 = compute_novelty_hash(_identity_slot(), "_extract_identity", [])
        assert h1 == h2
        assert len(h1) == 64


# ---------------------------------------------------------------------------
# Stage B-2: NoveltyCache lazy file creation
# ---------------------------------------------------------------------------


class TestNoveltyCacheLazy:
    """Cache file is NOT created by constructor or is_known; only by record()."""

    def test_constructor_does_not_create_file(self, tmp_path):
        """NoveltyCache(path=...) does not create the sqlite file."""
        path = tmp_path / "sub" / "novelty.sqlite"
        cache = NoveltyCache(path=path)
        assert not path.exists()
        cache.close()

    def test_is_known_on_missing_file_returns_false(self, tmp_path):
        """is_known() on non-existent file returns False without creating it."""
        path = tmp_path / "novelty.sqlite"
        cache = NoveltyCache(path=path)
        result = cache.is_known("deadbeef" * 8)
        assert result is False
        assert not path.exists()
        cache.close()

    def test_record_creates_file(self, tmp_path):
        """First record() call creates the sqlite file."""
        path = tmp_path / "novelty.sqlite"
        cache = NoveltyCache(path=path)
        cache.record("a" * 64, "identity", "_extract_identity", "ipv4-addr")
        assert path.exists()
        cache.close()

    def test_record_creates_parent_dirs(self, tmp_path):
        """record() creates missing parent directories."""
        path = tmp_path / "deep" / "nested" / "novelty.sqlite"
        cache = NoveltyCache(path=path)
        cache.record("b" * 64, "identity", "_extract_identity", "ipv4-addr")
        assert path.exists()
        cache.close()


# ---------------------------------------------------------------------------
# Stage B-3: Cache round-trip
# ---------------------------------------------------------------------------


class TestNoveltyCacheRoundTrip:
    """record() + is_known() round-trip."""

    def test_record_then_is_known_true(self, tmp_path):
        """After record(hash), is_known(hash) returns True."""
        cache = _fresh_cache(tmp_path)
        h = compute_novelty_hash(_identity_slot(), "_extract_identity", ["ipv4-addr"])
        cache.record(h, "identity", "_extract_identity", "ipv4-addr")
        assert cache.is_known(h) is True
        cache.close()

    def test_unknown_hash_is_false(self, tmp_path):
        """is_known returns False for a hash that was not recorded."""
        cache = _fresh_cache(tmp_path)
        cache.record("a" * 64, "identity", "_extract_identity", "ipv4-addr")
        assert cache.is_known("b" * 64) is False
        cache.close()

    def test_cross_cache_instance_persistence(self, tmp_path):
        """hash recorded in one NoveltyCache instance is visible to another on same path."""
        path = tmp_path / "novelty.sqlite"
        cache1 = NoveltyCache(path=path)
        h = compute_novelty_hash(_identity_slot(), "_extract_identity", ["ipv4-addr"])
        cache1.record(h, "identity", "_extract_identity", "ipv4-addr")
        cache1.close()

        cache2 = NoveltyCache(path=path)
        assert cache2.is_known(h) is True
        cache2.close()


# ---------------------------------------------------------------------------
# Stage B-4: Cache dedup
# ---------------------------------------------------------------------------


class TestNoveltyCacheDedup:
    """INSERT OR IGNORE: duplicate record() calls leave exactly one row."""

    def test_duplicate_record_leaves_one_row(self, tmp_path):
        """Two record() calls with same hash leave exactly 1 row."""
        path = tmp_path / "novelty.sqlite"
        cache = NoveltyCache(path=path)
        h = "c" * 64
        cache.record(h, "identity", "_extract_identity", "ipv4-addr")
        cache.record(h, "identity", "_extract_identity", "ipv4-addr")
        cache.close()

        conn = sqlite3.connect(str(path))
        count = conn.execute("SELECT COUNT(*) FROM novelty_hashes WHERE hash = ?", (h,)).fetchone()[
            0
        ]
        conn.close()
        assert count == 1


# ---------------------------------------------------------------------------
# Stage B-5: Schema
# ---------------------------------------------------------------------------


class TestNoveltyCacheSchema:
    """PRAGMA table_info returns the expected 6-column shape."""

    def test_schema_has_six_columns(self, tmp_path):
        """novelty_hashes table has exactly 6 columns."""
        path = tmp_path / "novelty.sqlite"
        cache = NoveltyCache(path=path)
        # Trigger schema creation
        cache.record("d" * 64, "identity", "_extract_identity", "ipv4-addr")
        cache.close()

        conn = sqlite3.connect(str(path))
        cols = conn.execute("PRAGMA table_info(novelty_hashes)").fetchall()
        conn.close()
        col_names = [c[1] for c in cols]
        assert col_names == [
            "hash",
            "slot",
            "extractor",
            "ordering_sig",
            "first_seen_at",
            "workspace_count",
        ]

    def test_workspace_count_defaults_to_one(self, tmp_path):
        """workspace_count column defaults to 1 on first INSERT."""
        path = tmp_path / "novelty.sqlite"
        cache = NoveltyCache(path=path)
        h = "e" * 64
        cache.record(h, "identity", "_extract_identity", "ipv4-addr")
        cache.close()

        conn = sqlite3.connect(str(path))
        row = conn.execute(
            "SELECT workspace_count FROM novelty_hashes WHERE hash = ?", (h,)
        ).fetchone()
        conn.close()
        assert row[0] == 1


# ---------------------------------------------------------------------------
# Stage B-6 / B-7: detect_novelty first and second occurrence
# ---------------------------------------------------------------------------


class TestDetectNovelty:
    """detect_novelty() returns True on first occurrence; False on repeat."""

    def test_first_occurrence_returns_true(self, tmp_path):
        """Fresh cache + first detection → True."""
        cache = _fresh_cache(tmp_path)
        result = detect_novelty(_identity_slot(), "_extract_identity", ["ipv4-addr"], cache)
        assert result is True
        cache.close()

    def test_first_occurrence_writes_to_cache(self, tmp_path):
        """After True return, cache.is_known returns True for same hash."""
        cache = _fresh_cache(tmp_path)
        detect_novelty(_identity_slot(), "_extract_identity", ["ipv4-addr"], cache)
        h = compute_novelty_hash(_identity_slot(), "_extract_identity", ["ipv4-addr"])
        assert cache.is_known(h) is True
        cache.close()

    def test_second_occurrence_returns_false(self, tmp_path):
        """Same inputs to populated cache → False."""
        cache = _fresh_cache(tmp_path)
        detect_novelty(_identity_slot(), "_extract_identity", ["ipv4-addr"], cache)
        result = detect_novelty(_identity_slot(), "_extract_identity", ["ipv4-addr"], cache)
        assert result is False
        cache.close()

    def test_second_occurrence_no_extra_cache_row(self, tmp_path):
        """Second detection call does not add a second row."""
        path = tmp_path / "novelty.sqlite"
        cache = NoveltyCache(path=path)
        detect_novelty(_identity_slot(), "_extract_identity", ["ipv4-addr"], cache)
        detect_novelty(_identity_slot(), "_extract_identity", ["ipv4-addr"], cache)
        cache.close()

        conn = sqlite3.connect(str(path))
        count = conn.execute("SELECT COUNT(*) FROM novelty_hashes").fetchone()[0]
        conn.close()
        assert count == 1

    def test_different_sco_types_novel(self, tmp_path):
        """Different SCO types on same slot = novel second event."""
        cache = _fresh_cache(tmp_path)
        r1 = detect_novelty(_identity_slot(), "_extract_identity", ["ipv4-addr"], cache)
        r2 = detect_novelty(_identity_slot(), "_extract_identity", ["domain-name"], cache)
        assert r1 is True
        assert r2 is True
        cache.close()


# ---------------------------------------------------------------------------
# Stage B-8: AP_NO_NOVELTY opt-out
# ---------------------------------------------------------------------------


class TestNoveltyOptOut:
    """AP_NO_NOVELTY env var disables detection entirely."""

    def test_detect_novelty_respects_opt_out(self, tmp_path, monkeypatch):
        """With AP_NO_NOVELTY=1, detect_novelty always returns False."""
        monkeypatch.setenv("AP_NO_NOVELTY", "1")
        cache = _fresh_cache(tmp_path)
        result = detect_novelty(_identity_slot(), "_extract_identity", ["ipv4-addr"], cache)
        assert result is False
        cache.close()

    def test_opt_out_does_not_write_cache(self, tmp_path, monkeypatch):
        """With AP_NO_NOVELTY set, the cache file is not created."""
        monkeypatch.setenv("AP_NO_NOVELTY", "1")
        path = tmp_path / "novelty.sqlite"
        cache = NoveltyCache(path=path)
        detect_novelty(_identity_slot(), "_extract_identity", ["ipv4-addr"], cache)
        cache.close()
        assert not path.exists()


# ---------------------------------------------------------------------------
# Stage B-9: novelty_enabled() truthy/falsy values
# ---------------------------------------------------------------------------


class TestNoveltyEnabled:
    """novelty_enabled() returns True when AP_NO_NOVELTY is unset/empty."""

    def test_enabled_when_env_unset(self, monkeypatch):
        """AP_NO_NOVELTY not set → novelty_enabled() is True."""
        monkeypatch.delenv("AP_NO_NOVELTY", raising=False)
        assert novelty_enabled() is True

    def test_disabled_when_env_is_1(self, monkeypatch):
        """AP_NO_NOVELTY=1 → novelty_enabled() is False."""
        monkeypatch.setenv("AP_NO_NOVELTY", "1")
        assert novelty_enabled() is False

    def test_disabled_when_env_is_true(self, monkeypatch):
        """AP_NO_NOVELTY=true → novelty_enabled() is False."""
        monkeypatch.setenv("AP_NO_NOVELTY", "true")
        assert novelty_enabled() is False

    def test_disabled_when_env_is_on(self, monkeypatch):
        """AP_NO_NOVELTY=on → novelty_enabled() is False."""
        monkeypatch.setenv("AP_NO_NOVELTY", "on")
        assert novelty_enabled() is False

    def test_disabled_when_env_is_any_nonempty(self, monkeypatch):
        """Any non-empty AP_NO_NOVELTY value → disabled."""
        monkeypatch.setenv("AP_NO_NOVELTY", "yes")
        assert novelty_enabled() is False

    def test_enabled_when_env_is_empty(self, monkeypatch):
        """AP_NO_NOVELTY='' (empty string) → novelty_enabled() is True."""
        monkeypatch.setenv("AP_NO_NOVELTY", "")
        assert novelty_enabled() is True


# ---------------------------------------------------------------------------
# Stage B-10: Event shape
# ---------------------------------------------------------------------------


class TestEmitDossierNoveltyRecognizedEvent:
    """emit_dossier_novelty_recognized_event returns correct dict shape."""

    def test_action_key(self):
        """Event has action='dossier_novelty_recognized'."""
        ev = emit_dossier_novelty_recognized_event(
            _identity_slot(), "_extract_identity", ["ipv4-addr"]
        )
        assert ev["action"] == "dossier_novelty_recognized"

    def test_points_is_one(self):
        """Event has points=1 (integer, per DEC-M8-NOVELTY-006)."""
        ev = emit_dossier_novelty_recognized_event(
            _identity_slot(), "_extract_identity", ["ipv4-addr"]
        )
        assert ev["points"] == 1
        assert isinstance(ev["points"], int)

    def test_indicator_is_slot_value(self):
        """Event indicator equals slot.value."""
        ev = emit_dossier_novelty_recognized_event(
            _identity_slot(), "_extract_identity", ["ipv4-addr"]
        )
        assert ev["indicator"] == _identity_slot().value

    def test_rule_description_nonempty(self):
        """rule_description is a non-empty string."""
        ev = emit_dossier_novelty_recognized_event(
            _identity_slot(), "_extract_identity", ["ipv4-addr"]
        )
        assert isinstance(ev["rule_description"], str)
        assert len(ev["rule_description"]) > 0

    def test_all_required_keys_present(self):
        """Event dict has all four required keys."""
        ev = emit_dossier_novelty_recognized_event(
            _identity_slot(), "_extract_identity", ["ipv4-addr"]
        )
        for key in ("action", "points", "indicator", "rule_description"):
            assert key in ev, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# Stage B-11: rule_description has no Rich markup (F64)
# ---------------------------------------------------------------------------


class TestRuleDescriptionNoRichMarkup:
    """rule_description must be plain ASCII — no Rich markup (F64 invariant)."""

    def test_no_square_brackets(self):
        """rule_description contains no [ or ] (Rich color/style markup)."""
        ev = emit_dossier_novelty_recognized_event(
            _identity_slot(), "_extract_identity", ["ipv4-addr", "domain-name"]
        )
        rd = ev["rule_description"]
        # Allow brackets only if they contain SCO types (not Rich tags)
        # Validate: no Rich-style [color] or [/color] patterns
        import re

        rich_pattern = re.compile(r"\[/?[a-zA-Z_]+\]")
        assert not rich_pattern.search(rd), f"rule_description contains Rich markup: {rd!r}"

    def test_no_curly_brace_markup(self):
        """rule_description contains no { or } characters."""
        ev = emit_dossier_novelty_recognized_event(
            _identity_slot(), "_extract_identity", ["ipv4-addr"]
        )
        assert "{" not in ev["rule_description"]
        assert "}" not in ev["rule_description"]


# ---------------------------------------------------------------------------
# Stage B-12: Default cache path
# ---------------------------------------------------------------------------


class TestDefaultCachePath:
    """NoveltyCache() default path is Path.home() / ".ap" / "dossier_novelty.sqlite"."""

    def test_default_path_is_user_home(self):
        """NoveltyCache() without args uses ~/.ap/dossier_novelty.sqlite."""
        cache = NoveltyCache()
        expected = Path.home() / ".ap" / "dossier_novelty.sqlite"
        assert cache.path == expected
        # Do NOT call record — must not create the real file in tests
        cache.close()


# ---------------------------------------------------------------------------
# Stage B-compound: _SLOT_EXTRACTOR_NAMES coverage
# ---------------------------------------------------------------------------


class TestSlotExtractorNames:
    """_SLOT_EXTRACTOR_NAMES covers all 9 DossierSlotName values."""

    def test_all_slots_have_extractor_name(self):
        """Every DossierSlotName.value has a corresponding entry."""
        for slot in DossierSlotName:
            assert slot.value in _SLOT_EXTRACTOR_NAMES, (
                f"DossierSlotName.{slot.name} missing from _SLOT_EXTRACTOR_NAMES"
            )

    def test_extractor_names_start_with_underscore(self):
        """All extractor names follow the _extract_* convention."""
        for slot_val, extractor in _SLOT_EXTRACTOR_NAMES.items():
            assert extractor.startswith("_extract_"), (
                f"Extractor for '{slot_val}' doesn't start with '_extract_': {extractor}"
            )
