"""Canonical visualization intents for Pivotglass.

This module owns the question-first selection policy and the bounded data
envelope sent to browser renderers.  It deliberately contains no rendering
geometry.  The web client may compile an approved intent through Flint or use
an accessible native renderer, but it may not change the analytical meaning of
the data.
"""

from __future__ import annotations

import math
from collections import Counter
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from adversary_pursuit.core.evidence_detail import evidence_ref
from adversary_pursuit.dossier.slot_inference import infer_dossier_state
from adversary_pursuit.dossier.slots import DossierSlotName

MAX_VISUALIZATION_ROWS = 5_000
MAX_RELATIONSHIP_GRAPH_NODES = 1_000


class VisualizationQuestion(StrEnum):
    """Analyst questions supported by deterministic visualization policy."""

    ACTIVITY_CONCENTRATION = "when_was_activity_concentrated"
    DOSSIER_COMPLETENESS = "how_complete_is_this_dossier"
    VALUE_DISTRIBUTION = "how_are_values_distributed"
    ENTITY_RELATIONSHIPS = "which_entities_relate"
    HIERARCHY = "how_does_this_hierarchy_divide"
    NUMERIC_CORRELATION = "are_numeric_features_correlated"
    COMPETING_HYPOTHESES = "which_evidence_supports_or_contradicts_hypotheses"
    RECORDED_UNCERTAINTY = "what_likelihood_and_confidence_are_recorded"
    INDICATOR_COMPLETENESS = "how_complete_are_indicator_investigations"
    TASK_STATUS = "which_indicator_enrichment_work_is_pending"
    METRIC_TREND = "how_does_this_metric_change"
    EVIDENCE_COMPOSITION = "which_evidence_types_are_stored"
    PIVOT_TRAIL = "how_did_the_analyst_reach_the_current_pivot"


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
    UNCERTAINTY_INTERVALS = "uncertainty_intervals"
    TIMELINE = "timeline"


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
    selection_reason: str
    reading_guide: str
    guardrail: str


VISUALIZATION_POLICIES: dict[VisualizationQuestion, VisualizationPolicy] = {
    VisualizationQuestion.ACTIVITY_CONCENTRATION: VisualizationPolicy(
        question=VisualizationQuestion.ACTIVITY_CONCENTRATION,
        view=VisualizationView.CALENDAR_HEATMAP,
        renderer=VisualizationRenderer.NATIVE,
        required_roles=("date", "value"),
        selection_reason=(
            "A calendar heatmap makes concentrated activity and days without events visible "
            "without implying a continuous measurement."
        ),
        reading_guide=(
            "Scan for darker days and clusters; a zero is an observed day without activity, "
            "not missing telemetry."
        ),
        guardrail="Expose timezone and render missing days explicitly.",
    ),
    VisualizationQuestion.DOSSIER_COMPLETENESS: VisualizationPolicy(
        question=VisualizationQuestion.DOSSIER_COMPLETENESS,
        view=VisualizationView.RADAR,
        renderer=VisualizationRenderer.FLINT_CHARTJS,
        required_roles=("category", "value"),
        selection_reason=(
            "A radar view compares one dossier's bounded facet scores on the same scale."
        ),
        reading_guide=(
            "Look for inward dents to find weak facets, then use the exact table before "
            "comparing or reporting a value."
        ),
        guardrail="Render one dossier on a common 0-100 scale with an accessible table.",
    ),
    VisualizationQuestion.VALUE_DISTRIBUTION: VisualizationPolicy(
        question=VisualizationQuestion.VALUE_DISTRIBUTION,
        view=VisualizationView.HISTOGRAM,
        renderer=VisualizationRenderer.FLINT_CHARTJS,
        required_roles=("value",),
        selection_reason=(
            "A histogram reveals the shape of one numeric distribution without implying "
            "time order or relationships between individual records."
        ),
        reading_guide=(
            "Read bar height as the number of values in each range; adjust the bins to test "
            "whether an apparent pattern is stable."
        ),
        guardrail="Show the sample count and expose the selected bin count.",
    ),
    VisualizationQuestion.ENTITY_RELATIONSHIPS: VisualizationPolicy(
        question=VisualizationQuestion.ENTITY_RELATIONSHIPS,
        view=VisualizationView.RELATIONSHIP_GRAPH,
        renderer=VisualizationRenderer.NATIVE,
        required_roles=("source", "target", "relationship"),
        selection_reason=(
            "A force-directed relationship graph preserves entities as nodes and typed "
            "relationships as inspectable edges."
        ),
        reading_guide=(
            "Follow labeled edges, not spatial proximity; select a node to inspect its "
            "admitted relationships and provenance."
        ),
        guardrail="Never draw an edge without its evidence basis and provenance state.",
    ),
    VisualizationQuestion.HIERARCHY: VisualizationPolicy(
        question=VisualizationQuestion.HIERARCHY,
        view=VisualizationView.DENDROGRAM,
        renderer=VisualizationRenderer.NATIVE,
        required_roles=("parent", "child"),
        selection_reason=(
            "A dendrogram preserves parent-child structure and makes path depth explicit."
        ),
        reading_guide=(
            "Read from the root toward the leaves; indentation expresses hierarchy, not "
            "confidence or time."
        ),
        guardrail="Preserve path and depth in the visible table.",
    ),
    VisualizationQuestion.NUMERIC_CORRELATION: VisualizationPolicy(
        question=VisualizationQuestion.NUMERIC_CORRELATION,
        view=VisualizationView.SCATTER,
        renderer=VisualizationRenderer.FLINT_CHARTJS,
        required_roles=("x", "y"),
        selection_reason=(
            "A scatter view exposes every numeric point and shows association or projected "
            "similarity without asserting a causal relationship."
        ),
        reading_guide=(
            "Nearby points have similar plotted measurements; inspect labels and explained "
            "variance before treating a cluster as meaningful."
        ),
        guardrail="Expose every plotted point and label explained variance for PCA projections.",
    ),
    VisualizationQuestion.COMPETING_HYPOTHESES: VisualizationPolicy(
        question=VisualizationQuestion.COMPETING_HYPOTHESES,
        view=VisualizationView.TASK_MATRIX,
        renderer=VisualizationRenderer.NATIVE,
        required_roles=("row", "column", "status"),
        selection_reason=(
            "An ACH matrix places the same evidence against every competing hypothesis so "
            "support, contradiction, mixed assessments, and unassessed cells remain visible."
        ),
        reading_guide=(
            "Compare evidence across each row and prioritize contradictions; an unassessed "
            "cell means no judgment was recorded."
        ),
        guardrail=(
            "Show only analyst-recorded evidence stances; an unassessed cell is not neutral "
            "evidence and no stance may be inferred from absence."
        ),
    ),
    VisualizationQuestion.RECORDED_UNCERTAINTY: VisualizationPolicy(
        question=VisualizationQuestion.RECORDED_UNCERTAINTY,
        view=VisualizationView.UNCERTAINTY_INTERVALS,
        renderer=VisualizationRenderer.NATIVE,
        required_roles=("target", "minimum", "maximum"),
        selection_reason=(
            "Bounded interval bars show the probability range attached to each recorded "
            "likelihood term while keeping analytic confidence visibly separate."
        ),
        reading_guide=(
            "Read the bar as the recorded probability range, then read confidence and its "
            "rationale separately below it."
        ),
        guardrail=(
            "Never convert confidence into probability or combine the two measurements on "
            "one scale; expose both rationales and the recorded assessor."
        ),
    ),
    VisualizationQuestion.INDICATOR_COMPLETENESS: VisualizationPolicy(
        question=VisualizationQuestion.INDICATOR_COMPLETENESS,
        view=VisualizationView.TASK_MATRIX,
        renderer=VisualizationRenderer.NATIVE,
        required_roles=("row", "column", "status"),
        selection_reason=(
            "A compact matrix aligns every indicator to the same investigation dimensions, "
            "so repeated gaps and uneven coverage are visible in one scan."
        ),
        reading_guide=(
            "Read across for one indicator or down for a shared gap; hover or focus any peg "
            "for the full dimension name, state meaning, and evidence count."
        ),
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
        selection_reason=(
            "A matrix preserves one authoritative job state per indicator and enrichment "
            "source while remaining readable at dense scale."
        ),
        reading_guide=(
            "Read across for one indicator or down for one enrichment source; select a cell "
            "to inspect its latest authoritative lifecycle event."
        ),
        guardrail="Pair color with text or shape and preserve authoritative lifecycle order.",
    ),
    VisualizationQuestion.METRIC_TREND: VisualizationPolicy(
        question=VisualizationQuestion.METRIC_TREND,
        view=VisualizationView.LINE,
        renderer=VisualizationRenderer.FLINT_CHARTJS,
        required_roles=("time", "value"),
        selection_reason=(
            "A line view is appropriate because the metric has an explicit order in time."
        ),
        reading_guide=(
            "Follow the ordered points from left to right; breaks remain breaks because "
            "Pivotglass does not silently interpolate missing values."
        ),
        guardrail="Do not interpolate missing values or create unreadable multi-series lines.",
    ),
    VisualizationQuestion.EVIDENCE_COMPOSITION: VisualizationPolicy(
        question=VisualizationQuestion.EVIDENCE_COMPOSITION,
        view=VisualizationView.BAR,
        renderer=VisualizationRenderer.FLINT_CHARTJS,
        required_roles=("category", "value"),
        selection_reason=(
            "A bar view supports direct comparison of discrete evidence-type counts."
        ),
        reading_guide=(
            "Compare bar lengths to see which stored evidence types dominate; open the exact "
            "table when a precise count matters."
        ),
        guardrail="Count only stored records in the stated workspace scope.",
    ),
    VisualizationQuestion.PIVOT_TRAIL: VisualizationPolicy(
        question=VisualizationQuestion.PIVOT_TRAIL,
        view=VisualizationView.TIMELINE,
        renderer=VisualizationRenderer.NATIVE,
        required_roles=("time", "event"),
        selection_reason=(
            "A chronological trail preserves the order of document admissions and analyst "
            "pivots, making the route into the current investigation easy to retrace."
        ),
        reading_guide=(
            "Read from oldest to newest; each arrow is an analyst workflow transition, not "
            "an observed relationship between threats."
        ),
        guardrail="Keep workflow navigation visibly separate from evidence and threat edges.",
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
    assertion_id: str | None = None
    annotation: str | None = None


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
    selection_rationale: str = Field(min_length=1)
    reading_guide: str = Field(min_length=1)
    chart_properties: dict[str, int | float | str | bool] = Field(default_factory=dict)
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
    chart_properties: dict[str, int | float | str | bool] | None = None,
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
        selection_rationale=policy.selection_reason,
        reading_guide=policy.reading_guide,
        chart_properties=chart_properties or {},
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


def dossier_completeness_intent(workspace: str, slots: list[dict[str, Any]]) -> VisualizationIntent:
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

    objects_by_id = {str(item["id"]): item for item in objects if item.get("id")}
    indicators = [
        item for item in objects if item.get("id") and _indicator_value(item) != "unavailable"
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
            objects_by_id[scope_id] for scope_id in sorted(scope_ids) if scope_id in objects_by_id
        ]
        contribution = infer_dossier_state(connected_evidence)
        statuses = [slot.status.value for slot in contribution.slots.values()]
        assessable_scores = [
            _DOSSIER_SCORE[status] for status in statuses if _DOSSIER_SCORE.get(status) is not None
        ]
        completeness = (
            round(sum(assessable_scores) / len(assessable_scores)) if assessable_scores else 0
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
                    "related_references": [evidence_ref(related_id) for related_id in related_ids],
                    "related_to": related_labels,
                }
            )

    return _intent(
        intent_id="indicator-constellation",
        title="Investigation constellation",
        question=VisualizationQuestion.INDICATOR_COMPLETENESS,
        question_text=("How complete is each investigation dimension for every stored indicator?"),
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


def task_matrix_intent(workspace: str, investigations: list[dict[str, Any]]) -> VisualizationIntent:
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
                "A blank cell means that enrichment has no authoritative job for the indicator."
            ),
        ),
    )


def pivot_trail_intent(
    workspace: str, pivot_events: list[dict[str, Any]]
) -> VisualizationIntent:
    """Render append-only analyst navigation in chronological order."""

    visible = pivot_events[-MAX_VISUALIZATION_ROWS:]
    omitted = max(0, len(pivot_events) - len(visible))
    rows = tuple(
        {
            "event_id": str(item.get("id", "")),
            "timestamp": str(item.get("created_at", "")),
            "from_kind": str(item.get("from_kind") or "start"),
            "from_ref": str(item.get("from_ref") or ""),
            "from_label": str(item.get("from_label") or "Investigation start"),
            "to_kind": str(item.get("to_kind", "unknown")),
            "to_ref": str(item.get("to_ref", "")),
            "to_label": str(item.get("to_label", "unavailable")),
            "action": str(item.get("action", "pivoted")),
            "basis": str(item.get("basis", "")),
            "created_by": str(item.get("created_by", "human")),
        }
        for item in visible
    )
    return _intent(
        intent_id="pivot-trail",
        title="Investigation pivot trail",
        question=VisualizationQuestion.PIVOT_TRAIL,
        question_text="How did I reach the current document or indicator?",
        workspace=workspace,
        description=(
            "Append-only analyst navigation and explicit document-admission events in the "
            "active workspace."
        ),
        record_count=len(rows),
        data=VisualizationData(rows=rows),
        fields={"time": "timestamp", "event": "action"},
        semantic_types={
            "event_id": "Identifier",
            "timestamp": "DateTime",
            "from_kind": "Category",
            "from_label": "Name",
            "to_kind": "Category",
            "to_label": "Name",
            "action": "Status",
            "basis": "Text",
            "created_by": "Name",
        },
        table_columns=(
            VisualizationTableColumn(key="timestamp", label="Time"),
            VisualizationTableColumn(key="from_label", label="From"),
            VisualizationTableColumn(key="action", label="Action"),
            VisualizationTableColumn(key="to_label", label="To"),
            VisualizationTableColumn(key="basis", label="Workflow basis"),
            VisualizationTableColumn(key="created_by", label="Recorded by"),
        ),
        missing_data=VisualizationMissingData(
            policy="omit_with_count" if omitted else "show",
            explanation=(
                "Only explicit analyst navigation and document-admission actions are shown. "
                "Absence of an event does not imply absence of a threat relationship."
            ),
            omitted_count=omitted,
        ),
        timezone="UTC",
        caveats=(
            "Pivot-trail arrows describe analyst workflow, never adversary causality or attribution.",
        ),
    )


def indicator_coverage_pca_intent(
    workspace: str,
    constellation: VisualizationIntent,
) -> VisualizationIntent:
    """Project comparable dossier-coverage profiles onto two principal components.

    PCA is deterministic descriptive geometry over the already-derived
    completeness states. It does not create graph edges, attribution, or
    confidence. Deferred dimensions are excluded rather than imputed.
    """

    grouped: dict[str, dict[str, Any]] = {}
    for row in constellation.data.rows:
        reference = str(row.get("reference", ""))
        if not reference:
            continue
        record = grouped.setdefault(
            reference,
            {
                "reference": reference,
                "indicator": str(row.get("indicator", "unavailable")),
                "indicator_type": str(row.get("indicator_type", "unknown")),
                "scores": {},
            },
        )
        status = str(row.get("status", "deferred"))
        record["scores"][str(row.get("dimension", "unknown"))] = _DOSSIER_SCORE.get(status)

    records = [grouped[key] for key in sorted(grouped)]
    dimensions = [dimension.value for dimension in DossierSlotName]
    eligible_dimensions = []
    for dimension in dimensions:
        values = [record["scores"].get(dimension) for record in records]
        if any(value is None for value in values):
            continue
        numeric = [float(value) for value in values]
        if len(numeric) >= 2 and max(numeric) - min(numeric) > 1e-12:  # noqa: PLR2004
            eligible_dimensions.append(dimension)

    rows: tuple[dict[str, Any], ...] = ()
    explained = (0.0, 0.0)
    if len(records) >= 3 and len(eligible_dimensions) >= 2:  # noqa: PLR2004
        matrix = [
            [float(record["scores"][dimension]) for dimension in eligible_dimensions]
            for record in records
        ]
        standardized = _standardize_columns(matrix)
        covariance = _covariance_matrix(standardized)
        first_value, first_vector = _leading_eigenpair(covariance)
        deflated = [
            [
                covariance[row_index][column_index]
                - first_value * first_vector[row_index] * first_vector[column_index]
                for column_index in range(len(covariance))
            ]
            for row_index in range(len(covariance))
        ]
        second_value, second_vector = _leading_eigenpair(deflated)
        total_variance = sum(covariance[index][index] for index in range(len(covariance)))
        if total_variance > 1e-12:
            explained = (
                round(max(0.0, first_value) / total_variance * 100, 2),
                round(max(0.0, second_value) / total_variance * 100, 2),
            )
        rows = tuple(
            {
                "reference": record["reference"],
                "indicator": record["indicator"],
                "indicator_type": record["indicator_type"],
                "pc1": round(_dot(vector, first_vector), 6),
                "pc2": round(_dot(vector, second_vector), 6),
                "pc1_variance_percent": explained[0],
                "pc2_variance_percent": explained[1],
                "feature_profile": ", ".join(
                    f"{dimension}={record['scores'][dimension]}"
                    for dimension in eligible_dimensions
                ),
            }
            for record, vector in zip(records, standardized, strict=True)
        )

    excluded_dimensions = [
        dimension for dimension in dimensions if dimension not in eligible_dimensions
    ]
    ready = bool(rows)
    return _intent(
        intent_id="indicator-coverage-pca",
        title="Indicator coverage similarity",
        question=VisualizationQuestion.NUMERIC_CORRELATION,
        question_text=(
            "Which indicators have similar evidence-coverage profiles across dossier dimensions?"
        ),
        workspace=workspace,
        description=(
            "Principal-component projection of comparable, source-derived dossier coverage "
            "states for stored indicators."
        ),
        record_count=len(records),
        data=VisualizationData(rows=rows),
        fields={"x": "pc1", "y": "pc2", "series": "indicator_type"},
        semantic_types={
            "reference": "Identifier",
            "indicator": "Name",
            "indicator_type": "Category",
            "pc1": "Number",
            "pc2": "Number",
            "pc1_variance_percent": "Percentage",
            "pc2_variance_percent": "Percentage",
            "feature_profile": "Text",
        },
        table_columns=(
            VisualizationTableColumn(key="indicator", label="Indicator"),
            VisualizationTableColumn(key="indicator_type", label="IoC type"),
            VisualizationTableColumn(key="pc1", label="Principal component 1"),
            VisualizationTableColumn(key="pc2", label="Principal component 2"),
            VisualizationTableColumn(key="pc1_variance_percent", label="PC1 variance (%)"),
            VisualizationTableColumn(key="pc2_variance_percent", label="PC2 variance (%)"),
            VisualizationTableColumn(key="feature_profile", label="Exact coverage inputs"),
        ),
        missing_data=VisualizationMissingData(
            policy="omit_with_count" if excluded_dimensions else "show",
            explanation=(
                "Deferred, unavailable, or zero-variance dimensions are excluded, never "
                "imputed. At least three indicators and two comparable varying dimensions "
                "are required."
            ),
            omitted_count=len(excluded_dimensions),
        ),
        caveats=(
            (
                f"PC1 explains {explained[0]}% and PC2 explains {explained[1]}% of included "
                "coverage variance."
                if ready
                else "Insufficient comparable variation for a two-component projection."
            ),
            "Distance represents similarity in coverage completeness, not a relationship, "
            "shared actor, maliciousness, or analytical confidence.",
            f"Included dimensions: {', '.join(eligible_dimensions) or 'none'}. Excluded: "
            f"{', '.join(excluded_dimensions) or 'none'}.",
        ),
    )


def competing_hypotheses_matrix_intent(
    workspace: str,
    analysis: dict[str, Any],
) -> VisualizationIntent:
    """Compare recorded evidence stances across competing hypotheses.

    The matrix is a direct projection of persisted evidence links. It never
    assigns a stance to an unlinked source/hypothesis pair and it retains
    mixed support/contradiction as an explicit review state.
    """

    hypotheses = sorted(
        analysis.get("hypotheses", ()),
        key=lambda row: (str(row.get("created_at", "")), str(row.get("id", ""))),
    )
    hypothesis_ids = {str(row.get("id", "")) for row in hypotheses if row.get("id")}
    evidence_links = [
        row
        for row in analysis.get("evidence_links", ())
        if row.get("source_id")
        and str(row.get("target_kind", "")) == "hypothesis"
        and str(row.get("target_id", "")) in hypothesis_ids
    ]
    sources: dict[tuple[str, str], dict[str, Any]] = {}
    for kind, collection, label_field in (
        ("observation", analysis.get("observations", ()), "entity_value"),
        ("assertion", analysis.get("assertions", ()), "statement"),
    ):
        for row in collection:
            record_id = str(row.get("id", ""))
            if not record_id:
                continue
            sources[(kind, record_id)] = {
                "source_kind": kind,
                "source_id": record_id,
                "evidence": str(row.get(label_field) or row.get("entity_ref") or record_id),
            }
    linked_source_keys = sorted(
        {
            (str(link.get("source_kind", "")), str(link.get("source_id", "")))
            for link in evidence_links
            if (str(link.get("source_kind", "")), str(link.get("source_id", ""))) in sources
        }
    )
    matrix_ready = len(hypotheses) >= 2 and bool(linked_source_keys)  # noqa: PLR2004
    per_hypothesis_limit = max(1, MAX_VISUALIZATION_ROWS // max(1, len(hypotheses)))
    visible_source_keys = linked_source_keys[:per_hypothesis_limit] if matrix_ready else []
    omitted_sources = max(0, len(linked_source_keys) - len(visible_source_keys))
    indexed_links: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for link in evidence_links:
        key = (
            str(link.get("source_kind", "")),
            str(link.get("source_id", "")),
            str(link.get("target_id", "")),
        )
        indexed_links.setdefault(key, []).append(link)

    rows: list[dict[str, Any]] = []
    for source_key in visible_source_keys:
        source = sources[source_key]
        for index, hypothesis in enumerate(hypotheses, start=1):
            target_id = str(hypothesis.get("id", ""))
            links = indexed_links.get((*source_key, target_id), [])
            stances = sorted({str(link.get("stance", "")) for link in links if link.get("stance")})
            status = "not_assessed" if not stances else stances[0] if len(stances) == 1 else "mixed"
            rationale = " | ".join(
                sorted({str(link.get("rationale", "")) for link in links if link.get("rationale")})
            )
            statement = str(hypothesis.get("statement") or target_id)
            rows.append(
                {
                    **source,
                    "hypothesis": f"H{index} · {statement}",
                    "hypothesis_id": target_id,
                    "hypothesis_status": str(hypothesis.get("status", "proposed")),
                    "stance": status,
                    "rationale": rationale or "No analyst-recorded assessment.",
                    "link_count": len(links),
                }
            )

    return _intent(
        intent_id="competing-hypotheses-matrix",
        title="Competing hypotheses matrix",
        question=VisualizationQuestion.COMPETING_HYPOTHESES,
        question_text="Which evidence supports or contradicts each competing hypothesis?",
        workspace=workspace,
        description=(
            "Analyst-recorded observation or assertion stances against persisted hypotheses."
        ),
        record_count=len(visible_source_keys),
        data=VisualizationData(rows=tuple(rows)),
        fields={
            "row": "evidence",
            "row_id": "source_id",
            "column": "hypothesis",
            "status": "stance",
        },
        semantic_types={
            "source_kind": "Category",
            "source_id": "Identifier",
            "evidence": "Text",
            "hypothesis": "Category",
            "hypothesis_id": "Identifier",
            "hypothesis_status": "Status",
            "stance": "Status",
            "rationale": "Text",
            "link_count": "Count",
        },
        table_columns=(
            VisualizationTableColumn(key="evidence", label="Evidence or assertion"),
            VisualizationTableColumn(key="source_kind", label="Source kind"),
            VisualizationTableColumn(key="hypothesis", label="Hypothesis"),
            VisualizationTableColumn(key="hypothesis_status", label="Hypothesis status"),
            VisualizationTableColumn(key="stance", label="Recorded stance"),
            VisualizationTableColumn(key="rationale", label="Analyst rationale"),
            VisualizationTableColumn(key="link_count", label="Recorded links"),
        ),
        missing_data=VisualizationMissingData(
            policy="omit_with_count" if omitted_sources else "show",
            explanation=(
                "Every visible source is crossed with every hypothesis. Cells without a "
                "persisted stance are shown as not assessed; they are not treated as neutral. "
                "At least two hypotheses and one linked evidence source are required."
            ),
            omitted_count=omitted_sources,
        ),
        caveats=(
            "Support and contradiction are analyst-recorded assessments, not properties "
            "inferred by the visualization.",
            "Mixed means the ledger contains both supporting and contradicting links for "
            "the same source/hypothesis pair and requires review.",
        ),
    )


def scientific_investigation_hierarchy_intent(
    workspace: str,
    analysis: dict[str, Any],
) -> VisualizationIntent:
    """Project persisted scientific-workflow membership as a bounded tree."""

    rows: list[dict[str, Any]] = []
    omitted = 0
    root_id = f"workspace:{workspace}"
    root_label = f"Workspace · {workspace}"

    def add_edge(
        *,
        parent_id: str,
        parent_label: str,
        child_id: str,
        child_label: str,
        child_kind: str,
        status: str,
        depth: int,
        path: str,
    ) -> None:
        nonlocal omitted
        if len(rows) >= MAX_VISUALIZATION_ROWS:
            omitted += 1
            return
        rows.append(
            {
                "parent_id": parent_id,
                "parent_label": parent_label,
                "child_id": child_id,
                "child_label": child_label,
                "child_kind": child_kind,
                "status": status,
                "depth": depth,
                "path": path,
            }
        )

    investigations = sorted(
        analysis.get("investigations", ()),
        key=lambda row: (str(row.get("created_at", "")), str(row.get("id", ""))),
    )
    lifecycle_items = list(analysis.get("lifecycle_items", ()))
    question_investigations = {
        str(item.get("record_id", "")): str(item.get("investigation_id", ""))
        for item in lifecycle_items
        if str(item.get("record_kind", "")) == "question" and item.get("record_id")
    }
    questions_by_investigation: dict[str, list[dict[str, Any]]] = {}
    for question in analysis.get("questions", ()):
        questions_by_investigation.setdefault(
            question_investigations.get(str(question.get("id", "")), ""), []
        ).append(question)
    hypotheses_by_question: dict[str, list[dict[str, Any]]] = {}
    for hypothesis in analysis.get("hypotheses", ()):
        hypotheses_by_question.setdefault(str(hypothesis.get("question_id", "")), []).append(
            hypothesis
        )
    lifecycle_by_investigation: dict[str, list[dict[str, Any]]] = {}
    for item in lifecycle_items:
        if str(item.get("record_kind", "")) in {"question", "hypothesis"}:
            continue
        lifecycle_by_investigation.setdefault(str(item.get("investigation_id", "")), []).append(
            item
        )

    for investigation in investigations:
        investigation_id = str(investigation.get("id", ""))
        if not investigation_id:
            continue
        investigation_label = str(investigation.get("title") or investigation_id)
        investigation_path = f"{root_label} / {investigation_label}"
        add_edge(
            parent_id=root_id,
            parent_label=root_label,
            child_id=f"investigation:{investigation_id}",
            child_label=investigation_label,
            child_kind="investigation",
            status=str(investigation.get("status", "unknown")),
            depth=1,
            path=investigation_path,
        )
        for question in sorted(
            questions_by_investigation.get(investigation_id, ()),
            key=lambda row: (str(row.get("created_at", "")), str(row.get("id", ""))),
        ):
            question_id = str(question.get("id", ""))
            if not question_id:
                continue
            question_label = str(question.get("text") or question_id)
            question_path = f"{investigation_path} / {question_label}"
            add_edge(
                parent_id=f"investigation:{investigation_id}",
                parent_label=investigation_label,
                child_id=f"question:{question_id}",
                child_label=question_label,
                child_kind="question",
                status=str(question.get("status", "open")),
                depth=2,
                path=question_path,
            )
            for hypothesis in sorted(
                hypotheses_by_question.get(question_id, ()),
                key=lambda row: (str(row.get("created_at", "")), str(row.get("id", ""))),
            ):
                hypothesis_id = str(hypothesis.get("id", ""))
                if not hypothesis_id:
                    continue
                hypothesis_label = str(hypothesis.get("statement") or hypothesis_id)
                add_edge(
                    parent_id=f"question:{question_id}",
                    parent_label=question_label,
                    child_id=f"hypothesis:{hypothesis_id}",
                    child_label=hypothesis_label,
                    child_kind="hypothesis",
                    status=str(hypothesis.get("status", "proposed")),
                    depth=3,
                    path=f"{question_path} / {hypothesis_label}",
                )
        for item in sorted(
            lifecycle_by_investigation.get(investigation_id, ()),
            key=lambda row: (str(row.get("created_at", "")), str(row.get("id", ""))),
        ):
            item_id = str(item.get("id", ""))
            if not item_id:
                continue
            item_kind = str(item.get("item_type", "workflow_item"))
            item_label = str(item.get("statement") or item_id)
            add_edge(
                parent_id=f"investigation:{investigation_id}",
                parent_label=investigation_label,
                child_id=f"lifecycle:{item_id}",
                child_label=item_label,
                child_kind=item_kind,
                status=str(item.get("status", "open")),
                depth=2,
                path=f"{investigation_path} / {item_label}",
            )

    return _intent(
        intent_id="scientific-investigation-hierarchy",
        title="Investigation hierarchy",
        question=VisualizationQuestion.HIERARCHY,
        question_text="How does this scientific investigation divide into questions and tests?",
        workspace=workspace,
        description=(
            "Persisted scientific investigations, questions, hypotheses, and lifecycle items."
        ),
        record_count=len(rows),
        data=VisualizationData(rows=tuple(rows)),
        fields={"parent": "parent_label", "child": "child_label"},
        semantic_types={
            "parent_id": "Identifier",
            "parent_label": "Text",
            "child_id": "Identifier",
            "child_label": "Text",
            "child_kind": "Category",
            "status": "Status",
            "depth": "Count",
            "path": "Text",
        },
        table_columns=(
            VisualizationTableColumn(key="parent_label", label="Parent"),
            VisualizationTableColumn(key="child_label", label="Child"),
            VisualizationTableColumn(key="child_kind", label="Record kind"),
            VisualizationTableColumn(key="status", label="Status"),
            VisualizationTableColumn(key="depth", label="Depth"),
            VisualizationTableColumn(key="path", label="Full path"),
        ),
        missing_data=VisualizationMissingData(
            policy="omit_with_count" if omitted else "show",
            explanation=(
                "Only persisted parent-child membership is shown. Records beyond the bounded "
                "rendering limit remain stored and are counted as omitted."
            ),
            omitted_count=omitted,
        ),
        caveats=(
            "Tree position represents scientific-workflow membership, not evidentiary support, "
            "causality, attribution, or confidence.",
        ),
    )


def recorded_uncertainty_intent(
    workspace: str,
    analysis: dict[str, Any],
) -> VisualizationIntent:
    """Show recorded likelihood intervals without turning confidence into probability."""

    targets: dict[tuple[str, str], str] = {}
    for kind, collection in (
        ("assertion", analysis.get("assertions", ())),
        ("hypothesis", analysis.get("hypotheses", ())),
    ):
        for row in collection:
            record_id = str(row.get("id", ""))
            if record_id:
                targets[(kind, record_id)] = str(
                    row.get("statement") or row.get("text") or record_id
                )

    latest_confidence: dict[tuple[str, str], dict[str, Any]] = {}
    for row in sorted(
        analysis.get("confidence", ()),
        key=lambda item: (str(item.get("created_at", "")), str(item.get("id", ""))),
    ):
        key = (str(row.get("target_kind", "")), str(row.get("target_id", "")))
        latest_confidence[key] = row

    rows: list[dict[str, Any]] = []
    invalid = 0
    for likelihood in sorted(
        analysis.get("likelihood", ()),
        key=lambda item: (str(item.get("created_at", "")), str(item.get("id", ""))),
    ):
        target_kind = str(likelihood.get("target_kind", ""))
        target_id = str(likelihood.get("target_id", ""))
        minimum = likelihood.get("probability_min")
        maximum = likelihood.get("probability_max")
        if (
            isinstance(minimum, bool)
            or isinstance(maximum, bool)
            or not isinstance(minimum, (int, float))
            or not isinstance(maximum, (int, float))
            or minimum < 0
            or maximum > 1
            or minimum > maximum
        ):
            invalid += 1
            continue
        confidence = latest_confidence.get((target_kind, target_id), {})
        rows.append(
            {
                "target": targets.get((target_kind, target_id), target_id or "unavailable"),
                "target_kind": target_kind or "unknown",
                "target_id": target_id,
                "likelihood_term": str(likelihood.get("term", "unavailable")).replace("_", " "),
                "probability_min_percent": round(float(minimum) * 100, 2),
                "probability_max_percent": round(float(maximum) * 100, 2),
                "likelihood_rationale": str(likelihood.get("rationale", "")),
                "likelihood_assessor": str(likelihood.get("assessed_by", "unknown")),
                "likelihood_recorded_at": str(likelihood.get("created_at", "")),
                "confidence_level": str(confidence.get("level", "not recorded")),
                "confidence_rationale": str(
                    confidence.get("rationale", "No confidence assessment recorded.")
                ),
                "confidence_assessor": str(confidence.get("assessed_by", "not recorded")),
            }
        )

    return _intent(
        intent_id="recorded-uncertainty",
        title="Likelihood and confidence",
        question=VisualizationQuestion.RECORDED_UNCERTAINTY,
        question_text="What likelihood and analytic confidence have been recorded?",
        workspace=workspace,
        description=(
            "Persisted likelihood intervals with separate latest confidence assessments "
            "for the same assertions or hypotheses."
        ),
        record_count=len(rows),
        data=VisualizationData(rows=tuple(rows)),
        fields={
            "target": "target",
            "minimum": "probability_min_percent",
            "maximum": "probability_max_percent",
        },
        semantic_types={
            "target": "Text",
            "target_kind": "Category",
            "target_id": "Identifier",
            "likelihood_term": "Category",
            "probability_min_percent": "Percentage",
            "probability_max_percent": "Percentage",
            "likelihood_rationale": "Text",
            "likelihood_assessor": "Category",
            "likelihood_recorded_at": "DateTime",
            "confidence_level": "Category",
            "confidence_rationale": "Text",
            "confidence_assessor": "Category",
        },
        table_columns=(
            VisualizationTableColumn(key="target", label="Assertion or hypothesis"),
            VisualizationTableColumn(key="target_kind", label="Record kind"),
            VisualizationTableColumn(key="likelihood_term", label="Likelihood term"),
            VisualizationTableColumn(key="probability_min_percent", label="Minimum (%)"),
            VisualizationTableColumn(key="probability_max_percent", label="Maximum (%)"),
            VisualizationTableColumn(key="likelihood_rationale", label="Likelihood rationale"),
            VisualizationTableColumn(key="likelihood_assessor", label="Likelihood assessor"),
            VisualizationTableColumn(key="confidence_level", label="Analytic confidence"),
            VisualizationTableColumn(key="confidence_rationale", label="Confidence rationale"),
            VisualizationTableColumn(key="confidence_assessor", label="Confidence assessor"),
        ),
        missing_data=VisualizationMissingData(
            policy="omit_with_count" if invalid else "show",
            explanation=(
                "Likelihood records without a valid bounded probability interval are omitted "
                "and counted. Missing confidence remains visible as not recorded."
            ),
            omitted_count=invalid,
        ),
        caveats=(
            "Likelihood describes an assessed probability range. Analytic confidence "
            "describes the quality and sufficiency of the reasoning and evidence.",
            "The latest confidence record is shown beside each likelihood interval for "
            "context, never as a numeric transformation or combined score.",
        ),
    )


def _standardize_columns(matrix: list[list[float]]) -> list[list[float]]:
    row_count = len(matrix)
    column_count = len(matrix[0])
    means = [sum(row[column] for row in matrix) / row_count for column in range(column_count)]
    deviations = [
        math.sqrt(sum((row[column] - means[column]) ** 2 for row in matrix) / (row_count - 1))
        for column in range(column_count)
    ]
    return [
        [(row[column] - means[column]) / deviations[column] for column in range(column_count)]
        for row in matrix
    ]


def _covariance_matrix(matrix: list[list[float]]) -> list[list[float]]:
    denominator = len(matrix) - 1
    width = len(matrix[0])
    return [
        [sum(row[left] * row[right] for row in matrix) / denominator for right in range(width)]
        for left in range(width)
    ]


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _leading_eigenpair(matrix: list[list[float]]) -> tuple[float, list[float]]:
    """Return one deterministic symmetric-matrix eigenpair by power iteration."""

    width = len(matrix)
    vector = [float(index + 1) for index in range(width)]
    magnitude = math.sqrt(_dot(vector, vector))
    vector = [value / magnitude for value in vector]
    for _ in range(120):
        candidate = [_dot(row, vector) for row in matrix]
        magnitude = math.sqrt(_dot(candidate, candidate))
        if magnitude <= 1e-12:
            return 0.0, [1.0 if index == 0 else 0.0 for index in range(width)]
        candidate = [value / magnitude for value in candidate]
        if _dot(candidate, vector) < 0:
            candidate = [-value for value in candidate]
        if math.sqrt(sum((a - b) ** 2 for a, b in zip(candidate, vector, strict=True))) < 1e-10:
            vector = candidate
            break
        vector = candidate
    anchor = max(range(width), key=lambda index: abs(vector[index]))
    if vector[anchor] < 0:
        vector = [-value for value in vector]
    eigenvalue = _dot(vector, [_dot(row, vector) for row in matrix])
    return eigenvalue, vector


def relationship_graph_intent(
    workspace: str,
    graph: dict[str, Any],
    analysis: dict[str, Any] | None = None,
) -> VisualizationIntent:
    """Build an indicator-first graph intent from the persisted graph authority."""

    all_nodes = tuple(
        VisualizationNode(
            reference=str(node.get("id", "")),
            label=str(node.get("value") or "unavailable"),
            entity_type=str(node.get("type") or "unknown"),
        )
        for node in graph.get("nodes", ())
        if node.get("id")
    )
    all_node_ids = {node.reference for node in all_nodes}
    all_edges = [
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
        if edge.get("source") in all_node_ids and edge.get("target") in all_node_ids
    ]
    for assertion in (analysis or {}).get("assertions", ()):
        if (
            assertion.get("method") != "manual-graph-relation"
            or assertion.get("status") != "active"
            or assertion.get("author_kind") != "human"
            or assertion.get("subject_ref") not in all_node_ids
            or assertion.get("object_ref") not in all_node_ids
            or not assertion.get("predicate")
        ):
            continue
        all_edges.append(
            VisualizationEdge(
                source=str(assertion["subject_ref"]),
                target=str(assertion["object_ref"]),
                relationship=str(assertion["predicate"]),
                basis="manual",
                provenance=(
                    f"Analyst assertion {assertion.get('id')}: "
                    f"{assertion.get('statement') or 'No annotation'}"
                ),
                assertion_id=str(assertion["id"]),
                annotation=str(assertion.get("statement") or ""),
            )
        )
    degree = {node.reference: 0 for node in all_nodes}
    for edge in all_edges:
        degree[edge.source] += 1
        degree[edge.target] += 1
    nodes = all_nodes
    if len(nodes) > MAX_RELATIONSHIP_GRAPH_NODES:
        nodes = tuple(
            sorted(
                nodes,
                key=lambda node: (
                    -degree[node.reference],
                    node.label.casefold(),
                    node.entity_type,
                    node.reference,
                ),
            )[:MAX_RELATIONSHIP_GRAPH_NODES]
        )
    node_ids = {node.reference for node in nodes}
    edge_priority = {"manual": 0, "explicit": 1, "property": 2}
    eligible_edges = [
        edge for edge in all_edges if edge.source in node_ids and edge.target in node_ids
    ]
    edge_limit = max(0, (MAX_VISUALIZATION_ROWS - len(nodes)) // 2)
    if len(eligible_edges) > edge_limit:
        eligible_edges.sort(
            key=lambda edge: (
                edge_priority[edge.basis],
                edge.source,
                edge.target,
                edge.relationship,
                edge.assertion_id or "",
            )
        )
    edges_tuple = tuple(eligible_edges[:edge_limit])
    omitted = (len(all_nodes) - len(nodes)) + (len(all_edges) - len(edges_tuple))
    labels = {node.reference: node.label for node in nodes}
    rows = tuple(
        {
            "source": labels[edge.source],
            "target": labels[edge.target],
            "relationship": edge.relationship,
            "basis": edge.basis,
            "provenance": edge.provenance,
            "assertion_id": edge.assertion_id,
            "annotation": edge.annotation,
        }
        for edge in edges_tuple
    )
    return _intent(
        intent_id="relationship-graph",
        title="Evidence relationships",
        question=VisualizationQuestion.ENTITY_RELATIONSHIPS,
        question_text="Which stored entities relate, and why is each edge present?",
        workspace=workspace,
        description="Stored STIX objects, explicit relationships, and conservative property pivots.",
        record_count=len(all_nodes),
        data=VisualizationData(rows=rows, nodes=nodes, edges=edges_tuple),
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
            policy="omit_with_count" if omitted else "show",
            explanation=(
                "Unconnected stored entities remain visible within the bounded view. "
                "When the graph exceeds the local rendering envelope, Pivotglass keeps "
                "the most connected entities and prioritizes analyst, stored, then property "
                "edges. Omitted records remain stored and available through graph export."
            ),
            omitted_count=omitted,
        ),
        caveats=(
            "Property pivots are navigation aids, not asserted STIX relationships.",
            "Manual edges are analyst-authored judgments with annotations, not observed facts.",
            "First/last seen and confidence remain unavailable until their persisted "
            "relationship fields exist; the visualization does not invent them.",
            "The interactive relationship view is bounded to 1,000 entities and a total "
            "of 5,000 node, edge, and exact-table records; graph export remains complete.",
        ),
    )


def relationship_degree_distribution_intent(
    workspace: str,
    graph: dict[str, Any],
    analysis: dict[str, Any] | None = None,
) -> VisualizationIntent:
    """Show the exact distribution of admitted graph-edge degree by entity."""

    admitted = relationship_graph_intent(workspace, graph, analysis)
    graph_nodes = {str(node["id"]): node for node in graph.get("nodes", ()) if node.get("id")}
    degree = {node.reference: 0 for node in admitted.data.nodes}
    for edge in admitted.data.edges:
        source = edge.source
        target = edge.target
        if source in degree and target in degree:
            degree[source] += 1
            degree[target] += 1
    rows = tuple(
        {
            "indicator": _indicator_value(graph_nodes[node_id]),
            "indicator_type": str(graph_nodes[node_id].get("type", "unknown")),
            "connection_count": degree[node_id],
        }
        for node_id in sorted(
            degree,
            key=lambda item: (_indicator_value(graph_nodes[item]).casefold(), item),
        )
    )
    omitted = max(0, len(graph_nodes) - len(rows))
    return _intent(
        intent_id="relationship-degree-distribution",
        title="Connection-count distribution",
        question=VisualizationQuestion.VALUE_DISTRIBUTION,
        question_text="How are admitted relationship counts distributed across entities?",
        workspace=workspace,
        description=(
            "Degree counts from the current relationship projection; each admitted edge "
            "contributes once to each endpoint."
        ),
        record_count=len(graph_nodes),
        data=VisualizationData(rows=rows),
        fields={"value": "connection_count"},
        semantic_types={
            "indicator": "Name",
            "indicator_type": "Category",
            "connection_count": "Count",
        },
        table_columns=(
            VisualizationTableColumn(key="indicator", label="Indicator"),
            VisualizationTableColumn(key="indicator_type", label="IoC type"),
            VisualizationTableColumn(key="connection_count", label="Admitted connections"),
        ),
        missing_data=VisualizationMissingData(
            policy="omit_with_count" if omitted else "show",
            explanation=(
                "Unconnected entities in the bounded relationship view are retained with a "
                "connection count of zero. Entities outside that view remain stored and are "
                "counted as omitted."
            ),
            omitted_count=omitted,
        ),
        chart_properties={"binCount": 10},
        caveats=(
            "Counts describe admitted graph edges, not actor importance, maliciousness, or "
            "analytic confidence.",
        ),
    )


def build_visualization_intents(
    *,
    workspace: str,
    objects: list[dict[str, Any]],
    dossier_slots: list[dict[str, Any]],
    graph: dict[str, Any],
    investigations: list[dict[str, Any]],
    analysis: dict[str, Any] | None = None,
) -> tuple[VisualizationIntent, ...]:
    """Build the initial 0.6.0 cockpit visualization set."""

    constellation = indicator_constellation_intent(workspace, objects, graph)
    return (
        constellation,
        pivot_trail_intent(workspace, (analysis or {}).get("pivot_trail", [])),
        evidence_composition_intent(workspace, objects),
        dossier_completeness_intent(workspace, dossier_slots),
        activity_concentration_intent(workspace, investigations),
        task_matrix_intent(workspace, investigations),
        relationship_graph_intent(workspace, graph, analysis),
        relationship_degree_distribution_intent(workspace, graph, analysis),
        indicator_coverage_pca_intent(workspace, constellation),
        competing_hypotheses_matrix_intent(workspace, analysis or {}),
        scientific_investigation_hierarchy_intent(workspace, analysis or {}),
        recorded_uncertainty_intent(workspace, analysis or {}),
    )
