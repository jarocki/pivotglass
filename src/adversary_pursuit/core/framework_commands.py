"""Shared deterministic commands for evidence-backed framework perspectives.

Both terminal interfaces call this adapter. It never downloads framework
content and never asks a model to manufacture a mapping. Human-authored
mappings must name immutable observation IDs; model and automated proposals
use the lower-level authority and remain proposed until explicitly reviewed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from adversary_pursuit.core.analytic_ledger import AnalyticLedger, ConfidenceLevel
from adversary_pursuit.core.framework_perspectives import (
    ATTACK_ENTERPRISE_V19_2,
    DIAMOND_VERSION,
    KILL_CHAIN_VERSION,
    AttackCatalog,
    AttackContentManifest,
    build_attack_navigator_layer,
    build_attack_perspective,
)
from adversary_pursuit.core.framework_projections import (
    Framework,
    FrameworkProjectionAuthority,
    MappingOrigin,
    MappingState,
)
from adversary_pursuit.core.information_requirements import validate_requirement_criteria

FRAMEWORK_USAGE = (
    "Usage: framework list [attack|kill_chain|diamond]|manifest|"
    "show <attack|kill_chain|diamond> [version]|"
    "map <framework> <version> <content-id> <observation-id[,observation-id...]> "
    "| <label> | <basis> | <low|moderate|high> | <confidence rationale>|"
    "require <framework> <version> <content-id> | <label> | <requirement> | <factor-json>|"
    "gaps|"
    "accept|reject <mapping-id> | <review note>|revoke <mapping-id> | <reason>|navigator"
)

DEFAULT_FRAMEWORK_VERSIONS: dict[Framework, str] = {
    Framework.ATTACK: ATTACK_ENTERPRISE_V19_2.version,
    Framework.KILL_CHAIN: KILL_CHAIN_VERSION,
    Framework.DIAMOND: DIAMOND_VERSION,
}


def default_attack_catalog_path() -> Path:
    """Return the documented operator-managed ATT&CK content location."""

    return Path.home() / ".ap" / "frameworks" / "enterprise-attack-19.2.json"


def execute_framework_command(
    args: tuple[str, ...],
    workspace_manager: Any,
    *,
    attack_catalog_path: Path | None = None,
    attack_manifest: AttackContentManifest = ATTACK_ENTERPRISE_V19_2,
) -> dict[str, Any]:
    """Execute one local framework command and return a structured result."""

    authority = FrameworkProjectionAuthority(workspace_manager)
    action = args[0].casefold() if args else "list"

    if action == "manifest":
        return {
            "title": "Framework content manifest",
            "data": {
                "attack": attack_manifest.model_dump(mode="json"),
                "local_path": str(attack_catalog_path or default_attack_catalog_path()),
                "download_policy": (
                    "Operator-managed; Pivotglass does not silently download or update content."
                ),
                "kill_chain_version": KILL_CHAIN_VERSION,
                "diamond_version": DIAMOND_VERSION,
            },
        }

    if action == "list":
        framework = _framework(args[1]) if len(args) == 2 else None
        if len(args) > 2:
            raise ValueError(FRAMEWORK_USAGE)
        mappings = authority.list(framework=framework)
        return {
            "title": "Framework mappings",
            "data": {
                "schema_version": "framework-mappings-1.0",
                "mappings": [mapping.model_dump(mode="json") for mapping in mappings],
            },
        }

    if action == "show" and len(args) in {2, 3}:
        framework = _framework(args[1])
        version = args[2] if len(args) == 3 else DEFAULT_FRAMEWORK_VERSIONS[framework]
        projection = authority.projection(framework, framework_version=version)
        return {
            "title": f"{framework.value.replace('_', ' ').title()} perspective",
            "data": projection.model_dump(mode="json"),
        }

    if action == "map":
        fields = _pipe_fields(args[1:], expected=5)
        heading = fields[0].split()
        if len(heading) != 4:
            raise ValueError(FRAMEWORK_USAGE)
        framework, version, content_id, observation_ids = heading
        refs = tuple(ref.strip() for ref in observation_ids.split(",") if ref.strip())
        mapping = authority.propose(
            framework=_framework(framework),
            framework_version=version,
            content_id=content_id,
            content_label=fields[1],
            evidence_refs=refs,
            basis=fields[2],
            mapper="human-analyst",
            mapper_version="1.0",
            origin=MappingOrigin.HUMAN,
            confidence=_confidence(fields[3]),
            confidence_rationale=fields[4],
        )
        return {
            "title": "Framework mapping proposed",
            "data": mapping.model_dump(mode="json"),
        }

    if action == "require":
        fields = _pipe_fields(args[1:], expected=4)
        heading = fields[0].split()
        if len(heading) != 3:
            raise ValueError(FRAMEWORK_USAGE)
        framework, version, content_id = heading
        framework_value = _framework(framework)
        accepted = any(
            mapping.framework_version == version
            and mapping.content_id == content_id
            and mapping.state is MappingState.ACCEPTED
            for mapping in authority.list(framework=framework_value)
        )
        if accepted:
            raise ValueError(
                f"{content_id} already has an accepted evidence-backed "
                f"{framework_value.value} mapping; it is not a framework gap."
            )
        criteria = validate_requirement_criteria(
            _json_object(fields[3], "framework requirement factors")
        )
        framework_ref = {
            "kind": "framework_content",
            "id": f"{framework_value.value}:{version}:{content_id}",
            "framework": framework_value.value,
            "version": version,
            "content_id": content_id,
            "label": fields[1],
        }
        addresses = list(criteria.get("addresses", []))
        if not any(
            ref.get("kind") == framework_ref["kind"] and ref.get("id") == framework_ref["id"]
            for ref in addresses
        ):
            addresses.append(framework_ref)
        criteria["addresses"] = addresses
        requirement, created = AnalyticLedger(workspace_manager).create_framework_gap_requirement(
            framework=framework_value.value,
            framework_version=version,
            content_id=content_id,
            statement=fields[2],
            criteria=criteria,
        )
        return {
            "title": (
                "Framework intelligence requirement recorded"
                if created
                else "Framework intelligence requirement already recorded"
            ),
            "data": {
                "item_id": requirement["id"],
                "created": created,
                "framework_gap": framework_ref,
                "criteria": requirement["criteria"],
                "content_class": "analyst_collection_requirement",
            },
        }

    if action == "gaps" and len(args) == 1:
        return {
            "title": "Framework intelligence requirements",
            "data": {
                "requirements": AnalyticLedger(workspace_manager).framework_gap_requirements(),
                "content_class": "analytic_planning",
            },
        }

    if action in {"accept", "reject"}:
        fields = _pipe_fields(args[1:], expected=2)
        if len(fields[0].split()) != 1:
            raise ValueError(FRAMEWORK_USAGE)
        state = MappingState.ACCEPTED if action == "accept" else MappingState.REJECTED
        mapping = authority.disposition(
            fields[0],
            state,
            analyst_override=fields[1],
        )
        return {
            "title": f"Framework mapping {state.value}",
            "data": mapping.model_dump(mode="json"),
        }

    if action == "revoke":
        fields = _pipe_fields(args[1:], expected=2)
        if len(fields[0].split()) != 1:
            raise ValueError(FRAMEWORK_USAGE)
        mapping = authority.disposition(
            fields[0],
            MappingState.REVOKED,
            revoked_reason=fields[1],
        )
        return {
            "title": "Framework mapping revoked",
            "data": mapping.model_dump(mode="json"),
        }

    if action == "navigator" and len(args) == 1:
        catalog_path = attack_catalog_path or default_attack_catalog_path()
        if not catalog_path.is_file():
            raise ValueError(
                f"ATT&CK 19.2 content is not installed at {catalog_path}. "
                "Run `framework manifest` for the pinned source URL and SHA-256 digest."
            )
        catalog = AttackCatalog.from_path(catalog_path, manifest=attack_manifest)
        perspective = build_attack_perspective(authority, catalog)
        return {
            "title": "ATT&CK Navigator layer",
            "filename": f"{workspace_manager.active}-attack-19.2.navigator.json",
            "mime": "application/json",
            "data": build_attack_navigator_layer(
                perspective,
                catalog,
                name=f"{workspace_manager.active} ATT&CK perspective",
                description="Evidence-backed Pivotglass framework mappings.",
            ),
        }

    raise ValueError(FRAMEWORK_USAGE)


def _framework(value: str) -> Framework:
    try:
        return Framework(value.casefold())
    except ValueError as exc:
        raise ValueError("Frameworks: attack, kill_chain, diamond.") from exc


def _confidence(value: str) -> ConfidenceLevel:
    try:
        return ConfidenceLevel(value.casefold())
    except ValueError as exc:
        raise ValueError("Confidence must be low, moderate, or high.") from exc


def _pipe_fields(args: tuple[str, ...], *, expected: int) -> list[str]:
    fields = [field.strip() for field in " ".join(args).split("|")]
    if len(fields) != expected or any(not field for field in fields):
        raise ValueError(FRAMEWORK_USAGE)
    return fields


def _json_object(value: str, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return parsed
