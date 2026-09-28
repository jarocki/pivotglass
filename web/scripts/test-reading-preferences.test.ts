import test from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_READING, readReadingPreferences } from "../app/reading-preferences.ts";

test("reading preferences start predictable and never infer reader traits", () => {
  assert.deepEqual(readReadingPreferences(null), { textSize: "standard", spotlight: false });
  assert.deepEqual(readReadingPreferences('{"ADHD":true,"age":28,"autistic":true}'), DEFAULT_READING);
});
test("malformed and hostile saved values fail to calm defaults", () => {
  for (const value of ["{", "null", "[]", "true", '{"textSize":"giant","spotlight":"true"}']) {
    assert.deepEqual(readReadingPreferences(value), DEFAULT_READING);
  }
});
test("explicit reader choices round-trip without affecting evidence or guidance", () => {
  const expected = { textSize: "large", spotlight: true };
  assert.deepEqual(readReadingPreferences(JSON.stringify(expected)), expected);
  assert.deepEqual(Object.keys(readReadingPreferences('{"workspace":"other","textSize":"large"}')).sort(), ["spotlight", "textSize"]);
});
