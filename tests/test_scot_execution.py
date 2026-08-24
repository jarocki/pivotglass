"""Approval, execution, and reconciliation contracts for SCOT4 publication."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.integrations.scot_execution import (
    ScotPublicationJournal,
    ScotRestPublisher,
    approve_scot_publication,
    execute_scot_publication,
    scot_confirmation,
)
from adversary_pursuit.integrations.scot_publication import (
    ScotPublicationItem,
    ScotPublicationManifest,
    compile_scot_write_plan,
)


def _plan():
    manifest = ScotPublicationManifest(
        publication_id="scot-publication-test",
        workspace="case",
        source_snapshot_sha256="1" * 64,
        items=(
            ScotPublicationItem(
                client_ref="scot-event:test",
                object_type="event",
                payload={
                    "subject": "Pivotglass hunt: case",
                    "status": "open",
                    "tags": [],
                },
                provenance_refs=("observation-test",),
            ),
        ),
        connections=(),
        digest_sha256="2" * 64,
    )
    return compile_scot_write_plan(manifest, owner="analyst")


def test_scot_publication_requires_exact_short_lived_approval_and_reconciles():
    plan = _plan()
    now = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
    approval = approve_scot_publication(
        plan,
        approved_by="reviewer@example.test",
        confirmation=scot_confirmation(plan),
        now=now,
    )
    event: dict = {}
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            event.update(json.loads(request.content))
            event["id"] = 42
            return httpx.Response(200, json=event)
        assert request.url.path == "/api/v1/event/42"
        return httpx.Response(200, json=event)

    with ScotRestPublisher(
        "https://scot.test/api/v1",
        "do-not-display",
        transport=httpx.MockTransport(handler),
    ) as publisher:
        receipt = publisher.publish(plan, approval, now=now + timedelta(minutes=1))

    assert receipt.complete is True
    assert receipt.reconciled is True
    assert receipt.approved_by == "reviewer@example.test"
    assert len(receipt.operations) == 2
    assert receipt.operations[0].remote_id == "42"
    assert receipt.operations[1].reconciled is True
    assert requests[0].headers["Authorization"] == "Bearer do-not-display"
    assert "do-not-display" not in receipt.model_dump_json()


def test_scot_publication_rejects_wrong_or_expired_approval():
    plan = _plan()
    now = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="confirmation"):
        approve_scot_publication(
            plan,
            approved_by="analyst",
            confirmation="yes",
            now=now,
        )
    approval = approve_scot_publication(
        plan,
        approved_by="analyst",
        confirmation=scot_confirmation(plan),
        now=now,
    )
    with ScotRestPublisher(
        "https://scot.test/api/v1",
        "secret",
        transport=httpx.MockTransport(lambda _request: httpx.Response(500)),
    ) as publisher:
        with pytest.raises(ValueError, match="expired"):
            publisher.publish(plan, approval, now=now + timedelta(minutes=16))


def test_scot_publication_fails_closed_when_readback_differs():
    plan = _plan()
    now = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
    approval = approve_scot_publication(
        plan,
        approved_by="analyst",
        confirmation=scot_confirmation(plan),
        now=now,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={**json.loads(request.content), "id": 42})
        return httpx.Response(
            200,
            json={
                "id": 42,
                "owner": "analyst",
                "tlp": "unset",
                "status": "open",
                "subject": "Different hunt",
                "view_count": 0,
                "message_id": "scot-publication-test",
            },
        )

    with ScotRestPublisher(
        "https://scot.test/api/v1",
        "secret",
        transport=httpx.MockTransport(handler),
    ) as publisher:
        with pytest.raises(RuntimeError, match="did not reconcile"):
            publisher.publish(plan, approval, now=now)


def test_scot_publication_rejects_public_cleartext_api():
    with pytest.raises(ValueError, match="loopback"):
        ScotRestPublisher("http://scot.example/api/v1", "secret")


def test_scot_publication_journal_blocks_replay_across_processes(tmp_path):
    plan = _plan()
    now = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
    approval = approve_scot_publication(
        plan,
        approved_by="analyst",
        confirmation=scot_confirmation(plan),
        now=now,
    )
    event: dict = {}
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            event.update(json.loads(request.content))
            event["id"] = 42
        return httpx.Response(200, json=event)

    manager = WorkspaceManager(tmp_path)
    manager.create("case")
    manager.switch("case")
    with ScotRestPublisher(
        "https://scot.test/api/v1",
        "secret",
        transport=httpx.MockTransport(handler),
    ) as publisher:
        stored = execute_scot_publication(
            plan,
            approval,
            publisher=publisher,
            journal=ScotPublicationJournal(manager),
            now=now,
        )
    assert stored["state"] == "complete"
    assert stored["receipt"]["reconciled"] is True
    assert len(requests) == 2

    restarted = WorkspaceManager(tmp_path)
    restarted.switch("case")
    journal = ScotPublicationJournal(restarted)
    assert journal.get(plan.digest_sha256)["state"] == "complete"
    with ScotRestPublisher(
        "https://scot.test/api/v1",
        "secret",
        transport=httpx.MockTransport(handler),
    ) as publisher:
        with pytest.raises(ValueError, match="already claimed"):
            execute_scot_publication(
                plan,
                approval,
                publisher=publisher,
                journal=journal,
                now=now,
            )
    assert len(requests) == 2


def test_scot_publication_journal_blocks_uncertain_retry(tmp_path):
    plan = _plan()
    now = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
    approval = approve_scot_publication(
        plan,
        approved_by="analyst",
        confirmation=scot_confirmation(plan),
        now=now,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={**json.loads(request.content), "id": 42})
        return httpx.Response(200, json={"id": 42, "subject": "does not match"})

    manager = WorkspaceManager(tmp_path)
    manager.create("case")
    manager.switch("case")
    journal = ScotPublicationJournal(manager)
    with ScotRestPublisher(
        "https://scot.test/api/v1",
        "secret",
        transport=httpx.MockTransport(handler),
    ) as publisher:
        with pytest.raises(RuntimeError, match="did not reconcile"):
            execute_scot_publication(
                plan,
                approval,
                publisher=publisher,
                journal=journal,
                now=now,
            )
    assert journal.get(plan.digest_sha256)["state"] == "outcome_uncertain"
    assert journal.get(plan.digest_sha256)["error_summary"] == "RuntimeError"

    with ScotRestPublisher(
        "https://scot.test/api/v1",
        "secret",
        transport=httpx.MockTransport(handler),
    ) as publisher:
        with pytest.raises(ValueError, match="outcome_uncertain"):
            execute_scot_publication(
                plan,
                approval,
                publisher=publisher,
                journal=journal,
                now=now,
            )
