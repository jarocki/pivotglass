"""Security and replay-safety contracts for inbound SCOT pivot requests."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from adversary_pursuit.agent.tools import ToolContext
from adversary_pursuit.core.analytic_ledger import AnalyticLedger
from adversary_pursuit.integrations.scot_pivot_intake import (
    ScotPivotAuthenticationError,
    authenticate_scot_pivot_request,
    scot_pivot_signature,
)
from adversary_pursuit.integrations.scot_publication import validate_scot_pivot_request
from adversary_pursuit.web.server import WebCockpitService, _handler

_SECRET = "test-only-scot-pivot-secret-32-bytes-minimum"
_KEY_ID = "scot4-primary"
_NONCE = "test_nonce_1234567890"


def _body(now: datetime) -> bytes:
    request = validate_scot_pivot_request(
        workspace="default",
        scot_object_type="event",
        scot_object_id=42,
        scot_revision="7",
        indicator="198.51.100.42",
        requested_by="scot-analyst@example.test",
        requested_at=now,
        reason="Follow the event relationship.",
    )
    return json.dumps(request.model_dump(mode="json"), separators=(",", ":")).encode()


def _headers(body: bytes, now: datetime, *, signature: str | None = None) -> dict[str, str]:
    timestamp = int(now.timestamp())
    return {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
        "X-Pivotglass-Key-Id": _KEY_ID,
        "X-Pivotglass-Timestamp": str(timestamp),
        "X-Pivotglass-Nonce": _NONCE,
        "X-Pivotglass-Signature": signature
        or scot_pivot_signature(
            _SECRET,
            key_id=_KEY_ID,
            timestamp=timestamp,
            nonce=_NONCE,
            body=body,
        ),
    }


def test_scot_pivot_authentication_is_deterministic_and_secret_safe():
    now = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    body = _body(now)
    headers = _headers(body, now)

    receipt = authenticate_scot_pivot_request(
        _SECRET,
        key_id=headers["X-Pivotglass-Key-Id"],
        timestamp=headers["X-Pivotglass-Timestamp"],
        nonce=headers["X-Pivotglass-Nonce"],
        signature=headers["X-Pivotglass-Signature"],
        body=body,
        now=now,
    )

    serialized = receipt.model_dump_json()
    assert receipt.scheme == "hmac-sha256-v1"
    assert receipt.key_id == _KEY_ID
    assert receipt.body_sha256
    assert receipt.nonce_sha256
    assert _SECRET not in serialized
    assert headers["X-Pivotglass-Signature"] not in serialized
    assert _NONCE not in serialized


@pytest.mark.parametrize(
    ("signature", "signed_at"),
    [
        ("sha256=" + "0" * 64, datetime(2026, 8, 25, 12, 0, tzinfo=UTC)),
        (None, datetime(2026, 8, 25, 11, 50, tzinfo=UTC)),
    ],
)
def test_scot_pivot_authentication_rejects_bad_or_stale_requests(signature, signed_at):
    now = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    body = _body(now)
    timestamp = int(signed_at.timestamp())
    supplied_signature = signature or scot_pivot_signature(
        _SECRET,
        key_id=_KEY_ID,
        timestamp=timestamp,
        nonce=_NONCE,
        body=body,
    )

    with pytest.raises(ScotPivotAuthenticationError, match="authentication failed"):
        authenticate_scot_pivot_request(
            _SECRET,
            key_id=_KEY_ID,
            timestamp=str(timestamp),
            nonce=_NONCE,
            signature=supplied_signature,
            body=body,
            now=now,
        )


def test_scot_pivot_authentication_requires_a_strong_configured_secret():
    now = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    body = _body(now)

    with pytest.raises(ScotPivotAuthenticationError, match="not configured"):
        authenticate_scot_pivot_request(
            None,
            key_id=_KEY_ID,
            timestamp=str(int(now.timestamp())),
            nonce=_NONCE,
            signature="sha256=" + "0" * 64,
            body=body,
            now=now,
        )


def test_scot_pivot_authentication_rejects_unrepresentable_timestamp():
    now = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    body = _body(now)

    with pytest.raises(ScotPivotAuthenticationError, match="authentication failed"):
        authenticate_scot_pivot_request(
            _SECRET,
            key_id=_KEY_ID,
            timestamp="9" * 200,
            nonce=_NONCE,
            signature="sha256=" + "0" * 64,
            body=body,
            now=now,
        )


def test_scot_pivot_authentication_preserves_exact_fractional_clock_skew():
    now = datetime(2026, 8, 25, 12, 0, 0, 999_999, tzinfo=UTC)
    signed_at = int(datetime(2026, 8, 25, 11, 55, 0, tzinfo=UTC).timestamp())
    body = _body(now)
    signature = scot_pivot_signature(
        _SECRET,
        key_id=_KEY_ID,
        timestamp=signed_at,
        nonce=_NONCE,
        body=body,
    )

    with pytest.raises(ScotPivotAuthenticationError, match="authentication failed"):
        authenticate_scot_pivot_request(
            _SECRET,
            key_id=_KEY_ID,
            timestamp=str(signed_at),
            nonce=_NONCE,
            signature=signature,
            body=body,
            now=now,
        )
    with pytest.raises(ScotPivotAuthenticationError, match="at least 32 bytes"):
        scot_pivot_signature(
            "too-short",
            key_id=_KEY_ID,
            timestamp=int(now.timestamp()),
            nonce=_NONCE,
            body=body,
        )


def test_scot_pivot_endpoint_authenticates_and_records_without_enqueueing(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("AP_SCOT_PIVOT_SECRET", _SECRET)
    ctx = ToolContext(
        config_dir=tmp_path / "config",
        workspace_dir=tmp_path / "workspaces",
    )
    service = WebCockpitService(ctx)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        _handler(service, tmp_path),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    now = datetime.now(UTC).replace(microsecond=0)
    body = _body(now)
    headers = _headers(body, now)

    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request("POST", "/api/integrations/scot/pivot-request", body, headers)
        response = connection.getresponse()
        first = json.loads(response.read())
        assert response.status == 201
        assert first["created"] is True
        assert first["enqueued"] is False

        connection.request("POST", "/api/integrations/scot/pivot-request", body, headers)
        response = connection.getresponse()
        repeated = json.loads(response.read())
        assert response.status == 200
        assert repeated["created"] is False

        bad_headers = {**headers, "X-Pivotglass-Signature": "sha256=" + "0" * 64}
        connection.request("POST", "/api/integrations/scot/pivot-request", body, bad_headers)
        response = connection.getresponse()
        error = json.loads(response.read())
        assert response.status == 401
        assert error == {"error": "SCOT pivot authentication failed"}

        oversized_time_headers = {
            **headers,
            "X-Pivotglass-Timestamp": "9" * 200,
            "X-Pivotglass-Signature": "sha256=" + "0" * 64,
        }
        connection.request(
            "POST",
            "/api/integrations/scot/pivot-request",
            body,
            oversized_time_headers,
        )
        response = connection.getresponse()
        error = json.loads(response.read())
        assert response.status == 401
        assert error == {"error": "SCOT pivot authentication failed"}

        valid_after_failure = _headers(body, now, signature=headers["X-Pivotglass-Signature"])
        connection.request(
            "POST",
            "/api/integrations/scot/pivot-request",
            body,
            valid_after_failure,
        )
        response = connection.getresponse()
        recovered = json.loads(response.read())
        assert response.status == 200
        assert recovered["created"] is False

        altered = json.loads(body)
        altered["request_id"] = "scot-pivot-000000000000000000000000"
        altered_body = json.dumps(altered, separators=(",", ":")).encode()
        altered_headers = _headers(altered_body, now)
        connection.request(
            "POST",
            "/api/integrations/scot/pivot-request",
            altered_body,
            altered_headers,
        )
        response = connection.getresponse()
        error = json.loads(response.read())
        assert response.status == 400
        assert error == {
            "error": "SCOT pivot request_id does not match the validated request"
        }
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    ledger = AnalyticLedger(ctx.workspace_mgr)
    assert len(ledger.scot_pivot_requests()) == 1
    assert ledger.enrichment_requests() == []
    stored = repr(ledger.scot_pivot_requests())
    assert _SECRET not in stored
    assert headers["X-Pivotglass-Signature"] not in stored
    assert _NONCE not in stored


def test_scot_pivot_endpoint_rejects_stale_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("AP_SCOT_PIVOT_SECRET", _SECRET)
    ctx = ToolContext(
        config_dir=tmp_path / "config",
        workspace_dir=tmp_path / "workspaces",
    )
    service = WebCockpitService(ctx)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(service, tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    requested_at = datetime.now(UTC).replace(microsecond=0)
    signed_at = requested_at - timedelta(minutes=10)
    body = _body(requested_at)
    headers = _headers(body, signed_at)

    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request("POST", "/api/integrations/scot/pivot-request", body, headers)
        response = connection.getresponse()
        assert response.status == 401
        assert json.loads(response.read()) == {
            "error": "SCOT pivot authentication failed"
        }
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert AnalyticLedger(ctx.workspace_mgr).scot_pivot_requests() == []
