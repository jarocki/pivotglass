"""Analyst-written report content: section text, severity and recommendations (#54).

These are assertions in the analytic ledger on a ``report:`` subject, so each
keeps its author, time, status and evidence links like any other analytic
record. Report sections read them; they never become evidence.

    report write <section> | <text>
    report severity <critical|high|medium|low|informational> | <reason>
    report recommend <priority 1-9> | <action> | <owner> | <due YYYY-MM-DD> | <expected outcome>
    report outcome <supported|refuted|inconclusive> | <what the hunt found, including nothing>
    report yara <sample-sha256> | <reference> | <string>; <string>; ...
    report validate <rule-id> <passed|failed|not-tested> | <what was tested, against what>
    report control <kill-chain-phase> <control-status> | <telemetry source and basis>
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from pivotglass.reports.contract import Severity

SECTION_PREFIX = "report:"
TEXT, SEVERITY, RECOMMENDATION = "text", "severity", "recommendation"
OUTCOME, YARA, VALIDATION, CONTROL = "outcome", "yara-strings", "validation", "control-status"
KILL_CHAIN_PHASE_IDS = (
    "reconnaissance", "weaponization", "delivery", "exploitation", "installation", "command-and-control", "actions-on-objectives",
)
WRITABLE_SECTIONS = (
    "threat_summary", "attack_narrative", "technical_mechanism", "triage_actions", "remediation_notes",
    "hunt_hypothesis", "threat_context", "baseline_false_positives", "triage_playbook",
)
OUTCOMES = ("supported", "refuted", "inconclusive")
VALIDATION_RESULTS = ("passed", "failed", "not-tested")


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


def hunt_outcome(analysis: dict[str, Any]) -> dict[str, Any] | None:
    rows = _active(analysis, SECTION_PREFIX + "hunt_outcome", OUTCOME)
    return rows[-1] if rows else None


def yara_inputs(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in _active(analysis, SECTION_PREFIX + "yara", YARA):
        rows.append({**json.loads(row.get("object_value") or "{}"), "id": row["id"], "author": row.get("author_kind")})
    return rows


def validations(analysis: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Latest validation record per rule id."""

    found: dict[str, dict[str, Any]] = {}
    for row in _active(analysis, SECTION_PREFIX + "validation", VALIDATION):
        fields = json.loads(row.get("object_value") or "{}")
        found[fields["rule_id"]] = {**fields, "note": row["statement"], "id": row["id"], "time": str(row.get("created_at") or "")[:16]}
    return found


def control_statuses(analysis: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Latest recorded control status per kill-chain phase."""

    found: dict[str, dict[str, Any]] = {}
    for phase in KILL_CHAIN_PHASE_IDS:
        rows = _active(analysis, f"{SECTION_PREFIX}control:{phase}", CONTROL)
        if rows:
            found[phase] = {"status": rows[-1]["object_value"], "basis": rows[-1]["statement"], "id": rows[-1]["id"]}
    return found


def record(ledger: Any, words: list[str], rest: str) -> dict[str, Any]:
    """Run ``report write|severity|recommend|outcome|yara|validate``; returns the created assertion id and a title."""

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
    elif verb == "outcome":
        if len(words) != 2 or words[1].casefold() not in OUTCOMES or not rest.strip():  # noqa: PLR2004
            raise ValueError(f"Usage: report outcome <{'|'.join(OUTCOMES)}> | <what the hunt found>")
        subject, predicate, value, statement = SECTION_PREFIX + "hunt_outcome", OUTCOME, words[1].casefold(), rest.strip()
    elif verb == "yara":
        fields = [part.strip() for part in rest.split("|")]
        usage = "Usage: report yara <sample-sha256> | <reference> | <string>; <string>; ..."
        strings = [item.strip() for item in fields[-1].split(";") if item.strip()] if len(fields) == 2 else []  # noqa: PLR2004
        if len(words) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", words[1]) or len(strings) < 1 or not fields[0]:  # noqa: PLR2004
            raise ValueError(usage)
        subject, predicate = SECTION_PREFIX + "yara", YARA
        statement = f"YARA strings from sample {words[1].lower()}"
        value = json.dumps({"sha256": words[1].lower(), "reference": fields[0], "strings": strings}, sort_keys=True)
    elif verb == "validate":
        if len(words) != 3 or words[2].casefold() not in VALIDATION_RESULTS or not rest.strip():  # noqa: PLR2004
            raise ValueError(f"Usage: report validate <rule-id> <{'|'.join(VALIDATION_RESULTS)}> | <what was tested>")
        subject, predicate, statement = SECTION_PREFIX + "validation", VALIDATION, rest.strip()
        value = json.dumps({"rule_id": words[1], "result": words[2].casefold()}, sort_keys=True)
    elif verb == "control":
        from pivotglass.reports.contract import ControlStatus

        statuses = [c.value for c in ControlStatus]
        if len(words) != 3 or words[1] not in KILL_CHAIN_PHASE_IDS or words[2] not in statuses or not rest.strip():  # noqa: PLR2004
            raise ValueError(f"Usage: report control <{'|'.join(KILL_CHAIN_PHASE_IDS)}> <{'|'.join(statuses)}> | <basis>")
        subject, predicate, value, statement = f"{SECTION_PREFIX}control:{words[1]}", CONTROL, words[2], rest.strip()
    else:
        raise ValueError("Usage: report write|severity|recommend|outcome|yara|validate|control ...")
    assertion_id = ledger.create_assertion(
        statement, assertion_type=AssertionType.JUDGMENT, subject_ref=subject, predicate=predicate, object_value=value
    )
    return {"title": f"Recorded {predicate} for the report", "data": {"assertion_id": assertion_id, "subject": subject}}
