"""The lazy sweep, which lapses holds, marks bookings nobody collected and hires gone overdue.

A hold lasts thirty minutes (BR-13), a confirmed booking that is not collected
by the time its branch closes on the first day of the hire is a no show
(BR-17), and a hire with a unit still out after its due date is overdue
(BR-52). Nothing wakes up for any of them, because there is no scheduler and
no process that is always on. Each is dealt with the next time somebody asks a
question it could spoil instead. That is before a hold, before a
confirmation, before a reservation or a list of them is read, before an
availability search is answered, before the counter's dashboard or diary is
read, and before a list of rentals is read. Until a sweep runs the exclusion
constraint still protects the units, so a sweep that runs late costs a little
availability and never costs correctness.

The sweep has three parts and each runs in a transaction of its own. The
first lapses holds, at most `HOLD_SWEEP_BATCH_SIZE` a call, oldest expiry
first. The second marks no shows, at most `NO_SHOW_SWEEP_BATCH_SIZE` a call,
earliest first day first, through `app.application.booking.no_show`. The third
marks hires overdue, at most `OVERDUE_SWEEP_BATCH_SIZE` a call, earliest due
date first, through `app.application.hire.overdue`. In each the due rows are
locked and then checked again, because a row can change between being found
and being locked. Two sweeps at once therefore take turns on a row, and the
second one finds it already dealt with.

A lapse releases its units with the reason `EXPIRED`, and a no show with the
reason `NO_SHOW` and counts the strike on the customer. A hire gone overdue
only changes its status. Each writes its own audit event in the same unit of
work (BR-49), with no actor, because nobody asked for it.

`settle_overdue_hold` does the same for one reservation a use case has already
locked. The batch is bounded, so a use case that is about to decide something
about one reservation makes sure of that one itself.

What the sweep costs a request is three statements when nothing is due, one
for each part, each read through a partial index that holds only the rows that
could be due. When something is due, each reservation in a batch is loaded with
its lines and allocations and written by its own statements, which the batch
size bounds. What degrades first as the data grows is the backlog. The sweep
clears one batch a call, so if holds ran out or bookings were missed faster
than requests arrived to sweep them, they would wait and their units would look
taken for longer. At a hundred times the volume this belongs in a scheduled
job that sweeps in bulk, and the request path keeps only the check on the one
reservation it is about to act on.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from app.application.booking.access import RESERVATION_EXPIRED_ACTION, record_change, state_of
from app.application.booking.no_show import NoShowSweep, mark_due_no_shows
from app.application.hire.overdue import mark_overdue_rentals
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.booking import Reservation
from app.domain.states.base import EXPIRE_MOVE

logger = logging.getLogger(__name__)

# The most reservations one sweep lapses. A request never pays for more.
HOLD_SWEEP_BATCH_SIZE: Final[int] = 25
# The most reservations one sweep marks as no shows. Each one also locks and
# counts on its customer, so the batch is the same size as the other half.
NO_SHOW_SWEEP_BATCH_SIZE: Final[int] = 25
# The most rentals one sweep marks as overdue. Each one is a status and an
# event, so the batch is the same size again.
OVERDUE_SWEEP_BATCH_SIZE: Final[int] = 25


@dataclass(frozen=True, slots=True)
class SweepCommand:
    """A request to run the sweep once.

    Attributes:
        batch_size: The most reservations to lapse in this call.
        no_show_batch_size: The most reservations to mark as no shows.
        overdue_batch_size: The most rentals to mark as overdue.

    """

    batch_size: int = HOLD_SWEEP_BATCH_SIZE
    no_show_batch_size: int = NO_SHOW_SWEEP_BATCH_SIZE
    overdue_batch_size: int = OVERDUE_SWEEP_BATCH_SIZE


@dataclass(frozen=True, slots=True)
class SweepResult:
    """What one sweep did.

    Attributes:
        expired_references: The references of the reservations it lapsed.
        no_show_references: The references of the ones it marked as no shows.
        customers_put_on_hold: The customers those no shows put on hold.
        overdue_references: The references of the rentals it marked as overdue.

    """

    expired_references: tuple[str, ...] = ()
    no_show_references: tuple[str, ...] = ()
    customers_put_on_hold: tuple[UUID, ...] = ()
    overdue_references: tuple[str, ...] = ()

    @property
    def expired_count(self) -> int:
        """Return how many reservations the sweep lapsed."""
        return len(self.expired_references)

    @property
    def no_show_count(self) -> int:
        """Return how many reservations the sweep marked as no shows."""
        return len(self.no_show_references)


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
    """Lapse the holds that ran out, mark the no shows and the overdue hires, a batch of each."""

    def execute(self, command: SweepCommand) -> SweepResult:
        """Run the three parts of the sweep once, each in its own transaction.

        Args:
            command: How many reservations or rentals each part takes at most.

        Returns:
            The references of the reservations lapsed and marked, the
            customers put on hold, and the rentals marked overdue.

        """
        expired = self._lapse_holds(command.batch_size)
        no_shows = self._mark_no_shows(command.no_show_batch_size)
        overdue = self._mark_overdue(command.overdue_batch_size)
        return SweepResult(
            expired_references=expired,
            no_show_references=no_shows.marked,
            customers_put_on_hold=no_shows.customers_put_on_hold,
            overdue_references=overdue,
        )

    def _lapse_holds(self, batch_size: int) -> tuple[str, ...]:
        """Lapse up to a batch of holds that have run out, and commit what was lapsed."""
        now = self._clock.now()
        with self._uow as uow:
            due = uow.reservations.lock_due_holds(now, batch_size)
            expired = tuple(
                reservation.reference
                for reservation in due
                if expire_if_due(uow, reservation, now)
            )
            if expired:
                uow.commit()
        log = logger.info if expired else logger.debug
        log(
            "reservation.hold_sweep_finished",
            extra={
                "due_count": len(due),
                "expired_count": len(expired),
                "expired_references": list(expired),
                "batch_size": batch_size,
            },
        )
        return expired

    def _mark_no_shows(self, batch_size: int) -> NoShowSweep:
        """Mark up to a batch of uncollected bookings as no shows, and commit what was marked."""
        now = self._clock.now()
        today = self._clock.today()
        with self._uow as uow:
            swept = mark_due_no_shows(uow, now, today, batch_size)
            if swept.marked:
                uow.commit()
        log = logger.info if swept.marked else logger.debug
        log(
            "reservation.no_show_sweep_finished",
            extra={
                "due_count": swept.due_count,
                "no_show_count": len(swept.marked),
                "no_show_references": list(swept.marked),
                "put_on_hold_count": len(swept.customers_put_on_hold),
                "batch_size": batch_size,
            },
        )
        return swept

    def _mark_overdue(self, batch_size: int) -> tuple[str, ...]:
        """Mark up to a batch of hires past their due date as overdue, and commit them."""
        now = self._clock.now()
        today = self._clock.today()
        with self._uow as uow:
            swept = mark_overdue_rentals(uow, now, today, batch_size)
            if swept.marked:
                uow.commit()
        log = logger.info if swept.marked else logger.debug
        log(
            "rental.overdue_sweep_finished",
            extra={
                "due_count": swept.due_count,
                "overdue_count": len(swept.marked),
                "overdue_references": list(swept.marked),
                "batch_size": batch_size,
            },
        )
        return swept.marked
