"""Tests for dossier/slot_inference.py — read-only inference of slot fill state.

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
"""

from __future__ import annotations

from adversary_pursuit.dossier.slot_inference import infer_dossier_state
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

    def test_timing_slot_marked_deferred_in_m1(self):
        """Timing (slot 4) must be DEFERRED in M-1 regardless of workspace content."""
        state = self._state_with_all_evidence()
        assert state.slots[DossierSlotName.TIMING].status == SlotStatus.DEFERRED

    def test_targeting_slot_marked_deferred_in_m1(self):
        """Targeting (slot 5) must be DEFERRED in M-1 regardless of workspace content."""
        state = self._state_with_all_evidence()
        assert state.slots[DossierSlotName.TARGETING].status == SlotStatus.DEFERRED

    def test_capability_slot_marked_deferred_in_m1(self):
        """Capability (slot 6) must be DEFERRED in M-1 regardless of workspace content."""
        state = self._state_with_all_evidence()
        assert state.slots[DossierSlotName.CAPABILITY].status == SlotStatus.DEFERRED

    def test_motivation_slot_marked_deferred_in_m1(self):
        """Motivation (slot 7) must be DEFERRED in M-1 regardless of workspace content."""
        state = self._state_with_all_evidence()
        assert state.slots[DossierSlotName.MOTIVATION].status == SlotStatus.DEFERRED

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
