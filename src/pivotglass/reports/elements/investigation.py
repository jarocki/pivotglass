"""Elements of the ``investigation-report`` type: the whole-workspace investigation record.

These replace ``core/dossier_report.py`` (DEC-M7-REPORT-002, superseded by
DEC-REPORT-ELEMENTS-001). The facts each section carries are unchanged; the
golden test in ``tests/test_report_system.py`` holds them to the old output.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pivotglass.reports.contract import OutputFormat, ProvenanceClass
from pivotglass.reports.elements import (
    ELEMENTS,
    ElementResult,
    ElementStatus,
    ReportContext,
    element,
)
from pivotglass.reports.elements.common import md

E, M, A = ProvenanceClass.EVIDENCE, ProvenanceClass.METHOD, ProvenanceClass.ANALYST


def _unresolved(analysis: dict[str, list[dict[str, Any]]]) -> int:
    return sum(1 for row in analysis["contradictions"] if row["status"] == "unresolved")


# --- overview ---------------------------------------------------------------


def _overview_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = [
        "## Overview",
        "",
        f"- **Workspace:** {md(c['workspace'])}",
        f"- **Total Score:** {c['total_score']}",
        f"- **Modules Used:** {c['modules_used']}",
        f"- **Total Indicators:** {c['total_indicators']}",
    ]
    if c.get("analytic_status"):
        lines.append(f"- **Analytic Status:** {c['analytic_status']}")
        lines.append(f"- **Open Contradictions:** {c['open_contradictions']}")
    return "\n".join(lines)


@element(
    "overview",
    "Overview",
    (M,),
    ("workspace", "analytic ledger"),
    markdown=_overview_md,
    description="Workspace, score, modules used, indicator count and analytic status.",
)
def build_overview(context: ReportContext) -> ElementResult:
    investigation = context.investigation
    content = {
        "workspace": context.workspace_name,
        "total_score": context.total_score,
        "modules_used": len({run["module_name"] for run in context.module_runs}),
        "total_indicators": len(context.stix_objects),
        "analytic_status": investigation["status"] if investigation else None,
        "open_contradictions": _unresolved(context.analysis),
    }
    return ELEMENTS["overview"].result(ElementStatus.COMPLETE, content)


# --- collection summary -----------------------------------------------------


def _summary_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Executive Summary", ""]
    if c["total_indicators"] == 0:
        lines.append("No indicators collected. Investigation workspace is empty.")
        return "\n".join(lines)
    lines.append(
        f"This investigation collected **{c['total_indicators']} indicator(s)** across "
        f"**{c['modules_used']} module(s)**. Total pursuit score: **{c['total_score']} pts**."
    )
    if c["type_counts"]:
        lines.append("Indicator types: " + ", ".join(f"{t}: {n}" for t, n in sorted(c["type_counts"].items())) + ".")
    return "\n".join(lines)


@element(
    "collection_summary",
    "Collection summary",
    (M,),
    ("STIX objects", "module runs"),
    markdown=_summary_md,
    description="Counts of what was collected, by type and source. A computed summary, not a judgment.",
)
def build_collection_summary(context: ReportContext) -> ElementResult:
    spec = ELEMENTS["collection_summary"]
    content = {
        "total_indicators": len(context.stix_objects),
        "modules_used": len({run["module_name"] for run in context.module_runs}),
        "total_score": context.total_score,
        "type_counts": dict(context.type_counts),
    }
    status = ElementStatus.COMPLETE if content["total_indicators"] else ElementStatus.EMPTY
    return spec.result(status, content, gaps=[] if content["total_indicators"] else ["Nothing has been collected."])


# --- scientific investigation -----------------------------------------------


def _fence(payload: str) -> str:
    # A recorded string may itself contain Markdown fences. Keep every authored
    # byte inside an inert, correctly closed block.
    return "`" * max(3, 1 + max((len(run) for run in re.findall(r"`+", payload)), default=0))


def _science_md(result: ElementResult, output: OutputFormat) -> str:  # noqa: PLR0915 - one section, many parts
    c = result.content
    lines = ["## Scientific Investigation", ""]
    inv = c.get("investigation")
    if inv is None:
        lines.append("_No scientific investigation has been framed yet. Use `analysis question <text>` to begin._")
        return "\n".join(lines)
    lines.extend(
        [
            f"### {md(inv['title'])}",
            "",
            f"- **Purpose:** {md(inv['purpose'])}",
            f"- **Scope:** {md(inv['scope'])}",
            f"- **State:** {inv['status']}",
            f"- **Authority:** {inv['created_by']}",
            "",
            "### Investigation Questions",
            "",
        ]
    )
    lines.extend(f"- **{str(row['status']).upper()}** — {md(row['text'])}" for row in c["questions"])
    if not c["questions"]:
        lines.append("_No question linked to this investigation._")

    lines.extend(["", "### Assumptions and Assertions", ""])
    lines.extend(
        f"- **{str(row['assertion_type']).upper()} · {str(row['status']).upper()} · "
        f"{str(row['author_kind']).upper()}** — {md(row['statement'])}"
        for row in c["assertions"]
    )
    if not c["assertions"]:
        lines.append("_No assumptions or assertions recorded._")

    lines.extend(
        [
            "",
            "### Competing Hypotheses",
            "",
            "| Hypothesis | Status | Author | Confidence | Likelihood |",
            "|---|---|---|---|---|",
        ]
    )
    lines.extend(
        f"| {md(row['statement'])} | {row['status']} | {row['author_kind']} | "
        f"{row['confidence'] or 'not assessed'} | {row['likelihood'] or 'not assessed'} |"
        for row in c["hypotheses"]
    )
    if not c["hypotheses"]:
        lines.append("| _No competing hypotheses recorded._ | — | — | — | — |")

    lines.extend(
        [
            "",
            "### Evidence Tests",
            "",
            "Evidence links below are explicit analytic relationships. They do not change the underlying observation.",
            "",
            "| Source record | Stance | Target record | Rationale |",
            "|---|---|---|---|",
        ]
    )
    lines.extend(
        f"| `{row['source_kind']}:{row['source_id']}` | **{row['stance']}** | "
        f"`{row['target_kind']}:{row['target_id']}` | {md(row['rationale'])} |"
        for row in c["evidence_links"]
    )
    if not c["evidence_links"]:
        lines.append("| _No explicit evidence tests recorded._ | — | — | — |")

    lines.extend(["", "### Predictions, Signposts, Collection, and Stopping Rules", ""])
    lines.extend(
        f"- **{str(item['item_type']).replace('_', ' ').upper()} · {str(item['status']).upper()}** — {md(item['statement'])}"
        for item in c["planning"]
    )
    if not c["planning"]:
        lines.append("_No predictions, signposts, collection requirements, or stop conditions._")

    lines.extend(
        [
            "",
            "### Priority Intelligence Requirements and Next Best Information",
            "",
            "Recorded requirements are ranked by explicit analyst priority when present. Otherwise the "
            "versioned deterministic information-value policy is used; missing factors score zero.",
            "",
            "| Rank | Requirement | Score | Authority |",
            "|---:|---|---:|---|",
        ]
    )
    lines.extend(
        f"| {row['rank']} | {md(row['statement'])} | {row['rank_score']}/100 | {row['priority_source']} |"
        for row in c["requirements"]
    )
    if not c["requirements"]:
        lines.append("| — | _No priority intelligence requirements recorded._ | — | — |")
    lines.extend(["", "**Method-derived suggestions (not evidence):**", ""])
    for row in c["suggestions"]:
        lines.append(
            f"- **{row['score']}/100 · {str(row['suggestion_type']).replace('_', ' ').upper()}** — {md(row['statement'])}"
        )
        lines.append(f"  - Rationale: {md(row['rationale'])}")
    if not c["suggestions"]:
        lines.append("_No method-derived next-information suggestions at this stage._")

    lines.extend(["", "### Structured Analytic Technique Runs", ""])
    if c["method_runs"]:
        lines.append("Recorded method work is authored analysis, not observed evidence or automatic approval.")
        for row in c["method_runs"]:
            lines.append(
                f"- **{str(row['technique']).replace('_', ' ').title()} v{row['technique_version']}** "
                f"— {row['status']}; analyst disposition: {row['analyst_disposition']}"
            )
            for label, key in (("Recorded inputs", "input_blob"), ("Recorded outputs", "output_blob")):
                payload = json.dumps(row.get(key) or {}, ensure_ascii=False, indent=2, sort_keys=True)
                fence = _fence(payload)
                lines.extend(["", f"**{label}:**", "", f"{fence}json", payload, fence, ""])
    else:
        lines.append("_No Structured Analytic Technique runs recorded._")

    lines.extend(["", "### Contradictions", ""])
    for row in c["contradictions"]:
        lines.append(f"- **{str(row['materiality']).upper()} · {str(row['status']).upper()}** — {md(row['summary'])}")
        if row["status"] == "unresolved":
            lines.append(f"  - Resolution required: {md(row['resolution_required'])}")
        elif row.get("resolution_note"):
            lines.append(f"  - Resolution: {md(row['resolution_note'])}")
    if not c["contradictions"]:
        lines.append("_No explicit contradictions recorded._")

    lines.extend(["", "### Conclusions, Limitations, and Intelligence Gaps", ""])
    lines.extend(
        f"- **{str(item['item_type']).replace('_', ' ').upper()} · {str(item['status']).upper()}** — {md(item['statement'])}"
        for item in c["closing"]
    )
    if not c["closing"]:
        lines.append("_No conclusion, limitation, or intelligence gap recorded._")

    lines.extend(["", "### Confidence Basis", ""])
    for row in c["confidence"]:
        lines.append(
            f"- **{row['target_kind']}:{row['target_id']} — {str(row['level']).upper()} confidence**: {md(row['rationale'])}"
        )
        if row.get("factors"):
            lines.append(f"  - Factors: `{row['factors']}`")
    if not c["confidence"]:
        lines.append("_No formal confidence assessment recorded._")
    return "\n".join(lines)


@element(
    "scientific_investigation",
    "Scientific investigation",
    (A, M),
    ("analytic ledger", "information requirements", "structured analysis"),
    markdown=_science_md,
    description=(
        "The investigation's questions, assertions, competing hypotheses with confidence and likelihood, "
        "evidence tests, planning items, ranked requirements, technique runs, contradictions and conclusions."
    ),
)
def build_scientific_investigation(context: ReportContext) -> ElementResult:  # noqa: PLR0914
    from pivotglass.core.information_requirements import build_information_requirements

    spec = ELEMENTS["scientific_investigation"]
    analysis = context.analysis
    investigations = analysis["investigations"]
    if not investigations:
        return spec.result(
            ElementStatus.EMPTY, {"investigation": None}, gaps=["No scientific investigation has been framed."]
        )
    investigation = investigations[-1]
    items = [item for item in analysis["lifecycle_items"] if item["investigation_id"] == investigation["id"]]
    linked = {
        (str(item.get("record_kind")), str(item.get("record_id")))
        for item in items
        if item.get("record_kind") and item.get("record_id")
    }

    def linked_rows(table: str, kind: str) -> list[dict[str, Any]]:
        return [row for row in analysis[table] if (kind, str(row["id"])) in linked]

    by_target = {
        name: {(str(row["target_kind"]), str(row["target_id"])): row for row in analysis[name]}
        for name in ("confidence", "likelihood")
    }
    hypotheses = []
    for row in linked_rows("hypotheses", "hypothesis"):
        key = ("hypothesis", str(row["id"]))
        hypotheses.append(
            {
                "id": row["id"],
                "statement": row["statement"],
                "status": row["status"],
                "author_kind": row["author_kind"],
                "confidence": (by_target["confidence"].get(key) or {}).get("level"),
                "likelihood": (by_target["likelihood"].get(key) or {}).get("term"),
            }
        )

    def item_rows(kinds: set[str]) -> list[dict[str, Any]]:
        return [
            {
                "id": item["id"],
                "item_type": item["item_type"],
                "status": item["status"],
                "statement": item.get("statement") or item.get("record_id") or "unavailable",
            }
            for item in items
            if item["item_type"] in kinds
        ]

    priority = build_information_requirements(analysis)
    content = {
        "investigation": {
            key: investigation[key] for key in ("id", "title", "purpose", "scope", "status", "created_by")
        },
        "questions": [
            {"id": row["id"], "status": row["status"], "text": row["text"]}
            for row in linked_rows("questions", "question")
        ],
        "assertions": [
            {key: row[key] for key in ("id", "assertion_type", "status", "author_kind", "statement")}
            for row in linked_rows("assertions", "assertion")
        ],
        "hypotheses": hypotheses,
        "evidence_links": [
            {key: row[key] for key in ("source_kind", "source_id", "stance", "target_kind", "target_id", "rationale")}
            for row in analysis["evidence_links"]
            if (str(row["target_kind"]), str(row["target_id"])) in linked
        ],
        "planning": item_rows({"prediction", "signpost", "collection_requirement", "stop_condition"}),
        "requirements": [
            {key: row[key] for key in ("rank", "statement", "rank_score", "priority_source")}
            for row in priority["requirements"]
        ],
        "suggestions": [
            {key: row[key] for key in ("score", "suggestion_type", "statement", "rationale")}
            for row in priority["suggestions"]
        ],
        "method_runs": [
            {
                key: row.get(key)
                for key in (
                    "id", "technique", "technique_version", "status", "analyst_disposition", "input_blob", "output_blob",
                )
            }
            for row in linked_rows("method_runs", "method_run")
        ],
        "contradictions": [
            {
                key: row.get(key)
                for key in ("id", "materiality", "status", "summary", "resolution_required", "resolution_note")
            }
            for row in analysis["contradictions"]
        ],
        "closing": item_rows({"conclusion", "limitation", "knowledge_gap"}),
        "confidence": [
            {key: row.get(key) for key in ("target_kind", "target_id", "level", "rationale", "factors")}
            for row in analysis["confidence"]
        ],
    }
    citations = [f"lifecycle:{item['id']}" for item in items]
    gaps = [] if content["questions"] else ["The investigation has no linked question."]
    status = ElementStatus.COMPLETE if content["questions"] else ElementStatus.PARTIAL
    return spec.result(status, content, citations=citations, gaps=gaps)


# --- dossier slots ----------------------------------------------------------


def _slots_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("slots")
    lines = ["## Dossier State", ""]
    if not rows:
        lines.append("_No dossier state recorded yet. Run a hunt to populate the dossier._")
        return "\n".join(lines)
    lines.extend(["| Slot | Status | Evidence Count | Contributing Types |", "|------|--------|----------------|--------------------|"])
    lines.extend(
        f"| {row['slot'].title()} | {row['status'].upper()} | {row['evidence_count']} | {', '.join(row['contributing_types'])} |"
        for row in rows
    )
    return "\n".join(lines)


@element(
    "dossier_slots",
    "Dossier state",
    (E, M),
    ("dossier state",),
    markdown=_slots_md,
    description="The nine dossier slots with status, evidence count and contributing types.",
)
def build_dossier_slots(context: ReportContext) -> ElementResult:
    from pivotglass.dossier.slots import DossierSlotName

    spec = ELEMENTS["dossier_slots"]
    state = context.dossier_state
    if state is None:
        return spec.result(ElementStatus.EMPTY, {"slots": []}, gaps=["No dossier state is recorded."])
    order = (
        DossierSlotName.IDENTITY, DossierSlotName.TTPS, DossierSlotName.INFRASTRUCTURE, DossierSlotName.TIMING,
        DossierSlotName.TARGETING, DossierSlotName.CAPABILITY, DossierSlotName.MOTIVATION,
        DossierSlotName.PREDICTIONS, DossierSlotName.DENIAL,
    )
    rows = []
    for name in order:
        slot = state.slots.get(name)
        rows.append(
            {
                "slot": name.value,
                "status": slot.status.value if slot else "empty",
                "evidence_count": slot.evidence_count if slot else 0,
                "contributing_types": sorted(slot.contributing_types) if slot and slot.contributing_types else [],
            }
        )
    return spec.result(ElementStatus.COMPLETE, {"slots": rows})


# --- legacy predictions -----------------------------------------------------


def _predictions_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("predictions", [])
    lines = [
        "## Predictions",
        "",
        "_Legacy Dossier Predictions Log. Schema-v4 scientific predictions and signposts are reported in "
        "Scientific Investigation above._",
        "",
    ]
    if not rows:
        lines.append(
            "_No legacy dossier predictions authored. Use `analysis prediction <text>` in the command bar or "
            "terminal cyberdeck to record a scientific prediction in the lifecycle section._"
        )
        return "\n".join(lines)
    groups = {status: [row for row in rows if row["status"] == status] for status in ("validated", "pending", "falsified")}
    lines.extend(
        [
            f"**Summary:** {len(groups['validated'])} validated, {len(groups['pending'])} pending, "
            f"{len(groups['falsified'])} falsified",
            "",
        ]
    )
    for status, heading in (("validated", "Validated"), ("pending", "Pending"), ("falsified", "Falsified")):
        if not groups[status]:
            continue
        lines.extend([f"### {heading} Predictions", ""])
        for row in groups[status]:
            text = f"**[{row['slot'].title()}]** {row['text']}"
            if status == "validated":
                lines.append(f"- {text} _(validated {(row['validated_at'] or 'unknown')[:10]})_")
            elif status == "falsified":
                lines.append(f"- ~~{text}~~")
            else:
                lines.append(f"- {text}")
        lines.append("")
    return "\n".join(lines).rstrip()


@element(
    "legacy_predictions",
    "Legacy predictions log",
    (A,),
    ("dossier predictions log",),
    markdown=_predictions_md,
    description="The pre-v4 dossier predictions log, grouped by status.",
)
def build_legacy_predictions(context: ReportContext) -> ElementResult:
    rows = [
        {"slot": p.slot, "text": p.text, "status": p.status, "validated_at": p.validated_at}
        for p in context.legacy_predictions
    ]
    return ELEMENTS["legacy_predictions"].result(
        ElementStatus.COMPLETE if rows else ElementStatus.EMPTY, {"predictions": rows}
    )


# --- analyst notes ----------------------------------------------------------


def _notes_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("notes", [])
    lines = ["## Analyst Notes", ""]
    if not rows:
        lines.append("_No analyst notes authored yet. Use `note <text>` to add notes._")
        return "\n".join(lines)
    for row in rows:
        stamp = f"[{str(row['created_at'])[:16]}] " if row.get("created_at") else ""
        lines.append(f"- {stamp}{row['content']}")
    return "\n".join(lines)


@element(
    "analyst_notes",
    "Analyst notes",
    (A,),
    ("analyst notes",),
    markdown=_notes_md,
    description="Free-text analyst notes, in the order written.",
)
def build_analyst_notes(context: ReportContext) -> ElementResult:
    rows = context.notes
    return ELEMENTS["analyst_notes"].result(
        ElementStatus.COMPLETE if rows else ElementStatus.EMPTY,
        {"notes": rows},
        citations=[f"note:{row['id']}" for row in rows],
    )


# --- statistics -------------------------------------------------------------


def _stats_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Statistics", "", f"- Total indicators: {c['total_indicators']}"]
    if c["type_counts"]:
        lines.append("- By type:")
        lines.extend(f"  - {t}: {n}" for t, n in sorted(c["type_counts"].items()))
    else:
        lines.append("- By type: (none)")
    lines.append(f"- Total score: {c['total_score']}")
    return "\n".join(lines)


@element(
    "statistics",
    "Statistics",
    (M,),
    ("STIX objects", "score events"),
    markdown=_stats_md,
    description="Indicator counts by type and the pursuit score.",
)
def build_statistics(context: ReportContext) -> ElementResult:
    content = {
        "total_indicators": len(context.stix_objects),
        "type_counts": dict(context.type_counts),
        "total_score": context.total_score,
    }
    return ELEMENTS["statistics"].result(ElementStatus.COMPLETE, content)
