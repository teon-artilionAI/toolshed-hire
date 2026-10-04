"""Helpers for the tests that run the admin operations against PostgreSQL itself.

The corrections, the force release and the reallocation are run through their
use cases, each on a unit of work of its own, the way a request wires them,
and through whichever unit of work a test hands in, so a test can make one
fail at the audit write. What a test reads back is read on a connection of its
own, as raw rows where a row has to be compared column for column, so what it
sees is what the database kept and not what a session remembers.

The world, the counter assistant and the administrator the suites act as are
committed here too, so each test module keeps only thin fixtures. The rows of
the two logs are written by tests/support/admin_log_pg.py, and the units and
rival bookings of a reallocation by tests/support/allocation_pg.py.

Importing this module opens no connection.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Final
from uuid import UUID

from sqlalchemy import Engine, select
from sqlmodel import Session, SQLModel, col
from sqlmodel import select as select_rows

from app.application.booking.access import ReservationCommand
from app.application.booking.expire_holds import ExpireHoldsAndNoShowsUseCase
from app.application.booking.force_release import ForceReleaseCommand, ForceReleaseUseCase
from app.application.booking.read_models import ReservationKey
from app.application.booking.reallocate import ReallocateUseCase
from app.application.booking.views import ReservationView
from app.application.hire.balance_payment import (
    BalancePaymentCommand,
    RecordBalancePaymentUseCase,
)
from app.application.hire.charge_corrections import (
    AdjustmentCommand,
    AdjustRentalUseCase,
    ChargeCorrectionCommand,
    ReverseChargeUseCase,
    WaiveChargeUseCase,
)
from app.application.hire.read_models import RentalKey
from app.application.hire.views import RentalView
from app.application.unit_of_work import UnitOfWork
from app.domain.enums import ChargeStatus, ChargeType, RentalStatus, UserRole
from app.domain.identity import Actor
from app.domain.money import Money
from app.domain.policies import StandardLateFeePolicy
from app.infrastructure.models import AuditEvent, Charge, Rental
from tests.support.booking import opening
from tests.support.booking_api import BookingWorld, build_booking_world
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.return_pg import clock_on, item_keys, run_return

REASON: Final[str] = "The customer was told on the phone it would not be charged."
# Two days after the fifth, the day the hires of these suites are due back.
TWO_DAYS_LATE: Final[date] = date(2026, 3, 7)

type UnitOfWorkFactory = Callable[[], UnitOfWork]


def admin_of(account_id: UUID) -> Actor:
    """Return an administrator, by the key of its account, as the actor of an operation."""
    return Actor(user_id=account_id, role=UserRole.ADMIN)


def run_waiver(
    engine: Engine,
    actor: Actor,
    charge_id: UUID,
    day: date,
    unit_of_work: UnitOfWorkFactory | None = None,
) -> RentalView:
    """Waive a charge on a day, through the unit of work asked for."""
    build = unit_of_work or opening(engine)
    return WaiveChargeUseCase(build(), clock_on(day), StandardLateFeePolicy()).execute(
        ChargeCorrectionCommand(actor=actor, charge_id=charge_id, reason=REASON)
    )


def run_reversal(
    engine: Engine,
    actor: Actor,
    charge_id: UUID,
    day: date,
    unit_of_work: UnitOfWorkFactory | None = None,
) -> RentalView:
    """Reverse a charge on a day, through the unit of work asked for."""
    build = unit_of_work or opening(engine)
    return ReverseChargeUseCase(build(), clock_on(day), StandardLateFeePolicy()).execute(
        ChargeCorrectionCommand(actor=actor, charge_id=charge_id, reason=REASON)
    )


def run_adjustment(
    engine: Engine,
    actor: Actor,
    rental_id: UUID,
    amount: str,
    day: date,
    unit_of_work: UnitOfWorkFactory | None = None,
) -> RentalView:
    """Adjust a rental by an amount that includes VAT on a day, through the unit of work given."""
    build = unit_of_work or opening(engine)
    return AdjustRentalUseCase(build(), clock_on(day), StandardLateFeePolicy()).execute(
        AdjustmentCommand(
            actor=actor,
            key=RentalKey.of(rental_id),
            amount_inc_vat=Money.create(amount),
            reason=REASON,
        )
    )


def run_balance_payment(
    engine: Engine, staff: Actor, rental_id: UUID, reference: str, day: date
) -> RentalView:
    """Record the payment of a rental's balance on a day."""
    return RecordBalancePaymentUseCase(
        opening(engine)(), clock_on(day), StandardLateFeePolicy()
    ).execute(
        BalancePaymentCommand(
            actor=staff, key=RentalKey.of(rental_id), payment_reference=reference
        )
    )


def run_release(
    engine: Engine,
    actor: Actor,
    allocation_id: UUID,
    unit_of_work: UnitOfWorkFactory | None = None,
) -> ReservationView:
    """Release one allocation by hand, on the still clock, through the unit of work asked for."""
    build = unit_of_work or opening(engine)
    return ForceReleaseUseCase(build(), FixedClock()).execute(
        ForceReleaseCommand(actor=actor, allocation_id=allocation_id, reason=REASON)
    )


def run_reallocation(
    engine: Engine,
    actor: Actor,
    reservation_id: UUID,
    unit_of_work: UnitOfWorkFactory | None = None,
) -> ReservationView:
    """Give a reservation replacement units on the still clock, through the unit of work given."""
    build = unit_of_work or opening(engine)
    clock = FixedClock()
    sweep = ExpireHoldsAndNoShowsUseCase(opening(engine)(), clock)
    return ReallocateUseCase(build(), clock, sweep).execute(
        ReservationCommand(actor=actor, key=ReservationKey.of(reservation_id))
    )


def row_of(engine: Engine, model: type[SQLModel], key: UUID) -> dict[str, object]:
    """Return every column of one row of a table, read on a connection of its own."""
    table = model.__table__
    with engine.connect() as connection:
        found = connection.execute(select(table).where(table.c.id == key)).mappings().one()
    return dict(found)


def charge_rows(engine: Engine, rental_id: UUID) -> list[dict[str, object]]:
    """Return every charge of a rental as stored, in the order they were raised."""
    table = Charge.__table__
    with engine.connect() as connection:
        found = connection.execute(
            select(table)
            .where(table.c.rental_id == rental_id)
            .order_by(table.c.raised_at, table.c.payment_reference.nulls_last(), table.c.id)
        ).mappings().all()
    return [dict(row) for row in found]


def audit_trail(engine: Engine, prefix: str) -> list[AuditEvent]:
    """Return the audit events whose action starts with a prefix, oldest first."""
    with Session(engine) as reader:
        return [
            event
            for event in reader.exec(select_rows(AuditEvent).order_by(col(AuditEvent.id)))
            if event.action.startswith(prefix)
        ]


def committed_world(session: Session, factory: Factory, units: int) -> BookingWorld:
    """Commit a branch holding a number of units of the factory's model, and its customer."""
    built = build_booking_world(factory, asset_count=units)
    session.commit()
    return built


def counter_assistant(session: Session, factory: Factory, world: BookingWorld) -> Actor:
    """Commit a counter assistant of the world's branch and return it as an actor."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return Actor(user_id=account.id, role=UserRole.COUNTER_STAFF, branch_id=world.branch.id)


def committed_administrator(session: Session, factory: Factory) -> Actor:
    """Commit an administrator and return it as an actor."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return admin_of(account.id)


def rows_of_type(
    engine: Engine, rental_id: UUID, charge_type: ChargeType
) -> list[dict[str, object]]:
    """Return the charges of one type on a rental as stored, in the order they were raised."""
    return [row for row in charge_rows(engine, rental_id) if row["charge_type"] == charge_type]


def late_fees(engine: Engine, rental_id: UUID) -> list[dict[str, object]]:
    """Return the late fees of a rental as stored, in the order they were raised."""
    return rows_of_type(engine, rental_id, ChargeType.LATE_FEE)


def one_back_late(engine: Engine, assistant: Actor, rental_id: UUID) -> UUID:
    """Take the first unit of a rental back two days late, and return its pending late fee."""
    first = item_keys(engine, rental_id)[0]
    run_return(engine, assistant, rental_id, TWO_DAYS_LATE, items=[first])
    (fee,) = late_fees(engine, rental_id)
    assert fee["status"] is ChargeStatus.PENDING
    return UUID(str(fee["id"]))


def all_back_late(engine: Engine, assistant: Actor, rental_id: UUID) -> None:
    """Take every unit of a rental back two days late, which settles the hire."""
    run_return(engine, assistant, rental_id, TWO_DAYS_LATE)
    assert row_of(engine, Rental, rental_id)["status"] is RentalStatus.SETTLED


__all__ = [
    "REASON",
    "TWO_DAYS_LATE",
    "all_back_late",
    "admin_of",
    "audit_trail",
    "charge_rows",
    "committed_administrator",
    "committed_world",
    "counter_assistant",
    "late_fees",
    "one_back_late",
    "rows_of_type",
    "row_of",
    "run_adjustment",
    "run_balance_payment",
    "run_reallocation",
    "run_release",
    "run_reversal",
    "run_waiver",
]
