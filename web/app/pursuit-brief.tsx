"use client";

export type PursuitBriefAction = {
  id: string;
  label: string;
  rationale: string;
  category: "required" | "current_work" | "method_suggestion" | "optional_improvement";
  action_type: "focus" | "command" | "pane" | "workbench";
  value: string;
  basis: Array<{ kind: string; id: string }>;
  permission: "review_only" | "local_read_only" | "analyst_record" | "remote_enrichment" | "external_publication";
  confirmation_required: boolean;
  auto_eligible: boolean;
  content_class: "method_derived_workflow";
};

export type PursuitBriefState = {
  schema_version: "1.0";
  policy: {
    id: string;
    content_class: "method_derived_workflow";
    human_authority: string;
  };
  subject: {
    title: string;
    question?: string | null;
    target?: string | null;
    workspace_state: string;
  };
  now: { stage: string; status: string };
  next_action: PursuitBriefAction;
  progress: Array<{
    id: string;
    label: string;
    current: number;
    total: number;
    detail: string;
  }>;
  open_work: {
    contradictions: number;
    knowledge_gaps: number;
    pending_reviews: number;
    queued_enrichments: number;
    weak_dossier_dimensions: number;
    failed_enrichments: number;
  };
  weakest_dimensions: Array<{ name: string; status: string; evidence_count: number }>;
  recent_change: {
    summary: string;
    content_class: string;
    basis: Array<{ kind: string; id: string }>;
  };
  object_count: number;
};

const CATEGORY_LABELS: Record<PursuitBriefAction["category"], string> = {
  required: "Needs attention",
  current_work: "In progress",
  method_suggestion: "Suggested next step",
  optional_improvement: "Worth reviewing",
};

const PERMISSION_LABELS: Record<PursuitBriefAction["permission"], string> = {
  review_only: "Review only",
  local_read_only: "Local read-only action",
  analyst_record: "Records analyst judgment",
  remote_enrichment: "Remote enrichment · confirmation required",
  external_publication: "External publication · confirmation required",
};

const OPEN_WORK: Array<[keyof PursuitBriefState["open_work"], string]> = [
  ["contradictions", "contradictions"],
  ["knowledge_gaps", "knowledge gaps"],
  ["pending_reviews", "review decisions"],
  ["queued_enrichments", "queued enrichments"],
  ["weak_dossier_dimensions", "coverage gaps"],
  ["failed_enrichments", "failed enrichments"],
];

function percentage(current: number, total: number) {
  if (total <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
}

export function PursuitBrief({
  brief,
  localQueuePending,
  active,
  onAction,
  onOpenWorkbench,
}: {
  brief: PursuitBriefState;
  localQueuePending: number;
  active: boolean;
  onAction: (action: PursuitBriefAction) => void;
  onOpenWorkbench: () => void;
}) {
  const openWork = {
    ...brief.open_work,
    queued_enrichments: brief.open_work.queued_enrichments + localQueuePending,
  };
  const openCount = OPEN_WORK.reduce((total, [key]) => total + openWork[key], 0);
  const target = brief.subject.target;
  const contextLine = brief.subject.question && brief.subject.title !== brief.subject.question
    ? brief.subject.title
    : "Current investigation";

  return (
    <section className="pursuit-brief" aria-labelledby="pursuit-brief-title">
      <header className="pursuit-brief-heading">
        <div>
          <span className="eyebrow">PURSUIT BRIEF · WORKFLOW GUIDANCE, NOT EVIDENCE</span>
          <h2 id="pursuit-brief-title">
            {brief.subject.question ?? "What do you want to find out?"}
          </h2>
          <p>
            {brief.subject.question
              ? `${contextLine}${target ? ` · latest target ${target}` : ""}`
              : "Start with one concrete indicator or a question that can be tested against sourced evidence."}
          </p>
        </div>
        <span className={`brief-state state-${brief.subject.workspace_state}`}>
          {brief.subject.workspace_state.replaceAll("_", " ")}
        </span>
      </header>

      <div className="pursuit-brief-core">
        <section className="brief-now" aria-label="Current investigation state">
          <span>NOW</span>
          <b>{active ? "Enrichment in progress" : brief.now.stage}</b>
          <p>{active ? "Receipts are arriving in the investigation timeline." : brief.now.status}</p>
          <small>{brief.object_count} stored observable{brief.object_count === 1 ? "" : "s"}</small>
        </section>

        <section className={`brief-next category-${brief.next_action.category}`} aria-label="Recommended next action">
          <span>{CATEGORY_LABELS[brief.next_action.category].toUpperCase()}</span>
          <h3>{brief.next_action.label}</h3>
          <p>{brief.next_action.rationale}</p>
          <div>
            <button className="brief-primary-action" onClick={() => onAction(brief.next_action)}>
              {brief.next_action.label}
            </button>
            <small>
              {PERMISSION_LABELS[brief.next_action.permission]}
              {brief.next_action.basis.length ? ` · ${brief.next_action.basis.length} basis record${brief.next_action.basis.length === 1 ? "" : "s"}` : ""}
            </small>
          </div>
        </section>
      </div>

      <div className="brief-progress" aria-label="Investigation progress measures">
        {brief.progress.map((item) => {
          const value = percentage(item.current, item.total);
          const unavailable = item.total === 0;
          const emptyLabel = item.id === "analyst_review" ? "None due" : item.id === "enrichment_work" ? "No live work" : "Not started";
          return (
            <section key={item.id} className={unavailable ? "unavailable" : ""}>
              <header><b>{item.label}</b><span>{unavailable ? emptyLabel : `${item.current}/${item.total}`}</span></header>
              <div className="brief-progress-track" aria-hidden="true"><i style={{ width: `${value}%` }} /></div>
              <small>{item.detail}</small>
            </section>
          );
        })}
      </div>

      <footer className="pursuit-brief-footer">
        <div className="brief-open-work" aria-label={`${openCount} open work records`}>
          <b>OPEN WORK</b>
          {OPEN_WORK.map(([key, label]) => openWork[key] > 0 && (
            <span className={key === "contradictions" || key === "failed_enrichments" ? "attention" : ""} key={key}>
              {openWork[key]} {label}
            </span>
          ))}
          {openCount === 0 && <span>Nothing requiring action</span>}
        </div>
        <div className="brief-recent-change">
          <b>RECENT CHANGE</b>
          <span>{brief.recent_change.summary}</span>
        </div>
        <button className="brief-workbench-link" onClick={onOpenWorkbench}>OPEN FULL WORKBENCH</button>
      </footer>
    </section>
  );
}
