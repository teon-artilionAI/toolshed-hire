"""Cancelling releases the allocations in the same transaction (BR-14).

A cancellation changes the status of a reservation and lets every unit it
holds go. Those are one commit. If they were two, there would be a moment at
which a cancelled booking still kept a machine off the shelf, or a booking
that still stood had lost its machines.

The claim is about what another connection can see, so the use cases run in
units of work that open their own connections and every assertion is made
through a different one. A cancellation that cannot commit, and one whose
audit event the database refuses, both leave every unit held and the status
as it was.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Final, Self

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import DataError
from sqlmodel import Session, col, select

from app.domain.audit import AuditEvent as DomainAuditEvent
from app.domain.enums import ReleaseReason, ReservationStatus
from app.infrastructure.audit import SqlAuditLog
from app.infrastructure.models import AssetAllocation, Reservation
from app.infrastructure.notification import FakeEmailGateway
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.booking import (
    CommitFailed,
    SqlDesk,
    UnitOfWorkThatCannotCommit,
    cancellation_of,
    customer_of,
    draft_command,
    opening,
    sql_desk,
)
from tests.support.booking_api import BookingWorld, build_booking_world
from tests.support.clock import FixedClock
from tests.support.factories import Factory

pytestmark = pytest.mark.postgres

ACTION_COLUMN_WIDTH: Final[int] = 60
UNITS: Final[int] = 3


class OverlongActionAuditLog(SqlAuditLog):
    """The real audit log, handed an action name the column cannot hold."""

    def record(self, event: DomainAuditEvent) -> None:
        """Write the event with an action one character longer than the column."""
        super().record(replace(event, action="x" * (ACTION_COLUMN_WIDTH + 1)))


class UnitOfWorkWhoseAuditInsertIsRefused(SqlAlchemyUnitOfWork):
    """The real unit of work, with the audit log above over the same session."""

    def __enter__(self) -> Self:
        """Open the real transaction, then swap in the audit log that will be refused."""
        entered = super().__enter__()
        self.audit = OverlongActionAuditLog(self._open_session())
        return entered


@pytest.fixture
def world(postgres_session: Session, postgres_factory: Factory) -> BookingWorld:
    """Return a committed branch, a model with three units and a customer."""
    built = build_booking_world(postgres_factory, asset_count=UNITS)
    postgres_session.commit()
    return built


@pytest.fixture
def desk(postgres_engine: Engine) -> SqlDesk:
    """Return the booking use cases, each on a connection of its own."""
    return sql_desk(opening(postgres_engine), FakeEmailGateway(), FixedClock())


def desk_on(engine: Engine, unit_of_work: type[SqlAlchemyUnitOfWork]) -> SqlDesk:
    """Return the booking use cases over a unit of work that fails in a chosen way."""
    return sql_desk(opening(engine, unit_of_work), FakeEmailGateway(), FixedClock())


def active_allocations(session: Session) -> list[AssetAllocation]:
    """Return every allocation another connection can see that still holds a unit."""
    session.rollback()
    return list(
        session.exec(select(AssetAllocation).where(col(AssetAllocation.released_at).is_(None)))
    )


class TestCancellingReleasesTheAllocationsInTheSameTransaction:
    """BR-14. The status and the releases are one commit, or neither happens."""

    def test_a_committed_cancellation_shows_the_status_and_every_release_together(
        self, postgres_session: Session, world: BookingWorld, desk: SqlDesk
    ) -> None:
        customer = customer_of(world)
        confirmed = desk.confirmed(draft_command(world, quantity=UNITS))
        desk.cancel.execute(cancellation_of(confirmed, customer, "The job fell through."))

        postgres_session.rollback()
        stored = postgres_session.get(Reservation, confirmed.detail.id)
        assert stored is not None
        assert stored.status is ReservationStatus.CANCELLED
        assert stored.cancellation_reason == "The job fell through."
        allocations = postgres_session.exec(select(AssetAllocation)).all()
        assert len(allocations) == UNITS
        assert {allocation.release_reason for allocation in allocations} == {
            ReleaseReason.CANCELLED
        }
        assert {allocation.released_at for allocation in allocations} == {stored.cancelled_at}

    def test_a_cancellation_that_cannot_commit_releases_nothing(
        self, postgres_engine: Engine, postgres_session: Session, world: BookingWorld, desk: SqlDesk
    ) -> None:
        customer = customer_of(world)
        held = desk.held(draft_command(world, quantity=UNITS))
        broken = desk_on(postgres_engine, UnitOfWorkThatCannotCommit)
        with pytest.raises(CommitFailed):
            broken.cancel.execute(cancellation_of(held, customer))
        assert len(active_allocations(postgres_session)) == UNITS
        stored = postgres_session.get(Reservation, held.detail.id)
        assert stored is not None
        assert stored.status is ReservationStatus.HELD

    def test_a_cancellation_whose_audit_insert_is_refused_releases_nothing(
        self, postgres_engine: Engine, postgres_session: Session, world: BookingWorld, desk: SqlDesk
    ) -> None:
        customer = customer_of(world)
        held = desk.held(draft_command(world, quantity=UNITS))
        broken = desk_on(postgres_engine, UnitOfWorkWhoseAuditInsertIsRefused)
        with pytest.raises(DataError):
            broken.cancel.execute(cancellation_of(held, customer))
        assert len(active_allocations(postgres_session)) == UNITS

    def test_the_released_units_can_be_held_by_the_next_customer(
        self, postgres_session: Session, world: BookingWorld, desk: SqlDesk
    ) -> None:
        customer = customer_of(world)
        first = desk.held(draft_command(world, quantity=UNITS))
        desk.cancel.execute(cancellation_of(first, customer))
        second = desk.held(draft_command(world, quantity=UNITS))
        assert second.detail.lines[0].allocated_count == UNITS
        assert len(active_allocations(postgres_session)) == UNITS
