"use client";

import type { GuidanceLevel } from "./guidance-profile";

export type WorkflowStage =
  | "welcome"
  | "file_selected"
  | "preview_complete"
  | "source_ingested"
  | "entities_admitted"
  | "investigation_complete";

export type GuidedAction =
  | "frame_questions"
  | "focus_command"
  | "focus_intake"
  | "focus_preview"
  | "choose_admitted"
  | "review_candidates"
  | "review_activity"
  | "review_evidence";

const CONTENT: Record<WorkflowStage, {
  step: string;
  title: string;
  body: string;
  action: GuidedAction;
  actionLabel: string;
  alternateAction?: GuidedAction;
  alternateLabel?: string;
  focus: string;
}> = {
  welcome: {
    step: "1 OF 5 · START",
    title: "Start by framing an investigative question",
    body: "Walk through what data you have, what happened, and what is unknown. Learn to turn those answers into questions you can test. You can also start with one indicator.",
    action: "frame_questions",
    actionLabel: "BUILD QUESTIONS THROUGH Q&A",
    alternateAction: "focus_command",
    alternateLabel: "ENTER ONE INDICATOR",
    focus: "command",
  },
  file_selected: {
    step: "2 OF 5 · INSPECT",
    title: "Preview the selected source locally",
    body: "Preview extracts bounded text and candidate strings without changing the workspace. Review the parser warnings before admission.",
    action: "focus_preview",
    actionLabel: "SHOW THE PREVIEW CONTROL",
    focus: "intake",
  },
  preview_complete: {
    step: "3 OF 5 · CHOOSE",
    title: "Select only the entities you want to admit",
    body: "Candidates are text matches, not facts. Check the useful indicators, then ingest the source and the selected entities together with provenance.",
    action: "review_candidates",
    actionLabel: "REVIEW CANDIDATES",
    focus: "intake",
  },
  source_ingested: {
    step: "3 OF 5 · SOURCE STORED",
    title: "The source is stored; no entities were admitted",
    body: "That is a valid choice. Reselect the local file and preview it again when you are ready to add candidate entities. The stored source receipt remains in the library.",
    action: "focus_intake",
    actionLabel: "RETURN TO INTAKE",
    focus: "intake",
  },
  entities_admitted: {
    step: "4 OF 5 · ENRICH",
    title: "Selected entities are now in the workspace",
    body: "Adding indicators does not run enrichment. Choose an added indicator below to put it in the command field, then choose Investigate when you are ready. Provenance is retained; no verdict or attribution is implied.",
    action: "choose_admitted",
    actionLabel: "CHOOSE AN ADDED INDICATOR",
    focus: "intake",
  },
  investigation_complete: {
    step: "5 OF 5 · REVIEW",
    title: "Review what changed and what remains missing",
    body: "Open Evidence to inspect provenance, contradictions, confidence, and incomplete Dossier dimensions before drawing a conclusion.",
    action: "review_evidence",
    actionLabel: "REVIEW EVIDENCE",
    focus: "activity",
  },
};

export function guidanceFocus(stage: WorkflowStage): string {
  return CONTENT[stage].focus;
}

export function GraduatedHelp({
  stage,
  level,
  onAction,
  onDismiss,
}: {
  stage: WorkflowStage;
  level: GuidanceLevel;
  onAction: (action: GuidedAction) => void;
  onDismiss: () => void;
}) {
  const content = CONTENT[stage];
  return (
    <aside
      className={`graduated-help level-${level}`}
      role="dialog"
      aria-modal="false"
      aria-live="polite"
      aria-labelledby="graduated-help-title"
      aria-describedby="graduated-help-description"
    >
      <strong className="guide-kicker">GUIDED NEXT STEP</strong>
      <header>
        <span>{level.toUpperCase()} GUIDANCE · {content.step}</span>
        <button type="button" aria-label="Dismiss this workflow tip" onClick={onDismiss}>×</button>
      </header>
      <h2 id="graduated-help-title">{content.title}</h2>
      <p id="graduated-help-description">{content.body}</p>
      <div>
        <button type="button" onClick={() => onAction(content.action)}>{content.actionLabel}</button>
        {content.alternateAction && <button type="button" onClick={() => onAction(content.alternateAction!)}>{content.alternateLabel}</button>}
        <button type="button" className="quiet" onClick={onDismiss}>NOT NOW</button>
      </div>
      <small>Workflow guidance is presentation, not evidence. Change or reset the guidance level in Help at any time.</small>
    </aside>
  );
}
