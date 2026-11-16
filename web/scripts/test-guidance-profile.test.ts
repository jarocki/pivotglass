import assert from "node:assert/strict";
import test from "node:test";

import {
  NEW_GUIDANCE_PROFILE,
  completedGuidanceProfile,
  readGuidanceProfile,
  suggestedGuidanceLevel,
} from "../app/guidance-profile.ts";

test("new analysts start without unasked tutoring", () => {
  assert.equal(NEW_GUIDANCE_PROFILE.level, "expert");
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

test("an unchosen v1.2 novice default migrates; a chosen level is kept", () => {
  assert.equal(readGuidanceProfile('{"level":"novice","levelLocked":false}').level, "expert");
  assert.equal(readGuidanceProfile('{"level":"novice","levelLocked":true}').level, "novice");
  assert.equal(readGuidanceProfile('{"level":"adept"}').level, "adept");
  assert.deepEqual(readGuidanceProfile("{"), NEW_GUIDANCE_PROFILE);
  assert.deepEqual(readGuidanceProfile(null), NEW_GUIDANCE_PROFILE);
});
