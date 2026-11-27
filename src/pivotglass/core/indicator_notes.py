"""Analyst notes on one indicator: the single read/write path (#40).

@decision DEC-INDICATOR-NOTES-001
@title One note store per indicator, shown wherever the indicator is inspected
@status accepted
@rationale The graph inspector and the evidence drawer each had their own way to
save and read notes about an indicator, so a note written in one place did not
appear in the other. Both now go through this module, which owns the `notes`
rows keyed by the indicator's STIX ID. Every existing linked note already used
that key, so no rows needed migrating. A note is analyst context and is always
served with ``evidence: False``; it never becomes an observation.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import select

from pivotglass.models.database import AnalystNote

MAX_NOTE_LENGTH = 4_000


def serialize_note(row: AnalystNote) -> dict[str, Any]:
    return {
        "id": row.id,
        "node_ref": row.stix_object_id,
        "content": row.content,
        "created_at": row.created_at,
        "content_class": "analyst_annotation",
        "evidence": False,
    }


def add_indicator_note(workspace_manager: Any, stix_id: str, content: str, *, known_ids: Iterable[str]) -> dict[str, Any]:
    """Record one note on a stored indicator and return it as served."""

    reference = str(stix_id).strip()
    text = str(content).strip()
    if not reference or reference not in set(known_ids):
        raise ValueError("a note must attach to an indicator stored in this workspace")
    if not text:
        raise ValueError("note text is required")
    if len(text) > MAX_NOTE_LENGTH:
        raise ValueError(f"note text must be {MAX_NOTE_LENGTH} characters or fewer")
    with workspace_manager.get_session() as session:
        row = AnalystNote(content=text, stix_object_id=reference)
        session.add(row)
        session.commit()
        session.refresh(row)
        return serialize_note(row)


def indicator_notes(workspace_manager: Any, stix_ids: str | Iterable[str]) -> list[dict[str, Any]]:
    """Notes on the given indicators, oldest first."""

    references = sorted({stix_ids} if isinstance(stix_ids, str) else set(stix_ids))
    if not references:
        return []
    with workspace_manager.get_session() as session:
        rows = session.execute(
            select(AnalystNote).where(AnalystNote.stix_object_id.in_(references)).order_by(AnalystNote.id)
        ).scalars().all()
        return [serialize_note(row) for row in rows]
