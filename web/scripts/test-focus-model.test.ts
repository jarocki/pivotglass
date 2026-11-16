import assert from "node:assert/strict";
import test from "node:test";
import {
  filterIndicators, groupIndicators, groupMentions, indexTags, indicatorKey,
  locateInSegments, occurrenceOrdinal, parseTagInput, type FocusCandidate, type TagDimension,
} from "../app/focus-model.ts";

const c = (value: string, start: number, type = "domain-name"): FocusCandidate => ({
  id: `${value}-${start}`, selection_key: `${value}-${start}`, entity_type: type, raw_value: value,
  normalized_value: value, start_char: start, end_char: start + value.length, start_line: 1,
});

const dims: TagDimension[] = [
  { name: "role", label: "Infrastructure role", key: "r", closed: false, ordered: false, values: [{ value: "c2", label: "C2" }, { value: "delivery", label: "Delivery" }] },
  { name: "tactic", label: "ATT&CK tactic", key: "a", closed: true, ordered: true, values: [
    { value: "initial-access", label: "TA0001 Initial Access" }, { value: "command-and-control", label: "TA0011 Command and Control" }, { value: "exfiltration", label: "TA0010 Exfiltration" }] },
  { name: "cluster", label: "Cluster", key: "c", closed: false, ordered: false, values: [] },
];

test("repeated mentions collapse into one indicator in first-mention order", () => {
  const rows = groupMentions([c("b.example", 50), c("a.example", 10), c("b.example", 5), c("x", 7, "file-hash-sha256")]);
  assert.deepEqual(rows.map((row) => row.value), ["b.example", "x", "a.example"]);
  assert.equal(rows[0].mentions.length, 2);
  assert.equal(rows[0].mentions[0].start_char, 5);
  assert.equal(rows[1].key, "file|x");
});

test("ordinal counts earlier and overlapping occurrences", () => {
  const text = "aaa evil.example evil.example aaa";
  assert.equal(occurrenceOrdinal(text, "evil.example", 4), 0);
  assert.equal(occurrenceOrdinal(text, "evil.example", 17), 1);
  assert.equal(occurrenceOrdinal("aaaa", "aa", 2), 2);
});

test("locate spans DOM text nodes split by markup", () => {
  // e.g. markdown rendered hxxp://bad_site_.example with an <em> in the middle
  const segments = ["see hxxp://bad", "_site_", ".example now and hxxp://bad_site_.example"];
  assert.deepEqual(locateInSegments(segments, "hxxp://bad_site_.example", 0), [
    { segment: 0, start: 4, end: 14 }, { segment: 1, start: 0, end: 6 }, { segment: 2, start: 0, end: 8 }]);
  assert.deepEqual(locateInSegments(segments, "hxxp://bad_site_.example", 1), [{ segment: 2, start: 17, end: 41 }]);
});

test("an occurrence the rendering does not contain is not located, never guessed", () => {
  assert.equal(locateInSegments(["one evil.example"], "evil.example", 1), null);
  assert.equal(locateInSegments(["nothing"], "evil.example", 0), null);
  assert.equal(locateInSegments(["x"], "", 0), null);
});

test("tactic grouping follows attack-path order with untagged last and multi-membership", () => {
  const indicators = groupMentions([c("a", 0), c("b", 2), c("d", 4), c("e", 6)]);
  const tags = indexTags([
    { entity_type: "domain-name", normalized_value: "a", dimension: "tactic", value: "exfiltration" },
    { entity_type: "domain-name", normalized_value: "b", dimension: "tactic", value: "initial-access" },
    { entity_type: "domain-name", normalized_value: "b", dimension: "tactic", value: "command-and-control" },
    { entity_type: "domain-name", normalized_value: "d", dimension: "role", value: "c2" },
  ]);
  const groups = groupIndicators(indicators, "tactic", tags, dims);
  assert.deepEqual(groups.map((group) => group.id), ["initial-access", "command-and-control", "exfiltration", "__untagged"]);
  assert.deepEqual(groups.map((group) => group.items.map((item) => item.value)), [["b"], ["b"], ["a"], ["d", "e"]]);
  assert.equal(groups[0].label, "TA0001 Initial Access");
  assert.equal(groups[3].label, "No ATT&CK tactic");
});

test("free-text cluster groups sort alphabetically", () => {
  const indicators = groupMentions([c("a", 0), c("b", 2)]);
  const tags = indexTags([
    { entity_type: "domain-name", normalized_value: "a", dimension: "cluster", value: "zeta kit" },
    { entity_type: "domain-name", normalized_value: "b", dimension: "cluster", value: "alpha kit" }]);
  assert.deepEqual(groupIndicators(indicators, "cluster", tags, dims).map((group) => group.id), ["alpha kit", "zeta kit"]);
});

test("filter combines value, type, and dimension:value terms", () => {
  const indicators = groupMentions([c("cdn.evil.example", 0), c("203.0.113.7", 30, "ipv4-addr"), c("https://x.example/a", 50, "url")]);
  const tags = indexTags([{ entity_type: "ipv4-addr", normalized_value: "203.0.113.7", dimension: "role", value: "c2" }]);
  assert.deepEqual(filterIndicators(indicators, "role:c2", tags).map((item) => item.value), ["203.0.113.7"]);
  assert.deepEqual(filterIndicators(indicators, "evil", tags).map((item) => item.value), ["cdn.evil.example"]);
  assert.deepEqual(filterIndicators(indicators, "ipv4 c2", tags).map((item) => item.value), ["203.0.113.7"]);
  assert.deepEqual(filterIndicators(indicators, "https://x", tags).map((item) => item.value), ["https://x.example/a"]);
  assert.equal(filterIndicators(indicators, "", tags).length, 3);
});

test("tag palette accepts bare known values and dimension:value", () => {
  assert.deepEqual(parseTagInput("C2", dims), { dimension: "role", value: "c2" });
  assert.deepEqual(parseTagInput("command-and-control", dims), { dimension: "tactic", value: "command-and-control" });
  assert.deepEqual(parseTagInput("cluster: Kit A", dims), { dimension: "cluster", value: "kit a" });
  assert.equal(parseTagInput("unknownthing", dims), null);
  assert.equal(indicatorKey("file-hash-md5", "ab"), "file|ab");
});
