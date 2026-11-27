"""Organisation input: profile, control inventory, environment model, telemetry (#59).

Data Pivotglass cannot collect, supplied by the analyst, stored per workspace
with provenance ``org_input``. Report sections read it; nothing else does.

@decision DEC-ORG-INPUT-001
@title Organisation input is analyst-supplied, validated, append-only, and withheld from models by default
@status accepted
@rationale Several report types need the organisation's own facts (what it
runs, which controls see which techniques, how its network connects, what its
logs recorded). Estimating them would turn a report into fiction, so a missing
input is shown as missing. Inputs are validated on import, stored as
append-only rows so an earlier profile is never silently overwritten, and the
current state is the latest import of each kind. Because this is the
organisation's own sensitive data, it is not shown to a model unless the
analyst turns ``org share-with-model on`` for the workspace.

File format for ``org import <path>`` (YAML or JSON; every section optional)::

    profile:
      name: Example Health
      industry: [healthcare]
      regions: [Western Europe]
      technology: [{vendor: Example, product: Gateway, version: "9.1.0", where: VPN edge}]
      crown_jewels: [{name: Patient records, data: [PHI], impact: critical}]
      vendors: [{name: Example Billing, service: billing SaaS, criticality: high}]
      capability_benchmark: {access: 3, malware: 3, evasion: 2, movement: 3, infrastructure: 3}
    controls:
      - {technique: T1071.001, control: Proxy, visibility: 2, alerting: 1, prevention: 0,
         last_tested: 2026-10-01, evidence: purple-team run 12}
    environment:
      nodes: [{id: vpn, label: VPN appliance, kind: entry}, {id: erp, label: ERP database, kind: objective, gate: AND}]
      edges: [{source: vpn, target: erp, technique: T1190, precondition: unpatched, status: assumed}]

Telemetry is imported separately with ``org telemetry <path.csv|path.json>``:
columns ``timestamp, host, source, summary`` and optional ``technique,
artifact_ref, precision``. Timestamps must carry a zone or be stated as UTC.
"""

from __future__ import annotations

import csv
import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select

from pivotglass.reports.contract import Severity, derive_gap_status

ATTACK_ID = r"^T\d{4}(?:\.\d{3})?$"
MAX_TELEMETRY_EVENTS = 50_000


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Technology(_Model):
    vendor: str = Field(min_length=1)
    product: str = Field(min_length=1)
    version: str | None = None
    where: str | None = None


class CrownJewel(_Model):
    name: str = Field(min_length=1)
    data: tuple[str, ...] = ()
    impact: Severity = Severity.HIGH


class Vendor(_Model):
    name: str = Field(min_length=1)
    service: str = ""
    criticality: Severity = Severity.MEDIUM


class Profile(_Model):
    name: str = ""
    industry: tuple[str, ...] = ()
    regions: tuple[str, ...] = ()
    technology: tuple[Technology, ...] = ()
    crown_jewels: tuple[CrownJewel, ...] = ()
    vendors: tuple[Vendor, ...] = ()
    # Self-assessed defensive maturity on the capability rubric's axes (1-5).
    capability_benchmark: dict[str, int] = Field(default_factory=dict)

    @field_validator("capability_benchmark")
    @classmethod
    def _rubric_axes(cls, value: dict[str, int]) -> dict[str, int]:
        from pivotglass.reports.rubrics import CAPABILITY_AXES

        unknown = sorted(set(value) - set(CAPABILITY_AXES))
        if unknown:
            raise ValueError(f"unknown capability axes: {', '.join(unknown)}; use {', '.join(CAPABILITY_AXES)}")
        if any(not 1 <= level <= 5 for level in value.values()):  # noqa: PLR2004
            raise ValueError("capability benchmark levels are 1-5")
        return value


class Control(_Model):
    technique: str = Field(pattern=ATTACK_ID)
    control: str = Field(min_length=1)
    visibility: int = Field(ge=0, le=2)
    alerting: int = Field(ge=0, le=2)
    prevention: int = Field(ge=0, le=2)
    last_tested: date | None = None
    evidence: str | None = None

    @property
    def gap_status(self) -> str:
        return derive_gap_status(self.visibility, self.alerting, self.prevention).value


class EnvNode(_Model):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    label: str = Field(min_length=1)
    kind: Literal["entry", "asset", "objective"] = "asset"
    gate: Literal["AND", "OR"] = "OR"  # how this node's incoming edges combine


class EnvEdge(_Model):
    source: str
    target: str
    technique: str | None = Field(default=None, pattern=ATTACK_ID)
    precondition: str = ""
    status: Literal["observed", "assumed"] = "assumed"


class Environment(_Model):
    nodes: tuple[EnvNode, ...] = ()
    edges: tuple[EnvEdge, ...] = ()

    @model_validator(mode="after")
    def _connected(self) -> Environment:
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("environment node ids must be unique")
        unknown = sorted(({e.source for e in self.edges} | {e.target for e in self.edges}) - set(ids))
        if unknown:
            raise ValueError(f"environment edges name unknown nodes: {', '.join(unknown)}")
        return self


class OrgImport(_Model):
    profile: Profile | None = None
    controls: tuple[Control, ...] | None = None
    environment: Environment | None = None

    @field_validator("controls")
    @classmethod
    def _one_row_per_technique_and_control(cls, value: tuple[Control, ...] | None) -> tuple[Control, ...] | None:
        keys = [(c.technique, c.control) for c in value or ()]
        if len(keys) != len(set(keys)):
            raise ValueError("each technique and control pair may appear once")
        return value


class TelemetryEvent(_Model):
    timestamp: datetime
    host: str = Field(min_length=1)
    source: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    technique: str | None = Field(default=None, pattern=ATTACK_ID)
    artifact_ref: str | None = None
    precision: Literal["second", "minute", "hour", "day"] = "second"

    @field_validator("timestamp")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("telemetry timestamps must carry a time zone (for example 2026-11-20T08:14:22Z)")
        return value.astimezone(timezone.utc)

    @field_validator("technique", "artifact_ref", mode="before")
    @classmethod
    def _blank(cls, value: Any) -> Any:
        return None if value in ("", None) else value


KINDS = ("profile", "controls", "environment", "telemetry", "policy")


class OrgInputs:
    """The single authority for organisation input in one workspace."""

    def __init__(self, workspace_manager: Any) -> None:
        self._workspace = workspace_manager

    def _add(self, kind: str, payload: Any, source: str) -> str:
        from pivotglass.models.database import OrganisationInput

        row_id = f"org-input-{uuid.uuid4()}"
        with self._workspace.get_session() as session:
            session.add(OrganisationInput(id=row_id, kind=kind, payload=payload, source=source[:500], created_by="human"))
            session.commit()
        return row_id

    def _latest(self, kind: str) -> Any:
        from pivotglass.models.database import OrganisationInput

        with self._workspace.get_session() as session:
            row = session.scalars(
                select(OrganisationInput).where(OrganisationInput.kind == kind)
                .order_by(OrganisationInput.created_at.desc(), OrganisationInput.id.desc())
            ).first()
            return None if row is None else {"payload": row.payload, "source": row.source, "at": row.created_at.isoformat(), "id": row.id}

    def import_file(self, path: Path) -> dict[str, Any]:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
        parsed = OrgImport.model_validate(data or {})
        recorded = {}
        for kind in ("profile", "controls", "environment"):
            value = getattr(parsed, kind)
            if value is not None:
                payload = [c.model_dump(mode="json") for c in value] if kind == "controls" else value.model_dump(mode="json")
                recorded[kind] = self._add(kind, payload, str(path.name))
        if not recorded:
            raise ValueError("the file has no profile, controls or environment section")
        return recorded

    def import_telemetry(self, path: Path) -> dict[str, Any]:
        if path.suffix.lower() == ".json":
            rows = json.loads(path.read_text(encoding="utf-8"))
            rows = rows.get("events", rows) if isinstance(rows, dict) else rows
        else:
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
        if not isinstance(rows, list) or not rows:
            raise ValueError("no telemetry events found")
        if len(rows) > MAX_TELEMETRY_EVENTS:
            raise ValueError(f"at most {MAX_TELEMETRY_EVENTS} events per import")
        events = []
        for number, row in enumerate(rows, 1):
            try:
                events.append(TelemetryEvent.model_validate({k: v for k, v in row.items() if k}).model_dump(mode="json"))
            except Exception as exc:
                raise ValueError(f"event {number}: {exc}") from exc
        events.sort(key=lambda e: e["timestamp"])
        return {"telemetry": self._add("telemetry", events, str(path.name)), "events": len(events)}

    def set_sharing(self, allowed: bool) -> str:
        return self._add("policy", {"share_with_model": allowed}, "analyst")

    def sharing_allowed(self) -> bool:
        latest = self._latest("policy")
        return bool(latest and latest["payload"].get("share_with_model"))

    def profile(self) -> Profile | None:
        latest = self._latest("profile")
        return Profile.model_validate(latest["payload"]) if latest else None

    def controls(self) -> tuple[Control, ...] | None:
        latest = self._latest("controls")
        return tuple(Control.model_validate(c) for c in latest["payload"]) if latest else None

    def environment(self) -> Environment | None:
        latest = self._latest("environment")
        return Environment.model_validate(latest["payload"]) if latest else None

    def telemetry(self) -> tuple[TelemetryEvent, ...] | None:
        latest = self._latest("telemetry")
        return tuple(TelemetryEvent.model_validate(e) for e in latest["payload"]) if latest else None

    def summary(self) -> dict[str, Any]:
        found = {}
        for kind in KINDS:
            latest = self._latest(kind)
            if latest:
                payload = latest["payload"]
                size = len(payload) if isinstance(payload, list) else None
                found[kind] = {"source": latest["source"], "imported_at": latest["at"], **({"rows": size} if size is not None else {})}
        found["share_with_model"] = self.sharing_allowed()
        return found


ORG_USAGE = "Usage: org [show] | import <path.yaml|path.json> | telemetry <path.csv|path.json> | share-with-model on|off"


def execute_org_command(text: str, workspace_mgr: Any) -> dict[str, Any]:
    words = text.split()
    store = OrgInputs(workspace_mgr)
    action = words[0].casefold() if words else "show"
    if action == "show" and len(words) <= 1:
        return {"title": "Organisation input", "data": store.summary()}
    if action in {"import", "telemetry"} and len(words) == 2:  # noqa: PLR2004
        path = Path(words[1]).expanduser()
        if not path.is_file():
            raise ValueError(f"no such file: {path}")
        result = store.import_file(path) if action == "import" else store.import_telemetry(path)
        return {"title": "Organisation input imported", "data": result}
    if action == "share-with-model" and len(words) == 2 and words[1].casefold() in {"on", "off"}:  # noqa: PLR2004
        store.set_sharing(words[1].casefold() == "on")
        state = "may now be shown" if words[1].casefold() == "on" else "is withheld from"
        return {"title": f"Organisation input {state} the model", "data": store.summary()}
    raise ValueError(ORG_USAGE)
