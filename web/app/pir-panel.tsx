"use client";

import { useEffect, useState } from "react";

/** Server-computed PIR state (DEC-PIR-001); the browser never derives the verdict. */
export type PirState = {
  verdict: "no_pir" | "answered" | "partially_answered" | "not_answered";
  verdict_label: string;
  question?: string | null;
  category?: string;
  level?: string;
  category_label?: string;
  level_label?: string;
  audience?: string;
  collection_fit?: "strong" | "good" | "partial" | "weak";
  fit_note?: string;
  stop_conditions?: Array<{ id: string; statement: string; status: string }>;
  resolved_count?: number;
  conclusion_count?: number;
  open_gaps?: string[];
  report_types?: Array<{ id: string; title: string; available: boolean }>;
  next_step?: string;
};

export type PirCatalogue = {
  categories: Array<{ id: string; label: string; focus: string; example: string; collection_fit: string; fit_note: string; default_level: string }>;
  levels: Array<{ id: string; label: string; audience: string; focus: string }>;
};

const MET = new Set(["satisfied", "resolved"]);

export function PirPanel({ pir, catalogue, busy, onCommand }: {
  pir: PirState | undefined; catalogue: PirCatalogue | undefined; busy: boolean; onCommand: (command: string) => Promise<void>;
}) {
  const recorded = Boolean(pir?.category && pir.category !== "unspecified");
  const [editing, setEditing] = useState(!recorded);
  const [category, setCategory] = useState(recorded ? pir!.category! : "");
  const [level, setLevel] = useState(recorded ? pir!.level! : "");
  useEffect(() => { if (!recorded) setEditing(true); }, [recorded]);
  if (!catalogue) return null;
  const chosen = catalogue.categories.find((item) => item.id === category);
  const tier = level || chosen?.default_level || "";

  async function save() {
    if (!chosen) return;
    await onCommand(`analysis pir ${chosen.id} ${tier}`);
    setEditing(false);
  }

  return (
    <section className={`pir-panel verdict-${pir?.verdict ?? "no_pir"}`} aria-label="Priority intelligence requirement">
      <header>
        <div>
          <span>Priority intelligence requirement</span>
          <b>{recorded ? `${pir!.category_label} · ${pir!.level_label}` : "Not yet chosen"}</b>
          {recorded && <small>Audience: {pir!.audience}</small>}
        </div>
        <strong className="pir-verdict">{pir?.verdict_label ?? "No PIR recorded"}</strong>
      </header>

      {recorded && !editing && <>
        <p className={`pir-fit fit-${pir!.collection_fit}`}><b>Collection fit: {pir!.collection_fit}.</b> {pir!.fit_note}</p>
        <ol className="pir-stops" aria-label="What an answer needs">
          {(pir!.stop_conditions ?? []).map((stop) => (
            <li key={stop.id} className={MET.has(stop.status) ? "met" : ""}>
              <span>{stop.statement}</span>
              {MET.has(stop.status)
                ? <button type="button" disabled={busy} onClick={() => void onCommand(`analysis item ${stop.id} open`)}>Reopen</button>
                : <button type="button" disabled={busy} onClick={() => void onCommand(`analysis item ${stop.id} satisfied`)}>Mark met</button>}
            </li>
          ))}
        </ol>
        <small className="pir-meta">
          {pir!.resolved_count ?? 0} of {pir!.stop_conditions?.length ?? 0} met · {pir!.conclusion_count ?? 0} accepted conclusion{pir!.conclusion_count === 1 ? "" : "s"}
          {(pir!.open_gaps?.length ?? 0) > 0 && ` · ${pir!.open_gaps!.length} open gap${pir!.open_gaps!.length === 1 ? "" : "s"}`}
          {(pir!.report_types?.length ?? 0) > 0 && <> · Suggested reports: {pir!.report_types!.map((item) => item.available ? item.title : `${item.title} (not built yet)`).join(", ")}</>}
        </small>
        <button type="button" className="pir-change" disabled={busy} onClick={() => setEditing(true)}>Change category or tier</button>
      </>}

      {editing && <div className="pir-form">
        <label>
          Category
          <select value={category} disabled={busy} onChange={(event) => { setCategory(event.target.value); setLevel(""); }}>
            <option value="">Choose what kind of question this is…</option>
            {catalogue.categories.map((item) => <option key={item.id} value={item.id}>{item.label} ({item.collection_fit} fit)</option>)}
          </select>
        </label>
        <label>
          Tier
          <select value={tier} disabled={busy || !chosen} onChange={(event) => setLevel(event.target.value)}>
            {catalogue.levels.map((item) => <option key={item.id} value={item.id}>{item.label}: {item.audience}</option>)}
          </select>
        </label>
        {chosen && <p className="pir-choice"><b>{chosen.focus}</b> For example: “{chosen.example}” <i>{chosen.fit_note}</i></p>}
        <div>
          <button type="button" disabled={busy || !chosen} onClick={() => void save()}>{recorded ? "Update PIR" : "Set PIR"}</button>
          {recorded && <button type="button" disabled={busy} onClick={() => setEditing(false)}>Cancel</button>}
        </div>
        {recorded && <small>Changing the category defers its open stop conditions; met ones are kept. Switching back reopens them.</small>}
      </div>}
    </section>
  );
}
