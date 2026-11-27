/** Pure grouping for the Investigate indicator table (#32); unit-tested in node. */

export type TableIndicator = { reference: string; stix_id: string; type?: string; value?: string };
export type TableTag = { entity_type: string; normalized_value: string; dimension: string; value: string };
export type AchSummary = {
  hypotheses: number;
  evidence_rows: number;
  leaders: Array<{ label: string; statement: string }>;
  strongest_disconfirming: { evidence: string; diagnosticity: string; hypothesis: string } | null;
};

export type Grouping = "cluster" | "role";

export function groupIndicatorRows(indicators: TableIndicator[], tags: TableTag[], grouping: Grouping) {
  const byValue = new Map<string, TableTag[]>();
  const key = (type: string, value: string) => `${type}|${value}`;
  for (const tag of tags) byValue.set(key(tag.entity_type, tag.normalized_value), [...(byValue.get(key(tag.entity_type, tag.normalized_value)) ?? []), tag]);
  const rows = indicators.filter((item) => item.value).map((item) => {
    const own = byValue.get(key(item.type ?? "", item.value!)) ?? [];
    const pick = (dimension: string) => [...new Set(own.filter((tag) => tag.dimension === dimension).map((tag) => tag.value))].sort();
    return { ...item, roles: pick("role"), tactics: pick("tactic"), clusters: pick("cluster") };
  });
  const groups = new Map<string, typeof rows>();
  for (const row of rows) {
    const keys = grouping === "cluster" ? row.clusters : row.roles;
    for (const key of keys.length ? keys : [""]) groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  const ordered = [...groups.entries()].sort(([a], [b]) => (a === "" ? 1 : 0) - (b === "" ? 1 : 0) || a.localeCompare(b));
  return ordered.map(([key, items]) => ({
    key,
    label: key || (grouping === "cluster" ? "No cluster" : "No role"),
    items: items.sort((a, b) => Number(!a.roles.length) - Number(!b.roles.length)
      || (a.roles[0] ?? "").localeCompare(b.roles[0] ?? "") || (a.value ?? "").localeCompare(b.value ?? "")),
  }));
}

