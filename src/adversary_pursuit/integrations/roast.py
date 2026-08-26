"""Read-only go-roast adapter and evidence-safe OAST analysis proposals."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from adversary_pursuit.integrations.local_tool import LocalToolReceipt, LocalToolRunner

_DOMAIN = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class RoastDecodedRecord(BaseModel):
    """Supported subset of go-roast's JSON decode record."""

    model_config = ConfigDict(extra="allow", frozen=True)

    original: str
    timestamp: datetime | None = None
    machine_id: str | None = None
    pid: int | None = Field(default=None, ge=0, le=65535)
    counter: int | None = Field(default=None, ge=0, le=16_777_215)
    nonce: str | None = None
    ksort: str | None = None
    campaign: str | None = None
    valid: bool
    error: str | None = None
    classification: dict[str, Any] | None = None
    nonce_timestamp: datetime | None = None
    nonce_counter: int | None = None


class AnalysisNodeProposal(BaseModel):
    """A sourced analytic entity proposed for analyst disposition."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: str
    value: str
    properties: dict[str, Any]
    provenance_refs: tuple[str, ...]
    truth_kind: Literal["external-derived-proposal"] = "external-derived-proposal"


class AnalysisRelationshipProposal(BaseModel):
    """A non-authoritative relationship proposed by an external analysis tool."""

    model_config = ConfigDict(frozen=True)

    source: str
    target: str
    relationship: str
    rationale: str
    confidence: str
    caveats: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    truth_kind: Literal["external-derived-proposal"] = "external-derived-proposal"


class RoastDecodePreview(BaseModel):
    """Reviewable go-roast output that does not mutate the governed graph."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-roast-preview-1.0"] = "pivotglass-roast-preview-1.0"
    records: tuple[RoastDecodedRecord, ...]
    nodes: tuple[AnalysisNodeProposal, ...]
    relationships: tuple[AnalysisRelationshipProposal, ...]
    caveats: tuple[str, ...]
    receipt: LocalToolReceipt
    disposition: Literal["preview"] = "preview"
    import_requires_analyst_action: Literal[True] = True


class RoastAdapter:
    """Invoke go-roast's JSON interface through the shared bounded runner."""

    def __init__(
        self,
        executable: str,
        *,
        timeout_seconds: float,
        max_output_bytes: int,
        max_records: int,
    ) -> None:
        self.runner = LocalToolRunner(
            "go-roast",
            executable,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
        )
        self.max_records = max_records

    def decode(self, domains: list[str]) -> RoastDecodePreview:
        normalized = _normalize_domains(domains, self.max_records)
        result = self.runner.run(
            "decode",
            ["decode", "--output", "json", "--quiet"],
            stdin="\n".join(normalized) + "\n",
        )
        try:
            raw = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("go-roast returned malformed JSON") from exc
        if not isinstance(raw, list):
            raise ValueError("go-roast decode output must be a JSON array")
        if len(raw) > self.max_records:
            raise ValueError("go-roast returned more records than the configured limit")
        records = tuple(RoastDecodedRecord.model_validate(item) for item in raw)
        nodes, relationships = _build_graph_proposals(records, result.receipt.request_sha256)
        return RoastDecodePreview(
            records=records,
            nodes=nodes,
            relationships=relationships,
            caveats=(
                "Decoded machine IDs are truncated or spoofable correlation fragments, not operator identity.",
                "Encoded and nonce timestamps may reflect client clock skew and require independent corroboration.",
                "All nodes and relationships are proposals until an analyst accepts them into the governed graph.",
            ),
            receipt=result.receipt,
        )

    def analyze(self, domains: list[str]) -> dict[str, Any]:
        normalized = _normalize_domains(domains, self.max_records)
        result = self.runner.run(
            "analyze",
            ["analyze", "--output", "json", "--quiet"],
            stdin="\n".join(normalized) + "\n",
        )
        try:
            analysis = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("go-roast returned malformed campaign JSON") from exc
        if not isinstance(analysis, dict):
            raise ValueError("go-roast campaign output must be a JSON object")
        return {
            "schema_version": "pivotglass-roast-campaign-preview-1.0",
            "analysis": analysis,
            "caveats": [
                "Campaign, machine, PID, timezone, and temporal groupings are analytic correlations, not identity proof.",
                "The result remains a review-only external analysis until analyst disposition.",
            ],
            "receipt": result.receipt.model_dump(mode="json"),
            "disposition": "preview",
            "import_requires_analyst_action": True,
        }


def _normalize_domains(domains: list[str], max_records: int) -> list[str]:
    normalized = [item.strip().lower().rstrip(".") for item in domains if item.strip()]
    if not normalized:
        raise ValueError("at least one OAST domain is required")
    if len(normalized) > max_records:
        raise ValueError("too many OAST domains for the configured record limit")
    for domain in normalized:
        if not _DOMAIN.fullmatch(domain):
            raise ValueError(f"invalid OAST domain: {domain[:80]!r}")
    return normalized


def _build_graph_proposals(
    records: tuple[RoastDecodedRecord, ...], receipt_ref: str
) -> tuple[tuple[AnalysisNodeProposal, ...], tuple[AnalysisRelationshipProposal, ...]]:
    nodes: dict[str, AnalysisNodeProposal] = {}
    relationships: dict[tuple[str, str, str], AnalysisRelationshipProposal] = {}
    for record in records:
        if not record.valid:
            continue
        domain_id = _id("oast-domain", record.original)
        provenance = (f"go-roast:{receipt_ref}",)
        nodes[domain_id] = AnalysisNodeProposal(
            id=domain_id,
            kind="oast-domain",
            value=record.original,
            properties=record.model_dump(mode="json", exclude_none=True),
            provenance_refs=provenance,
        )
        confidence = str((record.classification or {}).get("confidence") or "unknown")
        if record.campaign:
            campaign_id = _id("oast-campaign-fragment", record.campaign)
            nodes.setdefault(
                campaign_id,
                AnalysisNodeProposal(
                    id=campaign_id,
                    kind="oast-campaign-fragment",
                    value=record.campaign,
                    properties={},
                    provenance_refs=provenance,
                ),
            )
            _rel(
                relationships,
                domain_id,
                campaign_id,
                "encodes-campaign-fragment",
                "go-roast decoded the campaign fragment from the OAST domain preamble.",
                confidence,
                ("Campaign fragments can collide and require corroboration.",),
                provenance,
            )
        if record.machine_id:
            machine_id = _id("oast-machine-fragment", record.machine_id)
            nodes.setdefault(
                machine_id,
                AnalysisNodeProposal(
                    id=machine_id,
                    kind="oast-machine-fragment",
                    value=record.machine_id,
                    properties={},
                    provenance_refs=provenance,
                ),
            )
            _rel(
                relationships,
                domain_id,
                machine_id,
                "encodes-machine-fragment",
                "go-roast decoded the 24-bit machine fragment embedded in the OAST XID.",
                confidence,
                (
                    "The fragment is truncated, may change across XID versions, and can be spoofed.",
                    "It must not be treated as operator or device identity.",
                ),
                provenance,
            )
            if record.pid is not None:
                process_value = f"{record.machine_id}:{record.pid}"
                process_id = _id("oast-process-fragment", process_value)
                nodes.setdefault(
                    process_id,
                    AnalysisNodeProposal(
                        id=process_id,
                        kind="oast-process-fragment",
                        value=process_value,
                        properties={"machine_id": record.machine_id, "pid": record.pid},
                        provenance_refs=provenance,
                    ),
                )
                _rel(
                    relationships,
                    domain_id,
                    process_id,
                    "encodes-process-fragment",
                    "go-roast decoded a machine-fragment and 16-bit PID pair from the OAST XID.",
                    confidence,
                    ("PIDs wrap, are truncated, and are not globally unique.",),
                    provenance,
                )
    return tuple(sorted(nodes.values(), key=lambda item: item.id)), tuple(
        sorted(relationships.values(), key=lambda item: (item.source, item.target, item.relationship))
    )


def _rel(
    relationships: dict[tuple[str, str, str], AnalysisRelationshipProposal],
    source: str,
    target: str,
    relationship: str,
    rationale: str,
    confidence: str,
    caveats: tuple[str, ...],
    provenance: tuple[str, ...],
) -> None:
    relationships[(source, target, relationship)] = AnalysisRelationshipProposal(
        source=source,
        target=target,
        relationship=relationship,
        rationale=rationale,
        confidence=confidence,
        caveats=caveats,
        provenance_refs=provenance,
    )


def _id(kind: str, value: str) -> str:
    digest = hashlib.sha256(f"{kind}\0{value}".encode()).hexdigest()[:24]
    return f"roast-{kind}:{digest}"
