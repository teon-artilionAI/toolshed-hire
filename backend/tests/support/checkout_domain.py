"""Builders for the tests of a checkout in the domain, with no database anywhere.

A confirmed reservation is built by hand with its allocations in place, the
way a repository would hand it back, and priced with the standard policy. The
units it holds are built to match, and so is what the counter records for each
of them. `checked_out` runs the checkout of the domain on its first day.

The hire is the worked example of the reservation tests, two rotary hammers
and one concrete mixer from the ninth to the twelfth of March 2026, which is
three chargeable days.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid4

from app.domain.booking import Reservation
from app.domain.catalogue import Asset
from app.domain.checkout import Checkout, HandOver, check_out
from app.domain.enums import AssetStatus, ConditionGrade, ReservationStatus
from app.domain.policies import StandardPricingPolicy
from tests.support.reservations import (
    CONFIRMED_AT,
    HAMMER,
    MIXER,
    NINTH,
    TWO_LINES,
    LineRequest,
    a_draft,
    an_allocation,
)

NOW: Final[datetime] = datetime(2026, 3, 9, 6, 30, tzinfo=UTC)
RENTAL_REFERENCE: Final[str] = "TSH-H-26-000099"
NAMES: Final[dict[UUID, str]] = {HAMMER.id: HAMMER.name, MIXER.id: MIXER.name}
ASSISTANT: Final[UUID] = uuid4()
NO_DISCOUNT: Final[Decimal] = Decimal("0.00")
HOUR_METER_ON_FILE: Final[int] = 380
ONE_HAMMER: Final[tuple[LineRequest, ...]] = ((HAMMER, 1),)


def a_confirmed(
    lines: tuple[LineRequest, ...] = TWO_LINES, *, discount: Decimal = NO_DISCOUNT
) -> Reservation:
    """Return a priced, confirmed reservation holding every unit it asks for."""
    reservation = a_draft(*lines)
    reservation.price_with(StandardPricingPolicy(), discount)
    hold_every_unit(reservation)
    reservation.confirmed_at = CONFIRMED_AT
    reservation.status = ReservationStatus.CONFIRMED
    return reservation


def hold_every_unit(reservation: Reservation) -> None:
    """Give every line of a reservation an active allocation for each unit it asks for."""
    for line in reservation.lines:
        line.allocations.extend(
            an_allocation(line, branch_id=reservation.branch_id) for _ in range(line.quantity)
        )


def units_of(
    reservation: Reservation, status: AssetStatus = AssetStatus.AVAILABLE
) -> dict[UUID, Asset]:
    """Return a unit for every allocation the reservation holds, by its key."""
    held = [
        (line.product_model_id, allocation.asset_id)
        for line in reservation.lines
        for allocation in line.active_allocations()
    ]
    return {
        asset_id: Asset(
            id=asset_id,
            asset_tag=f"TSH-DR-{number:04d}",
            product_model_id=model_id,
            branch_id=reservation.branch_id,
            status=status,
            condition_grade=ConditionGrade.A,
            hour_meter_reading=HOUR_METER_ON_FILE,
        )
        for number, (model_id, asset_id) in enumerate(held, start=1)
    }


def every_unit(
    reservation: Reservation,
    *,
    condition: ConditionGrade = ConditionGrade.A,
    accessories: str | None = None,
    hour_meter: int | None = None,
) -> list[HandOver]:
    """Return what the counter records for every unit the reservation holds."""
    return [
        HandOver(
            allocation_id=allocation.id,
            condition_out=condition,
            accessories_out=accessories,
            hour_meter_out=hour_meter,
        )
        for line in reservation.lines
        for allocation in line.active_allocations()
    ]


def checked_out(
    reservation: Reservation,
    hand_overs: list[HandOver] | None = None,
    *,
    agreement_signed: bool = True,
    today: date = NINTH,
    units: dict[UUID, Asset] | None = None,
) -> Checkout:
    """Check the reservation out and return what the checkout made."""
    return check_out(
        reservation=reservation,
        hand_overs=hand_overs if hand_overs is not None else every_unit(reservation),
        agreement_signed=agreement_signed,
        reference=RENTAL_REFERENCE,
        model_names=NAMES,
        units=units if units is not None else units_of(reservation),
        checked_out_by=ASSISTANT,
        now=NOW,
        today=today,
    )


__all__ = [
    "ASSISTANT",
    "HOUR_METER_ON_FILE",
    "NO_DISCOUNT",
    "NOW",
    "ONE_HAMMER",
    "RENTAL_REFERENCE",
    "a_confirmed",
    "checked_out",
    "every_unit",
    "hold_every_unit",
    "units_of",
]
