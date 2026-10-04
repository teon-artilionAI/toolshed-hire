"""Marking a booking as not collected, through HTTP (FR-12, US-37, BR-17, BR-18).

A counter assistant marks a confirmed booking for today as a no show, with a
reason. These pin the reservation that comes back, the unit that is free again,
the audit event, the count on the customer and the third strike that puts the
customer on hold, after which a booking is refused with a sentence that says
the account is on hold and to contact a branch.

The refusals of the route, with their statuses and their words, are cases in
tests/api/reservation_no_show_refusals.py. These run against the in memory
database, and the clock stands still on Monday the second of March 2026.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from sqlmodel import Session, col, select

from app.domain.enums import UserRole
from app.infrastructure.models import AuditEvent, UserAccount
from tests.support.booking_api import (
    FIRST_HIRE,
    BookingClient,
    BookingWorld,
    answered,
    build_booking_world,
    created,
)
from tests.support.checkout_api import confirmed_today, customer_path
from tests.support.counter_api import NO_SHOW_REASON, mark_no_show
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of

STRIKES: Final[int] = 3
ON_HOLD_SENTENCE: Final[str] = (
    "This customer account is on hold, so it cannot make a reservation. "
    "Please contact a branch."
)


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world whose branch holds one unit."""
    built = build_booking_world(factory)
    session.commit()
    return built


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


def customer_summary(
    booking: BookingClient, assistant: UserAccount, world: BookingWorld
) -> dict[str, object]:
    """Return the world's customer as the counter sees them."""
    return answered(
        booking.client.get(customer_path(world.profile.id), headers=booking.headers(assistant))
    )


class TestMarkingANoShow:
    """The reservation comes back NO_SHOW and its unit is free again."""

    def test_the_reservation_comes_back_as_not_collected_holding_nothing(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant)

        marked = answered(mark_no_show(booking, assistant, reservation["id"]))

        assert (marked["id"], marked["status"]) == (reservation["id"], "NO_SHOW")
        (line,) = marked["lines"]
        assert (line["allocatedCount"], line["assetTags"]) == (0, [])
        assert (marked["canHold"], marked["canConfirm"], marked["canCancel"]) == (
            False,
            False,
            False,
        )
        assert marked["cancellationReason"] is None

    def test_the_unit_is_free_for_another_booking_of_the_same_days(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        missed = confirmed_today(booking, world, assistant)
        answered(mark_no_show(booking, assistant, missed["id"]))
        assert confirmed_today(booking, world, assistant)["status"] == "CONFIRMED"

    def test_the_audit_event_names_the_assistant_and_keeps_the_reason(
        self,
        booking: BookingClient,
        session: Session,
        world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        reservation = confirmed_today(booking, world, assistant)
        answered(mark_no_show(booking, assistant, reservation["id"]))
        (event,) = session.exec(
            select(AuditEvent).where(col(AuditEvent.action) == "reservation.no_show")
        ).all()
        assert str(event.entity_id) == reservation["id"]
        assert (event.actor_user_id, event.actor_role) == (assistant.id, UserRole.COUNTER_STAFF)
        assert event.after_state is not None
        assert event.after_state["no_show_reason"] == NO_SHOW_REASON

    def test_the_count_on_the_customer_goes_up_by_one(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant)
        answered(mark_no_show(booking, assistant, reservation["id"]))
        summary = customer_summary(booking, assistant, world)
        assert (summary["noShowCount"], summary["accountStatus"]) == (1, "ACTIVE")

    def test_an_administrator_may_mark_one_at_any_branch(
        self, booking: BookingClient, factory: Factory, session: Session, world: BookingWorld
    ) -> None:
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        reservation = confirmed_today(booking, world, administrator)
        assert answered(mark_no_show(booking, administrator, reservation["id"]))["status"] == (
            "NO_SHOW"
        )


class TestTheThirdStrike:
    """Three no shows inside twelve months put the customer on hold, and booking is refused."""

    def test_the_third_no_show_puts_the_customer_on_hold_and_a_booking_is_refused_plainly(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        for _ in range(STRIKES):
            reservation = confirmed_today(booking, world, assistant)
            answered(mark_no_show(booking, assistant, reservation["id"]))

        summary = customer_summary(booking, assistant, world)
        assert (summary["noShowCount"], summary["accountStatus"]) == (STRIKES, "ON_HOLD")

        refused = booking.create(world.customer, world.payload(FIRST_HIRE))
        assert refused.status_code == status.HTTP_403_FORBIDDEN
        assert problem_code(refused) == "account-on-hold"
        assert problem_of(refused)["detail"] == ON_HOLD_SENTENCE

    def test_two_no_shows_leave_the_customer_free_to_book(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        for _ in range(STRIKES - 1):
            reservation = confirmed_today(booking, world, assistant)
            answered(mark_no_show(booking, assistant, reservation["id"]))
        assert customer_summary(booking, assistant, world)["accountStatus"] == "ACTIVE"
        created(booking.create(world.customer, world.payload(FIRST_HIRE)))

    def test_staff_cannot_book_for_a_customer_on_hold_either(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        for _ in range(STRIKES):
            reservation = confirmed_today(booking, world, assistant)
            answered(mark_no_show(booking, assistant, reservation["id"]))
        refused = booking.create(
            assistant, world.payload(FIRST_HIRE, customer_profile_id=world.profile.id)
        )
        assert refused.status_code == status.HTTP_403_FORBIDDEN
        assert problem_of(refused)["detail"] == ON_HOLD_SENTENCE
