"""Report-type registry: YAML definitions in ``reports/types/``, validated at load (#50).

@decision DEC-REPORT-TYPES-001
@title A report type is data: an audience, a tier, a marking and an ordered element list
@status accepted
@rationale Report types differ in what they say and to whom, not in how a
section is built. Declaring them as validated YAML keeps the 18 CTI types and
the investigation record reviewable side by side, lets the reference docs be
generated from the same definitions, and makes an undefined element, a missing
mandatory section or an unknown marking a load error instead of a quiet
omission.
"""

from __future__ import annotations

import re
from enum import StrEnum
from functools import cache
from importlib import resources
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pivotglass.reports.claims import ACTOR_SCOPED
from pivotglass.reports.contract import TYPE_CODE_PATTERN, OutputFormat, Pap, Tlp
from pivotglass.reports.elements import load_builtin_elements
from pivotglass.reports.elements.common import MANDATORY_ELEMENTS
from pivotglass.reports.elements.planned import PLANNED
from pivotglass.reports.pir import IntelligenceLevel

SLUG = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
DEFAULT_TYPE = "investigation-report"


class ReportDomain(StrEnum):
    STRATEGIC = "strategic"  # 1 Strategic and executive
    OPERATIONAL = "operational"  # 2 Operational and incident
    ANALYTICAL = "analytical"  # 3 Analytical and attribution
    BEHAVIORAL = "behavioral"  # 4 Attack flow and behavioral
    DETECTION = "detection"  # 5 Detection, hunting and posture
    RECORD = "record"  # the whole-investigation record


DOMAIN_LABELS = {
    ReportDomain.STRATEGIC: "Strategic and executive",
    ReportDomain.OPERATIONAL: "Operational and incident",
    ReportDomain.ANALYTICAL: "Analytical and attribution",
    ReportDomain.BEHAVIORAL: "Attack flow and behavioral",
    ReportDomain.DETECTION: "Detection, hunting and posture",
    ReportDomain.RECORD: "Investigation record",
}


class Marking(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tlp: Tlp
    pap: Pap


class TypeElement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    required: bool = True
    guidance: str = ""
    options: dict[str, Any] = Field(default_factory=dict)


class ReportType(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    number: int | None = Field(default=None, ge=1, le=18)
    code: str
    title: str = Field(min_length=1)
    domain: ReportDomain
    tier: IntelligenceLevel | None = None
    audience: tuple[str, ...] = Field(min_length=1)
    purpose: str = Field(min_length=1)
    use_when: str = ""
    related: tuple[str, ...] = ()
    default_marking: Marking
    validity_days: int | None = Field(default=None, ge=1)
    elements: tuple[TypeElement, ...] = Field(min_length=1)
    formats: tuple[OutputFormat, ...]

    @field_validator("id")
    @classmethod
    def _slug(cls, value: str) -> str:
        if not SLUG.match(value):
            raise ValueError(f"report type id {value!r} must be a lowercase slug")
        return value

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if not TYPE_CODE_PATTERN.match(value):
            raise ValueError(f"report type code {value!r} must be 2-6 uppercase letters or digits")
        return value

    @model_validator(mode="after")
    def _elements(self) -> ReportType:
        known = load_builtin_elements()
        ids = [item.id for item in self.elements]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"elements listed twice: {', '.join(duplicates)}")
        unknown = [i for i in ids if i not in known and i not in PLANNED]
        if unknown:
            raise ValueError(f"undefined elements: {', '.join(unknown)}")
        for item in self.elements:
            accepted = known[item.id].options if item.id in known else ()
            extra = sorted(set(item.options) - set(accepted))
            if extra:
                raise ValueError(f"element {item.id} does not take options: {', '.join(extra)}")
        required = {item.id for item in self.elements if item.required}
        missing = [i for i in MANDATORY_ELEMENTS if i not in required]
        if missing:
            raise ValueError(f"every report type must require: {', '.join(missing)}")
        if ids[0] != "header":
            raise ValueError("the header must be the first element")
        if OutputFormat.MARKDOWN not in self.formats or OutputFormat.JSON not in self.formats:
            raise ValueError("every report type renders to markdown and json")
        return self

    @property
    def required_elements(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.elements if item.required)

    @property
    def planned_elements(self) -> tuple[str, ...]:
        """Required elements of this type whose builders do not exist yet (reports/elements/planned.py)."""

        return tuple(item.id for item in self.elements if item.id in PLANNED and item.required)

    @property
    def planned_optional(self) -> tuple[str, ...]:
        """Optional elements not built yet: the type renders without them and says so in its gaps."""

        return tuple(item.id for item in self.elements if item.id in PLANNED and not item.required)

    @property
    def available(self) -> bool:
        return not self.planned_elements

    @property
    def building_issues(self) -> tuple[int, ...]:
        return tuple(sorted({PLANNED[i].issue for i in self.planned_elements}))


def _parse(name: str, text: str) -> ReportType:
    try:
        data = yaml.safe_load(text)
        report_type = ReportType.model_validate(data)
    except Exception as exc:
        raise ValueError(f"report type {name}: {exc}") from exc
    if f"{report_type.id}.yaml" != name:
        raise ValueError(f"report type {name}: file name must be {report_type.id}.yaml")
    return report_type


@cache
def report_types() -> dict[str, ReportType]:
    """Every built-in report type, by id. Invalid or conflicting definitions fail loudly."""

    found: dict[str, ReportType] = {}
    codes: dict[str, str] = {}
    numbers: dict[int, str] = {}
    for entry in sorted(resources.files("pivotglass.reports").joinpath("types").iterdir(), key=lambda e: e.name):
        if not entry.name.endswith(".yaml"):
            continue
        report_type = _parse(entry.name, entry.read_text(encoding="utf-8"))
        for table, key in ((codes, report_type.code), (numbers, report_type.number)):
            if key is not None and key in table:
                raise ValueError(f"report types {table[key]} and {report_type.id} share {key!r}")
            if key is not None:
                table[key] = report_type.id
        found[report_type.id] = report_type
    for report_type in found.values():
        unknown = [r for r in report_type.related if r not in found or r == report_type.id]
        if unknown:
            raise ValueError(f"report type {report_type.id}: unknown related types {', '.join(unknown)}")
    if DEFAULT_TYPE not in found:
        raise ValueError(f"the default report type {DEFAULT_TYPE} is missing")
    return dict(sorted(found.items(), key=lambda item: (item[1].number or 0, item[0])))


def get_report_type(type_id: str, *, buildable: bool = False) -> ReportType:
    """The type by id. With ``buildable``, a planned type is an error naming the issues that build it."""

    types = report_types()
    key = type_id.strip().casefold().replace("_", "-")
    if key not in types:
        raise ValueError(f"unknown report type {type_id!r}; run `report types` for the list")
    report_type = types[key]
    if buildable and not report_type.available:
        issues = ", ".join(f"#{n}" for n in report_type.building_issues)
        raise ValueError(
            f"{report_type.title} is defined but not built yet: its sections "
            f"{', '.join(report_type.planned_elements)} arrive with {issues}"
        )
    return report_type


def report_title(type_id: str) -> str:
    return get_report_type(type_id).title


def report_type_summaries() -> list[dict[str, Any]]:
    """The catalogue the interfaces show: id, number, title, domain, tier, audience, formats."""

    return [
        {
            "id": t.id,
            "number": t.number,
            "code": t.code,
            "title": t.title,
            "domain": t.domain.value,
            "domain_label": DOMAIN_LABELS[t.domain],
            "tier": t.tier.value if t.tier else None,
            "audience": list(t.audience),
            "purpose": t.purpose,
            "use_when": t.use_when,
            "available": t.available,
            "actor_scoped": any(item.id in ACTOR_SCOPED for item in t.elements),
            "building_issues": list(t.building_issues),
            "formats": [f.value for f in t.formats],
            "default_marking": {"tlp": t.default_marking.tlp.value, "pap": t.default_marking.pap.value},
        }
        for t in report_types().values()
    ]
