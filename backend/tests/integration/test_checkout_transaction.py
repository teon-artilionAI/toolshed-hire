"""A checkout is one transaction on PostgreSQL.

In one unit of work a checkout opens the rental, writes an item for every
allocation and the two charges, moves every unit to ON_HIRE and the
reservation to COLLECTED, and writes the audit events (BR-26 to BR-28, BR-49).
These run it against the real database and read the result back through a
connection of their own. Then they make it fail at three moments, the audit
write, the commit, and a unit that cannot go on hire, and prove that nothing
of it was kept.

The keys of the schema that back the same rules up are proved on their own in
test_rental_schema_keys.py. The helpers are in tests/support/checkout_pg.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.application.unit_of_work import UnitOfWork
from app.domain.enums import (
    AssetStatus,
    ChargeType,
    ConditionGrade,
    RentalStatus,
    ReservationStatus,
    UserRole,
)
from app.domain.errors import StateTransitionError
from app.domain.identity import Actor
from app.infrastructure.models import Asset, Charge, Rental, RentalItem, Reservation
from tests.support.booking import (
    AuditWriteFailed,
    CommitFailed,
    UnitOfWorkThatCannotCommit,
    UnitOfWorkWithBrokenAudit,
)
from tests.support.booking_api import BookingWorld, build_booking_world
from tests.support.checkout_api import TODAY_HIRE
from tests.support.checkout_pg import (
    HOUR_METER_OUT,
    confirm_for_today,
    held_allocations,
    run_checkout,
    stored,
)
from tests.support.factories import Factory

pytestmark = pytest.mark.postgres

UNITS: Final[int] = 2
CHECKED_OUT_AT: Final[datetime] = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
# The deposit of the factory's model is R600.00, and the reservation holds two.
TWO_DEPOSITS: Final[Decimal] = Decimal("1200.00")
NOTHING_KEPT: Final[dict[str, object]] = {
    "reservation_status": ReservationStatus.CONFIRMED,
    "rentals": 0,
    "items": 0,
    "charges": 0,
    "unit_statuses": ["AVAILABLE"] * (UNITS + 1),
    "audit_actions": [],
}


@pytest.fixture
def world(postgres_session: Session, postgres_factory: Factory) -> BookingWorld:
    """Return a committed branch holding three units, and a customer."""
    built = build_booking_world(postgres_factory, asset_count=UNITS + 1)
    postgres_session.commit()
    return built


@pytest.fixture
def assistant(postgres_session: Session, postgres_factory: Factory, world: BookingWorld) -> Actor:
    """Return a counter assistant of the world's branch, as an actor."""
    account = postgres_factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    postgres_session.commit()
    return Actor(user_id=account.id, role=UserRole.COUNTER_STAFF, branch_id=world.branch.id)


@pytest.fixture
def confirmed(postgres_engine: Engine, world: BookingWorld, assistant: Actor) -> UUID:
    """Return the key of a reservation of two units for today, confirmed at the counter."""
    return confirm_for_today(postgres_engine, world, assistant, UNITS)


class TestACheckoutIsOneTransaction:
    """Everything a checkout writes is committed together."""

    def test_the_rental_its_items_its_charges_the_units_and_the_reservation_together(
        self, postgres_engine: Engine, assistant: Actor, confirmed: UUID
    ) -> None:
        outcome = run_checkout(postgres_engine, assistant, confirmed)
        assert outcome.created is True
        assert stored(postgres_engine, confirmed) == {
            "reservation_status": ReservationStatus.COLLECTED,
            "rentals": 1,
            "items": UNITS,
            "charges": 2,
            "unit_statuses": ["AVAILABLE", "ON_HIRE", "ON_HIRE"],
            "audit_actions": [
                "asset.status_changed",
                "asset.status_changed",
                "rental.checked_out",
                "reservation.collected",
            ],
        }

    def test_the_rows_carry_the_figures_and_the_facts_of_the_checkout(
        self, postgres_engine: Engine, world: BookingWorld, assistant: Actor, confirmed: UUID
    ) -> None:
        outcome = run_checkout(postgres_engine, assistant, confirmed)
        with Session(postgres_engine) as reader:
            rental = reader.get(Rental, outcome.rental.detail.id)
            assert rental is not None
            assert (rental.status, rental.branch_id) == (RentalStatus.OPEN, world.branch.id)
            assert (rental.checked_out_by_user_id, rental.checked_out_at) == (
                assistant.user_id, CHECKED_OUT_AT
            )
            assert (rental.due_back_on, rental.agreement_signed) == (TODAY_HIRE.end, True)
            assert rental.deposit_held == TWO_DEPOSITS
            charges = {
                charge.charge_type: charge
                for charge in reader.exec(
                    select(Charge).where(col(Charge.rental_id) == rental.id)
                )
            }
            reservation = reader.get(Reservation, confirmed)
            assert reservation is not None
            hire = charges[ChargeType.HIRE]
            assert (hire.amount_ex_vat, hire.vat_amount, hire.amount_inc_vat) == (
                reservation.subtotal_ex_vat,
                reservation.vat_amount,
                reservation.estimated_total_inc_vat,
            )
            assert charges[ChargeType.DEPOSIT_HOLD].amount_inc_vat == rental.deposit_held
            items = reader.exec(
                select(RentalItem).where(col(RentalItem.rental_id) == rental.id)
            ).all()
            assert {(item.condition_out, item.hour_meter_out) for item in items} == {
                (ConditionGrade.B, HOUR_METER_OUT)
            }
            on_hire = reader.exec(
                select(Asset).where(col(Asset.status) == AssetStatus.ON_HIRE)
            ).all()
            assert {asset.id for asset in on_hire} == {item.asset_id for item in items}
            assert {asset.condition_grade for asset in on_hire} == {ConditionGrade.B}
            assert {asset.hour_meter_reading for asset in on_hire} == {HOUR_METER_OUT}

    def test_a_checkout_asked_for_again_answers_with_the_rental_and_writes_nothing(
        self, postgres_engine: Engine, assistant: Actor, confirmed: UUID
    ) -> None:
        first = run_checkout(postgres_engine, assistant, confirmed)
        before = stored(postgres_engine, confirmed)
        again = run_checkout(postgres_engine, assistant, confirmed)
        assert (again.created, again.rental.detail.id) == (False, first.rental.detail.id)
        assert stored(postgres_engine, confirmed) == before


class TestAFailedCheckoutKeepsNothing:
    """Whatever stops a checkout, the reservation and its units are as they were."""

    def test_an_audit_event_that_cannot_be_written_undoes_everything(
        self, postgres_engine: Engine, assistant: Actor, confirmed: UUID
    ) -> None:
        def broken() -> UnitOfWork:
            """Return the real unit of work, with an audit log that cannot be written."""
            return UnitOfWorkWithBrokenAudit(lambda: Session(postgres_engine))

        with pytest.raises(AuditWriteFailed):
            run_checkout(postgres_engine, assistant, confirmed, broken)
        assert stored(postgres_engine, confirmed) == NOTHING_KEPT

    def test_a_commit_that_fails_undoes_everything(
        self, postgres_engine: Engine, assistant: Actor, confirmed: UUID
    ) -> None:
        def failing() -> UnitOfWork:
            """Return the real unit of work, with a commit that never succeeds."""
            return UnitOfWorkThatCannotCommit(lambda: Session(postgres_engine))

        with pytest.raises(CommitFailed):
            run_checkout(postgres_engine, assistant, confirmed, failing)
        assert stored(postgres_engine, confirmed) == NOTHING_KEPT

    def test_a_unit_put_in_quarantine_since_the_booking_refuses_the_whole_checkout(
        self, postgres_engine: Engine, assistant: Actor, confirmed: UUID
    ) -> None:
        held = held_allocations(postgres_engine, confirmed)
        with Session(postgres_engine) as writer:
            unit = writer.get(Asset, held[0].asset_id)
            assert unit is not None
            unit.status = AssetStatus.QUARANTINED
            writer.add(unit)
            writer.commit()
        with pytest.raises(StateTransitionError, match="in quarantine"):
            run_checkout(postgres_engine, assistant, confirmed)
        after = stored(postgres_engine, confirmed)
        assert (after["reservation_status"], after["rentals"], after["items"]) == (
            ReservationStatus.CONFIRMED, 0, 0
        )
        assert after["unit_statuses"] == ["AVAILABLE", "AVAILABLE", "QUARANTINED"]
