"""Workspace-owned replay protection for approved external side effects."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from adversary_pursuit.models.database import IntegrationExecution

_NAME = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


class IntegrationExecutionJournal:
    """Atomically claim exact plans and retain secret-safe outcome receipts."""

    def __init__(self, workspace_manager: Any, *, system: str, operation: str) -> None:
        if _NAME.fullmatch(system) is None or _NAME.fullmatch(operation) is None:
            raise ValueError("integration journal names must be bounded identifiers")
        self._workspace = workspace_manager
        self.system = system
        self.operation = operation

    def execution_id(self, plan_digest_sha256: str) -> str:
        self._validate_digest(plan_digest_sha256)
        return f"{self.system}:{self.operation}:{plan_digest_sha256}"

    def claim(
        self,
        plan_digest_sha256: str,
        *,
        approved_by: str,
        started_at: datetime,
    ) -> dict[str, Any]:
        """Atomically claim one exact plan before the first remote mutation."""
        execution_id = self.execution_id(plan_digest_sha256)
        if not approved_by.strip() or len(approved_by) > 254:
            raise ValueError("integration execution requires a bounded human identity")
        if started_at.utcoffset() is None:
            raise ValueError("integration execution time must include a timezone")
        try:
            with self._workspace.get_session() as session:
                existing = session.get(IntegrationExecution, execution_id)
                if existing is not None:
                    raise ValueError(
                        f"{self.system} {self.operation} is already claimed with state "
                        f"{existing.state}; inspect its receipt before any retry"
                    )
                session.add(
                    IntegrationExecution(
                        id=execution_id,
                        system=self.system,
                        operation=self.operation,
                        plan_digest_sha256=plan_digest_sha256,
                        state="in_progress",
                        approved_by=approved_by.strip(),
                        started_at=started_at,
                    )
                )
                session.flush()
                session.commit()
        except IntegrityError:
            raise ValueError(
                f"{self.system} {self.operation} was claimed concurrently; "
                "inspect its receipt before any retry"
            ) from None
        return self.get(plan_digest_sha256)

    def complete(
        self,
        plan_digest_sha256: str,
        *,
        receipt: dict[str, Any],
        completed_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Persist the sanitized receipt for an active execution claim."""
        with self._workspace.get_session() as session:
            row = session.get(IntegrationExecution, self.execution_id(plan_digest_sha256))
            if row is None or row.state != "in_progress":
                raise RuntimeError("integration completion has no active claim")
            row.state = "complete"
            row.completed_at = completed_at or datetime.now(UTC)
            row.receipt = receipt
            row.error_summary = None
            session.commit()
        return self.get(plan_digest_sha256)

    def fail(
        self,
        plan_digest_sha256: str,
        error: BaseException,
        *,
        state: str = "outcome_uncertain",
        receipt: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist a non-replayable failure without storing exception text."""
        if state not in {"outcome_uncertain", "failed_view_removed"}:
            raise ValueError("invalid integration failure state")
        with self._workspace.get_session() as session:
            row = session.get(IntegrationExecution, self.execution_id(plan_digest_sha256))
            if row is None:
                raise RuntimeError("integration failure has no active claim")
            if row.state == "complete":
                raise RuntimeError("completed integration execution cannot become failed")
            row.state = state
            row.completed_at = datetime.now(UTC)
            row.receipt = receipt
            row.error_summary = type(error).__name__
            session.commit()
        return self.get(plan_digest_sha256)

    def get(self, plan_digest_sha256: str) -> dict[str, Any]:
        """Return one sanitized persisted execution claim or receipt."""
        with self._workspace.get_session() as session:
            row = session.get(IntegrationExecution, self.execution_id(plan_digest_sha256))
            if row is None:
                raise ValueError("integration execution receipt was not found")
            return {
                "id": row.id,
                "system": row.system,
                "operation": row.operation,
                "plan_digest_sha256": row.plan_digest_sha256,
                "state": row.state,
                "approved_by": row.approved_by,
                "started_at": row.started_at,
                "completed_at": row.completed_at,
                "receipt": row.receipt,
                "error_summary": row.error_summary,
            }

    @staticmethod
    def _validate_digest(plan_digest_sha256: str) -> None:
        if _DIGEST.fullmatch(plan_digest_sha256) is None:
            raise ValueError("integration plan digest must be a lowercase SHA-256")
