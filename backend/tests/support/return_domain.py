"""Builders for the tests of returns, losses and settlement in the domain, with no database.

A hire is put out by the checkout of the domain itself, from a confirmed
reservation built the way a repository would hand it back
(`tests/support/checkout_domain.py`). So the rental, its items, their terms,
its two charges, the reservation and the units are exactly what a checkout
makes, and a return is run against them.

The hire runs from the ninth to the twelfth of March 2026, so the twelfth is
the day it is due back. The worked example's rotary hammer is used, with a
deposit of R1,200.00, a late fee of R120.00 a day and a replacement value of
R6,500.00.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Final
from uuid import UUID

from app.domain.booking import Reservation
from app.domain.business_time import business_instant
from app.domain.catalogue import Asset
from app.domain.enums import ConditionGrade
from app.domain.loss import LossOutcome, record_loss
from app.domain.policies import LateFeePolicy, StandardLateFeePolicy
from app.domain.rental import Rental
from app.domain.returns import ItemReturn, ReturnOutcome, return_items
from tests.support.checkout_domain import ASSISTANT, a_confirmed, checked_out
from tests.support.reservations import HAMMER, TWELFTH, LineRequest

WORKED_HAMMER: Final = replace(HAMMER, late_fee_per_day=Decimal("120.00"))
ONE_UNIT: Final[tuple[LineRequest, ...]] = ((WORKED_HAMMER, 1),)
TWO_UNITS: Final[tuple[LineRequest, ...]] = ((WORKED_HAMMER, 2),)
DUE_BACK_ON: Final[date] = TWELFTH
COUNTER_OPENS_FOR_RETURNS: Final[time] = time(10, 0)
POLICY: Final[StandardLateFeePolicy] = StandardLateFeePolicy()


@dataclass(frozen=True, slots=True)
class Hire:
    """A hire that is out, with everything a return works on.

    Attributes:
        rental: The rental the checkout opened.
        reservation: The reservation, now COLLECTED.
        units: The units, ON_HIRE, by their key.

    """

    rental: Rental
    reservation: Reservation
    units: dict[UUID, Asset]


def a_hire(lines: tuple[LineRequest, ...] = ONE_UNIT) -> Hire:
    """Return a hire of the lines asked for, checked out on its first day."""
    reservation = a_confirmed(lines)
    checkout = checked_out(reservation)
    return Hire(
        rental=checkout.rental,
        reservation=reservation,
        units={unit.id: unit for unit in checkout.units},
    )


def on_day(day: date) -> datetime:
    """Return ten in the morning in Cape Town on a day, when the counter takes units back."""
    return business_instant(day, COUNTER_OPENS_FOR_RETURNS)


def days_after_due(days: int) -> date:
    """Return the day a number of days after the hire was due back."""
    return DUE_BACK_ON + timedelta(days=days)


def back(
    hire: Hire,
    *positions: int,
    condition_in: ConditionGrade = ConditionGrade.A,
    hour_meter_in: int | None = None,
    accessories_in: str | None = None,
    notes: str | None = None,
) -> list[ItemReturn]:
    """Return what the counter records for the items at the positions named, every one if none."""
    chosen = positions or tuple(range(len(hire.rental.items)))
    return [
        ItemReturn(
            rental_item_id=hire.rental.items[position].id,
            condition_in=condition_in,
            hour_meter_in=hour_meter_in,
            accessories_in=accessories_in,
            notes=notes,
        )
        for position in chosen
    ]


def returned(
    hire: Hire,
    day: date,
    returns: list[ItemReturn],
    policy: LateFeePolicy = POLICY,
) -> ReturnOutcome:
    """Take the units named back on a day, through the return of the domain."""
    return return_items(
        rental=hire.rental,
        reservation=hire.reservation,
        returns=returns,
        units=hire.units,
        policy=policy,
        returned_by=ASSISTANT,
        now=on_day(day),
        today=day,
    )


def lost(hire: Hire, day: date, position: int = 0) -> LossOutcome:
    """Record the unit at a position as lost on a day, through the domain."""
    return record_loss(
        rental=hire.rental,
        reservation=hire.reservation,
        rental_item_id=hire.rental.items[position].id,
        units=hire.units,
        policy=POLICY,
        recorded_by=ASSISTANT,
        now=on_day(day),
        today=day,
    )


__all__ = [
    "DUE_BACK_ON",
    "ONE_UNIT",
    "POLICY",
    "TWO_UNITS",
    "WORKED_HAMMER",
    "Hire",
    "a_hire",
    "back",
    "days_after_due",
    "lost",
    "on_day",
    "returned",
]
