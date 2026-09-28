export type GuidanceLevel = "novice" | "adept" | "expert";

export type GuidanceProfile = {
  schema: 1;
  level: GuidanceLevel;
  completedWorkflows: number;
  dismissedTips: number;
  levelLocked: boolean;
};

export const NEW_GUIDANCE_PROFILE: GuidanceProfile = {
  schema: 1,
  level: "novice",
  completedWorkflows: 0,
  dismissedTips: 0,
  levelLocked: false,
};

export function suggestedGuidanceLevel(completedWorkflows: number): GuidanceLevel {
  if (completedWorkflows >= 12) return "expert";
  if (completedWorkflows >= 3) return "adept";
  return "novice";
}

/** Participation changes suggestions, never the analyst's chosen level. */
export function completedGuidanceProfile(profile: GuidanceProfile, completed: boolean): GuidanceProfile {
  return { ...profile, completedWorkflows: profile.completedWorkflows + (completed ? 1 : 0) };
}
