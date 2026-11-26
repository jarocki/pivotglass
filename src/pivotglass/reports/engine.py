"""Build, issue and read back reports (#50).

@decision DEC-REPORT-ISSUE-001
@title An issued report is an immutable, versioned record with a content hash
@status accepted
@rationale A report handed to someone must be identifiable and reproducible
later, even after the workspace changes. Issuing stores the complete JSON
rendering with a SHA-256 hash in ``report_issues``; every format re-renders
from that payload. A reissue appends the next version under the same report
id with a revision-history entry, so the history is recorded, not typed. A
report with pending model drafts can only be issued as DRAFT.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from pivotglass import __version__
from pivotglass.reports.contract import (
    REPORT_ID_PATTERN,
    Pap,
    ReportHeader,
    ReportStatus,
    Revision,
    SourceCitation,
    Tlp,
    format_report_id,
)
from pivotglass.reports.elements import (
    ELEMENTS,
    ElementResult,
    ElementStatus,
    ReportContext,
    build_element,
    load_builtin_elements,
)
from pivotglass.reports.elements.common import LATE_ELEMENTS
from pivotglass.reports.registry import ReportType, get_report_type

if TYPE_CHECKING:
    from pivotglass.core.workspace import WorkspaceManager

REPORT_FORMAT = "pivotglass-report-v1"


class Report(BaseModel):
    """A built report: header, element results in type order, and its completeness."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    format: str = REPORT_FORMAT
    type_id: str
    header: ReportHeader
    elements: tuple[ElementResult, ...]
    complete: bool
    missing_required: tuple[str, ...]
    pending_model_drafts: int

    def element(self, element_id: str) -> ElementResult | None:
        return next((item for item in self.elements if item.element_id == element_id), None)

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def content_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


class _Issue(BaseModel):
    report_id: str
    version: int
    status: ReportStatus
    revisions: tuple[Revision, ...]
    tlp: Tlp
    pap: Pap


def build_report(
    workspace_mgr: WorkspaceManager,
    type_id: str = "investigation-report",
    *,
    now: datetime | None = None,
    tlp: Tlp | None = None,
    pap: Pap | None = None,
    _issue: _Issue | None = None,
) -> Report:
    """Build a report from the workspace's current authorities. Reads only; never writes."""

    report_type = get_report_type(type_id)
    load_builtin_elements()
    context = ReportContext(workspace_mgr, now=now or datetime.now(timezone.utc))
    context.options = {item.id: dict(item.options) for item in report_type.elements}
    for item in report_type.elements:
        if item.id not in LATE_ELEMENTS:
            context.results[item.id] = build_element(ELEMENTS[item.id], context)
    context.results["sources"] = build_element(ELEMENTS["sources"], context)
    context.results["gaps_limitations"] = build_element(ELEMENTS["gaps_limitations"], context)
    context.header = _header(report_type, context, tlp, pap, _issue)
    context.results["header"] = build_element(ELEMENTS["header"], context)

    ordered = tuple(context.results[item.id] for item in report_type.elements)
    missing = tuple(
        item.id for item in report_type.elements if item.required and context.results[item.id].status is ElementStatus.EMPTY
    )
    return Report(
        type_id=report_type.id,
        header=context.header,
        elements=ordered,
        complete=not missing,
        missing_required=missing,
        pending_model_drafts=sum(result.pending_model_drafts for result in ordered),
    )


def _header(
    report_type: ReportType, context: ReportContext, tlp: Tlp | None, pap: Pap | None, issue: _Issue | None
) -> ReportHeader:
    pir = context.pir
    pirs: list[str] = []
    if pir.get("question"):
        label = f" ({pir['category_label']}, {pir['level_label']})" if pir.get("category_label") else ""
        pirs.append(f"{pir['question']}{label}")
    sources = tuple(
        SourceCitation(
            name=row["name"],
            reference=f"{row['runs']} run(s), {row['objects']} object(s)",
            reliability=row["reliability"],
            credibility=row["credibility"],
        )
        for row in context.results["sources"].content.get("sources", [])
    )
    valid_until = (
        (context.now + timedelta(days=report_type.validity_days)).date() if report_type.validity_days else None
    )
    return ReportHeader(
        report_id=issue.report_id if issue else None,
        type_id=report_type.id,
        title=report_type.title,
        version=issue.version if issue else 0,
        status=issue.status if issue else ReportStatus.DRAFT,
        issued_at=context.now,
        tlp=issue.tlp if issue else (tlp or report_type.default_marking.tlp),
        pap=issue.pap if issue else (pap or report_type.default_marking.pap),
        audience=report_type.audience,
        pirs=tuple(pirs),
        valid_until=valid_until,
        producer=f"Pivotglass {__version__} · workspace {context.workspace_name}",
        sources=sources,
        revision_history=issue.revisions if issue else (),
    )


# --- issuing ----------------------------------------------------------------


def _session(workspace_mgr: WorkspaceManager) -> Session:
    return workspace_mgr.get_session()


def issue_report(
    workspace_mgr: WorkspaceManager,
    type_id: str = "investigation-report",
    *,
    status: ReportStatus = ReportStatus.DRAFT,
    summary: str | None = None,
    tlp: Tlp | None = None,
    pap: Pap | None = None,
    issued_by: str = "human",
    now: datetime | None = None,
) -> Report:
    """Issue the next version of this type's report for the active investigation, or its first version."""

    from pivotglass.models.database import ReportIssue

    report_type = get_report_type(type_id)
    now = now or datetime.now(timezone.utc)
    preview = build_report(workspace_mgr, report_type.id, now=now, tlp=tlp, pap=pap)
    if status is ReportStatus.FINAL and preview.pending_model_drafts:
        raise ValueError(
            f"{preview.pending_model_drafts} model draft(s) are pending analyst review; issue as DRAFT or review them first"
        )
    investigation_id = _investigation_id(workspace_mgr)
    with _session(workspace_mgr) as session:
        latest = session.scalars(
            select(ReportIssue)
            .where(ReportIssue.type_id == report_type.id, ReportIssue.investigation_id == investigation_id)
            .order_by(ReportIssue.issued_at.desc(), ReportIssue.version.desc())
        ).first()
        if latest is None:
            report_id = format_report_id(report_type.code, now.year, _next_sequence(session, report_type.code, now.year))
            previous: tuple[Revision, ...] = ()
            marking_tlp = tlp or report_type.default_marking.tlp
            marking_pap = pap or report_type.default_marking.pap
        else:
            report_id = latest.report_id
            previous = Report.model_validate(latest.payload).header.revision_history
            marking_tlp = tlp or Tlp(latest.tlp)
            marking_pap = pap or Pap(latest.pap)
        version = len(previous) + 1
        revision = Revision(
            version=version,
            issued_at=now,
            status=status,
            summary=(summary or "").strip() or ("First issue" if version == 1 else "Reissued with current evidence"),
        )
        issue = _Issue(
            report_id=report_id,
            version=version,
            status=status,
            revisions=(*previous, revision),
            tlp=marking_tlp,
            pap=marking_pap,
        )
        report = build_report(workspace_mgr, report_type.id, now=now, _issue=issue)
        session.add(
            ReportIssue(
                id=f"report-issue-{uuid.uuid4()}",
                report_id=report_id,
                version=version,
                type_id=report_type.id,
                status=status.value,
                tlp=issue.tlp.value,
                pap=issue.pap.value,
                investigation_id=investigation_id,
                pir_category=(report.element("pir_verdict").content.get("category") if report.element("pir_verdict") else None),
                complete=int(report.complete),
                element_statuses={item.element_id: item.status.value for item in report.elements},
                content_hash=report.content_hash(),
                payload=report.model_dump(mode="json"),
                summary=revision.summary,
                issued_by=issued_by,
                issued_at=now.replace(tzinfo=None),
            )
        )
        session.commit()
    return report


def _investigation_id(workspace_mgr: WorkspaceManager) -> str | None:
    from pivotglass.core.analytic_ledger import AnalyticLedger
    from pivotglass.core.information_requirements import active_investigation_row

    row = active_investigation_row(AnalyticLedger(workspace_mgr).snapshot())
    return str(row["id"]) if row else None


def _next_sequence(session: Session, code: str, year: int) -> int:
    from pivotglass.models.database import ReportIssue

    prefix = f"PG-{code}-{year:04d}-"
    existing = session.scalars(select(ReportIssue.report_id).where(ReportIssue.report_id.like(prefix + "%"))).all()
    numbers = [int(match["seq"]) for rid in existing if (match := REPORT_ID_PATTERN.match(rid))]
    return max(numbers, default=0) + 1


def list_issues(workspace_mgr: WorkspaceManager, type_id: str | None = None) -> list[dict[str, Any]]:
    """Every issued version, newest first, without payloads."""

    from pivotglass.models.database import ReportIssue

    query = select(ReportIssue).order_by(ReportIssue.issued_at.desc(), ReportIssue.version.desc())
    if type_id:
        query = query.where(ReportIssue.type_id == get_report_type(type_id).id)
    with _session(workspace_mgr) as session:
        return [
            {
                "report_id": row.report_id,
                "version": row.version,
                "type_id": row.type_id,
                "status": row.status,
                "marking": f"TLP:{row.tlp} · PAP:{row.pap}",
                "complete": bool(row.complete),
                "issued_at": row.issued_at.replace(tzinfo=timezone.utc).isoformat(),
                "summary": row.summary,
                "content_hash": row.content_hash,
            }
            for row in session.scalars(query).all()
        ]


def load_issue(workspace_mgr: WorkspaceManager, report_id: str, version: int | None = None) -> Report:
    """Read an issued report back exactly as issued; the stored hash must still match."""

    from pivotglass.models.database import ReportIssue

    query = select(ReportIssue).where(ReportIssue.report_id == report_id.strip().upper())
    query = query.where(ReportIssue.version == version) if version else query.order_by(ReportIssue.version.desc())
    with _session(workspace_mgr) as session:
        row = session.scalars(query).first()
        if row is None:
            suffix = f" version {version}" if version else ""
            raise ValueError(f"no issued report {report_id}{suffix}")
        report = Report.model_validate(row.payload)
        if report.content_hash() != row.content_hash:
            raise ValueError(f"issued report {row.report_id} v{row.version} does not match its content hash")
        return report
