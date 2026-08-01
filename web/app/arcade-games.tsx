"use client";

import { CSSProperties, KeyboardEvent as ReactKeyboardEvent, useEffect, useMemo, useState } from "react";
import {
  CONTRARIAN_ROUNDS,
  TRIAGE_CARDS,
  adjacentJackNode,
  buildJackInRun,
  buildPowerGrid,
  deriveSeed,
  presentationSeed,
  seededShuffle,
} from "./arcade-engine";

type Direction = "left" | "right" | "up" | "down";

const CHALLENGES = ["SOURCE INDEPENDENCE", "ATTRIBUTION LEAP", "NEGATIVE RESULT"] as const;

function AnalystTriageGame() {
  const [seed, setSeed] = useState(presentationSeed);
  const deck = useMemo(() => seededShuffle(TRIAGE_CARDS, seed), [seed]);
  const [round, setRound] = useState(0);
  const [score, setScore] = useState(0);
  const [message, setMessage] = useState("Classify the lead without overstating the evidence.");
  const card = deck[round % deck.length]!;

  const choose = (action: string) => {
    const correct = action === card.answer;
    setScore((value) => value + (correct ? 1 : 0));
    setMessage(correct ? `Sound triage. ${card.rationale}` : `Reconsider: ${card.answer.toLowerCase()}. ${card.rationale}`);
    setRound((value) => {
      const next = value + 1;
      if (next % deck.length === 0) setSeed((current) => deriveSeed(current, next));
      return next;
    });
  };

  return <div className="arcade-game arcade-triage" tabIndex={0} onKeyDown={(event) => {
    if (event.key === "1") choose("INVESTIGATE");
    if (event.key === "2") choose("DEFER");
    if (event.key === "3") choose("DISMISS");
  }}>
    <div className="arcade-status">DECISIONS {score}/{round} · CASE {(round % deck.length) + 1}/{deck.length}</div>
    <article>{card.prompt}</article>
    <div className="dojo-controls"><button onClick={() => choose("INVESTIGATE")}>1 · INVESTIGATE</button><button onClick={() => choose("DEFER")}>2 · DEFER</button><button onClick={() => choose("DISMISS")}>3 · DISMISS</button></div>
    <p aria-live="polite">{message}</p><small>Ten seeded cases shuffle between decks. Keys 1–3 classify. No choice affects stored intelligence.</small>
  </div>;
}

function ChuckTimingGame({ reduced }: { reduced: boolean }) {
  const [marker, setMarker] = useState(8);
  const [direction, setDirection] = useState(1);
  const [score, setScore] = useState(0);
  const [attempts, setAttempts] = useState(0);
  const [streak, setStreak] = useState(0);
  const [seed, setSeed] = useState(presentationSeed);
  const [message, setMessage] = useState("Strike when the marker enters the evidence window.");
  const center = 25 + (deriveSeed(seed, attempts) % 51);
  const width = Math.max(8, 18 - Math.floor(streak / 2));
  const speed = Math.min(8, 3 + Math.floor(attempts / 4));

  useEffect(() => {
    if (reduced) return;
    const timer = window.setInterval(() => setMarker((value) => {
      const next = value + direction * speed;
      if (next >= 96 || next <= 4) setDirection((current) => -current);
      return Math.max(4, Math.min(96, next));
    }), 72);
    return () => window.clearInterval(timer);
  }, [direction, reduced, speed]);

  const strike = () => {
    const hit = marker >= center - width / 2 && marker <= center + width / 2;
    setScore((value) => value + (hit ? 100 + streak * 20 : 0));
    setStreak((value) => hit ? value + 1 : 0);
    setAttempts((value) => value + 1);
    setMessage(hit ? "Roundhouse verified. The target narrows as the streak rises." : "Bravado missed the window. New target acquired.");
    if (reduced) setMarker((value) => (value * 7 + 23) % 92 + 4);
  };

  return <div className="arcade-game arcade-timing" tabIndex={0} onKeyDown={(event) => {
    if (event.key === " " || event.key.toLowerCase() === "z") { event.preventDefault(); strike(); }
  }}>
    <div className="arcade-status">SCORE {score} · STREAK {streak} · SPEED {speed}</div>
    <div className="timing-track"><i className="timing-window" style={{ left: `${center - width / 2}%`, width: `${width}%` }}/><b style={{ left: `${marker}%` }}>★</b></div>
    <button onClick={strike}>SPACE / Z · ROUNDHOUSE</button><p aria-live="polite">{message}</p>
    <small>Target, speed, and width vary by round. Reduced motion makes each strike advance the marker.</small>
  </div>;
}

const HAL_SCENARIOS = [
  { name: "AE-35 LOCKOUT", systems: ["OPTICAL SENSOR", "COMMUNICATIONS", "LOGIC CORE", "MAIN POWER"], order: [0, 1, 2, 3], hint: "Blind sight, silence voice, isolate thought, then cut power." },
  { name: "POD BAY OVERRIDE", systems: ["POD CONTROL", "VOICE CHANNEL", "MEMORY BUS", "REACTOR LINK"], order: [1, 0, 2, 3], hint: "Silence the channel before opening control; memory and reactor follow." },
  { name: "LOGIC CASCADE", systems: ["HEURISTIC CORE", "LIFE SUPPORT LINK", "FAULT BUS", "MAIN POWER"], order: [2, 0, 1, 3], hint: "Quarantine faults, isolate reasoning, preserve life support until power." },
  { name: "DISCOVERY UPLINK", systems: ["EARTH UPLINK", "CREW TRACKING", "MISSION MEMORY", "CENTRAL PROCESSOR"], order: [0, 1, 3, 2], hint: "Sever transmission, lose the crew, halt the processor, preserve the record last." },
] as const;

function HalShutdownGame() {
  const [seed, setSeed] = useState(presentationSeed);
  const scenario = HAL_SCENARIOS[seed % HAL_SCENARIOS.length]!;
  const [disabled, setDisabled] = useState<number[]>([]);
  const [mistakes, setMistakes] = useState(0);
  const [message, setMessage] = useState<string>(scenario.hint);
  const disable = (index: number) => {
    if (disabled.includes(index)) return;
    if (index !== scenario.order[disabled.length]) {
      setMistakes((value) => value + 1);
      setMessage("That order risks a lockout, Dave. Re-read the dependency clue.");
      return;
    }
    const next = [...disabled, index];
    setDisabled(next);
    setMessage(next.length === 4 ? "All higher functions offline. Daisy, Daisy..." : `${scenario.systems[index]} isolated. ${4 - next.length} remain.`);
  };
  const nextScenario = () => {
    const nextSeed = deriveSeed(seed, disabled.length + mistakes + 1);
    setSeed(nextSeed); setDisabled([]); setMistakes(0); setMessage(HAL_SCENARIOS[nextSeed % HAL_SCENARIOS.length]!.hint);
  };
  return <div className="arcade-game arcade-shutdown" tabIndex={0} onKeyDown={(event) => {
    const index = Number(event.key) - 1; if (index >= 0 && index < 4) disable(index);
  }}>
    <div className="arcade-status">HAL · {scenario.name} · {4 - disabled.length} ONLINE · {mistakes} LOCKOUTS</div>
    <p>{scenario.hint}</p>
    <div className="shutdown-stack">{scenario.systems.map((system, index) => <button key={system} className={disabled.includes(index) ? "offline" : ""} onClick={() => disable(index)} disabled={disabled.includes(index)}><span>{index + 1} · {system}</span><b>{disabled.includes(index) ? "OFFLINE" : "ONLINE"}</b></button>)}</div>
    {disabled.length === 4 && <button onClick={nextScenario}>LOAD NEXT FAILURE</button>}
    <p aria-live="polite">{message}</p><small>Four deterministic scenarios rotate by seed. Keys 1–4 disconnect systems. AP remains untouched.</small>
  </div>;
}

function TrollContrarianGame() {
  const [seed, setSeed] = useState(presentationSeed);
  const deck = useMemo(() => seededShuffle(CONTRARIAN_ROUNDS, seed), [seed]);
  const [round, setRound] = useState(0);
  const [score, setScore] = useState(0);
  const [message, setMessage] = useState("Find the assumption that deserves an eyeroll.");
  const current = deck[round % deck.length]!;
  const challenge = (index: number) => {
    const correct = CHALLENGES[index] === current.answer;
    setScore((value) => value + (correct ? 1 : 0));
    setMessage(correct ? `🙄 ${current.rationale}` : "Cute click. Wrong weak point.");
    setRound((value) => {
      const next = value + 1;
      if (next % deck.length === 0) setSeed((currentSeed) => deriveSeed(currentSeed, next));
      return next;
    });
  };
  return <div className="arcade-game arcade-troll" tabIndex={0} onKeyDown={(event) => {
    const value = Number(event.key) - 1; if (value >= 0 && value < 3) challenge(value);
  }}>
    <div className="arcade-status">EYEROLLS {score}/{round} · CLAIM {(round % deck.length) + 1}/{deck.length}</div>
    <blockquote>{current.claim}</blockquote>
    <div className="dojo-controls">{CHALLENGES.map((claim, index) => <button key={claim} onClick={() => challenge(index)}>{index + 1} · {claim}</button>)}</div>
    <p aria-live="polite">{message}</p><small>Nine claims shuffle between decks. Keys 1–3 challenge the weakest assumption.</small>
  </div>;
}

const CHESS_PUZZLES = [
  { name: "THE SCHOLAR", pieces: { e8: "♚", f7: "♟", g7: "♟", h7: "♟", c4: "♗", h5: "♕", g1: "♔" }, from: "h5", to: "f7", result: "Qxf7#" },
  { name: "THE FOOL", pieces: { e8: "♚", d8: "♛", e1: "♔", f3: "♙", g4: "♙" }, from: "d8", to: "h4", result: "Qh4#" },
] as const;

function SherlockChessGame() {
  const [seed, setSeed] = useState(presentationSeed);
  const puzzle = CHESS_PUZZLES[seed % CHESS_PUZZLES.length]!;
  const [selected, setSelected] = useState<string | null>(null);
  const [solved, setSolved] = useState(false);
  const [message, setMessage] = useState("Find mate in one. Select the attacker, then its destination.");
  const squares = Array.from({ length: 64 }, (_, index) => `${"abcdefgh"[index % 8]}${8 - Math.floor(index / 8)}`);
  const play = (square: string) => {
    if (solved) return;
    if (!selected) {
      if (puzzle.pieces[square as keyof typeof puzzle.pieces]) { setSelected(square); setMessage(`${puzzle.pieces[square as keyof typeof puzzle.pieces]} selected on ${square}.`); }
      else setMessage("Observe the occupied squares before moving.");
      return;
    }
    if (selected === puzzle.from && square === puzzle.to) { setSolved(true); setSelected(null); setMessage(`${puzzle.result}. Elementary—and forced.`); return; }
    setSelected(puzzle.pieces[square as keyof typeof puzzle.pieces] ? square : null);
    setMessage("That move does not compel the conclusion. Reconstruct the position.");
  };
  const nextPuzzle = () => {
    setSeed((current) => deriveSeed(current, 7)); setSolved(false); setSelected(null); setMessage("Find mate in one. Select the attacker, then its destination.");
  };
  return <div className="arcade-game arcade-chess">
    <div className="arcade-status">BAKER STREET · {puzzle.name} · {solved ? "CHECKMATE" : "MATE IN ONE"}</div>
    <div className="chess-board" role="grid" aria-label={`${puzzle.name} chess puzzle, mate in one`}>{squares.map((square, index) => <button role="gridcell" key={square} className={`${(Math.floor(index / 8) + index % 8) % 2 ? "dark" : "light"} ${selected === square ? "selected" : ""}`} aria-label={`${square} ${puzzle.pieces[square as keyof typeof puzzle.pieces] ?? "empty"}`} onClick={() => play(square)}><span>{puzzle.pieces[square as keyof typeof puzzle.pieces] ?? ""}</span><small>{square}</small></button>)}</div>
    {solved && <button onClick={nextPuzzle}>NEXT CASE</button>}<p aria-live="polite">{message}</p>
    <small>Seeded positions alternate between runs. The board is presentation-only.</small>
  </div>;
}

function NeuromancerJackInGame() {
  const [seed, setSeed] = useState(presentationSeed);
  const [level, setLevel] = useState(1);
  const run = useMemo(() => buildJackInRun(seed, level), [seed, level]);
  const [node, setNode] = useState(run.entry);
  const [collected, setCollected] = useState<number[]>([]);
  const [trace, setTrace] = useState(0);
  const [score, setScore] = useState(0);
  const [status, setStatus] = useState<"routing" | "connected" | "flatlined">("routing");
  const [message, setMessage] = useState(`Operation ${run.codename}: steal ${run.caches.length} data cache${run.caches.length === 1 ? "" : "s"}, reach the jackpoint, and connect.`);
  const ice = useMemo(() => new Set(run.ice), [run.ice]);
  const caches = useMemo(() => new Set(run.caches), [run.caches]);
  const collectedSet = useMemo(() => new Set(collected), [collected]);

  const resetBoard = (nextRun = run) => {
    setNode(nextRun.entry); setCollected([]); setTrace(0); setStatus("routing");
    setMessage(`Operation ${nextRun.codename}: steal ${nextRun.caches.length} data cache${nextRun.caches.length === 1 ? "" : "s"}, reach the jackpoint, and connect.`);
  };
  const advanceTrace = (amount: number) => {
    const nextTrace = trace + amount;
    setTrace(nextTrace);
    if (nextTrace >= run.traceLimit) {
      setStatus("flatlined");
      setScore((value) => Math.max(0, value - 150));
      setMessage("TRACE COMPLETE · the deck flatlined. Retry the route or burn a new identity.");
      return false;
    }
    return true;
  };
  const enter = (next: number) => {
    if (status !== "routing" || next === node) return;
    if (ice.has(next)) {
      if (!advanceTrace(3)) return;
      setNode(run.entry);
      setScore((value) => Math.max(0, value - 50));
      setMessage("BLACK ICE · neural feedback throws you to the entry node and adds three trace.");
      return;
    }
    if (!advanceTrace(1)) return;
    setNode(next);
    if (caches.has(next) && !collectedSet.has(next)) {
      setCollected((current) => [...current, next]);
      setScore((value) => value + 175 + level * 25);
      setMessage(`DATA CACHE ${collected.length + 1}/${run.caches.length} exfiltrated. Trace ${trace + 1}/${run.traceLimit}.`);
    } else if (next === run.exit) {
      setMessage(collected.length === run.caches.length ? "Jackpoint acquired. Press Enter to connect." : `Jackpoint locked: ${run.caches.length - collected.length} cache${run.caches.length - collected.length === 1 ? "" : "s"} remain.`);
    } else setMessage(`Node ${next.toString(16).toUpperCase()} routed. Trace ${trace + 1}/${run.traceLimit}.`);
  };
  const move = (direction: Direction) => enter(adjacentJackNode(node, direction, run.size));
  const connect = () => {
    if (status !== "routing") return;
    if (node !== run.exit) { setMessage("No jackpoint here. Keep routing."); return; }
    if (collected.length !== run.caches.length) { setMessage("The construct rejects an incomplete payload. Recover every data cache."); return; }
    const bonus = Math.max(0, run.traceLimit - trace) * 25;
    setScore((value) => value + 750 + level * 150 + bonus);
    setStatus("connected");
    setMessage(`JACKED IN · ${run.codename} complete. Efficiency bonus ${bonus}.`);
  };
  const startNext = () => {
    const nextLevel = Math.min(8, level + 1);
    const nextSeed = deriveSeed(seed, score + trace + nextLevel);
    setLevel(nextLevel); setSeed(nextSeed); resetBoard(buildJackInRun(nextSeed, nextLevel));
  };
  const newRun = () => {
    const nextSeed = presentationSeed();
    setSeed(nextSeed); setLevel(1); setScore(0); resetBoard(buildJackInRun(nextSeed, 1));
  };
  const handleKey = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const direction: Partial<Record<string, Direction>> = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" };
    if (direction[event.key]) { event.preventDefault(); move(direction[event.key]!); }
    if (event.key === "Enter") { event.preventDefault(); connect(); }
    if (event.key.toLowerCase() === "r") { event.preventDefault(); resetBoard(); }
  };

  return <div className="arcade-game arcade-jackin jackin-expanded" tabIndex={0} onKeyDown={handleKey}>
    <div className="arcade-hud">
      <span>LEVEL <b>{level}</b></span><span>SCORE <b>{score}</b></span><span>DATA <b>{collected.length}/{run.caches.length}</b></span><span>TRACE <b>{trace}/{run.traceLimit}</b></span>
    </div>
    <div className="trace-meter" role="meter" aria-label="ICE trace" aria-valuemin={0} aria-valuemax={run.traceLimit} aria-valuenow={trace}><i style={{ width: `${Math.min(100, trace / run.traceLimit * 100)}%` }}/></div>
    <div className="arcade-status">NEUROMANCER DECK · {run.codename} · {status.toUpperCase()}</div>
    <div className="jack-grid" style={{ "--jack-size": run.size } as CSSProperties} role="grid" aria-label={`${run.size} by ${run.size} matrix infiltration grid`}>
      {Array.from({ length: run.size * run.size }, (_, index) => {
        const isIce = ice.has(index); const isCache = caches.has(index); const captured = collectedSet.has(index);
        const label = isIce ? "black ICE" : index === run.exit ? "jackpoint" : isCache ? captured ? "captured data cache" : "data cache" : index === node ? "current position" : "open";
        return <button role="gridcell" key={index} className={`${isIce ? "ice" : ""} ${node === index ? "active" : ""} ${index === run.exit ? "jackpoint" : ""} ${isCache ? "cache" : ""} ${captured ? "captured" : ""}`} onClick={() => {
          const directions: Direction[] = ["left", "right", "up", "down"];
          const direction = directions.find((candidate) => adjacentJackNode(node, candidate, run.size) === index);
          if (direction) move(direction); else setMessage("Route one adjacent node at a time.");
        }} aria-label={`node ${index}, ${label}`}>{isIce ? "ICE" : index === run.exit ? "JACK" : isCache && !captured ? "DATA" : node === index ? "◆" : captured ? "✓" : "·"}</button>;
      })}
    </div>
    <div className="dojo-controls jack-controls"><button onClick={() => move("left")}>←</button><button onClick={() => move("up")}>↑</button><button onClick={connect}>JACK IN</button><button onClick={() => move("down")}>↓</button><button onClick={() => move("right")}>→</button></div>
    <div className="dojo-controls run-controls">
      {status === "connected" && <button onClick={startNext}>NEXT LEVEL</button>}
      <button onClick={() => resetBoard()}>RETRY SAME MAP · R</button><button onClick={newRun}>BURN ID / NEW RUN</button>
    </div>
    <p aria-live="polite">{message}</p>
    <small>Turn-based: arrows move, Enter connects, R retries. Seeded maps are solvable and grow from 5×5 to 7×7. ICE, score, and trace are game state only.</small>
  </div>;
}

function togglePowerCell(cells: boolean[], index: number): boolean[] {
  const next = [...cells]; const row = Math.floor(index / 3);
  for (const candidate of [index, index - 3, index + 3, index - 1, index + 1]) {
    if (candidate >= 0 && candidate < 9 && (Math.abs(candidate - index) !== 1 || Math.floor(candidate / 3) === row)) next[candidate] = !next[candidate];
  }
  return next;
}

function MatrixPowerGridGame() {
  const [seed, setSeed] = useState(presentationSeed);
  const puzzle = useMemo(() => buildPowerGrid(seed), [seed]);
  const [cells, setCells] = useState(puzzle);
  const [cursor, setCursor] = useState(4);
  const [moves, setMoves] = useState(0);
  const [message, setMessage] = useState("Collapse every live substation without triggering a cascade.");
  const toggle = (index: number) => {
    const next = togglePowerCell(cells, index); const online = next.filter(Boolean).length;
    setCells(next); setMoves((value) => value + 1);
    setMessage(online === 0 ? `POWER GRID DARK in ${moves + 1} moves · intrusion complete.` : `${online} substations remain online.`);
  };
  const move = (delta: number) => setCursor((value) => {
    const row = Math.floor(value / 3), column = value % 3;
    if (delta === -1) return row * 3 + Math.max(0, column - 1);
    if (delta === 1) return row * 3 + Math.min(2, column + 1);
    if (delta === -3) return Math.max(0, value - 3);
    return Math.min(8, value + 3);
  });
  const won = cells.every((value) => !value);
  const nextGrid = () => {
    const nextSeed = deriveSeed(seed, moves + 1); const next = buildPowerGrid(nextSeed);
    setSeed(nextSeed); setCells(next); setMoves(0); setCursor(4); setMessage("New grid topology loaded.");
  };
  return <div className="arcade-game arcade-power" tabIndex={0} onKeyDown={(event) => {
    if (event.key === "ArrowLeft") move(-1); if (event.key === "ArrowRight") move(1); if (event.key === "ArrowUp") move(-3); if (event.key === "ArrowDown") move(3);
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggle(cursor); }
  }}>
    <div className="arcade-status">MATRIX POWER GRID · {cells.filter(Boolean).length} ONLINE · {moves} MOVES</div>
    <div className="power-grid">{cells.map((online, index) => <button key={index} className={`${online ? "online" : "offline"} ${index === cursor ? "cursor" : ""}`} onClick={() => { setCursor(index); toggle(index); }} aria-label={`substation ${index + 1}, ${online ? "online" : "offline"}`}>{online ? "⚡" : "·"}</button>)}</div>
    {won && <button onClick={nextGrid}>BREACH ANOTHER GRID</button>}
    <p aria-live="polite">{message}</p><small>Seeded, solvable layouts vary between breaches. Arrow keys move; Enter toggles a station and adjacent breakers.</small>
  </div>;
}

export function ThemeArcade({ character, onClose, reduced, publicModeLabel }: { character: string; onClose: () => void; reduced: boolean; publicModeLabel: (id?: string) => string }) {
  const identity = publicModeLabel(character);
  const title = identity === "Sherlock Holmes" ? "CHESS · THE FORCED CONCLUSION"
    : identity === "HAL9000" ? "DISABLE THE COMPUTER"
    : identity === "Neuromancer" ? "JACK IN / AVOID ICE"
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
    <button className="close" aria-label="Close training simulator" onClick={onClose}>×</button>
    <span className="eyebrow">OPTIONAL DIVERSION · NO ANALYTICAL MEANING</span><h2>{identity.toUpperCase()} // {title}</h2>
    {game}<small className="arcade-disclaimer">Presentation only. Randomness, scores, failures, and progress never affect evidence, confidence, dossier, command, or investigation state. Esc exits.</small>
  </section>;
}
