"""A return is one transaction on PostgreSQL, and what it lets go can be booked again.

In one unit of work a return records each unit as back, raises its late fee,
lets its allocation go, puts the unit back on the shelf, moves the rental and
the reservation on, settles the deposit when the last unit is back and writes
the audit events (BR-29 to BR-32, BR-49). These run it against the real
database and read the result back through a connection of their own. Then they
make it fail at the audit write and at the commit and prove that nothing of it
was kept, prove that a unit let go early can be held at once for days its old
hire still covered, and prove that the database refuses an edit of a settled
charge as well as the domain (BR-24).

The hire goes out on Monday the second of March 2026 and is due back on the
fifth. The helpers are in tests/support/return_pg.py.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Final
from uuid import UUID

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from app.application.hire.read_models import RentalKey
from app.application.unit_of_work import UnitOfWork
from app.domain.enums import ChargeStatus, UserRole
from app.domain.errors import AllocationConflictError, StateTransitionError
from app.domain.identity import Actor
from app.domain.period import BookingPeriod
from app.infrastructure.models import Rental
from app.infrastructure.notification import FakeEmailGateway
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.booking import (
    AuditWriteFailed,
    CommitFailed,
    UnitOfWorkThatCannotCommit,
    UnitOfWorkWithBrokenAudit,
    draft_command,
    opening,
    sql_desk,
)
from tests.support.booking_api import BookingWorld, build_booking_world
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.return_pg import item_keys, out_today, run_loss, run_return, stored_hire

pytestmark = pytest.mark.postgres

UNITS: Final[int] = 2
TWO_DAYS_LATE: Final[date] = date(2026, 3, 7)
FIFTEEN_DAYS_LATE: Final[date] = date(2026, 3, 20)
NOTHING_KEPT: Final[dict[str, object]] = {
    "status": "OPEN",
    "items_back": 0,
    "charge_types": ["DEPOSIT_HOLD", "HIRE"],
    "unit_statuses": ["ON_HIRE", "ON_HIRE"],
    "active_allocations": UNITS,
    "audit_actions": ["rental.checked_out"],
}


@pytest.fixture
def world(postgres_session: Session, postgres_factory: Factory) -> BookingWorld:
    """Return a committed branch holding two units of the factory's model."""
    built = build_booking_world(postgres_factory, asset_count=UNITS)
    postgres_session.commit()
    return built


@pytest.fixture
def assistant(postgres_session: Session, postgres_factory: Factory, world: BookingWorld) -> Actor:
    """Return a counter assistant of the world's branch, as an actor."""
    account = postgres_factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    postgres_session.commit()
    return Actor(user_id=account.id, role=UserRole.COUNTER_STAFF, branch_id=world.branch.id)


@pytest.fixture
def rental_id(postgres_engine: Engine, world: BookingWorld, assistant: Actor) -> UUID:
    """Return the key of a rental of both units, checked out today."""
    return out_today(postgres_engine, world, assistant, UNITS)


class TestAReturnIsOneTransaction:
    """Everything a return writes is committed together, and the constraints agree."""

    def test_the_last_units_back_two_days_late_settle_the_hire(
        self, postgres_engine: Engine, assistant: Actor, rental_id: UUID
    ) -> None:
        view = run_return(postgres_engine, assistant, rental_id, TWO_DAYS_LATE)
        detail = view.detail
        # Two units at R600.00 each, and two days at R120.00 for each of them.
        assert (detail.deposit_held, detail.deposit_withheld, detail.deposit_refunded) == (
            Decimal("1200.00"), Decimal("480.00"), Decimal("720.00")
        )
        assert stored_hire(postgres_engine, rental_id) == {
            "status": "SETTLED",
            "items_back": UNITS,
            "charge_types": ["DEPOSIT_HOLD", "DEPOSIT_RELEASE", "HIRE", "LATE_FEE", "LATE_FEE"],
            "unit_statuses": ["AVAILABLE", "AVAILABLE"],
            "active_allocations": 0,
            "audit_actions": [
                "rental.checked_out",
                "rental.deposit_settled",
                "rental.items_returned",
                "reservation.returned",
            ],
        }

    def test_an_audit_event_that_cannot_be_written_undoes_everything(
        self, postgres_engine: Engine, assistant: Actor, rental_id: UUID
    ) -> None:
        with pytest.raises(AuditWriteFailed):
            run_return(
                postgres_engine,
                assistant,
                rental_id,
                TWO_DAYS_LATE,
                unit_of_work=opening(postgres_engine, UnitOfWorkWithBrokenAudit),
            )
        assert stored_hire(postgres_engine, rental_id) == NOTHING_KEPT

    def test_a_commit_that_fails_undoes_everything(
        self, postgres_engine: Engine, assistant: Actor, rental_id: UUID
    ) -> None:
        with pytest.raises(CommitFailed):
            run_return(
                postgres_engine,
                assistant,
                rental_id,
                TWO_DAYS_LATE,
                unit_of_work=opening(postgres_engine, UnitOfWorkThatCannotCommit),
            )
        assert stored_hire(postgres_engine, rental_id) == NOTHING_KEPT


class TestAUnitLetGoIsBookableAgain:
    """The released allocation frees the unit for days its old hire still covered (US-23)."""

    def test_a_unit_back_early_can_be_held_for_days_inside_its_old_hire(
        self,
        postgres_engine: Engine,
        postgres_session: Session,
        postgres_factory: Factory,
    ) -> None:
        lone = build_booking_world(postgres_factory, asset_count=1)
        staff = postgres_factory.user(role=UserRole.COUNTER_STAFF, branch=lone.branch)
        postgres_session.commit()
        actor = Actor(user_id=staff.id, role=UserRole.COUNTER_STAFF, branch_id=lone.branch.id)
        rental = out_today(postgres_engine, lone, actor, 1)
        overlapping = BookingPeriod(date(2026, 3, 3), date(2026, 3, 5))
        desk = sql_desk(opening(postgres_engine), FakeEmailGateway(), FixedClock())
        command = draft_command(
            lone, overlapping, actor=actor, customer_profile_id=lone.profile.id
        )
        with pytest.raises(AllocationConflictError):
            desk.held(command)

        run_return(postgres_engine, actor, rental, date(2026, 3, 2))
        held = desk.held(command)
        assert held.detail.status.value == "HELD"


class TestALossOnPostgres:
    """The figures of a loss keep every check of the schema."""

    def test_a_lost_unit_closes_the_hire_with_a_balance_due(
        self, postgres_engine: Engine, assistant: Actor, rental_id: UUID
    ) -> None:
        first, second = item_keys(postgres_engine, rental_id)
        run_return(postgres_engine, assistant, rental_id, date(2026, 3, 5), items=[first])
        view = run_loss(postgres_engine, assistant, rental_id, second, FIFTEEN_DAYS_LATE)
        detail = view.detail
        assert (detail.deposit_withheld, detail.deposit_refunded) == (
            Decimal("1200.00"), Decimal("0.00")
        )
        # Fourteen days at R120.00 and R4,200.00 less the R600.00 kept, less
        # the R600.00 of the other unit's deposit that was left to pay it.
        assert detail.balance_due == Decimal("4680.00")
        assert stored_hire(postgres_engine, rental_id)["unit_statuses"] == ["AVAILABLE", "LOST"]
        assert stored_hire(postgres_engine, rental_id)["status"] == "RETURNED"


class TestASettledChargeIsNeverEdited:
    """The repository refuses to write over a settled charge (BR-24)."""

    def test_saving_a_settled_charge_as_pending_is_refused(
        self, postgres_engine: Engine, rental_id: UUID
    ) -> None:
        unit_of_work: UnitOfWork = SqlAlchemyUnitOfWork(lambda: Session(postgres_engine))
        with unit_of_work as uow:
            rental = uow.rentals.find_for_update(RentalKey.of(rental_id))
            assert rental is not None
            hire = rental.charges[0]
            assert hire.status is ChargeStatus.SETTLED
            rental.charges[0] = replace(hire, status=ChargeStatus.PENDING)
            with pytest.raises(StateTransitionError, match="never edited"):
                uow.rentals.save(rental)
        with Session(postgres_engine) as reader:
            stored = reader.get(Rental, rental_id)
            assert stored is not None and stored.status.value == "OPEN"
