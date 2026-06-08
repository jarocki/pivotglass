"""M-6 compound integration tests — dossier-aware auto-pivot end-to-end.

These tests exercise the full production sequence: DossierState loaded from
a real workspace → ranker constructed → EventBus.process_results called with
that ranker → F60 gates evaluate the ranked list → callbacks fire in slot-pressure
order → budget consumed by high-value pivots first.

This is the "M-6 ships" acceptance test (plan §4, three-stage).

Stage A — ranker reorders by slot pressure (INT1)
Stage B — M-6 disabled → byte-identical F60 ordering (INT2)
Stage C — budget consumed by high-value pivots first (INT3)
Additional:
  INT4 — all-EMPTY dossier: ordering follows slot-weight hierarchy
  INT5 — all-FILLED dossier: ordering preserves input order
  INT6 — decision log ALLOW entries carry dossier_weight > 0; SKIP entries
          (budget gate) carry the score for full diagnostic coverage

Production sequence exercised here:
  1. WorkspaceManager with real SQLite store
  2. save_dossier_state() persists a fabricated DossierState
  3. load_dossier_state() reads it back (same path as _execute_run_module line ~449)
  4. make_dossier_pivot_ranker(pre_dossier) builds the ranker closure
  5. EventBus.process_results(results, ..., ranker=ranker) re-orders + iterates
  6. F60 budget gate caps the number of callbacks
  7. Decision log shows dossier_weight for diagnostic inspection

@decision DEC-M6-INTEGRATION-TEST-001
@title Compound integration test crosses DossierState persistence, ranker, EventBus,
       and F60 budget gate in one realistic sequence
@status accepted
@rationale The implementer instructions require at least one test exercising the real
           production sequence end-to-end, crossing the boundaries of multiple internal
           components (CLAUDE.md Compound-Interaction Test Requirement). This file
           satisfies that requirement for M-6.

# @mock-exempt: AsyncMock callbacks simulate external module hunt() boundaries.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from adversary_pursuit.core.config import AutoPivotPolicyConfig
from adversary_pursuit.core.dossier_pivot import make_dossier_pivot_ranker
from adversary_pursuit.core.event_bus import EventBus, PivotConfig
from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.dossier.slot_inference import DossierState, SlotState
from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus
from adversary_pursuit.dossier.state import (
    default_deferred_state,
    load_dossier_state,
    save_dossier_state,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workspace(tmp_path) -> WorkspaceManager:
    wm = WorkspaceManager(workspace_dir=tmp_path)
    wm.create("default")
    wm.switch("default")
    return wm


def _make_state(overrides: dict[DossierSlotName, SlotStatus] | None = None) -> DossierState:
    """Build a DossierState with all slots DEFERRED then apply overrides."""
    slots = {slot: SlotState(name=slot, status=SlotStatus.DEFERRED) for slot in DossierSlotName}
    for slot_name, status in (overrides or {}).items():
        slots[slot_name] = SlotState(name=slot_name, status=status)
    return DossierState(slots=slots, total_sco_count=0)


def _permissive_bus(max_per_cascade: int = 100) -> EventBus:
    cfg = AutoPivotPolicyConfig(
        max_per_cascade=max_per_cascade,
        max_per_session=10_000,
        allowlist_path="/dev/null",
        denylist_path="/dev/null",
    )
    return EventBus(PivotConfig(enabled=True, policy=cfg))


def _sco(sco_type: str, value: str, sco_id: str = "", **extra) -> dict:
    d: dict = {"type": sco_type, "value": value}
    if sco_id:
        d["id"] = sco_id
    d.update(extra)
    return d


def _register_recording_callback(bus: EventBus, stix_type: str, fired: list) -> None:
    """Register an async callback that records (value) when invoked."""
    cb = AsyncMock(return_value=[])
    cb._module_path = f"test/{stix_type}"
    fired_ref = fired

    async def _impl(event):
        fired_ref.append(event.value)
        return []

    cb.side_effect = _impl
    bus.subscribe(stix_type, cb)


# ---------------------------------------------------------------------------
# Stage A — ranker reorders by slot pressure
# ---------------------------------------------------------------------------


class TestStageA_RankerReordersBySlotPressure:
    """Plan §4 Stage A: ranker re-orders 6 candidates by slot pressure.

    Workspace: Identity=EMPTY (5.0), TTPs=PARTIAL (3.0×0.5=1.5), Infrastructure=FILLED (0.0).
    Input order: [domain, ipv4, email, url, x509, file]  (Infrastructure-first).
    Expected fire order: email, x509 (Identity 5.0), url, file (TTPs 1.5), domain, ipv4 (Infra 0.0).
    """

    def test_ranker_reorders_identity_first_then_ttps_then_infra(self, tmp_path):
        """INT1: fire order reflects slot pressure — Identity > TTPs > Infrastructure."""
        wm = _make_workspace(tmp_path)
        state = _make_state(
            {
                DossierSlotName.IDENTITY: SlotStatus.EMPTY,
                DossierSlotName.TTPS: SlotStatus.PARTIAL,
                DossierSlotName.INFRASTRUCTURE: SlotStatus.FILLED,
            }
        )
        save_dossier_state(wm, state)
        pre_dossier = load_dossier_state(wm)
        assert pre_dossier is not None

        ranker = make_dossier_pivot_ranker(pre_dossier)
        bus = _permissive_bus()
        fired = []
        for stype in ("email-addr", "x509-certificate", "url", "file", "domain-name", "ipv4-addr"):
            _register_recording_callback(bus, stype, fired)

        # Infrastructure-first input order (domain, ipv4, email, url, x509, file).
        # Use values that pass F60's IOC filter:
        #   - Non-RFC6761 domain (avoid .test, .local, .example TLDs)
        #   - Non-RFC1918 IP
        #   - Non-example.com email / URL
        results = [
            _sco("domain-name", "actor-c2.malicious.ru", sco_id="d1"),
            _sco("ipv4-addr", "203.0.113.5", sco_id="i1"),
            _sco("email-addr", "actor@threatmail.ru", sco_id="e1"),
            _sco("url", "https://malware.malicious.ru/payload.exe", sco_id="u1"),
            _sco("x509-certificate", "cert-fingerprint", sco_id="x1"),
            _sco("file", "evil.exe", sco_id="f1"),
        ]

        asyncio.run(bus.process_results(results, "test/source", ranker=ranker))

        # Both Identity SCOs (email-addr, x509-certificate) must precede Infrastructure
        assert fired.index("actor@threatmail.ru") < fired.index("actor-c2.malicious.ru")
        assert fired.index("cert-fingerprint") < fired.index("203.0.113.5")
        # TTPs (url, file) must precede Infrastructure (domain, ipv4)
        assert fired.index("https://malware.malicious.ru/payload.exe") < fired.index(
            "actor-c2.malicious.ru"
        )
        assert fired.index("evil.exe") < fired.index("203.0.113.5")

    def test_identity_scos_fire_before_infrastructure_scos(self, tmp_path):
        """INT1 focused: Identity-filling SCOs fire before Infrastructure-filling SCOs."""
        wm = _make_workspace(tmp_path)
        state = _make_state(
            {
                DossierSlotName.IDENTITY: SlotStatus.EMPTY,
                DossierSlotName.INFRASTRUCTURE: SlotStatus.FILLED,
            }
        )
        save_dossier_state(wm, state)
        pre_dossier = load_dossier_state(wm)
        assert pre_dossier is not None

        ranker = make_dossier_pivot_ranker(pre_dossier)
        bus = _permissive_bus()
        fired = []
        _register_recording_callback(bus, "email-addr", fired)
        _register_recording_callback(bus, "ipv4-addr", fired)

        results = [
            _sco("ipv4-addr", "infra-first"),
            _sco("email-addr", "identity-second"),
        ]
        asyncio.run(bus.process_results(results, "test/source", ranker=ranker))
        assert fired[0] == "identity-second"
        assert fired[1] == "infra-first"


# ---------------------------------------------------------------------------
# Stage B — M-6 disabled → byte-identical F60 ordering
# ---------------------------------------------------------------------------


class TestStageB_M6Disabled:
    """Plan §4 Stage B: config flag False → input order unchanged + dossier_weight=None."""

    def test_ranker_none_preserves_input_order(self, tmp_path):
        """INT2: when ranker=None, process_results iterates in original input order."""
        wm = _make_workspace(tmp_path)
        state = _make_state(
            {
                DossierSlotName.IDENTITY: SlotStatus.EMPTY,
                DossierSlotName.INFRASTRUCTURE: SlotStatus.FILLED,
            }
        )
        save_dossier_state(wm, state)

        bus = _permissive_bus()
        fired = []
        _register_recording_callback(bus, "ipv4-addr", fired)
        _register_recording_callback(bus, "email-addr", fired)

        # Infrastructure-first input; WITHOUT ranker this order must be preserved
        results = [
            _sco("ipv4-addr", "infra-first"),
            _sco("email-addr", "identity-second"),
        ]
        asyncio.run(bus.process_results(results, "test/source", ranker=None))
        assert fired[0] == "infra-first"
        assert fired[1] == "identity-second"

    def test_decision_log_has_dossier_weight_none_when_no_ranker(self, tmp_path):
        """INT2: decision log entries carry dossier_weight=None when ranker is None."""
        wm = _make_workspace(tmp_path)
        state = _make_state({DossierSlotName.IDENTITY: SlotStatus.EMPTY})
        save_dossier_state(wm, state)

        bus = _permissive_bus()
        _register_recording_callback(bus, "email-addr", [])

        results = [_sco("email-addr", "actor@example.com", sco_id="sco-1")]
        asyncio.run(bus.process_results(results, "test/source", ranker=None))

        for entry in bus.get_decision_log():
            assert entry.get("dossier_weight") is None, (
                f"dossier_weight must be None when no ranker: got {entry.get('dossier_weight')}"
            )


# ---------------------------------------------------------------------------
# Stage C — budget consumed by high-value pivots first
# ---------------------------------------------------------------------------


class TestStageC_BudgetConsumedByHighValuePivots:
    """Plan §4 Stage C: 10 candidates, budget=5, ranker → only Identity+TTPs callbacks fire."""

    def test_high_value_pivots_consume_budget_before_infra(self, tmp_path):
        """INT3: with Identity=EMPTY, 5-callback budget is spent on Identity+TTPs SCOs,
        not the 5 Infrastructure SCOs that arrived first in input order."""
        wm = _make_workspace(tmp_path)
        state = _make_state(
            {
                DossierSlotName.IDENTITY: SlotStatus.EMPTY,
                DossierSlotName.TTPS: SlotStatus.PARTIAL,
                DossierSlotName.INFRASTRUCTURE: SlotStatus.FILLED,
            }
        )
        save_dossier_state(wm, state)
        pre_dossier = load_dossier_state(wm)
        assert pre_dossier is not None

        ranker = make_dossier_pivot_ranker(pre_dossier)
        # max_per_cascade=5 → 5 callbacks allowed
        bus = _permissive_bus(max_per_cascade=5)
        fired = []
        for stype in ("ipv4-addr", "domain-name", "email-addr", "url", "file"):
            _register_recording_callback(bus, stype, fired)

        # 10 candidates: 5 Infrastructure (lexically first) + 2 Identity + 3 TTPs
        results = [
            _sco("ipv4-addr", "infra1"),
            _sco("ipv4-addr", "infra2"),
            _sco("domain-name", "infra3"),
            _sco("domain-name", "infra4"),
            _sco("ipv4-addr", "infra5"),
            _sco("email-addr", "id1@example.com"),
            _sco("email-addr", "id2@example.com"),
            _sco("url", "https://c2.example/stage1"),
            _sco("url", "https://c2.example/stage2"),
            _sco("file", "loader.exe"),
        ]

        asyncio.run(bus.process_results(results, "test/source", ranker=ranker))

        # Exactly 5 callbacks fired
        assert len(fired) == 5

        # All 5 must be Identity or TTPs — not Infrastructure
        for v in fired:
            assert v not in ("infra1", "infra2", "infra3", "infra4", "infra5"), (
                f"Infrastructure SCO '{v}' should not have consumed budget"
            )

    def test_decision_log_skip_entries_carry_dossier_weight(self, tmp_path):
        """INT6: SKIP entries (budget gate) carry dossier_weight for full diagnostic coverage."""
        wm = _make_workspace(tmp_path)
        state = _make_state(
            {
                DossierSlotName.IDENTITY: SlotStatus.EMPTY,
                DossierSlotName.INFRASTRUCTURE: SlotStatus.FILLED,
            }
        )
        save_dossier_state(wm, state)
        pre_dossier = load_dossier_state(wm)
        assert pre_dossier is not None

        ranker = make_dossier_pivot_ranker(pre_dossier)
        # Budget=1: only 1 Identity SCO fires; the rest skip
        bus = _permissive_bus(max_per_cascade=1)
        _register_recording_callback(bus, "email-addr", [])
        _register_recording_callback(bus, "ipv4-addr", [])

        results = [
            _sco("email-addr", "id1@example.com", sco_id="e1"),
            _sco("ipv4-addr", "1.2.3.4", sco_id="i1"),
            _sco("email-addr", "id2@example.com", sco_id="e2"),
        ]
        asyncio.run(bus.process_results(results, "test/source", ranker=ranker))

        log = bus.get_decision_log()
        # All log entries must have dossier_weight populated (not None)
        for entry in log:
            assert "dossier_weight" in entry
            assert entry["dossier_weight"] is not None, (
                f"dossier_weight must be set for all entries when ranker is supplied: {entry}"
            )

        # ALLOW entries (Identity) carry positive weight
        allow_entries = [e for e in log if e["verdict"] == "allow"]
        assert all(e["dossier_weight"] > 0 for e in allow_entries)


# ---------------------------------------------------------------------------
# INT4 — all-EMPTY dossier: ordering follows slot-weight hierarchy
# ---------------------------------------------------------------------------


class TestAllEmptyDossier:
    def test_all_empty_ordering_follows_slot_weights(self, tmp_path):
        """INT4: all-EMPTY dossier → ordering follows SLOT_WEIGHTS (Identity > Infrastructure)."""
        wm = _make_workspace(tmp_path)
        state = _make_state({slot: SlotStatus.EMPTY for slot in DossierSlotName})
        save_dossier_state(wm, state)
        pre_dossier = load_dossier_state(wm)
        assert pre_dossier is not None

        ranker = make_dossier_pivot_ranker(pre_dossier)
        bus = _permissive_bus()
        fired = []
        _register_recording_callback(bus, "email-addr", fired)
        _register_recording_callback(bus, "ipv4-addr", fired)

        # Infrastructure first in input; Identity must win due to higher weight
        results = [
            _sco("ipv4-addr", "infra-first"),  # Infrastructure weight=2.0 → score 2.0
            _sco("email-addr", "identity-last"),  # Identity weight=5.0 → score 5.0
        ]
        asyncio.run(bus.process_results(results, "test/source", ranker=ranker))
        # email-addr (Identity=5.0) must fire before ipv4-addr (Infrastructure=2.0)
        assert fired[0] == "identity-last"
        assert fired[1] == "infra-first"


# ---------------------------------------------------------------------------
# INT5 — all-FILLED dossier: ordering preserves input order
# ---------------------------------------------------------------------------


class TestAllFilledDossier:
    def test_all_filled_preserves_input_order(self, tmp_path):
        """INT5: all-FILLED dossier → all scores 0.0 → stable sort = input order."""
        wm = _make_workspace(tmp_path)
        state = _make_state({slot: SlotStatus.FILLED for slot in DossierSlotName})
        save_dossier_state(wm, state)
        pre_dossier = load_dossier_state(wm)
        assert pre_dossier is not None

        ranker = make_dossier_pivot_ranker(pre_dossier)
        bus = _permissive_bus()
        fired = []
        _register_recording_callback(bus, "email-addr", fired)
        _register_recording_callback(bus, "ipv4-addr", fired)

        # When all slots are FILLED every score is 0.0 → stable sort preserves input order
        results = [
            _sco("ipv4-addr", "first"),
            _sco("email-addr", "second"),
        ]
        asyncio.run(bus.process_results(results, "test/source", ranker=ranker))
        assert fired[0] == "first"
        assert fired[1] == "second"

    def test_default_deferred_state_preserves_input_order(self, tmp_path):
        """INT5 variant: default_deferred_state (fresh workspace) → all DEFERRED → input order."""
        # Fresh workspace: load_dossier_state returns None → default_deferred_state used
        wm = _make_workspace(tmp_path)
        pre_dossier = load_dossier_state(wm) or default_deferred_state()

        ranker = make_dossier_pivot_ranker(pre_dossier)
        bus = _permissive_bus()
        fired = []
        _register_recording_callback(bus, "email-addr", fired)
        _register_recording_callback(bus, "ipv4-addr", fired)

        results = [
            _sco("ipv4-addr", "first"),
            _sco("email-addr", "second"),
        ]
        asyncio.run(bus.process_results(results, "test/source", ranker=ranker))
        # All DEFERRED → all scores 0.0 → input order preserved
        assert fired[0] == "first"
        assert fired[1] == "second"
