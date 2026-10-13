"""The owner's closure days on PostgreSQL (revision 0013).

The unique index of revision 0013 allows one live closure per branch and day,
and one for every branch per day through the nil UUID it keys them on. It has
the last word when two owners close the same day at once, and the repository
turns its refusal into the conflict the use case answers. A cancelled closure
holds nothing. A closure the owner adds through the route is in the calendar
every booking checks from the next request on, so a hire collected that day is
refused naming the closure. What a closure strands, the bookings on the day and
the hires due back on it, is read as one union, which PostgreSQL runs here.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Final
from uuid import uuid4

import pytest
from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.application.trading.closure_ports import DuplicateClosureDay
from app.domain import closure_day as domain
from app.domain.enums import RentalStatus, ReservationStatus, UserRole
from app.domain.period import BookingPeriod
from app.infrastructure.closure_days import SqlClosureDayRepository
from app.infrastructure.models import Branch, ClosureDay, UserAccount
from app.infrastructure.schema_ddl import CLOSURE_DAY_LIVE_INDEX_NAME
from tests.support.booking_api import BookingClient, BookingWorld, answered, build_booking_world
from tests.support.closure_day_api import STOCKTAKE_DAY, add_closure, closure_body, read_impact
from tests.support.factories import Factory
from tests.support.hire_factories import HireFactory
from tests.support.http import problem_of
from tests.support.pg import constraint_name_of

pytestmark = pytest.mark.postgres

ADDED_AT: Final[datetime] = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
# A hire collected on the stocktake day, a Friday the branch would trade.
COLLECTED_ON_THE_DAY: Final[BookingPeriod] = BookingPeriod(STOCKTAKE_DAY, date(2026, 3, 24))
# A hire that went out on the sixteenth and is due back on the stocktake day.
DUE_BACK_ON_THE_DAY: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 16), STOCKTAKE_DAY)


@pytest.fixture
def world(postgres_session: Session, postgres_factory: Factory) -> BookingWorld:
    """Return a committed branch with one unit of one model, and a customer."""
    built = build_booking_world(postgres_factory)
    postgres_session.commit()
    return built


@pytest.fixture
def owner(postgres_session: Session, postgres_factory: Factory, world: BookingWorld) -> UserAccount:
    """Return the committed owner, an administrator."""
    account = postgres_factory.user(role=UserRole.ADMIN)
    postgres_session.commit()
    return account


def closure_row(branch: Branch | None, owner: UserAccount) -> ClosureDay:
    """Return a live closure of the stocktake day, unflushed."""
    return ClosureDay(
        branch_id=branch.id if branch is not None else None,
        day=STOCKTAKE_DAY,
        reason="Stocktake",
        created_by_user_id=owner.id,
        created_at=ADDED_AT,
    )


def closure_of(branch: Branch | None) -> domain.ClosureDay:
    """Return a new live closure of the stocktake day as the use case builds it."""
    return domain.ClosureDay(
        id=uuid4(),
        branch_id=branch.id if branch is not None else None,
        branch_code=branch.code if branch is not None else None,
        day=STOCKTAKE_DAY,
        reason="Stocktake",
        created_at=ADDED_AT,
    )


class TestTheUniqueIndex:
    """One live closure per branch and day, and one for every branch per day."""

    @pytest.mark.parametrize("every_branch", [False, True], ids=["one-branch", "every-branch"])
    def test_a_second_live_closure_of_the_day_is_refused(
        self,
        postgres_session: Session,
        owner: UserAccount,
        world: BookingWorld,
        every_branch: bool,
    ) -> None:
        branch = None if every_branch else world.branch
        postgres_session.add(closure_row(branch, owner))
        postgres_session.flush()
        postgres_session.add(closure_row(branch, owner))

        with pytest.raises(IntegrityError) as refusal:
            postgres_session.flush()

        assert constraint_name_of(refusal.value) == CLOSURE_DAY_LIVE_INDEX_NAME
        postgres_session.rollback()

    def test_a_cancelled_closure_holds_nothing(
        self, postgres_session: Session, owner: UserAccount, world: BookingWorld
    ) -> None:
        cancelled = closure_row(world.branch, owner)
        cancelled.cancelled_at = ADDED_AT
        cancelled.cancelled_by_user_id = owner.id
        postgres_session.add(cancelled)
        postgres_session.flush()
        postgres_session.add(closure_row(world.branch, owner))

        postgres_session.flush()
        postgres_session.commit()

    def test_the_repository_turns_a_lost_race_into_the_duplicate(
        self, postgres_session: Session, owner: UserAccount, world: BookingWorld
    ) -> None:
        postgres_session.add(closure_row(world.branch, owner))
        postgres_session.commit()
        repository = SqlClosureDayRepository(postgres_session)
        # Read before the refusal, which leaves the session needing a rollback.
        branch_id, owner_id = world.branch.id, owner.id

        with pytest.raises(DuplicateClosureDay) as refusal:
            repository.add(closure_of(world.branch), owner_id)

        postgres_session.rollback()
        assert (refusal.value.branch_id, refusal.value.day) == (branch_id, STOCKTAKE_DAY)


class TestTheCalendarABookingChecks:
    """A closure added through the route refuses a hire collected that day."""

    def test_a_hire_collected_on_a_new_closure_day_is_refused_naming_it(
        self, booking: BookingClient, owner: UserAccount, world: BookingWorld
    ) -> None:
        assert booking.create(world.customer, world.payload(COLLECTED_ON_THE_DAY)).status_code == (
            status.HTTP_201_CREATED
        )
        added = add_closure(booking, owner, closure_body(world.branch.code))
        assert added.status_code == status.HTTP_201_CREATED, added.text

        refused = booking.create(world.customer, world.payload(COLLECTED_ON_THE_DAY))

        assert refused.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        errors = problem_of(refused)["errors"]
        assert isinstance(errors, dict)
        assert errors["fields"] == {
            "body.from": (
                "The branch is closed on Friday 20 March (Stocktake), so you cannot collect then. "
                "The next day it is open is Monday 23 March."
            )
        }

    def test_a_second_closure_through_the_route_is_a_conflict(
        self, booking: BookingClient, owner: UserAccount, world: BookingWorld
    ) -> None:
        first = add_closure(booking, owner, closure_body(None, reason="Election day"))
        assert first.status_code == status.HTTP_201_CREATED, first.text

        second = add_closure(booking, owner, closure_body(None))

        assert second.status_code == status.HTTP_409_CONFLICT
        assert "Every branch is already closed" in str(problem_of(second)["detail"])


class TestWhatAClosureStrands:
    """The bookings and the hires out on the day, read as one union on PostgreSQL."""

    def test_a_booking_collected_and_a_hire_due_back_that_day_are_both_named(
        self,
        postgres_session: Session,
        postgres_factory: Factory,
        booking: BookingClient,
        owner: UserAccount,
        world: BookingWorld,
    ) -> None:
        hires = HireFactory(postgres_factory)
        out = hires.booking(
            profile=world.profile,
            created_by=world.customer,
            branch=world.branch,
            model=world.product_model,
            units=world.assets,
            period=DUE_BACK_ON_THE_DAY,
            status=ReservationStatus.COLLECTED,
        )
        rental = hires.rental(out, checked_out_by=owner, status=RentalStatus.OVERDUE)
        held = postgres_factory.reservation(
            profile=world.profile,
            created_by=world.customer,
            branch=world.branch,
            period=COLLECTED_ON_THE_DAY,
        )
        postgres_session.commit()

        found = answered(
            read_impact(booking, owner, branchCode=world.branch.code, day=STOCKTAKE_DAY.isoformat())
        )

        items = found["items"]
        assert isinstance(items, list)
        assert [(item["reference"], item["hireDay"]) for item in items] == [
            (rental.reference, "due_back"),
            (held.reference, "collection"),
        ]
        assert found["total"] == 2
