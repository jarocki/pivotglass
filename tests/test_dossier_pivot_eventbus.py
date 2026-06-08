"""Tests for EventBus.process_results ranker kwarg (M-6).

Evaluation Contract gates (test_dossier_pivot_eventbus.py ~6 tests):
  EB1  process_results(results, source_module, ranker=None) → byte-identical F60
       (iteration follows input order)
  EB2  process_results(results, source_module, ranker=ranker) → iteration follows
       ranked order
  EB3  process_results does not call ranker when results is empty
  EB4  process_results propagates dry_run to publish unchanged (regression)
  EB5  process_results calls self._policy.reset_cascade_budget() exactly once (regression)
  EB6  process_results with ranker still respects per-cascade budget

Additional regression tests:
  EB7  positional-arg-only call (no ranker kwarg) is byte-identical to F60
  EB8  PivotPolicy.evaluate returns same PolicyDecision shape post-M-6 (gate invariant)

@decision DEC-M6-EVENTBUS-TEST-001
@title EventBus.process_results ranker kwarg tests cover F60 regression + M-6 ordering
@status accepted
@rationale These tests verify that (a) the new optional ranker kwarg does not break
           existing F60 call-site behavior (ranker=None is byte-identical to pre-M-6),
           and (b) when a ranker is supplied the iteration order changes accordingly.
           budget, dry_run, and reset_cascade_budget regression tests guard against
           the kwarg accidentally shadowing existing parameters or skipping budget resets.

# @mock-exempt: AsyncMock callbacks simulate external module hunt() boundaries.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from adversary_pursuit.core.config import AutoPivotPolicyConfig
from adversary_pursuit.core.dossier_pivot import make_dossier_pivot_ranker
from adversary_pursuit.core.event_bus import EventBus, PivotConfig
from adversary_pursuit.core.pivot_policy import PivotPolicy
from adversary_pursuit.dossier.slot_inference import DossierState, SlotState
from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _permissive_bus(max_per_cascade: int = 100) -> EventBus:
    """EventBus with a permissive policy (no IOC or confidence filtering)."""
    cfg = AutoPivotPolicyConfig(
        max_per_cascade=max_per_cascade,
        max_per_session=10_000,
        allowlist_path="/dev/null",
        denylist_path="/dev/null",
    )
    return EventBus(PivotConfig(enabled=True, policy=cfg))


def _make_state(overrides: dict[DossierSlotName, SlotStatus] | None = None) -> DossierState:
    slots = {slot: SlotState(name=slot, status=SlotStatus.DEFERRED) for slot in DossierSlotName}
    for slot_name, status in (overrides or {}).items():
        slots[slot_name] = SlotState(name=slot_name, status=status)
    return DossierState(slots=slots, total_sco_count=0)


def _sco(sco_type: str, value: str, sco_id: str = "", **extra) -> dict:
    d: dict = {"type": sco_type, "value": value}
    if sco_id:
        d["id"] = sco_id
    d.update(extra)
    return d


def _register_callback(bus: EventBus, stix_type: str, fired_order: list) -> AsyncMock:
    """Register a callback that appends to fired_order when invoked."""
    cb = AsyncMock(return_value=[])
    cb._module_path = f"test/{stix_type}"
    fired_order_ref = fired_order

    async def _impl(event):
        fired_order_ref.append(event.value)
        return []

    cb.side_effect = _impl
    bus.subscribe(stix_type, cb)
    return cb


# ---------------------------------------------------------------------------
# EB1: ranker=None → F60 input order
# ---------------------------------------------------------------------------


class TestRankerNone:
    def test_no_ranker_preserves_input_order(self):
        """EB1: process_results without ranker iterates in input order."""
        bus = _permissive_bus()
        fired = []
        _register_callback(bus, "ipv4-addr", fired)
        _register_callback(bus, "email-addr", fired)

        results = [
            _sco("ipv4-addr", "1.2.3.4"),
            _sco("email-addr", "actor@example.com"),
        ]
        asyncio.run(bus.process_results(results, source_module="test/mod", ranker=None))
        assert fired == ["1.2.3.4", "actor@example.com"]

    def test_positional_call_without_ranker_kwarg(self):
        """EB7: positional-arg-only call (pre-M-6 style) preserves F60 behavior."""
        bus = _permissive_bus()
        fired = []
        _register_callback(bus, "ipv4-addr", fired)
        _register_callback(bus, "email-addr", fired)

        results = [
            _sco("ipv4-addr", "1.2.3.4"),
            _sco("email-addr", "actor@example.com"),
        ]
        # No ranker kwarg — pure F60 call signature
        asyncio.run(bus.process_results(results, "test/mod", 0))
        assert fired == ["1.2.3.4", "actor@example.com"]


# ---------------------------------------------------------------------------
# EB2: ranker supplied → ranked order
# ---------------------------------------------------------------------------


class TestRankerSupplied:
    def test_ranker_applied_changes_iteration_order(self):
        """EB2: iteration follows ranked order when ranker is supplied."""
        # Identity=EMPTY (weight 5.0) → email-addr ranks first
        state = _make_state(
            {
                DossierSlotName.IDENTITY: SlotStatus.EMPTY,
                DossierSlotName.INFRASTRUCTURE: SlotStatus.FILLED,
            }
        )
        ranker = make_dossier_pivot_ranker(state)
        bus = _permissive_bus()
        fired = []
        _register_callback(bus, "email-addr", fired)
        _register_callback(bus, "ipv4-addr", fired)

        # Infrastructure-first input
        results = [
            _sco("ipv4-addr", "1.2.3.4"),
            _sco("email-addr", "actor@example.com"),
        ]
        asyncio.run(bus.process_results(results, "test/mod", ranker=ranker))
        # email-addr (Identity=EMPTY) must fire before ipv4-addr (Infrastructure=FILLED)
        assert fired[0] == "actor@example.com"
        assert fired[1] == "1.2.3.4"

    def test_decision_log_populated_with_dossier_weight_when_ranker_supplied(self):
        """EB2: decision log entries carry dossier_weight when ranker is supplied."""
        state = _make_state({DossierSlotName.IDENTITY: SlotStatus.EMPTY})
        ranker = make_dossier_pivot_ranker(state)
        bus = _permissive_bus()
        _register_callback(bus, "email-addr", [])

        results = [_sco("email-addr", "actor@example.com", sco_id="sco-1")]
        asyncio.run(bus.process_results(results, "test/mod", ranker=ranker))

        log = bus.get_decision_log()
        assert len(log) >= 1
        entry = log[0]
        assert "dossier_weight" in entry
        assert entry["dossier_weight"] is not None
        assert entry["dossier_weight"] == pytest.approx(5.0)  # Identity=EMPTY, weight=5.0

    def test_decision_log_dossier_weight_none_when_no_ranker(self):
        """EB1 corollary: dossier_weight is None in all entries when ranker=None."""
        bus = _permissive_bus()
        _register_callback(bus, "ipv4-addr", [])

        results = [_sco("ipv4-addr", "1.2.3.4", sco_id="sco-1")]
        asyncio.run(bus.process_results(results, "test/mod", ranker=None))

        log = bus.get_decision_log()
        assert len(log) >= 1
        for entry in log:
            assert entry.get("dossier_weight") is None


# ---------------------------------------------------------------------------
# EB3: empty results — ranker not called
# ---------------------------------------------------------------------------


class TestEmptyResults:
    def test_ranker_not_called_when_results_empty(self):
        """EB3: ranker is not invoked when results list is empty."""
        call_count = []

        def _counting_ranker(results, source_module):
            call_count.append(1)
            return results

        bus = _permissive_bus()
        asyncio.run(bus.process_results([], "test/mod", ranker=_counting_ranker))
        assert call_count == [], "ranker must not be called for empty results"

    def test_empty_results_returns_empty(self):
        """EB3 corollary: empty results → empty pivot_results regardless of ranker."""
        state = _make_state()
        ranker = make_dossier_pivot_ranker(state)
        bus = _permissive_bus()
        result = asyncio.run(bus.process_results([], "test/mod", ranker=ranker))
        assert result == []


# ---------------------------------------------------------------------------
# EB4: dry_run propagated
# ---------------------------------------------------------------------------


class TestDryRunPropagated:
    def test_dry_run_propagated_with_ranker(self):
        """EB4: dry_run is passed through to publish() when ranker is supplied."""
        state = _make_state({DossierSlotName.IDENTITY: SlotStatus.EMPTY})
        ranker = make_dossier_pivot_ranker(state)
        bus = _permissive_bus()
        actual_callback = AsyncMock(return_value=[])
        actual_callback._module_path = "test/email"
        bus.subscribe("email-addr", actual_callback)

        results = [_sco("email-addr", "actor@example.com")]
        asyncio.run(bus.process_results(results, "test/mod", dry_run=True, ranker=ranker))

        # dry_run=True → callback must NOT have been invoked
        actual_callback.assert_not_called()
        # But decision log should have an entry
        log = bus.get_decision_log()
        assert len(log) >= 1


# ---------------------------------------------------------------------------
# EB5: reset_cascade_budget called exactly once
# ---------------------------------------------------------------------------


class TestCascadeBudgetReset:
    def test_reset_cascade_budget_called_once(self):
        """EB5: reset_cascade_budget() is called exactly once per process_results call."""
        bus = _permissive_bus()
        with patch.object(bus._policy, "reset_cascade_budget") as mock_reset:
            asyncio.run(
                bus.process_results(
                    [_sco("email-addr", "a@b.com")],
                    "test/mod",
                )
            )
        mock_reset.assert_called_once()

    def test_reset_cascade_budget_called_once_with_ranker(self):
        """EB5: reset_cascade_budget() called exactly once even with ranker."""
        state = _make_state()
        ranker = make_dossier_pivot_ranker(state)
        bus = _permissive_bus()
        with patch.object(bus._policy, "reset_cascade_budget") as mock_reset:
            asyncio.run(
                bus.process_results(
                    [_sco("email-addr", "a@b.com")],
                    "test/mod",
                    ranker=ranker,
                )
            )
        mock_reset.assert_called_once()


# ---------------------------------------------------------------------------
# EB6: budget respected with ranker
# ---------------------------------------------------------------------------


class TestBudgetWithRanker:
    def test_per_cascade_budget_honored_with_ranker(self):
        """EB6: ranker changes order but budget still caps the number of callbacks."""
        # max_per_cascade=2 → only 2 callbacks allowed
        bus = _permissive_bus(max_per_cascade=2)
        state = _make_state({DossierSlotName.IDENTITY: SlotStatus.EMPTY})
        ranker = make_dossier_pivot_ranker(state)

        fired = []
        _register_callback(bus, "email-addr", fired)
        _register_callback(bus, "ipv4-addr", fired)

        # 4 candidates; budget caps at 2
        results = [
            _sco("ipv4-addr", "1.1.1.1"),
            _sco("ipv4-addr", "2.2.2.2"),
            _sco("email-addr", "a@b.com"),
            _sco("email-addr", "c@d.com"),
        ]
        asyncio.run(bus.process_results(results, "test/mod", ranker=ranker))
        # Exactly 2 callbacks fired (budget cap)
        assert len(fired) == 2
        # The 2 that fired must be the email-addrs (Identity=EMPTY, highest score)
        assert all("@" in v for v in fired)


# ---------------------------------------------------------------------------
# EB8: PivotPolicy.evaluate shape unchanged post-M-6 (F60 gate invariant)
# ---------------------------------------------------------------------------


class TestPivotPolicyEvaluateShapeUnchanged:
    def test_evaluate_returns_policy_decision_with_three_fields(self):
        """EB8: PivotPolicy.evaluate returns PolicyDecision(verdict, gate, reason)
        — shape unchanged by M-6."""
        from adversary_pursuit.core.pivot_policy import PolicyDecision

        policy = PivotPolicy(
            AutoPivotPolicyConfig(
                max_per_cascade=100,
                max_per_session=100,
                allowlist_path="/dev/null",
                denylist_path="/dev/null",
            )
        )
        decision = policy.evaluate(
            sco_type="ipv4-addr",
            value="1.2.3.4",
            source_module="test/mod",
            candidate_module="test/candidate",
        )
        assert isinstance(decision, PolicyDecision)
        assert hasattr(decision, "verdict")
        assert hasattr(decision, "gate")
        assert hasattr(decision, "reason")
        assert decision.verdict in ("allow", "skip")
