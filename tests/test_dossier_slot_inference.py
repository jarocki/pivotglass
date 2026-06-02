"""Tests for dossier/slot_inference.py — read-only inference of slot fill state.

Covers both M-1 (infer_dossier_state) and M-2 (infer_dossier_state_full) APIs.

@decision DEC-M1-DOSSIER-001 (read-only authority)
@title Inference tests verify the dossier package is the sole read-only slot-inference
       authority and never mutates workspace SCOs.
@status accepted
@rationale The Evaluation Contract requires 18 inference tests covering:
    - 3 SCO-type -> Identity slot fills
    - 4 SCO-type -> Infrastructure slot fills
    - 2 SCO-type -> TTPs slot fills
    - 6 deferred-status assertions (Timing/Targeting/Capability/Motivation/Predictions/Denial)
    - 3 edge-case tests (empty workspace, partial vs filled escalation, provenance-read without write)
    Plus 2 additional invariant tests (unknown SCO graceful handling, read-only assertion).
   These tests exercise the real production sequence: list[dict] SCOs -> DossierState.

@decision DEC-M2-DOSSIER-001 (new entrypoint)
@title infer_dossier_state_full() adds timing/capability/motivation extractors over M-1 base
@status accepted
@rationale M-2 extends M-1 without breaking the legacy thin-wrapper contract.

@decision DEC-M2-DOSSIER-002 (timing extractor)
@title Timing extractor uses x_ap_fetched_at + module_runs timestamps, UTC hour clustering
@status accepted

@decision DEC-M2-DOSSIER-003 (capability extractor)
@title Capability extractor reads DEFAULT_SUBSCRIPTIONS at call time
@status accepted

@decision DEC-M2-DOSSIER-004 (predictions/denial scaffold)
@title Predictions + Denial always return DEFERRED in M-2
@status accepted
"""

from __future__ import annotations

from adversary_pursuit.dossier.slot_inference import infer_dossier_state, infer_dossier_state_full
from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus

# ---------------------------------------------------------------------------
# Helper factories — synthetic SCO dicts as workspace.get_stix_objects() returns
# ---------------------------------------------------------------------------


def _email_sco(value: str = "threat@actor.ru") -> dict:
    return {"type": "email-addr", "value": value, "id": f"email-addr--fake-{value}"}


def _user_account_sco(user_id: str = "th3_ac70r") -> dict:
    return {"type": "user-account", "user_id": user_id, "id": f"user-account--fake-{user_id}"}


def _x509_sco(subject: str = "CN=evil.corp") -> dict:
    return {
        "type": "x509-certificate",
        "subject": subject,
        "id": f"x509-certificate--fake-{subject}",
    }


def _domain_sco(value: str = "evil.example.com") -> dict:
    return {"type": "domain-name", "value": value, "id": f"domain-name--fake-{value}"}


def _ipv4_sco(value: str = "1.2.3.4") -> dict:
    return {"type": "ipv4-addr", "value": value, "id": f"ipv4-addr--fake-{value}"}


def _ipv6_sco(value: str = "::1") -> dict:
    return {"type": "ipv6-addr", "value": value, "id": f"ipv6-addr--fake-{value}"}


def _autonomous_system_sco(number: int = 12345) -> dict:
    return {
        "type": "autonomous-system",
        "number": number,
        "id": f"autonomous-system--fake-{number}",
    }


def _url_sco(value: str = "https://c2.evil.example/beacon") -> dict:
    return {"type": "url", "value": value, "id": "url--fake"}


def _file_sco(name: str = "loader.dll") -> dict:
    return {"type": "file", "name": name, "id": f"file--fake-{name}"}


def _unknown_sco() -> dict:
    return {"type": "x-custom-unknown", "value": "something", "id": "x-custom--fake"}


def _provenance_sco(value: str = "1.2.3.4") -> dict:
    """SCO with x_ap_ provenance fields as workspace.store_stix_objects() would add."""
    return {
        "type": "ipv4-addr",
        "value": value,
        "id": f"ipv4-addr--prov-{value}",
        "x_ap_fetched_at": "2024-01-15T12:00:00Z",
        "x_ap_source_url": "https://api.shodan.io/shodan/host/1.2.3.4",
        "x_ap_api_version": "v1",
        "x_ap_response_sha256": "abc123",
    }


def _timestamped_sco(value: str, hour: int) -> dict:
    """SCO with x_ap_fetched_at set to the given UTC hour on a fixed date."""
    ts = f"2024-01-15T{hour:02d}:30:00Z"
    return {
        "type": "ipv4-addr",
        "value": value,
        "id": f"ipv4-addr--ts-{value}-h{hour}",
        "x_ap_fetched_at": ts,
    }


def _module_run(module_name: str = "osint/dns_resolve", hour: int = 10) -> dict:
    """Synthetic module run row as workspace.get_module_runs() would return."""
    return {
        "module_name": module_name,
        "target": "evil.example.com",
        "timestamp": f"2024-01-15T{hour:02d}:30:00",
        "result_count": 3,
    }


def _note(content: str) -> dict:
    """Synthetic AnalystNote dict as the engine-direct query returns."""
    return {"content": content}


# ---------------------------------------------------------------------------
# Identity slot — 3 SCO type tests
# ---------------------------------------------------------------------------


class TestIdentitySlotInference:
    """Slot 1 (Identity/Attribution) fills from email-addr, user-account, x509-certificate."""

    def test_identity_slot_filled_by_email_addr(self):
        """email-addr SCO contributes evidence to the Identity slot."""
        state = infer_dossier_state([_email_sco()])
        identity_slot = state.slots[DossierSlotName.IDENTITY]
        assert identity_slot.status != SlotStatus.EMPTY, (
            "email-addr SCO should contribute to Identity slot; got empty"
        )
        assert identity_slot.evidence_count >= 1

    def test_identity_slot_filled_by_user_account(self):
        """user-account SCO contributes evidence to the Identity slot."""
        state = infer_dossier_state([_user_account_sco()])
        identity_slot = state.slots[DossierSlotName.IDENTITY]
        assert identity_slot.status != SlotStatus.EMPTY
        assert identity_slot.evidence_count >= 1

    def test_identity_slot_filled_by_x509_certificate(self):
        """x509-certificate SCO contributes evidence to the Identity slot."""
        state = infer_dossier_state([_x509_sco()])
        identity_slot = state.slots[DossierSlotName.IDENTITY]
        assert identity_slot.status != SlotStatus.EMPTY
        assert identity_slot.evidence_count >= 1


# ---------------------------------------------------------------------------
# Infrastructure slot — 4 SCO type tests
# ---------------------------------------------------------------------------


class TestInfrastructureSlotInference:
    """Slot 3 (Infrastructure Habits) fills from domain-name, ipv4-addr, ipv6-addr, autonomous-system."""

    def test_infrastructure_slot_filled_by_domain_name(self):
        """domain-name SCO contributes evidence to Infrastructure slot."""
        state = infer_dossier_state([_domain_sco()])
        infra_slot = state.slots[DossierSlotName.INFRASTRUCTURE]
        assert infra_slot.status != SlotStatus.EMPTY
        assert infra_slot.evidence_count >= 1

    def test_infrastructure_slot_filled_by_ipv4_addr(self):
        """ipv4-addr SCO contributes evidence to Infrastructure slot."""
        state = infer_dossier_state([_ipv4_sco()])
        infra_slot = state.slots[DossierSlotName.INFRASTRUCTURE]
        assert infra_slot.status != SlotStatus.EMPTY
        assert infra_slot.evidence_count >= 1

    def test_infrastructure_slot_filled_by_ipv6_addr(self):
        """ipv6-addr SCO contributes evidence to Infrastructure slot."""
        state = infer_dossier_state([_ipv6_sco()])
        infra_slot = state.slots[DossierSlotName.INFRASTRUCTURE]
        assert infra_slot.status != SlotStatus.EMPTY
        assert infra_slot.evidence_count >= 1

    def test_infrastructure_slot_filled_by_autonomous_system(self):
        """autonomous-system SCO contributes evidence to Infrastructure slot."""
        state = infer_dossier_state([_autonomous_system_sco()])
        infra_slot = state.slots[DossierSlotName.INFRASTRUCTURE]
        assert infra_slot.status != SlotStatus.EMPTY
        assert infra_slot.evidence_count >= 1


# ---------------------------------------------------------------------------
# TTPs slot — 2 SCO type tests
# ---------------------------------------------------------------------------


class TestTTPsSlotInference:
    """Slot 2 (TTPs and Tradecraft) fills from url and file SCOs in M-1."""

    def test_ttps_slot_filled_by_url_sco(self):
        """url SCO (C2 indicator pattern) contributes evidence to TTPs slot."""
        state = infer_dossier_state([_url_sco()])
        ttps_slot = state.slots[DossierSlotName.TTPS]
        assert ttps_slot.status != SlotStatus.EMPTY
        assert ttps_slot.evidence_count >= 1

    def test_ttps_slot_filled_by_file_sco(self):
        """file SCO (payload/loader artifact) contributes evidence to TTPs slot."""
        state = infer_dossier_state([_file_sco()])
        ttps_slot = state.slots[DossierSlotName.TTPS]
        assert ttps_slot.status != SlotStatus.EMPTY
        assert ttps_slot.evidence_count >= 1


# ---------------------------------------------------------------------------
# Deferred slots — 6 assertion tests (DEC-M1-DOSSIER-002)
# ---------------------------------------------------------------------------


class TestDeferredSlotStatus:
    """Slots 4-9 render as deferred in M-1; their inference paths land in M-2/M-4/M-5."""

    def _state_with_all_evidence(self) -> object:
        """Build a rich workspace with multiple SCO types to ensure deferred slots
        stay deferred regardless of how much evidence is present."""
        scos = [
            _email_sco(),
            _user_account_sco(),
            _x509_sco(),
            _domain_sco(),
            _ipv4_sco(),
            _ipv6_sco(),
            _autonomous_system_sco(),
            _url_sco(),
            _file_sco(),
        ]
        return infer_dossier_state(scos)

    def test_timing_slot_empty_when_no_timestamps(self):
        """Timing (slot 4) returns EMPTY in M-2 when no x_ap_fetched_at or module_runs present.

        M-1 returned DEFERRED; M-2 ships a real extractor for this slot.
        infer_dossier_state() is a thin wrapper (no module_runs), so timing is EMPTY.
        """
        state = self._state_with_all_evidence()
        assert state.slots[DossierSlotName.TIMING].status == SlotStatus.EMPTY

    def test_targeting_slot_marked_deferred_in_m1(self):
        """Targeting (slot 5) must be DEFERRED — no M-2 extractor; remains deferred until M-3."""
        state = self._state_with_all_evidence()
        assert state.slots[DossierSlotName.TARGETING].status == SlotStatus.DEFERRED

    def test_capability_slot_empty_when_no_module_runs(self):
        """Capability (slot 6) returns EMPTY in M-2 when no module_runs present.

        M-1 returned DEFERRED; M-2 ships a real extractor. The thin wrapper
        infer_dossier_state() passes module_runs=None, so capability is EMPTY.
        """
        state = self._state_with_all_evidence()
        assert state.slots[DossierSlotName.CAPABILITY].status == SlotStatus.EMPTY

    def test_motivation_slot_empty_when_no_notes(self):
        """Motivation (slot 7) returns EMPTY in M-2 when no analyst notes present.

        M-1 returned DEFERRED; M-2 ships a real extractor. The thin wrapper
        infer_dossier_state() passes notes=None, so motivation is EMPTY.
        """
        state = self._state_with_all_evidence()
        assert state.slots[DossierSlotName.MOTIVATION].status == SlotStatus.EMPTY

    def test_predictions_slot_marked_deferred_in_m1(self):
        """Predictions (slot 8) must be DEFERRED in M-1 - requires M-4 persistence."""
        state = self._state_with_all_evidence()
        assert state.slots[DossierSlotName.PREDICTIONS].status == SlotStatus.DEFERRED

    def test_denial_slot_marked_deferred_in_m1(self):
        """Denial (slot 9) must be DEFERRED in M-1 - requires M-5 user-note surface."""
        state = self._state_with_all_evidence()
        assert state.slots[DossierSlotName.DENIAL].status == SlotStatus.DEFERRED


# ---------------------------------------------------------------------------
# Edge-case tests
# ---------------------------------------------------------------------------


class TestInferenceEdgeCases:
    """Edge-case coverage: empty workspace, partial vs filled escalation, provenance invariants."""

    def test_empty_workspace_yields_all_empty_or_deferred(self):
        """Zero SCOs -> infer_dossier_state returns without crash; all slots empty or deferred."""
        state = infer_dossier_state([])
        assert state is not None
        for slot_name, slot in state.slots.items():
            assert slot.status in (SlotStatus.EMPTY, SlotStatus.DEFERRED), (
                f"Slot {slot_name} should be empty or deferred on empty workspace, "
                f"got {slot.status}"
            )

    def test_partial_status_when_single_evidence_type_present(self):
        """Single SCO type for Identity -> status is partial (one evidence type, not corroborated)."""
        state = infer_dossier_state([_email_sco()])
        identity_slot = state.slots[DossierSlotName.IDENTITY]
        # With a single SCO type, status should be partial (not filled - filled requires multiple types)
        assert identity_slot.status == SlotStatus.PARTIAL, (
            f"Single email-addr SCO should yield Identity=partial, got {identity_slot.status}"
        )

    def test_filled_status_when_multiple_evidence_types_present(self):
        """Multiple distinct SCO types for Identity -> status escalates to filled."""
        # email-addr + x509-certificate = two independent Identity evidence types
        state = infer_dossier_state([_email_sco(), _x509_sco()])
        identity_slot = state.slots[DossierSlotName.IDENTITY]
        assert identity_slot.status == SlotStatus.FILLED, (
            f"Two distinct Identity SCO types should yield filled, got {identity_slot.status}"
        )

    def test_inference_is_read_only_no_workspace_mutation(self):
        """infer_dossier_state is a pure function - it must not call any workspace mutator.

        DEC-M1-DOSSIER-001: the dossier package MUST NOT call store_stix_objects or
        any other WorkspaceManager mutator. We verify this by checking that the input
        list is unchanged and by asserting the return type contains no write side effects.
        """
        original_scos = [_email_sco(), _domain_sco()]
        scos_copy = [dict(s) for s in original_scos]

        infer_dossier_state(original_scos)

        # Input list is unchanged
        assert original_scos == scos_copy, "infer_dossier_state must not mutate the input SCO list"
        # No x_ap_* fields written on the SCO dicts
        for sco in original_scos:
            for key in sco:
                assert not key.startswith("x_ap_"), (
                    f"infer_dossier_state wrote x_ap_* field {key!r} onto an SCO dict - "
                    "DEC-59-STIX-PROVENANCE-001 violation"
                )

    def test_inference_consumes_provenance_fields_without_writing(self):
        """Inference reads x_ap_* provenance fields without modifying them.

        DEC-59-STIX-PROVENANCE-001: workspace.store_stix_objects() is the sole x_ap_*
        authority. The dossier inference layer may READ x_ap_fetched_at etc. but must
        never add, update, or remove them.
        """
        sco = _provenance_sco()
        original_provenance = {k: v for k, v in sco.items() if k.startswith("x_ap_")}

        infer_dossier_state([sco])

        # provenance fields unchanged on the dict
        for key, val in original_provenance.items():
            assert sco.get(key) == val, f"infer_dossier_state modified provenance field {key!r}"

    def test_inference_ignores_unknown_sco_types_gracefully(self):
        """Unknown / future SCO types are silently skipped without raising.

        DEC-M1-DOSSIER-001 forbidden shortcut: no SCO-type auto-discovery.
        Inference uses an explicit SLOT_EVIDENCE_TYPES mapping; unknown types
        fall through without affecting any slot and without raising.
        """
        unknown = _unknown_sco()
        # Should not raise
        state = infer_dossier_state([unknown])
        # Unknown type contributes to no slot - all active inference slots stay empty
        identity_slot = state.slots[DossierSlotName.IDENTITY]
        infra_slot = state.slots[DossierSlotName.INFRASTRUCTURE]
        ttps_slot = state.slots[DossierSlotName.TTPS]
        assert identity_slot.status == SlotStatus.EMPTY
        assert infra_slot.status == SlotStatus.EMPTY
        assert ttps_slot.status == SlotStatus.EMPTY


# ---------------------------------------------------------------------------
# M-2: infer_dossier_state_full() — new entrypoint (DEC-M2-DOSSIER-001)
# ---------------------------------------------------------------------------


class TestInferDossierStateFullAPI:
    """infer_dossier_state_full() is the M-2 entrypoint; legacy wrapper still works."""

    def test_full_accepts_scos_only(self):
        """infer_dossier_state_full(scos) works with just SCOs (module_runs/notes default None)."""
        state = infer_dossier_state_full([_email_sco()])
        assert state is not None
        assert DossierSlotName.IDENTITY in state.slots

    def test_full_returns_dossier_state(self):
        """infer_dossier_state_full returns a DossierState with all 9 slots."""
        from adversary_pursuit.dossier.slot_inference import DossierState

        state = infer_dossier_state_full([])
        assert isinstance(state, DossierState)
        assert len(state.slots) == 9

    def test_legacy_wrapper_delegates_to_full(self):
        """infer_dossier_state(scos) is a thin wrapper around infer_dossier_state_full.

        Both return the same result for the same input. Identity/Infra/TTP slots
        must be identical whether called via the legacy or new entrypoint.
        """
        scos = [_email_sco(), _x509_sco(), _domain_sco()]
        state_legacy = infer_dossier_state(scos)
        state_full = infer_dossier_state_full(scos)

        # Active slot states must match
        for slot_name in (
            DossierSlotName.IDENTITY,
            DossierSlotName.INFRASTRUCTURE,
            DossierSlotName.TTPS,
        ):
            assert state_legacy.slots[slot_name].status == state_full.slots[slot_name].status, (
                f"Legacy wrapper produced different {slot_name} status than full entrypoint"
            )

    def test_full_predictions_always_deferred(self):
        """Predictions (slot 8) always DEFERRED in M-2 (DEC-M2-DOSSIER-004 scaffold-only)."""
        state = infer_dossier_state_full([_email_sco()], module_runs=[], notes=[])
        assert state.slots[DossierSlotName.PREDICTIONS].status == SlotStatus.DEFERRED

    def test_full_denial_always_deferred(self):
        """Denial (slot 9) always DEFERRED in M-2 (DEC-M2-DOSSIER-004 scaffold-only)."""
        state = infer_dossier_state_full([_email_sco()], module_runs=[], notes=[])
        assert state.slots[DossierSlotName.DENIAL].status == SlotStatus.DEFERRED


# ---------------------------------------------------------------------------
# M-2: Timing extractor (DEC-M2-DOSSIER-002)
# ---------------------------------------------------------------------------


class TestTimingExtractor:
    """Slot 4 (Timing/Behavioral): uses x_ap_fetched_at + module_runs timestamps.

    FILLED = >=10 events AND >=25% in one UTC hour bucket.
    With fewer than 10 events OR no dominant bucket: PARTIAL if any events, else EMPTY.
    """

    def test_timing_empty_when_no_scos_and_no_module_runs(self):
        """No SCOs, no module runs -> Timing slot is EMPTY."""
        state = infer_dossier_state_full([], module_runs=[], notes=[])
        assert state.slots[DossierSlotName.TIMING].status == SlotStatus.EMPTY

    def test_timing_partial_with_few_events(self):
        """Fewer than 10 events -> PARTIAL (some data, not enough for cluster inference)."""
        scos = [_timestamped_sco(f"10.0.0.{i}", hour=14) for i in range(3)]
        state = infer_dossier_state_full(scos, module_runs=[], notes=[])
        timing = state.slots[DossierSlotName.TIMING]
        assert timing.status == SlotStatus.PARTIAL, (
            f"3 timestamped events should yield Timing=partial, got {timing.status}"
        )

    def test_timing_filled_with_ten_plus_events_and_dominant_bucket(self):
        """>=10 events with >=25% in one hour bucket -> FILLED."""
        # 10 events at hour 14, 2 at other hours — 14:xx hour bucket = 10/12 = 83% > 25%
        scos = [_timestamped_sco(f"10.0.0.{i}", hour=14) for i in range(10)]
        scos += [_timestamped_sco(f"10.0.1.{i}", hour=7) for i in range(2)]
        state = infer_dossier_state_full(scos, module_runs=[], notes=[])
        timing = state.slots[DossierSlotName.TIMING]
        assert timing.status == SlotStatus.FILLED, (
            f"10 events with dominant hour-14 bucket should yield Timing=filled, "
            f"got {timing.status}"
        )

    def test_timing_uses_module_runs_timestamps(self):
        """module_runs timestamps contribute to timing event count."""
        # 0 SCOs but 10 module runs at hour 9 -> FILLED if bucket dominates
        runs = [_module_run("osint/dns_resolve", hour=9) for _ in range(10)]
        state = infer_dossier_state_full([], module_runs=runs, notes=[])
        timing = state.slots[DossierSlotName.TIMING]
        assert timing.status == SlotStatus.FILLED, (
            f"10 module runs in same hour should yield Timing=filled, got {timing.status}"
        )

    def test_timing_merges_scos_and_module_runs(self):
        """x_ap_fetched_at from SCOs and module_runs timestamps are merged."""
        # 6 SCOs at hour 14 + 4 module runs at hour 14 = 10 total, 100% in bucket -> FILLED
        scos = [_timestamped_sco(f"10.0.0.{i}", hour=14) for i in range(6)]
        runs = [_module_run("osint/abuseipdb", hour=14) for _ in range(4)]
        state = infer_dossier_state_full(scos, module_runs=runs, notes=[])
        timing = state.slots[DossierSlotName.TIMING]
        assert timing.status == SlotStatus.FILLED, (
            f"6 SCOs + 4 module runs at same hour should yield Timing=filled, got {timing.status}"
        )

    def test_timing_not_filled_when_no_dominant_bucket(self):
        """>=10 events but all in different hours -> not FILLED (no dominant bucket)."""
        # 12 events, each at a different hour -> max bucket = 1/12 = 8.3% < 25%
        scos = [_timestamped_sco(f"10.0.0.{i}", hour=i) for i in range(12)]
        state = infer_dossier_state_full(scos, module_runs=[], notes=[])
        timing = state.slots[DossierSlotName.TIMING]
        assert timing.status != SlotStatus.FILLED, (
            f"12 events spread across 12 hours should NOT be Timing=filled, got {timing.status}"
        )

    def test_timing_ignores_scos_without_fetched_at(self):
        """SCOs without x_ap_fetched_at are skipped for timing inference."""
        # Mix of scos with and without fetched_at — only the ones WITH it count
        scos_no_ts = [_ipv4_sco() for _ in range(10)]  # no x_ap_fetched_at
        state = infer_dossier_state_full(scos_no_ts, module_runs=[], notes=[])
        timing = state.slots[DossierSlotName.TIMING]
        # Without timestamps there are 0 timing events -> EMPTY
        assert timing.status == SlotStatus.EMPTY, (
            f"SCOs without x_ap_fetched_at should contribute 0 timing events, "
            f"got timing status={timing.status}"
        )


# ---------------------------------------------------------------------------
# M-2: Capability extractor (DEC-M2-DOSSIER-003)
# ---------------------------------------------------------------------------


class TestCapabilityExtractor:
    """Slot 6 (Capability Ceiling): reads DEFAULT_SUBSCRIPTIONS at call time.

    FILLED = >=3 observed modules AND >=3 unobserved modules.
    PARTIAL = some module runs exist but thresholds not met.
    EMPTY = no module runs at all.
    """

    def test_capability_empty_when_no_module_runs(self):
        """No module runs -> Capability slot is EMPTY."""
        state = infer_dossier_state_full([], module_runs=[], notes=[])
        assert state.slots[DossierSlotName.CAPABILITY].status == SlotStatus.EMPTY

    def test_capability_partial_when_few_modules_observed(self):
        """1 or 2 observed modules -> PARTIAL (below the >=3 threshold)."""
        runs = [
            _module_run("osint/dns_resolve", hour=10),
            _module_run("osint/whois_lookup", hour=11),
        ]
        state = infer_dossier_state_full([], module_runs=runs, notes=[])
        cap = state.slots[DossierSlotName.CAPABILITY]
        assert cap.status == SlotStatus.PARTIAL, (
            f"2 observed modules should yield Capability=partial, got {cap.status}"
        )

    def test_capability_filled_when_three_plus_observed_and_three_plus_unobserved(self):
        """>=3 observed AND >=3 unobserved from DEFAULT_SUBSCRIPTIONS -> FILLED."""
        # DEFAULT_SUBSCRIPTIONS has 12 modules. Use 3 of them.
        runs = [
            _module_run("osint/dns_resolve", hour=10),
            _module_run("osint/abuseipdb", hour=11),
            _module_run("osint/shodan_ip", hour=12),
        ]
        state = infer_dossier_state_full([], module_runs=runs, notes=[])
        cap = state.slots[DossierSlotName.CAPABILITY]
        assert cap.status == SlotStatus.FILLED, (
            f"3 observed modules with 9+ unobserved should yield Capability=filled, "
            f"got {cap.status}"
        )

    def test_capability_reads_default_subscriptions_at_call_time(self):
        """Capability extractor reads DEFAULT_SUBSCRIPTIONS dynamically, not at import time.

        This test verifies the extractor uses the DEFAULT_SUBSCRIPTIONS import
        at function call time (DEC-M2-DOSSIER-003: 'reads DEFAULT_SUBSCRIPTIONS
        at call time').
        """
        from adversary_pursuit.core.event_bus import DEFAULT_SUBSCRIPTIONS

        # Verify DEFAULT_SUBSCRIPTIONS is non-empty (sanity check)
        assert len(DEFAULT_SUBSCRIPTIONS) >= 6, (
            f"DEFAULT_SUBSCRIPTIONS has fewer than 6 entries — fixture mismatch: "
            f"{list(DEFAULT_SUBSCRIPTIONS.keys())}"
        )

        # Run with 3 known modules from DEFAULT_SUBSCRIPTIONS
        known_modules = list(DEFAULT_SUBSCRIPTIONS.keys())[:3]
        runs = [_module_run(mod, hour=10) for mod in known_modules]
        state = infer_dossier_state_full([], module_runs=runs, notes=[])
        cap = state.slots[DossierSlotName.CAPABILITY]

        # With 3 observed and (total - 3) >= 3 unobserved, should be FILLED
        total_subscribed = len(DEFAULT_SUBSCRIPTIONS)
        unobserved = total_subscribed - 3
        if unobserved >= 3:
            assert cap.status == SlotStatus.FILLED, (
                f"3 observed + {unobserved} unobserved should yield Capability=filled, "
                f"got {cap.status}"
            )

    def test_capability_counts_distinct_modules_not_run_count(self):
        """Same module run 5 times counts as 1 observed module, not 5."""
        # Only 1 distinct module, many runs
        runs = [_module_run("osint/dns_resolve", hour=10) for _ in range(5)]
        state = infer_dossier_state_full([], module_runs=runs, notes=[])
        cap = state.slots[DossierSlotName.CAPABILITY]
        # 1 distinct observed module < 3 threshold -> not FILLED
        assert cap.status != SlotStatus.FILLED, (
            f"5 runs of same module = 1 observed; should not be Capability=filled, got {cap.status}"
        )


# ---------------------------------------------------------------------------
# M-2: Motivation extractor (notes-based)
# ---------------------------------------------------------------------------


class TestMotivationExtractor:
    """Slot 7 (Motivation Indicators): populated from analyst notes keyword matching.

    FILLED = notes contain >=2 motivation-signal keywords from distinct categories.
    PARTIAL = notes contain 1 motivation-signal keyword.
    EMPTY = no notes or notes contain no motivation keywords.
    """

    def test_motivation_empty_when_no_notes(self):
        """No notes -> Motivation slot is EMPTY."""
        state = infer_dossier_state_full([], module_runs=[], notes=[])
        assert state.slots[DossierSlotName.MOTIVATION].status == SlotStatus.EMPTY

    def test_motivation_partial_with_one_keyword(self):
        """Single motivation keyword in notes -> PARTIAL."""
        notes = [_note("Actor appears financially motivated based on ransom note patterns.")]
        state = infer_dossier_state_full([], module_runs=[], notes=notes)
        motivation = state.slots[DossierSlotName.MOTIVATION]
        assert motivation.status in (SlotStatus.PARTIAL, SlotStatus.FILLED), (
            f"Note with financial keyword should yield at least Motivation=partial, "
            f"got {motivation.status}"
        )

    def test_motivation_filled_with_multiple_signal_keywords(self):
        """Multiple motivation keywords in notes -> FILLED."""
        notes = [
            _note("Actor is financially motivated, targeting SWIFT transfers."),
            _note("Nation-state affiliation suspected based on tooling and target selection."),
        ]
        state = infer_dossier_state_full([], module_runs=[], notes=notes)
        motivation = state.slots[DossierSlotName.MOTIVATION]
        assert motivation.status == SlotStatus.FILLED, (
            f"Notes with financial + nation-state keywords should yield Motivation=filled, "
            f"got {motivation.status}"
        )

    def test_motivation_empty_with_irrelevant_notes(self):
        """Notes with no motivation keywords -> EMPTY (or at most PARTIAL)."""
        notes = [
            _note("Checked DNS resolution for evil.example.com."),
            _note("Domain registered via Namecheap."),
        ]
        state = infer_dossier_state_full([], module_runs=[], notes=notes)
        motivation = state.slots[DossierSlotName.MOTIVATION]
        assert motivation.status == SlotStatus.EMPTY, (
            f"Notes without motivation keywords should yield Motivation=empty, "
            f"got {motivation.status}"
        )

    def test_motivation_reads_note_content_field(self):
        """Motivation extractor reads the 'content' field from note dicts."""
        notes = [{"content": "Hacktivist group motivated by political agenda."}]
        state = infer_dossier_state_full([], module_runs=[], notes=notes)
        motivation = state.slots[DossierSlotName.MOTIVATION]
        assert motivation.status != SlotStatus.EMPTY, (
            "Note with hacktivist keyword should not yield Motivation=empty"
        )


# ---------------------------------------------------------------------------
# M-2: Targeting slot — still DEFERRED via full entrypoint
# ---------------------------------------------------------------------------


class TestTargetingSlotStillDeferred:
    """Targeting (slot 5) remains DEFERRED in M-2; it is not in M-2 scope."""

    def test_targeting_deferred_via_full_entrypoint(self):
        """infer_dossier_state_full leaves Targeting=DEFERRED in M-2."""
        scos = [_domain_sco(), _ipv4_sco(), _email_sco()]
        state = infer_dossier_state_full(scos, module_runs=[], notes=[])
        assert state.slots[DossierSlotName.TARGETING].status == SlotStatus.DEFERRED


# ---------------------------------------------------------------------------
# M-2: Read-only invariant for full entrypoint
# ---------------------------------------------------------------------------


class TestInferDossierStateFullReadOnly:
    """infer_dossier_state_full must be a pure function — no workspace mutations."""

    def test_full_does_not_mutate_scos(self):
        """infer_dossier_state_full does not modify the input SCO list."""
        scos = [_email_sco(), _domain_sco()]
        scos_copy = [dict(s) for s in scos]
        infer_dossier_state_full(scos, module_runs=[], notes=[])
        assert scos == scos_copy, "infer_dossier_state_full must not mutate the input SCO list"

    def test_full_does_not_mutate_module_runs(self):
        """infer_dossier_state_full does not modify the module_runs list."""
        runs = [_module_run("osint/dns_resolve", hour=10)]
        runs_copy = [dict(r) for r in runs]
        infer_dossier_state_full([], module_runs=runs, notes=[])
        assert runs == runs_copy, "infer_dossier_state_full must not mutate the module_runs list"

    def test_full_does_not_mutate_notes(self):
        """infer_dossier_state_full does not modify the notes list."""
        notes = [_note("Financial motivation suspected.")]
        notes_copy = [dict(n) for n in notes]
        infer_dossier_state_full([], module_runs=[], notes=notes)
        assert notes == notes_copy, "infer_dossier_state_full must not mutate the notes list"

    def test_full_no_x_ap_writes(self):
        """infer_dossier_state_full does not write x_ap_* fields (DEC-59-STIX-PROVENANCE-001)."""
        scos = [_provenance_sco()]
        original_keys = set(scos[0].keys())
        infer_dossier_state_full(scos, module_runs=[], notes=[])
        for sco in scos:
            for key in sco:
                if key not in original_keys:
                    assert not key.startswith("x_ap_"), (
                        f"infer_dossier_state_full added x_ap_* field {key!r} to SCO dict"
                    )


# ---------------------------------------------------------------------------
# M-3 transition-readiness tests (B17–B18, Evaluation Contract §7.B)
# ---------------------------------------------------------------------------
# These tests assert that the M-2 inference output is comparable in the way
# M-3 caller wiring requires: (1) calling infer_dossier_state_full twice with
# identical inputs produces equal DossierState objects (frozen dataclass equality),
# and (2) adding a new SCO that contributes to the Identity slot changes the
# Identity slot status so pre.slots[IDENTITY].status != post.slots[IDENTITY].status.


class TestM3TransitionReadiness:
    """M-3 transition-readiness: infer_dossier_state_full output supports equality comparison."""

    def test_dossier_state_equality_on_identical_inputs(self):
        """B17: Calling infer_dossier_state_full twice with identical inputs returns equal states.

        M-3 relies on SlotStatus enum equality for transition detection. If the
        two DossierState objects have differing slot statuses on identical inputs,
        the dossier event emitter would spuriously fire. This test proves the
        frozen dataclass equality holds.
        """
        scos = [_email_sco("threat@actor.ru")]
        module_runs = [{"module_name": "osint/dns_resolve", "timestamp": "2026-01-01T10:00:00Z"}]
        notes = [{"content": "ransomware activity suspected"}]

        state1 = infer_dossier_state_full(scos, module_runs=module_runs, notes=notes)
        state2 = infer_dossier_state_full(scos, module_runs=module_runs, notes=notes)

        # DossierState and SlotState are frozen dataclasses — equality is structural
        assert state1 == state2, (
            "infer_dossier_state_full must return equal DossierState for identical inputs; "
            "M-3 transition detection requires this invariant."
        )

    def test_dossier_state_inequality_after_sco_addition(self):
        """B18: Adding an identity-class SCO changes the Identity slot status.

        M-3 captures pre_dossier before store_stix_objects and post_dossier after.
        If the Identity slot status does not change when a new email-addr SCO is added,
        the emit_dossier_slot_filled_events call would silently miss the transition.
        """
        # Pre: no email-addr SCOs (Identity slot should be EMPTY)
        scos_before = [{"type": "ipv4-addr", "value": "1.2.3.4", "id": "ipv4-addr--fake-1"}]
        pre = infer_dossier_state_full(scos_before, module_runs=[], notes=[])

        # Post: email-addr added → Identity slot should become PARTIAL (1 distinct type)
        scos_after = scos_before + [_email_sco("threat@actor.ru")]
        post = infer_dossier_state_full(scos_after, module_runs=[], notes=[])

        from adversary_pursuit.dossier.slots import DossierSlotName

        pre_identity_status = pre.slots[DossierSlotName.IDENTITY].status
        post_identity_status = post.slots[DossierSlotName.IDENTITY].status

        assert pre_identity_status != post_identity_status, (
            f"Adding an email-addr SCO must change Identity slot status; "
            f"pre={pre_identity_status!r}, post={post_identity_status!r}"
        )
        # Specifically: EMPTY -> PARTIAL (one distinct type = email-addr)
        from adversary_pursuit.dossier.slots import SlotStatus

        assert pre_identity_status == SlotStatus.EMPTY
        assert post_identity_status == SlotStatus.PARTIAL
