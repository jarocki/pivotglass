"""Tests for the shared investigation lifecycle authority."""

from adversary_pursuit.core.investigation import (
    ContentClass,
    EventClass,
    InvestigationStore,
    LifecycleState,
)


def test_event_cursor_is_stable_and_resumable():
    store = InvestigationStore()
    record = store.create("198.51.100.10", "ipv4-addr")
    first = store.append(
        record.investigation_id,
        event_class=EventClass.SYSTEM,
        severity="info",
        lifecycle=LifecycleState.PLANNED,
        content_class=ContentClass.SYSTEM,
    )
    store.append(
        record.investigation_id,
        event_class=EventClass.SYSTEM,
        severity="info",
        lifecycle=LifecycleState.RUNNING,
        content_class=ContentClass.SYSTEM,
    )

    resumed = store.snapshot(record.investigation_id, cursor=1)

    assert first.event_id.endswith(":1")
    assert resumed["cursor"] == 2
    assert [event["sequence"] for event in resumed["events"]] == [2]


def test_probe_terminal_state_does_not_finish_investigation():
    store = InvestigationStore()
    record = store.create("suspect.test", "domain-name")
    store.transition(record.investigation_id, LifecycleState.RUNNING)
    store.append(
        record.investigation_id,
        event_class=EventClass.DISCOVERY,
        severity="info",
        lifecycle=LifecycleState.SUCCEEDED,
        content_class=ContentClass.EVIDENCE,
    )

    assert store.snapshot(record.investigation_id)["lifecycle"] == "running"
    assert store.active_count() == 1

    store.transition(record.investigation_id, LifecycleState.SUCCEEDED)
    assert store.active_count() == 0


def test_cancellation_is_acknowledged_only_while_active():
    store = InvestigationStore()
    record = store.create("suspect.test", "domain-name")
    store.transition(record.investigation_id, LifecycleState.RUNNING)

    assert store.request_cancel(record.investigation_id) is True
    assert store.cancellation_requested(record.investigation_id) is True

    store.transition(record.investigation_id, LifecycleState.CANCELLED)
    assert store.request_cancel(record.investigation_id) is False


def test_alert_acknowledgement_preserves_attention_history():
    store = InvestigationStore()
    record = store.create("suspect.test", "domain-name")
    alert = store.append(
        record.investigation_id,
        event_class=EventClass.SOURCE_FAULT,
        severity="warning",
        lifecycle=LifecycleState.FAILED,
        content_class=ContentClass.SYSTEM,
        reason="provider unavailable",
    )

    assert store.alerts()[0]["acknowledged"] is False
    acknowledged = store.acknowledge_alert(alert.event_id)

    assert acknowledged["acknowledged"] is True
    assert len(store.alerts()) == 1
    assert store.alerts()[0]["reason"] == "provider unavailable"
