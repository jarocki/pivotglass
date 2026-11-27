"use client";

/**
 * Investigate's persistent indicator table (#32): every workspace indicator,
 * grouped by cluster or role tag, with a one-line ACH reading above it. Tags
 * are the analyst's records; the ACH line comes from the same matrix the
 * report uses (``ach_summary`` on the server).
 */

import { useMemo, useState } from "react";

import { groupIndicatorRows, type AchSummary, type Grouping, type TableIndicator, type TableTag } from "./indicator-table-model";

export type { AchSummary, TableTag } from "./indicator-table-model";
const ROWS_PER_GROUP = 12;

export function IndicatorTable({ indicators, tags, ach, onOpen, onOpenAch }: {
  indicators: TableIndicator[];
  tags: TableTag[];
  ach?: AchSummary | null;
  onOpen: (reference: string, origin: HTMLElement) => void;
  onOpenAch: () => void;
}) {
  const [grouping, setGrouping] = useState<Grouping>("cluster");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const groups = useMemo(() => groupIndicatorRows(indicators, tags, grouping), [indicators, tags, grouping]);
  const leader = ach?.leaders[0];
  return <section className="panel indicator-table" aria-label="Indicators">
    <header className="indicator-table-bar">
      <b>Indicators</b><span>{indicators.length}</span>
      <label><span className="sr-only">Group indicators by</span>
        <select value={grouping} onChange={(event) => setGrouping(event.target.value as Grouping)} aria-label="Group indicators by">
          <option value="cluster">By cluster</option><option value="role">By role</option>
        </select></label>
    </header>
    {ach && ach.hypotheses > 0 && <p className="ach-line">
      <span><b>{ach.hypotheses}</b> competing {ach.hypotheses === 1 ? "hypothesis" : "hypotheses"}</span>
      {leader && <span title={leader.statement}>least inconsistent: <b>{leader.label}</b>{ach.leaders.length > 1 ? ` (tied with ${ach.leaders.length - 1})` : ""}</span>}
      <span>{ach.strongest_disconfirming
        ? <>strongest against {ach.strongest_disconfirming.hypothesis}: <b title={ach.strongest_disconfirming.evidence}>{ach.strongest_disconfirming.evidence}</b> ({ach.strongest_disconfirming.diagnosticity} diagnosticity)</>
        : ach.evidence_rows ? "no evidence recorded against it" : "no evidence linked to a hypothesis yet"}</span>
      <button type="button" onClick={onOpenAch}>Open ACH matrix</button>
    </p>}
    {indicators.length === 0 ? <p className="empty-line">No indicators in this workspace yet.</p> : <div className="indicator-table-groups">
      {groups.map((group) => {
        const open = expanded.has(group.key);
        const shown = open ? group.items : group.items.slice(0, ROWS_PER_GROUP);
        return <section key={group.key || "__none"} className={group.key ? "" : "untagged"}>
          <h3>{group.label} <small>{group.items.length}</small></h3>
          <table>
            <thead><tr><th scope="col">Indicator</th><th scope="col">Type</th><th scope="col">Role</th><th scope="col">Tactic</th></tr></thead>
            <tbody>{shown.map((row) => <tr key={`${group.key}-${row.reference}`}>
              <td><button type="button" className="indicator-link" title={row.value} onClick={(event) => onOpen(row.reference, event.currentTarget)}>{row.value}</button></td>
              <td>{row.type}</td>
              <td>{row.roles.join(", ") || "—"}</td>
              <td>{row.tactics.map((t) => /^t\d{4}/.test(t) ? t.toUpperCase() : t).join(", ") || "—"}</td>
            </tr>)}</tbody>
          </table>
          {group.items.length > ROWS_PER_GROUP && <button type="button" className="link-button" onClick={() => setExpanded((current) => { const next = new Set(current); if (open) next.delete(group.key); else next.add(group.key); return next; })}>
            {open ? "Show fewer" : `Show all ${group.items.length}`}
          </button>}
        </section>;
      })}
    </div>}
  </section>;
}
