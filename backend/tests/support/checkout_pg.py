"""Helpers for the tests that run a checkout against PostgreSQL itself.

`confirm_for_today` books, holds and confirms a reservation for today through
the use cases, the way a request wires them, each on a connection of its own.
`run_checkout` checks every unit of it out through whichever unit of work a
test hands in, so a test can make the checkout fail at a moment it chooses.
`stored` reads back what was committed, on a connection of its own, so what a
test sees is what the database kept and not what a session remembers.

Importing this module opens no connection.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final
from uuid import UUID

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.application.booking.read_models import ReservationKey
from app.application.hire.checkout import CheckoutCommand, CheckoutOutcome, CheckoutRentalUseCase
from app.application.unit_of_work import UnitOfWork
from app.domain.checkout import HandOver
from app.domain.enums import ConditionGrade
from app.domain.identity import Actor
from app.domain.policies import StandardLateFeePolicy
from app.infrastructure.models import (
    Asset,
    AssetAllocation,
    AuditEvent,
    Charge,
    Rental,
    RentalItem,
    Reservation,
    ReservationLine,
)
from app.infrastructure.notification import FakeEmailGateway
from tests.support.booking import draft_command, opening, sql_desk
from tests.support.booking_api import BookingWorld
from tests.support.checkout_api import TODAY_HIRE
from tests.support.clock import FixedClock

HOUR_METER_OUT: Final[int] = 12
# The audit actions a checkout writes, which `stored` reports.
CHECKOUT_ACTIONS: Final[tuple[str, ...]] = ("rental.", "asset.", "reservation.collected")


def confirm_for_today(engine: Engine, world: BookingWorld, staff: Actor, quantity: int) -> UUID:
    """Return the key of a reservation for today, booked and confirmed by a member of staff."""
    desk = sql_desk(opening(engine), FakeEmailGateway(), FixedClock())
    command = draft_command(
        world, TODAY_HIRE, quantity=quantity, actor=staff, customer_profile_id=world.profile.id
    )
    return desk.confirmed(command).detail.id


def held_allocations(engine: Engine, reservation_id: UUID) -> list[AssetAllocation]:
    """Return the allocations the reservation holds right now, read on a connection of its own."""
    with Session(engine) as reader:
        return list(
            reader.exec(
                select(AssetAllocation)
                .join(
                    ReservationLine,
                    col(ReservationLine.id) == col(AssetAllocation.reservation_line_id),
                )
                .where(
                    col(ReservationLine.reservation_id) == reservation_id,
                    col(AssetAllocation.released_at).is_(None),
                )
            ).all()
        )


def run_checkout(
    engine: Engine,
    actor: Actor,
    reservation_id: UUID,
    unit_of_work: Callable[[], UnitOfWork] | None = None,
) -> CheckoutOutcome:
    """Check every unit of the reservation out in grade B, through the unit of work asked for."""
    hand_overs = tuple(
        HandOver(
            allocation_id=allocation.id,
            condition_out=ConditionGrade.B,
            hour_meter_out=HOUR_METER_OUT,
        )
        for allocation in held_allocations(engine, reservation_id)
    )
    build = unit_of_work or opening(engine)
    return CheckoutRentalUseCase(build(), FixedClock(), StandardLateFeePolicy()).execute(
        CheckoutCommand(
            actor=actor,
            key=ReservationKey.of(reservation_id),
            hand_overs=hand_overs,
            agreement_signed=True,
        )
    )


def stored(engine: Engine, reservation_id: UUID) -> dict[str, object]:
    """Return what is committed of a checkout, read on a connection of its own."""
    with Session(engine) as reader:
        reservation = reader.get(Reservation, reservation_id)
        assert reservation is not None
        rentals = reader.exec(
            select(Rental).where(col(Rental.reservation_id) == reservation_id)
        ).all()
        return {
            "reservation_status": reservation.status,
            "rentals": len(rentals),
            "items": len(reader.exec(select(RentalItem)).all()),
            "charges": len(reader.exec(select(Charge)).all()),
            "unit_statuses": sorted(asset.status.value for asset in reader.exec(select(Asset))),
            "audit_actions": sorted(
                event.action
                for event in reader.exec(select(AuditEvent))
                if event.action.startswith(CHECKOUT_ACTIONS)
            ),
        }


__all__ = [
    "HOUR_METER_OUT",
    "confirm_for_today",
    "held_allocations",
    "run_checkout",
    "stored",
]
