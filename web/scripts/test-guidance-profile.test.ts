import assert from "node:assert/strict";
import test from "node:test";

import {
  NEW_GUIDANCE_PROFILE,
  completedGuidanceProfile,
  suggestedGuidanceLevel,
} from "../app/guidance-profile.ts";

test("new analysts start with step-by-step novice guidance", () => {
  assert.equal(NEW_GUIDANCE_PROFILE.level, "novice");
  assert.equal(NEW_GUIDANCE_PROFILE.completedWorkflows, 0);
  assert.equal(NEW_GUIDANCE_PROFILE.levelLocked, false);
});

test("lighter guidance is suggested after completed workflows", () => {
  assert.equal(suggestedGuidanceLevel(0), "novice");
  assert.equal(suggestedGuidanceLevel(2), "novice");
  assert.equal(suggestedGuidanceLevel(3), "adept");
  assert.equal(suggestedGuidanceLevel(11), "adept");
  assert.equal(suggestedGuidanceLevel(12), "expert");
});

test("participation never silently promotes an analyst", () => {
  for (const level of ["novice", "adept", "expert"] as const) {
    const profile = { ...NEW_GUIDANCE_PROFILE, level, completedWorkflows: 12 };
    assert.equal(completedGuidanceProfile(profile, true).level, level);
    assert.equal(completedGuidanceProfile(profile, true).completedWorkflows, 13);
    assert.equal(completedGuidanceProfile(profile, false).completedWorkflows, 12);
  }
});
