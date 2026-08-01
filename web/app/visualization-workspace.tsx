"use client";

import { CSSProperties, useEffect, useMemo, useRef, useState } from "react";
import { Chart, registerables } from "chart.js";

import {
  compileFlintChartjs,
  exactDataExport,
  plottedRows,
  validateVisualizationIntent,
  type VisualizationIntent,
  type VisualizationRow,
  type VisualizationTheme,
} from "./visualization-intent";

Chart.register(...registerables);

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Unavailable";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function shortLabel(value: string, limit = 30): string {
  if (value.length <= limit) return value;
  const side = Math.floor((limit - 3) / 2);
  return `${value.slice(0, side)}...${value.slice(-side)}`;
}

function FlintCanvas({
  intent,
  theme,
}: {
  intent: VisualizationIntent;
  theme: VisualizationTheme;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [error, setError] = useState("");
  const rows = plottedRows(intent);

  useEffect(() => {
    if (!canvas.current || rows.length === 0) return;
    let chart: Chart | undefined;
    try {
      setError("");
      const width = canvas.current.parentElement?.clientWidth ?? 620;
      const config = compileFlintChartjs(intent, { width, height: 320 });
      const themed = config as typeof config & {
        options?: Record<string, unknown>;
        data: { datasets?: Array<Record<string, unknown>> };
      };
      const options = (themed.options ?? {}) as Record<string, unknown>;
      const plugins = (options.plugins ?? {}) as Record<string, unknown>;
      const scales = (options.scales ?? {}) as Record<string, Record<string, unknown>>;
      for (const scale of Object.values(scales)) {
        const ticks = (scale.ticks ?? {}) as Record<string, unknown>;
        const grid = (scale.grid ?? {}) as Record<string, unknown>;
        scale.ticks = { ...ticks, color: theme.dim_color };
        scale.grid = { ...grid, color: `${theme.border_color}33` };
        const pointLabels = scale.pointLabels as Record<string, unknown> | undefined;
        if (pointLabels) scale.pointLabels = { ...pointLabels, color: theme.text_color };
      }
      themed.options = {
        ...options,
        color: theme.text_color,
        plugins,
        scales,
      };
      for (const dataset of themed.data.datasets ?? []) {
        dataset.borderColor = theme.accent_color;
        dataset.backgroundColor = `${theme.accent_color}42`;
        dataset.pointBackgroundColor = theme.heading_color;
        dataset.borderWidth = 2;
      }
      chart = new Chart(canvas.current, themed as never);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    return () => chart?.destroy();
  }, [
    intent,
    rows.length,
    theme.accent_color,
    theme.border_color,
    theme.dim_color,
    theme.heading_color,
    theme.text_color,
  ]);

  if (error) return <div className="visualization-error">Unable to render: {error}</div>;
  if (rows.length === 0) return <VisualizationEmpty intent={intent} />;
  return (
    <div className="flint-canvas">
      <canvas
        ref={canvas}
        role="img"
        aria-label={`${intent.title}. ${intent.question_text}`}
      />
    </div>
  );
}

function VisualizationEmpty({ intent }: { intent: VisualizationIntent }) {
  return (
    <div className="visualization-empty">
      <b>NO DATA IN SCOPE</b>
      <span>{intent.source_scope.description}</span>
    </div>
  );
}

function AccessibleDataTable({ intent }: { intent: VisualizationIntent }) {
  if (intent.data.rows.length === 0) return null;
  return (
    <div className="visualization-table-wrap">
      <table className="visualization-table">
        <caption>Exact plotted data · {intent.source_scope.workspace}</caption>
        <thead>
          <tr>
            {intent.table_columns.map((column) => (
              <th scope="col" key={column.key}>{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {intent.data.rows.map((row, index) => (
            <tr key={`${intent.intent_id}-${index}`}>
              {intent.table_columns.map((column) => (
                <td key={column.key}>{displayValue(row[column.key])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CalendarHeatmap({ intent }: { intent: VisualizationIntent }) {
  const days = useMemo(() => {
    const counts = new Map(
      intent.data.rows.map((row) => [String(row.date), Number(row.count) || 0]),
    );
    if (counts.size === 0) return [];
    const ordered = [...counts.keys()].sort();
    const start = new Date(`${ordered[0]}T00:00:00Z`);
    const end = new Date(`${ordered[ordered.length - 1]}T00:00:00Z`);
    const span = Math.min(366, Math.floor((end.getTime() - start.getTime()) / 86_400_000) + 1);
    const result: Array<{ date: string; count: number; padding?: boolean }> = Array.from(
      { length: start.getUTCDay() },
      () => ({ date: "", count: 0, padding: true }),
    );
    for (let offset = 0; offset < span; offset += 1) {
      const day = new Date(start.getTime() + offset * 86_400_000).toISOString().slice(0, 10);
      result.push({ date: day, count: counts.get(day) ?? 0 });
    }
    return result;
  }, [intent.data.rows]);
  const maximum = Math.max(1, ...days.map((day) => day.count));

  if (days.length === 0) return <VisualizationEmpty intent={intent} />;
  return (
    <div className="calendar-visualization">
      <div className="calendar-weekdays" aria-hidden="true">
        {["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"].map((day) => <span key={day}>{day}</span>)}
      </div>
      <div className="calendar-grid" role="grid" aria-label={`${intent.title}, UTC`}>
        {days.map((day, index) => day.padding
          ? <span className="calendar-day padding" aria-hidden="true" key={`padding-${index}`} />
          : (
            <time
              className={`calendar-day ${day.count === 0 ? "zero" : ""}`}
              dateTime={day.date}
              key={day.date}
              style={{ "--day-intensity": `${Math.round((day.count / maximum) * 70) + 12}%` } as CSSProperties}
              aria-label={`${day.date}: ${day.count} events`}
            >
              <b>{day.count}</b>
              <span>{day.date.slice(5)}</span>
            </time>
          ))}
      </div>
    </div>
  );
}

const TERMINAL_GLYPH: Record<string, string> = {
  planned: "○",
  queued: "◷",
  running: "◌",
  succeeded: "✓",
  filled: "●",
  partial: "◐",
  deferred: "◇",
  empty: "∅",
  failed: "!",
  skipped: "↷",
  cancelled: "×",
};

function TaskMatrix({
  intent,
  onOpenEvidence,
}: {
  intent: VisualizationIntent;
  onOpenEvidence?: (reference: string, origin: HTMLElement) => void;
}) {
  const [selected, setSelected] = useState<VisualizationRow | null>(null);
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [completenessFilter, setCompletenessFilter] = useState("all");
  const [relatedReference, setRelatedReference] = useState("");
  const [firstSeenAfter, setFirstSeenAfter] = useState("");
  const [lastSeenBefore, setLastSeenBefore] = useState("");
  const [sortOrder, setSortOrder] = useState("last_desc");
  const rowField = intent.fields.row;
  const rowIdField = intent.fields.row_id ?? rowField;
  const columnField = intent.fields.column;
  const statusField = intent.fields.status;
  const isConstellation = intent.intent_id === "indicator-constellation";
  const metadata = useMemo(() => {
    const values = new Map<string, VisualizationRow>();
    for (const row of intent.data.rows) {
      const rowId = String(row[rowIdField]);
      if (!values.has(rowId)) values.set(rowId, row);
    }
    return values;
  }, [intent.data.rows, rowIdField]);
  const columns = useMemo(
    () => [...new Set(intent.data.rows.map((row) => String(row[columnField])))],
    [columnField, intent.data.rows],
  );
  const types = useMemo(
    () => [...new Set([...metadata.values()].map((row) => String(row.indicator_type ?? "")))]
      .filter(Boolean)
      .sort(),
    [metadata],
  );
  const rowIds = useMemo(() => {
    const dateValue = (row: VisualizationRow, field: string) => String(row[field] ?? "");
    const compareDates = (left: string, right: string, descending: boolean) => {
      if (!left && !right) return 0;
      if (!left) return 1;
      if (!right) return -1;
      return descending ? right.localeCompare(left) : left.localeCompare(right);
    };
    const values = [...metadata.entries()]
      .filter(([, row]) => {
        const label = String(row[rowField] ?? "");
        const completeness = Number(row.completeness_percent ?? 0);
        const related = Array.isArray(row.related_references)
          ? row.related_references.map(String)
          : [];
        const firstSeen = dateValue(row, "first_seen").slice(0, 10);
        const lastSeen = dateValue(row, "last_seen").slice(0, 10);
        return (
          (!query || label.toLocaleLowerCase().includes(query.toLocaleLowerCase()))
          && (typeFilter === "all" || String(row.indicator_type) === typeFilter)
          && (
            completenessFilter === "all"
            || (completenessFilter === "mapped" && completeness > 0)
            || (completenessFilter === "complete" && completeness >= 100)
            || (completenessFilter === "gaps" && completeness < 100)
            || (completenessFilter === "unmapped" && completeness === 0)
          )
          && (!relatedReference || related.includes(relatedReference))
          && (!firstSeenAfter || Boolean(firstSeen) && firstSeen >= firstSeenAfter)
          && (!lastSeenBefore || Boolean(lastSeen) && lastSeen <= lastSeenBefore)
        );
      });
    values.sort(([leftId, left], [rightId, right]) => {
      if (sortOrder === "last_desc" || sortOrder === "last_asc") {
        return compareDates(
          dateValue(left, "last_seen"),
          dateValue(right, "last_seen"),
          sortOrder === "last_desc",
        ) || leftId.localeCompare(rightId);
      }
      if (sortOrder === "first_desc" || sortOrder === "first_asc") {
        return compareDates(
          dateValue(left, "first_seen"),
          dateValue(right, "first_seen"),
          sortOrder === "first_desc",
        ) || leftId.localeCompare(rightId);
      }
      if (sortOrder === "complete_desc" || sortOrder === "complete_asc") {
        const direction = sortOrder === "complete_desc" ? -1 : 1;
        return (
          (Number(left.completeness_percent ?? 0) - Number(right.completeness_percent ?? 0))
          * direction
        ) || leftId.localeCompare(rightId);
      }
      if (sortOrder === "type") {
        return String(left.indicator_type).localeCompare(String(right.indicator_type))
          || String(left[rowField]).localeCompare(String(right[rowField]));
      }
      return String(left[rowField]).localeCompare(String(right[rowField]));
    });
    return values.map(([rowId]) => rowId);
  }, [
    completenessFilter,
    firstSeenAfter,
    lastSeenBefore,
    metadata,
    query,
    relatedReference,
    rowField,
    sortOrder,
    typeFilter,
  ]);
  const cells = useMemo(
    () => new Map(
      intent.data.rows.map((row) => [
        `${String(row[rowIdField])}\u0000${String(row[columnField])}`,
        row,
      ]),
    ),
    [columnField, intent.data.rows, rowIdField],
  );

  if (intent.data.rows.length === 0) return <VisualizationEmpty intent={intent} />;
  return (
    <>
      {isConstellation && (
        <div className="constellation-controls" aria-label="Constellation sort and filters">
          <label>
            <span>Find indicator</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="value contains…"
            />
          </label>
          <label>
            <span>IoC type</span>
            <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
              <option value="all">All types</option>
              {types.map((type) => <option value={type} key={type}>{type}</option>)}
            </select>
          </label>
          <label>
            <span>Completeness</span>
            <select
              value={completenessFilter}
              onChange={(event) => setCompletenessFilter(event.target.value)}
            >
              <option value="all">Any completeness</option>
              <option value="mapped">Some mapping</option>
              <option value="complete">100% mapped</option>
              <option value="gaps">Has gaps</option>
              <option value="unmapped">No mapping</option>
            </select>
          </label>
          <label>
            <span>Directly related to</span>
            <select
              value={relatedReference}
              onChange={(event) => setRelatedReference(event.target.value)}
            >
              <option value="">Any indicator</option>
              {[...metadata.entries()].map(([reference, row]) => (
                <option value={reference} key={reference}>
                  {String(row[rowField])} · {String(row.indicator_type)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>First seen on/after</span>
            <input
              type="date"
              value={firstSeenAfter}
              onChange={(event) => setFirstSeenAfter(event.target.value)}
            />
          </label>
          <label>
            <span>Last seen on/before</span>
            <input
              type="date"
              value={lastSeenBefore}
              onChange={(event) => setLastSeenBefore(event.target.value)}
            />
          </label>
          <label>
            <span>Sort</span>
            <select value={sortOrder} onChange={(event) => setSortOrder(event.target.value)}>
              <option value="last_desc">Last seen · newest</option>
              <option value="last_asc">Last seen · oldest</option>
              <option value="first_desc">First seen · newest</option>
              <option value="first_asc">First seen · oldest</option>
              <option value="complete_desc">Completeness · high</option>
              <option value="complete_asc">Completeness · low</option>
              <option value="type">IoC type</option>
              <option value="indicator">Indicator value</option>
            </select>
          </label>
          <button
            type="button"
            onClick={() => {
              setQuery("");
              setTypeFilter("all");
              setCompletenessFilter("all");
              setRelatedReference("");
              setFirstSeenAfter("");
              setLastSeenBefore("");
              setSortOrder("last_desc");
            }}
          >
            RESET
          </button>
          <output>{rowIds.length} of {metadata.size} indicators</output>
        </div>
      )}
      <div className="task-matrix-wrap">
        <table className="task-matrix">
          <caption className="sr-only">{intent.question_text}</caption>
          <thead>
            <tr>
              <th scope="col">Indicator</th>
              {columns.map((column) => (
                <th scope="col" key={column}>{column.replaceAll("_", " ")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rowIds.map((rowId) => {
              const row = metadata.get(rowId);
              if (!row) return null;
              const label = String(row[rowField]);
              return (
                <tr key={rowId}>
                  <th scope="row" title={label}>
                    {onOpenEvidence && row.reference
                      ? (
                        <button onClick={(event) => onOpenEvidence(String(row.reference), event.currentTarget)}>
                          <b>{shortLabel(label, 42)}</b>
                          {isConstellation && (
                            <small>
                              {displayValue(row.indicator_type)} · {displayValue(row.completeness_percent)}%
                            </small>
                          )}
                        </button>
                      )
                      : shortLabel(label, 42)}
                  </th>
                  {columns.map((column) => {
                    const cell = cells.get(`${rowId}\u0000${column}`);
                    if (!cell) return <td className="matrix-empty" key={column}>—</td>;
                    const status = String(cell[statusField]);
                    return (
                      <td key={column}>
                        <button
                          className={`matrix-cell state-${status}`}
                          onClick={() => setSelected(cell)}
                          aria-label={`${label}, ${column}, ${status}`}
                        >
                          <span className="matrix-led" aria-hidden="true">
                            {Array.from({ length: 9 }, (_, index) => <i key={index} />)}
                          </span>
                          <b>{TERMINAL_GLYPH[status] ?? "·"}</b>
                          <span>{status}</span>
                        </button>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {rowIds.length === 0 && (
        <div className="visualization-empty">
          <b>NO INDICATORS MATCH</b>
          <span>Adjust or reset the Constellation filters.</span>
        </div>
      )}
      {selected && (
        <div className="visualization-selection" aria-live="polite">
          <b>{displayValue(selected[rowField])}</b>
          <span>
            {displayValue(selected[columnField])} · {displayValue(selected[statusField])}
          </span>
          <small>
            {isConstellation
              ? (
                `${displayValue(selected.indicator_type)} · ${displayValue(selected.evidence_count)} `
                + `evidence records · first ${displayValue(selected.first_seen)} · `
                + `last ${displayValue(selected.last_seen)}`
              )
              : (
                `Event ${displayValue(selected.event_sequence)} · `
                + displayValue(selected.updated_at)
              )}
          </small>
        </div>
      )}
    </>
  );
}

type GraphPoint = { x: number; y: number };
type GraphViewport = { x: number; y: number; scale: number };
type GraphDrag =
  | {
      kind: "canvas";
      pointerId: number;
      startX: number;
      startY: number;
      originX: number;
      originY: number;
    }
  | {
      kind: "node";
      pointerId: number;
      reference: string;
      startX: number;
      startY: number;
      originX: number;
      originY: number;
    };

function stableHash(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function forceLayout(
  nodes: VisualizationIntent["data"]["nodes"],
  edges: VisualizationIntent["data"]["edges"],
  width: number,
  height: number,
): Record<string, GraphPoint> {
  const positions = new Map<string, GraphPoint>();
  const velocity = new Map<string, GraphPoint>();
  const radius = Math.min(width, height) * 0.32;
  nodes.forEach((node, index) => {
    const hash = stableHash(node.reference);
    const angle = (Math.PI * 2 * index) / Math.max(1, nodes.length) + (hash % 97) / 311;
    const jitter = ((hash >>> 8) % 61) - 30;
    positions.set(node.reference, {
      x: width / 2 + Math.cos(angle) * (radius + jitter),
      y: height / 2 + Math.sin(angle) * (radius + jitter),
    });
    velocity.set(node.reference, { x: 0, y: 0 });
  });

  const ideal = Math.max(76, Math.min(150, 560 / Math.sqrt(Math.max(nodes.length, 1))));
  for (let iteration = 0; iteration < 180; iteration += 1) {
    const cooling = 1 - iteration / 205;
    for (let leftIndex = 0; leftIndex < nodes.length; leftIndex += 1) {
      const left = positions.get(nodes[leftIndex].reference)!;
      const leftVelocity = velocity.get(nodes[leftIndex].reference)!;
      for (let rightIndex = leftIndex + 1; rightIndex < nodes.length; rightIndex += 1) {
        const right = positions.get(nodes[rightIndex].reference)!;
        const rightVelocity = velocity.get(nodes[rightIndex].reference)!;
        const dx = left.x - right.x || 0.1;
        const dy = left.y - right.y || 0.1;
        const distanceSquared = Math.max(dx * dx + dy * dy, 100);
        const distance = Math.sqrt(distanceSquared);
        const repulsion = Math.min(3.2, (ideal * ideal) / distanceSquared) * cooling;
        const pushX = (dx / distance) * repulsion;
        const pushY = (dy / distance) * repulsion;
        leftVelocity.x += pushX;
        leftVelocity.y += pushY;
        rightVelocity.x -= pushX;
        rightVelocity.y -= pushY;
      }
    }
    for (const edge of edges) {
      const source = positions.get(edge.source);
      const target = positions.get(edge.target);
      if (!source || !target) continue;
      const sourceVelocity = velocity.get(edge.source)!;
      const targetVelocity = velocity.get(edge.target)!;
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const distance = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
      const pull = ((distance - ideal) / ideal) * 0.075 * cooling;
      const pullX = (dx / distance) * pull;
      const pullY = (dy / distance) * pull;
      sourceVelocity.x += pullX;
      sourceVelocity.y += pullY;
      targetVelocity.x -= pullX;
      targetVelocity.y -= pullY;
    }
    for (const node of nodes) {
      const position = positions.get(node.reference)!;
      const speed = velocity.get(node.reference)!;
      speed.x += (width / 2 - position.x) * 0.0009;
      speed.y += (height / 2 - position.y) * 0.0009;
      speed.x *= 0.82;
      speed.y *= 0.82;
      position.x = Math.max(48, Math.min(width - 48, position.x + speed.x * 6));
      position.y = Math.max(38, Math.min(height - 38, position.y + speed.y * 6));
    }
  }
  return Object.fromEntries(positions);
}

function RelationshipGraph({
  intent,
  onOpenEvidence,
}: {
  intent: VisualizationIntent;
  onOpenEvidence?: (reference: string, origin: HTMLElement) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [viewport, setViewport] = useState<GraphViewport>({ x: 0, y: 0, scale: 1 });
  const [drag, setDrag] = useState<GraphDrag | null>(null);
  const [positions, setPositions] = useState<Record<string, GraphPoint>>({});
  const svgRef = useRef<SVGSVGElement>(null);
  const width = 760;
  const height = 430;
  const degree = new Map(intent.data.nodes.map((node) => [node.reference, 0]));
  const neighbors = new Map(intent.data.nodes.map((node) => [node.reference, new Set<string>()]));
  for (const edge of intent.data.edges) {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
    neighbors.get(edge.source)?.add(edge.target);
    neighbors.get(edge.target)?.add(edge.source);
  }
  const normalizedQuery = query.trim().toLowerCase();
  const ranked = [...intent.data.nodes].sort((left, right) => {
    const degreeDifference = (degree.get(right.reference) ?? 0) - (degree.get(left.reference) ?? 0);
    return degreeDifference || left.label.localeCompare(right.label);
  });
  const candidates = normalizedQuery
    ? ranked.filter((node) =>
        node.label.toLowerCase().includes(normalizedQuery)
        || node.entity_type.toLowerCase().includes(normalizedQuery))
    : ranked;
  const visibleNodes = candidates.slice(0, 48);
  const visibleIds = new Set(visibleNodes.map((node) => node.reference));
  const visibleEdges = intent.data.edges.filter(
    (edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target),
  );
  const graphKey = [
    ...visibleNodes.map((node) => node.reference),
    ...visibleEdges.map((edge) => `${edge.source}>${edge.target}:${edge.relationship}`),
  ].join("\u0000");
  const initialPositions = useMemo(
    () => forceLayout(visibleNodes, visibleEdges, width, height),
    // graphKey is a compact deterministic identity for the current presentation subset.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [graphKey],
  );
  useEffect(() => {
    setPositions(initialPositions);
    setViewport({ x: 0, y: 0, scale: 1 });
  }, [initialPositions]);
  const selectedNode = intent.data.nodes.find((node) => node.reference === selected);
  const markerId = `${intent.intent_id}-relationship-arrow`;

  const updateZoom = (factor: number) => {
    setViewport((current) => {
      const nextScale = Math.max(0.45, Math.min(3, current.scale * factor));
      const actualFactor = nextScale / current.scale;
      return {
        x: width / 2 - (width / 2 - current.x) * actualFactor,
        y: height / 2 - (height / 2 - current.y) * actualFactor,
        scale: nextScale,
      };
    });
  };

  const handlePointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (drag.kind === "canvas") {
      setViewport((current) => ({
        ...current,
        x: drag.originX + event.clientX - drag.startX,
        y: drag.originY + event.clientY - drag.startY,
      }));
      return;
    }
    setPositions((current) => ({
      ...current,
      [drag.reference]: {
        x: drag.originX + (event.clientX - drag.startX) / viewport.scale,
        y: drag.originY + (event.clientY - drag.startY) / viewport.scale,
      },
    }));
  };

  if (intent.data.nodes.length === 0) return <VisualizationEmpty intent={intent} />;
  return (
    <div className="relationship-visualization">
      <div className="relationship-controls">
        <label>
          <span>Filter indicators or types</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="domain, IP, file…" />
        </label>
        <span>
          Showing {visibleNodes.length} of {intent.data.nodes.length} nodes · {visibleEdges.length} visible edges
        </span>
        {intent.data.edges.length > 0 && (
          <span className="graph-zoom-controls" aria-label="Graph zoom controls">
            <button onClick={() => updateZoom(1.2)} aria-label="Zoom relationship graph in">＋</button>
            <button onClick={() => updateZoom(1 / 1.2)} aria-label="Zoom relationship graph out">－</button>
            <button onClick={() => setViewport({ x: 0, y: 0, scale: 1 })}>CENTER</button>
          </span>
        )}
        {(query || selected) && <button onClick={() => { setQuery(""); setSelected(null); }}>RESET VIEW</button>}
      </div>
      {intent.data.edges.length === 0 ? (
        <section className="unconnected-graph" aria-label="Unconnected stored indicators">
          <b>NO RELATIONSHIP EDGES IN SCOPE</b>
          <span>
            {intent.data.nodes.length} indicators remain visible as unconnected evidence.
            No relationship is inferred from proximity.
          </span>
          <div>
            {visibleNodes.map((node) => (
              <button
                key={node.reference}
                className={selected === node.reference ? "selected" : ""}
                title={node.label}
                onClick={() => setSelected(node.reference)}
                onDoubleClick={(event) => {
                  if (onOpenEvidence) onOpenEvidence(node.reference, event.currentTarget);
                }}
              >
                <b>{shortLabel(node.label, 30)}</b>
                <span>{node.entity_type}</span>
              </button>
            ))}
          </div>
        </section>
      ) : (
        <svg
          ref={svgRef}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-labelledby={`${intent.intent_id}-graph-title`}
          tabIndex={0}
          onPointerDown={(event) => {
            if (event.target !== event.currentTarget) return;
            event.currentTarget.setPointerCapture(event.pointerId);
            setDrag({
              kind: "canvas",
              pointerId: event.pointerId,
              startX: event.clientX,
              startY: event.clientY,
              originX: viewport.x,
              originY: viewport.y,
            });
          }}
          onPointerMove={handlePointerMove}
          onPointerUp={(event) => {
            if (drag?.pointerId === event.pointerId) setDrag(null);
          }}
          onPointerCancel={() => setDrag(null)}
          onWheel={(event) => {
            event.preventDefault();
            const rect = event.currentTarget.getBoundingClientRect();
            const cursorX = ((event.clientX - rect.left) / rect.width) * width;
            const cursorY = ((event.clientY - rect.top) / rect.height) * height;
            const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
            setViewport((current) => {
              const nextScale = Math.max(0.45, Math.min(3, current.scale * factor));
              const actualFactor = nextScale / current.scale;
              return {
                x: cursorX - (cursorX - current.x) * actualFactor,
                y: cursorY - (cursorY - current.y) * actualFactor,
                scale: nextScale,
              };
            });
          }}
        >
        <title id={`${intent.intent_id}-graph-title`}>
          {intent.question_text} Drag nodes or the background; use the wheel or controls to zoom.
        </title>
        <defs>
          <marker id={markerId} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" />
          </marker>
        </defs>
        <g transform={`translate(${viewport.x} ${viewport.y}) scale(${viewport.scale})`}>
          <g className="relationship-edges">
            {visibleEdges.map((edge, index) => {
              const source = positions[edge.source];
              const target = positions[edge.target];
              if (!source || !target) return null;
              return (
                <g key={`${edge.source}-${edge.target}-${index}`}>
                  <line
                    x1={source.x}
                    y1={source.y}
                    x2={target.x}
                    y2={target.y}
                    className={`basis-${edge.basis}`}
                    markerEnd={`url(#${markerId})`}
                  >
                    <title>{edge.relationship} · {edge.provenance}</title>
                  </line>
                  {visibleEdges.length <= 24 && (
                    <text x={(source.x + target.x) / 2} y={(source.y + target.y) / 2 - 4}>
                      {shortLabel(edge.relationship, 22)}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
          <g className="relationship-nodes">
            {visibleNodes.map((node) => {
              const position = positions[node.reference];
              if (!position) return null;
              return (
                <g
                  key={node.reference}
                  transform={`translate(${position.x} ${position.y})`}
                  className={[
                    selected === node.reference ? "selected" : "",
                    selected && neighbors.get(selected)?.has(node.reference) ? "neighbor" : "",
                    `type-${node.entity_type.replaceAll(/[^a-z0-9-]/gi, "-")}`,
                  ].join(" ")}
                  role="button"
                  tabIndex={0}
                  aria-label={`${node.label}, ${node.entity_type}, ${degree.get(node.reference) ?? 0} relationships`}
                  onClick={() => setSelected(node.reference)}
                  onDoubleClick={(event) => {
                    const origin = event.currentTarget.closest(".relationship-visualization");
                    if (onOpenEvidence && origin instanceof HTMLElement) {
                      onOpenEvidence(node.reference, origin);
                    }
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelected(node.reference);
                    }
                  }}
                  onPointerDown={(event) => {
                    event.stopPropagation();
                    event.currentTarget.setPointerCapture(event.pointerId);
                    setSelected(node.reference);
                    setDrag({
                      kind: "node",
                      pointerId: event.pointerId,
                      reference: node.reference,
                      startX: event.clientX,
                      startY: event.clientY,
                      originX: position.x,
                      originY: position.y,
                    });
                  }}
                >
                  <circle r={degree.get(node.reference) ? 26 : 21}>
                    <title>{node.label}</title>
                  </circle>
                  <text className="node-label" textAnchor="middle" y="-2">{shortLabel(node.label, 21)}</text>
                  <text className="node-type" textAnchor="middle" y="11">{node.entity_type}</text>
                </g>
              );
            })}
          </g>
        </g>
        </svg>
      )}
      <div className="graph-legend">
        <span><i className="explicit" /> Stored relationship</span>
        <span><i className="property" /> Property pivot</span>
        <span>Force layout is limited to 48 nodes; drag, pan, zoom, filtering, and selection change presentation only.</span>
      </div>
      {selectedNode && (
        <div className="visualization-selection" aria-live="polite">
          <b>{selectedNode.label}</b>
          <span>{selectedNode.entity_type} · {degree.get(selectedNode.reference) ?? 0} relationships</span>
          <small>Selection highlights the node and its visible neighbors without changing the graph layout.</small>
          {onOpenEvidence && (
            <button onClick={(event) => onOpenEvidence(selectedNode.reference, event.currentTarget)}>
              OPEN EVIDENCE
            </button>
          )}
        </div>
      )}
      <details className="relationship-node-inventory">
        <summary>View accessible node inventory</summary>
        <div className="visualization-table-wrap">
          <table className="visualization-table">
            <caption>Exact graph nodes · {intent.source_scope.workspace}</caption>
            <thead><tr><th scope="col">Indicator</th><th scope="col">Type</th><th scope="col">Relations</th></tr></thead>
            <tbody>
              {intent.data.nodes.map((node) => (
                <tr key={node.reference}>
                  <td>{node.label}</td>
                  <td>{node.entity_type}</td>
                  <td>{degree.get(node.reference) ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

function downloadIntent(intent: VisualizationIntent) {
  const exported = exactDataExport(intent);
  const url = URL.createObjectURL(new Blob([exported.content], { type: exported.mime }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = exported.filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function VisualizationWorkspace({
  intents,
  theme,
  onOpenEvidence,
}: {
  intents: VisualizationIntent[];
  theme: VisualizationTheme;
  onOpenEvidence?: (reference: string, origin: HTMLElement) => void;
}) {
  const preferred = intents.find((intent) => intent.intent_id === "indicator-constellation");
  const [selectedId, setSelectedId] = useState(preferred?.intent_id ?? intents[0]?.intent_id ?? "");
  const selected = intents.find((intent) => intent.intent_id === selectedId) ?? preferred ?? intents[0];

  useEffect(() => {
    if (intents.length && !intents.some((intent) => intent.intent_id === selectedId)) {
      setSelectedId(
        intents.find((intent) => intent.intent_id === "indicator-constellation")?.intent_id
        ?? intents[0].intent_id,
      );
    }
  }, [intents, selectedId]);

  if (!selected) return <div className="visualization-empty">Visualization intents unavailable.</div>;
  let validationError = "";
  try {
    validateVisualizationIntent(selected);
  } catch (reason) {
    validationError = reason instanceof Error ? reason.message : String(reason);
  }

  return (
    <section className="visualization-workspace" aria-label="Visual analysis">
      <nav className="visualization-tabs" aria-label="Analyst questions">
        {intents.map((intent) => (
          <button
            key={intent.intent_id}
            aria-pressed={intent.intent_id === selected.intent_id}
            onClick={() => setSelectedId(intent.intent_id)}
          >
            {intent.title}
          </button>
        ))}
      </nav>
      <header className="visualization-header">
        <div>
          <span>ANALYST QUESTION</span>
          <h3>{selected.question_text}</h3>
          <small>
            {selected.source_scope.description} · {selected.source_scope.record_count} records
            {selected.source_scope.timezone ? ` · ${selected.source_scope.timezone}` : ""}
          </small>
        </div>
        <button onClick={() => downloadIntent(selected)}>EXPORT EXACT DATA</button>
      </header>
      {validationError
        ? <div className="visualization-error">Rejected intent: {validationError}</div>
        : selected.renderer === "flint_chartjs"
          ? <FlintCanvas intent={selected} theme={theme} />
          : selected.view === "calendar_heatmap"
            ? <CalendarHeatmap intent={selected} />
            : selected.view === "task_matrix"
              ? <TaskMatrix intent={selected} onOpenEvidence={onOpenEvidence} />
              : selected.view === "relationship_graph"
                ? <RelationshipGraph intent={selected} onOpenEvidence={onOpenEvidence} />
                : <VisualizationEmpty intent={selected} />}
      <details className="visualization-data">
        <summary>View exact data and caveats</summary>
        <p>{selected.missing_data.explanation}</p>
        {selected.caveats.map((caveat) => <p key={caveat}>{caveat}</p>)}
        <AccessibleDataTable intent={selected} />
      </details>
    </section>
  );
}
