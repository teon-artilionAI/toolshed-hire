"""A unit recorded as lost, and the balance the deposit did not cover, over HTTP (BR-31 to BR-33).

A unit more than fourteen days late is recorded as lost. It owes fourteen days
of late fee, its deposit is kept, and the rest of its replacement value is
recovered. The deposit settles what it can when the last unit is closed, and
what it cannot cover is the balance due, which the counter records as paid.

The world is the worked example's, R1,200.00 deposit, R120.00 a day late and a
replacement value of R4,200.00. The hire goes out on the second of March and
is due back on the sixth, so the twenty first is fifteen days late.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

import pytest
from sqlmodel import Session, col, select

from app.domain.enums import AssetStatus, UserRole
from app.infrastructure.models import Asset, Charge, UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, answered
from tests.support.factories import Factory
from tests.support.rental_api import (
    charges_of,
    item_ids,
    on_hire,
    pay_balance,
    record_loss,
    return_body,
    take_back,
    worked_example_world,
)

# From the second of March to the twenty first, fifteen days after the sixth.
FIFTEEN_DAYS_LATE: Final[timedelta] = timedelta(days=19)
PAYMENT_REFERENCE: Final[str] = "EFT-20260321-0042"
TWO_UNITS: Final[int] = 2


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world of two units with the worked example's figures."""
    return worked_example_world(session, factory, units=TWO_UNITS)


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


class TestALostUnit:
    """Fourteen days of late fee, the deposit kept, and the rest of the value recovered."""

    def test_the_loss_charges_what_the_rule_says(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        rental = on_hire(booking, world, assistant)
        booking.clock.advance(FIFTEEN_DAYS_LATE)
        (item_key,) = item_ids(rental)
        lost = answered(record_loss(booking, assistant, rental["id"], item_key))

        (fee,) = charges_of(lost, "LATE_FEE")
        assert (fee["amountExVat"], fee["vatAmount"], fee["amountIncVat"]) == (
            "1460.87", "219.13", "1680.00"
        )
        (forfeit,) = charges_of(lost, "DEPOSIT_FORFEIT")
        assert (forfeit["amountIncVat"], forfeit["vatAmount"], forfeit["status"]) == (
            "1200.00", "0.00", "SETTLED"
        )
        (recovery,) = charges_of(lost, "DAMAGE_RECOVERY")
        assert (recovery["amountExVat"], recovery["vatAmount"], recovery["amountIncVat"]) == (
            "2608.70", "391.30", "3000.00"
        )
        assert {fee["rentalItemId"], forfeit["rentalItemId"], recovery["rentalItemId"]} == {
            item_key
        }

    def test_the_unit_is_lost_and_closed_and_the_balance_waits_for_its_payment(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        session: Session,
    ) -> None:
        rental = on_hire(booking, world, assistant)
        booking.clock.advance(FIFTEEN_DAYS_LATE)
        (item_key,) = item_ids(rental)
        lost = answered(record_loss(booking, assistant, rental["id"], item_key))

        (item,) = lost["items"]
        assert (item["daysLate"], item["conditionIn"]) == (15, None)
        assert item["returnedAt"] == "2026-03-21T10:00:00+02:00"
        assert (lost["status"], lost["settlementWaitingOn"]) == ("RETURNED", "BALANCE_PAYMENT")
        assert (lost["depositWithheld"], lost["depositRefunded"]) == ("1200.00", "0.00")
        assert lost["balanceDue"] == "4680.00"
        unit = session.exec(select(Asset).where(col(Asset.asset_tag) == item["assetTag"])).one()
        session.refresh(unit)
        assert unit.status is AssetStatus.LOST

    def test_a_lost_unit_and_one_returned_on_time_share_the_deposit(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        rental = on_hire(booking, world, assistant, quantity=TWO_UNITS)
        first, second = item_ids(rental)
        answered(take_back(booking, assistant, rental["id"], return_body(first)))
        booking.clock.advance(FIFTEEN_DAYS_LATE)
        lost = answered(record_loss(booking, assistant, rental["id"], second))

        assert lost["depositHeld"] == "2400.00"
        assert (lost["depositWithheld"], lost["depositRefunded"]) == ("2400.00", "0.00")
        assert lost["balanceDue"] == "3480.00"
        assert charges_of(lost, "DEPOSIT_RELEASE") == []


class TestTheBalancePayment:
    """The simulated payment settles every charge still owed and the rental (BR-33, BR-53)."""

    def test_the_payment_settles_the_rental_and_every_charge_with_its_reference(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        session: Session,
    ) -> None:
        rental = on_hire(booking, world, assistant)
        booking.clock.advance(FIFTEEN_DAYS_LATE)
        (item_key,) = item_ids(rental)
        answered(record_loss(booking, assistant, rental["id"], item_key))
        paid = answered(pay_balance(booking, assistant, rental["id"], f"  {PAYMENT_REFERENCE} "))

        assert (paid["status"], paid["balanceDue"]) == ("SETTLED", "0.00")
        assert paid["settledAt"] == "2026-03-21T10:00:00+02:00"
        assert paid["settlementWaitingOn"] is None
        assert {charge["status"] for charge in paid["charges"]} == {"SETTLED"}
        references = {
            charge.charge_type.value: charge.payment_reference
            for charge in session.exec(select(Charge))
        }
        assert references["LATE_FEE"] == PAYMENT_REFERENCE
        assert references["DAMAGE_RECOVERY"] == PAYMENT_REFERENCE
        assert references["DEPOSIT_FORFEIT"] == f"SIM-{rental['reference']}-03"
