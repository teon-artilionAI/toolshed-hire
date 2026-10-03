"""The detail of one rental reads the status it has today, with no list read first (BR-52).

Nothing wakes up when a due date passes. The list of rentals and the counter's
screens run the lazy sweep, and so does the read of one rental, for the one
rental it is about to show. A hire still out after its due date reads OVERDUE
on its own detail, the move is recorded once, and a hire that is not yet due
is read without anything being written.

A hire goes out on Monday the second of March 2026 and is due back on the
fourth, so on the fifth it is overdue.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Final

import pytest
from sqlmodel import Session, col, select

from app.domain.enums import UserRole
from app.domain.period import BookingPeriod
from app.infrastructure.models import AuditEvent, UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, answered
from tests.support.checkout_api import TODAY, read_rental
from tests.support.factories import Factory
from tests.support.rental_api import (
    item_ids,
    on_hire,
    return_body,
    take_back,
    worked_example_world,
)

DUE_ON_THE_FOURTH: Final[BookingPeriod] = BookingPeriod(TODAY, date(2026, 3, 4))
TO_THE_FIFTH: Final[timedelta] = timedelta(days=3)
TO_THE_FOURTH: Final[timedelta] = timedelta(days=2)
TWO_UNITS: Final[int] = 2
OVERDUE_ACTION: Final[str] = "rental.overdue"


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world of two units."""
    return worked_example_world(session, factory, units=TWO_UNITS)


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


def overdue_events(session: Session) -> list[AuditEvent]:
    """Return the audit events that moved a rental to OVERDUE."""
    return list(session.exec(select(AuditEvent).where(col(AuditEvent.action) == OVERDUE_ACTION)))


def test_a_hire_past_its_due_date_reads_overdue_on_its_own_detail(
    booking: BookingClient, world: BookingWorld, assistant: UserAccount, session: Session
) -> None:
    rental = on_hire(booking, world, assistant, quantity=TWO_UNITS, period=DUE_ON_THE_FOURTH)
    first, _second = item_ids(rental)
    answered(take_back(booking, assistant, rental["id"], return_body(first)))
    booking.clock.advance(TO_THE_FIFTH)

    shown = answered(read_rental(booking, assistant, rental["id"]))
    assert (shown["status"], shown["settlementWaitingOn"]) == ("OVERDUE", "ITEMS_OUT")
    again = answered(read_rental(booking, assistant, rental["reference"]))
    assert again["status"] == "OVERDUE"
    (event,) = overdue_events(session)
    assert (event.actor_user_id, (event.before_state or {})["status"]) == (
        None, "PARTIALLY_RETURNED"
    )


def test_a_hire_that_is_not_yet_due_is_read_without_writing_anything(
    booking: BookingClient, world: BookingWorld, assistant: UserAccount, session: Session
) -> None:
    rental = on_hire(booking, world, assistant, period=DUE_ON_THE_FOURTH)
    booking.clock.advance(TO_THE_FOURTH)
    shown = answered(read_rental(booking, assistant, rental["id"]))
    assert shown["status"] == "OPEN"
    assert overdue_events(session) == []
