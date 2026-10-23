"""The trade discount a customer may carry (BR-21).

A discount is a percentage of the hire subtotal, given to a trade customer and
copied onto each booking line when the booking is made. It is a display and
pricing input, not money, so it is stored as two decimal places and must stay
below 100. A value with more than two decimals is refused rather than rounded,
because rounding somebody's price without telling them is worse than asking
for the value again.

The rule lives here so the use case, the API and a future import all refuse
the same values. The field name is the one the request uses.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Final

from app.domain.customer_account import REFUSED_FIELD
from app.domain.errors import ValidationFailure

TRADE_DISCOUNT_FIELD: Final[str] = "tradeDiscountPercent"
ZERO: Final[Decimal] = Decimal("0")
ONE_HUNDRED: Final[Decimal] = Decimal("100")
TWO_PLACES: Final[Decimal] = Decimal("0.01")
RANGE_MESSAGE: Final[str] = "Enter a trade discount from 0 up to but below 100."
PLACES_MESSAGE: Final[str] = "Use at most two decimal places for the trade discount."
TRADE_ONLY_MESSAGE: Final[str] = "A trade discount can only be set on a trade account."


def checked_trade_discount(value: Decimal) -> Decimal:
    """Return the discount at two decimal places, or refuse it.

    Raises:
        ValidationFailure: Naming `tradeDiscountPercent` when the value is out
            of range or carries more than two decimals.

    """
    if not value.is_finite() or value < ZERO or value >= ONE_HUNDRED:
        raise ValidationFailure(RANGE_MESSAGE, {REFUSED_FIELD: TRADE_DISCOUNT_FIELD})
    try:
        placed = value.quantize(TWO_PLACES)
    except InvalidOperation as error:
        raise ValidationFailure(PLACES_MESSAGE, {REFUSED_FIELD: TRADE_DISCOUNT_FIELD}) from error
    if placed != value:
        raise ValidationFailure(PLACES_MESSAGE, {REFUSED_FIELD: TRADE_DISCOUNT_FIELD})
    return placed
