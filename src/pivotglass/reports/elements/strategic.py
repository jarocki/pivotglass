"""Domain 1 elements: executive briefing, landscape forecast, risk assessment (#53).

Mostly analyst judgment recorded with `report write|risk|scenario|risk-scenario`,
set beside the evidence Pivotglass holds: actor claims, mappings over the
collection period, and external exposure matched to the organisation's assets.
"""

from __future__ import annotations

import ipaddress
from collections import defaultdict
from statistics import mean
from typing import Any

from pivotglass.reports.claims import actor_subjects, claims
from pivotglass.reports.contract import (
    SEVERITY_DEFINITIONS,
    LikelihoodTerm,
    OutputFormat,
    ProvenanceClass,
    Severity,
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
from pivotglass.reports.elements.common import md
from pivotglass.reports.rubrics import LEVEL_NAMES
from pivotglass.reports.sections import overall_risk, risk_scenarios, scenarios, section_texts

E, M, A, D, O = (  # noqa: E741
    ProvenanceClass.EVIDENCE, ProvenanceClass.METHOD, ProvenanceClass.ANALYST, ProvenanceClass.MODEL_DRAFT, ProvenanceClass.ORG_INPUT,
)


def _spec(element_id: str):  # noqa: ANN202
    return ELEMENTS[element_id]


def _texts(context: ReportContext, section: str) -> list[dict[str, Any]]:
    return [{"id": r["id"], "text": r["statement"], "author": r.get("author_kind"), "draft": r.get("author_kind") == "model"}
            for r in section_texts(context.analysis, section)]


def _prose_element(context: ReportContext, element_id: str, section: str, hint: str) -> ElementResult:
    rows = _texts(context, section)
    spec = _spec(element_id)
    if not rows:
        return spec.result(ElementStatus.EMPTY, {"texts": []}, gaps=[f"Not written (`report write {section} | {hint}`)."])
    return spec.result(ElementStatus.COMPLETE, {"texts": rows}, citations=[f"assertion:{r['id']}" for r in rows],
                       pending_model_drafts=sum(r["draft"] for r in rows))


def _prose_md(heading: str):  # noqa: ANN202
    def render(result: ElementResult, output: OutputFormat) -> str:
        rows = result.content.get("texts", [])
        lines = [f"## {heading}", ""]
        lines += [f"{'**Model draft** · ' if r['draft'] else ''}{r['text']} <sub>— {r['author']}</sub>" for r in rows] or ["_Not written yet._"]
        return "\n".join(lines)

    return render


@element("bluf", "Bottom line up front", (D, A), ("report section text",), markdown=_prose_md("Bottom Line Up Front"),
         description="At most two sentences: what happened or is expected, whether we are affected, and the decision needed.")
def build_bluf(context: ReportContext) -> ElementResult:
    result = _prose_element(context, "bluf", "bluf", "<two sentences: what, whether we are affected, the decision>")
    long = [r for r in result.content.get("texts", []) if r["text"].count(". ") >= 2]  # noqa: PLR2004
    if long:
        return result.model_copy(update={"status": ElementStatus.PARTIAL, "gaps": (*result.gaps, "The BLUF runs past two sentences.")})
    return result


@element("situational_overview", "Situational overview", (D, A), ("report section text",), markdown=_prose_md("Situational Overview"),
         description="The actor, event or vulnerability in non-technical terms, with what is known and what is not.")
def build_situational_overview(context: ReportContext) -> ElementResult:
    return _prose_element(context, "situational_overview", "situational_overview", "<the situation in business terms>")


def _risk_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Overall Risk", ""]
    if not c:
        return "\n".join([*lines, "_No overall risk recorded (`report risk <severity> <confidence> | <reason>`)._"])
    lines.append(f"**{c['severity'].title()}** ({SEVERITY_DEFINITIONS[Severity(c['severity'])]}) — {md(c['text'])} *{c['confidence']} confidence*")
    return "\n".join(lines)


@element("risk_rating", "Overall risk", (A,), ("report risk record",), markdown=_risk_md,
         description="The overall risk to the organisation on the severity scale, with the reason and a separate confidence.")
def build_risk_rating(context: ReportContext) -> ElementResult:
    row = overall_risk(context.analysis)
    spec = _spec("risk_rating")
    if row is None:
        return spec.result(ElementStatus.EMPTY, {}, gaps=["No overall risk is recorded."])
    return spec.result(ElementStatus.COMPLETE, row, citations=[f"assertion:{row['id']}"])


# --- landscape ---------------------------------------------------------------------


def _period_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Period and Coverage", ""]
    if c.get("window"):
        lines.append(f"**Collection window:** {c['window'][0]} to {c['window'][1]} UTC, {c['observations']} observations from {len(c['sources'])} source(s).")
        lines.append("**Sources:** " + ", ".join(f"{s} ({n})" for s, n in c["sources"].items()))
    lines += [f"{r['text']} <sub>— {r['author']}</sub>" for r in c.get("texts", [])]
    lines += ["", "_Pivotglass collection sees infrastructure, indicators and feeds. It does not see geopolitics, the wider "
              "market or other organisations' incidents; forecasts here rest on analyst judgment._"]
    return "\n".join(lines)


@element("period_scope", "Period and coverage", (M, A), ("observations", "report section text"), markdown=_period_md,
         description="The reporting window, the sources collected in it and what they cannot see.")
def build_period_scope(context: ReportContext) -> ElementResult:
    times = sorted(str(o.get("fetched_at") or "")[:10] for o in context.observations if o.get("fetched_at"))
    sources: dict[str, int] = defaultdict(int)
    for o in context.observations:
        sources[str(o.get("source_module"))] += 1
    content = {"window": [times[0], times[-1]] if times else None, "observations": len(context.observations),
               "sources": dict(sorted(sources.items())), "texts": _texts(context, "period_scope")}
    spec = _spec("period_scope")
    if not times:
        return spec.result(ElementStatus.EMPTY, content, gaps=["Nothing was collected, so there is no period."])
    gaps = [] if content["texts"] else ["The analyst has not stated the reporting period (`report write period_scope | <period and scope>`)."]
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, content, gaps=gaps)


def _technique_times(context: ReportContext) -> list[dict[str, Any]]:
    seen = {str(o["id"]): str(o.get("fetched_at") or "")[:10] for o in context.observations}
    rows = []
    for m in context.mappings:
        if m.framework.value == "attack" and m.state.value == "accepted":
            dates = sorted(seen[r] for r in m.evidence_refs if seen.get(r))
            rows.append({"technique": m.content_id, "name": m.content_label, "first": dates[0] if dates else None, "evidence": len(m.evidence_refs)})
    return sorted(rows, key=lambda r: (r["first"] or "", r["technique"]))


def _trends_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Macro Trends", ""]
    lines += [f"{'**Model draft** · ' if r['draft'] else ''}{r['text']} <sub>— {r['author']}</sub>" for r in c.get("texts", [])]
    if c.get("counts"):
        lines += ["", "**In this collection:** " + "; ".join(f"{k}: {v}" for k, v in c["counts"].items())]
    if not (c.get("texts") or c.get("counts")):
        lines.append("_No trends written (`report write macro_trends | <shift and its support>`)._")
    return "\n".join(lines)


@element("macro_trends", "Macro trends", (A, D, E), ("report section text", "observations", "ATT&CK mappings"), markdown=_trends_md,
         description="Shifts in motivation, initial access and tooling over the period, with the counts in this collection.")
def build_macro_trends(context: ReportContext) -> ElementResult:
    counts: dict[str, int] = defaultdict(int)
    for row in context.stix_objects:
        counts[str(row.get("type"))] += 1
    counts["ATT&CK techniques (accepted)"] = len(_technique_times(context))
    texts = _texts(context, "macro_trends")
    spec = _spec("macro_trends")
    if not texts:
        return spec.result(ElementStatus.EMPTY, {"texts": [], "counts": dict(counts)}, gaps=["No trend analysis is written."])
    return spec.result(ElementStatus.COMPLETE, {"texts": texts, "counts": dict(counts)}, pending_model_drafts=sum(t["draft"] for t in texts))


def _emerging_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("techniques", [])
    lines = ["## Emerging Techniques", ""]
    lines += [f"- {r['first'] or 'date unknown'}: **{r['technique']}** {md(r['name'])} ({r['evidence']} observation(s))" for r in rows] or ["_No accepted technique._"]
    return "\n".join(lines)


@element("emerging_ttps", "Emerging techniques", (A, E), ("ATT&CK mappings", "observations"), markdown=_emerging_md,
         description="Accepted techniques in order of first observation in this collection.")
def build_emerging_ttps(context: ReportContext) -> ElementResult:
    rows = _technique_times(context)
    spec = _spec("emerging_ttps")
    if not rows:
        return spec.result(ElementStatus.EMPTY, {"techniques": []}, gaps=["No accepted ATT&CK mapping."])
    return spec.result(ElementStatus.COMPLETE, {"techniques": rows},
                       gaps=["First seen is when Pivotglass collected the evidence, not when the technique emerged."])


def _profile(context: ReportContext) -> Any:
    from pivotglass.reports.org import OrgInputs

    return OrgInputs(context.workspace_mgr).profile()


def _sector_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Sector and Regional Targeting", ""]
    if not c.get("rows"):
        return "\n".join([*lines, "_No targeting recorded for any actor._"])
    lines += ["| Actor | Targets | Kind | Ours | Basis |", "|---|---|---|---|---|"]
    lines += [f"| {md(r['actor'])} | {md(r['value'])} | {r['kind']} | {'**yes**' if r['ours'] else 'no' if c['profile'] else '—'} | {md(r['basis'])} |" for r in c["rows"]]
    return "\n".join(lines)


@element("sector_targeting", "Sector and regional targeting", (O, E), ("organisation profile", "actor claims"), markdown=_sector_md,
         description="Targeting claims for every actor, marked where they match our sectors or regions.")
def build_sector_targeting(context: ReportContext) -> ElementResult:
    profile = _profile(context)
    ours = {s.casefold() for s in (profile.industry + profile.regions)} if profile else set()
    rows = []
    for subject in actor_subjects(context.analysis):
        for predicate, kind in (("targets-sector", "sector"), ("targets-region", "region")):
            rows += [{"actor": subject.removeprefix("actor:"), "value": r["object_value"], "kind": kind, "basis": r["statement"],
                      "ours": str(r["object_value"]).casefold() in ours} for r in claims(context.analysis, subject, predicate)]
    spec = _spec("sector_targeting")
    gaps = [] if profile else ["No organisation profile, so relevance to our sectors and regions is unknown."]
    if not rows:
        return spec.result(ElementStatus.EMPTY, {"rows": [], "profile": bool(profile)}, gaps=[*gaps, "No targeting claims are recorded."])
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, {"rows": rows, "profile": bool(profile)}, gaps=gaps)


def _scenarios_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("scenarios", [])
    lines = ["## Forward-Looking Scenarios", ""]
    if not rows:
        return "\n".join([*lines, "_No scenarios recorded (`report scenario <most-likely|worst|best> <likelihood> <severity> | <description> | <signposts>`)._"])
    lines += ["| Scenario | Likelihood | Impact | Signposts |", "|---|---|---|---|"]
    lines += [f"| **{r['kind'].replace('-', ' ').title()}:** {md(r['text'])} | {likelihood_phrase(LikelihoodTerm(r['likelihood']))} | "
              f"{r['impact']} | {md(r['signposts'])} |" for r in rows]
    return "\n".join(lines)


@element("scenarios", "Forward-looking scenarios", (A,), ("report scenario records",), markdown=_scenarios_md,
         description="Most likely, worst and best case, each with an ICD 203 likelihood, impact on the severity scale, and signposts.")
def build_scenarios(context: ReportContext) -> ElementResult:
    rows = scenarios(context.analysis)
    spec = _spec("scenarios")
    missing = [k for k in ("most-likely", "worst", "best") if k not in {r["kind"] for r in rows}]
    if not rows:
        return spec.result(ElementStatus.EMPTY, {"scenarios": []}, gaps=["No scenarios are recorded."])
    gaps = [f"No {k.replace('-', ' ')} scenario." for k in missing]
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, {"scenarios": rows},
                       citations=[f"assertion:{r['id']}" for r in rows], gaps=gaps)


# --- risk assessment ---------------------------------------------------------------------


def _actors_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("actors", [])
    lines = ["## Relevant Threat Actors", ""]
    if not rows:
        return "\n".join([*lines, "_No actor has claims in this workspace._"])
    lines += ["| Actor | Motivation | Intent to target us | Capability | Precedent |", "|---|---|---|---|---|"]
    for r in rows:
        cap = f"{r['capability']:.1f} ({LEVEL_NAMES[round(r['capability'])]})" if r["capability"] else "not scored"
        lines.append(f"| {md(r['name'])} | {md(', '.join(r['motivation']) or '—')} | {md(r['intent'] or 'not assessed')} | {cap} | {md('; '.join(r['precedent']) or '—')} |")
    lines += ["", "_Capability is the mean of the actor's rubric scores._"]
    return "\n".join(lines)


@element("actor_matrix", "Relevant threat actors", (E, A), ("actor claims", "capability scores"), markdown=_actors_md,
         description="Actors with motivation, intent to target us, mean rubric capability and dated precedent.")
def build_actor_matrix(context: ReportContext) -> ElementResult:
    rows = []
    for subject in actor_subjects(context.analysis):
        scores = [int(r["object_value"]) for r in claims(context.analysis, subject, "capability:") if str(r.get("object_value") or "").isdigit()]
        intent = claims(context.analysis, subject, "intent")
        rows.append({
            "name": subject.removeprefix("actor:"),
            "motivation": [str(r["object_value"]) for r in claims(context.analysis, subject, "motivation")],
            "intent": f"{intent[-1]['object_value']}: {intent[-1]['statement']}" if intent else None,
            "capability": mean(scores) if scores else None,
            "precedent": [f"{r['object_value']} {r['statement']}" for r in claims(context.analysis, subject, "campaign")],
        })
    spec = _spec("actor_matrix")
    if not rows:
        return spec.result(ElementStatus.EMPTY, {"actors": []}, gaps=["No actor has claims."])
    gaps = [f"{r['name']}: intent to target us is not assessed (claim `intent`)." for r in rows if not r["intent"]]
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, {"actors": rows}, gaps=gaps)


def _owned(value: str, assets: tuple[str, ...]) -> bool:
    for asset in assets:
        try:
            if ipaddress.ip_address(value) in ipaddress.ip_network(asset, strict=False):
                return True
        except ValueError:
            pass
        name = value.lower().rstrip(".")
        if name == asset.lower() or name.endswith("." + asset.lower()):
            return True
    return False


def _surface_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("exposures", [])
    lines = ["## Attack Surface", ""]
    if not result.content.get("profile"):
        return "\n".join([*lines, "_No organisation profile with `external_assets`._"])
    if not rows:
        return "\n".join([*lines, "_No collected exposure data covers our external assets._"])
    lines += ["| Asset | Open ports | Known vulnerabilities | Source |", "|---|---|---|---|"]
    lines += [f"| {md(render_indicator(r['value'], r['type'], output))} | {', '.join(map(str, r['ports'])) or '—'} | {', '.join(r['vulns']) or '—'} | {r['source']} |" for r in rows]
    return "\n".join(lines)


_PORT_KEYS = ("x_internetdb_ports", "x_shodan_ports", "x_censys_ports", "ports")
_VULN_KEYS = ("x_internetdb_vulns", "x_shodan_vulns", "vulns")


@element("attack_surface", "Attack surface", (E, O), ("InternetDB, Shodan and Censys observations", "organisation external assets"),
         markdown=_surface_md, description="Open ports and known vulnerabilities collected for addresses and names we own.")
def build_attack_surface(context: ReportContext) -> ElementResult:
    profile = _profile(context)
    spec = _spec("attack_surface")
    if profile is None or not profile.external_assets:
        return spec.result(ElementStatus.EMPTY, {"profile": False, "exposures": []}, gaps=["No organisation profile with external assets."])
    rows = []
    for o in context.observations:
        blob = o.get("observed_blob") or {}
        value = str(o.get("entity_value") or "")
        if not isinstance(blob, dict) or not _owned(value, profile.external_assets):
            continue
        ports = sorted({p for k in _PORT_KEYS for p in (blob.get(k) or []) if isinstance(p, int)})
        vulns = sorted({str(v) for k in _VULN_KEYS for v in (blob.get(k) or [])})
        if ports or vulns:
            rows.append({"value": value, "type": blob.get("type"), "ports": ports, "vulns": vulns, "source": o.get("source_module")})
    gaps = [] if rows else ["None of our external assets has been scanned (run InternetDB, Shodan or Censys on them)."]
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, {"profile": True, "exposures": rows}, gaps=gaps)


def _risk_scenarios_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("scenarios", [])
    lines = ["## Risk Scenarios", ""]
    if not rows:
        return "\n".join([*lines, "_None recorded (`report risk-scenario ...`)._"])
    lines += ["| Scenario | Likelihood | Impact | Current control | Recommended control | Residual risk |", "|---|---|---|---|---|---|"]
    lines += [f"| {md(r['text'])} | {likelihood_phrase(LikelihoodTerm(r['likelihood']))} | {r['impact']} | {r['control_status'].replace('_', ' ')} | "
              f"{md(r['recommended_control'])} | {md(r['residual'])} |" for r in rows]
    return "\n".join(lines)


@element("risk_scenarios", "Risk scenarios", (A,), ("report risk-scenario records",), markdown=_risk_scenarios_md,
         description="Prioritised scenarios with likelihood, impact, current control status, recommended control and residual risk.")
def build_risk_scenarios(context: ReportContext) -> ElementResult:
    rows = risk_scenarios(context.analysis)
    spec = _spec("risk_scenarios")
    if not rows:
        return spec.result(ElementStatus.EMPTY, {"scenarios": []}, gaps=["No risk scenarios are recorded."])
    order = {s.value: i for i, s in enumerate(Severity)}
    rows.sort(key=lambda r: (order[r["impact"]], -list(LikelihoodTerm).index(LikelihoodTerm(r["likelihood"]))))
    return spec.result(ElementStatus.COMPLETE, {"scenarios": rows}, citations=[f"assertion:{r['id']}" for r in rows])
