"""Each move of a reservation is one transaction, proved from a second connection.

A draft writes a reservation, its lines and an audit event. A hold writes an
allocation for every unit and an audit event. A confirmation writes an audit
event and a queued notification. BR-09 and BR-49 say the rows of one move
commit together or not at all. A cancellation is held to the same promise in
test_cancellation_transaction.py.

An in memory test can show that the code asks for that. Only a real database
can show that it happens, because the claim is about what another connection
can see. So the use cases here run in units of work that open their own
connections, and every assertion is made through a different one. A row that
connection can read has been committed. A row it cannot read never was.

The audit failure in this file is a genuine one. The audit log is handed an
action name longer than the column, PostgreSQL refuses the insert, and whatever
the move had already written in the same transaction goes with it.

What happens to the notification after the commit is in
test_notification_outbox.py.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Final, Self
from uuid import UUID

import pytest
from sqlalchemy import Engine, func
from sqlalchemy.exc import DataError
from sqlmodel import Session, col, select

from app.domain.audit import AuditEvent as DomainAuditEvent
from app.domain.enums import ReservationStatus, UserRole
from app.domain.errors import AllocationConflictError
from app.infrastructure.audit import SqlAuditLog
from app.infrastructure.models import (
    AssetAllocation,
    AuditEvent,
    Notification,
    Reservation,
    ReservationLine,
)
from app.infrastructure.notification import FakeEmailGateway
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.request_context import RequestContext, bind_request_context, release_request_context
from tests.support.booking import (
    CommitFailed,
    SqlDesk,
    UnitOfWorkThatCannotCommit,
    actor_of,
    customer_of,
    draft_command,
    move_on,
    opening,
    sql_desk,
)
from tests.support.booking_api import BookingWorld, build_booking_world
from tests.support.clock import FixedClock
from tests.support.factories import Factory

pytestmark = pytest.mark.postgres

REQUEST_ID: Final[str] = "6f1c2b9e-3d4a-4c5b-8e7f-0a1b2c3d4e5f"
# From the block reserved for documentation, so it is nobody's real address.
CLIENT_ADDRESS: Final[str] = "203.0.113.9"
ACTION_COLUMN_WIDTH: Final[int] = 60
OCCURRED_AT: Final[datetime] = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
UNITS: Final[int] = 3
NOTHING: Final[dict[str, int]] = {
    "reservation": 0,
    "reservation_line": 0,
    "asset_allocation": 0,
    "audit_event": 0,
    "notification": 0,
}


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


def row_counts(session: Session) -> dict[str, int]:
    """Return how many committed rows each table a move writes to holds."""
    session.rollback()
    tables = (Reservation, ReservationLine, AssetAllocation, AuditEvent, Notification)
    return {
        str(table.__tablename__): int(session.exec(select(func.count()).select_from(table)).one())
        for table in tables
    }


def active_allocations(session: Session) -> list[AssetAllocation]:
    """Return every allocation another connection can see that still holds a unit."""
    session.rollback()
    return list(
        session.exec(select(AssetAllocation).where(col(AssetAllocation.released_at).is_(None)))
    )


class TestEachMoveCommitsItsRowsTogether:
    """What each move adds, counted from a connection that did not write it."""

    def test_a_draft_adds_a_reservation_a_line_and_an_event_and_holds_nothing(
        self, postgres_session: Session, world: BookingWorld, desk: SqlDesk
    ) -> None:
        desk.drafted(draft_command(world, quantity=UNITS))
        assert row_counts(postgres_session) == {
            **NOTHING,
            "reservation": 1,
            "reservation_line": 1,
            "audit_event": 1,
        }

    def test_a_hold_of_three_units_allocates_three_specific_assets_in_one_transaction(
        self, postgres_session: Session, world: BookingWorld, desk: SqlDesk
    ) -> None:
        """US-12. One line, three named units, one commit."""
        asset_ids = {asset.id for asset in world.assets}
        held = desk.held(draft_command(world, quantity=UNITS))
        allocations = active_allocations(postgres_session)
        assert {allocation.asset_id for allocation in allocations} == asset_ids
        assert len({allocation.reservation_line_id for allocation in allocations}) == 1
        assert held.detail.lines[0].allocated_count == UNITS
        assert row_counts(postgres_session)["audit_event"] == 2

    def test_with_only_two_units_free_nothing_is_allocated(
        self, postgres_session: Session, world: BookingWorld, desk: SqlDesk
    ) -> None:
        """US-12. Two of three is none of three (BR-09)."""
        customer = customer_of(world)
        desk.held(draft_command(world, quantity=1))
        wanted = desk.drafted(draft_command(world, quantity=UNITS))
        with pytest.raises(AllocationConflictError):
            desk.hold.execute(move_on(wanted, customer))
        assert len(active_allocations(postgres_session)) == 1
        stored = postgres_session.get(Reservation, wanted.detail.id)
        assert stored is not None
        assert stored.status is ReservationStatus.DRAFT

    def test_a_confirmation_adds_an_event_and_exactly_one_notification(
        self, postgres_session: Session, world: BookingWorld, desk: SqlDesk
    ) -> None:
        customer = customer_of(world)
        held = desk.held(draft_command(world))
        assert row_counts(postgres_session)["notification"] == 0
        desk.confirm.execute(move_on(held, customer))
        counts = row_counts(postgres_session)
        assert counts["notification"] == 1
        assert counts["audit_event"] == 3

    def test_the_audit_event_is_stored_with_the_actor_the_role_the_request_and_the_address(
        self,
        postgres_session: Session,
        postgres_factory: Factory,
        world: BookingWorld,
        desk: SqlDesk,
    ) -> None:
        assistant = postgres_factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
        postgres_session.commit()
        actor = actor_of(assistant)
        tag = world.assets[0].asset_tag
        draft = desk.drafted(
            draft_command(world, actor=actor, customer_profile_id=world.profile.id)
        )

        token = bind_request_context(
            RequestContext(request_id=REQUEST_ID, client_address=ip_address(CLIENT_ADDRESS))
        )
        try:
            held = desk.hold.execute(move_on(draft, actor))
        finally:
            release_request_context(token)

        postgres_session.rollback()
        event = postgres_session.exec(select(AuditEvent).order_by(col(AuditEvent.id))).all()[-1]
        assert event.action == "reservation.held"
        assert event.entity_type == "reservation"
        assert event.entity_id == held.detail.id
        assert event.actor_user_id == actor.user_id
        assert event.actor_role is UserRole.COUNTER_STAFF
        assert event.request_id == UUID(REQUEST_ID)
        assert event.ip_address == ip_address(CLIENT_ADDRESS)
        assert event.before_state == {
            "status": "DRAFT",
            "hold_expires_at": None,
            "active_allocation_count": 0,
        }
        assert event.after_state == {
            "reference": held.detail.reference,
            "status": "HELD",
            "hold_expires_at": "2026-03-02T08:30:00+00:00",
            "active_allocation_count": 1,
            "asset_tags": [tag],
        }

    def test_the_event_is_timed_by_the_clock_the_use_case_was_given(
        self, postgres_engine: Engine, postgres_session: Session, world: BookingWorld
    ) -> None:
        clock = FixedClock(OCCURRED_AT)
        sql_desk(opening(postgres_engine), FakeEmailGateway(), clock).drafted(
            draft_command(world)
        )
        (event,) = postgres_session.exec(select(AuditEvent)).all()
        assert event.occurred_at == OCCURRED_AT


class TestAMoveThatFailsLeavesNothingBehind:
    """Whatever was written before the failure is rolled back with it."""

    def test_a_refused_audit_insert_rolls_the_whole_hold_back(
        self, postgres_engine: Engine, postgres_session: Session, world: BookingWorld, desk: SqlDesk
    ) -> None:
        customer = customer_of(world)
        draft = desk.drafted(draft_command(world, quantity=UNITS))
        before = row_counts(postgres_session)
        broken = desk_on(postgres_engine, UnitOfWorkWhoseAuditInsertIsRefused)
        with pytest.raises(DataError):
            broken.hold.execute(move_on(draft, customer))
        assert row_counts(postgres_session) == before
        assert active_allocations(postgres_session) == []

    def test_the_units_are_free_again_once_the_failed_hold_has_rolled_back(
        self, postgres_engine: Engine, postgres_session: Session, world: BookingWorld, desk: SqlDesk
    ) -> None:
        """The row locks and the allocations both go with the transaction."""
        customer = customer_of(world)
        draft = desk.drafted(draft_command(world, quantity=UNITS))
        broken = desk_on(postgres_engine, UnitOfWorkWhoseAuditInsertIsRefused)
        with pytest.raises(DataError):
            broken.hold.execute(move_on(draft, customer))
        held = desk.hold.execute(move_on(draft, customer))
        assert held.detail.lines[0].allocated_count == UNITS
        assert len(active_allocations(postgres_session)) == UNITS

    def test_a_confirmation_that_cannot_commit_keeps_neither_it_nor_its_notification(
        self, postgres_engine: Engine, postgres_session: Session, world: BookingWorld, desk: SqlDesk
    ) -> None:
        """The outbox row is in the confirmation's transaction, so it shares its fate."""
        customer = customer_of(world)
        held = desk.held(draft_command(world))
        gateway = FakeEmailGateway()
        broken = sql_desk(
            opening(postgres_engine, UnitOfWorkThatCannotCommit), gateway, FixedClock()
        )
        with pytest.raises(CommitFailed):
            broken.confirm.execute(move_on(held, customer))
        assert row_counts(postgres_session)["notification"] == 0
        stored = postgres_session.get(Reservation, held.detail.id)
        assert stored is not None
        assert stored.status is ReservationStatus.HELD
        assert gateway.sent == []
