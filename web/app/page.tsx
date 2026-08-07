"use client";

import { CSSProperties, FormEvent, KeyboardEvent as ReactKeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { characterGuidance, type CharacterGuidance, type GuidanceCandidate } from "./character-guidance";
import { AdvisorPortal, CharacterAdvisorArtwork, speakCharacterNarration, stopCharacterNarration } from "./character-advisor";
import { BadgeArtwork } from "./badge-artwork";
import { FlowMusicEngine } from "./flow-music";
import { ThemeArcade } from "./arcade-games";
import { ConfigurationCenter, type ConfigurationAdvisory } from "./configuration-center";
import { ScientificWorkbench, type AnalyticSnapshot } from "./scientific-workbench";
import { type VisualizationIntent } from "./visualization-intent";
import { TaskMatrix, VisualizationWorkspace } from "./visualization-workspace";

type Briefing = { source: string; artifacts: string; purpose: string; watch_for: string };
type Lifecycle = "planned" | "queued" | "running" | "succeeded" | "empty" | "failed" | "skipped" | "cancelled";
type FeedEvent = { event_id: string; sequence: number; event_class: string; severity: string; lifecycle: Lifecycle; content_class: "evidence" | "narration" | "system"; created_at?: string; updated_at?: string; tool?: string; source?: string; briefing?: Briefing; summary?: string; reason?: string; result_count?: number; artifact_ids?: string[]; actions?: string[] };
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
type BadgeAward = { badge_id: string; badge_name: string; badge_description?: string; badge_rarity?: string; badge_artwork?: string; badge_glyph?: string; challenge_id?: string; awarded_at: string };
type ChallengeRecord = { id: string; name: string; description: string; status: string; origin?: string; subject_value?: string; points: number; progress_current?: number; progress_target?: number; progress_label?: string; evidence_basis?: Array<Record<string, unknown>>; badge?: BadgeAward };
type State = { workspace: string; stats: Record<string, number>; objects: EvidenceCard[]; briefings: Record<string, Briefing>; character: string; modes: Mode[]; dossier_slots: DossierSlot[]; visualizations: VisualizationIntent[]; analysis: AnalyticSnapshot; processed_targets: string[]; instruments: Instruments; challenges: ChallengeRecord[]; badges: BadgeAward[]; badge_summary: { count: number; latest: BadgeAward | null } };
type InvestigationSnapshot = { investigation_id: string; lifecycle: Lifecycle; cursor: number; events: FeedEvent[] };
type AlertEvent = FeedEvent & { acknowledged: boolean; investigation_id: string };
type AlertState = { alerts: AlertEvent[]; unread_count: number; highest_unread: string };
type CommandResult = { kind: string; title?: string; text?: string; data?: unknown; commands?: Array<{ command: string; purpose: string }>; snapshot?: InvestigationSnapshot; state?: State; filename?: string; mime?: string; content?: string; printable?: boolean; synthesized?: boolean; action?: string };

const paneIds = ["intelligence", "dossier", "artifact-field", "systems"] as const;
type PaneId = typeof paneIds[number];
const PANE_LABELS: Record<PaneId, string> = {
  intelligence: "intelligence",
  dossier: "dossier",
  "artifact-field": "visual analysis",
  systems: "systems",
};
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

function guidanceCandidates(state: State, alerts: AlertState): GuidanceCandidate[] {
  const candidates: GuidanceCandidate[] = [];
  if (alerts.unread_count > 0) candidates.push({
    category: "attention",
    idea: `${alerts.unread_count} attention record${alerts.unread_count === 1 ? " is" : "s are"} waiting for review. Resolve the interruption before it becomes background noise.`,
    action: "alerts", actionLabel: "REVIEW ATTENTION", value: "alerts",
  });
  if (state.objects.length === 0) candidates.push({
    category: "investigation",
    idea: "Start with one concrete indicator or an analyst question, then let each sourced result earn the next pivot.",
    action: "focus", actionLabel: "START A PURSUIT", value: "",
  });
  const gaps = state.dossier_slots.filter((slot) => slot.status === "empty" || slot.status === "partial").length;
  if (state.objects.length > 0 && gaps > 0) candidates.push({
    category: "dossier",
    idea: `${gaps} Dossier dimension${gaps === 1 ? " still has" : "s still have"} gaps. Inspect the weakest facet and choose an enrichment that could actually change it.`,
    action: "pane", actionLabel: "OPEN DOSSIER", value: "dossier",
  });
  const constellation = state.visualizations.find((intent) => intent.intent_id === "indicator-constellation");
  if ((constellation?.data.rows.length ?? 0) > 0) candidates.push({
    category: "visualization",
    idea: "Compare the RGB Constellation rows. A dark column across related indicators is a collection gap; an isolated bright cell may be the clue worth testing.",
    action: "pane", actionLabel: "OPEN CONSTELLATION", value: "artifact-field",
  });
  if (state.challenges.some((challenge) => challenge.status !== "completed")) candidates.push({
    category: "challenge",
    idea: "A pursuit challenge is still open. Use it as a testable next objective, not as a substitute for analytical judgment.",
    action: "command", actionLabel: "SHOW CHALLENGES", value: "challenges",
  });
  return candidates;
}

function PanelTitle({ id, title, status, collapsed, maximized = false, onToggle, onMaximize }: { id: string; title: string; status: string; collapsed: boolean; maximized?: boolean; onToggle: () => void; onMaximize?: () => void }) {
  return <div className="panel-title"><span>{title}</span><span className="panel-actions"><small>{status}</small>{onMaximize && <button className="collapse-button" onClick={onMaximize} title={`${maximized ? "Restore" : "Maximize"} ${title}`}>{maximized ? "↙ RESTORE" : "↗ MAX"}</button>}<button className="collapse-button" onClick={onToggle} aria-expanded={!collapsed} aria-controls={`${id}-content`} title={`${collapsed ? "Expand" : "Collapse"} ${title}`}>{collapsed ? "▸ EXPAND" : "▾ COLLAPSE"}</button></span></div>;
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
  const [voiceAudio, setVoiceAudio] = useState(false);
  const [music, setMusic] = useState(false);
  const [musicVolume, setMusicVolume] = useState(18);
  const [displayMode, setDisplayMode] = useState<DisplayMode>("night");
  const [contrast, setContrast] = useState<ContrastMode>("normal");
  const [collapsed, setCollapsed] = useState<Record<PaneId, boolean>>({ intelligence: false, dossier: false, "artifact-field": false, systems: true });
  const [activePane, setActivePane] = useState<PaneId>("intelligence");
  const [expandedTask, setExpandedTask] = useState<string | null>(null);
  const [dojo, setDojo] = useState(false);
  const [commandResult, setCommandResult] = useState<CommandResult | null>(null);
  const [configurationOpen, setConfigurationOpen] = useState(false);
  const [configurationAdvisory, setConfigurationAdvisory] = useState<ConfigurationAdvisory | null>(null);
  const [guidance, setGuidance] = useState<CharacterGuidance | null>(null);
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
  const scoreMilestones = useRef<{ workspace: string; badges: number; dossierFilled: number } | null>(null);
  const musicPreferenceLoaded = useRef(false);
  const detailOrigin = useRef<HTMLElement | null>(null);
  const overlayOrigin = useRef<HTMLElement | null>(null);
  const dialogRef = useRef<HTMLElement | null>(null);
  const feedRef = useRef<HTMLDivElement>(null);
  const cockpitRef = useRef<HTMLElement | null>(null);
  const guidanceSequence = useRef(0);
  const commandInputRef = useRef<HTMLInputElement | null>(null);
  const modalOpen = Boolean(detail || help || alertsOpen || palette || dojo || commandResult || configurationOpen);

  const refresh = async () => { const response = await fetch("/api/state", { cache: "no-store" }); setState(await response.json()); };
  const refreshAlerts = async () => { const response = await fetch("/api/alerts", { cache: "no-store" }); if (response.ok) setAlerts(await response.json()); };
  useEffect(() => { Promise.all([refresh(), refreshAlerts()]).catch((reason) => setError(String(reason))); }, []);
  useEffect(() => {
    let stopped = false;
    const poll = async () => {
      try {
        const response = await fetch("/api/advisories", { cache: "no-store" });
        if (!response.ok || stopped) return;
        const result = await response.json() as { advisory?: ConfigurationAdvisory | null };
        if (result.advisory?.content_class === "narration" && result.advisory.evidence === false) {
          setConfigurationAdvisory(result.advisory);
        }
      } catch { /* configuration guidance must never disrupt investigation flow */ }
    };
    const first = window.setTimeout(() => void poll(), 8_000);
    const interval = window.setInterval(() => void poll(), 60_000);
    return () => { stopped = true; window.clearTimeout(first); window.clearInterval(interval); };
  }, [state?.character]);
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
  useEffect(() => {
    const storedEffects = window.localStorage.getItem("pivotglass.effects");
    const storedNarration = window.localStorage.getItem("pivotglass.narration");
    const storedVoiceAudio = window.localStorage.getItem("pivotglass.narration.audio");
    const storedMusicVolume = window.localStorage.getItem("pivotglass.music.volume");
    const storedPanes = window.localStorage.getItem("pivotglass.panes");
    const storedVolume = Number(storedMusicVolume);
    if (storedEffects === "full" || storedEffects === "reduced" || storedEffects === "off") setEffects(storedEffects);
    else setEffects(window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "reduced" : "full");
    if (storedNarration === "full" || storedNarration === "brief" || storedNarration === "off") setNarration(storedNarration);
    setVoiceAudio(storedVoiceAudio === "true");
    if (storedMusicVolume !== null && Number.isFinite(storedVolume) && storedVolume >= 0 && storedVolume <= 100) setMusicVolume(storedVolume);

    let panes: Partial<Record<PaneId, boolean>> = {};
    if (storedPanes) {
      try { panes = JSON.parse(storedPanes) as Partial<Record<PaneId, boolean>>; }
      catch { /* ignore invalid local preference */ }
    }
    if (window.localStorage.getItem("pivotglass.visualAnalysisIntroduced") !== "1") {
      panes["artifact-field"] = false;
      window.localStorage.setItem("pivotglass.visualAnalysisIntroduced", "1");
      window.localStorage.setItem("pivotglass.panes", JSON.stringify({ ...collapsed, ...panes }));
    }
    setCollapsed((current) => ({ ...current, ...panes }));
    setMusic(window.localStorage.getItem("pivotglass.music.enabled") === "true");
    musicPreferenceLoaded.current = true;
  }, []);
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
  useEffect(() => { if (!(detail || help || alertsOpen || palette || dojo || commandResult || configurationOpen)) return; const root = dialogRef.current; const focusable = root?.querySelectorAll<HTMLElement>("button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [href], [tabindex]:not([tabindex='-1'])"); (root?.querySelector<HTMLElement>("[data-initial-focus]") ?? focusable?.[0])?.focus(); const trap = (event: KeyboardEvent) => { if (event.key !== "Tab" || !focusable?.length) return; const first = focusable[0]; const last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } }; window.addEventListener("keydown", trap); return () => window.removeEventListener("keydown", trap); }, [detail, help, alertsOpen, palette, dojo, commandResult, configurationOpen]);
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
  useEffect(() => {
    if (!state) return;
    const current = { workspace: state.workspace, badges: state.badge_summary.count, dossierFilled: dossier };
    const previous = scoreMilestones.current;
    scoreMilestones.current = current;
    if (!previous || previous.workspace !== current.workspace) return;
    if (current.badges > previous.badges) audioRef.current?.accent("badge");
    else if (current.dossierFilled > previous.dossierFilled) audioRef.current?.accent("dossier");
  }, [dossier, state?.badge_summary.count, state?.workspace]);
  const configuredSources = state?.instruments.sources.configured ?? 0;
  const taskGroups = useMemo(() => groupTasks(feed), [feed]);
  const enrichmentActivity = state?.visualizations.find((intent) => intent.intent_id === "task-matrix");
  const liveEnrichmentRows = useMemo(() => {
    if (!investigationId) return [];
    const indicator = target.trim() || "Current investigation";
    return taskGroups.map((task) => ({
      indicator,
      enrichment: task.tool,
      status: task.latest.lifecycle,
      updated_at: task.latest.updated_at ?? task.latest.created_at ?? "",
      event_sequence: task.latest.sequence,
      investigation_id: investigationId,
    }));
  }, [investigationId, target, taskGroups]);
  const processedTargets = useMemo(() => new Set(state?.processed_targets ?? []), [state?.processed_targets]);
  const availableGuidance = useMemo(
    () => state ? guidanceCandidates(state, alerts) : [],
    [alerts, state],
  );
  useEffect(() => {
    if (!state || narration === "off" || availableGuidance.length === 0) {
      setGuidance(null);
      return;
    }
    const present = () => {
      if (modalOpen || active) return;
      const next = characterGuidance(state.character, availableGuidance, guidanceSequence.current);
      guidanceSequence.current += 1;
      setGuidance(next);
    };
    const first = window.setTimeout(present, 16_000);
    const interval = window.setInterval(present, 120_000);
    return () => { window.clearTimeout(first); window.clearInterval(interval); };
  }, [active, availableGuidance, modalOpen, narration, state]);
  const advisorMessage = configurationAdvisory?.message ?? guidance?.message ?? "";
  useEffect(() => {
    if (!voiceAudio || narration === "off" || modalOpen || !advisorMessage || !state?.character) return;
    speakCharacterNarration(state.character, advisorMessage);
    return stopCharacterNarration;
  }, [advisorMessage, modalOpen, narration, state?.character, voiceAudio]);
  useEffect(() => stopCharacterNarration, []);

  function closeOverlays() { if (detail) closeDetail(); setPalette(false); setHelp(false); setAlertsOpen(false); setDojo(false); setConfigurationOpen(false); setMenu(false); requestAnimationFrame(() => overlayOrigin.current?.focus()); }
  function openOverlay(kind: "help" | "palette" | "alerts" | "dojo" | "configuration", origin?: HTMLElement) { overlayOrigin.current = origin ?? document.activeElement as HTMLElement; setHelp(kind === "help"); setPalette(kind === "palette"); setAlertsOpen(kind === "alerts"); setDojo(kind === "dojo"); setConfigurationOpen(kind === "configuration"); setMenu(false); }
  function closeCommandResult() { if (!commandResult) return; setCommandResult(null); requestAnimationFrame(() => overlayOrigin.current?.focus()); }
  function togglePane(id: PaneId) { setCollapsed((current) => { const next = { ...current, [id]: !current[id] }; window.localStorage.setItem("pivotglass.panes", JSON.stringify(next)); return next; }); }
  function toggleMaximize(id: PaneId) { setActivePane(id); setMaximized((current) => current === id ? null : id); }
  function followGuidance(idea: CharacterGuidance) {
    setGuidance(null);
    if (idea.action === "focus") {
      requestAnimationFrame(() => commandInputRef.current?.focus());
    } else if (idea.action === "pane") {
      go(idea.value as PaneId);
    } else if (idea.action === "alerts") {
      openOverlay("alerts", document.activeElement as HTMLElement);
    } else {
      setTarget(idea.value);
      requestAnimationFrame(() => commandInputRef.current?.focus());
    }
  }

  async function switchMode(name: string) {
    stopCharacterNarration();
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
    if (result.kind === "configuration") { setCommandResult(null); openOverlay("configuration"); return; }
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

  async function runAnalyticCommand(command: string) {
    setError("");
    const response = await fetch("/api/command", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ command }) });
    const result = await response.json() as CommandResult & { error?: string };
    if (!response.ok) throw new Error(result.error ?? "Analytic command failed");
    if (result.state) setState(result.state);
    else await refresh();
    return result.title ?? "Analytic record updated";
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
  function setVoiceAudioPreference(enabled: boolean) { setVoiceAudio(enabled); window.localStorage.setItem("pivotglass.narration.audio", String(enabled)); if (!enabled) stopCharacterNarration(); }

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
    ...paneIds.map((id) => ({ label: `Go to ${PANE_LABELS[id]}`, run: () => go(id) })),
    { label: "Open operator help", run: () => openOverlay("help") },
    { label: "Open model and API configuration", run: () => openOverlay("configuration") },
    { label: "Open Attention Needed", run: () => openOverlay("alerts") },
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
    if (result.kind === "challenges" && Array.isArray(decoded)) {
      const challenges = decoded as ChallengeRecord[];
      return <section className="structured-result challenge-result"><header><b>ACTIVE PURSUIT CHALLENGES</b><span>{challenges.filter((item) => item.status === "completed").length}/{challenges.length} COMPLETE</span></header><div>{challenges.map((item) => { const reward = item.badge; const current = item.progress_current ?? 0; const goal = item.progress_target ?? 1; const rarity = reward?.badge_rarity ?? "common"; return <article key={item.id} className={`challenge-card state-${item.status} rarity-${rarity}`}><BadgeArtwork badgeId={reward?.badge_id} kind={reward?.badge_artwork} glyph={reward?.badge_glyph} rarity={rarity} label={`${reward?.badge_name ?? item.name} badge artwork`}/><div><header><b>{item.name}</b><span>{item.status.toUpperCase()} · {item.points} PTS</span></header><p>{item.description}</p><progress max={goal} value={Math.min(current, goal)}/><small>{current}/{goal} {item.progress_label ?? "requirements met"} · {item.subject_value ?? "workspace-wide"}</small>{Boolean(item.evidence_basis?.length) && <details><summary>PUBLIC-REPORTING BASIS · {item.evidence_basis?.length} RECORDS</summary><pre>{JSON.stringify(item.evidence_basis, null, 2)}</pre></details>}</div></article>; })}</div></section>;
    }
    if (result.kind === "badges" && Array.isArray(decoded)) {
      const badges = decoded as BadgeAward[];
      return <section className="structured-result badge-result"><header><b>EARNED BADGES</b><span>{badges.length} TOTAL</span></header><div>{[...badges].reverse().map((badge) => { const rarity = badge.badge_rarity ?? "common"; return <article key={badge.badge_id} className={`badge-card rarity-${rarity}`}><BadgeArtwork badgeId={badge.badge_id} kind={badge.badge_artwork} glyph={badge.badge_glyph} rarity={rarity} label={`${badge.badge_name} badge artwork`}/><div><b>{badge.badge_name}</b><span>{rarity} · {new Date(badge.awarded_at).toLocaleString()}</span><p>{badge.badge_description ?? "Workspace milestone earned."}</p><small>{badge.challenge_id ? `Challenge: ${badge.challenge_id}` : "Workspace milestone"}</small></div></article>; })}</div></section>;
    }
    return <pre>{JSON.stringify(decoded, null, 2)}</pre>;
  }

  const selectedDossierSlot = state?.dossier_slots.find((slot) => slot.name === selectedFacet);

  return <main ref={cockpitRef} tabIndex={-1} style={style} className={`mode-${state?.character ?? "default"} effects-${effects} narration-${narration} display-${displayMode} contrast-${contrast} ${maximized ? `max-${maximized}` : ""}`}>
    <AmbientEnvironment character={state?.character ?? "default"} />
    <div className="fog-band" aria-hidden="true" />
    <header className="masthead">
      <button className="menu-button" onClick={() => setMenu(!menu)} aria-expanded={menu}>☰ <span>DECK</span></button>
      <div className="brand"><span className="eyebrow">{mode?.cockpit.deck_name ?? "HUNT CONTROL"} // LOCAL INTELLIGENCE SYSTEM</span><h1>PIVOTGLASS</h1><small>{mode?.cockpit.vehicle ?? "AP-01 PURSUIT DECK"}</small></div>
      <div className="status-cluster"><span className="lamp ok" /><span className={`lamp ${active ? "hot" : ""}`} /><span className={active ? "system-state pulse" : "system-state"}>{active ? "HUNT ACTIVE" : "SYSTEM READY"}</span><button className="badge-summary" title="Open earned badges" onClick={(event) => { overlayOrigin.current = event.currentTarget; void runQuick("badges"); }}><BadgeArtwork badgeId={state?.badge_summary.latest?.badge_id} kind={state?.badge_summary.latest?.badge_artwork} glyph={state?.badge_summary.latest?.badge_glyph} rarity={state?.badge_summary.latest?.badge_rarity} label="Most recently earned badge"/><span><b>{state?.badge_summary.count ?? 0} BADGES</b><small>{state?.badge_summary.latest?.badge_name ?? "NO BADGE YET"}</small></span></button><span className="focus-status" aria-live="polite">FOCUS · {focusZone.toUpperCase()}</span>{reviewingHistory && alerts.unread_count > 0 && <button className="unread-badge" onClick={(event) => openOverlay("alerts", event.currentTarget)}>{alerts.highest_unread.toUpperCase()} · {alerts.unread_count} UNREAD</button>}<button className="help-button" onClick={(event) => openOverlay("help", event.currentTarget)}>HELP ?</button></div>
      {menu && <nav className="deck-menu" aria-label="Cockpit navigation">{paneIds.map((id) => <button key={id} onClick={() => { go(id); setMenu(false); }}>{PANE_LABELS[id]}</button>)}<button onClick={(event) => openOverlay("configuration", event.currentTarget)}>MODEL + API CONFIGURATION</button><hr/><label>DAY / NIGHT</label><div className="segmented display-choice">{(["night", "day"] as const).map((value) => <button className={displayMode === value ? "selected" : ""} key={value} onClick={() => { setDisplayMode(value); window.localStorage.setItem("pivotglass.display", value); }}>{value}</button>)}</div><label>CONTRAST</label><div className="segmented">{(["soft", "normal", "high"] as const).map((value) => <button className={contrast === value ? "selected" : ""} key={value} onClick={() => { setContrast(value); window.localStorage.setItem("pivotglass.contrast", value); }}>{value}</button>)}</div><label>VISUAL EFFECTS</label><div className="segmented">{(["full", "reduced", "off"] as const).map((value) => <button className={effects === value ? "selected" : ""} key={value} onClick={() => setEffectsPreference(value)}>{value}</button>)}</div><label>NARRATION</label><div className="segmented">{(["full", "brief", "off"] as const).map((value) => <button className={narration === value ? "selected" : ""} key={value} onClick={() => setNarrationPreference(value)}>{value}</button>)}</div><label>DEVICE VOICE AUDIO · OFF BY DEFAULT</label><button className={voiceAudio ? "selected" : ""} onClick={() => setVoiceAudioPreference(!voiceAudio)}>{voiceAudio ? "MUTE ADVISOR VOICE" : "ENABLE ADVISOR VOICE"}</button><small>Uses an available browser or operating-system voice. No actor or character voice is cloned.</small><label>GENERATIVE MUSIC · OFF BY DEFAULT</label><button className={music ? "selected" : ""} onClick={toggleMusic}>{music ? "MUTE MUSIC" : "ENABLE MUSIC"}</button><input type="range" min="0" max="100" value={musicVolume} onChange={(event) => setMusicVolume(Number(event.target.value))} aria-label="Music volume"/><hr/><label>CHARACTER VOICE</label>{publicModes(state?.modes).map(({ mode: item, label }) => <button className={item.name === state?.character ? "selected" : ""} key={item.name} onClick={() => switchMode(item.name)}><b>{label}</b><small>{item.personality}</small></button>)}</nav>}
    </header>

    <nav className="pane-switcher" aria-label="Primary cockpit panes">{paneIds.map((id) => <button key={id} aria-current={activePane === id ? "page" : undefined} title={`Open and focus ${PANE_LABELS[id]} pane`} onClick={() => go(id)}>{PANE_LABELS[id]}</button>)}<button title="Use the active pane at full viewport size" onClick={() => toggleMaximize(activePane)}>{maximized ? "RESTORE VIEW" : "MAXIMIZE PANE"}</button><button title="Search all cockpit commands" onClick={(event) => openOverlay("palette", event.currentTarget)}>COMMANDS ⌘K</button><button title="Configure models and intelligence APIs" onClick={(event) => openOverlay("configuration", event.currentTarget)}>CONFIGURATION</button><button title="Open optional theme arcade" onClick={(event) => openOverlay("dojo", event.currentTarget)}>THEME ARCADE</button></nav>

    <section className="voice-strip"><b>{publicModeLabel(state?.character).toUpperCase()}</b><span>{mode?.greeting || "Cockpit link established."}</span><i>{mode?.pursuit_title ?? "THE HUNT"}</i></section>

    <section className={`command-rail ${commandFocused ? "has-focus" : ""}`}><form onSubmit={investigate}><span className="prompt">glass://command</span><div className="command-combobox"><input ref={commandInputRef} value={target} onChange={(event) => setTarget(event.target.value)} onFocus={() => setCommandFocused(true)} onBlur={() => window.setTimeout(() => setCommandFocused(false), 120)} onKeyDown={commandKeyDown} placeholder="indicator, command, search, or analyst question" aria-label="Investigation target" role="combobox" aria-autocomplete="list" aria-expanded={commandFocused && completions.length > 0} aria-controls="command-completions" aria-activedescendant={completionIndex >= 0 ? `completion-${completionIndex}` : undefined}/>{commandFocused && completions.length > 0 && <div id="command-completions" className="command-completions" role="listbox">{completions.slice(0, 10).map((completion, index) => <button type="button" role="option" id={`completion-${index}`} aria-selected={completionIndex === index} className={completionIndex === index ? "selected" : ""} key={completion} onMouseDown={(event) => event.preventDefault()} onClick={() => chooseCompletion(completion)}><b>{completion}</b></button>)}</div>}</div><button disabled={active}>{active ? `WORKING ${elapsed}s` : "EXECUTE"}</button>{active && investigationId && <button type="button" className="cancel" onClick={cancelInvestigation}>CANCEL</button>}</form>{error && <div className="error">⚠ FAULT · {error}</div>}<small className="command-hint">Tab completes · / focuses command · F6 moves focus · ? opens help when the command is empty</small>{investigationQueue.length > 0 && <section className="investigation-queue" aria-label={`Investigation queue for ${state?.workspace ?? "current workspace"}`}><header><b>INVESTIGATION QUEUE · {state?.workspace}</b><span>{investigationQueue.filter((item) => item.status === "pending").length} PENDING</span><button disabled={active || !investigationQueue.some((item) => item.status === "pending")} onClick={() => void runQueue(false)}>RUN NEXT</button><button disabled={active || !investigationQueue.some((item) => item.status === "pending")} onClick={() => void runQueue(true)}>RUN ALL</button><button disabled={active} onClick={() => setInvestigationQueue((current) => current.filter((item) => item.status === "pending" || item.status === "running"))}>CLEAR FINISHED</button></header><ol>{investigationQueue.map((item, index) => <li key={`${item.target}-${item.addedAt}`}><span className={`queue-state ${item.status}`}>{item.status}</span><b title={`${item.target} · workspace ${item.workspace}`}>{shortenMiddle(item.target, 48)}</b>{item.error && <small>{item.error}</small>}<div><button disabled={active || index === 0} onClick={() => moveQueue(item.addedAt, -1)} aria-label={`Move ${item.target} earlier`}>↑</button><button disabled={active || index === investigationQueue.length - 1} onClick={() => moveQueue(item.addedAt, 1)} aria-label={`Move ${item.target} later`}>↓</button><button disabled={active || item.status === "running"} onClick={() => setInvestigationQueue((current) => current.filter((candidate) => candidate !== item))}>REMOVE</button>{item.status === "failed" && <button disabled={active} onClick={() => setInvestigationQueue((current) => current.map((candidate) => candidate === item ? {...candidate, status: "pending", error: undefined} : candidate))}>RETRY</button>}</div></li>)}</ol></section>}</section>

    <section className={`telemetry-rack ${collapsed.systems ? "collapsed" : ""}`} id="systems" tabIndex={-1}>
      <button className="telemetry-collapse" onClick={() => togglePane("systems")} aria-expanded={!collapsed.systems} aria-controls="systems-content" title={`${collapsed.systems ? "Expand" : "Collapse"} system telemetry`}>{collapsed.systems ? "▸ SYSTEMS" : "▾ SYSTEMS"}</button>
      <div id="systems-content" className="telemetry-content">
      <Meter label="REACTOR / LOCAL API" value={state?.instruments.local_api.available ? 100 : 0} detail={state?.instruments.local_api.available ? "AVAILABLE" : "UNAVAILABLE"} />
      <Meter label="DOSSIER CELLS" value={(dossierProgress / 9) * 100} detail={`${dossier} FILLED`} warning={dossier >= 8} />
      <Meter label="ENRICHMENT BAY" value={null} detail={`${configuredSources} SOURCES`} />
      <Meter label="TOKEN CORE" value={state?.instruments.model_tokens.available ? 100 : null} detail={state?.instruments.model_tokens.available ? `${state.instruments.model_tokens.used ?? 0} USED` : "NOT ENGAGED"} />
      <div className="damage"><span>INVESTIGATION STATE</span><b className={error ? "danger" : active ? "caution" : "ok-text"}>{error ? "FAULT" : active ? "RUNNING" : "IDLE"}</b><small>{error ? "SEE ATTENTION NEEDED" : active ? `${elapsed}s ELAPSED · EVENT STREAM LIVE` : "NO ACTIVE INVESTIGATION"}</small></div></div>
    </section>

    <section className="cockpit-grid">
      <article className={`panel feed-panel ${collapsed.intelligence ? "collapsed" : ""}`} id="intelligence" tabIndex={-1}><PanelTitle id="intelligence" title={`${mode?.cockpit.left_rail} ${mode?.pursuit_title} // INTELLIGENCE`} status={`${taskGroups.length} TASKS · ${feed.length} EVENTS`} collapsed={collapsed.intelligence} maximized={maximized === "intelligence"} onToggle={() => togglePane("intelligence")} onMaximize={() => toggleMaximize("intelligence")}/><div id="intelligence-content" className="feed" ref={feedRef} tabIndex={0} aria-label="Scrollable intelligence feed" onScroll={(event) => { const node = event.currentTarget; setReviewingHistory(node.scrollHeight - node.scrollTop - node.clientHeight > 32); }}>
        {state?.analysis && <ScientificWorkbench analysis={state.analysis} onCommand={runAnalyticCommand}/>}
        {feed.length === 0 && <div className="standby"><div className="reticle"><i/><i/><i/></div><b>AWAITING TARGET LOCK</b><span>Evidence, retrieval briefings, and justified pivots will appear here.</span></div>}
        {enrichmentActivity && (enrichmentActivity.data.rows.length > 0 || liveEnrichmentRows.length > 0) && <><section className="hunt-summary"><b>ENRICHMENT ACTIVITY</b><span>indicators × enrichment sources · RGB status blocks · newest activity first</span></section><TaskMatrix intent={enrichmentActivity} liveRows={liveEnrichmentRows} onSelectCell={(cell) => setExpandedTask(String(cell.enrichment ?? ""))}/></>}
        {taskGroups.filter((task) => expandedTask === task.key).map((task) => <section className="task-detail" id={`task-${task.key}`} key={task.key}><header><div><b>{task.tool}</b><small>{task.events.length} ordered transitions · {task.artifacts.length} evidence records</small></div><button onClick={() => setExpandedTask(null)}>COLLAPSE</button></header>{task.events.map((item) => <section id={`event-${item.event_id}`} className={`event ${item.content_class} state-${item.lifecycle} class-${item.event_class}`} key={item.event_id}><div className="event-head"><b>{item.lifecycle.toUpperCase()}</b><span>{item.source ?? item.event_class}</span></div><small>{item.tool} · event {item.sequence}</small>{item.briefing && <><p><label>GATHER</label>{item.briefing.artifacts}</p><p><label>WHY</label>{item.briefing.purpose}</p><p><label>WATCH</label>{item.briefing.watch_for}</p><small>Retrieval goal—not an observed finding.</small></>}{item.summary && <pre>{item.summary}</pre>}{item.reason && <p><label>STATE</label>{item.reason}</p>}{item.artifact_ids?.map((id) => { const artifact = state?.objects.find((candidate) => candidate.reference === id || candidate.stix_id === id); return <button className="evidence-link" title={artifact?.value ?? "Open stored evidence"} key={id} onClick={(event) => openDetail(id, event.currentTarget)}>OPEN {shortenMiddle(artifact?.value ?? "stored evidence", 44)}</button>; })}</section>)}</section>)}
      </div></article>

      <aside className="right-stack">
        <article className={`panel instruments ${collapsed.dossier ? "collapsed" : ""}`} id="dossier" tabIndex={-1}><PanelTitle id="dossier" title={mode?.cockpit.hud_title ?? "TACTICAL HUD"} status={`${dossier}/9 FACETS`} collapsed={collapsed.dossier} maximized={maximized === "dossier"} onToggle={() => togglePane("dossier")} onMaximize={() => toggleMaximize("dossier")}/><div id="dossier-content" className="panel-content"><dl><div><dt>WORKSPACE</dt><dd>{state?.workspace ?? "—"}</dd></div><div><dt>CHARACTER</dt><dd>{publicModeLabel(state?.character)}</dd></div><div><dt>ARTIFACTS</dt><dd>{state?.objects.length ?? 0}</dd></div><div><dt>DOSSIER</dt><dd>{dossier}/9 FILLED</dd></div></dl><div className="dossier-object" aria-label={`${dossier} of 9 dossier facets filled`}><div className="dossier-core"><b>DOSSIER</b><span>{dossierProgress}/9 mapped</span></div><div className="dossier-facets">{(state?.dossier_slots ?? Array.from({length: 9}, (_, index) => ({name: `slot ${index + 1}`, status: "empty" as const, evidence_count: 0}))).map((slot, index) => <button className={`${slot.status} ${selectedFacet === slot.name ? "selected" : ""}`} key={slot.name} data-tooltip={`${slot.name.replaceAll("_", " ")}: ${slot.status}, ${slot.evidence_count} source-backed puzzle pieces. Click to inspect this plane.`} onClick={() => setSelectedFacet((current) => current === slot.name ? null : slot.name)} aria-pressed={selectedFacet === slot.name} aria-label={`${slot.name}: ${slot.status}, ${slot.evidence_count} evidence. Inspect dossier facet.`}><span>{index + 1}</span><small>{slot.name.replaceAll("_", " ")}</small></button>)}</div></div>{selectedDossierSlot && <section className="facet-evidence"><header><b>{selectedDossierSlot.name.replaceAll("_", " ").toUpperCase()}</b><button onClick={() => setSelectedFacet(null)}>CLOSE</button></header><p>{selectedDossierSlot.evidence_count} source-backed puzzle pieces contribute to this plane.</p>{selectedDossierSlot.evidence?.length ? <div>{selectedDossierSlot.evidence.map((item) => <button key={item.reference} onClick={(event) => void openDetail(item.reference, event.currentTarget)}><b title={item.value}>{shortenMiddle(item.value, 38)}</b><span>{item.type}</span></button>)}</div> : <small>No directly attributable stored evidence yet.</small>}</section>}</div></article>
        <article className={`panel chart-panel ${collapsed["artifact-field"] ? "collapsed" : ""}`} id="artifact-field" tabIndex={-1}><PanelTitle id="artifact-field" title="VISUAL ANALYSIS" status="PYTHON INTENT / FLINT" collapsed={collapsed["artifact-field"]} maximized={maximized === "artifact-field"} onToggle={() => togglePane("artifact-field")} onMaximize={() => toggleMaximize("artifact-field")}/><div id="artifact-field-content" className="panel-content"><VisualizationWorkspace intents={state?.visualizations ?? []} theme={theme} onOpenEvidence={(reference, origin) => void openDetail(reference, origin)}/><div className="artifact-list">{state?.objects.slice(-12).map((item) => { const queued = investigationQueue.some((entry) => entry.target === item.value && ["pending", "running"].includes(entry.status)); return <div className="artifact-row" key={item.reference} data-tooltip={`${item.value} · ${item.type} · ${item.country ? `source-backed location ${item.country}` : "location unknown"} · ${queued ? "already queued" : processedTargets.has(item.value ?? "") ? "processed previously; queue to re-run" : "new; click queue to investigate"}`}><button title={`${item.value} · ${item.country ?? "location unknown"} · open provenance`} onClick={(event) => openDetail(item.reference, event.currentTarget)}><b>{flag(item.country)} {item.known_malware ? "☠️ " : ""}{shortenMiddle(item.value)}</b><span>{item.type} · {queued ? "queued" : processedTargets.has(item.value ?? "") ? "processed" : "new"}</span></button><button className="queue-indicator" onClick={() => queueIndicator(item.value)} disabled={queued} title={queued ? "Already queued" : processedTargets.has(item.value ?? "") ? "Queue a fresh investigation" : "Queue this indicator for investigation"}>{queued ? "✓ QUEUED" : processedTargets.has(item.value ?? "") ? "↻ QUEUE AGAIN" : "+ QUEUE"}</button></div>; })}</div></div></article>
        <article className="panel alert-panel"><div className="panel-title"><button title="Open persistent attention records" onClick={(event) => openOverlay("alerts", event.currentTarget)}>ATTENTION NEEDED</button><small>{error ? "FAULT" : alerts.unread_count ? `${alerts.unread_count} UNREAD · ${alerts.highest_unread.toUpperCase()}` : "CLEAR"}</small></div><p>{error ? error : alerts.unread_count ? "Attention records are waiting. Open Attention Needed to inspect and acknowledge them." : active ? "Enrichment activity underway. Retrieval briefings are prospective until evidence arrives." : "No unacknowledged attention records."}</p></article>
      </aside>
    </section>

    {narration !== "off" && (configurationAdvisory || guidance) && <AdvisorPortal style={style}>
    {configurationAdvisory ? <aside className={`configuration-advisory advisor-${configurationAdvisory.character}`} aria-live="polite" role="status">
      <CharacterAdvisorArtwork character={configurationAdvisory.character} category="configuration" label={`${configurationAdvisory.character_name} configuration advisor artwork`}/>
      <div className="advisor-copy"><span>{configurationAdvisory.character_name.toUpperCase()} · CONFIGURATION ADVISOR · NARRATION</span>
      <p>{configurationAdvisory.message}</p>
      <div><button onClick={(event) => openOverlay("configuration", event.currentTarget)}>CONFIGURE</button><button onClick={() => setTarget(configurationAdvisory.action)}>COPY ACTION TO COMMAND</button><button onClick={() => speakCharacterNarration(configurationAdvisory.character, configurationAdvisory.message)}>READ ALOUD</button><button aria-label="Dismiss configuration suggestion" onClick={() => { stopCharacterNarration(); setConfigurationAdvisory(null); }}>DISMISS</button></div></div>
    </aside> : guidance && <aside className={`configuration-advisory character-guidance advisor-${state?.character ?? "default"}`} aria-live="polite" role="status">
      <CharacterAdvisorArtwork character={state?.character ?? "default"} category={guidance.category} label={`${guidance.characterName} ${guidance.category} advisor artwork`}/>
      <div className="advisor-copy"><span>{guidance.characterName.toUpperCase()} · ANALYST ADVISOR · NARRATION, NOT EVIDENCE</span>
      <p>{guidance.message}</p>
      <div><button onClick={() => followGuidance(guidance)}>{guidance.actionLabel}</button><button onClick={() => speakCharacterNarration(state?.character ?? "default", guidance.message)}>READ ALOUD</button><button aria-label="Dismiss field guidance" onClick={() => { stopCharacterNarration(); setGuidance(null); }}>DISMISS</button></div></div>
    </aside>}
    </AdvisorPortal>}
    <footer><span>EVIDENCE ≠ INFERENCE</span><span>LOCALHOST · NO TELEMETRY · OPERATOR CONTROLLED</span><button title="Open contextual operator help" onClick={(event) => openOverlay("help", event.currentTarget)}>HELP ?</button></footer>
    {help && <div className="modal-backdrop" onMouseDown={closeOverlays}><section ref={dialogRef} className="help-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="help-heading"><button className="close" aria-label="Close help" onClick={closeOverlays}>×</button><span className="eyebrow">PIVOTGLASS FIELD MANUAL · {PANE_LABELS[activePane].toUpperCase()}</span><h2 id="help-heading" tabIndex={-1}>WHAT DO YOU WANT TO DO?</h2><div className="help-tasks"><button onClick={() => { closeOverlays(); document.querySelector<HTMLInputElement>('[aria-label="Investigation target"]')?.focus(); }}><b>START A HUNT</b><span>Focus the target field. Enter a domain, IP, URL, email, or hash, then choose EXECUTE.</span><kbd>RETURN</kbd></button><button onClick={() => { closeOverlays(); go("intelligence"); }}><b>REVIEW ENRICHMENTS</b><span>Select an RGB status block to open its ordered transitions and evidence links.</span><kbd>CLICK / ENTER</kbd></button><button onClick={() => { closeOverlays(); go("artifact-field"); }}><b>DRILL INTO EVIDENCE</b><span>Open an artifact to inspect provenance, normalized fields, and the safe raw record.</span><kbd>CLICK / ENTER</kbd></button><button onClick={() => { closeOverlays(); openOverlay("palette"); }}><b>FIND A CONTROL</b><span>Search pane, effects, narration, audio, alert, and character commands.</span><kbd>⌘/CTRL K</kbd></button></div><dl className="keymap"><div><dt>?</dt><dd>Help when command is empty</dd></div><div><dt>/</dt><dd>Focus command input</dd></div><div><dt>F6</dt><dd>Move between command and cockpit</dd></div><div><dt>ESC</dt><dd>Close dialog or return focus to cockpit</dd></div><div><dt>TAB</dt><dd>Complete a command or move controls</dd></div></dl><p className="truth-note"><b>Reading the display:</b> queued/running describe enrichment state; succeeded means the source completed, not that a claim is true. Evidence is observed source output. Narration is interpretation and remains labeled separately. A connection is an evidence-backed relationship between graph nodes.</p><small>Help is contextual to the active pane. Actions above perform the route they describe.</small></section></div>}
    {detail && <div className="detail-backdrop" onMouseDown={closeDetail}><aside ref={dialogRef} className="detail-drawer" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label={`Evidence ${detail.value}`}><button className="close" onClick={closeDetail}>×</button><span className="eyebrow">INDICATOR DETAIL · STORED LOCAL DATA</span><h2 title={detail.value}>{shortenMiddle(detail.value, 72)}</h2><button className="queue-detail" onClick={() => void queueIndicator(detail.value)} disabled={active}>+ QUEUE FOR INVESTIGATION</button><dl><div><dt>TYPE</dt><dd>{detail.type}</dd></div><div><dt>FULL INDICATOR</dt><dd>{detail.value}</dd></div><div><dt>PURPOSE / ROLE</dt><dd>{detail.purpose.join(" · ")}</dd></div><div><dt>SOURCE MODULE</dt><dd>{detail.source_module}</dd></div><div><dt>ORIGINAL QUERY</dt><dd>{detail.original_query}</dd></div></dl>{detail.source_intelligence && <section className="source-intelligence"><header><div><span>SOURCE INTELLIGENCE</span><h3>{detail.source_intelligence.provider}</h3></div><b>{detail.source_intelligence.headline}</b></header><dl>{detail.source_intelligence.facts.map((fact) => <div key={fact.label}><dt>{fact.label}</dt><dd>{typeof fact.value === "string" || typeof fact.value === "number" || typeof fact.value === "boolean" ? String(fact.value) : <code>{JSON.stringify(fact.value)}</code>}</dd></div>)}</dl>{detail.source_intelligence.links.length > 0 && <nav aria-label={`${detail.source_intelligence.provider} external evidence links`}>{detail.source_intelligence.links.map((link) => <a href={link.url} target="_blank" rel="noreferrer" key={`${link.label}-${link.url}`}>{link.label} ↗</a>)}</nav>}{detail.source_intelligence.groups.map((group) => <details key={group.title}><summary>{group.title}</summary><pre>{JSON.stringify(group.items, null, 2)}</pre></details>)}</section>}<h3>DISCOVERY BREADCRUMBS</h3><ol className="breadcrumbs">{detail.breadcrumbs.map((crumb, index) => <li key={`${crumb.indicator}-${index}`}><b>{crumb.indicator}</b><span>{crumb.relationship}</span></li>)}</ol><h3>RELATIONSHIPS</h3>{detail.relationships.length ? <ol className="relationship-list">{detail.relationships.map((relation, index) => <li key={`${relation.indicator}-${index}`}><span>{relation.direction ?? "related"} · {relation.relationship ?? "related to"}{relation.basis ? ` · ${relation.basis}` : ""}</span><b title={relation.indicator}>{shortenMiddle(relation.indicator, 48)}</b><div>{relation.reference && <button onClick={(event) => void openDetail(relation.reference!, event.currentTarget)}>OPEN DETAIL</button>}{relation.indicator && relation.indicator !== "unavailable" && <button onClick={() => queueIndicator(relation.indicator)}>+ QUEUE</button>}</div></li>)}</ol> : <p>No explicit relationship stored.</p>}<h3>HISTORICAL COLLECTION</h3><pre>{detail.history.length ? JSON.stringify(detail.history, null, 2) : "No matching module run recorded."}</pre><h3>PROVENANCE</h3><pre>{JSON.stringify(detail.provenance, null, 2)}</pre><h3>NORMALIZED FIELDS</h3><pre>{JSON.stringify(detail.normalized, null, 2)}</pre><h3>DOSSIER CONTRIBUTIONS</h3><pre>{detail.dossier_contributions.length ? JSON.stringify(detail.dossier_contributions, null, 2) : "unavailable"}</pre><h3>ANALYST ANNOTATION</h3><div className="annotation-editor"><textarea value={noteText} onChange={(event) => setNoteText(event.target.value)} placeholder="Record a sourced observation, hypothesis, or collection note"/><button onClick={() => void saveAnnotation()} disabled={!noteText.trim()}>SAVE LINKED NOTE</button></div><h3>SAFE RAW RECORD</h3><pre>{JSON.stringify(detail.raw, null, 2)}</pre><small>Opened from stored evidence. Backend identifiers remain hidden; no network service or model was invoked.</small></aside></div>}
    {alertsOpen && <div className="modal-backdrop" onMouseDown={closeOverlays}><section ref={dialogRef} className="alert-queue" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Attention needed alerts"><button className="close" aria-label="Close alerts" onClick={closeOverlays}>×</button><span className="eyebrow">PERSISTENT ATTENTION RECORD</span><h2>ATTENTION NEEDED</h2>{alerts.alerts.length === 0 && <p>No attention records.</p>}{alerts.alerts.map((alert) => <article className={alert.acknowledged ? "acknowledged" : ""} key={alert.event_id}><header><b>{alert.event_class.replaceAll("_", " ").toUpperCase()}</b><span>{alert.severity.toUpperCase()} · {alert.acknowledged ? "ACKNOWLEDGED" : "UNREAD"}</span></header><p>{alert.summary ?? alert.reason ?? alert.source}</p><div><button onClick={() => jumpToAlert(alert)}>ORIGIN</button>{!alert.acknowledged && <button onClick={() => acknowledge(alert.event_id)}>ACKNOWLEDGE</button>}{alert.artifact_ids?.map((id) => <button key={id} onClick={(event) => openDetail(id, event.currentTarget)}>DETAILS</button>)}</div></article>)}</section></div>}
    {palette && <div className="modal-backdrop" onMouseDown={closeOverlays}><section ref={dialogRef} className="command-palette" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Command palette"><input autoFocus value={paletteQuery} onChange={(event) => setPaletteQuery(event.target.value)} placeholder="Search cockpit commands" aria-label="Search cockpit commands"/>{paletteCommands.map((command) => <button key={command.label} onClick={() => { command.run(); setPalette(false); setPaletteQuery(""); }}>{command.label}</button>)}</section></div>}
    {commandResult && <div className="modal-backdrop command-result-backdrop" onMouseDown={closeCommandResult}><section ref={dialogRef} className="command-result" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label={commandResult.title ?? "Command result"}><button className="close" aria-label="Close command result" onClick={closeCommandResult}>×</button><span className="eyebrow">{commandResult.synthesized ? "MODEL SYNTHESIS · VERIFY AGAINST EVIDENCE" : "DETERMINISTIC WORKSPACE RESULT"}</span><h2>{commandResult.title ?? "ANALYST COMMANDS"}</h2>{commandResult.text && <pre>{commandResult.text}</pre>}{renderCommandData(commandResult)}{commandResult.commands && <div className="command-reference">{commandResult.commands.map((item) => <button key={item.command} onClick={() => { setTarget(item.command.replace(/ <.*$/, " ")); setCommandResult(null); document.querySelector<HTMLInputElement>('[aria-label="Investigation target"]')?.focus(); }}><b>{item.command}</b><span>{item.purpose}</span></button>)}</div>}{commandResult.printable && <button className="print-action" onClick={() => window.print()}>PRINT / SAVE PDF</button>}</section></div>}
    {dojo && <div className="modal-backdrop" onMouseDown={closeOverlays}><section ref={dialogRef} onMouseDown={(event) => event.stopPropagation()}><ThemeArcade character={state?.character ?? "sensei"} onClose={closeOverlays} reduced={effects !== "full"} publicModeLabel={publicModeLabel}/></section></div>}
    {configurationOpen && <div className="modal-backdrop configuration-backdrop" onMouseDown={closeOverlays}><section ref={dialogRef} onMouseDown={(event) => event.stopPropagation()}><ConfigurationCenter onClose={closeOverlays}/></section></div>}
    {tooltip && <div className={`viewport-tooltip ${tooltip.below ? "below" : "above"}`} role="tooltip" style={{ left: tooltip.left, top: tooltip.top }}>{tooltip.text}</div>}
  </main>;
}
