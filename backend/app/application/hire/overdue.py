"""The half of the lazy sweep that marks hires overdue, which is BR-52.

A rental that still has a unit out after the day it was due back reads as
OVERDUE. Nothing wakes up when the day passes, so the same sweep that lapses
holds and marks no shows moves such a rental to OVERDUE the next time somebody
asks a question it could spoil, such as the list of rentals or the counter's
dashboard.

`mark_overdue_rentals` takes at most a batch of the due rentals, locked, and
asks the domain again, through `Rental.status_on`, what each one reads as now
that it holds the lock, because a unit can come back between the rental being
found and being locked. Each move writes an audit event with no actor, because
nobody asked for it (BR-49). Returning units moves the rental on again, to
RETURNED once the last one is back.

The batch is bounded, so the read of one rental makes sure of the rental it is
about to show with `mark_overdue_rental`, the way the read of one reservation
lapses the one hold it is about to show.

Nothing here commits. The caller owns the transaction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime

from app.application.hire.rental_audit import (
    RENTAL_OVERDUE_ACTION,
    record_rental_change,
    rental_state,
)
from app.application.unit_of_work import UnitOfWork
from app.domain.enums import RentalStatus
from app.domain.rental import Rental

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OverdueSweep:
    """What one pass of the overdue half of the sweep did.

    Attributes:
        due_count: How many rentals the query found and locked.
        marked: The references of the ones it moved to OVERDUE.

    """

    due_count: int
    marked: tuple[str, ...]


def mark_overdue_rentals(uow: UnitOfWork, now: datetime, today: date, limit: int) -> OverdueSweep:
    """Move every rental with a unit out past its due date to OVERDUE, a batch at a time.

    Args:
        uow: The open unit of work the sweep runs in.
        now: The current instant, from the clock.
        today: The current business day, which decides what is past due.
        limit: The most rentals to take in this pass.

    """
    due = uow.rentals.lock_due_overdue(today, limit)
    marked = [rental.reference for rental in due if mark_overdue_rental(uow, rental, now, today)]
    return OverdueSweep(due_count=len(due), marked=tuple(marked))


def mark_overdue_rental(uow: UnitOfWork, rental: Rental, now: datetime, today: date) -> bool:
    """Move one locked rental to OVERDUE when it reads as overdue today, and record it.

    Args:
        uow: The open unit of work that holds the lock on the rental.
        rental: The rental, as the lock read it.
        now: The current instant, from the clock.
        today: The current business day, which decides what is past due.

    Returns:
        True when the rental moved. A rental that is already OVERDUE, or no
        longer has a unit out past its due date, is left as it is.

    """
    already_overdue = rental.status is RentalStatus.OVERDUE
    if already_overdue or rental.status_on(today) is not RentalStatus.OVERDUE:
        return False
    before = rental_state(rental)
    rental.status = RentalStatus.OVERDUE
    uow.rentals.save(rental)
    record_rental_change(
        uow,
        actor=None,
        rental=rental,
        action=RENTAL_OVERDUE_ACTION,
        occurred_at=now,
        before=before,
        extra={"due_back_on": rental.due_back_on.isoformat()},
    )
    logger.info(
        "rental.marked_overdue",
        extra={
            "reference": rental.reference,
            "rental_id": str(rental.id),
            "due_back_on": rental.due_back_on.isoformat(),
            "status_before": before["status"],
            "items_out": len(rental.items_out()),
        },
    )
    return True
