"""Deterministic, exact-span entity candidates from parser output.

Extraction is a review aid, not evidence admission. Candidates retain their
document occurrence, parser receipt, source locations, rule version, and raw
context. This module has no model, network, STIX, or graph mutation dependency.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass
from typing import Callable, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from adversary_pursuit.models.database import (
    DocumentEntityCandidate,
    DocumentExtractionReceipt,
    DocumentParserReceipt,
)

EXTRACTOR_NAME = "pivotglass-deterministic-entity-extractor"
EXTRACTOR_VERSION = "1.0"


class EntityExtractionLimits(BaseModel):
    """Hard limits for deterministic extraction."""

    model_config = ConfigDict(frozen=True)

    max_candidates: int = Field(default=10_000, ge=1, le=100_000)
    context_chars: int = Field(default=80, ge=0, le=1_000)


class EntityCandidate(BaseModel):
    """One candidate located exactly within one parser output."""

    model_config = ConfigDict(frozen=True)

    id: str
    occurrence_id: str
    parser_receipt_id: str
    entity_type: str
    raw_value: str
    normalized_value: str
    start_char: int
    end_char: int
    start_byte: int
    end_byte: int
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    context: str
    rule_id: str
    rule_version: str
    normalization_note: str | None = None
    state: Literal["candidate"] = "candidate"
    truth_boundary: str = (
        "This is a deterministic text candidate, not admitted evidence, a graph node, "
        "a relationship, a verdict, or actor attribution."
    )


class EntityExtractionResult(BaseModel):
    """Reproducible candidate set and persistence receipt."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-document-entity-extraction-1.0"] = (
        "pivotglass-document-entity-extraction-1.0"
    )
    extraction_receipt_id: str
    occurrence_id: str
    parser_receipt_id: str
    extractor_name: str = EXTRACTOR_NAME
    extractor_version: str = EXTRACTOR_VERSION
    configuration_sha256: str
    input_sha256: str
    state: Literal["complete", "partial"]
    warnings: tuple[str, ...]
    candidates: tuple[EntityCandidate, ...]
    reused: bool = False


Normalizer = Callable[[str], tuple[str, str | None] | None]


@dataclass(frozen=True)
class _Rule:
    id: str
    entity_type: str
    pattern: re.Pattern[str]
    normalize: Normalizer
    trim_terminal: bool = False


def _identity_upper(raw: str) -> tuple[str, None]:
    return raw.upper(), None


def _normalize_hash(raw: str) -> tuple[str, None]:
    return raw.lower(), None


def _normalize_ip(raw: str) -> tuple[str, None] | None:
    try:
        return ipaddress.ip_address(raw).compressed, None
    except ValueError:
        return None


def _normalize_domain(raw: str) -> tuple[str, None] | None:
    try:
        value = raw.rstrip(".").encode("idna").decode("ascii").casefold()
    except UnicodeError:
        return None
    labels = value.split(".")
    if len(labels) < 2 or any(not label or len(label) > 63 for label in labels):
        return None
    if any(label.startswith("-") or label.endswith("-") for label in labels):
        return None
    return value, None


def _normalize_email(raw: str) -> tuple[str, str | None] | None:
    local, separator, domain = raw.rpartition("@")
    if not separator or not local:
        return None
    normalized_domain = _normalize_domain(domain)
    if normalized_domain is None:
        return None
    return f"{local}@{normalized_domain[0]}", None


def _normalize_url(raw: str) -> tuple[str, str | None] | None:
    try:
        parsed = urlsplit(raw)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme.casefold() not in {"http", "https"} or not hostname:
        return None
    normalized_host = _normalize_domain(hostname)
    if normalized_host is None:
        try:
            normalized_host_value = ipaddress.ip_address(hostname).compressed
        except ValueError:
            return None
    else:
        normalized_host_value = normalized_host[0]
    if ":" in normalized_host_value and not normalized_host_value.startswith("["):
        normalized_host_value = f"[{normalized_host_value}]"
    netloc = normalized_host_value + (f":{port}" if port is not None else "")
    note = None
    if parsed.username is not None or parsed.password is not None:
        note = "Embedded URL credentials were omitted from the normalized candidate."
    return (
        urlunsplit(
            (
                parsed.scheme.casefold(),
                netloc,
                parsed.path,
                parsed.query,
                "",
            )
        ),
        note,
    )


_FLAGS = re.IGNORECASE | re.ASCII
_RULES = (
    _Rule(
        "url-http",
        "url",
        re.compile(r"\bhttps?://[^\s<>\"']+", _FLAGS),
        _normalize_url,
        trim_terminal=True,
    ),
    _Rule(
        "email-rfc5322-subset",
        "email-addr",
        re.compile(r"(?<![\w.+-])[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9-]+(?:\.[A-Z0-9-]+)+(?![\w-])", _FLAGS),
        _normalize_email,
    ),
    _Rule(
        "hash-sha256-hex",
        "file-hash-sha256",
        re.compile(r"(?<![0-9A-F])[0-9A-F]{64}(?![0-9A-F])", _FLAGS),
        _normalize_hash,
    ),
    _Rule(
        "hash-sha1-hex",
        "file-hash-sha1",
        re.compile(r"(?<![0-9A-F])[0-9A-F]{40}(?![0-9A-F])", _FLAGS),
        _normalize_hash,
    ),
    _Rule(
        "hash-md5-hex",
        "file-hash-md5",
        re.compile(r"(?<![0-9A-F])[0-9A-F]{32}(?![0-9A-F])", _FLAGS),
        _normalize_hash,
    ),
    _Rule(
        "ipv4-address",
        "ipv4-addr",
        re.compile(r"(?<![\w:])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![\w:])", _FLAGS),
        _normalize_ip,
    ),
    _Rule(
        "ipv6-address",
        "ipv6-addr",
        re.compile(r"(?<![\w:])(?:[0-9A-F]{0,4}:){2,7}[0-9A-F]{0,4}(?![\w:])", _FLAGS),
        _normalize_ip,
    ),
    _Rule(
        "cve-identifier",
        "vulnerability",
        re.compile(r"(?<![A-Z0-9-])CVE-[0-9]{4}-[0-9]{4,7}(?![A-Z0-9-])", _FLAGS),
        _identity_upper,
    ),
    _Rule(
        "attack-technique-identifier",
        "attack-pattern",
        re.compile(r"(?<![A-Z0-9.])T[0-9]{4}(?:\.[0-9]{3})?(?![A-Z0-9.])", _FLAGS),
        _identity_upper,
    ),
    _Rule(
        "domain-ascii",
        "domain-name",
        re.compile(r"(?<![A-Z0-9-])(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}(?![A-Z0-9-])", _FLAGS),
        _normalize_domain,
    ),
)


@dataclass(frozen=True)
class _Match:
    rule: _Rule
    start: int
    end: int
    raw: str
    normalized: str
    note: str | None


def _overlaps(start: int, end: int, occupied: list[tuple[int, int]]) -> bool:
    return any(start < occupied_end and end > occupied_start for occupied_start, occupied_end in occupied)


def _line_column(text: str, position: int) -> tuple[int, int]:
    line = text.count("\n", 0, position) + 1
    prior_newline = text.rfind("\n", 0, position)
    return line, position - prior_newline


def _byte_offsets(text: str, positions: set[int]) -> dict[int, int]:
    offsets: dict[int, int] = {}
    previous_position = 0
    previous_bytes = 0
    for position in sorted(positions):
        previous_bytes += len(text[previous_position:position].encode("utf-8"))
        offsets[position] = previous_bytes
        previous_position = position
    return offsets


def extract_entity_candidates(
    text: str,
    *,
    occurrence_id: str,
    parser_receipt_id: str,
    input_sha256: str,
    limits: EntityExtractionLimits | None = None,
) -> EntityExtractionResult:
    """Extract bounded, deterministic candidates from one exact parser output."""

    active_limits = limits or EntityExtractionLimits()
    matches: list[_Match] = []
    occupied: list[tuple[int, int]] = []
    warnings: list[str] = []
    truncated = False
    for rule in _RULES:
        for match in rule.pattern.finditer(text):
            start, end = match.span()
            raw = match.group(0)
            if rule.trim_terminal:
                trimmed = raw.rstrip(".,;:!?)]}")
                end -= len(raw) - len(trimmed)
                raw = trimmed
            if not raw or _overlaps(start, end, occupied):
                continue
            normalized = rule.normalize(raw)
            if normalized is None:
                continue
            matches.append(
                _Match(rule, start, end, raw, normalized[0], normalized[1])
            )
            occupied.append((start, end))
            if len(matches) >= active_limits.max_candidates:
                warnings.append(
                    f"Candidate limit reached at {active_limits.max_candidates}; remaining text was not extracted."
                )
                truncated = True
                break
        if truncated:
            break
    matches.sort(key=lambda item: (item.start, item.end, item.rule.id))
    byte_offsets = _byte_offsets(
        text,
        {position for item in matches for position in (item.start, item.end)},
    )
    config_json = active_limits.model_dump_json()
    configuration_sha256 = hashlib.sha256(config_json.encode()).hexdigest()
    receipt_basis = json.dumps(
        {
            "parser_receipt_id": parser_receipt_id,
            "input_sha256": input_sha256,
            "extractor": EXTRACTOR_NAME,
            "version": EXTRACTOR_VERSION,
            "configuration_sha256": configuration_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    receipt_id = f"document-extraction-{hashlib.sha256(receipt_basis.encode()).hexdigest()[:32]}"
    candidates: list[EntityCandidate] = []
    for item in matches:
        start_line, start_column = _line_column(text, item.start)
        end_line, end_column = _line_column(text, item.end)
        candidate_basis = (
            f"{receipt_id}\0{item.rule.entity_type}\0{item.start}\0{item.end}\0"
            f"{item.normalized}\0{EXTRACTOR_VERSION}"
        )
        candidates.append(
            EntityCandidate(
                id=f"document-candidate-{hashlib.sha256(candidate_basis.encode()).hexdigest()[:32]}",
                occurrence_id=occurrence_id,
                parser_receipt_id=parser_receipt_id,
                entity_type=item.rule.entity_type,
                raw_value=item.raw,
                normalized_value=item.normalized,
                start_char=item.start,
                end_char=item.end,
                start_byte=byte_offsets[item.start],
                end_byte=byte_offsets[item.end],
                start_line=start_line,
                start_column=start_column,
                end_line=end_line,
                end_column=end_column,
                context=text[
                    max(0, item.start - active_limits.context_chars) : min(
                        len(text), item.end + active_limits.context_chars
                    )
                ],
                rule_id=item.rule.id,
                rule_version=EXTRACTOR_VERSION,
                normalization_note=item.note,
            )
        )
    return EntityExtractionResult(
        extraction_receipt_id=receipt_id,
        occurrence_id=occurrence_id,
        parser_receipt_id=parser_receipt_id,
        configuration_sha256=configuration_sha256,
        input_sha256=input_sha256,
        state="partial" if truncated else "complete",
        warnings=tuple(warnings),
        candidates=tuple(candidates),
    )


class DocumentEntityExtractionService:
    """Persist and list exact-span candidates without admitting graph truth."""

    def __init__(self, workspace_manager: object) -> None:
        self._workspace = workspace_manager

    def extract_parser_receipt(
        self,
        parser_receipt_id: str,
        *,
        limits: EntityExtractionLimits | None = None,
    ) -> EntityExtractionResult:
        with self._workspace.get_session() as session:  # type: ignore[attr-defined]
            parser = session.get(DocumentParserReceipt, parser_receipt_id)
            if parser is None:
                raise ValueError("Document parser receipt was not found in this workspace.")
            if parser.state == "failed":
                raise ValueError("Cannot extract candidates from a failed parser receipt.")
            result = extract_entity_candidates(
                parser.output_text,
                occurrence_id=parser.occurrence_id,
                parser_receipt_id=parser.id,
                input_sha256=parser.output_sha256,
                limits=limits,
            )
            existing = session.get(DocumentExtractionReceipt, result.extraction_receipt_id)
            if existing is not None:
                candidates = tuple(
                    _candidate_from_row(row)
                    for row in session.execute(
                        select(DocumentEntityCandidate)
                        .where(
                            DocumentEntityCandidate.extraction_receipt_id
                            == result.extraction_receipt_id
                        )
                        .order_by(
                            DocumentEntityCandidate.start_char,
                            DocumentEntityCandidate.end_char,
                            DocumentEntityCandidate.id,
                        )
                    ).scalars()
                )
                return result.model_copy(update={"candidates": candidates, "reused": True})
            session.add(
                DocumentExtractionReceipt(
                    id=result.extraction_receipt_id,
                    parser_receipt_id=result.parser_receipt_id,
                    extractor_name=result.extractor_name,
                    extractor_version=result.extractor_version,
                    configuration_sha256=result.configuration_sha256,
                    input_sha256=result.input_sha256,
                    candidate_count=len(result.candidates),
                    warnings=list(result.warnings),
                    state=result.state,
                )
            )
            for candidate in result.candidates:
                session.add(
                    DocumentEntityCandidate(
                        extraction_receipt_id=result.extraction_receipt_id,
                        disposition=None,
                        disposition_reason=None,
                        **candidate.model_dump(exclude={"truth_boundary"}),
                    )
                )
            session.commit()
        return result

    def list_candidates(self, parser_receipt_id: str) -> tuple[EntityCandidate, ...]:
        with self._workspace.get_session() as session:  # type: ignore[attr-defined]
            rows = session.execute(
                select(DocumentEntityCandidate)
                .where(DocumentEntityCandidate.parser_receipt_id == parser_receipt_id)
                .order_by(
                    DocumentEntityCandidate.start_char,
                    DocumentEntityCandidate.end_char,
                    DocumentEntityCandidate.id,
                )
            ).scalars()
            return tuple(_candidate_from_row(row) for row in rows)


def _candidate_from_row(row: DocumentEntityCandidate) -> EntityCandidate:
    return EntityCandidate(
        id=row.id,
        occurrence_id=row.occurrence_id,
        parser_receipt_id=row.parser_receipt_id,
        entity_type=row.entity_type,
        raw_value=row.raw_value,
        normalized_value=row.normalized_value,
        start_char=row.start_char,
        end_char=row.end_char,
        start_byte=row.start_byte,
        end_byte=row.end_byte,
        start_line=row.start_line,
        start_column=row.start_column,
        end_line=row.end_line,
        end_column=row.end_column,
        context=row.context,
        rule_id=row.rule_id,
        rule_version=row.rule_version,
        normalization_note=row.normalization_note,
        state="candidate",
    )
