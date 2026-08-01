"""Canonical visualization intents for Pivotglass.

This module owns the question-first selection policy and the bounded data
envelope sent to browser renderers.  It deliberately contains no rendering
geometry.  The web client may compile an approved intent through Flint or use
an accessible native renderer, but it may not change the analytical meaning of
the data.
"""

from __future__ import annotations

from collections import Counter
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from adversary_pursuit.core.evidence_detail import evidence_ref
from adversary_pursuit.dossier.slot_inference import infer_dossier_state
from adversary_pursuit.dossier.slots import DossierSlotName

MAX_VISUALIZATION_ROWS = 5_000


class VisualizationQuestion(StrEnum):
    """Analyst questions supported by deterministic visualization policy."""

    ACTIVITY_CONCENTRATION = "when_was_activity_concentrated"
    DOSSIER_COMPLETENESS = "how_complete_is_this_dossier"
    VALUE_DISTRIBUTION = "how_are_values_distributed"
    ENTITY_RELATIONSHIPS = "which_entities_relate"
    HIERARCHY = "how_does_this_hierarchy_divide"
    NUMERIC_CORRELATION = "are_numeric_features_correlated"
    INDICATOR_COMPLETENESS = "how_complete_are_indicator_investigations"
    TASK_STATUS = "which_indicator_enrichment_work_is_pending"
    METRIC_TREND = "how_does_this_metric_change"
    EVIDENCE_COMPOSITION = "which_evidence_types_are_stored"


class VisualizationView(StrEnum):
    """Renderer-neutral views selected by the Python policy."""

    CALENDAR_HEATMAP = "calendar_heatmap"
    RADAR = "radar"
    HISTOGRAM = "histogram"
    RELATIONSHIP_GRAPH = "relationship_graph"
    DENDROGRAM = "dendrogram"
    SCATTER = "scatter"
    TASK_MATRIX = "task_matrix"
    LINE = "line"
    BAR = "bar"


class VisualizationRenderer(StrEnum):
    """Allowed renderer families.

    ``flint_chartjs`` means the TypeScript adapter must compile the semantic
    fields through Flint before Chart.js sees them.  ``native`` is reserved for
    operational structures not represented by the installed Chart.js backend.
    """

    FLINT_CHARTJS = "flint_chartjs"
    NATIVE = "native"


class VisualizationPolicy(BaseModel):
    """One immutable question-to-view policy row."""

    model_config = ConfigDict(frozen=True)

    question: VisualizationQuestion
    view: VisualizationView
    renderer: VisualizationRenderer
    required_roles: tuple[str, ...]
    guardrail: str


VISUALIZATION_POLICIES: dict[VisualizationQuestion, VisualizationPolicy] = {
    VisualizationQuestion.ACTIVITY_CONCENTRATION: VisualizationPolicy(
        question=VisualizationQuestion.ACTIVITY_CONCENTRATION,
        view=VisualizationView.CALENDAR_HEATMAP,
        renderer=VisualizationRenderer.NATIVE,
        required_roles=("date", "value"),
        guardrail="Expose timezone and render missing days explicitly.",
    ),
    VisualizationQuestion.DOSSIER_COMPLETENESS: VisualizationPolicy(
        question=VisualizationQuestion.DOSSIER_COMPLETENESS,
        view=VisualizationView.RADAR,
        renderer=VisualizationRenderer.FLINT_CHARTJS,
        required_roles=("category", "value"),
        guardrail="Render one dossier on a common 0-100 scale with an accessible table.",
    ),
    VisualizationQuestion.VALUE_DISTRIBUTION: VisualizationPolicy(
        question=VisualizationQuestion.VALUE_DISTRIBUTION,
        view=VisualizationView.HISTOGRAM,
        renderer=VisualizationRenderer.FLINT_CHARTJS,
        required_roles=("value",),
        guardrail="Show the sample count and expose the selected bin count.",
    ),
    VisualizationQuestion.ENTITY_RELATIONSHIPS: VisualizationPolicy(
        question=VisualizationQuestion.ENTITY_RELATIONSHIPS,
        view=VisualizationView.RELATIONSHIP_GRAPH,
        renderer=VisualizationRenderer.NATIVE,
        required_roles=("source", "target", "relationship"),
        guardrail="Never draw an edge without its evidence basis and provenance state.",
    ),
    VisualizationQuestion.HIERARCHY: VisualizationPolicy(
        question=VisualizationQuestion.HIERARCHY,
        view=VisualizationView.DENDROGRAM,
        renderer=VisualizationRenderer.NATIVE,
        required_roles=("parent", "child"),
        guardrail="Preserve path and depth in the visible table.",
    ),
    VisualizationQuestion.NUMERIC_CORRELATION: VisualizationPolicy(
        question=VisualizationQuestion.NUMERIC_CORRELATION,
        view=VisualizationView.SCATTER,
        renderer=VisualizationRenderer.FLINT_CHARTJS,
        required_roles=("x", "y"),
        guardrail="Expose every plotted point and label explained variance for PCA projections.",
    ),
    VisualizationQuestion.INDICATOR_COMPLETENESS: VisualizationPolicy(
        question=VisualizationQuestion.INDICATOR_COMPLETENESS,
        view=VisualizationView.TASK_MATRIX,
        renderer=VisualizationRenderer.NATIVE,
        required_roles=("row", "column", "status"),
        guardrail=(
            "Show all canonical dimensions and distinguish unavailable inference "
            "from observed evidence gaps."
        ),
    ),
    VisualizationQuestion.TASK_STATUS: VisualizationPolicy(
        question=VisualizationQuestion.TASK_STATUS,
        view=VisualizationView.TASK_MATRIX,
        renderer=VisualizationRenderer.NATIVE,
        required_roles=("row", "column", "status"),
        guardrail="Pair color with text or shape and preserve authoritative lifecycle order.",
    ),
    VisualizationQuestion.METRIC_TREND: VisualizationPolicy(
        question=VisualizationQuestion.METRIC_TREND,
        view=VisualizationView.LINE,
        renderer=VisualizationRenderer.FLINT_CHARTJS,
        required_roles=("time", "value"),
        guardrail="Do not interpolate missing values or create unreadable multi-series lines.",
    ),
    VisualizationQuestion.EVIDENCE_COMPOSITION: VisualizationPolicy(
        question=VisualizationQuestion.EVIDENCE_COMPOSITION,
        view=VisualizationView.BAR,
        renderer=VisualizationRenderer.FLINT_CHARTJS,
        required_roles=("category", "value"),
        guardrail="Count only stored records in the stated workspace scope.",
    ),
}


class VisualizationSourceScope(BaseModel):
    """Human-readable scope for the exact plotted data."""

    model_config = ConfigDict(frozen=True)

    workspace: str
    description: str
    record_count: int = Field(ge=0)
    timezone: str | None = None


class VisualizationTableColumn(BaseModel):
    """One accessible/exported data column."""

    model_config = ConfigDict(frozen=True)

    key: str
    label: str


class VisualizationMissingData(BaseModel):
    """Explicit treatment of absent or unavailable values."""

    model_config = ConfigDict(frozen=True)

    policy: Literal["show", "omit_with_count", "not_applicable"]
    explanation: str
    omitted_count: int = Field(default=0, ge=0)


class VisualizationNode(BaseModel):
    """Indicator-first graph node.

    ``reference`` is for detail lookup only.  The visible label is always the
    actual indicator value.
    """

    model_config = ConfigDict(frozen=True)

    reference: str
    label: str
    entity_type: str


class VisualizationEdge(BaseModel):
    """A typed directional edge with an explicit analytical basis."""

    model_config = ConfigDict(frozen=True)

    source: str
    target: str
    relationship: str
    basis: Literal["explicit", "property", "manual"]
    provenance: str


class VisualizationData(BaseModel):
    """Bounded exact data carried by a visualization intent."""

    model_config = ConfigDict(frozen=True)

    rows: tuple[dict[str, Any], ...] = ()
    nodes: tuple[VisualizationNode, ...] = ()
    edges: tuple[VisualizationEdge, ...] = ()

    @model_validator(mode="after")
    def bounded(self) -> VisualizationData:
        total = len(self.rows) + len(self.nodes) + len(self.edges)
        if total > MAX_VISUALIZATION_ROWS:
            raise ValueError(
                f"visualization data exceeds the {MAX_VISUALIZATION_ROWS}-record limit"
            )
        return self


class VisualizationIntent(BaseModel):
    """Validated, renderer-neutral visualization request."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    intent_id: str
    title: str
    question: VisualizationQuestion
    question_text: str
    view: VisualizationView
    renderer: VisualizationRenderer
    source_scope: VisualizationSourceScope
    data: VisualizationData
    fields: dict[str, str]
    semantic_types: dict[str, str]
    table_columns: tuple[VisualizationTableColumn, ...]
    missing_data: VisualizationMissingData
    caveats: tuple[str, ...] = ()
    export_filename: str

    @model_validator(mode="after")
    def follows_policy(self) -> VisualizationIntent:
        policy = VISUALIZATION_POLICIES[self.question]
        if self.view != policy.view or self.renderer != policy.renderer:
            raise ValueError("visualization view or renderer does not match policy")
        missing_roles = [role for role in policy.required_roles if role not in self.fields]
        if missing_roles:
            raise ValueError(
                f"visualization intent is missing required field roles: {', '.join(missing_roles)}"
            )
        return self


def visualization_policy(question: VisualizationQuestion | str) -> VisualizationPolicy:
    """Return the deterministic policy row for an analyst question."""

    return VISUALIZATION_POLICIES[VisualizationQuestion(question)]


def _intent(
    *,
    intent_id: str,
    title: str,
    question: VisualizationQuestion,
    question_text: str,
    workspace: str,
    description: str,
    record_count: int,
    data: VisualizationData,
    fields: dict[str, str],
    semantic_types: dict[str, str],
    table_columns: tuple[VisualizationTableColumn, ...],
    missing_data: VisualizationMissingData,
    caveats: tuple[str, ...] = (),
    timezone: str | None = None,
) -> VisualizationIntent:
    policy = visualization_policy(question)
    return VisualizationIntent(
        intent_id=intent_id,
        title=title,
        question=question,
        question_text=question_text,
        view=policy.view,
        renderer=policy.renderer,
        source_scope=VisualizationSourceScope(
            workspace=workspace,
            description=description,
            record_count=record_count,
            timezone=timezone,
        ),
        data=data,
        fields=fields,
        semantic_types=semantic_types,
        table_columns=table_columns,
        missing_data=missing_data,
        caveats=(policy.guardrail, *caveats),
        export_filename=f"{workspace}-{intent_id}.csv",
    )


def evidence_composition_intent(
    workspace: str, objects: list[dict[str, Any]]
) -> VisualizationIntent:
    """Count stored evidence by STIX type without inferring categories."""

    counts = Counter(str(item.get("type", "unknown")) for item in objects)
    rows = tuple(
        {"evidence_type": evidence_type, "count": count}
        for evidence_type, count in sorted(counts.items())
    )
    return _intent(
        intent_id="evidence-composition",
        title="Stored evidence types",
        question=VisualizationQuestion.EVIDENCE_COMPOSITION,
        question_text="Which evidence types are stored in this workspace?",
        workspace=workspace,
        description="Stored STIX cyber-observable records in the active workspace.",
        record_count=len(objects),
        data=VisualizationData(rows=rows),
        fields={"category": "evidence_type", "value": "count"},
        semantic_types={"evidence_type": "Category", "count": "Count"},
        table_columns=(
            VisualizationTableColumn(key="evidence_type", label="Evidence type"),
            VisualizationTableColumn(key="count", label="Count"),
        ),
        missing_data=VisualizationMissingData(
            policy="show",
            explanation="An empty workspace is shown as an empty state.",
        ),
    )


_DOSSIER_SCORE: dict[str, int | None] = {
    "empty": 0,
    "partial": 50,
    "filled": 100,
    "deferred": None,
}


def dossier_completeness_intent(
    workspace: str, slots: list[dict[str, Any]]
) -> VisualizationIntent:
    """Project categorical dossier states onto an explicitly caveated 0-100 scale."""

    omitted = 0
    rows: list[dict[str, Any]] = []
    for slot in slots:
        status = str(slot.get("status", "empty"))
        score = _DOSSIER_SCORE.get(status)
        if score is None:
            omitted += 1
        rows.append(
            {
                "facet": str(slot.get("name", "unknown")).replace("_", " "),
                "score": score,
                "status": status,
                "evidence_count": int(slot.get("evidence_count", 0)),
            }
        )
    return _intent(
        intent_id="dossier-completeness",
        title="Dossier completeness",
        question=VisualizationQuestion.DOSSIER_COMPLETENESS,
        question_text="How complete is this dossier?",
        workspace=workspace,
        description="The nine canonical dossier facets for the active workspace.",
        record_count=len(slots),
        data=VisualizationData(rows=tuple(rows)),
        fields={"category": "facet", "value": "score"},
        semantic_types={
            "facet": "Category",
            "score": "Percentage",
            "status": "Status",
            "evidence_count": "Count",
        },
        table_columns=(
            VisualizationTableColumn(key="facet", label="Facet"),
            VisualizationTableColumn(key="status", label="Status"),
            VisualizationTableColumn(key="score", label="Display score"),
            VisualizationTableColumn(key="evidence_count", label="Evidence records"),
        ),
        missing_data=VisualizationMissingData(
            policy="omit_with_count",
            explanation=(
                "Deferred facets have no implemented inference path and are omitted "
                "from the radar shape, while remaining visible in the table."
            ),
            omitted_count=omitted,
        ),
        caveats=(
            "Empty, partial, and filled map to 0, 50, and 100 for display; "
            "this is not a confidence score.",
        ),
    )


def activity_concentration_intent(
    workspace: str, investigations: list[dict[str, Any]]
) -> VisualizationIntent:
    """Count authoritative investigation events by UTC calendar day."""

    counts: Counter[str] = Counter()
    total_events = 0
    for investigation in investigations:
        for event in investigation.get("events", ()):
            created_at = str(event.get("created_at", ""))
            if len(created_at) >= 10:
                counts[created_at[:10]] += 1
                total_events += 1
    rows = tuple({"date": day, "count": count} for day, count in sorted(counts.items()))
    return _intent(
        intent_id="activity-calendar",
        title="Investigation activity",
        question=VisualizationQuestion.ACTIVITY_CONCENTRATION,
        question_text="When was investigation activity concentrated?",
        workspace=workspace,
        description="Authoritative lifecycle events created in this local service session.",
        record_count=total_events,
        data=VisualizationData(rows=rows),
        fields={"date": "date", "value": "count"},
        semantic_types={"date": "Date", "count": "Count"},
        table_columns=(
            VisualizationTableColumn(key="date", label="UTC date"),
            VisualizationTableColumn(key="count", label="Events"),
        ),
        missing_data=VisualizationMissingData(
            policy="show",
            explanation="Calendar days without events render as zero, not as missing telemetry.",
        ),
        timezone="UTC",
    )


def _indicator_value(item: dict[str, Any]) -> str:
    """Return the actual observable value used throughout the cockpit."""

    return str(
        item.get(
            "value",
            item.get("x_indicator_value", item.get("name", "unavailable")),
        )
    )


def _first_seen(item: dict[str, Any]) -> str:
    for key in ("first_seen", "x_ap_first_seen", "created", "x_ap_fetched_at"):
        if item.get(key):
            return str(item[key])
    return ""


def _last_seen(item: dict[str, Any]) -> str:
    for key in (
        "last_seen",
        "x_ap_last_seen",
        "modified",
        "x_ap_fetched_at",
        "created",
        "first_seen",
    ):
        if item.get(key):
            return str(item[key])
    return ""


def indicator_constellation_intent(
    workspace: str,
    objects: list[dict[str, Any]],
    graph: dict[str, Any],
) -> VisualizationIntent:
    """Project persisted indicators against every canonical investigation dimension.

    Each cell is derived from the stored indicator, its direct graph
    neighborhood, and the canonical dossier inference authority. Direct
    relatedness comes only from edges already admitted by the relationship
    authority.
    """

    graph_labels = {
        str(node.get("id", "")): str(node.get("value") or "unavailable")
        for node in graph.get("nodes", ())
        if node.get("id")
    }
    adjacency: dict[str, set[str]] = {reference: set() for reference in graph_labels}
    for edge in graph.get("edges", ()):
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if source in adjacency and target in adjacency:
            adjacency[source].add(target)
            adjacency[target].add(source)

    objects_by_id = {
        str(item["id"]): item
        for item in objects
        if item.get("id")
    }
    indicators = [
        item
        for item in objects
        if item.get("id") and _indicator_value(item) != "unavailable"
    ]
    indicators.sort(
        key=lambda item: (
            _last_seen(item),
            _first_seen(item),
            _indicator_value(item).casefold(),
        ),
        reverse=True,
    )
    per_indicator_limit = max(1, MAX_VISUALIZATION_ROWS // len(DossierSlotName))
    visible = indicators[:per_indicator_limit]
    omitted = max(0, len(indicators) - len(visible))

    rows: list[dict[str, Any]] = []
    for item in visible:
        stix_id = str(item["id"])
        reference = evidence_ref(stix_id)
        indicator = _indicator_value(item)
        scope_ids = {stix_id, *adjacency.get(stix_id, ())}
        connected_evidence = [
            objects_by_id[scope_id]
            for scope_id in sorted(scope_ids)
            if scope_id in objects_by_id
        ]
        contribution = infer_dossier_state(connected_evidence)
        statuses = [slot.status.value for slot in contribution.slots.values()]
        assessable_scores = [
            _DOSSIER_SCORE[status]
            for status in statuses
            if _DOSSIER_SCORE.get(status) is not None
        ]
        completeness = (
            round(sum(assessable_scores) / len(assessable_scores))
            if assessable_scores
            else 0
        )
        related_ids = sorted(adjacency.get(stix_id, ()))
        related_labels = sorted(
            {
                graph_labels[related_id]
                for related_id in related_ids
                if graph_labels.get(related_id) not in (None, "unavailable")
            },
            key=str.casefold,
        )
        for dimension in DossierSlotName:
            slot = contribution.slots[dimension]
            rows.append(
                {
                    "reference": reference,
                    "indicator": indicator,
                    "indicator_type": str(item.get("type", "unknown")),
                    "dimension": dimension.value,
                    "status": slot.status.value,
                    "evidence_count": slot.evidence_count,
                    "completeness_percent": completeness,
                    "first_seen": _first_seen(item),
                    "last_seen": _last_seen(item),
                    "related_references": [
                        evidence_ref(related_id) for related_id in related_ids
                    ],
                    "related_to": related_labels,
                }
            )

    return _intent(
        intent_id="indicator-constellation",
        title="Investigation constellation",
        question=VisualizationQuestion.INDICATOR_COMPLETENESS,
        question_text=(
            "How complete is each investigation dimension for every stored indicator?"
        ),
        workspace=workspace,
        description=(
            "Persistent stored indicators and their direct graph neighborhoods "
            "mapped to the nine canonical Dossier dimensions."
        ),
        record_count=len(visible),
        data=VisualizationData(rows=tuple(rows)),
        fields={
            "row": "indicator",
            "row_id": "reference",
            "column": "dimension",
            "status": "status",
        },
        semantic_types={
            "reference": "Identifier",
            "indicator": "Name",
            "indicator_type": "Category",
            "dimension": "Category",
            "status": "Status",
            "evidence_count": "Count",
            "completeness_percent": "Percentage",
            "first_seen": "DateTime",
            "last_seen": "DateTime",
            "related_to": "NameList",
        },
        table_columns=(
            VisualizationTableColumn(key="indicator", label="Indicator"),
            VisualizationTableColumn(key="indicator_type", label="IoC type"),
            VisualizationTableColumn(key="dimension", label="Investigation dimension"),
            VisualizationTableColumn(key="status", label="Completeness"),
            VisualizationTableColumn(key="evidence_count", label="Evidence records"),
            VisualizationTableColumn(key="completeness_percent", label="Overall mapped score"),
            VisualizationTableColumn(key="first_seen", label="First seen"),
            VisualizationTableColumn(key="last_seen", label="Last seen"),
            VisualizationTableColumn(key="related_to", label="Directly related indicators"),
        ),
        missing_data=VisualizationMissingData(
            policy="omit_with_count" if omitted else "show",
            explanation=(
                "Empty means the implemented inference found no supporting evidence; "
                "deferred means that dimension has no applicable automated inference path. "
                "Indicators beyond the bounded local rendering limit remain stored."
            ),
            omitted_count=omitted,
        ),
        caveats=(
            "The overall mapped score averages empty, partial, and filled states across "
            "implemented dimensions; it is a navigation aid, not analytical confidence.",
            "Dimension coverage includes only the indicator and evidence joined by direct "
            "graph edges admitted by the relationship authority.",
            "The initial order is newest last-seen first; unavailable dates sort last.",
        ),
    )


def task_matrix_intent(
    workspace: str, investigations: list[dict[str, Any]]
) -> VisualizationIntent:
    """Project one authoritative latest lifecycle into each target/enrichment cell."""

    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for investigation in investigations:
        target = str(investigation.get("target", "unavailable"))
        for event in investigation.get("events", ()):
            enrichment = str(event.get("tool") or "")
            if not enrichment:
                continue
            key = (target, enrichment)
            latest[key] = {
                "indicator": target,
                "enrichment": enrichment,
                "status": str(event.get("lifecycle", "planned")),
                "updated_at": str(event.get("updated_at", "")),
                "event_sequence": int(event.get("sequence", 0)),
                "investigation_id": str(investigation.get("investigation_id", "")),
            }
    rows = tuple(latest[key] for key in sorted(latest))
    return _intent(
        intent_id="task-matrix",
        title="Indicator enrichment activity",
        question=VisualizationQuestion.TASK_STATUS,
        question_text="Which indicator enrichments are pending or complete?",
        workspace=workspace,
        description=(
            "Latest authoritative lifecycle event for each session indicator/enrichment pair."
        ),
        record_count=len(rows),
        data=VisualizationData(rows=rows),
        fields={"row": "indicator", "column": "enrichment", "status": "status"},
        semantic_types={
            "indicator": "Name",
            "enrichment": "Category",
            "status": "Status",
            "updated_at": "DateTime",
            "event_sequence": "Count",
        },
        table_columns=(
            VisualizationTableColumn(key="indicator", label="Indicator"),
            VisualizationTableColumn(key="enrichment", label="Enrichment source"),
            VisualizationTableColumn(key="status", label="Latest status"),
            VisualizationTableColumn(key="updated_at", label="Updated"),
        ),
        missing_data=VisualizationMissingData(
            policy="show",
            explanation=(
                "A blank cell means that enrichment has no authoritative job "
                "for the indicator."
            ),
        ),
    )


def relationship_graph_intent(
    workspace: str, graph: dict[str, Any]
) -> VisualizationIntent:
    """Build an indicator-first graph intent from the persisted graph authority."""

    nodes = tuple(
        VisualizationNode(
            reference=str(node.get("id", "")),
            label=str(node.get("value") or "unavailable"),
            entity_type=str(node.get("type") or "unknown"),
        )
        for node in graph.get("nodes", ())
        if node.get("id")
    )
    node_ids = {node.reference for node in nodes}
    edges = tuple(
        VisualizationEdge(
            source=str(edge.get("source", "")),
            target=str(edge.get("target", "")),
            relationship=str(edge.get("relationship") or "related-to"),
            basis=(
                str(edge.get("basis"))
                if str(edge.get("basis")) in {"explicit", "property", "manual"}
                else "explicit"
            ),
            provenance=(
                "Stored STIX relationship"
                if edge.get("basis") != "property"
                else "Conservative typed-property pivot"
            ),
        )
        for edge in graph.get("edges", ())
        if edge.get("source") in node_ids and edge.get("target") in node_ids
    )
    labels = {node.reference: node.label for node in nodes}
    rows = tuple(
        {
            "source": labels[edge.source],
            "target": labels[edge.target],
            "relationship": edge.relationship,
            "basis": edge.basis,
            "provenance": edge.provenance,
        }
        for edge in edges
    )
    return _intent(
        intent_id="relationship-graph",
        title="Evidence relationships",
        question=VisualizationQuestion.ENTITY_RELATIONSHIPS,
        question_text="Which stored entities relate, and why is each edge present?",
        workspace=workspace,
        description="Stored STIX objects, explicit relationships, and conservative property pivots.",
        record_count=len(nodes),
        data=VisualizationData(rows=rows, nodes=nodes, edges=edges),
        fields={"source": "source", "target": "target", "relationship": "relationship"},
        semantic_types={
            "source": "Name",
            "target": "Name",
            "relationship": "Category",
            "basis": "Category",
        },
        table_columns=(
            VisualizationTableColumn(key="source", label="Source indicator"),
            VisualizationTableColumn(key="relationship", label="Relationship"),
            VisualizationTableColumn(key="target", label="Target indicator"),
            VisualizationTableColumn(key="basis", label="Evidence basis"),
            VisualizationTableColumn(key="provenance", label="Provenance state"),
        ),
        missing_data=VisualizationMissingData(
            policy="show",
            explanation="Unconnected stored entities remain visible as nodes.",
        ),
        caveats=(
            "Property pivots are navigation aids, not asserted STIX relationships.",
            "First/last seen and confidence remain unavailable until their persisted "
            "relationship fields exist; the visualization does not invent them.",
        ),
    )


def build_visualization_intents(
    *,
    workspace: str,
    objects: list[dict[str, Any]],
    dossier_slots: list[dict[str, Any]],
    graph: dict[str, Any],
    investigations: list[dict[str, Any]],
) -> tuple[VisualizationIntent, ...]:
    """Build the initial 0.6.0 cockpit visualization set."""

    return (
        indicator_constellation_intent(workspace, objects, graph),
        evidence_composition_intent(workspace, objects),
        dossier_completeness_intent(workspace, dossier_slots),
        activity_concentration_intent(workspace, investigations),
        task_matrix_intent(workspace, investigations),
        relationship_graph_intent(workspace, graph),
    )
