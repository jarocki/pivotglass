import assert from "node:assert/strict";
import test from "node:test";

import { placeGuidance, type RectLike } from "../app/guidance-position.ts";

function rect(top: number, left: number, width: number, height: number): RectLike {
  return { top, left, width, height, right: left + width, bottom: top + height };
}

function assertInside(
  placement: ReturnType<typeof placeGuidance>,
  panel: Pick<RectLike, "width" | "height">,
  viewport: { width: number; height: number },
) {
  assert.ok(placement.top >= 12);
  assert.ok(placement.left >= 12);
  assert.ok(placement.top + Math.min(panel.height, viewport.height - 24) <= viewport.height - 12);
  assert.ok(placement.left + Math.min(panel.width, viewport.width - 24) <= viewport.width - 12);
}

test("guidance sits immediately below an early focused task when space permits", () => {
  const target = rect(90, 180, 680, 80);
  const panel = { width: 420, height: 220 };
  const viewport = { width: 1024, height: 768 };
  const placement = placeGuidance(target, panel, viewport);

  assert.equal(placement.relation, "below");
  assert.equal(placement.top, target.bottom + 10);
  assertInside(placement, panel, viewport);
});

test("guidance moves above a low focused task instead of falling below the viewport", () => {
  const target = rect(650, 220, 900, 80);
  const panel = { width: 420, height: 240 };
  const viewport = { width: 1440, height: 900 };
  const placement = placeGuidance(target, panel, viewport);

  assert.equal(placement.relation, "above");
  assert.equal(placement.top + panel.height + 10, target.top);
  assertInside(placement, panel, viewport);
});

test("guidance remains visible in a 320 by 568 viewport", () => {
  const target = rect(170, 0, 320, 300);
  const panel = { width: 420, height: 300 };
  const viewport = { width: 320, height: 568 };
  const placement = placeGuidance(target, panel, viewport);

  assert.equal(placement.relation, "overlap");
  assertInside(placement, panel, viewport);
});

test("guidance stays near the viewport when its focused task extends below the fold", () => {
  const target = rect(520, 40, 310, 900);
  const panel = { width: 360, height: 230 };
  const viewport = { width: 390, height: 844 };
  const placement = placeGuidance(target, panel, viewport);

  assert.equal(placement.relation, "above");
  assertInside(placement, panel, viewport);
  assert.ok(placement.top < 590, "the guide should not follow off-screen content down the page");
});
