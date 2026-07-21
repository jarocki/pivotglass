"use client";

import { CSSProperties, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Chart, registerables } from "chart.js";
import { assembleChartjs } from "flint-chart";

Chart.register(...registerables);

type Briefing = { source: string; artifacts: string; purpose: string; watch_for: string };
type FeedEvent = { kind: "probe" | "evidence"; tool: string; source: string; briefing?: Briefing; summary?: string };
type Theme = { border_color: string; accent_color: string; heading_color: string; text_color: string; dim_color: string };
type Cockpit = { deck_name: string; vehicle: string; hud_title: string; left_rail: string; right_rail: string };
type Mode = { name: string; personality: string; greeting: string; pursuit_title: string; theme: Theme; cockpit: Cockpit };
type DossierSlot = { name: string; status: "empty" | "partial" | "filled" | "deferred"; evidence_count: number };
type State = { workspace: string; stats: Record<string, number>; objects: Array<{ type?: string; value?: string }>; briefings: Record<string, Briefing>; character: string; modes: Mode[]; dossier_slots: DossierSlot[] };

const paneIds = ["intelligence", "dossier", "artifact-field", "systems"] as const;

function Meter({ label, value, detail, warning = false }: { label: string; value: number; detail: string; warning?: boolean }) {
  return <div className={`meter ${warning ? "warning" : ""}`}><div><span>{label}</span><b>{detail}</b></div><div className="meter-track"><i style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div></div>;
}

function DistributionChart({ objects, theme }: { objects: State["objects"]; theme: Theme }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const counts = useMemo(() => {
    const result = new Map<string, number>();
    for (const object of objects) result.set(object.type ?? "unknown", (result.get(object.type ?? "unknown") ?? 0) + 1);
    return [...result].map(([type, count]) => ({ type, count }));
  }, [objects]);

  useEffect(() => {
    if (!canvas.current || counts.length === 0) return;
    const config = assembleChartjs({ data: { values: counts }, semantic_types: { type: "Category", count: "Quantity" }, chart_spec: { chartType: "Bar Chart", encodings: { x: { field: "type" }, y: { field: "count" } }, baseSize: { width: 620, height: 240 } } });
    const themed = config as typeof config & { options?: Record<string, unknown> };
    themed.options = { ...themed.options, color: theme.text_color, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: theme.dim_color }, grid: { color: `${theme.border_color}33` } }, y: { ticks: { color: theme.dim_color }, grid: { color: `${theme.border_color}33` } } } };
    for (const dataset of (themed.data as { datasets?: Array<Record<string, unknown>> }).datasets ?? []) { dataset.backgroundColor = `${theme.accent_color}55`; dataset.borderColor = theme.accent_color; dataset.borderWidth = 1; }
    const chart = new Chart(canvas.current, themed as never);
    return () => chart.destroy();
  }, [counts, theme]);
  return counts.length === 0 ? <div className="empty-chart">NO ARTIFACTS IN VIEW</div> : <canvas ref={canvas} aria-label="Artifact type distribution compiled by Flint" />;
}

export default function Cockpit() {
  const [state, setState] = useState<State | null>(null);
  const [feed, setFeed] = useState<FeedEvent[]>([]);
  const [target, setTarget] = useState("");
  const [active, setActive] = useState(false);
  const [error, setError] = useState("");
  const [help, setHelp] = useState(false);
  const [menu, setMenu] = useState(false);
  const feedRef = useRef<HTMLDivElement>(null);

  const refresh = async () => { const response = await fetch("/api/state", { cache: "no-store" }); setState(await response.json()); };
  useEffect(() => { refresh().catch((reason) => setError(String(reason))); }, []);
  useEffect(() => { const key = (event: KeyboardEvent) => { if (event.key === "?") setHelp((value) => !value); if (event.key === "Escape") { setHelp(false); setMenu(false); } }; window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key); }, []);

  const mode = state?.modes.find((item) => item.name === state.character) ?? state?.modes[0];
  const theme = mode?.theme ?? { border_color: "#00d7d7", accent_color: "#00d700", heading_color: "#00d7d7", text_color: "#ffffff", dim_color: "#5f5f5f" };
  const style = { "--line": theme.border_color, "--accent": theme.accent_color, "--heading": theme.heading_color, "--ink": theme.text_color, "--dim": theme.dim_color } as CSSProperties;
  const dossier = state?.dossier_slots.filter((slot) => slot.status === "filled").length ?? 0;
  const dossierProgress = state?.dossier_slots.filter((slot) => slot.status === "filled" || slot.status === "partial").length ?? 0;
  const availableSources = Object.keys(state?.briefings ?? {}).length;

  async function switchMode(name: string) {
    const response = await fetch("/api/mode", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
    const result = await response.json();
    if (!response.ok) { setError(result.error ?? "Mode switch failed"); return; }
    setState(result); setMenu(false);
  }

  async function investigate(event: FormEvent) {
    event.preventDefault(); const value = target.trim(); if (!value || !state) return;
    setError(""); setActive(true);
    try {
      const planResponse = await fetch(`/api/plan?target=${encodeURIComponent(value)}`, { cache: "no-store" });
      const plan = await planResponse.json(); if (!planResponse.ok) throw new Error(plan.error ?? "Unable to plan investigation");
      setFeed(plan.events); requestAnimationFrame(() => feedRef.current?.scrollTo({ top: 0, behavior: "smooth" }));
      const response = await fetch("/api/investigate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ target: value }) });
      const result = await response.json(); if (!response.ok) throw new Error(result.error ?? "Investigation failed");
      setFeed(result.events); await refresh(); requestAnimationFrame(() => feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: "smooth" }));
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); } finally { setActive(false); }
  }

  function go(id: typeof paneIds[number]) { document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "center" }); }

  return <main style={style} className={`mode-${state?.character ?? "default"}`}>
    <div className="scanline" />
    <header className="masthead">
      <button className="menu-button" onClick={() => setMenu(!menu)} aria-expanded={menu}>☰ <span>DECK</span></button>
      <div className="brand"><span className="eyebrow">{mode?.cockpit.deck_name ?? "HUNT CONTROL"} // LOCAL INTELLIGENCE SYSTEM</span><h1>PIVOTGLASS</h1><small>{mode?.cockpit.vehicle ?? "AP-01 PURSUIT DECK"}</small></div>
      <div className="status-cluster"><span className="lamp ok" /><span className={`lamp ${active ? "hot" : ""}`} /><span className={active ? "system-state pulse" : "system-state"}>{active ? "HUNT ACTIVE" : "SYSTEM READY"}</span><button className="help-button" onClick={() => setHelp(true)}>HELP ?</button></div>
      {menu && <nav className="deck-menu" aria-label="Cockpit navigation">{paneIds.map((id) => <button key={id} onClick={() => { go(id); setMenu(false); }}>{id.replace("-", " ")}</button>)}<hr/><label>CHARACTER VOICE</label>{state?.modes.map((item) => <button className={item.name === state.character ? "selected" : ""} key={item.name} onClick={() => switchMode(item.name)}><b>{item.name.replaceAll("_", " ")}</b><small>{item.personality}</small></button>)}</nav>}
    </header>

    <section className="voice-strip"><b>{state?.character?.replaceAll("_", " ").toUpperCase() ?? "DEFAULT"}</b><span>{mode?.greeting || "Cockpit link established."}</span><i>{mode?.pursuit_title ?? "THE HUNT"}</i></section>

    <section className="command-rail"><form onSubmit={investigate}><span className="prompt">glass://acquire</span><input value={target} onChange={(event) => setTarget(event.target.value)} placeholder="domain, IP, URL, email, or hash" aria-label="Investigation target"/><button disabled={active}>{active ? "TRACKING…" : "ACQUIRE"}</button></form>{error && <div className="error">⚠ FAULT · {error}</div>}</section>

    <section className="telemetry-rack" id="systems">
      <Meter label="REACTOR / LOCAL API" value={100} detail="100%" />
      <Meter label="DOSSIER CELLS" value={(dossierProgress / 9) * 100} detail={`${dossier} FILLED`} warning={dossier >= 8} />
      <Meter label="PROBE BAY" value={Math.min(100, availableSources * 7)} detail={`${availableSources} SOURCES`} />
      <Meter label="TOKEN CORE" value={active ? 35 : 0} detail={active ? "ENGAGED" : "STANDBY"} />
      <div className="damage"><span>HULL / WEAR</span><b className={error ? "danger" : "ok-text"}>{error ? "ALERT" : "NOMINAL"}</b><small>{error ? "RECOVERY CARD ACTIVE" : "NO STRUCTURAL FAULTS"}</small></div>
    </section>

    <section className="cockpit-grid">
      <article className="panel feed-panel" id="intelligence"><div className="panel-title"><span>{mode?.cockpit.left_rail} {mode?.pursuit_title} // INTELLIGENCE</span><small>{feed.length} EVENTS · SCROLL ACTIVE</small></div><div className="feed" ref={feedRef} tabIndex={0} aria-label="Scrollable intelligence feed">
        {feed.length === 0 && <div className="standby"><div className="reticle"><i/><i/><i/></div><b>AWAITING TARGET LOCK</b><span>Evidence, retrieval briefings, and justified pivots will appear here.</span></div>}
        {feed.map((item, index) => <section className={`event ${item.kind}`} key={`${item.tool}-${item.kind}-${index}`}><div className="event-head"><b>{item.kind.toUpperCase()}</b><span>{item.source}</span></div>{item.briefing && <><p><label>GATHER</label>{item.briefing.artifacts}</p><p><label>WHY</label>{item.briefing.purpose}</p><p><label>WATCH</label>{item.briefing.watch_for}</p><small>Retrieval goal—not an observed finding.</small></>}{item.summary && <pre>{item.summary}</pre>}</section>)}
      </div></article>

      <aside className="right-stack">
        <article className="panel instruments" id="dossier"><div className="panel-title"><span>{mode?.cockpit.hud_title ?? "TACTICAL HUD"}</span><small>LIVE</small></div><dl><div><dt>WORKSPACE</dt><dd>{state?.workspace ?? "—"}</dd></div><div><dt>CHARACTER</dt><dd>{state?.character ?? "—"}</dd></div><div><dt>ARTIFACTS</dt><dd>{state?.objects.length ?? 0}</dd></div><div><dt>DOSSIER</dt><dd>{dossier}/9 FILLED</dd></div><div><dt>TRANSPORT</dt><dd>LOOPBACK / VERIFIED</dd></div></dl><div className="dossier-grid" aria-label={`${dossier} of 9 dossier cells filled`}>{(state?.dossier_slots ?? Array.from({length: 9}, (_, index) => ({name: `slot ${index + 1}`, status: "empty" as const, evidence_count: 0}))).map((slot, index) => <i className={slot.status} key={slot.name} title={`${slot.name}: ${slot.status} (${slot.evidence_count} evidence)`}>{index + 1}</i>)}</div></article>
        <article className="panel chart-panel" id="artifact-field"><div className="panel-title"><span>ARTIFACT FIELD</span><small>MICROSOFT FLINT / CHART.JS</small></div><DistributionChart objects={state?.objects ?? []} theme={theme}/></article>
        <article className="panel alert-panel"><div className="panel-title"><span>MASTER CAUTION</span><small>{error ? "1 ALERT" : "CLEAR"}</small></div><p>{error ? error : active ? "Probe activity underway. Retrieval briefings are prospective until evidence arrives." : "All local systems nominal. Token core remains offline until synthesis is requested."}</p></article>
      </aside>
    </section>

    <footer><span>EVIDENCE ≠ INFERENCE</span><span>LOCALHOST · NO TELEMETRY · OPERATOR CONTROLLED</span><span>?</span></footer>
    {help && <div className="modal-backdrop" onMouseDown={() => setHelp(false)}><section className="help-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Operator help"><button className="close" onClick={() => setHelp(false)}>×</button><span className="eyebrow">PIVOTGLASS FIELD MANUAL</span><h2>OPERATOR HELP</h2><div className="help-grid"><div><b>ACQUIRE</b><p>Enter a supported indicator. Pivotglass plans deterministic API probes before gathering evidence.</p></div><div><b>NAVIGATE</b><p>Open DECK to jump between intelligence, dossier, visualization, and system panes.</p></div><div><b>CHARACTER</b><p>Select a voice in DECK. The web cockpit uses the same canonical themes and identities as the TUI.</p></div><div><b>GROUND TRUTH</b><p>PROBE cards teach retrieval intent. EVIDENCE cards report observed tool output. Neither is silently promoted to inference.</p></div></div><small>Press ? to toggle help · Esc to close · Tab to navigate controls</small></section></div>}
  </main>;
}
