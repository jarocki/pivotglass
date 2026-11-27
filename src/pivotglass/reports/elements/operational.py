"""Domain 2 elements: alert, campaign and vulnerability sections (#54, #58).

Evidence sections read observations, mappings and analyst tags. Analyst prose,
severity and recommendations come from ``reports/sections.py`` records; the
narrative's step list is a method over accepted Kill Chain and ATT&CK
mappings, so a missing phase is shown as missing rather than written around.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from pivotglass.reports.claims import claims
from pivotglass.reports.contract import (
    SEVERITY_DEFINITIONS,
    OutputFormat,
    ProvenanceClass,
    Severity,
    render_indicator,
)
from pivotglass.reports.elements import (
    ELEMENTS,
    ElementResult,
    ElementStatus,
    ReportContext,
    element,
)
from pivotglass.reports.elements.common import (
    detailed_indicators,
    guess_indicator_kind,
    indicator_rows,
    md,
)
from pivotglass.reports.sections import recommendations, section_texts, severity

E, M, A, D = ProvenanceClass.EVIDENCE, ProvenanceClass.METHOD, ProvenanceClass.ANALYST, ProvenanceClass.MODEL_DRAFT
KILL_CHAIN_PHASES = (
    ("reconnaissance", "Reconnaissance"), ("weaponization", "Weaponization"), ("delivery", "Delivery"),
    ("exploitation", "Exploitation"), ("installation", "Installation"),
    ("command-and-control", "Command and Control"), ("actions-on-objectives", "Actions on Objectives"),
)


def _spec(element_id: str):  # noqa: ANN202
    return ELEMENTS[element_id]


def _texts(context: ReportContext, section: str) -> list[dict[str, Any]]:
    return [
        {"id": row["id"], "text": row["statement"], "author": row.get("author_kind"), "time": str(row.get("created_at") or "")[:16],
         "draft": row.get("author_kind") == "model"}
        for row in section_texts(context.analysis, section)
    ]


def _prose(rows: list[dict[str, Any]]) -> list[str]:
    return [f"{'**Model draft** · ' if r['draft'] else ''}{r['text']} <sub>— {r['author']}, {r['time']}</sub>" for r in rows]


def _accepted(context: ReportContext, framework: str) -> list[Any]:
    return [m for m in context.mappings if m.framework.value == framework and m.state.value == "accepted"]


# --- threat summary ---------------------------------------------------------


def _summary_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Threat Summary", ""]
    rating = c.get("severity")
    if rating:
        lines += [f"**Severity: {rating['level'].title()}** — {md(rating['reason'])} ({SEVERITY_DEFINITIONS[Severity(rating['level'])]})", ""]
    lines += _prose(c.get("texts", [])) or ["_No summary written. Add one with `report write threat_summary | <text>`._"]
    return "\n".join(lines)


@element(
    "threat_summary",
    "Threat summary",
    (D, A),
    ("report section text", "report severity"),
    markdown=_summary_md,
    description="Two or three sentences: what is happening, who is targeted, how it arrives and why it matters now, "
    "with the severity and its reason.",
)
def build_threat_summary(context: ReportContext) -> ElementResult:
    texts = _texts(context, "threat_summary")
    rated = severity(context.analysis)
    content = {
        "texts": texts,
        "severity": {"level": rated["object_value"], "reason": rated["statement"], "id": rated["id"]} if rated else None,
    }
    gaps = [] if texts else ["No threat summary is written (`report write threat_summary | <text>`)."]
    if not rated:
        gaps.append("No severity is recorded (`report severity <level> | <reason>`).")
    status = ElementStatus.EMPTY if not texts else ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE
    return _spec("threat_summary").result(status, content, gaps=gaps, pending_model_drafts=sum(r["draft"] for r in texts))


# --- techniques and delivery --------------------------------------------------


def _technique_rows(context: ReportContext) -> list[dict[str, Any]]:
    catalog = context.attack_catalog
    rows = []
    for m in sorted(_accepted(context, "attack"), key=lambda m: m.content_id):
        technique = catalog.technique(m.content_id) if catalog else None
        rows.append(
            {"technique_id": m.content_id, "name": technique.name if technique else m.content_label,
             "tactics": list(technique.tactics) if technique else [], "procedure": m.basis,
             "evidence": list(m.evidence_refs), "version": m.framework_version}
        )
    return rows


def _techniques_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("techniques", [])
    lines = ["## Techniques Observed", ""]
    if not rows:
        return "\n".join([*lines, "_No accepted ATT&CK mapping._"])
    lines += [f"- **{r['technique_id']}** {md(r['name'])} — {md(r['procedure'])}" for r in rows]
    return "\n".join(lines)


@element(
    "technique_list",
    "Techniques observed",
    (E,),
    ("accepted framework mappings",),
    markdown=_techniques_md,
    description="ATT&CK technique IDs and names observed in this activity, with the procedure, pinned to v19.2.",
)
def build_technique_list(context: ReportContext) -> ElementResult:
    rows = _technique_rows(context)
    spec = _spec("technique_list")
    if not rows:
        return spec.result(ElementStatus.EMPTY, {"techniques": []}, gaps=["No accepted ATT&CK mapping exists."])
    other = [r["technique_id"] for r in rows if r["version"] != "19.2"]
    gaps = [f"{len(other)} mapping(s) use an ATT&CK version other than 19.2."] if other else []
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, {"techniques": rows},
                       citations=[f"observation:{ref}" for r in rows for ref in r["evidence"]], gaps=gaps)


def _delivery_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Delivery and Initial Access", ""]
    if not (c.get("steps") or c.get("indicators")):
        return "\n".join([*lines, "_How the activity arrives is not established._"])
    lines += [f"- **{md(s['phase'])}:** {md(s['procedure'])} <sub>[{s['source']}]</sub>" for s in c.get("steps", [])]
    if c.get("indicators"):
        lines += ["", "Delivery indicators (analyst-tagged): " + ", ".join(
            f"{md(render_indicator(i['value'], i['type'], output))} ({i['role']})" for i in c["indicators"])]
    return "\n".join(lines)


@element(
    "delivery_vector",
    "Delivery and initial access",
    (E,),
    ("Kill Chain delivery and exploitation mappings", "ATT&CK initial-access mappings", "role and tactic tags"),
    markdown=_delivery_md,
    description="How the activity reaches the target and gains a foothold: accepted Kill Chain delivery and exploitation "
    "mappings, ATT&CK initial-access techniques, and indicators tagged as delivery or phishing.",
)
def build_delivery_vector(context: ReportContext) -> ElementResult:
    steps = [
        {"phase": m.content_label, "procedure": m.basis, "source": f"mapping:{m.id}"}
        for m in _accepted(context, "kill_chain")
        if m.content_id in {"delivery", "exploitation"}
    ]
    steps += [
        {"phase": f"{r['technique_id']} {r['name']}", "procedure": r["procedure"], "source": f"ATT&CK {r['version']}"}
        for r in _technique_rows(context)
        if "initial-access" in r["tactics"]
    ]
    tags = context.indicator_tags
    indicators = []
    for row in indicator_rows(context.stix_objects):
        found = tags.get((row["type"], row["value"].lower()), {})
        roles = found.get("role", set()) & {"delivery", "phishing"}
        if roles or "initial-access" in found.get("tactic", set()):
            indicators.append({"type": row["type"], "value": row["value"], "role": ", ".join(sorted(roles)) or "initial access"})
    spec = _spec("delivery_vector")
    gaps = []
    if context.attack_catalog is None and _accepted(context, "attack"):
        gaps.append("ATT&CK content is not installed, so initial-access techniques cannot be identified by tactic.")
    if not (steps or indicators):
        return spec.result(ElementStatus.EMPTY, {"steps": [], "indicators": []},
                           gaps=gaps + ["No delivery or exploitation mapping and no indicator tagged delivery or phishing."])
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, {"steps": steps, "indicators": indicators},
                       citations=[s["source"] for s in steps], gaps=gaps)


# --- triage -----------------------------------------------------------------

_BLOCK_WHERE = {
    "domain-name": "DNS resolver and web proxy", "url": "web proxy", "ipv4-addr": "firewall and proxy",
    "ipv6-addr": "firewall and proxy", "file": "EDR hash blocklist", "email-addr": "mail gateway",
}
_SEARCH_LOGS = {
    "domain-name": "DNS and proxy logs", "url": "proxy logs", "ipv4-addr": "firewall, proxy and NetFlow logs",
    "ipv6-addr": "firewall, proxy and NetFlow logs", "file": "EDR file and process events", "email-addr": "mail gateway logs",
}


def _triage_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Triage and Containment Actions", ""]
    for index, step in enumerate(c.get("steps", []), 1):
        lines.append(f"{index}. **{step['action']}** — {md(step['detail'])} _(owner: {md(step['owner'])})_")
    lines += ["", *_prose(c.get("notes", []))] if c.get("notes") else []
    lines += ["", f"_Method: steps generated from the indicator types in this report; lookback {c.get('lookback_days')} days. "
              "Add analyst steps with `report write triage_actions | <text>`._"]
    return "\n".join(lines)


@element(
    "triage_actions",
    "Triage and containment actions",
    (M, A),
    ("indicator types", "report section text"),
    markdown=_triage_md,
    description="Block, search (with a lookback window) and isolate steps generated from the indicator types present, "
    "plus analyst steps.",
    options=("lookback_days",),
)
def build_triage_actions(context: ReportContext) -> ElementResult:
    lookback = int(context.options.get("triage_actions", {}).get("lookback_days", 30))
    blockable, _excluded = detailed_indicators(context, blocking=True)
    types = sorted({row["type"] for row in blockable if row["type"] in _BLOCK_WHERE})
    steps = []
    if types:
        steps.append({"action": "Block", "detail": "; ".join(f"{t} at the {_BLOCK_WHERE[t]}" for t in types), "owner": "SOC"})
        steps.append({"action": "Search", "detail": f"the last {lookback} days of " + "; ".join(sorted({_SEARCH_LOGS[t] for t in types}))
                      + " for the listed indicators", "owner": "SOC"})
        steps.append({"action": "Isolate", "detail": "any host that resolved, connected to or executed a listed indicator, "
                      "and escalate to incident response", "owner": "Incident response"})
    notes = _texts(context, "triage_actions")
    spec = _spec("triage_actions")
    if not (steps or notes):
        return spec.result(ElementStatus.EMPTY, {"steps": [], "notes": [], "lookback_days": lookback},
                           gaps=["No indicators to act on and no analyst triage steps."])
    gaps = [] if notes else ["Only generated steps: no analyst has reviewed or added triage steps."]
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE,
                       {"steps": steps, "notes": notes, "lookback_days": lookback}, gaps=gaps)


# --- pointers to companion reports --------------------------------------------

_COMPANIONS = ("detection-signature-bundle", "threat-hunting-package", "attack-navigator-layer")


def _pointers_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("reports", [])
    lines = ["## Detection and Hunt Pointers", ""]
    if not rows:
        return "\n".join([*lines, "_No detection bundle, hunting package or Navigator layer has been issued for this investigation._"])
    lines += [f"- **{r['report_id']}** v{r['version']} ({r['status']}) — {r['type_id']}: open with `report open {r['report_id']}`" for r in rows]
    return "\n".join(lines)


@element(
    "detection_pointers",
    "Detection and hunt pointers",
    (M,),
    ("issued reports",),
    markdown=_pointers_md,
    description="Issued detection bundles, hunting packages and Navigator layers for this investigation.",
)
def build_detection_pointers(context: ReportContext) -> ElementResult:
    from pivotglass.reports.engine import list_issues

    latest: dict[str, dict[str, Any]] = {}
    for row in list_issues(context.workspace_mgr):
        if row["type_id"] in _COMPANIONS and row["report_id"] not in latest:
            latest[row["report_id"]] = row
    rows = list(latest.values())
    spec = _spec("detection_pointers")
    if not rows:
        return spec.result(ElementStatus.EMPTY, {"reports": []}, gaps=["No companion detection or hunting report is issued."])
    return spec.result(ElementStatus.COMPLETE, {"reports": rows}, citations=[f"report:{r['report_id']}" for r in rows])


# --- campaign -------------------------------------------------------------------

_ACTIVITY_FIELDS = ("first_seen", "last_seen", "x_first_seen", "x_last_seen", "firstseen", "lastseen", "date_added", "first_submission_date")


def _campaign_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Campaign Timeline", ""]
    if c.get("first") and c.get("last"):
        lines.append(f"**Dated activity:** {c['first']} to {c['last']}, from {c['dated']} record(s): dates reported by sources, and dated analyst claims.")
    else:
        lines.append("_No source reports when this activity happened._")
    lines += ["", "| Date | Event | Source |", "|---|---|---|"] if c.get("events") else []
    for event in c.get("events", []):
        lines.append(f"| {event['date']} | {md(event['event'])} | {event['source']} |")
    if c.get("collection_window"):
        lines += ["", f"_Pivotglass collected between {c['collection_window'][0]} and {c['collection_window'][1]} UTC; that is when it looked, not when the activity happened._"]
    return "\n".join(lines)


@element(
    "campaign_timeline",
    "Campaign timeline",
    (E, M),
    ("observation first- and last-seen fields", "campaign claims"),
    markdown=_campaign_md,
    description="First and last observed activity from source-reported dates (not collection times), and dated events.",
)
def build_campaign_timeline(context: ReportContext) -> ElementResult:
    events = []
    for obs in context.observations:
        blob = obs.get("observed_blob") or {}
        if not isinstance(blob, dict):
            continue
        for key in _ACTIVITY_FIELDS:
            value = str(blob.get(key) or "")[:10]
            if len(value) == 10 and value[4] == "-":  # noqa: PLR2004
                label = "first seen" if "first" in key or key == "date_added" else "last seen"
                events.append({"date": value, "event": f"{obs.get('entity_value')} {label} ({key})", "source": obs.get("source_module")})
    for row in claims(context.analysis, context.subject, "campaign") if context.subject else []:
        events.append({"date": str(row.get("object_value")), "event": row["statement"], "source": f"claim:{row['id']}"})
    events.sort(key=lambda e: e["date"])
    collected = sorted(str(o.get("fetched_at") or "")[:16].replace("T", " ") for o in context.observations if o.get("fetched_at"))
    content = {
        "events": events, "dated": len(events),
        "first": events[0]["date"] if events else None, "last": events[-1]["date"] if events else None,
        "collection_window": [collected[0], collected[-1]] if collected else None,
    }
    spec = _spec("campaign_timeline")
    if not events:
        return spec.result(ElementStatus.EMPTY, content, gaps=["No source reports activity dates; only collection times are known."])
    return spec.result(ElementStatus.COMPLETE, content, citations=[str(e["source"]) for e in events])


def _narrative_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Attack Narrative", ""]
    lines += _prose(c.get("texts", []))
    if c.get("texts"):
        lines.append("")
    lines += ["| Phase | What was observed | Techniques |", "|---|---|---|"]
    for step in c.get("steps", []):
        observed = "; ".join(md(p) for p in step["procedures"]) or "_not observed_"
        lines.append(f"| {step['phase']} | {observed} | {', '.join(step['techniques']) or '—'} |")
    lines += ["", "_Method: each phase lists accepted Kill Chain mappings and ATT&CK techniques mapped to the same evidence. "
              "An unobserved phase is a gap in the evidence, not a step that did not happen._"]
    return "\n".join(lines)


@element(
    "attack_narrative",
    "Attack narrative",
    (D, A, M),
    ("Kill Chain mappings", "ATT&CK mappings", "report section text"),
    markdown=_narrative_md,
    description="The intrusion phase by phase from accepted mappings, with the analyst's narrative; unobserved phases are "
    "stated as gaps.",
)
def build_attack_narrative(context: ReportContext) -> ElementResult:
    by_phase: dict[str, list[Any]] = defaultdict(list)
    for m in _accepted(context, "kill_chain"):
        by_phase[m.content_id].append(m)
    techniques = _accepted(context, "attack")
    steps = []
    for phase, label in KILL_CHAIN_PHASES:
        refs = {ref for m in by_phase.get(phase, []) for ref in m.evidence_refs}
        steps.append({
            "phase": label,
            "procedures": [m.basis for m in by_phase.get(phase, [])],
            "techniques": sorted({t.content_id for t in techniques if refs & set(t.evidence_refs)}),
        })
    texts = _texts(context, "attack_narrative")
    observed = [s for s in steps if s["procedures"]]
    spec = _spec("attack_narrative")
    gaps = [f"{s['phase']}: not observed." for s in steps if not s["procedures"]]
    if not texts:
        gaps.append("No narrative is written (`report write attack_narrative | <text>`).")
    if not (observed or texts):
        return spec.result(ElementStatus.EMPTY, {"steps": steps, "texts": []}, gaps=gaps)
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, {"steps": steps, "texts": texts},
                       citations=[f"mapping:{m.id}" for ms in by_phase.values() for m in ms], gaps=gaps,
                       pending_model_drafts=sum(r["draft"] for r in texts))


def _infra_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("infrastructure", [])
    lines = ["## Infrastructure", ""]
    if not rows:
        return "\n".join([*lines, "_No infrastructure collected._"])
    lines += ["| Value | Type | Role | Hosting / ASN | Connected to | Sources |", "|---|---|---|---|---|---:|"]
    for r in rows:
        value = md(render_indicator(r["value"], r["type"], output))
        linked = ", ".join(md(render_indicator(v, guess_indicator_kind(v), output)) for v in r["connected"][:4]) or "—"
        lines.append(f"| {value} | {r['type']} | {r['role'] or '—'} | {md(r['hosting'] or '—')} | {linked} | {r['sources']} |")
    return "\n".join(lines)


_HOSTING_KEYS = ("as_name", "x_as_name", "org", "x_hosting_provider", "asn", "x_asn", "isp")


@element(
    "infrastructure_breakdown",
    "Infrastructure",
    (E,),
    ("STIX objects", "role tags", "investigation graph", "observations"),
    markdown=_infra_md,
    description="Each domain, address and URL with its role tag, hosting or ASN, connections and source count.",
)
def build_infrastructure_breakdown(context: ReportContext) -> ElementResult:
    from pivotglass.reports.elements.analytical import infra_graph

    graph = infra_graph(context)
    values = {n["record_ref"]: n["value"] for n in graph["nodes"]}
    by_node = {n["id"]: n["record_ref"] for n in graph["nodes"]}
    connected: dict[str, set[str]] = defaultdict(set)
    for e in graph["edges"]:
        a, b = by_node.get(e["source"]), by_node.get(e["target"])
        if a and b:
            connected[a].add(values[b])
            connected[b].add(values[a])
    sources: dict[str, set[str]] = defaultdict(set)
    for obs in context.observations:
        sources[str(obs.get("entity_ref"))].add(str(obs.get("source_module")))
    tags = context.indicator_tags
    rows = []
    for obj in context.stix_objects:
        if obj.get("type") not in {"domain-name", "ipv4-addr", "ipv6-addr", "url"}:
            continue
        value = str(obj.get("value") or "")
        hosting = next((str(obj[k]) for k in _HOSTING_KEYS if obj.get(k)), None)
        rows.append({
            "value": value, "type": obj["type"],
            "role": ", ".join(sorted(tags.get((obj["type"], value.lower()), {}).get("role", ()))) or None,
            "hosting": hosting, "connected": sorted(connected.get(str(obj.get("id")), ())),
            "sources": len(sources.get(str(obj.get("id")), ())),
        })
    spec = _spec("infrastructure_breakdown")
    if not rows:
        return spec.result(ElementStatus.EMPTY, {"infrastructure": []}, gaps=["No domains, addresses or URLs are collected."])
    gaps = []
    if not any(r["role"] for r in rows):
        gaps.append("No infrastructure is tagged with its role (delivery, staging, C2, exfiltration).")
    if not any(r["hosting"] for r in rows):
        gaps.append("No hosting or ASN data is collected for this infrastructure.")
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, {"infrastructure": rows}, gaps=gaps)


# --- recommendations --------------------------------------------------------------


def _recommendations_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("recommendations", [])
    lines = ["## Recommendations", ""]
    if not rows:
        return "\n".join([*lines, "_None recorded. Add one with `report recommend <1-9> | <action> | <owner> | <due> | <outcome>`._"])
    lines += ["| # | Action | Owner | Due | Expected outcome |", "|---:|---|---|---|---|"]
    lines += [f"| {r.get('priority', '—')} | {md(r['action'])} | {md(r.get('owner', '—'))} | {r.get('due', '—')} | {md(r.get('outcome', '—'))} |" for r in rows]
    return "\n".join(lines)


@element(
    "recommendations",
    "Recommendations",
    (A,),
    ("report recommendations",),
    markdown=_recommendations_md,
    description="Numbered actions, each with an owner, a due date and the expected outcome, in priority order.",
)
def build_recommendations(context: ReportContext) -> ElementResult:
    rows = recommendations(context.analysis)
    spec = _spec("recommendations")
    if not rows:
        return spec.result(ElementStatus.EMPTY, {"recommendations": []}, gaps=["No recommendation is recorded."])
    return spec.result(ElementStatus.COMPLETE, {"recommendations": rows}, citations=[f"assertion:{r['id']}" for r in rows])
