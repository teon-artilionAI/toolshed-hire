"""The money value object, which is BR-22.

Every rand amount that takes part in a calculation is a `Money`. It holds a
`Decimal` and nothing else, and it will not be built from a float or combined
with one. A float cannot hold most rand amounts exactly, so one float anywhere
in a calculation changes the figure a customer is charged, and it does so
without failing.

An amount is kept exact for as long as it is being worked on. It is rounded
once, half up to the cent, at the point a charge is written, and `rounded` is
the only place that rounding happens. Half up is the rule the design document
names, and it is not the default of `Decimal`, which rounds a half to the even
neighbour.

A negative amount is allowed, because a refund and a reversing charge are
amounts like any other.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Final

CURRENCY_CODE: Final[str] = "ZAR"
# The smallest amount a charge is written in.
ONE_CENT: Final[Decimal] = Decimal("0.01")
NOTHING: Final[Decimal] = Decimal("0")
# What a percentage is divided by to become a fraction.
PERCENT_BASE: Final[Decimal] = Decimal("100")


class InvalidMoney(ValueError):
    """Raised when something that is not an exact rand amount is used as money."""


def _refuse_inexact(value: object, purpose: str) -> None:
    """Refuse a float or a boolean wherever an exact number is expected.

    A boolean is refused by name because Python counts it as an integer, and
    an amount multiplied by True is a mistake that would otherwise pass.

    Raises:
        InvalidMoney: If the value is a float or a boolean.

    """
    if isinstance(value, float | bool):
        raise InvalidMoney(
            f"Attempted to use {value!r} ({type(value).__name__}) as {purpose}. Money is "
            "exact, so pass a Decimal, or an int where a whole number is meant."
        )


@dataclass(frozen=True, slots=True)
class Money:
    """An exact amount in rand.

    Attributes:
        amount: The amount, to as many decimals as the calculation produced.

    """

    amount: Decimal

    def __post_init__(self) -> None:
        """Refuse anything that is not a finite Decimal.

        Raises:
            InvalidMoney: If the amount is not a Decimal, or is not a number.

        """
        if not isinstance(self.amount, Decimal):
            raise InvalidMoney(
                f"Attempted to build Money from {self.amount!r} "
                f"({type(self.amount).__name__}). The amount must be a Decimal. "
                "Use Money.create to build one from an int or from text."
            )
        if not self.amount.is_finite():
            raise InvalidMoney(
                f"Attempted to build Money from {self.amount!r}, which is not a finite number."
            )

    @classmethod
    def zero(cls) -> Money:
        """Return no money at all."""
        return cls(NOTHING)

    @classmethod
    def create(cls, amount: Decimal | int | str) -> Money:
        """Build an amount from a Decimal, a whole number or text such as "280.00".

        Raises:
            InvalidMoney: If the amount is a float or a boolean, or is text
                that does not spell a number.

        """
        _refuse_inexact(amount, "an amount of money")
        if isinstance(amount, Decimal):
            return cls(amount)
        try:
            return cls(Decimal(amount))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise InvalidMoney(
                f"Attempted to build Money from {amount!r} ({type(amount).__name__}), "
                "which does not spell an amount."
            ) from error

    @property
    def currency(self) -> str:
        """Return the currency every amount in this system is held in."""
        return CURRENCY_CODE

    def add(self, other: Money) -> Money:
        """Return this amount plus another."""
        return Money(self.amount + _amount_of(other, "add"))

    def subtract(self, other: Money) -> Money:
        """Return this amount less another. The result may be negative."""
        return Money(self.amount - _amount_of(other, "subtract"))

    def times(self, factor: int) -> Money:
        """Return this amount a whole number of times, for a quantity or a count of days.

        Raises:
            InvalidMoney: If the factor is not an int.

        """
        _refuse_inexact(factor, "a multiplier")
        if not isinstance(factor, int):
            raise InvalidMoney(
                f"Attempted to multiply Money by {factor!r} ({type(factor).__name__}). "
                "An amount is multiplied by a whole number. Use percent_of for a rate."
            )
        return Money(self.amount * factor)

    def percent_of(self, rate: Decimal | int) -> Money:
        """Return `rate` percent of this amount, unrounded.

        Args:
            rate: The percentage, for example 15 for fifteen percent.

        Raises:
            InvalidMoney: If the rate is not a finite Decimal or an int.

        """
        _refuse_inexact(rate, "a percentage")
        if not isinstance(rate, Decimal | int):
            raise InvalidMoney(
                f"Attempted to take {rate!r} ({type(rate).__name__}) percent of Money. "
                "A percentage is a Decimal or an int."
            )
        percentage = Decimal(rate)
        if not percentage.is_finite():
            raise InvalidMoney(
                f"Attempted to take {rate!r} percent of Money, which is not a finite number."
            )
        return Money(self.amount * percentage / PERCENT_BASE)

    def rounded(self) -> Money:
        """Return the amount as a charge is written, half up to the cent."""
        return Money(self.amount.quantize(ONE_CENT, rounding=ROUND_HALF_UP))

    def is_negative(self) -> bool:
        """Return True when the amount is below zero, as a refund is."""
        return self.amount < NOTHING

    def __lt__(self, other: Money) -> bool:
        """Return True when this amount is smaller than the other."""
        return self.amount < _amount_of(other, "compare")

    def __le__(self, other: Money) -> bool:
        """Return True when this amount is not larger than the other."""
        return self.amount <= _amount_of(other, "compare")

    def __gt__(self, other: Money) -> bool:
        """Return True when this amount is larger than the other."""
        return self.amount > _amount_of(other, "compare")

    def __ge__(self, other: Money) -> bool:
        """Return True when this amount is not smaller than the other."""
        return self.amount >= _amount_of(other, "compare")


def _amount_of(other: object, operation: str) -> Decimal:
    """Return the amount of another Money, refusing anything that is not one.

    Raises:
        InvalidMoney: If `other` is not Money. A float, an int and a bare
            Decimal are all refused, so two amounts are only ever combined
            when both were built as money.

    """
    if not isinstance(other, Money):
        raise InvalidMoney(
            f"Attempted to {operation} Money and {other!r} ({type(other).__name__}). "
            "Money is only combined or compared with Money."
        )
    return other.amount
