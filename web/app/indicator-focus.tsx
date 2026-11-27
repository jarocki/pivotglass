"use client";

/*
 * Indicator focus mode (#12): indicator list on the left, the rendered source
 * on the right, the focused indicator highlighted, and details on demand (#15)
 * in a translucent hover card. Tagging (#16) is one keystroke away.
 *
 * Source rendering obeys DEC-DOC-RENDER-001: HTML and Markdown arrive already
 * sanitized and are shown in an iframe sandbox *without* allow-scripts; PDF is
 * drawn by pdf.js 6 (no eval code path; document JavaScript and XFA are never
 * enabled because the scripting sandbox is not loaded). Plain formats render from parser text,
 * so their highlights use exact offsets.
 */

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  filterIndicators, groupIndicators, groupMentions, indexTags, locateInSegments, occurrenceOrdinal,
  parseTagInput, type DocumentRelations, type FocusCandidate, type FocusIndicator, type IndicatorContext,
  type Tag, type TagDimension,
  canSetAside, clipboardText, hexGroups,
} from "./focus-model";

export type FocusRendering = { kind: "text" | "html" | "pdf"; anchoring: "exact" | "ordinal"; html: string | null; notes: string[] };

export type FocusSource = {
  id: string;
  filename: string;
  mediaType: string;
  outputText: string;
  rendering: FocusRendering;
  candidates: FocusCandidate[];
  relations: DocumentRelations;
  warnings: string[];
  occurrenceId?: string;
  stored: boolean;
  loadPdf?: () => Promise<ArrayBuffer>;
};

type Hover = { key: string; x: number; y: number; pinned: boolean };
type ViewMode = "rendered" | "text";

const EMPTY_CONTEXT: IndicatorContext = { entity: null, relationships: [], observed_by: [], documents: [], tags: [], investigated_at: null, known: [] };

export function IndicatorFocus({
  source, workspace, admittedKeys, busy, status, onClose, onAdmit, onStore, onInvestigate,
}: {
  source: FocusSource;
  workspace: string;
  admittedKeys: Set<string>;
  busy: boolean;
  status: string;
  onClose: () => void;
  onAdmit: (selectionKeys: string[]) => Promise<void>;
  onStore?: () => Promise<void>;
  onInvestigate?: (value: string) => void;
}) {
  const indicators = useMemo(() => groupMentions(source.candidates), [source.candidates]);
  const [dimensions, setDimensions] = useState<TagDimension[]>([]);
  const [context, setContext] = useState<Record<string, IndicatorContext>>({});
  const [contextError, setContextError] = useState("");
  const [filter, setFilter] = useState("");
  const [grouping, setGrouping] = useState("source");
  const [focusKey, setFocusKey] = useState<string | null>(indicators[0]?.key ?? null);
  const [mention, setMention] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [hover, setHover] = useState<Hover | null>(null);
  const [palette, setPalette] = useState(false);
  const [view, setView] = useState<ViewMode>(source.rendering.kind === "text" ? "text" : "rendered");
  const [located, setLocated] = useState<Record<string, boolean>>({});
  const [tagError, setTagError] = useState("");
  const [copyNotice, setCopyNotice] = useState("");
  const [exportOpen, setExportOpen] = useState(false);
  useEffect(() => { if (!copyNotice) return; const timer = window.setTimeout(() => setCopyNotice(""), 2400); return () => window.clearTimeout(timer); }, [copyNotice]);
  const rootRef = useRef<HTMLDivElement>(null);
  const filterRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLOListElement>(null);

  const tags = useMemo(() => indexTags(Object.values(context).flatMap((item) => item.tags)), [context]);
  const visible = useMemo(() => filterIndicators(indicators, filter, tags), [indicators, filter, tags]);
  const groups = useMemo(() => groupIndicators(visible, grouping, tags, dimensions), [visible, grouping, tags, dimensions]);
  // Navigation order is display order; an indicator in several groups is visited once.
  const order = useMemo(() => [...new Map(groups.flatMap((group) => group.items).map((item) => [item.key, item])).values()], [groups]);
  const byKey = useMemo(() => new Map(indicators.map((item) => [item.key, item])), [indicators]);
  const focused = focusKey ? byKey.get(focusKey) ?? null : null;
  const focusMention = focused ? focused.mentions[Math.min(mention, focused.mentions.length - 1)] : null;

  const requestContext = useCallback(async (items: FocusIndicator[]) => {
    if (!items.length) return;
    try {
      const response = await fetch("/api/indicators/context", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_workspace: workspace, occurrence_id: source.occurrenceId ?? null,
          indicators: items.map((item) => ({ entity_type: item.entityType, normalized_value: item.value })) }),
      });
      const result = await response.json() as { context?: Record<string, IndicatorContext>; error?: string };
      if (!response.ok || !result.context) throw new Error(result.error ?? "Indicator context is unavailable.");
      setContext((current) => ({ ...current, ...result.context }));
      setContextError("");
    } catch (reason) {
      setContextError(reason instanceof Error ? reason.message : "Indicator context is unavailable.");
    }
  }, [workspace, source.occurrenceId]);

  useEffect(() => { void requestContext(indicators); }, [indicators, requestContext]);
  useEffect(() => {
    void fetch("/api/tags/dimensions", { cache: "no-store" }).then((response) => response.json())
      .then((result: { dimensions?: TagDimension[] }) => setDimensions(result.dimensions ?? [])).catch(() => setDimensions([]));
  }, []);
  // Refresh entity state once admission has created workspace entities.
  useEffect(() => { if (admittedKeys.size) void requestContext(indicators); }, [admittedKeys, indicators, requestContext]);

  const move = useCallback((delta: number) => {
    if (!order.length) return;
    const at = Math.max(0, order.findIndex((item) => item.key === focusKey));
    const next = order[(at + delta + order.length) % order.length];
    setFocusKey(next.key); setMention(0); setHover(null);
  }, [order, focusKey]);

  const targets = useCallback(() => selected.size ? [...selected] : focusKey ? [focusKey] : [], [selected, focusKey]);

  const applyTags = useCallback(async (changes: Array<{ key: string; dimension: string; value: string; action: "add" | "remove"; note?: string }>) => {
    if (!changes.length) return;
    setTagError("");
    try {
      const response = await fetch("/api/tags", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_workspace: workspace, operator: "local analyst", changes: changes.map((change) => {
          const item = byKey.get(change.key)!;
          return { entity_type: item.entityType, normalized_value: item.value, dimension: change.dimension, value: change.value, action: change.action, note: change.note };
        }) }),
      });
      const result = await response.json() as { tags?: Tag[]; error?: string };
      if (!response.ok || !result.tags) throw new Error(result.error ?? "Tags were not saved.");
      const touched = new Set(changes.map((change) => change.key));
      setContext((current) => {
        const next = { ...current };
        for (const key of touched) next[key] = { ...(next[key] ?? EMPTY_CONTEXT), tags: result.tags!.filter((tag) => `${tag.entity_type}|${tag.normalized_value}` === key) };
        return next;
      });
    } catch (reason) {
      setTagError(reason instanceof Error ? reason.message : "Tags were not saved.");
    }
  }, [workspace, byKey]);

  const setAsideKeys = useMemo(() => indicators.filter((item) => canSetAside(context[item.key])).map((item) => item.key), [indicators, context]);
  /** Tag known-good and scanner indicators role:benign, noting which list matched. */
  const setAside = useCallback((keys: string[]) => applyTags(keys.map((key) => {
    const match = context[key]?.known?.[0];
    return { key, dimension: "role", value: "benign", action: "add" as const, note: match ? `Set aside: ${match.label} (${match.source})` : undefined };
  })), [applyTags, context]);

  const admit = useCallback(async () => {
    const keys = targets().flatMap((key) => byKey.get(key)?.mentions.map((item) => item.selection_key) ?? []);
    if (keys.length) { await onAdmit(keys); setSelected(new Set()); }
  }, [targets, byKey, onAdmit]);

  /** c copies the current value; y copies the selection (or current) defanged, Y refanged. */
  const copy = useCallback(async (scope: "current" | "selection", defanged: boolean) => {
    const keys = scope === "current" ? (focusKey ? [focusKey] : []) : targets();
    const items = keys.map((key) => byKey.get(key)).filter((item): item is FocusIndicator => Boolean(item));
    if (!items.length) return;
    try {
      await navigator.clipboard.writeText(clipboardText(items, defanged));
      setCopyNotice(items.length === 1 ? `Copied ${defanged ? "defanged " : ""}${items[0]!.value}` : `Copied ${items.length} indicators${defanged ? ", defanged" : ""}`);
    } catch { setCopyNotice("Clipboard is not available in this browser context."); }
  }, [focusKey, targets, byKey]);

  /** e exports the filtered set (what the list shows) as CSV or STIX (#33). */
  const exportSet = useCallback(async (format: "csv" | "stix", defanged: boolean) => {
    setExportOpen(false);
    rootRef.current?.focus();
    if (!order.length) return;
    try {
      const response = await fetch("/api/indicators/export", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_workspace: workspace, occurrence_id: source.occurrenceId ?? null, format, defanged,
          source_label: source.filename, indicators: order.map((item) => ({ entity_type: item.entityType, normalized_value: item.value })) }),
      });
      const result = await response.json() as { text?: string; media_type?: string; extension?: string; count?: number; skipped?: string[]; error?: string };
      if (!response.ok || result.text === undefined) throw new Error(result.error ?? "Export failed.");
      const url = URL.createObjectURL(new Blob([result.text], { type: result.media_type }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `${source.filename.replace(/\.[^.]+$/, "").replace(/[^\w.-]+/g, "_") || "indicators"}-indicators.${result.extension}`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      const skipped = result.skipped?.length ? `; ${result.skipped.length} without a STIX form left out` : "";
      setCopyNotice(`Exported ${result.count} indicators as ${format === "csv" ? `CSV${defanged ? ", defanged" : ""}` : "STIX 2.1"}${skipped}`);
    } catch (reason) {
      setCopyNotice(reason instanceof Error ? reason.message : "Export failed.");
    }
  }, [order, workspace, source.occurrenceId, source.filename]);

  const onKeyDown = (event: React.KeyboardEvent) => {
    const typing = (event.target as HTMLElement).closest("input,textarea,select");
    if (event.key === "Escape") {
      event.preventDefault();
      if (palette) setPalette(false);
      else if (exportOpen) { setExportOpen(false); rootRef.current?.focus(); }
      else if (typing) (event.target as HTMLElement).blur();
      else if (hover?.pinned) setHover(null);
      else onClose();
      return;
    }
    if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
    const key = event.key;
    const handled = (() => {
      if (key === "j" || key === "ArrowDown") move(1);
      else if (key === "k" || key === "ArrowUp") move(-1);
      else if (key === "n" && focused) setMention((value) => (value + 1) % focused.mentions.length);
      else if (key === "p" && focused) setMention((value) => (value - 1 + focused.mentions.length) % focused.mentions.length);
      else if (key === " " && focusKey) setSelected((current) => { const next = new Set(current); if (next.has(focusKey)) next.delete(focusKey); else next.add(focusKey); return next; });
      else if (key === "a") void admit();
      else if (key === "c") void copy("current", false);
      else if (key === "y") void copy("selection", true);
      else if (key === "Y") void copy("selection", false);
      else if (key === "t") setPalette(true);
      else if (key === "e") setExportOpen(true);
      else if (key === "i" && focusKey) setHover((current) => current?.pinned ? null : { key: focusKey, ...anchorPoint(listRef.current, focusKey), pinned: true });
      else if (key === "/") filterRef.current?.focus();
      else if (key === "g") setGrouping((current) => { const options = ["source", "type", ...dimensions.map((item) => item.name)]; return options[(options.indexOf(current) + 1) % options.length]; });
      else if (key === "v" && source.rendering.kind !== "text") setView((current) => current === "text" ? "rendered" : "text");
      else if (key === "Enter" && focused && onInvestigate) onInvestigate(focused.value);
      else return false;
      return true;
    })();
    if (handled) event.preventDefault();
  };

  useLayoutEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-key="${CSS.escape(focusKey ?? "")}"]`)?.scrollIntoView({ block: "nearest" });
  }, [focusKey, grouping]);

  const onSourceHover = useCallback((key: string | null, x = 0, y = 0) => {
    setHover((current) => current?.pinned ? current : key ? { key, x, y, pinned: false } : null);
  }, []);
  const onSourcePick = useCallback((key: string) => { setFocusKey(key); setMention(0); }, []);

  const notLocated = view === "rendered" && source.rendering.anchoring === "ordinal" && focusMention && located[focusMention.selection_key] === false;
  const selectionCount = selected.size;
  const admittedCount = indicators.filter((item) => item.mentions.some((m) => admittedKeys.has(m.selection_key) || m.state === "admitted")).length;

  // Portal into <main>: theme tokens still apply, but the view escapes the
  // intake section's stacking context so no cockpit layer can sit above it.
  const [host, setHost] = useState<HTMLElement | null>(null);
  useEffect(() => { setHost(document.querySelector("main")); }, []);
  useEffect(() => { if (host) rootRef.current?.focus(); }, [host]);
  if (!host) return null;

  return createPortal(<div ref={rootRef} className="indicator-focus" role="dialog" aria-modal="true" aria-label={`Indicator focus: ${source.filename}`} tabIndex={-1} onKeyDown={onKeyDown}>
    <header className="focus-bar">
      <b title={source.filename}>{source.filename}</b>
      <span>{indicators.length} indicators · {source.candidates.length} mentions · {admittedCount} in workspace{source.stored ? "" : " · not stored"}</span>
      <label><span className="sr-only">Group by</span><select value={grouping} onChange={(event) => setGrouping(event.target.value)} aria-label="Group indicators by">
        <option value="source">Source order</option><option value="type">Type</option>
        {dimensions.map((item) => <option key={item.name} value={item.name}>{item.label}</option>)}
      </select></label>
      {source.rendering.kind !== "text" && <div className="segmented" role="group" aria-label="Source view">
        <button className={view === "rendered" ? "selected" : ""} onClick={() => setView("rendered")}>Rendered</button>
        <button className={view === "text" ? "selected" : ""} onClick={() => setView("text")}>Text</button>
      </div>}
      {!source.stored && onStore && <button disabled={busy} onClick={() => void onStore()}>Store source</button>}
      {setAsideKeys.length > 0 && <button title="Tag public resolvers, revocation servers, empty-file hashes, research scanners and similar list matches as Benign / noise. Shared cloud and CDN space is not included." onClick={() => void setAside(setAsideKeys)}>Set aside {setAsideKeys.length} known</button>}
      <button className="primary" disabled={busy || (!selectionCount && !focusKey)} onClick={() => void admit()}>
        {busy ? "Saving…" : selectionCount ? `Admit ${selectionCount}` : "Admit current"}
      </button>
      <span className="focus-export">
        <button aria-expanded={exportOpen} aria-haspopup="menu" disabled={!order.length} title="Export the filtered list (e)" onClick={() => setExportOpen((current) => !current)}>Export {order.length}</button>
        {exportOpen && <span className="focus-export-menu" role="menu" aria-label={`Export ${order.length} filtered indicators`}>
          <button role="menuitem" autoFocus onClick={() => void exportSet("csv", true)}>CSV, defanged</button>
          <button role="menuitem" onClick={() => void exportSet("csv", false)}>CSV, live values</button>
          <button role="menuitem" onClick={() => void exportSet("stix", false)} title="STIX values are never defanged">STIX 2.1 bundle</button>
        </span>}
      </span>
      <button aria-label="Close focus mode" onClick={onClose}>✕</button>
    </header>
    {(status || contextError || tagError || copyNotice) && <p className="focus-notice" role="status">{[copyNotice, status, contextError, tagError].filter(Boolean).join(" · ")}</p>}
    <div className="focus-body">
      <section className="focus-list" aria-label="Indicators">
        <input ref={filterRef} value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Filter — value, type, role:c2, tactic:…" aria-label="Filter indicators" />
        {palette && focusKey && <TagPalette dimensions={dimensions} count={targets().length} onClose={() => { setPalette(false); rootRef.current?.focus(); }}
          onApply={(dimension, value) => { void applyTags(targets().map((key) => ({ key, dimension, value, action: "add" }))); setPalette(false); rootRef.current?.focus(); }} />}
        <ol ref={listRef}>
          {groups.map((group) => <li key={group.id} className="focus-group">
            {group.label && <h3>{group.label} <small>{group.items.length}</small></h3>}
            <ol>{group.items.map((item) => <IndicatorRow key={item.key} item={item} focused={item.key === focusKey} selected={selected.has(item.key)}
              admitted={item.mentions.some((m) => admittedKeys.has(m.selection_key) || m.state === "admitted")}
              context={context[item.key]} relations={source.relations[item.key]}
              onFocus={() => { setFocusKey(item.key); setMention(0); }}
              onToggle={() => setSelected((current) => { const next = new Set(current); if (next.has(item.key)) next.delete(item.key); else next.add(item.key); return next; })}
              onHover={(x, y) => setHover((current) => current?.pinned ? current : { key: item.key, x, y, pinned: false })}
              onLeave={() => setHover((current) => current?.pinned ? current : null)}
              onRemoveTag={(tag) => void applyTags([{ key: item.key, dimension: tag.dimension, value: tag.value, action: "remove" }])} />)}</ol>
          </li>)}
          {!order.length && <li className="focus-empty">{indicators.length ? "No indicators match this filter." : "No indicators were found in this source."}</li>}
        </ol>
        <p className="focus-keys" aria-label="Keyboard shortcuts"><span><kbd>j</kbd><kbd>k</kbd> move</span><span><kbd>n</kbd><kbd>p</kbd> mention</span><span><kbd>space</kbd> select</span><span><kbd>a</kbd> admit</span><span><kbd>c</kbd> copy</span><span><kbd>y</kbd> copy list</span><span><kbd>e</kbd> export</span><span><kbd>t</kbd> tag</span><span><kbd>i</kbd> details</span><span><kbd>g</kbd> group</span><span><kbd>/</kbd> filter</span><span><kbd>↵</kbd> investigate</span><span><kbd>esc</kbd> close</span></p>
      </section>
      <section className="focus-source" aria-label={`Source: ${source.filename}`}>
        {focused && <div className="focus-source-head">
          <IndicatorValue value={focused.value}/>
          <span>mention {Math.min(mention, focused.mentions.length - 1) + 1} of {focused.mentions.length} · line {focusMention?.start_line}</span>
          {notLocated && <button onClick={() => setView("text")}>Not located in this layout — show in text</button>}
        </div>}
        {(source.rendering.notes.length > 0 || source.warnings.length > 0) && <details className="focus-notes"><summary>{source.rendering.notes.length + source.warnings.length} rendering note(s)</summary>
          {[...source.rendering.notes, ...source.warnings].map((note) => <p key={note}>{note}</p>)}</details>}
        {view === "text" || source.rendering.kind === "text"
          ? <TextSource text={source.outputText} candidates={source.candidates} focus={focusMention} onHover={onSourceHover} onPick={onSourcePick} />
          : source.rendering.kind === "html"
            ? <HtmlSource html={source.rendering.html ?? ""} text={source.outputText} candidates={source.candidates} focus={focusMention} onHover={onSourceHover} onPick={onSourcePick} onLocated={setLocated} />
            : <PdfSource load={source.loadPdf} text={source.outputText} candidates={source.candidates} focus={focusMention} onHover={onSourceHover} onPick={onSourcePick} onLocated={setLocated} />}
      </section>
    </div>
    {hover && byKey.get(hover.key) && <HoverCard hover={hover} item={byKey.get(hover.key)!} context={context[hover.key]} relations={source.relations[hover.key]}
      byKey={byKey} dimensions={dimensions} onFocus={(key) => { setFocusKey(key); setMention(0); setHover(null); }}
      onInvestigate={onInvestigate} onClose={() => setHover(null)} />}
  </div>, host);
}

/** Long digests read in groups of 8; the spans keep a copy byte-identical. */
function IndicatorValue({ value }: { value: string }) {
  const groups = hexGroups(value);
  return <code className="indicator-value" title={value}>{groups ? groups.map((group, index) => <span key={index} className="hex-group">{group}</span>) : value}</code>;
}

function anchorPoint(list: HTMLElement | null, key: string) {
  const rect = list?.querySelector<HTMLElement>(`[data-key="${CSS.escape(key)}"]`)?.getBoundingClientRect();
  return rect ? { x: rect.right + 8, y: rect.top } : { x: 360, y: 120 };
}

function IndicatorRow({ item, focused, selected, admitted, context, relations, onFocus, onToggle, onHover, onLeave, onRemoveTag }: {
  item: FocusIndicator; focused: boolean; selected: boolean; admitted: boolean;
  context?: IndicatorContext; relations?: DocumentRelations[string];
  onFocus: () => void; onToggle: () => void; onHover: (x: number, y: number) => void; onLeave: () => void; onRemoveTag: (tag: Tag) => void;
}) {
  const known = context?.entity ? 1 : 0;
  const elsewhere = context?.documents.length ?? 0;
  const linked = (context?.relationships.length ?? 0) + (relations?.structural.length ?? 0);
  return <li data-key={item.key} className={`focus-row ${focused ? "focused" : ""} ${selected ? "selected" : ""}`}
    onClick={onFocus} onMouseEnter={(event) => { const rect = event.currentTarget.getBoundingClientRect(); onHover(rect.right + 8, rect.top); }} onMouseLeave={onLeave}>
    <input type="checkbox" checked={selected} onChange={onToggle} onClick={(event) => event.stopPropagation()} aria-label={`Select ${item.value}`} tabIndex={-1} />
    <div>
      <IndicatorValue value={item.value}/>
      <span className="focus-row-meta">
        <i>{item.entityType}</i>
        {item.mentions.length > 1 && <i>×{item.mentions.length}</i>}
        {admitted && <i className="admitted" title="Admitted to this workspace">✓ in case</i>}
        {!admitted && known > 0 && <i className="known" title="Already a workspace entity">known</i>}
        {context?.known?.[0] && <i className={`listed listed-${context.known[0].category}`} title={`${context.known[0].category_label}: ${context.known.map((match) => `${match.label} (${match.source})`).join("; ")}. Context, not a verdict.`}>{context.known[0].label}</i>}
        {elsewhere > 0 && <i className="elsewhere" title="Also mentioned in other stored sources">{elsewhere} other src</i>}
        {linked > 0 && <i className="linked" title="Relationships and structural links">{linked} links</i>}
      </span>
      {(context?.tags.length ?? 0) > 0 && <span className="focus-tags">{context!.tags.map((tag) =>
        <button key={`${tag.dimension}:${tag.value}`} className={`tag tag-${tag.dimension}`} title={`${tag.dimension}: ${tag.value} — click to remove`}
          onClick={(event) => { event.stopPropagation(); onRemoveTag(tag); }}>{tag.dimension === "tactic" || tag.dimension === "status" ? tag.value : `${tag.dimension}:${tag.value}`}</button>)}</span>}
    </div>
  </li>;
}

function TagPalette({ dimensions, count, onApply, onClose }: { dimensions: TagDimension[]; count: number; onApply: (dimension: string, value: string) => void; onClose: () => void }) {
  const [input, setInput] = useState("");
  const [active, setActive] = useState(0);
  const query = input.trim().toLocaleLowerCase();
  const options = dimensions.flatMap((dimension) => dimension.values.map((item) => ({ dimension: dimension.name, dimensionLabel: dimension.label, ...item })))
    .filter((option) => !query || `${option.dimension}:${option.value} ${option.label}`.toLocaleLowerCase().includes(query.replace(/^\w+:/, (match) => match)));
  // Exact value matches first, so Enter applies what was typed.
  options.sort((a, b) => Number(b.value === query) - Number(a.value === query));
  const parsed = parseTagInput(input, dimensions);
  const free = !parsed && query.includes(":") ? parseTagInput(query, dimensions) : null;
  const choices = [...(parsed && !options.some((o) => o.dimension === parsed.dimension && o.value === parsed.value) ? [{ dimension: parsed.dimension, dimensionLabel: parsed.dimension, value: parsed.value, label: parsed.value }] : []), ...options].slice(0, 12);
  return <div className="tag-palette" role="dialog" aria-label="Tag indicators">
    <input autoFocus value={input} placeholder={`Tag ${count} indicator${count === 1 ? "" : "s"} — c2, tactic:…, cluster:name`}
      onChange={(event) => { setInput(event.target.value); setActive(0); }}
      onKeyDown={(event) => {
        if (event.key === "ArrowDown") { event.preventDefault(); setActive((value) => Math.min(value + 1, choices.length - 1)); }
        else if (event.key === "ArrowUp") { event.preventDefault(); setActive((value) => Math.max(value - 1, 0)); }
        else if (event.key === "Enter") { event.preventDefault(); const choice = choices[active] ?? free; if (choice) onApply(choice.dimension, choice.value); }
        else if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); onClose(); }
      }} aria-label="Tag value" />
    <ol>{choices.map((choice, index) => <li key={`${choice.dimension}:${choice.value}`} className={index === active ? "active" : ""}
      onMouseDown={(event) => { event.preventDefault(); onApply(choice.dimension, choice.value); }}>
      <b>{choice.label}</b><small>{choice.dimensionLabel}</small></li>)}
      {!choices.length && <li className="hint">Type <code>cluster:name</code> or <code>role:name</code> to create a new value.</li>}</ol>
  </div>;
}

/* ---------- source views ---------- */

type SourceProps = {
  text: string;
  candidates: FocusCandidate[];
  focus: FocusCandidate | null;
  onHover: (key: string | null, x?: number, y?: number) => void;
  onPick: (key: string) => void;
};

const keyOf = (candidate: FocusCandidate) => `${candidate.entity_type.startsWith("file-hash-") ? "file" : candidate.entity_type}|${candidate.normalized_value}`;

/** Exact-offset rendering of parser text with nested highlights (a domain inside a URL). */
function TextSource({ text, candidates, focus, onHover, onPick }: SourceProps) {
  const ref = useRef<HTMLPreElement>(null);
  const content = useMemo(() => {
    // The extractor records one mention per value; mark later repeats too so the
    // analyst can hover any occurrence. Repeats carry no mention identity.
    const taken = candidates.map((item) => [item.start_char, item.end_char]);
    const repeats: FocusCandidate[] = [];
    for (const item of new Map(candidates.map((c) => [c.raw_value, c])).values()) {
      for (let at = text.indexOf(item.raw_value); at >= 0 && item.raw_value; at = text.indexOf(item.raw_value, at + item.raw_value.length)) {
        const end = at + item.raw_value.length;
        if (taken.some(([start, stop]) => at === start && end === stop)) continue;
        repeats.push({ ...item, selection_key: `repeat:${at}`, start_char: at, end_char: end });
      }
    }
    const sorted = [...candidates, ...repeats].sort((a, b) => a.start_char - b.start_char || b.end_char - a.end_char);
    const build = (from: number, to: number, items: FocusCandidate[]): ReactNode[] => {
      const out: ReactNode[] = [];
      let cursor = from;
      for (let index = 0; index < items.length; index += 1) {
        const item = items[index];
        if (item.start_char < cursor || item.end_char > to) continue; // partial overlap: reachable from the list
        const inner: FocusCandidate[] = [];
        while (index + 1 < items.length && items[index + 1].start_char < item.end_char) inner.push(items[++index]);
        out.push(text.slice(cursor, item.start_char));
        out.push(<mark key={item.selection_key} data-key={keyOf(item)} data-mention={item.selection_key.startsWith("repeat:") ? undefined : item.selection_key}>{build(item.start_char, item.end_char, inner)}</mark>);
        cursor = item.end_char;
      }
      out.push(text.slice(cursor, to));
      return out;
    };
    return build(0, text.length, sorted);
  }, [text, candidates]);
  useMarkFocus(ref.current, focus);
  return <pre ref={ref} className="focus-text" onMouseOver={(event) => markHover(event, onHover)} onMouseOut={(event) => { if (!(event.relatedTarget as HTMLElement | null)?.closest?.("mark")) onHover(null); }}
    onClick={(event) => { const mark = (event.target as HTMLElement).closest("mark"); if (mark?.getAttribute("data-key")) onPick(mark.getAttribute("data-key")!); }}>{content}</pre>;
}

function markHover(event: React.MouseEvent, onHover: SourceProps["onHover"]) {
  const mark = (event.target as HTMLElement).closest("mark");
  const key = mark?.getAttribute("data-key");
  if (!mark || !key) return;
  const rect = mark.getBoundingClientRect();
  onHover(key, rect.left, rect.bottom + 6);
}

/** Highlight and scroll to the focused mention inside any container (document or iframe). */
function useMarkFocus(root: ParentNode | null | undefined, focus: FocusCandidate | null, version = 0) {
  useEffect(() => {
    if (!root) return;
    root.querySelectorAll("mark.focused").forEach((node) => node.classList.remove("focused"));
    root.querySelectorAll("mark.focused-indicator").forEach((node) => node.classList.remove("focused-indicator"));
    if (!focus) return;
    root.querySelectorAll(`mark[data-key="${CSS.escape(keyOf(focus))}"]`).forEach((node) => node.classList.add("focused-indicator"));
    const pieces = root.querySelectorAll<HTMLElement>(`mark[data-mention="${CSS.escape(focus.selection_key)}"]`);
    pieces.forEach((node) => node.classList.add("focused"));
    pieces[0]?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [root, focus, version]);
}

/** Wrap located mentions in <mark> elements across the text nodes of ``root``. */
function anchorMentions(root: HTMLElement, text: string, candidates: FocusCandidate[]): Record<string, boolean> {
  const doc = root.ownerDocument;
  const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) nodes.push(node as Text);
  const segments = nodes.map((node) => node.data);
  const claims = new Map<number, Array<{ start: number; end: number; candidate: FocusCandidate }>>();
  const located: Record<string, boolean> = {};
  // Longer values first so a URL claims its span before the domain inside it.
  for (const candidate of [...candidates].sort((a, b) => b.raw_value.length - a.raw_value.length)) {
    const ordinal = occurrenceOrdinal(text, candidate.raw_value, candidate.start_char);
    const pieces = locateInSegments(segments, candidate.raw_value, ordinal);
    const free = pieces?.every((piece) => !(claims.get(piece.segment) ?? []).some((claim) => piece.start < claim.end && claim.start < piece.end));
    located[candidate.selection_key] = Boolean(pieces && free);
    if (!pieces || !free) continue;
    for (const piece of pieces) claims.set(piece.segment, [...(claims.get(piece.segment) ?? []), { start: piece.start, end: piece.end, candidate }]);
  }
  const byRaw = new Map(candidates.map((candidate) => [candidate.raw_value, candidate]));
  for (const candidate of [...byRaw.values()].sort((a, b) => b.raw_value.length - a.raw_value.length)) {
    for (let ordinal = 0; ordinal < 500; ordinal += 1) {
      const pieces = locateInSegments(segments, candidate.raw_value, ordinal);
      if (!pieces) break;
      const free = pieces.every((piece) => !(claims.get(piece.segment) ?? []).some((claim) => piece.start < claim.end && claim.start < piece.end));
      if (!free) continue;
      const repeat = { ...candidate, selection_key: "" };
      for (const piece of pieces) claims.set(piece.segment, [...(claims.get(piece.segment) ?? []), { start: piece.start, end: piece.end, candidate: repeat }]);
    }
  }
  for (const [segment, items] of claims) {
    let node = nodes[segment];
    for (const claim of [...items].sort((a, b) => b.start - a.start)) {
      const tail = node.splitText(claim.start);
      tail.splitText(claim.end - claim.start);
      const mark = doc.createElement("mark");
      mark.setAttribute("data-key", keyOf(claim.candidate));
      if (claim.candidate.selection_key) mark.setAttribute("data-mention", claim.candidate.selection_key);
      tail.parentNode!.replaceChild(mark, tail);
      mark.appendChild(tail);
      node = nodes[segment];
    }
  }
  return located;
}

function themeCss(root: HTMLElement | null): string {
  const style = root ? getComputedStyle(root) : null;
  const read = (name: string, fallback: string) => style?.getPropertyValue(name).trim() || fallback;
  // The frame cannot inherit the cockpit's rem scale, so pass the analyst's
  // text size in: standard (14px root) reads at 16px in the source.
  const rootPx = parseFloat(getComputedStyle(document.documentElement).fontSize) || 14;
  return `:root{--frame-size:${Math.round(rootPx * 16 / 14)}px;--ink:${read("--ink", "#f3f7f8")};--dim:${read("--dim", "#a6b5bd")};--base:${read("--base", "#071116")};--line:${read("--line", "#49c6d6")};--accent:${read("--accent", "#65d98b")};--focus:${read("--focus-ring", "#ffd166")}}`;
}

const FRAME_CSS = `html,body{margin:0;background:var(--base);color:var(--ink);font:var(--frame-size,15px)/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
body{padding:18px 24px;max-width:min(100%,110ch)}a,.pg-link{color:var(--line);text-decoration:underline dotted}
table{border-collapse:collapse}td,th{border:1px solid color-mix(in srgb,var(--line) 30%,transparent);padding:3px 6px}
pre,code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;word-break:break-word}
.pg-title{font-weight:700;color:var(--dim);margin-bottom:8px}
.pg-media::before{content:"[" attr(data-label) "]";color:var(--dim);font-size:12px}
mark{background:color-mix(in srgb,var(--line) 22%,transparent);color:inherit;border-radius:2px;cursor:pointer}
mark.focused-indicator{background:color-mix(in srgb,var(--accent) 30%,transparent)}
mark.focused{background:var(--focus);color:#000;box-shadow:0 0 0 2px var(--focus)}`;

function HtmlSource({ html, text, candidates, focus, onHover, onPick, onLocated }: SourceProps & { html: string; onLocated: (value: Record<string, boolean>) => void }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [body, setBody] = useState<HTMLElement | null>(null);
  const [version, setVersion] = useState(0);
  const srcDoc = useMemo(() => `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><style>${themeCss(frame.current?.closest("main") ?? null)}${FRAME_CSS}</style></head><body>${html}</body></html>`, [html]);
  const onLoad = () => {
    const doc = frame.current?.contentDocument;
    if (!doc?.body) return;
    onLocated(anchorMentions(doc.body, text, candidates));
    const offset = () => frame.current!.getBoundingClientRect();
    doc.addEventListener("mouseover", (event) => {
      const mark = (event.target as HTMLElement).closest?.("mark");
      const key = mark?.getAttribute("data-key");
      if (!mark || !key) return;
      const rect = mark.getBoundingClientRect(); const base = offset();
      onHover(key, base.left + rect.left, base.top + rect.bottom + 6);
    });
    doc.addEventListener("mouseout", (event) => { if (!(event.relatedTarget as HTMLElement | null)?.closest?.("mark")) onHover(null); });
    doc.addEventListener("click", (event) => { const key = (event.target as HTMLElement).closest?.("mark")?.getAttribute("data-key"); if (key) onPick(key); });
    // Keep focus-mode shortcuts working after a click inside the frame.
    doc.addEventListener("keydown", (event) => { frame.current?.closest<HTMLElement>(".indicator-focus")?.dispatchEvent(new KeyboardEvent("keydown", event)); });
    setBody(doc.body); setVersion((value) => value + 1);
  };
  useMarkFocus(body, focus, version);
  // No allow-scripts: sanitized markup cannot run code even if the sanitizer missed something.
  return <iframe ref={frame} className="focus-frame" title="Rendered source" sandbox="allow-same-origin" srcDoc={srcDoc} onLoad={onLoad} />;
}

// Text-layer geometry copied from pdfjs-dist 6.4.299 web/pdf_viewer.css so the
// invisible text spans line up with canvas glyphs; marks then land on the
// right characters. Update together with the pdfjs-dist pin.
const PDF_CSS = `.pdf-page{position:relative;margin:0 auto 14px;box-shadow:0 4px 18px #0006}.pdf-page canvas{display:block}
.textLayer{position:absolute;text-align:initial;inset:0;overflow:clip;opacity:1;line-height:1;letter-spacing:normal;word-spacing:normal;text-size-adjust:none;forced-color-adjust:none;transform-origin:0 0;z-index:0;
--min-font-size:1;--text-scale-factor:calc(var(--total-scale-factor) * var(--min-font-size));--min-font-size-inv:calc(1 / var(--min-font-size))}
.textLayer :is(span,br){color:transparent;position:absolute;white-space:pre;cursor:text;transform-origin:0% 0%}
.textLayer > :not(.markedContent),.textLayer .markedContent span:not(.markedContent){z-index:1;--font-height:0;font-size:calc(var(--text-scale-factor) * var(--font-height));--scale-x:1;--rotate:0deg;transform:rotate(var(--rotate)) scaleX(var(--scale-x)) scale(var(--min-font-size-inv))}
.textLayer .markedContent{display:contents}
.textLayer mark{color:transparent;margin:-1px;padding:1px;border-radius:3px;background:color-mix(in srgb,var(--line) 35%,transparent);cursor:pointer}
.textLayer mark.focused-indicator{background:color-mix(in srgb,var(--accent) 45%,transparent)}
.textLayer mark.focused{background:color-mix(in srgb,var(--focus-ring,#ffd166) 70%,transparent);outline:2px solid var(--focus-ring,#ffd166)}`;

function PdfSource({ load, text, candidates, focus, onHover, onPick, onLocated }: SourceProps & { load?: () => Promise<ArrayBuffer>; onLocated: (value: Record<string, boolean>) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let cancelled = false;
    const container = ref.current;
    if (!container || !load) { setState("error"); setMessage("PDF bytes are unavailable for page rendering."); return; }
    (async () => {
      const pdfjs = await import("pdfjs-dist");
      pdfjs.GlobalWorkerOptions.workerSrc = "/vendor/pdf.worker.min.mjs";
      const data = new Uint8Array(await load());
      const doc = await pdfjs.getDocument({ data, enableXfa: false, stopAtErrors: false }).promise;
      const width = Math.max(320, container.clientWidth - 32);
      const limit = Math.min(doc.numPages, 200);
      for (let number = 1; number <= limit && !cancelled; number += 1) {
        const page = await doc.getPage(number);
        const scale = width / page.getViewport({ scale: 1 }).width;
        const viewport = page.getViewport({ scale });
        const wrapper = document.createElement("div");
        wrapper.className = "pdf-page"; wrapper.style.width = `${viewport.width}px`; wrapper.style.height = `${viewport.height}px`;
        const canvas = document.createElement("canvas");
        const ratio = window.devicePixelRatio || 1;
        canvas.width = Math.floor(viewport.width * ratio); canvas.height = Math.floor(viewport.height * ratio);
        canvas.style.width = `${viewport.width}px`; canvas.style.height = `${viewport.height}px`;
        const layer = document.createElement("div");
        layer.className = "textLayer";
        layer.style.setProperty("--scale-factor", String(scale));
        layer.style.setProperty("--total-scale-factor", String(scale));
        wrapper.append(canvas, layer);
        container.append(wrapper);
        await page.render({ canvas, canvasContext: canvas.getContext("2d")!, viewport, transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0] }).promise;
        await new pdfjs.TextLayer({ textContentSource: page.streamTextContent(), container: layer, viewport }).render();
      }
      if (cancelled) return;
      onLocated(anchorMentions(container, text, candidates));
      setState("ready"); setVersion((value) => value + 1);
      if (doc.numPages > limit) setMessage(`Showing the first ${limit} of ${doc.numPages} pages.`);
    })().catch((reason) => { if (!cancelled) { setState("error"); setMessage(reason instanceof Error ? reason.message : "The PDF could not be drawn."); } });
    return () => { cancelled = true; container.replaceChildren(); };
  }, [load, text, candidates, onLocated]);
  useMarkFocus(state === "ready" ? ref.current : null, focus, version);
  return <div className="focus-pdf">
    <style>{PDF_CSS}</style>
    {state !== "ready" && <p className="focus-notice">{state === "loading" ? "Drawing pages…" : `${message} Use Text view for exact locations.`}</p>}
    {state === "ready" && message && <p className="focus-notice">{message}</p>}
    <div ref={ref} onMouseOver={(event) => markHover(event, onHover)} onMouseOut={(event) => { if (!(event.relatedTarget as HTMLElement | null)?.closest?.("mark")) onHover(null); }}
      onClick={(event) => { const key = (event.target as HTMLElement).closest("mark")?.getAttribute("data-key"); if (key) onPick(key); }} />
  </div>;
}

/* ---------- details on demand ---------- */

function HoverCard({ hover, item, context, relations, byKey, dimensions, onFocus, onInvestigate, onClose }: {
  hover: Hover; item: FocusIndicator; context?: IndicatorContext; relations?: DocumentRelations[string];
  byKey: Map<string, FocusIndicator>; dimensions: TagDimension[];
  onFocus: (key: string) => void; onInvestigate?: (value: string) => void; onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: hover.x, top: hover.y });
  useLayoutEffect(() => {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    const left = Math.max(8, Math.min(hover.x, window.innerWidth - rect.width - 8));
    const top = hover.y + rect.height > window.innerHeight - 8 ? Math.max(8, hover.y - rect.height - 28) : hover.y;
    setPosition({ left, top });
  }, [hover.x, hover.y, context, relations]);
  const label = (key: string) => byKey.get(key)?.value ?? key.split("|").slice(1).join("|");
  const peers = (items: Array<{ key: string; relation?: string }>) => items.map((peer) =>
    <li key={`${peer.key}${peer.relation ?? ""}`}><button onClick={() => onFocus(peer.key)}>{peer.relation && <em>{peer.relation}</em>}<code>{label(peer.key)}</code></button></li>);
  const ctx = context;
  const dimensionLabel = (name: string) => dimensions.find((item) => item.name === name)?.label ?? name;
  const empty = !ctx?.known?.length && !ctx?.entity && !ctx?.relationships.length && !ctx?.observed_by.length && !ctx?.documents.length && !ctx?.tags.length
    && !relations?.structural.length && !relations?.same_line.length && !relations?.same_paragraph.length;
  return <div ref={ref} className={`hover-card ${hover.pinned ? "pinned" : ""}`} role="tooltip" style={position}>
    <header><code>{item.value}</code><span>{item.entityType}{item.mentions.length > 1 ? ` · ${item.mentions.length} mentions here (n/p)` : ""}</span>
      {hover.pinned && <button aria-label="Close details" onClick={onClose}>✕</button>}</header>
    {ctx === undefined && <p className="dim">Loading what the workspace knows…</p>}
    {ctx?.known?.length ? <section className="known-section"><h4>Known <small>list match, not a verdict</small></h4><ul>{ctx.known.map((match) => <li key={match.list_id + match.category}><em className={`listed listed-${match.category}`}>{match.category_label}</em><span>{match.label}</span><small>{match.source}</small></li>)}</ul></section> : null}
    {ctx?.tags.length ? <section><h4>Analyst tags</h4><p>{ctx.tags.map((tag) => <span key={`${tag.dimension}${tag.value}`} className={`tag tag-${tag.dimension}`} title={`${dimensionLabel(tag.dimension)} · ${tag.created_by ?? ""}${tag.note ? ` · ${tag.note}` : ""}`}>{tag.value}</span>)}</p></section> : null}
    {ctx && <section><h4>Workspace</h4>
      <p>{ctx.entity ? "Entity in this case" : "Not in this case yet"}{ctx.investigated_at ? ` · investigated ${new Date(ctx.investigated_at).toLocaleString()}` : ""}</p>
      {ctx.relationships.length > 0 && <ul>{ctx.relationships.map((rel, index) => <li key={index}><em>{rel.direction === "out" ? rel.relationship_type : `← ${rel.relationship_type}`}</em><code>{rel.other_label}</code><small>{rel.other_type}</small></li>)}</ul>}
      {ctx.observed_by.length > 0 && <p className="dim">Observed by {ctx.observed_by.map((obs) => `${obs.source}${obs.count > 1 ? ` ×${obs.count}` : ""}`).join(", ")}</p>}
    </section>}
    {ctx?.documents.length ? <section><h4>Other sources</h4><ul>{ctx.documents.map((doc) => <li key={doc.occurrence_id}><code>{doc.filename}</code><small>{doc.copies > 1 ? `stored ${doc.copies}×` : ""}{doc.admitted ? `${doc.copies > 1 ? " · " : ""}admitted` : ""}</small></li>)}</ul></section> : null}
    {relations?.structural.length ? <section><h4>Derived from the value</h4><ul>{peers(relations.structural)}</ul></section> : null}
    {relations?.same_line.length || relations?.same_paragraph.length ? <section><h4>Nearby in this source <small>position only</small></h4>
      {relations.same_line.length > 0 && <><h5>Same line</h5><ul className="peer-list">{peers(relations.same_line)}</ul></>}
      {relations.same_paragraph.length > 0 && <><h5>Same paragraph</h5><ul className="peer-list">{peers(relations.same_paragraph)}</ul></>}</section> : null}
    {ctx && empty && <p className="dim">Nothing known yet beyond this mention.</p>}
    {hover.pinned && <footer>
      <button onClick={() => void navigator.clipboard?.writeText(item.value)}>Copy</button>
      {onInvestigate && <button onClick={() => onInvestigate(item.value)}>Investigate</button>}
    </footer>}
  </div>;
}
