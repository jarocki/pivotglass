"""The report contract every Pivotglass report type shares (#51).

@decision DEC-REPORT-CONTRACT-001
@title One module owns every report vocabulary
@status accepted
@rationale All 18 report types, every renderer and the example validator read
their terms from here, so a marking, a likelihood term or a control status
means the same thing in every report. Estimative language is not redefined:
the likelihood and confidence scales are the analytic ledger's own
(``LikelihoodTerm``, ``LIKELIHOOD_RANGES``, ``ConfidenceLevel``), re-exported
with display labels. Defanging reuses ``defang_indicator_value``; this module
only decides *when* it applies (human-readable formats, never machine ones).
"""

from __future__ import annotations

import ipaddress
import re
from datetime import date, datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pivotglass.core.analytic_ledger import (
    LIKELIHOOD_RANGES,
    ConfidenceLevel,
    LikelihoodTerm,
)
from pivotglass.core.document_entity_extraction import defang_indicator_value

__all__ = [
    "LIKELIHOOD_RANGES",
    "ConfidenceLevel",
    "LikelihoodTerm",
]

# --- Estimative language (ICD 203), reused from the analytic ledger ---------

LIKELIHOOD_LABELS: dict[LikelihoodTerm, str] = {
    LikelihoodTerm.ALMOST_NO_CHANCE: "Almost no chance",
    LikelihoodTerm.VERY_UNLIKELY: "Very unlikely",
    LikelihoodTerm.UNLIKELY: "Unlikely",
    LikelihoodTerm.ROUGHLY_EVEN_CHANCE: "Roughly even chance",
    LikelihoodTerm.LIKELY: "Likely",
    LikelihoodTerm.VERY_LIKELY: "Very likely",
    LikelihoodTerm.ALMOST_CERTAIN: "Almost certain",
}

CONFIDENCE_DEFINITIONS: dict[ConfidenceLevel, str] = {
    ConfidenceLevel.HIGH: (
        "Based on high-quality information from multiple independent sources; "
        "the judgment could still be wrong."
    ),
    ConfidenceLevel.MODERATE: (
        "Credibly sourced and plausible, but not corroborated or of sufficient "
        "quality to warrant high confidence."
    ),
    ConfidenceLevel.LOW: (
        "Based on scant, fragmented, questionable or poorly corroborated "
        "information; significant concerns about the sources remain."
    ),
}


def likelihood_phrase(term: LikelihoodTerm) -> str:
    """``Likely (55–80%)``: the term with its stated probability range."""

    low, high = LIKELIHOOD_RANGES[term]
    return f"{LIKELIHOOD_LABELS[term]} ({low:.0%}–{high:.0%})"


# --- Handling markings ------------------------------------------------------


class Tlp(StrEnum):
    """FIRST Traffic Light Protocol 2.0."""

    CLEAR = "CLEAR"
    GREEN = "GREEN"
    AMBER = "AMBER"
    AMBER_STRICT = "AMBER+STRICT"
    RED = "RED"


TLP_DEFINITIONS: dict[Tlp, str] = {
    Tlp.CLEAR: "Recipients may share without limit, subject to copyright.",
    Tlp.GREEN: "Recipients may share within their community, but not on publicly accessible channels.",
    Tlp.AMBER: "Recipients may share on a need-to-know basis within their organisation and its clients.",
    Tlp.AMBER_STRICT: "Recipients may share on a need-to-know basis within their organisation only.",
    Tlp.RED: "For the named recipients only; no further disclosure.",
}


def tlp_label(tlp: Tlp) -> str:
    return f"TLP:{tlp.value}"


class Pap(StrEnum):
    """FIRST Permissible Actions Protocol: what recipients may *do* with the indicators."""

    CLEAR = "CLEAR"
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"


PAP_DEFINITIONS: dict[Pap, str] = {
    Pap.CLEAR: "No restrictions on the actions recipients may take.",
    Pap.GREEN: "Active actions are allowed, such as blocking traffic or contacting the infrastructure.",
    Pap.AMBER: "Passive cross-checks only (for example passive DNS or public databases) that cannot alert the adversary.",
    Pap.RED: "Non-detectable actions only: internal logs and offline tools, no online lookups.",
}


def pap_label(pap: Pap) -> str:
    return f"PAP:{pap.value}"


# --- Admiralty (NATO AJP-2.1) source ratings --------------------------------


class SourceReliability(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"


SOURCE_RELIABILITY_LABELS: dict[SourceReliability, str] = {
    SourceReliability.A: "Completely reliable",
    SourceReliability.B: "Usually reliable",
    SourceReliability.C: "Fairly reliable",
    SourceReliability.D: "Not usually reliable",
    SourceReliability.E: "Unreliable",
    SourceReliability.F: "Reliability cannot be judged",
}


class InformationCredibility(StrEnum):
    CONFIRMED = "1"
    PROBABLY_TRUE = "2"
    POSSIBLY_TRUE = "3"
    DOUBTFUL = "4"
    IMPROBABLE = "5"
    CANNOT_BE_JUDGED = "6"


INFORMATION_CREDIBILITY_LABELS: dict[InformationCredibility, str] = {
    InformationCredibility.CONFIRMED: "Confirmed by other sources",
    InformationCredibility.PROBABLY_TRUE: "Probably true",
    InformationCredibility.POSSIBLY_TRUE: "Possibly true",
    InformationCredibility.DOUBTFUL: "Doubtful",
    InformationCredibility.IMPROBABLE: "Improbable",
    InformationCredibility.CANNOT_BE_JUDGED: "Truth cannot be judged",
}


# --- Severity, control status, gap status -----------------------------------


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


SEVERITY_DEFINITIONS: dict[Severity, str] = {
    Severity.CRITICAL: "Active or imminent harm to the organisation; act now.",
    Severity.HIGH: "Credible threat to the organisation's assets; act within days.",
    Severity.MEDIUM: "Relevant threat with limited exposure or mitigations in place; plan action.",
    Severity.LOW: "Little expected impact on the organisation; monitor.",
    Severity.INFORMATIONAL: "Context only; no action expected.",
}


class ControlStatus(StrEnum):
    NOT_OBSERVED = "not_observed"
    LOGGED = "logged"
    DETECTED = "detected"
    BLOCKED = "blocked"
    PREVENTED = "prevented"
    MISSED = "missed"
    NOT_APPLICABLE = "not_applicable"


CONTROL_STATUS_DEFINITIONS: dict[ControlStatus, str] = {
    ControlStatus.NOT_OBSERVED: "No telemetry shows whether the activity occurred or whether a control saw it.",
    ControlStatus.LOGGED: "The activity was recorded in logs, but nothing alerted on it.",
    ControlStatus.DETECTED: "A control raised an alert, but the activity still ran.",
    ControlStatus.BLOCKED: "A control stopped this instance after it started (for example a killed process or dropped connection).",
    ControlStatus.PREVENTED: "A control stopped the activity before it could run (for example application control or a patched flaw).",
    ControlStatus.MISSED: "The activity occurred and the control that should have seen it did not.",
    ControlStatus.NOT_APPLICABLE: "The step does not apply to this environment.",
}


class GapStatus(StrEnum):
    NOT_ASSESSED = "not_assessed"
    CRITICAL = "critical"
    MODERATE = "moderate"
    MINOR = "minor"
    NONE = "none"


GAP_SCORE_SCALE = {
    "visibility": ("0 = no relevant logs", "1 = partial logs", "2 = full logs, retained and searchable"),
    "alerting": ("0 = no alert", "1 = alert exists but is untested", "2 = alert validated by a test"),
    "prevention": ("0 = no prevention", "1 = audit or partial mode", "2 = enforced prevention"),
}

GAP_RULE = (
    "Critical when visibility is 0, or when both alerting and prevention are 0. "
    "Moderate when the best of alerting and prevention is 1. "
    "Minor when alerting or prevention is 2 but visibility is below 2. "
    "None when alerting or prevention is 2 and visibility is 2. "
    "Not assessed when any score is missing."
)


def derive_gap_status(visibility: int | None, alerting: int | None, prevention: int | None) -> GapStatus:
    """Apply ``GAP_RULE``. Gap status is always derived, never entered by hand."""

    scores = (visibility, alerting, prevention)
    if any(score is None for score in scores):
        return GapStatus.NOT_ASSESSED
    for name, score in zip(("visibility", "alerting", "prevention"), scores):
        if score not in (0, 1, 2):
            raise ValueError(f"{name} score must be 0, 1 or 2, not {score!r}")
    best_response = max(alerting, prevention)  # type: ignore[type-var]
    if visibility == 0 or best_response == 0:
        return GapStatus.CRITICAL
    if best_response == 1:
        return GapStatus.MODERATE
    if visibility < 2:  # type: ignore[operator]
        return GapStatus.MINOR
    return GapStatus.NONE


# --- Provenance and status --------------------------------------------------


class ProvenanceClass(StrEnum):
    EVIDENCE = "evidence"
    METHOD = "method"
    ANALYST = "analyst"
    MODEL_DRAFT = "model_draft"
    ORG_INPUT = "org_input"


PROVENANCE_LABELS: dict[ProvenanceClass, str] = {
    ProvenanceClass.EVIDENCE: "Evidence",
    ProvenanceClass.METHOD: "Method",
    ProvenanceClass.ANALYST: "Analyst",
    ProvenanceClass.MODEL_DRAFT: "Model draft",
    ProvenanceClass.ORG_INPUT: "Organisation input",
}


class ReportStatus(StrEnum):
    DRAFT = "DRAFT"
    FINAL = "FINAL"


# --- Report identity --------------------------------------------------------

REPORT_ID_PATTERN = re.compile(r"^PG-(?P<code>[A-Z][A-Z0-9]{1,5})-(?P<year>\d{4})-(?P<seq>\d{4,})$")
TYPE_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{1,5}$")


def format_report_id(type_code: str, year: int, sequence: int) -> str:
    """``PG-<CODE>-<YYYY>-<NNNN>``; sequence numbers are per workspace, type and year."""

    if not TYPE_CODE_PATTERN.match(type_code):
        raise ValueError(f"report type code must be 2-6 uppercase letters or digits, not {type_code!r}")
    if not 1 <= sequence:
        raise ValueError("report sequence starts at 1")
    return f"PG-{type_code}-{year:04d}-{sequence:04d}"


# --- Shared header ----------------------------------------------------------


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("report times must carry a timezone")
    return value.astimezone(timezone.utc)


class SourceCitation(BaseModel):
    """One source in a report's source list, with its Admiralty rating."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    reference: str | None = None
    reliability: SourceReliability = SourceReliability.F
    credibility: InformationCredibility = InformationCredibility.CANNOT_BE_JUDGED

    @property
    def rating(self) -> str:
        return f"{self.reliability.value}{self.credibility.value}"


class Revision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = Field(ge=1)
    issued_at: datetime
    status: ReportStatus
    summary: str = Field(min_length=1)

    @field_validator("issued_at")
    @classmethod
    def _issued_utc(cls, value: datetime) -> datetime:
        return _utc(value)


class ReportHeader(BaseModel):
    """The header every report carries. Built by the report system, never typed by hand.

    A preview (rendered, not issued) has no report id, version 0 and no
    revision history; it always renders as an unissued draft.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_id: str | None
    type_id: str
    title: str = Field(min_length=1)
    version: int = Field(ge=0)
    status: ReportStatus
    issued_at: datetime
    tlp: Tlp
    pap: Pap
    audience: tuple[str, ...] = Field(min_length=1)
    pirs: tuple[str, ...] = ()
    valid_until: date | None = None
    producer: str = Field(min_length=1)
    feedback_contact: str | None = None
    sources: tuple[SourceCitation, ...] = ()
    revision_history: tuple[Revision, ...] = ()

    @field_validator("issued_at")
    @classmethod
    def _issued_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @field_validator("report_id")
    @classmethod
    def _report_id(cls, value: str | None) -> str | None:
        if value is not None and not REPORT_ID_PATTERN.match(value):
            raise ValueError(f"report id {value!r} does not match PG-<CODE>-<YYYY>-<NNNN>")
        return value

    @model_validator(mode="after")
    def _consistent(self) -> ReportHeader:
        if self.valid_until is not None and self.valid_until < self.issued_at.date():
            raise ValueError("valid_until is before the issue date")
        if self.report_id is None:
            if self.version != 0 or self.revision_history or self.status is not ReportStatus.DRAFT:
                raise ValueError("an unissued preview has version 0, no revisions and DRAFT status")
            return self
        if not self.revision_history:
            raise ValueError("an issued report needs a revision history")
        versions = [revision.version for revision in self.revision_history]
        if versions != list(range(1, len(versions) + 1)):
            raise ValueError("revision history must list versions 1..N in order")
        if versions[-1] != self.version:
            raise ValueError("the last revision must be the header's version")
        if self.revision_history[-1].status != self.status:
            raise ValueError("the last revision's status must be the header's status")
        return self

    @property
    def issued(self) -> bool:
        return self.report_id is not None

    @property
    def marking(self) -> str:
        return f"{tlp_label(self.tlp)} · {pap_label(self.pap)}"


class Judgment(BaseModel):
    """A key judgment: likelihood (how probable) and confidence (how good the evidence), stated separately."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    statement: str = Field(min_length=1)
    likelihood: LikelihoodTerm
    confidence: ConfidenceLevel
    rationale: str = Field(min_length=1)
    citations: tuple[str, ...] = ()

    def phrase(self) -> str:
        return f"{likelihood_phrase(self.likelihood)}; {self.confidence.value} confidence"


# --- Defanging policy -------------------------------------------------------


class OutputFormat(StrEnum):
    MARKDOWN = "markdown"
    JSON = "json"
    STIX = "stix"
    CSV = "csv"
    NAVIGATOR = "navigator"
    SIGMA = "sigma"
    SURICATA = "suricata"
    YARA = "yara"
    MERMAID = "mermaid"


HUMAN_READABLE_FORMATS = frozenset({OutputFormat.MARKDOWN, OutputFormat.MERMAID})


def render_indicator(value: str, entity_type: str | None, output: OutputFormat) -> str:
    """Defang for people, never for machines: a defanged value in a rule or bundle is a broken value."""

    if output in HUMAN_READABLE_FORMATS:
        return defang_indicator_value(value, entity_type)
    return value


# --- Reserved example data --------------------------------------------------

RESERVED_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32")
)
RESERVED_DOMAINS = ("example", "example.com", "example.net", "example.org", "test", "invalid", "localhost")


def is_reserved_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return any(address.version == net.version and address in net for net in RESERVED_NETWORKS)


def is_reserved_domain(value: str) -> bool:
    name = value.strip().rstrip(".").casefold()
    return any(name == reserved or name.endswith("." + reserved) for reserved in RESERVED_DOMAINS)


def _refang(text: str) -> str:
    return (
        text.replace("[.]", ".").replace("[:]", ":").replace("[@]", "@")
        .replace("hxxps", "https").replace("hxxp", "http")
    )


_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
_IPV6 = re.compile(r"(?<![\w:])(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F:]*[0-9a-fA-F](?![\w:])")
_URL_HOST = re.compile(r"\bhttps?://(?:[^@/\s]+@)?(\[[0-9a-fA-F:]+\]|[A-Za-z0-9.-]+)")
_EMAIL_HOST = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")


def unreserved_values(text: str) -> list[str]:
    """Network values in ``text`` that are not reserved for documentation.

    Covers IPv4 and IPv6 addresses, URL hosts and email domains, defanged or
    not. Bare domain names in prose are not scanned (``contract.py`` would look
    like one); structured example indicators go through
    :func:`unreserved_indicator` instead, which checks every type.
    """

    refanged = _refang(text)
    found: list[str] = []
    for match in _IPV4.findall(refanged):
        if all(int(octet) <= 255 for octet in match.split(".")) and not is_reserved_ip(match):
            found.append(match)
    for match in _IPV6.findall(refanged):
        try:
            ipaddress.IPv6Address(match)
        except ValueError:
            continue
        if not is_reserved_ip(match):
            found.append(match)
    for host in _URL_HOST.findall(refanged) + _EMAIL_HOST.findall(refanged):
        host = host.strip("[]")
        if is_reserved_ip(host) or is_reserved_domain(host):
            continue
        try:
            ipaddress.ip_address(host)
        except ValueError:
            found.append(host)
        # an unreserved IP host is already reported by the address scan
    return list(dict.fromkeys(found))


_DOMAIN_TYPES = {"domain-name", "domain", "hostname"}
_IP_TYPES = {"ipv4-addr", "ipv6-addr", "ip", "ipv4", "ipv6"}


def unreserved_indicator(value: str, entity_type: str) -> str | None:
    """Return ``value`` if this structured example indicator is not reserved, else ``None``."""

    kind = entity_type.casefold()
    plain = _refang(value)
    if kind in _IP_TYPES:
        return None if is_reserved_ip(plain.split("/")[0]) else value
    if kind in _DOMAIN_TYPES:
        return None if is_reserved_domain(plain) else value
    return value if unreserved_values(plain) else None
