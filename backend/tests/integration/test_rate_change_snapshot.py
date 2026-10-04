"""A rate raised from R280 to R310 reaches new bookings only, on PostgreSQL, through HTTP (US-30).

This is the rate change of the design document run end to end (BR-20). The
counter books a rotary hammer at R280 a day for three days. The administrator
then raises the daily rate to R310 through the admin catalogue. The booking
that was already made, its line and the rental checked out from it after the
raise all stay at R280, because each of them holds its own copy of the
figures. A new quote and a new booking of the same model take R310. The audit
event of the change records the rate before and after.

Every request goes through HTTP on the real database, on the still clock of
the booking tests, which stands on Monday the second of March 2026.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

import pytest
from sqlalchemy import Engine, text
from sqlmodel import Session

from app.domain.enums import UserRole
from app.infrastructure.models import UserAccount
from tests.support.admin_catalogue_api import DAILY_AFTER, DAILY_BEFORE, edit_model
from tests.support.booking_api import BookingClient, BookingWorld, answered, build_booking_world
from tests.support.catalogue import model_quote_path
from tests.support.checkout_api import TODAY_HIRE, checked_out, confirmed_today
from tests.support.factories import Factory

pytestmark = pytest.mark.postgres

UNITS: Final[int] = 2
WEEKLY: Final[Decimal] = Decimal("1120.00")
# Three days at each rate, which is what the line and the hire charge come to.
THREE_DAYS_BEFORE: Final[str] = "840.00"
THREE_DAYS_AFTER: Final[str] = "930.00"
QUOTE_PERIOD: Final[dict[str, str]] = {
    "from": TODAY_HIRE.start.isoformat(),
    "to": TODAY_HIRE.end.isoformat(),
}
SNAPSHOT_QUERY: Final[str] = (
    "SELECT daily_rate_snapshot FROM reservation_line WHERE reservation_id = :reservation"
)


@pytest.fixture
def world(postgres_session: Session, postgres_factory: Factory) -> BookingWorld:
    """Return a committed branch holding two hammers at R280 a day."""
    built = build_booking_world(postgres_factory, asset_count=UNITS)
    built.product_model.daily_rate = Decimal(DAILY_BEFORE)
    built.product_model.weekly_rate = WEEKLY
    postgres_session.add(built.product_model)
    postgres_session.commit()
    return built


@pytest.fixture
def assistant(
    postgres_session: Session, postgres_factory: Factory, world: BookingWorld
) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = postgres_factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    postgres_session.commit()
    return account


@pytest.fixture
def administrator(postgres_session: Session, postgres_factory: Factory) -> UserAccount:
    """Return a committed administrator."""
    account = postgres_factory.user(role=UserRole.ADMIN)
    postgres_session.commit()
    return account


def line_of(reservation: dict[str, object]) -> dict[str, object]:
    """Return the one line of a reservation."""
    lines = reservation["lines"]
    assert isinstance(lines, list)
    (line,) = lines
    assert isinstance(line, dict)
    return line


def hire_charge_of(rental: dict[str, object]) -> dict[str, object]:
    """Return the hire charge of a rental."""
    charges = rental["charges"]
    assert isinstance(charges, list)
    (charge,) = [charge for charge in charges if charge["type"] == "HIRE"]
    assert isinstance(charge, dict)
    return charge


def stored_snapshot(engine: Engine, reservation_id: object) -> Decimal:
    """Return the daily rate a stored reservation line holds, read on a connection of its own."""
    with engine.connect() as connection:
        return Decimal(
            connection.execute(text(SNAPSHOT_QUERY), {"reservation": reservation_id}).scalar_one()
        )


def test_a_raised_rate_reaches_new_bookings_and_leaves_existing_ones_at_the_old_rate(
    booking: BookingClient,
    postgres_engine: Engine,
    world: BookingWorld,
    assistant: UserAccount,
    administrator: UserAccount,
) -> None:
    booked = confirmed_today(booking, world, assistant)
    assert line_of(booked)["dailyRate"] == DAILY_BEFORE

    raised = answered(
        edit_model(booking, administrator, world.product_model.id, {"dailyRate": DAILY_AFTER})
    )
    assert raised["dailyRate"] == DAILY_AFTER

    existing = answered(booking.read(assistant, booked["id"]))
    assert (line_of(existing)["dailyRate"], line_of(existing)["lineSubtotalExVat"]) == (
        DAILY_BEFORE,
        THREE_DAYS_BEFORE,
    )
    assert existing["subtotalExVat"] == THREE_DAYS_BEFORE
    assert stored_snapshot(postgres_engine, booked["id"]) == Decimal(DAILY_BEFORE)

    rental = checked_out(booking, assistant, booked["id"])
    assert hire_charge_of(rental)["amountExVat"] == THREE_DAYS_BEFORE

    quote = answered(
        booking.client.get(model_quote_path(world.product_model.slug), params=QUOTE_PERIOD)
    )
    assert (quote["perUnit"]["dailyRate"], quote["subtotalExVat"]) == (
        DAILY_AFTER,
        THREE_DAYS_AFTER,
    )

    second = confirmed_today(booking, world, assistant)
    assert (line_of(second)["dailyRate"], second["subtotalExVat"]) == (
        DAILY_AFTER,
        THREE_DAYS_AFTER,
    )
    assert answered(booking.read(assistant, booked["id"]))["subtotalExVat"] == THREE_DAYS_BEFORE


def test_the_audit_event_of_the_raise_records_the_rate_before_and_after(
    booking: BookingClient,
    postgres_engine: Engine,
    world: BookingWorld,
    administrator: UserAccount,
) -> None:
    answered(
        edit_model(booking, administrator, world.product_model.id, {"dailyRate": DAILY_AFTER})
    )
    with postgres_engine.connect() as connection:
        before, after, actor = connection.execute(
            text(
                "SELECT before_state, after_state, actor_user_id FROM audit_event "
                "WHERE entity_id = :model AND action = 'product_model.updated'"
            ),
            {"model": world.product_model.id},
        ).one()
    assert (before, after, actor) == (
        {"daily_rate": DAILY_BEFORE},
        {"daily_rate": DAILY_AFTER},
        administrator.id,
    )
