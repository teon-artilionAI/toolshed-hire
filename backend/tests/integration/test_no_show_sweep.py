"""The no show half of the lazy sweep on PostgreSQL (BR-17, BR-18).

A confirmed booking nobody collected by closing time on the first day of the
hire becomes a no show the next time the sweep runs. This file proves that
what the sweep writes is what the database keeps. The units are released with
the reason `NO_SHOW`, the running count on the customer goes up by one for each
booking, and the third no show inside twelve months puts the customer on hold,
counted from the reservations and not from that running count.

And the sweep reads through the partial index on the first day of a confirmed
booking, because its status is written into the statement as a literal.

Two sweeps at once, and two no shows of one customer at once, are in
tests/integration/test_no_show_races.py. The clock stands still on Monday the
second of March 2026. The branch closes at 17:00 in Cape Town, which is 15:00
UTC.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from sqlmodel import Session, select

from app.domain.enums import AccountStatus, ReleaseReason, ReservationStatus, UserRole
from app.infrastructure.booking import SqlReservationRepository
from app.infrastructure.models import AssetAllocation, Reservation, UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, build_booking_world
from tests.support.checkout_api import confirmed_today
from tests.support.counter_api import AFTER_CLOSING
from tests.support.factories import Factory
from tests.support.no_show_pg import (
    INSIDE_THE_WINDOW,
    NO_SHOW_ACTION,
    ON_HOLD_ACTION,
    OUTSIDE_THE_WINDOW,
    earlier_no_shows,
    events,
    stored_profile,
    sweep_once,
)
from tests.support.statements import recorded_statements

pytestmark = pytest.mark.postgres

UNITS: Final[int] = 2
CONFIRMED_START_INDEX: Final[str] = "ix_reservation_confirmed_start"
EXPLAIN_THE_SWEEP: Final[str] = (
    "EXPLAIN SELECT reservation.id FROM reservation JOIN branch ON branch.id = "
    "reservation.branch_id WHERE reservation.status = 'CONFIRMED' AND "
    "reservation.start_date <= DATE '2026-03-02' AND (reservation.start_date < DATE "
    "'2026-03-02' OR branch.closes_at < TIME '17:00:01') ORDER BY reservation.start_date, "
    "reservation.id LIMIT 25 FOR UPDATE OF reservation"
)


@pytest.fixture
def world(postgres_session: Session, postgres_factory: Factory) -> BookingWorld:
    """Return a committed branch with two units of one model, and a customer."""
    built = build_booking_world(postgres_factory, asset_count=UNITS)
    postgres_session.commit()
    return built


@pytest.fixture
def assistant(
    postgres_session: Session, postgres_factory: Factory, world: BookingWorld
) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = postgres_factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    postgres_session.commit()
    return account


class TestWhatTheSweepKeeps:
    """The move, the release, the count and the hold, as the database keeps them."""

    def test_the_units_are_released_as_a_no_show_and_the_customer_counted_once(
        self,
        booking: BookingClient,
        postgres_engine: Engine,
        postgres_session: Session,
        world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        reservation = confirmed_today(booking, world, assistant, quantity=UNITS)

        result = sweep_once(postgres_engine)

        assert result.no_show_references == (reservation["reference"],)
        postgres_session.rollback()
        stored = postgres_session.get(Reservation, UUID(str(reservation["id"])))
        assert stored is not None
        assert stored.status is ReservationStatus.NO_SHOW
        released = postgres_session.exec(select(AssetAllocation)).all()
        assert {allocation.release_reason for allocation in released} == {ReleaseReason.NO_SHOW}
        assert stored_profile(postgres_session, world).no_show_count == 1
        (event,) = events(postgres_session, NO_SHOW_ACTION)
        assert (event.actor_user_id, event.actor_role) == (None, None)

    def test_the_third_no_show_in_twelve_months_puts_the_customer_on_hold(
        self,
        booking: BookingClient,
        postgres_engine: Engine,
        postgres_factory: Factory,
        postgres_session: Session,
        world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        earlier_no_shows(
            postgres_factory, postgres_session, world, assistant, *INSIDE_THE_WINDOW
        )
        confirmed_today(booking, world, assistant)

        result = sweep_once(postgres_engine)

        assert result.customers_put_on_hold == (world.profile.id,)
        profile = stored_profile(postgres_session, world)
        assert profile.account_status is AccountStatus.ON_HOLD
        assert profile.no_show_count == 1, "The hold is counted from the reservations."
        (event,) = events(postgres_session, ON_HOLD_ACTION)
        assert event.entity_id == world.profile.id

    def test_a_no_show_outside_the_window_does_not_count_towards_the_hold(
        self,
        booking: BookingClient,
        postgres_engine: Engine,
        postgres_factory: Factory,
        postgres_session: Session,
        world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        earlier_no_shows(
            postgres_factory,
            postgres_session,
            world,
            assistant,
            INSIDE_THE_WINDOW[0],
            OUTSIDE_THE_WINDOW,
        )
        confirmed_today(booking, world, assistant)

        assert sweep_once(postgres_engine).customers_put_on_hold == ()
        assert stored_profile(postgres_session, world).account_status is AccountStatus.ACTIVE


class TestTheSweepReadsThroughThePartialIndex:
    """The statement is one the planner can answer from `ix_reservation_confirmed_start`."""

    def test_the_status_is_in_the_statement_as_a_literal_and_the_rows_are_locked(
        self, postgres_engine: Engine, postgres_session: Session
    ) -> None:
        with recorded_statements(postgres_engine) as statements:
            SqlReservationRepository(postgres_session).lock_due_no_shows(AFTER_CLOSING, 25)
        (sweep,) = [sql for sql in statements if "branch.closes_at <" in sql]
        assert "reservation.status = 'CONFIRMED'" in sweep
        assert "FOR UPDATE OF reservation" in sweep
        assert "SKIP LOCKED" not in sweep
        assert "LIMIT" in sweep

    def test_the_planner_uses_the_partial_index_for_that_statement(
        self, postgres_session: Session
    ) -> None:
        """The table is tiny here, so sequential scans are switched off to see the choice."""
        postgres_session.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            str(row[0]) for row in postgres_session.execute(text(EXPLAIN_THE_SWEEP)).all()
        )
        assert CONFIRMED_START_INDEX in plan, f"The sweep does not use its index:\n{plan}"
