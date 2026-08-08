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
  subject_ref?: string | null;
  predicate?: string | null;
  object_value?: string | null;
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
type ConfidenceAssessment = {
  id: string;
  target_kind: string;
  target_id: string;
  level: "low" | "moderate" | "high";
  rationale: string;
  factors: Record<string, unknown>;
};
type ConfidenceReview = {
  assessment_id: string;
  target_kind: string;
  target_id: string;
  level: string;
  warnings: Array<{ code: string; message: string }>;
};
type ContradictionCandidate = {
  id: string;
  content_class: "method_derived_suggestion";
  conflict_kind: "value_mismatch" | "non_overlapping_interval";
  left_kind: "assertion";
  left_id: string;
  right_kind: "assertion";
  right_id: string;
  summary: string;
  resolution_required: string;
  materiality: "low" | "medium" | "high";
};
type AnalyticRigorState = {
  policy: { id: string; candidate_authority: string; confidence_authority: string };
  contradiction_candidates: ContradictionCandidate[];
  confidence_reviews: ConfidenceReview[];
};

export type AnalyticSnapshot = {
  investigations: AnalyticInvestigation[];
  lifecycle_items: AnalyticLifecycleItem[];
  questions: AnalyticQuestion[];
  hypotheses: AnalyticHypothesis[];
  assertions: AnalyticAssertion[];
  evidence_links: AnalyticEvidenceLink[];
  confidence: ConfidenceAssessment[];
  likelihood: Array<Record<string, unknown>>;
  contradictions: AnalyticContradiction[];
  method_runs?: AnalyticMethodRun[];
  information_requirements?: InformationRequirementState;
  rigor?: AnalyticRigorState;
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
  const [claimType, setClaimType] = useState("judgment");
  const [claimSubject, setClaimSubject] = useState("");
  const [claimPredicate, setClaimPredicate] = useState("");
  const [claimValue, setClaimValue] = useState("");
  const [claimStatement, setClaimStatement] = useState("");
  const [confidenceTarget, setConfidenceTarget] = useState("");
  const [confidenceLevel, setConfidenceLevel] = useState<"low" | "moderate" | "high">("low");
  const [confidenceRationale, setConfidenceRationale] = useState("");
  const [sourceQuality, setSourceQuality] = useState("");
  const [sourceCount, setSourceCount] = useState(1);
  const [dependenceGroups, setDependenceGroups] = useState(1);
  const [independenceNotes, setIndependenceNotes] = useState("");
  const [corroboration, setCorroboration] = useState("");
  const [confidenceAssumptions, setConfidenceAssumptions] = useState("");
  const [confidenceGaps, setConfidenceGaps] = useState("");
  const [analyticRigor, setAnalyticRigor] = useState("");
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
  const judgments = [
    ...analysis.assertions.map((item) => ({ kind: "assertion", id: item.id, label: item.statement })),
    ...analysis.hypotheses.map((item) => ({ kind: "hypothesis", id: item.id, label: item.statement })),
  ];
  const confidenceReviewById = new Map(
    (analysis.rigor?.confidence_reviews ?? []).map((review) => [review.assessment_id, review]),
  );
  const liveConfidenceWarnings = [
    ...(sourceCount > dependenceGroups
      ? [`${sourceCount} cited sources collapse to ${dependenceGroups} independent group(s).`]
      : []),
    ...(["moderate", "high"].includes(confidenceLevel) && dependenceGroups < 2
      ? [`${confidenceLevel.toUpperCase()} confidence has fewer than two independent source groups.`]
      : []),
  ];
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

  async function recordStructuredClaim(event: FormEvent) {
    event.preventDefault();
    if (![claimSubject, claimPredicate, claimValue, claimStatement].every((value) => value.trim())) return;
    await run(
      `analysis claim ${claimType} ${claimSubject.trim()} ${claimPredicate.trim()} ${claimValue.trim()} | ${claimStatement.trim()}`,
    );
    setClaimValue("");
    setClaimStatement("");
  }

  async function recordConfidence(event: FormEvent) {
    event.preventDefault();
    const [targetKind, targetId] = confidenceTarget.split(":", 2);
    if (!targetKind || !targetId || !confidenceRationale.trim()) return;
    const factors = {
      source_quality: sourceQuality.trim() || "not assessed",
      source_independence: {
        source_count: sourceCount,
        dependence_group_count: dependenceGroups,
        notes: independenceNotes.trim() || "not assessed",
      },
      corroboration: corroboration.trim() || "not assessed",
      assumptions: confidenceAssumptions.trim() || "none recorded",
      knowledge_gaps: confidenceGaps.trim() || "none recorded",
      analytic_rigor: analyticRigor.trim() || "not assessed",
    };
    await run(
      `analysis confidence ${targetKind} ${targetId} ${confidenceLevel} ${confidenceRationale.trim()} | ${JSON.stringify(factors)}`,
    );
    setConfidenceRationale("");
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

      <details className="analysis-review">
        <summary><b>REVIEW ASSUMPTIONS, EXPLANATIONS &amp; CONTRADICTIONS</b><span>{assumptions.length + analysis.hypotheses.length} records · {unresolved.length} open conflicts</span></summary>
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
      </details>

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

      <details className="rigor-workspace" open={(analysis.rigor?.contradiction_candidates.length ?? 0) > 0}>
        <summary>
          <b>CONFIDENCE &amp; CONTRADICTION REVIEW</b>
          <span>{analysis.rigor?.contradiction_candidates.length ?? 0} CANDIDATE CONFLICTS · {analysis.confidence.length} ASSESSMENTS</span>
        </summary>
        <p className="rigor-explainer">
          Conflict candidates and dependence warnings are deterministic review aids, not evidence.
          Only an explicit analyst action records a contradiction or confidence judgment.
        </p>
        <div className="rigor-grid">
          <section>
            <header><b>STRUCTURED VALUE CLAIM</b><span>ENABLES VALUE / INTERVAL REVIEW</span></header>
            <form className="rigor-form" onSubmit={recordStructuredClaim}>
              <label>TYPE<select value={claimType} onChange={(event) => setClaimType(event.target.value)}><option value="judgment">judgment</option><option value="inferred">inferred</option><option value="assumed">assumed</option></select></label>
              <label>SUBJECT<input value={claimSubject} onChange={(event) => setClaimSubject(event.target.value)} placeholder="indicator or analytic subject" /></label>
              <label>PREDICATE<input value={claimPredicate} onChange={(event) => setClaimPredicate(event.target.value)} placeholder="first_seen, operator, port…" /></label>
              <label>VALUE OR INTERVAL<input value={claimValue} onChange={(event) => setClaimValue(event.target.value)} placeholder={'scalar or {"min":1,"max":5,"unit":"days"}'} /></label>
              <label className="wide">READABLE CLAIM<textarea value={claimStatement} onChange={(event) => setClaimStatement(event.target.value)} placeholder="State exactly what this value means and its relevant time boundary." /></label>
              <button disabled={busy || ![claimSubject, claimPredicate, claimValue, claimStatement].every((value) => value.trim())}>RECORD CLAIM</button>
            </form>
            <div className="candidate-list">
              {(analysis.rigor?.contradiction_candidates.length ?? 0) === 0 && <p className="empty-copy">No unrecorded value or non-overlapping interval conflicts detected.</p>}
              {analysis.rigor?.contradiction_candidates.map((candidate) => (
                <article key={candidate.id}>
                  <span>{candidate.conflict_kind.replaceAll("_", " ").toUpperCase()} · METHOD-DERIVED · NOT YET RECORDED</span>
                  <p>{candidate.summary}</p>
                  <small>NEEDED: {candidate.resolution_required}</small>
                  <button disabled={busy} onClick={() => void run(`analysis contradiction ${candidate.left_kind} ${candidate.left_id} ${candidate.right_kind} ${candidate.right_id} ${candidate.summary} | ${candidate.resolution_required} | ${candidate.materiality}`)}>RECORD CONTRADICTION</button>
                </article>
              ))}
            </div>
          </section>

          <section>
            <header><b>FORMAL CONFIDENCE</b><span>LIKELIHOOD REMAINS SEPARATE</span></header>
            <form className="rigor-form" onSubmit={recordConfidence}>
              <label className="wide">JUDGMENT<select value={confidenceTarget} onChange={(event) => setConfidenceTarget(event.target.value)}><option value="">Choose an assertion or hypothesis</option>{judgments.map((item) => <option value={`${item.kind}:${item.id}`} key={`${item.kind}:${item.id}`}>{item.kind}: {item.label}</option>)}</select></label>
              <label>LEVEL<select value={confidenceLevel} onChange={(event) => setConfidenceLevel(event.target.value as "low" | "moderate" | "high")}><option value="low">low</option><option value="moderate">moderate</option><option value="high">high</option></select></label>
              <label>SOURCES<input type="number" min="0" value={sourceCount} onChange={(event) => setSourceCount(Math.max(0, Number(event.target.value)))} /></label>
              <label>INDEPENDENT GROUPS<input type="number" min="0" value={dependenceGroups} onChange={(event) => setDependenceGroups(Math.max(0, Number(event.target.value)))} /></label>
              <label>SOURCE QUALITY<input value={sourceQuality} onChange={(event) => setSourceQuality(event.target.value)} placeholder="access, reliability, limitations" /></label>
              <label>INDEPENDENCE NOTES<input value={independenceNotes} onChange={(event) => setIndependenceNotes(event.target.value)} placeholder="shared upstream reporting?" /></label>
              <label>CORROBORATION<input value={corroboration} onChange={(event) => setCorroboration(event.target.value)} placeholder="what independently agrees?" /></label>
              <label>ASSUMPTIONS<input value={confidenceAssumptions} onChange={(event) => setConfidenceAssumptions(event.target.value)} placeholder="material assumptions" /></label>
              <label>KNOWLEDGE GAPS<input value={confidenceGaps} onChange={(event) => setConfidenceGaps(event.target.value)} placeholder="unresolved information" /></label>
              <label>ANALYTIC RIGOR<input value={analyticRigor} onChange={(event) => setAnalyticRigor(event.target.value)} placeholder="methods and alternatives tested" /></label>
              <label className="wide">RATIONALE<textarea value={confidenceRationale} onChange={(event) => setConfidenceRationale(event.target.value)} placeholder="Explain why this evidentiary and logical basis warrants the selected level." /></label>
              {liveConfidenceWarnings.length > 0 && <div className="rigor-warning wide" role="alert">{liveConfidenceWarnings.map((warning) => <span key={warning}>{warning}</span>)}</div>}
              <button disabled={busy || !confidenceTarget || !confidenceRationale.trim()}>RECORD CONFIDENCE</button>
            </form>
            <div className="confidence-list">
              {analysis.confidence.length === 0 && <p className="empty-copy">No formal confidence assessment recorded.</p>}
              {analysis.confidence.map((assessment) => {
                const review = confidenceReviewById.get(assessment.id);
                return <article className={review?.warnings.length ? "has-warning" : ""} key={assessment.id}><span>{assessment.level.toUpperCase()} CONFIDENCE · {assessment.target_kind}</span><p>{assessment.rationale}</p>{review?.warnings.map((warning) => <small key={warning.code}>⚠ {warning.message}</small>)}</article>;
              })}
            </div>
          </section>
        </div>
        <small className="analytic-truth-label">{analysis.rigor?.policy.confidence_authority ?? "Warnings never silently rewrite analyst judgment."}</small>
      </details>

      <details className="information-review">
        <summary><b>NEXT BEST INFORMATION</b><span>{requirementState?.suggestions.length ?? 0} method-derived suggestions · {requirementState?.requirements.length ?? 0} recorded requirements</span></summary>
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
      </details>

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
