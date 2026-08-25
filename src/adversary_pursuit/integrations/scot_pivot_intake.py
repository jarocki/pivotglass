"""Authenticated, non-enqueueing intake for SCOT-side pivot requests."""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

_KEY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_NONCE = re.compile(r"[A-Za-z0-9_-]{16,128}")
_SIGNATURE = re.compile(r"sha256=([0-9a-f]{64})")


class ScotPivotAuthenticationError(ValueError):
    """Raised without reflecting credentials or attacker-controlled header values."""


class ScotPivotAuthenticationReceipt(BaseModel):
    """Secret-safe receipt for one authenticated inbound SCOT request."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-scot-pivot-auth-1.0"] = (
        "pivotglass-scot-pivot-auth-1.0"
    )
    scheme: Literal["hmac-sha256-v1"] = "hmac-sha256-v1"
    key_id: str
    signed_at: datetime
    authenticated_at: datetime
    body_sha256: str
    nonce_sha256: str
    maximum_clock_skew_seconds: int


def scot_pivot_signature(
    secret: str,
    *,
    key_id: str,
    timestamp: int,
    nonce: str,
    body: bytes,
) -> str:
    """Return the documented SCOT request signature for test and client use."""
    _validate_secret(secret)
    _validate_headers(key_id=key_id, timestamp=str(timestamp), nonce=nonce)
    message = _signature_message(key_id, timestamp, nonce, body)
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def authenticate_scot_pivot_request(
    secret: str | None,
    *,
    key_id: str,
    timestamp: str,
    nonce: str,
    signature: str,
    body: bytes,
    now: datetime | None = None,
    maximum_clock_skew_seconds: int = 300,
) -> ScotPivotAuthenticationReceipt:
    """Authenticate a bounded request without retaining its secret or signature."""
    if secret is None:
        raise ScotPivotAuthenticationError("SCOT pivot intake is not configured")
    _validate_secret(secret)
    if not 30 <= maximum_clock_skew_seconds <= 900:
        raise ValueError("SCOT pivot clock skew must be between 30 and 900 seconds")
    signed_at_seconds = _validate_headers(
        key_id=key_id,
        timestamp=timestamp,
        nonce=nonce,
    )
    current_time = now or datetime.now(UTC)
    if current_time.utcoffset() is None:
        raise ValueError("SCOT pivot authentication time must include a timezone")
    signed_at = datetime.fromtimestamp(signed_at_seconds, tz=UTC)
    if abs((current_time - signed_at).total_seconds()) > maximum_clock_skew_seconds:
        raise ScotPivotAuthenticationError("SCOT pivot authentication failed")
    match = _SIGNATURE.fullmatch(signature.strip().casefold())
    if match is None:
        raise ScotPivotAuthenticationError("SCOT pivot authentication failed")
    expected = hmac.new(
        secret.encode("utf-8"),
        _signature_message(key_id, signed_at_seconds, nonce, body),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, match.group(1)):
        raise ScotPivotAuthenticationError("SCOT pivot authentication failed")
    return ScotPivotAuthenticationReceipt(
        key_id=key_id,
        signed_at=signed_at,
        authenticated_at=current_time,
        body_sha256=hashlib.sha256(body).hexdigest(),
        nonce_sha256=hashlib.sha256(nonce.encode()).hexdigest(),
        maximum_clock_skew_seconds=maximum_clock_skew_seconds,
    )


def _validate_secret(secret: str) -> None:
    if len(secret.encode("utf-8")) < 32:
        raise ScotPivotAuthenticationError("SCOT pivot intake secret must be at least 32 bytes")


def _validate_headers(*, key_id: str, timestamp: str, nonce: str) -> int:
    if _KEY_ID.fullmatch(key_id) is None or _NONCE.fullmatch(nonce) is None:
        raise ScotPivotAuthenticationError("SCOT pivot authentication failed")
    try:
        parsed_timestamp = int(timestamp)
    except ValueError:
        raise ScotPivotAuthenticationError("SCOT pivot authentication failed") from None
    if str(parsed_timestamp) != timestamp or parsed_timestamp < 0:
        raise ScotPivotAuthenticationError("SCOT pivot authentication failed")
    return parsed_timestamp


def _signature_message(key_id: str, timestamp: int, nonce: str, body: bytes) -> bytes:
    prefix = f"pivotglass-scot-pivot-v1\n{key_id}\n{timestamp}\n{nonce}\n".encode()
    return prefix + body
