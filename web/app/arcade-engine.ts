/*
 * Presentation-only arcade authority.
 *
 * Every generator here is pure and seeded so replayability can be tested without
 * allowing game randomness to leak into evidence, investigation, or command state.
 */

export type TriageCard = {
  prompt: string;
  answer: "INVESTIGATE" | "DEFER" | "DISMISS";
  rationale: string;
};

export type ContrarianRound = {
  claim: string;
  answer: "SOURCE INDEPENDENCE" | "ATTRIBUTION LEAP" | "NEGATIVE RESULT";
  rationale: string;
};

export type JackInRun = {
  seed: number;
  level: number;
  size: number;
  entry: number;
  exit: number;
  ice: number[];
  caches: number[];
  traceLimit: number;
  codename: string;
};

export const TRIAGE_CARDS: readonly TriageCard[] = [
  { prompt: "A new domain shares a registrar with one known C2.", answer: "INVESTIGATE", rationale: "The overlap is a lead worth testing, not attribution." },
  { prompt: "An unattributed IP has no current relationships.", answer: "DEFER", rationale: "Retain the lead until evidence gives it investigative priority." },
  { prompt: "A private RFC1918 address arrived from a public feed.", answer: "DISMISS", rationale: "It cannot identify public infrastructure without additional context." },
  { prompt: "A URL redirects to a newly registered domain with the same page hash as a known lure.", answer: "INVESTIGATE", rationale: "Two independently useful properties support a scoped pivot." },
  { prompt: "A single sandbox labels a signed system binary as malicious without behavior.", answer: "DEFER", rationale: "Preserve the result while seeking corroborating behavior or reputation." },
  { prompt: "An impossible IPv4 address appears only in a malformed vendor response.", answer: "DISMISS", rationale: "The value is not a valid indicator and its source is malformed." },
  { prompt: "A certificate fingerprint recurs across three recent phishing hosts.", answer: "INVESTIGATE", rationale: "Recurrence across hosts creates a concrete infrastructure pivot." },
  { prompt: "An old passive-DNS answer has no timestamp or source provenance.", answer: "DEFER", rationale: "The clue may matter, but its time and reliability are unresolved." },
  { prompt: "A file hash is all zeroes and the source marks it as a placeholder.", answer: "DISMISS", rationale: "The source explicitly says the value is not observed evidence." },
  { prompt: "An IP appears in both a victim report and a current scanner allowlist.", answer: "INVESTIGATE", rationale: "The conflicting roles require time-bounded verification." },
] as const;

export const CONTRARIAN_ROUNDS: readonly ContrarianRound[] = [
  { claim: "It shares an ASN, so it must be the same actor.", answer: "ATTRIBUTION LEAP", rationale: "One shared property is not attribution." },
  { claim: "The API returned nothing, so the host is clean.", answer: "NEGATIVE RESULT", rationale: "Absence of results is not evidence of safety." },
  { claim: "Three sources agree on the timestamp.", answer: "SOURCE INDEPENDENCE", rationale: "Corroboration matters only if the sources are genuinely independent." },
  { claim: "The same malware family means the same intrusion set.", answer: "ATTRIBUTION LEAP", rationale: "Commodity malware rarely identifies one operator." },
  { claim: "VirusTotal has no detections, so the file is benign.", answer: "NEGATIVE RESULT", rationale: "Zero detections describes current coverage, not ground truth." },
  { claim: "Two feeds report the domain, therefore two sources confirmed it.", answer: "SOURCE INDEPENDENCE", rationale: "Feeds often republish the same upstream observation." },
  { claim: "The IP geolocates to a country, so that country launched the attack.", answer: "ATTRIBUTION LEAP", rationale: "Hosting geography does not establish operator identity." },
  { claim: "The endpoint never contacted the domain again, so remediation worked.", answer: "NEGATIVE RESULT", rationale: "Silence can also mean evasion, dormancy, or lost visibility." },
  { claim: "The reports use different wording, so they must be independent.", answer: "SOURCE INDEPENDENCE", rationale: "Different prose can still derive from one underlying report." },
] as const;

export function normalizeSeed(seed: number): number {
  const normalized = Math.trunc(seed) >>> 0;
  return normalized || 0x6d2b79f5;
}

export function deriveSeed(seed: number, salt: number): number {
  let value = (normalizeSeed(seed) ^ Math.imul(salt + 1, 0x9e3779b1)) >>> 0;
  value ^= value >>> 16;
  value = Math.imul(value, 0x85ebca6b) >>> 0;
  value ^= value >>> 13;
  return normalizeSeed(value);
}

export function seededRandom(seed: number): () => number {
  let state = normalizeSeed(seed);
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

export function seededShuffle<T>(items: readonly T[], seed: number): T[] {
  const shuffled = [...items];
  const random = seededRandom(seed);
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const target = Math.floor(random() * (index + 1));
    [shuffled[index], shuffled[target]] = [shuffled[target]!, shuffled[index]!];
  }
  return shuffled;
}

export function presentationSeed(): number {
  if (typeof globalThis.crypto?.getRandomValues === "function") {
    return normalizeSeed(globalThis.crypto.getRandomValues(new Uint32Array(1))[0]!);
  }
  return normalizeSeed(Date.now());
}

function guaranteedRoute(size: number, random: () => number): number[] {
  const route = [0];
  let row = 0;
  let column = 0;
  while (row < size - 1 || column < size - 1) {
    const canMoveRight = column < size - 1;
    const canMoveDown = row < size - 1;
    if (canMoveRight && (!canMoveDown || random() < 0.5)) column += 1;
    else row += 1;
    route.push(row * size + column);
  }
  return route;
}

export function buildJackInRun(seed: number, level: number): JackInRun {
  const safeLevel = Math.max(1, Math.min(8, Math.trunc(level) || 1));
  const runSeed = deriveSeed(seed, safeLevel);
  const random = seededRandom(runSeed);
  const size = safeLevel < 3 ? 5 : safeLevel < 6 ? 6 : 7;
  const route = guaranteedRoute(size, random);
  const routeSet = new Set(route);
  const entry = 0;
  const exit = size * size - 1;
  const candidates = Array.from({ length: size * size }, (_, index) => index)
    .filter((index) => !routeSet.has(index) && index !== entry && index !== exit);
  const density = Math.min(0.18 + safeLevel * 0.025, 0.36);
  const ice = seededShuffle(candidates, deriveSeed(runSeed, 2))
    .slice(0, Math.max(4, Math.floor(candidates.length * density)))
    .sort((left, right) => left - right);
  const cacheCount = Math.min(1 + Math.floor(safeLevel / 2), 4);
  const cacheCandidates = route.slice(2, -1);
  const caches = seededShuffle(cacheCandidates, deriveSeed(runSeed, 3))
    .slice(0, Math.min(cacheCount, cacheCandidates.length))
    .sort((left, right) => left - right);
  const minimumRouteMoves = route.length - 1;
  return {
    seed: normalizeSeed(seed),
    level: safeLevel,
    size,
    entry,
    exit,
    ice,
    caches,
    traceLimit: minimumRouteMoves + Math.max(7, 13 - safeLevel),
    codename: ["WINTERMUTE", "KUANG", "STRAYLIGHT", "FREESIDE", "NEON GHOST", "BLACK SUN"][runSeed % 6]!,
  };
}

export function adjacentJackNode(node: number, direction: "left" | "right" | "up" | "down", size: number): number {
  const row = Math.floor(node / size);
  const column = node % size;
  if (direction === "left") return column === 0 ? node : node - 1;
  if (direction === "right") return column === size - 1 ? node : node + 1;
  if (direction === "up") return row === 0 ? node : node - size;
  return row === size - 1 ? node : node + size;
}

export function buildPowerGrid(seed: number): boolean[] {
  const cells = Array.from({ length: 9 }, () => false);
  const random = seededRandom(seed);
  const moves = new Set<number>();
  while (moves.size < 3 + (normalizeSeed(seed) % 4)) moves.add(Math.floor(random() * 9));
  for (const index of moves) {
    const row = Math.floor(index / 3);
    for (const candidate of [index, index - 3, index + 3, index - 1, index + 1]) {
      if (candidate >= 0 && candidate < 9 && (Math.abs(candidate - index) !== 1 || Math.floor(candidate / 3) === row)) {
        cells[candidate] = !cells[candidate];
      }
    }
  }
  return cells;
}
