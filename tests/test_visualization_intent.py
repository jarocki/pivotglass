"""Tests for the deterministic Pivotglass visualization authority."""

from __future__ import annotations

import pytest

from adversary_pursuit.core.investigation import (
    ContentClass,
    EventClass,
    InvestigationStore,
    LifecycleState,
)
from adversary_pursuit.core.visualization import (
    MAX_VISUALIZATION_ROWS,
    VISUALIZATION_POLICIES,
    VisualizationData,
    VisualizationQuestion,
    VisualizationRenderer,
    VisualizationView,
    activity_concentration_intent,
    dossier_completeness_intent,
    evidence_composition_intent,
    indicator_constellation_intent,
    relationship_graph_intent,
    task_matrix_intent,
    visualization_policy,
)


def test_every_supported_question_has_one_deterministic_policy():
    assert set(VISUALIZATION_POLICIES) == set(VisualizationQuestion)
    assert visualization_policy(
        VisualizationQuestion.ACTIVITY_CONCENTRATION
    ).view == VisualizationView.CALENDAR_HEATMAP
    assert visualization_policy(
        VisualizationQuestion.DOSSIER_COMPLETENESS
    ).renderer == VisualizationRenderer.FLINT_CHARTJS
    assert visualization_policy(
        VisualizationQuestion.ENTITY_RELATIONSHIPS
    ).view == VisualizationView.RELATIONSHIP_GRAPH
    assert visualization_policy(
        VisualizationQuestion.TASK_STATUS
    ).view == VisualizationView.TASK_MATRIX


def test_visualization_data_is_bounded():
    with pytest.raises(ValueError, match="record limit"):
        VisualizationData(rows=tuple({"value": index} for index in range(MAX_VISUALIZATION_ROWS + 1)))


def test_evidence_composition_counts_only_stored_object_types():
    intent = evidence_composition_intent(
        "case-red",
        [
            {"type": "domain-name", "value": "one.test"},
            {"type": "ipv4-addr", "value": "198.51.100.8"},
            {"type": "domain-name", "value": "two.test"},
        ],
    )

    assert intent.view == VisualizationView.BAR
    assert intent.source_scope.workspace == "case-red"
    assert intent.source_scope.record_count == 3
    assert intent.data.rows == (
        {"evidence_type": "domain-name", "count": 2},
        {"evidence_type": "ipv4-addr", "count": 1},
    )


def test_dossier_radar_keeps_deferred_facets_out_of_numeric_shape():
    intent = dossier_completeness_intent(
        "default",
        [
            {"name": "identity", "status": "filled", "evidence_count": 3},
            {"name": "ttps", "status": "partial", "evidence_count": 1},
            {"name": "timing", "status": "deferred", "evidence_count": 0},
        ],
    )

    assert [row["score"] for row in intent.data.rows] == [100, 50, None]
    assert intent.missing_data.omitted_count == 1
    assert "not a confidence score" in intent.caveats[-1]


def test_activity_calendar_uses_authoritative_utc_event_dates():
    intent = activity_concentration_intent(
        "default",
        [
            {
                "events": [
                    {"created_at": "2026-07-29T23:59:00+00:00"},
                    {"created_at": "2026-07-29T23:59:30+00:00"},
                    {"created_at": "2026-07-30T00:00:00+00:00"},
                ]
            }
        ],
    )

    assert intent.source_scope.timezone == "UTC"
    assert intent.data.rows == (
        {"date": "2026-07-29", "count": 2},
        {"date": "2026-07-30", "count": 1},
    )


def test_task_matrix_keeps_one_latest_lifecycle_per_indicator_enrichment():
    store = InvestigationStore()
    record = store.create("suspect.test", "domain-name")
    store.append(
        record.investigation_id,
        event_class=EventClass.SYSTEM,
        severity="info",
        lifecycle=LifecycleState.QUEUED,
        content_class=ContentClass.SYSTEM,
        tool="virustotal_lookup",
    )
    store.append(
        record.investigation_id,
        event_class=EventClass.DISCOVERY,
        severity="info",
        lifecycle=LifecycleState.SUCCEEDED,
        content_class=ContentClass.EVIDENCE,
        tool="virustotal_lookup",
    )

    intent = task_matrix_intent("default", store.snapshots())

    assert len(intent.data.rows) == 1
    assert intent.data.rows[0]["indicator"] == "suspect.test"
    assert intent.data.rows[0]["enrichment"] == "virustotal_lookup"
    assert intent.data.rows[0]["status"] == "succeeded"
    assert intent.data.rows[0]["event_sequence"] == 2


def test_indicator_constellation_is_persistent_newest_first_and_relation_aware():
    objects = [
        {
            "id": "domain-name--older",
            "type": "domain-name",
            "value": "older.test",
            "first_seen": "2026-06-01T00:00:00Z",
            "last_seen": "2026-06-02T00:00:00Z",
        },
        {
            "id": "ipv4-addr--newer",
            "type": "ipv4-addr",
            "value": "198.51.100.8",
            "first_seen": "2026-07-01T00:00:00Z",
            "last_seen": "2026-07-29T00:00:00Z",
        },
    ]
    intent = indicator_constellation_intent(
        "case-red",
        objects,
        {
            "nodes": [
                {"id": item["id"], "type": item["type"], "value": item["value"]}
                for item in objects
            ],
            "edges": [
                {
                    "source": "domain-name--older",
                    "target": "ipv4-addr--newer",
                    "relationship": "resolves-to",
                    "basis": "explicit",
                }
            ],
        },
    )

    assert intent.intent_id == "indicator-constellation"
    assert intent.source_scope.record_count == 2
    assert len(intent.data.rows) == 18
    assert [row["indicator"] for row in intent.data.rows[::9]] == [
        "198.51.100.8",
        "older.test",
    ]
    assert [row["dimension"] for row in intent.data.rows[:9]] == [
        "identity",
        "ttps",
        "infrastructure",
        "timing",
        "targeting",
        "capability",
        "motivation",
        "predictions",
        "denial",
    ]
    infrastructure = intent.data.rows[2]
    assert infrastructure["status"] == "filled"
    assert infrastructure["evidence_count"] == 2
    assert infrastructure["completeness_percent"] == 14
    assert infrastructure["related_to"] == ["older.test"]
    assert infrastructure["reference"].startswith("ev-")
    assert "ipv4-addr--newer" not in str(intent.data.rows)
    assert "not analytical confidence" in intent.caveats[1]


def test_relationship_graph_exposes_actual_labels_and_edge_basis():
    intent = relationship_graph_intent(
        "default",
        {
            "nodes": [
                {"id": "domain-name--one", "type": "domain-name", "value": "suspect.test"},
                {"id": "ipv4-addr--one", "type": "ipv4-addr", "value": "198.51.100.8"},
            ],
            "edges": [
                {
                    "source": "domain-name--one",
                    "target": "ipv4-addr--one",
                    "relationship": "resolves-to",
                    "basis": "explicit",
                }
            ],
        },
    )

    assert [node.label for node in intent.data.nodes] == ["suspect.test", "198.51.100.8"]
    assert intent.data.rows[0]["source"] == "suspect.test"
    assert intent.data.rows[0]["target"] == "198.51.100.8"
    assert intent.semantic_types["source"] == "Name"
    assert [column.label for column in intent.table_columns[:3]] == [
        "Source indicator",
        "Relationship",
        "Target indicator",
    ]
    assert intent.data.edges[0].provenance == "Stored STIX relationship"
    assert intent.data.edges[0].basis == "explicit"


def test_relationship_graph_drops_edges_whose_nodes_are_not_in_scope():
    intent = relationship_graph_intent(
        "default",
        {
            "nodes": [{"id": "domain-name--one", "type": "domain-name", "value": "one.test"}],
            "edges": [
                {
                    "source": "domain-name--one",
                    "target": "domain-name--missing",
                    "relationship": "related-to",
                    "basis": "explicit",
                }
            ],
        },
    )

    assert intent.data.edges == ()
    assert intent.data.rows == ()
