/** Explicit tutorial destinations; no action here executes enrichment. */
export function intakeTargetFor(action: string): string | null {
  const targets: Record<string, string> = {
    focus_intake: "input[type='file']",
    focus_preview: "[data-action='preview-document']",
    review_candidates: "input[type='checkbox']",
    choose_admitted: "[data-action='use-admitted-indicator']",
  };
  return Object.hasOwn(targets, action) ? targets[action] : null;
}
