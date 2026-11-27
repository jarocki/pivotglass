"""M-6 compound integration tests — dossier-aware pivot-run ordering end-to-end.

These tests exercise the full production sequence: DossierState loaded from
a real workspace → ranker constructed → a PivotRun seeded with module results
(autopivot's shape, DEC-PIVOT-AUTOPIVOT-001) orders its frontier with that
ranker (DEC-M6-PIVOT-010) → policy gates evaluate each indicator → modules are
called in slot-pressure order → budget consumed by high-value pivots first.
Until v1.5.0 the same scenarios ran through the retired event-harness cascade.

This is the "M-6 ships" acceptance test (plan §4, three-stage).

Stage A — ranker reorders by slot pressure (INT1)
Stage B — M-6 disabled → discovery ordering (INT2)
Stage C — budget consumed by high-value pivots first (INT3)
Additional:
  INT4 — all-EMPTY dossier: ordering follows slot-weight hierarchy
  INT5 — all-FILLED dossier: ordering preserves input order
  INT6 — decision ALLOW entries carry dossier_weight > 0; SKIP entries
          (budget gate) carry the score for full diagnostic coverage

Production sequence exercised here:
  1. WorkspaceManager with real SQLite store
  2. save_dossier_state() persists a fabricated DossierState
  3. load_dossier_state() reads it back (same path as _execute_run_module line ~449)
  4. make_dossier_pivot_ranker(pre_dossier) builds the ranker closure
  5. PivotRun(result_seeds=results, ranker=ranker) orders its frontier + expands
  6. The policy's budget gate caps the number of module calls
  7. The run's decisions show dossier_weight for diagnostic inspection

@decision DEC-M6-INTEGRATION-TEST-001
@title Compound integration test crosses DossierState persistence, ranker, PivotRun,
       and the policy budget gate in one realistic sequence
@status accepted
@rationale The implementer instructions require at least one test exercising the real
           production sequence end-to-end, crossing the boundaries of multiple internal
           components (CLAUDE.md Compound-Interaction Test Requirement). This file
           satisfies that requirement for M-6.

A recording executor stands in for the module boundary (``ToolContext.run_module``).
"""

from __future__ import annotations

from pivotglass.core.config import AutoPivotPolicyConfig
from pivotglass.core.dossier_pivot import make_dossier_pivot_ranker
from pivotglass.core.workspace import WorkspaceManager
from pivotglass.dossier.slot_inference import DossierState, SlotState
from pivotglass.dossier.slots import DossierSlotName, SlotStatus
from pivotglass.dossier.state import (
    default_deferred_state,
    load_dossier_state,
    save_dossier_state,
)
from pivotglass.modules.pivoting.run import ModuleOutcome, PivotRun

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


class _Harness:
    """Modules subscribed one per STIX type; records the values they are asked about."""

    def __init__(self, budget: int) -> None:
        self.budget = budget
        self.types: list[str] = []
        self.fired: list[str] = []
        self.log: list[dict] = []


def _permissive_run(max_per_cascade: int = 100) -> _Harness:
    return _Harness(max_per_cascade)


def _sco(sco_type: str, value: str, sco_id: str = "", **extra) -> dict:
    d: dict = {"type": sco_type, "value": value}
    if sco_id:
        d["id"] = sco_id
    d.update(extra)
    return d


def _register_recording_callback(harness: _Harness, stix_type: str, fired: list) -> None:
    """Subscribe a module to *stix_type* that records each value it is asked about."""
    harness.types.append(stix_type)
    harness.fired = fired


def _process(harness: _Harness, results: list[dict], ranker=None) -> dict:
    """Seed a pivot run with *results* as autopivot does and run it to completion."""

    def executor(_module: str, value: str) -> ModuleOutcome:
        harness.fired.append(value)
        return ModuleOutcome([])

    cfg = AutoPivotPolicyConfig(allowlist_path="/dev/null", denylist_path="/dev/null")
    snapshot = PivotRun(
        result_seeds=results, result_source="test/source", executor=executor,
        subscriptions={f"test/{stix_type}": [stix_type] for stix_type in harness.types},
        policy_config=cfg, budget=harness.budget, ranker=ranker,
    ).run()
    harness.log = snapshot["decisions"]
    return snapshot


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
        harness = _permissive_run()
        fired = []
        for stype in ("email-addr", "x509-certificate", "url", "file", "domain-name", "ipv4-addr"):
            _register_recording_callback(harness, stype, fired)

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

        _process(harness, results, ranker=ranker)

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
        harness = _permissive_run()
        fired = []
        _register_recording_callback(harness, "email-addr", fired)
        _register_recording_callback(harness, "ipv4-addr", fired)

        results = [
            _sco("ipv4-addr", "infra-first"),
            _sco("email-addr", "identity-second"),
        ]
        _process(harness, results, ranker=ranker)
        assert fired[0] == "identity-second"
        assert fired[1] == "infra-first"


# ---------------------------------------------------------------------------
# Stage B — M-6 disabled → discovery ordering
# ---------------------------------------------------------------------------


class TestStageB_M6Disabled:
    """Plan §4 Stage B: config flag False → input order unchanged, no dossier_weight."""

    def test_ranker_none_preserves_input_order(self, tmp_path):
        """INT2: with no ranker, the run expands in original discovery order."""
        wm = _make_workspace(tmp_path)
        state = _make_state(
            {
                DossierSlotName.IDENTITY: SlotStatus.EMPTY,
                DossierSlotName.INFRASTRUCTURE: SlotStatus.FILLED,
            }
        )
        save_dossier_state(wm, state)

        harness = _permissive_run()
        fired = []
        _register_recording_callback(harness, "ipv4-addr", fired)
        _register_recording_callback(harness, "email-addr", fired)

        # Infrastructure-first input; WITHOUT ranker this order must be preserved
        results = [
            _sco("ipv4-addr", "infra-first"),
            _sco("email-addr", "identity-second"),
        ]
        _process(harness, results, ranker=None)
        assert fired[0] == "infra-first"
        assert fired[1] == "identity-second"

    def test_decision_log_has_no_dossier_weight_when_no_ranker(self, tmp_path):
        """INT2: decisions carry no dossier_weight when there is no ranker."""
        wm = _make_workspace(tmp_path)
        state = _make_state({DossierSlotName.IDENTITY: SlotStatus.EMPTY})
        save_dossier_state(wm, state)

        harness = _permissive_run()
        _register_recording_callback(harness, "email-addr", [])

        results = [_sco("email-addr", "actor@example.com", sco_id="sco-1")]
        _process(harness, results, ranker=None)

        assert harness.log
        for entry in harness.log:
            assert "dossier_weight" not in entry, f"no ranker, no dossier_weight: {entry}"


# ---------------------------------------------------------------------------
# Stage C — budget consumed by high-value pivots first
# ---------------------------------------------------------------------------


class TestStageC_BudgetConsumedByHighValuePivots:
    """Plan §4 Stage C: 10 candidates, budget=5, ranker → only Identity+TTPs module calls happen."""

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
        # budget 5 → 5 module calls allowed
        harness = _permissive_run(max_per_cascade=5)
        fired = []
        for stype in ("ipv4-addr", "domain-name", "email-addr", "url", "file"):
            _register_recording_callback(harness, stype, fired)

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

        _process(harness, results, ranker=ranker)

        # Exactly 5 module calls made
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
        harness = _permissive_run(max_per_cascade=1)
        _register_recording_callback(harness, "email-addr", [])
        _register_recording_callback(harness, "ipv4-addr", [])

        results = [
            _sco("email-addr", "id1@example.com", sco_id="e1"),
            _sco("ipv4-addr", "1.2.3.4", sco_id="i1"),
            _sco("email-addr", "id2@example.com", sco_id="e2"),
        ]
        _process(harness, results, ranker=ranker)

        log = harness.log
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
        harness = _permissive_run()
        fired = []
        _register_recording_callback(harness, "email-addr", fired)
        _register_recording_callback(harness, "ipv4-addr", fired)

        # Infrastructure first in input; Identity must win due to higher weight
        results = [
            _sco("ipv4-addr", "infra-first"),  # Infrastructure weight=2.0 → score 2.0
            _sco("email-addr", "identity-last"),  # Identity weight=5.0 → score 5.0
        ]
        _process(harness, results, ranker=ranker)
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
        harness = _permissive_run()
        fired = []
        _register_recording_callback(harness, "email-addr", fired)
        _register_recording_callback(harness, "ipv4-addr", fired)

        # When all slots are FILLED every score is 0.0 → stable sort preserves input order
        results = [
            _sco("ipv4-addr", "first"),
            _sco("email-addr", "second"),
        ]
        _process(harness, results, ranker=ranker)
        assert fired[0] == "first"
        assert fired[1] == "second"

    def test_default_deferred_state_preserves_input_order(self, tmp_path):
        """INT5 variant: default_deferred_state (fresh workspace) → all DEFERRED → input order."""
        # Fresh workspace: load_dossier_state returns None → default_deferred_state used
        wm = _make_workspace(tmp_path)
        pre_dossier = load_dossier_state(wm) or default_deferred_state()

        ranker = make_dossier_pivot_ranker(pre_dossier)
        harness = _permissive_run()
        fired = []
        _register_recording_callback(harness, "email-addr", fired)
        _register_recording_callback(harness, "ipv4-addr", fired)

        results = [
            _sco("ipv4-addr", "first"),
            _sco("email-addr", "second"),
        ]
        _process(harness, results, ranker=ranker)
        # All DEFERRED → all scores 0.0 → input order preserved
        assert fired[0] == "first"
        assert fired[1] == "second"
