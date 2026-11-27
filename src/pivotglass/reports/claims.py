"""Structured analyst claims that report sections read (#55).

Actor profiles, capability scores and similar sections are analyst knowledge,
not collected evidence. Analysts record them with the existing claim command,
for example::

    analysis claim judgment actor:Example-Spider alias Example Spider | Vendor A's name
    analysis claim judgment actor:Example-Spider motivation financial | Ransom notes and leak site
    analysis claim judgment actor:Example-Spider capability:malware 4 | Custom loader, see report

The subject is the actor reference (``actor:<name>``); the predicate is one of
``REPORT_PREDICATES``. Each claim stays an assertion in the analytic ledger,
with its author, status and evidence links; this module only defines which
predicates the report sections read and what they mean.
"""

from __future__ import annotations

from typing import Any

ACTOR_PREFIX = "actor:"
# Elements about one actor; a report type containing any of them needs a subject.
ACTOR_SCOPED = frozenset({"actor_identity", "motivation", "victimology", "historical_timeline", "arsenal", "capability_radar"})

REPORT_PREDICATES: dict[str, str] = {
    "alias": "Another name for the actor; the statement names who uses it.",
    "mitre-group": "The MITRE ATT&CK group ID (G####).",
    "origin": "Assessed origin or sponsorship; always a judgment.",
    "motivation": "financial, espionage, disruption, ideology or other; the statement gives the basis.",
    "targets-sector": "A sector the actor targets.",
    "targets-region": "A country or region the actor targets.",
    "campaign": "A dated event in the actor's history; the value is YYYY, YYYY-MM or YYYY-MM-DD.",
    "uses-malware": "A malware family the actor uses.",
    "uses-tool": "A dual-use or living-off-the-land tool the actor uses.",
    "exploits": "A vulnerability (CVE ID) the actor exploits.",
    "intent": "Intent to target this organisation: high, medium or low; the statement gives the basis.",
    "capability": "capability:<axis> with a value 1-5 on the capability rubric.",
}


def actor_subjects(analysis: dict[str, Any]) -> list[str]:
    """Every actor subject with at least one active claim, most-claimed first."""

    counts: dict[str, int] = {}
    for row in analysis.get("assertions", []):
        subject = str(row.get("subject_ref") or "")
        if subject.startswith(ACTOR_PREFIX) and row.get("status") == "active":
            counts[subject] = counts.get(subject, 0) + 1
    return sorted(counts, key=lambda subject: (-counts[subject], subject))


def actor_name(subject: str) -> str:
    return subject.removeprefix(ACTOR_PREFIX).replace("-", " ").strip() or subject


def claims(analysis: dict[str, Any], subject: str | None, predicate: str) -> list[dict[str, Any]]:
    """Active claims about ``subject`` with ``predicate`` (or ``predicate:*`` when it ends with ':')."""

    if subject is None:
        return []
    rows = []
    for row in analysis.get("assertions", []):
        found = str(row.get("predicate") or "")
        matches = found.startswith(predicate) if predicate.endswith(":") else found == predicate
        if row.get("subject_ref") == subject and matches and row.get("status") == "active":
            rows.append(row)
    return sorted(rows, key=lambda row: (str(row.get("created_at") or ""), str(row["id"])))


def resolve_subject(analysis: dict[str, Any], requested: str | None) -> str | None:
    """The actor a report is about: the requested one, or the only one recorded."""

    subjects = actor_subjects(analysis)
    if requested:
        subject = requested if requested.startswith(ACTOR_PREFIX) else ACTOR_PREFIX + requested
        if subject not in subjects:
            known = ", ".join(subjects) or "none"
            raise ValueError(f"no claims about {subject}; actors with claims: {known}")
        return subject
    if len(subjects) > 1:
        raise ValueError(f"several actors have claims ({', '.join(subjects)}); name one, e.g. `{subjects[0]}`")
    return subjects[0] if subjects else None
