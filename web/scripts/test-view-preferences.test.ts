import assert from "node:assert/strict";
import test from "node:test";
import { DEFAULT_VIEW, nextWidth, readViewPreferences, rootFontPercent, stepTextSize } from "../app/view-preferences.ts";

test("missing or malformed preferences fall back to defaults", () => {
  assert.deepEqual(readViewPreferences(null), DEFAULT_VIEW);
  for (const value of ["{", "null", "[]", "true"]) assert.deepEqual(readViewPreferences(value), DEFAULT_VIEW);
  assert.deepEqual(readViewPreferences('{"width":"giant","text":"huge","density":1,"spotlight":"true"}'), DEFAULT_VIEW);
});

test("preferences are choices, not inferred traits", () => {
  assert.deepEqual(readViewPreferences('{"ADHD":true,"age":58,"autistic":true}'), DEFAULT_VIEW);
  assert.deepEqual(Object.keys(readViewPreferences('{"workspace":"other","width":"full"}')).sort(), ["density", "spotlight", "text", "width"]);
});

test("valid preferences round-trip", () => {
  const expected = { width: "full", text: "xlarge", density: "compact", spotlight: true } as const;
  assert.deepEqual(readViewPreferences(JSON.stringify(expected)), expected);
});

test("v1.2 reading preferences migrate once, and the new key wins", () => {
  assert.deepEqual(readViewPreferences(null, '{"textSize":"large","spotlight":true}'), { ...DEFAULT_VIEW, text: "large", spotlight: true });
  assert.deepEqual(readViewPreferences('{"text":"compact"}', '{"textSize":"large"}').text, "compact");
});

test("text size steps clamp and widths cycle", () => {
  assert.equal(stepTextSize("standard", 1), "large");
  assert.equal(stepTextSize("xlarge", 1), "xlarge");
  assert.equal(stepTextSize("compact", -1), "compact");
  assert.equal(nextWidth("column"), "wide");
  assert.equal(nextWidth("full"), "column");
  assert.ok(rootFontPercent("standard") < rootFontPercent("large"));
});
