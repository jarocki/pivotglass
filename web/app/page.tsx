"use client";

import { CSSProperties, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Chart, registerables } from "chart.js";
import { assembleChartjs } from "flint-chart";
import { FlowMusicEngine } from "./flow-music";

Chart.register(...registerables);

type Briefing = { source: string; artifacts: string; purpose: string; watch_for: string };
type Lifecycle = "planned" | "queued" | "running" | "succeeded" | "empty" | "failed" | "skipped" | "cancelled";
type FeedEvent = { event_id: string; sequence: number; event_class: string; severity: string; lifecycle: Lifecycle; content_class: "evidence" | "narration" | "system"; tool?: string; source?: string; briefing?: Briefing; summary?: string; reason?: string; result_count?: number; artifact_ids?: string[]; actions?: string[] };
type Theme = { border_color: string; accent_color: string; heading_color: string; text_color: string; dim_color: string };
type Cockpit = { deck_name: string; vehicle: string; hud_title: string; left_rail: string; right_rail: string };
type Mode = { name: string; personality: string; greeting: string; pursuit_title: string; theme: Theme; cockpit: Cockpit };
type DossierSlot = { name: string; status: "empty" | "partial" | "filled" | "deferred"; evidence_count: number };
type Instruments = { local_api: { available: boolean; checked_at: string }; sources: { configured: number; queued: number }; model_tokens: { available: boolean; reason: string; used?: number }; active_investigations: number };
type EvidenceCard = { reference: string; stix_id: string; type?: string; value?: string; retrieved_at?: string };
type EvidenceDetail = { reference: string; stix_id: string; type: string; value: string; source_module: string; original_query: string; provenance: Record<string, unknown>; normalized: Record<string, unknown>; raw: Record<string, unknown>; relationships: unknown[]; dossier_contributions: unknown[]; supporting_observations: unknown[]; conflicting_observations: unknown[]; next_pivots: unknown[] };
type State = { workspace: string; stats: Record<string, number>; objects: EvidenceCard[]; briefings: Record<string, Briefing>; character: string; modes: Mode[]; dossier_slots: DossierSlot[]; instruments: Instruments };
type InvestigationSnapshot = { investigation_id: string; lifecycle: Lifecycle; cursor: number; events: FeedEvent[] };
type AlertEvent = FeedEvent & { acknowledged: boolean; investigation_id: string };
type AlertState = { alerts: AlertEvent[]; unread_count: number; highest_unread: string };

const paneIds = ["intelligence", "dossier", "artifact-field", "systems"] as const;
type PaneId = typeof paneIds[number];
type TaskGroup = { key: string; tool: string; events: FeedEvent[]; latest: FeedEvent; artifacts: string[]; interesting: boolean };

function groupTasks(feed: FeedEvent[]): TaskGroup[] {
  const groups = new Map<string, FeedEvent[]>();
  for (const event of feed) {
    if (!event.tool) continue;
    const key = event.tool;
    groups.set(key, [...(groups.get(key) ?? []), event]);
  }
  return [...groups].map(([key, events]) => ({
    key, tool: key, events, latest: events[events.length - 1],
    artifacts: [...new Set(events.flatMap((item) => item.artifact_ids ?? []))],
    interesting: events.some((item) => ["discovery", "contradiction", "source_fault"].includes(item.event_class)),
  }));
}

function PanelTitle({ id, title, status, collapsed, onToggle }: { id: string; title: string; status: string; collapsed: boolean; onToggle: () => void }) {
  return <div className="panel-title"><span>{title}</span><span className="panel-actions"><small>{status}</small><button className="collapse-button" onClick={onToggle} aria-expanded={!collapsed} aria-controls={`${id}-content`} title={`${collapsed ? "Expand" : "Collapse"} ${title}`}>{collapsed ? "▸ EXPAND" : "▾ COLLAPSE"}</button></span></div>;
}

function SenseiDojo({ onClose, reduced }: { onClose: () => void; reduced: boolean }) {
  const [position, setPosition] = useState(12); const [opponent, setOpponent] = useState(72); const [score, setScore] = useState(0); const [message, setMessage] = useState("A calm stance defeats a hurried cursor.");
  const strike = () => { const hit = Math.abs(position - opponent) < 22; setMessage(hit ? "Clean form. The log remains mightier than the legend." : "Distance is evidence. Observe before acting."); if (hit) { setScore((value) => value + 1); setOpponent(42 + ((score * 17) % 44)); } };
  return <section className="dojo" role="dialog" aria-modal="true" aria-label="Sensei training diversion" onKeyDown={(event) => { if (event.key === "ArrowRight") setPosition((value) => Math.min(78, value + 8)); if (event.key === "ArrowLeft") setPosition((value) => Math.max(4, value - 8)); if (event.key.toLowerCase() === "z") strike(); }} tabIndex={-1}>
    <button className="close" aria-label="Close training simulator" onClick={onClose}>×</button><span className="eyebrow">OPTIONAL DIVERSION · NO ANALYTICAL MEANING</span><h2>SENSEI // FLOW DOJO</h2>
    <div className={`dojo-stage ${reduced ? "static" : ""}`}><i style={{ left: `${position}%` }}>▟</i><i className="opponent" style={{ left: `${opponent}%` }}>▙</i><b>COMBO {score}</b></div>
    <p aria-live="polite">{message}</p><div className="dojo-controls"><button onClick={() => setPosition((value) => Math.max(4, value - 8))}>← STEP</button><button onClick={strike}>Z · STRIKE</button><button onClick={() => setPosition((value) => Math.min(78, value + 8))}>STEP →</button></div><small>Arrow keys move · Z strikes · Esc exits. This score never affects evidence, confidence, or dossier state.</small>
  </section>;
}

function AmbientEnvironment({ character }: { character: string }) {
  return <div className="ambient-environment" aria-hidden="true">
    <div className="code-rain">{Array.from({ length: 16 }, (_, index) => <i key={index}>{`${(index * 1103515245 + 12345).toString(2)} ﾊﾝﾄ 01`}</i>)}</div>
    <div className="white-rabbit">◢◤</div>
    <div className="sprawl-grid" />
    <div className="pixel-arena"><i className="fighter fighter-a">▟</i><i className="fighter fighter-b">▙</i></div>
    <div className="detective-rain" />
    <div className="computer-lens"><i /></div>
    <div className="theme-sigil">{character.replaceAll("_", " ")}</div>
  </div>;
}

function Meter({ label, value, detail, warning = false }: { label: string; value: number | null; detail: string; warning?: boolean }) {
  return <div className={`meter ${warning ? "warning" : ""} ${value === null ? "unavailable" : ""}`}><div><span>{label}</span><b>{detail}</b></div><div className="meter-track"><i style={{ width: value === null ? "0%" : `${Math.max(0, Math.min(100, value))}%` }} /></div></div>;
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
  return counts.length === 0 ? <div className="empty-chart">NO ARTIFACTS IN VIEW</div> : <><canvas ref={canvas} aria-label="Artifact type distribution compiled by Flint" /><table className="chart-data"><caption>Artifact type distribution</caption><thead><tr><th scope="col">Type</th><th scope="col">Count</th></tr></thead><tbody>{counts.map((item) => <tr key={item.type}><td>{item.type}</td><td>{item.count}</td></tr>)}</tbody></table></>;
}

export default function Cockpit() {
  const [state, setState] = useState<State | null>(null);
  const [feed, setFeed] = useState<FeedEvent[]>([]);
  const [target, setTarget] = useState("");
  const [active, setActive] = useState(false);
  const [error, setError] = useState("");
  const [help, setHelp] = useState(false);
  const [menu, setMenu] = useState(false);
  const [investigationId, setInvestigationId] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [detail, setDetail] = useState<EvidenceDetail | null>(null);
  const [alerts, setAlerts] = useState<AlertState>({ alerts: [], unread_count: 0, highest_unread: "clear" });
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [reviewingHistory, setReviewingHistory] = useState(false);
  const [palette, setPalette] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState("");
  const [effects, setEffects] = useState<"full" | "reduced" | "off">("full");
  const [narration, setNarration] = useState<"full" | "brief" | "off">("full");
  const [music, setMusic] = useState(false);
  const [musicVolume, setMusicVolume] = useState(18);
  const [collapsed, setCollapsed] = useState<Record<PaneId, boolean>>({ intelligence: false, dossier: false, "artifact-field": false, systems: false });
  const [activePane, setActivePane] = useState<PaneId>("intelligence");
  const [expandedTask, setExpandedTask] = useState<string | null>(null);
  const [dojo, setDojo] = useState(false);
  const audioRef = useRef<FlowMusicEngine | null>(null);
  const detailOrigin = useRef<HTMLElement | null>(null);
  const overlayOrigin = useRef<HTMLElement | null>(null);
  const dialogRef = useRef<HTMLElement | null>(null);
  const feedRef = useRef<HTMLDivElement>(null);

  const refresh = async () => { const response = await fetch("/api/state", { cache: "no-store" }); setState(await response.json()); };
  const refreshAlerts = async () => { const response = await fetch("/api/alerts", { cache: "no-store" }); if (response.ok) setAlerts(await response.json()); };
  useEffect(() => { Promise.all([refresh(), refreshAlerts()]).catch((reason) => setError(String(reason))); }, []);
  useEffect(() => { const storedEffects = window.localStorage.getItem("pivotglass.effects"); const storedNarration = window.localStorage.getItem("pivotglass.narration"); const storedMusicVolume = window.localStorage.getItem("pivotglass.music.volume"); const storedPanes = window.localStorage.getItem("pivotglass.panes"); const storedVolume = Number(storedMusicVolume); if (storedEffects === "full" || storedEffects === "reduced" || storedEffects === "off") setEffects(storedEffects); if (storedNarration === "full" || storedNarration === "brief" || storedNarration === "off") setNarration(storedNarration); if (storedMusicVolume !== null && Number.isFinite(storedVolume) && storedVolume >= 0 && storedVolume <= 100) setMusicVolume(storedVolume); if (storedPanes) { try { setCollapsed((current) => ({ ...current, ...JSON.parse(storedPanes) })); } catch { /* ignore invalid local preference */ } } }, []);
  useEffect(() => { audioRef.current?.setVolume(musicVolume); window.localStorage.setItem("pivotglass.music.volume", String(musicVolume)); }, [musicVolume]);
  useEffect(() => { audioRef.current?.setPhase(error ? "caution" : active ? "investigating" : feed.length ? "complete" : "idle"); }, [active, error, feed.length]);
  useEffect(() => () => stopMusic(), []);
  useEffect(() => { if (!active) return; const started = Date.now(); const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000); return () => window.clearInterval(timer); }, [active]);
  useEffect(() => { const key = (event: KeyboardEvent) => { const target = event.target as HTMLElement | null; const editing = !!target && (target.matches("input, textarea, select") || target.isContentEditable); if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); openOverlay("palette"); } else if (event.key === "/" && !editing) { event.preventDefault(); openOverlay("palette"); } else if (event.key === "?" && !editing) { event.preventDefault(); openOverlay("help"); } if (event.key === "Escape") closeOverlays(); }; window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key); });
  useEffect(() => { const restore = () => { if (!window.location.hash.startsWith("#evidence=")) { setDetail(null); requestAnimationFrame(() => detailOrigin.current?.focus()); } const pane = new URL(window.location.href).searchParams.get("pane"); if (pane && paneIds.includes(pane as typeof paneIds[number])) document.getElementById(pane)?.scrollIntoView({ behavior: "auto", block: "center" }); }; restore(); window.addEventListener("popstate", restore); return () => window.removeEventListener("popstate", restore); }, []);
  useEffect(() => { if (!(detail || help || alertsOpen || palette || dojo)) return; const root = dialogRef.current; const focusable = root?.querySelectorAll<HTMLElement>("button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex='-1'])"); (root?.querySelector<HTMLElement>("[data-initial-focus]") ?? focusable?.[0])?.focus(); const trap = (event: KeyboardEvent) => { if (event.key !== "Tab" || !focusable?.length) return; const first = focusable[0]; const last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } }; window.addEventListener("keydown", trap); return () => window.removeEventListener("keydown", trap); }, [detail, help, alertsOpen, palette, dojo]);

  const mode = state?.modes.find((item) => item.name === state.character) ?? state?.modes[0];
  const theme = mode?.theme ?? { border_color: "#00d7d7", accent_color: "#00d700", heading_color: "#00d7d7", text_color: "#ffffff", dim_color: "#5f5f5f" };
  const style = { "--line": theme.border_color, "--accent": theme.accent_color, "--heading": theme.heading_color, "--ink": theme.text_color, "--dim": theme.dim_color } as CSSProperties;
  const dossier = state?.dossier_slots.filter((slot) => slot.status === "filled").length ?? 0;
  const dossierProgress = state?.dossier_slots.filter((slot) => slot.status === "filled" || slot.status === "partial").length ?? 0;
  const configuredSources = state?.instruments.sources.configured ?? 0;
  const taskGroups = useMemo(() => groupTasks(feed), [feed]);

  function closeOverlays() { if (detail) closeDetail(); setPalette(false); setHelp(false); setAlertsOpen(false); setDojo(false); setMenu(false); requestAnimationFrame(() => overlayOrigin.current?.focus()); }
  function openOverlay(kind: "help" | "palette" | "alerts" | "dojo", origin?: HTMLElement) { overlayOrigin.current = origin ?? document.activeElement as HTMLElement; setHelp(kind === "help"); setPalette(kind === "palette"); setAlertsOpen(kind === "alerts"); setDojo(kind === "dojo"); setMenu(false); }
  function togglePane(id: PaneId) { setCollapsed((current) => { const next = { ...current, [id]: !current[id] }; window.localStorage.setItem("pivotglass.panes", JSON.stringify(next)); return next; }); }

  async function switchMode(name: string) {
    if (music) stopMusic();
    const response = await fetch("/api/mode", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
    const result = await response.json();
    if (!response.ok) { setError(result.error ?? "Mode switch failed"); return; }
    setState(result); setMenu(false);
  }

  async function investigate(event: FormEvent) {
    event.preventDefault(); const value = target.trim(); if (!value || !state) return;
    setError(""); setActive(true);
    try {
      const response = await fetch("/api/investigate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ target: value }) });
      const result = await response.json() as InvestigationSnapshot & { error?: string }; if (!response.ok) throw new Error(result.error ?? "Investigation failed");
      setInvestigationId(result.investigation_id); setFeed(result.events); setExpandedTask(null); requestAnimationFrame(() => feedRef.current?.scrollTo({ top: 0, behavior: effects === "full" ? "smooth" : "auto" }));
      let cursor = result.cursor; let lifecycle = result.lifecycle;
      while (!["succeeded", "empty", "failed", "cancelled"].includes(lifecycle)) {
        await new Promise((resolve) => window.setTimeout(resolve, 350));
        const eventResponse = await fetch(`/api/investigations/${result.investigation_id}/events?cursor=${cursor}`, { cache: "no-store" });
        const update = await eventResponse.json() as InvestigationSnapshot & { error?: string }; if (!eventResponse.ok) throw new Error(update.error ?? "Investigation stream failed");
        if (update.events.length) { setFeed((current) => [...current, ...update.events]); await refreshAlerts(); }
        cursor = update.cursor; lifecycle = update.lifecycle;
      }
      await Promise.all([refresh(), refreshAlerts()]); if (!reviewingHistory) requestAnimationFrame(() => feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: effects === "full" ? "smooth" : "auto" }));
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); } finally { setActive(false); setInvestigationId(null); }
  }

  async function cancelInvestigation() {
    if (!investigationId) return;
    const response = await fetch(`/api/investigations/${investigationId}/cancel`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    if (!response.ok) setError("Cancellation could not be acknowledged");
  }

  async function openDetail(identifier: string, origin: HTMLElement) {
    detailOrigin.current = origin;
    const response = await fetch(`/api/evidence/${encodeURIComponent(identifier)}`, { cache: "no-store" });
    const result = await response.json() as EvidenceDetail & { error?: string };
    if (!response.ok) { setError(result.error ?? "Evidence detail unavailable"); return; }
    setHelp(false); setPalette(false); setAlertsOpen(false); setDojo(false);
    setDetail(result); window.history.pushState({ evidence: result.reference }, "", `#evidence=${result.reference}`);
  }

  function closeDetail() {
    setDetail(null);
    if (window.location.hash.startsWith("#evidence=")) window.history.back();
    else requestAnimationFrame(() => detailOrigin.current?.focus());
  }

  async function acknowledge(eventId: string) {
    const response = await fetch(`/api/alerts/${encodeURIComponent(eventId)}/acknowledge`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    if (response.ok) await refreshAlerts();
  }

  function jumpToAlert(alert: AlertEvent) {
    closeOverlays(); setExpandedTask(alert.tool ?? null);
    requestAnimationFrame(() => document.getElementById(`event-${alert.event_id}`)?.scrollIntoView({ behavior: effects === "full" ? "smooth" : "auto", block: "center" }));
  }

  function go(id: PaneId) { setActivePane(id); if (collapsed[id]) togglePane(id); const url = new URL(window.location.href); url.searchParams.set("pane", id); window.history.pushState({ pane: id }, "", url); requestAnimationFrame(() => { const panel = document.getElementById(id); panel?.scrollIntoView({ behavior: effects === "full" ? "smooth" : "auto", block: "center" }); panel?.focus({ preventScroll: true }); }); }

  function setEffectsPreference(value: "full" | "reduced" | "off") { setEffects(value); window.localStorage.setItem("pivotglass.effects", value); }
  function setNarrationPreference(value: "full" | "brief" | "off") { setNarration(value); window.localStorage.setItem("pivotglass.narration", value); }

  function stopMusic() {
    const engine = audioRef.current;
    if (!engine) return;
    void engine.stop();
    audioRef.current = null;
    setMusic(false);
  }

  function startMusic() {
    if (audioRef.current) return;
    const engine = new FlowMusicEngine(state?.character ?? "default", musicVolume);
    engine.setPhase(error ? "caution" : active ? "investigating" : feed.length ? "complete" : "idle"); engine.start(); audioRef.current = engine; setMusic(true);
  }

  function toggleMusic() { if (music) stopMusic(); else startMusic(); }

  const paletteCommands = [
    ...paneIds.map((id) => ({ label: `Go to ${id.replace("-", " ")}`, run: () => go(id) })),
    { label: "Open operator help", run: () => openOverlay("help") },
    { label: "Open Master Caution", run: () => openOverlay("alerts") },
    ...(state?.character === "sensei" ? [{ label: "Open Sensei Flow Dojo", run: () => openOverlay("dojo") }] : []),
    { label: "Mute visual effects", run: () => setEffectsPreference("off") },
    { label: "Reduce visual effects", run: () => setEffectsPreference("reduced") },
    { label: "Enable full visual effects", run: () => setEffectsPreference("full") },
    { label: music ? "Mute generative music" : "Enable generative music", run: toggleMusic },
  ].filter((command) => command.label.toLowerCase().includes(paletteQuery.toLowerCase()));

  return <main style={style} className={`mode-${state?.character ?? "default"} effects-${effects} narration-${narration}`}>
    <AmbientEnvironment character={state?.character ?? "default"} />
    <div className="scanline" />
    <header className="masthead">
      <button className="menu-button" onClick={() => setMenu(!menu)} aria-expanded={menu}>☰ <span>DECK</span></button>
      <div className="brand"><span className="eyebrow">{mode?.cockpit.deck_name ?? "HUNT CONTROL"} // LOCAL INTELLIGENCE SYSTEM</span><h1>PIVOTGLASS</h1><small>{mode?.cockpit.vehicle ?? "AP-01 PURSUIT DECK"}</small></div>
      <div className="status-cluster"><span className="lamp ok" /><span className={`lamp ${active ? "hot" : ""}`} /><span className={active ? "system-state pulse" : "system-state"}>{active ? "HUNT ACTIVE" : "SYSTEM READY"}</span>{reviewingHistory && alerts.unread_count > 0 && <button className="unread-badge" onClick={(event) => openOverlay("alerts", event.currentTarget)}>{alerts.highest_unread.toUpperCase()} · {alerts.unread_count} UNREAD</button>}<button className="help-button" onClick={(event) => openOverlay("help", event.currentTarget)}>HELP ?</button></div>
      {menu && <nav className="deck-menu" aria-label="Cockpit navigation">{paneIds.map((id) => <button key={id} onClick={() => { go(id); setMenu(false); }}>{id.replace("-", " ")}</button>)}<hr/><label>VISUAL EFFECTS</label><div className="segmented">{(["full", "reduced", "off"] as const).map((value) => <button className={effects === value ? "selected" : ""} key={value} onClick={() => setEffectsPreference(value)}>{value}</button>)}</div><label>NARRATION</label><div className="segmented">{(["full", "brief", "off"] as const).map((value) => <button className={narration === value ? "selected" : ""} key={value} onClick={() => setNarrationPreference(value)}>{value}</button>)}</div><label>GENERATIVE MUSIC · OFF BY DEFAULT</label><button className={music ? "selected" : ""} onClick={toggleMusic}>{music ? "MUTE MUSIC" : "ENABLE MUSIC"}</button><input type="range" min="0" max="100" value={musicVolume} onChange={(event) => setMusicVolume(Number(event.target.value))} aria-label="Music volume"/><hr/><label>CHARACTER VOICE</label>{state?.modes.map((item) => <button className={item.name === state.character ? "selected" : ""} key={item.name} onClick={() => switchMode(item.name)}><b>{item.name.replaceAll("_", " ")}</b><small>{item.personality}</small></button>)}</nav>}
    </header>

    <nav className="pane-switcher" aria-label="Primary cockpit panes">{paneIds.map((id) => <button key={id} aria-current={activePane === id ? "page" : undefined} title={`Open and focus ${id.replace("-", " ")} pane`} onClick={() => go(id)}>{id.replace("-", " ")}</button>)}<button title="Search all cockpit commands" onClick={(event) => openOverlay("palette", event.currentTarget)}>COMMANDS ⌘K</button>{state?.character === "sensei" && <button title="Open optional keyboard training diversion" onClick={(event) => openOverlay("dojo", event.currentTarget)}>FLOW DOJO</button>}</nav>

    <section className="voice-strip"><b>{state?.character?.replaceAll("_", " ").toUpperCase() ?? "DEFAULT"}</b><span>{mode?.greeting || "Cockpit link established."}</span><i>{mode?.pursuit_title ?? "THE HUNT"}</i></section>

    <section className="command-rail"><form onSubmit={investigate}><span className="prompt">glass://acquire</span><input value={target} onChange={(event) => setTarget(event.target.value)} placeholder="domain, IP, URL, email, or hash" aria-label="Investigation target"/><button disabled={active}>{active ? `TRACKING ${elapsed}s` : "ACQUIRE"}</button>{active && <button type="button" className="cancel" onClick={cancelInvestigation}>CANCEL</button>}</form>{error && <div className="error">⚠ FAULT · {error}</div>}</section>

    <section className={`telemetry-rack ${collapsed.systems ? "collapsed" : ""}`} id="systems" tabIndex={-1}>
      <button className="telemetry-collapse" onClick={() => togglePane("systems")} aria-expanded={!collapsed.systems} aria-controls="systems-content" title={`${collapsed.systems ? "Expand" : "Collapse"} system telemetry`}>{collapsed.systems ? "▸ SYSTEMS" : "▾ SYSTEMS"}</button>
      <div id="systems-content" className="telemetry-content">
      <Meter label="REACTOR / LOCAL API" value={state?.instruments.local_api.available ? 100 : 0} detail={state?.instruments.local_api.available ? "AVAILABLE" : "UNAVAILABLE"} />
      <Meter label="DOSSIER CELLS" value={(dossierProgress / 9) * 100} detail={`${dossier} FILLED`} warning={dossier >= 8} />
      <Meter label="PROBE BAY" value={null} detail={`${configuredSources} CONFIGURED`} />
      <Meter label="TOKEN CORE" value={state?.instruments.model_tokens.available ? 100 : null} detail={state?.instruments.model_tokens.available ? `${state.instruments.model_tokens.used ?? 0} USED` : "NOT ENGAGED"} />
      <div className="damage"><span>INVESTIGATION STATE</span><b className={error ? "danger" : active ? "caution" : "ok-text"}>{error ? "FAULT" : active ? "RUNNING" : "IDLE"}</b><small>{error ? "SEE MASTER CAUTION" : active ? `${elapsed}s ELAPSED · EVENT STREAM LIVE` : "NO ACTIVE INVESTIGATION"}</small></div></div>
    </section>

    <section className="cockpit-grid">
      <article className={`panel feed-panel ${collapsed.intelligence ? "collapsed" : ""}`} id="intelligence" tabIndex={-1}><PanelTitle id="intelligence" title={`${mode?.cockpit.left_rail} ${mode?.pursuit_title} // INTELLIGENCE`} status={`${taskGroups.length} TASKS · ${feed.length} EVENTS`} collapsed={collapsed.intelligence} onToggle={() => togglePane("intelligence")}/><div id="intelligence-content" className="feed" ref={feedRef} tabIndex={0} aria-label="Scrollable intelligence feed" onScroll={(event) => { const node = event.currentTarget; setReviewingHistory(node.scrollHeight - node.scrollTop - node.clientHeight > 32); }}>
        {feed.length === 0 && <div className="standby"><div className="reticle"><i/><i/><i/></div><b>AWAITING TARGET LOCK</b><span>Evidence, retrieval briefings, and justified pivots will appear here.</span></div>}
        {taskGroups.length > 0 && <><section className="hunt-summary"><b>TASK CONSTELLATION</b><span>{taskGroups.length} deterministic probes · select a pixel for its complete transition history</span></section><div className="task-field" role="list" aria-label={`${taskGroups.length} investigation tasks`}>{taskGroups.map((task) => <button role="listitem" key={task.key} className={`task-pixel state-${task.latest.lifecycle} ${task.interesting ? "interesting" : ""}`} aria-expanded={expandedTask === task.key} aria-controls={`task-${task.key}`} onClick={() => setExpandedTask((current) => current === task.key ? null : task.key)} data-tooltip={`${task.tool} · ${task.latest.lifecycle} · ${task.artifacts.length} evidence · click for full history`} aria-label={`${task.tool}, ${task.latest.lifecycle}, ${task.artifacts.length} evidence. ${expandedTask === task.key ? "Collapse" : "Open"} full history`}><i/><i/><i/><i/><i/><i/><i/><i/><i/><span>{task.latest.lifecycle === "succeeded" ? "✓" : task.latest.lifecycle === "failed" ? "!" : task.latest.lifecycle === "running" ? "…" : "·"}</span></button>)}</div></>}
        {taskGroups.filter((task) => expandedTask === task.key).map((task) => <section className="task-detail" id={`task-${task.key}`} key={task.key}><header><div><b>{task.tool}</b><small>{task.events.length} ordered transitions · {task.artifacts.length} evidence records</small></div><button onClick={() => setExpandedTask(null)}>COLLAPSE</button></header>{task.events.map((item) => <section id={`event-${item.event_id}`} className={`event ${item.content_class} state-${item.lifecycle} class-${item.event_class}`} key={item.event_id}><div className="event-head"><b>{item.lifecycle.toUpperCase()}</b><span>{item.source ?? item.event_class}</span></div><small>{item.tool} · event {item.sequence}</small>{item.briefing && <><p><label>GATHER</label>{item.briefing.artifacts}</p><p><label>WHY</label>{item.briefing.purpose}</p><p><label>WATCH</label>{item.briefing.watch_for}</p><small>Retrieval goal—not an observed finding.</small></>}{item.summary && <pre>{item.summary}</pre>}{item.reason && <p><label>STATE</label>{item.reason}</p>}{item.artifact_ids?.map((id) => <button className="evidence-link" key={id} onClick={(event) => openDetail(id, event.currentTarget)}>OPEN EVIDENCE {id}</button>)}</section>)}</section>)}
      </div></article>

      <aside className="right-stack">
        <article className={`panel instruments ${collapsed.dossier ? "collapsed" : ""}`} id="dossier" tabIndex={-1}><PanelTitle id="dossier" title={mode?.cockpit.hud_title ?? "TACTICAL HUD"} status={`${dossier}/9 CELLS`} collapsed={collapsed.dossier} onToggle={() => togglePane("dossier")}/><div id="dossier-content" className="panel-content"><dl><div><dt>WORKSPACE</dt><dd>{state?.workspace ?? "—"}</dd></div><div><dt>CHARACTER</dt><dd>{state?.character ?? "—"}</dd></div><div><dt>ARTIFACTS</dt><dd>{state?.objects.length ?? 0}</dd></div><div><dt>DOSSIER</dt><dd>{dossier}/9 FILLED</dd></div><div><dt>TRANSPORT</dt><dd>LOOPBACK / VERIFIED</dd></div></dl><div className="dossier-grid" aria-label={`${dossier} of 9 dossier cells filled`}>{(state?.dossier_slots ?? Array.from({length: 9}, (_, index) => ({name: `slot ${index + 1}`, status: "empty" as const, evidence_count: 0}))).map((slot, index) => <button className={slot.status} key={slot.name} data-tooltip={`${slot.name}: ${slot.status}, ${slot.evidence_count} evidence. Click to inspect matching artifacts.`} onClick={() => go("artifact-field")} aria-label={`${slot.name}: ${slot.status}, ${slot.evidence_count} evidence. Open artifact field.`}>{index + 1}</button>)}</div></div></article>
        <article className={`panel chart-panel ${collapsed["artifact-field"] ? "collapsed" : ""}`} id="artifact-field" tabIndex={-1}><PanelTitle id="artifact-field" title="ARTIFACT FIELD" status="FLINT / CHART.JS" collapsed={collapsed["artifact-field"]} onToggle={() => togglePane("artifact-field")}/><div id="artifact-field-content" className="panel-content"><DistributionChart objects={state?.objects ?? []} theme={theme}/><div className="artifact-list">{state?.objects.slice(-5).map((item) => <button title={`Open full evidence record ${item.reference}`} key={item.reference} onClick={(event) => openDetail(item.reference, event.currentTarget)}><b>{item.reference}</b><span>{item.type} · {item.value}</span></button>)}</div></div></article>
        <article className="panel alert-panel"><div className="panel-title"><button title="Open persistent attention records" onClick={(event) => openOverlay("alerts", event.currentTarget)}>MASTER CAUTION</button><small>{error ? "FAULT" : alerts.unread_count ? `${alerts.unread_count} UNREAD · ${alerts.highest_unread.toUpperCase()}` : "CLEAR"}</small></div><p>{error ? error : alerts.unread_count ? "Attention records are waiting. Open Master Caution to inspect and acknowledge them." : active ? "Probe activity underway. Retrieval briefings are prospective until evidence arrives." : "No unacknowledged attention records."}</p></article>
      </aside>
    </section>

    <footer><span>EVIDENCE ≠ INFERENCE</span><span>LOCALHOST · NO TELEMETRY · OPERATOR CONTROLLED</span><button title="Open contextual operator help" onClick={(event) => openOverlay("help", event.currentTarget)}>HELP ?</button></footer>
    {help && <div className="modal-backdrop" onMouseDown={closeOverlays}><section ref={dialogRef} className="help-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="help-heading"><button className="close" aria-label="Close help" onClick={closeOverlays}>×</button><span className="eyebrow">PIVOTGLASS FIELD MANUAL · {activePane.replace("-", " ").toUpperCase()}</span><h2 id="help-heading" tabIndex={-1}>WHAT DO YOU WANT TO DO?</h2><div className="help-tasks"><button onClick={() => { closeOverlays(); document.querySelector<HTMLInputElement>('[aria-label="Investigation target"]')?.focus(); }}><b>START A HUNT</b><span>Focus the target field. Enter a domain, IP, URL, email, or hash, then choose ACQUIRE.</span><kbd>RETURN</kbd></button><button onClick={() => { closeOverlays(); go("intelligence"); }}><b>REVIEW PROBES</b><span>Select a 3×3 task pixel to open its ordered transitions and evidence links.</span><kbd>CLICK / ENTER</kbd></button><button onClick={() => { closeOverlays(); go("artifact-field"); }}><b>DRILL INTO EVIDENCE</b><span>Open an artifact to inspect provenance, normalized fields, and the safe raw record.</span><kbd>CLICK / ENTER</kbd></button><button onClick={() => { closeOverlays(); openOverlay("palette"); }}><b>FIND A CONTROL</b><span>Search pane, effects, narration, audio, alert, and character commands.</span><kbd>⌘/CTRL K</kbd></button></div><dl className="keymap"><div><dt>?</dt><dd>Help, except while typing</dd></div><div><dt>/</dt><dd>Command search</dd></div><div><dt>ESC</dt><dd>Close the front dialog</dd></div><div><dt>TAB</dt><dd>Move between controls</dd></div></dl><p className="truth-note"><b>Reading the display:</b> queued/running describe retrieval state; succeeded means the tool completed, not that a claim is true. Evidence is observed tool output. Narration is interpretation and remains labeled separately.</p><small>Help is contextual to the active pane. Actions above perform the route they describe.</small></section></div>}
    {detail && <div className="detail-backdrop" onMouseDown={closeDetail}><aside ref={dialogRef} className="detail-drawer" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label={`Evidence ${detail.reference}`}><button className="close" onClick={closeDetail}>×</button><span className="eyebrow">EVIDENCE DETAIL · STORED LOCAL DATA</span><h2>{detail.reference}</h2><dl><div><dt>STIX ID</dt><dd>{detail.stix_id}</dd></div><div><dt>TYPE</dt><dd>{detail.type}</dd></div><div><dt>VALUE</dt><dd>{detail.value}</dd></div><div><dt>SOURCE MODULE</dt><dd>{detail.source_module}</dd></div><div><dt>ORIGINAL QUERY</dt><dd>{detail.original_query}</dd></div></dl><h3>PROVENANCE</h3><pre>{JSON.stringify(detail.provenance, null, 2)}</pre><h3>NORMALIZED FIELDS</h3><pre>{JSON.stringify(detail.normalized, null, 2)}</pre><h3>DOSSIER CONTRIBUTIONS</h3><pre>{detail.dossier_contributions.length ? JSON.stringify(detail.dossier_contributions, null, 2) : "unavailable"}</pre><h3>SAFE RAW RECORD</h3><pre>{JSON.stringify(detail.raw, null, 2)}</pre><small>Opened from stored evidence. No network service or model was invoked.</small></aside></div>}
    {alertsOpen && <div className="modal-backdrop" onMouseDown={closeOverlays}><section ref={dialogRef} className="alert-queue" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Master caution alerts"><button className="close" aria-label="Close alerts" onClick={closeOverlays}>×</button><span className="eyebrow">PERSISTENT ATTENTION RECORD</span><h2>MASTER CAUTION</h2>{alerts.alerts.length === 0 && <p>No attention records.</p>}{alerts.alerts.map((alert) => <article className={alert.acknowledged ? "acknowledged" : ""} key={alert.event_id}><header><b>{alert.event_class.replaceAll("_", " ").toUpperCase()}</b><span>{alert.severity.toUpperCase()} · {alert.acknowledged ? "ACKNOWLEDGED" : "UNREAD"}</span></header><p>{alert.summary ?? alert.reason ?? alert.source}</p><div><button onClick={() => jumpToAlert(alert)}>ORIGIN</button>{!alert.acknowledged && <button onClick={() => acknowledge(alert.event_id)}>ACKNOWLEDGE</button>}{alert.artifact_ids?.map((id) => <button key={id} onClick={(event) => openDetail(id, event.currentTarget)}>DETAILS</button>)}</div></article>)}</section></div>}
    {palette && <div className="modal-backdrop" onMouseDown={() => setPalette(false)}><section ref={dialogRef} className="command-palette" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Command palette"><input autoFocus value={paletteQuery} onChange={(event) => setPaletteQuery(event.target.value)} placeholder="Search cockpit commands" aria-label="Search cockpit commands"/>{paletteCommands.map((command) => <button key={command.label} onClick={() => { command.run(); setPalette(false); setPaletteQuery(""); }}>{command.label}</button>)}</section></div>}
    {dojo && <div className="modal-backdrop" onMouseDown={closeOverlays}><section ref={dialogRef} onMouseDown={(event) => event.stopPropagation()}><SenseiDojo onClose={closeOverlays} reduced={effects !== "full"}/></section></div>}
  </main>;
}
