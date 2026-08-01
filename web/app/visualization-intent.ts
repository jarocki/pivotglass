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
  | "bar";

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

export function validateVisualizationIntent(intent: VisualizationIntent): void {
  if (intent.schema_version !== "1.0") {
    throw new Error(`Unsupported visualization schema ${String(intent.schema_version)}`);
  }
  if (intent.data.rows.length + intent.data.nodes.length + intent.data.edges.length > 5_000) {
    throw new Error("Visualization exceeds the local rendering limit");
  }
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
): ReturnType<typeof assembleChartjs> {
  validateVisualizationIntent(intent);
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
    },
    options: { addTooltips: true },
  });
}

function csvCell(value: unknown): string {
  const text = value === null || value === undefined
    ? ""
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);
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
