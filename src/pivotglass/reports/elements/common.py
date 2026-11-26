"""Elements every report type can use: header, PIR verdict, sources, gaps, IOCs, collection timeline."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from pivotglass.reports.contract import (
    INFORMATION_CREDIBILITY_LABELS,
    PAP_DEFINITIONS,
    SOURCE_RELIABILITY_LABELS,
    TLP_DEFINITIONS,
    InformationCredibility,
    OutputFormat,
    Pap,
    ProvenanceClass,
    SourceReliability,
    Tlp,
    pap_label,
    render_indicator,
    tlp_label,
)
from pivotglass.reports.elements import ElementResult, ElementStatus, ReportContext, element

E, M, A = ProvenanceClass.EVIDENCE, ProvenanceClass.METHOD, ProvenanceClass.ANALYST
MET = {"satisfied", "resolved"}

# Elements built after every other element, because they summarise them.
LATE_ELEMENTS = ("sources", "gaps_limitations", "header")
# Every report type must include these, as required elements.
MANDATORY_ELEMENTS = ("header", "pir_verdict", "gaps_limitations", "sources")


def guess_indicator_kind(value: str) -> str | None:
    """The STIX type a bare collection target most likely is, for defanging only."""

    import ipaddress
    import re

    try:
        return f"ipv{ipaddress.ip_address(value).version}-addr"
    except ValueError:
        pass
    if "://" in value:
        return "url"
    if "@" in value:
        return "email-addr"
    if re.fullmatch(r"(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}\.?", value):
        return "domain-name"
    return None


def md(value: object) -> str:
    """One table-safe Markdown line: pipes escaped, newlines folded."""

    return str(value).replace("|", "\\|").replace("\n", " ")


def _empty_line(text: str) -> str:
    return f"_{text}_"


# --- header -----------------------------------------------------------------


def _header_md(result: ElementResult, output: OutputFormat) -> str:
    h = result.content
    tlp, pap = Tlp(h["tlp"]), Pap(h["pap"])
    issued = h["report_id"] is not None
    identity = (
        f"**{h['report_id']}** · version {h['version']} · **{h['status']}**"
        if issued
        else "**Preview — not issued.** Issue it to give it an ID and a revision history."
    )
    lines = [
        f"# {h['title']}",
        "",
        f"**{tlp_label(tlp)}** · **{pap_label(pap)}**",
        "",
        f"- **Report:** {identity}",
        f"- **{'Issued' if issued else 'Generated'}:** {h['issued_at'][:16].replace('T', ' ')} UTC",
    ]
    if h.get("valid_until"):
        lines.append(f"- **Valid until:** {h['valid_until']}")
    lines.append(f"- **Audience:** {md(', '.join(h['audience']))}")
    if h.get("pirs"):
        lines.append(f"- **Requirement addressed:** {md('; '.join(h['pirs']))}")
    lines.append(f"- **Producer:** {md(h['producer'])}")
    if h.get("feedback_contact"):
        lines.append(f"- **Feedback:** {md(h['feedback_contact'])}")
    lines.extend(["", f"> {tlp_label(tlp)}: {TLP_DEFINITIONS[tlp]} {pap_label(pap)}: {PAP_DEFINITIONS[pap]}"])
    revisions = h.get("revision_history") or []
    if len(revisions) > 1:
        lines.extend(["", "| Version | Issued (UTC) | Status | Change |", "|---:|---|---|---|"])
        lines.extend(
            f"| {r['version']} | {r['issued_at'][:16].replace('T', ' ')} | {r['status']} | {md(r['summary'])} |"
            for r in revisions
        )
    return "\n".join(lines)


@element(
    "header",
    "Report header",
    (M,),
    ("ReportIssue", "reports/contract.py"),
    markdown=_header_md,
    description="Report ID, version, status, marking, audience, requirement, validity and producer.",
)
def build_header(context: ReportContext) -> ElementResult:
    from pivotglass.reports.elements import ELEMENTS

    if context.header is None:
        raise RuntimeError("the report header was not prepared")
    return ELEMENTS["header"].result(ElementStatus.COMPLETE, context.header.model_dump(mode="json"))


# --- PIR verdict ------------------------------------------------------------


def _pir_md(result: ElementResult, output: OutputFormat) -> str:
    pir = result.content
    lines = ["## Priority Intelligence Requirement", ""]
    if pir.get("question"):
        lines.extend([f"**Question:** {md(pir['question'])}", ""])
    if pir.get("verdict") == "no_pir" and not pir.get("category_label"):
        lines.append(f"**Verdict:** {pir.get('verdict_label', 'No PIR recorded')}. {pir.get('next_step', '')}".rstrip())
        return "\n".join(lines)
    lines.append(f"- **Category:** {pir['category_label']} · **Tier:** {pir['level_label']} ({pir['audience']})")
    lines.append(f"- **Verdict:** {pir['verdict_label']}")
    lines.append(
        f"- **Stop conditions met:** {pir['resolved_count']} of {len(pir['stop_conditions'])}"
        f" · **Accepted conclusions:** {pir['conclusion_count']}"
    )
    lines.append(f"- **Collection fit ({pir['collection_fit']}):** {md(pir['fit_note'])}")
    open_stops = [stop for stop in pir["stop_conditions"] if stop["status"] not in MET]
    if open_stops:
        lines.extend(["", "Still needed for an answer:"])
        lines.extend(f"- {md(stop['statement'])}" for stop in open_stops)
    if pir.get("open_gaps"):
        lines.extend(["", "Open knowledge gaps:"])
        lines.extend(f"- {md(gap)}" for gap in pir["open_gaps"])
    return "\n".join(lines)


@element(
    "pir_verdict",
    "Priority intelligence requirement",
    (M,),
    ("AnalyticInvestigation", "reports/pir.py"),
    markdown=_pir_md,
    description="The question, its category and tier, and the deterministic verdict (DEC-PIR-001).",
)
def build_pir_verdict(context: ReportContext) -> ElementResult:
    from pivotglass.reports.elements import ELEMENTS

    spec = ELEMENTS["pir_verdict"]
    pir = context.pir
    if pir.get("verdict") == "no_pir":
        return spec.result(
            ElementStatus.PARTIAL,
            pir,
            gaps=["No PIR category and tier are recorded, so the report cannot state whether it answers one."],
        )
    citations = [f"lifecycle:{stop['id']}" for stop in pir.get("stop_conditions", [])]
    return spec.result(ElementStatus.COMPLETE, pir, citations=citations)


# --- sources ----------------------------------------------------------------


def _sources_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("sources", [])
    lines = ["## Sources", ""]
    if not rows:
        lines.append(_empty_line("No collection source has run in this workspace."))
        return "\n".join(lines)
    lines.extend(
        [
            "| Source | Runs | Objects | First run (UTC) | Last run (UTC) | Rating |",
            "|---|---:|---:|---|---|---|",
        ]
    )
    for row in rows:
        rating = f"{row['reliability']}{row['credibility']}"
        lines.append(
            f"| {md(row['name'])} | {row['runs']} | {row['objects']} | {row['first_run'] or 'unknown'} | "
            f"{row['last_run'] or 'unknown'} | {rating} |"
        )
    lines.extend(
        [
            "",
            "Ratings use the Admiralty code: source reliability "
            + ", ".join(f"{k.value} {v.lower()}" for k, v in SOURCE_RELIABILITY_LABELS.items())
            + "; information credibility "
            + ", ".join(f"{k.value} {v.lower()}" for k, v in INFORMATION_CREDIBILITY_LABELS.items())
            + ".",
        ]
    )
    return "\n".join(lines)


def _time(value: object) -> str | None:
    text = str(value or "")[:16].replace("T", " ")
    return text or None


@element(
    "sources",
    "Sources",
    (M,),
    ("module runs",),
    markdown=_sources_md,
    description="Every collection source that ran, with run and object counts and its Admiralty rating.",
)
def build_sources(context: ReportContext) -> ElementResult:
    from pivotglass.reports.elements import ELEMENTS

    spec = ELEMENTS["sources"]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in context.module_runs:
        grouped[str(run.get("module_name") or "unknown")].append(run)
    rows = []
    for name in sorted(grouped):
        runs = grouped[name]
        times = sorted(t for t in (_time(run.get("timestamp")) for run in runs) if t)
        rows.append(
            {
                "name": name,
                "runs": len(runs),
                "objects": sum(int(run.get("result_count") or 0) for run in runs),
                "first_run": times[0] if times else None,
                "last_run": times[-1] if times else None,
                # Pivotglass records no source ratings yet; F6 states that honestly.
                "reliability": SourceReliability.F.value,
                "credibility": InformationCredibility.CANNOT_BE_JUDGED.value,
            }
        )
    if not rows:
        return spec.result(ElementStatus.EMPTY, {"sources": []}, gaps=["No collection source has run."])
    return spec.result(
        ElementStatus.PARTIAL,
        {"sources": rows},
        citations=[f"module:{row['name']}" for row in rows],
        gaps=["Sources are not yet rated, so each is shown as F6 (reliability and credibility cannot be judged)."],
    )


# --- gaps and limitations ---------------------------------------------------


def _gaps_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Gaps and Limitations", ""]
    if not any(c.get(key) for key in ("knowledge_gaps", "limitations", "report_gaps", "load_errors")):
        lines.append(_empty_line("No gaps or limitations recorded, and every element of this report was built in full."))
        return "\n".join(lines)
    for key, heading in (
        ("knowledge_gaps", "Knowledge gaps (analyst)"),
        ("limitations", "Limitations (analyst)"),
        ("report_gaps", "Incomplete report elements"),
        ("load_errors", "Records that could not be read"),
    ):
        if c.get(key):
            lines.extend([f"**{heading}:**", ""])
            for row in c[key]:
                if isinstance(row, dict):
                    suffix = f" ({row['status']})" if row.get("status") and row["status"] != "open" else ""
                    lines.append(f"- {md(row.get('statement') or row.get('gap'))}{suffix}")
                else:
                    lines.append(f"- {md(row)}")
            lines.append("")
    return "\n".join(lines).rstrip()


@element(
    "gaps_limitations",
    "Gaps and limitations",
    (M, A),
    ("lifecycle knowledge_gap and limitation items", "element results"),
    markdown=_gaps_md,
    description="Recorded knowledge gaps and limitations, plus every element that came back empty or partial.",
)
def build_gaps_limitations(context: ReportContext) -> ElementResult:
    from pivotglass.reports.elements import ELEMENTS

    investigation = context.investigation
    items = [
        row
        for row in context.analysis["lifecycle_items"]
        if investigation is not None and row.get("investigation_id") == investigation["id"]
    ]

    def pick(kind: str) -> list[dict[str, Any]]:
        return [
            {"id": row["id"], "statement": row.get("statement"), "status": row.get("status")}
            for row in items
            if row.get("item_type") == kind and row.get("status") != "deferred"
        ]

    report_gaps = [
        {"element": result.element_id, "status": result.status.value, "gap": f"{result.title}: {gap}"}
        for result in context.results.values()
        for gap in result.gaps
    ]
    content = {
        "knowledge_gaps": pick("knowledge_gap"),
        "limitations": pick("limitation"),
        "report_gaps": report_gaps,
        "load_errors": list(context.load_errors),
    }
    citations = [f"lifecycle:{row['id']}" for row in content["knowledge_gaps"] + content["limitations"]]
    # The section itself is always complete: listing nothing is a statement.
    return ELEMENTS["gaps_limitations"].result(ElementStatus.COMPLETE, content, citations=citations)


# --- IOC table --------------------------------------------------------------


def _ioc_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("indicators", [])
    lines = ["## Indicators of Compromise", ""]
    if not rows:
        lines.append(_empty_line("No indicators collected."))
        return "\n".join(lines)
    lines.extend(["| Type | Value | First Seen |", "|------|-------|------------|"])
    for row in rows:
        value = render_indicator(row["value"], row["type"], output)
        lines.append(f"| {row['type']} | {md(value)} | {row['first_seen'] or 'unknown'} |")
    if output in {OutputFormat.MARKDOWN}:
        lines.extend(["", "_Values are defanged for reading. The JSON and STIX renderings carry them unchanged._"])
    return "\n".join(lines)


def indicator_rows(stix_objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per collected SCO: type, display value (best hash for files), first seen, STIX id."""

    from pivotglass.core.evidence_detail import _indicator_value

    rows = []
    for obj in stix_objects:
        obj_type = str(obj.get("type", ""))
        value = _indicator_value(obj)
        if obj_type == "file":
            hashes = obj.get("hashes") or {}
            if isinstance(hashes, dict):
                value = next((str(hashes[k]) for k in ("SHA-256", "SHA-1", "MD5") if hashes.get(k)), value)
        rows.append(
            {
                "type": obj_type,
                "value": value,
                "first_seen": str(obj.get("created", ""))[:10] or None,
                "stix_id": obj.get("id"),
            }
        )
    return rows


@element(
    "ioc_table",
    "Indicators of compromise",
    (E,),
    ("STIX objects",),
    markdown=_ioc_md,
    description="Every collected indicator, with its type and first-seen date.",
)
def build_ioc_table(context: ReportContext) -> ElementResult:
    from pivotglass.reports.elements import ELEMENTS

    spec = ELEMENTS["ioc_table"]
    rows = indicator_rows(context.stix_objects)
    if not rows:
        return spec.result(ElementStatus.EMPTY, {"indicators": []}, gaps=["No indicators have been collected."])
    citations = [f"stix:{row['stix_id']}" for row in rows if row["stix_id"]]
    return spec.result(ElementStatus.COMPLETE, {"indicators": rows}, citations=citations)


# --- collection timeline ----------------------------------------------------


def _timeline_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("runs", [])
    lines = ["## Investigation Timeline", ""]
    if not rows:
        lines.append(_empty_line("No module runs recorded."))
        return "\n".join(lines)
    lines.extend(
        f"- `{row['time'] or 'unknown'}` — **{row['module']}** on `{render_indicator(row['target'], guess_indicator_kind(row['target']), output)}`"
        f" -> {row['objects']} object(s)"
        for row in rows
    )
    return "\n".join(lines)


@element(
    "collection_timeline",
    "Investigation timeline",
    (E,),
    ("module runs",),
    markdown=_timeline_md,
    description="Each collection run in order: time, source, target and object count.",
)
def build_collection_timeline(context: ReportContext) -> ElementResult:
    from pivotglass.reports.elements import ELEMENTS

    spec = ELEMENTS["collection_timeline"]
    rows = [
        {
            "time": _time(run.get("timestamp")),
            "module": str(run.get("module_name") or "unknown"),
            "target": str(run.get("target") or "unknown"),
            "objects": int(run.get("result_count") or 0),
        }
        for run in context.module_runs
    ]
    if not rows:
        return spec.result(ElementStatus.EMPTY, {"runs": []}, gaps=["No module runs are recorded."])
    return spec.result(ElementStatus.COMPLETE, {"runs": rows}, citations=[f"module:{r['module']}" for r in rows])


__all__ = ["LATE_ELEMENTS", "MANDATORY_ELEMENTS", "guess_indicator_kind", "indicator_rows", "md"]
