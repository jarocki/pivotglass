import assert from "node:assert/strict";
import test from "node:test";
import {
  CONTRARIAN_ROUNDS,
  TRIAGE_CARDS,
  adjacentJackNode,
  buildJackInRun,
  buildPowerGrid,
  seededShuffle,
} from "../app/arcade-engine.ts";

function reachable(run: ReturnType<typeof buildJackInRun>): Set<number> {
  const visited = new Set<number>([run.entry]);
  const queue = [run.entry];
  const ice = new Set(run.ice);
  while (queue.length) {
    const node = queue.shift()!;
    for (const direction of ["left", "right", "up", "down"] as const) {
      const next = adjacentJackNode(node, direction, run.size);
      if (next !== node && !ice.has(next) && !visited.has(next)) {
        visited.add(next);
        queue.push(next);
      }
    }
  }
  return visited;
}

test("seeded content order is reproducible but varies by seed", () => {
  const first = seededShuffle(TRIAGE_CARDS, 701).map((card) => card.prompt);
  assert.deepEqual(first, seededShuffle(TRIAGE_CARDS, 701).map((card) => card.prompt));
  assert.notDeepEqual(first, seededShuffle(TRIAGE_CARDS, 702).map((card) => card.prompt));
  assert.ok(TRIAGE_CARDS.length >= 10);
  assert.ok(CONTRARIAN_ROUNDS.length >= 9);
});

test("Jack In generation is deterministic and changes between seeds", () => {
  assert.deepEqual(buildJackInRun(0xdeadbeef, 4), buildJackInRun(0xdeadbeef, 4));
  const layouts = new Set(Array.from({ length: 12 }, (_, index) => JSON.stringify(buildJackInRun(1000 + index, 4).ice)));
  assert.ok(layouts.size >= 10, `expected at least 10 distinct layouts, received ${layouts.size}`);
});

test("every generated Jack In objective is reachable without crossing ICE", () => {
  for (let level = 1; level <= 8; level += 1) {
    for (let seed = 1; seed <= 100; seed += 1) {
      const run = buildJackInRun(seed, level);
      const open = reachable(run);
      assert.ok(open.has(run.exit), `exit unreachable for seed ${seed}, level ${level}`);
      for (const cache of run.caches) assert.ok(open.has(cache), `cache ${cache} unreachable for seed ${seed}, level ${level}`);
    }
  }
});

test("Jack In difficulty stays bounded and progresses from 5x5 to 7x7", () => {
  const runs = Array.from({ length: 12 }, (_, index) => buildJackInRun(42, index - 1));
  for (const run of runs) {
    assert.ok(run.level >= 1 && run.level <= 8);
    assert.ok(run.size >= 5 && run.size <= 7);
    assert.ok(run.caches.length >= 1 && run.caches.length <= 4);
    assert.ok(run.ice.length < run.size * run.size);
    assert.ok(run.traceLimit > run.size * 2 - 2);
  }
  assert.equal(buildJackInRun(42, 1).size, 5);
  assert.equal(buildJackInRun(42, 8).size, 7);
  assert.ok(buildJackInRun(42, 8).caches.length > buildJackInRun(42, 1).caches.length);
});

test("grid movement never wraps across rows", () => {
  assert.equal(adjacentJackNode(4, "right", 5), 4);
  assert.equal(adjacentJackNode(5, "left", 5), 5);
  assert.equal(adjacentJackNode(0, "up", 5), 0);
  assert.equal(adjacentJackNode(24, "down", 5), 24);
});

test("power-grid puzzles are seeded, varied, and non-empty", () => {
  assert.deepEqual(buildPowerGrid(91), buildPowerGrid(91));
  const puzzles = Array.from({ length: 20 }, (_, index) => buildPowerGrid(91 + index));
  assert.ok(puzzles.every((puzzle) => puzzle.some(Boolean)));
  assert.ok(new Set(puzzles.map((puzzle) => JSON.stringify(puzzle))).size >= 12);
});
