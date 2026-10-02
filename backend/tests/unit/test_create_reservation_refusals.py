"""What the use case that creates a draft refuses, and what it leaves behind.

Run against ports and nothing else, like test_create_reservation_use_case.py.
Every refusal about something the caller sent names the field it was sent in,
so a form can put the sentence beside the right input, and the sentence is a
plain one. Each refusal is also checked for what matters most, which is that
nothing was kept.

The clock stands still on Monday the second of March 2026 unless a test moves
it, so the booking window runs from that day to ninety days after it.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Final
from uuid import uuid4

import pytest

from app.application.booking.reservation_request import (
    CreateReservationCommand,
    RequestedLine,
)
from app.application.refusal import refused_parameter_of
from app.domain.enums import AccountStatus, UserRole
from app.domain.errors import (
    AccountOnHoldError,
    AuthorisationFailure,
    BranchScopeError,
    ValidationFailure,
)
from app.domain.identity import Actor
from app.domain.period import BookingPeriod
from tests.support.clock import FixedClock
from tests.support.memory_world import (
    FIRST_HIRE,
    MODEL_SLUG,
    MemoryWorld,
    build_memory_world,
    open_desk,
)

TODAY: Final[date] = date(2026, 3, 2)
LAST_BOOKABLE_START: Final[date] = TODAY + timedelta(days=90)
FORBIDDEN_IN_A_SENTENCE: Final[tuple[str, ...]] = ("BR-", "NFR-", "start=", "end=", "Attempted")


def refusal_of(world: MemoryWorld, command: CreateReservationCommand) -> ValidationFailure:
    """Run a command that is expected to be refused, and return the refusal."""
    with pytest.raises(ValidationFailure) as refusal:
        open_desk(world).create.execute(command)
    assert not any(mark in refusal.value.message for mark in FORBIDDEN_IN_A_SENTENCE)
    assert world.store.committed.reservations == []
    assert world.store.committed.audit_events == []
    return refusal.value


def with_lines(world: MemoryWorld, *lines: RequestedLine) -> CreateReservationCommand:
    """Return the world's draft command with its lines replaced."""
    return replace(world.draft_command(), lines=lines)


class TestThePeriod:
    """The booking window and the hire limits, each naming the date at fault."""

    def test_a_hire_starting_yesterday_names_the_start(self) -> None:
        world = build_memory_world()
        yesterday = BookingPeriod(TODAY - timedelta(days=1), TODAY + timedelta(days=2))
        refusal = refusal_of(world, world.draft_command(yesterday))
        assert refused_parameter_of(refusal) == "from"
        assert refusal.message == "The hire has to start today or later."
        assert refusal.rule == "BR-04"

    def test_a_hire_starting_today_is_accepted(self) -> None:
        world = build_memory_world()
        today = BookingPeriod(TODAY, TODAY + timedelta(days=2))
        draft = open_desk(world).drafted(world.draft_command(today))
        assert draft.detail.start_date == TODAY

    def test_the_day_is_the_business_day_and_not_the_utc_day(self) -> None:
        """At 23:00 UTC on the second it is already the third in Cape Town."""
        world = build_memory_world()
        late_evening = FixedClock(datetime(2026, 3, 2, 23, 0, tzinfo=UTC))
        second = BookingPeriod(TODAY, TODAY + timedelta(days=2))
        with pytest.raises(ValidationFailure) as refusal:
            open_desk(world, clock=late_evening).create.execute(world.draft_command(second))
        assert refusal.value.rule == "BR-04"

    def test_a_hire_starting_ninety_days_ahead_is_accepted(self) -> None:
        world = build_memory_world()
        horizon = BookingPeriod(LAST_BOOKABLE_START, LAST_BOOKABLE_START + timedelta(days=3))
        draft = open_desk(world).drafted(world.draft_command(horizon))
        assert draft.detail.start_date == LAST_BOOKABLE_START

    def test_a_hire_starting_ninety_one_days_ahead_names_the_start(self) -> None:
        world = build_memory_world()
        start = LAST_BOOKABLE_START + timedelta(days=1)
        refusal = refusal_of(
            world, world.draft_command(BookingPeriod(start, start + timedelta(days=3)))
        )
        assert refused_parameter_of(refusal) == "from"
        assert refusal.rule == "BR-05"

    def test_a_return_date_on_the_start_date_names_the_return(self) -> None:
        world = build_memory_world()
        command = replace(world.draft_command(), end=FIRST_HIRE.start)
        refusal = refusal_of(world, command)
        assert refused_parameter_of(refusal) == "to"
        assert refusal.message == "The return date has to be after the start date."

    def test_a_hire_longer_than_the_model_allows_names_the_model_and_the_return(self) -> None:
        world = build_memory_world(max_hire_days=2)
        refusal = refusal_of(world, world.draft_command())
        assert refused_parameter_of(refusal) == "to"
        assert refusal.message == "GBH 2-26 DRE Rotary Hammer can be hired for at most 2 days."
        assert refusal.rule == "BR-03"

    def test_a_hire_shorter_than_the_model_allows_names_the_model_and_the_return(self) -> None:
        world = build_memory_world(min_hire_days=5)
        refusal = refusal_of(world, world.draft_command())
        assert refused_parameter_of(refusal) == "to"
        assert refusal.message == (
            "GBH 2-26 DRE Rotary Hammer has to be hired for at least 5 days."
        )


class TestTheLines:
    """At least one line, a model once, and a quantity of one to ten."""

    def test_no_lines_names_the_lines(self) -> None:
        world = build_memory_world()
        refusal = refusal_of(world, with_lines(world))
        assert refused_parameter_of(refusal) == "lines"
        assert refusal.message == "Add at least one tool to the reservation."

    @pytest.mark.parametrize("quantity", [0, 11, -1])
    def test_a_quantity_outside_one_to_ten_names_the_quantity_of_its_line(
        self, quantity: int
    ) -> None:
        world = build_memory_world()
        refusal = refusal_of(world, world.draft_command(quantity=quantity))
        assert refused_parameter_of(refusal) == "lines.0.quantity"
        assert refusal.message == "You can hire between 1 and 10 of one tool at a time."

    @pytest.mark.parametrize("quantity", [1, 10])
    def test_the_two_ends_of_the_range_are_accepted(self, quantity: int) -> None:
        world = build_memory_world()
        draft = open_desk(world).drafted(world.draft_command(quantity=quantity))
        assert draft.detail.lines[0].quantity == quantity

    def test_one_model_named_twice_names_the_second_line(self) -> None:
        world = build_memory_world()
        line = RequestedLine(model_slug=MODEL_SLUG, quantity=1)
        refusal = refusal_of(world, with_lines(world, line, line))
        assert refused_parameter_of(refusal) == "lines.1.modelSlug"
        assert refusal.message == (
            "Each tool can appear once in a reservation. Change the quantity instead."
        )

    def test_a_slug_no_published_model_carries_names_its_line(self) -> None:
        world = build_memory_world()
        unknown = RequestedLine(model_slug="no-such-model", quantity=1)
        refusal = refusal_of(world, with_lines(world, unknown))
        assert refused_parameter_of(refusal) == "lines.0.modelSlug"
        assert refusal.message == (
            "We could not find that tool. Browse the catalogue to choose another."
        )

    def test_a_model_that_is_not_published_is_refused_in_the_same_words(self) -> None:
        world = build_memory_world()
        world.store.unpublished_slugs.add(MODEL_SLUG)
        refusal = refusal_of(world, world.draft_command())
        assert refused_parameter_of(refusal) == "lines.0.modelSlug"
        assert refusal.message == (
            "We could not find that tool. Browse the catalogue to choose another."
        )


class TestTheBranchAndTheCustomer:
    """Who the booking is for, where, and whether they may book at all."""

    def test_an_unknown_branch_code_names_the_branch(self) -> None:
        world = build_memory_world()
        refusal = refusal_of(world, replace(world.draft_command(), branch_code="XYZ"))
        assert refused_parameter_of(refusal) == "branchCode"
        assert refusal.message == (
            "We do not have a branch with that code. Choose a branch from the list."
        )

    def test_a_branch_that_has_stopped_trading_is_refused_like_an_unknown_one(self) -> None:
        world = build_memory_world()
        world.store.closed_branch_codes.add(world.branch.code)
        refusal = refusal_of(world, world.draft_command())
        assert refused_parameter_of(refusal) == "branchCode"

    def test_a_customer_who_names_a_profile_is_refused_even_when_it_is_their_own(self) -> None:
        world = build_memory_world()
        with pytest.raises(AuthorisationFailure) as refusal:
            open_desk(world).create.execute(
                world.draft_command(customer_profile_id=world.profile.id)
            )
        assert refusal.value.message == (
            "Only a member of staff can make a reservation for another customer."
        )
        assert world.store.committed.reservations == []

    def test_staff_who_name_no_customer_are_asked_for_one(self) -> None:
        world = build_memory_world()
        refusal = refusal_of(world, world.draft_command(actor=world.assistant()))
        assert refused_parameter_of(refusal) == "customerProfileId"
        assert refusal.message == "Choose the customer this reservation is for."

    def test_staff_who_name_a_customer_that_does_not_exist_are_told_so(self) -> None:
        world = build_memory_world()
        refusal = refusal_of(
            world, world.draft_command(actor=world.assistant(), customer_profile_id=uuid4())
        )
        assert refused_parameter_of(refusal) == "customerProfileId"
        assert refusal.message == (
            "We could not find that customer. Choose a customer from the list."
        )

    def test_a_customer_account_with_no_profile_cannot_book(self) -> None:
        world = build_memory_world()
        stranger = Actor(user_id=uuid4(), role=UserRole.CUSTOMER)
        refusal = refusal_of(world, world.draft_command(actor=stranger))
        assert refused_parameter_of(refusal) is None
        assert refusal.message.startswith("This account has no customer profile yet")

    def test_a_counter_assistant_cannot_book_at_another_branch(self) -> None:
        world = build_memory_world()
        elsewhere = world.assistant(at_own_branch=False)
        with pytest.raises(BranchScopeError):
            open_desk(world).create.execute(
                world.draft_command(actor=elsewhere, customer_profile_id=world.profile.id)
            )
        assert world.store.committed.reservations == []

    @pytest.mark.parametrize("standing", [AccountStatus.ON_HOLD, AccountStatus.BLACKLISTED])
    def test_a_customer_who_is_not_in_good_standing_cannot_create_a_draft(
        self, standing: AccountStatus
    ) -> None:
        world = build_memory_world(account_status=standing)
        with pytest.raises(AccountOnHoldError) as refusal:
            open_desk(world).drafted()
        assert refusal.value.rule == "BR-18"
        assert refusal.value.detail == {"account_status": standing.value}
        assert world.store.committed.reservations == []

    def test_staff_cannot_book_for_a_customer_who_is_on_hold_either(self) -> None:
        world = build_memory_world(account_status=AccountStatus.ON_HOLD)
        with pytest.raises(AccountOnHoldError):
            open_desk(world).drafted(
                world.draft_command(actor=world.assistant(), customer_profile_id=world.profile.id)
            )
