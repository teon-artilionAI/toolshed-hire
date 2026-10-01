"""The fixed figures of the one closed hire the seed carries.

This is the worked example from the design document. Reservation
TSH-R-26-000123 puts one Bosch GBH 2-26 out from the Cape Town CBD branch for
four days, the unit comes back two days late, and the late fee is taken out of
the deposit before the rest is released.

Nothing here touches a database. The amounts are worked out from the rates of
the product model and then compared with the figures the document states, so a
later change to a rate in the seed data stops the load with an explanation
instead of quietly seeding a different example.

Three rules shape the amounts. Hire rates exclude VAT, so VAT is added on top.
A late fee is quoted including VAT, so the VAT is taken out of it. A deposit
movement carries no VAT at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from app.domain.enums import ChargeType
from seeding.errors import SeedDataError

RESERVATION_REFERENCE: Final[str] = "TSH-R-26-000123"
RENTAL_REFERENCE: Final[str] = "TSH-H-26-000098"
BRANCH_CODE: Final[str] = "CBD"
MODEL_SKU: Final[str] = "DR-BOSCH-GBH226"
ASSET_TAG: Final[str] = "TSH-DR-0042"
QUANTITY: Final[int] = 1
FIRST_LINE_POSITION: Final[int] = 1
# The hire, the deposit taken, the late fee and the deposit given back.
CHARGE_COUNT: Final[int] = 4

HIRE_START: Final[date] = date(2026, 3, 6)
# Exclusive. The day the unit was due back.
HIRE_END: Final[date] = date(2026, 3, 10)
RETURNED_ON: Final[date] = date(2026, 3, 12)

# South Africa keeps one offset all year, so a fixed offset is exact and the
# load needs no time zone database on the machine it runs on.
SOUTH_AFRICA_STANDARD_TIME: Final[timezone] = timezone(timedelta(hours=2), "SAST")
BOOKED_AT: Final[datetime] = datetime(2026, 3, 2, 9, 14, tzinfo=SOUTH_AFRICA_STANDARD_TIME)
CHECKED_OUT_AT: Final[datetime] = datetime(2026, 3, 6, 8, 22, tzinfo=SOUTH_AFRICA_STANDARD_TIME)
RETURNED_AT: Final[datetime] = datetime(2026, 3, 12, 9, 40, tzinfo=SOUTH_AFRICA_STANDARD_TIME)

HOUR_METER_OUT: Final[int] = 401
HOUR_METER_IN: Final[int] = 412

VAT_RATE_PERCENT: Final[Decimal] = Decimal("15.00")
NO_VAT: Final[Decimal] = Decimal("0.00")
NOTHING: Final[Decimal] = Decimal("0.00")
CENT: Final[Decimal] = Decimal("0.01")
ONE_HUNDRED: Final[Decimal] = Decimal("100")

# What the design document states. The computed figures have to equal these.
EXPECTED_HIRE_DAYS: Final[int] = 4
EXPECTED_DAYS_LATE: Final[int] = 2
EXPECTED_DEPOSIT_HELD: Final[Decimal] = Decimal("1200.00")
EXPECTED_DEPOSIT_WITHHELD: Final[Decimal] = Decimal("240.00")
EXPECTED_DEPOSIT_REFUNDED: Final[Decimal] = Decimal("960.00")
EXPECTED_BALANCE_DUE: Final[Decimal] = Decimal("0.00")
EXPECTED_LATE_FEE_EX_VAT: Final[Decimal] = Decimal("208.70")
EXPECTED_LATE_FEE_VAT: Final[Decimal] = Decimal("31.30")


@dataclass(frozen=True, slots=True)
class ChargeFigures:
    """One money line of the worked example, ready to be written as a charge.

    `attributable_to_item` is True when the line belongs to the one unit on
    hire and False when it belongs to the hire as a whole, which is how the
    deposit movements are kept.
    """

    charge_type: ChargeType
    description: str
    amount_ex_vat: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    amount_inc_vat: Decimal
    raised_at: datetime
    attributable_to_item: bool


@dataclass(frozen=True, slots=True)
class WorkedExampleFigures:
    """Every amount of the worked example, computed from the model's rates."""

    hire_days: int
    days_late: int
    subtotal_ex_vat: Decimal
    vat_amount: Decimal
    total_inc_vat: Decimal
    deposit_held: Decimal
    deposit_withheld: Decimal
    deposit_refunded: Decimal
    balance_due: Decimal
    charges: tuple[ChargeFigures, ...]


def vat_on(amount_ex_vat: Decimal) -> Decimal:
    """Return the VAT to add to an amount that excludes it, rounded to the cent."""
    return (amount_ex_vat * VAT_RATE_PERCENT / ONE_HUNDRED).quantize(CENT, ROUND_HALF_UP)


def split_vat_inclusive(amount_inc_vat: Decimal) -> tuple[Decimal, Decimal]:
    """Split an amount that includes VAT into the part before VAT and the VAT.

    The part before VAT is rounded to the cent and the VAT is whatever is left,
    so the two always add back to the amount that was charged.
    """
    amount_ex_vat = (amount_inc_vat * ONE_HUNDRED / (ONE_HUNDRED + VAT_RATE_PERCENT)).quantize(
        CENT, ROUND_HALF_UP
    )
    return amount_ex_vat, amount_inc_vat - amount_ex_vat


def compute_figures(
    *, model_name: str, daily_rate: Decimal, deposit_amount: Decimal, late_fee_per_day: Decimal
) -> WorkedExampleFigures:
    """Work out the worked example from one product model's rates.

    Args:
        model_name: The display name of the model, used in the hire description.
        daily_rate: The daily hire rate, excluding VAT.
        deposit_amount: The deposit taken per unit.
        late_fee_per_day: The late fee per unit per day, including VAT.

    Returns:
        The totals and the four charges, in the order they were raised.

    Raises:
        SeedDataError: If the result is not the worked example the design
            document states, which means a rate in the seed data has changed.

    """
    hire_days = (HIRE_END - HIRE_START).days
    days_late = (RETURNED_ON - HIRE_END).days

    subtotal_ex_vat = daily_rate * hire_days * QUANTITY
    hire_vat = vat_on(subtotal_ex_vat)
    deposit_held = deposit_amount * QUANTITY
    late_fee_inc_vat = late_fee_per_day * days_late * QUANTITY
    late_fee_ex_vat, late_fee_vat = split_vat_inclusive(late_fee_inc_vat)
    # The late fee comes out of the deposit first. Only what the deposit cannot
    # cover is left for the customer to pay.
    deposit_withheld = min(late_fee_inc_vat, deposit_held)
    deposit_refunded = deposit_held - deposit_withheld
    balance_due = late_fee_inc_vat - deposit_withheld

    charges = (
        ChargeFigures(
            charge_type=ChargeType.HIRE,
            description=f"{model_name}, {hire_days} days at R{daily_rate} a day",
            amount_ex_vat=subtotal_ex_vat,
            vat_rate=VAT_RATE_PERCENT,
            vat_amount=hire_vat,
            amount_inc_vat=subtotal_ex_vat + hire_vat,
            raised_at=CHECKED_OUT_AT,
            attributable_to_item=True,
        ),
        ChargeFigures(
            charge_type=ChargeType.DEPOSIT_HOLD,
            description="Refundable deposit held at collection",
            amount_ex_vat=deposit_held,
            vat_rate=NO_VAT,
            vat_amount=NOTHING,
            amount_inc_vat=deposit_held,
            raised_at=CHECKED_OUT_AT,
            attributable_to_item=False,
        ),
        ChargeFigures(
            charge_type=ChargeType.LATE_FEE,
            description=(
                f"{ASSET_TAG} returned {days_late} days late, R{late_fee_per_day} a day "
                "including VAT"
            ),
            amount_ex_vat=late_fee_ex_vat,
            vat_rate=VAT_RATE_PERCENT,
            vat_amount=late_fee_vat,
            amount_inc_vat=late_fee_inc_vat,
            raised_at=RETURNED_AT,
            attributable_to_item=True,
        ),
        ChargeFigures(
            charge_type=ChargeType.DEPOSIT_RELEASE,
            description=f"Deposit released after R{deposit_withheld} was withheld for late fees",
            amount_ex_vat=-deposit_refunded,
            vat_rate=NO_VAT,
            vat_amount=NOTHING,
            amount_inc_vat=-deposit_refunded,
            raised_at=RETURNED_AT,
            attributable_to_item=False,
        ),
    )
    figures = WorkedExampleFigures(
        hire_days=hire_days,
        days_late=days_late,
        subtotal_ex_vat=subtotal_ex_vat,
        vat_amount=hire_vat,
        total_inc_vat=subtotal_ex_vat + hire_vat,
        deposit_held=deposit_held,
        deposit_withheld=deposit_withheld,
        deposit_refunded=deposit_refunded,
        balance_due=balance_due,
        charges=charges,
    )
    _check_against_the_document(figures, late_fee_ex_vat, late_fee_vat)
    return figures


def _check_against_the_document(
    figures: WorkedExampleFigures, late_fee_ex_vat: Decimal, late_fee_vat: Decimal
) -> None:
    """Refuse figures that differ from the ones the design document states."""
    comparisons: tuple[tuple[str, Decimal | int, Decimal | int], ...] = (
        ("hire days", figures.hire_days, EXPECTED_HIRE_DAYS),
        ("days late", figures.days_late, EXPECTED_DAYS_LATE),
        ("deposit held", figures.deposit_held, EXPECTED_DEPOSIT_HELD),
        ("deposit withheld", figures.deposit_withheld, EXPECTED_DEPOSIT_WITHHELD),
        ("deposit refunded", figures.deposit_refunded, EXPECTED_DEPOSIT_REFUNDED),
        ("balance due", figures.balance_due, EXPECTED_BALANCE_DUE),
        ("number of charges", len(figures.charges), CHARGE_COUNT),
        ("late fee before VAT", late_fee_ex_vat, EXPECTED_LATE_FEE_EX_VAT),
        ("late fee VAT", late_fee_vat, EXPECTED_LATE_FEE_VAT),
    )
    differing = [
        f"{label} is {actual}, expected {expected}"
        for label, actual, expected in comparisons
        if actual != expected
    ]
    if differing:
        raise SeedDataError(
            f"The worked example for {RENTAL_REFERENCE} no longer matches the design "
            f"document. {'. '.join(differing)}. The figures come from the rates of product "
            f"model {MODEL_SKU} in the seed data, so check its deposit and its late fee."
        )
