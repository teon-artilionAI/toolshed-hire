"""Checking a reservation out, through HTTP (FR-17, US-22, BR-26 to BR-28).

A counter assistant hands every unit of a confirmed reservation over with its
condition and gets the rental back. These pin the shape of the rental, the
figures of the two charges, what happened to the units and to the reservation,
the audit trail, and a checkout asked for twice.

The two reads are pinned in tests/api/test_checkout_reads.py, and the
refusals, with their statuses and their words, are cases in
tests/api/reservation_checkout_refusals.py. These run against the in memory
database, and the clock stands still on Monday the second of March 2026, which
is the first day of the hire every test here books.
"""

from __future__ import annotations

import re
from typing import Final
from uuid import UUID

import pytest
from fastapi import status
from sqlmodel import Session, col, select

from app.domain.enums import AssetStatus, ConditionGrade, UserRole
from app.infrastructure.models import Asset, AuditEvent, Charge, UserAccount
from tests.support.booking_api import (
    BookingClient,
    BookingWorld,
    answered,
    build_booking_world,
    created,
)
from tests.support.checkout_api import (
    CHARGE_MEMBERS,
    ITEM_MEMBERS,
    RENTAL_MEMBERS,
    TODAY_HIRE,
    check_out,
    checked_out,
    checkout_body,
    confirmed_today,
    read_checkout,
)
from tests.support.factories import Factory

RENTAL_REFERENCE: Final[re.Pattern[str]] = re.compile(r"^TSH-H-26-\d{6}$")
PAYMENT_REFERENCE: Final[str] = "SIM-{reference}-{position:02d}"
LOCATION_HEADER: Final[str] = "Location"
TWO_UNITS: Final[int] = 2
THREE_UNITS: Final[int] = 3
# Three days of a model at R185.00 a day, and its deposit of R600.00.
THREE_DAYS_EX_VAT: Final[str] = "555.00"
THREE_DAYS_VAT: Final[str] = "83.25"
THREE_DAYS_INC_VAT: Final[str] = "638.25"
ONE_DEPOSIT: Final[str] = "600.00"
HOUR_METER: Final[int] = 412
ACCESSORIES: Final[str] = "Chuck key, side handle"


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world whose branch holds three units."""
    built = build_booking_world(factory, asset_count=THREE_UNITS)
    session.commit()
    return built


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


class TestTheCheckout:
    """POST /api/reservations/{id}/checkout, which opens the rental."""

    def test_the_rental_has_the_shape_of_the_contract(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant)
        rental = checked_out(booking, assistant, reservation["id"])

        assert rental.keys() == RENTAL_MEMBERS
        assert RENTAL_REFERENCE.match(str(rental["reference"]))
        assert (rental["status"], rental["reservationId"]) == ("OPEN", reservation["id"])
        assert rental["reservationReference"] == reservation["reference"]
        assert (rental["branchCode"], rental["branchName"]) == (
            world.branch.code, world.branch.name
        )
        assert rental["customerProfileId"] == str(world.profile.id)
        assert (rental["customerName"], rental["customerPhone"]) == (
            world.profile.display_name, world.profile.contact_phone
        )
        assert (rental["from"], rental["dueBackOn"]) == ("2026-03-02", "2026-03-05")
        assert rental["checkedOutAt"] == "2026-03-02T10:00:00+02:00"
        assert (rental["returnedAt"], rental["settledAt"]) == (None, None)
        assert (rental["agreementSigned"], rental["canReturn"]) == (True, True)
        assert rental["settlementWaitingOn"] == "ITEMS_OUT"

    def test_the_rental_holds_the_deposit_and_owes_nothing(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant)
        rental = checked_out(booking, assistant, reservation["id"])
        assert (rental["depositHeld"], rental["depositWithheld"]) == (ONE_DEPOSIT, "0.00")
        assert (rental["depositRefunded"], rental["balanceDue"]) == ("0.00", "0.00")

    def test_each_unit_becomes_an_item_with_what_the_counter_recorded(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant)
        preview = answered(read_checkout(booking, assistant, reservation["id"]))
        body = checkout_body(preview, hourMeterOut=HOUR_METER, accessoriesOut=ACCESSORIES)
        body["items"][0]["conditionOut"] = "B"
        rental = created(check_out(booking, assistant, reservation["id"], body))

        (item,) = rental["items"]
        assert item.keys() == ITEM_MEMBERS
        assert item["assetTag"] == preview["units"][0]["assetTag"]
        assert (item["modelName"], item["modelSlug"]) == (
            world.product_model.name, world.product_model.slug
        )
        assert (item["conditionOut"], item["hourMeterOut"], item["accessoriesOut"]) == (
            "B", HOUR_METER, ACCESSORIES
        )
        assert (item["conditionIn"], item["hourMeterIn"], item["accessoriesIn"]) == (
            None, None, None
        )
        assert (item["returnedAt"], item["daysLate"], item["lateFeePerDay"]) == (
            None, 0, "120.00"
        )
        assert (item["daysLateToday"], item["lateFeeToday"]) == (0, "0.00")
        assert item["damageAssessment"] == "NOT_NEEDED"

    def test_the_hire_charge_is_the_stored_total_and_belongs_to_the_one_unit(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant)
        rental = checked_out(booking, assistant, reservation["id"])

        hire, deposit = rental["charges"]
        assert hire.keys() == CHARGE_MEMBERS
        assert (hire["type"], hire["status"]) == ("HIRE", "SETTLED")
        assert (hire["amountExVat"], hire["vatRate"], hire["vatAmount"]) == (
            THREE_DAYS_EX_VAT, "15.00", THREE_DAYS_VAT
        )
        assert hire["amountIncVat"] == THREE_DAYS_INC_VAT == reservation["estimatedTotalIncVat"]
        assert hire["description"] == f"{world.product_model.name}, 3 days"
        assert hire["rentalItemId"] == rental["items"][0]["id"]
        assert hire["raisedAt"] == rental["checkedOutAt"]

    def test_the_deposit_hold_carries_no_vat_and_belongs_to_the_hire(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant)
        rental = checked_out(booking, assistant, reservation["id"])

        _hire, deposit = rental["charges"]
        assert (deposit["type"], deposit["status"], deposit["rentalItemId"]) == (
            "DEPOSIT_HOLD", "SETTLED", None
        )
        assert deposit["description"] == "Refundable deposit held at collection"
        assert (deposit["amountExVat"], deposit["vatRate"], deposit["vatAmount"]) == (
            ONE_DEPOSIT, "0.00", "0.00"
        )
        assert deposit["amountIncVat"] == ONE_DEPOSIT

    def test_both_charges_are_paid_at_the_counter_with_a_simulated_reference(
        self,
        booking: BookingClient,
        session: Session,
        world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        reservation = confirmed_today(booking, world, assistant)
        rental = checked_out(booking, assistant, reservation["id"])
        stored = session.exec(
            select(Charge).where(col(Charge.rental_id) == UUID(str(rental["id"])))
        ).all()
        references = sorted(str(charge.payment_reference) for charge in stored)
        assert references == [
            PAYMENT_REFERENCE.format(reference=rental["reference"], position=position)
            for position in (1, 2)
        ]
        assert {charge.raised_by_user_id for charge in stored} == {assistant.id}
        assert all(charge.settled_at is not None for charge in stored)

    def test_a_hire_of_several_units_holds_a_deposit_for_each_and_one_charge_for_the_hire(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant, quantity=TWO_UNITS)
        rental = checked_out(booking, assistant, reservation["id"])
        hire, deposit = rental["charges"]
        assert len(rental["items"]) == TWO_UNITS
        assert rental["depositHeld"] == deposit["amountIncVat"] == "1200.00"
        assert hire["rentalItemId"] is None
        assert hire["amountIncVat"] == reservation["estimatedTotalIncVat"]
        assert hire["description"] == f"2 x {world.product_model.name}, 3 days"

    def test_the_answer_is_201_with_the_address_of_the_rental(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant)
        preview = answered(read_checkout(booking, assistant, reservation["id"]))
        response = check_out(booking, assistant, reservation["id"], checkout_body(preview))
        assert response.status_code == status.HTTP_201_CREATED
        assert response.headers[LOCATION_HEADER] == f"/api/rentals/{response.json()['id']}"

    def test_the_reservation_is_collected_and_the_units_are_on_hire(
        self,
        booking: BookingClient,
        session: Session,
        world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        reservation = confirmed_today(booking, world, assistant)
        preview = answered(read_checkout(booking, assistant, reservation["id"]))
        body = checkout_body(preview, hourMeterOut=HOUR_METER, conditionOut="C")
        created(check_out(booking, assistant, reservation["id"], body))

        assert answered(booking.read(assistant, reservation["id"]))["status"] == "COLLECTED"
        tag = preview["units"][0]["assetTag"]
        unit = session.exec(select(Asset).where(col(Asset.asset_tag) == tag)).one()
        session.refresh(unit)
        assert (unit.status, unit.condition_grade) == (AssetStatus.ON_HIRE, ConditionGrade.C)
        assert unit.hour_meter_reading == HOUR_METER
        others = session.exec(select(Asset).where(col(Asset.asset_tag) != tag)).all()
        assert {other.status for other in others} == {AssetStatus.AVAILABLE}

    def test_the_reservation_the_rental_and_every_unit_are_audited(
        self,
        booking: BookingClient,
        session: Session,
        world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        reservation = confirmed_today(booking, world, assistant, quantity=TWO_UNITS)
        rental = checked_out(booking, assistant, reservation["id"])
        events = {
            (event.action, str(event.entity_id)): event
            for event in session.exec(select(AuditEvent)).all()
        }
        collected = events[("reservation.collected", str(reservation["id"]))]
        assert collected.after_state is not None
        assert collected.after_state["status"] == "COLLECTED"
        assert collected.after_state["rental_reference"] == rental["reference"]
        opened = events[("rental.checked_out", str(rental["id"]))]
        assert opened.actor_user_id == assistant.id
        assert opened.after_state is not None
        assert opened.after_state["asset_tags"] == reservation["lines"][0]["assetTags"]
        moved = [
            event for (action, _key), event in events.items() if action == "asset.status_changed"
        ]
        assert len(moved) == TWO_UNITS
        assert {str(event.before_state) for event in moved} == {str({"status": "AVAILABLE"})}

    def test_an_administrator_checks_out_at_any_branch(
        self, booking: BookingClient, session: Session, factory: Factory, world: BookingWorld
    ) -> None:
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        reservation = confirmed_today(booking, world, administrator)
        assert checked_out(booking, administrator, reservation["id"])["status"] == "OPEN"

    def test_a_walk_in_booked_and_confirmed_at_the_counter_is_checked_out(
        self,
        booking: BookingClient,
        session: Session,
        factory: Factory,
        world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        """BR-47 is satisfied by the counter, so a customer with no address can be served."""
        walk_in = factory.customer_profile(branch=world.branch)
        session.commit()
        body = world.payload(TODAY_HIRE, customer_profile_id=walk_in.id)
        draft = created(booking.create(assistant, body))
        answered(booking.hold(assistant, draft["id"]))
        answered(booking.confirm(assistant, draft["id"]))
        rental = checked_out(booking, assistant, draft["id"])
        assert rental["customerName"] == walk_in.display_name
