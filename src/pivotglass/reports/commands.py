"""The ``report`` command, shared by the web cockpit, the cyberdeck, chat and the classic console (#50).

Grammar::

    report [generate]                        preview the investigation report (Markdown)
    report types                             list report types
    report <type> [actor:<name>] [markdown|json|stix] [tlp:<x>] [pap:<x>]
                                             preview one type in one format
    report issue <type> [draft|final] [tlp:<x>] [pap:<x>] [| <change summary>]
                                             issue the next version and record it
    report history [<type>]                  list issued versions, newest first
    report open <report-id> [<version>] [markdown|json|stix]
                                             read an issued report back as issued

Previews read the workspace and write nothing. Only ``report issue`` writes,
and only a ``report_issues`` row.
"""

from __future__ import annotations

from typing import Any

from pivotglass.reports.contract import OutputFormat, Pap, ReportStatus, Tlp
from pivotglass.reports.engine import build_report, issue_report, list_issues, load_issue
from pivotglass.reports.registry import DEFAULT_TYPE, get_report_type, report_type_summaries
from pivotglass.reports.render import render

REPORT_USAGE = (
    "Usage: report [types | <type> [actor:<name>] [markdown|json|stix] [tlp:<marking>] [pap:<marking>] | "
    "issue <type> [actor:<name>] [draft|final] [tlp:<marking>] [pap:<marking>] [| <change summary>] | "
    "history [<type>] | open <report-id> [<version>] [markdown|json|stix] | "
    "write <section> | <text> | severity <level> | <reason> | "
    "recommend <1-9> | <action> | <owner> | <due> | <outcome> | outcome <result> | <findings> | "
    "yara <sha256> | <reference> | <strings> | validate <rule-id> <passed|failed|not-tested> | <test> | "
    "control <kill-chain-phase> <control-status> | <basis> | risk <severity> <confidence> | <reason> | "
    "scenario <kind> <likelihood> <severity> | <description> | <signposts> | "
    "risk-scenario <likelihood> <severity> <control-status> | <scenario> | <control> | <residual>]"
)
_MIME = {
    OutputFormat.MARKDOWN: "text/markdown", OutputFormat.JSON: "application/json",
    OutputFormat.STIX: "application/json", OutputFormat.MERMAID: "text/vnd.mermaid",
    OutputFormat.SIGMA: "application/yaml", OutputFormat.SURICATA: "text/plain", OutputFormat.YARA: "text/plain",
    OutputFormat.NAVIGATOR: "application/json",
}
_EXTENSION = {
    OutputFormat.MARKDOWN: "md", OutputFormat.JSON: "json", OutputFormat.STIX: "stix.json", OutputFormat.MERMAID: "mmd",
    OutputFormat.SIGMA: "sigma.yml", OutputFormat.SURICATA: "rules", OutputFormat.YARA: "yar",
    OutputFormat.NAVIGATOR: "layer.json",
}


def _options(words: list[str]) -> tuple[list[str], dict[str, Any]]:
    """Split ``tlp:``/``pap:``/format/status words from positional ones."""

    found: dict[str, Any] = {}
    rest: list[str] = []
    for word in words:
        lower = word.casefold()
        if lower.startswith(("tlp:", "pap:")):
            enum = Tlp if lower.startswith("tlp:") else Pap
            value = word[4:].upper()
            if value not in {m.value for m in enum}:
                choices = ", ".join(m.value for m in enum)
                raise ValueError(f"{enum.__name__.upper()} must be one of {choices}, not {value!r}")
            found[lower[:3]] = enum(value)
        elif lower in {f.value for f in _EXTENSION}:
            found["format"] = OutputFormat(lower)
        elif lower in {"draft", "final"}:
            found["status"] = ReportStatus(lower.upper())
        elif lower.startswith("actor:"):
            found["subject"] = word
        else:
            rest.append(word)
    return rest, found


def _rendered(report: Any, output: OutputFormat, workspace: str) -> dict[str, Any]:
    header = report.header
    name = header.report_id or f"{workspace}-{report.type_id}-preview"
    if header.report_id:
        name = f"{header.report_id}-v{header.version}"
    return {
        "title": f"{header.title} · {header.report_id or 'preview'}",
        "format": output.value,
        "text": render(report, output),
        "filename": f"{name}.{_EXTENSION[output]}",
        "mime": _MIME[output],
        "type_id": report.type_id,
        "subject": report.subject,
        "report_id": header.report_id,
        "version": header.version,
        "status": header.status.value,
        "marking": header.marking,
        "complete": report.complete,
        "missing_required": list(report.missing_required),
    }


def execute_report_command(text: str | tuple[str, ...], workspace_mgr: Any) -> dict[str, Any]:
    """Run one ``report`` command (without the leading word) and return structured data."""

    raw = text if isinstance(text, str) else " ".join(text)
    command, _, summary = raw.partition("|")
    words = command.split()
    try:
        workspace = str(workspace_mgr.active)
    except RuntimeError:
        workspace = "workspace"
    if words and words[0].casefold() == "generate":  # long-standing spelling of the bare preview
        words = words[1:]
    action = words[0].casefold() if words else ""

    if action in {"write", "severity", "recommend", "outcome", "yara", "validate", "control", "risk", "scenario", "risk-scenario"}:
        from pivotglass.core.analytic_ledger import AnalyticLedger
        from pivotglass.reports.sections import record

        return record(AnalyticLedger(workspace_mgr), words, summary)
    if action == "types":
        return {"title": "Report types", "data": report_type_summaries()}
    if action == "history":
        type_id = words[1] if len(words) > 1 else None
        return {"title": "Issued reports", "data": list_issues(workspace_mgr, type_id)}
    if action == "open":
        rest, opts = _options(words[1:])
        if not rest or len(rest) > 2:
            raise ValueError(REPORT_USAGE)
        version = int(rest[1]) if len(rest) == 2 else None  # noqa: PLR2004
        report = load_issue(workspace_mgr, rest[0], version)
        return _rendered(report, opts.get("format", OutputFormat.MARKDOWN), workspace)
    if action == "issue":
        rest, opts = _options(words[1:])
        if len(rest) > 1 or "format" in opts:
            raise ValueError(REPORT_USAGE)
        report = issue_report(
            workspace_mgr,
            rest[0] if rest else DEFAULT_TYPE,
            status=opts.get("status", ReportStatus.DRAFT),
            summary=summary.strip() or None,
            tlp=opts.get("tlp"),
            pap=opts.get("pap"),
            subject=opts.get("subject"),
        )
        result = _rendered(report, OutputFormat.MARKDOWN, workspace)
        result["title"] = f"Issued {report.header.report_id} v{report.header.version} ({report.header.status.value})"
        return result

    rest, opts = _options(words)
    if summary.strip() or "status" in opts or len(rest) > 1:
        raise ValueError(REPORT_USAGE)
    report_type = get_report_type(rest[0]) if rest else get_report_type(DEFAULT_TYPE)
    report = build_report(
        workspace_mgr, report_type.id, tlp=opts.get("tlp"), pap=opts.get("pap"), subject=opts.get("subject")
    )
    return _rendered(report, opts.get("format", OutputFormat.MARKDOWN), workspace)
