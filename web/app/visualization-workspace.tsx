"use client";

import { CSSProperties, useEffect, useMemo, useRef, useState } from "react";
import { Chart, registerables } from "chart.js";

import {
  appendGraphPresentationHistory,
  compileFlintChartjs,
  exactDataExport,
  graphPresentationSnapshotsEqual,
  hiddenGraphReferences,
  updateGraphSelection,
  plottedRows,
  validateVisualizationIntent,
  type GraphPresentationSnapshot,
  type VisualizationEdge,
  type VisualizationIntent,
  type VisualizationRow,
  type VisualizationTheme,
} from "./visualization-intent";
import { RGBLed, rgbLabelForStatus } from "./rgb-led";
import { LiteBritePeg } from "./lite-brite-peg";

Chart.register(...registerables);

const CONSTELLATION_COLUMN_LABELS: Readonly<Record<string, string>> = {
  identity: "ID",
  ttps: "TTP",
  infrastructure: "INF",
  timing: "TIM",
  targeting: "TAR",
  capability: "CAP",
  motivation: "MOT",
  predictions: "PRE",
  denial: "DEN",
};

const CONSTELLATION_DIMENSION_HELP: Readonly<Record<string, string>> = {
  identity: "Who or what is associated with this activity?",
  ttps: "Which observed behaviors and techniques are supported?",
  infrastructure: "Which systems, services, and hosting relationships are supported?",
  timing: "When was the activity observed, and what timing pattern is supported?",
  targeting: "Which victims, sectors, regions, or technologies are supported?",
  capability: "What can the observed tooling or infrastructure demonstrably do?",
  motivation: "What source-backed intent or objective is recorded?",
  predictions: "Which testable expectations are recorded for future observation?",
  denial: "Which evidence could contradict or falsify the current assessment?",
};

const VISUALIZATION_VIEW_LABELS: Readonly<Record<VisualizationIntent["view"], string>> = {
  calendar_heatmap: "Calendar heatmap",
  radar: "Radar chart",
  histogram: "Histogram",
  relationship_graph: "Force-directed graph",
  dendrogram: "Dendrogram",
  scatter: "Scatter plot",
  task_matrix: "Matrix",
  line: "Line chart",
  bar: "Bar chart",
  uncertainty_intervals: "Interval plot",
};

function constellationStatusHelp(status: string): string {
  if (status === "filled") {
    return "Filled: source-backed evidence meets the configured coverage threshold; coverage is not confidence or truth.";
  }
  if (status === "partial") return "Partial: some source-backed evidence exists, but material gaps remain.";
  if (status === "deferred") {
    return "Deferred: no applicable automated inference path exists; this is not an observed evidence gap.";
  }
  if (status === "empty") return "Empty: no supporting evidence is present in the admitted neighborhood.";
  return `${status.replaceAll("_", " ")}: inspect the authoritative record for details.`;
}

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
  const [binCount, setBinCount] = useState(
    Number(intent.chart_properties.binCount ?? 10),
  );
  const rows = plottedRows(intent);

  useEffect(() => {
    setBinCount(Number(intent.chart_properties.binCount ?? 10));
  }, [intent.chart_properties.binCount, intent.intent_id]);

  useEffect(() => {
    if (!canvas.current || rows.length === 0) return;
    let chart: Chart | undefined;
    try {
      setError("");
      const width = canvas.current.parentElement?.clientWidth ?? 620;
      const config = compileFlintChartjs(
        intent,
        { width, height: 320 },
        intent.view === "histogram" ? { binCount } : intent.chart_properties,
      );
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
    binCount,
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
      {intent.view === "histogram" && (
        <label className="histogram-bins">
          <span>BINS</span>
          <input
            aria-label="Histogram bin count"
            type="range"
            min="5"
            max="50"
            step="1"
            value={binCount}
            onInput={(event) => setBinCount(Number(event.currentTarget.value))}
          />
          <output>{binCount}</output>
        </label>
      )}
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

function UncertaintyIntervals({ intent }: { intent: VisualizationIntent }) {
  if (!intent.data.rows.length) return <VisualizationEmpty intent={intent} />;
  return (
    <div className="uncertainty-intervals">
      <div className="uncertainty-axis" aria-hidden="true">
        {[0, 25, 50, 75, 100].map((value) => <span key={value}>{value}%</span>)}
      </div>
      {intent.data.rows.map((row, index) => {
        const minimum = Math.max(0, Math.min(100, Number(row.probability_min_percent) || 0));
        const maximum = Math.max(minimum, Math.min(100, Number(row.probability_max_percent) || 0));
        const label = displayValue(row.target);
        return (
          <article key={`${displayValue(row.target_id)}-${index}`}>
            <header>
              <b>{label}</b>
              <span>{displayValue(row.target_kind)} · {displayValue(row.likelihood_term)}</span>
            </header>
            <div
              className="uncertainty-track"
              role="img"
              aria-label={`${label}: ${minimum}% to ${maximum}% likelihood; analytic confidence ${displayValue(row.confidence_level)}`}
            >
              <i style={{ left: `${minimum}%`, width: `${Math.max(1, maximum - minimum)}%` }} />
              <span style={{ left: `${minimum}%` }}>{minimum}%</span>
              <span style={{ left: `${maximum}%` }}>{maximum}%</span>
            </div>
            <footer>
              <span>LIKELIHOOD · {displayValue(row.likelihood_assessor)}</span>
              <p>{displayValue(row.likelihood_rationale)}</p>
              <span>CONFIDENCE · {displayValue(row.confidence_level)} · {displayValue(row.confidence_assessor)}</span>
              <p>{displayValue(row.confidence_rationale)}</p>
            </footer>
          </article>
        );
      })}
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

type HierarchyNode = {
  id: string;
  label: string;
  kind: string;
  status: string;
};

function HierarchyBranch({
  nodeId,
  nodes,
  children,
  depth,
  ancestors,
}: {
  nodeId: string;
  nodes: Map<string, HierarchyNode>;
  children: Map<string, string[]>;
  depth: number;
  ancestors: ReadonlySet<string>;
}) {
  const node = nodes.get(nodeId);
  if (!node) return null;
  if (ancestors.has(nodeId)) {
    return <li role="treeitem"><span>CYCLE REJECTED · {node.label}</span></li>;
  }
  const childIds = children.get(nodeId) ?? [];
  const nextAncestors = new Set(ancestors).add(nodeId);
  return (
    <li role="treeitem" aria-level={depth + 1}>
      {childIds.length
        ? (
          <details open={depth < 2}>
            <summary>
              <b>{node.label}</b>
              <span>{node.kind.replaceAll("_", " ")} · {node.status.replaceAll("_", " ")}</span>
            </summary>
            <ul role="group">
              {childIds.map((childId) => (
                <HierarchyBranch
                  key={childId}
                  nodeId={childId}
                  nodes={nodes}
                  children={children}
                  depth={depth + 1}
                  ancestors={nextAncestors}
                />
              ))}
            </ul>
          </details>
        )
        : (
          <div className="hierarchy-leaf">
            <b>{node.label}</b>
            <span>{node.kind.replaceAll("_", " ")} · {node.status.replaceAll("_", " ")}</span>
          </div>
        )}
    </li>
  );
}

function HierarchyTree({ intent }: { intent: VisualizationIntent }) {
  const hierarchy = useMemo(() => {
    const nodes = new Map<string, HierarchyNode>();
    const children = new Map<string, string[]>();
    const childIds = new Set<string>();
    for (const row of intent.data.rows) {
      const parentId = String(row.parent_id ?? "");
      const childId = String(row.child_id ?? "");
      if (!parentId || !childId) continue;
      if (!nodes.has(parentId)) {
        nodes.set(parentId, {
          id: parentId,
          label: String(row.parent_label ?? parentId),
          kind: parentId.startsWith("workspace:") ? "workspace" : "parent",
          status: "persisted",
        });
      }
      nodes.set(childId, {
        id: childId,
        label: String(row.child_label ?? childId),
        kind: String(row.child_kind ?? "record"),
        status: String(row.status ?? "unknown"),
      });
      const entries = children.get(parentId) ?? [];
      if (!entries.includes(childId)) entries.push(childId);
      children.set(parentId, entries);
      childIds.add(childId);
    }
    for (const entries of children.values()) {
      entries.sort((left, right) => (
        (nodes.get(left)?.label ?? left).localeCompare(nodes.get(right)?.label ?? right)
      ));
    }
    const roots = [...nodes.keys()]
      .filter((nodeId) => !childIds.has(nodeId))
      .sort((left, right) => left.localeCompare(right));
    return { nodes, children, roots };
  }, [intent.data.rows]);

  if (!hierarchy.roots.length) return <VisualizationEmpty intent={intent} />;
  return (
    <div className="hierarchy-visualization">
      <ul role="tree" aria-label={intent.question_text}>
        {hierarchy.roots.map((rootId) => (
          <HierarchyBranch
            key={rootId}
            nodeId={rootId}
            nodes={hierarchy.nodes}
            children={hierarchy.children}
            depth={0}
            ancestors={new Set()}
          />
        ))}
      </ul>
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
  supports: "+",
  contradicts: "−",
  mixed: "±",
  not_assessed: "?",
};

export function TaskMatrix({
  intent,
  onOpenEvidence,
  onSelectCell,
  liveRows = [],
}: {
  intent: VisualizationIntent;
  onOpenEvidence?: (reference: string, origin: HTMLElement) => void;
  onSelectCell?: (row: VisualizationRow) => void;
  liveRows?: VisualizationRow[];
}) {
  const [selected, setSelected] = useState<VisualizationRow | null>(null);
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [completenessFilter, setCompletenessFilter] = useState("all");
  const [relatedReference, setRelatedReference] = useState("");
  const [firstSeenAfter, setFirstSeenAfter] = useState("");
  const [lastSeenBefore, setLastSeenBefore] = useState("");
  const [sortOrder, setSortOrder] = useState("last_desc");
  const [gridFocus, setGridFocus] = useState({ row: 0, column: 0 });
  const matrixWrap = useRef<HTMLDivElement>(null);
  const rowField = intent.fields.row;
  const rowIdField = intent.fields.row_id ?? rowField;
  const columnField = intent.fields.column;
  const statusField = intent.fields.status;
  const isConstellation = intent.intent_id === "indicator-constellation";
  const isAch = intent.intent_id === "competing-hypotheses-matrix";
  const rowHeading = intent.table_columns.find((column) => column.key === rowField)?.label
    ?? "Indicator";
  const mergedRows = useMemo(() => {
    const rows = new Map<string, VisualizationRow>();
    for (const row of [...intent.data.rows, ...liveRows]) {
      rows.set(`${String(row[rowIdField])}\u0000${String(row[columnField])}`, row);
    }
    return [...rows.values()];
  }, [columnField, intent.data.rows, liveRows, rowIdField]);
  const metadata = useMemo(() => {
    const values = new Map<string, VisualizationRow>();
    for (const row of mergedRows) {
      const rowId = String(row[rowIdField]);
      if (!values.has(rowId)) values.set(rowId, row);
    }
    return values;
  }, [mergedRows, rowIdField]);
  const latestUpdate = useMemo(() => {
    const values = new Map<string, string>();
    for (const row of mergedRows) {
      const rowId = String(row[rowIdField]);
      const updated = String(row.updated_at ?? "");
      if (updated > (values.get(rowId) ?? "")) values.set(rowId, updated);
    }
    return values;
  }, [mergedRows, rowIdField]);
  const columns = useMemo(
    () => [...new Set(mergedRows.map((row) => String(row[columnField])))],
    [columnField, mergedRows],
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
      if (!isConstellation) {
        return (latestUpdate.get(rightId) ?? "").localeCompare(latestUpdate.get(leftId) ?? "")
          || leftId.localeCompare(rightId);
      }
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
    isConstellation,
    latestUpdate,
    query,
    relatedReference,
    rowField,
    sortOrder,
    typeFilter,
  ]);
  const cells = useMemo(
    () => new Map(
      mergedRows.map((row) => [
        `${String(row[rowIdField])}\u0000${String(row[columnField])}`,
        row,
      ]),
    ),
    [columnField, mergedRows, rowIdField],
  );
  const activeCell = selected;

  useEffect(() => {
    setGridFocus((current) => ({
      row: Math.min(current.row, Math.max(rowIds.length - 1, 0)),
      column: Math.min(current.column, Math.max(columns.length - 1, 0)),
    }));
  }, [columns.length, rowIds.length]);

  const focusGridCell = (row: number, column: number) => {
    const next = {
      row: Math.max(0, Math.min(row, rowIds.length - 1)),
      column: Math.max(0, Math.min(column, columns.length - 1)),
    };
    setGridFocus(next);
    requestAnimationFrame(() => {
      matrixWrap.current
        ?.querySelector<HTMLButtonElement>(
          `[data-grid-row="${next.row}"][data-grid-column="${next.column}"]`,
        )
        ?.focus();
    });
  };

  if (mergedRows.length === 0) return <VisualizationEmpty intent={intent} />;
  return (
    <>
      {isConstellation && (
        <section className="constellation-tools" aria-label="Constellation sort and filters">
          <div className="constellation-toolbar">
            <label className="constellation-search">
              <span>Find indicator</span>
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Indicator value…"
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
            <output>{rowIds.length} / {metadata.size} indicators</output>
          </div>
          <details className="constellation-more">
            <summary>FILTERS</summary>
            <div className="constellation-controls">
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
                RESET FILTERS
              </button>
            </div>
          </details>
        </section>
      )}
      {isConstellation && (
        <div className="lite-brite-legend" aria-label="Lite Brite Dossier status legend">
          {(["filled", "partial", "deferred", "empty"] as const).map((status) => (
            <span key={status}>
              <LiteBritePeg compact status={status} label={`${status} Dossier status`} />
              <b>{status}</b>
            </span>
          ))}
        </div>
      )}
      {activeCell && (
        <div className="visualization-selection" aria-live={selected ? "polite" : "off"}>
          <b>{displayValue(activeCell[rowField])}</b>
          <span>
            {displayValue(activeCell[columnField])} · {displayValue(activeCell[statusField]).replaceAll("_", " ")}
          </span>
          <small>
            {isConstellation
              ? (
                `${constellationStatusHelp(displayValue(activeCell[statusField]))} `
                + `${displayValue(activeCell.evidence_count)} evidence records · `
                + `first ${displayValue(activeCell.first_seen)} · last ${displayValue(activeCell.last_seen)}`
              )
              : isAch
                ? `${displayValue(activeCell.source_kind)} · ${displayValue(activeCell.rationale)}`
                : (
                  `Event ${displayValue(activeCell.event_sequence)} · `
                  + displayValue(activeCell.updated_at)
                )}
          </small>
        </div>
      )}
      <div
        className={`task-matrix-wrap ${isConstellation ? "constellation-matrix-wrap" : ""}`}
        ref={matrixWrap}
      >
        <table className={`task-matrix ${isConstellation ? "constellation-matrix" : ""}`}>
          <caption className="sr-only">{intent.question_text}</caption>
          <thead>
            <tr>
              <th scope="col">{rowHeading}</th>
              {columns.map((column) => (
                <th
                  scope="col"
                  key={column}
                  title={column.replaceAll("_", " ")}
                >
                  {isConstellation
                    ? (
                      <button
                        type="button"
                        className="constellation-dimension-help"
                        aria-label={`${column.replaceAll("_", " ")}: ${CONSTELLATION_DIMENSION_HELP[column] ?? "Canonical Dossier dimension."}`}
                        data-tooltip={`${column.replaceAll("_", " ")}: ${CONSTELLATION_DIMENSION_HELP[column] ?? "Canonical Dossier dimension."}`}
                      >
                        {CONSTELLATION_COLUMN_LABELS[column] ?? column.slice(0, 3).toUpperCase()}
                      </button>
                    )
                    : column.replaceAll("_", " ")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rowIds.map((rowId, rowIndex) => {
              const row = metadata.get(rowId);
              if (!row) return null;
              const label = String(row[rowField]);
              return (
                <tr key={rowId}>
                  <th scope="row" title={label}>
                    {onOpenEvidence && row.reference
                      ? (
                        <button
                          data-tooltip={`${label} · ${displayValue(row.indicator_type)} · ${displayValue(row.completeness_percent)}% mapped. Open source evidence and provenance.`}
                          onClick={(event) => onOpenEvidence(String(row.reference), event.currentTarget)}
                        >
                          <b>{shortLabel(label, isConstellation ? 30 : 42)}</b>
                          {isConstellation && (
                            <small>
                              {displayValue(row.indicator_type)} · {displayValue(row.completeness_percent)}%
                            </small>
                          )}
                        </button>
                      )
                      : shortLabel(label, 42)}
                  </th>
                  {columns.map((column, columnIndex) => {
                    const cell = cells.get(`${rowId}\u0000${column}`);
                    if (!cell) return <td className="matrix-empty" key={column}>—</td>;
                    const status = String(cell[statusField]);
                    const dimension = column.replaceAll("_", " ");
                    const evidenceCount = displayValue(cell.evidence_count);
                    const cellHelp = isConstellation
                      ? `${dimension}: ${CONSTELLATION_DIMENSION_HELP[column] ?? "Canonical Dossier dimension."} ${constellationStatusHelp(status)} ${evidenceCount} source-backed evidence records contribute.`
                      : isAch
                        ? `${column} · ${status.replaceAll("_", " ")} · ${displayValue(cell.rationale)}`
                        : `${dimension} · ${status.replaceAll("_", " ")} · latest authoritative lifecycle state`;
                    const isSelected = (
                      selected?.[rowIdField] === cell[rowIdField]
                      && selected?.[columnField] === cell[columnField]
                    );
                    return (
                      <td key={column}>
                        <button
                          className={`matrix-cell ${isConstellation ? "lite-brite-cell" : ""} state-${status} ${isSelected ? "selected" : ""}`}
                          data-tooltip={cellHelp}
                          data-grid-row={rowIndex}
                          data-grid-column={columnIndex}
                          tabIndex={isConstellation
                            ? (gridFocus.row === rowIndex && gridFocus.column === columnIndex ? 0 : -1)
                            : 0}
                          aria-pressed={isConstellation ? isSelected : undefined}
                          onClick={() => {
                            setSelected(cell);
                            onSelectCell?.(cell);
                          }}
                          onFocus={() => {
                            if (isConstellation) setGridFocus({ row: rowIndex, column: columnIndex });
                          }}
                          onKeyDown={(event) => {
                            if (!isConstellation) return;
                            let nextRow = rowIndex;
                            let nextColumn = columnIndex;
                            if (event.key === "ArrowDown") nextRow += 1;
                            else if (event.key === "ArrowUp") nextRow -= 1;
                            else if (event.key === "ArrowRight") nextColumn += 1;
                            else if (event.key === "ArrowLeft") nextColumn -= 1;
                            else if (event.key === "Home") nextColumn = 0;
                            else if (event.key === "End") nextColumn = columns.length - 1;
                            else return;
                            event.preventDefault();
                            focusGridCell(nextRow, nextColumn);
                          }}
                          title={`${dimension} · ${status}`}
                          aria-label={isConstellation
                            ? `${label}. ${cellHelp}`
                            : `${label}, ${column}, ${status}. RGB status ${rgbLabelForStatus(status)}`}
                        >
                          {isConstellation
                            ? (
                              <LiteBritePeg
                                compact
                                status={status}
                                label={`${dimension}, ${status}`}
                              />
                            )
                            : (
                              <>
                                <RGBLed status={status} label={`${status} RGB status ${rgbLabelForStatus(status)}`} />
                                <b>{TERMINAL_GLYPH[status] ?? "·"}</b>
                                <span>{status.replaceAll("_", " ")}</span>
                              </>
                            )}
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
    </>
  );
}

type GraphPoint = { x: number; y: number };
type GraphViewport = { x: number; y: number; scale: number };
export type GraphLayoutSummary = {
  id: string;
  name: string;
  graph_fingerprint: string;
  updated_at: string;
};
type ResolvedGraphLayout = GraphLayoutSummary & {
  node_positions: Record<string, GraphPoint>;
  pinned_refs: string[];
  viewport: GraphViewport;
  filter_text: string;
  labels: Record<string, string>;
  topology_changed: boolean;
  missing_node_refs: string[];
  new_node_refs: string[];
};
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
  layouts,
  onLayoutsChanged,
  onDataChanged,
}: {
  intent: VisualizationIntent;
  onOpenEvidence?: (reference: string, origin: HTMLElement) => void;
  layouts: GraphLayoutSummary[];
  onLayoutsChanged?: () => Promise<void> | void;
  onDataChanged?: () => Promise<void> | void;
}) {
  const [selectedRefs, setSelectedRefs] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [viewport, setViewport] = useState<GraphViewport>({ x: 0, y: 0, scale: 1 });
  const [drag, setDrag] = useState<GraphDrag | null>(null);
  const [positions, setPositions] = useState<Record<string, GraphPoint>>({});
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [pinned, setPinned] = useState<Set<string>>(new Set());
  const [collapsedRefs, setCollapsedRefs] = useState<Set<string>>(new Set());
  const [undoStack, setUndoStack] = useState<GraphPresentationSnapshot[]>([]);
  const [redoStack, setRedoStack] = useState<GraphPresentationSnapshot[]>([]);
  const [layoutName, setLayoutName] = useState("");
  const [layoutMessage, setLayoutMessage] = useState("");
  const [layoutBusy, setLayoutBusy] = useState(false);
  const [relationPredicate, setRelationPredicate] = useState("related-to");
  const [relationAnnotation, setRelationAnnotation] = useState("");
  const [relationMessage, setRelationMessage] = useState("");
  const [relationBusy, setRelationBusy] = useState(false);
  const [nodeAnnotation, setNodeAnnotation] = useState("");
  const [nodeAnnotationMessage, setNodeAnnotationMessage] = useState("");
  const [nodeAnnotationBusy, setNodeAnnotationBusy] = useState(false);
  const [relationCorrection, setRelationCorrection] = useState<{
    mode: "revise" | "retract";
    edge: VisualizationEdge;
  } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const pendingLayoutPositions = useRef<Record<string, GraphPoint> | null>(null);
  const graphInitialized = useRef(false);
  const interactionStart = useRef<GraphPresentationSnapshot | null>(null);
  const labelEditStart = useRef<GraphPresentationSnapshot | null>(null);
  const labelEditCheckpointed = useRef(false);
  const wheelCommitTimer = useRef<number | null>(null);
  const latestPresentation = useRef<GraphPresentationSnapshot>({
    positions: {},
    viewport: { x: 0, y: 0, scale: 1 },
    labels: {},
    pinned_refs: [],
    collapsed_refs: [],
  });
  const width = 760;
  const height = 430;
  const degree = new Map(intent.data.nodes.map((node) => [node.reference, 0]));
  const graphLabels = new Map(intent.data.nodes.map((node) => [node.reference, node.label]));
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
  const filteredCandidates = normalizedQuery
    ? ranked.filter((node) =>
        node.label.toLowerCase().includes(normalizedQuery)
        || node.entity_type.toLowerCase().includes(normalizedQuery))
    : ranked;
  const protectedRefs = new Set([...selectedRefs, ...pinned]);
  const hiddenRefs = hiddenGraphReferences(intent.data.edges, collapsedRefs, protectedRefs);
  const priorityRefs = new Set([...selectedRefs, ...pinned]);
  const candidates = [
    ...ranked.filter((node) => priorityRefs.has(node.reference) && !hiddenRefs.has(node.reference)),
    ...filteredCandidates.filter(
      (node) => !priorityRefs.has(node.reference) && !hiddenRefs.has(node.reference),
    ),
  ];
  const visibleNodes = candidates.slice(0, 48);
  const visibleIds = new Set(visibleNodes.map((node) => node.reference));
  const visibleEdges = intent.data.edges.filter(
    (edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target),
  );
  const manualEdges = visibleEdges.filter(
    (edge) => edge.basis === "manual" && Boolean(edge.assertion_id),
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
    const restored = pendingLayoutPositions.current;
    pendingLayoutPositions.current = null;
    setPositions((current) => (
      restored
        ? { ...initialPositions, ...current, ...restored }
        : { ...initialPositions, ...current }
    ));
    if (!graphInitialized.current) {
      graphInitialized.current = true;
      if (!restored) setViewport({ x: 0, y: 0, scale: 1 });
    }
  }, [initialPositions]);
  const selected = selectedRefs.at(-1) ?? null;
  const selectedSet = new Set(selectedRefs);
  const selectedNode = intent.data.nodes.find((node) => node.reference === selected);
  const selectedNodes = selectedRefs
    .map((reference) => intent.data.nodes.find((node) => node.reference === reference))
    .filter((node): node is NonNullable<typeof node> => Boolean(node));
  const markerId = `${intent.intent_id}-relationship-arrow`;

  latestPresentation.current = {
    positions,
    viewport,
    labels,
    pinned_refs: [...pinned],
    collapsed_refs: [...collapsedRefs],
  };

  const pushUndo = (snapshot: GraphPresentationSnapshot) => {
    setUndoStack((current) => appendGraphPresentationHistory(current, snapshot));
    setRedoStack([]);
  };

  const checkpointPresentation = () => {
    pushUndo(latestPresentation.current);
  };

  const beginPresentationInteraction = () => {
    if (!interactionStart.current) interactionStart.current = latestPresentation.current;
  };

  const completePresentationInteraction = () => {
    const before = interactionStart.current;
    interactionStart.current = null;
    if (before && !graphPresentationSnapshotsEqual(before, latestPresentation.current)) {
      pushUndo(before);
    }
  };

  const applyPresentation = (snapshot: GraphPresentationSnapshot) => {
    setPositions(snapshot.positions);
    setViewport(snapshot.viewport);
    setLabels(snapshot.labels);
    setPinned(new Set(snapshot.pinned_refs));
    setCollapsedRefs(new Set(snapshot.collapsed_refs));
  };

  const undoPresentation = () => {
    const previous = undoStack.at(-1);
    if (!previous) return;
    const currentPresentation = latestPresentation.current;
    setUndoStack((current) => current.slice(0, -1));
    setRedoStack((current) => appendGraphPresentationHistory(current, currentPresentation));
    applyPresentation(previous);
  };

  const redoPresentation = () => {
    const next = redoStack.at(-1);
    if (!next) return;
    const currentPresentation = latestPresentation.current;
    setRedoStack((current) => current.slice(0, -1));
    setUndoStack((current) => appendGraphPresentationHistory(current, currentPresentation));
    applyPresentation(next);
  };

  const selectNode = (reference: string, additive: boolean) => {
    setSelectedRefs((current) => updateGraphSelection(current, reference, additive));
  };

  const toggleNeighborhood = (reference: string) => {
    checkpointPresentation();
    setCollapsedRefs((current) => {
      const next = new Set(current);
      if (next.has(reference)) next.delete(reference);
      else next.add(reference);
      return next;
    });
  };

  const recordManualRelation = async () => {
    if (!relationAnnotation.trim()) return;
    if (relationCorrection?.mode !== "retract" && selectedNodes.length !== 2) return;
    setRelationBusy(true);
    setRelationMessage("");
    try {
      const command = relationCorrection?.mode === "retract"
        ? [
            "analysis relation-retract",
            relationCorrection.edge.assertion_id,
            "|",
            relationAnnotation.trim(),
          ].join(" ")
        : [
            relationCorrection?.mode === "revise"
              ? `analysis relation-revise ${relationCorrection.edge.assertion_id}`
              : "analysis relation",
            selectedNodes[0].reference,
            relationPredicate.trim().toLowerCase(),
            selectedNodes[1].reference,
            "|",
            relationAnnotation.trim(),
          ].join(" ");
      const response = await fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          command,
          workspace: intent.source_scope.workspace,
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? "Unable to record analyst relation");
      const assertionId = result.data?.replacement_assertion_id
        ?? result.data?.assertion_id
        ?? "recorded assertion";
      setRelationMessage(
        relationCorrection?.mode === "retract"
          ? `Retracted ${result.data?.assertion_id ?? "analyst assertion"}; its history remains auditable.`
          : relationCorrection?.mode === "revise"
            ? `Recorded replacement ${assertionId}; the former judgment remains in correction history.`
            : `Recorded ${assertionId}. It is an analyst judgment, not observed evidence.`,
      );
      setRelationAnnotation("");
      setRelationCorrection(null);
      await onDataChanged?.();
    } catch (reason) {
      setRelationMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRelationBusy(false);
    }
  };

  const beginRelationCorrection = (
    mode: "revise" | "retract",
    edge: VisualizationEdge,
  ) => {
    setRelationCorrection({ mode, edge });
    setRelationMessage("");
    setRelationAnnotation("");
    if (mode === "revise") {
      setSelectedRefs([edge.source, edge.target]);
      setRelationPredicate(edge.relationship);
    }
  };

  const saveNodeAnnotation = async () => {
    if (!selectedNode || !nodeAnnotation.trim()) return;
    setNodeAnnotationBusy(true);
    setNodeAnnotationMessage("");
    try {
      const response = await fetch("/api/graph-annotations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          node_ref: selectedNode.reference,
          text: nodeAnnotation.trim(),
        }),
      });
      const result = await response.json() as {
        annotation?: { id: number };
        error?: string;
      };
      if (!response.ok || !result.annotation) {
        throw new Error(result.error ?? "Unable to save graph annotation");
      }
      setNodeAnnotation("");
      setNodeAnnotationMessage(
        `Saved analyst note ${result.annotation.id}. Graph evidence was unchanged.`,
      );
    } catch (reason) {
      setNodeAnnotationMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setNodeAnnotationBusy(false);
    }
  };

  const updateZoom = (factor: number) => {
    checkpointPresentation();
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

  const saveLayout = async () => {
    const name = layoutName.trim();
    if (!name) {
      setLayoutMessage("Enter a layout name first.");
      return;
    }
    setLayoutBusy(true);
    setLayoutMessage("");
    try {
      const response = await fetch("/api/graph-layouts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "save",
          name,
          node_positions: Object.fromEntries(
            Object.entries(positions).filter(([reference]) => visibleIds.has(reference)),
          ),
          viewport,
          filter_text: query,
          labels,
          pinned_refs: [...pinned],
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? "Unable to save graph layout");
      setLayoutMessage(`Saved “${name}” as presentation state only.`);
      await onLayoutsChanged?.();
    } catch (reason) {
      setLayoutMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLayoutBusy(false);
    }
  };

  const loadLayout = async (name: string) => {
    if (!name) return;
    setLayoutBusy(true);
    setLayoutMessage("");
    const previousPresentation = latestPresentation.current;
    try {
      const response = await fetch(`/api/graph-layouts?name=${encodeURIComponent(name)}`, {
        cache: "no-store",
      });
      const result = await response.json() as ResolvedGraphLayout & { error?: string };
      if (!response.ok) throw new Error(result.error ?? "Unable to load graph layout");
      pushUndo(previousPresentation);
      setLayoutName(result.name);
      pendingLayoutPositions.current = result.node_positions;
      setQuery(result.filter_text);
      setPositions((current) => ({ ...current, ...result.node_positions }));
      setLabels(result.labels);
      setPinned(new Set(result.pinned_refs));
      window.setTimeout(() => {
        pendingLayoutPositions.current = null;
      }, 0);
      setViewport(result.viewport);
      setLayoutMessage(
        result.topology_changed
          ? `Loaded with graph changes: ${result.new_node_refs.length} new, ${result.missing_node_refs.length} absent.`
          : "Loaded saved presentation. Evidence and relationships were not changed.",
      );
    } catch (reason) {
      setLayoutMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLayoutBusy(false);
    }
  };

  const deleteLayout = async () => {
    const name = layoutName.trim();
    if (!name || !layouts.some((layout) => layout.name === name)) return;
    setLayoutBusy(true);
    setLayoutMessage("");
    try {
      const response = await fetch("/api/graph-layouts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "delete", name, confirmation: name }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? "Unable to delete graph layout");
      setLayoutName("");
      setLayoutMessage(`Deleted presentation “${name}”. Graph evidence was untouched.`);
      await onLayoutsChanged?.();
    } catch (reason) {
      setLayoutMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLayoutBusy(false);
    }
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

  useEffect(() => () => {
    if (wheelCommitTimer.current !== null) window.clearTimeout(wheelCommitTimer.current);
  }, []);

  if (intent.data.nodes.length === 0) return <VisualizationEmpty intent={intent} />;
  return (
    <div
      className="relationship-visualization"
      onKeyDown={(event) => {
        if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "z") return;
        if (
          event.target instanceof HTMLInputElement
          || event.target instanceof HTMLTextAreaElement
          || event.target instanceof HTMLSelectElement
        ) return;
        event.preventDefault();
        if (event.shiftKey) redoPresentation();
        else undoPresentation();
      }}
    >
      <div className="relationship-controls">
        <label>
          <span>Filter indicators or types</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="domain, IP, file…" />
        </label>
        <span>
          Showing {visibleNodes.length} of {intent.data.nodes.length} nodes · {visibleEdges.length} visible edges
          {hiddenRefs.size > 0 ? ` · ${hiddenRefs.size} collapsed` : ""}
        </span>
        {intent.data.edges.length > 0 && (
          <span className="graph-zoom-controls" aria-label="Graph zoom controls">
            <button onClick={() => updateZoom(1.2)} aria-label="Zoom relationship graph in">＋</button>
            <button onClick={() => updateZoom(1 / 1.2)} aria-label="Zoom relationship graph out">－</button>
            <button onClick={() => { checkpointPresentation(); setViewport({ x: 0, y: 0, scale: 1 }); }}>CENTER</button>
          </span>
        )}
        <span className="graph-history-controls" aria-label="Graph presentation history">
          <button onClick={undoPresentation} disabled={undoStack.length === 0}>UNDO VIEW</button>
          <button onClick={redoPresentation} disabled={redoStack.length === 0}>REDO VIEW</button>
        </span>
        {selectedRefs.length > 0 && <span>{selectedRefs.length} selected</span>}
        {hiddenRefs.size > 0 && (
          <button onClick={() => { checkpointPresentation(); setCollapsedRefs(new Set()); }}>SHOW ALL CONNECTIONS</button>
        )}
        {(query || selectedRefs.length > 0 || collapsedRefs.size > 0) && (
          <button onClick={() => {
            if (collapsedRefs.size > 0) checkpointPresentation();
            setQuery("");
            setSelectedRefs([]);
            setCollapsedRefs(new Set());
          }}>RESET VIEW</button>
        )}
      </div>
      <div className="graph-layout-controls" aria-label="Saved graph presentations">
        <label>
          <span>Saved presentation</span>
          <select
            value={layouts.some((layout) => layout.name === layoutName) ? layoutName : ""}
            onChange={(event) => void loadLayout(event.target.value)}
            disabled={layoutBusy}
          >
            <option value="">Choose a layout</option>
            {layouts.map((layout) => <option key={layout.id} value={layout.name}>{layout.name}</option>)}
          </select>
        </label>
        <label>
          <span>Layout name</span>
          <input
            value={layoutName}
            onChange={(event) => setLayoutName(event.target.value)}
            maxLength={64}
            placeholder="Analyst view"
          />
        </label>
        <button onClick={() => void saveLayout()} disabled={layoutBusy || !layoutName.trim()}>
          SAVE VIEW
        </button>
        <button
          onClick={() => void deleteLayout()}
          disabled={layoutBusy || !layouts.some((layout) => layout.name === layoutName.trim())}
        >
          DELETE VIEW
        </button>
        {layoutMessage && <small role="status">{layoutMessage}</small>}
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
                className={selectedSet.has(node.reference) ? "selected" : ""}
                title={node.label}
                aria-pressed={selectedSet.has(node.reference)}
                onClick={(event) => selectNode(
                  node.reference,
                  event.shiftKey || event.metaKey || event.ctrlKey,
                )}
                onDoubleClick={() => {
                  if ((degree.get(node.reference) ?? 0) > 0) toggleNeighborhood(node.reference);
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
            beginPresentationInteraction();
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
            if (drag?.pointerId === event.pointerId) {
              setDrag(null);
              completePresentationInteraction();
            }
          }}
          onPointerCancel={() => {
            setDrag(null);
            completePresentationInteraction();
          }}
          onWheel={(event) => {
            event.preventDefault();
            beginPresentationInteraction();
            if (wheelCommitTimer.current !== null) window.clearTimeout(wheelCommitTimer.current);
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
            wheelCommitTimer.current = window.setTimeout(() => {
              wheelCommitTimer.current = null;
              completePresentationInteraction();
            }, 180);
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
                    selectedSet.has(node.reference) ? "selected" : "",
                    pinned.has(node.reference) ? "pinned" : "",
                    collapsedRefs.has(node.reference) ? "collapsed" : "",
                    selectedRefs.some((reference) => neighbors.get(reference)?.has(node.reference))
                      ? "neighbor"
                      : "",
                    `type-${node.entity_type.replaceAll(/[^a-z0-9-]/gi, "-")}`,
                  ].join(" ")}
                  role="button"
                  tabIndex={0}
                  aria-pressed={selectedSet.has(node.reference)}
                  aria-label={`${labels[node.reference] ?? node.label}, ${node.entity_type}, ${degree.get(node.reference) ?? 0} relationships`}
                  onClick={(event) => selectNode(
                    node.reference,
                    event.shiftKey || event.metaKey || event.ctrlKey,
                  )}
                  onDoubleClick={() => toggleNeighborhood(node.reference)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      selectNode(
                        node.reference,
                        event.shiftKey || event.metaKey || event.ctrlKey,
                      );
                    }
                  }}
                  onPointerDown={(event) => {
                    event.stopPropagation();
                    beginPresentationInteraction();
                    event.currentTarget.setPointerCapture(event.pointerId);
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
                    <title>{labels[node.reference] ?? node.label}</title>
                  </circle>
                  <text className="node-label" textAnchor="middle" y="-2">{shortLabel(labels[node.reference] ?? node.label, 21)}</text>
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
        <span><i className="manual" /> Analyst assertion</span>
        <span>Force layout is limited to 48 nodes; drag, pan, zoom, filtering, selection, and collapsed connections change presentation only. Double-click a node to collapse or expand its direct connections. Shift, Command, or Control selects more than one node.</span>
      </div>
      {manualEdges.length > 0 && (
        <details className="manual-relation-review">
          <summary>Review analyst relations · {manualEdges.length}</summary>
          <div className="manual-relation-list">
            {manualEdges.map((edge) => (
              <article key={edge.assertion_id ?? `${edge.source}-${edge.target}`}>
                <b>
                  {shortLabel(labels[edge.source] ?? graphLabels.get(edge.source) ?? edge.source, 28)} {edge.relationship} {shortLabel(labels[edge.target] ?? graphLabels.get(edge.target) ?? edge.target, 28)}
                </b>
                <span>{edge.annotation || "No analyst annotation recorded."}</span>
                <small>{edge.assertion_id}</small>
                <div>
                  <button onClick={() => beginRelationCorrection("revise", edge)}>REVISE</button>
                  <button onClick={() => beginRelationCorrection("retract", edge)}>RETRACT</button>
                </div>
              </article>
            ))}
          </div>
        </details>
      )}
      {selectedRefs.length > 1 && (
        <div className="graph-multiselect" aria-live="polite">
          <b>{selectedRefs.length} NODES SELECTED</b>
          <span>Selection is temporary presentation state and is never saved as evidence or a relationship.</span>
          <button onClick={() => {
            checkpointPresentation();
            setPinned((current) => new Set([...current, ...selectedRefs]));
          }}>
            PIN SELECTED
          </button>
          <button onClick={() => {
            checkpointPresentation();
            setPinned((current) => {
              const next = new Set(current);
              selectedRefs.forEach((reference) => next.delete(reference));
              return next;
            });
          }}>
            UNPIN SELECTED
          </button>
          <button onClick={() => setSelectedRefs([])}>CLEAR SELECTION</button>
        </div>
      )}
      {selectedNodes.length === 2 && relationCorrection?.mode !== "retract" && (
        <form
          className="manual-graph-relation"
          onSubmit={(event) => {
            event.preventDefault();
            void recordManualRelation();
          }}
        >
          <b>
            {relationCorrection?.mode === "revise"
              ? "REVISE ANALYST RELATION"
              : "ANNOTATED ANALYST RELATION"}
          </b>
          <span>
            {shortLabel(selectedNodes[0].label, 32)} → {shortLabel(selectedNodes[1].label, 32)}
          </span>
          <label>
            <span>Relationship</span>
            <input
              value={relationPredicate}
              onChange={(event) => setRelationPredicate(event.target.value)}
              pattern="[a-z][a-z0-9-]{0,63}"
              maxLength={64}
              required
            />
          </label>
          <label className="relation-annotation">
            <span>Required analyst annotation</span>
            <input
              value={relationAnnotation}
              onChange={(event) => setRelationAnnotation(event.target.value)}
              maxLength={1000}
              placeholder="Why should these entities be related?"
              required
            />
          </label>
          <button disabled={relationBusy || !relationAnnotation.trim()}>
            {relationCorrection?.mode === "revise" ? "SAVE REVISION" : "RECORD JUDGMENT"}
          </button>
          {relationCorrection && (
            <button type="button" onClick={() => setRelationCorrection(null)}>CANCEL</button>
          )}
          <small>
            {relationCorrection?.mode === "revise"
              ? "The former judgment remains auditable and the replacement becomes the active analyst assertion."
              : "Direction follows selection order. This creates a visible analyst assertion, never an observed edge."}
          </small>
          {relationMessage && <small role="status">{relationMessage}</small>}
        </form>
      )}
      {relationCorrection?.mode === "retract" && (
        <form
          className="manual-graph-relation"
          onSubmit={(event) => {
            event.preventDefault();
            void recordManualRelation();
          }}
        >
          <b>RETRACT ANALYST RELATION</b>
          <span>
            {shortLabel(labels[relationCorrection.edge.source] ?? graphLabels.get(relationCorrection.edge.source) ?? relationCorrection.edge.source, 28)} {relationCorrection.edge.relationship} {shortLabel(labels[relationCorrection.edge.target] ?? graphLabels.get(relationCorrection.edge.target) ?? relationCorrection.edge.target, 28)}
          </span>
          <label className="relation-annotation">
            <span>Required retraction reason</span>
            <input
              value={relationAnnotation}
              onChange={(event) => setRelationAnnotation(event.target.value)}
              maxLength={1000}
              placeholder="Why is this judgment being withdrawn?"
              required
            />
          </label>
          <button disabled={relationBusy || !relationAnnotation.trim()}>CONFIRM RETRACTION</button>
          <button type="button" onClick={() => setRelationCorrection(null)}>CANCEL</button>
          <small>The assertion is withdrawn from the active graph, never deleted from its audit history.</small>
          {relationMessage && <small role="status">{relationMessage}</small>}
        </form>
      )}
      {selectedNode && (
        <div className="visualization-selection" aria-live="polite">
          <b>{selectedNode.label}</b>
          <span>{selectedNode.entity_type} · {degree.get(selectedNode.reference) ?? 0} relationships</span>
          <small>
            {selectedRefs.length > 1 ? "Primary selection" : "Selection"} highlights visible neighbors without changing graph evidence.
          </small>
          <button onClick={() => {
            checkpointPresentation();
            setPinned((current) => {
              const next = new Set(current);
              if (next.has(selectedNode.reference)) next.delete(selectedNode.reference);
              else next.add(selectedNode.reference);
              return next;
            });
          }}>
            {pinned.has(selectedNode.reference) ? "UNPIN FROM VIEW" : "PIN IN VIEW"}
          </button>
          {(degree.get(selectedNode.reference) ?? 0) > 0 && (
            <button onClick={() => toggleNeighborhood(selectedNode.reference)}>
              {collapsedRefs.has(selectedNode.reference)
                ? "EXPAND DIRECT CONNECTIONS"
                : "COLLAPSE DIRECT CONNECTIONS"}
            </button>
          )}
          <label className="graph-display-label">
            <span>Presentation label</span>
            <input
              value={labels[selectedNode.reference] ?? ""}
              maxLength={160}
              placeholder={selectedNode.label}
              onFocus={() => {
                labelEditStart.current = latestPresentation.current;
                labelEditCheckpointed.current = false;
              }}
              onChange={(event) => {
                const before = labelEditStart.current ?? latestPresentation.current;
                const previousLabel = before.labels[selectedNode.reference] ?? "";
                if (!labelEditCheckpointed.current && event.target.value !== previousLabel) {
                  pushUndo(before);
                  labelEditCheckpointed.current = true;
                }
                setLabels((current) => ({
                  ...current,
                  [selectedNode.reference]: event.target.value,
                }));
              }}
              onBlur={() => {
                labelEditStart.current = null;
                labelEditCheckpointed.current = false;
              }}
            />
          </label>
          <label className="graph-node-annotation">
            <span>Analyst note</span>
            <textarea
              value={nodeAnnotation}
              maxLength={4000}
              onChange={(event) => setNodeAnnotation(event.target.value)}
              placeholder="Why does this node matter? This remains analyst-authored context."
            />
          </label>
          <button
            onClick={() => void saveNodeAnnotation()}
            disabled={nodeAnnotationBusy || !nodeAnnotation.trim()}
          >
            SAVE NODE NOTE
          </button>
          {nodeAnnotationMessage && <small role="status">{nodeAnnotationMessage}</small>}
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
            <thead><tr><th scope="col">Indicator</th><th scope="col">Type</th><th scope="col">Relations</th><th scope="col">View</th></tr></thead>
            <tbody>
              {intent.data.nodes.map((node) => (
                <tr key={node.reference}>
                  <td>{node.label}</td>
                  <td>{node.entity_type}</td>
                  <td>{degree.get(node.reference) ?? 0}</td>
                  <td>{hiddenRefs.has(node.reference) ? "Collapsed" : "Visible"}</td>
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
  graphLayouts = [],
  onGraphLayoutsChanged,
  onDataChanged,
}: {
  intents: VisualizationIntent[];
  theme: VisualizationTheme;
  onOpenEvidence?: (reference: string, origin: HTMLElement) => void;
  graphLayouts?: GraphLayoutSummary[];
  onGraphLayoutsChanged?: () => Promise<void> | void;
  onDataChanged?: () => Promise<void> | void;
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
      <div className="visualization-picker">
        <label>
          <span>CHOOSE AN ANALYST QUESTION</span>
          <select value={selected.intent_id} onChange={(event) => setSelectedId(event.target.value)}>
            {intents.map((intent) => (
              <option key={intent.intent_id} value={intent.intent_id}>{intent.title}</option>
            ))}
          </select>
        </label>
        <small>{intents.length} evidence views · Pivotglass recommends the first applicable view.</small>
      </div>
      <header className="visualization-header">
        <div>
          <span>ANALYST QUESTION</span>
          <h3>{selected.question_text}</h3>
          <small>
            {selected.source_scope.description} · {selected.source_scope.record_count} records
            {selected.source_scope.timezone ? ` · ${selected.source_scope.timezone}` : ""}
          </small>
          <aside className="visualization-explainer" aria-label="Why Pivotglass selected this visualization">
            <b>{VISUALIZATION_VIEW_LABELS[selected.view]}</b>
            <p><strong>Why this fits</strong> {selected.selection_rationale}</p>
            <p><strong>How to read it</strong> {selected.reading_guide}</p>
          </aside>
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
              : selected.view === "dendrogram"
                ? <HierarchyTree intent={selected} />
              : selected.view === "uncertainty_intervals"
                ? <UncertaintyIntervals intent={selected} />
              : selected.view === "relationship_graph"
                ? <RelationshipGraph intent={selected} onOpenEvidence={onOpenEvidence} layouts={graphLayouts} onLayoutsChanged={onGraphLayoutsChanged} onDataChanged={onDataChanged} />
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
