"""The six reservation routes and the shape of what each one answers with.

A customer builds a draft, holds it, confirms it, reads it, lists their
reservations and cancels one. This file walks that path and pins the contract
at every step. The names on the wire are camelCase, money is a string with two
decimals, a date is `YYYY-MM-DD` and an instant is ISO 8601 with the offset of
Cape Town.

The worked example is two rotary hammers for three days at 185.00 a day. That
is 1110.00 excluding VAT, 166.50 of VAT and 1276.50 in all, with 1200.00 of
deposit beside it.

These run against the in memory database, and the clock stands still on
Monday the second of March 2026 at 10:00 in Cape Town. What a route refuses is
in test_reservation_refusals.py.
"""

from __future__ import annotations

from typing import Final

from fastapi import status
from sqlmodel import Session, select

from app.domain.enums import UserRole
from app.infrastructure.models import AssetAllocation, Reservation
from tests.support.booking_api import (
    BookingClient,
    BookingWorld,
    answered,
    build_booking_world,
    reservation_path,
)
from tests.support.factories import Factory

RESERVATION_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "id",
        "reference",
        "status",
        "branchCode",
        "branchName",
        "from",
        "to",
        "hireDays",
        "lines",
        "subtotalExVat",
        "discountPercent",
        "vatAmount",
        "estimatedTotalIncVat",
        "depositTotal",
        "holdExpiresAt",
        "confirmedAt",
        "cancelledAt",
        "cancellationReason",
        "canHold",
        "canConfirm",
        "canCancel",
        "customerName",
        "createdAt",
    }
)
LINE_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "modelSlug",
        "modelName",
        "quantity",
        "dailyRate",
        "weeklyRate",
        "depositPerUnit",
        "lineSubtotalExVat",
        "allocatedCount",
        "assetTags",
    }
)
PAGE_MEMBERS: Final[frozenset[str]] = frozenset({"items", "page", "pageSize", "total"})
# The hold starts at 10:00 in Cape Town and lasts thirty minutes.
HOLD_RUNS_OUT_AT: Final[str] = "2026-03-02T10:30:00+02:00"
CONFIRMED_AT: Final[str] = "2026-03-02T10:00:00+02:00"
REASON: Final[str] = "The job was moved to next month."


def two_hammers(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world whose branch holds three rotary hammers."""
    world = build_booking_world(factory, asset_count=3)
    session.commit()
    return world


class TestCreatingADraft:
    """POST /api/reservations answers 201 with the reservation and where to read it."""

    def test_the_draft_is_returned_in_the_shape_of_the_contract(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = two_hammers(session, factory)
        response = booking.create(world.customer, world.payload(quantity=2))

        assert response.status_code == status.HTTP_201_CREATED
        body = response.json()
        assert body.keys() == RESERVATION_MEMBERS
        (line,) = body["lines"]
        assert line.keys() == LINE_MEMBERS
        assert body["status"] == "DRAFT"
        assert body["branchCode"] == world.branch.code
        assert body["branchName"] == world.branch.name
        assert (body["from"], body["to"], body["hireDays"]) == ("2026-03-09", "2026-03-12", 3)
        assert body["customerName"] == world.profile.display_name

    def test_the_figures_are_strings_with_two_decimals(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = two_hammers(session, factory)
        body = booking.drafted(world, quantity=2)
        (line,) = body["lines"]
        assert line == {
            "modelSlug": world.product_model.slug,
            "modelName": world.product_model.name,
            "quantity": 2,
            "dailyRate": "185.00",
            "weeklyRate": "740.00",
            "depositPerUnit": "600.00",
            "lineSubtotalExVat": "1110.00",
            "allocatedCount": 0,
            "assetTags": [],
        }
        assert body["subtotalExVat"] == "1110.00"
        assert body["discountPercent"] == "0.00"
        assert body["vatAmount"] == "166.50"
        assert body["estimatedTotalIncVat"] == "1276.50"
        assert body["depositTotal"] == "1200.00"

    def test_a_draft_holds_nothing_and_offers_hold_and_cancel(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = two_hammers(session, factory)
        body = booking.drafted(world, quantity=2)
        assert body["holdExpiresAt"] is None
        assert body["confirmedAt"] is None
        assert body["cancelledAt"] is None
        assert body["cancellationReason"] is None
        assert (body["canHold"], body["canConfirm"], body["canCancel"]) == (True, False, True)
        assert session.exec(select(AssetAllocation)).all() == []

    def test_the_location_header_is_the_path_of_the_new_reservation(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = two_hammers(session, factory)
        response = booking.create(world.customer, world.payload())
        location = response.headers["Location"]
        assert location == reservation_path(response.json()["id"])
        assert answered(booking.client.get(location, headers=booking.headers(world.customer)))[
            "id"
        ] == response.json()["id"]

    def test_the_reference_has_the_documented_form(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = two_hammers(session, factory)
        reference = str(booking.drafted(world)["reference"])
        assert reference.startswith("TSH-R-26-")
        assert len(reference) == len("TSH-R-26-000124")

    def test_notes_are_stored_with_the_reservation(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = two_hammers(session, factory)
        body = {**world.payload(), "notes": "Collecting with a bakkie, please have it at the gate."}
        created = booking.create(world.customer, body).json()
        stored = session.exec(select(Reservation)).one()
        assert str(stored.id) == created["id"]
        assert stored.notes == body["notes"]


class TestHoldingConfirmingAndCancelling:
    """Each move answers 200 with the reservation as it now stands."""

    def test_a_hold_answers_with_the_expiry_thirty_minutes_ahead_in_cape_town_time(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = two_hammers(session, factory)
        draft = booking.drafted(world, quantity=2)
        response = booking.hold(world.customer, draft["id"])

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body.keys() == RESERVATION_MEMBERS
        assert body["status"] == "HELD"
        assert body["holdExpiresAt"] == HOLD_RUNS_OUT_AT
        assert body["lines"][0]["allocatedCount"] == 2
        assert (body["canHold"], body["canConfirm"], body["canCancel"]) == (False, True, True)

    def test_a_confirmation_clears_the_expiry_and_says_when_it_happened(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = two_hammers(session, factory)
        held = booking.held(world)
        response = booking.confirm(world.customer, held["id"])

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["status"] == "CONFIRMED"
        assert body["holdExpiresAt"] is None
        assert body["confirmedAt"] == CONFIRMED_AT
        assert (body["canHold"], body["canConfirm"], body["canCancel"]) == (False, False, True)

    def test_a_cancellation_answers_with_when_and_why(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = two_hammers(session, factory)
        held = booking.held(world)
        response = booking.cancel(world.customer, held["id"], REASON)

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["status"] == "CANCELLED"
        assert body["cancelledAt"] == CONFIRMED_AT
        assert body["cancellationReason"] == REASON
        assert body["lines"][0]["allocatedCount"] == 0
        assert (body["canHold"], body["canConfirm"], body["canCancel"]) == (False, False, False)

    def test_a_cancellation_needs_no_body_at_all(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = two_hammers(session, factory)
        held = booking.held(world)
        response = booking.client.post(
            f"{reservation_path(held['id'])}/cancellation",
            headers=booking.headers(world.customer),
        )
        assert answered(response)["cancellationReason"] is None

    def test_every_move_can_name_the_reservation_by_its_reference(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = two_hammers(session, factory)
        reference = booking.drafted(world)["reference"]
        assert answered(booking.hold(world.customer, reference))["status"] == "HELD"
        assert answered(booking.confirm(world.customer, reference))["status"] == "CONFIRMED"
        assert answered(booking.cancel(world.customer, reference))["status"] == "CANCELLED"

    def test_there_is_no_route_that_deletes_a_reservation(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = two_hammers(session, factory)
        draft = booking.drafted(world)
        response = booking.client.delete(
            reservation_path(draft["id"]), headers=booking.headers(world.customer)
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert len(session.exec(select(Reservation)).all()) == 1


class TestTheCustomerIsNeverShownATag:
    """Staff see which units were given. The customer sees how many (US-07)."""

    def test_the_customer_is_sent_an_empty_list_of_tags(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = two_hammers(session, factory)
        held = booking.held(world, quantity=2)
        (line,) = held["lines"]
        assert line["assetTags"] == []
        assert line["allocatedCount"] == 2
        tags = {asset.asset_tag for asset in world.assets}
        assert not any(tag in booking.read(world.customer, held["id"]).text for tag in tags)

    def test_counter_staff_and_administrators_are_sent_the_tags(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = two_hammers(session, factory)
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        held = booking.held(world, quantity=2)
        expected = sorted(asset.asset_tag for asset in world.assets)[:2]
        for member_of_staff in (assistant, administrator):
            body = answered(booking.read(member_of_staff, held["id"]))
            assert body["lines"][0]["assetTags"] == expected
