"""Capacity measurements are reproducible and read product limits from authorities."""

from __future__ import annotations

from adversary_pursuit.core.visualization import (
    MAX_RELATIONSHIP_GRAPH_NODES,
    MAX_VISUALIZATION_ROWS,
)
from scripts.measure_capacity import measure_capacity


def test_capacity_receipt_runs_offline_synthetic_scenarios() -> None:
    receipt = measure_capacity(storage_entities=25, graph_nodes=12)

    assert receipt["schema"] == "pivotglass-capacity-receipt-1.0"
    assert receipt["enforced_limits"]["visualization_records"] == MAX_VISUALIZATION_ROWS
    assert receipt["enforced_limits"]["relationship_graph_nodes"] == (MAX_RELATIONSHIP_GRAPH_NODES)
    assert receipt["storage"]["stored_entities"] == 25
    assert receipt["storage"]["cockpit_objects"] == 25
    assert receipt["storage"]["constellation_omitted"] == 0
    assert receipt["connected_graph"]["stored_records"] == 23
    assert receipt["connected_graph"]["visible_nodes"] == 12
    assert receipt["connected_graph"]["visible_edges"] == 11
    assert receipt["connected_graph"]["omitted_records"] == 0
    assert receipt["storage"]["cockpit_state"]["elapsed_seconds"] >= 0
    assert receipt["connected_graph"]["cockpit_state"]["peak_python_mib"] >= 0
