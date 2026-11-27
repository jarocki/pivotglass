"""Sections built from organisation input (#59): profile, exposure, controls, benchmark, objective, telemetry.

An absent input is a gap naming the `org` command that supplies it; nothing
here estimates the organisation's own facts.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from pivotglass.reports.claims import actor_subjects, claims
from pivotglass.reports.contract import GAP_RULE, OutputFormat, ProvenanceClass, render_indicator
from pivotglass.reports.elements import (
    ELEMENTS,
    ElementResult,
    ElementStatus,
    ReportContext,
    element,
)
from pivotglass.reports.elements.common import md
from pivotglass.reports.rubrics import CAPABILITY_AXES

E, M, O = ProvenanceClass.EVIDENCE, ProvenanceClass.METHOD, ProvenanceClass.ORG_INPUT  # noqa: E741
NO_PROFILE = "No organisation profile is imported (`org import <file>`); see the report reference for the format."


def _spec(element_id: str):  # noqa: ANN202
    return ELEMENTS[element_id]


def _org(context: ReportContext) -> Any:
    from pivotglass.reports.org import OrgInputs

    return OrgInputs(context.workspace_mgr)


def _version(text: str) -> tuple[int, ...] | None:
    parts = re.findall(r"\d+", text or "")
    return tuple(int(p) for p in parts) if parts else None


def in_range(version: str | None, match: dict[str, Any]) -> bool | None:
    """Whether ``version`` falls in an NVD CPE match range; ``None`` when it cannot be compared."""

    v = _version(version or "")
    if v is None:
        return None
    checks = (
        ("version_start_including", lambda b: v >= b), ("version_start_excluding", lambda b: v > b),
        ("version_end_including", lambda b: v <= b), ("version_end_excluding", lambda b: v < b),
    )
    bounded = False
    for key, test in checks:
        bound = _version(match.get(key) or "")
        if bound is not None:
            bounded = True
            if not test(bound):
                return False
    if bounded:
        return True
    cpe_version = (match.get("criteria") or "").split(":")[5:6]
    if cpe_version and cpe_version[0] not in {"*", "-"}:
        return _version(cpe_version[0]) == v
    return None


# --- asset profile ---------------------------------------------------------------


def _assets_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Scope and Assets", ""]
    if not c:
        return "\n".join([*lines, f"_{NO_PROFILE}_"])
    if c.get("name"):
        lines.append(f"**Organisation:** {md(c['name'])} · {md(', '.join(c['industry']) or 'industry not stated')} · {md(', '.join(c['regions']) or 'regions not stated')}")
    if c.get("crown_jewels"):
        lines += ["", "| Critical asset | Data | Impact if lost |", "|---|---|---|"]
        lines += [f"| {md(j['name'])} | {md(', '.join(j['data']) or '—')} | {j['impact']} |" for j in c["crown_jewels"]]
    if c.get("technology"):
        lines += ["", "**Technology:** " + "; ".join(md(f"{t['vendor']} {t['product']} {t.get('version') or ''}".strip()) for t in c["technology"])]
    if c.get("vendors"):
        lines += ["", "**Critical vendors:** " + "; ".join(md(f"{v['name']} ({v['service']}, {v['criticality']})") for v in c["vendors"])]
    lines += ["", f"_Organisation input from {md(c['_source'])}, imported {c['_at'][:16].replace('T', ' ')} UTC._"]
    return "\n".join(lines)


def _profile_content(context: ReportContext) -> dict[str, Any] | None:
    store = _org(context)
    profile = store.profile()
    if profile is None:
        return None
    meta = store.summary().get("profile", {})
    return {**profile.model_dump(mode="json"), "_source": meta.get("source", ""), "_at": meta.get("imported_at", "")}


@element(
    "asset_profile",
    "Scope and assets",
    (O,),
    ("organisation profile",),
    markdown=_assets_md,
    description="The organisation, its critical assets and data with the impact of losing each, its technology and critical vendors.",
)
def build_asset_profile(context: ReportContext) -> ElementResult:
    content = _profile_content(context)
    spec = _spec("asset_profile")
    if content is None:
        return spec.result(ElementStatus.EMPTY, {}, gaps=[NO_PROFILE])
    gaps = [] if content["crown_jewels"] else ["The profile names no critical assets."]
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, content, gaps=gaps)


# --- exposure ----------------------------------------------------------------------


def _exposure_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Organisational Exposure", ""]
    if not c.get("profile"):
        return "\n".join([*lines, f"_{NO_PROFILE}_"])
    lines.append("**Sector and regional relevance:**" + ("" if c["targeting"] else " _no recorded targeting matches our sectors or regions_"))
    lines += [f"- {md(t['actor'])} targets {md(t['value'])} ({t['kind']}) — {md(t['basis'])}" for t in c["targeting"]]
    lines += ["", "**Technology exposure:**" + ("" if c["technology"] else " _none of our recorded technology matches a vulnerability in this investigation_")]
    for t in c["technology"]:
        state = {True: "**affected**", False: "not affected", None: "version not compared"}[t["affected"]]
        lines.append(f"- {t['cve']}: {md(t['product'])} {md(t['version'] or '')} — {state} ({md(t['basis'])})")
    lines += ["", "**Controls for the techniques in this investigation:**" + ("" if c["controls"] else " _no control is recorded for them_")]
    lines += [f"- {r['technique']}: {md(r['control'])} — gap {r['gap_status']}" for r in c["controls"]]
    return "\n".join(lines)


@element(
    "org_exposure",
    "Organisational exposure",
    (O, E),
    ("organisation profile", "control inventory", "actor claims", "NVD and KEV records", "ATT&CK mappings"),
    markdown=_exposure_md,
    description="Whether actors target our sectors or regions, whether we run affected technology (NVD version ranges, "
    "KEV vendor and product), and the gap status of our controls for the techniques seen.",
)
def build_org_exposure(context: ReportContext) -> ElementResult:
    from pivotglass.reports.elements.vulnerability import KEV, NVD, vulnerabilities

    store = _org(context)
    profile, controls = store.profile(), store.controls()
    spec = _spec("org_exposure")
    if profile is None:
        return spec.result(ElementStatus.EMPTY, {"profile": False}, gaps=[NO_PROFILE])
    ours = {s.casefold() for s in profile.industry} | {r.casefold() for r in profile.regions}
    targeting = []
    for subject in actor_subjects(context.analysis):
        for predicate, kind in (("targets-sector", "sector"), ("targets-region", "region")):
            for row in claims(context.analysis, subject, predicate):
                if str(row.get("object_value") or "").casefold() in ours:
                    targeting.append({"actor": subject.removeprefix("actor:"), "value": row["object_value"], "kind": kind, "basis": row["statement"]})
    technology = []
    for cve, data in vulnerabilities(context).items():
        matches = (data.get(NVD) or {}).get("x_nvd_configurations", [])
        kev = data.get(KEV) or {}
        for tech in profile.technology:
            vendor, product = tech.vendor.casefold().replace(" ", "_"), tech.product.casefold().replace(" ", "_")
            hits = [m for m in matches if f":{vendor}:{product}:" in m.get("criteria", "").casefold()]
            if hits:
                verdicts = [in_range(tech.version, m) for m in hits]
                affected = True if True in verdicts else None if None in verdicts else False
                technology.append({"cve": cve, "product": f"{tech.vendor} {tech.product}", "version": tech.version,
                                   "affected": affected, "basis": "NVD configuration"})
            elif kev.get("x_kev_listed") and kev.get("x_kev_vendor", "").casefold() == tech.vendor.casefold() and \
                    kev.get("x_kev_product", "").casefold() == tech.product.casefold():
                technology.append({"cve": cve, "product": f"{tech.vendor} {tech.product}", "version": tech.version,
                                   "affected": None, "basis": "KEV vendor and product; versions not stated"})
    techniques = {m.content_id for m in context.mappings if m.framework.value == "attack" and m.state.value == "accepted"}
    control_rows = [
        {"technique": c.technique, "control": c.control, "gap_status": c.gap_status}
        for c in (controls or ()) if c.technique in techniques
    ]
    gaps = []
    if controls is None:
        gaps.append("No control inventory is imported, so control status is unknown.")
    if not profile.technology:
        gaps.append("The profile lists no technology, so technical exposure cannot be checked.")
    uncovered = sorted(techniques - {c["technique"] for c in control_rows})
    if controls is not None and uncovered:
        gaps.append(f"No control is recorded for {', '.join(uncovered)}.")
    content = {"profile": True, "targeting": targeting, "technology": technology, "controls": control_rows}
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, content, gaps=gaps)


# --- controls ------------------------------------------------------------------------


def _controls_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("controls", [])
    lines = ["## Control Coverage", ""]
    if not rows:
        return "\n".join([*lines, "_No control inventory is imported (`org import <file>` with a `controls` section)._"])
    lines += ["| Technique | Control | Visibility | Alerting | Prevention | Gap | Last tested | Evidence |", "|---|---|---:|---:|---:|---|---|---|"]
    lines += [
        f"| {r['technique']} | {md(r['control'])} | {r['visibility']} | {r['alerting']} | {r['prevention']} | {r['gap_status']} | "
        f"{r['last_tested'] or 'never'} | {md(r['evidence'] or '—')} |"
        for r in rows
    ]
    lines += ["", f"_Scores 0-2 per dimension (organisation input). Gap rule: {GAP_RULE}_"]
    return "\n".join(lines)


@element(
    "control_matrix",
    "Control coverage",
    (O,),
    ("control inventory",),
    markdown=_controls_md,
    description="Per technique: the control, visibility, alerting and prevention scores (0-2), the derived gap status, "
    "and when and how it was last tested.",
)
def build_control_matrix(context: ReportContext) -> ElementResult:
    controls = _org(context).controls()
    spec = _spec("control_matrix")
    if controls is None:
        return spec.result(ElementStatus.EMPTY, {"controls": []}, gaps=["No control inventory is imported."])
    rows = [{**c.model_dump(mode="json"), "gap_status": c.gap_status} for c in controls]
    untested = [r["technique"] for r in rows if not r["last_tested"]]
    gaps = [f"Never tested: {', '.join(untested)}."] if untested else []
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, {"controls": rows}, gaps=gaps)


# --- capability benchmark -----------------------------------------------------------


def _benchmark_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("axes", [])
    lines = ["## Defence Benchmark", ""]
    if not rows:
        return "\n".join([*lines, "_No capability benchmark in the organisation profile._"])
    lines += ["| Axis | Actor | Our level | Difference |", "|---|---:|---:|---:|"]
    for r in rows:
        diff = "—" if r["actor"] is None or r["ours"] is None else f"{r['actor'] - r['ours']:+d}"
        lines.append(f"| {r['title']} | {r['actor'] or '—'} | {r['ours'] or '—'} | {diff} |")
    lines += ["", "_Positive difference: the actor's level exceeds our self-assessed level on that axis._"]
    return "\n".join(lines)


@element(
    "defense_benchmark",
    "Defence benchmark",
    (O,),
    ("organisation profile (capability_benchmark)", "capability scores"),
    markdown=_benchmark_md,
    description="The organisation's self-assessed level on each rubric axis beside the actor's score.",
)
def build_defense_benchmark(context: ReportContext) -> ElementResult:
    profile = _org(context).profile()
    spec = _spec("defense_benchmark")
    if profile is None or not profile.capability_benchmark:
        return spec.result(ElementStatus.EMPTY, {"axes": []}, gaps=["No capability benchmark in the organisation profile."])
    radar = context.results.get("capability_radar")
    actor = {s["axis"]: s["score"] for s in (radar.content.get("scores", []) if radar else [])}
    rows = [{"axis": a, "title": title, "actor": actor.get(a), "ours": profile.capability_benchmark.get(a)} for a, (title, _l) in CAPABILITY_AXES.items()]
    missing = [r["title"] for r in rows if r["ours"] is None]
    return spec.result(ElementStatus.PARTIAL if missing else ElementStatus.COMPLETE, {"axes": rows},
                       gaps=[f"No benchmark level for: {', '.join(missing)}."] if missing else [])


# --- objective ------------------------------------------------------------------------


def _objective_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("objectives", [])
    lines = ["## Objective", ""]
    if not rows:
        return "\n".join([*lines, "_No environment model with an objective node is imported (`org import`, `environment` section)._"])
    lines += [f"- **{md(r['label'])}** (`{r['id']}`)" + (f" — protects {md(r['protects'])}" if r.get("protects") else "") for r in rows]
    return "\n".join(lines)


@element(
    "objective",
    "Objective",
    (O,),
    ("environment model",),
    markdown=_objective_md,
    description="The asset or outcome the attack paths lead to, from the environment model's objective nodes.",
)
def build_objective(context: ReportContext) -> ElementResult:
    env = _org(context).environment()
    profile = _org(context).profile()
    spec = _spec("objective")
    objectives = [n for n in (env.nodes if env else ()) if n.kind == "objective"]
    if not objectives:
        return spec.result(ElementStatus.EMPTY, {"objectives": []}, gaps=["No objective node in an imported environment model."])
    jewels = {j.name.casefold(): j.name for j in (profile.crown_jewels if profile else ())}
    rows = [{"id": n.id, "label": n.label, "protects": jewels.get(n.label.casefold())} for n in objectives]
    return spec.result(ElementStatus.COMPLETE, {"objectives": rows})


# --- forensic timeline -------------------------------------------------------------------


def _forensic_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("events", [])
    lines = ["## Forensic Timeline", ""]
    if not rows:
        return "\n".join([*lines, "_No telemetry is imported (`org telemetry <file.csv>`)._"])
    lines += ["| Time (UTC) | Host | Source | Technique | Event | Artifact |", "|---|---|---|---|---|---|"]
    for r in rows[:500]:
        stamp = r["timestamp"][:19].replace("T", " ")
        precision = "" if r["precision"] == "second" else f" (±{r['precision']})"
        lines.append(f"| `{stamp}`{precision} | {md(r['host'])} | {md(r['source'])} | {r['technique'] or '—'} | "
                     f"{md(render_indicator(r['summary'], None, output))} | {md(r['artifact_ref'] or '—')} |")
    if len(rows) > 500:  # noqa: PLR2004
        lines.append(f"_{len(rows) - 500} more events are in the JSON rendering._")
    return "\n".join(lines)


@element(
    "forensic_timeline",
    "Forensic timeline",
    (O, M),
    ("imported telemetry",),
    markdown=_forensic_md,
    description="Imported host and network events in UTC with host, source, technique, summary, precision and artifact reference.",
)
def build_forensic_timeline(context: ReportContext) -> ElementResult:
    events = _org(context).telemetry()
    spec = _spec("forensic_timeline")
    if not events:
        return spec.result(ElementStatus.EMPTY, {"events": []}, gaps=["No telemetry is imported."])
    rows = [e.model_dump(mode="json") for e in events]
    by_host: dict[str, int] = defaultdict(int)
    for r in rows:
        by_host[r["host"]] += 1
    gaps = [] if any(r["technique"] for r in rows) else ["No imported event names an ATT&CK technique."]
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, {"events": rows, "hosts": dict(by_host)}, gaps=gaps)
