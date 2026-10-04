"""A settled hire corrected on PostgreSQL, with the settled rows it holds left alone (BR-24).

The repository writes a charge's status only from PENDING, so a settled row
handed back to it as waived is refused and stays exactly as it was. A settled
hire is never edited (BR-53), so a positive adjustment of it is refused and
keeps nothing, and a negative one is paid back at once and leaves it SETTLED
with the `settled_at` it had. An adjustment whose audit event cannot be
written keeps nothing. The waiver and the reversal are in
tests/integration/test_charge_correction_transaction.py.

The hire of two units goes out on Monday the second of March 2026, is due back
on the fifth and comes back two days late, which settles it. The helpers are
in tests/support/admin_pg.py and tests/support/return_pg.py.
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
from app.domain.enums import ChargeStatus, ChargeType, RentalStatus
from app.domain.errors import StateTransitionError
from app.domain.identity import Actor
from app.infrastructure.models import Charge, Rental
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.admin_pg import (
    REASON,
    all_back_late,
    audit_trail,
    charge_rows,
    committed_administrator,
    committed_world,
    counter_assistant,
    late_fees,
    row_of,
    run_adjustment,
)
from tests.support.booking import AuditWriteFailed, UnitOfWorkWithBrokenAudit, opening
from tests.support.booking_api import BookingWorld
from tests.support.factories import Factory
from tests.support.return_pg import out_today

pytestmark = pytest.mark.postgres

UNITS: Final[int] = 2
NEXT_DAY: Final[date] = date(2026, 3, 8)
CHARGE_EVENTS: Final[str] = "charge."


@pytest.fixture
def world(postgres_session: Session, postgres_factory: Factory) -> BookingWorld:
    """Return a committed branch holding two units of the factory's model."""
    return committed_world(postgres_session, postgres_factory, UNITS)


@pytest.fixture
def assistant(postgres_session: Session, postgres_factory: Factory, world: BookingWorld) -> Actor:
    """Return a counter assistant of the world's branch, as an actor."""
    return counter_assistant(postgres_session, postgres_factory, world)


@pytest.fixture
def administrator(postgres_session: Session, postgres_factory: Factory) -> Actor:
    """Return a committed administrator, as an actor."""
    return committed_administrator(postgres_session, postgres_factory)


@pytest.fixture
def rental_id(postgres_engine: Engine, world: BookingWorld, assistant: Actor) -> UUID:
    """Return the key of a rental of both units, checked out today."""
    return out_today(postgres_engine, world, assistant, UNITS)


class TestTheRepositoryRefusesToWaiveASettledCharge:
    """A settled row is never written over, whatever the domain hands the repository (BR-24)."""

    def test_saving_a_settled_fee_as_waived_is_refused(
        self, postgres_engine: Engine, assistant: Actor, rental_id: UUID
    ) -> None:
        all_back_late(postgres_engine, assistant, rental_id)
        fee_id = UUID(str(late_fees(postgres_engine, rental_id)[0]["id"]))
        before = row_of(postgres_engine, Charge, fee_id)
        unit_of_work: UnitOfWork = SqlAlchemyUnitOfWork(lambda: Session(postgres_engine))
        with unit_of_work as uow:
            rental = uow.rentals.find_for_update(RentalKey.of(rental_id))
            assert rental is not None
            rental.charges = [
                replace(charge, status=ChargeStatus.WAIVED, reason=REASON)
                if charge.id == fee_id
                else charge
                for charge in rental.charges
            ]
            with pytest.raises(StateTransitionError, match="never edited"):
                uow.rentals.save(rental)
        assert row_of(postgres_engine, Charge, fee_id) == before


class TestASettledHireIsNeverEdited:
    """Only a correction that gives money back is made to a settled hire (BR-53)."""

    def test_an_amount_owed_is_refused_and_keeps_nothing(
        self, postgres_engine: Engine, assistant: Actor, administrator: Actor, rental_id: UUID
    ) -> None:
        all_back_late(postgres_engine, assistant, rental_id)
        charges_before = charge_rows(postgres_engine, rental_id)
        rental_before = row_of(postgres_engine, Rental, rental_id)
        with pytest.raises(StateTransitionError, match="only a correction that gives money back"):
            run_adjustment(postgres_engine, administrator, rental_id, "150.00", NEXT_DAY)
        assert charge_rows(postgres_engine, rental_id) == charges_before
        assert row_of(postgres_engine, Rental, rental_id) == rental_before
        assert audit_trail(postgres_engine, CHARGE_EVENTS) == []

    def test_a_credit_is_paid_back_and_the_hire_stays_settled(
        self, postgres_engine: Engine, assistant: Actor, administrator: Actor, rental_id: UUID
    ) -> None:
        all_back_late(postgres_engine, assistant, rental_id)
        settled_before = row_of(postgres_engine, Rental, rental_id)["settled_at"]
        run_adjustment(postgres_engine, administrator, rental_id, "-150.00", NEXT_DAY)

        rental = row_of(postgres_engine, Rental, rental_id)
        assert rental["status"] is RentalStatus.SETTLED
        assert (rental["balance_due"], rental["settled_at"]) == (Decimal("0.00"), settled_before)
        (adjustment,) = [
            row for row in charge_rows(postgres_engine, rental_id)
            if row["charge_type"] == ChargeType.ADJUSTMENT
        ]
        assert (adjustment["status"], adjustment["waiver_reason"]) == (
            ChargeStatus.SETTLED, REASON
        )
        assert (
            adjustment["amount_ex_vat"], adjustment["vat_amount"], adjustment["amount_inc_vat"]
        ) == (Decimal("-130.43"), Decimal("-19.57"), Decimal("-150.00"))
        (event,) = audit_trail(postgres_engine, CHARGE_EVENTS)
        assert (event.action, event.entity_id) == ("charge.adjusted", adjustment["id"])

    def test_an_adjustment_whose_event_cannot_be_written_keeps_nothing(
        self, postgres_engine: Engine, assistant: Actor, administrator: Actor, rental_id: UUID
    ) -> None:
        all_back_late(postgres_engine, assistant, rental_id)
        charges_before = charge_rows(postgres_engine, rental_id)
        rental_before = row_of(postgres_engine, Rental, rental_id)
        with pytest.raises(AuditWriteFailed):
            run_adjustment(
                postgres_engine,
                administrator,
                rental_id,
                "-150.00",
                NEXT_DAY,
                unit_of_work=opening(postgres_engine, UnitOfWorkWithBrokenAudit),
            )
        assert charge_rows(postgres_engine, rental_id) == charges_before
        assert row_of(postgres_engine, Rental, rental_id) == rental_before
