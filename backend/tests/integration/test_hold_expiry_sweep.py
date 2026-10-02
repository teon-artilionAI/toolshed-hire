"""The lazy sweep on PostgreSQL, where its row locks are real (BR-13).

A hold that has run out is lapsed the next time somebody asks a question it
could spoil. This file proves three things the in memory tests cannot.

The units of a lapsed hold really are free again. A visitor's availability
search, which runs the sweep before it answers, reports the unit free, and
another customer can hold it.

Two sweeps at once are safe. The first one locks the due rows. The second
waits for those locks, reads the rows again once they are released and finds
nothing left to lapse, so every hold is lapsed once and has one audit event.
The staged test holds the first sweep at its commit until PostgreSQL itself
reports the second one blocked, so the race is known to have happened.

And the sweep reads through the partial index on the hold expiry. Its status
condition is written into the statement as a literal, which is what lets the
planner use an index that is filtered on that status.

The clock stands still on Monday the second of March 2026 until a test moves it.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Final, Self

import pytest
from sqlalchemy import Engine, text
from sqlmodel import Session, col, select

from app.application.booking.expire_holds import (
    ExpireHoldsAndNoShowsUseCase,
    SweepCommand,
    SweepResult,
)
from app.domain.enums import ReleaseReason, ReservationStatus
from app.infrastructure.booking import SqlReservationRepository
from app.infrastructure.models import AssetAllocation, AuditEvent, Reservation
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.booking_api import (
    FIRST_HIRE,
    BookingClient,
    BookingWorld,
    answered,
    build_booking_world,
)
from tests.support.catalogue import model_availability_path
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.race import (
    BARRIER_TIMEOUT_SECONDS,
    RESULT_TIMEOUT_SECONDS,
    backend_pid,
    wait_until_backend_is_blocked,
)
from tests.support.statements import recorded_statements

pytestmark = pytest.mark.postgres

HOLDS: Final[int] = 4
BACKEND_POLL_SECONDS: Final[float] = 0.01
JUST_PAST_THE_HOLD: Final[timedelta] = timedelta(minutes=30, seconds=1)
EXPIRED_ACTION: Final[str] = "reservation.expired"
HOLD_EXPIRY_INDEX: Final[str] = "ix_reservation_hold_expiry"
THE_WHOLE_HIRE: Final[dict[str, object]] = {
    "from": FIRST_HIRE.start.isoformat(),
    "to": FIRST_HIRE.end.isoformat(),
}
EXPLAIN_THE_SWEEP: Final[str] = (
    "EXPLAIN SELECT id FROM reservation WHERE reservation.status = 'HELD' "
    "AND hold_expires_at < now() ORDER BY hold_expires_at, id LIMIT 25 FOR UPDATE"
)


class UnitOfWorkThatPausesAtCommit(SqlAlchemyUnitOfWork):
    """The real unit of work, which says when it is about to commit and then waits.

    It holds every row lock its transaction took until the test lets it go,
    which is how a second sweep can be made to wait on the first.
    """

    about_to_commit: threading.Event
    may_commit: threading.Event

    def commit(self) -> None:
        """Announce the commit, wait to be released, then commit."""
        self.about_to_commit.set()
        if not self.may_commit.wait(timeout=BARRIER_TIMEOUT_SECONDS):
            raise AssertionError(
                "The first sweep was never released, so the staged race never completed."
            )
        super().commit()


class UnitOfWorkThatAnnouncesItsBackend(SqlAlchemyUnitOfWork):
    """The real unit of work, which writes down the backend its transaction runs on."""

    backends: list[int]

    def __enter__(self) -> Self:
        """Open the real transaction, then note the process id of its connection."""
        entered = super().__enter__()
        self.backends.append(backend_pid(self._open_session()))
        return entered


@pytest.fixture
def world(postgres_session: Session, postgres_factory: Factory) -> BookingWorld:
    """Return a committed branch with four units of one model, and a customer."""
    built = build_booking_world(postgres_factory, asset_count=HOLDS)
    postgres_session.commit()
    return built


def sweep_on(unit_of_work: SqlAlchemyUnitOfWork, clock: FixedClock) -> Callable[[], SweepResult]:
    """Return a call that runs one sweep in the given unit of work."""
    return lambda: ExpireHoldsAndNoShowsUseCase(unit_of_work, clock).execute(SweepCommand())


def statuses(session: Session) -> list[ReservationStatus]:
    """Return the committed status of every reservation."""
    session.rollback()
    return [reservation.status for reservation in session.exec(select(Reservation))]


def expired_events(session: Session) -> list[AuditEvent]:
    """Return every committed audit event of a lapse."""
    session.rollback()
    return list(
        session.exec(select(AuditEvent).where(col(AuditEvent.action) == EXPIRED_ACTION))
    )


class TestTheUnitsOfALapsedHoldAreFreeAgain:
    """An expired hold is swept, and its units become available again."""

    def test_an_availability_search_reports_the_unit_free_once_the_hold_has_run_out(
        self, booking: BookingClient, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        world = build_booking_world(postgres_factory)
        postgres_session.commit()
        path = model_availability_path(world.product_model.slug)
        branch_code = world.branch.code
        held = booking.held(world)

        while_held = answered(booking.client.get(path, params=THE_WHOLE_HIRE))
        booking.clock.advance(JUST_PAST_THE_HOLD)
        after = answered(booking.client.get(path, params=THE_WHOLE_HIRE))

        assert {"branchCode": branch_code, "available": False}.items() <= (
            _answer_for(while_held, branch_code).items()
        )
        assert _answer_for(after, branch_code)["available"] is True
        postgres_session.rollback()
        stored = postgres_session.get(Reservation, held["id"])
        assert stored is not None
        assert stored.status is ReservationStatus.EXPIRED
        (allocation,) = postgres_session.exec(select(AssetAllocation)).all()
        assert allocation.release_reason is ReleaseReason.EXPIRED
        assert len(expired_events(postgres_session)) == 1

    def test_another_customer_can_hold_the_unit_once_the_first_hold_has_run_out(
        self, booking: BookingClient, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        world = build_booking_world(postgres_factory)
        postgres_session.commit()
        booking.held(world)
        booking.clock.advance(JUST_PAST_THE_HOLD)
        second = booking.held(world)
        assert second["status"] == "HELD"
        assert sorted(status.value for status in statuses(postgres_session)) == [
            "EXPIRED",
            "HELD",
        ]

    def test_a_hold_that_still_stands_keeps_its_unit_through_a_search(
        self, booking: BookingClient, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        world = build_booking_world(postgres_factory)
        postgres_session.commit()
        path = model_availability_path(world.product_model.slug)
        branch_code = world.branch.code
        booking.held(world)
        booking.clock.advance(timedelta(minutes=30))
        answer = answered(booking.client.get(path, params=THE_WHOLE_HIRE))
        assert _answer_for(answer, branch_code)["available"] is False
        assert statuses(postgres_session) == [ReservationStatus.HELD]


class TestTwoSweepsAtOnce:
    """Every due hold is lapsed exactly once, however the two sweeps interleave."""

    def test_two_sweeps_released_together_lapse_each_hold_once(
        self,
        booking: BookingClient,
        postgres_engine: Engine,
        postgres_session: Session,
        world: BookingWorld,
    ) -> None:
        for _ in range(HOLDS):
            booking.held(world)
        clock = FixedClock(booking.clock.now() + JUST_PAST_THE_HOLD)
        barrier = threading.Barrier(2)

        def _sweep() -> SweepResult:
            """Wait for the other sweep, then run."""
            unit_of_work = SqlAlchemyUnitOfWork(lambda: Session(postgres_engine))
            barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)
            return sweep_on(unit_of_work, clock)()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(_sweep), pool.submit(_sweep)]
            results = [future.result(timeout=RESULT_TIMEOUT_SECONDS) for future in futures]

        assert sum(result.expired_count for result in results) == HOLDS
        assert statuses(postgres_session) == [ReservationStatus.EXPIRED] * HOLDS
        events = expired_events(postgres_session)
        assert len(events) == HOLDS
        assert len({event.entity_id for event in events}) == HOLDS

    def test_a_sweep_that_waits_behind_another_finds_nothing_left_to_lapse(
        self,
        booking: BookingClient,
        postgres_engine: Engine,
        postgres_session: Session,
        world: BookingWorld,
    ) -> None:
        """Staged, so the second sweep is known to have waited on the first."""
        for _ in range(HOLDS):
            booking.held(world)
        clock = FixedClock(booking.clock.now() + JUST_PAST_THE_HOLD)
        first_unit = UnitOfWorkThatPausesAtCommit(lambda: Session(postgres_engine))
        first_unit.about_to_commit = threading.Event()
        first_unit.may_commit = threading.Event()
        second_unit = UnitOfWorkThatAnnouncesItsBackend(lambda: Session(postgres_engine))
        second_unit.backends = []

        def _second() -> SweepResult:
            """Start once the first sweep holds its locks, and wait behind them."""
            first_unit.about_to_commit.wait(timeout=BARRIER_TIMEOUT_SECONDS)
            return sweep_on(second_unit, clock)()

        def _referee() -> None:
            """Release the first sweep once the second is genuinely waiting on a lock."""
            first_unit.about_to_commit.wait(timeout=BARRIER_TIMEOUT_SECONDS)
            deadline = time.monotonic() + BARRIER_TIMEOUT_SECONDS
            while not second_unit.backends and time.monotonic() < deadline:
                time.sleep(BACKEND_POLL_SECONDS)
            with Session(postgres_engine) as watcher:
                wait_until_backend_is_blocked(watcher, second_unit.backends[0])
            first_unit.may_commit.set()

        referee = threading.Thread(target=_referee, name="referee", daemon=True)
        referee.start()
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(sweep_on(first_unit, clock))
                second = pool.submit(_second)
                first_result = first.result(timeout=RESULT_TIMEOUT_SECONDS)
                second_result = second.result(timeout=RESULT_TIMEOUT_SECONDS)
        finally:
            first_unit.may_commit.set()
            referee.join(timeout=BARRIER_TIMEOUT_SECONDS)

        assert first_result.expired_count == HOLDS
        assert second_result.expired_count == 0
        assert len(expired_events(postgres_session)) == HOLDS
        released = postgres_session.exec(select(AssetAllocation)).all()
        assert {allocation.release_reason for allocation in released} == {ReleaseReason.EXPIRED}
        assert len({allocation.released_at for allocation in released}) == 1


class TestTheSweepReadsThroughThePartialIndex:
    """The statement is one the planner can answer from `ix_reservation_hold_expiry`."""

    def test_the_status_is_in_the_statement_as_a_literal_and_not_a_parameter(
        self, postgres_engine: Engine, postgres_session: Session
    ) -> None:
        with recorded_statements(postgres_engine) as statements:
            SqlReservationRepository(postgres_session).lock_due_holds(FixedClock().now(), 25)
        (sweep,) = [sql for sql in statements if "hold_expires_at <" in sql]
        assert "reservation.status = 'HELD'" in sweep
        assert "FOR UPDATE" in sweep
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
        assert HOLD_EXPIRY_INDEX in plan, f"The sweep does not use its index:\n{plan}"


def _answer_for(body: dict[str, object], branch_code: str) -> dict[str, object]:
    """Return the answer of one branch from an availability response."""
    branches = body["branches"]
    assert isinstance(branches, list)
    (answer,) = [branch for branch in branches if branch["branchCode"] == branch_code]
    found: dict[str, object] = answer
    return found
