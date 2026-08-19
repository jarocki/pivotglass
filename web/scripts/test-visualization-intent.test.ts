import assert from "node:assert/strict";
import test from "node:test";

import {
  compileFlintChartjs,
  exactDataExport,
  validateVisualizationIntent,
  type VisualizationIntent,
} from "../app/visualization-intent.ts";

function histogramIntent(): VisualizationIntent {
  return {
    schema_version: "1.0",
    intent_id: "relationship-degree-distribution",
    title: "Connection-count distribution",
    question: "how_are_values_distributed",
    question_text: "How are admitted relationship counts distributed across entities?",
    view: "histogram",
    renderer: "flint_chartjs",
    source_scope: {
      workspace: "case",
      description: "Admitted graph degree.",
      record_count: 1,
    },
    data: {
      rows: [{ indicator: "=HYPERLINK(\"https://invalid.test\")", connection_count: 2 }],
      nodes: [],
      edges: [],
    },
    fields: { value: "connection_count" },
    semantic_types: { indicator: "Name", connection_count: "Count" },
    table_columns: [
      { key: "indicator", label: "Indicator" },
      { key: "connection_count", label: "Connections" },
    ],
    missing_data: {
      policy: "show",
      explanation: "Zero-degree entities remain visible.",
      omitted_count: 0,
    },
    selection_rationale: "A histogram exposes the shape of one numeric distribution.",
    chart_properties: { binCount: 10 },
    caveats: [],
    export_filename: "case-degree.csv",
  };
}

test("histogram intent permits only bounded Flint bin counts", () => {
  const intent = histogramIntent();
  assert.doesNotThrow(() => validateVisualizationIntent(intent));
  assert.throws(
    () => validateVisualizationIntent({ ...intent, chart_properties: { binCount: 51 } }),
    /integer from 5 to 50/,
  );
  assert.throws(
    () => validateVisualizationIntent({ ...intent, chart_properties: { arbitrary: 1 } }),
    /outside the allow-list/,
  );
  assert.throws(
    () => compileFlintChartjs(intent, { width: 640, height: 320 }, { arbitrary: 1 }),
    /outside the allow-list/,
  );
});

test("CSV exact-data export neutralizes spreadsheet formulas", () => {
  const exported = exactDataExport(histogramIntent());
  assert.equal(exported.mime, "text/csv");
  assert.match(exported.content, /'=HYPERLINK/);
  assert.doesNotMatch(exported.content, /,"=HYPERLINK/);
});
