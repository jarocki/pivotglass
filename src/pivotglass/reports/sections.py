"""Analyst-written report content: section text, severity and recommendations (#54).

These are assertions in the analytic ledger on a ``report:`` subject, so each
keeps its author, time, status and evidence links like any other analytic
record. Report sections read them; they never become evidence.

    report write <section> | <text>
    report severity <critical|high|medium|low|informational> | <reason>
    report recommend <priority 1-9> | <action> | <owner> | <due YYYY-MM-DD> | <expected outcome>
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from pivotglass.reports.contract import Severity

SECTION_PREFIX = "report:"
TEXT, SEVERITY, RECOMMENDATION = "text", "severity", "recommendation"
WRITABLE_SECTIONS = (
    "threat_summary", "attack_narrative", "technical_mechanism", "triage_actions", "remediation_notes",
)


def _active(analysis: dict[str, Any], subject: str, predicate: str) -> list[dict[str, Any]]:
    rows = [
        row for row in analysis.get("assertions", [])
        if row.get("subject_ref") == subject and row.get("predicate") == predicate and row.get("status") == "active"
    ]
    return sorted(rows, key=lambda row: (str(row.get("created_at") or ""), str(row["id"])))


def section_texts(analysis: dict[str, Any], section: str) -> list[dict[str, Any]]:
    return _active(analysis, SECTION_PREFIX + section, TEXT)


def severity(analysis: dict[str, Any]) -> dict[str, Any] | None:
    """The latest recorded severity, or ``None``."""

    rows = _active(analysis, SECTION_PREFIX + "severity", SEVERITY)
    return rows[-1] if rows else None


def recommendations(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in _active(analysis, SECTION_PREFIX + "recommendation", RECOMMENDATION):
        try:
            fields = json.loads(row.get("object_value") or "{}")
        except json.JSONDecodeError:
            fields = {}
        rows.append({**fields, "id": row["id"], "action": row["statement"], "author": row.get("author_kind")})
    return sorted(rows, key=lambda r: (int(r.get("priority") or 9), str(r["id"])))


def record(ledger: Any, words: list[str], rest: str) -> dict[str, Any]:
    """Run ``report write|severity|recommend``; returns the created assertion id and a title."""

    from pivotglass.core.analytic_ledger import AssertionType

    verb = words[0].casefold()
    if verb == "write":
        if len(words) != 2 or words[1] not in WRITABLE_SECTIONS or not rest.strip():  # noqa: PLR2004
            raise ValueError(f"Usage: report write <{'|'.join(WRITABLE_SECTIONS)}> | <text>")
        subject, predicate, value, statement = SECTION_PREFIX + words[1], TEXT, None, rest.strip()
    elif verb == "severity":
        values = [s.value for s in Severity]
        if len(words) != 2 or words[1].casefold() not in values or not rest.strip():  # noqa: PLR2004
            raise ValueError(f"Usage: report severity <{'|'.join(values)}> | <reason>")
        subject, predicate, value, statement = SECTION_PREFIX + "severity", SEVERITY, words[1].casefold(), rest.strip()
    elif verb == "recommend":
        fields = [part.strip() for part in rest.split("|")]
        usage = "Usage: report recommend <priority 1-9> | <action> | <owner> | <due YYYY-MM-DD> | <expected outcome>"
        if len(words) != 2 or not re.fullmatch(r"[1-9]", words[1]) or len(fields) != 4 or not all(fields):  # noqa: PLR2004
            raise ValueError(usage)
        action, owner, due, outcome = fields
        try:
            date.fromisoformat(due)
        except ValueError as exc:
            raise ValueError(usage) from exc
        subject, predicate, statement = SECTION_PREFIX + "recommendation", RECOMMENDATION, action
        value = json.dumps({"priority": int(words[1]), "owner": owner, "due": due, "outcome": outcome}, sort_keys=True)
    else:
        raise ValueError("Usage: report write|severity|recommend ...")
    assertion_id = ledger.create_assertion(
        statement, assertion_type=AssertionType.JUDGMENT, subject_ref=subject, predicate=predicate, object_value=value
    )
    return {"title": f"Recorded {predicate} for the report", "data": {"assertion_id": assertion_id, "subject": subject}}
