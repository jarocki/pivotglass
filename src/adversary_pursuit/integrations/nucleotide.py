"""Read-only Nucleotide attribution and actor-fingerprint adapter."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict

from adversary_pursuit.integrations.local_tool import LocalToolReceipt, LocalToolRunner

_MAX_LOOKUP_BYTES = 250_000_000
_ACTOR_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")


class NucleotideLookupMatch(BaseModel):
    """One URL attribution emitted by Nucleotide's documented TSV interface."""

    model_config = ConfigDict(frozen=True)

    url: str
    attribution: Literal["UNIQUE", "AMBIGUOUS", "NO_MATCH"]
    template_id: str | None = None
    snippet: str | None = None
    severity: str | None = None
    template_name: str | None = None


class NucleotideLookupPreview(BaseModel):
    """Review-only URL-to-template attribution results."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-nucleotide-lookup-preview-1.0"] = (
        "pivotglass-nucleotide-lookup-preview-1.0"
    )
    lookup_sha256: str
    matches: tuple[NucleotideLookupMatch, ...]
    caveats: tuple[str, ...]
    receipt: LocalToolReceipt
    disposition: Literal["preview"] = "preview"
    import_requires_analyst_action: Literal[True] = True


class NucleotideFingerprintPreview(BaseModel):
    """Review-only actor-behavior hypothesis produced from pre-grouped events."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-nucleotide-fingerprint-preview-1.0"] = (
        "pivotglass-nucleotide-fingerprint-preview-1.0"
    )
    lookup_sha256: str
    event_count: int
    fingerprint: dict[str, Any]
    supporting_signals: tuple[str, ...]
    contradictions: tuple[str, ...]
    caveats: tuple[str, ...]
    receipt: LocalToolReceipt
    disposition: Literal["preview"] = "preview"
    import_requires_analyst_action: Literal[True] = True
    generated_controls_are_review_only: Literal[True] = True


class NucleotideAdapter:
    """Invoke an installed Nucleotide CLI against a configured lookup artifact."""

    def __init__(
        self,
        executable: str,
        lookup_path: str,
        *,
        timeout_seconds: float,
        max_output_bytes: int,
        max_records: int,
    ) -> None:
        self.runner = LocalToolRunner(
            "nucleotide",
            executable,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
        )
        self.lookup_path = _lookup_path(lookup_path)
        self.lookup_sha256 = _file_sha256(self.lookup_path)
        self.max_records = max_records

    def lookup(self, urls: list[str], *, strict: bool = False) -> NucleotideLookupPreview:
        normalized = _normalize_urls(urls, self.max_records)
        args = ["lookup", str(self.lookup_path), *normalized]
        if strict:
            args.append("--strict")
        result = self.runner.run("lookup", args)
        matches = tuple(_parse_lookup_line(line) for line in result.stdout.splitlines() if line)
        if len(matches) > self.max_records * 10:
            raise ValueError("Nucleotide returned more attribution rows than the configured limit")
        return NucleotideLookupPreview(
            lookup_sha256=self.lookup_sha256,
            matches=matches,
            caveats=(
                "UNIQUE means unique within the configured template corpus, not proof that Nuclei executed the request.",
                "AMBIGUOUS matches preserve every candidate and require analyst disposition.",
                "Attribution is derived analysis and remains separate from observed request evidence.",
            ),
            receipt=result.receipt,
        )

    def fingerprint(self, actor_id: str, events: list[dict[str, Any]]) -> NucleotideFingerprintPreview:
        normalized_id = actor_id.strip()
        if not _ACTOR_ID.fullmatch(normalized_id):
            raise ValueError("actor ID must be 1-128 safe identifier characters")
        normalized_events = _validate_events(events, self.max_records)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", encoding="utf-8") as handle:
            for event in normalized_events:
                handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            result = self.runner.run(
                "fingerprint",
                [
                    "fingerprint",
                    handle.name,
                    "--lookup",
                    str(self.lookup_path),
                    "--actor-id",
                    normalized_id,
                ],
            )
        try:
            parsed = yaml.safe_load(result.stdout)
        except yaml.YAMLError as exc:
            raise ValueError("Nucleotide returned malformed fingerprint YAML") from exc
        if not isinstance(parsed, dict) or not isinstance(parsed.get("actor_fingerprint"), dict):
            raise ValueError("Nucleotide fingerprint output is missing actor_fingerprint")
        fingerprint = parsed["actor_fingerprint"]
        tool_inference = fingerprint.get("tool_inference") or {}
        signals = tuple(str(item) for item in tool_inference.get("signals") or [])
        contradictions = tuple(str(item) for item in tool_inference.get("contradictions") or [])
        return NucleotideFingerprintPreview(
            lookup_sha256=self.lookup_sha256,
            event_count=len(normalized_events),
            fingerprint=parsed,
            supporting_signals=signals,
            contradictions=contradictions,
            caveats=(
                "Events must already be grouped by an analyst; Pivotglass does not infer actor identity from this batch.",
                "A Nuclei-shaped request can be produced by another tool consuming public templates.",
                "Confidence is explainable model output from Nucleotide, not a formal Pivotglass confidence disposition.",
                "Generated Snort, Suricata, Sigma, or YARA content is an artifact for review and is never deployed here.",
            ),
            receipt=result.receipt,
        )

    def lookup_info(self) -> dict[str, Any]:
        with self.lookup_path.open("rb") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("Nucleotide lookup artifact must be a JSON object")
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        signatures = data.get("signatures") if isinstance(data.get("signatures"), dict) else {}
        return {
            "lookup_path": str(self.lookup_path),
            "lookup_sha256": self.lookup_sha256,
            "metadata": metadata,
            "template_count": len(data.get("templates") or {}),
            "signature_families": sorted(signatures),
            "controls_are_review_only": True,
        }


def _lookup_path(value: str) -> Path:
    if not value or "\x00" in value:
        raise ValueError("Nucleotide lookup path is missing")
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Nucleotide lookup artifact is unavailable: {value}")
    if path.stat().st_size > _MAX_LOOKUP_BYTES:
        raise ValueError("Nucleotide lookup artifact exceeds the 250 MB safety limit")
    return path


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_urls(urls: list[str], max_records: int) -> list[str]:
    normalized = [item.strip() for item in urls if item.strip()]
    if not normalized:
        raise ValueError("at least one URL is required")
    if len(normalized) > max_records:
        raise ValueError("too many URLs for the configured record limit")
    for url in normalized:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or len(url) > 4096:
            raise ValueError(f"invalid URL for Nucleotide lookup: {url[:100]!r}")
    return normalized


def _parse_lookup_line(line: str) -> NucleotideLookupMatch:
    fields = line.split("\t")
    if len(fields) < 2 or fields[1] not in {"UNIQUE", "AMBIGUOUS", "NO_MATCH"}:
        raise ValueError("Nucleotide returned an unsupported lookup row")
    fields.extend([""] * (6 - len(fields)))
    return NucleotideLookupMatch(
        url=fields[0],
        attribution=fields[1],
        template_id=fields[2] or None,
        snippet=fields[3] or None,
        severity=fields[4] or None,
        template_name=fields[5] or None,
    )


def _validate_events(events: list[dict[str, Any]], max_records: int) -> list[dict[str, Any]]:
    if not events:
        raise ValueError("at least one observed event is required")
    if len(events) > max_records:
        raise ValueError("too many events for the configured record limit")
    normalized: list[dict[str, Any]] = []
    for index, event in enumerate(events, 1):
        if not isinstance(event, dict):
            raise ValueError(f"event {index} must be a JSON object")
        uri = event.get("uri") or event.get("url")
        if not isinstance(uri, str) or not uri.strip() or len(uri) > 4096:
            raise ValueError(f"event {index} requires a bounded uri or url string")
        encoded = json.dumps(event, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode()) > 100_000:
            raise ValueError(f"event {index} exceeds the 100 KB safety limit")
        normalized.append(event)
    return normalized
