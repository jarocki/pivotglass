"""Shared bounded response consumption for optional HTTP integrations."""

from __future__ import annotations

import httpx


class ResponseSizeLimitError(RuntimeError):
    """Raised before a remote response can exceed its configured memory budget."""


def read_bounded_response(response: httpx.Response, max_response_bytes: int) -> bytes:
    """Read decoded response bytes without buffering beyond ``max_response_bytes``."""
    if max_response_bytes <= 0:
        raise ValueError("response size limit must be positive")
    content_encoding = response.headers.get("Content-Encoding", "").strip().casefold()
    if content_encoding not in {"", "identity"}:
        # httpx expands encoded bodies before iter_bytes yields them. A hostile
        # compressed chunk could therefore exceed the memory budget before a
        # decoded-byte counter can run. These small API responses explicitly
        # request identity encoding and fail closed if a server ignores it.
        raise ResponseSizeLimitError
    declared_length = response.headers.get("Content-Length")
    if declared_length is not None:
        try:
            if int(declared_length) > max_response_bytes:
                raise ResponseSizeLimitError
        except ValueError:
            pass

    content = bytearray()
    for chunk in response.iter_bytes():
        if len(content) + len(chunk) > max_response_bytes:
            raise ResponseSizeLimitError
        content.extend(chunk)
    return bytes(content)
