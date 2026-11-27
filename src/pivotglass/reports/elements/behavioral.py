"""Domain 4 elements: kill chain, ATT&CK Navigator layer, attack tree, choke points, dwell metrics (#56).

The Navigator layer here is a report artifact: accepted mappings only, scored
by independently sourced evidence, one gradient. It is distinct from
``framework navigator`` (framework_perspectives.build_attack_navigator_layer),
which colours every mapping by its review state for mapping review.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from itertools import product
from typing import Any

from pivotglass.reports.contract import CONTROL_STATUS_DEFINITIONS, OutputFormat, ProvenanceClass
from pivotglass.reports.elements import (
    ELEMENTS,
    ElementResult,
    ElementStatus,
    ReportContext,
    element,
)
from pivotglass.reports.elements.common import md
from pivotglass.reports.elements.operational import KILL_CHAIN_PHASES
from pivotglass.reports.sections import control_statuses

E, M, A, O = ProvenanceClass.EVIDENCE, ProvenanceClass.METHOD, ProvenanceClass.ANALYST, ProvenanceClass.ORG_INPUT  # noqa: E741
MAX_SCENARIOS = 500


def _spec(element_id: str):  # noqa: ANN202
    return ELEMENTS[element_id]


def _org(context: ReportContext) -> Any:
    from pivotglass.reports.org import OrgInputs

    return OrgInputs(context.workspace_mgr)


# --- kill chain -----------------------------------------------------------------


def _kill_chain_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("phases", [])
    lines = ["## Kill Chain", "", "| Phase | Observed adversary action | ATT&CK | Telemetry | Control status |", "|---|---|---|---|---|"]
    for r in rows:
        action = "; ".join(md(a) for a in r["actions"]) or "_not observed_"
        status = f"**{r['status'].replace('_', ' ')}**" if r["status"] else "_not recorded_"
        lines.append(f"| {r['phase']} | {action} | {', '.join(r['techniques']) or '—'} | {md(r['telemetry'] or '—')} | {status} |")
    lines += ["", "**Control status terms:** " + "; ".join(f"*{k.value.replace('_', ' ')}*: {v}" for k, v in CONTROL_STATUS_DEFINITIONS.items())]
    return "\n".join(lines)


@element(
    "kill_chain_table",
    "Kill chain",
    (E, A, O),
    ("Kill Chain mappings", "ATT&CK mappings", "imported telemetry", "report control records"),
    markdown=_kill_chain_md,
    description="For each of the seven phases: the observed action from accepted mappings, the ATT&CK techniques on the "
    "same evidence or in telemetry, the telemetry source, and the recorded control status.",
)
def build_kill_chain_table(context: ReportContext) -> ElementResult:
    by_phase: dict[str, list[Any]] = defaultdict(list)
    for m in context.mappings:
        if m.framework.value == "kill_chain" and m.state.value == "accepted":
            by_phase[m.content_id].append(m)
    attack = [m for m in context.mappings if m.framework.value == "attack" and m.state.value == "accepted"]
    statuses = control_statuses(context.analysis)
    events = _org(context).telemetry() or ()
    rows = []
    for phase, label in KILL_CHAIN_PHASES:
        refs = {r for m in by_phase.get(phase, []) for r in m.evidence_refs}
        techniques = sorted({t.content_id for t in attack if refs & set(t.evidence_refs)})
        telemetry = sorted({e.source for e in events if e.technique and e.technique in techniques})
        recorded = statuses.get(phase)
        rows.append({
            "phase": label, "phase_id": phase, "actions": [m.basis for m in by_phase.get(phase, [])], "techniques": techniques,
            "telemetry": ", ".join(telemetry) or (recorded["basis"] if recorded else None),
            "status": recorded["status"] if recorded else None,
        })
    observed = [r for r in rows if r["actions"]]
    spec = _spec("kill_chain_table")
    if not observed:
        return spec.result(ElementStatus.EMPTY, {"phases": rows}, gaps=["No accepted Kill Chain mapping."])
    gaps = [f"{r['phase']}: observed, but no control status is recorded (`report control {r['phase_id']} <status> | <basis>`)."
            for r in observed if not r["status"]]
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, {"phases": rows},
                       citations=[f"mapping:{m.id}" for ms in by_phase.values() for m in ms], gaps=gaps)


# --- Navigator layer ------------------------------------------------------------------


def navigator_layer(context: ReportContext, name: str) -> dict[str, Any]:
    from pivotglass.core.framework_perspectives import ATTACK_ENTERPRISE_V19_2 as PIN

    sources = {str(o["id"]): str(o.get("source_dependence_group") or o.get("source_module")) for o in context.observations}
    techniques = []
    for m in sorted(context.mappings, key=lambda m: m.content_id):
        if m.framework.value != "attack" or m.state.value != "accepted" or m.framework_version != PIN.version:
            continue
        independent = sorted({sources.get(ref, ref) for ref in m.evidence_refs})
        techniques.append({
            "techniqueID": m.content_id,
            "score": len(independent),
            "comment": f"{m.basis} [evidence: {', '.join(m.evidence_refs)}]",
            "enabled": True,
            "metadata": [{"name": "Confidence", "value": m.confidence.value}, {"name": "Independent sources", "value": ", ".join(independent)}],
        })
    high = max((t["score"] for t in techniques), default=1)
    return {
        "name": name,
        "versions": {"attack": PIN.version, "navigator": PIN.navigator_version, "layer": PIN.navigator_layer_version},
        "domain": PIN.domain,
        "description": "Accepted ATT&CK mappings from a Pivotglass investigation. Score: independently sourced evidence per technique.",
        "techniques": techniques,
        "gradient": {"colors": ["#ffffff", "#e8613c"], "minValue": 0, "maxValue": max(high, 1)},
        "legendItems": [],
        "metadata": [{"name": "Generator", "value": "Pivotglass report"}, {"name": "ATT&CK content digest", "value": PIN.sha256}],
        "showTacticRowBackground": False,
        "selectTechniquesAcrossTactics": True,
        "selectSubtechniquesWithParent": False,
        "layout": {"layout": "side", "aggregateFunction": "max", "showID": True},
    }


def _navigator_md(result: ElementResult, output: OutputFormat) -> str:
    layer = result.content.get("layer") or {}
    rows = layer.get("techniques", [])
    lines = ["## ATT&CK Navigator Layer", ""]
    if not rows:
        return "\n".join([*lines, "_No accepted ATT&CK mapping on the pinned release._"])
    v = layer["versions"]
    lines += [f"Layer {v['layer']} for Navigator {v['navigator']}, ATT&CK {v['attack']}. Download it with `report attack-navigator-layer navigator`.", "",
              "| Technique | Score | Comment |", "|---|---:|---|"]
    lines += [f"| {t['techniqueID']} | {t['score']} | {md(t['comment'])} |" for t in rows]
    lines += ["", "_Score is the number of independent sources behind the technique; one gradient, no per-technique colours._"]
    return "\n".join(lines)


@element(
    "navigator_layer",
    "ATT&CK Navigator layer",
    (M,),
    ("accepted ATT&CK mappings", "pinned ATT&CK v19.2", "observations"),
    markdown=_navigator_md,
    description="A layer 4.5 file for Navigator 5.3.2 and ATT&CK 19.2: score is the number of independently sourced "
    "observations per technique, one gradient, and each comment carries the procedure and its evidence.",
)
def build_navigator_layer(context: ReportContext) -> ElementResult:
    layer = navigator_layer(context, f"Pivotglass {context.workspace_name}")
    spec = _spec("navigator_layer")
    if not layer["techniques"]:
        return spec.result(ElementStatus.EMPTY, {"layer": layer}, gaps=["No accepted ATT&CK mapping on ATT&CK 19.2."])
    return spec.result(ElementStatus.COMPLETE, {"layer": layer})


# --- attack tree ------------------------------------------------------------------------


def attack_scenarios(env: Any, objective: str) -> list[frozenset[str]]:
    """Minimal sets of nodes an attacker must hold to reach ``objective``, honouring AND/OR gates."""

    nodes = {n.id: n for n in env.nodes}
    incoming: dict[str, list[str]] = defaultdict(list)
    for e in env.edges:
        incoming[e.target].append(e.source)
    memo: dict[str, list[frozenset[str]]] = {}

    def solve(node: str, seen: frozenset[str]) -> list[frozenset[str]]:
        if node in memo:
            return memo[node]
        if node in seen:
            return []  # a cycle contributes no path
        n = nodes[node]
        if n.kind == "entry" or not incoming[node]:
            result = [frozenset({node})] if n.kind == "entry" else []
        else:
            options = [solve(p, seen | {node}) for p in incoming[node]]
            if n.gate == "AND":
                result = [frozenset({node}).union(*combo) for combo in product(*options)] if all(options) else []
            else:
                result = [s | {node} for opt in options for s in opt]
        result = sorted(set(result), key=lambda s: (len(s), sorted(s)))[:MAX_SCENARIOS]
        memo[node] = result
        return result

    return solve(objective, frozenset())


def _tree_content(context: ReportContext) -> dict[str, Any] | None:
    env = _org(context).environment()
    if env is None:
        return None
    objectives = [n for n in env.nodes if n.kind == "objective"]
    scenarios = {o.id: [sorted(s) for s in attack_scenarios(env, o.id)] for o in objectives}
    return {
        "nodes": [n.model_dump(mode="json") for n in env.nodes],
        "edges": [e.model_dump(mode="json") for e in env.edges],
        "scenarios": scenarios,
    }


def _tree_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Attack Tree", ""]
    if not c.get("nodes"):
        return "\n".join([*lines, "_No environment model is imported (`org import`, `environment` section)._"])
    labels = {n["id"]: n["label"] for n in c["nodes"]}
    lines += ["| From | To | Technique | Precondition | Basis |", "|---|---|---|---|---|"]
    lines += [f"| {md(labels[e['source']])} | {md(labels[e['target']])} | {e['technique'] or '—'} | {md(e['precondition'] or '—')} | {e['status']} |" for e in c["edges"]]
    gates = [n for n in c["nodes"] if n["gate"] == "AND"]
    if gates:
        lines += ["", "AND gates (every incoming step is required): " + ", ".join(md(n["label"]) for n in gates)]
    for objective, scenarios in c["scenarios"].items():
        lines += ["", f"**Ways to reach {md(labels[objective])}: {len(scenarios)}**"]
        lines += [f"- {' + '.join(md(labels[n]) for n in s)}" for s in scenarios[:20]]
    lines += ["", "_Download the diagram with `report attack-graph-tree mermaid`. Assumed steps come from the environment model, not observation._"]
    return "\n".join(lines)


@element(
    "attack_tree",
    "Attack tree",
    (O, M),
    ("environment model",),
    markdown=_tree_md,
    description="Paths from entry points to the objective with explicit AND and OR gates; each step names its technique, "
    "precondition, and whether it is observed or assumed.",
)
def build_attack_tree(context: ReportContext) -> ElementResult:
    content = _tree_content(context)
    spec = _spec("attack_tree")
    if content is None:
        return spec.result(ElementStatus.EMPTY, {}, gaps=["No environment model is imported."])
    gaps = [f"No path reaches {o}." for o, s in content["scenarios"].items() if not s]
    if not content["scenarios"]:
        gaps.append("The environment model has no objective node.")
    assumed = sum(1 for e in content["edges"] if e["status"] == "assumed")
    if assumed:
        gaps.append(f"{assumed} of {len(content['edges'])} steps are assumed, not observed.")
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, content, gaps=gaps)


def _choke_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("choke_points", [])
    lines = ["## Choke Points", ""]
    if not rows:
        return "\n".join([*lines, "_No node lies on most of the ways to the objective._"])
    lines += ["| Node | Objective | Ways it severs | Share |", "|---|---|---:|---:|"]
    lines += [f"| {md(r['label'])} | {md(r['objective'])} | {r['severed']} of {r['total']} | {r['share']:.0%} |" for r in rows]
    lines += ["", "_Method: a node severs a way to the objective when that way needs it; entry points and the objective are excluded._"]
    return "\n".join(lines)


@element(
    "choke_points",
    "Choke points",
    (O, M),
    ("attack tree",),
    markdown=_choke_md,
    description="Nodes that every way (or most ways) to the objective must cross, with the share each one severs.",
)
def build_choke_points(context: ReportContext) -> ElementResult:
    content = _tree_content(context)
    spec = _spec("choke_points")
    if content is None:
        return spec.result(ElementStatus.EMPTY, {"choke_points": []}, gaps=["No environment model is imported."])
    labels = {n["id"]: n["label"] for n in content["nodes"]}
    kinds = {n["id"]: n["kind"] for n in content["nodes"]}
    rows = []
    for objective, scenarios in content["scenarios"].items():
        total = len(scenarios)
        counts: dict[str, int] = defaultdict(int)
        for s in scenarios:
            for node in s:
                if kinds[node] == "asset":
                    counts[node] += 1
        rows += [
            {"node": n, "label": labels[n], "objective": labels[objective], "severed": c, "total": total, "share": c / total}
            for n, c in counts.items() if total and c / total >= 0.5  # noqa: PLR2004
        ]
    rows.sort(key=lambda r: (-r["share"], r["label"]))
    if not rows:
        return spec.result(ElementStatus.EMPTY, {"choke_points": []}, gaps=["No node lies on at least half the ways to the objective."])
    return spec.result(ElementStatus.COMPLETE, {"choke_points": rows})


def mermaid_attack_tree(content: dict[str, Any]) -> str:
    from pivotglass.reports.elements.analytical import _mermaid_label

    lines = ["flowchart LR"]
    for n in content.get("nodes", []):
        label = _mermaid_label(f"{n['label']}{' [AND]' if n['gate'] == 'AND' else ''}")
        shape = {"entry": f"([{label}])", "objective": f"[[{label}]]"}.get(n["kind"], f"[{label}]")
        lines.append(f"  {n['id']}{shape}")
    for e in content.get("edges", []):
        arrow = "-->" if e["status"] == "observed" else "-.->"
        text = " ".join(x for x in (e["technique"], e["precondition"]) if x)
        lines.append(f"  {e['source']} {arrow}|{_mermaid_label(text or e['status'])}| {e['target']}")
    return "\n".join(lines) + "\n"


# --- dwell metrics -----------------------------------------------------------------------


def _dwell_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Dwell and Response Times", ""]
    if not c.get("first_malicious"):
        return "\n".join([*lines, "_No telemetry marks the first malicious event._"])
    lines += [f"- **First malicious event:** {c['first_malicious']} UTC ({c['first_basis']})"]
    lines += [f"- **Detection:** {c['detection'] or 'not marked'}", f"- **Containment:** {c['containment'] or 'not marked'}"]
    if c.get("dwell"):
        lines.append(f"- **Dwell time (first malicious to detection):** {c['dwell']}")
    if c.get("time_to_contain"):
        lines.append(f"- **Time to contain (detection to containment):** {c['time_to_contain']}")
    if c.get("coarse"):
        lines.append(f"- _Precision: {c['coarse']} event(s) are only accurate to the minute or worse._")
    return "\n".join(lines)


def _span(start: str, end: str) -> str:
    delta = datetime.fromisoformat(end) - datetime.fromisoformat(start)
    hours, rest = divmod(int(delta.total_seconds()), 3600)
    return f"{hours // 24}d {hours % 24}h {rest // 60}m" if hours >= 24 else f"{hours}h {rest // 60}m"  # noqa: PLR2004


@element(
    "dwell_metrics",
    "Dwell and response times",
    (O, M),
    ("imported telemetry markers",),
    markdown=_dwell_md,
    description="First malicious event, detection and containment from marked telemetry, and the dwell and response "
    "intervals computed from them.",
)
def build_dwell_metrics(context: ReportContext) -> ElementResult:
    events = _org(context).telemetry() or ()
    spec = _spec("dwell_metrics")
    if not events:
        return spec.result(ElementStatus.EMPTY, {}, gaps=["No telemetry is imported."])

    def first(marker: str) -> Any:
        return next((e for e in events if e.marker == marker), None)

    start = first("first-malicious")
    basis = "marked first-malicious"
    if start is None:
        start = next((e for e in events if e.technique), None)
        basis = "earliest event with an ATT&CK technique (no event is marked first-malicious)"
    detection, containment = first("detection"), first("containment")
    if start is None:
        return spec.result(ElementStatus.EMPTY, {}, gaps=["No event is marked or mapped as malicious."])
    iso = lambda e: e.timestamp.isoformat() if e else None  # noqa: E731
    content = {
        "first_malicious": iso(start)[:19].replace("T", " "), "first_basis": basis,
        "detection": iso(detection)[:19].replace("T", " ") if detection else None,
        "containment": iso(containment)[:19].replace("T", " ") if containment else None,
        "dwell": _span(iso(start), iso(detection)) if detection else None,
        "time_to_contain": _span(iso(detection), iso(containment)) if detection and containment else None,
        "coarse": sum(1 for e in (start, detection, containment) if e and e.precision != "second"),
    }
    gaps = []
    if detection is None:
        gaps.append("No telemetry event is marked detection, so dwell time is unknown.")
    if containment is None:
        gaps.append("No telemetry event is marked containment, so time to contain is unknown.")
    if start.marker is None:
        gaps.append("The first malicious event is inferred, not marked.")
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, content, gaps=gaps)


__all__ = ["attack_scenarios", "mermaid_attack_tree", "navigator_layer"]
