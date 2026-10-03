"""The keys of the hire tables back the rules of a checkout up, on PostgreSQL.

These go round the application altogether and write to the tables directly,
after one ordinary checkout has given them a rental to work with. The unique
key on the reservation of a rental refuses a second rental for one
reservation (BR-26). The composite foreign key from an item to its allocation
refuses an item whose unit is not the one its allocation holds, and the unique
key on the allocation of an item refuses a second item for one allocation
(BR-28). Each refusal is read from the driver's own diagnostics.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.domain.enums import ConditionGrade, RentalStatus, UserRole
from app.domain.identity import Actor
from app.infrastructure.models import Asset, Rental, RentalItem
from tests.support.booking_api import BookingWorld, build_booking_world
from tests.support.checkout_pg import confirm_for_today, run_checkout
from tests.support.factories import Factory
from tests.support.pg import constraint_name_of, sqlstate_of

pytestmark = pytest.mark.postgres

UNITS: Final[int] = 2
UNIQUE_VIOLATION_SQLSTATE: Final[str] = "23505"
FOREIGN_KEY_VIOLATION_SQLSTATE: Final[str] = "23503"
ONE_RENTAL_PER_RESERVATION: Final[str] = "rental_reservation_id_key"
ONE_ITEM_PER_ALLOCATION: Final[str] = "rental_item_asset_allocation_id_key"
ITEM_AND_ALLOCATION_AGREE: Final[str] = "fk_rental_item_allocation_asset"
SECOND_REFERENCE: Final[str] = "TSH-H-26-900001"


@pytest.fixture
def checked_out(
    postgres_engine: Engine, postgres_session: Session, postgres_factory: Factory
) -> UUID:
    """Check a reservation of two units out, and return the key of the reservation."""
    world: BookingWorld = build_booking_world(postgres_factory, asset_count=UNITS + 1)
    account = postgres_factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    postgres_session.commit()
    staff = Actor(user_id=account.id, role=UserRole.COUNTER_STAFF, branch_id=world.branch.id)
    reservation_id = confirm_for_today(postgres_engine, world, staff, UNITS)
    run_checkout(postgres_engine, staff, reservation_id)
    return reservation_id


def test_a_second_rental_for_one_reservation_is_refused(
    postgres_engine: Engine, checked_out: UUID
) -> None:
    with Session(postgres_engine) as writer:
        first = writer.exec(select(Rental).where(col(Rental.reservation_id) == checked_out)).one()
        writer.add(
            Rental(
                reference=SECOND_REFERENCE,
                reservation_id=checked_out,
                branch_id=first.branch_id,
                status=RentalStatus.OPEN,
                checked_out_at=first.checked_out_at,
                checked_out_by_user_id=first.checked_out_by_user_id,
                due_back_on=first.due_back_on,
                deposit_held=first.deposit_held,
            )
        )
        with pytest.raises(IntegrityError) as refusal:
            writer.flush()
    assert sqlstate_of(refusal.value) == UNIQUE_VIOLATION_SQLSTATE
    assert constraint_name_of(refusal.value) == ONE_RENTAL_PER_RESERVATION


def test_an_item_whose_unit_is_not_the_one_its_allocation_holds_is_refused(
    postgres_engine: Engine, checked_out: UUID
) -> None:
    with Session(postgres_engine) as writer:
        item = writer.exec(select(RentalItem)).first()
        assert item is not None
        other_unit = writer.exec(select(Asset).where(col(Asset.id) != item.asset_id)).first()
        assert other_unit is not None
        item.asset_id = other_unit.id
        writer.add(item)
        with pytest.raises(IntegrityError) as refusal:
            writer.flush()
    assert sqlstate_of(refusal.value) == FOREIGN_KEY_VIOLATION_SQLSTATE
    assert constraint_name_of(refusal.value) == ITEM_AND_ALLOCATION_AGREE


def test_an_allocation_is_collected_into_one_item_only(
    postgres_engine: Engine, checked_out: UUID
) -> None:
    with Session(postgres_engine) as writer:
        item = writer.exec(select(RentalItem)).first()
        assert item is not None
        writer.add(
            RentalItem(
                rental_id=item.rental_id,
                asset_allocation_id=item.asset_allocation_id,
                asset_id=item.asset_id,
                condition_out=ConditionGrade.A,
                checked_out_at=item.checked_out_at,
            )
        )
        with pytest.raises(IntegrityError) as refusal:
            writer.flush()
    assert sqlstate_of(refusal.value) == UNIQUE_VIOLATION_SQLSTATE
    assert constraint_name_of(refusal.value) == ONE_ITEM_PER_ALLOCATION
