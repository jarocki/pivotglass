#!/usr/bin/env python3
"""Validate Pivotglass's model and migration Storm against a disposable Cortex."""

from __future__ import annotations

import asyncio
import copy
import os
import tempfile

from adversary_pursuit.integrations.synapse_graph import (
    SynapseManifestEdge,
    SynapseManifestNode,
    SynapseShadowManifest,
)
from adversary_pursuit.integrations.synapse_migration import (
    compile_synapse_migration_plan,
    pivotglass_synapse_model_contract,
)

os.environ.setdefault("SYN_AXON_LIMIT_DISK_FREE", "0")

try:
    import synapse.axon as s_axon
    import synapse.cortex as s_cortex
except ImportError as exc:  # pragma: no cover - optional validation environment
    raise SystemExit(
        "Vertex Synapse is not installed. Run this script in a disposable "
        "Python 3.11+ environment containing the pinned Synapse checkout."
    ) from exc

# A disposable validation Cortex is intentionally tiny. Permit it to start on
# developer workstations whose free-space percentage is below Synapse's
# production default; this changes only the validator process.
s_cortex.Cortex.confbase["limit:disk:free"]["default"] = 0
s_axon.Axon.confbase["limit:disk:free"]["default"] = 0


async def _validate() -> None:
    contract = pivotglass_synapse_model_contract()
    manifest = SynapseShadowManifest(
        workspace="contract-validation",
        source_snapshot_sha256="1" * 64,
        nodes=(
            SynapseManifestNode(
                id="synapse-node-native",
                form="inet:fqdn",
                value="validation.example",
                source_node_ids=("entity:validation",),
                properties={
                    "pivotglass:layers": ["entity"],
                    "pivotglass:kinds": ["domain-name"],
                    "pivotglass:labels": ["validation.example"],
                    "pivotglass:record_refs": ["domain-name--validation"],
                    "pivotglass:states": [],
                },
            ),
            SynapseManifestNode(
                id="synapse-node-record",
                form="pivotglass:record",
                value="epistemic:question:validation",
                source_node_ids=("epistemic:question:validation",),
                properties={
                    "pivotglass:layers": ["epistemic"],
                    "pivotglass:kinds": ["question"],
                    "pivotglass:labels": ["What should validation prove?"],
                    "pivotglass:record_refs": ["question-validation"],
                    "pivotglass:states": ["open"],
                },
            ),
        ),
        edges=(
            SynapseManifestEdge(
                id="synapse-edge-validation",
                source="synapse-node-record",
                target="synapse-node-native",
                relationship="references",
                truth_kind="structural",
                provenance_refs=("question-validation",),
                rationale="Disposable validation relationship.",
                directed=True,
            ),
        ),
        digest_sha256="2" * 64,
    )
    plan = compile_synapse_migration_plan(manifest)
    with tempfile.TemporaryDirectory(prefix="pivotglass-synapse-") as directory:
        core = await s_cortex.Cortex.anit(
            directory,
            conf={"limit:disk:free": 0, "health:sysctl:checks": False},
        )
        try:
            core.model.addDataModels(
                [(contract.model_name, copy.deepcopy(contract.model_definition))]
            )
            for operation in plan.operations:
                nodes = await core.nodes(
                    operation.query,
                    opts={"vars": copy.deepcopy(operation.variables)},
                )
                if operation.phase == "readback" and not nodes:
                    raise RuntimeError(
                        f"Synapse readback returned no node for {operation.manifest_ref}"
                    )
        finally:
            await core.fini()
    print(
        "Validated Pivotglass Synapse model "
        f"{contract.model_version} ({contract.digest_sha256}) and "
        f"{len(plan.operations)} parameterized Storm operations."
    )


def main() -> None:
    asyncio.run(_validate())


if __name__ == "__main__":
    main()
