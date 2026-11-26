"""Report element runtime (#50).

An element is one section or artifact of a report. Its builder reads existing
authorities through a :class:`ReportContext` and returns an
:class:`ElementResult`: a status, structured content, citations and gaps.
Renderers consume results only; they never read an authority themselves.

@decision DEC-REPORT-ELEMENTS-001
@title Reports are assembled from elements that carry provenance and gaps
@status accepted
@rationale One report generator per report type would copy the same reads
and formatting 18 times and could not say, per section, whether content is
evidence, a method's output, analyst writing, a model draft or organisation
input. Elements are written once, reused across types, and each declares its
provenance class. An element that cannot be built returns ``empty`` with the
reason as a gap, so a report never silently omits a section.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from pivotglass.reports.contract import OutputFormat, ProvenanceClass, ReportHeader

if TYPE_CHECKING:
    from pivotglass.core.workspace import WorkspaceManager

_LOG = logging.getLogger(__name__)


class ElementStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    EMPTY = "empty"


class ElementResult(BaseModel):
    """What one element contributed to a report. Immutable once built."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    element_id: str
    title: str
    provenance: tuple[ProvenanceClass, ...] = Field(min_length=1)
    status: ElementStatus
    content: dict[str, Any] = Field(default_factory=dict)
    citations: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()
    pending_model_drafts: int = 0


@dataclass
class ReportContext:
    """Read-only access to the authorities an element may need, loaded once per report.

    A load failure is not swallowed: it is recorded in ``load_errors`` and the
    Gaps and Limitations element reports it.
    """

    workspace_mgr: WorkspaceManager
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    header: ReportHeader | None = None
    options: dict[str, dict[str, Any]] = field(default_factory=dict)
    results: dict[str, ElementResult] = field(default_factory=dict)
    load_errors: list[str] = field(default_factory=list)
    _cache: dict[str, Any] = field(default_factory=dict)

    def _load(self, key: str, label: str, loader: Callable[[], Any], empty: Any) -> Any:
        if key not in self._cache:
            try:
                self._cache[key] = loader()
            except Exception as exc:  # noqa: BLE001 - recorded and reported as a gap
                _LOG.warning("report could not read %s", label, exc_info=True)
                self.load_errors.append(f"{label} could not be read: {exc}")
                self._cache[key] = empty
        return self._cache[key]

    @property
    def workspace_name(self) -> str:
        try:
            return str(self.workspace_mgr.active)
        except RuntimeError:
            return "(unknown)"

    @property
    def analysis(self) -> dict[str, list[dict[str, Any]]]:
        def load() -> dict[str, list[dict[str, Any]]]:
            from pivotglass.core.analytic_ledger import AnalyticLedger

            return AnalyticLedger(self.workspace_mgr).snapshot()

        empty = {
            key: []
            for key in (
                "investigations", "lifecycle_items", "questions", "hypotheses", "assertions",
                "evidence_links", "method_runs", "confidence", "likelihood", "contradictions",
            )
        }
        return self._load("analysis", "the analytic ledger", load, empty)

    @property
    def investigation(self) -> dict[str, Any] | None:
        from pivotglass.core.information_requirements import active_investigation_row

        return active_investigation_row(self.analysis)

    @property
    def pir(self) -> dict[str, Any]:
        from pivotglass.reports.pir import pir_state

        return self._load("pir", "the PIR", lambda: pir_state(self.analysis), {"verdict": "no_pir"})

    @property
    def stix_objects(self) -> list[dict[str, Any]]:
        return self._load("stix", "STIX objects", self.workspace_mgr.get_stix_objects, [])

    @property
    def module_runs(self) -> list[dict[str, Any]]:
        return self._load("runs", "module runs", self.workspace_mgr.get_module_runs, [])

    @property
    def type_counts(self) -> dict[str, int]:
        return self._load("type_counts", "indicator type counts", self.workspace_mgr.get_stix_type_counts, {})

    @property
    def total_score(self) -> int:
        return self._load("score", "the pursuit score", self.workspace_mgr.get_total_score, 0)

    @property
    def dossier_state(self) -> Any:
        def load() -> Any:
            from pivotglass.dossier.state import default_deferred_state, load_dossier_state

            state = load_dossier_state(self.workspace_mgr)
            return state if state is not None else default_deferred_state()

        return self._load("dossier", "the dossier state", load, None)

    @property
    def legacy_predictions(self) -> list[Any]:
        def load() -> list[Any]:
            from pivotglass.dossier.predictions import load_predictions_log

            return list(load_predictions_log(self.workspace_mgr) or [])

        return self._load("predictions", "the legacy predictions log", load, [])

    @property
    def notes(self) -> list[dict[str, Any]]:
        def load() -> list[dict[str, Any]]:
            from sqlalchemy import select
            from sqlalchemy.orm import Session

            from pivotglass.models.database import AnalystNote

            engine = self.workspace_mgr._engine
            if engine is None:
                return []
            with Session(engine) as session:
                rows = session.scalars(select(AnalystNote).order_by(AnalystNote.id)).all()
                return [
                    {"id": row.id, "content": row.content, "created_at": str(row.created_at) if row.created_at else None}
                    for row in rows
                ]

        return self._load("notes", "analyst notes", load, [])


Builder = Callable[[ReportContext], "ElementResult"]
MarkdownRenderer = Callable[[ElementResult, OutputFormat], str]


@dataclass(frozen=True)
class ElementSpec:
    """A registered element: identity, provenance, authorities, builder and Markdown form."""

    id: str
    title: str
    provenance: tuple[ProvenanceClass, ...]
    authorities: tuple[str, ...]
    build: Builder
    markdown: MarkdownRenderer
    description: str = ""
    options: tuple[str, ...] = ()

    def result(
        self,
        status: ElementStatus,
        content: dict[str, Any] | None = None,
        *,
        citations: tuple[str, ...] | list[str] = (),
        gaps: tuple[str, ...] | list[str] = (),
        pending_model_drafts: int = 0,
    ) -> ElementResult:
        return ElementResult(
            element_id=self.id,
            title=self.title,
            provenance=self.provenance,
            status=status,
            content=content or {},
            citations=tuple(citations),
            gaps=tuple(gaps),
            pending_model_drafts=pending_model_drafts,
        )


ELEMENTS: dict[str, ElementSpec] = {}


def element(
    id: str,  # noqa: A002 - the element's id is its public name
    title: str,
    provenance: tuple[ProvenanceClass, ...],
    authorities: tuple[str, ...],
    *,
    markdown: MarkdownRenderer,
    description: str = "",
) -> Callable[[Builder], Builder]:
    """Register an element builder. Duplicate ids are a programming error."""

    def register(build: Builder) -> Builder:
        if id in ELEMENTS:
            raise RuntimeError(f"report element {id!r} is registered twice")
        ELEMENTS[id] = ElementSpec(id, title, provenance, authorities, build, markdown, description)
        return build

    return register


def build_element(spec: ElementSpec, context: ReportContext) -> ElementResult:
    """Run one builder. A builder failure becomes an ``empty`` result with the error as its gap."""

    try:
        result = spec.build(context)
    except Exception as exc:  # noqa: BLE001 - reported in the report, not hidden
        _LOG.warning("report element %s failed", spec.id, exc_info=True)
        return spec.result(ElementStatus.EMPTY, gaps=[f"{spec.title} could not be built: {exc}"])
    if result.element_id != spec.id:
        raise RuntimeError(f"element {spec.id!r} returned a result for {result.element_id!r}")
    return result


def load_builtin_elements() -> dict[str, ElementSpec]:
    """Import the built-in element modules so their builders register."""

    from pivotglass.reports.elements import common, investigation  # noqa: F401
    from pivotglass.reports.elements.planned import PLANNED

    both = sorted(set(PLANNED) & set(ELEMENTS))
    if both:
        raise RuntimeError(f"report elements both built and planned: {', '.join(both)}")
    return ELEMENTS
