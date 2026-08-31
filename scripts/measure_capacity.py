#!/usr/bin/env python3
"""Produce a reproducible local Pivotglass capacity receipt.

The benchmark uses reserved synthetic values and opens no network connection.
Timings are descriptive measurements for the current machine, not universal
performance promises. Product limits are read from the same constants used by
the visualization and document authorities.
"""

from __future__ import annotations

import argparse
import json
import platform
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any

from stix2 import DomainName, Relationship

from adversary_pursuit.agent.tools import ToolContext
from adversary_pursuit.core.document_entity_extraction import EntityExtractionLimits
from adversary_pursuit.core.document_ingestion import DocumentLimits
from adversary_pursuit.core.visualization import (
    MAX_RELATIONSHIP_GRAPH_NODES,
    MAX_VISUALIZATION_ROWS,
)
from adversary_pursuit.core.workspace_admin import export_workspace
from adversary_pursuit.web.server import WebCockpitService


def _measure(operation: Callable[[], Any]) -> tuple[Any, dict[str, float]]:
    tracemalloc.start()
    started = time.perf_counter()
    result = operation()
    elapsed = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, {
        "elapsed_seconds": round(elapsed, 6),
        "peak_python_mib": round(peak / 1_048_576, 3),
    }


def _service(root: Path) -> WebCockpitService:
    return WebCockpitService(
        ToolContext(
            config_dir=root / "config",
            workspace_dir=root / "workspaces",
        )
    )


def _storage_scenario(root: Path, entity_count: int) -> dict[str, Any]:
    service, startup = _measure(lambda: _service(root))

    def ingest() -> int:
        stored = 0
        for offset in range(0, entity_count, 500):
            objects = [
                DomainName(value=f"capacity-{index:06d}.example")
                for index in range(offset, min(offset + 500, entity_count))
            ]
            stored += service.ctx.workspace_mgr.store_stix_objects(
                objects,
                module_name="capacity/offline-fixture",
                target=f"entities-{offset}-{offset + len(objects) - 1}",
                fetched_at="2026-08-31T00:00:00Z",
                source_dependence_group="capacity-fixture",
            )
        return stored

    stored, ingest_measurement = _measure(ingest)
    state, state_measurement = _measure(service.state)
    exported, export_measurement = _measure(
        lambda: export_workspace(service.ctx.workspace_mgr, "default")
    )
    state_json, state_json_measurement = _measure(
        lambda: json.dumps(state, default=str, separators=(",", ":")).encode("utf-8")
    )
    export_json, export_json_measurement = _measure(
        lambda: json.dumps(exported, default=str, separators=(",", ":")).encode("utf-8")
    )
    constellation = next(
        intent
        for intent in state["visualizations"]
        if intent["intent_id"] == "indicator-constellation"
    )
    return {
        "requested_entities": entity_count,
        "stored_entities": stored,
        "workspace_bytes": (root / "workspaces" / "default.db").stat().st_size,
        "cockpit_objects": len(state["objects"]),
        "constellation_rows": len(constellation["data"]["rows"]),
        "constellation_omitted": constellation["missing_data"]["omitted_count"],
        "cockpit_json_bytes": len(state_json),
        "workspace_export_json_bytes": len(export_json),
        "startup": startup,
        "ingest": ingest_measurement,
        "cockpit_state": state_measurement,
        "cockpit_json": state_json_measurement,
        "workspace_export": export_measurement,
        "workspace_export_json": export_json_measurement,
    }


def _graph_scenario(root: Path, node_count: int) -> dict[str, Any]:
    service = _service(root)
    nodes = [DomainName(value=f"graph-{index:06d}.example") for index in range(node_count)]
    relationships = [
        Relationship(
            source_ref=nodes[index].id,
            target_ref=nodes[index + 1].id,
            relationship_type="related-to",
        )
        for index in range(max(0, node_count - 1))
    ]
    stored, ingest_measurement = _measure(
        lambda: service.ctx.workspace_mgr.store_stix_objects(
            [*nodes, *relationships],
            module_name="capacity/offline-graph-fixture",
            target=f"graph-chain-{node_count}",
            fetched_at="2026-08-31T00:00:00Z",
            source_dependence_group="capacity-fixture",
        )
    )
    state, state_measurement = _measure(service.state)
    graph = next(
        intent for intent in state["visualizations"] if intent["intent_id"] == "relationship-graph"
    )
    return {
        "requested_nodes": node_count,
        "stored_records": stored,
        "visible_nodes": len(graph["data"]["nodes"]),
        "visible_edges": len(graph["data"]["edges"]),
        "exact_table_rows": len(graph["data"]["rows"]),
        "omitted_records": graph["missing_data"]["omitted_count"],
        "ingest": ingest_measurement,
        "cockpit_state": state_measurement,
    }


def measure_capacity(storage_entities: int, graph_nodes: int) -> dict[str, Any]:
    """Measure bounded storage and connected-graph scenarios."""

    if storage_entities < 1 or graph_nodes < 2:
        raise ValueError("storage entities must be positive and graph nodes must be at least two")
    with tempfile.TemporaryDirectory(prefix="pivotglass-capacity-") as temporary:
        root = Path(temporary)
        storage = _storage_scenario(root / "storage", storage_entities)
        graph = _graph_scenario(root / "graph", graph_nodes)
    parser_limits = DocumentLimits()
    extraction_limits = EntityExtractionLimits()
    return {
        "schema": "pivotglass-capacity-receipt-1.0",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "enforced_limits": {
            "raw_document_bytes": parser_limits.max_bytes,
            "parser_output_characters": parser_limits.max_output_chars,
            "entity_candidates": extraction_limits.max_candidates,
            "visualization_records": MAX_VISUALIZATION_ROWS,
            "relationship_graph_nodes": MAX_RELATIONSHIP_GRAPH_NODES,
        },
        "storage": storage,
        "connected_graph": graph,
        "interpretation": (
            "Timings and traced Python allocations describe this run only. The release "
            "envelope is defined by enforced limits and the conservative qualified sizes "
            "published in docs/CAPACITY.md."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-entities", type=int, default=5_000)
    parser.add_argument("--graph-nodes", type=int, default=1_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = measure_capacity(args.storage_entities, args.graph_nodes)
    content = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
