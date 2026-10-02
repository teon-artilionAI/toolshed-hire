"""The reservation routes on PostgreSQL, where the exclusion constraint is real.

The fast suite walks the same routes on the in memory database, which has no
`daterange` and no exclusion constraint. This file walks them on the real one,
so the conflict a customer is shown is the one the database enforces.

US-17 is here. A unit held for the 20th to the 24th refuses a second booking
for the 22nd to the 26th, with a 409 that names the dates, and a booking that
starts on the 24th succeeds, because a period is half open and the 24th is the
day the unit comes back (BR-02).

So is the rule of US-30 at the level of a reservation. A price changed in the
catalogue after a line was added does not move the figures of the reservation,
through a hold, a confirmation and a read (BR-20).

The clock stands still on Monday the second of March 2026.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final

import pytest
from fastapi import status
from sqlalchemy import Engine, text
from sqlmodel import Session, col, select

from app.domain.enums import ReleaseReason, UserRole
from app.domain.period import BookingPeriod
from app.infrastructure.models import AssetAllocation, CustomerProfile, ReservationLine
from tests.support.booking_api import (
    BookingClient,
    BookingWorld,
    answered,
    build_booking_world,
)
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of

pytestmark = pytest.mark.postgres

TWENTIETH_TO_TWENTY_FOURTH: Final[BookingPeriod] = BookingPeriod(
    date(2026, 3, 20), date(2026, 3, 24)
)
TWENTY_SECOND_TO_TWENTY_SIXTH: Final[BookingPeriod] = BookingPeriod(
    date(2026, 3, 22), date(2026, 3, 26)
)
FROM_THE_TWENTY_FOURTH: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 24), date(2026, 3, 27))
CONFLICT_PROBLEM: Final[str] = "asset-unavailable"
NEW_DAILY_RATE: Final[Decimal] = Decimal("999.00")
NEW_DEPOSIT: Final[Decimal] = Decimal("9.00")
# A second past the cutoff for a hire starting on the ninth. 17:00 in Cape Town
# on the eighth is 15:00 UTC.
AFTER_FIVE_ON_THE_EIGHTH: Final[datetime] = datetime(2026, 3, 8, 15, 0, 1, tzinfo=UTC)


@pytest.fixture
def world(postgres_session: Session, postgres_factory: Factory) -> BookingWorld:
    """Return a committed branch with one unit of one model, and a customer."""
    built = build_booking_world(postgres_factory)
    postgres_session.commit()
    return built


class TestAHeldUnitRefusesAnOverlappingHire:
    """US-17. The conflict is a clean 409 that names the dates."""

    def test_the_twenty_second_to_the_twenty_sixth_is_refused_naming_the_dates(
        self, booking: BookingClient, world: BookingWorld
    ) -> None:
        booking.held(world, TWENTIETH_TO_TWENTY_FOURTH)
        second = booking.drafted(world, TWENTY_SECOND_TO_TWENTY_SIXTH)

        response = booking.hold(world.customer, second["id"])

        assert response.status_code == status.HTTP_409_CONFLICT
        assert problem_code(response) == CONFLICT_PROBLEM
        detail = str(problem_of(response)["detail"])
        assert "22 March 2026" in detail
        assert "26 March 2026" in detail
        assert world.product_model.name in detail

    def test_the_refused_hire_allocated_nothing_and_is_still_a_draft(
        self, booking: BookingClient, postgres_session: Session, world: BookingWorld
    ) -> None:
        booking.held(world, TWENTIETH_TO_TWENTY_FOURTH)
        second = booking.drafted(world, TWENTY_SECOND_TO_TWENTY_SIXTH)
        booking.hold(world.customer, second["id"])

        (only,) = postgres_session.exec(select(AssetAllocation)).all()
        assert (only.start_date, only.end_date) == (date(2026, 3, 20), date(2026, 3, 24))
        assert answered(booking.read(world.customer, second["id"]))["status"] == "DRAFT"

    def test_a_hire_starting_on_the_twenty_fourth_succeeds(
        self, booking: BookingClient, postgres_session: Session, world: BookingWorld
    ) -> None:
        booking.held(world, TWENTIETH_TO_TWENTY_FOURTH)
        adjacent = booking.held(world, FROM_THE_TWENTY_FOURTH)

        assert adjacent["status"] == "HELD"
        allocations = postgres_session.exec(select(AssetAllocation)).all()
        assert len(allocations) == 2
        assert len({allocation.asset_id for allocation in allocations}) == 1

    def test_the_refused_hire_can_be_held_once_the_first_is_cancelled(
        self, booking: BookingClient, world: BookingWorld
    ) -> None:
        first = booking.held(world, TWENTIETH_TO_TWENTY_FOURTH)
        second = booking.drafted(world, TWENTY_SECOND_TO_TWENTY_SIXTH)
        assert booking.hold(world.customer, second["id"]).status_code == status.HTTP_409_CONFLICT
        answered(booking.cancel(world.customer, first["id"]))
        assert answered(booking.hold(world.customer, second["id"]))["status"] == "HELD"


class TestAPriceChangeLeavesAReservationAlone:
    """US-30 at the level of a reservation. The snapshot is what is charged (BR-20)."""

    def test_the_figures_survive_a_catalogue_change_through_every_later_move(
        self,
        booking: BookingClient,
        postgres_engine: Engine,
        postgres_session: Session,
        world: BookingWorld,
    ) -> None:
        draft = booking.drafted(world)
        # Changed on a connection of its own, as an administrator's request would.
        with postgres_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE product_model SET daily_rate = :rate, weekly_rate = :rate, "
                    "deposit_amount = :deposit WHERE id = :id"
                ),
                {"rate": NEW_DAILY_RATE, "deposit": NEW_DEPOSIT, "id": world.product_model.id},
            )

        held = answered(booking.hold(world.customer, draft["id"]))
        confirmed = answered(booking.confirm(world.customer, draft["id"]))
        read_back = answered(booking.read(world.customer, draft["id"]))

        for body in (held, confirmed, read_back):
            assert body["lines"][0]["dailyRate"] == "185.00"
            assert body["lines"][0]["depositPerUnit"] == "600.00"
            assert body["lines"][0]["lineSubtotalExVat"] == draft["lines"][0]["lineSubtotalExVat"]
            for member in ("subtotalExVat", "vatAmount", "estimatedTotalIncVat", "depositTotal"):
                assert body[member] == draft[member]
        postgres_session.rollback()
        line = postgres_session.exec(select(ReservationLine)).one()
        assert line.daily_rate_snapshot == Decimal("185.00")
        assert line.deposit_snapshot == Decimal("600.00")

    def test_a_draft_made_after_the_change_is_priced_at_the_new_rate(
        self,
        booking: BookingClient,
        postgres_engine: Engine,
        postgres_session: Session,
        world: BookingWorld,
    ) -> None:
        before = booking.drafted(world)
        model_id = world.product_model.id
        with postgres_engine.begin() as connection:
            connection.execute(
                text("UPDATE product_model SET daily_rate = :rate WHERE id = :id"),
                {"rate": NEW_DAILY_RATE, "id": model_id},
            )
        # The test and its requests share one session, which has just read the
        # model to find its key. A request of its own would start with nothing
        # loaded, so what this session holds is forgotten before the next one.
        postgres_session.expire_all()
        after = booking.drafted(world)
        assert before["lines"][0]["dailyRate"] == "185.00"
        assert after["lines"][0]["dailyRate"] == "999.00"
        assert after["subtotalExVat"] != before["subtotalExVat"]


class TestALateCancellationIsCountedOnTheProfile:
    """BR-16. Counted in the database, in the transaction of the cancellation."""

    def test_a_confirmed_booking_cancelled_after_the_cutoff_raises_the_count_by_one(
        self, booking: BookingClient, postgres_session: Session, world: BookingWorld
    ) -> None:
        confirmed = booking.confirmed(world)
        booking.clock.instant = AFTER_FIVE_ON_THE_EIGHTH
        answered(booking.cancel(world.customer, confirmed["id"]))

        postgres_session.rollback()
        profile = postgres_session.exec(
            select(CustomerProfile).where(col(CustomerProfile.id) == world.profile.id)
        ).one()
        assert profile.late_cancellation_count == 1
        (allocation,) = postgres_session.exec(select(AssetAllocation)).all()
        assert allocation.release_reason is ReleaseReason.CANCELLED

    def test_a_cancellation_before_the_cutoff_leaves_the_count_at_nought(
        self, booking: BookingClient, postgres_session: Session, world: BookingWorld
    ) -> None:
        confirmed = booking.confirmed(world)
        answered(booking.cancel(world.customer, confirmed["id"]))
        postgres_session.rollback()
        profile = postgres_session.exec(
            select(CustomerProfile).where(col(CustomerProfile.id) == world.profile.id)
        ).one()
        assert profile.late_cancellation_count == 0


class TestStaffSeeTheUnitsOnTheRealDatabase:
    """The tags a hold was given are the ones the allocation rows name."""

    def test_the_tags_staff_are_shown_are_the_units_that_were_allocated(
        self,
        booking: BookingClient,
        postgres_session: Session,
        postgres_factory: Factory,
        world: BookingWorld,
    ) -> None:
        administrator = postgres_factory.user(role=UserRole.ADMIN)
        postgres_session.commit()
        tag = world.assets[0].asset_tag
        held = booking.held(world)
        shown = answered(booking.read(administrator, held["reference"]))
        assert shown["lines"][0]["assetTags"] == [tag]
        assert answered(booking.read(world.customer, held["reference"]))["lines"][0][
            "assetTags"
        ] == []
