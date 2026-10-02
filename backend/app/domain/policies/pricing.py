"""The pricing policy port, and what a policy is asked with and answers.

BR-21 says a hire price is produced by a pricing policy and not by arithmetic
scattered through the system. `PricingPolicy` is that policy as a port. The
design document names the pattern, which is Strategy, so the rule can be
swapped without touching what calls it.

A policy works from a `LineSnapshot`, which is the rates as they were copied
onto a line (BR-20), and a `BookingPeriod`. It does not know a catalogue
exists, so a price worked out from a snapshot cannot move when the catalogue
does. The trade discount is handed in as well. The policy never looks one up.

A policy decides one thing, which is what one unit costs for the period.
`quote_for_unit_charge` turns that into the amounts a charge is written with,
and every policy ends by calling it, so the quantity, the discount, the VAT
and the rounding are done one way.

Nothing is rounded while it is being worked out (BR-22). The amount after the
discount and the VAT on it are each rounded once, half up, from the exact
figure. Those are the two amounts a hire charge is written with. The total is
their sum and the discount shown is the subtotal less the amount charged, so
the figures on a quote always add up to the cent.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Final, Protocol

from app.domain.money import Money
from app.domain.period import BookingPeriod
from app.domain.vat import VAT_RATE_PERCENT, vat_on

MINIMUM_LINE_QUANTITY: Final[int] = 1
NO_DISCOUNT_PERCENT: Final[Decimal] = Decimal("0.00")
FULL_DISCOUNT_PERCENT: Final[Decimal] = Decimal("100.00")


class InvalidPricingInput(ValueError):
    """Raised when a policy is asked to price something that cannot be priced."""


class PricingBasis(str, Enum):
    """Which of the two totals BR-21 compares was the one charged."""

    WEEKLY = "WEEKLY"
    DAILY = "DAILY"


@dataclass(frozen=True, slots=True)
class LineSnapshot:
    """The figures of one line as they stood when they were copied (BR-20).

    Attributes:
        daily_rate: The rate for one day, excluding VAT.
        weekly_rate: The rate for each complete seven days, excluding VAT.
        deposit: The deposit held for one unit. It carries no VAT.
        quantity: How many units the line hires.

    """

    daily_rate: Money
    weekly_rate: Money
    deposit: Money
    quantity: int

    def __post_init__(self) -> None:
        """Refuse a line no booking could carry.

        Raises:
            InvalidPricingInput: If a rate or the deposit is not Money or is
                negative, or the quantity is not a whole number of at least
                one.

        """
        for label, amount in (
            ("daily rate", self.daily_rate),
            ("weekly rate", self.weekly_rate),
            ("deposit", self.deposit),
        ):
            if not isinstance(amount, Money):
                raise InvalidPricingInput(
                    f"Attempted to price a line whose {label} is {amount!r} "
                    f"({type(amount).__name__}). A rate and a deposit are Money."
                )
            if amount.is_negative():
                raise InvalidPricingInput(
                    f"Attempted to price a line whose {label} is {amount.amount}. "
                    "A rate and a deposit are never negative."
                )
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise InvalidPricingInput(
                f"Attempted to price a line with a quantity of {self.quantity!r} "
                f"({type(self.quantity).__name__}). A quantity is a whole number."
            )
        if self.quantity < MINIMUM_LINE_QUANTITY:
            raise InvalidPricingInput(
                f"Attempted to price a line with a quantity of {self.quantity}. "
                f"A line hires at least {MINIMUM_LINE_QUANTITY} unit."
            )


@dataclass(frozen=True, slots=True)
class HireQuote:
    """What a hire costs, with every amount as a charge would be written.

    Every amount here is already rounded to the cent. `subtotal_ex_vat` less
    `discount_amount` is `amount_ex_vat`, and `amount_ex_vat` plus `vat_amount`
    is `total_inc_vat`, exactly.

    Attributes:
        period: The hire period that was priced.
        quantity: How many units.
        daily_rate: The daily rate the price was worked out from.
        weekly_rate: The weekly rate the price was worked out from.
        basis: Which of the two totals was charged for one unit.
        unit_amount_ex_vat: What one unit costs for the period, before any
            discount and excluding VAT.
        subtotal_ex_vat: The unit amount for every unit, before any discount.
        discount_percent: The trade discount that was applied.
        discount_amount: What the discount took off the subtotal.
        amount_ex_vat: The subtotal after the discount, which is the amount
            the hire is charged at, excluding VAT.
        vat_rate_percent: The VAT rate that was applied.
        vat_amount: The VAT on the amount charged.
        total_inc_vat: The hire charge including VAT. The deposit is not in it.
        deposit_per_unit: The deposit held for one unit.
        deposit_total: The deposit held for every unit. It carries no VAT.

    """

    period: BookingPeriod
    quantity: int
    daily_rate: Money
    weekly_rate: Money
    basis: PricingBasis
    unit_amount_ex_vat: Money
    subtotal_ex_vat: Money
    discount_percent: Decimal
    discount_amount: Money
    amount_ex_vat: Money
    vat_rate_percent: Decimal
    vat_amount: Money
    total_inc_vat: Money
    deposit_per_unit: Money
    deposit_total: Money


class PricingPolicy(Protocol):
    """How a hire is priced. The Strategy the design document names for BR-21."""

    def name(self) -> str:
        """Return the name the policy is logged under."""
        ...

    def quote(
        self, line: LineSnapshot, period: BookingPeriod, discount_percent: Decimal
    ) -> HireQuote:
        """Price one line for one period.

        Args:
            line: The rates, the deposit and the quantity, as snapshotted.
            period: The half open hire period.
            discount_percent: The trade discount to apply, from 0 to 100.

        Raises:
            InvalidPricingInput: If the discount is not a percentage.

        """
        ...


def quote_for_unit_charge(
    *,
    line: LineSnapshot,
    period: BookingPeriod,
    basis: PricingBasis,
    unit_charge: Money,
    discount_percent: Decimal,
) -> HireQuote:
    """Turn what one unit costs into the amounts a hire charge is written with.

    Args:
        line: The line being priced.
        period: The period being priced.
        basis: Which total the policy charged for one unit.
        unit_charge: What one unit costs for the period, exact and unrounded.
        discount_percent: The trade discount, from 0 to 100.

    Raises:
        InvalidPricingInput: If the discount is not a Decimal from 0 to 100.

    """
    _ensure_percentage(discount_percent)
    subtotal = unit_charge.times(line.quantity)
    after_discount = subtotal.subtract(subtotal.percent_of(discount_percent))
    amount_ex_vat = after_discount.rounded()
    vat_amount = vat_on(after_discount).rounded()
    subtotal_ex_vat = subtotal.rounded()
    return HireQuote(
        period=period,
        quantity=line.quantity,
        daily_rate=line.daily_rate.rounded(),
        weekly_rate=line.weekly_rate.rounded(),
        basis=basis,
        unit_amount_ex_vat=unit_charge.rounded(),
        subtotal_ex_vat=subtotal_ex_vat,
        discount_percent=discount_percent,
        discount_amount=subtotal_ex_vat.subtract(amount_ex_vat),
        amount_ex_vat=amount_ex_vat,
        vat_rate_percent=VAT_RATE_PERCENT,
        vat_amount=vat_amount,
        total_inc_vat=amount_ex_vat.add(vat_amount),
        deposit_per_unit=line.deposit.rounded(),
        deposit_total=line.deposit.times(line.quantity).rounded(),
    )


def _ensure_percentage(discount_percent: Decimal) -> None:
    """Refuse a discount that is not an exact percentage from 0 to 100.

    Raises:
        InvalidPricingInput: If the discount is a float or any other type
            than Decimal, is not a number, or is outside 0 to 100.

    """
    if not isinstance(discount_percent, Decimal):
        raise InvalidPricingInput(
            f"Attempted to price a hire with a discount of {discount_percent!r} "
            f"({type(discount_percent).__name__}). A discount is a Decimal percentage."
        )
    if not discount_percent.is_finite() or not (
        NO_DISCOUNT_PERCENT <= discount_percent <= FULL_DISCOUNT_PERCENT
    ):
        raise InvalidPricingInput(
            f"Attempted to price a hire with a discount of {discount_percent} percent. "
            f"A discount is between {NO_DISCOUNT_PERCENT} and {FULL_DISCOUNT_PERCENT}."
        )
