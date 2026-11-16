/** Explicit tutorial destinations; no action here executes enrichment. */
export function intakeTargetFor(action: string): string | null {
  const targets: Record<string, string> = {
    focus_intake: "[data-action='choose-source']",
    focus_preview: "[data-action='reopen-focus']",
    review_candidates: "[data-action='reopen-focus'], [data-action='open-stored-source']",
    choose_admitted: "[data-action='use-admitted-indicator']",
  };
  return Object.hasOwn(targets, action) ? targets[action] : null;
}
