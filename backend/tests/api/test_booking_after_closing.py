"""A hire for today cannot be booked once the branch has closed, through HTTP (BR-04).

The rule is pinned either side of closing time in
tests/unit/test_booking_after_closing.py. This asks the route, as a customer
and as counter staff, and pins the 422 that names the start date and the
sentence beside it. The branch of the world closes at 17:00 in Cape Town.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Final

import pytest
from fastapi import status
from sqlmodel import Session

from app.domain.enums import UserRole
from app.domain.period import BookingPeriod
from app.infrastructure.models import UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, build_booking_world, created
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of

TODAY_HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 2), date(2026, 3, 4))
TOMORROW_HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 3), date(2026, 3, 5))
# A minute after 17:00 in Cape Town on Monday the second of March 2026.
AFTER_CLOSING: Final[datetime] = datetime(2026, 3, 2, 15, 1, tzinfo=UTC)
CLOSED_FOR_TODAY: Final[str] = (
    "The branch has closed for today. The earliest a hire can start is tomorrow."
)


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world of two units."""
    built = build_booking_world(factory, asset_count=2)
    session.commit()
    return built


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


def test_a_customer_cannot_book_today_after_closing(
    booking: BookingClient, world: BookingWorld
) -> None:
    booking.clock.instant = AFTER_CLOSING
    response = booking.create(world.customer, world.payload(TODAY_HIRE))
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert problem_code(response) == "request-validation-failure"
    assert problem_of(response)["errors"] == {"fields": {"body.from": CLOSED_FOR_TODAY}}


def test_counter_staff_cannot_book_today_after_closing_either(
    booking: BookingClient, world: BookingWorld, assistant: UserAccount
) -> None:
    booking.clock.instant = AFTER_CLOSING
    body = world.payload(TODAY_HIRE, customer_profile_id=world.profile.id)
    response = booking.create(assistant, body)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert problem_of(response)["errors"] == {"fields": {"body.from": CLOSED_FOR_TODAY}}


def test_tomorrow_can_still_be_booked_after_closing(
    booking: BookingClient, world: BookingWorld
) -> None:
    booking.clock.instant = AFTER_CLOSING
    draft = created(booking.create(world.customer, world.payload(TOMORROW_HIRE)))
    assert draft["status"] == "DRAFT"
