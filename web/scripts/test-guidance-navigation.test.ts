import test from "node:test";
import assert from "node:assert/strict";
import { intakeTargetFor } from "../app/guidance-navigation.ts";

test("workflow steps have distinct action-matched destinations", () => {
  assert.equal(intakeTargetFor("focus_intake"), "input[type='file']");
  assert.equal(intakeTargetFor("focus_preview"), "[data-action='preview-document']");
  assert.equal(intakeTargetFor("review_candidates"), "input[type='checkbox']");
  assert.equal(intakeTargetFor("choose_admitted"), "[data-action='use-admitted-indicator']");
});
test("unknown or inherited action names cannot route or execute anything", () => {
  for (const action of ["constructor", "__proto__", "investigate", "delete", ""]) {
    assert.equal(intakeTargetFor(action), null);
  }
});
