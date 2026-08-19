"""Version-pinned ATT&CK, Kill Chain, and Diamond Model perspectives.

The classes in this module are read-only views over
``FrameworkProjectionAuthority`` records.  They never create observations,
relationships, or confidence assessments.  Every displayed framework element
retains the mapping and evidence references that justify it.

ATT&CK content is loaded only from an operator-supplied local file and checked
against a pinned release manifest.  Runtime code never silently downloads a
moving dataset.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from adversary_pursuit.core.analytic_ledger import ConfidenceLevel
from adversary_pursuit.core.framework_projections import (
    Framework,
    FrameworkMapping,
    FrameworkProjectionAuthority,
    MappingState,
)


class AttackContentManifest(BaseModel):
    """An immutable pointer to one exact ATT&CK STIX collection."""

    model_config = ConfigDict(frozen=True)

    domain: str
    version: str
    source_url: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    collection_name: str
    navigator_layer_version: str
    navigator_version: str


ATTACK_ENTERPRISE_V19_2 = AttackContentManifest(
    domain="enterprise-attack",
    version="19.2",
    source_url=(
        "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/"
        "v19.2/enterprise-attack/enterprise-attack.json"
    ),
    sha256="dc1639caa5501d720e280cf1cbd8fbe009884a0c9b3e6e9ed9d0c25166c3d8f4",
    collection_name="Enterprise ATT&CK",
    navigator_layer_version="4.5",
    navigator_version="5.3.2",
)


class AttackTechnique(BaseModel):
    """The bounded ATT&CK fields needed for mapping and Navigator export."""

    model_config = ConfigDict(frozen=True)

    attack_id: str = Field(pattern=r"^T\d{4}(?:\.\d{3})?$")
    stix_id: str
    name: str
    tactics: tuple[str, ...]
    technique_version: str
    is_subtechnique: bool = False


class AttackTactic(BaseModel):
    model_config = ConfigDict(frozen=True)

    attack_id: str = Field(pattern=r"^TA\d{4}$")
    stix_id: str
    name: str
    shortname: str


class AttackCatalog(BaseModel):
    """A verified, minimal projection of a pinned ATT&CK collection."""

    model_config = ConfigDict(frozen=True)

    manifest: AttackContentManifest
    collection_modified: str
    tactics: tuple[AttackTactic, ...]
    techniques: tuple[AttackTechnique, ...]

    def technique(self, attack_id: str) -> AttackTechnique | None:
        normalized = attack_id.strip().upper()
        return next((item for item in self.techniques if item.attack_id == normalized), None)

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        manifest: AttackContentManifest = ATTACK_ENTERPRISE_V19_2,
    ) -> AttackCatalog:
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != manifest.sha256:
            raise ValueError(
                f"ATT&CK content digest mismatch: expected {manifest.sha256}, got {digest}"
            )
        payload = json.loads(raw)
        if payload.get("type") != "bundle" or not isinstance(payload.get("objects"), list):
            raise ValueError("ATT&CK content must be a STIX bundle with an objects list")
        objects = payload["objects"]
        collection = next(
            (
                item
                for item in objects
                if item.get("type") == "x-mitre-collection"
                and item.get("name") == manifest.collection_name
            ),
            None,
        )
        if collection is None:
            raise ValueError(f"ATT&CK collection {manifest.collection_name!r} is missing")
        if str(collection.get("x_mitre_version")) != manifest.version:
            raise ValueError(
                "ATT&CK collection version mismatch: "
                f"expected {manifest.version}, got {collection.get('x_mitre_version')}"
            )

        tactics = tuple(
            sorted(
                (
                    tactic
                    for item in objects
                    if (tactic := _attack_tactic(item, manifest.domain)) is not None
                ),
                key=lambda item: item.attack_id,
            )
        )
        techniques = tuple(
            sorted(
                (
                    technique
                    for item in objects
                    if (technique := _attack_technique(item, manifest.domain)) is not None
                ),
                key=lambda item: item.attack_id,
            )
        )
        return cls(
            manifest=manifest,
            collection_modified=str(collection.get("modified", "")),
            tactics=tactics,
            techniques=techniques,
        )


def _active_attack_object(item: Mapping[str, Any], object_type: str, domain: str) -> bool:
    return (
        item.get("type") == object_type
        and not item.get("revoked", False)
        and not item.get("x_mitre_deprecated", False)
        and domain in item.get("x_mitre_domains", ())
    )


def _external_id(item: Mapping[str, Any], pattern: re.Pattern[str]) -> str:
    for reference in item.get("external_references", ()):
        candidate = str(reference.get("external_id", "")).upper()
        if pattern.fullmatch(candidate):
            return candidate
    raise ValueError(f"ATT&CK object {item.get('id')} lacks a valid external identifier")


def _attack_tactic(item: Mapping[str, Any], domain: str) -> AttackTactic | None:
    if not _active_attack_object(item, "x-mitre-tactic", domain):
        return None
    attack_id = _external_id(item, re.compile(r"TA\d{4}"))
    return AttackTactic(
        attack_id=attack_id,
        stix_id=str(item["id"]),
        name=str(item["name"]),
        shortname=str(item.get("x_mitre_shortname", "")),
    )


def _attack_technique(item: Mapping[str, Any], domain: str) -> AttackTechnique | None:
    if not _active_attack_object(item, "attack-pattern", domain):
        return None
    attack_id = _external_id(item, re.compile(r"T\d{4}(?:\.\d{3})?"))
    tactics = tuple(
        dict.fromkeys(
            str(phase.get("phase_name", ""))
            for phase in item.get("kill_chain_phases", ())
            if phase.get("kill_chain_name") == "mitre-attack" and phase.get("phase_name")
        )
    )
    return AttackTechnique(
        attack_id=attack_id,
        stix_id=str(item["id"]),
        name=str(item["name"]),
        tactics=tactics,
        technique_version=str(item.get("x_mitre_version", "")),
        is_subtechnique=bool(item.get("x_mitre_is_subtechnique", False)),
    )


class AttackPerspective(BaseModel):
    model_config = ConfigDict(frozen=True)

    catalog_version: str
    collection_modified: str
    mappings: tuple[FrameworkMapping, ...]
    gaps: tuple[dict[str, str], ...]
    unknown_content_ids: tuple[str, ...]


def build_attack_perspective(
    authority: FrameworkProjectionAuthority,
    catalog: AttackCatalog,
    *,
    required_technique_ids: Iterable[str] = (),
) -> AttackPerspective:
    required = []
    unknown_required: list[str] = []
    for attack_id in dict.fromkeys(item.strip().upper() for item in required_technique_ids):
        technique = catalog.technique(attack_id)
        if technique is None:
            unknown_required.append(attack_id)
        else:
            required.append((technique.attack_id, technique.name))
    projection = authority.projection(
        Framework.ATTACK,
        framework_version=catalog.manifest.version,
        required_content=required,
    )
    unknown_mappings = tuple(
        sorted(
            mapping.content_id
            for mapping in projection.mappings
            if catalog.technique(mapping.content_id) is None
        )
    )
    return AttackPerspective(
        catalog_version=catalog.manifest.version,
        collection_modified=catalog.collection_modified,
        mappings=projection.mappings,
        gaps=tuple(gap.model_dump() for gap in projection.gaps),
        unknown_content_ids=tuple(sorted(set((*unknown_required, *unknown_mappings)))),
    )


_NAVIGATOR_COLORS: dict[MappingState, str] = {
    MappingState.ACCEPTED: "#4CAF50",
    MappingState.PROPOSED: "#F2C94C",
    MappingState.REJECTED: "#9E9E9E",
    MappingState.SUPERSEDED: "#6C7A89",
    MappingState.REVOKED: "#D9534F",
}


def build_attack_navigator_layer(
    perspective: AttackPerspective,
    catalog: AttackCatalog,
    *,
    name: str,
    description: str,
    include_nonaccepted: bool = True,
) -> dict[str, Any]:
    """Export a Navigator layer 4.5 with visible disposition and provenance."""

    techniques: list[dict[str, Any]] = []
    for mapping in perspective.mappings:
        technique = catalog.technique(mapping.content_id)
        if technique is None or (not include_nonaccepted and mapping.state is not MappingState.ACCEPTED):
            continue
        metadata = [
            {"name": "Mapping state", "value": mapping.state.value},
            {"name": "Confidence", "value": mapping.confidence.value},
            {"name": "Mapping ID", "value": mapping.id},
            {"name": "Evidence references", "value": ", ".join(mapping.evidence_refs)},
            {"name": "Mapper", "value": f"{mapping.mapper} {mapping.mapper_version}"},
        ]
        techniques.append(
            {
                "techniqueID": technique.attack_id,
                "color": _NAVIGATOR_COLORS[mapping.state],
                "comment": f"{mapping.basis}\nConfidence: {mapping.confidence_rationale}",
                "metadata": metadata,
                "enabled": True,
            }
        )
    techniques.sort(key=lambda item: item["techniqueID"])
    return {
        "name": name,
        "versions": {
            "attack": catalog.manifest.version,
            "navigator": catalog.manifest.navigator_version,
            "layer": catalog.manifest.navigator_layer_version,
        },
        "domain": catalog.manifest.domain,
        "description": description,
        "techniques": techniques,
        "legendItems": [
            {"label": state.value.title(), "color": color}
            for state, color in _NAVIGATOR_COLORS.items()
        ],
        "metadata": [
            {"name": "Pivotglass framework schema", "value": "framework-mappings-1.0"},
            {"name": "ATT&CK content digest", "value": catalog.manifest.sha256},
        ],
        "showTacticRowBackground": True,
        "tacticRowBackground": "#1b2330",
        "selectTechniquesAcrossTactics": True,
        "selectSubtechniquesWithParent": False,
        "layout": {"layout": "side", "aggregateFunction": "average", "showID": True},
    }


class KillChainPhase(StrEnum):
    RECONNAISSANCE = "reconnaissance"
    WEAPONIZATION = "weaponization"
    DELIVERY = "delivery"
    EXPLOITATION = "exploitation"
    INSTALLATION = "installation"
    COMMAND_AND_CONTROL = "command-and-control"
    ACTIONS_ON_OBJECTIVES = "actions-on-objectives"


class KillChainRelation(StrEnum):
    PRECEDES = "precedes"
    LOOPS_TO = "loops_to"
    PARALLEL_WITH = "parallel_with"
    AMBIGUOUS = "ambiguous"


class KillChainAssignment(BaseModel):
    model_config = ConfigDict(frozen=True)

    mapping_id: str
    phase: KillChainPhase
    evidence_refs: tuple[str, ...]
    basis: str
    confidence: ConfidenceLevel
    state: MappingState


class KillChainTransition(BaseModel):
    """An explicit event relationship; canonical phase order is never inferred."""

    model_config = ConfigDict(frozen=True)

    source_mapping_id: str
    target_mapping_id: str
    relation: KillChainRelation
    evidence_refs: tuple[str, ...]
    rationale: str = Field(min_length=1)

    @field_validator("evidence_refs")
    @classmethod
    def require_evidence(cls, refs: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(ref.strip() for ref in refs if ref.strip()))
        if not normalized:
            raise ValueError("kill-chain transitions require evidence references")
        return normalized


class KillChainPerspective(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    assignments: tuple[KillChainAssignment, ...]
    transitions: tuple[KillChainTransition, ...]
    unmapped_phases: tuple[KillChainPhase, ...]
    caveat: str


KILL_CHAIN_VERSION = "lockheed-martin-2011"


def build_kill_chain_perspective(
    authority: FrameworkProjectionAuthority,
    *,
    transitions: Iterable[KillChainTransition] = (),
) -> KillChainPerspective:
    projection = authority.projection(
        Framework.KILL_CHAIN,
        framework_version=KILL_CHAIN_VERSION,
    )
    assignments: list[KillChainAssignment] = []
    for mapping in projection.mappings:
        try:
            phase = KillChainPhase(mapping.content_id.removeprefix("kill-chain:"))
        except ValueError as exc:
            raise ValueError(f"Unknown Kill Chain phase mapping: {mapping.content_id}") from exc
        assignments.append(
            KillChainAssignment(
                mapping_id=mapping.id,
                phase=phase,
                evidence_refs=mapping.evidence_refs,
                basis=mapping.basis,
                confidence=mapping.confidence,
                state=mapping.state,
            )
        )
    by_id = {assignment.mapping_id for assignment in assignments}
    checked_transitions = tuple(transitions)
    for transition in checked_transitions:
        if transition.source_mapping_id not in by_id or transition.target_mapping_id not in by_id:
            raise ValueError("Kill Chain transition refers to an unknown mapping")
    mapped = {
        assignment.phase
        for assignment in assignments
        if assignment.state is MappingState.ACCEPTED
    }
    return KillChainPerspective(
        version=KILL_CHAIN_VERSION,
        assignments=tuple(assignments),
        transitions=checked_transitions,
        unmapped_phases=tuple(phase for phase in KillChainPhase if phase not in mapped),
        caveat=(
            "Phase order is a presentation aid, not a claim that activity was linear. "
            "Only explicit, evidence-backed transitions are shown."
        ),
    )


class DiamondVertex(StrEnum):
    ADVERSARY = "adversary"
    CAPABILITY = "capability"
    INFRASTRUCTURE = "infrastructure"
    VICTIM = "victim"


class DiamondVertexAssignment(BaseModel):
    model_config = ConfigDict(frozen=True)

    vertex: DiamondVertex
    value_ref: str
    mapping_id: str
    evidence_refs: tuple[str, ...]
    basis: str
    confidence: ConfidenceLevel


class DiamondMetaFeature(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    value: str = Field(min_length=1)
    evidence_refs: tuple[str, ...]

    @field_validator("evidence_refs")
    @classmethod
    def require_evidence(cls, refs: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(ref.strip() for ref in refs if ref.strip()))
        if not normalized:
            raise ValueError("Diamond meta-features require evidence references")
        return normalized


class DiamondEvent(BaseModel):
    """One event projected from accepted, evidence-backed vertex mappings."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(min_length=1)
    vertices: tuple[DiamondVertexAssignment, ...]
    unknown_vertices: tuple[DiamondVertex, ...]
    meta_features: tuple[DiamondMetaFeature, ...] = ()
    activity_thread: str | None = None
    activity_group: str | None = None
    confidence: ConfidenceLevel
    confidence_rationale: str = Field(min_length=1)
    provisional: bool

    @model_validator(mode="after")
    def one_assignment_per_vertex(self) -> DiamondEvent:
        vertices = [item.vertex for item in self.vertices]
        if len(vertices) != len(set(vertices)):
            raise ValueError("Diamond events permit only one assignment per core vertex")
        return self


DIAMOND_VERSION = "diamond-model-1.0"


def build_diamond_event(
    authority: FrameworkProjectionAuthority,
    *,
    event_id: str,
    mapping_ids: Iterable[str],
    confidence: ConfidenceLevel,
    confidence_rationale: str,
    meta_features: Iterable[DiamondMetaFeature] = (),
    activity_thread: str | None = None,
    activity_group: str | None = None,
) -> DiamondEvent:
    projection = authority.projection(
        Framework.DIAMOND,
        framework_version=DIAMOND_VERSION,
    )
    selected = {item for item in mapping_ids}
    available = {mapping.id: mapping for mapping in projection.mappings}
    missing = selected - available.keys()
    if missing:
        raise ValueError(f"Unknown Diamond mapping IDs: {', '.join(sorted(missing))}")
    assignments: list[DiamondVertexAssignment] = []
    provisional = False
    for mapping_id in sorted(selected):
        mapping = available[mapping_id]
        content = mapping.content_id.removeprefix("diamond:")
        vertex_name, separator, value_ref = content.partition(":")
        if not separator or not value_ref:
            raise ValueError(
                "Diamond content IDs must be diamond:<vertex>:<value-reference>"
            )
        try:
            vertex = DiamondVertex(vertex_name)
        except ValueError as exc:
            raise ValueError(f"Unknown Diamond vertex: {vertex_name}") from exc
        provisional = provisional or mapping.state is not MappingState.ACCEPTED
        assignments.append(
            DiamondVertexAssignment(
                vertex=vertex,
                value_ref=value_ref,
                mapping_id=mapping.id,
                evidence_refs=mapping.evidence_refs,
                basis=mapping.basis,
                confidence=mapping.confidence,
            )
        )
    known = {assignment.vertex for assignment in assignments}
    return DiamondEvent(
        event_id=event_id,
        vertices=tuple(assignments),
        unknown_vertices=tuple(vertex for vertex in DiamondVertex if vertex not in known),
        meta_features=tuple(meta_features),
        activity_thread=activity_thread,
        activity_group=activity_group,
        confidence=confidence,
        confidence_rationale=confidence_rationale,
        provisional=provisional,
    )
