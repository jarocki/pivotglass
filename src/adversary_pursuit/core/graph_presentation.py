"""Durable presentation state for the editable investigation graph.

This module is the sole authority for saved graph layouts. Layout records may
store coordinates, viewport, filter text, and analyst display labels. They may
not store nodes, edges, evidence, or relationships; those always come from the
workspace graph authorities at render time.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from adversary_pursuit.models.database import GraphPresentationLayout

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}$")
_MAX_LAYOUTS = 20
_MAX_NODES = 1_000
_MAX_LABEL_LENGTH = 160
_COORDINATE_LIMIT = 100_000.0


def graph_fingerprint(node_refs: set[str], edge_keys: set[str]) -> str:
    """Return a stable identity for the exact graph topology in scope."""

    payload = json.dumps(
        {"nodes": sorted(node_refs), "edges": sorted(edge_keys)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class GraphPresentationAuthority:
    """Validate and persist graph presentation independently from graph truth."""

    def __init__(self, workspace_manager: Any) -> None:
        self.workspace_manager = workspace_manager

    def list(self) -> list[dict[str, Any]]:
        """Return saved layouts newest first without resolving graph state."""

        self.workspace_manager._ensure_active()
        with self.workspace_manager.get_session() as session:
            rows = (
                session.execute(
                    select(GraphPresentationLayout).order_by(
                        GraphPresentationLayout.updated_at.desc(),
                        GraphPresentationLayout.name.asc(),
                    )
                )
                .scalars()
                .all()
            )
            return [self._serialize(row) for row in rows]

    def resolve(
        self,
        name: str,
        *,
        current_node_refs: set[str],
        current_edge_keys: set[str],
    ) -> dict[str, Any]:
        """Load a layout and report graph drift without hiding it."""

        normalized = self._validate_name(name)
        self.workspace_manager._ensure_active()
        with self.workspace_manager.get_session() as session:
            row = session.execute(
                select(GraphPresentationLayout).where(
                    GraphPresentationLayout.name == normalized
                )
            ).scalar_one_or_none()
            if row is None:
                raise ValueError(f"saved graph layout does not exist: {normalized}")
            result = self._serialize(row)
        saved_refs = set(result["node_positions"])
        result["node_positions"] = {
            reference: point
            for reference, point in result["node_positions"].items()
            if reference in current_node_refs
        }
        result["missing_node_refs"] = sorted(saved_refs - current_node_refs)
        result["new_node_refs"] = sorted(current_node_refs - saved_refs)
        current_fingerprint = graph_fingerprint(current_node_refs, current_edge_keys)
        result["current_graph_fingerprint"] = current_fingerprint
        result["topology_changed"] = result["graph_fingerprint"] != current_fingerprint
        return result

    def save(
        self,
        name: str,
        *,
        node_positions: dict[str, Any],
        viewport: dict[str, Any],
        filter_text: str,
        labels: dict[str, Any] | None,
        pinned_refs: list[Any] | tuple[Any, ...] | None,
        current_node_refs: set[str],
        current_edge_keys: set[str],
        created_by: str = "human",
    ) -> dict[str, Any]:
        """Create or replace one bounded presentation record."""

        normalized = self._validate_name(name)
        positions = self._validate_positions(node_positions, current_node_refs)
        clean_viewport = self._validate_viewport(viewport)
        clean_filter = str(filter_text).strip()[:256]
        clean_labels = self._validate_labels(labels or {}, current_node_refs)
        clean_pins = self._validate_pins(pinned_refs or [], current_node_refs)
        actor = str(created_by).strip()[:80] or "human"
        fingerprint = graph_fingerprint(current_node_refs, current_edge_keys)
        layout_id = f"graph-layout-{hashlib.sha256(normalized.casefold().encode()).hexdigest()[:24]}"
        now = datetime.now(timezone.utc)

        self.workspace_manager._ensure_active()
        with self.workspace_manager.get_session() as session:
            row = session.execute(
                select(GraphPresentationLayout).where(
                    GraphPresentationLayout.name == normalized
                )
            ).scalar_one_or_none()
            if row is None:
                count = len(session.execute(select(GraphPresentationLayout.id)).scalars().all())
                if count >= _MAX_LAYOUTS:
                    raise ValueError(f"a workspace may contain at most {_MAX_LAYOUTS} saved layouts")
                row = GraphPresentationLayout(
                    id=layout_id,
                    name=normalized,
                    created_by=actor,
                    created_at=now,
                )
                session.add(row)
            row.graph_fingerprint = fingerprint
            row.node_positions = positions
            row.pinned_refs = clean_pins
            row.viewport = clean_viewport
            row.filter_text = clean_filter
            row.labels = clean_labels
            row.updated_at = now
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def delete(self, name: str) -> bool:
        """Delete presentation state only; graph and evidence remain untouched."""

        normalized = self._validate_name(name)
        self.workspace_manager._ensure_active()
        with self.workspace_manager.get_session() as session:
            row = session.execute(
                select(GraphPresentationLayout).where(
                    GraphPresentationLayout.name == normalized
                )
            ).scalar_one_or_none()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True

    @staticmethod
    def _validate_name(name: str) -> str:
        normalized = str(name).strip()
        if not _NAME_RE.fullmatch(normalized):
            raise ValueError(
                "layout name must be 1-64 letters, numbers, spaces, periods, underscores, or hyphens"
            )
        return normalized

    @staticmethod
    def _number(value: Any, label: str) -> float:
        if isinstance(value, bool):
            raise ValueError(f"{label} must be numeric")
        number = float(value)
        if not math.isfinite(number) or abs(number) > _COORDINATE_LIMIT:
            raise ValueError(f"{label} is outside the supported presentation range")
        return round(number, 3)

    @classmethod
    def _validate_positions(
        cls, positions: dict[str, Any], current_node_refs: set[str]
    ) -> dict[str, dict[str, float]]:
        if not isinstance(positions, dict):
            raise ValueError("node_positions must be an object")
        if len(positions) > _MAX_NODES:
            raise ValueError(f"a saved layout may contain at most {_MAX_NODES} node positions")
        unknown = sorted(set(positions) - current_node_refs)
        if unknown:
            raise ValueError(f"layout references nodes outside the current graph: {unknown[0]}")
        result: dict[str, dict[str, float]] = {}
        for reference, point in positions.items():
            if not isinstance(point, dict):
                raise ValueError(f"position for {reference} must be an object")
            result[reference] = {
                "x": cls._number(point.get("x"), f"x position for {reference}"),
                "y": cls._number(point.get("y"), f"y position for {reference}"),
            }
        return result

    @classmethod
    def _validate_viewport(cls, viewport: dict[str, Any]) -> dict[str, float]:
        if not isinstance(viewport, dict):
            raise ValueError("viewport must be an object")
        scale = cls._number(viewport.get("scale", 1), "viewport scale")
        if not 0.25 <= scale <= 4:
            raise ValueError("viewport scale must be between 0.25 and 4")
        return {
            "x": cls._number(viewport.get("x", 0), "viewport x"),
            "y": cls._number(viewport.get("y", 0), "viewport y"),
            "scale": scale,
        }

    @staticmethod
    def _validate_labels(
        labels: dict[str, Any], current_node_refs: set[str]
    ) -> dict[str, str]:
        if not isinstance(labels, dict):
            raise ValueError("labels must be an object")
        unknown = sorted(set(labels) - current_node_refs)
        if unknown:
            raise ValueError(f"layout labels reference nodes outside the current graph: {unknown[0]}")
        return {
            reference: str(label).strip()[:_MAX_LABEL_LENGTH]
            for reference, label in labels.items()
            if str(label).strip()
        }

    @staticmethod
    def _validate_pins(pinned_refs: list[Any] | tuple[Any, ...], current_node_refs: set[str]) -> list[str]:
        if not isinstance(pinned_refs, (list, tuple)):
            raise ValueError("pinned_refs must be an array")
        pins = list(dict.fromkeys(str(reference) for reference in pinned_refs))
        unknown = sorted(set(pins) - current_node_refs)
        if unknown:
            raise ValueError(f"layout pins reference nodes outside the current graph: {unknown[0]}")
        return pins[:_MAX_NODES]

    @staticmethod
    def _serialize(row: GraphPresentationLayout) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "graph_fingerprint": row.graph_fingerprint,
            "node_positions": dict(row.node_positions or {}),
            "pinned_refs": list(row.pinned_refs or []),
            "viewport": dict(row.viewport or {}),
            "filter_text": row.filter_text,
            "labels": dict(row.labels or {}),
            "created_by": row.created_by,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
