"""A pricing policy for tests, which charges the same amount whatever is hired.

A test of a booking wants a price it can state in one line, without working
through the weekly rule to find it. This policy charges a fixed amount for one
unit, for any period and whatever rates the line carries. The quantity, the
discount and the VAT are then applied exactly as the standard policy applies
them, because both policies end in the same function.

It never looks at a weekly rate, so it reports the daily basis.

It lives beside the standard policy because the design document places it
there. Nothing in the running application builds one.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from app.domain.money import Money
from app.domain.period import BookingPeriod
from app.domain.policies.pricing import (
    HireQuote,
    InvalidPricingInput,
    LineSnapshot,
    PricingBasis,
    quote_for_unit_charge,
)

FIXED_RATE_POLICY_NAME: Final[str] = "fixed-rate"


class FixedRatePricingPolicy:
    """One fixed amount for one unit, for any period."""

    def __init__(self, fixed: Money) -> None:
        """Keep the amount one unit is charged.

        Args:
            fixed: What one unit costs for any period, excluding VAT.

        Raises:
            InvalidPricingInput: If the amount is not Money, or is negative.

        """
        if not isinstance(fixed, Money) or fixed.is_negative():
            raise InvalidPricingInput(
                f"Attempted to build a fixed rate policy charging {fixed!r}. "
                "A hire charge is Money and is never negative."
            )
        self._fixed = fixed

    def name(self) -> str:
        """Return the name the policy is logged under."""
        return FIXED_RATE_POLICY_NAME

    def quote(
        self, line: LineSnapshot, period: BookingPeriod, discount_percent: Decimal
    ) -> HireQuote:
        """Price one line at the fixed amount for each unit.

        Raises:
            InvalidPricingInput: If the discount is not a percentage.

        """
        return quote_for_unit_charge(
            line=line,
            period=period,
            basis=PricingBasis.DAILY,
            unit_charge=self._fixed,
            discount_percent=discount_percent,
        )
