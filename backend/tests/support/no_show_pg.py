"""Helpers for the tests that run the no show half of the sweep against PostgreSQL itself.

A sweep is run on a connection of its own, after closing time on the day of
the still clock, through whichever unit of work a test hands in, so a test can
hold one sweep at its commit while another waits. What was committed is read
back on the test's own session after a rollback, so a test sees what the
database kept and not what a session remembers.

Importing this module opens no connection.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import date
from typing import Final, Self

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.application.booking.expire_holds import (
    ExpireHoldsAndNoShowsUseCase,
    SweepCommand,
    SweepResult,
)
from app.domain.enums import ReservationStatus
from app.infrastructure.models import AuditEvent, CustomerProfile, UserAccount
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.booking_api import BookingWorld
from tests.support.clock import FixedClock
from tests.support.counter_api import AFTER_CLOSING
from tests.support.factories import Factory
from tests.support.hire_factories import HireFactory, hire_from
from tests.support.race import BARRIER_TIMEOUT_SECONDS, backend_pid

NO_SHOW_ACTION: Final[str] = "reservation.no_show"
ON_HOLD_ACTION: Final[str] = "customer.put_on_hold"
# Inside the twelve months that end on the second of March 2026, and outside them.
INSIDE_THE_WINDOW: Final[tuple[date, ...]] = (date(2025, 12, 1), date(2026, 2, 2))
OUTSIDE_THE_WINDOW: Final[date] = date(2025, 3, 2)


class UnitOfWorkThatPausesAtCommit(SqlAlchemyUnitOfWork):
    """The real unit of work, which says when it is about to commit and then waits."""

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
    """The real unit of work, which writes down the backend of every transaction it opens."""

    backends: list[int]

    def __enter__(self) -> Self:
        """Open the real transaction, then note the process id of its connection."""
        entered = super().__enter__()
        self.backends.append(backend_pid(self._open_session()))
        return entered


def sweep_on(unit_of_work: SqlAlchemyUnitOfWork) -> Callable[[], SweepResult]:
    """Return a call that runs one sweep after closing time, in the given unit of work."""
    clock = FixedClock(AFTER_CLOSING)
    return lambda: ExpireHoldsAndNoShowsUseCase(unit_of_work, clock).execute(SweepCommand())


def sweep_once(engine: Engine) -> SweepResult:
    """Run one sweep after closing time, on a connection of its own."""
    return sweep_on(SqlAlchemyUnitOfWork(lambda: Session(engine)))()


def stored_profile(session: Session, world: BookingWorld) -> CustomerProfile:
    """Return the customer profile of the world as it is committed."""
    session.rollback()
    profile = session.get(CustomerProfile, world.profile.id)
    assert profile is not None
    session.refresh(profile)
    return profile


def events(session: Session, action: str) -> list[AuditEvent]:
    """Return every committed audit event of one action."""
    session.rollback()
    return list(session.exec(select(AuditEvent).where(col(AuditEvent.action) == action)))


def earlier_no_shows(
    factory: Factory, session: Session, world: BookingWorld, staff: UserAccount, *days: date
) -> None:
    """Commit reservations of the world's customer that were not collected, one for each day."""
    hire = HireFactory(factory)
    for first_day in days:
        hire.booking(
            profile=world.profile,
            created_by=staff,
            branch=world.branch,
            model=world.product_model,
            units=[],
            period=hire_from(first_day),
            status=ReservationStatus.NO_SHOW,
        )
    session.commit()


__all__ = [
    "INSIDE_THE_WINDOW",
    "NO_SHOW_ACTION",
    "ON_HOLD_ACTION",
    "OUTSIDE_THE_WINDOW",
    "UnitOfWorkThatAnnouncesItsBackend",
    "UnitOfWorkThatPausesAtCommit",
    "earlier_no_shows",
    "events",
    "stored_profile",
    "sweep_on",
    "sweep_once",
]
