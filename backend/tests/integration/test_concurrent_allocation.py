"""Two genuinely concurrent transactions cannot double book one unit.

A single threaded test proves that the code refuses a booking it can already
see. It says nothing about the case the whole design exists for, which is two
customers pressing Confirm on the last plate compactor inside the same
millisecond. That case is only reachable with two real connections running at
once, so this file uses two threads, two independent PostgreSQL connections and
a barrier that neither thread passes until the other has arrived.

The engine is NullPool, configured in conftest. A pooled engine that handed both
threads the same connection would serialise them, both bookings would succeed,
and the suite would report a green tick for a race it never ran.

Two variants run, and the second is the one that matters.

WITH THE APPLICATION ROW LOCK
    `allocate_assets` selects candidates with `SELECT ... FOR UPDATE SKIP
    LOCKED`. The loser either skips the locked row and finds nothing free, or
    reaches the insert and is refused there.

WITH THE APPLICATION ROW LOCK BYPASSED
    The rows are inserted directly with no lock of any kind, which is what a
    future refactor, a hand written script or a second service would do. Now
    nothing stands between the two transactions except the exclusion
    constraint. This was verified by dropping the constraint: only the bypass
    tests failed, while the locked variants above went on passing, because the
    lock happily hides the constraint's absence. That is precisely why the
    bypass variant exists.

There is a second finding worth reading, because it is a real property of the
database and not a quirk of the test. When two unlocked transactions insert
conflicting rows at the same instant, each writes its row and then waits for the
other to commit or roll back before it can finish checking the exclusion
constraint. That is a cycle, so PostgreSQL breaks it by aborting one transaction
with SQLSTATE 40P01, deadlock_detected, rather than with 23P01. Both outcomes
are correct and both leave exactly one allocation, so the simultaneous test
accepts either and the staged test below pins 23P01 exactly. The application
path never sees 40P01, because the row lock is taken first, which is a second
reason that lock exists beyond throughput.
"""

from __future__ import annotations

import logging
import threading
from datetime import date
from typing import Final

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from app.domain.errors import AssetUnavailableConflict
from app.domain.period import BookingPeriod
from app.infrastructure.schema_ddl import OVERLAP_CONSTRAINT_NAME
from tests.support.contenders import (
    AllocationTarget,
    book_through_the_use_case,
    hold_an_uncommitted_allocation,
    insert_after_the_first_writer,
    insert_without_any_lock,
)
from tests.support.factories import Factory
from tests.support.pg import EXCLUSION_VIOLATION_SQLSTATE, count_active_allocations
from tests.support.race import (
    BARRIER_TIMEOUT_SECONDS,
    CONTENDER_COUNT,
    EXPECTED_WINNERS,
    Outcome,
    run_race,
    wait_until_backend_is_blocked,
)
from tests.support.scenarios import build_allocation_scenario

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.postgres

CONTESTED_HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 9), date(2026, 3, 12))
DEADLOCK_SQLSTATE: Final[str] = "40P01"
REFUSAL_SQLSTATES: Final[frozenset[str]] = frozenset(
    {EXCLUSION_VIOLATION_SQLSTATE, DEADLOCK_SQLSTATE}
)
STAGED_EVENT_COUNT: Final[int] = 3


class TestTwoTransactionsFightingOverTheLastUnit:
    """Through the real use case: exactly one wins, and the database agrees."""

    def test_only_one_of_two_simultaneous_bookings_of_the_last_unit_survives(
        self, postgres_engine: Engine, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        scenario = build_allocation_scenario(postgres_factory, CONTESTED_HIRE)
        postgres_session.commit()
        command = AllocationTarget.of(scenario, CONTESTED_HIRE).as_command(
            scenario.product_model.id
        )
        barrier = threading.Barrier(CONTENDER_COUNT)

        def _contender() -> Outcome:
            """Book the contested unit through the real use case."""
            return book_through_the_use_case(postgres_engine, command, barrier)

        outcomes = run_race(_contender, _contender)

        assert sum(outcome.succeeded for outcome in outcomes) == EXPECTED_WINNERS
        loser = next(outcome for outcome in outcomes if not outcome.succeeded)
        assert isinstance(loser.error, AssetUnavailableConflict)
        assert count_active_allocations(postgres_session, scenario.asset.id) == 1

    def test_the_loser_is_told_it_lost_rather_than_being_handed_a_server_fault(
        self, postgres_engine: Engine, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        """The conflict is a domain error, which the API maps to 409 and never to 500."""
        scenario = build_allocation_scenario(postgres_factory, CONTESTED_HIRE)
        postgres_session.commit()
        command = AllocationTarget.of(scenario, CONTESTED_HIRE).as_command(
            scenario.product_model.id
        )
        barrier = threading.Barrier(CONTENDER_COUNT)

        def _contender() -> Outcome:
            """Book the contested unit through the real use case."""
            return book_through_the_use_case(postgres_engine, command, barrier)

        outcomes = run_race(_contender, _contender)

        loser = next(outcome for outcome in outcomes if not outcome.succeeded)
        assert isinstance(loser.error, AssetUnavailableConflict)
        assert loser.error.detail["period"] == CONTESTED_HIRE.as_postgres_daterange()

    def test_two_simultaneous_bookings_take_different_units_when_two_are_free(
        self, postgres_engine: Engine, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        """SKIP LOCKED is a throughput decision, not a correctness one.

        Without it the second transaction would queue on the row the first one
        locked and would then find it taken, turning a branch with two free
        units into a branch that can serve one customer at a time.
        """
        scenario = build_allocation_scenario(postgres_factory, CONTESTED_HIRE, asset_count=2)
        postgres_session.commit()
        command = AllocationTarget(
            line_id=scenario.line.id,
            asset_id=scenario.assets[0].id,
            branch_id=scenario.branch.id,
            period=CONTESTED_HIRE,
        ).as_command(scenario.product_model.id)
        barrier = threading.Barrier(CONTENDER_COUNT)

        def _contender() -> Outcome:
            """Book one free unit of the model through the real use case."""
            return book_through_the_use_case(postgres_engine, command, barrier)

        outcomes = run_race(_contender, _contender)

        assert all(outcome.succeeded for outcome in outcomes)
        held = sum(
            count_active_allocations(postgres_session, asset.id) for asset in scenario.assets
        )
        assert held == CONTENDER_COUNT


class TestTheConstraintIsTheLastLineOfDefence:
    """With the row lock bypassed, only the exclusion constraint stands in the way."""

    def test_two_simultaneous_unlocked_inserts_leave_exactly_one_allocation(
        self, postgres_engine: Engine, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        scenario = build_allocation_scenario(postgres_factory, CONTESTED_HIRE)
        postgres_session.commit()
        target = AllocationTarget.of(scenario, CONTESTED_HIRE)
        barrier = threading.Barrier(CONTENDER_COUNT)

        def _contender() -> Outcome:
            """Insert the contested allocation with no lock of any kind."""
            return insert_without_any_lock(postgres_engine, target, barrier)

        outcomes = run_race(_contender, _contender)

        assert sum(outcome.succeeded for outcome in outcomes) == EXPECTED_WINNERS
        loser = next(outcome for outcome in outcomes if not outcome.succeeded)
        assert loser.sqlstate in REFUSAL_SQLSTATES, (
            "The database refused the second unlocked insert with an unexpected SQLSTATE. "
            f"Expected one of {sorted(REFUSAL_SQLSTATES)}, which are the exclusion violation "
            "and the deadlock PostgreSQL raises when both writers wait on each other. Got "
            f"{loser.sqlstate!r}."
        )
        assert count_active_allocations(postgres_session, target.asset_id) == 1

    def test_an_unlocked_insert_arriving_second_is_refused_by_the_exclusion_constraint(
        self, postgres_engine: Engine, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        """Staged rather than simultaneous, so the refusal is 23P01 every time.

        The first writer holds its uncommitted row until the second writer is
        provably blocked on it, which is the ordering a request arriving a few
        milliseconds later actually experiences. The second writer waits inside
        PostgreSQL, is released when the first commits, and is then refused by
        name.
        """
        scenario = build_allocation_scenario(postgres_factory, CONTESTED_HIRE)
        postgres_session.commit()
        target = AllocationTarget.of(scenario, CONTESTED_HIRE)
        written, announce, release = (threading.Event() for _ in range(STAGED_EVENT_COUNT))
        pid_holder: list[int] = []

        def _first() -> Outcome:
            """Hold the row uncommitted until the second writer is stuck behind it."""
            return hold_an_uncommitted_allocation(postgres_engine, target, written, release)

        def _second() -> Outcome:
            """Announce this backend, then insert into the held row and block."""
            return insert_after_the_first_writer(
                postgres_engine, target, written, announce, pid_holder
            )

        def _referee() -> None:
            """Release the first writer once the second is genuinely waiting on a lock.

            Opens its own session. The test's session belongs to the main
            thread, and a SQLAlchemy session is not shared across threads.
            """
            announce.wait(timeout=BARRIER_TIMEOUT_SECONDS)
            with Session(postgres_engine) as watcher:
                wait_until_backend_is_blocked(watcher, pid_holder[0])
            release.set()

        referee = threading.Thread(target=_referee, name="referee", daemon=True)
        referee.start()
        try:
            first, second = run_race(_first, _second)
        finally:
            release.set()
            referee.join(timeout=BARRIER_TIMEOUT_SECONDS)

        assert first.succeeded
        assert not second.succeeded
        assert second.sqlstate == EXCLUSION_VIOLATION_SQLSTATE
        assert second.constraint == OVERLAP_CONSTRAINT_NAME
        assert count_active_allocations(postgres_session, target.asset_id) == 1
