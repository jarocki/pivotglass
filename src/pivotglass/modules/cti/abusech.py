"""Shared abuse.ch Auth-Key handling for ThreatFox, URLhaus, and MalwareBazaar.

@decision DEC-ABUSECH-AUTH-001
@title One abuse.ch Auth-Key, three services, a missing key is "not configured"
@status accepted
@rationale Since 2024 abuse.ch requires an ``Auth-Key`` header on every API
           call (401 ``Unauthorized`` without one, 403 ``unknown_auth_key`` for
           a key it does not know; probed 2026-11-23). One key from an
           abuse.ch account works for all three services, so it is stored once
           (``api_keys.abusech``, env ``PIVOTGLASS_ABUSECH_API_KEY``). Each
           service keeps its own id, base URL, enabled toggle, and credential
           test because the three APIs live on different hosts. A missing key
           raises ``AuthenticationError`` naming the env var, which the web hunt
           records as a skipped, not-configured source (DEC-UNCONFIGURED-SOURCE-001)
           instead of a raw 401. A rejected key stays an authentication fault.
"""

from __future__ import annotations

from typing import Any

import httpx

from pivotglass.modules.base import AuthenticationError, RateLimitError

KEY_ENV_VAR = "PIVOTGLASS_ABUSECH_API_KEY"


def auth_headers(config: dict[str, Any], source: str) -> dict[str, str]:
    """Request headers carrying the Auth-Key; raise when no key is configured."""
    api_key = str(config.get("api_key") or "") if isinstance(config, dict) else ""
    if not api_key:
        raise AuthenticationError(
            f"{source} API key not configured: abuse.ch requires an Auth-Key. "
            f"Add it under abuse.ch in Configuration or set {KEY_ENV_VAR}."
        )
    return {"Auth-Key": api_key, "Accept": "application/json"}


def check_response(response: httpx.Response, source: str) -> None:
    """Raise the typed error for rate limits and rejected keys; other errors via raise_for_status."""
    if response.status_code == 429:
        retry_header = response.headers.get("Retry-After")
        retry_after = int(retry_header) if retry_header and retry_header.isdigit() else None
        raise RateLimitError(f"{source} API rate limit exceeded.", retry_after=retry_after)
    if response.status_code in (401, 403):
        raise AuthenticationError(
            f"{source} rejected the abuse.ch API key (HTTP {response.status_code}); "
            f"check the Auth-Key in Configuration or {KEY_ENV_VAR}."
        )
    response.raise_for_status()
