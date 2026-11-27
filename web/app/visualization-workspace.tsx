"use client";

import { CSSProperties, RefObject, useCallback, useEffect, useLayoutEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Chart, registerables } from "chart.js";

import {
  appendGraphPresentationHistory,
  bundleGraphLeaves,
  compileFlintChartjs,
  radarHasShape,
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
import { Icon } from "./icons";
import { RGBLed, rgbLabelForStatus } from "./rgb-led";
import { LiteBritePeg } from "./lite-brite-peg";
import { COVERAGE_LABELS, indicatorTypeLabel, reportedCountry, tooltipPosition } from "./constellation-presentation";

Chart.register(...registerables);

const CONSTELLATION_COLUMN_LABELS: Readonly<Record<string, string>> = {
  identity: "Identity",
  ttps: "Techniques",
  infrastructure: "Infrastructure",
  timing: "Timing",
  targeting: "Targeting",
  capability: "Capability",
  motivation: "Motivation",
  predictions: "Predictions",
  denial: "Counterevidence",
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
  timeline: "Chronological trail",
};

function constellationStatusHelp(status: string): string {
  if (status === "filled") {
    return "Coverage met: source-backed evidence meets the configured coverage threshold; coverage is not confidence or truth.";
  }
  if (status === "partial") return "Some evidence: source-backed evidence exists, but material gaps remain.";
  if (status === "deferred") {
    return "No automated path: this dimension needs analyst assessment; no work is automatically scheduled.";
  }
  if (status === "empty") return "No evidence: no supporting evidence is present in the admitted neighborhood. This is not a threat verdict.";
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
      const height = Math.max(260, (canvas.current.parentElement?.clientHeight ?? 320) - 40);
      const config = compileFlintChartjs(
        intent,
        { width, height },
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
      const datasets = themed.data.datasets ?? [];
      // A series field (indicator type) keeps one colour per series, from the
      // same type hues as the relationship graph (#37); a single series uses the accent.
      const bySeries = Boolean(intent.fields.series) && datasets.length > 1;
      const rootStyle = getComputedStyle(document.documentElement);
      for (const dataset of datasets) {
        const hue = bySeries
          ? rootStyle.getPropertyValue(`--type-${String(dataset.label ?? "")}`).trim() || theme.dim_color
          : theme.accent_color;
        dataset.borderColor = hue;
        dataset.backgroundColor = bySeries ? hue : `${hue}42`;
        dataset.pointBackgroundColor = bySeries ? hue : theme.heading_color;
        dataset.borderWidth = bySeries ? 1 : 2;
      }
      if (bySeries) {
        const legend = (plugins.legend ?? {}) as Record<string, unknown>;
        plugins.legend = { ...legend, display: true, labels: { ...((legend.labels ?? {}) as object), color: theme.text_color } };
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
    <div className="flint-canvas" data-viz-fill="" data-viz-max="640">
      {intent.view === "histogram" && (
        <label className="histogram-bins">
          <span>Bins</span>
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

/** Compact coverage list used when a radar would have fewer than three spokes (#38). */
function FacetBars({ intent }: { intent: VisualizationIntent }) {
  const category = intent.fields.category;
  const value = intent.fields.value;
  if (intent.data.rows.length === 0) return <VisualizationEmpty intent={intent} />;
  return (
    <ul className="facet-bars" aria-label={intent.title}>
      {intent.data.rows.map((row) => {
        const raw = row[value];
        const score = raw === null || raw === undefined ? null : Math.max(0, Math.min(100, Number(raw)));
        const state = String(row.status ?? (score === null ? "deferred" : ""));
        const status = COVERAGE_LABELS[state] ?? state;
        return (
          <li key={String(row[category])} className={score ? "" : "empty"}>
            <span className="facet-name">{String(row[category])}</span>
            <span className="facet-track" aria-hidden="true">
              <span style={{ width: `${score ?? 0}%` }} />
            </span>
            <span className="facet-status">{status}</span>
          </li>
        );
      })}
    </ul>
  );
}

function VisualizationEmpty({ intent }: { intent: VisualizationIntent }) {
  return (
    <div className="visualization-empty">
      <b>Nothing recorded for this view yet.</b>
      <span>Scope: {intent.source_scope.description}</span>
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

/**
 * Provenance as a dense timeline (#39): one row per event (time, source,
 * action, result), oldest first, so a 30-event trail fits one screen. A row
 * opens its card (basis, actor, full timestamp) on demand.
 */
function PivotTrail({ intent }: { intent: VisualizationIntent }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!intent.data.rows.length) return <VisualizationEmpty intent={intent} />;
  const rows = [...intent.data.rows].sort((left, right) =>
    displayValue(left.timestamp).localeCompare(displayValue(right.timestamp)));
  const words = (value: unknown) => displayValue(value).replaceAll("_", " ");
  return <div className="provenance-history">
    <p>Each row records a source admission, analyst grouping, or investigation step. Select a row for its basis.</p>
    <div className="provenance-timeline" role="region" aria-label="Provenance timeline" data-viz-fill="" tabIndex={0}>
      <table>
        <thead><tr><th scope="col">Time (UTC)</th><th scope="col">Source</th><th scope="col">Action</th><th scope="col">Result</th></tr></thead>
        <tbody>
          {rows.map((row, index) => {
            const id = String(row.event_id ?? index);
            const expanded = open === id;
            const stamp = displayValue(row.timestamp);
            return [
              <tr key={id} className={expanded ? "open" : ""} aria-expanded={expanded} tabIndex={0}
                onClick={() => setOpen(expanded ? null : id)}
                onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setOpen(expanded ? null : id); } }}>
                <td><time dateTime={stamp} title={stamp}>{stamp.slice(0, 16).replace("T", " ")}</time></td>
                <td title={words(row.from_kind)}>{displayValue(row.from_label)}</td>
                <td>{words(row.action)}</td>
                <td>{displayValue(row.to_label)}</td>
              </tr>,
              expanded && <tr key={`${id}-card`} className="provenance-card"><td colSpan={4}>
                <dl>
                  <div><dt>Basis</dt><dd>{displayValue(row.basis) || "Not recorded"}</dd></div>
                  <div><dt>Source kind</dt><dd>{words(row.from_kind)}</dd></div>
                  <div><dt>Recorded by</dt><dd>{displayValue(row.created_by)}</dd></div>
                  <div><dt>Time</dt><dd>{stamp}</dd></div>
                </dl>
              </td></tr>,
            ];
          })}
        </tbody>
      </table>
    </div>
  </div>;
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
    <div className="hierarchy-visualization" data-viz-fill="">
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

function MatrixTooltip({ tip, id, onEnter, onLeave }: {
  tip: { text: string; anchor: HTMLElement }; id: string; onEnter: () => void; onLeave: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [style, setStyle] = useState<CSSProperties>({ visibility: "hidden" });
  useLayoutEffect(() => {
    const box = ref.current;
    if (!box) return;
    const theme = getComputedStyle(tip.anchor);
    setStyle({
      ...tooltipPosition(tip.anchor.getBoundingClientRect(), box.getBoundingClientRect(),
        { width: window.innerWidth, height: window.innerHeight }),
      background: theme.getPropertyValue("--elevated"),
      color: theme.getPropertyValue("--ink"),
      borderColor: theme.getPropertyValue("--line"),
    });
  }, [tip]);
  return createPortal(<div ref={ref} id={id} className="matrix-hover-tooltip" role="tooltip" style={style}
    onPointerEnter={onEnter} onPointerLeave={onLeave}>
    {tip.text}
  </div>, document.body);
}

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
  const [hoverTip, setHoverTip] = useState<{ text: string; anchor: HTMLElement } | null>(null);
  const tooltipId = useId();
  const tooltipTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
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
  const keepHoverTip = () => {
    if (tooltipTimer.current) clearTimeout(tooltipTimer.current);
  };
  const scheduleHideHoverTip = () => {
    keepHoverTip();
    tooltipTimer.current = setTimeout(() => setHoverTip(null), 180);
  };
  useEffect(() => () => { if (tooltipTimer.current) clearTimeout(tooltipTimer.current); }, []);
  const showHoverTip = (event: React.SyntheticEvent<HTMLElement>, text: string) => {
    keepHoverTip();
    setHoverTip({ text, anchor: event.currentTarget });
  };

  useEffect(() => {
    if (!hoverTip) return;
    const dismiss = (event?: Event) => {
      if (event?.target instanceof Element && event.target.closest(".matrix-hover-tooltip")) return;
      if (event?.type === "scroll" && document.activeElement === hoverTip.anchor) {
        const rect = hoverTip.anchor.getBoundingClientRect();
        if (rect.bottom > 0 && rect.top < window.innerHeight) {
          setHoverTip({ ...hoverTip });
          return;
        }
      }
      setHoverTip(null);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.stopPropagation();
      dismiss();
    };
    window.addEventListener("resize", dismiss);
    document.addEventListener("scroll", dismiss, true);
    document.addEventListener("keydown", escape, true);
    return () => {
      window.removeEventListener("resize", dismiss);
      document.removeEventListener("scroll", dismiss, true);
      document.removeEventListener("keydown", escape, true);
    };
  }, [hoverTip]);

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
            <summary>Filters · {[query, typeFilter !== "all", completenessFilter !== "all", relatedReference, firstSeenAfter, lastSeenBefore].filter(Boolean).length} active</summary>
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
        <div className="lite-brite-legend" aria-label="Evidence coverage legend">
          {(["filled", "partial", "empty", "deferred"] as const).map((status) => (
            <span key={status}>
              <LiteBritePeg compact status={status} label={COVERAGE_LABELS[status]} />
              <b>{COVERAGE_LABELS[status]}</b>
            </span>
          ))}
          <small>Coverage—not confidence or safety. Hover or focus for facts; click for details.</small>
        </div>
      )}
      {!isConstellation && activeCell && (
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
      {hoverTip && <MatrixTooltip tip={hoverTip} id={tooltipId} onEnter={keepHoverTip} onLeave={scheduleHideHoverTip} />}
      <div
        className={`task-matrix-wrap ${isConstellation ? "constellation-matrix-wrap" : ""}`}
        ref={matrixWrap}
        data-viz-fill=""
        data-viz-reserve={activeCell ? 150 : 56}
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
                  title={isConstellation ? undefined : column.replaceAll("_", " ")}
                >
                  {isConstellation
                    ? (
                      <button
                        type="button"
                        className="constellation-dimension-help"
                        id={`${tooltipId}-column-${column}`}
                        aria-label={`${CONSTELLATION_COLUMN_LABELS[column] ?? column}: ${CONSTELLATION_DIMENSION_HELP[column] ?? "Canonical Dossier dimension."}`}
                        onPointerEnter={(event) => showHoverTip(event, `${CONSTELLATION_COLUMN_LABELS[column] ?? column}: ${CONSTELLATION_DIMENSION_HELP[column] ?? "Canonical Dossier dimension."}`)}
                        onPointerLeave={scheduleHideHoverTip}
                        onFocus={(event) => showHoverTip(event, `${CONSTELLATION_COLUMN_LABELS[column] ?? column}: ${CONSTELLATION_DIMENSION_HELP[column] ?? "Canonical Dossier dimension."}`)}
                        onBlur={() => setHoverTip(null)}
                        aria-describedby={hoverTip?.anchor.id === `${tooltipId}-column-${column}` ? tooltipId : undefined}
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
              const country = row.country_source ? reportedCountry(row.country_code) : null;
              // The hover adds only what the row does not already show: where the infrastructure
              // sits (and who said so) and which dimensions still lack evidence.
              const gaps = isConstellation
                ? columns.filter((column) => String(cells.get(`${rowId}\u0000${column}`)?.[statusField] ?? "") === "empty")
                  .map((column) => CONSTELLATION_COLUMN_LABELS[column] ?? column)
                : [];
              const hintParts = [
                country ? `${country.flag} ${country.name} · ${displayValue(row.country_source)}, ${displayValue(row.country_observed_at).slice(0, 10)}` : "",
                row.known ? `Known: ${displayValue(row.known)} · ${displayValue(row.known_source)}` : "",
                gaps.length ? `No evidence yet: ${gaps.join(", ")}` : "",
              ].filter(Boolean);
              const rowHint = hintParts.join("\n");
              const indicatorHelp = [`${label}, ${indicatorTypeLabel(String(row.indicator_type))}, ${displayValue(row.completeness_percent)}% coverage`, ...hintParts].join(". ");
              return (
                <tr key={rowId}>
                  <th scope="row">
                    {onOpenEvidence && row.reference
                      ? (
                        <button
                          id={`${tooltipId}-row-${rowIndex}`}
                          onPointerEnter={(event) => { if (rowHint) showHoverTip(event, rowHint); }}
                          onPointerLeave={scheduleHideHoverTip}
                          onFocus={(event) => { if (rowHint) showHoverTip(event, rowHint); }}
                          onBlur={() => setHoverTip(null)}
                          aria-describedby={hoverTip?.anchor.id === `${tooltipId}-row-${rowIndex}` ? tooltipId : undefined}
                          aria-label={indicatorHelp}
                          onClick={(event) => { setHoverTip(null); onOpenEvidence(String(row.reference), event.currentTarget); }}
                        >
                          <b>{label}</b>
                          {isConstellation && (
                            <small>
                              {country && <span className="constellation-country" aria-label={`Source-reported location: ${country.name}`}><span aria-hidden="true">{country.flag}</span> {country.code}</span>}
                              {indicatorTypeLabel(String(row.indicator_type))} · {displayValue(row.completeness_percent)}% coverage
                              {row.known ? <span className={`listed listed-${displayValue(row.known_category)}`}> · {displayValue(row.known)}</span> : null}
                            </small>
                          )}
                        </button>
                      )
                      : label}
                  </th>
                  {columns.map((column, columnIndex) => {
                    const cell = cells.get(`${rowId}\u0000${column}`);
                    if (!cell) return <td className="matrix-empty" key={column}>—</td>;
                    const status = String(cell[statusField]);
                    const dimension = isConstellation ? CONSTELLATION_COLUMN_LABELS[column] ?? column : column.replaceAll("_", " ");
                    const evidenceCount = displayValue(cell.evidence_count);
                    const cellHelp = isConstellation
                      ? `${label}. ${dimension}: ${CONSTELLATION_DIMENSION_HELP[column] ?? "Canonical Dossier dimension."} ${constellationStatusHelp(status)} ${evidenceCount} source-backed evidence records.`
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
                          id={`${tooltipId}-cell-${rowIndex}-${columnIndex}`}
                          onPointerEnter={(event) => showHoverTip(event, cellHelp)}
                          onPointerLeave={scheduleHideHoverTip}
                          data-grid-row={rowIndex}
                          data-grid-column={columnIndex}
                          tabIndex={isConstellation
                            ? (gridFocus.row === rowIndex && gridFocus.column === columnIndex ? 0 : -1)
                            : 0}
                          aria-pressed={isConstellation ? isSelected : undefined}
                          onClick={() => {
                            setHoverTip(null);
                            setSelected(cell);
                            onSelectCell?.(cell);
                          }}
                          onFocus={(event) => {
                            showHoverTip(event, cellHelp);
                            if (isConstellation) setGridFocus({ row: rowIndex, column: columnIndex });
                          }}
                          onBlur={() => setHoverTip(null)}
                          aria-describedby={hoverTip?.anchor.id === `${tooltipId}-cell-${rowIndex}-${columnIndex}` ? tooltipId : undefined}
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
                          title={isConstellation ? undefined : `${dimension} · ${status}`}
                          aria-label={isConstellation
                            ? cellHelp
                            : `${label}, ${column}, ${status}. RGB status ${rgbLabelForStatus(status)}`}
                        >
                          {isConstellation
                            ? (
                              <LiteBritePeg
                                compact
                                status={status}
                                label={`${dimension}, ${COVERAGE_LABELS[status] ?? status}`}
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
      {isConstellation && (
        <section className="visualization-selection constellation-selection" aria-label="Selected coverage details" aria-live="polite">
          {activeCell ? <>
            <b>{displayValue(activeCell[rowField])}</b>
            <span>{CONSTELLATION_COLUMN_LABELS[String(activeCell[columnField])] ?? displayValue(activeCell[columnField])} · {COVERAGE_LABELS[String(activeCell[statusField])] ?? displayValue(activeCell[statusField])}</span>
            <small>{constellationStatusHelp(String(activeCell[statusField]))} {displayValue(activeCell.evidence_count)} source-backed evidence records. First seen: {displayValue(activeCell.first_seen)} · Last seen: {displayValue(activeCell.last_seen)}.</small>
            {onOpenEvidence && activeCell.reference && <button type="button" onClick={(event) => onOpenEvidence(String(activeCell.reference), event.currentTarget)}>Open evidence & provenance</button>}
          </> : null}
        </section>
      )}
      {rowIds.length === 0 && (
        <div className="visualization-empty">
          <b>No indicators match</b>
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

type GraphNodeNote = { id: number; content: string; created_at: string };

/** Hubs keep rank order; everything else is dealt round-robin by indicator type. */
function diversifyByType<T extends { entity_type: string }>(ranked: T[], isHub: (node: T) => boolean): T[] {
  const ordered = ranked.filter(isHub);
  const queues = new Map<string, T[]>();
  for (const node of ranked) {
    if (isHub(node)) continue;
    queues.set(node.entity_type, [...(queues.get(node.entity_type) ?? []), node]);
  }
  const lanes = [...queues.values()];
  while (lanes.some((lane) => lane.length)) {
    for (const lane of lanes) {
      const next = lane.shift();
      if (next) ordered.push(next);
    }
  }
  return ordered;
}

/** Layout area grows with node count and keeps the canvas aspect ratio. */
function layoutSpace(count: number, width: number, height: number): { width: number; height: number } {
  const ideal = Math.max(76, Math.min(150, 560 / Math.sqrt(Math.max(count, 1))));
  const aspect = width / Math.max(height, 1);
  const logicalWidth = Math.max(width, Math.sqrt(count * ideal * ideal * 2.2 * aspect));
  return { width: logicalWidth, height: logicalWidth / aspect };
}

/**
 * Scale and centre so every visible node fits. Nodes and labels are drawn at a constant
 * screen size, so the padding (room for labels to the right, the legend below) is in pixels.
 */
function fitViewport(points: Record<string, GraphPoint>, width: number, height: number): GraphViewport {
  const values = Object.values(points);
  if (!values.length) return { x: 0, y: 0, scale: 1 };
  const xs = values.map((point) => point.x);
  const ys = values.map((point) => point.y);
  const pad = { left: 28, right: Math.min(210, width * 0.22), top: 32, bottom: 64 };
  const spanX = Math.max(1, Math.max(...xs) - Math.min(...xs));
  const spanY = Math.max(1, Math.max(...ys) - Math.min(...ys));
  const scale = Math.max(0.15, Math.min(1.6,
    (width - pad.left - pad.right) / spanX,
    (height - pad.top - pad.bottom) / spanY,
  ));
  const centreX = (Math.min(...xs) + Math.max(...xs)) / 2;
  const centreY = (Math.min(...ys) + Math.max(...ys)) / 2;
  return {
    x: pad.left + (width - pad.left - pad.right) / 2 - centreX * scale,
    y: pad.top + (height - pad.top - pad.bottom) / 2 - centreY * scale,
    scale,
  };
}

function forceLayout(
  nodes: VisualizationIntent["data"]["nodes"],
  edges: VisualizationIntent["data"]["edges"],
  width: number,
  height: number,
): Record<string, GraphPoint> {
  const positions = new Map<string, GraphPoint>();
  const velocity = new Map<string, GraphPoint>();
  // Wide canvases are common (a 1600px pane is often 3:1). Start on an ellipse and pull
  // weaker horizontally so the settled graph uses the width instead of a central disc.
  const aspect = Math.max(1 / 3, Math.min(3, width / Math.max(height, 1)));
  const radius = Math.min(width, height) * 0.32;
  // Measured on a 1538×538 canvas: dividing by aspect² flattened the graph to a 6.6:1
  // strip; dividing by aspect settles near the canvas's own proportions.
  const gravityX = 0.0016 / Math.max(1, aspect);
  const gravityY = 0.0016 * Math.min(1, aspect);
  nodes.forEach((node, index) => {
    const hash = stableHash(node.reference);
    const angle = (Math.PI * 2 * index) / Math.max(1, nodes.length) + (hash % 97) / 311;
    const jitter = ((hash >>> 8) % 61) - 30;
    positions.set(node.reference, {
      x: width / 2 + Math.cos(angle) * (radius + jitter) * Math.max(1, aspect),
      y: height / 2 + Math.sin(angle) * (radius + jitter) / Math.min(1, aspect),
    });
    velocity.set(node.reference, { x: 0, y: 0 });
  });

  // Edge length follows the space available, so a large canvas spreads the graph out.
  const ideal = Math.max(76, Math.min(220, Math.sqrt((width * height) / (Math.max(nodes.length, 1) * 2.4))));
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
      speed.x += (width / 2 - position.x) * gravityX;
      speed.y += (height / 2 - position.y) * gravityY;
      speed.x *= 0.82;
      speed.y *= 0.82;
      // Soft bounds only: a hard clamp at the canvas edge stacked leaves into rows along the
      // border. Fit-to-view scales whatever extent the layout settles into.
      position.x = Math.max(-width, Math.min(width * 2, position.x + speed.x * 6));
      position.y = Math.max(-height, Math.min(height * 2, position.y + speed.y * 6));
    }
  }
  return Object.fromEntries(positions);
}

/** Text position for a node label on the side chosen by the collision pass. */
function labelPlacement(side: "right" | "left" | "above" | "below", radius: number, font: number) {
  if (side === "left") return { x: -(radius + 5), y: font / 3, textAnchor: "end" as const };
  if (side === "above") return { x: 0, y: -(radius + 6), textAnchor: "middle" as const };
  if (side === "below") return { x: 0, y: radius + 4 + font, textAnchor: "middle" as const };
  return { x: radius + 5, y: font / 3, textAnchor: "start" as const };
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
  const [expandedBundles, setExpandedBundles] = useState<Set<string>>(new Set());
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
  // The canvas is measured, never fixed: viewBox units equal CSS pixels, so the graph fills
  // whatever space the view gives it and text never scales with the window.
  const [size, setSize] = useState<{ width: number; height: number; font?: number }>({ width: 0, height: 0 });
  const canvasObserver = useRef<ResizeObserver | null>(null);
  const canvasRef = useCallback((element: HTMLDivElement | null) => {
    canvasObserver.current?.disconnect();
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      const rootPx = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
      const next = {
        width: Math.round(entry.contentRect.width),
        height: Math.round(entry.contentRect.height),
        font: Math.round(rootPx * 0.857 * 10) / 10,
      };
      setSize((current) => current.width === next.width && current.height === next.height && current.font === next.font ? current : next);
    });
    observer.observe(element);
    canvasObserver.current = observer;
  }, []);
  const width = size.width || 960;
  const height = size.height || 560;
  const measured = size.width > 0 && size.height > 0;
  const viewportTouched = useRef(false);
  const [hovered, setHovered] = useState<string | null>(null);
  const [showGroups, setShowGroups] = useState(true);
  const [nodeNotes, setNodeNotes] = useState<GraphNodeNote[]>([]);
  const [notesVersion, setNotesVersion] = useState(0);
  const exactDegree = new Map<string, number>();
  for (const edge of intent.data.edges) {
    exactDegree.set(edge.source, (exactDegree.get(edge.source) ?? 0) + 1);
    exactDegree.set(edge.target, (exactDegree.get(edge.target) ?? 0) + 1);
  }
  const normalizedQuery = query.trim().toLowerCase();
  const matchesQuery = (node: { label: string; entity_type: string }) =>
    node.label.toLowerCase().includes(normalizedQuery) || node.entity_type.toLowerCase().includes(normalizedQuery);
  // Same-type leaves of a big hub draw as one aggregate (#41). Selected, pinned and
  // filter-matched nodes always draw on their own.
  const graph = bundleGraphLeaves(intent.data.nodes, intent.data.edges, {
    expanded: expandedBundles,
    label: (type, count) => `${count} ${indicatorTypeLabel(type)}`,
    protectedReferences: new Set([
      ...selectedRefs, ...pinned,
      ...(normalizedQuery ? intent.data.nodes.filter(matchesQuery).map((node) => node.reference) : []),
    ]),
  });
  const degree = new Map(graph.nodes.map((node) => [node.reference, 0]));
  const graphLabels = new Map(graph.nodes.map((node) => [node.reference, node.label]));
  const neighbors = new Map(graph.nodes.map((node) => [node.reference, new Set<string>()]));
  for (const edge of graph.edges) {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
    neighbors.get(edge.source)?.add(edge.target);
    neighbors.get(edge.target)?.add(edge.source);
  }
  const ranked = [...graph.nodes].sort((left, right) => {
    const degreeDifference = (degree.get(right.reference) ?? 0) - (degree.get(left.reference) ?? 0);
    return degreeDifference || left.label.localeCompare(right.label);
  });
  const filteredCandidates = normalizedQuery
    ? ranked.filter(matchesQuery)
    : ranked;
  const protectedRefs = new Set([...selectedRefs, ...pinned]);
  const hiddenRefs = hiddenGraphReferences(graph.edges, collapsedRefs, protectedRefs);
  const priorityRefs = new Set([...selectedRefs, ...pinned]);
  const groupHidden = (node: { entity_type: string }) => !showGroups && node.entity_type === "analyst-group";
  const candidates = [
    ...ranked.filter((node) => priorityRefs.has(node.reference) && !hiddenRefs.has(node.reference)),
    // Hubs first, then one of each indicator type in turn, so 48 slots never fill with a
    // single alphabetical run of one type.
    ...diversifyByType(
      filteredCandidates.filter(
        (node) => !priorityRefs.has(node.reference) && !hiddenRefs.has(node.reference) && !groupHidden(node),
      ),
      (node) => (degree.get(node.reference) ?? 0) >= 3,
    ),
  ];
  const visibleNodes = candidates.slice(0, 48);
  const visibleIds = new Set(visibleNodes.map((node) => node.reference));
  const visibleEdges = graph.edges.filter(
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
    () => {
      if (!measured) return {};
      const space = layoutSpace(visibleNodes.length, width, height);
      return forceLayout(visibleNodes, visibleEdges, space.width, space.height);
    },
    // graphKey is a compact deterministic identity for the current presentation subset; the
    // layout is computed once the canvas is measured and is not recomputed on resize.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [graphKey, measured],
  );
  useEffect(() => {
    const restored = pendingLayoutPositions.current;
    pendingLayoutPositions.current = null;
    setPositions((current) => (
      restored
        ? { ...initialPositions, ...current, ...restored }
        : { ...initialPositions, ...current }
    ));
    if (!graphInitialized.current && Object.keys(initialPositions).length) {
      graphInitialized.current = true;
      if (!restored) setViewport(fitViewport(initialPositions, width, height));
    }
  }, [initialPositions]);
  useEffect(() => {
    // Keep the whole graph in view as the window or pane changes size, until the analyst
    // pans or zooms; after that their view is theirs.
    if (!graphInitialized.current || viewportTouched.current) return;
    // Positions set in this same commit are not in this closure yet; fall back to the layout.
    const current = Object.entries({ ...initialPositions, ...positions }).filter(([reference]) => visibleIds.has(reference));
    if (!current.length) return;
    setViewport(fitViewport(Object.fromEntries(current), width, height));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [width, height]);
  const selected = selectedRefs.at(-1) ?? null;
  const selectedSet = new Set(selectedRefs);
  const selectedNode = graph.nodes.find((node) => node.reference === selected);
  const selectedNodes = selectedRefs
    .map((reference) => graph.nodes.find((node) => node.reference === reference))
    .filter((node): node is NonNullable<typeof node> => Boolean(node));
  const markerId = `${intent.intent_id}-relationship-arrow`;
  const selectedNodeRef = selectedNode?.reference;
  // Notes attach to stored indicators; presentation-only nodes (analyst groups) have none.
  const selectedNodeTakesNotes = selectedNode?.evidence !== false;
  useEffect(() => { setNodeAnnotationMessage(""); }, [selectedNodeRef]);
  useEffect(() => {
    if (!selectedNodeRef || !selectedNodeTakesNotes) {
      setNodeNotes([]);
      return;
    }
    let live = true;
    fetch(`/api/graph-annotations?node_ref=${encodeURIComponent(selectedNodeRef)}`, { cache: "no-store" })
      .then((response) => response.ok ? response.json() : { annotations: [] })
      .then((result: { annotations?: GraphNodeNote[] }) => { if (live) setNodeNotes(result.annotations ?? []); })
      .catch(() => { if (live) setNodeNotes([]); });
    return () => { live = false; };
  }, [selectedNodeRef, selectedNodeTakesNotes, notesVersion]);

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

  const expandBundle = (reference: string) => {
    setExpandedBundles((current) => new Set([...current, reference]));
    setHovered(null);
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
      setNodeAnnotationMessage("Note saved. It is analyst context, not evidence.");
      setNotesVersion((current) => current + 1);
    } catch (reason) {
      setNodeAnnotationMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setNodeAnnotationBusy(false);
    }
  };

  const fitToView = () => {
    checkpointPresentation();
    viewportTouched.current = false;
    setViewport(fitViewport(
      Object.fromEntries(Object.entries(positions).filter(([reference]) => visibleIds.has(reference))),
      width,
      height,
    ));
  };

  const updateZoom = (factor: number) => {
    viewportTouched.current = true;
    checkpointPresentation();
    setViewport((current) => {
      const nextScale = Math.max(0.15, Math.min(4, current.scale * factor));
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
      viewportTouched.current = true;
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

  // Visual hierarchy: node area follows degree, so hubs are what the eye meets first.
  const maxDegree = Math.max(1, ...visibleNodes.map((node) => degree.get(node.reference) ?? 0));
  const nodeRadius = (reference: string) => 7 + 19 * Math.sqrt((degree.get(reference) ?? 0) / maxDegree);
  const hubRefs = new Set(
    [...visibleNodes]
      .filter((node) => (degree.get(node.reference) ?? 0) > 1)
      .sort((left, right) => (degree.get(right.reference) ?? 0) - (degree.get(left.reference) ?? 0))
      .slice(0, 8)
      .map((node) => node.reference),
  );
  // Focus is the hovered node, else the selection; its neighbourhood stays bright, the rest dims.
  const focusRefs = new Set<string>();
  for (const reference of hovered ? [hovered] : selectedRefs) {
    focusRefs.add(reference);
    neighbors.get(reference)?.forEach((neighbor) => focusRefs.add(neighbor));
  }
  const coreRefs: Set<string> = hovered ? new Set([hovered]) : selectedSet;
  const focusEdgeCount = visibleEdges.filter((edge) => coreRefs.has(edge.source) || coreRefs.has(edge.target)).length;
  const toScreen = (point: GraphPoint): GraphPoint => ({
    x: point.x * viewport.scale + viewport.x,
    y: point.y * viewport.scale + viewport.y,
  });
  const labelled = (reference: string) => visibleNodes.length <= 16
    || hubRefs.has(reference)
    || focusRefs.has(reference)
    || pinned.has(reference)
    || Boolean(labels[reference])
    || viewport.scale >= 1.6;

  type LabelSide = "right" | "left" | "above" | "below";
  const labelSide = new Map<string, LabelSide>();
  const topHubs = new Set([...hubRefs].slice(0, 3));
  {
    const font = size.font || 12;
    const lineHeight = font * 1.25;
    const obstacles: Array<[number, number, number, number, string]> = [];
    for (const node of visibleNodes) {
      if (!positions[node.reference]) continue;
      const point = toScreen(positions[node.reference]);
      const r = nodeRadius(node.reference);
      obstacles.push([point.x - r, point.x + r, point.y - r, point.y + r, node.reference]);
    }
    const rank = (reference: string) => (selectedSet.has(reference) || reference === hovered ? 0
      : coreRefs.has(reference) ? 1
        : pinned.has(reference) || labels[reference] ? 2
          : focusRefs.has(reference) ? 3 : 4);
    const candidates = visibleNodes
      .filter((node) => positions[node.reference] && labelled(node.reference))
      .sort((left, right) => rank(left.reference) - rank(right.reference)
        || (degree.get(right.reference) ?? 0) - (degree.get(left.reference) ?? 0));
    const placed: Array<[number, number, number, number]> = [];
    const overlaps = (box: [number, number, number, number], self: string) =>
      placed.some((other) => box[0] < other[1] && box[1] > other[0] && box[2] < other[3] && box[3] > other[2])
      || obstacles.some((other) => other[4] !== self
        && box[0] < other[1] && box[1] > other[0] && box[2] < other[3] && box[3] > other[2]);
    for (const node of candidates) {
      const point = toScreen(positions[node.reference]);
      const r = nodeRadius(node.reference);
      const textWidth = (shortLabel(labels[node.reference] || node.label, 44).length + (node.country_code ? 3 : 0)) * font * 0.66 + 6; // bold UI text runs ~0.62em per glyph
      const top = point.y - lineHeight / 2;
      const boxes: Array<[LabelSide, [number, number, number, number]]> = [
        ["right", [point.x + r + 5, point.x + r + 5 + textWidth, top, top + lineHeight]],
        ["left", [point.x - r - 5 - textWidth, point.x - r - 5, top, top + lineHeight]],
        ["above", [point.x - textWidth / 2, point.x + textWidth / 2, point.y - r - 4 - lineHeight, point.y - r - 4]],
        ["below", [point.x - textWidth / 2, point.x + textWidth / 2, point.y + r + 4, point.y + r + 4 + lineHeight]],
      ];
      // The selection, the hovered node and the three largest hubs are always named.
      const mustShow = rank(node.reference) <= 1 || topHubs.has(node.reference);
      // Fallback: overprinting a node is tolerable for a must-show label; overprinting another
      // label is not, except for the selection or hover, which may never disappear.
      const hits = (box: [number, number, number, number], set: Array<[number, number, number, number, ...unknown[]]>) =>
        set.filter((other) => other[4] !== node.reference
          && box[0] < other[1] && box[1] > other[0] && box[2] < other[3] && box[3] > other[2]).length;
      const score = (box: [number, number, number, number]) => hits(box, placed) * 100 + hits(box, obstacles);
      const fallback = boxes.reduce((best, candidate) => score(candidate[1]) < score(best[1]) ? candidate : best);
      const choice = boxes.find(([, box]) => !overlaps(box, node.reference))
        ?? (rank(node.reference) <= 1 || (mustShow && hits(fallback[1], placed) === 0) ? fallback : undefined);
      if (!choice) continue;
      labelSide.set(node.reference, choice[0]);
      placed.push(choice[1]);
    }
  }

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
        <input
          className="graph-filter"
          aria-label="Filter graph nodes by value or type"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Filter nodes…"
        />
        <span className="graph-count">
          {visibleNodes.length} of {intent.data.nodes.length} nodes · {visibleEdges.length} edges
          {hiddenRefs.size > 0 ? ` · ${hiddenRefs.size} collapsed` : ""}
          {graph.bundled.size > 0 ? ` · ${graph.bundled.size} bundled` : ""}
        </span>
        {intent.data.nodes.some((node) => node.entity_type === "analyst-group") && (
          <label className="graph-toggle" title="Analyst promotion groups are your bookkeeping, not adversary evidence">
            <input type="checkbox" checked={showGroups} onChange={(event) => setShowGroups(event.target.checked)} />
            Analyst groups
          </label>
        )}
        {hiddenRefs.size > 0 && (
          <button onClick={() => { checkpointPresentation(); setCollapsedRefs(new Set()); }}>Show all connections</button>
        )}
        {expandedBundles.size > 0 && (
          <button onClick={() => setExpandedBundles(new Set())} title="Draw same-type leaves of each hub as one node again">Bundle leaves</button>
        )}
        {(query || selectedRefs.length > 0 || collapsedRefs.size > 0) && (
          <button onClick={() => {
            if (collapsedRefs.size > 0) checkpointPresentation();
            setQuery("");
            setSelectedRefs([]);
            setCollapsedRefs(new Set());
          }}>Reset</button>
        )}
        <span className="graph-toolbar-end">
          <span className="icon-group" aria-label="Graph presentation history">
            <button className="icon-button" onClick={undoPresentation} disabled={undoStack.length === 0} aria-label="Undo view change" title="Undo view change (⌘Z)"><Icon name="undo" /></button>
            <button className="icon-button" onClick={redoPresentation} disabled={redoStack.length === 0} aria-label="Redo view change" title="Redo view change (⇧⌘Z)"><Icon name="redo" /></button>
          </span>
          <details className="graph-layouts">
            <summary>Layouts{layouts.length ? ` · ${layouts.length}` : ""}</summary>
            <div className="graph-layouts-menu" aria-label="Saved graph layouts">
              <label>
                <span>Open a saved layout</span>
                <select
                  value={layouts.some((layout) => layout.name === layoutName) ? layoutName : ""}
                  onChange={(event) => void loadLayout(event.target.value)}
                  disabled={layoutBusy || layouts.length === 0}
                >
                  <option value="">{layouts.length ? "Choose a layout" : "No saved layouts"}</option>
                  {layouts.map((layout) => <option key={layout.id} value={layout.name}>{layout.name}</option>)}
                </select>
              </label>
              <label>
                <span>Save this arrangement as</span>
                <input
                  value={layoutName}
                  onChange={(event) => setLayoutName(event.target.value)}
                  maxLength={64}
                  placeholder="Layout name"
                />
              </label>
              <div>
                <button onClick={() => void saveLayout()} disabled={layoutBusy || !layoutName.trim()}>Save</button>
                <button
                  onClick={() => void deleteLayout()}
                  disabled={layoutBusy || !layouts.some((layout) => layout.name === layoutName.trim())}
                >
                  Delete
                </button>
              </div>
              <small>Layouts store positions, labels and zoom only. Evidence is never changed.</small>
              {layoutMessage && <small role="status">{layoutMessage}</small>}
            </div>
          </details>
        </span>
      </div>
      <div className={`graph-stage ${selectedRefs.length > 0 || relationCorrection ? "has-inspector" : ""}`} data-viz-fill="" data-viz-reserve="92">
        <div className="graph-canvas" ref={canvasRef}>
      {intent.data.edges.length === 0 ? (
        <section className="unconnected-graph" aria-label="Unconnected stored indicators">
          <b>No relationship edges in scope</b>
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
                <b>{node.label}</b>
                <span>{node.entity_type}</span>
              </button>
            ))}
          </div>
        </section>
      ) : (
        <svg
          ref={svgRef}
          viewBox={`0 0 ${width} ${height}`}
          width={width}
          height={height}
          role="img"
          aria-labelledby={`${intent.intent_id}-graph-title`}
          tabIndex={0}
          onPointerDown={(event) => {
            if (event.target !== event.currentTarget) return;
            viewportTouched.current = true;
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
            viewportTouched.current = true;
            beginPresentationInteraction();
            if (wheelCommitTimer.current !== null) window.clearTimeout(wheelCommitTimer.current);
            const rect = event.currentTarget.getBoundingClientRect();
            const cursorX = ((event.clientX - rect.left) / rect.width) * width;
            const cursorY = ((event.clientY - rect.top) / rect.height) * height;
            const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
            setViewport((current) => {
              const nextScale = Math.max(0.15, Math.min(4, current.scale * factor));
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
        {/* Zoom moves positions only; nodes and labels keep their on-screen size at every zoom. */}
        <g>
          <g className="relationship-edges">
            {visibleEdges.map((edge, index) => {
              if (!positions[edge.source] || !positions[edge.target]) return null;
              const source = toScreen(positions[edge.source]);
              const target = toScreen(positions[edge.target]);
              const touchesFocus = coreRefs.has(edge.source) || coreRefs.has(edge.target);
              return (
                <g key={`${edge.source}-${edge.target}-${index}`} className={focusRefs.size === 0 ? "" : touchesFocus ? "focus" : "dim"}>
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
                  {touchesFocus && focusEdgeCount <= 12 && (
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
              if (!positions[node.reference]) return null;
              const position = toScreen(positions[node.reference]);
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
                    focusRefs.size > 0 && !focusRefs.has(node.reference) ? "dim" : "",
                    node.reference === hovered ? "hovered" : "",
                    `type-${node.entity_type.replaceAll(/[^a-z0-9-]/gi, "-")}`,
                    node.known_category ? `known-${node.known_category}` : "",
                    node.bundle ? "bundle" : "",
                  ].join(" ")}
                  role="button"
                  tabIndex={0}
                  aria-pressed={node.bundle ? undefined : selectedSet.has(node.reference)}
                  aria-label={node.bundle
                    ? `${node.bundle.members.length} ${node.entity_type} leaves of ${graphLabels.get(node.bundle.hub) ?? node.bundle.hub}, bundled; press to expand`
                    : `${labels[node.reference] ?? node.label}, ${node.entity_type}, ${exactDegree.get(node.reference) ?? 0} relationships`}
                  onClick={(event) => node.bundle ? expandBundle(node.reference) : selectNode(
                    node.reference,
                    event.shiftKey || event.metaKey || event.ctrlKey,
                  )}
                  onDoubleClick={() => toggleNeighborhood(node.reference)}
                  onPointerEnter={() => setHovered(node.reference)}
                  onPointerLeave={() => setHovered((current) => current === node.reference ? null : current)}
                  onFocus={() => setHovered(node.reference)}
                  onBlur={() => setHovered((current) => current === node.reference ? null : current)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      if (node.bundle) expandBundle(node.reference);
                      else selectNode(
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
                      // Graph coordinates, not screen: the move handler adds the pointer delta
                      // divided by scale. Storing the screen position here made a dragged node
                      // jump away from the pointer by the current pan offset.
                      originX: positions[node.reference].x,
                      originY: positions[node.reference].y,
                    });
                  }}
                >
                  <circle r={nodeRadius(node.reference)}>
                    <title>{node.bundle ? `${node.bundle.members.length} ${node.entity_type} with one connection each, to ${graphLabels.get(node.bundle.hub) ?? node.bundle.hub}. Click to expand.` : `${node.label} · ${node.entity_type} · ${exactDegree.get(node.reference) ?? 0} relationships`}{node.known_label ? ` · known: ${node.known_label} (list match, not a verdict)` : ""}</title>
                  </circle>
                  {labelSide.has(node.reference) && (
                    <text
                      className="node-label"
                      {...labelPlacement(labelSide.get(node.reference)!, nodeRadius(node.reference), size.font || 12)}
                    >
                      {node.country_code ? `${reportedCountry(node.country_code)?.flag ?? ""} ` : ""}{shortLabel(labels[node.reference] || node.label, 44)}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        </g>
        </svg>
      )}
        {intent.data.edges.length > 0 && (
          <div className="graph-overlay graph-zoom-controls" aria-label="Graph zoom controls">
            <button className="icon-button" onClick={() => updateZoom(1.2)} aria-label="Zoom in" title="Zoom in"><Icon name="plus" /></button>
            <button className="icon-button" onClick={() => updateZoom(1 / 1.2)} aria-label="Zoom out" title="Zoom out"><Icon name="minus" /></button>
            <button className="icon-button" onClick={fitToView} aria-label="Fit graph to view" title="Fit graph to view"><Icon name="fit" /></button>
          </div>
        )}
        <div className="graph-overlay graph-legend">
          {visibleEdges.some((edge) => edge.basis === "explicit") && <span><i className="explicit" /> Stored relationship</span>}
          {visibleEdges.some((edge) => edge.basis === "property") && <span><i className="property" /> Property pivot</span>}
          {visibleEdges.some((edge) => edge.basis === "manual") && <span><i className="manual" /> Analyst assertion or group</span>}
          {visibleEdges.some((edge) => edge.basis === "bundle") && <span><i className="bundle" /> Bundled leaves (click to expand)</span>}
          {[...new Set(visibleNodes.map((node) => node.entity_type))].map((type) => (
            <span key={type}><b className={`swatch type-${type.replaceAll(/[^a-z0-9-]/gi, "-")}`} /> {type}</span>
          ))}
          <details>
            <summary aria-label="Graph controls help">?</summary>
            <p>Click a node to inspect it; Shift, Command or Control adds to the selection. Drag nodes or the background, and scroll to zoom. Double-click a node to collapse or expand its direct connections. Five or more same-type nodes whose only connection is the same hub draw as one bundle; click it to expand. Up to 48 nodes are drawn: hubs first, then each indicator type in turn. Everything here changes presentation only.</p>
          </details>
        </div>
        </div>
        {(selectedRefs.length > 0 || relationCorrection) && (
          <aside className="graph-inspector" aria-label="Selected nodes">
        {selectedNode && (
          <section className="graph-inspector-node" aria-live="polite">
            <header>
              <div>
                <b title={selectedNode.label}>{labels[selectedNode.reference] || selectedNode.label}</b>
                <span>{selectedNode.entity_type} · {exactDegree.get(selectedNode.reference) ?? 0} relationships</span>
              </div>
              <button className="icon-button" onClick={() => setSelectedRefs([])} aria-label="Clear selection" title="Clear selection (Esc)"><Icon name="close" /></button>
            </header>
            <div className="graph-inspector-actions">
              {onOpenEvidence && selectedNode.evidence !== false && (
                <button className="primary" onClick={(event) => onOpenEvidence(selectedNode.reference, event.currentTarget)}>
                  Open evidence
                </button>
              )}
              {selectedNode.evidence === false && (
                <p className="graph-inspector-hint">Analyst bookkeeping, not evidence. Open a member node for its evidence.</p>
              )}
              <button aria-pressed={pinned.has(selectedNode.reference)} onClick={() => {
                checkpointPresentation();
                setPinned((current) => {
                  const next = new Set(current);
                  if (next.has(selectedNode.reference)) next.delete(selectedNode.reference);
                  else next.add(selectedNode.reference);
                  return next;
                });
              }}>
                {pinned.has(selectedNode.reference) ? "Unpin" : "Pin"}
              </button>
              {(degree.get(selectedNode.reference) ?? 0) > 0 && (
                <button onClick={() => toggleNeighborhood(selectedNode.reference)}>
                  {collapsedRefs.has(selectedNode.reference) ? "Expand connections" : "Collapse connections"}
                </button>
              )}
            </div>
            {selectedNodeTakesNotes && (
            <section className="graph-node-notes" aria-label="Analyst notes on this node">
              <h4>Analyst notes{nodeNotes.length ? ` · ${nodeNotes.length}` : ""}</h4>
              {nodeNotes.length ? (
                <ol>
                  {nodeNotes.map((note) => (
                    <li key={note.id}><p>{note.content}</p><time>{note.created_at.slice(0, 16)}</time></li>
                  ))}
                </ol>
              ) : <small>No notes on this node yet.</small>}
              <form onSubmit={(event) => { event.preventDefault(); void saveNodeAnnotation(); }}>
                <label>
                  <span className="sr-only">New analyst note</span>
                  <textarea
                    value={nodeAnnotation}
                    maxLength={4000}
                    rows={3}
                    onChange={(event) => setNodeAnnotation(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                        event.preventDefault();
                        void saveNodeAnnotation();
                      }
                    }}
                    placeholder="Add a note: why this node matters (⌘↵ saves)"
                  />
                </label>
                <button disabled={nodeAnnotationBusy || !nodeAnnotation.trim()}>Save note</button>
                {nodeAnnotationMessage && <small role="status">{nodeAnnotationMessage}</small>}
              </form>
            </section>
            )}
            <details className="graph-display-label">
              <summary>Rename on this graph</summary>
              <label>
                <span>Display label (this graph only; the indicator is unchanged)</span>
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
            </details>
          </section>
        )}
      {selectedRefs.length > 1 && (
        <div className="graph-multiselect" aria-live="polite">
          <b>{selectedRefs.length} nodes selected</b>
          <span>Selection is temporary presentation state and is never saved as evidence or a relationship.</span>
          <button onClick={() => {
            checkpointPresentation();
            setPinned((current) => new Set([...current, ...selectedRefs]));
          }}>
            Pin selected
          </button>
          <button onClick={() => {
            checkpointPresentation();
            setPinned((current) => {
              const next = new Set(current);
              selectedRefs.forEach((reference) => next.delete(reference));
              return next;
            });
          }}>
            UNPin selected
          </button>
          <button onClick={() => setSelectedRefs([])}>Clear selection</button>
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
              ? "Revise analyst relation"
              : "Annotated analyst relation"}
          </b>
          <span>
            {selectedNodes[0].label} → {selectedNodes[1].label}
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
            {relationCorrection?.mode === "revise" ? "Save revision" : "Record judgment"}
          </button>
          {relationCorrection && (
            <button type="button" onClick={() => setRelationCorrection(null)}>Cancel</button>
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
          <b>Retract analyst relation</b>
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
          <button disabled={relationBusy || !relationAnnotation.trim()}>Confirm retraction</button>
          <button type="button" onClick={() => setRelationCorrection(null)}>Cancel</button>
          <small>The assertion is withdrawn from the active graph, never deleted from its audit history.</small>
          {relationMessage && <small role="status">{relationMessage}</small>}
        </form>
      )}
          </aside>
        )}
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
                  <button onClick={() => beginRelationCorrection("revise", edge)}>Revise</button>
                  <button onClick={() => beginRelationCorrection("retract", edge)}>Retract</button>
                </div>
              </article>
            ))}
          </div>
        </details>
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
                  <td>{exactDegree.get(node.reference) ?? 0}</td>
                  <td>{graph.bundled.has(node.reference) ? "Bundled" : hiddenRefs.has(node.reference) ? "Collapsed" : "Visible"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

/** The three views analysts open most; every other view stays one select away. */
const PRIMARY_VIEWS: ReadonlyArray<readonly [string, string]> = [
  ["relationship-graph", "Graph"],
  ["indicator-constellation", "Coverage"],
  ["pivot-trail", "Provenance"],
];

/**
 * Size each element marked ``data-viz-fill`` so the visualization fills the rest of the
 * window (less ``data-viz-reserve`` px for what follows it), instead of a fixed-height box.
 * Recomputed on resize and whenever the workspace's own layout changes.
 */
function useFillHeight(root: RefObject<HTMLElement | null>, key: string) {
  useLayoutEffect(() => {
    const host = root.current;
    if (!host) return;
    let frame = 0;
    const apply = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        host.querySelectorAll<HTMLElement>("[data-viz-fill]").forEach((element) => {
          const fixed = Boolean(element.closest(".pane-maximized"));
          const top = element.getBoundingClientRect().top + (fixed ? 0 : window.scrollY);
          const reserve = Number(element.dataset.vizReserve ?? 48);
          let height = window.innerHeight - top - reserve;
          if (height < 420) height = Math.max(420, Math.round(window.innerHeight * 0.72));
          const cap = Number(element.dataset.vizMax ?? 0);
          if (cap) height = Math.min(height, cap);
          const value = `${Math.round(height)}px`;
          if (element.style.height !== value) element.style.height = value;
        });
      });
    };
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(host);
    window.addEventListener("resize", apply);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("resize", apply);
    };
  }, [root, key]);
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

  const workspaceRef = useRef<HTMLElement>(null);
  useFillHeight(workspaceRef, selected?.intent_id ?? "");
  // Views with data first, in server order; empty views sink to the end of the list.
  const orderedIntents = [...intents].sort(
    (left, right) => Number(right.source_scope.record_count > 0) - Number(left.source_scope.record_count > 0),
  );

  if (!selected) return <div className="visualization-empty">Visualization intents unavailable.</div>;
  let validationError = "";
  try {
    validateVisualizationIntent(selected);
  } catch (reason) {
    validationError = reason instanceof Error ? reason.message : String(reason);
  }
  // A sparse dossier radar is drawn, and explained, as a coverage list (#38).
  const facetList = !validationError && selected.view === "radar" && !radarHasShape(selected);

  return (
    <section ref={workspaceRef} className="visualization-workspace" aria-label="Visual analysis">
      <header className="viz-bar">
        <nav className="viz-tabs" aria-label="Primary views">
          {PRIMARY_VIEWS.map(([id, label]) => {
            const intent = intents.find((item) => item.intent_id === id);
            return intent && (
              <button key={id} aria-pressed={selected.intent_id === id} onClick={() => setSelectedId(id)}>
                {label}<small>{intent.source_scope.record_count}</small>
              </button>
            );
          })}
        </nav>
        <label className="viz-more">
          <span className="sr-only">All evidence views</span>
          <select value={selected.intent_id} onChange={(event) => setSelectedId(event.target.value)}>
            {orderedIntents.map((intent) => (
              <option key={intent.intent_id} value={intent.intent_id}>
                {intent.title} · {intent.source_scope.record_count ? intent.source_scope.record_count : "no data"}
              </option>
            ))}
          </select>
        </label>
        <button className="viz-export" onClick={() => downloadIntent(selected)} title="Download this view's exact data">Export</button>
      </header>
      <div className="viz-question">
        <h3>{selected.question_text}</h3>
        <p>
          {selected.source_scope.record_count} records
          {selected.source_scope.timezone ? ` · ${selected.source_scope.timezone}` : ""}
          <span> · {selected.source_scope.description}</span>
        </p>
        <details className="visualization-explainer-toggle">
          <summary>How to read this {facetList ? "coverage list" : VISUALIZATION_VIEW_LABELS[selected.view].toLowerCase()}</summary>
          <aside className="visualization-explainer" aria-label="Why Pivotglass selected this visualization">
            {facetList
              ? <>
                <p><strong>Why this fits</strong> Fewer than three facets have evidence, so a radar would have no shape to compare.</p>
                <p><strong>How to read it</strong> One bar per facet: some evidence fills half, coverage met fills it all, a dashed outline has none. Bar length is not a confidence score.</p>
              </>
              : <>
                <p><strong>Why this fits</strong> {selected.selection_rationale}</p>
                <p><strong>How to read it</strong> {selected.reading_guide}</p>
              </>}
          </aside>
        </details>
      </div>
      {validationError
        ? <div className="visualization-error">Rejected intent: {validationError}</div>
        : selected.renderer === "flint_chartjs"
          ? facetList
            ? <FacetBars intent={selected} />
            : <FlintCanvas intent={selected} theme={theme} />
          : selected.view === "calendar_heatmap"
            ? <CalendarHeatmap intent={selected} />
            : selected.view === "timeline"
              ? <PivotTrail intent={selected} />
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
