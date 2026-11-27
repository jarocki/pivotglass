"""Report elements that are specified but not yet built (#52).

Each entry fixes an element's id, title, provenance, authorities and meaning,
so the 18 report-type definitions can be complete and validated before every
builder exists. The issue named is the one that builds it. A report type that
uses a planned element is listed as planned and cannot be rendered: Pivotglass
never fills a section it cannot build.

When a builder lands it registers with ``@element`` under the same id, and its
entry here is deleted in the same change; ``tests/test_report_types.py``
fails if an id is both planned and built.
"""

from __future__ import annotations

from dataclasses import dataclass

from pivotglass.reports.contract import ProvenanceClass

E = ProvenanceClass.EVIDENCE
M = ProvenanceClass.METHOD
A = ProvenanceClass.ANALYST
D = ProvenanceClass.MODEL_DRAFT
O = ProvenanceClass.ORG_INPUT  # noqa: E741 - one letter, like the others


@dataclass(frozen=True)
class PlannedElement:
    id: str
    title: str
    provenance: tuple[ProvenanceClass, ...]
    authorities: tuple[str, ...]
    description: str
    issue: int


_PLANNED = (
    # --- Domain 3: analytical and attribution (#55) --------------------------
    # Built in reports/elements/analytical.py except the organisation benchmark.
    # --- Domain 2: operational and incident (#54, #58) ------------------------
    # --- Domain 5: detection, hunting and posture (#57) -----------------------
    PlannedElement(
        "technique_scope", "Techniques in scope", (E, M), ("accepted mappings", "actor profiles"),
        "The ATT&CK techniques assessed and why each is in scope (observed, or attributed to an actor "
        "of concern).", 57,
    ),
    PlannedElement(
        "gap_list", "Coverage gaps", (M,), ("control matrix", "gap rule (reports/contract.py)"),
        "Each technique's gap status derived by the stated rule, critical first.", 57,
    ),
    PlannedElement(
        "emulation_plan", "Adversary emulation plan", (M,), ("pinned Atomic Red Team index",),
        "Per gap, the Atomic Red Team test ID, the telemetry it should produce and the pass criteria.", 57,
    ),
    # --- Domain 1: strategic and executive (#53) ------------------------------
    PlannedElement(
        "bluf", "Bottom line up front", (D, A), ("cited evidence", "key judgments"),
        "At most two sentences: what happened or is expected, whether the organisation is affected, "
        "and the decision leadership must make.", 53,
    ),
    PlannedElement(
        "risk_rating", "Overall risk", (A,), ("analyst",),
        "The overall risk to the organisation on the severity scale, with the reason and the confidence.", 53,
    ),
    PlannedElement(
        "situational_overview", "Situational overview", (D, A), ("cited evidence",),
        "The actor, event or vulnerability in non-technical terms, with what is known and what is not.", 53,
    ),
    PlannedElement(
        "period_scope", "Period and coverage", (M,), ("module runs", "observations"),
        "The reporting window, the sources collected in it and what they cannot see.", 53,
    ),
    PlannedElement(
        "macro_trends", "Macro trends", (A, D, E), ("framework mappings over the period",),
        "Shifts in motivation, initial access and tooling over the period, each supported by counts "
        "or cited cases.", 53,
    ),
    PlannedElement(
        "sector_targeting", "Sector and regional targeting", (O, E), ("organisation profile (#59)", "victimology"),
        "Activity against the organisation's sectors and regions in the period, with sources.", 53,
    ),
    PlannedElement(
        "emerging_ttps", "Emerging techniques", (A, E), ("framework mappings",),
        "Techniques newly observed or rising in the period, with first-seen dates.", 53,
    ),
    PlannedElement(
        "scenarios", "Forward-looking scenarios", (A,), ("analyst", "signposts"),
        "Most likely, worst and best cases for the period ahead, each with an ICD 203 likelihood, "
        "impact on the severity scale, and the signposts that would show it unfolding.", 53,
    ),
    PlannedElement(
        "actor_matrix", "Relevant threat actors", (E, A), ("hypotheses", "Nucleotide aliases", "dossier Capability slot"),
        "Actors relevant to the scope with motivation, intent to target, capability (rubric level) and "
        "cited precedent.", 53,
    ),
    PlannedElement(
        "attack_surface", "Attack surface", (E, O), ("Shodan, Censys and InternetDB observations", "organisation assets (#59)"),
        "Externally visible services and exposures matched to the organisation's assets.", 53,
    ),
    PlannedElement(
        "risk_scenarios", "Risk scenarios", (A,), ("analyst",),
        "Prioritised scenarios, each with likelihood (ICD 203), impact (severity), current control "
        "status, recommended control and residual risk.", 53,
    ),
    # --- Domain 4: attack flow and behavioural (#56) --------------------------
)

PLANNED: dict[str, PlannedElement] = {item.id: item for item in _PLANNED}
if len(PLANNED) != len(_PLANNED):  # pragma: no cover - guards the table above
    raise RuntimeError("a planned report element is declared twice")
