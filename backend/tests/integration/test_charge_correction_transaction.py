"""A waiver and a reversal are each one transaction on PostgreSQL, and no settled row is touched.

A waiver and a reversal each change the charges of a hire, work its deposit,
balance and status out again, and write their audit event with the
administrator and the reason, in one unit of work (BR-24, BR-25, BR-49). These
run the two use cases against the real database and read the result back
through a connection of their own. Then they make each fail at the audit write
and prove nothing of it was kept, follow a waived fee into the settlement that
comes after it, and compare the reversed charge column for column with what it
was. The repository's refusal to write over a settled charge and the
adjustment of a settled hire are in
tests/integration/test_settled_hire_corrections.py.

The hire of two units goes out on Monday the second of March 2026 and is due
back on the fifth. The helpers are in tests/support/admin_pg.py and
tests/support/return_pg.py.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Final
from uuid import UUID

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from app.domain.enums import ChargeStatus, ChargeType, RentalStatus, UserRole
from app.domain.errors import StateTransitionError
from app.domain.identity import Actor
from app.infrastructure.models import Charge, Rental
from tests.support.admin_pg import (
    REASON,
    all_back_late,
    audit_trail,
    charge_rows,
    committed_administrator,
    committed_world,
    counter_assistant,
    late_fees,
    one_back_late,
    row_of,
    run_reversal,
    run_waiver,
)
from tests.support.booking import AuditWriteFailed, UnitOfWorkWithBrokenAudit, opening
from tests.support.booking_api import BookingWorld
from tests.support.factories import Factory
from tests.support.return_pg import item_keys, out_today, run_return

pytestmark = pytest.mark.postgres

UNITS: Final[int] = 2
NEXT_DAY: Final[date] = date(2026, 3, 8)
CHARGE_EVENTS: Final[str] = "charge."
SIMULATED_PREFIX: Final[str] = "SIM-"


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


class TestAWaiverIsOneTransaction:
    """The waived fee, its reason and its event are kept together, or not at all."""

    def test_the_fee_is_stored_waived_with_its_reason_and_its_event(
        self, postgres_engine: Engine, assistant: Actor, administrator: Actor, rental_id: UUID
    ) -> None:
        fee_id = one_back_late(postgres_engine, assistant, rental_id)
        run_waiver(postgres_engine, administrator, fee_id, NEXT_DAY)

        stored = row_of(postgres_engine, Charge, fee_id)
        assert (stored["status"], stored["waiver_reason"]) == (ChargeStatus.WAIVED, REASON)
        assert (stored["settled_at"], stored["payment_reference"]) == (None, None)
        (event,) = audit_trail(postgres_engine, CHARGE_EVENTS)
        assert (event.action, event.entity_type, event.entity_id) == (
            "charge.waived", "charge", fee_id
        )
        assert (event.actor_user_id, event.actor_role) == (administrator.user_id, UserRole.ADMIN)
        assert event.before_state == {"status": "PENDING"}
        assert (event.after_state or {})["reason"] == REASON

    def test_the_settlement_still_to_come_withholds_nothing_for_the_waived_fee(
        self, postgres_engine: Engine, assistant: Actor, administrator: Actor, rental_id: UUID
    ) -> None:
        fee_id = one_back_late(postgres_engine, assistant, rental_id)
        run_waiver(postgres_engine, administrator, fee_id, NEXT_DAY)
        second = item_keys(postgres_engine, rental_id)[1]
        run_return(postgres_engine, assistant, rental_id, NEXT_DAY, items=[second])

        rental = row_of(postgres_engine, Rental, rental_id)
        # Only the second unit's three days at R120.00 are withheld.
        assert (rental["deposit_withheld"], rental["deposit_refunded"]) == (
            Decimal("360.00"), Decimal("840.00")
        )
        assert rental["status"] is RentalStatus.SETTLED
        assert row_of(postgres_engine, Charge, fee_id)["status"] is ChargeStatus.WAIVED

    def test_an_event_that_cannot_be_written_keeps_nothing(
        self, postgres_engine: Engine, assistant: Actor, administrator: Actor, rental_id: UUID
    ) -> None:
        fee_id = one_back_late(postgres_engine, assistant, rental_id)
        before = row_of(postgres_engine, Charge, fee_id)
        with pytest.raises(AuditWriteFailed):
            run_waiver(
                postgres_engine,
                administrator,
                fee_id,
                NEXT_DAY,
                unit_of_work=opening(postgres_engine, UnitOfWorkWithBrokenAudit),
            )
        assert row_of(postgres_engine, Charge, fee_id) == before
        assert audit_trail(postgres_engine, CHARGE_EVENTS) == []


class TestAReversalNeverTouchesTheOriginal:
    """A reversal is a new negated row, and the settled row it undoes stays exactly as it was."""

    def test_the_reversal_points_back_and_the_original_is_unchanged(
        self, postgres_engine: Engine, assistant: Actor, administrator: Actor, rental_id: UUID
    ) -> None:
        all_back_late(postgres_engine, assistant, rental_id)
        original_id = UUID(str(late_fees(postgres_engine, rental_id)[0]["id"]))
        original_before = row_of(postgres_engine, Charge, original_id)
        rental_before = row_of(postgres_engine, Rental, rental_id)

        run_reversal(postgres_engine, administrator, original_id, NEXT_DAY)

        assert row_of(postgres_engine, Charge, original_id) == original_before
        (reversal,) = [
            row for row in charge_rows(postgres_engine, rental_id)
            if row["reverses_charge_id"] == original_id
        ]
        assert (reversal["charge_type"], reversal["waiver_reason"]) == (
            ChargeType.LATE_FEE, REASON
        )
        assert (reversal["amount_ex_vat"], reversal["vat_amount"], reversal["amount_inc_vat"]) == (
            Decimal("-208.70"), Decimal("-31.30"), Decimal("-240.00")
        )
        # The hire was settled, so the credit is paid back at once.
        assert reversal["status"] is ChargeStatus.SETTLED
        assert str(reversal["payment_reference"]).startswith(SIMULATED_PREFIX)
        rental = row_of(postgres_engine, Rental, rental_id)
        assert rental["status"] is RentalStatus.SETTLED
        assert rental["settled_at"] == rental_before["settled_at"]
        assert (rental["deposit_withheld"], rental["balance_due"]) == (
            Decimal("480.00"), Decimal("0.00")
        )

    def test_the_reversal_and_the_rework_each_write_their_event(
        self, postgres_engine: Engine, assistant: Actor, administrator: Actor, rental_id: UUID
    ) -> None:
        all_back_late(postgres_engine, assistant, rental_id)
        original_id = UUID(str(late_fees(postgres_engine, rental_id)[0]["id"]))
        run_reversal(postgres_engine, administrator, original_id, NEXT_DAY)

        (event,) = audit_trail(postgres_engine, CHARGE_EVENTS)
        (reversal,) = [
            row for row in charge_rows(postgres_engine, rental_id)
            if row["reverses_charge_id"] == original_id
        ]
        assert (event.action, event.entity_id) == ("charge.reversed", original_id)
        assert (event.after_state or {})["reversal_charge_id"] == str(reversal["id"])
        assert (event.after_state or {})["reason"] == REASON
        assert [e.action for e in audit_trail(postgres_engine, "rental.settlement")] == [
            "rental.settlement_reworked"
        ]

    def test_an_event_that_cannot_be_written_keeps_nothing(
        self, postgres_engine: Engine, assistant: Actor, administrator: Actor, rental_id: UUID
    ) -> None:
        all_back_late(postgres_engine, assistant, rental_id)
        charges_before = charge_rows(postgres_engine, rental_id)
        rental_before = row_of(postgres_engine, Rental, rental_id)
        with pytest.raises(AuditWriteFailed):
            run_reversal(
                postgres_engine,
                administrator,
                UUID(str(late_fees(postgres_engine, rental_id)[0]["id"])),
                NEXT_DAY,
                unit_of_work=opening(postgres_engine, UnitOfWorkWithBrokenAudit),
            )
        assert charge_rows(postgres_engine, rental_id) == charges_before
        assert row_of(postgres_engine, Rental, rental_id) == rental_before

    def test_a_charge_is_reversed_once(
        self, postgres_engine: Engine, assistant: Actor, administrator: Actor, rental_id: UUID
    ) -> None:
        all_back_late(postgres_engine, assistant, rental_id)
        original_id = UUID(str(late_fees(postgres_engine, rental_id)[0]["id"]))
        run_reversal(postgres_engine, administrator, original_id, NEXT_DAY)
        with pytest.raises(StateTransitionError, match="already been reversed"):
            run_reversal(postgres_engine, administrator, original_id, NEXT_DAY)
        reversals = [
            row for row in charge_rows(postgres_engine, rental_id)
            if row["reverses_charge_id"] == original_id
        ]
        assert len(reversals) == 1
