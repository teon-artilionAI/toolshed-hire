"""Taking units back and settling the deposit, through HTTP (FR-18, FR-19, US-23, BR-29 to BR-32).

The worked example of the design document is followed through the routes. A
unit goes out with a deposit of R1,200.00 and a late fee of R120.00 a day, the
clock moves on to two days after it was due back, and the return withholds
R240.00, releases R960.00 and settles the hire. These pin that, a partial
return and the last one, what happens to the unit, the allocation and the
reservation, the audit trail, and what a unit still out would owe today.

They run against the in memory database, and the clock stands still on Monday
the second of March 2026 until a test moves it. The refusals are in
tests/api/test_rental_refusals.py.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final
from uuid import UUID

import pytest
from sqlmodel import Session, col, select

from app.domain.enums import AssetStatus, ReleaseReason, ReservationStatus, UserRole
from app.infrastructure.models import Asset, AssetAllocation, AuditEvent, Reservation, UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, answered
from tests.support.checkout_api import read_rental
from tests.support.factories import Factory
from tests.support.rental_api import (
    ONE_DAY,
    charges_of,
    item_ids,
    on_hire,
    return_body,
    take_back,
    worked_example_world,
)

TWO_UNITS: Final[int] = 2
HOUR_METER_IN: Final[int] = 412
# Two days after the sixth, the day the hire of these tests is due back.
TWO_DAYS_LATE: Final[int] = 6


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world of two units with the deposit and late fee of the worked example."""
    return worked_example_world(session, factory, units=TWO_UNITS)


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


class TestTheWorkedExample:
    """R1,200.00 held, two days late at R120.00, R240.00 withheld, R960.00 released, settled."""

    def test_the_return_two_days_late_settles_the_hire_as_the_document_says(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        rental = on_hire(booking, world, assistant)
        booking.clock.advance(ONE_DAY * TWO_DAYS_LATE)
        back = answered(take_back(booking, assistant, rental["id"], return_body(*item_ids(rental))))

        assert back["depositHeld"] == "1200.00"
        assert (back["depositWithheld"], back["depositRefunded"]) == ("240.00", "960.00")
        assert (back["balanceDue"], back["status"]) == ("0.00", "SETTLED")
        assert back["settledAt"] == back["returnedAt"] == "2026-03-08T10:00:00+02:00"
        assert back["settlementWaitingOn"] is None
        (item,) = back["items"]
        assert (item["daysLate"], item["conditionIn"]) == (2, "A")

    def test_the_late_fee_is_stored_as_two_hundred_and_eight_seventy_plus_vat(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        rental = on_hire(booking, world, assistant)
        booking.clock.advance(ONE_DAY * TWO_DAYS_LATE)
        back = answered(take_back(booking, assistant, rental["id"], return_body(*item_ids(rental))))

        (fee,) = charges_of(back, "LATE_FEE")
        assert (fee["amountExVat"], fee["vatRate"], fee["vatAmount"]) == (
            "208.70", "15.00", "31.30"
        )
        assert (fee["amountIncVat"], fee["status"]) == ("240.00", "SETTLED")
        assert fee["rentalItemId"] == item_ids(rental)[0]
        (release,) = charges_of(back, "DEPOSIT_RELEASE")
        assert (release["amountExVat"], release["vatAmount"], release["amountIncVat"]) == (
            "-960.00", "0.00", "-960.00"
        )
        assert release["status"] == "SETTLED"

    def test_a_unit_still_out_shows_what_a_return_today_would_charge(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        rental = on_hire(booking, world, assistant)
        booking.clock.advance(ONE_DAY * TWO_DAYS_LATE)
        shown = answered(read_rental(booking, assistant, rental["id"]))
        (item,) = shown["items"]
        assert (item["daysLateToday"], item["lateFeeToday"]) == (2, "240.00")


class TestAPartialReturn:
    """Units come back one at a time, and the rental follows them (BR-29)."""

    def test_the_first_unit_back_leaves_the_rental_partly_returned(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        rental = on_hire(booking, world, assistant, quantity=TWO_UNITS)
        first, second = item_ids(rental)
        back = answered(take_back(booking, assistant, rental["id"], return_body(first)))

        assert (back["status"], back["returnedAt"]) == ("PARTIALLY_RETURNED", None)
        assert back["settlementWaitingOn"] == "ITEMS_OUT"
        assert back["canReturn"] is True
        assert (back["depositWithheld"], back["depositRefunded"]) == ("0.00", "0.00")
        by_key = {item["id"]: item for item in back["items"]}
        assert by_key[first]["returnedAt"] == "2026-03-02T10:00:00+02:00"
        assert by_key[second]["returnedAt"] is None

    def test_the_last_unit_back_returns_the_hire_and_releases_the_whole_deposit(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        session: Session,
    ) -> None:
        rental = on_hire(booking, world, assistant, quantity=TWO_UNITS)
        first, second = item_ids(rental)
        answered(take_back(booking, assistant, rental["id"], return_body(first)))
        back = answered(take_back(booking, assistant, rental["id"], return_body(second)))

        assert (back["status"], back["canReturn"]) == ("SETTLED", False)
        assert (back["depositRefunded"], back["depositWithheld"]) == ("2400.00", "0.00")
        (release,) = charges_of(back, "DEPOSIT_RELEASE")
        assert release["description"] == "Deposit released in full"
        reservation = session.get(Reservation, UUID(str(back["reservationId"])))
        assert reservation is not None
        session.refresh(reservation)
        assert reservation.status is ReservationStatus.RETURNED


class TestWhatAReturnDoesToTheUnit:
    """The unit is back on the shelf and its allocation is let go (US-23)."""

    def test_the_unit_is_available_with_what_the_counter_recorded(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        session: Session,
    ) -> None:
        rental = on_hire(booking, world, assistant)
        body = return_body(
            *item_ids(rental),
            conditionIn="B",
            hourMeterIn=HOUR_METER_IN,
            accessoriesIn="  Chuck key  ",
            notes="Dusty",
        )
        back = answered(take_back(booking, assistant, rental["id"], body))

        (item,) = back["items"]
        assert (item["conditionIn"], item["hourMeterIn"], item["accessoriesIn"]) == (
            "B", HOUR_METER_IN, "Chuck key"
        )
        unit = session.exec(select(Asset).where(col(Asset.asset_tag) == item["assetTag"])).one()
        session.refresh(unit)
        assert (unit.status, unit.condition_grade.value, unit.hour_meter_reading) == (
            AssetStatus.AVAILABLE, "B", HOUR_METER_IN
        )
        allocation = session.exec(
            select(AssetAllocation).where(col(AssetAllocation.asset_id) == unit.id)
        ).one()
        session.refresh(allocation)
        assert allocation.release_reason is ReleaseReason.RETURNED

    def test_the_return_writes_its_audit_events(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        session: Session,
    ) -> None:
        rental = on_hire(booking, world, assistant)
        answered(take_back(booking, assistant, rental["id"], return_body(*item_ids(rental))))
        actions = sorted(
            event.action
            for event in session.exec(select(AuditEvent))
            if event.action.startswith(("rental.items", "rental.deposit", "reservation.returned"))
        )
        assert actions == [
            "rental.deposit_settled", "rental.items_returned", "reservation.returned"
        ]
        moves = [
            event
            for event in session.exec(select(AuditEvent))
            if event.action == "asset.status_changed"
            and (event.after_state or {}).get("status") == "AVAILABLE"
        ]
        assert len(moves) == 1
        assert moves[0].actor_user_id == assistant.id


def test_a_hire_returned_on_its_due_date_owes_no_late_fee(
    booking: BookingClient, world: BookingWorld, assistant: UserAccount
) -> None:
    rental = on_hire(booking, world, assistant)
    booking.clock.advance(ONE_DAY * 4)
    back = answered(take_back(booking, assistant, rental["id"], return_body(*item_ids(rental))))
    assert charges_of(back, "LATE_FEE") == []
    assert (back["depositRefunded"], back["status"]) == (str(Decimal("1200.00")), "SETTLED")


def test_a_list_with_one_unit_that_is_not_on_the_rental_returns_neither(
    booking: BookingClient, world: BookingWorld, assistant: UserAccount, session: Session
) -> None:
    rental = on_hire(booking, world, assistant)
    (key,) = item_ids(rental)
    body = return_body(key, str(UUID(int=7)))
    refused = take_back(booking, assistant, rental["id"], body)
    assert refused.status_code == 422
    shown = answered(read_rental(booking, assistant, rental["id"]))
    assert (shown["status"], shown["items"][0]["returnedAt"]) == ("OPEN", None)
    assert charges_of(shown, "LATE_FEE") == charges_of(shown, "DEPOSIT_RELEASE") == []
