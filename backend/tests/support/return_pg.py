"""Helpers for the tests that run returns and losses against PostgreSQL itself.

`out_today` books, confirms and checks a hire out for today through the use
cases, each on a connection of its own, the way a request wires them.
`run_return` and `run_loss` act on it through whichever unit of work a test
hands in, on a clock set to ten in the morning of the day asked for, so a test
can make the return fail at a moment it chooses or run it days late.
`stored_hire` reads back what was committed, on a connection of its own, so
what a test sees is what the database kept.

Importing this module opens no connection.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, time
from uuid import UUID

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.application.hire.loss import LossCommand, RecordLossUseCase
from app.application.hire.read_models import RentalKey
from app.application.hire.returns import ReturnCommand, ReturnRentalItemsUseCase
from app.application.hire.views import RentalView
from app.application.unit_of_work import UnitOfWork
from app.domain.business_time import business_instant
from app.domain.enums import ConditionGrade
from app.domain.identity import Actor
from app.domain.policies import StandardLateFeePolicy
from app.domain.returns import ItemReturn
from app.infrastructure.models import (
    Asset,
    AssetAllocation,
    AuditEvent,
    Charge,
    Rental,
    RentalItem,
)
from tests.support.booking import opening
from tests.support.booking_api import BookingWorld
from tests.support.checkout_pg import confirm_for_today, run_checkout
from tests.support.clock import FixedClock

COUNTER_TIME = time(10, 0)
RENTAL_ACTIONS = ("rental.", "reservation.returned")


def out_today(engine: Engine, world: BookingWorld, staff: Actor, quantity: int) -> UUID:
    """Return the key of a rental of `quantity` units checked out today by a member of staff."""
    reservation_id = confirm_for_today(engine, world, staff, quantity)
    return run_checkout(engine, staff, reservation_id).rental.detail.id


def clock_on(day: date) -> FixedClock:
    """Return a clock standing at ten in the morning in Cape Town on a day."""
    return FixedClock(business_instant(day, COUNTER_TIME))


def item_keys(engine: Engine, rental_id: UUID) -> list[UUID]:
    """Return the keys of the items of a rental, read on a connection of its own."""
    with Session(engine) as reader:
        return [
            item.id
            for item in reader.exec(
                select(RentalItem)
                .where(col(RentalItem.rental_id) == rental_id)
                .order_by(col(RentalItem.id))
            )
        ]


def run_return(
    engine: Engine,
    staff: Actor,
    rental_id: UUID,
    day: date,
    *,
    items: list[UUID] | None = None,
    unit_of_work: Callable[[], UnitOfWork] | None = None,
) -> RentalView:
    """Take the units named back on a day, every unit when none is named."""
    keys = items if items is not None else item_keys(engine, rental_id)
    build = unit_of_work or opening(engine)
    return ReturnRentalItemsUseCase(build(), clock_on(day), StandardLateFeePolicy()).execute(
        ReturnCommand(
            actor=staff,
            key=RentalKey.of(rental_id),
            returns=tuple(
                ItemReturn(rental_item_id=key, condition_in=ConditionGrade.A) for key in keys
            ),
        )
    )


def run_loss(engine: Engine, staff: Actor, rental_id: UUID, item_id: UUID, day: date) -> RentalView:
    """Record one unit of a rental as lost on a day."""
    return RecordLossUseCase(opening(engine)(), clock_on(day), StandardLateFeePolicy()).execute(
        LossCommand(actor=staff, key=RentalKey.of(rental_id), rental_item_id=item_id)
    )


def stored_hire(engine: Engine, rental_id: UUID) -> dict[str, object]:
    """Return what is committed of a hire, read on a connection of its own."""
    with Session(engine) as reader:
        rental = reader.get(Rental, rental_id)
        assert rental is not None
        items = reader.exec(select(RentalItem).where(col(RentalItem.rental_id) == rental_id)).all()
        unit_ids = [item.asset_id for item in items]
        return {
            "status": rental.status.value,
            "items_back": sum(item.returned_at is not None for item in items),
            "charge_types": sorted(
                charge.charge_type.value
                for charge in reader.exec(select(Charge).where(col(Charge.rental_id) == rental_id))
            ),
            "unit_statuses": sorted(
                unit.status.value
                for unit in reader.exec(select(Asset).where(col(Asset.id).in_(unit_ids)))
            ),
            "active_allocations": len(
                reader.exec(
                    select(AssetAllocation).where(
                        col(AssetAllocation.asset_id).in_(unit_ids),
                        col(AssetAllocation.released_at).is_(None),
                    )
                ).all()
            ),
            "audit_actions": sorted(
                event.action
                for event in reader.exec(select(AuditEvent))
                if event.action.startswith(RENTAL_ACTIONS)
            ),
        }


__all__ = [
    "clock_on",
    "item_keys",
    "out_today",
    "run_loss",
    "run_return",
    "stored_hire",
]
