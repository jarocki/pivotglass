"""Novel slot-fill method detection for the dossier system (M-8).

This module is the AUTHORITY for dossier novelty hashing, cross-workspace
cache management, and novel-method event emission.

A "novel method" is a unique (slot_name, extractor_name, sco_type_set) tuple
that has not been observed in any prior hunt across all workspaces for this user.
The first time a particular combination is encountered, a
``dossier_novelty_recognized`` ScoreEvent is emitted and the hash is persisted
to the global cache at ``~/.ap/dossier_novelty.sqlite``.

Design decisions captured here:
  DEC-M8-NOVELTY-001: global SQLite at ``~/.ap/dossier_novelty.sqlite``
  DEC-M8-NOVELTY-002: hash = sha256(f"{slot.value}|{extractor}|{','.join(sorted(sco_types))}")
  DEC-M8-NOVELTY-003: NoveltyCache class with lazy open on first write
  DEC-M8-NOVELTY-004: schema: novelty_hashes(hash, slot, extractor, ordering_sig, first_seen_at, workspace_count)
  DEC-M8-NOVELTY-005: detect_novelty() — pure function, side-effect only on novel path
  DEC-M8-NOVELTY-006: points=1 (integer; matches M-3 per-IOC baseline)
  DEC-M8-NOVELTY-007: emission inserted between falsification events and narration loop
  DEC-M8-NOVELTY-008: AP_NO_NOVELTY env-var opt-out (truthy = disabled; default ON)
  DEC-M8-NOVELTY-009: _DOSSIER_ACTIONS widened to 4-tuple (F64 filter)
  DEC-M8-NOVELTY-010: Pioneer badge (RARE, threshold=1) + BadgeMetric.DOSSIER_NOVELTY_RECOGNIZED

@decision DEC-M8-NOVELTY-001
@title Cross-workspace novelty cache at ~/.ap/dossier_novelty.sqlite
@status accepted
@rationale Option A from plan §2.1. Cross-workspace accumulation is the semantic
           intent of the achievement — a user pursuing different actors should get
           credit for genuinely new (slot, extractor, sco_types) combinations once
           globally, not once per workspace. The ~/.ap/ directory is already the
           established cross-workspace state home (config, workspace DB location).
           Second SQLite authority is acceptable because it owns a DISTINCT domain:
           workspace SQLite = per-workspace facts; novelty SQLite = global analytic
           method registry. The two databases never need joins.

@decision DEC-M8-NOVELTY-002
@title Hash = sha256(slot.value|extractor|sorted_sco_types)
@status accepted
@rationale SCO-type SET is the "ordering" dimension (plan §2.3). Same (slot, extractor)
           combo with the same SCO inputs is the same analytic method regardless of
           SCO discovery order. sorted() makes the hash order-independent. The pipe
           separator cannot appear in slot values or sorted SCO-type lists. 64-char
           SHA-256 hex is the natural PRIMARY KEY type.

@decision DEC-M8-NOVELTY-003
@title NoveltyCache opens lazily; file created only on first INSERT
@status accepted
@rationale Users who set AP_NO_NOVELTY=1 before their first hunt, or whose hunts
           never trigger a slot-fill, should not see a ~/.ap/dossier_novelty.sqlite
           file appear. The file is an opt-in artefact produced by first use, not
           by process startup. Lazy-open is enforced by _ensure_open() which is only
           called from record(), not from is_known(). is_known() on a non-existent
           file returns False without creating the file.

Public API:
  - compute_novelty_hash(slot, extractor_name, sco_types) -> str
  - novelty_enabled() -> bool
  - NoveltyCache(path=None)  — path overridable for test isolation
  - detect_novelty(slot, extractor_name, sco_types, cache) -> bool
  - emit_dossier_novelty_recognized_event(slot, extractor_name, sco_types) -> dict
  - _SLOT_EXTRACTOR_NAMES: dict[DossierSlotName, str]  — slot -> extractor name map
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from adversary_pursuit.dossier.slots import DossierSlotName

# ---------------------------------------------------------------------------
# Default cache path (overridable in tests via NoveltyCache(path=...))
# ---------------------------------------------------------------------------

_DEFAULT_CACHE_PATH = Path.home() / ".ap" / "dossier_novelty.sqlite"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS novelty_hashes (
    hash            TEXT PRIMARY KEY,
    slot            TEXT NOT NULL,
    extractor       TEXT NOT NULL,
    ordering_sig    TEXT NOT NULL,
    first_seen_at   TEXT NOT NULL,
    workspace_count INTEGER NOT NULL DEFAULT 1
)
"""

# ---------------------------------------------------------------------------
# Slot → extractor name map (DEC-M8-NOVELTY-002)
# Decouples novelty detection from slot_inference.py (BYTEWISE UNCHANGED M-1..M-7).
# The map mirrors the private function names in dossier/slot_inference.py
# but is owned here so slot_inference.py requires no modification.
# ---------------------------------------------------------------------------

_SLOT_EXTRACTOR_NAMES: dict[str, str] = {
    "identity": "_extract_identity",
    "ttps": "_extract_ttps",
    "infrastructure": "_extract_infrastructure",
    "timing": "_extract_timing",
    "targeting": "_extract_targeting",
    "capability": "_extract_capability",
    "motivation": "_extract_motivation",
    "predictions": "_extract_predictions",
    "denial": "_extract_denial",
}


# ---------------------------------------------------------------------------
# Opt-out (DEC-M8-NOVELTY-008)
# ---------------------------------------------------------------------------


def novelty_enabled() -> bool:
    """Return True when novelty detection is active (AP_NO_NOVELTY unset/falsy).

    Mirrors the AP_NO_BANNER pattern in core/console.py and agent/banner.py.
    Any non-empty value for AP_NO_NOVELTY disables novelty detection globally.

    Returns
    -------
    bool
        True  — detection enabled (default, AP_NO_NOVELTY not set or empty).
        False — detection disabled (AP_NO_NOVELTY set to any non-empty value).
    """
    return not os.environ.get("AP_NO_NOVELTY")


# ---------------------------------------------------------------------------
# Hash function (DEC-M8-NOVELTY-002)
# ---------------------------------------------------------------------------


def compute_novelty_hash(
    slot: "DossierSlotName",
    extractor_name: str,
    sco_types: Iterable[str],
) -> str:
    """Compute the 64-char SHA-256 hex digest for a (slot, extractor, sco_types) tuple.

    The hash is ORDER-INDEPENDENT with respect to ``sco_types`` — a frozenset is
    equivalent to any permutation of the same elements. The pipe ``|`` separator
    is unambiguous because it cannot appear in slot values or STIX SCO type names.

    Parameters
    ----------
    slot:
        DossierSlotName enum member identifying the filled slot.
    extractor_name:
        Name of the slot_inference extractor function (e.g. ``"_extract_identity"``).
        Use ``_SLOT_EXTRACTOR_NAMES[slot.value]`` for the canonical mapping.
    sco_types:
        Iterable of STIX SCO type strings (e.g. ``["ipv4-addr", "domain-name"]``).
        Order does not affect the hash.

    Returns
    -------
    str
        64-character lowercase SHA-256 hex digest.
    """
    ordering_sig = ",".join(sorted(set(sco_types)))
    raw = f"{slot.value}|{extractor_name}|{ordering_sig}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# NoveltyCache (DEC-M8-NOVELTY-003 / DEC-M8-NOVELTY-004)
# ---------------------------------------------------------------------------


class NoveltyCache:
    """Cross-workspace SQLite cache for observed (slot, extractor, sco_types) hashes.

    The cache file is created lazily on the first ``record()`` call.  ``is_known()``
    on a non-existent file returns False without creating the file.

    Parameters
    ----------
    path:
        Path to the SQLite file.  Defaults to ``~/.ap/dossier_novelty.sqlite``.
        Override in tests: ``NoveltyCache(path=tmp_path / "novelty.sqlite")``.

    Usage
    -----
    cache = NoveltyCache()
    if not cache.is_known(h):
        cache.record(h, "identity", "_extract_identity", "ipv4-addr,domain-name")
    cache.close()
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path: Path = path if path is not None else _DEFAULT_CACHE_PATH
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Schema collision guard (plan risk-register)
    # ------------------------------------------------------------------

    _EXPECTED_COLUMNS: frozenset[str] = frozenset(
        {"hash", "slot", "extractor", "ordering_sig", "first_seen_at", "workspace_count"}
    )

    def _check_schema(self, conn: sqlite3.Connection) -> None:
        """Raise RuntimeError when the on-disk schema is incompatible.

        Called immediately after opening an existing database file (both the
        mutating and read-only paths).  A file created by this module with the
        current schema passes silently.  A file that already exists with a
        different column set raises a clear error with remediation instructions
        instead of silently corrupting data.

        Empty-table check: if PRAGMA table_info returns zero rows the table was
        just created by ``CREATE TABLE IF NOT EXISTS`` and has the correct schema
        by construction — no mismatch possible.
        """
        cursor = conn.execute("PRAGMA table_info(novelty_hashes)")
        rows = cursor.fetchall()
        if not rows:
            # Table was freshly created — schema is correct by construction.
            return
        cols = {row[1] for row in rows}
        if cols != self._EXPECTED_COLUMNS:
            raise RuntimeError(
                f"Novelty cache schema mismatch at {self.path}. "
                f"Expected columns {sorted(self._EXPECTED_COLUMNS)}, got {sorted(cols)}. "
                f"Remove or back up the file and let M-8 recreate it."
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_open(self) -> sqlite3.Connection:
        """Open the SQLite connection and create the schema if needed.

        Called only from mutating paths (``record``).  The parent directory is
        created with ``mkdir(parents=True, exist_ok=True)`` so the first write
        to a fresh ``~/.ap/`` directory succeeds without pre-creating it.
        """
        if self._conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self.path),
                check_same_thread=False,
                isolation_level=None,  # autocommit
            )
            self._conn.execute(_CREATE_TABLE_SQL)
            self._check_schema(self._conn)
        return self._conn

    def _read_conn(self) -> sqlite3.Connection | None:
        """Return an open connection for read-only queries, or None if file absent.

        Does NOT create the file — returns None when ``self.path`` does not exist.
        """
        if self._conn is not None:
            return self._conn
        if not self.path.exists():
            return None
        self._conn = sqlite3.connect(
            str(self.path),
            check_same_thread=False,
            isolation_level=None,
        )
        self._conn.execute(_CREATE_TABLE_SQL)
        self._check_schema(self._conn)
        return self._conn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_known(self, hash_hex: str) -> bool:
        """Return True if *hash_hex* is already in the cache.

        Returns False (not novel) when the cache file does not exist yet — no
        file creation side effect.

        Parameters
        ----------
        hash_hex:
            64-char SHA-256 hex from ``compute_novelty_hash()``.
        """
        conn = self._read_conn()
        if conn is None:
            return False
        row = conn.execute("SELECT 1 FROM novelty_hashes WHERE hash = ?", (hash_hex,)).fetchone()
        return row is not None

    def record(
        self,
        hash_hex: str,
        slot: str,
        extractor: str,
        ordering_sig: str,
    ) -> None:
        """Persist a new novelty hash.  No-op if the hash already exists.

        Uses ``INSERT OR IGNORE`` so concurrent processes cannot produce duplicate
        rows.  The ``workspace_count`` column defaults to 1; future slices may add
        an UPDATE branch to increment it across workspaces.

        Parameters
        ----------
        hash_hex:
            64-char SHA-256 hex digest.
        slot:
            DossierSlotName.value string (e.g. ``"identity"``).
        extractor:
            Extractor function name string (e.g. ``"_extract_identity"``).
        ordering_sig:
            ``','.join(sorted(sco_types))`` signature string.
        """
        conn = self._ensure_open()
        first_seen = datetime.now(tz=timezone.utc).isoformat()
        conn.execute(
            """
            INSERT OR IGNORE INTO novelty_hashes
                (hash, slot, extractor, ordering_sig, first_seen_at, workspace_count)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (hash_hex, slot, extractor, ordering_sig, first_seen),
        )

    def close(self) -> None:
        """Close the SQLite connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None


# ---------------------------------------------------------------------------
# Detector (DEC-M8-NOVELTY-005)
# ---------------------------------------------------------------------------


def detect_novelty(
    slot: "DossierSlotName",
    extractor_name: str,
    sco_types: Iterable[str],
    cache: NoveltyCache,
) -> bool:
    """Return True if this (slot, extractor, sco_types) combination is novel.

    Side effects on True:
      - Calls ``cache.record()`` to persist the hash.

    Side effects on False (already known OR AP_NO_NOVELTY set):
      - None.

    Parameters
    ----------
    slot:
        DossierSlotName enum member for the filled slot.
    extractor_name:
        Extractor function name (from ``_SLOT_EXTRACTOR_NAMES``).
    sco_types:
        Iterable of STIX SCO type strings fed to this slot's extractor.
    cache:
        NoveltyCache instance to check and write.

    Returns
    -------
    bool
        True  — first-ever observation; cache.record() was called.
        False — already known, or AP_NO_NOVELTY is set.
    """
    if not novelty_enabled():
        return False

    sco_set = sorted(set(sco_types))
    ordering_sig = ",".join(sco_set)
    hash_hex = compute_novelty_hash(slot, extractor_name, sco_set)

    if cache.is_known(hash_hex):
        return False

    cache.record(hash_hex, slot.value, extractor_name, ordering_sig)
    return True


# ---------------------------------------------------------------------------
# Event emitter (DEC-M8-NOVELTY-006 / DEC-M8-NOVELTY-007)
# ---------------------------------------------------------------------------


def emit_dossier_novelty_recognized_event(
    slot: "DossierSlotName",
    extractor_name: str,
    sco_types: Iterable[str],
) -> dict:
    """Build a ScoreEvent dict for a novel slot-fill method observation.

    The returned dict follows the same contract as M-3/M-4/M-5 dossier events
    (action, points, indicator, rule_description).  It is ready for
    ``workspace_mgr.store_score_events([...])`` and flows through the same
    F64 ``_DOSSIER_ACTIONS`` filter in ``_execute_run_module``.

    Points=1 (integer) matches the M-3 per-IOC baseline and preserves the
    integer-only ScoreEvent contract (DEC-M8-NOVELTY-006).

    rule_description is plain ASCII — no Rich markup (F64 invariant).

    Parameters
    ----------
    slot:
        DossierSlotName for the filled slot.
    extractor_name:
        Extractor function name.
    sco_types:
        Iterable of STIX SCO type strings.

    Returns
    -------
    dict
        Score event dict with keys: action, points, indicator, rule_description.
    """
    slot_display = slot.value.replace("_", " ").title()
    sco_summary = ", ".join(sorted(set(sco_types)))
    rule_description = f"Novel slot-fill method: {slot_display} via {extractor_name}" + (
        f" [{sco_summary}]" if sco_summary else ""
    )
    return {
        "action": "dossier_novelty_recognized",
        "points": 1,
        "indicator": slot.value,
        "rule_description": rule_description,
    }
