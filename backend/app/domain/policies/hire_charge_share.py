"""How a hire charge raised on a whole hire is shared between its units, for the report.

A checkout of more than one unit raises one HIRE charge for the hire as a
whole, and `app/domain/checkout_charges.py` says why it is not split there.
The utilisation report attributes hire revenue to each unit, so that one
charge is shared here and nowhere else.

A unit is weighed by its part of the booking line it was hired on, which is
the line amount divided equally between the units the line books. Its share is
the charge in proportion to its weight among the weights of every unit on the
hire, rounded half up to the cent. The last unit takes whatever the rounding
left, so the shares always add up to the charge to the cent. A reversing
charge is a negative amount and is shared by the same weights, so it nets each
unit's share off exactly.

When every weight is nought, for example a hire booked at no charge, the
charge is shared equally.

It lives among the policies because it scales an amount, and every place an
amount is scaled is kept in this package and in the VAT module.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from app.domain.money import Money

# A unit's part of its line, and the weight of each unit when every weight is nought.
ONE_PART: Final[int] = 1


@dataclass(frozen=True, slots=True)
class UnitOnLine:
    """One unit of a hire, as its share of a hire charge is weighed.

    Attributes:
        line_amount: The amount of the booking line it was hired on, excluding VAT.
        units_on_line: How many units that line books, one or more.

    """

    line_amount: Money
    units_on_line: int


def shares_of_hire_charge(charge: Money, units: Sequence[UnitOnLine]) -> tuple[Money, ...]:
    """Return the share of a hire charge each unit of the hire is given, in the order given.

    Args:
        charge: The charge excluding VAT, negative for a reversal.
        units: Every unit on the hire, in the order the shares are wanted.
            The last one takes the rounding cent.

    Returns:
        One amount for each unit, each to the cent, adding up to the charge.

    Raises:
        ValueError: If no unit is given, because a charge cannot be shared
            between nothing.
        InvalidMoney: If a line books no unit or a line amount is below nought.

    """
    if not units:
        raise ValueError(
            f"Attempted to share a hire charge of {charge.amount} between no units. A hire "
            "charge is shared between the units of its hire, and every hire has one."
        )
    weights = [unit.line_amount.in_proportion(ONE_PART, unit.units_on_line) for unit in units]
    total = Money.zero()
    for weight in weights:
        total = total.add(weight)
    if total == Money.zero():
        weights = [Money.create(ONE_PART) for _ in units]
        total = Money.create(len(units))
    shares: list[Money] = []
    given = Money.zero()
    for weight in weights[:-1]:
        share = charge.in_proportion(weight.amount, total.amount).rounded()
        shares.append(share)
        given = given.add(share)
    shares.append(charge.subtract(given).rounded())
    return tuple(shares)
