"""Versioned Synapse model contract and non-executing shadow migration plans."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from adversary_pursuit.integrations.synapse_graph import (
    SynapseManifestNode,
    SynapseShadowManifest,
)

_NATIVE_FORMS = frozenset(
    {
        "hash:md5",
        "hash:sha1",
        "hash:sha256",
        "hash:sha512",
        "inet:email",
        "inet:fqdn",
        "inet:ipv4",
        "inet:ipv6",
        "inet:url",
    }
)


class SynapseModelContract(BaseModel):
    """Pinned CoreModule-style data model required by Pivotglass migration."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-synapse-model-contract-1.0"] = (
        "pivotglass-synapse-model-contract-1.0"
    )
    model_name: Literal["pivotglass"] = "pivotglass"
    model_version: Literal["1.0.0"] = "1.0.0"
    model_definition: dict[str, Any]
    digest_sha256: str


class SynapseStormOperation(BaseModel):
    """One parameterized Storm mutation or exact readback in a disabled plan."""

    model_config = ConfigDict(frozen=True)

    operation_id: str
    phase: Literal["write", "readback"]
    query: str
    variables: dict[str, Any]
    opts: dict[str, Any]
    depends_on: tuple[str, ...] = ()
    manifest_ref: str
    description: str


class SynapseMigrationPlan(BaseModel):
    """Reviewable shadow-load DAG that does not enable remote mutation."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-synapse-migration-plan-1.0"] = (
        "pivotglass-synapse-migration-plan-1.0"
    )
    workspace: str
    manifest_digest_sha256: str
    model_digest_sha256: str
    operations: tuple[SynapseStormOperation, ...]
    digest_sha256: str
    approval_required: Literal[True] = True
    execution_enabled: Literal[False] = False
    storm_validation_required: Literal[True] = True
    isolated_shadow_view_required: Literal[True] = True
    backup_required: Literal[True] = True
    readback_required: Literal[True] = True


def pivotglass_synapse_model_contract() -> SynapseModelContract:
    """Return the exact custom forms used for records and evidence-rich edges."""
    definition = {
        "types": [
            [
                "pivotglass:record",
                ["str", {"strip": True}],
                {"doc": "A stable Pivotglass governed-record identifier."},
            ],
            [
                "pivotglass:edge",
                ["guid", {}],
                {"doc": "A provenance-bearing Pivotglass graph relationship."},
            ],
        ],
        "forms": [
            [
                "pivotglass:record",
                {},
                [
                    _prop("workspace", "str", "The originating Pivotglass workspace."),
                    _prop("source:snapshot", "str", "The source graph snapshot SHA-256."),
                    _prop("source:value", "str", "The source manifest value."),
                    _prop("node", "ndef", "The corresponding native Synapse node, when any."),
                    _array_prop("layers", "str", "Source graph layers."),
                    _array_prop("kinds", "str", "Source graph entity or record kinds."),
                    _array_prop("labels", "str", "Source display labels."),
                    _array_prop("record:refs", "str", "Authoritative Pivotglass record references."),
                    _array_prop("states", "str", "Source record states and dispositions."),
                    _array_prop("source:node:ids", "str", "Source graph node identifiers."),
                ],
            ],
            [
                "pivotglass:edge",
                {},
                [
                    _prop("workspace", "str", "The originating Pivotglass workspace."),
                    _prop("source:snapshot", "str", "The source graph snapshot SHA-256."),
                    _prop("manifest:ref", "str", "The stable source manifest edge identifier."),
                    _prop("source", "ndef", "The directional source node definition."),
                    _prop("target", "ndef", "The directional target node definition."),
                    _prop("relationship", "str", "The typed Pivotglass relationship."),
                    _prop("truth:kind", "str", "Observed, derived, asserted, or structural truth class."),
                    _array_prop("provenance:refs", "str", "Immutable provenance references."),
                    _prop("rationale", "str", "Why this relationship exists."),
                    _prop("directed", "bool", "Whether the relationship is directional."),
                ],
            ],
        ],
    }
    content = {
        "schema_version": "pivotglass-synapse-model-contract-1.0",
        "model_name": "pivotglass",
        "model_version": "1.0.0",
        "model_definition": definition,
    }
    return SynapseModelContract(
        model_definition=definition,
        digest_sha256=_digest(content),
    )


def compile_synapse_migration_plan(
    manifest: SynapseShadowManifest,
) -> SynapseMigrationPlan:
    """Compile bound-variable Storm writes/readbacks without running them."""
    model = pivotglass_synapse_model_contract()
    writes: list[SynapseStormOperation] = []
    node_by_id = {node.id: node for node in manifest.nodes}
    node_dependency: dict[str, str] = {}

    for node in manifest.nodes:
        if node.form not in _NATIVE_FORMS and node.form != "pivotglass:record":
            raise ValueError(f"unsupported Synapse manifest form: {node.form}")
        native_operation: str | None = None
        if node.form in _NATIVE_FORMS:
            native_operation = _operation_id("native", node.id)
            writes.append(
                SynapseStormOperation(
                    operation_id=native_operation,
                    phase="write",
                    query=f"[ {node.form}=$pivotglass_value ]",
                    variables={"pivotglass_value": node.value},
                    opts={"readonly": False},
                    manifest_ref=node.id,
                    description=f"Ensure native Synapse node {node.form} exists in the shadow view.",
                )
            )
        record_operation = _operation_id("record", node.id)
        record_variables = {
            "record_id": node.id,
            "workspace": manifest.workspace,
            "source_snapshot": manifest.source_snapshot_sha256,
            "source_value": node.value,
            "layers": list(node.properties.get("pivotglass:layers", [])),
            "kinds": list(node.properties.get("pivotglass:kinds", [])),
            "labels": list(node.properties.get("pivotglass:labels", [])),
            "record_refs": list(node.properties.get("pivotglass:record_refs", [])),
            "states": list(node.properties.get("pivotglass:states", [])),
            "source_node_ids": list(node.source_node_ids),
        }
        node_clause = ""
        if node.form in _NATIVE_FORMS:
            node_clause = " :node=$source_node"
            record_variables["source_node"] = [node.form, node.value]
        writes.append(
            SynapseStormOperation(
                operation_id=record_operation,
                phase="write",
                query=(
                    "[ pivotglass:record=$record_id :workspace=$workspace "
                    ":source:snapshot=$source_snapshot :source:value=$source_value"
                    f"{node_clause} :layers=$layers :kinds=$kinds :labels=$labels "
                    ":record:refs=$record_refs :states=$states "
                    ":source:node:ids=$source_node_ids ]"
                ),
                variables=record_variables,
                opts={"readonly": False},
                depends_on=(native_operation,) if native_operation else (),
                manifest_ref=node.id,
                description="Create the governed Pivotglass companion record in the shadow view.",
            )
        )
        node_dependency[node.id] = record_operation

    for edge in manifest.edges:
        source_node = node_by_id.get(edge.source)
        target_node = node_by_id.get(edge.target)
        if source_node is None or target_node is None:
            raise ValueError("Synapse manifest edge references an unknown node")
        operation_id = _operation_id("edge", edge.id)
        writes.append(
            SynapseStormOperation(
                operation_id=operation_id,
                phase="write",
                query=(
                    "[ pivotglass:edge=$edge_guid :workspace=$workspace "
                    ":source:snapshot=$source_snapshot :manifest:ref=$manifest_ref "
                    ":source=$source :target=$target :relationship=$relationship "
                    ":truth:kind=$truth_kind :provenance:refs=$provenance_refs "
                    ":rationale=$rationale :directed=$directed ]"
                ),
                variables={
                    "edge_guid": _guid(edge.id),
                    "workspace": manifest.workspace,
                    "source_snapshot": manifest.source_snapshot_sha256,
                    "manifest_ref": edge.id,
                    "source": list(_node_ndef(source_node)),
                    "target": list(_node_ndef(target_node)),
                    "relationship": edge.relationship,
                    "truth_kind": edge.truth_kind,
                    "provenance_refs": list(edge.provenance_refs),
                    "rationale": edge.rationale,
                    "directed": edge.directed,
                },
                opts={"readonly": False},
                depends_on=tuple(
                    sorted((node_dependency[edge.source], node_dependency[edge.target]))
                ),
                manifest_ref=edge.id,
                description="Create one evidence-rich relationship node in the shadow view.",
            )
        )

    operations = list(writes)
    for write in writes:
        if write.operation_id.startswith("synapse-native-"):
            query = write.query.strip("[] ")
            variables = dict(write.variables)
        elif write.operation_id.startswith("synapse-record-"):
            query = "pivotglass:record=$record_id"
            variables = {"record_id": write.variables["record_id"]}
        else:
            query = "pivotglass:edge=$edge_guid"
            variables = {"edge_guid": write.variables["edge_guid"]}
        operations.append(
            SynapseStormOperation(
                operation_id=_operation_id("readback", write.operation_id),
                phase="readback",
                query=query,
                variables=variables,
                opts={"readonly": True},
                depends_on=(write.operation_id,),
                manifest_ref=write.manifest_ref,
                description=f"Read back and reconcile {write.manifest_ref} from the shadow view.",
            )
        )

    content = {
        "schema_version": "pivotglass-synapse-migration-plan-1.0",
        "workspace": manifest.workspace,
        "manifest_digest_sha256": manifest.digest_sha256,
        "model_digest_sha256": model.digest_sha256,
        "operations": [operation.model_dump(mode="json") for operation in operations],
    }
    return SynapseMigrationPlan(
        workspace=manifest.workspace,
        manifest_digest_sha256=manifest.digest_sha256,
        model_digest_sha256=model.digest_sha256,
        operations=tuple(operations),
        digest_sha256=_digest(content),
    )


def _prop(name: str, type_name: str, doc: str) -> list[Any]:
    return [name, [type_name, {}], {"doc": doc}]


def _array_prop(name: str, item_type: str, doc: str) -> list[Any]:
    return [name, ["array", {"type": item_type, "uniq": True, "sorted": True}], {"doc": doc}]


def _node_ndef(node: SynapseManifestNode) -> tuple[str, str]:
    if node.form in _NATIVE_FORMS:
        return node.form, node.value
    return "pivotglass:record", node.id


def _operation_id(action: str, value: str) -> str:
    return f"synapse-{action}-{_digest(value)[:24]}"


def _guid(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
