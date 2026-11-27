"""Domain 3 elements: actor profile, Diamond Model, ACH, capability radar, infrastructure graph (#55).

Every builder reads ledger records, framework mappings, observations or the
governed graph through the report context. Analyst knowledge comes from
structured claims (reports/claims.py); nothing here invents a value. Methods
(diagnosticity, inconsistency tally, sensitivity, event grouping, pivot
ranking) are stated in the section they produce.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from pivotglass.reports.claims import REPORT_PREDICATES, actor_name, claims
from pivotglass.reports.contract import (
    LikelihoodTerm,
    OutputFormat,
    ProvenanceClass,
    likelihood_phrase,
    render_indicator,
)
from pivotglass.reports.elements import (
    ELEMENTS,
    ElementResult,
    ElementStatus,
    ReportContext,
    element,
)
from pivotglass.reports.elements.common import guess_indicator_kind, md
from pivotglass.reports.rubrics import CAPABILITY_AXES, LEVEL_NAMES, RUBRIC_VERSION

E, M, A, D = ProvenanceClass.EVIDENCE, ProvenanceClass.METHOD, ProvenanceClass.ANALYST, ProvenanceClass.MODEL_DRAFT
NO_ACTOR = (
    "No actor is named. Record claims about it, e.g. "
    "`analysis claim judgment actor:<name> alias <name> | <who uses it>`, then name it: `report <type> actor:<name>`."
)


# --- shared helpers ---------------------------------------------------------


def _assessed(context: ReportContext) -> dict[tuple[str, str], dict[str, Any]]:
    found: dict[tuple[str, str], dict[str, Any]] = defaultdict(dict)
    for name in ("likelihood", "confidence"):
        for row in context.analysis[name]:
            found[(str(row["target_kind"]), str(row["target_id"]))][name] = row
    return found


def _citations(context: ReportContext, kind: str, record_id: str) -> list[str]:
    return [
        f"{row['source_kind']}:{row['source_id']}"
        for row in context.analysis["evidence_links"]
        if row["target_kind"] == kind and str(row["target_id"]) == str(record_id)
    ]


def _judgment(context: ReportContext, kind: str, row: dict[str, Any], text_field: str) -> dict[str, Any]:
    assessed = _assessed(context).get((kind, str(row["id"])), {})
    likelihood = assessed.get("likelihood", {}).get("term")
    confidence = assessed.get("confidence", {}).get("level")
    return {
        "id": row["id"],
        "kind": kind,
        "statement": row[text_field],
        "value": row.get("object_value"),
        "likelihood": likelihood,
        "likelihood_phrase": likelihood_phrase(LikelihoodTerm(likelihood)) if likelihood else None,
        "confidence": confidence,
        "author": row.get("author_kind"),
        "draft": row.get("author_kind") == "model" and row.get("status") in {"proposed", "active"},
        "citations": _citations(context, kind, row["id"]),
    }


def _phrase(row: dict[str, Any]) -> str:
    likelihood = row.get("likelihood_phrase") or "likelihood not assessed"
    confidence = f"{row['confidence']} confidence" if row.get("confidence") else "confidence not assessed"
    return f"{likelihood}; {confidence}"


def _cite(row: dict[str, Any]) -> str:
    return f" <sub>[{', '.join(row['citations'])}]</sub>" if row.get("citations") else " <sub>[no citation]</sub>"


def _draft(row: dict[str, Any]) -> str:
    return "**Model draft** · " if row.get("draft") else ""


def _claim_rows(context: ReportContext, predicate: str) -> list[dict[str, Any]]:
    return [_judgment(context, "assertion", row, "statement") for row in claims(context.analysis, context.subject, predicate)]


def _observation_times(context: ReportContext) -> dict[str, str]:
    return {str(row["id"]): str(row.get("fetched_at") or "") for row in context.observations}


def _spec(element_id: str):  # noqa: ANN202 - small local accessor
    return ELEMENTS[element_id]


def _claims_section(heading: str, rows: list[dict[str, Any]], empty: str, *, value_label: str | None = None) -> str:
    lines = [f"## {heading}", ""]
    if not rows:
        return "\n".join([*lines, f"_{empty}_"])
    for row in rows:
        value = f"**{md(row['value'])}** — " if value_label and row.get("value") else ""
        lines.append(f"- {_draft(row)}{value}{md(row['statement'])} ({_phrase(row)}){_cite(row)}")
    return "\n".join(lines)


def _claims_element(context: ReportContext, element_id: str, predicates: tuple[str, ...], gap: str) -> ElementResult:
    spec = _spec(element_id)
    if context.subject is None:
        return spec.result(ElementStatus.EMPTY, {"rows": []}, gaps=[NO_ACTOR])
    rows = [row for predicate in predicates for row in _claim_rows(context, predicate)]
    gaps = [] if rows else [gap]
    gaps += [f"Claim {row['id']} has no cited evidence." for row in rows if not row["citations"]]
    status = ElementStatus.EMPTY if not rows else ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE
    return spec.result(
        status,
        {"subject": context.subject, "rows": rows},
        citations=[c for row in rows for c in row["citations"]],
        gaps=gaps,
        pending_model_drafts=sum(1 for row in rows if row["draft"]),
    )


# --- key judgments ----------------------------------------------------------


def _key_judgments_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("judgments", [])
    lines = ["## Key Judgments", ""]
    if not rows:
        return "\n".join([*lines, "_No judgments recorded. Record one with `analysis assertion judgment <text>` and assess it._"])
    for index, row in enumerate(rows, 1):
        lines.append(f"{index}. {_draft(row)}{md(row['statement'])} — *{_phrase(row)}*{_cite(row)}")
    lines += ["", "_Likelihood is how probable the judgment is; confidence is how good the evidence is._"]
    return "\n".join(lines)


@element(
    "key_judgments",
    "Key judgments",
    (A, D),
    ("analytic ledger assertions and hypotheses",),
    markdown=_key_judgments_md,
    description="Numbered judgments, each with an ICD 203 likelihood term, a separate confidence level, "
    "and citations. Model drafts stay labelled until accepted.",
)
def build_key_judgments(context: ReportContext) -> ElementResult:
    analysis = context.analysis
    rows = [
        _judgment(context, "assertion", row, "statement")
        for row in analysis["assertions"]
        # Structured claims (a predicate) appear in their own sections, not as key judgments.
        if row["assertion_type"] == "judgment" and row["status"] == "active" and not row.get("predicate")
    ]
    rows += [_judgment(context, "hypothesis", row, "statement") for row in analysis["hypotheses"] if row["status"] == "retained"]
    gaps = [
        f"Judgment {row['id']} lacks {' and '.join(k for k in ('likelihood', 'confidence') if not row[k])}."
        for row in rows
        if not (row["likelihood"] and row["confidence"])
    ]
    if not rows:
        gaps.append("No judgment or retained hypothesis is recorded.")
    status = ElementStatus.EMPTY if not rows else ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE
    return _spec("key_judgments").result(
        status,
        {"judgments": rows},
        citations=[c for row in rows for c in row["citations"]],
        gaps=gaps,
        pending_model_drafts=sum(1 for row in rows if row["draft"]),
    )


# --- actor identity and claims-backed sections ------------------------------


def _identity_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Actor Identity", ""]
    if not c.get("subject"):
        return "\n".join([*lines, f"_{NO_ACTOR}_"])
    lines.append(f"- **Tracked name:** {md(c['name'])} (`{c['subject']}`)")
    if c["mitre_group"]:
        lines.append(f"- **MITRE ATT&CK group:** {', '.join(md(r['value']) for r in c['mitre_group'])}")
    lines.append("- **Aliases:**" + ("" if c["aliases"] else " _none recorded_"))
    lines += [f"  - **{md(r['value'])}** — {md(r['statement'])}{_cite(r)}" for r in c["aliases"]]
    lines.append("- **Origin or sponsorship (judgment):**" + ("" if c["origin"] else " _not assessed_"))
    lines += [f"  - {_draft(r)}{md(r['statement'])} — *{_phrase(r)}*{_cite(r)}" for r in c["origin"]]
    return "\n".join(lines)


@element(
    "actor_identity",
    "Actor identity",
    (E, A),
    ("actor claims (alias, mitre-group, origin)",),
    markdown=_identity_md,
    description="The tracked name, every alias with who uses it, the MITRE group ID when one exists, and any "
    "origin or sponsorship assessment stated as a judgment.",
)
def build_actor_identity(context: ReportContext) -> ElementResult:
    spec = _spec("actor_identity")
    if context.subject is None:
        return spec.result(ElementStatus.EMPTY, {"subject": None}, gaps=[NO_ACTOR])
    content = {
        "subject": context.subject,
        "name": actor_name(context.subject),
        "aliases": _claim_rows(context, "alias"),
        "mitre_group": _claim_rows(context, "mitre-group"),
        "origin": _claim_rows(context, "origin"),
    }
    gaps = []
    if not content["aliases"]:
        gaps.append("No aliases are recorded; other organisations' names for this actor are unknown.")
    gaps += [f"The origin judgment {r['id']} lacks a likelihood or confidence." for r in content["origin"] if not (r["likelihood"] and r["confidence"])]
    rows = content["aliases"] + content["mitre_group"] + content["origin"]
    return spec.result(
        ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE,
        content,
        citations=[c for row in rows for c in row["citations"]],
        gaps=gaps,
        pending_model_drafts=sum(1 for row in rows if row["draft"]),
    )


@element(
    "motivation",
    "Motivation and objectives",
    (E, A),
    ("actor claims (motivation)",),
    markdown=lambda r, o: _claims_section("Motivation and Objectives", r.content.get("rows", []), "No motivation recorded.", value_label="motivation"),
    description=REPORT_PREDICATES["motivation"],
)
def build_motivation(context: ReportContext) -> ElementResult:
    return _claims_element(context, "motivation", ("motivation",), "No motivation claim is recorded.")


@element(
    "victimology",
    "Victimology",
    (E, A),
    ("actor claims (targets-sector, targets-region)",),
    markdown=lambda r, o: _claims_section("Victimology", r.content.get("rows", []), "No targeting recorded.", value_label="target"),
    description="Targeted sectors and regions, each with its basis and citations.",
)
def build_victimology(context: ReportContext) -> ElementResult:
    return _claims_element(
        context, "victimology", ("targets-sector", "targets-region"), "No sector or regional targeting is recorded."
    )


def _timeline_md(result: ElementResult, output: OutputFormat) -> str:
    rows = sorted(result.content.get("rows", []), key=lambda row: str(row.get("value") or ""))
    lines = ["## Historical Timeline", ""]
    if not rows:
        lines.append("_No dated events recorded._")
    lines += [f"- **{md(row['value'])}** — {_draft(row)}{md(row['statement'])}{_cite(row)}" for row in rows]
    window = result.content.get("collection_window")
    if window:
        lines += ["", f"_Collection in this workspace ran {window[0]} to {window[1]} UTC; that is when Pivotglass looked, not when the actor acted._"]
    return "\n".join(lines)


@element(
    "historical_timeline",
    "Historical timeline",
    (E,),
    ("actor claims (campaign)", "observations"),
    markdown=_timeline_md,
    description="Dated campaigns, tooling changes and disruptions, oldest first, each with a citation.",
)
def build_historical_timeline(context: ReportContext) -> ElementResult:
    result = _claims_element(context, "historical_timeline", ("campaign",), "No dated campaign or event is recorded.")
    bad = [r["id"] for r in result.content.get("rows", []) if not re.fullmatch(r"\d{4}(-\d{2}){0,2}", str(r.get("value") or ""))]
    times = sorted(t[:16].replace("T", " ") for t in _observation_times(context).values() if t)
    content = {**result.content, "collection_window": [times[0], times[-1]] if times else None}
    gaps = list(result.gaps) + [f"Campaign claim {i} has no YYYY, YYYY-MM or YYYY-MM-DD date." for i in bad]
    status = result.status if not bad else ElementStatus.PARTIAL
    return result.model_copy(update={"content": content, "gaps": tuple(gaps), "status": status})


def _arsenal_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Arsenal and Tooling", ""]
    for heading, key in (("Malware", "malware"), ("Tools", "tools")):
        lines.append(f"**{heading}:**" + ("" if c.get(key) else " _none recorded_"))
        lines += [f"- **{md(r['value'])}** — {_draft(r)}{md(r['statement'])}{_cite(r)}" for r in c.get(key, [])]
        lines.append("")
    files = c.get("files", [])
    if files:
        lines.append(f"**Files collected ({len(files)}):**")
        lines += [f"- `{md(f['value'])}`{' (' + md(f['name']) + ')' if f.get('name') else ''}" for f in files[:50]]
    return "\n".join(lines).rstrip()


@element(
    "arsenal",
    "Arsenal and tooling",
    (E, A),
    ("actor claims (uses-malware, uses-tool)", "file observations"),
    markdown=_arsenal_md,
    description="Malware families and dual-use tools attributed by claim, and the files collected.",
)
def build_arsenal(context: ReportContext) -> ElementResult:
    spec = _spec("arsenal")
    files = [
        {
            "value": next((str((o.get("hashes") or {})[k]) for k in ("SHA-256", "SHA-1", "MD5") if (o.get("hashes") or {}).get(k)), str(o.get("name") or "")),
            "name": o.get("name"),
        }
        for o in context.stix_objects
        if o.get("type") == "file"
    ]
    malware, tools = _claim_rows(context, "uses-malware"), _claim_rows(context, "uses-tool")
    gaps = [] if (malware or tools) else ["No malware or tool use is recorded as a claim."]
    if context.subject is None:
        gaps = [NO_ACTOR]
    status = ElementStatus.EMPTY if not (malware or tools or files) else ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE
    rows = malware + tools
    return spec.result(
        status,
        {"malware": malware, "tools": tools, "files": files},
        citations=[c for r in rows for c in r["citations"]],
        gaps=gaps,
        pending_model_drafts=sum(1 for r in rows if r["draft"]),
    )


# --- infrastructure patterns ------------------------------------------------


def _opsec_md(result: ElementResult, output: OutputFormat) -> str:
    patterns = result.content.get("patterns", [])
    lines = ["## Infrastructure and OPSEC Patterns", ""]
    if not patterns:
        return "\n".join([*lines, "_No attribute repeats across the collected infrastructure._"])
    lines += ["| Attribute | Value | Seen on | Examples |", "|---|---|---:|---|"]
    for p in patterns:
        examples = ", ".join(md(render_indicator(v, guess_indicator_kind(v), output)) for v in p["examples"])
        lines.append(f"| {p['attribute']} | {md(p['value'])} | {p['count']} | {examples} |")
    lines += ["", "_Method: an attribute is listed when at least two collected objects share it. Repetition is a lead, not proof of common control._"]
    return "\n".join(lines)


_PATTERN_FIELDS = {
    "registrar": ("registrar", "x_registrar", "x_pivotglass_registrar"),
    "name server": ("name_servers", "x_name_servers", "nameservers"),
    "ASN": ("asn", "x_asn", "number"),
    "hosting organisation": ("as_name", "x_as_name", "x_hosting_provider", "org"),
    "certificate issuer": ("issuer", "x_issuer"),
}


@element(
    "infra_opsec",
    "Infrastructure and OPSEC patterns",
    (E, M),
    ("STIX objects",),
    markdown=_opsec_md,
    description="Attributes shared by two or more collected objects (TLD, registrar, name server, ASN, "
    "hosting, certificate issuer), with how often each was seen.",
)
def build_infra_opsec(context: ReportContext) -> ElementResult:
    seen: dict[tuple[str, str], list[str]] = defaultdict(list)
    for obj in context.stix_objects:
        value = str(obj.get("value") or obj.get("name") or "")
        if obj.get("type") == "domain-name" and "." in value:
            seen[("TLD", "." + value.rsplit(".", 1)[1].lower())].append(value)
        for attribute, keys in _PATTERN_FIELDS.items():
            for key in keys:
                raw = obj.get(key)
                for item in raw if isinstance(raw, list) else [raw]:
                    if item not in (None, "", [], {}):
                        seen[(attribute, str(item).lower())].append(value or str(obj.get("id")))
    patterns = [
        {"attribute": attribute, "value": value, "count": len(set(objects)), "examples": sorted(set(objects))[:3]}
        for (attribute, value), objects in seen.items()
        if len(set(objects)) >= 2  # noqa: PLR2004
    ]
    patterns.sort(key=lambda p: (-p["count"], p["attribute"], p["value"]))
    spec = _spec("infra_opsec")
    if not patterns:
        return spec.result(ElementStatus.EMPTY, {"patterns": []}, gaps=["No infrastructure attribute repeats across collected objects."])
    return spec.result(ElementStatus.COMPLETE, {"patterns": patterns, "method": "shared attribute, two or more objects"})


# --- ATT&CK techniques ------------------------------------------------------


def _attack_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("techniques", [])
    lines = ["## ATT&CK Techniques and Procedures", ""]
    if not rows:
        return "\n".join([*lines, "_No accepted ATT&CK mapping._"])
    lines += [f"_ATT&CK Enterprise {result.content['version']}; accepted mappings only._", "", "| Tactic | Technique | Procedure | Confidence | Evidence |", "|---|---|---|---|---|"]
    for row in rows:
        lines.append(
            f"| {md(', '.join(row['tactics']) or '—')} | {row['technique_id']} {md(row['name'])} | {md(row['procedure'])} | "
            f"{row['confidence']} | {len(row['evidence'])} observation(s) |"
        )
    return "\n".join(lines)


@element(
    "attack_matrix",
    "ATT&CK techniques and procedures",
    (E,),
    ("accepted framework mappings", "pinned ATT&CK Enterprise v19.2"),
    markdown=_attack_md,
    description="Tactic, technique ID and name, and the observed procedure, from accepted mappings against the pinned release.",
)
def build_attack_matrix(context: ReportContext) -> ElementResult:
    from pivotglass.core.framework_perspectives import ATTACK_ENTERPRISE_V19_2

    version = ATTACK_ENTERPRISE_V19_2.version
    attack = [m for m in context.mappings if m.framework.value == "attack" and m.state.value == "accepted"]
    current = [m for m in attack if m.framework_version == version]
    catalog = context.attack_catalog
    rows = []
    for m in sorted(current, key=lambda m: m.content_id):
        technique = catalog.technique(m.content_id) if catalog else None
        rows.append(
            {
                "technique_id": m.content_id,
                "name": technique.name if technique else m.content_label,
                "tactics": list(technique.tactics) if technique else [],
                "procedure": m.basis,
                "confidence": m.confidence.value,
                "evidence": list(m.evidence_refs),
                "mapping_id": m.id,
            }
        )
    gaps = []
    if len(attack) > len(current):
        gaps.append(f"{len(attack) - len(current)} accepted mapping(s) on other ATT&CK versions are excluded.")
    if rows and catalog is None:
        gaps.append("The pinned ATT&CK content is not installed, so tactics are not shown (`framework manifest`).")
    if not rows:
        gaps.append("No accepted ATT&CK mapping exists for this investigation.")
    status = ElementStatus.EMPTY if not rows else ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE
    return _spec("attack_matrix").result(
        status,
        {"version": version, "techniques": rows},
        citations=[f"observation:{ref}" for row in rows for ref in row["evidence"]],
        gaps=gaps,
    )


# --- Diamond Model ----------------------------------------------------------

_VERTICES = ("adversary", "capability", "infrastructure", "victim")
_META = ("timestamp", "phase", "result", "direction", "methodology", "resources", "social-political", "technology")


def diamond_events(context: ReportContext) -> list[dict[str, Any]]:
    """Group live Diamond mappings into events: mappings that share evidence belong to one event."""

    live = [
        m for m in context.mappings
        if m.framework.value == "diamond" and m.state.value in {"accepted", "proposed"}
    ]
    parents = {m.id: m.id for m in live}

    def find(item: str) -> str:
        while parents[item] != item:
            parents[item] = parents[parents[item]]
            item = parents[item]
        return item

    by_ref: dict[str, list[str]] = defaultdict(list)
    for m in live:
        for ref in m.evidence_refs:
            by_ref[ref].append(m.id)
    for ids in by_ref.values():
        for other in ids[1:]:
            parents[find(other)] = find(ids[0])
    groups: dict[str, list[Any]] = defaultdict(list)
    for m in live:
        groups[find(m.id)].append(m)
    times = _observation_times(context)
    phases = {
        ref: m.content_label
        for m in context.mappings
        if m.framework.value == "kill_chain" and m.state.value == "accepted"
        for ref in m.evidence_refs
    }
    events = []
    for members in groups.values():
        vertices: dict[str, list[dict[str, Any]]] = defaultdict(list)
        refs = sorted({ref for m in members for ref in m.evidence_refs})
        for m in members:
            vertex, _, value = m.content_id.removeprefix("diamond:").partition(":")
            vertices[vertex].append(
                {"value": value, "basis": m.basis, "confidence": m.confidence.value, "state": m.state.value, "mapping_id": m.id}
            )
        stamps = sorted(times[r] for r in refs if times.get(r))
        meta = {name: None for name in _META}
        meta["timestamp"] = stamps[0] if stamps else None
        meta["phase"] = next((phases[r] for r in refs if r in phases), None)
        events.append(
            {
                "vertices": {v: vertices.get(v, []) for v in _VERTICES},
                "unknown_vertices": [v for v in _VERTICES if not vertices.get(v)],
                "meta_features": meta,
                "evidence": refs,
                "provisional": any(m.state.value != "accepted" for m in members),
            }
        )
    events.sort(key=lambda e: (e["meta_features"]["timestamp"] or "", e["evidence"]))
    for index, event in enumerate(events, 1):
        event["event_id"] = f"E{index}"
    return events


def _diamond_md(result: ElementResult, output: OutputFormat) -> str:
    events = result.content.get("events", [])
    lines = ["## Diamond Events", ""]
    if not events:
        return "\n".join([*lines, "_No Diamond mappings recorded. Map a vertex with `framework map diamond diamond-model-1.0 diamond:<vertex>:<value> <observation-id> | ...`._"])
    lines.append("_Method: Diamond mappings that share an evidence observation form one event. Unknown vertices stay unknown._")
    for event in events:
        flag = " · provisional (contains unaccepted mappings)" if event["provisional"] else ""
        lines += ["", f"### Event {event['event_id']}{flag}", "", "| Vertex | Value | Confidence | Basis |", "|---|---|---|---|"]
        for vertex in _VERTICES:
            assigned = event["vertices"][vertex]
            if not assigned:
                lines.append(f"| {vertex.title()} | _unknown_ | — | collect evidence for this vertex |")
            for item in assigned:
                value = render_indicator(item["value"], guess_indicator_kind(item["value"]), output)
                state = "" if item["state"] == "accepted" else f" ({item['state']})"
                lines.append(f"| {vertex.title()} | {md(value)}{state} | {item['confidence']} | {md(item['basis'])} |")
        meta = event["meta_features"]
        recorded = ", ".join(f"{k}: {md(v)}" for k, v in meta.items() if v) or "none"
        missing = ", ".join(k for k, v in meta.items() if not v)
        lines += ["", f"Meta-features recorded: {recorded}. Not recorded: {missing or 'none'}. Evidence: {len(event['evidence'])} observation(s)."]
    return "\n".join(lines)


@element(
    "diamond_events",
    "Diamond events",
    (E, A),
    ("Diamond framework mappings", "observations", "Kill Chain mappings"),
    markdown=_diamond_md,
    description="Each event's four vertices with evidence and confidence, and the meta-features "
    "(timestamp, phase, result, direction, methodology, resources, social-political, technology).",
)
def build_diamond_events(context: ReportContext) -> ElementResult:
    events = diamond_events(context)
    spec = _spec("diamond_events")
    if not events:
        return spec.result(ElementStatus.EMPTY, {"events": []}, gaps=["No Diamond Model mappings are recorded."])
    gaps = [f"Event {e['event_id']}: {', '.join(e['unknown_vertices'])} unknown." for e in events if e["unknown_vertices"]]
    gaps += [f"Event {e['event_id']} includes mappings not yet accepted." for e in events if e["provisional"]]
    return spec.result(
        ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE,
        {"events": events},
        citations=[f"observation:{r}" for e in events for r in e["evidence"]],
        gaps=gaps,
    )


def _threads_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Activity Threads", ""]
    if not c.get("links"):
        return "\n".join([*lines, "_No two events share a vertex value, so no thread links them._"])
    lines += ["| From | To | Shared vertex | Value | Link |", "|---|---|---|---|---|"]
    for link in c["links"]:
        value = render_indicator(link["value"], guess_indicator_kind(link["value"]), output)
        lines.append(f"| {link['from']} | {link['to']} | {link['vertex']} | {md(value)} | {link['kind']} |")
    lines += ["", "**Activity groups:** " + "; ".join(f"{g['id']}: {', '.join(g['events'])}" for g in c["groups"])]
    lines += ["", "_Method: events are linked when they share a vertex value, in time order. A shared value is an observed link; that the events belong to one operation is an inference._"]
    return "\n".join(lines)


@element(
    "activity_threads",
    "Activity threads",
    (E, M),
    ("Diamond events",),
    markdown=_threads_md,
    description="How events connect: the shared vertex between each pair, observed or inferred, and the resulting activity groups.",
)
def build_activity_threads(context: ReportContext) -> ElementResult:
    events = diamond_events(context)
    links = []
    for i, left in enumerate(events):
        for right in events[i + 1 :]:
            for vertex in _VERTICES:
                shared = {v["value"] for v in left["vertices"][vertex]} & {v["value"] for v in right["vertices"][vertex]}
                links += [
                    {"from": left["event_id"], "to": right["event_id"], "vertex": vertex, "value": value, "kind": "observed shared value"}
                    for value in sorted(shared)
                ]
    groups: list[set[str]] = [{e["event_id"]} for e in events]
    for link in links:
        a = next(g for g in groups if link["from"] in g)
        b = next(g for g in groups if link["to"] in g)
        if a is not b:
            a |= b
            groups.remove(b)
    group_rows = [{"id": f"AG{n}", "events": sorted(g, key=lambda e: int(e[1:]))} for n, g in enumerate(groups, 1)]
    spec = _spec("activity_threads")
    if len(events) < 2:  # noqa: PLR2004
        return spec.result(ElementStatus.EMPTY, {"links": [], "groups": group_rows}, gaps=["Fewer than two Diamond events exist, so there is no thread."])
    return spec.result(ElementStatus.COMPLETE if links else ElementStatus.PARTIAL, {"links": links, "groups": group_rows},
                       gaps=[] if links else ["No events share a vertex value."])


# --- ACH --------------------------------------------------------------------

_DIAGNOSTIC_WEIGHT = {"high": 2.0, "medium": 1.0, "low": 0.0}


def _hypotheses(context: ReportContext) -> list[dict[str, Any]]:
    rows = [row for row in context.analysis["hypotheses"] if row["status"] != "rejected"]
    rows.sort(key=lambda row: (str(row.get("created_at") or ""), str(row["id"])))
    return [{**_judgment(context, "hypothesis", row, "statement"), "label": f"H{i}", "status": row["status"]} for i, row in enumerate(rows, 1)]


def ach_matrix(context: ReportContext) -> dict[str, Any]:
    """Evidence x hypothesis matrix from recorded evidence links, with diagnosticity and tallies."""

    hypotheses = _hypotheses(context)
    ids = {h["id"]: h["label"] for h in hypotheses}
    labels = {
        **{("observation", str(o["id"])): str(o.get("entity_value") or o["id"]) for o in context.observations},
        **{("assertion", str(a["id"])): str(a["statement"]) for a in context.analysis["assertions"]},
    }
    scores: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for link in context.analysis["evidence_links"]:
        if link["target_kind"] == "hypothesis" and str(link["target_id"]) in ids:
            mark = "C" if link["stance"] == "supports" else "I"
            scores[(link["source_kind"], str(link["source_id"]))][ids[str(link["target_id"])]].add(mark)
    rows = []
    for index, (key, by_h) in enumerate(sorted(scores.items()), 1):
        cells = {h["label"]: ("C/I" if len(by_h.get(h["label"], ())) > 1 else next(iter(by_h.get(h["label"], {"—"})))) for h in hypotheses}
        marks = {v for v in cells.values() if v in {"C", "I"}}
        assessed = [v for v in cells.values() if v != "—"]
        diagnosticity = "high" if marks == {"C", "I"} else "low" if len(assessed) == len(hypotheses) and len(marks) == 1 else "medium"
        rows.append(
            {
                "id": f"E{index}", "source": f"{key[0]}:{key[1]}", "evidence": labels.get(key, key[1]),
                "rating": "F6", "diagnosticity": diagnosticity, "scores": cells,
            }
        )
    tally = {
        h["label"]: sum(_DIAGNOSTIC_WEIGHT[r["diagnosticity"]] for r in rows if r["scores"][h["label"]] in {"I", "C/I"})
        for h in hypotheses
    }
    return {"hypotheses": hypotheses, "rows": rows, "tally": tally}


def _least_inconsistent(rows: list[dict[str, Any]], labels: list[str]) -> list[str]:
    tally = {h: sum(_DIAGNOSTIC_WEIGHT[r["diagnosticity"]] for r in rows if r["scores"][h] in {"I", "C/I"}) for h in labels}
    best = min(tally.values(), default=0)
    return sorted(h for h, v in tally.items() if v == best)


def _ach_hyp_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("hypotheses", [])
    lines = ["## Competing Hypotheses", ""]
    lines += [f"- **{h['label']}** {_draft(h)}{md(h['statement'])} ({h['status']}; {_phrase(h)})" for h in rows]
    if not rows:
        lines.append("_No hypotheses recorded._")
    lines += ["", "_Check: the set should include an unattributed or new actor and a deception (false-flag) hypothesis._"]
    return "\n".join(lines)


@element(
    "ach_hypotheses",
    "Competing hypotheses",
    (A,),
    ("analytic ledger hypotheses",),
    markdown=_ach_hyp_md,
    description="The full hypothesis set, including an unattributed actor and a deception hypothesis, each falsifiable.",
)
def build_ach_hypotheses(context: ReportContext) -> ElementResult:
    rows = _hypotheses(context)
    spec = _spec("ach_hypotheses")
    gaps = [] if len(rows) >= 2 else ["ACH needs at least two competing hypotheses."]  # noqa: PLR2004
    status = ElementStatus.EMPTY if not rows else ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE
    return spec.result(status, {"hypotheses": rows}, citations=[f"hypothesis:{h['id']}" for h in rows], gaps=gaps,
                       pending_model_drafts=sum(1 for h in rows if h["draft"] and h["status"] == "proposed"))


def _ach_matrix_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    labels = [h["label"] for h in c.get("hypotheses", [])]
    lines = ["## ACH Matrix", ""]
    if not c.get("rows"):
        return "\n".join([*lines, "_No evidence is linked to the hypotheses. Link it with `analysis link ... supports|contradicts ... | <rationale>`._"])
    lines += [
        "| ID | Evidence | Rating | Diagnosticity | " + " | ".join(labels) + " |",
        "|---|---|---|---|" + "---|" * len(labels),
    ]
    for r in c["rows"]:
        evidence = render_indicator(r["evidence"], guess_indicator_kind(r["evidence"]), output)
        lines.append(f"| {r['id']} | {md(evidence)} | {r['rating']} | {r['diagnosticity']} | " + " | ".join(r["scores"][h] for h in labels) + " |")
    lines.append("| | **Weighted inconsistency** | | | " + " | ".join(f"**{c['tally'][h]:g}**" for h in labels) + " |")
    lines += [
        "",
        "_C consistent, I inconsistent, C/I both recorded, — not assessed. Diagnosticity comes from the spread of scores "
        "across hypotheses: high when the row has both C and I, low when every hypothesis scores alike, medium otherwise. "
        "Inconsistencies weigh 2 (high), 1 (medium) or 0 (low). Ratings are F6 until sources are rated._",
    ]
    return "\n".join(lines)


@element(
    "ach_matrix",
    "ACH matrix",
    (A, M),
    ("analytic ledger evidence links",),
    markdown=_ach_matrix_md,
    description="Evidence rows with source rating, diagnosticity from the spread of scores, a consistency score "
    "per hypothesis, and the weighted inconsistency tally.",
)
def build_ach_matrix(context: ReportContext) -> ElementResult:
    matrix = ach_matrix(context)
    spec = _spec("ach_matrix")
    if not matrix["rows"]:
        return spec.result(ElementStatus.EMPTY, matrix, gaps=["No evidence is linked to the hypotheses."])
    gaps = ["Evidence sources are not rated (shown as F6)."]
    if all(r["diagnosticity"] != "high" for r in matrix["rows"]):
        gaps.append("No evidence discriminates between hypotheses (no high-diagnosticity row).")
    return spec.result(ElementStatus.PARTIAL, matrix, citations=[r["source"] for r in matrix["rows"]], gaps=gaps)


def _ach_judgment_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## ACH Judgment", ""]
    if not c.get("leaders"):
        return "\n".join([*lines, "_No judgment: the matrix is empty._"])
    for h in c["leaders_detail"]:
        lines.append(f"- **Least inconsistent:** {h['label']} — {md(h['statement'])} (*{_phrase(h)}*)")
    if len(c["leaders"]) > 1:
        lines.append("- **Tie:** the evidence does not separate these hypotheses.")
    for row in c["rejected"]:
        lines.append(f"- **{row['label']}** scores {row['tally']:g} weighted inconsistencies.")
    lines += ["", "**Sensitivity check:**", ""]
    if c["sensitive_rows"]:
        lines += [f"- Removing {r} would change the result or make it a tie; the judgment rests on it." for r in c["sensitive_rows"]]
    else:
        lines.append("- No single evidence row changes the result if removed.")
    if c.get("recorded"):
        rec = c["recorded"]
        lines += ["", f"**Recorded ACH run ({rec['status']}, analyst disposition {rec['disposition']}):** least inconsistent "
                  f"{md(rec['least_inconsistent'])}; sensitivity: {md(rec['sensitivity'])}"]
        if c.get("disagreement"):
            lines.append(f"- _The recorded run and the computed tally disagree: {md(c['disagreement'])}_")
    return "\n".join(lines)


@element(
    "ach_judgment",
    "ACH judgment",
    (A, M),
    ("ACH matrix", "analysis_of_competing_hypotheses method runs"),
    markdown=_ach_judgment_md,
    description="The least-inconsistent hypothesis with likelihood and confidence, the tallies of the others, a "
    "sensitivity check, and the recorded ACH run when one exists.",
)
def build_ach_judgment(context: ReportContext) -> ElementResult:
    matrix = ach_matrix(context)
    labels = [h["label"] for h in matrix["hypotheses"]]
    spec = _spec("ach_judgment")
    if not matrix["rows"] or len(labels) < 2:  # noqa: PLR2004
        return spec.result(ElementStatus.EMPTY, {"leaders": []}, gaps=["No ACH judgment: fewer than two hypotheses or no linked evidence."])
    leaders = _least_inconsistent(matrix["rows"], labels)
    sensitive = [
        r["id"] for r in matrix["rows"]
        if _least_inconsistent([x for x in matrix["rows"] if x is not r], labels) != leaders
    ]
    by_label = {h["label"]: h for h in matrix["hypotheses"]}
    runs = [r for r in context.analysis["method_runs"] if r["technique"] == "analysis_of_competing_hypotheses"]
    recorded = None
    disagreement = None
    if runs:
        run = runs[-1]
        out = run.get("output_blob") or {}
        recorded = {
            "id": run["id"], "status": run["status"], "disposition": run["analyst_disposition"],
            "least_inconsistent": str(out.get("least_inconsistent", "not recorded")),
            "sensitivity": str(out.get("sensitivity", "not recorded")),
        }
        named = {h for h in labels if h in recorded["least_inconsistent"]} | {
            by_label[h]["label"] for h in labels if str(by_label[h]["id"]) in recorded["least_inconsistent"]
        }
        if named and named != set(leaders):
            disagreement = f"run names {', '.join(sorted(named))}; tally gives {', '.join(leaders)}"
    gaps = []
    detail = [by_label[h] for h in leaders]
    gaps += [f"{h['label']} has no likelihood or confidence assessment." for h in detail if not (h["likelihood"] and h["confidence"])]
    if len(leaders) > 1:
        gaps.append("The evidence does not separate the leading hypotheses.")
    if disagreement:
        gaps.append(f"The recorded ACH run disagrees with the computed tally ({disagreement}).")
    content = {
        "leaders": leaders,
        "leaders_detail": detail,
        "rejected": [{"label": h, "tally": matrix["tally"][h]} for h in labels if h not in leaders],
        "sensitive_rows": sensitive,
        "recorded": recorded,
        "disagreement": disagreement,
    }
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, content,
                       citations=[r["source"] for r in matrix["rows"]], gaps=gaps)


def _signposts_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("signposts", [])
    lines = ["## Signposts", ""]
    if not rows:
        return "\n".join([*lines, "_No signposts recorded. Add one with `analysis signpost <text>`._"])
    lines += [f"- **{r['status'].upper()}** — {md(r['statement'])} <sub>[{r['source']}]</sub>" for r in rows]
    return "\n".join(lines)


@element(
    "signposts",
    "Signposts",
    (A,),
    ("signpost lifecycle items", "indicators_and_signposts method runs"),
    markdown=_signposts_md,
    description="Observable future developments that would raise or lower a judgment.",
)
def build_signposts(context: ReportContext) -> ElementResult:
    investigation = context.investigation
    rows = [
        {"statement": i.get("statement"), "status": i["status"], "source": f"lifecycle:{i['id']}"}
        for i in context.analysis["lifecycle_items"]
        if i["item_type"] == "signpost" and investigation and i["investigation_id"] == investigation["id"]
    ]
    for run in context.analysis["method_runs"]:
        if run["technique"] == "indicators_and_signposts":
            for text in (run.get("output_blob") or {}).get("signposts", []):
                rows.append({"statement": str(text), "status": run["analyst_disposition"], "source": f"method_run:{run['id']}"})
    spec = _spec("signposts")
    if not rows:
        return spec.result(ElementStatus.EMPTY, {"signposts": []}, gaps=["No signposts are recorded."])
    return spec.result(ElementStatus.COMPLETE, {"signposts": rows}, citations=[r["source"] for r in rows])


# --- capability -------------------------------------------------------------


def _rubric_md(result: ElementResult, output: OutputFormat) -> str:
    lines = ["## Capability Rubric", "", f"_{result.content['version']}. Score each axis with `analysis claim judgment actor:<name> capability:<axis> <1-5> | <basis>`._", ""]
    for axis in result.content["axes"]:
        lines += [f"**{axis['title']}** (`{axis['id']}`)", ""]
        lines += [f"{level}. *{LEVEL_NAMES[int(level)]}* — {text}" for level, text in axis["levels"].items()]
        lines.append("")
    return "\n".join(lines).rstrip()


@element(
    "capability_rubric",
    "Capability rubric",
    (M,),
    ("reports/rubrics.py",),
    markdown=_rubric_md,
    description="The axes and the definition of each level 1 to 5, so scores are comparable.",
)
def build_capability_rubric(context: ReportContext) -> ElementResult:
    axes = [{"id": key, "title": title, "levels": {str(k): v for k, v in levels.items()}} for key, (title, levels) in CAPABILITY_AXES.items()]
    return _spec("capability_rubric").result(ElementStatus.COMPLETE, {"version": RUBRIC_VERSION, "axes": axes})


def _radar_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("scores", [])
    lines = ["## Capability Scores", ""]
    if not result.content.get("subject"):
        return "\n".join([*lines, f"_{NO_ACTOR}_"])
    lines += ["| Axis | Score | Level | Confidence | Basis |", "|---|---:|---|---|---|"]
    for r in rows:
        if r["score"] is None:
            lines.append(f"| {r['title']} | — | not scored | — | — |")
        else:
            lines.append(f"| {r['title']} | {r['score']} | {LEVEL_NAMES[r['score']]} | {r['confidence'] or 'not assessed'} | {_draft(r)}{md(r['statement'])}{_cite(r)} |")
    lines += ["", "_The JSON rendering carries these scores for the radar chart._"]
    return "\n".join(lines)


@element(
    "capability_radar",
    "Capability scores",
    (A,),
    ("actor claims (capability:<axis>)", "capability rubric"),
    markdown=_radar_md,
    description="One score per rubric axis with its citations and confidence, for a radar chart and a table.",
)
def build_capability_radar(context: ReportContext) -> ElementResult:
    spec = _spec("capability_radar")
    if context.subject is None:
        return spec.result(ElementStatus.EMPTY, {"subject": None, "scores": []}, gaps=[NO_ACTOR])
    latest: dict[str, dict[str, Any]] = {}
    invalid = []
    for row in _claim_rows(context, "capability:"):
        axis = next((a["predicate"] for a in context.analysis["assertions"] if a["id"] == row["id"]), "").removeprefix("capability:")
        try:
            score = int(str(row["value"]).strip())
        except ValueError:
            score = 0
        if axis not in CAPABILITY_AXES or not 1 <= score <= 5:  # noqa: PLR2004
            invalid.append(row["id"])
            continue
        latest[axis] = {**row, "score": score}
    scores = []
    for axis, (title, _levels) in CAPABILITY_AXES.items():
        row = latest.get(axis)
        scores.append({"axis": axis, "title": title, "score": row["score"] if row else None, **({k: row[k] for k in ("statement", "confidence", "citations", "draft", "id")} if row else {})})
    gaps = [f"{s['title']} is not scored." for s in scores if s["score"] is None]
    gaps += [f"{s['title']}: the score cites no evidence." for s in scores if s["score"] and not s.get("citations")]
    gaps += [f"Claim {i} is not a rubric axis with a score of 1-5." for i in invalid]
    scored = [s for s in scores if s["score"]]
    status = ElementStatus.EMPTY if not scored else ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE
    return spec.result(
        status, {"subject": context.subject, "rubric": RUBRIC_VERSION, "scores": scores},
        citations=[c for s in scored for c in s.get("citations", [])], gaps=gaps,
        pending_model_drafts=sum(1 for s in scored if s.get("draft")),
    )


# --- infrastructure graph ---------------------------------------------------


def infra_graph(context: ReportContext) -> dict[str, Any]:
    graph = context.graph
    times = _observation_times(context)
    if graph is None:
        return {"nodes": [], "edges": [], "clusters": []}
    nodes = [
        {"id": n.id, "type": n.kind, "value": n.label, "record_ref": n.record_ref}
        for n in graph.nodes if n.layer == "entity"
    ]
    node_ids = {n["id"] for n in nodes}
    edges = []
    for e in graph.edges:
        if e.layer != "entity" or e.source not in node_ids or e.target not in node_ids:
            continue
        stamps = sorted(times[r] for r in e.provenance_refs if times.get(r))
        edges.append(
            {
                "id": e.id, "source": e.source, "target": e.target, "relationship": e.relationship,
                "truth_kind": e.truth_kind, "evidence": list(e.provenance_refs),
                "first_seen": stamps[0] if stamps else None, "last_seen": stamps[-1] if stamps else None,
            }
        )
    record_to_node = {n["record_ref"]: n["id"] for n in nodes}
    clusters = [
        {
            "id": c.id, "nodes": [record_to_node.get(e.reference, e.reference) for e in c.entities],
            "first_observed": c.first_observed, "last_observed": c.last_observed,
            "truth_classes": list(c.truth_classes), "sources": len(c.provenance_sources),
        }
        for c in context.clusters
    ]
    return {"nodes": nodes, "edges": edges, "clusters": clusters}


def _graph_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Infrastructure Graph", ""]
    if not c.get("nodes"):
        return "\n".join([*lines, "_The graph is empty._"])
    multi = [k for k in c["clusters"] if len(k["nodes"]) > 1]
    lines.append(
        f"{len(c['nodes'])} entities, {len(c['edges'])} connections, {len(c['clusters'])} clusters "
        f"({len(multi)} with more than one entity). _Method: clusters are connected components of admitted entity edges; "
        "a cluster is a navigation summary, not proof of common control._"
    )
    values = {n["id"]: n for n in c["nodes"]}

    def label(node_id: str) -> str:
        n = values.get(node_id)
        return md(render_indicator(n["value"], n["type"], output)) if n else node_id

    if c["edges"]:
        lines += ["", "| From | Relationship | To | Truth | First seen | Last seen | Evidence |", "|---|---|---|---|---|---|---:|"]
        for e in c["edges"][:200]:
            lines.append(
                f"| {label(e['source'])} | {e['relationship']} | {label(e['target'])} | {e['truth_kind']} | "
                f"{(e['first_seen'] or '—')[:16]} | {(e['last_seen'] or '—')[:16]} | {len(e['evidence'])} |"
            )
    if multi:
        lines += ["", "**Clusters:**", ""]
        lines += [f"- `{k['id']}` — {len(k['nodes'])} entities: {', '.join(label(n) for n in k['nodes'][:8])}" for k in multi[:50]]
    lines += ["", "_Truth: observed (a source reported it), property (a shared typed property), or an analyst judgment._"]
    return "\n".join(lines)


@element(
    "infra_graph",
    "Infrastructure graph",
    (E, M),
    ("investigation graph", "evidence clusters", "observations"),
    markdown=_graph_md,
    description="Entities, connections with truth class, time bounds and evidence, and cluster boundaries with the method.",
)
def build_infra_graph(context: ReportContext) -> ElementResult:
    graph = infra_graph(context)
    spec = _spec("infra_graph")
    if not graph["nodes"]:
        return spec.result(ElementStatus.EMPTY, graph, gaps=["The investigation graph has no entities."])
    gaps = []
    if not graph["edges"]:
        gaps.append("No connections between entities are recorded; every entity is its own cluster.")
    undated = sum(1 for e in graph["edges"] if not e["first_seen"])
    if undated:
        gaps.append(f"{undated} connection(s) have no observation time, so their time bounds are unknown.")
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, graph,
                       citations=sorted({f"observation:{r}" for e in graph["edges"] for r in e["evidence"]}), gaps=gaps)


def _pivots_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("pivots", [])
    lines = ["## Pivot Points", ""]
    if not rows:
        return "\n".join([*lines, "_No entity joins two or more others._"])
    lines += ["| Pivot | Type | Joins | Relationships |", "|---|---|---:|---|"]
    lines += [
        f"| {md(render_indicator(r['value'], r['type'], output))} | {r['type']} | {r['degree']} | {md(', '.join(r['relationships']))} |"
        for r in rows
    ]
    lines += ["", "_Method: entities ranked by how many other entities they connect to. A highly shared value (a large host or CDN) can join unrelated activity; check before pivoting._"]
    return "\n".join(lines)


@element(
    "pivot_points",
    "Pivot points",
    (M,),
    ("investigation graph",),
    markdown=_pivots_md,
    description="Entities that join two or more others, ranked by how many they join, with the relationships involved.",
)
def build_pivot_points(context: ReportContext) -> ElementResult:
    graph = infra_graph(context)
    neighbours: dict[str, set[str]] = defaultdict(set)
    relationships: dict[str, Counter[str]] = defaultdict(Counter)
    for e in graph["edges"]:
        for a, b in ((e["source"], e["target"]), (e["target"], e["source"])):
            neighbours[a].add(b)
            relationships[a][e["relationship"]] += 1
    nodes = {n["id"]: n for n in graph["nodes"]}
    rows = [
        {"id": n, "value": nodes[n]["value"], "type": nodes[n]["type"], "degree": len(others), "relationships": sorted(relationships[n])}
        for n, others in neighbours.items()
        if len(others) >= 2 and n in nodes  # noqa: PLR2004
    ]
    rows.sort(key=lambda r: (-r["degree"], r["value"]))
    spec = _spec("pivot_points")
    if not rows:
        return spec.result(ElementStatus.EMPTY, {"pivots": []}, gaps=["No entity connects two or more others."])
    return spec.result(ElementStatus.COMPLETE, {"pivots": rows[:50], "method": "degree in the admitted entity graph"})


__all__ = ["ach_matrix", "diamond_events", "infra_graph"]


# --- Mermaid (types 8 and 11) -----------------------------------------------


def _mermaid_label(text: str) -> str:
    return '"' + str(text).replace('"', "'").replace("\n", " ")[:80] + '"'


def mermaid_infra_graph(content: dict[str, Any]) -> str:
    """The infrastructure graph as a Mermaid flowchart, one subgraph per multi-entity cluster. Defanged."""

    ids = {n["id"]: f"n{i}" for i, n in enumerate(content.get("nodes", []))}
    nodes = {n["id"]: n for n in content.get("nodes", [])}
    lines = ["flowchart LR"]
    clustered: set[str] = set()
    for index, cluster in enumerate(k for k in content.get("clusters", []) if len(k["nodes"]) > 1):
        lines.append(f"  subgraph c{index}[{_mermaid_label(f'Cluster {index + 1}')}]")
        for node in cluster["nodes"]:
            if node in nodes:
                n = nodes[node]
                lines.append(f"    {ids[node]}[{_mermaid_label(render_indicator(n['value'], n['type'], OutputFormat.MERMAID))}]")
                clustered.add(node)
        lines.append("  end")
    for node_id, n in nodes.items():
        if node_id not in clustered:
            lines.append(f"  {ids[node_id]}[{_mermaid_label(render_indicator(n['value'], n['type'], OutputFormat.MERMAID))}]")
    for e in content.get("edges", []):
        if e["source"] in ids and e["target"] in ids:
            style = "-->" if e["truth_kind"] == "observed" else "-.->"
            lines.append(f"  {ids[e['source']]} {style}|{_mermaid_label(e['relationship'])}| {ids[e['target']]}")
    return "\n".join(lines) + "\n"


def mermaid_diamond(events: list[dict[str, Any]], links: list[dict[str, Any]]) -> str:
    """Each Diamond event as its four vertices; thread links between events. Defanged; unknown vertices dashed."""

    lines = ["flowchart TB"]
    for event in events:
        eid = event["event_id"]
        lines.append(f"  subgraph {eid}[{_mermaid_label('Event ' + eid)}]")
        for vertex in _VERTICES:
            values = event["vertices"][vertex]
            text = "; ".join(render_indicator(v["value"], guess_indicator_kind(v["value"]), OutputFormat.MERMAID) for v in values) or "unknown"
            lines.append(f"    {eid}_{vertex}[{_mermaid_label(f'{vertex.title()}: {text}')}]")
        lines += [
            f"    {eid}_adversary --- {eid}_capability",
            f"    {eid}_capability --- {eid}_victim",
            f"    {eid}_victim --- {eid}_infrastructure",
            f"    {eid}_infrastructure --- {eid}_adversary",
            "  end",
        ]
        for vertex in event["unknown_vertices"]:
            lines.append(f"  style {eid}_{vertex} stroke-dasharray: 4 4")
    for link in links:
        lines.append(f"  {link['from']}_{link['vertex']} ==>|{_mermaid_label('shared ' + link['vertex'])}| {link['to']}_{link['vertex']}")
    return "\n".join(lines) + "\n"
