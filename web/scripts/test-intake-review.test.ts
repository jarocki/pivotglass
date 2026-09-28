import assert from "node:assert/strict";
import test from "node:test";
import { candidatePage, createIntakeRequestScope, selectCandidatePage } from "../app/intake-review.ts";

test("every reviewable candidate is reachable, including beyond the old 100 limit", () => {
  const items = Array.from({ length: 2000 }, (_, index) => `candidate-${index}`);
  const all = Array.from({ length: 40 }, (_, page) => candidatePage(items, page).items).flat();
  assert.deepEqual(all, items);
  assert.equal(candidatePage(items, 2).items[0], "candidate-100");
});

test("page bounds handle empty, incomplete, negative, and past-end pages", () => {
  assert.deepEqual(candidatePage([], 100), { page: 0, pageCount: 1, start: 0, items: [] });
  const items = Array.from({ length: 103 }, (_, index) => index);
  assert.deepEqual(candidatePage(items, 99), { page: 2, pageCount: 3, start: 100, items: [100, 101, 102] });
  assert.equal(candidatePage(items, -5).page, 0);
});

test("selecting a page preserves other reviewed selections without selecting unseen candidates", () => {
  const initial = new Set(["candidate-1"]);
  const selected = selectCandidatePage(initial, ["candidate-101", "candidate-102", "candidate-101"]);
  assert.deepEqual([...selected], ["candidate-1", "candidate-101", "candidate-102"]);
  assert.deepEqual([...initial], ["candidate-1"]);
  assert.equal(selected.has("candidate-103"), false);
});

test("late library reads cannot replace newer reads or a successful ingestion", () => {
  const requests = createIntakeRequestScope();
  const old = requests.begin();
  const current = requests.begin();
  assert.equal(requests.current(old), false);
  assert.equal(requests.current(current), true);
  requests.invalidate();
  assert.equal(requests.current(current), false);
});

test("workspace scopes invalidate independently and can retry after errors", () => {
  const first = createIntakeRequestScope();
  const second = createIntakeRequestScope();
  const pending = first.begin();
  const independent = second.begin();
  first.invalidate();
  assert.equal(first.current(pending), false);
  assert.equal(second.current(independent), true);
  assert.equal(first.current(first.begin()), true);
});
