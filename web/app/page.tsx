"use client";

import { CSSProperties, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Chart, registerables } from "chart.js";
import { assembleChartjs } from "flint-chart";

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
  const detailOrigin = useRef<HTMLElement | null>(null);
  const dialogRef = useRef<HTMLElement | null>(null);
  const feedRef = useRef<HTMLDivElement>(null);

  const refresh = async () => { const response = await fetch("/api/state", { cache: "no-store" }); setState(await response.json()); };
  const refreshAlerts = async () => { const response = await fetch("/api/alerts", { cache: "no-store" }); if (response.ok) setAlerts(await response.json()); };
  useEffect(() => { Promise.all([refresh(), refreshAlerts()]).catch((reason) => setError(String(reason))); }, []);
  useEffect(() => { const storedEffects = window.localStorage.getItem("pivotglass.effects"); const storedNarration = window.localStorage.getItem("pivotglass.narration"); if (storedEffects === "full" || storedEffects === "reduced" || storedEffects === "off") setEffects(storedEffects); if (storedNarration === "full" || storedNarration === "brief" || storedNarration === "off") setNarration(storedNarration); }, []);
  useEffect(() => { if (!active) return; const started = Date.now(); const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000); return () => window.clearInterval(timer); }, [active]);
  useEffect(() => { const key = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setPalette(true); } else if (event.key === "/" && !(event.target instanceof HTMLInputElement)) { event.preventDefault(); setPalette(true); } else if (event.key === "?") setHelp((value) => !value); if (event.key === "Escape") { if (detail) closeDetail(); setPalette(false); setHelp(false); setMenu(false); setAlertsOpen(false); } }; window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key); });
  useEffect(() => { const restore = () => { if (!window.location.hash.startsWith("#evidence=")) { setDetail(null); requestAnimationFrame(() => detailOrigin.current?.focus()); } const pane = new URL(window.location.href).searchParams.get("pane"); if (pane && paneIds.includes(pane as typeof paneIds[number])) document.getElementById(pane)?.scrollIntoView({ behavior: "auto", block: "center" }); }; restore(); window.addEventListener("popstate", restore); return () => window.removeEventListener("popstate", restore); }, []);
  useEffect(() => { if (!(detail || help || alertsOpen || palette)) return; const root = dialogRef.current; const focusable = root?.querySelectorAll<HTMLElement>("button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex='-1'])"); focusable?.[0]?.focus(); const trap = (event: KeyboardEvent) => { if (event.key !== "Tab" || !focusable?.length) return; const first = focusable[0]; const last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } }; window.addEventListener("keydown", trap); return () => window.removeEventListener("keydown", trap); }, [detail, help, alertsOpen, palette]);

  const mode = state?.modes.find((item) => item.name === state.character) ?? state?.modes[0];
  const theme = mode?.theme ?? { border_color: "#00d7d7", accent_color: "#00d700", heading_color: "#00d7d7", text_color: "#ffffff", dim_color: "#5f5f5f" };
  const style = { "--line": theme.border_color, "--accent": theme.accent_color, "--heading": theme.heading_color, "--ink": theme.text_color, "--dim": theme.dim_color } as CSSProperties;
  const dossier = state?.dossier_slots.filter((slot) => slot.status === "filled").length ?? 0;
  const dossierProgress = state?.dossier_slots.filter((slot) => slot.status === "filled" || slot.status === "partial").length ?? 0;
  const configuredSources = state?.instruments.sources.configured ?? 0;

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
      const response = await fetch("/api/investigate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ target: value }) });
      const result = await response.json() as InvestigationSnapshot & { error?: string }; if (!response.ok) throw new Error(result.error ?? "Investigation failed");
      setInvestigationId(result.investigation_id); setFeed(result.events); requestAnimationFrame(() => feedRef.current?.scrollTo({ top: 0, behavior: "smooth" }));
      let cursor = result.cursor; let lifecycle = result.lifecycle;
      while (!["succeeded", "empty", "failed", "cancelled"].includes(lifecycle)) {
        await new Promise((resolve) => window.setTimeout(resolve, 350));
        const eventResponse = await fetch(`/api/investigations/${result.investigation_id}/events?cursor=${cursor}`, { cache: "no-store" });
        const update = await eventResponse.json() as InvestigationSnapshot & { error?: string }; if (!eventResponse.ok) throw new Error(update.error ?? "Investigation stream failed");
        if (update.events.length) { setFeed((current) => [...current, ...update.events]); await refreshAlerts(); }
        cursor = update.cursor; lifecycle = update.lifecycle;
      }
      await Promise.all([refresh(), refreshAlerts()]); requestAnimationFrame(() => feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: "smooth" }));
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
    setAlertsOpen(false);
    document.getElementById(`event-${alert.event_id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function go(id: typeof paneIds[number]) { const url = new URL(window.location.href); url.searchParams.set("pane", id); window.history.pushState({ pane: id }, "", url); document.getElementById(id)?.scrollIntoView({ behavior: effects === "full" ? "smooth" : "auto", block: "center" }); }

  function setEffectsPreference(value: "full" | "reduced" | "off") { setEffects(value); window.localStorage.setItem("pivotglass.effects", value); }
  function setNarrationPreference(value: "full" | "brief" | "off") { setNarration(value); window.localStorage.setItem("pivotglass.narration", value); }

  const paletteCommands = [
    ...paneIds.map((id) => ({ label: `Go to ${id.replace("-", " ")}`, run: () => go(id) })),
    { label: "Open operator help", run: () => setHelp(true) },
    { label: "Open Master Caution", run: () => setAlertsOpen(true) },
    { label: "Mute visual effects", run: () => setEffectsPreference("off") },
    { label: "Reduce visual effects", run: () => setEffectsPreference("reduced") },
    { label: "Enable full visual effects", run: () => setEffectsPreference("full") },
  ].filter((command) => command.label.toLowerCase().includes(paletteQuery.toLowerCase()));

  return <main style={style} className={`mode-${state?.character ?? "default"} effects-${effects} narration-${narration}`}>
    <div className="scanline" />
    <header className="masthead">
      <button className="menu-button" onClick={() => setMenu(!menu)} aria-expanded={menu}>☰ <span>DECK</span></button>
      <div className="brand"><span className="eyebrow">{mode?.cockpit.deck_name ?? "HUNT CONTROL"} // LOCAL INTELLIGENCE SYSTEM</span><h1>PIVOTGLASS</h1><small>{mode?.cockpit.vehicle ?? "AP-01 PURSUIT DECK"}</small></div>
      <div className="status-cluster"><span className="lamp ok" /><span className={`lamp ${active ? "hot" : ""}`} /><span className={active ? "system-state pulse" : "system-state"}>{active ? "HUNT ACTIVE" : "SYSTEM READY"}</span>{reviewingHistory && alerts.unread_count > 0 && <button className="unread-badge" onClick={() => setAlertsOpen(true)}>{alerts.highest_unread.toUpperCase()} · {alerts.unread_count} UNREAD</button>}<button className="help-button" onClick={() => setHelp(true)}>HELP ?</button></div>
      {menu && <nav className="deck-menu" aria-label="Cockpit navigation">{paneIds.map((id) => <button key={id} onClick={() => { go(id); setMenu(false); }}>{id.replace("-", " ")}</button>)}<hr/><label>VISUAL EFFECTS</label><div className="segmented">{(["full", "reduced", "off"] as const).map((value) => <button className={effects === value ? "selected" : ""} key={value} onClick={() => setEffectsPreference(value)}>{value}</button>)}</div><label>NARRATION</label><div className="segmented">{(["full", "brief", "off"] as const).map((value) => <button className={narration === value ? "selected" : ""} key={value} onClick={() => setNarrationPreference(value)}>{value}</button>)}</div><hr/><label>CHARACTER VOICE</label>{state?.modes.map((item) => <button className={item.name === state.character ? "selected" : ""} key={item.name} onClick={() => switchMode(item.name)}><b>{item.name.replaceAll("_", " ")}</b><small>{item.personality}</small></button>)}</nav>}
    </header>

    <nav className="pane-switcher" aria-label="Primary cockpit panes">{paneIds.map((id) => <button key={id} onClick={() => go(id)}>{id.replace("-", " ")}</button>)}<button onClick={() => setPalette(true)}>COMMANDS ⌘K</button></nav>

    <section className="voice-strip"><b>{state?.character?.replaceAll("_", " ").toUpperCase() ?? "DEFAULT"}</b><span>{mode?.greeting || "Cockpit link established."}</span><i>{mode?.pursuit_title ?? "THE HUNT"}</i></section>

    <section className="command-rail"><form onSubmit={investigate}><span className="prompt">glass://acquire</span><input value={target} onChange={(event) => setTarget(event.target.value)} placeholder="domain, IP, URL, email, or hash" aria-label="Investigation target"/><button disabled={active}>{active ? `TRACKING ${elapsed}s` : "ACQUIRE"}</button>{active && <button type="button" className="cancel" onClick={cancelInvestigation}>CANCEL</button>}</form>{error && <div className="error">⚠ FAULT · {error}</div>}</section>

    <section className="telemetry-rack" id="systems">
      <Meter label="REACTOR / LOCAL API" value={state?.instruments.local_api.available ? 100 : 0} detail={state?.instruments.local_api.available ? "AVAILABLE" : "UNAVAILABLE"} />
      <Meter label="DOSSIER CELLS" value={(dossierProgress / 9) * 100} detail={`${dossier} FILLED`} warning={dossier >= 8} />
      <Meter label="PROBE BAY" value={null} detail={`${configuredSources} CONFIGURED`} />
      <Meter label="TOKEN CORE" value={state?.instruments.model_tokens.available ? 100 : null} detail={state?.instruments.model_tokens.available ? `${state.instruments.model_tokens.used ?? 0} USED` : "NOT ENGAGED"} />
      <div className="damage"><span>INVESTIGATION STATE</span><b className={error ? "danger" : active ? "caution" : "ok-text"}>{error ? "FAULT" : active ? "RUNNING" : "IDLE"}</b><small>{error ? "SEE MASTER CAUTION" : active ? `${elapsed}s ELAPSED · EVENT STREAM LIVE` : "NO ACTIVE INVESTIGATION"}</small></div>
    </section>

    <section className="cockpit-grid">
      <article className="panel feed-panel" id="intelligence"><div className="panel-title"><span>{mode?.cockpit.left_rail} {mode?.pursuit_title} // INTELLIGENCE</span><small>{feed.length} EVENTS · SCROLL ACTIVE</small></div><div className="feed" ref={feedRef} tabIndex={0} aria-label="Scrollable intelligence feed" onScroll={(event) => { const node = event.currentTarget; setReviewingHistory(node.scrollHeight - node.scrollTop - node.clientHeight > 32); }}>
        {feed.length === 0 && <div className="standby"><div className="reticle"><i/><i/><i/></div><b>AWAITING TARGET LOCK</b><span>Evidence, retrieval briefings, and justified pivots will appear here.</span></div>}
        {feed.map((item) => <section id={`event-${item.event_id}`} className={`event ${item.content_class} state-${item.lifecycle} class-${item.event_class}`} key={item.event_id}><div className="event-head"><b>{item.lifecycle.toUpperCase()}</b><span>{item.source ?? item.event_class}</span></div>{item.tool && <small>{item.tool} · event {item.sequence}</small>}{item.briefing && <><p><label>GATHER</label>{item.briefing.artifacts}</p><p><label>WHY</label>{item.briefing.purpose}</p><p><label>WATCH</label>{item.briefing.watch_for}</p><small>Retrieval goal—not an observed finding.</small></>}{item.summary && <pre>{item.summary}</pre>}{item.reason && <p><label>STATE</label>{item.reason}</p>}{item.artifact_ids?.map((id) => <button className="evidence-link" key={id} onClick={(event) => openDetail(id, event.currentTarget)}>OPEN EVIDENCE</button>)}</section>)}
      </div></article>

      <aside className="right-stack">
        <article className="panel instruments" id="dossier"><div className="panel-title"><span>{mode?.cockpit.hud_title ?? "TACTICAL HUD"}</span><small>LIVE</small></div><dl><div><dt>WORKSPACE</dt><dd>{state?.workspace ?? "—"}</dd></div><div><dt>CHARACTER</dt><dd>{state?.character ?? "—"}</dd></div><div><dt>ARTIFACTS</dt><dd>{state?.objects.length ?? 0}</dd></div><div><dt>DOSSIER</dt><dd>{dossier}/9 FILLED</dd></div><div><dt>TRANSPORT</dt><dd>LOOPBACK / VERIFIED</dd></div></dl><div className="dossier-grid" aria-label={`${dossier} of 9 dossier cells filled`}>{(state?.dossier_slots ?? Array.from({length: 9}, (_, index) => ({name: `slot ${index + 1}`, status: "empty" as const, evidence_count: 0}))).map((slot, index) => <i className={slot.status} key={slot.name} title={`${slot.name}: ${slot.status} (${slot.evidence_count} evidence)`}>{index + 1}</i>)}</div></article>
        <article className="panel chart-panel" id="artifact-field"><div className="panel-title"><span>ARTIFACT FIELD</span><small>MICROSOFT FLINT / CHART.JS</small></div><DistributionChart objects={state?.objects ?? []} theme={theme}/><div className="artifact-list">{state?.objects.slice(-5).map((item) => <button key={item.reference} onClick={(event) => openDetail(item.reference, event.currentTarget)}><b>{item.reference}</b><span>{item.type} · {item.value}</span></button>)}</div></article>
        <article className="panel alert-panel"><div className="panel-title"><button onClick={() => setAlertsOpen(true)}>MASTER CAUTION</button><small>{error ? "FAULT" : alerts.unread_count ? `${alerts.unread_count} UNREAD · ${alerts.highest_unread.toUpperCase()}` : "CLEAR"}</small></div><p>{error ? error : alerts.unread_count ? "Attention records are waiting. Open Master Caution to inspect and acknowledge them." : active ? "Probe activity underway. Retrieval briefings are prospective until evidence arrives." : "No unacknowledged attention records."}</p></article>
      </aside>
    </section>

    <footer><span>EVIDENCE ≠ INFERENCE</span><span>LOCALHOST · NO TELEMETRY · OPERATOR CONTROLLED</span><span>?</span></footer>
    {help && <div className="modal-backdrop" onMouseDown={() => setHelp(false)}><section ref={dialogRef} className="help-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Operator help"><button className="close" onClick={() => setHelp(false)}>×</button><span className="eyebrow">PIVOTGLASS FIELD MANUAL</span><h2>OPERATOR HELP</h2><div className="help-grid"><div><b>ACQUIRE</b><p>Enter a supported indicator. Pivotglass plans deterministic API probes before gathering evidence.</p></div><div><b>NAVIGATE</b><p>Use the persistent pane switcher or press Command/Control K for searchable commands.</p></div><div><b>CHARACTER</b><p>Select a voice in DECK. The web cockpit uses the same canonical themes and identities as the TUI.</p></div><div><b>GROUND TRUTH</b><p>PROBE cards teach retrieval intent. EVIDENCE cards report observed tool output. Neither is silently promoted to inference.</p></div></div><small>Press ? to toggle help · Esc to close · Tab to navigate controls</small></section></div>}
    {detail && <div className="detail-backdrop" onMouseDown={closeDetail}><aside ref={dialogRef} className="detail-drawer" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label={`Evidence ${detail.reference}`}><button className="close" onClick={closeDetail}>×</button><span className="eyebrow">EVIDENCE DETAIL · STORED LOCAL DATA</span><h2>{detail.reference}</h2><dl><div><dt>STIX ID</dt><dd>{detail.stix_id}</dd></div><div><dt>TYPE</dt><dd>{detail.type}</dd></div><div><dt>VALUE</dt><dd>{detail.value}</dd></div><div><dt>SOURCE MODULE</dt><dd>{detail.source_module}</dd></div><div><dt>ORIGINAL QUERY</dt><dd>{detail.original_query}</dd></div></dl><h3>PROVENANCE</h3><pre>{JSON.stringify(detail.provenance, null, 2)}</pre><h3>NORMALIZED FIELDS</h3><pre>{JSON.stringify(detail.normalized, null, 2)}</pre><h3>DOSSIER CONTRIBUTIONS</h3><pre>{detail.dossier_contributions.length ? JSON.stringify(detail.dossier_contributions, null, 2) : "unavailable"}</pre><h3>SAFE RAW RECORD</h3><pre>{JSON.stringify(detail.raw, null, 2)}</pre><small>Opened from stored evidence. No network service or model was invoked.</small></aside></div>}
    {alertsOpen && <div className="modal-backdrop" onMouseDown={() => setAlertsOpen(false)}><section ref={dialogRef} className="alert-queue" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Master caution alerts"><button className="close" onClick={() => setAlertsOpen(false)}>×</button><span className="eyebrow">PERSISTENT ATTENTION RECORD</span><h2>MASTER CAUTION</h2>{alerts.alerts.length === 0 && <p>No attention records.</p>}{alerts.alerts.map((alert) => <article className={alert.acknowledged ? "acknowledged" : ""} key={alert.event_id}><header><b>{alert.event_class.replaceAll("_", " ").toUpperCase()}</b><span>{alert.severity.toUpperCase()} · {alert.acknowledged ? "ACKNOWLEDGED" : "UNREAD"}</span></header><p>{alert.summary ?? alert.reason ?? alert.source}</p><div><button onClick={() => jumpToAlert(alert)}>ORIGIN</button>{!alert.acknowledged && <button onClick={() => acknowledge(alert.event_id)}>ACKNOWLEDGE</button>}{alert.artifact_ids?.map((id) => <button key={id} onClick={(event) => openDetail(id, event.currentTarget)}>DETAILS</button>)}</div></article>)}</section></div>}
    {palette && <div className="modal-backdrop" onMouseDown={() => setPalette(false)}><section ref={dialogRef} className="command-palette" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Command palette"><input autoFocus value={paletteQuery} onChange={(event) => setPaletteQuery(event.target.value)} placeholder="Search cockpit commands" aria-label="Search cockpit commands"/>{paletteCommands.map((command) => <button key={command.label} onClick={() => { command.run(); setPalette(false); setPaletteQuery(""); }}>{command.label}</button>)}</section></div>}
  </main>;
}
