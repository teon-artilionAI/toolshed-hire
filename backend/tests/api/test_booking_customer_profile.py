"""A reservation belongs to a customer profile, not to a sign in account.

A signed in customer has an account, and the reservation is owned by that
account's customer profile, so that a walk-in with no login can own a booking
history on the same terms. A customer books for their own profile. Counter
staff and administrators name the profile they are booking for. These tests
pin both halves of that. The right profile is recorded, and a caller with no
profile to book for cannot make a reservation at all.

They also pin what is copied when a line is added. The five figures of the
model are written onto the line (BR-20) and the trade discount of the customer
is the one the totals were worked out with (BR-21).

These run against the in memory database, like the rest of tests/api.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final
from uuid import UUID

from fastapi import status
from sqlmodel import Session, select

from app.domain.enums import UserRole
from app.infrastructure.models import Reservation, ReservationLine
from tests.support.booking_api import BookingClient, answered, build_booking_world, created
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of

VALIDATION_PROBLEM: Final[str] = "validation-failure"
TEN_PERCENT: Final[Decimal] = Decimal("10.00")


def stored_reservation(session: Session, response_body: dict[str, object]) -> Reservation:
    """Return the reservation row a response describes."""
    reservation = session.get(Reservation, UUID(str(response_body["id"])))
    assert reservation is not None, "The API reported a reservation that is not in the database."
    return reservation


class TestTheReservationIsOwnedByTheCustomersProfile:
    """The account is how the caller is named. The profile is what owns the booking."""

    def test_a_customer_booking_is_recorded_against_their_own_profile(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = build_booking_world(factory)
        session.commit()
        reservation = stored_reservation(session, booking.drafted(world))
        assert reservation.customer_profile_id == world.profile.id
        assert reservation.created_by_user_id == world.customer.id

    def test_counter_staff_booking_for_a_customer_is_recorded_against_that_customers_profile(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = build_booking_world(factory)
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
        session.commit()
        body = created(
            booking.create(assistant, world.payload(customer_profile_id=world.profile.id))
        )
        reservation = stored_reservation(session, body)
        assert reservation.customer_profile_id == world.profile.id
        assert reservation.created_by_user_id == assistant.id
        assert body["customerName"] == world.profile.display_name

    def test_staff_book_for_a_walk_in_who_has_a_profile_and_no_account(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = build_booking_world(factory)
        walk_in = factory.customer_profile(branch=world.branch)
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        draft = created(
            booking.create(administrator, world.payload(customer_profile_id=walk_in.id))
        )
        answered(booking.hold(administrator, draft["id"]))
        confirmed = answered(booking.confirm(administrator, draft["id"]))
        assert confirmed["status"] == "CONFIRMED"
        assert confirmed["customerName"] == walk_in.display_name
        assert stored_reservation(session, draft).customer_profile_id == walk_in.id

    def test_the_customer_reads_the_reservation_staff_made_for_them(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = build_booking_world(factory)
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
        session.commit()
        draft = created(
            booking.create(assistant, world.payload(customer_profile_id=world.profile.id))
        )
        assert answered(booking.read(world.customer, draft["id"]))["id"] == draft["id"]


class TestWhatIsCopiedWhenTheLineIsAdded:
    """The snapshots of the model and the discount of the customer."""

    def test_the_line_snapshots_every_price_on_the_product_model(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        """BR-20. A later catalogue price change must not rewrite this booking."""
        world = build_booking_world(factory)
        session.commit()
        booking.drafted(world)
        line = session.exec(select(ReservationLine)).one()
        model = world.product_model
        assert line.daily_rate_snapshot == model.daily_rate
        assert line.weekly_rate_snapshot == model.weekly_rate
        assert line.deposit_snapshot == model.deposit_amount
        assert line.late_fee_per_day_snapshot == model.late_fee_per_day
        assert line.replacement_value_snapshot == model.replacement_value

    def test_the_stored_totals_are_the_ones_the_response_reported(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = build_booking_world(factory)
        session.commit()
        body = booking.drafted(world)
        reservation = stored_reservation(session, body)
        assert f"{reservation.subtotal_ex_vat:.2f}" == body["subtotalExVat"] == "555.00"
        assert f"{reservation.vat_amount:.2f}" == body["vatAmount"] == "83.25"
        assert f"{reservation.estimated_total_inc_vat:.2f}" == body["estimatedTotalIncVat"]
        assert body["estimatedTotalIncVat"] == "638.25"
        assert f"{reservation.deposit_total:.2f}" == body["depositTotal"] == "600.00"

    def test_a_trade_customers_discount_is_applied_and_stored_on_the_line(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        """555.00 less ten percent is 499.50, and the VAT on that is 74.93."""
        world = build_booking_world(factory, trade_discount_percent=TEN_PERCENT)
        session.commit()
        body = booking.drafted(world)
        assert body["discountPercent"] == "10.00"
        assert body["subtotalExVat"] == "499.50"
        assert body["vatAmount"] == "74.93"
        assert body["estimatedTotalIncVat"] == "574.43"
        assert session.exec(select(ReservationLine)).one().discount_percent == TEN_PERCENT

    def test_a_price_change_after_the_draft_leaves_the_reservation_as_it_was(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = build_booking_world(factory)
        session.commit()
        draft = booking.drafted(world)
        world.product_model.daily_rate = Decimal("999.00")
        world.product_model.deposit_amount = Decimal("9.00")
        session.add(world.product_model)
        session.commit()
        held = answered(booking.hold(world.customer, draft["id"]))
        for body in (held, answered(booking.read(world.customer, draft["id"]))):
            assert body["lines"][0]["dailyRate"] == "185.00"
            assert body["estimatedTotalIncVat"] == draft["estimatedTotalIncVat"]
            assert body["depositTotal"] == draft["depositTotal"]


class TestACallerWithNoProfileToBookFor:
    """Staff accounts carry no customer profile, so they cannot be the customer."""

    def test_a_customer_account_with_no_profile_is_refused_in_a_plain_sentence(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = build_booking_world(factory)
        without_a_profile = factory.user(role=UserRole.CUSTOMER)
        session.commit()
        response = booking.create(without_a_profile, world.payload())
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert problem_code(response) == VALIDATION_PROBLEM
        assert problem_of(response)["detail"] == (
            "This account has no customer profile yet, so it cannot make a reservation. "
            "Please speak to the branch."
        )

    def test_a_refused_booking_leaves_no_reservation_behind(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = build_booking_world(factory)
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        response = booking.create(administrator, world.payload())
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert session.exec(select(Reservation)).all() == []
