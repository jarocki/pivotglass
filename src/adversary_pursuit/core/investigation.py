"""Authoritative lifecycle records for analyst-visible investigations.

The model is deliberately UI-neutral.  Web and terminal adapters may choose
different transports, but lifecycle names, timestamps, classifications, and
operator actions come from this module.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def utc_now() -> str:
    """Return a stable, timezone-qualified timestamp."""
    return datetime.now(UTC).isoformat()


class LifecycleState(StrEnum):
    PLANNED = "planned"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    EMPTY = "empty"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class EventClass(StrEnum):
    DISCOVERY = "discovery"
    SOURCE_FAULT = "source_fault"
    OPERATOR_ACTION = "operator_action"
    SYSTEM = "system"


class ContentClass(StrEnum):
    EVIDENCE = "evidence"
    NARRATION = "narration"
    SYSTEM = "system"


TERMINAL_STATES = {
    LifecycleState.SUCCEEDED,
    LifecycleState.EMPTY,
    LifecycleState.FAILED,
    LifecycleState.SKIPPED,
    LifecycleState.CANCELLED,
}


@dataclass(frozen=True)
class InvestigationEvent:
    investigation_id: str
    event_id: str
    sequence: int
    event_class: str
    severity: str
    lifecycle: str
    content_class: str
    created_at: str
    updated_at: str
    target: str
    target_type: str
    tool: str | None = None
    source: str | None = None
    queue_position: int | None = None
    result_count: int | None = None
    artifact_ids: tuple[str, ...] = ()
    summary: str | None = None
    reason: str | None = None
    retryable: bool = False
    actions: tuple[str, ...] = ()
    briefing: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InvestigationRecord:
    investigation_id: str
    target: str
    target_type: str
    created_at: str
    lifecycle: str = LifecycleState.PLANNED
    updated_at: str = ""
    completed_at: str | None = None
    cancel_requested: bool = False
    events: list[InvestigationEvent] = field(default_factory=list)

    def snapshot(self, cursor: int = 0) -> dict[str, Any]:
        events = [event.to_dict() for event in self.events[cursor:]]
        return {
            "investigation_id": self.investigation_id,
            "target": self.target,
            "target_type": self.target_type,
            "lifecycle": self.lifecycle,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "cancel_requested": self.cancel_requested,
            "cursor": len(self.events),
            "events": events,
        }


class InvestigationStore:
    """Thread-safe in-memory session authority for investigation events."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[str, InvestigationRecord] = {}

    def create(self, target: str, target_type: str) -> InvestigationRecord:
        now = utc_now()
        record = InvestigationRecord(
            investigation_id=str(uuid.uuid4()),
            target=target,
            target_type=target_type,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._records[record.investigation_id] = record
        return record

    def append(
        self,
        investigation_id: str,
        *,
        event_class: EventClass,
        severity: str,
        lifecycle: LifecycleState,
        content_class: ContentClass,
        tool: str | None = None,
        source: str | None = None,
        queue_position: int | None = None,
        result_count: int | None = None,
        artifact_ids: tuple[str, ...] = (),
        summary: str | None = None,
        reason: str | None = None,
        retryable: bool = False,
        actions: tuple[str, ...] = (),
        briefing: dict[str, Any] | None = None,
    ) -> InvestigationEvent:
        with self._lock:
            record = self._records[investigation_id]
            now = utc_now()
            event = InvestigationEvent(
                investigation_id=investigation_id,
                event_id=f"{investigation_id}:{len(record.events) + 1}",
                sequence=len(record.events) + 1,
                event_class=event_class,
                severity=severity,
                lifecycle=lifecycle,
                content_class=content_class,
                created_at=now,
                updated_at=now,
                target=record.target,
                target_type=record.target_type,
                tool=tool,
                source=source,
                queue_position=queue_position,
                result_count=result_count,
                artifact_ids=artifact_ids,
                summary=summary,
                reason=reason,
                retryable=retryable,
                actions=actions,
                briefing=briefing,
            )
            record.events.append(event)
            record.updated_at = now
            return event

    def transition(self, investigation_id: str, lifecycle: LifecycleState) -> None:
        """Update the investigation-level lifecycle independently of probe events."""
        with self._lock:
            record = self._records[investigation_id]
            now = utc_now()
            record.lifecycle = lifecycle
            record.updated_at = now
            if lifecycle in TERMINAL_STATES:
                record.completed_at = now

    def snapshot(self, investigation_id: str, cursor: int = 0) -> dict[str, Any]:
        with self._lock:
            return self._records[investigation_id].snapshot(max(0, cursor))

    def request_cancel(self, investigation_id: str) -> bool:
        with self._lock:
            record = self._records[investigation_id]
            if record.lifecycle in TERMINAL_STATES:
                return False
            record.cancel_requested = True
            record.updated_at = utc_now()
            return True

    def cancellation_requested(self, investigation_id: str) -> bool:
        with self._lock:
            return self._records[investigation_id].cancel_requested

    def active_count(self) -> int:
        with self._lock:
            return sum(record.lifecycle not in TERMINAL_STATES for record in self._records.values())
