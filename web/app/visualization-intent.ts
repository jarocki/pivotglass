import { assembleChartjs } from "flint-chart";

export type VisualizationView =
  | "calendar_heatmap"
  | "radar"
  | "histogram"
  | "relationship_graph"
  | "dendrogram"
  | "scatter"
  | "task_matrix"
  | "line"
  | "bar"
  | "uncertainty_intervals";

export type VisualizationRow = Record<string, unknown>;

export type VisualizationNode = {
  reference: string;
  label: string;
  entity_type: string;
};

export type VisualizationEdge = {
  source: string;
  target: string;
  relationship: string;
  basis: "explicit" | "property" | "manual";
  provenance: string;
  assertion_id?: string | null;
  annotation?: string | null;
};

export type VisualizationIntent = {
  schema_version: "1.0";
  intent_id: string;
  title: string;
  question: string;
  question_text: string;
  view: VisualizationView;
  renderer: "flint_chartjs" | "native";
  source_scope: {
    workspace: string;
    description: string;
    record_count: number;
    timezone?: string | null;
  };
  data: {
    rows: VisualizationRow[];
    nodes: VisualizationNode[];
    edges: VisualizationEdge[];
  };
  fields: Record<string, string>;
  semantic_types: Record<string, string>;
  table_columns: Array<{ key: string; label: string }>;
  missing_data: {
    policy: "show" | "omit_with_count" | "not_applicable";
    explanation: string;
    omitted_count: number;
  };
  selection_rationale: string;
  reading_guide: string;
  chart_properties: Record<string, number | string | boolean>;
  caveats: string[];
  export_filename: string;
};

export type VisualizationTheme = {
  border_color: string;
  accent_color: string;
  heading_color: string;
  text_color: string;
  dim_color: string;
};

export type GraphPresentationSnapshot = {
  positions: Record<string, { x: number; y: number }>;
  viewport: { x: number; y: number; scale: number };
  labels: Record<string, string>;
  pinned_refs: string[];
  collapsed_refs: string[];
};

export function graphPresentationSnapshotsEqual(
  left: GraphPresentationSnapshot,
  right: GraphPresentationSnapshot,
): boolean {
  const normalized = (snapshot: GraphPresentationSnapshot) => ({
    positions: Object.fromEntries(Object.entries(snapshot.positions).sort(([a], [b]) => a.localeCompare(b))),
    viewport: snapshot.viewport,
    labels: Object.fromEntries(Object.entries(snapshot.labels).sort(([a], [b]) => a.localeCompare(b))),
    pinned_refs: [...snapshot.pinned_refs].sort(),
    collapsed_refs: [...snapshot.collapsed_refs].sort(),
  });
  return JSON.stringify(normalized(left)) === JSON.stringify(normalized(right));
}

export function appendGraphPresentationHistory(
  history: readonly GraphPresentationSnapshot[],
  snapshot: GraphPresentationSnapshot,
  limit = 50,
): GraphPresentationSnapshot[] {
  if (!Number.isInteger(limit) || limit < 1) throw new Error("Graph history limit must be positive");
  if (history.length && graphPresentationSnapshotsEqual(history.at(-1)!, snapshot)) {
    return [...history];
  }
  return [...history, snapshot].slice(-limit);
}

export function updateGraphSelection(
  current: readonly string[],
  reference: string,
  additive: boolean,
): string[] {
  if (!additive) return [reference];
  if (current.includes(reference)) {
    return current.filter((candidate) => candidate !== reference);
  }
  return [...current, reference];
}

export function hiddenGraphReferences(
  edges: readonly VisualizationEdge[],
  collapsedRoots: ReadonlySet<string>,
  protectedReferences: ReadonlySet<string> = new Set(),
): Set<string> {
  const hidden = new Set<string>();
  for (const edge of edges) {
    if (collapsedRoots.has(edge.source)) hidden.add(edge.target);
    if (collapsedRoots.has(edge.target)) hidden.add(edge.source);
  }
  for (const reference of collapsedRoots) hidden.delete(reference);
  for (const reference of protectedReferences) hidden.delete(reference);
  return hidden;
}

const FLINT_CHART_TYPES: Partial<Record<VisualizationView, string>> = {
  bar: "Bar Chart",
  histogram: "Histogram",
  line: "Line Chart",
  radar: "Radar Chart",
  scatter: "Scatter Plot",
};

const REQUIRED_FIELDS: Partial<Record<VisualizationView, string[]>> = {
  bar: ["category", "value"],
  histogram: ["value"],
  line: ["time", "value"],
  radar: ["category", "value"],
  scatter: ["x", "y"],
};

function validateChartProperties(
  view: VisualizationView,
  chartProperties: Record<string, number | string | boolean>,
): void {
  const propertyKeys = Object.keys(chartProperties);
  if (propertyKeys.some((key) => key !== "binCount")) {
    throw new Error("Visualization contains a chart property outside the allow-list");
  }
  if ("binCount" in chartProperties) {
    const binCount = chartProperties.binCount;
    if (
      view !== "histogram"
      || typeof binCount !== "number"
      || !Number.isInteger(binCount)
      || binCount < 5
      || binCount > 50
    ) {
      throw new Error("Histogram bin count must be an integer from 5 to 50");
    }
  }
}

export function validateVisualizationIntent(intent: VisualizationIntent): void {
  if (intent.schema_version !== "1.0") {
    throw new Error(`Unsupported visualization schema ${String(intent.schema_version)}`);
  }
  if (intent.data.rows.length + intent.data.nodes.length + intent.data.edges.length > 5_000) {
    throw new Error("Visualization exceeds the local rendering limit");
  }
  if (!intent.selection_rationale.trim()) {
    throw new Error("Visualization is missing its selection rationale");
  }
  if (!intent.reading_guide.trim()) {
    throw new Error("Visualization is missing its reading guide");
  }
  validateChartProperties(intent.view, intent.chart_properties);
  if (intent.renderer === "flint_chartjs") {
    const chartType = FLINT_CHART_TYPES[intent.view];
    if (!chartType) throw new Error(`View ${intent.view} is not allowed for Flint/Chart.js`);
    for (const role of REQUIRED_FIELDS[intent.view] ?? []) {
      if (!intent.fields[role]) throw new Error(`Visualization is missing the ${role} field`);
    }
  }
}

export function plottedRows(intent: VisualizationIntent): VisualizationRow[] {
  const requiredFields = (REQUIRED_FIELDS[intent.view] ?? [])
    .map((role) => intent.fields[role])
    .filter(Boolean);
  return intent.data.rows.filter((row) =>
    requiredFields.every((field) => row[field] !== null && row[field] !== undefined),
  );
}

export function compileFlintChartjs(
  intent: VisualizationIntent,
  size: { width: number; height: number },
  chartProperties: Record<string, number | string | boolean> = intent.chart_properties,
): ReturnType<typeof assembleChartjs> {
  validateVisualizationIntent(intent);
  validateChartProperties(intent.view, chartProperties);
  if (intent.renderer !== "flint_chartjs") {
    throw new Error(`View ${intent.view} does not use the Flint/Chart.js renderer`);
  }
  const chartType = FLINT_CHART_TYPES[intent.view];
  if (!chartType) throw new Error(`No allow-listed Flint chart for ${intent.view}`);

  const encodings: Record<string, { field: string }> = {};
  if (intent.view === "histogram") {
    encodings.x = { field: intent.fields.value };
  } else if (intent.view === "radar" || intent.view === "bar") {
    encodings.x = { field: intent.fields.category };
    encodings.y = { field: intent.fields.value };
  } else if (intent.view === "line") {
    encodings.x = { field: intent.fields.time };
    encodings.y = { field: intent.fields.value };
    if (intent.fields.series) encodings.color = { field: intent.fields.series };
  } else if (intent.view === "scatter") {
    encodings.x = { field: intent.fields.x };
    encodings.y = { field: intent.fields.y };
    if (intent.fields.series) encodings.color = { field: intent.fields.series };
  }

  return assembleChartjs({
    data: { values: plottedRows(intent) },
    semantic_types: intent.semantic_types,
    chart_spec: {
      chartType,
      encodings,
      baseSize: {
        width: Math.max(320, Math.min(1_200, Math.round(size.width))),
        height: Math.max(240, Math.min(640, Math.round(size.height))),
      },
      chartProperties,
    },
    options: { addTooltips: true },
  });
}

function csvCell(value: unknown): string {
  const raw = value === null || value === undefined
    ? ""
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);
  const text = /^[=+\-@]/.test(raw.trimStart()) ? `'${raw}` : raw;
  return `"${text.replaceAll('"', '""')}"`;
}

export function exactDataExport(intent: VisualizationIntent): {
  content: string;
  mime: string;
  filename: string;
} {
  validateVisualizationIntent(intent);
  if (intent.view === "relationship_graph") {
    return {
      content: JSON.stringify(
        {
          schema_version: intent.schema_version,
          question: intent.question_text,
          source_scope: intent.source_scope,
          nodes: intent.data.nodes,
          edges: intent.data.edges,
        },
        null,
        2,
      ),
      mime: "application/json",
      filename: intent.export_filename.replace(/\.csv$/i, ".json"),
    };
  }
  const keys = intent.table_columns.map((column) => column.key);
  const header = intent.table_columns.map((column) => csvCell(column.label)).join(",");
  const body = intent.data.rows.map((row) => keys.map((key) => csvCell(row[key])).join(","));
  return {
    content: [header, ...body].join("\n"),
    mime: "text/csv",
    filename: intent.export_filename,
  };
}
