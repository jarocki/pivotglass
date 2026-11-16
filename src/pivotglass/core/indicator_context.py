"""Details on demand: what is already known about an indicator, and why.

The single authority behind every hover card, list badge and graph tooltip
that answers "how does this indicator relate to anything else?". Every item
it returns carries its basis, so the interface can keep evidence, document
position, and analyst judgment visibly distinct:

``observed``      A collection source returned it (evidence observations).
``relationship``  A stored STIX relationship, with its type.
``structural``    Derivable from the value itself (a URL's host, an email's domain).
``position``      Mentioned near another indicator in the same source text.
                  Position is a reading aid, never an asserted relationship.
``analyst``       A tag or investigation recorded by an analyst.

@decision DEC-INDICATOR-CONTEXT-001
@title One batch context authority, fetched per document, shared by list, source and graph
@status accepted
@rationale Hover must feel instant, so the client fetches context for every
           indicator in a document in one request and caches it. A single
           server authority keeps the hover card, the list badges, and graph
           tooltips from developing separate notions of "related".
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Sequence
from urllib.parse import urlsplit

from sqlalchemy import or_, select

from pivotglass.core.indicator_tags import IndicatorTagAuthority, canonical_entity_type
from pivotglass.models.database import (
    DocumentEntityCandidate,
    DocumentOccurrence,
    EvidenceObservation,
    EvidenceSource,
    PivotTrailEvent,
    Relationship,
    StixObject,
)

MAX_INDICATORS = 2_000
MAX_ITEMS_PER_SECTION = 25
MAX_PARAGRAPH_LINES = 12
_CHUNK = 500


def indicator_key(entity_type: str, normalized_value: str) -> str:
    return f"{canonical_entity_type(entity_type)}|{normalized_value}"


def _host(entity_type: str, value: str) -> str | None:
    if entity_type == "url":
        try:
            host = urlsplit(value if "://" in value else f"http://{value}").hostname
        except ValueError:
            return None
        return host.casefold().rstrip(".") if host else None
    if entity_type == "email-addr" and "@" in value:
        return value.rsplit("@", 1)[1].casefold().rstrip(".")
    return None


def _parents(domain: str) -> list[str]:
    labels = domain.split(".")
    return [".".join(labels[index:]) for index in range(1, len(labels) - 1)]


def document_relations(
    candidates: Sequence[Any], output_text: str
) -> dict[str, dict[str, list[dict[str, str]]]]:
    """Relations visible inside one document, keyed by :func:`indicator_key`.

    ``candidates`` may be extractor models, ORM rows, or dicts with
    ``entity_type``, ``normalized_value``, ``start_char`` and ``start_line``.
    """

    def field(item: Any, name: str) -> Any:
        return item[name] if isinstance(item, dict) else getattr(item, name)

    paragraph_starts = [0]
    cursor = output_text.find("\n\n")
    while cursor >= 0:
        paragraph_starts.append(cursor + 2)
        cursor = output_text.find("\n\n", cursor + 2)

    # Extracted HTML and PDF text often has no blank lines, which would make the
    # whole document one "paragraph". Blocks longer than this are not treated
    # as paragraphs, so nearness stays meaningful.
    boundaries = [*paragraph_starts, len(output_text) + 2]
    oversized = {
        index
        for index in range(len(paragraph_starts))
        if output_text.count("\n", boundaries[index], boundaries[index + 1] - 2) >= MAX_PARAGRAPH_LINES
    }
    if len(paragraph_starts) == 1:
        # No blank lines at all: the text has no paragraph structure to report.
        oversized.add(0)

    def paragraph(offset: int) -> int:
        low, high = 0, len(paragraph_starts) - 1
        while low < high:
            middle = (low + high + 1) // 2
            if paragraph_starts[middle] <= offset:
                low = middle
            else:
                high = middle - 1
        return low

    keys: dict[str, tuple[str, str]] = {}
    lines: dict[int, set[str]] = defaultdict(set)
    paragraphs: dict[int, set[str]] = defaultdict(set)
    mentions: dict[str, tuple[set[int], set[int]]] = defaultdict(lambda: (set(), set()))
    for item in candidates:
        entity_type = canonical_entity_type(str(field(item, "entity_type")))
        value = str(field(item, "normalized_value"))
        key = indicator_key(entity_type, value)
        keys[key] = (entity_type, value)
        line = int(field(item, "start_line"))
        block = paragraph(int(field(item, "start_char")))
        lines[line].add(key)
        if block not in oversized:
            paragraphs[block].add(key)
        mentions[key][0].add(line)
        mentions[key][1].add(block)

    by_value = {value.casefold(): key for key, (_type, value) in keys.items()}
    result: dict[str, dict[str, list[dict[str, str]]]] = {}
    for key, (entity_type, value) in keys.items():
        structural: list[dict[str, str]] = []
        host = _host(entity_type, value)
        if host:
            target = by_value.get(host)
            if target and target != key:
                structural.append({"key": target, "relation": "host"})
            for parent in _parents(host):
                target = by_value.get(parent)
                if target and target != key:
                    structural.append({"key": target, "relation": "parent domain"})
        if entity_type == "domain-name":
            for parent in _parents(value.casefold()):
                target = by_value.get(parent)
                if target:
                    structural.append({"key": target, "relation": "parent domain"})
        for other, (other_type, other_value) in keys.items():
            if other == key:
                continue
            other_host = _host(other_type, other_value)
            if other_host == value.casefold():
                structural.append({"key": other, "relation": "used by"})
            elif entity_type == "domain-name" and other_type == "domain-name" and (
                other_value.casefold().endswith("." + value.casefold())
            ):
                structural.append({"key": other, "relation": "subdomain"})
        line_peers = set().union(*(lines[line] for line in mentions[key][0])) - {key}
        paragraph_peers = (
            set().union(*(paragraphs[block] for block in mentions[key][1])) - {key} - line_peers
        )
        result[key] = {
            "structural": structural[:MAX_ITEMS_PER_SECTION],
            "same_line": [{"key": peer} for peer in sorted(line_peers)][:MAX_ITEMS_PER_SECTION],
            "same_paragraph": [{"key": peer} for peer in sorted(paragraph_peers)][
                :MAX_ITEMS_PER_SECTION
            ],
        }
    return result


def _chunks(values: Sequence[str]) -> Iterable[Sequence[str]]:
    for start in range(0, len(values), _CHUNK):
        yield values[start : start + _CHUNK]


def _label(row: StixObject | None, ref: str) -> str:
    if row is None:
        return ref
    blob = row.json_blob or {}
    return str(row.value or blob.get("name") or blob.get("value") or ref)


class IndicatorContextAuthority:
    """Workspace knowledge about a batch of indicators."""

    def __init__(self, workspace_manager: Any) -> None:
        self._workspace = workspace_manager

    def context(
        self,
        indicators: Iterable[tuple[str, str]],
        *,
        current_occurrence_id: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        wanted: dict[str, tuple[str, str]] = {}
        for entity_type, value in indicators:
            clean = str(value).strip()
            if clean:
                canonical = canonical_entity_type(str(entity_type))
                wanted[indicator_key(canonical, clean)] = (canonical, clean)
        if len(wanted) > MAX_INDICATORS:
            raise ValueError(f"at most {MAX_INDICATORS} indicators can be described at once")
        result: dict[str, dict[str, Any]] = {
            key: {
                "entity": None,
                "relationships": [],
                "observed_by": [],
                "documents": [],
                "tags": [],
                "investigated_at": None,
            }
            for key in wanted
        }
        if not wanted:
            return result
        values = sorted({value for _type, value in wanted.values()})
        with self._workspace.get_session() as session:
            entities: dict[str, StixObject] = {}
            for chunk in _chunks(values):
                for row in session.execute(
                    select(StixObject).where(StixObject.value.in_(chunk))
                ).scalars():
                    key = indicator_key(row.type, row.value or "")
                    if key in result:
                        entities[row.id] = row
                        result[key]["entity"] = {"id": row.id, "type": row.type}
            ids = sorted(entities)
            ref_to_key = {
                row_id: indicator_key(row.type, row.value or "") for row_id, row in entities.items()
            }

            rels: list[Relationship] = []
            for chunk in _chunks(ids):
                rels.extend(
                    session.execute(
                        select(Relationship).where(
                            or_(Relationship.source_ref.in_(chunk), Relationship.target_ref.in_(chunk))
                        ).order_by(Relationship.created_at.desc())
                    ).scalars()
                )
            other_refs = sorted(
                {rel.target_ref for rel in rels} | {rel.source_ref for rel in rels}
            )
            labels: dict[str, StixObject] = {}
            for chunk in _chunks(other_refs):
                for row in session.execute(
                    select(StixObject).where(StixObject.id.in_(chunk))
                ).scalars():
                    labels[row.id] = row
            for rel in rels:
                for own, other, direction in (
                    (rel.source_ref, rel.target_ref, "out"),
                    (rel.target_ref, rel.source_ref, "in"),
                ):
                    key = ref_to_key.get(own)
                    if key is None or own == other:
                        continue
                    section = result[key]["relationships"]
                    if len(section) >= MAX_ITEMS_PER_SECTION:
                        continue
                    other_row = labels.get(other)
                    section.append(
                        {
                            "relationship_type": rel.relationship_type,
                            "direction": direction,
                            "other_ref": other,
                            "other_label": _label(other_row, other),
                            "other_type": other_row.type if other_row else other.split("--")[0],
                            "basis": "relationship",
                        }
                    )

            sources: dict[str, str] = {
                row.id: row.name for row in session.execute(select(EvidenceSource)).scalars()
            }
            seen: dict[tuple[str, str], dict[str, Any]] = {}
            for chunk in _chunks(ids):
                for obs in session.execute(
                    select(EvidenceObservation).where(EvidenceObservation.entity_ref.in_(chunk))
                ).scalars():
                    key = ref_to_key[obs.entity_ref]
                    name = sources.get(obs.source_id, obs.source_id)
                    entry = seen.setdefault(
                        (key, name), {"source": name, "count": 0, "latest": "", "basis": "observed"}
                    )
                    entry["count"] += 1
                    entry["latest"] = max(entry["latest"], obs.fetched_at or "")
            for (key, _name), entry in sorted(seen.items(), key=lambda item: item[1]["latest"], reverse=True):
                if len(result[key]["observed_by"]) < MAX_ITEMS_PER_SECTION:
                    result[key]["observed_by"].append(entry)

            occurrences = {
                row.id: (row.filename, row.content_sha256)
                for row in session.execute(select(DocumentOccurrence)).scalars()
            }
            current_content = occurrences.get(current_occurrence_id or "", (None, None))[1]
            docs: dict[tuple[str, str], dict[str, Any]] = {}
            for chunk in _chunks(values):
                for cand in session.execute(
                    select(DocumentEntityCandidate).where(
                        DocumentEntityCandidate.normalized_value.in_(chunk)
                    )
                ).scalars():
                    key = indicator_key(cand.entity_type, cand.normalized_value)
                    filename, content = occurrences.get(cand.occurrence_id, (cand.occurrence_id, None))
                    # Re-ingesting identical bytes is one source, not several.
                    if key not in result or cand.occurrence_id == current_occurrence_id or (
                        content is not None and content == current_content
                    ):
                        continue
                    entry = docs.setdefault(
                        (key, content or cand.occurrence_id),
                        {
                            "occurrence_id": cand.occurrence_id,
                            "filename": filename,
                            "mentions": 0,
                            "copies": set(),
                            "admitted": False,
                        },
                    )
                    entry["copies"].add(cand.occurrence_id)
                    if len(entry["copies"]) == 1:
                        entry["mentions"] += 1
                    entry["admitted"] = entry["admitted"] or cand.state == "admitted"
            for entry in docs.values():
                entry["copies"] = len(entry["copies"])
            for (key, _occurrence), entry in docs.items():
                if len(result[key]["documents"]) < MAX_ITEMS_PER_SECTION:
                    result[key]["documents"].append(entry)

            by_label = {value: key for key, (_type, value) in wanted.items()}
            for chunk in _chunks(values):
                for event in session.execute(
                    select(PivotTrailEvent).where(
                        PivotTrailEvent.to_kind == "indicator",
                        PivotTrailEvent.action == "investigated",
                        PivotTrailEvent.to_label.in_(chunk),
                    )
                ).scalars():
                    key = by_label.get(event.to_label)
                    if key:
                        stamp = event.created_at.isoformat()
                        current = result[key]["investigated_at"]
                        result[key]["investigated_at"] = max(current or "", stamp)

        for tag in IndicatorTagAuthority(self._workspace).current(set(wanted.values())):
            key = indicator_key(tag["entity_type"], tag["normalized_value"])
            if key in result:
                result[key]["tags"].append(tag)
        return result

