"""Shared HTTP request path for keyless context sources.

@decision DEC-MODULE-KEYLESS-HTTP-001
@title One request helper for keyless sources: generic User-Agent, bounded timeout, clear failures
@status accepted
@rationale Mnemonic passive DNS, Shodan InternetDB, SANS ISC, RDAP, Wayback CDX,
           and CIRCL hashlookup need no credential, so the only things they share
           are transport concerns: a descriptive User-Agent (SANS ISC requires one),
           a bounded timeout, HTTP 429 as RateLimitError, and network failures as a
           ModuleError naming the source. The User-Agent is ``pivotglass/<version>``
           and carries no contact or personal detail. Status semantics that differ
           per source (404 as "no data", 402 as Mnemonic's quota signal) stay in each
           module. ``transport`` is a class attribute so tests can inject an
           ``httpx.MockTransport``; production leaves it ``None``.
"""

from __future__ import annotations

from typing import Any

import httpx

from pivotglass import __version__
from pivotglass.modules.base import ModuleError, RateLimitError

USER_AGENT = f"pivotglass/{__version__}"
DEFAULT_TIMEOUT = 20.0


def _retry_after(response: httpx.Response) -> int | None:
    value = response.headers.get("Retry-After", "")
    return int(value) if value.isdigit() else None


async def keyless_get(
    source: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    follow_redirects: bool = False,
    accept: str = "application/json",
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.Response:
    """GET *url* for keyless *source*; raise on 429 and network failure.

    The caller interprets every other status code.
    """
    try:
        async with httpx.AsyncClient(
            transport=transport,
            timeout=timeout,
            follow_redirects=follow_redirects,
            headers={"User-Agent": USER_AGENT, "Accept": accept},
        ) as client:
            response = await client.get(url, params=params)
    except httpx.TimeoutException as exc:
        raise ModuleError(f"{source} did not answer within {timeout:.0f} seconds; no result recorded.") from exc
    except httpx.RequestError as exc:
        raise ModuleError(f"{source} is unreachable ({type(exc).__name__}); no result recorded.") from exc
    if response.status_code == 429:
        raise RateLimitError(f"{source} rate limit reached; try again later.", retry_after=_retry_after(response))
    return response


def unexpected_status(source: str, response: httpx.Response) -> ModuleError:
    """Return the error for a status code the source does not document as a result."""
    return ModuleError(f"{source} returned HTTP {response.status_code}; no result recorded.")


def json_body(source: str, response: httpx.Response) -> Any:
    """Decode a JSON body or raise a ModuleError that names the source."""
    try:
        return response.json()
    except ValueError as exc:
        raise ModuleError(f"{source} returned a response that is not JSON; no result recorded.") from exc
