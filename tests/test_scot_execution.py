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
    validate_scot_approval,
)
from adversary_pursuit.integrations.scot_publication import (
    ScotPublicationItem,
    ScotPublicationManifest,
    ScotPublishedConnection,
    ScotWriteOperation,
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


class _CountingStream(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.yielded = 0
        self.closed = False

    def __iter__(self):
        for chunk in self.chunks:
            self.yielded += 1
            yield chunk

    def close(self) -> None:
        self.closed = True


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


def test_scot_publisher_stops_before_oversized_response_is_fully_buffered():
    stream = _CountingStream([b"x" * 700, b"y" * 700, b"z" * 700])
    operation = ScotWriteOperation(
        operation_id="read-test",
        phase="readback",
        method="GET",
        path_template="/event/42",
        expected_status=(200,),
        description="Read a bounded test response.",
    )

    with ScotRestPublisher(
        "https://scot.test/api/v1",
        "secret",
        max_response_bytes=1_000,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, stream=stream)
        ),
    ) as publisher:
        with pytest.raises(RuntimeError, match="size limit"):
            publisher._request(operation, "/event/42", None)

    assert stream.yielded == 2
    assert stream.closed is True


def test_scot_publisher_rejects_compressed_response_before_expansion():
    stream = _CountingStream([b"compressed-body-must-not-be-read"])
    operation = ScotWriteOperation(
        operation_id="read-compressed-test",
        phase="readback",
        method="GET",
        path_template="/event/42",
        expected_status=(200,),
        description="Reject an encoded test response.",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Accept-Encoding"] == "identity"
        return httpx.Response(
            200,
            headers={"content-encoding": "gzip"},
            stream=stream,
        )

    with ScotRestPublisher(
        "https://scot.test/api/v1",
        "secret",
        max_response_bytes=1_000,
        transport=httpx.MockTransport(handler),
    ) as publisher:
        with pytest.raises(RuntimeError, match="size limit"):
            publisher._request(operation, "/event/42", None)

    assert stream.yielded == 0
    assert stream.closed is True


def test_scot_link_operations_are_unique_for_distinct_connection_assertions():
    event = ScotPublicationItem(
        client_ref="scot-event:test",
        object_type="event",
        payload={"subject": "Pivotglass hunt: case", "status": "open", "tags": []},
        provenance_refs=("observation-test",),
    )
    source = ScotPublicationItem(
        client_ref="scot-entity:source",
        object_type="entity",
        parent_client_ref=event.client_ref,
        payload={"value": "source.test", "type": "domain-name", "tags": []},
        provenance_refs=("observation-source",),
    )
    target = ScotPublicationItem(
        client_ref="scot-entity:target",
        object_type="entity",
        parent_client_ref=event.client_ref,
        payload={"value": "198.51.100.42", "type": "ipv4-addr", "tags": []},
        provenance_refs=("observation-target",),
    )
    connections = (
        ScotPublishedConnection(
            source_client_ref=source.client_ref,
            target_client_ref=target.client_ref,
            relationship="resolves-to",
            truth_kind="observed",
            provenance_refs=("observation-dns",),
            rationale="A passive-DNS source reported the resolution.",
        ),
        ScotPublishedConnection(
            source_client_ref=source.client_ref,
            target_client_ref=target.client_ref,
            relationship="resolves-to",
            truth_kind="inferred",
            provenance_refs=("assertion-review",),
            rationale="An analyst inferred continuity across the time gap.",
        ),
    )
    manifest = ScotPublicationManifest(
        publication_id="scot-publication-links",
        workspace="case",
        source_snapshot_sha256="1" * 64,
        items=(event, source, target),
        connections=connections,
        digest_sha256="2" * 64,
    )

    plan = compile_scot_write_plan(manifest, owner="analyst")
    links = [operation for operation in plan.operations if operation.path_template == "/link/"]
    readbacks = [
        operation
        for operation in plan.operations
        if operation.phase == "readback" and operation.path_template.startswith("/link/")
    ]

    assert len(links) == 2
    assert len({operation.operation_id for operation in links}) == 2
    assert len(readbacks) == 2
    assert {operation.depends_on[0] for operation in readbacks} == {
        operation.operation_id for operation in links
    }


def test_scot_plan_rejects_duplicate_operation_identity_before_execution():
    plan = _plan()
    duplicate = plan.model_copy(update={"operations": (plan.operations[0], plan.operations[0])})

    with pytest.raises(ValueError, match="duplicate operation IDs"):
        approve_scot_publication(
            duplicate,
            approved_by="analyst",
            confirmation=scot_confirmation(duplicate),
        )

    approval = approve_scot_publication(
        plan,
        approved_by="analyst",
        confirmation=scot_confirmation(plan),
    )

    with pytest.raises(ValueError, match="duplicate operation IDs"):
        validate_scot_approval(duplicate, approval)


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
