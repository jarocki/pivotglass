import assert from "node:assert/strict";
import test from "node:test";
import {
  ADVISOR_COOLDOWN_MS,
  ADVISOR_IDLE_MS,
  advisorCanInterrupt,
} from "../app/advisor-idle.ts";

const now = 2_000_000;

test("advisor waits for the selected extended-idle threshold", () => {
  const common = {
    now,
    lastPresentedAt: 0,
    busy: false,
    overlayOpen: false,
    adviceVisible: false,
  };
  assert.equal(advisorCanInterrupt({
    ...common,
    narration: "full",
    lastActivityAt: now - ADVISOR_IDLE_MS.full + 1,
  }), false);
  assert.equal(advisorCanInterrupt({
    ...common,
    narration: "full",
    lastActivityAt: now - ADVISOR_IDLE_MS.full,
  }), true);
  assert.ok(ADVISOR_IDLE_MS.brief > ADVISOR_IDLE_MS.full);
});

test("active work, overlays, visible advice, and cooldown prevent interruption", () => {
  const common = {
    now,
    lastActivityAt: now - ADVISOR_IDLE_MS.full,
    lastPresentedAt: now - ADVISOR_COOLDOWN_MS,
    narration: "full" as const,
    busy: false,
    overlayOpen: false,
    adviceVisible: false,
  };
  assert.equal(advisorCanInterrupt({ ...common, busy: true }), false);
  assert.equal(advisorCanInterrupt({ ...common, overlayOpen: true }), false);
  assert.equal(advisorCanInterrupt({ ...common, adviceVisible: true }), false);
  assert.equal(advisorCanInterrupt({
    ...common,
    lastPresentedAt: now - ADVISOR_COOLDOWN_MS + 1,
  }), false);
  assert.equal(advisorCanInterrupt({ ...common, narration: "off" }), false);
});
