import assert from "node:assert/strict";
import test from "node:test";

import {
  compileFlintChartjs,
  exactDataExport,
  appendGraphPresentationHistory,
  graphPresentationSnapshotsEqual,
  hiddenGraphReferences,
  updateGraphSelection,
  validateVisualizationIntent,
  type VisualizationIntent,
  type GraphPresentationSnapshot,
} from "../app/visualization-intent.ts";

test("graph selection is local, deterministic, and supports additive toggles", () => {
  assert.deepEqual(updateGraphSelection([], "node-a", false), ["node-a"]);
  assert.deepEqual(updateGraphSelection(["node-a"], "node-b", false), ["node-b"]);
  assert.deepEqual(updateGraphSelection(["node-a"], "node-b", true), ["node-a", "node-b"]);
  assert.deepEqual(updateGraphSelection(["node-a", "node-b"], "node-a", true), ["node-b"]);
});

test("collapsed graph branches hide only direct unprotected connections", () => {
  const edges = [
    { source: "root", target: "left", relationship: "resolves-to", basis: "explicit", provenance: "test" },
    { source: "right", target: "root", relationship: "contains", basis: "property", provenance: "test" },
    { source: "left", target: "leaf", relationship: "related-to", basis: "manual", provenance: "test" },
  ] satisfies VisualizationIntent["data"]["edges"];

  assert.deepEqual(
    [...hiddenGraphReferences(edges, new Set(["root"]))].sort(),
    ["left", "right"],
  );
  assert.deepEqual(
    [...hiddenGraphReferences(edges, new Set(["root"]), new Set(["right"]))],
    ["left"],
  );
  assert.deepEqual(
    [...hiddenGraphReferences(edges, new Set(["root", "left"]))].sort(),
    ["leaf", "right"],
  );
});

test("graph presentation history is bounded and ignores set ordering", () => {
  const snapshot = (x: number, pins: string[]): GraphPresentationSnapshot => ({
    positions: { node: { x, y: 2 } },
    viewport: { x: 0, y: 0, scale: 1 },
    labels: { node: "Visible label" },
    pinned_refs: pins,
    collapsed_refs: ["root-b", "root-a"],
  });

  assert.equal(
    graphPresentationSnapshotsEqual(
      snapshot(1, ["node-b", "node-a"]),
      { ...snapshot(1, ["node-a", "node-b"]), collapsed_refs: ["root-a", "root-b"] },
    ),
    true,
  );
  assert.equal(graphPresentationSnapshotsEqual(snapshot(1, []), snapshot(3, [])), false);
  assert.deepEqual(
    appendGraphPresentationHistory([snapshot(1, []), snapshot(2, [])], snapshot(3, []), 2)
      .map((item) => item.positions.node.x),
    [2, 3],
  );
  assert.deepEqual(
    appendGraphPresentationHistory([snapshot(1, [])], snapshot(1, [])).map(
      (item) => item.positions.node.x,
    ),
    [1],
  );
  assert.throws(() => appendGraphPresentationHistory([], snapshot(1, []), 0), /must be positive/);
});

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
