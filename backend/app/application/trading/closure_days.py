"""The use cases by which the owner adds and cancels a closure day.

A closure closes one branch, or every branch, on one day, with a reason a
customer reads. Adding one holds the reason and the day to the rules of
`app.domain.closure_day`, looks the branch up among those still trading, and
asks whether the day is closed already, at that branch or at every branch, so
a second closure is refused in a plain sentence. The unique index of revision
0013 has the last word, and a race lost to it is refused the same way.

Cancelling one locks it first, so two owners cancelling it at once take turns
and the second is told it was cancelled already. A closure is never deleted
(BR-51).

The change and its audit event, `branch.closure_day_added` or
`branch.closure_day_cancelled`, commit in one unit of work (BR-49). Neither
touches a booking. The owner reads the bookings a closure strands before
adding it and rings each customer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Final
from uuid import UUID, uuid4

from app.application.audit import audit_event_for
from app.application.availability.search import UNKNOWN_BRANCH_MESSAGE
from app.application.identity.account_rules import refused_field, wire_name
from app.application.refusal import refused
from app.application.trading.closure_ports import DuplicateClosureDay
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.audit import StateValue
from app.domain.closure_day import (
    CANCELLED_STATE,
    LIVE_STATE,
    ClosureDay,
    duplicate_closure,
    ensure_day_may_close,
    written_closure_reason,
)
from app.domain.errors import NotFound, ValidationFailure
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

CLOSURE_ENTITY_TYPE: Final[str] = "closure_day"
CLOSURE_ADDED_ACTION: Final[str] = "branch.closure_day_added"
CLOSURE_CANCELLED_ACTION: Final[str] = "branch.closure_day_cancelled"
CLOSURE_NOT_FOUND_MESSAGE: Final[str] = "We could not find that closure day."
BRANCH_CODE_FIELD: Final[str] = "branch_code"
# The keys of the audit event, as the log reads them.
BRANCH_CODE_KEY: Final[str] = "branch_code"
DAY_KEY: Final[str] = "day"
REASON_KEY: Final[str] = "reason"
STATE_KEY: Final[str] = "state"


@dataclass(frozen=True, slots=True)
class AddClosureDayCommand:
    """A request to close a branch, or every branch, on a day.

    Attributes:
        actor: The owner deciding.
        branch_code: The branch, in capitals, or None for every branch.
        day: The day to close.
        reason: Why, as a customer will read it.

    """

    actor: Actor
    branch_code: str | None
    day: date
    reason: str


@dataclass(frozen=True, slots=True)
class CancelClosureDayCommand:
    """A request to open a closed day again.

    Attributes:
        actor: The owner deciding.
        closure_id: The closure to cancel.

    """

    actor: Actor
    closure_id: UUID


class AddClosureDayUseCase(UseCase[AddClosureDayCommand, ClosureDay]):
    """Close a branch, or every branch, on a day, with its audit event."""

    def execute(self, command: AddClosureDayCommand) -> ClosureDay:
        """Add the closure, or refuse and write nothing.

        Raises:
            ValidationFailure: Naming `reason`, `day` or `branchCode`, for a
                reason out of bounds, a day that has passed or is too far
                ahead, or a branch that is not trading.
            StateTransitionError: If the day is closed already at that branch
                or at every branch.

        """
        logger.info(
            "trading.closure_day_add_requested",
            extra={
                "actor_user_id": str(command.actor.user_id),
                "branch_code": command.branch_code,
                "day": command.day.isoformat(),
            },
        )
        now = self._clock.now()
        reason = _checked_terms(command.reason, command.day, self._clock.today())
        with self._uow as uow:
            branch_id = _trading_branch_id(uow, command.branch_code)
            existing = uow.closure_days.live_on(branch_id, command.day)
            if existing is not None:
                logger.info(
                    "trading.closure_day_already_closed",
                    extra={
                        "branch_code": command.branch_code,
                        "day": command.day.isoformat(),
                        "existing_closure_id": str(existing.id),
                    },
                )
                raise duplicate_closure(command.day, existing)
            closure = ClosureDay(
                id=uuid4(),
                branch_id=branch_id,
                branch_code=command.branch_code,
                day=command.day,
                reason=reason,
                created_at=now,
            )
            try:
                uow.closure_days.add(closure, command.actor.user_id)
            except DuplicateClosureDay as duplicate:
                logger.info(
                    "trading.closure_day_race_lost",
                    extra={"branch_code": command.branch_code, "day": command.day.isoformat()},
                )
                raise duplicate_closure(command.day, None) from duplicate
            uow.audit.record(
                audit_event_for(
                    actor=command.actor,
                    entity_type=CLOSURE_ENTITY_TYPE,
                    entity_id=closure.id,
                    action=CLOSURE_ADDED_ACTION,
                    occurred_at=now,
                    after_state=_closure_state(closure),
                )
            )
            uow.commit()
        logger.info(
            "trading.closure_day_added",
            extra={
                "closure_id": str(closure.id),
                "branch_code": closure.branch_code,
                "day": closure.day.isoformat(),
            },
        )
        return closure


class CancelClosureDayUseCase(UseCase[CancelClosureDayCommand, ClosureDay]):
    """Open a closed day again, with its audit event. The row is kept (BR-51)."""

    def execute(self, command: CancelClosureDayCommand) -> ClosureDay:
        """Cancel the closure, or refuse and write nothing.

        Raises:
            NotFound: If there is no closure with this key.
            StateTransitionError: If it was cancelled already.

        """
        closure_id = command.closure_id
        logger.info(
            "trading.closure_day_cancel_requested",
            extra={"actor_user_id": str(command.actor.user_id), "closure_id": str(closure_id)},
        )
        now = self._clock.now()
        with self._uow as uow:
            stored = uow.closure_days.get_for_update(closure_id)
            if stored is None:
                logger.info("trading.closure_day_not_found", extra={"closure_id": str(closure_id)})
                raise NotFound(CLOSURE_NOT_FOUND_MESSAGE, {"closure_day": str(closure_id)})
            if not stored.is_live:
                logger.info(
                    "trading.closure_day_already_cancelled", extra={"closure_id": str(closure_id)}
                )
            cancelled = stored.cancelled(now)
            uow.closure_days.save_cancellation(cancelled, command.actor.user_id)
            uow.audit.record(
                audit_event_for(
                    actor=command.actor,
                    entity_type=CLOSURE_ENTITY_TYPE,
                    entity_id=closure_id,
                    action=CLOSURE_CANCELLED_ACTION,
                    occurred_at=now,
                    before_state={STATE_KEY: LIVE_STATE},
                    after_state={STATE_KEY: CANCELLED_STATE, **_closure_state(cancelled)},
                )
            )
            uow.commit()
        logger.info(
            "trading.closure_day_cancelled",
            extra={
                "closure_id": str(closure_id),
                "branch_code": cancelled.branch_code,
                "day": cancelled.day.isoformat(),
            },
        )
        return cancelled


def _checked_terms(reason: str, day: date, today: date) -> str:
    """Return the reason as it is kept, once the reason and the day keep their rules.

    Raises:
        ValidationFailure: Naming `reason` or `day`, the reason first.

    """
    try:
        written = written_closure_reason(reason)
        ensure_day_may_close(day, today)
    except ValidationFailure as failure:
        raise refused_field(failure) from failure
    return written


def _trading_branch_id(uow: UnitOfWork, branch_code: str | None) -> UUID | None:
    """Return the key of the trading branch a closure is for, or None for every branch.

    Raises:
        ValidationFailure: Naming `branchCode` when no trading branch has the code.

    """
    if branch_code is None:
        return None
    branch = uow.branches.find_active_by_code(branch_code)
    if branch is None:
        logger.info("trading.closure_branch_unknown", extra={"branch_code": branch_code})
        raise refused(wire_name(BRANCH_CODE_FIELD), UNKNOWN_BRANCH_MESSAGE, {"branch": branch_code})
    return branch.id


def _closure_state(closure: ClosureDay) -> dict[str, StateValue]:
    """Return what the audit event keeps of a closure."""
    return {
        BRANCH_CODE_KEY: closure.branch_code,
        DAY_KEY: closure.day.isoformat(),
        REASON_KEY: closure.reason,
    }
