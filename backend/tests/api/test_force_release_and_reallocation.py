"""Releasing a unit of a booking by hand and giving the booking a replacement (US-32, BR-08).

An administrator releases one of the two units of a booking for today. The
allocation keeps its row, released with the reason REALLOCATED, the booking
holds one unit fewer than it asks for, the checkout read says so and the
checkout is refused until counter staff of the branch ask for a replacement
through the allocation path a hold uses. These pin that, the refusals of the
release, a hold left short that cannot be confirmed until it is topped up, and
the audit event each writes.

The refusals of the reallocation route are in
tests/api/reservation_reallocation_refusals.py. These run against the in
memory database, and the clock stands still on Monday the second of March
2026.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID, uuid4

import pytest
from fastapi import status
from sqlmodel import Session, col, select

from app.application.booking.force_release import (
    ALLOCATION_NOT_FOUND_MESSAGE,
    RESERVATION_UNIT_RELEASED_ACTION,
)
from app.application.booking.reallocate import RESERVATION_REALLOCATED_ACTION
from app.domain.enums import ReleaseReason, UserRole
from app.domain.reallocation import (
    ALREADY_RELEASED_MESSAGE,
    ON_HIRE_MESSAGE,
    units_missing_message,
)
from app.domain.states.guards import NOT_EVERY_UNIT_HELD_MESSAGE
from app.infrastructure.models import AssetAllocation, AuditEvent, UserAccount
from tests.support.admin_api import REASON, held_units, reallocate, release
from tests.support.booking_api import BookingClient, BookingWorld, answered, build_booking_world
from tests.support.catalogue import refused_fields
from tests.support.checkout_api import (
    TODAY_HIRE,
    check_out,
    checked_out,
    checkout_body,
    confirmed_today,
    read_checkout,
)
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of

BOTH_UNITS: Final[int] = 2
ONE_SHORT: Final[int] = 1
TRANSITION: Final[str] = "state-transition"


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world whose branch holds two units of its model."""
    built = build_booking_world(factory, asset_count=BOTH_UNITS)
    session.commit()
    return built


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


@pytest.fixture
def administrator(session: Session, factory: Factory) -> UserAccount:
    """Return a committed administrator."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return account


def both_booked(booking: BookingClient, world: BookingWorld, assistant: UserAccount) -> str:
    """Book and confirm both units for today at the counter, and return the reservation's key."""
    return str(confirmed_today(booking, world, assistant, quantity=BOTH_UNITS)["id"])


def released_one(
    booking: BookingClient, administrator: UserAccount, key: str
) -> tuple[dict[str, object], dict[str, object]]:
    """Release the first unit of a booking by hand, and return the unit and the answer."""
    unit = held_units(booking, administrator, key)[0]
    return unit, answered(release(booking, administrator, unit["allocationId"]))


def drafted_today(booking: BookingClient, world: BookingWorld, staff: UserAccount) -> str:
    """Create a draft of both units for today at the counter, and return its key."""
    body = world.payload(TODAY_HIRE, quantity=BOTH_UNITS, customer_profile_id=world.profile.id)
    response = booking.create(staff, body)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return str(response.json()["id"])


def events_of(session: Session, action: str) -> list[AuditEvent]:
    """Return the audit events of one action, as committed."""
    session.expire_all()
    return list(session.exec(select(AuditEvent).where(col(AuditEvent.action) == action)))


class TestTheRelease:
    """One allocation is let go, and the booking knows it is short."""

    def test_the_booking_holds_one_unit_fewer_and_the_allocation_keeps_its_row(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        administrator: UserAccount,
        session: Session,
    ) -> None:
        key = both_booked(booking, world, assistant)
        unit, answer = released_one(booking, administrator, key)

        assert answer["status"] == "CONFIRMED"
        (line,) = answer["lines"]
        assert line["allocatedCount"] == ONE_SHORT
        assert unit["assetTag"] not in line["assetTags"]
        stored = session.get(AssetAllocation, UUID(str(unit["allocationId"])))
        assert stored is not None
        session.refresh(stored)
        assert stored.release_reason is ReleaseReason.REALLOCATED
        assert stored.released_at is not None

    def test_the_checkout_read_says_a_unit_is_missing_and_the_checkout_is_refused(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        administrator: UserAccount,
    ) -> None:
        key = both_booked(booking, world, assistant)
        released_one(booking, administrator, key)

        preview = answered(read_checkout(booking, assistant, key))
        assert (preview["unitsShort"], preview["canCheckOut"]) == (ONE_SHORT, False)
        assert preview["refusal"] == units_missing_message(ONE_SHORT)
        refused = check_out(booking, assistant, key, checkout_body(preview))
        assert refused.status_code == status.HTTP_409_CONFLICT
        assert problem_code(refused) == TRANSITION
        assert problem_of(refused)["detail"] == units_missing_message(ONE_SHORT)

    def test_the_release_is_recorded_with_the_reason_the_unit_and_what_is_short(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        administrator: UserAccount,
        session: Session,
    ) -> None:
        key = both_booked(booking, world, assistant)
        unit, _ = released_one(booking, administrator, key)

        (event,) = events_of(session, RESERVATION_UNIT_RELEASED_ACTION)
        assert (event.entity_type, str(event.entity_id)) == ("reservation", key)
        assert event.actor_user_id == administrator.id
        after = event.after_state or {}
        assert (after["reason"], after["asset_tag"], after["units_short"]) == (
            REASON, unit["assetTag"], ONE_SHORT
        )
        assert after["release_reason"] == ReleaseReason.REALLOCATED.value


class TestTheReplacement:
    """A short line is topped up through the allocation path of a hold."""

    def test_a_replacement_tops_the_line_up_and_the_booking_can_be_checked_out(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        administrator: UserAccount,
        session: Session,
    ) -> None:
        key = both_booked(booking, world, assistant)
        released_one(booking, administrator, key)

        topped_up = answered(reallocate(booking, assistant, key))
        (line,) = topped_up["lines"]
        assert (topped_up["status"], line["allocatedCount"]) == ("CONFIRMED", BOTH_UNITS)
        preview = answered(read_checkout(booking, assistant, key))
        assert (preview["unitsShort"], preview["canCheckOut"], preview["refusal"]) == (
            0, True, None
        )
        assert checked_out(booking, assistant, key)["status"] == "OPEN"
        (event,) = events_of(session, RESERVATION_REALLOCATED_ACTION)
        assert event.actor_user_id == assistant.id
        assert len((event.after_state or {})["asset_tags"]) == ONE_SHORT

    def test_a_booking_short_of_nothing_is_answered_as_it_stands(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        session: Session,
    ) -> None:
        key = both_booked(booking, world, assistant)
        answer = answered(reallocate(booking, assistant, key))
        assert answer["lines"][0]["allocatedCount"] == BOTH_UNITS
        assert events_of(session, RESERVATION_REALLOCATED_ACTION) == []

    def test_a_hold_left_short_cannot_be_confirmed_until_it_is_topped_up(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        administrator: UserAccount,
    ) -> None:
        draft = drafted_today(booking, world, assistant)
        answered(booking.hold(assistant, draft))
        released_one(booking, administrator, draft)

        refused = booking.confirm(assistant, draft)
        assert refused.status_code == status.HTTP_409_CONFLICT
        assert problem_of(refused)["detail"] == NOT_EVERY_UNIT_HELD_MESSAGE
        answered(reallocate(booking, assistant, draft))
        assert answered(booking.confirm(assistant, draft))["status"] == "CONFIRMED"


class TestWhatTheReleaseRefuses:
    """An allocation that is not active, a unit out on hire, and callers who are not admins."""

    def test_the_same_allocation_is_not_released_twice(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        administrator: UserAccount,
    ) -> None:
        key = both_booked(booking, world, assistant)
        unit, _ = released_one(booking, administrator, key)
        again = release(booking, administrator, unit["allocationId"])
        assert again.status_code == status.HTTP_409_CONFLICT
        assert problem_of(again)["detail"] == ALREADY_RELEASED_MESSAGE

    def test_a_unit_out_on_hire_on_its_booking_is_not_released(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        administrator: UserAccount,
    ) -> None:
        key = str(confirmed_today(booking, world, assistant)["id"])
        unit = held_units(booking, administrator, key)[0]
        checked_out(booking, assistant, key)
        refused = release(booking, administrator, unit["allocationId"])
        assert refused.status_code == status.HTTP_409_CONFLICT
        assert (problem_code(refused), problem_of(refused)["detail"]) == (
            TRANSITION, ON_HIRE_MESSAGE
        )

    def test_an_allocation_nobody_made_is_not_found(
        self, booking: BookingClient, administrator: UserAccount
    ) -> None:
        refused = release(booking, administrator, uuid4())
        assert refused.status_code == status.HTTP_404_NOT_FOUND
        assert problem_of(refused)["detail"] == ALLOCATION_NOT_FOUND_MESSAGE

    def test_a_reason_too_short_is_refused_naming_it(
        self, booking: BookingClient, administrator: UserAccount
    ) -> None:
        refused = release(booking, administrator, uuid4(), reason="abcd")
        assert refused.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert refused_fields(problem_of(refused)).keys() == {"body.reason"}

    @pytest.mark.parametrize("caller", ["assistant", "customer"])
    def test_counter_staff_and_customers_are_refused(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        caller: str,
    ) -> None:
        key = both_booked(booking, world, assistant)
        unit = held_units(booking, assistant, key)[0]
        account = assistant if caller == "assistant" else world.customer
        refused = release(booking, account, unit["allocationId"])
        assert refused.status_code == status.HTTP_403_FORBIDDEN
        assert answered(read_checkout(booking, assistant, key))["unitsShort"] == 0

    def test_a_caller_with_no_credential_is_refused(self, booking: BookingClient) -> None:
        refused = booking.client.post(
            f"/api/admin/allocations/{uuid4()}/release", json={"reason": REASON}
        )
        assert refused.status_code == status.HTTP_401_UNAUTHORIZED
