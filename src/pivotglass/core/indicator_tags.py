"""Multidimensional analyst tagging of indicators.

The single authority for indicator tags. A tag places one indicator on one
analytic dimension (its infrastructure role, its ATT&CK tactic, the cluster the
analyst believes it belongs to, or its review status). Several dimensions on
the same set of indicators give the analyst a multidimensional clustering they
can group, filter, and order by, without a model deciding membership.

@decision DEC-INDICATOR-TAGS-001
@title Tags are append-only events keyed by canonical type and normalized value
@status accepted
@rationale Analysts classify indicators while reading a source, often before
           deciding to admit them. Keying by (canonical STIX type, normalized
           value) makes a tag follow the indicator across candidates, admitted
           entities, and every document that mentions it. Append-only events
           keep who-said-what-when for handoff review; current state is derived.
           Analyst promotion groups (pivot trail) stay separate: they record
           which indicators were admitted together, not what they are.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import select

from pivotglass.models.database import IndicatorTagEvent

# ATT&CK Enterprise tactics in matrix order. The order is the attack-path order
# used when grouping or sorting by the ``tactic`` dimension.
ATTACK_TACTICS: tuple[tuple[str, str, str], ...] = (
    ("reconnaissance", "TA0043", "Reconnaissance"),
    ("resource-development", "TA0042", "Resource Development"),
    ("initial-access", "TA0001", "Initial Access"),
    ("execution", "TA0002", "Execution"),
    ("persistence", "TA0003", "Persistence"),
    ("privilege-escalation", "TA0004", "Privilege Escalation"),
    ("defense-evasion", "TA0005", "Defense Evasion"),
    ("credential-access", "TA0006", "Credential Access"),
    ("discovery", "TA0007", "Discovery"),
    ("lateral-movement", "TA0008", "Lateral Movement"),
    ("collection", "TA0009", "Collection"),
    ("command-and-control", "TA0011", "Command and Control"),
    ("exfiltration", "TA0010", "Exfiltration"),
    ("impact", "TA0040", "Impact"),
)


@dataclass(frozen=True)
class TagDimension:
    name: str
    label: str
    key: str  # one-key shortcut in focus mode
    closed: bool  # closed dimensions accept only ``values``
    values: tuple[tuple[str, str], ...]  # (value, label) in display order
    ordered: bool = False  # value order is meaningful (attack path)


DIMENSIONS: tuple[TagDimension, ...] = (
    TagDimension(
        name="role",
        label="Infrastructure role",
        key="r",
        closed=False,
        values=(
            ("c2", "C2"),
            ("delivery", "Delivery"),
            ("staging", "Staging"),
            ("exfil", "Exfiltration"),
            ("phishing", "Phishing"),
            ("hosting", "Hosting / shared"),
            ("victim", "Victim"),
            ("benign", "Benign / noise"),
        ),
    ),
    TagDimension(
        name="tactic",
        label="ATT&CK tactic",
        key="a",
        closed=True,
        values=tuple((value, f"{tid} {label}") for value, tid, label in ATTACK_TACTICS),
        ordered=True,
    ),
    TagDimension(name="cluster", label="Cluster", key="c", closed=False, values=()),
    TagDimension(
        name="status",
        label="Review status",
        key="s",
        closed=True,
        values=(
            ("needs-pivot", "Needs pivot"),
            ("reviewed", "Reviewed"),
            ("false-positive", "False positive"),
        ),
    ),
)
_BY_NAME = {item.name: item for item in DIMENSIONS}
_OPEN_VALUE = re.compile(r"^[a-z0-9][a-z0-9._:/ -]{0,63}$")


def canonical_entity_type(entity_type: str) -> str:
    """Return the STIX type an extractor candidate type is admitted as."""

    value = entity_type.strip()
    return "file" if value.startswith("file-hash-") else value


def _clean_value(dimension: TagDimension, raw: str) -> str:
    value = " ".join(raw.strip().casefold().split())
    if dimension.closed:
        allowed = {item for item, _label in dimension.values}
        if value not in allowed:
            raise ValueError(
                f"'{raw}' is not a {dimension.name} value; choose one of: "
                + ", ".join(sorted(allowed))
            )
        return value
    if not _OPEN_VALUE.match(value):
        raise ValueError(
            f"{dimension.name} tags are 1-64 lowercase letters, digits, spaces or . _ : / -"
        )
    return value


def dimension_catalog() -> list[dict[str, Any]]:
    return [
        {
            "name": item.name,
            "label": item.label,
            "key": item.key,
            "closed": item.closed,
            "ordered": item.ordered,
            "values": [{"value": value, "label": label} for value, label in item.values],
        }
        for item in DIMENSIONS
    ]


class IndicatorTagAuthority:
    """Read and change the analyst's indicator tags in the active workspace."""

    def __init__(self, workspace_manager: Any) -> None:
        self._workspace = workspace_manager

    def apply(
        self,
        changes: Iterable[dict[str, Any]],
        *,
        operator: str,
    ) -> list[dict[str, Any]]:
        """Validate every change first, then record them in one transaction."""

        rows: list[IndicatorTagEvent] = []
        # Explicit, strictly increasing times keep "add then remove" in one
        # batch in submitted order when current state is derived.
        started = datetime.now(timezone.utc)
        for change in changes:
            dimension = _BY_NAME.get(str(change.get("dimension") or "").strip())
            if dimension is None:
                raise ValueError(
                    "unknown tag dimension; choose one of: " + ", ".join(_BY_NAME)
                )
            action = str(change.get("action") or "add")
            if action not in {"add", "remove"}:
                raise ValueError("tag action must be add or remove")
            entity_type = canonical_entity_type(str(change.get("entity_type") or ""))
            value = str(change.get("normalized_value") or "").strip()
            if not entity_type or not value:
                raise ValueError("tag changes need an entity_type and normalized_value")
            note = str(change.get("note") or "").strip()[:2_000] or None
            rows.append(
                IndicatorTagEvent(
                    id=f"indicator-tag-{uuid.uuid4().hex}",
                    entity_type=entity_type,
                    normalized_value=value,
                    dimension=dimension.name,
                    value=_clean_value(dimension, str(change.get("value") or "")),
                    action=action,
                    note=note,
                    created_by=operator.strip() or "human",
                    created_at=started + timedelta(microseconds=len(rows)),
                )
            )
        if not rows:
            raise ValueError("no tag changes were supplied")
        if len(rows) > 5_000:
            raise ValueError("at most 5000 tag changes can be applied at once")
        touched = {(row.entity_type, row.normalized_value) for row in rows}
        with self._workspace.get_session() as session:
            session.add_all(rows)
            session.commit()
        return self.current(touched)

    def current(
        self, indicators: set[tuple[str, str]] | None = None
    ) -> list[dict[str, Any]]:
        """Return active tags, optionally only for ``(entity_type, value)`` keys."""

        query = select(IndicatorTagEvent).order_by(
            IndicatorTagEvent.created_at, IndicatorTagEvent.id
        )
        if indicators is not None:
            if not indicators:
                return []
            values = {value for _type, value in indicators}
            query = query.where(IndicatorTagEvent.normalized_value.in_(values))
        latest: dict[tuple[str, str, str, str], IndicatorTagEvent] = {}
        with self._workspace.get_session() as session:
            for row in session.execute(query).scalars():
                key = (row.entity_type, row.normalized_value, row.dimension, row.value)
                if indicators is None or key[:2] in indicators:
                    latest[key] = row
            return [
                {
                    "entity_type": row.entity_type,
                    "normalized_value": row.normalized_value,
                    "dimension": row.dimension,
                    "value": row.value,
                    "note": row.note,
                    "created_by": row.created_by,
                    "created_at": row.created_at.isoformat(),
                }
                for row in latest.values()
                if row.action == "add"
            ]
