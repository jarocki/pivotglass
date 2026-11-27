"""Export a set of indicators with their workspace context (#33).

@decision DEC-INDICATOR-EXPORT-001
@title Focus-mode exports are built server-side from the indicator-context authority
@status accepted
@rationale The analyst exports exactly the indicators the focus filter shows.
Tags, first-seen time and observing sources come from
IndicatorContextAuthority, the same source the focus list reads, so the file
matches the screen. STIX objects are built with python-stix2 so they validate.
Defanging applies only to CSV: a defanged value is not a valid STIX value, so
the STIX bundle always carries real values.
Spreadsheet formula prefixes are neutralised in CSV cells.
"""

from __future__ import annotations

import csv
import io
import ipaddress
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import stix2

from pivotglass.core.document_entity_extraction import defang_indicator_value
from pivotglass.core.indicator_context import IndicatorContextAuthority, indicator_key
from pivotglass.core.indicator_tags import canonical_entity_type
from pivotglass.models.stix import dict_to_stix

MAX_EXPORT = 2_000
CSV_COLUMNS = (
    "value", "type", "role", "tactic", "cluster", "other_tags",
    "source_document", "observed_by", "first_seen",
)
NAMED_DIMENSIONS = ("role", "tactic", "cluster")
_ATTACK_NAMESPACE = uuid.UUID("6f1c0e52-49f4-5d0c-9a4c-8c0f6b2f8e41")


def _csv_safe(value: str) -> str:
    return f"'{value}" if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value


def _rows(
    workspace_manager: Any, indicators: Sequence[tuple[str, str]], source_label: str, occurrence_id: str | None
) -> list[dict[str, Any]]:
    wanted: dict[str, tuple[str, str]] = {}
    for entity_type, value in indicators:
        canonical = canonical_entity_type(str(entity_type))
        clean = str(value).strip()
        if clean:
            wanted.setdefault(indicator_key(canonical, clean), (canonical, clean))
    if len(wanted) > MAX_EXPORT:
        raise ValueError(f"at most {MAX_EXPORT} indicators can be exported at once")
    context = IndicatorContextAuthority(workspace_manager).context(
        list(wanted.values()), current_occurrence_id=occurrence_id
    ) if wanted else {}
    rows = []
    for key, (entity_type, value) in wanted.items():
        item = context.get(key, {})
        tags: dict[str, list[str]] = {}
        for tag in item.get("tags", []):
            tags.setdefault(str(tag["dimension"]), []).append(str(tag["value"]))
        rows.append({
            "value": value,
            "type": entity_type,
            "tags": {dimension: sorted(set(values)) for dimension, values in sorted(tags.items())},
            "source_document": source_label,
            "observed_by": [str(entry["source"]) for entry in item.get("observed_by", [])],
            "first_seen": item.get("first_seen"),
        })
    return rows


def _csv(rows: list[dict[str, Any]], defanged: bool) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        tags = row["tags"]
        other = [f"{dim}:{value}" for dim, values in tags.items() if dim not in NAMED_DIMENSIONS for value in values]
        record = {
            "value": defang_indicator_value(row["value"], row["type"]) if defanged else row["value"],
            "type": row["type"],
            **{dim: ";".join(tags.get(dim, [])) for dim in NAMED_DIMENSIONS},
            "other_tags": ";".join(other),
            "source_document": row["source_document"],
            "observed_by": ";".join(row["observed_by"]),
            "first_seen": row["first_seen"] or "",
        }
        writer.writerow({key: _csv_safe(str(value)) for key, value in record.items()})
    return out.getvalue()


def _stix_object(row: dict[str, Any], now: datetime) -> Any | None:
    extra = {
        "x_pivotglass_tags": [f"{dim}:{value}" for dim, values in row["tags"].items() for value in values],
        "x_pivotglass_source_document": row["source_document"],
        "x_pivotglass_observed_by": row["observed_by"],
    }
    if row["first_seen"]:
        extra["x_pivotglass_first_seen"] = row["first_seen"]
    extra = {key: value for key, value in extra.items() if value}
    if row["type"] == "vulnerability":
        return dict_to_stix({"type": "vulnerability", "name": row["value"], **extra})
    if row["type"] == "attack-pattern":
        technique = row["value"].upper()
        return stix2.AttackPattern(
            id=f"attack-pattern--{uuid.uuid5(_ATTACK_NAMESPACE, technique)}",
            name=technique, created=now, modified=now, allow_custom=True,
            external_references=[{"source_name": "mitre-attack", "external_id": technique}],
            **extra,
        )
    if row["type"] in {"ipv4-addr", "ipv6-addr"}:
        try:
            address = ipaddress.ip_address(row["value"])
        except ValueError:
            return None
        if address.version != (4 if row["type"] == "ipv4-addr" else 6) or "%" in row["value"]:
            return None
    made = dict_to_stix({"type": row["type"], "value": row["value"], **extra})
    return None if isinstance(made, dict) else made


def export_indicators(
    workspace_manager: Any,
    indicators: Sequence[tuple[str, str]],
    *,
    output: str,
    defanged: bool = False,
    source_label: str = "",
    occurrence_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return ``{text, media_type, extension, count, skipped}`` for CSV or a STIX 2.1 bundle."""

    rows = _rows(workspace_manager, indicators, source_label, occurrence_id)
    if output == "csv":
        return {"text": _csv(rows, defanged), "media_type": "text/csv", "extension": "csv",
                "count": len(rows), "skipped": []}
    if output != "stix":
        raise ValueError("export format must be csv or stix")
    moment = now or datetime.now(UTC)
    objects, skipped = [], []
    for row in rows:
        made = _stix_object(row, moment)
        if made is None:
            skipped.append(f"{row['type']}|{row['value']}")
        else:
            objects.append(made)
    if not objects:
        raise ValueError("none of these indicators has a STIX representation")
    bundle = stix2.Bundle(objects=objects, allow_custom=True)
    return {"text": json.dumps(json.loads(bundle.serialize()), indent=2), "media_type": "application/stix+json",
            "extension": "stix.json", "count": len(objects), "skipped": skipped}
