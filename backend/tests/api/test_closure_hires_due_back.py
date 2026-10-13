"""The hires still out that a closure strands, through HTTP.

A customer who has the equipment cannot bring it back on a day the branch is
closed, so the impact read names every hire still out whose equipment is due
back that day, beside the bookings. A hire is out while it is open, partly
returned or overdue, and it is named by its own reference with the day it was
collected and the day it is due back. A hire brought back is not named. These
run against the in memory database on the still clock's Monday 2 March 2026.
"""

from __future__ import annotations

from datetime import date
from typing import Final

import pytest
from sqlmodel import Session

from app.domain.enums import RentalStatus, ReservationStatus, UserRole
from app.domain.period import BookingPeriod
from app.infrastructure.models import Branch, Rental, UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, answered, build_booking_world
from tests.support.closure_day_api import STOCKTAKE_DAY, read_impact
from tests.support.factories import Factory
from tests.support.hire_factories import HireFactory

# A hire collected on the sixteenth and due back on the stocktake day.
DUE_BACK_ON_THE_DAY: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 16), STOCKTAKE_DAY)
# A hire that went out the same day and is due back after it.
DUE_BACK_LATER: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 16), date(2026, 3, 23))


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Commit a branch, a hammer and a customer who can book it."""
    built = build_booking_world(factory)
    session.commit()
    return built


@pytest.fixture
def owner(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return the committed owner, an administrator."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return account


def hire_out(
    factory: Factory,
    world: BookingWorld,
    owner: UserAccount,
    *,
    period: BookingPeriod = DUE_BACK_ON_THE_DAY,
    status: RentalStatus = RentalStatus.OPEN,
    branch: Branch | None = None,
) -> Rental:
    """Write a collected booking of the world's hammer and the hire opened from it.

    A hire in RETURNED or SETTLED has every unit back. Any other still has
    the hammer out.
    """
    hires = HireFactory(factory)
    booked = hires.booking(
        profile=world.profile,
        created_by=world.customer,
        branch=branch or world.branch,
        model=world.product_model,
        units=world.assets,
        period=period,
        status=ReservationStatus.COLLECTED,
    )
    back = status in {RentalStatus.RETURNED, RentalStatus.SETTLED}
    return hires.rental(
        booked, checked_out_by=owner, units_back=len(world.assets) if back else 0, status=status
    )


class TestTheHiresDueBack:
    """A hire still out and due back that day is named beside the bookings."""

    @pytest.mark.parametrize(
        "still_out",
        [RentalStatus.OPEN, RentalStatus.PARTIALLY_RETURNED, RentalStatus.OVERDUE],
        ids=["open", "partly-returned", "overdue"],
    )
    def test_a_hire_still_out_and_due_back_that_day_is_named(
        self,
        session: Session,
        factory: Factory,
        booking: BookingClient,
        owner: UserAccount,
        world: BookingWorld,
        still_out: RentalStatus,
    ) -> None:
        rental = hire_out(factory, world, owner, status=still_out)
        session.commit()

        found = answered(
            read_impact(booking, owner, branchCode=world.branch.code, day=STOCKTAKE_DAY.isoformat())
        )

        assert found["total"] == 1
        assert found["items"] == [
            {
                "reference": rental.reference,
                "branchCode": world.branch.code,
                "customerName": world.profile.display_name,
                "customerPhone": world.profile.contact_phone,
                "from": DUE_BACK_ON_THE_DAY.start.isoformat(),
                "to": STOCKTAKE_DAY.isoformat(),
                "hireDay": "due_back",
            }
        ]

    @pytest.mark.parametrize(
        "brought_back", [RentalStatus.RETURNED, RentalStatus.SETTLED], ids=["returned", "settled"]
    )
    def test_a_hire_brought_back_is_not_named(
        self,
        session: Session,
        factory: Factory,
        booking: BookingClient,
        owner: UserAccount,
        world: BookingWorld,
        brought_back: RentalStatus,
    ) -> None:
        hire_out(factory, world, owner, status=brought_back)
        session.commit()

        found = answered(read_impact(booking, owner, day=STOCKTAKE_DAY.isoformat()))

        assert (found["items"], found["total"]) == ([], 0)

    def test_hires_due_back_another_day_or_at_another_branch_are_left_to_their_own(
        self,
        session: Session,
        factory: Factory,
        booking: BookingClient,
        owner: UserAccount,
        world: BookingWorld,
    ) -> None:
        here = hire_out(factory, world, owner)
        hire_out(factory, world, owner, period=DUE_BACK_LATER)
        elsewhere = hire_out(factory, world, owner, branch=factory.branch())
        held = factory.reservation(
            profile=world.profile,
            created_by=world.customer,
            branch=world.branch,
            period=BookingPeriod(STOCKTAKE_DAY, date(2026, 3, 24)),
        )
        session.commit()

        at_branch = answered(
            read_impact(booking, owner, branchCode=world.branch.code, day=STOCKTAKE_DAY.isoformat())
        )
        anywhere = answered(read_impact(booking, owner, day=STOCKTAKE_DAY.isoformat()))

        items = at_branch["items"]
        assert isinstance(items, list)
        assert [(item["reference"], item["hireDay"]) for item in items] == [
            (here.reference, "due_back"),
            (held.reference, "collection"),
        ]
        assert at_branch["total"] == 2
        listed = anywhere["items"]
        assert isinstance(listed, list)
        assert {item["reference"] for item in listed} == {
            here.reference,
            elsewhere.reference,
            held.reference,
        }
        assert anywhere["total"] == 3
