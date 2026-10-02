"""Reading one reservation and a list of them, run against ports and nothing else.

A customer reads their own reservations and nobody else's, and one that is
not theirs is answered in the words used for one that never existed (BR-42).
Staff read any customer's, at any branch. A list is newest first, can be
narrowed by status, and only staff may narrow it to one customer or one
branch.

The unit of work is the in memory double from tests/support, which applies the
scope of the caller the way the SQL repository does. The same reads run
against SQL in tests/api/test_reservation_reads.py.
"""

from __future__ import annotations

from typing import Final
from uuid import uuid4

import pytest

from app.application.booking.access import ReservationCommand
from app.application.booking.read_models import ReservationKey
from app.application.booking.read_reservation import ListReservationsQuery
from app.application.refusal import refused_parameter_of
from app.domain.enums import AccountStatus, ReservationStatus, UserRole
from app.domain.errors import AuthorisationFailure, NotFound, ValidationFailure
from app.domain.identity import Actor, CustomerProfile
from tests.support.memory_world import BookingDesk, MemoryWorld, build_memory_world, open_desk

NOT_FOUND_MESSAGE: Final[str] = (
    "We could not find that reservation. Check the reference and try again."
)


def second_customer(world: MemoryWorld) -> Actor:
    """Add a second customer with a profile to a world, and return them as an actor."""
    account_id = uuid4()
    world.store.profiles[account_id] = CustomerProfile(
        id=uuid4(),
        user_account_id=account_id,
        display_name="Pieter van Wyk",
        account_status=AccountStatus.ACTIVE,
        email="pieter.vanwyk@example.co.za",
        email_verified=True,
    )
    return Actor(user_id=account_id, role=UserRole.CUSTOMER)


def references_of(desk: BookingDesk, query: ListReservationsQuery) -> list[str]:
    """Return the references on one page of a list, in the order they were returned."""
    return [view.detail.reference for view in desk.reads.page(query).items]


class TestReadingOneReservation:
    """By its key or its reference, and only by somebody allowed to see it."""

    def test_the_owner_reads_their_reservation_by_its_key(self) -> None:
        desk = open_desk(build_memory_world())
        draft = desk.drafted()
        assert desk.reads.one(desk.command_for(draft)).detail == draft.detail

    def test_the_owner_reads_their_reservation_by_its_reference(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        draft = desk.drafted()
        by_reference = ReservationCommand(
            actor=world.customer, key=ReservationKey.parse(draft.detail.reference)
        )
        assert desk.reads.one(by_reference).detail.id == draft.detail.id

    def test_another_customers_reservation_is_not_found(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        draft = desk.drafted()
        with pytest.raises(NotFound) as refusal:
            desk.reads.one(desk.command_for(draft, actor=second_customer(world)))
        assert refusal.value.message == NOT_FOUND_MESSAGE

    def test_the_refusal_is_the_same_as_for_a_key_nobody_issued(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        draft = desk.drafted()
        stranger = second_customer(world)
        with pytest.raises(NotFound) as not_theirs:
            desk.reads.one(desk.command_for(draft, actor=stranger))
        missing = uuid4()
        with pytest.raises(NotFound) as never_issued:
            desk.reads.one(ReservationCommand(actor=stranger, key=ReservationKey.of(missing)))
        assert not_theirs.value.message == never_issued.value.message
        assert not_theirs.value.detail == {"reservation": str(draft.detail.id)}
        assert never_issued.value.detail == {"reservation": str(missing)}

    @pytest.mark.parametrize("at_own_branch", [True, False])
    def test_counter_staff_read_a_reservation_at_any_branch(self, at_own_branch: bool) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        held = desk.held()
        assistant = world.assistant(at_own_branch=at_own_branch)
        shown = desk.reads.one(desk.command_for(held, actor=assistant))
        assert shown.detail.lines[0].asset_tags == ("TSH-DR-0001",)
        assert shown.can_cancel is at_own_branch

    def test_a_customer_is_shown_their_hold_without_the_tags(self) -> None:
        desk = open_desk(build_memory_world())
        held = desk.held()
        shown = desk.reads.one(desk.command_for(held))
        assert shown.detail.lines[0].asset_tags == ()
        assert shown.detail.lines[0].allocated_count == 1
        assert (shown.can_hold, shown.can_confirm, shown.can_cancel) == (False, True, True)


class TestListingReservations:
    """Newest first, the caller's own unless they are staff."""

    def test_a_customer_sees_their_own_newest_first(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        first = desk.drafted().detail.reference
        second = desk.drafted().detail.reference
        third = desk.drafted().detail.reference
        assert references_of(desk, ListReservationsQuery(actor=world.customer)) == [
            third,
            second,
            first,
        ]

    def test_a_customer_does_not_see_anybody_elses(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        desk.drafted()
        page = desk.reads.page(ListReservationsQuery(actor=second_customer(world)))
        assert page.items == ()
        assert page.total == 0

    def test_staff_see_every_customers_reservations(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        other = second_customer(world)
        desk.drafted()
        desk.drafted(world.draft_command(actor=other))
        page = desk.reads.page(ListReservationsQuery(actor=world.assistant(at_own_branch=False)))
        assert page.total == 2

    def test_a_list_can_be_narrowed_to_one_status(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        desk.drafted()
        held = desk.held().detail.reference
        query = ListReservationsQuery(actor=world.customer, status=ReservationStatus.HELD)
        assert references_of(desk, query) == [held]

    def test_a_list_is_paged_and_reports_the_total(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        references = [desk.drafted().detail.reference for _ in range(5)]
        second_page = desk.reads.page(
            ListReservationsQuery(actor=world.customer, page=2, page_size=2)
        )
        assert [view.detail.reference for view in second_page.items] == [
            references[2],
            references[1],
        ]
        assert (second_page.page, second_page.page_size, second_page.total) == (2, 2, 5)

    def test_staff_narrow_a_list_to_one_customer(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        other = second_customer(world)
        desk.drafted()
        theirs = desk.drafted(world.draft_command(actor=other)).detail.reference
        other_profile = world.store.profiles[other.user_id]
        query = ListReservationsQuery(
            actor=world.assistant(), customer_profile_id=other_profile.id
        )
        assert references_of(desk, query) == [theirs]

    def test_staff_narrow_a_list_to_one_branch(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        here = desk.drafted().detail.reference
        query = ListReservationsQuery(actor=world.assistant(), branch_code=world.branch.code)
        assert references_of(desk, query) == [here]

    def test_an_unknown_branch_code_names_the_branch(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        with pytest.raises(ValidationFailure) as refusal:
            desk.reads.page(ListReservationsQuery(actor=world.assistant(), branch_code="XYZ"))
        assert refused_parameter_of(refusal.value) == "branch"

    def test_a_customer_may_not_narrow_a_list_to_a_customer(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        with pytest.raises(AuthorisationFailure):
            desk.reads.page(
                ListReservationsQuery(actor=world.customer, customer_profile_id=world.profile.id)
            )

    def test_a_customer_may_not_narrow_a_list_to_a_branch(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        with pytest.raises(AuthorisationFailure) as refusal:
            desk.reads.page(
                ListReservationsQuery(actor=world.customer, branch_code=world.branch.code)
            )
        assert refusal.value.message == (
            "Only a member of staff can list the reservations of another customer or of "
            "one branch."
        )
