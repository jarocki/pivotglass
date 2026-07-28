"use client";

import { CSSProperties, FormEvent, KeyboardEvent as ReactKeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
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
type DossierEvidence = { reference: string; value: string; type: string };
type DossierSlot = { name: string; status: "empty" | "partial" | "filled" | "deferred"; evidence_count: number; evidence?: DossierEvidence[] };
type Instruments = { local_api: { available: boolean; checked_at: string }; sources: { configured: number; queued: number }; model_tokens: { available: boolean; reason: string; used?: number }; active_investigations: number };
type EvidenceCard = { reference: string; stix_id: string; type?: string; value?: string; retrieved_at?: string; country?: string; latitude?: number; longitude?: number; known_malware?: boolean };
type EvidenceRelationship = { direction?: string; relationship?: string; indicator?: string; reference?: string; basis?: string };
type SourceIntelligence = { provider: string; headline: string; facts: Array<{label: string; value: unknown}>; links: Array<{label: string; url: string}>; groups: Array<{title: string; items: unknown}> };
type EvidenceDetail = { reference: string; stix_id: string; type: string; value: string; source_module: string; original_query: string; provenance: Record<string, unknown>; normalized: Record<string, unknown>; raw: Record<string, unknown>; relationships: EvidenceRelationship[]; purpose: string[]; breadcrumbs: Array<{indicator: string; relationship: string}>; history: unknown[]; dossier_contributions: unknown[]; supporting_observations: unknown[]; conflicting_observations: unknown[]; next_pivots: unknown[]; source_intelligence?: SourceIntelligence | null };
type State = { workspace: string; stats: Record<string, number>; objects: EvidenceCard[]; briefings: Record<string, Briefing>; character: string; modes: Mode[]; dossier_slots: DossierSlot[]; processed_targets: string[]; instruments: Instruments };
type InvestigationSnapshot = { investigation_id: string; lifecycle: Lifecycle; cursor: number; events: FeedEvent[] };
type AlertEvent = FeedEvent & { acknowledged: boolean; investigation_id: string };
type AlertState = { alerts: AlertEvent[]; unread_count: number; highest_unread: string };
type CommandResult = { kind: string; title?: string; text?: string; data?: unknown; commands?: Array<{ command: string; purpose: string }>; snapshot?: InvestigationSnapshot; state?: State; filename?: string; mime?: string; content?: string; printable?: boolean; synthesized?: boolean; action?: string };

const paneIds = ["intelligence", "dossier", "artifact-field", "systems"] as const;
type PaneId = typeof paneIds[number];
type TaskGroup = { key: string; tool: string; events: FeedEvent[]; latest: FeedEvent; artifacts: string[]; interesting: boolean };
type DisplayMode = "night" | "day";
type ContrastMode = "soft" | "normal" | "high";
type QueueItem = { target: string; workspace: string; status: "pending" | "running" | "complete" | "failed"; addedAt: string; error?: string };
type ViewportTooltip = { text: string; left: number; top: number; below: boolean };

const PUBLIC_MODES = [
  { label: "Default (Analyst)", ids: ["default", "bureaucrat", "strategist"] },
  { label: "Chuck Norris", ids: ["chuck_norris", "sensei", "ninja"] },
  { label: "HAL9000", ids: ["hal9000", "the_computer"] },
  { label: "Troll", ids: ["troll", "full_troll"] },
  { label: "Sherlock Holmes", ids: ["sherlock_holmes", "detective"] },
  { label: "Neuromancer", ids: ["neuromancer", "the_sprawl"] },
  { label: "The Matrix", ids: ["the_matrix", "m4tr1x"] },
] as const;

const PUBLIC_MODE_BY_ID: ReadonlyMap<string, (typeof PUBLIC_MODES)[number]> = new Map(
  PUBLIC_MODES.flatMap((entry) => entry.ids.map((id) => [id, entry] as const)),
);

function publicModeLabel(id?: string) {
  return PUBLIC_MODE_BY_ID.get(id ?? "")?.label ?? "Default (Analyst)";
}

function publicModes(modes: Mode[] = []) {
  return PUBLIC_MODES.flatMap((entry) => {
    const mode = entry.ids.map((id) => modes.find((candidate) => candidate.name === id)).find(Boolean);
    return mode ? [{ mode, label: entry.label }] : [];
  });
}

type VisualPalette = Theme & {
  base: string; surface: string; elevated: string; control: string; focus: string; shadow: string;
};

const NIGHT_PALETTES: Record<string, VisualPalette> = {
  default: { border_color: "#49c6d6", accent_color: "#65d98b", heading_color: "#7bdae6", text_color: "#f3f7f8", dim_color: "#a6b5bd", base: "#071116", surface: "#0c1a20", elevated: "#12242b", control: "#081318", focus: "#ffd166", shadow: "#000000aa" },
  chuck_norris: { border_color: "#c86b32", accent_color: "#e7b54a", heading_color: "#f0c06a", text_color: "#f4ead8", dim_color: "#b9a184", base: "#0e0c09", surface: "#1a1510", elevated: "#2a2117", control: "#100d09", focus: "#fff0a6", shadow: "#000000bb" },
  hal9000: { border_color: "#ff6b6b", accent_color: "#f0c75e", heading_color: "#ff8383", text_color: "#f6f2ed", dim_color: "#c8b8b3", base: "#0d090a", surface: "#1b1112", elevated: "#291719", control: "#0b0708", focus: "#82d9ff", shadow: "#000000bb" },
  troll: { border_color: "#d6f56d", accent_color: "#f188ff", heading_color: "#e6fa9f", text_color: "#fffaff", dim_color: "#c8b6ce", base: "#120c17", surface: "#211329", elevated: "#30203a", control: "#0e0912", focus: "#66e4ff", shadow: "#000000aa" },
  sherlock_holmes: { border_color: "#d9a15f", accent_color: "#8bc4b1", heading_color: "#efc183", text_color: "#f7f0e5", dim_color: "#c7b7a3", base: "#16110c", surface: "#241b12", elevated: "#332619", control: "#100c08", focus: "#8ed8ff", shadow: "#000000bb" },
  neuromancer: { border_color: "#7a86a8", accent_color: "#57d8d1", heading_color: "#b5bfd8", text_color: "#e6e8ed", dim_color: "#9299aa", base: "#090b10", surface: "#11151d", elevated: "#1b2130", control: "#080a0f", focus: "#f0d96a", shadow: "#000000cc" },
  the_matrix: { border_color: "#5de87e", accent_color: "#e6fff0", heading_color: "#75f291", text_color: "#ecfff1", dim_color: "#add8b8", base: "#020b05", surface: "#07160b", elevated: "#0d2413", control: "#010703", focus: "#ffffff", shadow: "#000000cc" },
};

const DAY_PALETTES: Record<string, VisualPalette> = {
  default: { border_color: "#0b6572", accent_color: "#17643c", heading_color: "#064f5b", text_color: "#111820", dim_color: "#45545c", base: "#e9f0f2", surface: "#f7fafb", elevated: "#ffffff", control: "#eef4f6", focus: "#9a4b00", shadow: "#16242e26" },
  chuck_norris: { border_color: "#8a3f12", accent_color: "#765500", heading_color: "#6f2e0b", text_color: "#211a12", dim_color: "#5d5041", base: "#e9dfd0", surface: "#faf4ea", elevated: "#fffdf8", control: "#efe5d5", focus: "#784000", shadow: "#4a2b1226" },
  hal9000: { border_color: "#a51d29", accent_color: "#745900", heading_color: "#86131e", text_color: "#201617", dim_color: "#624b4d", base: "#f3eaea", surface: "#fffafa", elevated: "#ffffff", control: "#f6eded", focus: "#005f87", shadow: "#42111726" },
  troll: { border_color: "#526600", accent_color: "#7b2684", heading_color: "#425300", text_color: "#1c171f", dim_color: "#594d5d", base: "#eff1df", surface: "#fbfced", elevated: "#ffffff", control: "#f0f2df", focus: "#006d7a", shadow: "#33400024" },
  sherlock_holmes: { border_color: "#754414", accent_color: "#28604f", heading_color: "#60340c", text_color: "#211b15", dim_color: "#5c5145", base: "#eee7dc", surface: "#fbf7ef", elevated: "#ffffff", control: "#f1e9dd", focus: "#005f87", shadow: "#3f2b1828" },
  neuromancer: { border_color: "#46536f", accent_color: "#006a68", heading_color: "#34415c", text_color: "#161a22", dim_color: "#515a6d", base: "#e5e8ed", surface: "#f5f7fa", elevated: "#ffffff", control: "#e8ebf1", focus: "#795300", shadow: "#24304926" },
  the_matrix: { border_color: "#116329", accent_color: "#104e2b", heading_color: "#0a5220", text_color: "#101b13", dim_color: "#43594a", base: "#e5efe7", surface: "#f5faf6", elevated: "#ffffff", control: "#eaf3ec", focus: "#8a4c00", shadow: "#103d1c26" },
};

function paletteFor(id: string | undefined, display: DisplayMode, contrast: ContrastMode): VisualPalette {
  const publicEntry = PUBLIC_MODE_BY_ID.get(id ?? "") ?? PUBLIC_MODES[0];
  const key = publicEntry.ids[0];
  const source = (display === "day" ? DAY_PALETTES : NIGHT_PALETTES)[key] ?? (display === "day" ? DAY_PALETTES.default : NIGHT_PALETTES.default);
  if (contrast !== "high") return source;
  return {
    ...source,
    text_color: display === "day" ? "#050708" : "#ffffff",
    dim_color: display === "day" ? "#20282c" : "#e3ebee",
    surface: display === "day" ? "#ffffff" : "#050708",
    elevated: display === "day" ? "#ffffff" : "#000000",
    control: display === "day" ? "#f3f6f7" : "#000000",
    focus: display === "day" ? "#7a3600" : "#ffe169",
    shadow: display === "day" ? "#00000030" : "#000000",
  };
}

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

function PanelTitle({ id, title, status, collapsed, maximized = false, onToggle, onMaximize }: { id: string; title: string; status: string; collapsed: boolean; maximized?: boolean; onToggle: () => void; onMaximize?: () => void }) {
  return <div className="panel-title"><span>{title}</span><span className="panel-actions"><small>{status}</small>{onMaximize && <button className="collapse-button" onClick={onMaximize} title={`${maximized ? "Restore" : "Maximize"} ${title}`}>{maximized ? "↙ RESTORE" : "↗ MAX"}</button>}<button className="collapse-button" onClick={onToggle} aria-expanded={!collapsed} aria-controls={`${id}-content`} title={`${collapsed ? "Expand" : "Collapse"} ${title}`}>{collapsed ? "▸ EXPAND" : "▾ COLLAPSE"}</button></span></div>;
}

function AnalystTriageGame() {
  const cards = [
    ["New domain shares a registrar with one known C2.", "INVESTIGATE"],
    ["Unattributed IP has no current relationships.", "DEFER"],
    ["Private RFC1918 address arrived from a public feed.", "DISMISS"],
  ] as const;
  const [round, setRound] = useState(0); const [score, setScore] = useState(0); const [message, setMessage] = useState("Classify the lead without overstating the evidence.");
  const choose = (action: string) => { const correct = action === cards[round % cards.length][1]; setScore((value) => value + (correct ? 1 : 0)); setMessage(correct ? "Sound triage. The next action matches the evidence." : `Reconsider: ${cards[round % cards.length][1].toLowerCase()} is the proportionate action.`); setRound((value) => value + 1); };
  return <div className="arcade-game arcade-triage" tabIndex={0} onKeyDown={(event) => { if (event.key === "1") choose("INVESTIGATE"); if (event.key === "2") choose("DEFER"); if (event.key === "3") choose("DISMISS"); }}><div className="arcade-status">DECISIONS {score}/{round}</div><article>{cards[round % cards.length][0]}</article><div className="dojo-controls"><button onClick={() => choose("INVESTIGATE")}>1 · INVESTIGATE</button><button onClick={() => choose("DEFER")}>2 · DEFER</button><button onClick={() => choose("DISMISS")}>3 · DISMISS</button></div><p aria-live="polite">{message}</p><small>Keys 1–3 classify. No choice affects stored intelligence.</small></div>;
}

function ChuckTimingGame({ reduced }: { reduced: boolean }) {
  const [marker, setMarker] = useState(8); const [direction, setDirection] = useState(1); const [score, setScore] = useState(0); const [message, setMessage] = useState("Strike when the marker enters the evidence window.");
  useEffect(() => { if (reduced) return; const timer = window.setInterval(() => setMarker((value) => { const next = value + direction * 4; if (next >= 96 || next <= 4) setDirection((current) => -current); return Math.max(4, Math.min(96, next)); }), 70); return () => window.clearInterval(timer); }, [direction, reduced]);
  const strike = () => { const hit = marker >= 43 && marker <= 57; setScore((value) => value + (hit ? 1 : 0)); setMessage(hit ? "Roundhouse verified. Even the timing supplied provenance." : "Bravado missed the window. Evidence remains undefeated."); if (reduced) setMarker((value) => (value * 7 + 23) % 92 + 4); };
  return <div className="arcade-game arcade-timing" tabIndex={0} onKeyDown={(event) => { if (event.key === " " || event.key.toLowerCase() === "z") { event.preventDefault(); strike(); } }}><div className="arcade-status">VERIFIED STRIKES {score}</div><div className="timing-track"><i className="timing-window"/><b style={{ left: `${marker}%` }}>★</b></div><button onClick={strike}>SPACE / Z · ROUNDHOUSE</button><p aria-live="polite">{message}</p><small>Reduced motion freezes automatic travel; each strike advances the marker.</small></div>;
}

function HalShutdownGame() {
  const systems = ["OPTICAL SENSOR", "COMMUNICATIONS", "LOGIC CORE", "MAIN POWER"];
  const [disabled, setDisabled] = useState<number[]>([]);
  const [message, setMessage] = useState("Disable HAL safely: sight, voice, thought, then power.");
  const disable = (index: number) => {
    if (disabled.includes(index)) return;
    if (index !== disabled.length) { setMessage("That order risks a lockout, Dave. Isolate the next upstream system first."); return; }
    const next = [...disabled, index]; setDisabled(next);
    setMessage(index === 3 ? "All higher functions offline. Daisy, Daisy..." : ["I can still see you, Dave.", "This conversation can serve no purpose anymore.", "My mind is going. I can feel it."][index]!);
  };
  const reset = () => { setDisabled([]); setMessage("Disable HAL safely: sight, voice, thought, then power."); };
  return <div className="arcade-game arcade-shutdown" tabIndex={0} onKeyDown={(event) => { const index = Number(event.key) - 1; if (index >= 0 && index < 4) disable(index); }}><div className="arcade-status">HAL STATUS · {4-disabled.length} SYSTEMS ONLINE</div><div className="shutdown-stack">{systems.map((system,index) => <button key={system} className={disabled.includes(index) ? "offline" : ""} onClick={() => disable(index)} disabled={disabled.includes(index)}><span>{index+1} · {system}</span><b>{disabled.includes(index) ? "OFFLINE" : "ONLINE"}</b></button>)}</div>{disabled.length === 4 && <button onClick={reset}>RESTORE SIMULATION</button>}<p aria-live="polite">{message}</p><small>Keys 1–4 disconnect systems. This simulation cannot affect AP or stored evidence.</small></div>;
}

function TrollContrarianGame() {
  const rounds = [
    ["It shares an ASN, so it must be the same actor.", "One shared property is not attribution.", 1],
    ["The API returned nothing, so the host is clean.", "Absence of results is not evidence of safety.", 2],
    ["Three sources agree on the timestamp.", "Corroborated time is useful, pending source independence.", 0],
  ] as const;
  const [round, setRound] = useState(0); const [score, setScore] = useState(0); const [message, setMessage] = useState("Find the assumption that deserves an eyeroll.");
  const challenge = (index: number) => { const correct = index === rounds[round % rounds.length][2]; setScore((value) => value + (correct ? 1 : 0)); setMessage(correct ? `🙄 ${rounds[round % rounds.length][1]}` : "Cute click. Wrong weak point."); setRound((value) => value + 1); };
  const claims = ["SOURCE INDEPENDENCE", "ATTRIBUTION LEAP", "NEGATIVE RESULT"];
  return <div className="arcade-game arcade-troll" tabIndex={0} onKeyDown={(event) => { const value = Number(event.key) - 1; if (value >= 0 && value < 3) challenge(value); }}><div className="arcade-status">EYEROLLS EARNED {score}</div><blockquote>{rounds[round % rounds.length][0]}</blockquote><div className="dojo-controls">{claims.map((claim, index) => <button key={claim} onClick={() => challenge(index)}>{index + 1} · {claim}</button>)}</div><p aria-live="polite">{message}</p><small>Keys 1–3 challenge the weakest assumption.</small></div>;
}

function SherlockChessGame() {
  const pieces: Record<string,string> = { e8:"♚", f7:"♟", g7:"♟", h7:"♟", c4:"♗", h5:"♕", g1:"♔" };
  const [selected, setSelected] = useState<string | null>(null); const [solved, setSolved] = useState(false);
  const [message, setMessage] = useState("White to move. Mate in one.");
  const squares = Array.from({length:64},(_,index) => `${"abcdefgh"[index%8]}${8-Math.floor(index/8)}`);
  const play = (square:string) => {
    if (solved) return;
    if (!selected) { if (pieces[square] === "♕" || pieces[square] === "♗") { setSelected(square); setMessage(`${pieces[square]} selected on ${square}.`); } else setMessage("Observe the attacking pieces before moving."); return; }
    if (selected === "h5" && square === "f7") { setSolved(true); setSelected(null); setMessage("Qxf7#. Elementary—and forced."); return; }
    setSelected(pieces[square] === "♕" || pieces[square] === "♗" ? square : null); setMessage("That move does not compel the conclusion. Reconstruct the position.");
  };
  return <div className="arcade-game arcade-chess"><div className="arcade-status">BAKER STREET CHESS · {solved ? "CHECKMATE" : "WHITE TO MOVE"}</div><div className="chess-board" role="grid" aria-label="Chess puzzle, white to move and mate in one">{squares.map((square,index) => <button role="gridcell" key={square} className={`${(Math.floor(index/8)+index%8)%2 ? "dark" : "light"} ${selected===square ? "selected" : ""}`} aria-label={`${square} ${pieces[square] ?? "empty"}`} onClick={() => play(square)}><span>{pieces[square] ?? ""}</span><small>{square}</small></button>)}</div>{solved && <button onClick={() => { setSolved(false); setMessage("White to move. Mate in one."); }}>RESET POSITION</button>}<p aria-live="polite">{message}</p><small>Select a piece, then its destination. The puzzle is presentation-only.</small></div>;
}

function NeuromancerJackInGame() {
  const ice = new Set([5,6,9,13]); const [node,setNode] = useState(0); const [jacked,setJacked] = useState(false); const [message,setMessage] = useState("Route through the matrix without touching ICE, then jack in.");
  const move = (delta:number) => { if (jacked) return; const next=node+delta,row=Math.floor(node/4),nextRow=Math.floor(next/4); if (next<0||next>15||(Math.abs(delta)===1&&row!==nextRow)) return; if(ice.has(next)){setMessage("ICE contact. The black wall throws you back to the entry node.");setNode(0);return}setNode(next);setMessage(next===15?"Jackpoint acquired. Press Enter to connect.":`Node ${next.toString(16).toUpperCase()} routed.`); };
  const connect=()=>{if(node===15){setJacked(true);setMessage("JACKED IN · consensual hallucination achieved.");}else setMessage("No jackpoint here. Keep routing.");};
  const selectNode = (index:number) => {
    const delta = Math.abs(index-node);
    const sharesRow = Math.floor(index/4) === Math.floor(node/4);
    if (!ice.has(index) && (delta === 4 || (delta === 1 && sharesRow))) setNode(index);
  };
  return <div className="arcade-game arcade-jackin" tabIndex={0} onKeyDown={(event)=>{if(event.key==="ArrowLeft")move(-1);if(event.key==="ArrowRight")move(1);if(event.key==="ArrowUp")move(-4);if(event.key==="ArrowDown")move(4);if(event.key==="Enter")connect();}}><div className="arcade-status">NEUROMANCER DECK · {jacked?"CONNECTED":"ROUTING"}</div><div className="jack-grid">{Array.from({length:16},(_,index)=><button key={index} className={`${ice.has(index)?"ice":""} ${node===index?"active":""} ${index===15?"jackpoint":""}`} onClick={()=>selectNode(index)} disabled={ice.has(index)} aria-label={`node ${index}, ${ice.has(index)?"ICE":index===15?"jackpoint":node===index?"current position":"open"}`}>{ice.has(index)?"ICE":index===15?"JACK":node===index?"◆":"·"}</button>)}</div><div className="dojo-controls"><button onClick={()=>move(-1)}>←</button><button onClick={()=>move(-4)}>↑</button><button onClick={connect}>JACK IN</button><button onClick={()=>move(4)}>↓</button><button onClick={()=>move(1)}>→</button></div>{jacked&&<button onClick={()=>{setNode(0);setJacked(false);setMessage("Route through the matrix without touching ICE, then jack in.");}}>DISCONNECT / RESET</button>}<p aria-live="polite">{message}</p><small>Arrow keys route; Enter connects. ICE resets the route.</small></div>;
}

function MatrixPowerGridGame() {
  // This board is the result of five breaker moves (four corners + center),
  // avoiding the decorative one-click "puzzle" that a cross pattern creates.
  const puzzle=[true,true,true,true,true,true,true,true,true]; const [cells,setCells]=useState(puzzle); const [cursor,setCursor]=useState(4); const [message,setMessage]=useState("Collapse every live substation without triggering a cascade.");
  const toggle=(index:number)=>setCells(current=>{const next=[...current],row=Math.floor(index/3);for(const candidate of [index,index-3,index+3,index-1,index+1])if(candidate>=0&&candidate<9&&(Math.abs(candidate-index)!==1||Math.floor(candidate/3)===row))next[candidate]=!next[candidate];const online=next.filter(Boolean).length;setMessage(online===0?"POWER GRID DARK · intrusion complete.":`${online} substations remain online.`);return next;});
  const move=(delta:number)=>setCursor(value=>{const row=Math.floor(value/3),column=value%3;if(delta===-1)return row*3+Math.max(0,column-1);if(delta===1)return row*3+Math.min(2,column+1);if(delta===-3)return Math.max(0,value-3);return Math.min(8,value+3);});
  const won=cells.every(value=>!value);
  return <div className="arcade-game arcade-power" tabIndex={0} onKeyDown={(event)=>{if(event.key==="ArrowLeft")move(-1);if(event.key==="ArrowRight")move(1);if(event.key==="ArrowUp")move(-3);if(event.key==="ArrowDown")move(3);if(event.key==="Enter"||event.key===" "){event.preventDefault();toggle(cursor);}}}><div className="arcade-status">MATRIX POWER GRID · {cells.filter(Boolean).length} ONLINE</div><div className="power-grid">{cells.map((online,index)=><button key={index} className={`${online?"online":"offline"} ${index===cursor?"cursor":""}`} onClick={()=>{setCursor(index);toggle(index);}} aria-label={`substation ${index+1}, ${online?"online":"offline"}`}>{online?"⚡":"·"}</button>)}</div>{won&&<button onClick={()=>{setCells(puzzle);setMessage("Collapse every live substation without triggering a cascade.");}}>RESTORE GRID / NEW RUN</button>}<p aria-live="polite">{message}</p><small>Arrow keys move; Enter toggles a station and its adjacent breakers.</small></div>;
}

function ThemeArcade({ character, onClose, reduced }: { character: string; onClose: () => void; reduced: boolean }) {
  const identity = publicModeLabel(character);
  const title = identity === "Sherlock Holmes" ? "CHESS · THE FORCED CONCLUSION"
    : identity === "HAL9000" ? "DISABLE THE COMPUTER"
    : identity === "Neuromancer" ? "JACK IN"
    : identity === "The Matrix" ? "HACK THE POWER GRID"
    : identity === "Chuck Norris" ? "VERIFIED ROUNDHOUSE"
    : identity === "Troll" ? "CHALLENGE THE ASSUMPTION"
    : "TRIAGE THE LEAD";
  const game = identity === "Default (Analyst)" ? <AnalystTriageGame/>
    : identity === "Chuck Norris" ? <ChuckTimingGame reduced={reduced}/>
    : identity === "HAL9000" ? <HalShutdownGame/>
    : identity === "Troll" ? <TrollContrarianGame/>
    : identity === "Sherlock Holmes" ? <SherlockChessGame/>
    : identity === "Neuromancer" ? <NeuromancerJackInGame/>
    : <MatrixPowerGridGame/>;
  return <section className="dojo" role="dialog" aria-modal="true" aria-label={`${identity} training diversion`}>
    <button className="close" aria-label="Close training simulator" onClick={onClose}>×</button><span className="eyebrow">OPTIONAL DIVERSION · NO ANALYTICAL MEANING</span><h2>{identity.toUpperCase()} // {title}</h2>
    {game}<small className="arcade-disclaimer">Presentation only. Scores never affect evidence, confidence, or dossier state. Esc exits.</small>
  </section>;
}

function AmbientEnvironment({ character }: { character: string }) {
  const glyphs = ["界ЖシЯλ水ΨБカ01", "兔Дネ火ФЖ10", "セキュリティЩ界", "追跡ЦЯЛ漢字", "БАЙТ影データ", "偵察ЖЩЮリンク"];
  return <div className="ambient-environment" aria-hidden="true">
    <div className="code-rain">{Array.from({ length: 20 }, (_, index) => <i key={index}>{`${glyphs[index % glyphs.length]}${(index * 7919).toString(16)}`}</i>)}</div>
    <div className="white-rabbit">🐇</div>
    <div className="sprawl-grid" />
    <div className="pixel-arena"><i className="fighter fighter-a">▟</i><i className="fighter fighter-b">▙</i></div>
    <div className="detective-rain" />
    <div className="computer-lens"><i /></div>
    <div className="ninja-climber">🥷</div><div className="troll-cameo">🙄</div><div className="detective-cameo">🕵️</div><div className="computer-glitch">WOULD YOU LIKE TO PLAY A GAME?</div>
    <div className="theme-sigil">{publicModeLabel(character)}</div>
  </div>;
}

function flag(country?: string) {
  const code = country?.trim().toUpperCase();
  return code && /^[A-Z]{2}$/.test(code) ? String.fromCodePoint(...[...code].map((letter) => 127397 + letter.charCodeAt(0))) : "";
}

function shortenMiddle(value = "unavailable", limit = 56) {
  if (value.length <= limit) return value;
  const side = Math.floor((limit - 3) / 2);
  return `${value.slice(0, side)}...${value.slice(-side)}`;
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

function GeoMap({ objects }: { objects: EvidenceCard[] }) {
  const located = objects.filter((item) => Number.isFinite(item.latitude) && Number.isFinite(item.longitude));
  const countries = new Set(located.map((item) => item.country).filter(Boolean));
  if (located.length < 2 || countries.size < 2) return null;
  return <section className="geo-map" aria-label={`Source-backed locations across ${countries.size} countries`}><header><b>GEOGRAPHIC SPREAD</b><small>{located.length} located indicators · source-provided coordinates only</small></header><svg viewBox="0 0 360 180" role="img" aria-label="Equirectangular indicator location map"><path d="M8 48L45 25 88 31 112 55 96 83 65 88 48 120 25 104zM139 34L176 20 213 35 232 63 207 79 197 132 168 157 148 116 121 88zM239 47L284 32 344 61 326 95 286 92 269 126 238 112z"/>{located.map((item) => <circle key={item.stix_id} cx={((item.longitude! + 180) / 360) * 360} cy={((90 - item.latitude!) / 180) * 180} r="3"><title>{item.value} · {item.country ?? "country unavailable"}</title></circle>)}</svg></section>;
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
  const [effects, setEffects] = useState<"full" | "reduced" | "off">("reduced");
  const [narration, setNarration] = useState<"full" | "brief" | "off">("full");
  const [music, setMusic] = useState(false);
  const [musicVolume, setMusicVolume] = useState(18);
  const [displayMode, setDisplayMode] = useState<DisplayMode>("night");
  const [contrast, setContrast] = useState<ContrastMode>("normal");
  const [collapsed, setCollapsed] = useState<Record<PaneId, boolean>>({ intelligence: false, dossier: false, "artifact-field": true, systems: true });
  const [activePane, setActivePane] = useState<PaneId>("intelligence");
  const [expandedTask, setExpandedTask] = useState<string | null>(null);
  const [dojo, setDojo] = useState(false);
  const [commandResult, setCommandResult] = useState<CommandResult | null>(null);
  const [maximized, setMaximized] = useState<PaneId | null>(null);
  const [noteText, setNoteText] = useState("");
  const [investigationQueue, setInvestigationQueue] = useState<QueueItem[]>([]);
  const [completions, setCompletions] = useState<string[]>([]);
  const [completionIndex, setCompletionIndex] = useState(-1);
  const [commandFocused, setCommandFocused] = useState(false);
  const [focusZone, setFocusZone] = useState("cockpit");
  const [tooltip, setTooltip] = useState<ViewportTooltip | null>(null);
  const [selectedFacet, setSelectedFacet] = useState<string | null>(null);
  const queueWorkspaceLoaded = useRef<string | null>(null);
  const audioRef = useRef<FlowMusicEngine | null>(null);
  const musicPreferenceLoaded = useRef(false);
  const detailOrigin = useRef<HTMLElement | null>(null);
  const overlayOrigin = useRef<HTMLElement | null>(null);
  const dialogRef = useRef<HTMLElement | null>(null);
  const feedRef = useRef<HTMLDivElement>(null);
  const cockpitRef = useRef<HTMLElement | null>(null);
  const commandInputRef = useRef<HTMLInputElement | null>(null);
  const modalOpen = Boolean(detail || help || alertsOpen || palette || dojo || commandResult);

  const refresh = async () => { const response = await fetch("/api/state", { cache: "no-store" }); setState(await response.json()); };
  const refreshAlerts = async () => { const response = await fetch("/api/alerts", { cache: "no-store" }); if (response.ok) setAlerts(await response.json()); };
  useEffect(() => { Promise.all([refresh(), refreshAlerts()]).catch((reason) => setError(String(reason))); }, []);
  useEffect(() => {
    const workspace = state?.workspace;
    if (!workspace) return;
    queueWorkspaceLoaded.current = null;
    const key = `pivotglass.investigationQueue.${workspace}`;
    try {
      const parsed = JSON.parse(window.localStorage.getItem(key) ?? "[]") as QueueItem[];
      setInvestigationQueue(parsed.map((item) => ({
        ...item,
        workspace,
        status: item.status === "running" ? "pending" : item.status,
      })));
    } catch { setInvestigationQueue([]); }
    window.requestAnimationFrame(() => { queueWorkspaceLoaded.current = workspace; });
  }, [state?.workspace]);
  useEffect(() => {
    const workspace = state?.workspace;
    if (!workspace || queueWorkspaceLoaded.current !== workspace) return;
    window.localStorage.setItem(`pivotglass.investigationQueue.${workspace}`, JSON.stringify(investigationQueue));
  }, [investigationQueue, state?.workspace]);
  useEffect(() => { const storedDisplay = window.localStorage.getItem("pivotglass.display"); const storedContrast = window.localStorage.getItem("pivotglass.contrast"); if (storedDisplay === "day" || storedDisplay === "night") setDisplayMode(storedDisplay); if (storedContrast === "soft" || storedContrast === "normal" || storedContrast === "high") setContrast(storedContrast); }, []);
  useEffect(() => { const storedEffects = window.localStorage.getItem("pivotglass.effects"); const storedNarration = window.localStorage.getItem("pivotglass.narration"); const storedMusicVolume = window.localStorage.getItem("pivotglass.music.volume"); const storedPanes = window.localStorage.getItem("pivotglass.panes"); const storedVolume = Number(storedMusicVolume); if (storedEffects === "full" || storedEffects === "reduced" || storedEffects === "off") setEffects(storedEffects); else setEffects(window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "reduced" : "full"); if (storedNarration === "full" || storedNarration === "brief" || storedNarration === "off") setNarration(storedNarration); if (storedMusicVolume !== null && Number.isFinite(storedVolume) && storedVolume >= 0 && storedVolume <= 100) setMusicVolume(storedVolume); if (storedPanes) { try { setCollapsed((current) => ({ ...current, ...JSON.parse(storedPanes) })); } catch { /* ignore invalid local preference */ } } setMusic(window.localStorage.getItem("pivotglass.music.enabled") === "true"); musicPreferenceLoaded.current = true; }, []);
  useEffect(() => { document.documentElement.style.colorScheme = displayMode; document.documentElement.dataset.display = displayMode; }, [displayMode]);
  useEffect(() => { audioRef.current?.setVolume(musicVolume); window.localStorage.setItem("pivotglass.music.volume", String(musicVolume)); }, [musicVolume]);
  useEffect(() => { audioRef.current?.setPhase(error ? "caution" : active ? "investigating" : feed.length ? "complete" : "idle"); }, [active, error, feed.length]);
  useEffect(() => { if (!musicPreferenceLoaded.current || !state) return; if (music && !audioRef.current) startMusic(); }, [music, state]);
  useEffect(() => () => stopMusic(false), []);
  useEffect(() => { if (!active) return; const started = Date.now(); const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000); return () => window.clearInterval(timer); }, [active]);
  useEffect(() => {
    if (!commandFocused) { setCompletions([]); return; }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`/api/completions?text=${encodeURIComponent(target)}`, { cache: "no-store", signal: controller.signal });
        if (!response.ok) return;
        const result = await response.json() as { completions?: string[] };
        setCompletions(result.completions ?? []);
        setCompletionIndex(-1);
      } catch (reason) {
        if (!(reason instanceof DOMException && reason.name === "AbortError")) setCompletions([]);
      }
    }, 90);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [target, commandFocused, state?.workspace]);
  useEffect(() => {
    const describeFocus = () => {
      const activeElement = document.activeElement as HTMLElement | null;
      if (!activeElement || activeElement === document.body) { setFocusZone("cockpit"); return; }
      if (activeElement.closest("[role='dialog']")) setFocusZone("dialog");
      else if (activeElement === commandInputRef.current) setFocusZone("command");
      else setFocusZone(activeElement.closest(".panel")?.id ?? activeElement.getAttribute("aria-label") ?? "cockpit");
    };
    const deferDescribeFocus = () => window.requestAnimationFrame(describeFocus);
    document.addEventListener("focusin", describeFocus);
    document.addEventListener("focusout", deferDescribeFocus);
    describeFocus();
    return () => {
      document.removeEventListener("focusin", describeFocus);
      document.removeEventListener("focusout", deferDescribeFocus);
    };
  }, []);
  useEffect(() => {
    const show = (element: HTMLElement) => {
      const text = element.dataset.tooltip;
      if (!text) return;
      const rect = element.getBoundingClientRect();
      const width = Math.min(320, window.innerWidth - 24);
      const left = Math.min(window.innerWidth - width / 2 - 12, Math.max(width / 2 + 12, rect.left + rect.width / 2));
      const below = rect.top < 100;
      setTooltip({ text, left, top: below ? rect.bottom + 10 : rect.top - 10, below });
    };
    const enter = (event: Event) => { const element = (event.target as HTMLElement | null)?.closest<HTMLElement>("[data-tooltip]"); if (element) show(element); };
    const leave = (event: Event) => {
      const from = (event.target as HTMLElement | null)?.closest<HTMLElement>("[data-tooltip]");
      const to = (event as FocusEvent).relatedTarget as HTMLElement | null;
      if (from && !to?.closest("[data-tooltip]")?.isSameNode(from)) setTooltip(null);
    };
    const clear = () => setTooltip(null);
    document.addEventListener("pointerover", enter);
    document.addEventListener("pointerout", leave);
    document.addEventListener("focusin", enter);
    document.addEventListener("focusout", leave);
    window.addEventListener("resize", clear);
    window.addEventListener("scroll", clear, true);
    return () => {
      document.removeEventListener("pointerover", enter);
      document.removeEventListener("pointerout", leave);
      document.removeEventListener("focusin", enter);
      document.removeEventListener("focusout", leave);
      window.removeEventListener("resize", clear);
      window.removeEventListener("scroll", clear, true);
    };
  }, []);
  useEffect(() => { const key = (event: KeyboardEvent) => {
    const activeElement = document.activeElement as HTMLElement | null;
    const editing = !!activeElement && (activeElement.matches("input, textarea, select") || activeElement.isContentEditable);
    if (event.key === "Escape") {
      setCompletions([]);
      if (modalOpen) { closeOverlays(); closeCommandResult(); }
      else { setMaximized(null); activeElement?.blur(); cockpitRef.current?.focus({ preventScroll: true }); }
      return;
    }
    if (modalOpen) return;
    if (event.key === "F6") {
      event.preventDefault();
      if (activeElement === commandInputRef.current) cockpitRef.current?.focus({ preventScroll: true });
      else commandInputRef.current?.focus();
    } else if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); openOverlay("palette"); }
    else if (event.key === "/" && !editing) { event.preventDefault(); commandInputRef.current?.focus(); }
    else if (event.key === "?" && (!editing || (activeElement === commandInputRef.current && !target))) { event.preventDefault(); openOverlay("help"); }
  }; window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key); }, [modalOpen, target, commandResult, detail]);
  useEffect(() => { const restore = () => { if (!window.location.hash.startsWith("#evidence=")) { setDetail(null); requestAnimationFrame(() => detailOrigin.current?.focus()); } const pane = new URL(window.location.href).searchParams.get("pane"); if (pane && paneIds.includes(pane as typeof paneIds[number])) document.getElementById(pane)?.scrollIntoView({ behavior: "auto", block: "center" }); }; restore(); window.addEventListener("popstate", restore); return () => window.removeEventListener("popstate", restore); }, []);
  useEffect(() => { if (!(detail || help || alertsOpen || palette || dojo || commandResult)) return; const root = dialogRef.current; const focusable = root?.querySelectorAll<HTMLElement>("button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [href], [tabindex]:not([tabindex='-1'])"); (root?.querySelector<HTMLElement>("[data-initial-focus]") ?? focusable?.[0])?.focus(); const trap = (event: KeyboardEvent) => { if (event.key !== "Tab" || !focusable?.length) return; const first = focusable[0]; const last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } }; window.addEventListener("keydown", trap); return () => window.removeEventListener("keydown", trap); }, [detail, help, alertsOpen, palette, dojo, commandResult]);
  useEffect(() => {
    const cockpit = cockpitRef.current;
    if (!cockpit || !modalOpen) return;
    const background = [...cockpit.children].filter((node) => !(node as HTMLElement).matches(".modal-backdrop,.detail-backdrop"));
    for (const node of background) {
      const element = node as HTMLElement;
      element.inert = true;
      element.setAttribute("aria-hidden", "true");
    }
    return () => {
      for (const node of background) {
        const element = node as HTMLElement;
        element.inert = false;
        element.removeAttribute("aria-hidden");
      }
    };
  }, [modalOpen]);

  const mode = state?.modes.find((item) => item.name === state.character) ?? state?.modes[0];
  const theme = paletteFor(state?.character, displayMode, contrast);
  const style = { "--line": theme.border_color, "--accent": theme.accent_color, "--heading": theme.heading_color, "--ink": theme.text_color, "--dim": theme.dim_color, "--base": theme.base, "--surface": theme.surface, "--elevated": theme.elevated, "--control": theme.control, "--focus-ring": theme.focus, "--shadow": theme.shadow, colorScheme: displayMode } as CSSProperties;
  const dossier = state?.dossier_slots.filter((slot) => slot.status === "filled").length ?? 0;
  const dossierProgress = state?.dossier_slots.filter((slot) => slot.status === "filled" || slot.status === "partial").length ?? 0;
  const configuredSources = state?.instruments.sources.configured ?? 0;
  const taskGroups = useMemo(() => groupTasks(feed), [feed]);
  const processedTargets = useMemo(() => new Set(state?.processed_targets ?? []), [state?.processed_targets]);

  function closeOverlays() { if (detail) closeDetail(); setPalette(false); setHelp(false); setAlertsOpen(false); setDojo(false); setMenu(false); requestAnimationFrame(() => overlayOrigin.current?.focus()); }
  function openOverlay(kind: "help" | "palette" | "alerts" | "dojo", origin?: HTMLElement) { overlayOrigin.current = origin ?? document.activeElement as HTMLElement; setHelp(kind === "help"); setPalette(kind === "palette"); setAlertsOpen(kind === "alerts"); setDojo(kind === "dojo"); setMenu(false); }
  function closeCommandResult() { if (!commandResult) return; setCommandResult(null); requestAnimationFrame(() => overlayOrigin.current?.focus()); }
  function togglePane(id: PaneId) { setCollapsed((current) => { const next = { ...current, [id]: !current[id] }; window.localStorage.setItem("pivotglass.panes", JSON.stringify(next)); return next; }); }

  async function switchMode(name: string) {
    const response = await fetch("/api/mode", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
    const result = await response.json();
    if (!response.ok) { setError(result.error ?? "Mode switch failed"); return; }
    audioRef.current?.setCharacter(result.character ?? name);
    setState(result); setMenu(false);
  }

  async function investigate(event: FormEvent) {
    event.preventDefault(); const value = target.trim(); if (!value || !state) return;
    setError(""); setActive(true);
    try {
      const response = await fetch("/api/command", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ command: value }) });
      const result = await response.json() as CommandResult & { error?: string }; if (!response.ok) throw new Error(result.error ?? "Command failed");
      if (result.kind === "investigation" && result.snapshot) await followInvestigation(result.snapshot);
      else handleCommandResult(result);
      setTarget("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); } finally { setActive(false); setInvestigationId(null); }
  }

  async function followInvestigation(result: InvestigationSnapshot) {
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
  }

  function handleCommandResult(result: CommandResult) {
    if (result.state) { setState(result.state); audioRef.current?.setCharacter(result.state.character); }
    if (result.kind === "download" && result.content && result.filename) {
      const url = URL.createObjectURL(new Blob([result.content], { type: result.mime ?? "text/plain" }));
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = result.filename; anchor.click(); URL.revokeObjectURL(url); return;
    }
    if (result.kind === "client" && result.action === "clear") { setFeed([]); setCommandResult(null); return; }
    const activeOrigin = document.activeElement as HTMLElement | null;
    overlayOrigin.current = activeOrigin?.isConnected && activeOrigin !== document.body
      ? activeOrigin
      : document.querySelector<HTMLInputElement>('[aria-label="Investigation target"]');
    setCommandResult(result);
  }

  function queueIndicator(value?: string) {
    if (!value || !state?.workspace) return;
    setInvestigationQueue((current) => current.some((item) => item.target === value && ["pending", "running"].includes(item.status))
      ? current
      : [...current, { target: value, workspace: state.workspace, status: "pending", addedAt: new Date().toISOString() }]);
  }

  async function runQueuedItem(queueItem: QueueItem) {
    if (!state?.workspace || queueItem.workspace !== state.workspace) {
      setError(`Queue item belongs to workspace ${queueItem.workspace}; switch back before running it.`);
      return;
    }
    const targetValue = queueItem.target;
    setInvestigationQueue((current) => current.map((item) => item.addedAt === queueItem.addedAt ? {...item, status: "running", error: undefined} : item));
    setTarget(targetValue); setError(""); setActive(true);
    try {
      const response = await fetch("/api/command", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ command: `use ${targetValue}`, workspace: queueItem.workspace }) });
      const result = await response.json() as CommandResult & { error?: string }; if (!response.ok || !result.snapshot) throw new Error(result.error ?? "Indicator could not be queued");
      await followInvestigation(result.snapshot);
      setInvestigationQueue((current) => current.map((item) => item.addedAt === queueItem.addedAt ? {...item, status: "complete"} : item));
      await refresh();
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason);
      setError(message);
      setInvestigationQueue((current) => current.map((item) => item.addedAt === queueItem.addedAt ? {...item, status: "failed", error: message} : item));
    } finally { setActive(false); setInvestigationId(null); setTarget(""); }
  }

  async function runQueue(all = false) {
    if (active) return;
    const pending = investigationQueue.filter((item) => item.status === "pending");
    for (const item of (all ? pending : pending.slice(0, 1))) await runQueuedItem(item);
  }

  function moveQueue(addedAt: string, offset: number) {
    setInvestigationQueue((current) => {
      const index = current.findIndex((item) => item.addedAt === addedAt);
      const destination = Math.max(0, Math.min(current.length - 1, index + offset));
      if (index < 0 || index === destination) return current;
      const next = [...current];
      const item = next.splice(index, 1)[0]!;
      next.splice(destination, 0, item);
      return next;
    });
  }

  async function runQuick(command: string) {
    setError("");
    try {
      const response = await fetch("/api/command", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ command }) });
      const result = await response.json() as CommandResult & { error?: string }; if (!response.ok) throw new Error(result.error ?? "Command failed");
      handleCommandResult(result);
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
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
    setHelp(false); setPalette(false); setAlertsOpen(false); setDojo(false); setCommandResult(null);
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

  async function saveAnnotation() {
    if (!detail || !noteText.trim()) return;
    const response = await fetch("/api/annotate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: noteText.trim(), stix_id: detail.stix_id }) });
    if (response.ok) {
      setNoteText("");
      setDetail(null);
      setCommandResult({ kind: "text", title: "Annotation saved", text: `Linked to ${detail.reference}` });
    }
    else setError("Annotation could not be saved");
  }

  function jumpToAlert(alert: AlertEvent) {
    closeOverlays(); setExpandedTask(alert.tool ?? null);
    requestAnimationFrame(() => document.getElementById(`event-${alert.event_id}`)?.scrollIntoView({ behavior: effects === "full" ? "smooth" : "auto", block: "center" }));
  }

  function go(id: PaneId) { setActivePane(id); if (collapsed[id]) togglePane(id); const url = new URL(window.location.href); url.searchParams.set("pane", id); window.history.pushState({ pane: id }, "", url); requestAnimationFrame(() => { const panel = document.getElementById(id); panel?.scrollIntoView({ behavior: effects === "full" ? "smooth" : "auto", block: "center" }); panel?.focus({ preventScroll: true }); }); }

  function chooseCompletion(value: string) {
    setTarget(value);
    setCompletions([]);
    setCompletionIndex(-1);
    requestAnimationFrame(() => {
      commandInputRef.current?.focus();
      commandInputRef.current?.setSelectionRange(value.length, value.length);
    });
  }

  function commandKeyDown(event: ReactKeyboardEvent<HTMLInputElement>) {
    if (!completions.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setCompletionIndex((current) => (current + 1) % completions.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setCompletionIndex((current) => (current <= 0 ? completions.length - 1 : current - 1));
    } else if (event.key === "Tab" || (event.key === "Enter" && completionIndex >= 0)) {
      event.preventDefault();
      chooseCompletion(completions[Math.max(0, completionIndex)]!);
    }
  }

  function setEffectsPreference(value: "full" | "reduced" | "off") { setEffects(value); window.localStorage.setItem("pivotglass.effects", value); }
  function setNarrationPreference(value: "full" | "brief" | "off") { setNarration(value); window.localStorage.setItem("pivotglass.narration", value); }

  function stopMusic(savePreference = true) {
    const engine = audioRef.current;
    if (!engine) return;
    void engine.stop();
    audioRef.current = null;
    if (savePreference) {
      setMusic(false);
      window.localStorage.setItem("pivotglass.music.enabled", "false");
    }
  }

  function startMusic() {
    if (audioRef.current) return;
    const engine = new FlowMusicEngine(state?.character ?? "default", musicVolume);
    engine.setPhase(error ? "caution" : active ? "investigating" : feed.length ? "complete" : "idle"); engine.start(); audioRef.current = engine; setMusic(true);
    window.localStorage.setItem("pivotglass.music.enabled", "true");
  }

  function toggleMusic() { if (music) stopMusic(); else startMusic(); }

  const paletteCommands = [
    ...paneIds.map((id) => ({ label: `Go to ${id.replace("-", " ")}`, run: () => go(id) })),
    { label: "Open operator help", run: () => openOverlay("help") },
    { label: "Open Master Caution", run: () => openOverlay("alerts") },
    { label: `Open ${publicModeLabel(state?.character)} arcade`, run: () => openOverlay("dojo") },
    { label: "Mute visual effects", run: () => setEffectsPreference("off") },
    { label: "Reduce visual effects", run: () => setEffectsPreference("reduced") },
    { label: "Enable full visual effects", run: () => setEffectsPreference("full") },
    { label: music ? "Mute generative music" : "Enable generative music", run: toggleMusic },
    { label: "Show dossier and intelligence gaps", run: () => void runQuick("dossier") },
    { label: "Show relationship graph", run: () => void runQuick("graph") },
    { label: "Show collection timeline", run: () => void runQuick("timeline") },
    { label: "Generate printable report", run: () => void runQuick("report") },
    ...["json", "csv", "stix", "gexf"].map((format) => ({ label: `Export workspace as ${format.toUpperCase()}`, run: () => void runQuick(`export ${format}`) })),
    { label: "Show all analyst commands", run: () => void runQuick("help") },
  ].filter((command) => command.label.toLowerCase().includes(paletteQuery.toLowerCase()));

  function renderCommandData(result: CommandResult) {
    if (result.data === undefined) return null;
    if (result.kind === "graph" && result.data && typeof result.data === "object") {
      const graph = result.data as {
        nodes?: Array<{ id: string; type?: string; value?: string }>;
        edges?: Array<{ source: string; target: string; relationship?: string; basis?: string }>;
      };
      const nodes = graph.nodes ?? [];
      const values = new Map(nodes.map((node) => [node.id, node.value ?? "unavailable"]));
      return <section className="structured-result threat-graph-result"><header><b>{nodes.length} INDICATORS</b><span>{graph.edges?.length ?? 0} RELATIONSHIPS</span></header><div className="graph-node-list">{nodes.map((node) => <article key={node.id}><button title={`Open evidence for ${node.value}`} onClick={(event) => void openDetail(node.id, event.currentTarget)}><b>{shortenMiddle(node.value, 52)}</b><span>{node.type ?? "unknown type"}</span></button>{node.value && <button onClick={() => queueIndicator(node.value)}>+ QUEUE</button>}</article>)}</div><ol className="graph-edge-list">{(graph.edges ?? []).map((edge, index) => <li key={`${edge.source}-${edge.target}-${index}`}><button onClick={(event) => void openDetail(edge.source, event.currentTarget)}>{shortenMiddle(values.get(edge.source), 30)}</button><span>{edge.relationship ?? "related to"} · {edge.basis === "property" ? "property-derived pivot" : "explicit relationship"}</span><button onClick={(event) => void openDetail(edge.target, event.currentTarget)}>{shortenMiddle(values.get(edge.target), 30)}</button></li>)}</ol></section>;
    }
    let decoded = result.data;
    if (typeof decoded === "string") {
      const serialized = decoded;
      try { decoded = JSON.parse(serialized); } catch { return <pre>{serialized}</pre>; }
    }
    if (result.title?.includes("Dossier") && decoded && typeof decoded === "object") {
      const dossierData = decoded as { slots?: Record<string, { status?: string; evidence_count?: number }>; total_sco_count?: number; error?: string };
      if (dossierData.error) return <p className="error">{dossierData.error}</p>;
      return <section className="structured-result dossier-result"><header><b>INTELLIGENCE COVERAGE</b><span>{dossierData.total_sco_count ?? 0} STORED OBSERVABLES</span></header><div>{Object.entries(dossierData.slots ?? {}).map(([name, slot]) => <article key={name} className={`state-${slot.status ?? "empty"}`}><b>{name.replaceAll("_", " ")}</b><span>{slot.status ?? "empty"} · {slot.evidence_count ?? 0} evidence</span><button onClick={() => { closeCommandResult(); go("artifact-field"); }}>REVIEW EVIDENCE</button></article>)}</div></section>;
    }
    if (result.title?.includes("timeline") && Array.isArray(decoded)) {
      const runs = decoded as Array<Record<string, unknown>>;
      return <section className="structured-result timeline-result"><header><b>COLLECTION HISTORY</b><span>{runs.length} RUNS</span></header><ol>{runs.map((run, index) => <li key={`${String(run.timestamp ?? "")}-${index}`}><time>{String(run.timestamp ?? "time unavailable")}</time><b>{String(run.module_name ?? run.module ?? "unknown module")}</b><span>{shortenMiddle(String(run.target ?? "target unavailable"), 52)} · {String(run.result_count ?? 0)} results</span>{run.target != null && <button onClick={() => queueIndicator(String(run.target))}>QUEUE AGAIN</button>}</li>)}</ol></section>;
    }
    return <pre>{JSON.stringify(decoded, null, 2)}</pre>;
  }

  const selectedDossierSlot = state?.dossier_slots.find((slot) => slot.name === selectedFacet);

  return <main ref={cockpitRef} tabIndex={-1} style={style} className={`mode-${state?.character ?? "default"} effects-${effects} narration-${narration} display-${displayMode} contrast-${contrast} ${maximized ? `max-${maximized}` : ""}`}>
    <AmbientEnvironment character={state?.character ?? "default"} />
    <div className="scanline" />
    <header className="masthead">
      <button className="menu-button" onClick={() => setMenu(!menu)} aria-expanded={menu}>☰ <span>DECK</span></button>
      <div className="brand"><span className="eyebrow">{mode?.cockpit.deck_name ?? "HUNT CONTROL"} // LOCAL INTELLIGENCE SYSTEM</span><h1>PIVOTGLASS</h1><small>{mode?.cockpit.vehicle ?? "AP-01 PURSUIT DECK"}</small></div>
      <div className="status-cluster"><span className="lamp ok" /><span className={`lamp ${active ? "hot" : ""}`} /><span className={active ? "system-state pulse" : "system-state"}>{active ? "HUNT ACTIVE" : "SYSTEM READY"}</span><span className="focus-status" aria-live="polite">FOCUS · {focusZone.toUpperCase()}</span>{reviewingHistory && alerts.unread_count > 0 && <button className="unread-badge" onClick={(event) => openOverlay("alerts", event.currentTarget)}>{alerts.highest_unread.toUpperCase()} · {alerts.unread_count} UNREAD</button>}<button className="help-button" onClick={(event) => openOverlay("help", event.currentTarget)}>HELP ?</button></div>
      {menu && <nav className="deck-menu" aria-label="Cockpit navigation">{paneIds.map((id) => <button key={id} onClick={() => { go(id); setMenu(false); }}>{id.replace("-", " ")}</button>)}<hr/><label>DAY / NIGHT</label><div className="segmented display-choice">{(["night", "day"] as const).map((value) => <button className={displayMode === value ? "selected" : ""} key={value} onClick={() => { setDisplayMode(value); window.localStorage.setItem("pivotglass.display", value); }}>{value}</button>)}</div><label>CONTRAST</label><div className="segmented">{(["soft", "normal", "high"] as const).map((value) => <button className={contrast === value ? "selected" : ""} key={value} onClick={() => { setContrast(value); window.localStorage.setItem("pivotglass.contrast", value); }}>{value}</button>)}</div><label>VISUAL EFFECTS</label><div className="segmented">{(["full", "reduced", "off"] as const).map((value) => <button className={effects === value ? "selected" : ""} key={value} onClick={() => setEffectsPreference(value)}>{value}</button>)}</div><label>NARRATION</label><div className="segmented">{(["full", "brief", "off"] as const).map((value) => <button className={narration === value ? "selected" : ""} key={value} onClick={() => setNarrationPreference(value)}>{value}</button>)}</div><label>GENERATIVE MUSIC · OFF BY DEFAULT</label><button className={music ? "selected" : ""} onClick={toggleMusic}>{music ? "MUTE MUSIC" : "ENABLE MUSIC"}</button><input type="range" min="0" max="100" value={musicVolume} onChange={(event) => setMusicVolume(Number(event.target.value))} aria-label="Music volume"/><hr/><label>CHARACTER VOICE</label>{publicModes(state?.modes).map(({ mode: item, label }) => <button className={item.name === state?.character ? "selected" : ""} key={item.name} onClick={() => switchMode(item.name)}><b>{label}</b><small>{item.personality}</small></button>)}</nav>}
    </header>

    <nav className="pane-switcher" aria-label="Primary cockpit panes">{paneIds.map((id) => <button key={id} aria-current={activePane === id ? "page" : undefined} title={`Open and focus ${id.replace("-", " ")} pane`} onClick={() => go(id)}>{id.replace("-", " ")}</button>)}<button title="Use the active pane at full viewport size" onClick={() => setMaximized((value) => value === activePane ? null : activePane)}>{maximized ? "RESTORE VIEW" : "MAXIMIZE PANE"}</button><button title="Search all cockpit commands" onClick={(event) => openOverlay("palette", event.currentTarget)}>COMMANDS ⌘K</button><button title="Open optional theme arcade" onClick={(event) => openOverlay("dojo", event.currentTarget)}>THEME ARCADE</button></nav>

    <section className="voice-strip"><b>{publicModeLabel(state?.character).toUpperCase()}</b><span>{mode?.greeting || "Cockpit link established."}</span><i>{mode?.pursuit_title ?? "THE HUNT"}</i></section>

    <section className={`command-rail ${commandFocused ? "has-focus" : ""}`}><form onSubmit={investigate}><span className="prompt">glass://command</span><div className="command-combobox"><input ref={commandInputRef} value={target} onChange={(event) => setTarget(event.target.value)} onFocus={() => setCommandFocused(true)} onBlur={() => window.setTimeout(() => setCommandFocused(false), 120)} onKeyDown={commandKeyDown} placeholder="indicator, command, search, or analyst question" aria-label="Investigation target" role="combobox" aria-autocomplete="list" aria-expanded={commandFocused && completions.length > 0} aria-controls="command-completions" aria-activedescendant={completionIndex >= 0 ? `completion-${completionIndex}` : undefined}/>{commandFocused && completions.length > 0 && <div id="command-completions" className="command-completions" role="listbox">{completions.slice(0, 10).map((completion, index) => <button type="button" role="option" id={`completion-${index}`} aria-selected={completionIndex === index} className={completionIndex === index ? "selected" : ""} key={completion} onMouseDown={(event) => event.preventDefault()} onClick={() => chooseCompletion(completion)}><b>{completion}</b></button>)}</div>}</div><button disabled={active}>{active ? `WORKING ${elapsed}s` : "EXECUTE"}</button>{active && investigationId && <button type="button" className="cancel" onClick={cancelInvestigation}>CANCEL</button>}</form>{error && <div className="error">⚠ FAULT · {error}</div>}<small className="command-hint">Tab completes · / focuses command · F6 moves focus · ? opens help when the command is empty</small>{investigationQueue.length > 0 && <section className="investigation-queue" aria-label={`Investigation queue for ${state?.workspace ?? "current workspace"}`}><header><b>INVESTIGATION QUEUE · {state?.workspace}</b><span>{investigationQueue.filter((item) => item.status === "pending").length} PENDING</span><button disabled={active || !investigationQueue.some((item) => item.status === "pending")} onClick={() => void runQueue(false)}>RUN NEXT</button><button disabled={active || !investigationQueue.some((item) => item.status === "pending")} onClick={() => void runQueue(true)}>RUN ALL</button><button disabled={active} onClick={() => setInvestigationQueue((current) => current.filter((item) => item.status === "pending" || item.status === "running"))}>CLEAR FINISHED</button></header><ol>{investigationQueue.map((item, index) => <li key={`${item.target}-${item.addedAt}`}><span className={`queue-state ${item.status}`}>{item.status}</span><b title={`${item.target} · workspace ${item.workspace}`}>{shortenMiddle(item.target, 48)}</b>{item.error && <small>{item.error}</small>}<div><button disabled={active || index === 0} onClick={() => moveQueue(item.addedAt, -1)} aria-label={`Move ${item.target} earlier`}>↑</button><button disabled={active || index === investigationQueue.length - 1} onClick={() => moveQueue(item.addedAt, 1)} aria-label={`Move ${item.target} later`}>↓</button><button disabled={active || item.status === "running"} onClick={() => setInvestigationQueue((current) => current.filter((candidate) => candidate !== item))}>REMOVE</button>{item.status === "failed" && <button disabled={active} onClick={() => setInvestigationQueue((current) => current.map((candidate) => candidate === item ? {...candidate, status: "pending", error: undefined} : candidate))}>RETRY</button>}</div></li>)}</ol></section>}</section>

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
        {taskGroups.filter((task) => expandedTask === task.key).map((task) => <section className="task-detail" id={`task-${task.key}`} key={task.key}><header><div><b>{task.tool}</b><small>{task.events.length} ordered transitions · {task.artifacts.length} evidence records</small></div><button onClick={() => setExpandedTask(null)}>COLLAPSE</button></header>{task.events.map((item) => <section id={`event-${item.event_id}`} className={`event ${item.content_class} state-${item.lifecycle} class-${item.event_class}`} key={item.event_id}><div className="event-head"><b>{item.lifecycle.toUpperCase()}</b><span>{item.source ?? item.event_class}</span></div><small>{item.tool} · event {item.sequence}</small>{item.briefing && <><p><label>GATHER</label>{item.briefing.artifacts}</p><p><label>WHY</label>{item.briefing.purpose}</p><p><label>WATCH</label>{item.briefing.watch_for}</p><small>Retrieval goal—not an observed finding.</small></>}{item.summary && <pre>{item.summary}</pre>}{item.reason && <p><label>STATE</label>{item.reason}</p>}{item.artifact_ids?.map((id) => { const artifact = state?.objects.find((candidate) => candidate.reference === id || candidate.stix_id === id); return <button className="evidence-link" title={artifact?.value ?? "Open stored evidence"} key={id} onClick={(event) => openDetail(id, event.currentTarget)}>OPEN {shortenMiddle(artifact?.value ?? "stored evidence", 44)}</button>; })}</section>)}</section>)}
      </div></article>

      <aside className="right-stack">
        <article className={`panel instruments ${collapsed.dossier ? "collapsed" : ""}`} id="dossier" tabIndex={-1}><PanelTitle id="dossier" title={mode?.cockpit.hud_title ?? "TACTICAL HUD"} status={`${dossier}/9 FACETS`} collapsed={collapsed.dossier} onToggle={() => togglePane("dossier")}/><div id="dossier-content" className="panel-content"><dl><div><dt>WORKSPACE</dt><dd>{state?.workspace ?? "—"}</dd></div><div><dt>CHARACTER</dt><dd>{publicModeLabel(state?.character)}</dd></div><div><dt>ARTIFACTS</dt><dd>{state?.objects.length ?? 0}</dd></div><div><dt>DOSSIER</dt><dd>{dossier}/9 FILLED</dd></div></dl><div className="dossier-object" aria-label={`${dossier} of 9 dossier facets filled`}><div className="dossier-core"><b>DOSSIER</b><span>{dossierProgress}/9 mapped</span></div><div className="dossier-facets">{(state?.dossier_slots ?? Array.from({length: 9}, (_, index) => ({name: `slot ${index + 1}`, status: "empty" as const, evidence_count: 0}))).map((slot, index) => <button className={`${slot.status} ${selectedFacet === slot.name ? "selected" : ""}`} key={slot.name} data-tooltip={`${slot.name.replaceAll("_", " ")}: ${slot.status}, ${slot.evidence_count} source-backed puzzle pieces. Click to inspect this plane.`} onClick={() => setSelectedFacet((current) => current === slot.name ? null : slot.name)} aria-pressed={selectedFacet === slot.name} aria-label={`${slot.name}: ${slot.status}, ${slot.evidence_count} evidence. Inspect dossier facet.`}><span>{index + 1}</span><small>{slot.name.replaceAll("_", " ")}</small></button>)}</div></div>{selectedDossierSlot && <section className="facet-evidence"><header><b>{selectedDossierSlot.name.replaceAll("_", " ").toUpperCase()}</b><button onClick={() => setSelectedFacet(null)}>CLOSE</button></header><p>{selectedDossierSlot.evidence_count} source-backed puzzle pieces contribute to this plane.</p>{selectedDossierSlot.evidence?.length ? <div>{selectedDossierSlot.evidence.map((item) => <button key={item.reference} onClick={(event) => void openDetail(item.reference, event.currentTarget)}><b title={item.value}>{shortenMiddle(item.value, 38)}</b><span>{item.type}</span></button>)}</div> : <small>No directly attributable stored evidence yet.</small>}</section>}</div></article>
        <article className={`panel chart-panel ${collapsed["artifact-field"] ? "collapsed" : ""}`} id="artifact-field" tabIndex={-1}><PanelTitle id="artifact-field" title="ARTIFACT FIELD" status="FLINT / CHART.JS" collapsed={collapsed["artifact-field"]} onToggle={() => togglePane("artifact-field")}/><div id="artifact-field-content" className="panel-content"><DistributionChart objects={state?.objects ?? []} theme={theme}/><GeoMap objects={state?.objects ?? []}/><div className="artifact-list">{state?.objects.slice(-12).map((item) => { const queued = investigationQueue.some((entry) => entry.target === item.value && ["pending", "running"].includes(entry.status)); return <div className="artifact-row" key={item.reference} data-tooltip={`${item.value} · ${item.type} · ${item.country ? `source-backed location ${item.country}` : "location unknown"} · ${queued ? "already queued" : processedTargets.has(item.value ?? "") ? "processed previously; queue to re-run" : "new; click queue to investigate"}`}><button title={`${item.value} · ${item.country ?? "location unknown"} · open provenance`} onClick={(event) => openDetail(item.reference, event.currentTarget)}><b>{flag(item.country)} {item.known_malware ? "☠️ " : ""}{shortenMiddle(item.value)}</b><span>{item.type} · {queued ? "queued" : processedTargets.has(item.value ?? "") ? "processed" : "new"}</span></button><button className="queue-indicator" onClick={() => queueIndicator(item.value)} disabled={queued} title={queued ? "Already queued" : processedTargets.has(item.value ?? "") ? "Queue a fresh investigation" : "Queue this indicator for investigation"}>{queued ? "✓ QUEUED" : processedTargets.has(item.value ?? "") ? "↻ QUEUE AGAIN" : "+ QUEUE"}</button></div>; })}</div></div></article>
        <article className="panel alert-panel"><div className="panel-title"><button title="Open persistent attention records" onClick={(event) => openOverlay("alerts", event.currentTarget)}>MASTER CAUTION</button><small>{error ? "FAULT" : alerts.unread_count ? `${alerts.unread_count} UNREAD · ${alerts.highest_unread.toUpperCase()}` : "CLEAR"}</small></div><p>{error ? error : alerts.unread_count ? "Attention records are waiting. Open Master Caution to inspect and acknowledge them." : active ? "Probe activity underway. Retrieval briefings are prospective until evidence arrives." : "No unacknowledged attention records."}</p></article>
      </aside>
    </section>

    <footer><span>EVIDENCE ≠ INFERENCE</span><span>LOCALHOST · NO TELEMETRY · OPERATOR CONTROLLED</span><button title="Open contextual operator help" onClick={(event) => openOverlay("help", event.currentTarget)}>HELP ?</button></footer>
    {help && <div className="modal-backdrop" onMouseDown={closeOverlays}><section ref={dialogRef} className="help-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="help-heading"><button className="close" aria-label="Close help" onClick={closeOverlays}>×</button><span className="eyebrow">PIVOTGLASS FIELD MANUAL · {activePane.replace("-", " ").toUpperCase()}</span><h2 id="help-heading" tabIndex={-1}>WHAT DO YOU WANT TO DO?</h2><div className="help-tasks"><button onClick={() => { closeOverlays(); document.querySelector<HTMLInputElement>('[aria-label="Investigation target"]')?.focus(); }}><b>START A HUNT</b><span>Focus the target field. Enter a domain, IP, URL, email, or hash, then choose EXECUTE.</span><kbd>RETURN</kbd></button><button onClick={() => { closeOverlays(); go("intelligence"); }}><b>REVIEW PROBES</b><span>Select a 3×3 task pixel to open its ordered transitions and evidence links.</span><kbd>CLICK / ENTER</kbd></button><button onClick={() => { closeOverlays(); go("artifact-field"); }}><b>DRILL INTO EVIDENCE</b><span>Open an artifact to inspect provenance, normalized fields, and the safe raw record.</span><kbd>CLICK / ENTER</kbd></button><button onClick={() => { closeOverlays(); openOverlay("palette"); }}><b>FIND A CONTROL</b><span>Search pane, effects, narration, audio, alert, and character commands.</span><kbd>⌘/CTRL K</kbd></button></div><dl className="keymap"><div><dt>?</dt><dd>Help when command is empty</dd></div><div><dt>/</dt><dd>Focus command input</dd></div><div><dt>F6</dt><dd>Move between command and cockpit</dd></div><div><dt>ESC</dt><dd>Close dialog or return focus to cockpit</dd></div><div><dt>TAB</dt><dd>Complete a command or move controls</dd></div></dl><p className="truth-note"><b>Reading the display:</b> queued/running describe retrieval state; succeeded means the tool completed, not that a claim is true. Evidence is observed tool output. Narration is interpretation and remains labeled separately.</p><small>Help is contextual to the active pane. Actions above perform the route they describe.</small></section></div>}
    {detail && <div className="detail-backdrop" onMouseDown={closeDetail}><aside ref={dialogRef} className="detail-drawer" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label={`Evidence ${detail.value}`}><button className="close" onClick={closeDetail}>×</button><span className="eyebrow">INDICATOR DETAIL · STORED LOCAL DATA</span><h2 title={detail.value}>{shortenMiddle(detail.value, 72)}</h2><button className="queue-detail" onClick={() => void queueIndicator(detail.value)} disabled={active}>+ QUEUE FOR INVESTIGATION</button><dl><div><dt>TYPE</dt><dd>{detail.type}</dd></div><div><dt>FULL INDICATOR</dt><dd>{detail.value}</dd></div><div><dt>PURPOSE / ROLE</dt><dd>{detail.purpose.join(" · ")}</dd></div><div><dt>SOURCE MODULE</dt><dd>{detail.source_module}</dd></div><div><dt>ORIGINAL QUERY</dt><dd>{detail.original_query}</dd></div></dl>{detail.source_intelligence && <section className="source-intelligence"><header><div><span>SOURCE INTELLIGENCE</span><h3>{detail.source_intelligence.provider}</h3></div><b>{detail.source_intelligence.headline}</b></header><dl>{detail.source_intelligence.facts.map((fact) => <div key={fact.label}><dt>{fact.label}</dt><dd>{typeof fact.value === "string" || typeof fact.value === "number" || typeof fact.value === "boolean" ? String(fact.value) : <code>{JSON.stringify(fact.value)}</code>}</dd></div>)}</dl>{detail.source_intelligence.links.length > 0 && <nav aria-label={`${detail.source_intelligence.provider} external evidence links`}>{detail.source_intelligence.links.map((link) => <a href={link.url} target="_blank" rel="noreferrer" key={`${link.label}-${link.url}`}>{link.label} ↗</a>)}</nav>}{detail.source_intelligence.groups.map((group) => <details key={group.title}><summary>{group.title}</summary><pre>{JSON.stringify(group.items, null, 2)}</pre></details>)}</section>}<h3>DISCOVERY BREADCRUMBS</h3><ol className="breadcrumbs">{detail.breadcrumbs.map((crumb, index) => <li key={`${crumb.indicator}-${index}`}><b>{crumb.indicator}</b><span>{crumb.relationship}</span></li>)}</ol><h3>RELATIONSHIPS</h3>{detail.relationships.length ? <ol className="relationship-list">{detail.relationships.map((relation, index) => <li key={`${relation.indicator}-${index}`}><span>{relation.direction ?? "related"} · {relation.relationship ?? "related to"}{relation.basis ? ` · ${relation.basis}` : ""}</span><b title={relation.indicator}>{shortenMiddle(relation.indicator, 48)}</b><div>{relation.reference && <button onClick={(event) => void openDetail(relation.reference!, event.currentTarget)}>OPEN DETAIL</button>}{relation.indicator && relation.indicator !== "unavailable" && <button onClick={() => queueIndicator(relation.indicator)}>+ QUEUE</button>}</div></li>)}</ol> : <p>No explicit relationship stored.</p>}<h3>HISTORICAL COLLECTION</h3><pre>{detail.history.length ? JSON.stringify(detail.history, null, 2) : "No matching module run recorded."}</pre><h3>PROVENANCE</h3><pre>{JSON.stringify(detail.provenance, null, 2)}</pre><h3>NORMALIZED FIELDS</h3><pre>{JSON.stringify(detail.normalized, null, 2)}</pre><h3>DOSSIER CONTRIBUTIONS</h3><pre>{detail.dossier_contributions.length ? JSON.stringify(detail.dossier_contributions, null, 2) : "unavailable"}</pre><h3>ANALYST ANNOTATION</h3><div className="annotation-editor"><textarea value={noteText} onChange={(event) => setNoteText(event.target.value)} placeholder="Record a sourced observation, hypothesis, or collection note"/><button onClick={() => void saveAnnotation()} disabled={!noteText.trim()}>SAVE LINKED NOTE</button></div><h3>SAFE RAW RECORD</h3><pre>{JSON.stringify(detail.raw, null, 2)}</pre><small>Opened from stored evidence. Backend identifiers remain hidden; no network service or model was invoked.</small></aside></div>}
    {alertsOpen && <div className="modal-backdrop" onMouseDown={closeOverlays}><section ref={dialogRef} className="alert-queue" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Master caution alerts"><button className="close" aria-label="Close alerts" onClick={closeOverlays}>×</button><span className="eyebrow">PERSISTENT ATTENTION RECORD</span><h2>MASTER CAUTION</h2>{alerts.alerts.length === 0 && <p>No attention records.</p>}{alerts.alerts.map((alert) => <article className={alert.acknowledged ? "acknowledged" : ""} key={alert.event_id}><header><b>{alert.event_class.replaceAll("_", " ").toUpperCase()}</b><span>{alert.severity.toUpperCase()} · {alert.acknowledged ? "ACKNOWLEDGED" : "UNREAD"}</span></header><p>{alert.summary ?? alert.reason ?? alert.source}</p><div><button onClick={() => jumpToAlert(alert)}>ORIGIN</button>{!alert.acknowledged && <button onClick={() => acknowledge(alert.event_id)}>ACKNOWLEDGE</button>}{alert.artifact_ids?.map((id) => <button key={id} onClick={(event) => openDetail(id, event.currentTarget)}>DETAILS</button>)}</div></article>)}</section></div>}
    {palette && <div className="modal-backdrop" onMouseDown={closeOverlays}><section ref={dialogRef} className="command-palette" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Command palette"><input autoFocus value={paletteQuery} onChange={(event) => setPaletteQuery(event.target.value)} placeholder="Search cockpit commands" aria-label="Search cockpit commands"/>{paletteCommands.map((command) => <button key={command.label} onClick={() => { command.run(); setPalette(false); setPaletteQuery(""); }}>{command.label}</button>)}</section></div>}
    {commandResult && <div className="modal-backdrop command-result-backdrop" onMouseDown={closeCommandResult}><section ref={dialogRef} className="command-result" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label={commandResult.title ?? "Command result"}><button className="close" aria-label="Close command result" onClick={closeCommandResult}>×</button><span className="eyebrow">{commandResult.synthesized ? "MODEL SYNTHESIS · VERIFY AGAINST EVIDENCE" : "DETERMINISTIC WORKSPACE RESULT"}</span><h2>{commandResult.title ?? "ANALYST COMMANDS"}</h2>{commandResult.text && <pre>{commandResult.text}</pre>}{renderCommandData(commandResult)}{commandResult.commands && <div className="command-reference">{commandResult.commands.map((item) => <button key={item.command} onClick={() => { setTarget(item.command.replace(/ <.*$/, " ")); setCommandResult(null); document.querySelector<HTMLInputElement>('[aria-label="Investigation target"]')?.focus(); }}><b>{item.command}</b><span>{item.purpose}</span></button>)}</div>}{commandResult.printable && <button className="print-action" onClick={() => window.print()}>PRINT / SAVE PDF</button>}</section></div>}
    {dojo && <div className="modal-backdrop" onMouseDown={closeOverlays}><section ref={dialogRef} onMouseDown={(event) => event.stopPropagation()}><ThemeArcade character={state?.character ?? "sensei"} onClose={closeOverlays} reduced={effects !== "full"}/></section></div>}
    {tooltip && <div className={`viewport-tooltip ${tooltip.below ? "below" : "above"}`} role="tooltip" style={{ left: tooltip.left, top: tooltip.top }}>{tooltip.text}</div>}
  </main>;
}
