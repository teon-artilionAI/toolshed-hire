"""No shows marked at the same moment on PostgreSQL, where the row locks are real (BR-17, BR-18).

Two sweeps at once are safe. Every booking is marked once and counted once,
whichever sweep marks it. The staged test holds the first sweep at its commit
until PostgreSQL reports the second one blocked, so the race is known to have
happened, and the second then finds nothing left to mark.

Two no shows of one customer marked by hand at the same moment take turns on
the lock of the profile, so the second counts the first and a third strike is
never missed because two arrived together.

The clock stands still on Monday the second of March 2026. The branch closes
at 17:00 in Cape Town, which is 15:00 UTC.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Final

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from app.application.booking.expire_holds import SweepResult
from app.application.booking.mark_no_show import MarkNoShowCommand, MarkNoShowUseCase
from app.application.booking.read_models import ReservationKey
from app.domain.enums import AccountStatus, UserRole
from app.domain.identity import Actor
from app.infrastructure.models import UserAccount
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.booking_api import BookingClient, BookingWorld, build_booking_world
from tests.support.checkout_api import confirmed_today
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.no_show_pg import (
    INSIDE_THE_WINDOW,
    NO_SHOW_ACTION,
    ON_HOLD_ACTION,
    UnitOfWorkThatAnnouncesItsBackend,
    UnitOfWorkThatPausesAtCommit,
    earlier_no_shows,
    events,
    stored_profile,
    sweep_on,
)
from tests.support.race import (
    BARRIER_TIMEOUT_SECONDS,
    RESULT_TIMEOUT_SECONDS,
    wait_until_backend_is_blocked,
)

pytestmark = pytest.mark.postgres

BOOKINGS: Final[int] = 4
# The second sweep opens one transaction for each half, and the no show half
# is the one that waits.
HALVES_OF_A_SWEEP: Final[int] = 2
BACKEND_POLL_SECONDS: Final[float] = 0.01
REASON: Final[str] = "Nobody came by closing time."


@pytest.fixture
def world(postgres_session: Session, postgres_factory: Factory) -> BookingWorld:
    """Return a committed branch with four units of one model, and a customer."""
    built = build_booking_world(postgres_factory, asset_count=BOOKINGS)
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


class TestTwoSweepsAtOnce:
    """Every booking is marked once and counted once, however the two sweeps interleave."""

    def test_two_sweeps_released_together_mark_and_count_each_booking_once(
        self,
        booking: BookingClient,
        postgres_engine: Engine,
        postgres_session: Session,
        world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        for _ in range(BOOKINGS):
            confirmed_today(booking, world, assistant)
        barrier = threading.Barrier(2)

        def _sweep() -> SweepResult:
            """Wait for the other sweep, then run."""
            unit_of_work = SqlAlchemyUnitOfWork(lambda: Session(postgres_engine))
            barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)
            return sweep_on(unit_of_work)()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(_sweep), pool.submit(_sweep)]
            results = [future.result(timeout=RESULT_TIMEOUT_SECONDS) for future in futures]

        assert sum(result.no_show_count for result in results) == BOOKINGS
        marked = events(postgres_session, NO_SHOW_ACTION)
        assert len({event.entity_id for event in marked}) == len(marked) == BOOKINGS
        profile = stored_profile(postgres_session, world)
        assert profile.no_show_count == BOOKINGS
        assert profile.account_status is AccountStatus.ON_HOLD
        assert len(events(postgres_session, ON_HOLD_ACTION)) == 1

    def test_a_sweep_that_waits_behind_another_finds_nothing_left_to_mark(
        self,
        booking: BookingClient,
        postgres_engine: Engine,
        postgres_session: Session,
        world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        """Staged, so the second sweep is known to have waited on the first."""
        for _ in range(BOOKINGS):
            confirmed_today(booking, world, assistant)
        first_unit = UnitOfWorkThatPausesAtCommit(lambda: Session(postgres_engine))
        first_unit.about_to_commit = threading.Event()
        first_unit.may_commit = threading.Event()
        second_unit = UnitOfWorkThatAnnouncesItsBackend(lambda: Session(postgres_engine))
        second_unit.backends = []

        def _second() -> SweepResult:
            """Start once the first sweep holds its locks, and wait behind them."""
            first_unit.about_to_commit.wait(timeout=BARRIER_TIMEOUT_SECONDS)
            return sweep_on(second_unit)()

        def _referee() -> None:
            """Release the first sweep once the no show half of the second is waiting."""
            first_unit.about_to_commit.wait(timeout=BARRIER_TIMEOUT_SECONDS)
            deadline = time.monotonic() + BARRIER_TIMEOUT_SECONDS
            while len(second_unit.backends) < HALVES_OF_A_SWEEP and time.monotonic() < deadline:
                time.sleep(BACKEND_POLL_SECONDS)
            with Session(postgres_engine) as watcher:
                wait_until_backend_is_blocked(watcher, second_unit.backends[-1])
            first_unit.may_commit.set()

        referee = threading.Thread(target=_referee, name="referee", daemon=True)
        referee.start()
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(sweep_on(first_unit))
                second = pool.submit(_second)
                first_result = first.result(timeout=RESULT_TIMEOUT_SECONDS)
                second_result = second.result(timeout=RESULT_TIMEOUT_SECONDS)
        finally:
            first_unit.may_commit.set()
            referee.join(timeout=BARRIER_TIMEOUT_SECONDS)

        assert first_result.no_show_count == BOOKINGS
        assert second_result.no_show_count == 0
        assert len(events(postgres_session, NO_SHOW_ACTION)) == BOOKINGS
        assert stored_profile(postgres_session, world).no_show_count == BOOKINGS


class TestTwoNoShowsOfOneCustomerAtOnce:
    """The lock on the profile makes the second count the first, so the third strike lands."""

    def test_two_bookings_marked_together_after_one_earlier_strike_put_the_customer_on_hold(
        self,
        booking: BookingClient,
        postgres_engine: Engine,
        postgres_factory: Factory,
        postgres_session: Session,
        world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        earlier_no_shows(postgres_factory, postgres_session, world, assistant, INSIDE_THE_WINDOW[0])
        keys = [confirmed_today(booking, world, assistant)["id"] for _ in range(2)]
        staff = Actor(user_id=assistant.id, role=UserRole.COUNTER_STAFF, branch_id=world.branch.id)
        barrier = threading.Barrier(2)

        def _mark(key: object) -> str:
            """Wait for the other, then mark one booking as not collected."""
            use_case = MarkNoShowUseCase(
                SqlAlchemyUnitOfWork(lambda: Session(postgres_engine)), FixedClock()
            )
            barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)
            command = MarkNoShowCommand(
                actor=staff, key=ReservationKey.parse(str(key)), reason=REASON
            )
            return use_case.execute(command).detail.status.value

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = [
                future.result(timeout=RESULT_TIMEOUT_SECONDS)
                for future in [pool.submit(_mark, key) for key in keys]
            ]

        assert outcomes == ["NO_SHOW", "NO_SHOW"]
        profile = stored_profile(postgres_session, world)
        assert (profile.account_status, profile.no_show_count) == (AccountStatus.ON_HOLD, 2)
        assert len(events(postgres_session, ON_HOLD_ACTION)) == 1
