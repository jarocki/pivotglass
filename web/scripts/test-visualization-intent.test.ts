import assert from "node:assert/strict";
import test from "node:test";

import {
  compileFlintChartjs,
  countHistogramBins,
  radarHasShape,
  exactDataExport,
  appendGraphPresentationHistory,
  bundleGraphLeaves,
  bundleReference,
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
    reading_guide: "Read each bar as the count of values in its numeric range.",
    chart_properties: { binCount: 10 },
    caveats: [],
    export_filename: "case-degree.csv",
  };
}

test("histogram intent permits only bounded Flint bin counts", () => {
  const intent = histogramIntent();
  assert.doesNotThrow(() => validateVisualizationIntent(intent));
  assert.throws(
    () => validateVisualizationIntent({ ...intent, reading_guide: "" }),
    /missing its reading guide/,
  );
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

test("count histograms bin on whole numbers, zero bins included (#36)", () => {
  assert.deepEqual(countHistogramBins([0, 1, 1, 2, 2, 2, 5], 10), {
    labels: ["0", "1", "2", "3", "4", "5"],
    counts: [1, 2, 3, 0, 0, 1],
  });
  // A span wider than the bin limit gets integer-width ranges, never fractions.
  const wide = countHistogramBins([0, 99], 10);
  assert.equal(wide.labels[0], "0\u20139");
  assert.equal(wide.counts.length, 10);
  assert.deepEqual(countHistogramBins([], 10), { labels: [], counts: [] });

  const intent = histogramIntent();
  intent.data.rows = [0, 1, 1, 2].map((connection_count) => ({ indicator: "x", connection_count }));
  const config = compileFlintChartjs(intent, { width: 640, height: 320 }) as unknown as {
    data: { labels: string[]; datasets: Array<{ data: number[] }> };
    options: { scales: { x: { title: { text: string } } } };
  };
  assert.deepEqual(config.data.labels, ["0", "1", "2"]);
  assert.deepEqual(config.data.datasets[0].data, [1, 2, 1]);
  assert.equal(config.options.scales.x.title.text, "Connections");
});

test("a radar with fewer than three non-zero spokes is drawn as bars (#38)", () => {
  const radar = (scores: Array<number | null>): VisualizationIntent => ({
    ...histogramIntent(),
    view: "radar",
    fields: { category: "facet", value: "score" },
    semantic_types: { facet: "Category", score: "Percentage" },
    chart_properties: {},
    data: { rows: scores.map((score, index) => ({ facet: `f${index}`, score })), nodes: [], edges: [] },
  });
  assert.equal(radarHasShape(radar([100, 50, 0, 0, null])), false);
  assert.equal(radarHasShape(radar([100, 50, 50, 0])), true);
});

test("same-type leaves of a hub bundle into one aggregate that keeps exact members (#41)", () => {
  const leaf = (n: number, type = "ipv4-addr") => ({ reference: `ip${n}`, label: `192.0.2.${n}`, entity_type: type });
  const nodes = [
    { reference: "hub", label: "group", entity_type: "domain-name" },
    ...Array.from({ length: 7 }, (_, n) => leaf(n)),
    { reference: "d1", label: "a.example", entity_type: "domain-name" },
    { reference: "other", label: "b.example", entity_type: "domain-name" },
  ];
  const edges = [
    ...Array.from({ length: 7 }, (_, n) => ({ source: "hub", target: `ip${n}`, relationship: "resolves", basis: "explicit" as const, provenance: "dns" })),
    { source: "hub", target: "d1", relationship: "related", basis: "explicit" as const, provenance: "x" },
    { source: "d1", target: "other", relationship: "related", basis: "explicit" as const, provenance: "x" },
  ];
  const key = bundleReference("hub", "ipv4-addr");
  const bundled = bundleGraphLeaves(nodes, edges);
  const aggregate = bundled.nodes.find((node) => node.reference === key)!;
  assert.equal(aggregate.label, "7 ipv4-addr");
  assert.equal(aggregate.evidence, false);
  assert.deepEqual(aggregate.bundle, { hub: "hub", members: ["ip0", "ip1", "ip2", "ip3", "ip4", "ip5", "ip6"] });
  assert.equal(bundled.bundled.size, 7);
  assert.ok(!bundled.nodes.some((node) => node.reference === "ip0"));
  assert.deepEqual(bundled.edges.filter((edge) => edge.target === key).map((edge) => edge.basis), ["bundle"]);
  // d1 is a single leaf of its type at the hub and has two connections: never bundled.
  assert.ok(bundled.nodes.some((node) => node.reference === "d1"));

  // A selected or pinned member stays out; below the minimum, nothing bundles.
  const guarded = bundleGraphLeaves(nodes, edges, { protectedReferences: new Set(["ip0", "ip1", "ip2"]) });
  assert.equal(guarded.bundled.size, 0);
  const oneGuarded = bundleGraphLeaves(nodes, edges, { protectedReferences: new Set(["ip0"]) });
  assert.equal(oneGuarded.nodes.find((node) => node.reference === key)!.bundle!.members.length, 6);
  assert.ok(oneGuarded.nodes.some((node) => node.reference === "ip0"));

  // Expanding restores the original nodes and edges exactly.
  const expanded = bundleGraphLeaves(nodes, edges, { expanded: new Set([key]) });
  assert.deepEqual(expanded.nodes, nodes);
  assert.deepEqual(expanded.edges, edges);
});
