/**
 * Pure logic for indicator focus mode: grouping mentions into indicators,
 * locating a mention inside a rendered view, and clustering by tag dimension.
 * No DOM access here, so every rule is unit-tested in node.
 */

export type FocusCandidate = {
  id: string;
  selection_key: string;
  entity_type: string;
  raw_value: string;
  normalized_value: string;
  start_char: number;
  end_char: number;
  start_line: number;
  state?: string;
};

export type Tag = { entity_type: string; normalized_value: string; dimension: string; value: string; note?: string | null; created_by?: string; created_at?: string };

export type TagDimension = {
  name: string; label: string; key: string; closed: boolean; ordered: boolean;
  values: Array<{ value: string; label: string }>;
};

export type Relation = { key: string; relation?: string };
export type DocumentRelations = Record<string, { structural: Relation[]; same_line: Relation[]; same_paragraph: Relation[] }>;

export type IndicatorContext = {
  entity: { id: string; type: string } | null;
  relationships: Array<{ relationship_type: string; direction: "in" | "out"; other_label: string; other_type: string }>;
  observed_by: Array<{ source: string; count: number; latest: string }>;
  documents: Array<{ occurrence_id: string; filename: string; mentions: number; copies: number; admitted: boolean }>;
  tags: Tag[];
  investigated_at: string | null;
  /** Earliest evidence observation in the workspace; null when never collected. */
  first_seen?: string | null;
  /** Curated-list / hashlookup recognition: context, never a verdict (DEC-KNOWN-GOOD-001). */
  known?: KnownMatch[];
};

export type KnownMatch = { list_id: string; category: "benign" | "scanner" | "shared" | "sinkhole" | "contested" | "reserved"; label: string; matched: string; source: string; set_aside: boolean; category_label: string };

/** True when the analyst may set this indicator aside as known good or scanner noise. */
export function canSetAside(context?: IndicatorContext): boolean {
  const known = context?.known ?? [];
  return known.length > 0 && known[0].set_aside && !known.some((item) => item.category === "contested")
    && !(context?.tags ?? []).some((tag) => tag.dimension === "role" && tag.value === "benign");
}

export type FocusIndicator = {
  key: string;
  entityType: string;
  value: string;
  mentions: FocusCandidate[];
};

/** Matches the server's ``indicator_key``: file hashes are admitted as ``file``. */
export function canonicalType(entityType: string): string {
  return entityType.startsWith("file-hash-") ? "file" : entityType;
}

export function indicatorKey(entityType: string, value: string): string {
  return `${canonicalType(entityType)}|${value}`;
}

/** One row per distinct indicator, mentions in source order, rows in first-mention order. */
export function groupMentions(candidates: FocusCandidate[]): FocusIndicator[] {
  const byKey = new Map<string, FocusIndicator>();
  for (const candidate of [...candidates].sort((a, b) => a.start_char - b.start_char)) {
    const key = indicatorKey(candidate.entity_type, candidate.normalized_value);
    const existing = byKey.get(key);
    if (existing) existing.mentions.push(candidate);
    else byKey.set(key, { key, entityType: canonicalType(candidate.entity_type), value: candidate.normalized_value, mentions: [candidate] });
  }
  return [...byKey.values()];
}

/** How many times ``raw`` occurs in ``text`` before ``start`` (overlapping matches count). */
export function occurrenceOrdinal(text: string, raw: string, start: number): number {
  if (!raw) return 0;
  let count = 0;
  for (let index = text.indexOf(raw); index >= 0 && index < start; index = text.indexOf(raw, index + 1)) count += 1;
  return count;
}

export type SegmentPiece = { segment: number; start: number; end: number };

/**
 * Find the ``ordinal``-th occurrence of ``raw`` across consecutive text
 * segments (DOM text nodes) and return the per-segment pieces to highlight.
 * Returns null when the rendering does not contain that many occurrences;
 * the caller must say "not located" rather than guess.
 */
export function locateInSegments(segments: string[], raw: string, ordinal: number): SegmentPiece[] | null {
  if (!raw) return null;
  const joined = segments.join("");
  let index = joined.indexOf(raw);
  for (let seen = 0; index >= 0 && seen < ordinal; seen += 1) index = joined.indexOf(raw, index + 1);
  if (index < 0) return null;
  const end = index + raw.length;
  const pieces: SegmentPiece[] = [];
  let offset = 0;
  segments.forEach((segment, position) => {
    const segmentEnd = offset + segment.length;
    const from = Math.max(index, offset);
    const to = Math.min(end, segmentEnd);
    if (from < to) pieces.push({ segment: position, start: from - offset, end: to - offset });
    offset = segmentEnd;
  });
  return pieces;
}

export type TagIndex = Map<string, Tag[]>;

export function indexTags(tags: Tag[]): TagIndex {
  const index: TagIndex = new Map();
  for (const tag of tags) {
    const key = indicatorKey(tag.entity_type, tag.normalized_value);
    index.set(key, [...(index.get(key) ?? []), tag]);
  }
  return index;
}

export type Grouping = "source" | "type" | string; // string = tag dimension name

export type IndicatorGroup = { id: string; label: string; items: FocusIndicator[] };

/**
 * Cluster indicators by a tag dimension. An indicator with several values on
 * the dimension appears in each group; untagged indicators come last. Ordered
 * dimensions (ATT&CK tactic) follow the catalog order, giving the attack path.
 */
export function groupIndicators(
  indicators: FocusIndicator[],
  grouping: Grouping,
  tags: TagIndex,
  dimensions: TagDimension[],
): IndicatorGroup[] {
  if (grouping === "source") return [{ id: "all", label: "", items: indicators }];
  if (grouping === "type") {
    const groups = new Map<string, FocusIndicator[]>();
    for (const item of indicators) groups.set(item.entityType, [...(groups.get(item.entityType) ?? []), item]);
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([id, items]) => ({ id, label: id, items }));
  }
  const dimension = dimensions.find((item) => item.name === grouping);
  const groups = new Map<string, FocusIndicator[]>();
  const untagged: FocusIndicator[] = [];
  for (const item of indicators) {
    const values = (tags.get(item.key) ?? []).filter((tag) => tag.dimension === grouping).map((tag) => tag.value);
    if (!values.length) untagged.push(item);
    for (const value of new Set(values)) groups.set(value, [...(groups.get(value) ?? []), item]);
  }
  const catalog = dimension?.values ?? [];
  const rank = (value: string) => { const at = catalog.findIndex((item) => item.value === value); return at < 0 ? catalog.length : at; };
  const label = (value: string) => catalog.find((item) => item.value === value)?.label ?? value;
  const ordered = [...groups.entries()].sort(([a], [b]) => (dimension?.ordered || catalog.length ? rank(a) - rank(b) : 0) || a.localeCompare(b));
  const result = ordered.map(([id, items]) => ({ id, label: label(id), items }));
  if (untagged.length) result.push({ id: "__untagged", label: `No ${dimension?.label ?? grouping}`, items: untagged });
  return result;
}

/** Filter by value, type, ``dimension:value`` tag terms, or ``is:new`` / ``is:known`` (all terms must match). */
export function filterIndicators(
  indicators: FocusIndicator[], query: string, tags: TagIndex, isKnown: (key: string) => boolean = () => false,
): FocusIndicator[] {
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return indicators;
  return indicators.filter((item) => terms.every((term) => {
    if (term === "is:new") return !isKnown(item.key);
    if (term === "is:known") return isKnown(item.key);
    const own = tags.get(item.key) ?? [];
    if (term.includes(":") && !term.includes("//")) {
      const [dimension, value] = term.split(":", 2);
      const known = own.some((tag) => tag.dimension === dimension);
      if (known || ["role", "tactic", "cluster", "status"].includes(dimension)) {
        return own.some((tag) => tag.dimension === dimension && (!value || tag.value.includes(value)));
      }
    }
    return item.value.toLocaleLowerCase().includes(term) || item.entityType.includes(term)
      || own.some((tag) => tag.value.includes(term));
  }));
}

/** Parse palette input such as ``c2``, ``role:c2``, ``cluster:kit a`` into a tag. */
export function parseTagInput(input: string, dimensions: TagDimension[]): { dimension: string; value: string } | null {
  const text = input.trim().toLocaleLowerCase();
  if (!text) return null;
  const colon = text.indexOf(":");
  if (colon > 0) {
    const dimension = dimensions.find((item) => item.name === text.slice(0, colon).trim());
    const value = text.slice(colon + 1).trim();
    if (dimension && value) return { dimension: dimension.name, value };
  }
  // A bare ATT&CK technique ID is a technique-level tactic tag (#31).
  if (/^t\d{4}(\.\d{3})?$/.test(text) && dimensions.some((item) => item.name === "tactic")) return { dimension: "tactic", value: text };
  // Exact values win over labels across every dimension: "exfiltration" is the
  // ATT&CK tactic, even though the role "exfil" is labelled "Exfiltration".
  for (const exact of [true, false]) {
    for (const dimension of dimensions) {
      const match = dimension.values.find((item) => exact ? item.value === text : item.label.toLocaleLowerCase() === text);
      if (match) return { dimension: dimension.name, value: match.value };
    }
  }
  return null;
}

/**
 * Analyst-safe presentation form. Mirrors ``defang_indicator_value`` on the
 * server; both are checked against tests/fixtures/defang_cases.json.
 */
export function defangValue(value: string, entityType: string): string {
  const kind = entityType.toLocaleLowerCase();
  if (kind === "url" || kind === "uri" || /^https?:\/\//i.test(value)) {
    const separator = value.indexOf("://");
    if (separator < 0) return value.replaceAll(".", "[.]"); // a scheme-less URL value
    const original = value.slice(0, separator);
    const scheme = { http: "hxxp", https: "hxxps" }[original.toLocaleLowerCase()] ?? original;
    return `${scheme}[:]//${value.slice(separator + 3).replaceAll(".", "[.]")}`;
  }
  if (["email", "email-addr", "email-address"].includes(kind) || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
    const at = value.lastIndexOf("@");
    if (at >= 0) return `${value.slice(0, at)}[@]${value.slice(at + 1).replaceAll(".", "[.]")}`;
  }
  if (["ipv4-addr", "ipv6-addr", "domain-name", "hostname", "ip"].includes(kind)) return value.replaceAll(".", "[.]");
  return value;
}

/** Newline-separated values for the clipboard, in list order. */
export function clipboardText(items: Array<{ value: string; entityType: string }>, defanged: boolean): string {
  return items.map((item) => defanged ? defangValue(item.value, item.entityType) : item.value).join("\n");
}

/**
 * Split a long hex digest into groups of 8 for reading and comparison. The
 * groups are display-only: callers render them as adjacent spans so a copy
 * still yields the raw digest.
 */
export function hexGroups(value: string): string[] | null {
  if (!/^[0-9a-f]{24,}$/i.test(value)) return null;
  return value.match(/.{1,8}/g) ?? null;
}

export type FocusSort = "source" | "new-first" | "first-seen" | "value";
export const FOCUS_SORTS: Array<{ value: FocusSort; label: string }> = [
  { value: "source", label: "Source order" },
  { value: "new-first", label: "New first" },
  { value: "first-seen", label: "First seen, oldest" },
  { value: "value", label: "Value A–Z" },
];

/**
 * Order the list (#29). Source order anchors on the first indicator a report
 * names; the other orders let the analyst start elsewhere. Ties keep source order.
 */
export function sortIndicators(
  indicators: FocusIndicator[], sort: FocusSort, context: Record<string, IndicatorContext | undefined>,
): FocusIndicator[] {
  if (sort === "source") return indicators;
  const position = new Map(indicators.map((item, index) => [item.key, index]));
  const known = (item: FocusIndicator) => Boolean(context[item.key]?.entity);
  const seen = (item: FocusIndicator) => context[item.key]?.first_seen ?? null;
  const compare: Record<Exclude<FocusSort, "source">, (a: FocusIndicator, b: FocusIndicator) => number> = {
    "new-first": (a, b) => Number(known(a)) - Number(known(b)),
    // Never-seen indicators sort last: there is no first-seen time to order by.
    "first-seen": (a, b) => (seen(a) === null ? 1 : 0) - (seen(b) === null ? 1 : 0) || (seen(a) ?? "").localeCompare(seen(b) ?? ""),
    value: (a, b) => a.value.localeCompare(b.value),
  };
  return [...indicators].sort((a, b) => compare[sort](a, b) || position.get(a.key)! - position.get(b.key)!);
}
