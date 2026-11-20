export type GuidanceLevel = "novice" | "adept" | "expert";

export type GuidanceProfile = {
  schema: 1;
  level: GuidanceLevel;
  completedWorkflows: number;
  dismissedTips: number;
  levelLocked: boolean;
};

/**
 * New analysts start at "expert": no unasked tutoring (#27, expertise-reversal
 * effect). Novice coaching is an explicit choice in Help, or one click from
 * the empty Activity pane.
 */
export const NEW_GUIDANCE_PROFILE: GuidanceProfile = {
  schema: 1,
  level: "expert",
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

/**
 * Parse a stored profile. Before v1.3.0 every analyst defaulted to "novice";
 * an unlocked novice level was never chosen, so it becomes the new default.
 */
export function readGuidanceProfile(raw: string | null): GuidanceProfile {
  try {
    const parsed = raw ? JSON.parse(raw) as Partial<GuidanceProfile> : null;
    if (!parsed || typeof parsed !== "object") return { ...NEW_GUIDANCE_PROFILE };
    const levelLocked = Boolean(parsed.levelLocked);
    const stored = parsed.level === "adept" || parsed.level === "expert" || parsed.level === "novice" ? parsed.level : NEW_GUIDANCE_PROFILE.level;
    return {
      schema: 1,
      level: stored === "novice" && !levelLocked ? NEW_GUIDANCE_PROFILE.level : stored,
      completedWorkflows: Math.max(0, Number(parsed.completedWorkflows) || 0),
      dismissedTips: Math.max(0, Number(parsed.dismissedTips) || 0),
      levelLocked,
    };
  } catch { return { ...NEW_GUIDANCE_PROFILE }; }
}
