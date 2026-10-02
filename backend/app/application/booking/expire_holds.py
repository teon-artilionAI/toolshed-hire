"""The lazy sweep that lapses holds which have run out (BR-13).

A hold lasts thirty minutes. Nothing wakes up when one runs out, because there
is no scheduler and no process that is always on. A hold is lapsed the next
time somebody asks a question it could spoil instead. That is before a hold,
before a confirmation, before a reservation or a list of them is read, and
before an availability search is answered. Until a sweep runs the exclusion
constraint still protects the units, so a sweep that runs late costs a little
availability and never costs correctness.

One call takes at most `HOLD_SWEEP_BATCH_SIZE` reservations, oldest expiry
first, so no request pays for an unbounded backlog. The due rows are locked
and then checked again, because a row can be confirmed or lapsed by another
request between being found and being locked. Two sweeps at once therefore
take turns on a row, and the second one finds it already dealt with.

Each lapse releases its units with the reason `EXPIRED` and writes its own
audit event in the same unit of work (BR-49). The event has no actor, because
nobody asked for it.

`settle_overdue_hold` does the same for one reservation a use case has already
locked. The batch is bounded, so a use case that is about to decide something
about one reservation makes sure of that one itself.

What degrades first as the data grows is the backlog. The sweep runs on the
request path and clears one batch a call, so if holds ran out faster than
requests arrived to sweep them, expired holds would wait and their units would
look taken for longer. Each reservation in a batch is also loaded with its
lines and allocations by its own statements. That is bounded by the batch
size today. At a hundred times the volume this belongs in a scheduled job that
sweeps in bulk, and the request path keeps only the check on the one
reservation it is about to act on.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from app.application.booking.access import RESERVATION_EXPIRED_ACTION, record_change, state_of
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.booking import Reservation
from app.domain.states.base import EXPIRE_MOVE

logger = logging.getLogger(__name__)

# The most reservations one sweep lapses. A request never pays for more.
HOLD_SWEEP_BATCH_SIZE: Final[int] = 25


@dataclass(frozen=True, slots=True)
class SweepCommand:
    """A request to run the sweep once.

    Attributes:
        batch_size: The most reservations to lapse in this call.

    """

    batch_size: int = HOLD_SWEEP_BATCH_SIZE


@dataclass(frozen=True, slots=True)
class SweepResult:
    """What one sweep did.

    Attributes:
        expired_references: The references of the reservations it lapsed.

    """

    expired_references: tuple[str, ...] = ()

    @property
    def expired_count(self) -> int:
        """Return how many reservations the sweep lapsed."""
        return len(self.expired_references)


def expire_if_due(uow: UnitOfWork, reservation: Reservation, now: datetime) -> bool:
    """Lapse one locked reservation when its hold has run out. Nothing is committed here.

    Args:
        uow: The open unit of work that holds the lock on the reservation.
        reservation: The reservation, read for a change.
        now: The current instant, from the clock.

    Returns:
        True when the reservation was lapsed, and False when it is not held or
        its hold still stands.

    """
    if not (reservation.state.permits(EXPIRE_MOVE) and reservation.hold_has_expired(now)):
        return False
    before = state_of(reservation)
    reservation.expire(now=now)
    uow.reservations.save(reservation)
    record_change(
        uow,
        actor=None,
        reservation=reservation,
        action=RESERVATION_EXPIRED_ACTION,
        occurred_at=now,
        before=before,
    )
    logger.info(
        "reservation.hold_expired",
        extra={
            "reference": reservation.reference,
            "reservation_id": str(reservation.id),
            "released_count": before["active_allocation_count"],
        },
    )
    return True


def settle_overdue_hold(uow: UnitOfWork, reservation: Reservation, now: datetime) -> bool:
    """Lapse one locked reservation when its hold has run out, and commit that.

    A use case calls this before it decides anything about a reservation. The
    lapse is a change in its own right, so it is committed at once and stands
    even when the move the caller asked for is then refused.

    Returns:
        True when the reservation was lapsed.

    """
    if not expire_if_due(uow, reservation, now):
        return False
    uow.commit()
    return True


class ExpireHoldsAndNoShowsUseCase(UseCase[SweepCommand, SweepResult]):
    """Lapse the holds that have run out, a bounded batch at a time.

    The design document gives this use case two halves. The half that lapses
    holds is built. The half that marks a confirmed reservation as not
    collected (BR-17) comes with checkout, and its place is marked below.
    """

    def execute(self, command: SweepCommand) -> SweepResult:
        """Run the sweep once and commit what it lapsed.

        Args:
            command: How many reservations to take at most.

        Returns:
            The references of the reservations that were lapsed.

        """
        now = self._clock.now()
        with self._uow as uow:
            due = uow.reservations.lock_due_holds(now, command.batch_size)
            expired = tuple(
                reservation.reference
                for reservation in due
                if expire_if_due(uow, reservation, now)
            )
            # The no-show half of the sweep goes here (BR-17). It will lock the
            # confirmed reservations whose branch has closed on their first
            # day, call `mark_no_show` on each and count the strike.
            if expired:
                uow.commit()
        log = logger.info if expired else logger.debug
        log(
            "reservation.hold_sweep_finished",
            extra={
                "due_count": len(due),
                "expired_count": len(expired),
                "expired_references": list(expired),
                "batch_size": command.batch_size,
            },
        )
        return SweepResult(expired_references=expired)
