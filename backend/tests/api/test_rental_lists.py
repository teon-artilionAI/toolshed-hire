"""The two lists of rentals, and the sweep that marks a hire overdue, through HTTP (BR-42, BR-52).

Staff list rentals at any branch, the overdue first and then the newest, and
narrow the list by branch, status, customer or to the overdue alone. Reading
the list runs the sweep, which moves a hire with a unit out past its due date
to OVERDUE. A customer lists their own rentals, newest first, and never sees
an asset tag.

Two hires go out on Monday the second of March. The first is due back on the
fourth and the second on the sixth, so on the fifth the first is overdue and
the second is not.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Final

import pytest
from sqlmodel import Session, col, select

from app.domain.enums import UserRole
from app.domain.period import BookingPeriod
from app.infrastructure.models import AuditEvent, UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, answered
from tests.support.checkout_api import RENTAL_MEMBERS, TODAY
from tests.support.factories import Factory
from tests.support.rental_api import (
    item_ids,
    list_rentals,
    my_rentals,
    on_hire,
    return_body,
    take_back,
    worked_example_world,
)

DUE_ON_THE_FOURTH: Final[BookingPeriod] = BookingPeriod(TODAY, date(2026, 3, 4))
TO_THE_FIFTH: Final[timedelta] = timedelta(days=3)
THREE_UNITS: Final[int] = 3
PAGE_MEMBERS: Final[frozenset[str]] = frozenset({"items", "page", "pageSize", "total"})


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world of three units."""
    return worked_example_world(session, factory, units=THREE_UNITS)


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


@pytest.fixture
def two_hires(
    booking: BookingClient, world: BookingWorld, assistant: UserAccount
) -> tuple[dict[str, object], dict[str, object]]:
    """Put out a hire due back on the fourth and one due on the sixth, and move to the fifth."""
    early = on_hire(booking, world, assistant, period=DUE_ON_THE_FOURTH)
    later = on_hire(booking, world, assistant)
    booking.clock.advance(TO_THE_FIFTH)
    return early, later


class TestTheStaffList:
    """Any branch, the overdue first, and the sweep before the answer."""

    def test_the_list_runs_the_sweep_and_puts_the_overdue_hire_first(
        self,
        booking: BookingClient,
        assistant: UserAccount,
        session: Session,
        two_hires: tuple[dict[str, object], dict[str, object]],
    ) -> None:
        early, later = two_hires
        page = answered(list_rentals(booking, assistant))

        assert page.keys() == PAGE_MEMBERS
        assert (page["page"], page["pageSize"], page["total"]) == (1, 20, 2)
        first, second = page["items"]
        assert first.keys() == RENTAL_MEMBERS
        assert (first["id"], first["status"]) == (early["id"], "OVERDUE")
        assert (second["id"], second["status"]) == (later["id"], "OPEN")
        (event,) = session.exec(
            select(AuditEvent).where(col(AuditEvent.action) == "rental.overdue")
        ).all()
        assert (event.actor_user_id, event.actor_role) == (None, None)

    def test_the_filters_narrow_the_list(
        self,
        booking: BookingClient,
        assistant: UserAccount,
        world: BookingWorld,
        two_hires: tuple[dict[str, object], dict[str, object]],
    ) -> None:
        early, later = two_hires
        overdue = answered(list_rentals(booking, assistant, overdueOnly="true"))
        assert [rental["id"] for rental in overdue["items"]] == [early["id"]]
        open_ones = answered(list_rentals(booking, assistant, status="OPEN"))
        assert [rental["id"] for rental in open_ones["items"]] == [later["id"]]
        at_branch = answered(
            list_rentals(
                booking,
                assistant,
                branchCode=world.branch.code,
                customerProfileId=str(world.profile.id),
                pageSize=1,
                page=2,
            )
        )
        assert (at_branch["total"], len(at_branch["items"])) == (2, 1)
        assert at_branch["items"][0]["id"] == later["id"]

    def test_returning_the_overdue_hire_moves_it_on(
        self,
        booking: BookingClient,
        assistant: UserAccount,
        two_hires: tuple[dict[str, object], dict[str, object]],
    ) -> None:
        early, _later = two_hires
        answered(list_rentals(booking, assistant))
        back = answered(take_back(booking, assistant, early["id"], return_body(*item_ids(early))))
        assert back["status"] == "SETTLED"
        overdue = answered(list_rentals(booking, assistant, overdueOnly="true"))
        assert overdue["items"] == []


class TestTheCustomerList:
    """Their own rentals only, newest first, and never a tag (US-07, BR-42)."""

    def test_a_customer_sees_their_own_rentals_with_no_tag(
        self,
        booking: BookingClient,
        world: BookingWorld,
        two_hires: tuple[dict[str, object], dict[str, object]],
    ) -> None:
        early, later = two_hires
        page = answered(my_rentals(booking, world.customer))

        assert page["total"] == 2
        assert [rental["id"] for rental in page["items"]] == [later["id"], early["id"]]
        tags = [item["assetTag"] for rental in page["items"] for item in rental["items"]]
        values = [item["replacementValue"] for rental in page["items"] for item in rental["items"]]
        assert tags == values == [None, None]
        assert all(rental["canReturn"] is False for rental in page["items"])

    def test_another_customer_sees_none_of_them(
        self,
        booking: BookingClient,
        factory: Factory,
        session: Session,
        world: BookingWorld,
        two_hires: tuple[dict[str, object], dict[str, object]],
    ) -> None:
        stranger = factory.user(role=UserRole.CUSTOMER)
        factory.customer_profile(branch=world.branch, account=stranger)
        session.commit()
        page = answered(my_rentals(booking, stranger))
        assert (page["items"], page["total"]) == ([], 0)
