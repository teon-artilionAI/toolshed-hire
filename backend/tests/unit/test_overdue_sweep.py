"""The overdue part of the lazy sweep, run against ports and nothing else (BR-52).

A hire with a unit still out after the day it was due back reads as OVERDUE,
and the sweep is what moves it there. These pin what one sweep does. It takes
the hires past their due date that do not already read OVERDUE, a bounded
batch of them, earliest due date first, asks the domain again what each reads
as, moves it and writes an audit event with no actor. A hire still inside its
period, and one that is back, are left alone.

The unit of work is the in memory double from tests/support. The hires are
put out by the domain's own checkout and are due back on the twelfth of March
2026.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from app.application.booking.expire_holds import SweepCommand
from app.application.hire.rental_audit import RENTAL_OVERDUE_ACTION
from app.domain.enums import RentalStatus
from app.domain.rental import Rental
from tests.support.memory import COMMIT
from tests.support.memory_world import BookingDesk, build_memory_world, open_desk
from tests.support.return_domain import (
    DUE_BACK_ON,
    TWO_UNITS,
    a_hire,
    back,
    days_after_due,
    on_day,
    returned,
)

SMALL_BATCH: Final[int] = 1


def desk_on(day: date, *rentals: Rental) -> BookingDesk:
    """Return the booking desk of a world holding the rentals, its clock on a day."""
    world = build_memory_world()
    world.store.committed.rentals.extend(rentals)
    desk = open_desk(world)
    desk.clock.instant = on_day(day)
    return desk


def stored(desk: BookingDesk) -> dict[str, RentalStatus]:
    """Return the status of every committed rental by its reference."""
    return {rental.reference: rental.status for rental in desk.world.store.committed.rentals}


def numbered(rental: Rental, number: int) -> Rental:
    """Give a rental a reference of its own, so two of them can be told apart."""
    rental.reference = f"TSH-H-26-{number:06d}"
    return rental


class TestWhatOneSweepMarks:
    """A hire past its due date with a unit out, and nothing else."""

    def test_a_hire_out_past_its_due_date_is_marked_overdue_with_no_actor(self) -> None:
        rental = a_hire().rental
        desk = desk_on(days_after_due(1), rental)
        result = desk.sweep.execute(SweepCommand())

        assert result.overdue_references == (rental.reference,)
        assert stored(desk) == {rental.reference: RentalStatus.OVERDUE}
        (event,) = [
            event
            for event in desk.world.store.committed.audit_events
            if event.action == RENTAL_OVERDUE_ACTION
        ]
        assert (event.actor_user_id, event.actor_role) == (None, None)
        assert event.after_state is not None and event.after_state["status"] == "OVERDUE"
        assert desk.world.store.journal[-1] == COMMIT

    def test_a_partly_returned_hire_with_a_unit_out_past_due_is_marked_too(self) -> None:
        hire = a_hire(TWO_UNITS)
        returned(hire, DUE_BACK_ON, back(hire, 0))
        desk = desk_on(days_after_due(2), hire.rental)
        desk.sweep.execute(SweepCommand())
        assert stored(desk) == {hire.rental.reference: RentalStatus.OVERDUE}

    def test_a_hire_on_its_due_date_and_one_that_is_back_are_left_alone(self) -> None:
        out = numbered(a_hire().rental, 1)
        hire = a_hire()
        returned(hire, DUE_BACK_ON, back(hire))
        back_already = numbered(hire.rental, 2)
        desk = desk_on(DUE_BACK_ON, out, back_already)
        result = desk.sweep.execute(SweepCommand())
        assert result.overdue_references == ()
        assert stored(desk) == {
            out.reference: RentalStatus.OPEN,
            back_already.reference: RentalStatus.RETURNED,
        }


class TestTheSweepIsBoundedAndChecksAgain:
    """At most a batch, the earliest due first, and the domain asked again under the lock."""

    def test_a_sweep_takes_no_more_than_its_batch_and_starts_with_the_earliest(self) -> None:
        later = numbered(a_hire().rental, 1)
        earlier = numbered(a_hire().rental, 2)
        earlier.due_back_on = date(2026, 3, 10)
        desk = desk_on(days_after_due(3), later, earlier)
        first = desk.sweep.execute(SweepCommand(overdue_batch_size=SMALL_BATCH))
        assert first.overdue_references == (earlier.reference,)
        second = desk.sweep.execute(SweepCommand(overdue_batch_size=SMALL_BATCH))
        assert second.overdue_references == (later.reference,)

    def test_a_hire_that_no_longer_reads_overdue_under_the_lock_is_skipped(self) -> None:
        hire = a_hire()
        returned(hire, DUE_BACK_ON, back(hire))
        desk = desk_on(days_after_due(4), hire.rental)
        desk.world.store.stale_overdue_query = True
        result = desk.sweep.execute(SweepCommand())
        assert result.overdue_references == ()
        assert stored(desk) == {hire.rental.reference: RentalStatus.RETURNED}
