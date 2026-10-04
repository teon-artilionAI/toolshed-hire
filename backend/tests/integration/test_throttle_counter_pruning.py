"""Pruning the throttle counters on PostgreSQL, the fourth part of the lazy sweep (C-17).

The in memory tests prove which counters go. These prove what only PostgreSQL
can.

The sweep runs as the restricted application role, which may delete from
`rate_limit_counter` and from no other table, and the pruning is one statement
that deletes at most its batch, oldest window first, and leaves every counter
younger than the cutoff alone.

The statement reads `ix_rate_limit_counter_window_started_at`, the index of
revision 0012, with sequential scans switched off, so it never reads the whole
table to find what is due.

A counter another transaction holds locked is skipped and not waited for, so
two sweeps at once never wait on each other here. The test that proves it sets
a lock timeout, so a statement that did wait would fail rather than hang.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Final

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.dialects import postgresql
from sqlmodel import Session, col, select

from app.application.booking.expire_holds import ExpireHoldsAndNoShowsUseCase, SweepCommand
from app.application.throttle_pruning import finished_window_cutoff
from app.infrastructure.models import RateLimitCounter
from app.infrastructure.rate_limit import SqlRateLimitStore, pruning_statement
from app.infrastructure.schema_ddl import RATE_LIMIT_WINDOW_INDEX
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.clock import FixedClock
from tests.support.roles import (
    APPLICATION_ROLE,
    APPLICATION_ROLE_PASSWORD,
    engine_as,
    provision_restricted_roles,
)
from tests.support.statements import recorded_statements

pytestmark = [pytest.mark.postgres, pytest.mark.usefixtures("postgres_session")]

NOW: Final[datetime] = FixedClock().now()
CUTOFF: Final[datetime] = finished_window_cutoff(NOW)
SMALL_BATCH: Final[int] = 50
OLD_COUNTERS: Final[int] = SMALL_BATCH + 20
YOUNG_COUNTERS: Final[int] = 30
# One statement for each of the four parts of a sweep with nothing else due.
SWEEP_STATEMENTS: Final[int] = 4
DELETE_PREFIX: Final[str] = "DELETE FROM rate_limit_counter"
LOCK_TIMEOUT: Final[str] = "SET LOCAL lock_timeout = '2s'"
NO_SEQUENTIAL_SCAN: Final[str] = "SET LOCAL enable_seqscan = off"
INSERT_COUNTERS = text(
    "INSERT INTO rate_limit_counter (bucket_key_hash, window_started_at, request_count) "
    "SELECT lpad(to_hex(n), 64, '0'), CAST(:newest AS timestamptz) - n * interval '1 second', 1 "
    "FROM generate_series(1, :count) AS n"
)


@pytest.fixture(scope="module")
def application_engine(postgres_engine: Engine, postgres_url: str) -> Iterator[Engine]:
    """Yield an engine signed in as the restricted application role."""
    provision_restricted_roles(postgres_engine, postgres_url)
    engine = engine_as(postgres_url, APPLICATION_ROLE, APPLICATION_ROLE_PASSWORD)
    try:
        yield engine
    finally:
        engine.dispose()


def add_counters(engine: Engine, *, newest: datetime, count: int) -> None:
    """Commit `count` counters a second apart, the newest one second before `newest`."""
    with engine.begin() as connection:
        connection.execute(INSERT_COUNTERS, {"newest": newest, "count": count})


def window_starts(engine: Engine) -> list[datetime]:
    """Return the start of every committed counter's window, oldest first."""
    with Session(engine) as session:
        statement = select(RateLimitCounter.window_started_at).order_by(
            col(RateLimitCounter.window_started_at)
        )
        return list(session.exec(statement).all())


def sweep_as(engine: Engine, batch: int) -> int:
    """Run the whole sweep once on its own connection and return how many counters went."""
    use_case = ExpireHoldsAndNoShowsUseCase(
        SqlAlchemyUnitOfWork(lambda: Session(engine)), FixedClock(NOW)
    )
    return use_case.execute(SweepCommand(counter_batch_size=batch)).pruned_counter_count


class TestTheSweepPrunesAsTheApplicationRole:
    """One statement, at most a batch, oldest first, and nothing young."""

    def test_one_sweep_deletes_one_batch_of_the_oldest_in_one_statement(
        self, postgres_engine: Engine, application_engine: Engine
    ) -> None:
        add_counters(postgres_engine, newest=CUTOFF, count=OLD_COUNTERS)
        add_counters(postgres_engine, newest=NOW, count=YOUNG_COUNTERS)
        oldest_kept = window_starts(postgres_engine)[SMALL_BATCH]
        with recorded_statements(application_engine) as statements:
            assert sweep_as(application_engine, SMALL_BATCH) == SMALL_BATCH
        assert len(statements) == SWEEP_STATEMENTS
        assert [s for s in statements if s.startswith(DELETE_PREFIX)] == [statements[-1]]
        starts = window_starts(postgres_engine)
        assert len(starts) == OLD_COUNTERS + YOUNG_COUNTERS - SMALL_BATCH
        assert starts[0] == oldest_kept

    def test_the_next_sweeps_finish_the_old_ones_and_never_touch_a_young_one(
        self, postgres_engine: Engine, application_engine: Engine
    ) -> None:
        just_after_the_cutoff = CUTOFF + timedelta(seconds=YOUNG_COUNTERS + 1)
        add_counters(postgres_engine, newest=CUTOFF, count=OLD_COUNTERS)
        add_counters(postgres_engine, newest=just_after_the_cutoff, count=YOUNG_COUNTERS)
        assert sweep_as(application_engine, SMALL_BATCH) == SMALL_BATCH
        assert sweep_as(application_engine, SMALL_BATCH) == OLD_COUNTERS - SMALL_BATCH
        assert sweep_as(application_engine, SMALL_BATCH) == 0
        starts = window_starts(postgres_engine)
        assert len(starts) == YOUNG_COUNTERS
        assert min(starts) >= CUTOFF


class TestTheStatementStandsOnItsIndex:
    """The planner reaches the old counters through the index of revision 0012."""

    def test_the_plan_reads_the_window_index_once_sequential_scans_are_off(
        self, postgres_engine: Engine
    ) -> None:
        add_counters(postgres_engine, newest=CUTOFF, count=OLD_COUNTERS)
        compiled = pruning_statement(CUTOFF, SMALL_BATCH).compile(dialect=postgresql.dialect())
        with postgres_engine.begin() as connection:
            connection.execute(text("ANALYZE rate_limit_counter"))
            connection.execute(text(NO_SEQUENTIAL_SCAN))
            plan = connection.exec_driver_sql(f"EXPLAIN {compiled}", compiled.params).all()
        text_of_plan = "\n".join(str(line[0]) for line in plan)
        assert RATE_LIMIT_WINDOW_INDEX in text_of_plan
        assert "LockRows" in text_of_plan


class TestALockedCounterIsSkippedAndNotWaitedFor:
    """Two sweeps at once each delete what the other has not taken."""

    def test_a_counter_held_by_another_transaction_is_left_for_later(
        self, postgres_engine: Engine, application_engine: Engine
    ) -> None:
        add_counters(postgres_engine, newest=CUTOFF, count=3)
        with Session(postgres_engine) as holder:
            held_id = holder.exec(
                select(RateLimitCounter.id)
                .order_by(col(RateLimitCounter.window_started_at))
                .limit(1)
                .with_for_update()
            ).one()
            with Session(application_engine) as pruner:
                pruner.execute(text(LOCK_TIMEOUT))
                deleted = SqlRateLimitStore(pruner).delete_windows_before(CUTOFF, SMALL_BATCH)
                pruner.commit()
            holder.commit()
        assert deleted == 2
        with Session(postgres_engine) as reader:
            remaining = reader.exec(select(RateLimitCounter.id)).all()
        assert list(remaining) == [held_id]
