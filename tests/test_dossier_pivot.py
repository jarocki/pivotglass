"""Tests for core/dossier_pivot.py — M-6 dossier-aware ranker unit tests.

Evaluation Contract gates (test_dossier_pivot.py ~12 tests):
  P1  compute_slot_fill_score: single EMPTY slot → SLOT_WEIGHTS[slot] × 1.0
  P2  compute_slot_fill_score: all slots FILLED → returns 0.0
  P3  compute_slot_fill_score: PARTIAL slot → weight × 0.5
  P4  compute_slot_fill_score: DEFERRED slot → returns 0.0
  P5  compute_slot_fill_score: SCO type not in SLOT_EVIDENCE_TYPES → 0.0
  P6  compute_slot_fill_score: SCO type mapping to two slots → sum of contributions
  P7  make_dossier_pivot_ranker: returns callable taking (results, source_module)
  P8  make_dossier_pivot_ranker: Identity-filling SCO ranks above Infrastructure SCO
      when Identity=EMPTY and Infrastructure=FILLED
  P9  make_dossier_pivot_ranker: stable sort — equal slot-fill scores preserve input order
  P10 make_dossier_pivot_ranker: tie-break on x_abuse_confidence_score (higher first;
      missing field treated as -1) (DEC-M6-PIVOT-006)
  P11 make_dossier_pivot_ranker: empty results list → empty output; input not mutated
  P12 STATUS_MULTIPLIERS contains exactly 4 keys with correct values
      (regression guard — DEC-M6-PIVOT-003)

@decision DEC-M6-PIVOT-003
@title STATUS_MULTIPLIERS is the single authority for status-to-weight values
@status accepted
@rationale Tests assert exact values as a regression guard so future implementers
           can't silently change the weights without a deliberate test update.

@decision DEC-M6-PIVOT-006
@title Tie-break: equal slot-fill scores → higher x_abuse_confidence_score first
@status accepted
@rationale Mirrors F60's preference for high-confidence indicators.
"""

from __future__ import annotations

import pytest

from adversary_pursuit.core.dossier_pivot import (
    STATUS_MULTIPLIERS,
    compute_slot_fill_score,
    make_dossier_pivot_ranker,
)
from adversary_pursuit.dossier.slot_inference import DossierState, SlotState
from adversary_pursuit.dossier.slots import (
    SLOT_WEIGHTS,
    DossierSlotName,
    SlotStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(overrides: dict[DossierSlotName, SlotStatus] | None = None) -> DossierState:
    """Build a DossierState with all slots DEFERRED, then apply overrides."""
    slots = {slot: SlotState(name=slot, status=SlotStatus.DEFERRED) for slot in DossierSlotName}
    for slot_name, status in (overrides or {}).items():
        slots[slot_name] = SlotState(name=slot_name, status=status)
    return DossierState(slots=slots, total_sco_count=0)


def _all_empty() -> DossierState:
    return _make_state({slot: SlotStatus.EMPTY for slot in DossierSlotName})


def _all_filled() -> DossierState:
    return _make_state({slot: SlotStatus.FILLED for slot in DossierSlotName})


def _sco(sco_type: str, value: str = "x", sco_id: str = "", **extra) -> dict:
    d: dict = {"type": sco_type, "value": value}
    if sco_id:
        d["id"] = sco_id
    d.update(extra)
    return d


# ---------------------------------------------------------------------------
# STATUS_MULTIPLIERS regression guard (P12)
# ---------------------------------------------------------------------------


class TestStatusMultipliers:
    def test_exactly_four_keys(self):
        """STATUS_MULTIPLIERS must have exactly 4 keys (DEC-M6-PIVOT-003)."""
        assert len(STATUS_MULTIPLIERS) == 4

    def test_empty_multiplier(self):
        assert STATUS_MULTIPLIERS[SlotStatus.EMPTY] == 1.0

    def test_partial_multiplier(self):
        assert STATUS_MULTIPLIERS[SlotStatus.PARTIAL] == 0.5

    def test_filled_multiplier(self):
        assert STATUS_MULTIPLIERS[SlotStatus.FILLED] == 0.0

    def test_deferred_multiplier(self):
        assert STATUS_MULTIPLIERS[SlotStatus.DEFERRED] == 0.0


# ---------------------------------------------------------------------------
# compute_slot_fill_score (P1–P6)
# ---------------------------------------------------------------------------


class TestComputeSlotFillScore:
    def test_single_empty_slot_returns_slot_weight(self):
        """P1: email-addr → Identity slot. Identity=EMPTY → 5.0 × 1.0 = 5.0."""
        state = _make_state({DossierSlotName.IDENTITY: SlotStatus.EMPTY})
        score = compute_slot_fill_score("email-addr", state)
        assert score == pytest.approx(SLOT_WEIGHTS[DossierSlotName.IDENTITY] * 1.0)

    def test_all_slots_filled_returns_zero(self):
        """P2: any SCO type → 0.0 when every slot is FILLED."""
        state = _all_filled()
        assert compute_slot_fill_score("email-addr", state) == 0.0
        assert compute_slot_fill_score("ipv4-addr", state) == 0.0
        assert compute_slot_fill_score("url", state) == 0.0

    def test_partial_slot_returns_half_weight(self):
        """P3: ipv4-addr → Infrastructure slot. Infrastructure=PARTIAL → 2.0 × 0.5 = 1.0."""
        state = _make_state({DossierSlotName.INFRASTRUCTURE: SlotStatus.PARTIAL})
        score = compute_slot_fill_score("ipv4-addr", state)
        assert score == pytest.approx(SLOT_WEIGHTS[DossierSlotName.INFRASTRUCTURE] * 0.5)

    def test_deferred_slot_returns_zero(self):
        """P4: DEFERRED slot multiplier is 0.0 → score = 0."""
        state = _make_state({DossierSlotName.IDENTITY: SlotStatus.DEFERRED})
        assert compute_slot_fill_score("email-addr", state) == 0.0

    def test_unknown_sco_type_returns_zero(self):
        """P5: SCO type not in SLOT_EVIDENCE_TYPES returns 0.0."""
        state = _all_empty()
        assert compute_slot_fill_score("mutex", state) == 0.0
        assert compute_slot_fill_score("windows-registry-key", state) == 0.0
        assert compute_slot_fill_score("", state) == 0.0

    def test_multi_slot_sco_type_returns_sum(self):
        """P6: A SCO type mapping to two slots returns the sum of contributions.

        We inject a synthetic two-slot mapping by patching SLOT_EVIDENCE_TYPES
        rather than relying on a production type that happens to map to two slots.
        The ranker must be robust to multi-slot mappings whether or not any
        current type exercises them.
        """
        from adversary_pursuit.dossier import slots as slots_mod

        # Temporarily add a two-slot mapping
        original = slots_mod.SLOT_EVIDENCE_TYPES.get("test-multi-sco")
        slots_mod.SLOT_EVIDENCE_TYPES["test-multi-sco"] = [
            DossierSlotName.IDENTITY,
            DossierSlotName.INFRASTRUCTURE,
        ]
        try:
            state = _make_state(
                {
                    DossierSlotName.IDENTITY: SlotStatus.EMPTY,
                    DossierSlotName.INFRASTRUCTURE: SlotStatus.EMPTY,
                }
            )
            score = compute_slot_fill_score("test-multi-sco", state)
            expected = (
                SLOT_WEIGHTS[DossierSlotName.IDENTITY] * 1.0
                + SLOT_WEIGHTS[DossierSlotName.INFRASTRUCTURE] * 1.0
            )
            assert score == pytest.approx(expected)
        finally:
            if original is None:
                del slots_mod.SLOT_EVIDENCE_TYPES["test-multi-sco"]
            else:
                slots_mod.SLOT_EVIDENCE_TYPES["test-multi-sco"] = original


# ---------------------------------------------------------------------------
# make_dossier_pivot_ranker (P7–P11)
# ---------------------------------------------------------------------------


class TestMakeDossierPivotRanker:
    def test_returns_callable(self):
        """P7: make_dossier_pivot_ranker returns a callable."""
        state = _all_empty()
        ranker = make_dossier_pivot_ranker(state)
        assert callable(ranker)

    def test_callable_accepts_results_and_source_module(self):
        """P7: callable takes (results, source_module) and returns list."""
        state = _all_empty()
        ranker = make_dossier_pivot_ranker(state)
        results = [_sco("email-addr", "a@b.com"), _sco("ipv4-addr", "1.2.3.4")]
        output = ranker(results, "test/source")
        assert isinstance(output, list)
        assert len(output) == 2

    def test_does_not_mutate_input(self):
        """P7: ranker returns a new list; input is not mutated."""
        state = _all_empty()
        ranker = make_dossier_pivot_ranker(state)
        results = [_sco("ipv4-addr", "1.2.3.4"), _sco("email-addr", "a@b.com")]
        original_ids = [id(r) for r in results]
        output = ranker(results, "test/source")
        # Input order unchanged
        assert [id(r) for r in results] == original_ids
        # Output is a distinct list
        assert output is not results

    def test_identity_ranks_above_infrastructure_when_identity_empty_infra_filled(self):
        """P8: email-addr (Identity=EMPTY, score=5.0) ranked before
        ipv4-addr (Infrastructure=FILLED, score=0.0)."""
        state = _make_state(
            {
                DossierSlotName.IDENTITY: SlotStatus.EMPTY,
                DossierSlotName.INFRASTRUCTURE: SlotStatus.FILLED,
            }
        )
        ranker = make_dossier_pivot_ranker(state)
        # Infrastructure-first input order
        results = [
            _sco("ipv4-addr", "1.2.3.4"),
            _sco("domain-name", "evil.com"),
            _sco("email-addr", "actor@example.com"),
        ]
        ranked = ranker(results, "test/source")
        # email-addr (Identity) must come first
        assert ranked[0]["type"] == "email-addr"
        # Infrastructure pivots at the end
        assert ranked[-1]["type"] in ("ipv4-addr", "domain-name")

    def test_stable_sort_equal_scores_preserve_input_order(self):
        """P9: two SCOs with identical slot-fill scores keep their original order."""
        state = _make_state({DossierSlotName.IDENTITY: SlotStatus.EMPTY})
        ranker = make_dossier_pivot_ranker(state)
        # Both email-addr map to Identity → same score
        sco_a = _sco("email-addr", "a@example.com", sco_id="id-a")
        sco_b = _sco("email-addr", "b@example.com", sco_id="id-b")
        results = [sco_a, sco_b]
        ranked = ranker(results, "test/source")
        assert ranked[0]["id"] == "id-a"
        assert ranked[1]["id"] == "id-b"

    def test_tie_break_higher_confidence_first(self):
        """P10: equal slot-fill scores → higher x_abuse_confidence_score first
        (DEC-M6-PIVOT-006)."""
        state = _make_state({DossierSlotName.INFRASTRUCTURE: SlotStatus.EMPTY})
        ranker = make_dossier_pivot_ranker(state)
        # Both are ipv4-addr → same slot score; differ in confidence
        low_conf = _sco("ipv4-addr", "1.2.3.4", sco_id="low", x_abuse_confidence_score=30)
        high_conf = _sco("ipv4-addr", "5.6.7.8", sco_id="high", x_abuse_confidence_score=90)
        # Input order: low first
        results = [low_conf, high_conf]
        ranked = ranker(results, "test/source")
        assert ranked[0]["id"] == "high"
        assert ranked[1]["id"] == "low"

    def test_tie_break_missing_confidence_treated_as_minus_one(self):
        """P10: missing x_abuse_confidence_score treated as -1 → scored item wins tie."""
        state = _make_state({DossierSlotName.INFRASTRUCTURE: SlotStatus.EMPTY})
        ranker = make_dossier_pivot_ranker(state)
        no_score = _sco("ipv4-addr", "1.2.3.4", sco_id="no-score")
        has_score = _sco("ipv4-addr", "5.6.7.8", sco_id="has-score", x_abuse_confidence_score=10)
        results = [no_score, has_score]
        ranked = ranker(results, "test/source")
        assert ranked[0]["id"] == "has-score"

    def test_empty_results_returns_empty_list(self):
        """P11: empty input → empty output."""
        state = _all_empty()
        ranker = make_dossier_pivot_ranker(state)
        assert ranker([], "test/source") == []

    def test_all_filled_dossier_preserves_input_order(self):
        """When all slots are FILLED, every score is 0.0 → stable sort = input order."""
        state = _all_filled()
        ranker = make_dossier_pivot_ranker(state)
        results = [
            _sco("email-addr", "a@b.com", sco_id="1"),
            _sco("ipv4-addr", "1.2.3.4", sco_id="2"),
            _sco("url", "http://x.com", sco_id="3"),
        ]
        ranked = ranker(results, "test/source")
        assert [r["id"] for r in ranked] == ["1", "2", "3"]

    def test_ranker_exposes_score_for_type_side_channel(self):
        """make_dossier_pivot_ranker attaches _score_for_type so EventBus.publish
        can populate dossier_weight without re-importing dossier_pivot."""
        state = _make_state({DossierSlotName.IDENTITY: SlotStatus.EMPTY})
        ranker = make_dossier_pivot_ranker(state)
        score_fn = getattr(ranker, "_score_for_type", None)
        assert score_fn is not None, "ranker must expose _score_for_type side-channel"
        assert score_fn("email-addr") == pytest.approx(5.0)
        assert score_fn("ipv4-addr") == 0.0  # Identity=EMPTY but ipv4→Infrastructure=DEFERRED

    def test_deferred_slots_not_preferred(self):
        """DEFERRED slots get score 0.0 → DEFERRED SCO types sort to the end.
        Guards against future regressions if a slot extractor is re-scaffolded."""
        # All slots DEFERRED (default)
        state = _make_state()
        ranker = make_dossier_pivot_ranker(state)
        # email-addr → Identity (DEFERRED) → score 0.0
        # ipv4-addr → Infrastructure (DEFERRED) → score 0.0
        results = [
            _sco("email-addr", "a@b.com", sco_id="1"),
            _sco("ipv4-addr", "1.2.3.4", sco_id="2"),
        ]
        ranked = ranker(results, "test/source")
        # Stable sort: original order preserved when all 0.0
        assert [r["id"] for r in ranked] == ["1", "2"]
