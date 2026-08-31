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
    competing_hypotheses_matrix_intent,
    dossier_completeness_intent,
    evidence_composition_intent,
    indicator_constellation_intent,
    indicator_coverage_pca_intent,
    recorded_uncertainty_intent,
    relationship_degree_distribution_intent,
    relationship_graph_intent,
    scientific_investigation_hierarchy_intent,
    task_matrix_intent,
    visualization_policy,
)


def test_every_supported_question_has_one_deterministic_policy():
    assert set(VISUALIZATION_POLICIES) == set(VisualizationQuestion)
    assert all(policy.selection_reason for policy in VISUALIZATION_POLICIES.values())
    assert all(policy.reading_guide for policy in VISUALIZATION_POLICIES.values())
    assert (
        visualization_policy(VisualizationQuestion.ACTIVITY_CONCENTRATION).view
        == VisualizationView.CALENDAR_HEATMAP
    )
    assert (
        visualization_policy(VisualizationQuestion.DOSSIER_COMPLETENESS).renderer
        == VisualizationRenderer.FLINT_CHARTJS
    )
    assert (
        visualization_policy(VisualizationQuestion.ENTITY_RELATIONSHIPS).view
        == VisualizationView.RELATIONSHIP_GRAPH
    )
    assert (
        visualization_policy(VisualizationQuestion.TASK_STATUS).view
        == VisualizationView.TASK_MATRIX
    )
    assert (
        "matrix"
        in visualization_policy(VisualizationQuestion.TASK_STATUS).selection_reason.casefold()
    )


def test_visualization_data_is_bounded():
    with pytest.raises(ValueError, match="record limit"):
        VisualizationData(
            rows=tuple({"value": index} for index in range(MAX_VISUALIZATION_ROWS + 1))
        )


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
                {"id": item["id"], "type": item["type"], "value": item["value"]} for item in objects
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


def test_indicator_coverage_pca_is_deterministic_and_never_imputes_deferred_facets():
    constellation = indicator_constellation_intent("case-red", [], {"nodes": [], "edges": []})
    profiles = (
        ("ev-one", "one.test", "domain-name", ("empty", "empty", "filled")),
        ("ev-two", "two.test", "domain-name", ("partial", "filled", "partial")),
        ("ev-three", "198.51.100.8", "ipv4-addr", ("filled", "partial", "empty")),
        ("ev-four", "203.0.113.9", "ipv4-addr", ("filled", "filled", "partial")),
    )
    rows = tuple(
        {
            "reference": reference,
            "indicator": indicator,
            "indicator_type": indicator_type,
            "dimension": dimension,
            "status": status,
        }
        for reference, indicator, indicator_type, statuses in profiles
        for dimension, status in zip(
            ("identity", "infrastructure", "timing"), statuses, strict=True
        )
    ) + tuple(
        {
            "reference": reference,
            "indicator": indicator,
            "indicator_type": indicator_type,
            "dimension": "predictions",
            "status": "deferred",
        }
        for reference, indicator, indicator_type, _statuses in profiles
    )
    constellation = constellation.model_copy(update={"data": VisualizationData(rows=rows)})

    first = indicator_coverage_pca_intent("case-red", constellation)
    second = indicator_coverage_pca_intent("case-red", constellation)

    assert first.view == VisualizationView.SCATTER
    assert first.renderer == VisualizationRenderer.FLINT_CHARTJS
    assert first.data.rows == second.data.rows
    assert len(first.data.rows) == 4
    assert {row["indicator"] for row in first.data.rows} == {
        "one.test",
        "two.test",
        "198.51.100.8",
        "203.0.113.9",
    }
    assert all("predictions=" not in row["feature_profile"] for row in first.data.rows)
    assert all("identity=" in row["feature_profile"] for row in first.data.rows)
    assert first.data.rows[0]["pc1_variance_percent"] > 0
    assert first.data.rows[0]["pc2_variance_percent"] >= 0
    assert "not a relationship" in first.caveats[-2]
    assert "predictions" in first.caveats[-1]


def test_indicator_coverage_pca_shows_empty_state_without_comparable_variation():
    constellation = indicator_constellation_intent("default", [], {"nodes": [], "edges": []})

    intent = indicator_coverage_pca_intent("default", constellation)

    assert intent.data.rows == ()
    assert intent.source_scope.record_count == 0
    assert "Insufficient comparable variation" in intent.caveats[-3]


def test_competing_hypotheses_matrix_shows_recorded_and_unassessed_stances():
    analysis = {
        "hypotheses": [
            {
                "id": "hypothesis-one",
                "statement": "The operator controls the relay.",
                "status": "retained",
                "created_at": "2026-08-24T10:00:00Z",
            },
            {
                "id": "hypothesis-two",
                "statement": "The relay is shared infrastructure.",
                "status": "proposed",
                "created_at": "2026-08-24T10:01:00Z",
            },
        ],
        "observations": [
            {
                "id": "observation-one",
                "entity_value": "relay.test",
            }
        ],
        "assertions": [
            {
                "id": "assertion-one",
                "statement": "The certificate appears on unrelated domains.",
            }
        ],
        "evidence_links": [
            {
                "source_kind": "observation",
                "source_id": "observation-one",
                "target_kind": "hypothesis",
                "target_id": "hypothesis-one",
                "stance": "supports",
                "rationale": "The relay was observed in the case.",
            },
            {
                "source_kind": "assertion",
                "source_id": "assertion-one",
                "target_kind": "hypothesis",
                "target_id": "hypothesis-one",
                "stance": "contradicts",
                "rationale": "Shared use weakens exclusive control.",
            },
            {
                "source_kind": "assertion",
                "source_id": "assertion-one",
                "target_kind": "hypothesis",
                "target_id": "hypothesis-one",
                "stance": "supports",
                "rationale": "Reuse may still reflect common operation.",
            },
        ],
    }

    intent = competing_hypotheses_matrix_intent("case-red", analysis)

    assert intent.view == VisualizationView.TASK_MATRIX
    assert intent.renderer == VisualizationRenderer.NATIVE
    assert len(intent.data.rows) == 4
    cells = {
        (row["source_id"], row["hypothesis_id"]): row for row in intent.data.rows
    }
    assert cells[("observation-one", "hypothesis-one")]["stance"] == "supports"
    assert cells[("observation-one", "hypothesis-two")]["stance"] == "not_assessed"
    assert cells[("assertion-one", "hypothesis-one")]["stance"] == "mixed"
    assert cells[("assertion-one", "hypothesis-one")]["link_count"] == 2
    assert "No analyst-recorded assessment" in cells[
        ("assertion-one", "hypothesis-two")
    ]["rationale"]
    assert "not treated as neutral" in intent.missing_data.explanation
    assert "not properties inferred" in intent.caveats[-2]


def test_competing_hypotheses_matrix_requires_competing_hypotheses():
    intent = competing_hypotheses_matrix_intent(
        "default",
        {
            "hypotheses": [{"id": "only-one", "statement": "One explanation"}],
            "observations": [{"id": "observed", "entity_value": "one.test"}],
            "evidence_links": [
                {
                    "source_kind": "observation",
                    "source_id": "observed",
                    "target_kind": "hypothesis",
                    "target_id": "only-one",
                    "stance": "supports",
                }
            ],
        },
    )

    assert intent.data.rows == ()
    assert intent.source_scope.record_count == 0


def test_scientific_investigation_hierarchy_preserves_path_depth_and_status():
    analysis = {
        "investigations": [
            {
                "id": "investigation-one",
                "title": "Relay ownership",
                "status": "analyzing",
                "created_at": "2026-08-24T10:00:00Z",
            }
        ],
        "questions": [
            {
                "id": "question-one",
                "text": "Who controls the relay?",
                "status": "open",
                "created_at": "2026-08-24T10:01:00Z",
            }
        ],
        "hypotheses": [
            {
                "id": "hypothesis-one",
                "question_id": "question-one",
                "statement": "One operator controls it.",
                "status": "retained",
                "created_at": "2026-08-24T10:02:00Z",
            }
        ],
        "lifecycle_items": [
            {
                "id": "lifecycle-question",
                "investigation_id": "investigation-one",
                "record_kind": "question",
                "record_id": "question-one",
                "item_type": "question",
            },
            {
                "id": "lifecycle-hypothesis",
                "investigation_id": "investigation-one",
                "record_kind": "hypothesis",
                "record_id": "hypothesis-one",
                "item_type": "hypothesis",
            },
            {
                "id": "lifecycle-signpost",
                "investigation_id": "investigation-one",
                "record_kind": None,
                "record_id": None,
                "item_type": "signpost",
                "statement": "A second independent source appears.",
                "status": "open",
                "created_at": "2026-08-24T10:03:00Z",
            },
        ],
    }

    intent = scientific_investigation_hierarchy_intent("case-red", analysis)

    assert intent.view == VisualizationView.DENDROGRAM
    assert intent.renderer == VisualizationRenderer.NATIVE
    assert len(intent.data.rows) == 4
    by_kind = {row["child_kind"]: row for row in intent.data.rows}
    assert by_kind["investigation"]["depth"] == 1
    assert by_kind["question"]["parent_id"] == "investigation:investigation-one"
    assert by_kind["hypothesis"]["depth"] == 3
    assert by_kind["hypothesis"]["status"] == "retained"
    assert by_kind["signpost"]["depth"] == 2
    assert by_kind["hypothesis"]["path"] == (
        "Workspace · case-red / Relay ownership / Who controls the relay? / "
        "One operator controls it."
    )
    assert "not evidentiary support" in intent.caveats[-1]


def test_scientific_investigation_hierarchy_has_truthful_empty_state():
    intent = scientific_investigation_hierarchy_intent("default", {})

    assert intent.data.rows == ()
    assert intent.source_scope.record_count == 0


def test_recorded_uncertainty_keeps_likelihood_and_confidence_separate():
    intent = recorded_uncertainty_intent(
        "case-red",
        {
            "hypotheses": [
                {
                    "id": "hypothesis-one",
                    "statement": "One operator controls the relay.",
                }
            ],
            "likelihood": [
                {
                    "id": "likelihood-one",
                    "target_kind": "hypothesis",
                    "target_id": "hypothesis-one",
                    "term": "unlikely",
                    "probability_min": 0.2,
                    "probability_max": 0.45,
                    "rationale": "Shared hosting remains a plausible alternative.",
                    "assessed_by": "human",
                    "created_at": "2026-08-24T10:00:00Z",
                }
            ],
            "confidence": [
                {
                    "id": "confidence-older",
                    "target_kind": "hypothesis",
                    "target_id": "hypothesis-one",
                    "level": "low",
                    "rationale": "Initial review.",
                    "assessed_by": "human",
                    "created_at": "2026-08-24T09:00:00Z",
                },
                {
                    "id": "confidence-latest",
                    "target_kind": "hypothesis",
                    "target_id": "hypothesis-one",
                    "level": "moderate",
                    "rationale": "Two independent sources now support the assessment.",
                    "assessed_by": "human",
                    "created_at": "2026-08-24T11:00:00Z",
                },
            ],
        },
    )

    assert intent.view == VisualizationView.UNCERTAINTY_INTERVALS
    assert intent.renderer == VisualizationRenderer.NATIVE
    assert intent.data.rows == (
        {
            "target": "One operator controls the relay.",
            "target_kind": "hypothesis",
            "target_id": "hypothesis-one",
            "likelihood_term": "unlikely",
            "probability_min_percent": 20.0,
            "probability_max_percent": 45.0,
            "likelihood_rationale": "Shared hosting remains a plausible alternative.",
            "likelihood_assessor": "human",
            "likelihood_recorded_at": "2026-08-24T10:00:00Z",
            "confidence_level": "moderate",
            "confidence_rationale": "Two independent sources now support the assessment.",
            "confidence_assessor": "human",
        },
    )
    assert "Never convert confidence into probability" in intent.caveats[0]
    assert "never as a numeric transformation" in intent.caveats[-1]


def test_recorded_uncertainty_omits_invalid_intervals_without_guessing():
    intent = recorded_uncertainty_intent(
        "default",
        {
            "likelihood": [
                {
                    "target_kind": "hypothesis",
                    "target_id": "bad-range",
                    "term": "likely",
                    "probability_min": 0.8,
                    "probability_max": 0.2,
                }
            ]
        },
    )

    assert intent.data.rows == ()
    assert intent.missing_data.omitted_count == 1
    assert "valid bounded probability interval" in intent.missing_data.explanation


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


def test_relationship_graph_keeps_manual_assertions_visibly_distinct():
    graph = {
        "nodes": [
            {"id": "domain-name--one", "type": "domain-name", "value": "one.test"},
            {"id": "ipv4-addr--one", "type": "ipv4-addr", "value": "198.51.100.8"},
        ],
        "edges": [],
    }
    analysis = {
        "assertions": [
            {
                "id": "assertion-manual",
                "statement": "Analyst annotated shared control after review.",
                "status": "active",
                "author_kind": "human",
                "method": "manual-graph-relation",
                "subject_ref": "domain-name--one",
                "predicate": "possibly-controlled-by",
                "object_ref": "ipv4-addr--one",
            }
        ]
    }

    intent = relationship_graph_intent("default", graph, analysis)
    distribution = relationship_degree_distribution_intent("default", graph, analysis)

    assert len(intent.data.edges) == 1
    assert intent.data.edges[0].basis == "manual"
    assert intent.data.edges[0].assertion_id == "assertion-manual"
    assert intent.data.edges[0].annotation == "Analyst annotated shared control after review."
    assert "Analyst assertion assertion-manual" in intent.data.edges[0].provenance
    assert {row["connection_count"] for row in distribution.data.rows} == {1}


def test_relationship_degree_histogram_counts_only_admitted_edges():
    intent = relationship_degree_distribution_intent(
        "default",
        {
            "nodes": [
                {"id": "domain-name--one", "type": "domain-name", "value": "one.test"},
                {"id": "ipv4-addr--one", "type": "ipv4-addr", "value": "198.51.100.8"},
                {"id": "domain-name--two", "type": "domain-name", "value": "two.test"},
            ],
            "edges": [
                {
                    "source": "domain-name--one",
                    "target": "ipv4-addr--one",
                    "relationship": "resolves-to",
                    "basis": "explicit",
                },
                {
                    "source": "domain-name--missing",
                    "target": "domain-name--two",
                    "relationship": "related-to",
                    "basis": "explicit",
                },
            ],
        },
    )

    assert intent.view == VisualizationView.HISTOGRAM
    assert intent.renderer == VisualizationRenderer.FLINT_CHARTJS
    assert intent.chart_properties == {"binCount": 10}
    assert intent.selection_rationale
    assert intent.reading_guide
    assert intent.data.rows == (
        {
            "indicator": "198.51.100.8",
            "indicator_type": "ipv4-addr",
            "connection_count": 1,
        },
        {
            "indicator": "one.test",
            "indicator_type": "domain-name",
            "connection_count": 1,
        },
        {
            "indicator": "two.test",
            "indicator_type": "domain-name",
            "connection_count": 0,
        },
    )
