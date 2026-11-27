"use client";

import { useState } from "react";

/** One entry of the server's report-type registry (reports/registry.py). */
export type ReportTypeSummary = {
  id: string; number: number | null; code: string; title: string; domain: string; domain_label: string;
  tier: string | null; audience: string[]; purpose: string; use_when: string; formats: string[];
  available: boolean; building_issues: number[]; actor_scoped: boolean;
  default_marking: { tlp: string; pap: string };
};

/** Server-computed state of the report shown in the dialog. */
export type ReportMeta = {
  type_id: string; subject: string | null; report_id: string | null; version: number; status: string; marking: string; complete: boolean; missing_required: string[];
};

const TLP = ["CLEAR", "GREEN", "AMBER", "AMBER+STRICT", "RED"];
const PAP = ["CLEAR", "GREEN", "AMBER", "RED"];
const FORMAT_LABELS: Record<string, string> = { markdown: "Markdown", json: "JSON", stix: "STIX 2.1", mermaid: "Mermaid", navigator: "Navigator layer", sigma: "Sigma", suricata: "Suricata", yara: "YARA" };

/** Choose a report type, format and marking; preview it, issue it, or list what was issued. */
export function ReportPicker({ types, meta, busy, onCommand }: {
  types: ReportTypeSummary[]; meta: ReportMeta; busy: boolean; onCommand: (command: string) => void;
}) {
  const [typeId, setTypeId] = useState(meta.type_id ?? types.find((item) => item.available)?.id ?? "investigation-report");
  const chosen = types.find((item) => item.id === typeId) ?? types[0];
  const [format, setFormat] = useState("markdown");
  const [tlp, setTlp] = useState(chosen?.default_marking.tlp ?? "AMBER");
  const [pap, setPap] = useState(chosen?.default_marking.pap ?? "AMBER");
  const [summary, setSummary] = useState("");
  const [actor, setActor] = useState(meta.subject?.replace(/^actor:/, "") ?? "");
  if (!chosen) return null;
  const subject = chosen.actor_scoped && actor.trim() ? ` actor:${actor.trim().replace(/^actor:/, "").replace(/\s+/g, "-")}` : "";
  const marking = `tlp:${tlp} pap:${pap}${subject}`;
  const formats = chosen.formats.includes(format) ? format : "markdown";

  function pick(id: string) {
    const next = types.find((item) => item.id === id);
    setTypeId(id);
    if (next) { setTlp(next.default_marking.tlp); setPap(next.default_marking.pap); if (!next.formats.includes(format)) setFormat("markdown"); }
  }

  function issue(status: "draft" | "final") {
    const note = summary.trim().replaceAll("|", "/");
    onCommand(`report issue ${chosen.id} ${status} ${marking}${note ? ` | ${note}` : ""}`);
    setSummary("");
  }

  return (
    <section className="report-picker" aria-label="Report type and issue">
      <p className={`report-state ${meta.complete ? "complete" : "incomplete"}`}>
        <b>{meta.report_id ? `${meta.report_id} · v${meta.version} · ${meta.status}` : "Preview, not issued"}</b>
        <span>{meta.marking}</span>
        <span>{meta.complete ? "Complete" : `Incomplete: ${meta.missing_required.join(", ")} missing`}</span>
      </p>
      <div className="report-controls">
        <label>Report
          <select value={chosen.id} disabled={busy} onChange={(event) => pick(event.target.value)}>
            {types.map((item) => <option key={item.id} value={item.id} disabled={!item.available}>{item.number ? `${item.number}. ` : ""}{item.title}{item.available ? "" : ` (not built yet: ${item.building_issues.map((n) => `#${n}`).join(", ")})`}</option>)}
          </select>
        </label>
        <label>Format
          <select value={formats} disabled={busy} onChange={(event) => setFormat(event.target.value)}>
            {chosen.formats.map((item) => <option key={item} value={item}>{FORMAT_LABELS[item] ?? item}</option>)}
          </select>
        </label>
        <label>TLP
          <select value={tlp} disabled={busy} onChange={(event) => setTlp(event.target.value)}>{TLP.map((item) => <option key={item}>{item}</option>)}</select>
        </label>
        <label>PAP
          <select value={pap} disabled={busy} onChange={(event) => setPap(event.target.value)}>{PAP.map((item) => <option key={item}>{item}</option>)}</select>
        </label>
      </div>
      {chosen.actor_scoped && <label className="report-actor">Actor
        <input value={actor} disabled={busy} onChange={(event) => setActor(event.target.value)} placeholder="Leave blank when one actor has claims" aria-label="Actor name"/>
      </label>}
      <small className="report-purpose">{chosen.purpose} <i>For {chosen.audience.join(", ")}.</i>{formats !== "markdown" && " Machine formats download as files; JSON, STIX and rule files are not defanged."}</small>
      <div className="report-buttons">
        <button type="button" disabled={busy} onClick={() => onCommand(`report ${chosen.id} ${formats} ${marking}`)}>Preview</button>
        <input value={summary} disabled={busy} maxLength={200} onChange={(event) => setSummary(event.target.value)} placeholder="What changed (for the revision history)" aria-label="Change summary"/>
        <button type="button" disabled={busy} onClick={() => issue("draft")}>Issue draft</button>
        <button type="button" disabled={busy} onClick={() => issue("final")}>Issue final</button>
        <button type="button" disabled={busy} onClick={() => onCommand("report history")}>Issued reports</button>
      </div>
    </section>
  );
}
