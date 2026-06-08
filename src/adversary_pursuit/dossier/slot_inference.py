"""Dossier slot inference — read-only, pure-function slot fill state computation.

Consumes a list of STIX SCO dicts (as returned by WorkspaceManager.get_stix_objects())
and returns a DossierState value object describing each slot's fill status and
evidence count. No I/O, no workspace mutations, no x_ap_* writes.

M-1 public API: infer_dossier_state(scos) — preserved as thin wrapper.
M-2 public API: infer_dossier_state_full(scos, module_runs, notes) — new entrypoint.
M-5 public API: slot 9 (Denial) now returns real status via _extract_denial().
    _is_dga_shaped(label) — exported for unit testing of the DGA detector.

@decision DEC-M1-DOSSIER-001 (inference authority)
@title slot_inference.infer_dossier_state() is a pure function; never mutates workspace
@status accepted
@rationale Sacred Practice 12: the question "what is the dossier state of this workspace?"
    has exactly one owner (this module). The function is:
      - Pure: same SCO list -> same DossierState, no hidden state.
      - Read-only: it consumes the SCO list but never calls any WorkspaceManager
        mutator, never sets x_ap_* provenance fields (DEC-59-STIX-PROVENANCE-001
        preserved), and never emits ScoreEvents (DEC-M1-DOSSIER-002 / M-3 scope).
      - Deterministic: iterates SCO types against an explicit SLOT_EVIDENCE_TYPES
        table; unknown types are silently skipped (no auto-discovery).
    The DossierState value object is the handoff point to panel.render().

@decision DEC-M1-DOSSIER-INFERENCE-STATUS-001
@title partial vs filled threshold: 1 distinct SCO type -> partial; 2+ -> filled
@status accepted
@rationale Phase 16 §3 defines confidence levels tied to distinct-source count
    (e.g., Identity high = independently corroborated by >=2 evidence types from
    >=2 modules). M-1 uses distinct SCO TYPE count as the proxy for corroboration:
    one type -> partial (single uncorroborated source class); two or more distinct
    types -> filled (two independent evidence categories). This is a conservative
    mapping; M-2 will refine by adding per-module attribution. The threshold is
    intentionally simple so it is testable with synthetic fixtures.

@decision DEC-M2-DOSSIER-001
@title infer_dossier_state_full() is the M-2 entrypoint; infer_dossier_state() is a thin wrapper
@status accepted
@rationale DEC-M2-DOSSIER-001: M-2 extends M-1 without replacing it. The legacy
    infer_dossier_state(scos) is the call site in chat.py's 'dossier' meta-command —
    changing that call signature would require touching chat.py. Instead, M-2 adds
    infer_dossier_state_full(scos, module_runs, notes) as the canonical entrypoint
    and makes infer_dossier_state() a thin wrapper that passes module_runs=None,
    notes=None. The get_dossier_state LLM tool fetches module_runs and notes from
    the workspace and calls infer_dossier_state_full() directly (DEC-M2-DOSSIER-005).
    Zero workspace.py edits (per Scope Manifest forbidden list).

@decision DEC-M2-DOSSIER-002
@title Timing extractor: x_ap_fetched_at + module_runs timestamps, UTC hour-of-day clustering
@status accepted
@rationale Phase 16 §3 Slot 4 specifies: confidence High = >=10 events across >=3
    distinct sources clustering to a timezone distribution. M-2 maps this to:
    - Event set: union of x_ap_fetched_at fields from SCOs + timestamp fields from
      module_runs rows (both available without workspace mutations).
    - Clustering unit: UTC hour-of-day (0-23). A simpler proxy than full timezone
      inference; sufficient for MVP-level behavioral pattern detection.
    - FILLED threshold: >=10 events AND >=25% of events fall in one hour bucket.
    - PARTIAL: some timestamped events exist but thresholds not met.
    - EMPTY: no timestamped events at all.
    The 25% bucket threshold catches dominant work windows (e.g. 9-5 in one zone)
    without requiring the full >=3-sources corroboration gate (deferred to M-3).

@decision DEC-M2-DOSSIER-003
@title Capability extractor: reads DEFAULT_SUBSCRIPTIONS at call time; observed vs unobserved
@status accepted
@rationale Phase 16 §3 Slot 6 specifies: capability is inferred from absence-of-evidence
    (tools NOT pivoted to) as much as from evidence of use. DEFAULT_SUBSCRIPTIONS is
    the canonical registry of AP-supported module types (DEC-EVENTBUS-002 opt-in bus).
    The extractor reads it at call time (not at import time) so that runtime additions
    to DEFAULT_SUBSCRIPTIONS are picked up without module reload.
    - observed_modules: set of distinct module_name values in module_runs.
    - unobserved_modules: DEFAULT_SUBSCRIPTIONS keys NOT in observed_modules.
    - FILLED: >=3 observed AND >=3 unobserved (actor has both confirmed capabilities
      and confirmed gaps — the "ceiling" is identifiable).
    - PARTIAL: any module runs exist but threshold not met.
    - EMPTY: no module runs at all.
    Counts distinct module names, not run count (5 runs of one module = 1 observed).

@decision DEC-M2-MOTIVATION-001
@title Motivation extractor: analyst notes keyword matching, category-based threshold
@status accepted
@rationale Phase 16 §3 Slot 7 specifies: motivation is inferred from targeting profile
    + TTP slot + Identity slot triangulation. M-2 uses a simpler proxy available
    without M-4 persistence: analyst notes keyword matching. Notes are passed in as
    list[dict] with a 'content' field (same pattern as core/report.py:348-369).
    Categories and keywords:
      financial:   ransom, financial, swift, payment, bitcoin, extort, profit, money
      hacktivist:  hacktivist, political, ideology, activist, protest, deface
      nation-state: nation-state, apt, state-sponsored, espionage, government, military
      ego:         ego, fame, notoriety, reputation, skill, challenge, lulz
    - FILLED: >=2 distinct category signals found across notes.
    - PARTIAL: 1 category signal found.
    - EMPTY: 0 signals (no notes, or notes with no keyword matches).
    This is a conservative MVP; M-3 will refine with TTP/Identity cross-slot inference.

@decision DEC-M5-DENIAL-001
@title Slot 9 Denial extractor vocabulary v1.0: DGA-shaped domains, fast-flux TTL, note keywords
@status accepted
@rationale Three evidence categories drive slot 9 in M-5: (1) DGA-shaped domain
    (label length >=12 AND consonant-to-vowel ratio >=3); (2) fast-flux / decoy
    infrastructure hint (SCO carries x_ap_dns_ttl <=60 sec); (3) denial/evasion
    keyword in analyst note content. FILLED requires >=2 distinct categories
    (cross-category corroboration, mirroring DEC-M1-DOSSIER-INFERENCE-STATUS-001).
    PARTIAL = >=1 evidence from any single category. EMPTY = 0 evidence.
    This deliberately small vocabulary ships M-5; richer DGA detection and
    multi-stage TTP cross-reference land in M-7 or later slices.

@decision DEC-M5-DENIAL-002
@title Slot 9 Denial status thresholds: EMPTY/PARTIAL/FILLED by category count
@status accepted
@rationale EMPTY: 0 evidence items. PARTIAL: >=1 from any single category.
    FILLED: >=1 from at least 2 distinct categories. This mirrors the
    DEC-M1-DOSSIER-INFERENCE-STATUS-001 "distinct types >=2 -> filled" shape
    applied to denial-evidence categories instead of STIX types.

@decision DEC-M5-DENIAL-003
@title _is_dga_shaped uses consonant-to-vowel ratio >=3 as conservative DGA detector
@status accepted
@rationale Intentionally conservative MVP: catches high-consonant DGA outputs
    (e.g. "xqzpfwbkdmrl") while intentionally missing dictionary-word DGAs and
    likely flagging some legitimate-but-cryptic base32/base64 subdomain labels.
    label length >=12 pre-filter avoids false-positives on short hostnames.
    Unit tests document both the true-positive set and the known-miss set so
    future implementers can tune the thresholds with real workspace data.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from adversary_pursuit.dossier.slots import (
    M1_ACTIVE_SLOTS,
    SLOT_EVIDENCE_TYPES,
    DossierSlotName,
    SlotStatus,
)

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# M-5: Denial / Deception keyword vocabulary (DEC-M5-DENIAL-001)
# ---------------------------------------------------------------------------
# Substring match (case-insensitive) against analyst note content.
# Intentionally small vocabulary — richer vocabulary lands in M-7+.
# Mirrors _MOTIVATION_CATEGORIES shape: frozenset of lowercase fragments.

_DENIAL_KEYWORDS: frozenset[str] = frozenset(
    {
        "decoy",
        "deception",
        "evasion",
        "evasive",
        "sandbox",
        "sandbox-aware",
        "sandbox-evasion",
        "obfuscation",
        "obfuscated",
        "anti-analysis",
        "anti-vm",
        "anti-sandbox",
        "dga",
        "fast-flux",
        "fast flux",
        "flux",
        "domain generation",
        "domain-generation",
        "honeypot",
    }
)

# ---------------------------------------------------------------------------
# M-2: Motivation keyword categories (DEC-M2-MOTIVATION-001)
# ---------------------------------------------------------------------------
# Each category maps to a list of lowercase keyword fragments. A note 'hits'
# a category if any keyword appears as a substring of the lowercased content.
# Using fragments (not whole-word match) keeps the detector simple and broad;
# M-3 can narrow with NLP if needed.

_MOTIVATION_CATEGORIES: dict[str, list[str]] = {
    "financial": [
        "ransom",
        "financial",
        "swift",
        "payment",
        "bitcoin",
        "extort",
        "profit",
        "money",
    ],
    "hacktivist": ["hacktivist", "political", "ideology", "activist", "protest", "deface"],
    "nation-state": [
        "nation-state",
        "apt",
        "state-sponsored",
        "espionage",
        "government",
        "military",
    ],
    "ego": ["ego", "fame", "notoriety", "reputation", "skill", "challenge", "lulz"],
}


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SlotState:
    """Immutable state for a single dossier slot.

    Parameters
    ----------
    name:
        The DossierSlotName enum member for this slot.
    status:
        Current fill status: empty / partial / filled / deferred.
    evidence_count:
        Number of SCOs that contribute to this slot. Zero when status is
        empty or deferred; >= 1 when partial or filled.
    contributing_types:
        Frozenset of STIX type strings that contributed evidence.
        Used to determine partial vs filled threshold.
    """

    name: DossierSlotName
    status: SlotStatus
    evidence_count: int = 0
    contributing_types: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class DossierState:
    """Immutable snapshot of all 9 slot fill states for the current workspace.

    Produced by infer_dossier_state() and consumed by panel.render().
    Contains no references to WorkspaceManager or any mutable I/O resource.

    Parameters
    ----------
    slots:
        Mapping from DossierSlotName -> SlotState. Always contains all 9 slots.
    total_sco_count:
        Total number of input SCOs that were processed (for panel display).
    """

    slots: dict[DossierSlotName, SlotState]
    total_sco_count: int = 0


# ---------------------------------------------------------------------------
# Inference engine
# ---------------------------------------------------------------------------


def infer_dossier_state(scos: list[dict]) -> DossierState:
    """Infer dossier slot fill state from a list of STIX SCO dicts.

    M-1 legacy entrypoint. Preserved as a thin wrapper around
    infer_dossier_state_full() for the chat.py 'dossier' meta-command call site
    (DEC-M2-DOSSIER-001). Passes module_runs=None, notes=None so Timing and
    Motivation slots remain DEFERRED when called without the extended inputs.

    Pure function: same input -> same output; no side effects; no I/O.
    Consumes WorkspaceManager.get_stix_objects() output directly.

    Parameters
    ----------
    scos:
        List of plain STIX SCO dicts as returned by
        WorkspaceManager.get_stix_objects(). May include x_ap_* provenance
        fields which are read but never modified (DEC-59-STIX-PROVENANCE-001).
        Unknown SCO types are silently skipped (no auto-discovery).

    Returns
    -------
    DossierState
        Immutable snapshot of all 9 slot fill states and total SCO count.
    """
    return infer_dossier_state_full(scos, module_runs=None, notes=None)


def infer_dossier_state_full(
    scos: list[dict],
    module_runs: list[dict] | None = None,
    notes: list[dict] | None = None,
) -> DossierState:
    """Infer dossier slot fill state with full M-2 extractor set.

    The M-2 canonical entrypoint. Extends M-1 (Identity/TTPs/Infrastructure)
    with three new extractors: Timing (DEC-M2-DOSSIER-002), Capability
    (DEC-M2-DOSSIER-003), and Motivation (DEC-M2-MOTIVATION-001). Slots 5
    (Targeting), 8 (Predictions), and 9 (Denial) remain DEFERRED in M-2
    (DEC-M2-DOSSIER-004 scaffold-only).

    Pure function: same inputs -> same output; no side effects; no I/O.
    All inputs are consumed read-only — none are mutated.

    Parameters
    ----------
    scos:
        List of plain STIX SCO dicts. x_ap_fetched_at fields are read for
        Timing inference but never written (DEC-59-STIX-PROVENANCE-001).
    module_runs:
        List of module run dicts as returned by
        WorkspaceManager.get_module_runs() — keys: module_name, target,
        timestamp, result_count. Used by Timing and Capability extractors.
        Pass None or [] when not available.
    notes:
        List of analyst note dicts with at least a 'content' key — same
        format produced by the engine-direct AnalystNote query in
        core/report.py:348-369. Used by Motivation extractor.
        Pass None or [] when not available.

    Returns
    -------
    DossierState
        Immutable snapshot of all 9 slot fill states and total SCO count.

    Notes
    -----
    - Status thresholds for SCO-based slots: 1 distinct type -> partial;
      >=2 -> filled (DEC-M1-DOSSIER-INFERENCE-STATUS-001).
    - Timing FILLED: >=10 timestamped events AND >=25% in one UTC hour bucket.
    - Capability FILLED: >=3 observed modules AND >=3 unobserved modules.
    - Motivation FILLED: >=2 distinct category signals across notes.
    - Slots 5/8/9 (Targeting/Predictions/Denial): always DEFERRED in M-2.
    """
    _module_runs = module_runs or []
    _notes = notes or []

    # ------------------------------------------------------------------
    # Step 1: M-1 SCO-based slots (Identity / TTPs / Infrastructure)
    # ------------------------------------------------------------------
    slot_type_sets: dict[DossierSlotName, set[str]] = {slot: set() for slot in M1_ACTIVE_SLOTS}
    slot_sco_counts: dict[DossierSlotName, int] = {slot: 0 for slot in M1_ACTIVE_SLOTS}

    for sco in scos:
        sco_type = sco.get("type", "")
        if not sco_type:
            _LOG.debug("infer_dossier_state_full: SCO missing 'type' field, skipping")
            continue

        target_slots = SLOT_EVIDENCE_TYPES.get(sco_type)
        if target_slots is None:
            _LOG.debug("infer_dossier_state_full: unknown SCO type %r, skipping", sco_type)
            continue

        for slot in target_slots:
            if slot in slot_type_sets:
                slot_type_sets[slot].add(sco_type)
                slot_sco_counts[slot] = slot_sco_counts[slot] + 1

    active_slot_states: dict[DossierSlotName, SlotState] = {}
    for slot in M1_ACTIVE_SLOTS:
        types_seen = slot_type_sets[slot]
        count = slot_sco_counts[slot]

        if count == 0:
            status = SlotStatus.EMPTY
        elif len(types_seen) >= 2:
            status = SlotStatus.FILLED
        else:
            status = SlotStatus.PARTIAL

        active_slot_states[slot] = SlotState(
            name=slot,
            status=status,
            evidence_count=count,
            contributing_types=frozenset(types_seen),
        )

    # ------------------------------------------------------------------
    # Step 2: Timing extractor (DEC-M2-DOSSIER-002)
    # Collect UTC hour-of-day values from x_ap_fetched_at (SCOs) and
    # timestamp (module_runs). Count events and find dominant bucket.
    # ------------------------------------------------------------------
    timing_slot = _extract_timing(scos, _module_runs)

    # ------------------------------------------------------------------
    # Step 3: Capability extractor (DEC-M2-DOSSIER-003)
    # Compare observed module names against DEFAULT_SUBSCRIPTIONS registry.
    # ------------------------------------------------------------------
    capability_slot = _extract_capability(_module_runs)

    # ------------------------------------------------------------------
    # Step 4: Motivation extractor (DEC-M2-MOTIVATION-001)
    # Keyword-match analyst notes against motivation category vocabulary.
    # ------------------------------------------------------------------
    motivation_slot = _extract_motivation(_notes)

    # ------------------------------------------------------------------
    # Step 5: Denial extractor (DEC-M5-DENIAL-001)
    # Slot 9 now returns a real status; DEFERRED set shrinks to {TARGETING}.
    # ------------------------------------------------------------------
    denial_slot = _extract_denial(scos, _notes)

    # ------------------------------------------------------------------
    # Step 6: Always-DEFERRED slots in M-5 (Targeting / Predictions only)
    # Predictions slot is overlaid by apply_predictions_overlay at call sites.
    # DEC-M2-DOSSIER-004 scaffold: Targeting remains DEFERRED (no automated
    # extractor until user-supplied victim-industry context is available).
    # ------------------------------------------------------------------
    deferred_names = [
        DossierSlotName.TARGETING,
        DossierSlotName.PREDICTIONS,
    ]
    deferred_states: dict[DossierSlotName, SlotState] = {
        slot: SlotState(
            name=slot,
            status=SlotStatus.DEFERRED,
            evidence_count=0,
            contributing_types=frozenset(),
        )
        for slot in deferred_names
    }

    # ------------------------------------------------------------------
    # Merge: all 9 slots present in result (single authority per slot)
    # ------------------------------------------------------------------
    all_slots: dict[DossierSlotName, SlotState] = {
        **active_slot_states,
        DossierSlotName.TIMING: timing_slot,
        DossierSlotName.CAPABILITY: capability_slot,
        DossierSlotName.MOTIVATION: motivation_slot,
        DossierSlotName.DENIAL: denial_slot,
        **deferred_states,
    }

    return DossierState(slots=all_slots, total_sco_count=len(scos))


# ---------------------------------------------------------------------------
# M-2 extractor helpers — pure functions, each returning a single SlotState
# ---------------------------------------------------------------------------


def _extract_timing(scos: list[dict], module_runs: list[dict]) -> SlotState:
    """Extract Timing slot state from timestamped events (DEC-M2-DOSSIER-002).

    Collects UTC hour-of-day values from:
    - sco['x_ap_fetched_at'] (ISO 8601 strings ending in 'Z' or '+00:00')
    - module_run['timestamp'] (ISO 8601 strings, may lack timezone suffix)

    FILLED:  total >= 10 AND max_bucket_count / total >= 0.25
    PARTIAL: total >= 1 AND not FILLED
    EMPTY:   total == 0
    """
    hours: list[int] = []

    for sco in scos:
        ts = sco.get("x_ap_fetched_at", "")
        if ts:
            hour = _parse_utc_hour(ts)
            if hour is not None:
                hours.append(hour)

    for run in module_runs:
        ts = run.get("timestamp", "")
        if ts:
            hour = _parse_utc_hour(ts)
            if hour is not None:
                hours.append(hour)

    total = len(hours)
    if total == 0:
        return SlotState(
            name=DossierSlotName.TIMING,
            status=SlotStatus.EMPTY,
            evidence_count=0,
            contributing_types=frozenset(),
        )

    bucket_counts = Counter(hours)
    max_bucket = max(bucket_counts.values())

    if total >= 10 and (max_bucket / total) >= 0.25:
        status = SlotStatus.FILLED
    else:
        status = SlotStatus.PARTIAL

    return SlotState(
        name=DossierSlotName.TIMING,
        status=status,
        evidence_count=total,
        contributing_types=frozenset({"timestamp"}),
    )


def _parse_utc_hour(ts: object) -> int | None:
    """Parse a UTC hour-of-day (0-23) from a timestamp value.

    Accepts:
    - datetime.datetime objects (reads .hour directly)
    - ISO 8601 strings: 'YYYY-MM-DDTHH:MM:SSZ', 'YYYY-MM-DDTHH:MM:SS+00:00',
      'YYYY-MM-DDTHH:MM:SS' (assumed UTC)

    WorkspaceManager.get_module_runs() returns row.timestamp as a
    datetime.datetime from SQLAlchemy; x_ap_fetched_at on SCO dicts is an
    ISO 8601 string. Both are handled here.

    Returns None on parse failure or unsupported type (silently skipped).
    """
    import datetime as _dt

    if ts is None:
        return None
    # datetime.datetime fast-path — avoids string parsing entirely
    if isinstance(ts, _dt.datetime):
        hour = ts.hour
        return hour if 0 <= hour <= 23 else None
    if not isinstance(ts, str) or not ts or "T" not in ts:
        return None
    try:
        time_part = ts.split("T", 1)[1]
        # Strip timezone suffix: Z, +00:00, -05:00, etc.
        for suffix in ("Z", "+", "-"):
            idx = time_part.find(suffix)
            if idx > 0:
                time_part = time_part[:idx]
        hour_str = time_part.split(":")[0]
        hour = int(hour_str)
        if 0 <= hour <= 23:
            return hour
        return None
    except (IndexError, ValueError):
        return None


def _extract_capability(module_runs: list[dict]) -> SlotState:
    """Extract Capability slot state from module run history (DEC-M2-DOSSIER-003).

    Reads DEFAULT_SUBSCRIPTIONS at call time to get the canonical module registry.
    Compares observed distinct module names against the registry.

    FILLED:  observed >= 3 AND unobserved >= 3
    PARTIAL: any module runs exist but threshold not met (observed >= 1)
    EMPTY:   no module runs at all
    """
    # Import at call time per DEC-M2-DOSSIER-003 — picks up runtime additions
    from adversary_pursuit.core.event_bus import DEFAULT_SUBSCRIPTIONS

    observed_modules: set[str] = {run.get("module_name", "") for run in module_runs}
    observed_modules.discard("")  # remove empty strings from missing module_name

    if not observed_modules:
        return SlotState(
            name=DossierSlotName.CAPABILITY,
            status=SlotStatus.EMPTY,
            evidence_count=0,
            contributing_types=frozenset(),
        )

    all_subscribed = set(DEFAULT_SUBSCRIPTIONS.keys())
    unobserved_modules = all_subscribed - observed_modules
    observed_count = len(observed_modules)
    unobserved_count = len(unobserved_modules)

    if observed_count >= 3 and unobserved_count >= 3:
        status = SlotStatus.FILLED
    else:
        status = SlotStatus.PARTIAL

    return SlotState(
        name=DossierSlotName.CAPABILITY,
        status=status,
        evidence_count=len(module_runs),
        contributing_types=frozenset(observed_modules),
    )


def _extract_motivation(notes: list[dict]) -> SlotState:
    """Extract Motivation slot state from analyst notes (DEC-M2-MOTIVATION-001).

    Keyword-matches each note's 'content' field against _MOTIVATION_CATEGORIES.
    Counts distinct categories that appear across all notes.

    FILLED:  >= 2 distinct motivation categories detected
    PARTIAL: == 1 distinct motivation category detected
    EMPTY:   0 categories detected (no notes, or no keyword matches)
    """
    categories_hit: set[str] = set()
    note_count = 0

    for note in notes:
        content = note.get("content", "")
        if not content:
            continue
        note_count += 1
        lowered = content.lower()
        for category, keywords in _MOTIVATION_CATEGORIES.items():
            if any(kw in lowered for kw in keywords):
                categories_hit.add(category)

    n_categories = len(categories_hit)
    if n_categories == 0:
        return SlotState(
            name=DossierSlotName.MOTIVATION,
            status=SlotStatus.EMPTY,
            evidence_count=0,
            contributing_types=frozenset(),
        )
    elif n_categories >= 2:
        status = SlotStatus.FILLED
    else:
        status = SlotStatus.PARTIAL

    return SlotState(
        name=DossierSlotName.MOTIVATION,
        status=status,
        evidence_count=note_count,
        contributing_types=frozenset(categories_hit),
    )


# ---------------------------------------------------------------------------
# M-5 extractor helpers — Denial / Deception slot 9 (DEC-M5-DENIAL-001..003)
# ---------------------------------------------------------------------------


def _is_dga_shaped(label: str) -> bool:
    """Return True if *label* looks like a DGA-generated hostname component.

    A label is considered DGA-shaped when BOTH conditions hold:
      1. Length >= 12 characters (short labels are excluded to reduce FP rate).
      2. Consonant-to-vowel ratio >= 3 (no recognisable word fragments).

    This is a deliberately conservative MVP detector (DEC-M5-DENIAL-003):
    - True positives: high-consonant random strings (e.g. "xqzpfwbkdmrl").
    - Known false negatives: dictionary-word DGAs (e.g. "green-apple-pen").
    - Known false positives: long base32/base64 subdomain labels with high
      consonant density.

    Only the individual hostname label (not the full FQDN) should be passed.
    For "xqzpfwbkdmrl.example.org" call _is_dga_shaped("xqzpfwbkdmrl").

    Parameters
    ----------
    label:
        A single DNS label string (no dots).

    Returns
    -------
    bool
        True when the label satisfies both the length and ratio thresholds.
    """
    if len(label) < 12:
        return False
    lowered = label.lower()
    vowels = sum(1 for ch in lowered if ch in "aeiou")
    consonants = sum(1 for ch in lowered if ch.isalpha() and ch not in "aeiou")
    if vowels == 0:
        # All consonants — unambiguously DGA-shaped by ratio rule
        return True
    return (consonants / vowels) >= 3


def _extract_denial(scos: list[dict], notes: list[dict]) -> SlotState:
    """Extract Denial / Deception slot state from SCOs and analyst notes.

    Three evidence categories (DEC-M5-DENIAL-001):
      - "dga":          Any domain-name SCO whose first label is DGA-shaped
                        per _is_dga_shaped() (DEC-M5-DENIAL-003).
      - "fast_flux":    Any ipv4-addr or ipv6-addr SCO carrying x_ap_dns_ttl
                        field with value <= 60 seconds (forward-compatible;
                        no AP module sets this field yet as of M-5).
      - "note_keyword": Any analyst note whose content contains a substring
                        from _DENIAL_KEYWORDS (case-insensitive).

    Status thresholds (DEC-M5-DENIAL-002):
      EMPTY:   0 evidence items from any category.
      PARTIAL: >= 1 evidence item from exactly 1 category.
      FILLED:  >= 1 evidence item from >= 2 distinct categories
               (cross-category corroboration).

    Parameters
    ----------
    scos:
        List of plain STIX SCO dicts as returned by get_stix_objects().
    notes:
        List of analyst note dicts with at least a 'content' key.

    Returns
    -------
    SlotState
        Denial slot state with contributing_types set to the categories that
        contributed evidence (e.g. frozenset({"dga", "note_keyword"})).
    """
    categories_hit: set[str] = set()
    evidence_count: int = 0

    # -- DGA-shaped domain detection --
    for sco in scos:
        if sco.get("type") != "domain-name":
            continue
        value = sco.get("value", "")
        if not value:
            continue
        # Check only the first label (leftmost component) — the part most likely
        # to be DGA-generated; the TLD / SLD are legitimate in many cases.
        first_label = value.split(".")[0]
        if _is_dga_shaped(first_label):
            categories_hit.add("dga")
            evidence_count += 1

    # -- Fast-flux / low-TTL infrastructure detection --
    for sco in scos:
        if sco.get("type") not in ("ipv4-addr", "ipv6-addr"):
            continue
        ttl = sco.get("x_ap_dns_ttl")
        if ttl is not None:
            try:
                if int(ttl) <= 60:
                    categories_hit.add("fast_flux")
                    evidence_count += 1
            except (TypeError, ValueError):
                pass

    # -- Denial / evasion keyword in analyst notes --
    for note in notes:
        content = note.get("content", "")
        if not content:
            continue
        lowered = content.lower()
        if any(kw in lowered for kw in _DENIAL_KEYWORDS):
            categories_hit.add("note_keyword")
            evidence_count += 1

    # -- Status thresholds (DEC-M5-DENIAL-002) --
    n_categories = len(categories_hit)
    if n_categories == 0:
        status = SlotStatus.EMPTY
        evidence_count = 0
    elif n_categories >= 2:
        status = SlotStatus.FILLED
    else:
        status = SlotStatus.PARTIAL

    return SlotState(
        name=DossierSlotName.DENIAL,
        status=status,
        evidence_count=evidence_count,
        contributing_types=frozenset(categories_hit),
    )
