"use client";

import { useState } from "react";

/** One entry of the server's report-type registry (reports/registry.py). */
export type ReportTypeSummary = {
  id: string; number: number | null; code: string; title: string; domain: string; domain_label: string;
  tier: string | null; audience: string[]; purpose: string; formats: string[];
  default_marking: { tlp: string; pap: string };
};

/** Server-computed state of the report shown in the dialog. */
export type ReportMeta = {
  report_id: string | null; version: number; status: string; marking: string; complete: boolean; missing_required: string[];
};

const TLP = ["CLEAR", "GREEN", "AMBER", "AMBER+STRICT", "RED"];
const PAP = ["CLEAR", "GREEN", "AMBER", "RED"];

/** Choose a report type, format and marking; preview it, issue it, or list what was issued. */
export function ReportPicker({ types, meta, busy, onCommand }: {
  types: ReportTypeSummary[]; meta: ReportMeta; busy: boolean; onCommand: (command: string) => void;
}) {
  const [typeId, setTypeId] = useState(types[0]?.id ?? "investigation-report");
  const chosen = types.find((item) => item.id === typeId) ?? types[0];
  const [format, setFormat] = useState("markdown");
  const [tlp, setTlp] = useState(chosen?.default_marking.tlp ?? "AMBER");
  const [pap, setPap] = useState(chosen?.default_marking.pap ?? "AMBER");
  const [summary, setSummary] = useState("");
  if (!chosen) return null;
  const marking = `tlp:${tlp} pap:${pap}`;
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
            {types.map((item) => <option key={item.id} value={item.id}>{item.number ? `${item.number}. ` : ""}{item.title}</option>)}
          </select>
        </label>
        <label>Format
          <select value={formats} disabled={busy} onChange={(event) => setFormat(event.target.value)}>
            {chosen.formats.map((item) => <option key={item} value={item}>{item === "stix" ? "STIX 2.1" : item === "json" ? "JSON" : "Markdown"}</option>)}
          </select>
        </label>
        <label>TLP
          <select value={tlp} disabled={busy} onChange={(event) => setTlp(event.target.value)}>{TLP.map((item) => <option key={item}>{item}</option>)}</select>
        </label>
        <label>PAP
          <select value={pap} disabled={busy} onChange={(event) => setPap(event.target.value)}>{PAP.map((item) => <option key={item}>{item}</option>)}</select>
        </label>
      </div>
      <small className="report-purpose">{chosen.purpose} <i>For {chosen.audience.join(", ")}.</i>{formats !== "markdown" && " JSON and STIX download as files and are not defanged."}</small>
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
