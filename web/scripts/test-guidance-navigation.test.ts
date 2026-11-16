import test from "node:test";
import assert from "node:assert/strict";
import { intakeTargetFor } from "../app/guidance-navigation.ts";

test("workflow steps have distinct action-matched destinations", () => {
  assert.equal(intakeTargetFor("focus_intake"), "[data-action='choose-source']");
  assert.equal(intakeTargetFor("focus_preview"), "[data-action='reopen-focus']");
  assert.equal(intakeTargetFor("review_candidates"), "[data-action='reopen-focus'], [data-action='open-stored-source']");
  assert.equal(intakeTargetFor("choose_admitted"), "[data-action='use-admitted-indicator']");
});
test("unknown or inherited action names cannot route or execute anything", () => {
  for (const action of ["constructor", "__proto__", "investigate", "delete", ""]) {
    assert.equal(intakeTargetFor(action), null);
  }
});
