"""Governed, local-first document intake and preview.

Document bytes prove only what a source contained. Parsing creates an
auditable representation; it does not admit extracted strings or relationships
to the investigation graph. This module deliberately has no model or network
client dependency.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import mimetypes
import os
import time
import uuid
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterator, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field

from adversary_pursuit.models.database import (
    DocumentContent,
    DocumentOccurrence,
    DocumentParserReceipt,
)

PARSER_VERSION = "pivotglass-bounded-preview-1.1"


class DocumentLimits(BaseModel):
    """Hard deterministic limits applied before and during parsing."""

    model_config = ConfigDict(frozen=True)

    max_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=100 * 1024 * 1024)
    max_output_chars: int = Field(default=2_000_000, ge=1_000, le=10_000_000)
    max_rows: int = Field(default=50_000, ge=1, le=250_000)
    max_parts: int = Field(default=100, ge=1, le=1_000)
    max_json_depth: int = Field(default=64, ge=2, le=256)


class DocumentPreview(BaseModel):
    """Non-mutating parse result suitable for analyst review."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-document-preview-1.0"] = (
        "pivotglass-document-preview-1.0"
    )
    content_sha256: str
    size_bytes: int
    filename: str
    supplied_media_type: str | None
    detected_media_type: str
    parser_name: str
    parser_version: str = PARSER_VERSION
    state: Literal["parsed", "partial", "failed"]
    output_text: str
    output_sha256: str
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    skipped: tuple[str, ...]
    limits: DocumentLimits
    elapsed_ms: int
    truth_boundary: str = (
        "The document is evidence of source content. Parsed text is not proof of its claims, "
        "and no entity or relationship has been admitted."
    )


class DocumentIntakeReceipt(BaseModel):
    """Persistent receipt for one stored source occurrence and parser run."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-document-intake-1.0"] = (
        "pivotglass-document-intake-1.0"
    )
    workspace: str
    occurrence_id: str
    parser_receipt_id: str
    storage_ref: str
    reused_content: bool
    preview: DocumentPreview


class _TextExtractor(HTMLParser):
    """Extract visible text while refusing script and style bodies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.casefold() in {"script", "style", "noscript", "template"}:
            self._ignored_depth += 1
        elif not self._ignored_depth and tag.casefold() in {
            "p",
            "br",
            "div",
            "li",
            "tr",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        }:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript", "template"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "\n".join(line.strip() for line in "".join(self.parts).splitlines() if line.strip())


def _safe_filename(filename: str) -> str:
    value = Path(filename.replace("\x00", "")).name.strip()
    return (value or "document.bin")[:255]


def _safe_source_uri(value: str | None, filename: str) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"} and parsed.hostname:
        host = parsed.hostname
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    return f"file:{_safe_filename(filename)}"


def _detect_media_type(data: bytes, filename: str, supplied: str | None) -> str:
    prefix = data[:16]
    if filename.casefold().endswith((".jsonl", ".ndjson")):
        return "application/x-ndjson"
    if prefix.startswith(b"%PDF-"):
        return "application/pdf"
    if prefix.startswith((b"{", b"[")):
        return "application/json"
    if prefix.startswith(b"From ") or b"\nMIME-Version:" in data[:8_192]:
        return "message/rfc822"
    guessed = mimetypes.guess_type(filename)[0]
    if guessed:
        return guessed
    if supplied and ";" not in supplied:
        return supplied.casefold()
    try:
        data[:4_096].decode("utf-8")
    except UnicodeDecodeError:
        return "application/octet-stream"
    return "text/plain"


def _decode_text(data: bytes, warnings: list[str]) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        warnings.append("Invalid UTF-8 sequences were replaced in the preview.")
        return data.decode("utf-8", errors="replace")


def _enforce_json_source_depth(source: str, max_depth: int, *, label: str) -> None:
    """Reject excessive container nesting before the JSON decoder sees it."""

    depth = 0
    in_string = False
    escaped = False
    # _json_depth historically counts an empty root container as depth zero.
    # Allowing one additional source container preserves that public boundary;
    # the exact post-parse check below still rejects populated values over the
    # configured limit.
    maximum_containers = max_depth + 1
    for character in source:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > maximum_containers:
                raise ValueError(f"{label} exceeds the configured nesting-depth limit.")
        elif character in "]}":
            depth = max(0, depth - 1)


def _json_depth(value: Any) -> int:
    """Return historical JSON depth with O(nesting depth) auxiliary memory."""

    maximum = 0
    frames: list[tuple[Iterator[Any], int]] = [(iter((value,)), 0)]
    while frames:
        items, depth = frames[-1]
        try:
            item = next(items)
        except StopIteration:
            frames.pop()
            continue
        maximum = max(maximum, depth)
        if isinstance(item, dict):
            frames.append((iter(item.values()), depth + 1))
        elif isinstance(item, list):
            frames.append((iter(item), depth + 1))
    return maximum


def _parse_email(data: bytes, limits: DocumentLimits) -> tuple[str, list[str], list[str]]:
    message = BytesParser(policy=policy.default).parsebytes(data)
    text_parts: list[str] = []
    warnings: list[str] = []
    skipped: list[str] = []
    parts = list(message.walk())
    if len(parts) > limits.max_parts:
        warnings.append(f"Message part limit reached; inspected {limits.max_parts} parts.")
        parts = parts[: limits.max_parts]
    for part in parts:
        if part.is_multipart():
            continue
        disposition = part.get_content_disposition()
        filename = part.get_filename()
        if disposition == "attachment" or filename:
            skipped.append(f"Attachment retained by parent message but not parsed: {filename or 'unnamed'}")
            continue
        media_type = part.get_content_type()
        payload = part.get_payload(decode=True) or b""
        if media_type == "text/plain":
            text_parts.append(_decode_text(payload, warnings))
        elif media_type == "text/html":
            extractor = _TextExtractor()
            extractor.feed(_decode_text(payload, warnings))
            text_parts.append(extractor.text())
        else:
            skipped.append(f"Unsupported message part: {media_type}")
    header = "\n".join(
        f"{name}: {message.get(name)}"
        for name in ("Date", "From", "To", "Cc", "Subject", "Message-ID")
        if message.get(name)
    )
    return "\n\n".join(item for item in (header, *text_parts) if item.strip()), warnings, skipped


def preview_document(
    data: bytes,
    *,
    filename: str,
    supplied_media_type: str | None = None,
    limits: DocumentLimits | None = None,
) -> DocumentPreview:
    """Parse untrusted bytes locally without persisting or admitting anything."""

    active_limits = limits or DocumentLimits()
    if len(data) > active_limits.max_bytes:
        raise ValueError(
            f"Document is {len(data)} bytes; configured limit is {active_limits.max_bytes}."
        )
    started = time.monotonic()
    safe_name = _safe_filename(filename)
    digest = hashlib.sha256(data).hexdigest()
    media_type = _detect_media_type(data, safe_name, supplied_media_type)
    warnings: list[str] = []
    errors: list[str] = []
    skipped: list[str] = []
    state: Literal["parsed", "partial", "failed"] = "parsed"
    parser_name = media_type
    output = ""
    try:
        if media_type in {"text/plain", "text/markdown"}:
            output = _decode_text(data, warnings)
        elif media_type == "text/html":
            extractor = _TextExtractor()
            extractor.feed(_decode_text(data, warnings))
            output = extractor.text()
            warnings.append("Active HTML, scripts, styles, templates, and external references were not run.")
        elif media_type in {"text/csv", "application/csv"}:
            rows: list[list[str]] = []
            reader = csv.reader(io.StringIO(_decode_text(data, warnings)))
            for index, row in enumerate(reader):
                if index >= active_limits.max_rows:
                    warnings.append(f"CSV row limit reached at {active_limits.max_rows} rows.")
                    state = "partial"
                    break
                rows.append([cell[:16_384] for cell in row[:1_024]])
            output = "\n".join("\t".join(row) for row in rows)
        elif media_type == "application/json":
            source = _decode_text(data, warnings)
            _enforce_json_source_depth(
                source,
                active_limits.max_json_depth,
                label="JSON document",
            )
            value = json.loads(source)
            depth = _json_depth(value)
            if depth > active_limits.max_json_depth:
                raise ValueError(
                    f"JSON nesting depth {depth} exceeds limit {active_limits.max_json_depth}."
                )
            output = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        elif media_type in {"application/x-ndjson", "application/jsonl"} or safe_name.casefold().endswith(
            (".jsonl", ".ndjson")
        ):
            records: list[str] = []
            for index, line in enumerate(_decode_text(data, warnings).splitlines()):
                if index >= active_limits.max_rows:
                    warnings.append(f"JSONL row limit reached at {active_limits.max_rows} rows.")
                    state = "partial"
                    break
                if not line.strip():
                    continue
                _enforce_json_source_depth(
                    line,
                    active_limits.max_json_depth,
                    label="JSONL record",
                )
                value = json.loads(line)
                if _json_depth(value) > active_limits.max_json_depth:
                    raise ValueError("JSONL record exceeds the configured nesting-depth limit.")
                records.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
            output = "\n".join(records)
        elif media_type == "message/rfc822":
            output, message_warnings, message_skipped = _parse_email(data, active_limits)
            warnings.extend(message_warnings)
            skipped.extend(message_skipped)
            if skipped:
                state = "partial"
        elif media_type == "application/pdf":
            state = "partial"
            output = "PDF document validated and stored by content hash."
            skipped.append("PDF text extraction and OCR are not qualified in the v0.9.2 preview parser.")
        else:
            state = "partial"
            output = "Document validated and stored by content hash."
            skipped.append(f"No qualified preview parser for {media_type}.")
    except (csv.Error, json.JSONDecodeError, UnicodeError, ValueError) as exc:
        state = "failed"
        errors.append(str(exc))
        output = ""
    if len(output) > active_limits.max_output_chars:
        output = output[: active_limits.max_output_chars]
        warnings.append(
            f"Preview output truncated at {active_limits.max_output_chars} characters."
        )
        if state == "parsed":
            state = "partial"
    elapsed_ms = max(0, round((time.monotonic() - started) * 1_000))
    return DocumentPreview(
        content_sha256=digest,
        size_bytes=len(data),
        filename=safe_name,
        supplied_media_type=supplied_media_type,
        detected_media_type=media_type,
        parser_name=parser_name,
        state=state,
        output_text=output,
        output_sha256=hashlib.sha256(output.encode()).hexdigest(),
        warnings=tuple(warnings),
        errors=tuple(errors),
        skipped=tuple(skipped),
        limits=active_limits,
        elapsed_ms=elapsed_ms,
    )


class DocumentIntakeService:
    """Persist reviewed document bytes and their bounded parser receipt."""

    def __init__(self, workspace_manager: Any) -> None:
        self._workspace = workspace_manager

    def preview_bytes(
        self,
        data: bytes,
        *,
        filename: str,
        supplied_media_type: str | None = None,
        limits: DocumentLimits | None = None,
    ) -> DocumentPreview:
        return preview_document(
            data,
            filename=filename,
            supplied_media_type=supplied_media_type,
            limits=limits,
        )

    def store_bytes(
        self,
        data: bytes,
        *,
        filename: str,
        operator: str,
        source_kind: Literal["local", "downloaded", "scot", "synapse", "message"] = "local",
        source_uri: str | None = None,
        supplied_media_type: str | None = None,
        parent_occurrence_id: str | None = None,
        handling_labels: tuple[str, ...] = (),
        acquired_at: datetime | None = None,
        limits: DocumentLimits | None = None,
    ) -> DocumentIntakeReceipt:
        preview = self.preview_bytes(
            data,
            filename=filename,
            supplied_media_type=supplied_media_type,
            limits=limits,
        )
        if preview.state == "failed":
            raise ValueError("Document parser failed: " + "; ".join(preview.errors))
        workspace = self._workspace.active
        store_root = self._workspace._content_store_path(workspace)  # noqa: SLF001
        content_path = store_root / "sha256" / preview.content_sha256[:2] / preview.content_sha256
        content_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        reused = content_path.exists()
        if reused:
            existing = content_path.read_bytes()
            if hashlib.sha256(existing).hexdigest() != preview.content_sha256:
                raise RuntimeError("Content-addressed store failed integrity verification.")
        else:
            descriptor = os.open(content_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                content_path.unlink(missing_ok=True)
                raise

        occurrence_id = f"document-occurrence-{uuid.uuid4().hex}"
        receipt_id = f"document-parser-{uuid.uuid4().hex}"
        storage_ref = f"sha256:{preview.content_sha256}"
        configuration_sha256 = hashlib.sha256(
            preview.limits.model_dump_json().encode()
        ).hexdigest()
        occurred = acquired_at or datetime.now(timezone.utc)
        with self._workspace.get_session() as session:
            content = session.get(DocumentContent, preview.content_sha256)
            if content is None:
                session.add(
                    DocumentContent(
                        sha256=preview.content_sha256,
                        size_bytes=preview.size_bytes,
                        detected_media_type=preview.detected_media_type,
                        storage_ref=storage_ref,
                    )
                )
            session.add(
                DocumentOccurrence(
                    id=occurrence_id,
                    content_sha256=preview.content_sha256,
                    filename=preview.filename,
                    source_kind=source_kind,
                    source_uri=_safe_source_uri(source_uri, preview.filename),
                    supplied_media_type=supplied_media_type,
                    detected_media_type=preview.detected_media_type,
                    operator=operator.strip() or "local analyst",
                    acquired_at=occurred,
                    parent_occurrence_id=parent_occurrence_id,
                    handling_labels=sorted(set(handling_labels)),
                    lifecycle_state=preview.state,
                )
            )
            session.add(
                DocumentParserReceipt(
                    id=receipt_id,
                    occurrence_id=occurrence_id,
                    parser_name=preview.parser_name,
                    parser_version=preview.parser_version,
                    configuration_sha256=configuration_sha256,
                    output_sha256=preview.output_sha256,
                    output_text=preview.output_text,
                    warnings=list(preview.warnings),
                    errors=list(preview.errors),
                    skipped=list(preview.skipped),
                    limits=preview.limits.model_dump(mode="json"),
                    elapsed_ms=preview.elapsed_ms,
                    state=preview.state,
                )
            )
            session.commit()
        return DocumentIntakeReceipt(
            workspace=workspace,
            occurrence_id=occurrence_id,
            parser_receipt_id=receipt_id,
            storage_ref=storage_ref,
            reused_content=reused,
            preview=preview,
        )
