"""The SQL repository of the closure days the owner adds and cancels.

It maps the `closure_day` rows to the domain's `ClosureDay` and back, on the
session of the unit of work that created it. A closure about to be cancelled is
read with `SELECT ... FOR UPDATE`, so two owners cancelling it at once take
turns and the second reads the cancellation the first committed.

Every statement stands on a key or an index. A closure is read by its primary
key. Whether a day is closed already is read through `ix_closure_day_live_day`,
which holds only the live closures, and a day holds one or two of them. The
unique index `uq_closure_day_live` has the last word on a second live closure,
and a row it refuses is raised as `DuplicateClosureDay`, recognised by SQLSTATE
and the index name read from the driver, never from its message.

Every instant written comes from the clock the use case was handed.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Final
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, or_, select

from app.application.trading.closure_ports import DuplicateClosureDay
from app.domain import closure_day as domain
from app.infrastructure.booking_mapping import in_utc, required_utc
from app.infrastructure.catalogue_uniques import UNIQUE_VIOLATION_SQLSTATE
from app.infrastructure.models import Branch, ClosureDay
from app.infrastructure.schema_ddl import CLOSURE_DAY_LIVE_INDEX_NAME

logger = logging.getLogger(__name__)

CREATED_AT_COLUMN: Final[str] = "closure_day.created_at"


class SqlClosureDayRepository:
    """Reads and writes closure days through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session

    def live_on(self, branch_id: UUID | None, day: date) -> domain.ClosureDay | None:
        """Return the live closure that already closes a branch on a day, or None.

        The branch's own closure is preferred to one for every branch, so the
        refusal names the closure the owner would cancel.
        """
        scope = (
            or_(col(ClosureDay.branch_id) == branch_id, col(ClosureDay.branch_id).is_(None))
            if branch_id is not None
            else col(ClosureDay.branch_id).is_(None)
        )
        statement = (
            select(ClosureDay, col(Branch.code))
            .outerjoin(Branch, col(Branch.id) == col(ClosureDay.branch_id))
            .where(col(ClosureDay.day) == day, col(ClosureDay.cancelled_at).is_(None), scope)
            .order_by(col(ClosureDay.branch_id).is_(None))
        )
        found = self._session.exec(statement).first()
        logger.debug(
            "trading.closure_day_live_on_read",
            extra={
                "branch_id": str(branch_id) if branch_id else None,
                "day": day.isoformat(),
                "found": found is not None,
            },
        )
        if found is None:
            return None
        row, code = found
        return closure_of(row, code)

    def get_for_update(self, closure_id: UUID) -> domain.ClosureDay | None:
        """Return the closure with this key locked for the rest of the transaction, or None."""
        statement = (
            select(ClosureDay)
            .where(col(ClosureDay.id) == closure_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = self._session.exec(statement).first()
        logger.debug(
            "trading.closure_day_locked",
            extra={"closure_id": str(closure_id), "found": row is not None},
        )
        if row is None:
            return None
        branch = self._session.get(Branch, row.branch_id) if row.branch_id else None
        return closure_of(row, branch.code if branch is not None else None)

    def add(self, closure: domain.ClosureDay, created_by_user_id: UUID) -> None:
        """Write a new live closure inside the current transaction.

        Raises:
            DuplicateClosureDay: If `uq_closure_day_live` refused it.
            IntegrityError: Unchanged, for every other fault of integrity.

        """
        self._session.add(
            ClosureDay(
                id=closure.id,
                branch_id=closure.branch_id,
                day=closure.day,
                reason=closure.reason,
                created_by_user_id=created_by_user_id,
                created_at=closure.created_at,
            )
        )
        try:
            self._session.flush()
        except IntegrityError as error:
            if _is_live_closure_violation(error):
                raise DuplicateClosureDay(closure.branch_id, closure.day) from error
            logger.error(
                "trading.closure_day_write_failed",
                extra={"closure_id": str(closure.id), "sqlstate": _sqlstate_of(error)},
            )
            raise
        logger.info(
            "trading.closure_day_row_added",
            extra={
                "closure_id": str(closure.id),
                "branch_id": str(closure.branch_id) if closure.branch_id else None,
                "day": closure.day.isoformat(),
            },
        )

    def save_cancellation(self, closure: domain.ClosureDay, cancelled_by_user_id: UUID) -> None:
        """Stamp a closure this transaction locked as cancelled, by whom and when.

        Raises:
            RuntimeError: If the closure has no row or carries no cancellation,
                which would mean a use case skipped `ClosureDay.cancelled`.

        """
        row = self._session.get(ClosureDay, closure.id)
        if row is None or closure.cancelled_at is None:
            raise RuntimeError(
                f"Attempted to save the cancellation of closure {closure.id}, which has no row "
                "or no cancellation. Read it with get_for_update and cancel it first."
            )
        row.cancelled_at = closure.cancelled_at
        row.cancelled_by_user_id = cancelled_by_user_id
        self._session.add(row)
        self._session.flush()
        logger.info("trading.closure_day_row_cancelled", extra={"closure_id": str(closure.id)})


def closure_of(row: ClosureDay, branch_code: str | None) -> domain.ClosureDay:
    """Return the domain closure for a `closure_day` row and its branch's code."""
    return domain.ClosureDay(
        id=row.id,
        branch_id=row.branch_id,
        branch_code=branch_code,
        day=row.day,
        reason=row.reason,
        created_at=required_utc(row.created_at, CREATED_AT_COLUMN),
        cancelled_at=in_utc(row.cancelled_at),
    )


def _is_live_closure_violation(error: IntegrityError) -> bool:
    """Return True when the unique index of the live closures refused a row."""
    if _sqlstate_of(error) != UNIQUE_VIOLATION_SQLSTATE:
        return False
    diagnostics = getattr(error.orig, "diag", None)
    constraint = getattr(diagnostics, "constraint_name", None) if diagnostics is not None else None
    return constraint == CLOSURE_DAY_LIVE_INDEX_NAME


def _sqlstate_of(error: IntegrityError) -> str | None:
    """Return the five character SQLSTATE the driver reported, if any."""
    state = getattr(error.orig, "sqlstate", None)
    return str(state) if state is not None else None
