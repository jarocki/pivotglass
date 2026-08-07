"use client";

import { FormEvent, useMemo, useState } from "react";

export type AnalyticInvestigation = {
  id: string;
  title: string;
  purpose: string;
  scope: string;
  status: string;
  primary_question_id?: string | null;
};

export type AnalyticLifecycleItem = {
  id: string;
  investigation_id: string;
  item_type: string;
  record_kind?: string | null;
  record_id?: string | null;
  statement?: string | null;
  status: string;
  priority: number;
  criteria: Record<string, unknown>;
  evidence_refs: Array<Record<string, unknown>>;
  author_kind: string;
  analyst_disposition: string;
};

type AnalyticQuestion = { id: string; text: string; status: string };
type AnalyticAssertion = {
  id: string;
  statement: string;
  assertion_type: string;
  status: string;
  author_kind: string;
};
type AnalyticHypothesis = {
  id: string;
  question_id: string;
  statement: string;
  status: string;
  author_kind: string;
};
type AnalyticEvidenceLink = {
  id: number;
  source_kind: string;
  source_id: string;
  target_kind: string;
  target_id: string;
  stance: "supports" | "contradicts";
  rationale: string;
};
type AnalyticContradiction = {
  id: string;
  summary: string;
  materiality: string;
  status: string;
  resolution_required: string;
  resolution_note?: string | null;
};
type AnalyticMethodRun = {
  id: string;
  technique: string;
  status: string;
  analyst_disposition: string;
  output_blob?: Record<string, unknown> | null;
};
type RankedInformationRequirement = {
  id: string;
  statement: string;
  status: string;
  rank: number;
  analyst_priority: number;
  information_value: number;
  rank_score: number;
  priority_source: "analyst" | "deterministic";
  contributions: Record<string, number>;
  scoring_error?: string | null;
};
type InformationSuggestion = {
  id: string;
  suggestion_type: string;
  statement: string;
  score: number;
  rationale: string;
  source_refs: Array<{ kind: string; id: string }>;
  criteria?: Record<string, unknown> | null;
  adoptable: boolean;
  content_class: "method_derived_suggestion";
};
type InformationRequirementState = {
  policy: {
    id: string;
    weights: Record<string, number>;
    missing_factor_behavior: string;
    human_authority: string;
  };
  requirements: RankedInformationRequirement[];
  suggestions: InformationSuggestion[];
};

export type AnalyticSnapshot = {
  investigations: AnalyticInvestigation[];
  lifecycle_items: AnalyticLifecycleItem[];
  questions: AnalyticQuestion[];
  hypotheses: AnalyticHypothesis[];
  assertions: AnalyticAssertion[];
  evidence_links: AnalyticEvidenceLink[];
  confidence: Array<Record<string, unknown>>;
  likelihood: Array<Record<string, unknown>>;
  contradictions: AnalyticContradiction[];
  method_runs?: AnalyticMethodRun[];
  information_requirements?: InformationRequirementState;
};

type CaptureKind =
  | "question"
  | "assumption"
  | "hypothesis"
  | "prediction"
  | "signpost"
  | "collect"
  | "stop"
  | "limitation"
  | "gap";

const STAGES = [
  { label: "FRAME", types: ["question", "assumption"] },
  { label: "EXPLAIN", types: ["hypothesis", "assertion"] },
  { label: "PREDICT", types: ["prediction", "signpost"] },
  { label: "COLLECT", types: ["collection_requirement", "observation", "stop_condition"] },
  { label: "TEST", types: ["method_run"] },
  { label: "CONCLUDE", types: ["conclusion", "limitation", "knowledge_gap"] },
] as const;

const CAPTURE_LABELS: Record<CaptureKind, string> = {
  question: "Investigation question",
  assumption: "Key assumption",
  hypothesis: "Competing hypothesis",
  prediction: "Observable prediction",
  signpost: "Decision-changing signpost",
  collect: "Collection requirement",
  stop: "Stop condition",
  limitation: "Limitation",
  gap: "Intelligence gap",
};

export function ScientificWorkbench({
  analysis,
  onCommand,
}: {
  analysis: AnalyticSnapshot;
  onCommand: (command: string) => Promise<string>;
}) {
  const [kind, setKind] = useState<CaptureKind>("question");
  const [statement, setStatement] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const active = [...analysis.investigations]
    .reverse()
    .find((item) => !["concluded", "suspended"].includes(item.status));
  const current = active ?? analysis.investigations.at(-1);
  const items = current
    ? analysis.lifecycle_items.filter((item) => item.investigation_id === current.id)
    : [];
  const assumptions = analysis.assertions.filter((item) => item.assertion_type === "assumed");
  const unresolved = analysis.contradictions.filter((item) => item.status === "unresolved");
  const gaps = items.filter((item) => ["knowledge_gap", "limitation"].includes(item.item_type));
  const achRows = useMemo(() => {
    const rows = new Map<string, { label: string; cells: Map<string, AnalyticEvidenceLink> }>();
    for (const link of analysis.evidence_links) {
      if (link.target_kind !== "hypothesis") continue;
      const key = `${link.source_kind}:${link.source_id}`;
      const row = rows.get(key) ?? {
        label: key,
        cells: new Map<string, AnalyticEvidenceLink>(),
      };
      row.cells.set(link.target_id, link);
      rows.set(key, row);
    }
    return [...rows.values()];
  }, [analysis.evidence_links]);

  async function run(command: string) {
    setBusy(true);
    setNotice("");
    try {
      setNotice(await onCommand(command));
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function capture(event: FormEvent) {
    event.preventDefault();
    const cleaned = statement.trim();
    if (!cleaned) return;
    if (kind === "hypothesis") {
      const questionId = current?.primary_question_id ?? analysis.questions.at(-1)?.id;
      if (!questionId) {
        setNotice("Record the investigation question before proposing hypotheses.");
        return;
      }
      await run(`analysis hypothesis ${questionId} ${cleaned}`);
    } else {
      await run(`analysis ${kind} ${cleaned}`);
    }
    setStatement("");
  }

  async function adoptSuggestion(suggestion: InformationSuggestion) {
    if (!suggestion.adoptable || !suggestion.criteria) return;
    await run(
      `analysis requirement ${suggestion.statement} | ${JSON.stringify(suggestion.criteria)}`,
    );
  }

  const requirementState = analysis.information_requirements;

  return (
    <section className="scientific-workbench" aria-label="Scientific investigation workbench">
      <header>
        <div>
          <span>SCIENTIFIC NOTEBOOK · ANALYST JUDGMENT</span>
          <h3>{current?.title ?? "FRAME THE INVESTIGATION"}</h3>
          <p>
            {current?.purpose ?? "Begin with a question that can be tested against sourced evidence."}
          </p>
        </div>
        <b className={`investigation-state state-${current?.status ?? "empty"}`}>
          {(current?.status ?? "not started").replaceAll("_", " ")}
        </b>
      </header>

      <ol className="lifecycle-rail" aria-label="Scientific lifecycle progress">
        {STAGES.map((stage, index) => {
          const count = items.filter((item) => stage.types.includes(item.item_type as never)).length;
          return (
            <li className={count ? "has-records" : "empty"} key={stage.label}>
              <span>{index + 1}</span>
              <b>{stage.label}</b>
              <small>{count} RECORD{count === 1 ? "" : "S"}</small>
            </li>
          );
        })}
      </ol>

      <form className="analytic-capture" onSubmit={capture}>
        <label>
          ADD TO NOTEBOOK
          <select value={kind} onChange={(event) => setKind(event.target.value as CaptureKind)}>
            {(Object.keys(CAPTURE_LABELS) as CaptureKind[]).map((value) => (
              <option value={value} key={value}>{CAPTURE_LABELS[value]}</option>
            ))}
          </select>
        </label>
        <textarea
          value={statement}
          onChange={(event) => setStatement(event.target.value)}
          placeholder={kind === "question" ? "What exactly must this investigation answer?" : `Record a ${CAPTURE_LABELS[kind].toLowerCase()}…`}
          aria-label={`New ${CAPTURE_LABELS[kind]}`}
        />
        <button disabled={busy || !statement.trim()}>{busy ? "RECORDING…" : "RECORD"}</button>
      </form>
      {notice && <p className="analytic-notice" role="status">{notice}</p>}

      <div className="analytic-columns">
        <section>
          <header><b>ASSUMPTIONS</b><span>{assumptions.length}</span></header>
          {assumptions.length === 0 && <p className="empty-copy">No assumptions exposed yet.</p>}
          {assumptions.map((item) => (
            <article key={item.id}>
              <span>{item.author_kind === "model" ? "MODEL PROPOSAL · HUMAN REVIEW REQUIRED" : "ANALYST RECORD"}</span>
              <p>{item.statement}</p>
            </article>
          ))}
        </section>

        <section>
          <header><b>COMPETING HYPOTHESES</b><span>{analysis.hypotheses.length}</span></header>
          {analysis.hypotheses.length === 0 && <p className="empty-copy">No competing explanations recorded.</p>}
          {analysis.hypotheses.map((item) => (
            <article key={item.id}>
              <span>{item.status.toUpperCase()} · {item.author_kind.toUpperCase()}</span>
              <p>{item.statement}</p>
              <div>
                <button disabled={busy || item.status === "retained"} onClick={() => void run(`analysis accept ${item.id}`)}>RETAIN</button>
                <button disabled={busy || item.status === "rejected"} onClick={() => void run(`analysis reject ${item.id}`)}>REJECT</button>
                <button disabled={busy || item.status === "suspended"} onClick={() => void run(`analysis suspend ${item.id}`)}>SUSPEND</button>
              </div>
            </article>
          ))}
        </section>

        <section className={unresolved.length ? "has-conflict" : ""}>
          <header><b>CONTRADICTIONS</b><span>{unresolved.length} OPEN</span></header>
          {analysis.contradictions.length === 0 && <p className="empty-copy">No explicit contradictions recorded.</p>}
          {analysis.contradictions.map((item) => (
            <article key={item.id} className={`contradiction-${item.status}`}>
              <span>{item.materiality.toUpperCase()} · {item.status.toUpperCase()}</span>
              <p>{item.summary}</p>
              <small>{item.status === "unresolved" ? `NEEDED: ${item.resolution_required}` : item.resolution_note}</small>
            </article>
          ))}
        </section>
      </div>

      <details className="ach-workspace" open={analysis.hypotheses.length > 1}>
        <summary>
          <b>ANALYSIS OF COMPETING HYPOTHESES</b>
          <span>{achRows.length} EVIDENCE ROWS · {analysis.hypotheses.length} HYPOTHESES</span>
        </summary>
        {analysis.hypotheses.length < 2 ? (
          <p className="empty-copy">Record at least two hypotheses before using the comparison matrix.</p>
        ) : achRows.length === 0 ? (
          <p className="empty-copy">No evidence has been explicitly linked to a hypothesis. Empty cells are unknown, not neutral.</p>
        ) : (
          <div className="ach-scroll">
            <table>
              <thead><tr><th>EVIDENCE / ASSERTION</th>{analysis.hypotheses.map((item, index) => <th key={item.id}>H{index + 1}<small>{item.statement}</small></th>)}</tr></thead>
              <tbody>{achRows.map((row) => <tr key={row.label}><th>{row.label}</th>{analysis.hypotheses.map((hypothesis) => { const link = row.cells.get(hypothesis.id); return <td className={link ? `stance-${link.stance}` : "stance-unknown"} title={link?.rationale ?? "No explicit link"} key={hypothesis.id}>{link?.stance === "supports" ? "+" : link?.stance === "contradicts" ? "−" : "·"}<small>{link?.stance ?? "unknown"}</small></td>; })}</tr>)}</tbody>
            </table>
          </div>
        )}
      </details>

      <section className="information-requirements" aria-label="Priority intelligence requirements">
        <header>
          <div>
            <b>PRIORITY INTELLIGENCE REQUIREMENTS</b>
            <span>WHAT INFORMATION WOULD MOST CHANGE THE JUDGMENT?</span>
          </div>
          <small>DETERMINISTIC POLICY · {requirementState?.policy.id ?? "NOT AVAILABLE"}</small>
        </header>
        <p className="requirement-explainer">
          An analyst-set priority controls rank. Otherwise Pivotglass scores only the declared
          decision impact, discriminating power, time sensitivity, and feasibility; missing
          factors remain zero.
        </p>
        <div className="requirement-grid">
          <section>
            <header><b>RECORDED REQUIREMENTS</b><span>{requirementState?.requirements.length ?? 0}</span></header>
            {!requirementState?.requirements.length && <p className="empty-copy">No bounded information requirements recorded.</p>}
            {requirementState?.requirements.map((item) => (
              <article key={item.id}>
                <span>#{item.rank} · {item.priority_source === "analyst" ? "ANALYST PRIORITY" : "INFORMATION VALUE"} · {item.rank_score}/100</span>
                <p>{item.statement}</p>
                <small>
                  DECISION {item.contributions.decision_impact ?? 0} · DISCRIMINATION {item.contributions.discriminating_power ?? 0} · TIME {item.contributions.time_sensitivity ?? 0} · FEASIBILITY {item.contributions.feasibility ?? 0}
                </small>
                {item.scoring_error && <small>SCORING PAUSED: {item.scoring_error}</small>}
                <label>
                  ANALYST PRIORITY
                  <select
                    aria-label={`Priority for ${item.statement}`}
                    value={item.analyst_priority}
                    disabled={busy}
                    onChange={(event) => void run(`analysis prioritize ${item.id} ${event.target.value}`)}
                  >
                    <option value={0}>Use information value</option>
                    <option value={25}>25 · low</option>
                    <option value={50}>50 · medium</option>
                    <option value={75}>75 · high</option>
                    <option value={100}>100 · critical</option>
                  </select>
                </label>
              </article>
            ))}
          </section>
          <section>
            <header><b>NEXT BEST INFORMATION</b><span>{requirementState?.suggestions.length ?? 0}</span></header>
            {!requirementState?.suggestions.length && <p className="empty-copy">No method-derived suggestions at this stage.</p>}
            {requirementState?.suggestions.map((item) => (
              <article key={item.id}>
                <span>METHOD-DERIVED SUGGESTION · {item.score}/100 · NOT EVIDENCE</span>
                <p>{item.statement}</p>
                <small>{item.rationale}</small>
                {item.source_refs.length > 0 && <small>BASIS: {item.source_refs.map((ref) => `${ref.kind}:${ref.id}`).join(" · ")}</small>}
                {item.adoptable && <button disabled={busy} onClick={() => void adoptSuggestion(item)}>ADOPT AS REQUIREMENT</button>}
              </article>
            ))}
          </section>
        </div>
        <small className="analytic-truth-label">Suggestions are reproducible method output. Adoption is an explicit analyst action; neither suggestions nor priorities are observations.</small>
      </section>

      {(gaps.length > 0 || items.some((item) => item.item_type === "stop_condition")) && (
        <footer>
          {gaps.map((item) => <span key={item.id}><b>{item.item_type.replaceAll("_", " ")}</b>{item.statement}</span>)}
          {items.filter((item) => item.item_type === "stop_condition").map((item) => <span key={item.id}><b>stop condition</b>{item.statement}</span>)}
        </footer>
      )}
      <small className="analytic-truth-label">This notebook contains analyst judgments and method state. It does not convert inference into observed evidence.</small>
    </section>
  );
}
