"""The four things a thread can do while another thread books the same unit.

Each contender opens its own session, does one piece of work in one
transaction, and returns an Outcome rather than raising. Returning is what lets
the test say "exactly one of these two succeeded" in a single line instead of
unpicking which thread raised what.

Two of them go through the real use case, so the application's row lock is in
play. Two of them insert directly with no lock at all, which is what a future
refactor or a hand written script would do, and is the only way to reach the
exclusion constraint as the last line of defence.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlmodel import Session

from app.application.allocate import AllocationCommand, allocate_assets
from app.domain.enums import AllocationStatus
from app.domain.errors import AssetUnavailableConflict
from app.domain.period import BookingPeriod
from app.infrastructure.models import AssetAllocation
from tests.support.pg import constraint_name_of, sqlstate_of
from tests.support.race import BARRIER_TIMEOUT_SECONDS, Outcome, backend_pid
from tests.support.scenarios import AllocationScenario

logger = logging.getLogger(__name__)

SINGLE_UNIT = 1


@dataclass(frozen=True, slots=True)
class AllocationTarget:
    """The one physical unit and one period that both contenders are after."""

    line_id: UUID
    asset_id: UUID
    branch_id: UUID
    period: BookingPeriod

    @classmethod
    def of(cls, scenario: AllocationScenario, period: BookingPeriod) -> AllocationTarget:
        """Build a target from a scenario holding exactly one asset."""
        return cls(
            line_id=scenario.line.id,
            asset_id=scenario.asset.id,
            branch_id=scenario.branch.id,
            period=period,
        )

    def as_row(self) -> AssetAllocation:
        """Return an active allocation row for this target, not yet added to a session."""
        return AssetAllocation(
            reservation_line_id=self.line_id,
            asset_id=self.asset_id,
            branch_id=self.branch_id,
            start_date=self.period.start,
            end_date=self.period.end,
            status=AllocationStatus.ACTIVE,
            allocated_at=datetime.now(UTC),
            released_at=None,
        )

    def as_command(self, product_model_id: UUID) -> AllocationCommand:
        """Return the use case command that books this target."""
        return AllocationCommand(
            reservation_line_id=self.line_id,
            product_model_id=product_model_id,
            branch_id=self.branch_id,
            period=self.period,
            quantity=SINGLE_UNIT,
        )


def book_through_the_use_case(
    engine: Engine, command: AllocationCommand, barrier: threading.Barrier
) -> Outcome:
    """Run the real allocation use case in its own transaction, racing the other thread."""
    with Session(engine) as session:
        barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)
        try:
            allocate_assets(session, command)
            session.commit()
        except AssetUnavailableConflict as exc:
            session.rollback()
            logger.info("test.contender_lost", extra={"reason": exc.code})
            return Outcome(succeeded=False, error=exc)
        logger.info("test.contender_won", extra={"line_id": str(command.reservation_line_id)})
        return Outcome(succeeded=True)


def insert_without_any_lock(
    engine: Engine, target: AllocationTarget, barrier: threading.Barrier
) -> Outcome:
    """Insert an allocation with no row lock, so only the constraint can refuse it.

    OperationalError is caught alongside IntegrityError because two simultaneous
    unlocked writers can end in a deadlock rather than an exclusion violation.
    Both are the database refusing the second booking, and the caller decides
    which SQLSTATEs it will accept.
    """
    with Session(engine) as session:
        session.add(target.as_row())
        barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)
        try:
            session.commit()
        except (IntegrityError, OperationalError) as exc:
            session.rollback()
            state = sqlstate_of(exc)
            logger.info("test.unlocked_contender_lost", extra={"sqlstate": state})
            return Outcome(
                succeeded=False, error=exc, sqlstate=state, constraint=constraint_name_of(exc)
            )
        logger.info("test.unlocked_contender_won", extra={"asset_id": str(target.asset_id)})
        return Outcome(succeeded=True)


def hold_an_uncommitted_allocation(
    engine: Engine,
    target: AllocationTarget,
    written: threading.Event,
    release: threading.Event,
) -> Outcome:
    """Write an allocation, hold it uncommitted, and commit only when released.

    Raises:
        AssertionError: If nothing ever releases it, which means the second
            writer never reached the lock and the staged race did not happen.

    """
    with Session(engine) as session:
        session.add(target.as_row())
        session.flush()
        written.set()
        if not release.wait(timeout=BARRIER_TIMEOUT_SECONDS):
            session.rollback()
            raise AssertionError(
                "The first writer was never released, so the staged race never completed. "
                "The second writer did not reach the lock it was expected to wait on."
            )
        session.commit()
        return Outcome(succeeded=True)


def insert_after_the_first_writer(
    engine: Engine,
    target: AllocationTarget,
    written: threading.Event,
    announce: threading.Event,
    pid_holder: list[int],
) -> Outcome:
    """Wait for the first writer's row, announce this backend, then insert into it.

    The insert blocks inside PostgreSQL until the first writer commits, and is
    then refused by the exclusion constraint. Announcing the backend process id
    before issuing the statement is what lets the test wait for the block itself
    rather than for an arbitrary number of milliseconds. Nothing commits or
    rolls back between reading that process id and the insert, because against a
    NullPool engine that would close the connection and move the work to a
    different backend.
    """
    with Session(engine) as session:
        pid_holder.append(backend_pid(session))
        written.wait(timeout=BARRIER_TIMEOUT_SECONDS)
        session.add(target.as_row())
        announce.set()
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            return Outcome(
                succeeded=False,
                error=exc,
                sqlstate=sqlstate_of(exc),
                constraint=constraint_name_of(exc),
            )
        return Outcome(succeeded=True)


__all__ = [
    "AllocationTarget",
    "book_through_the_use_case",
    "hold_an_uncommitted_allocation",
    "insert_after_the_first_writer",
    "insert_without_any_lock",
]
