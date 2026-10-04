"""The standard pricing policy, which is the rule of BR-21.

One unit over a hire period is charged the lower of two totals. The first
charges each complete week at the weekly rate and the days left over at the
daily rate. The second charges every day at the daily rate. A hire shorter
than a week has no complete week, so the two totals are the same figure.

This class is the only place in the system that multiplies a rate by a number
of days. A test reads the source of every other module to keep it that way.
So the catalogue asks it what seven days at a daily rate come to, when it
holds a weekly rate to the most the policy could ever charge for a week.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from app.domain.money import Money
from app.domain.period import DAYS_IN_A_WEEK, BookingPeriod
from app.domain.policies.pricing import (
    HireQuote,
    LineSnapshot,
    PricingBasis,
    quote_for_unit_charge,
)

STANDARD_POLICY_NAME: Final[str] = "standard"


class StandardPricingPolicy:
    """Weeks at the weekly rate and the rest at the daily rate, when that is cheaper."""

    # The number of days one weekly rate pays for. It is the week a
    # `BookingPeriod` counts in, so the two cannot disagree.
    WEEK_LENGTH_DAYS: Final[int] = DAYS_IN_A_WEEK

    def name(self) -> str:
        """Return the name the policy is logged under."""
        return STANDARD_POLICY_NAME

    @classmethod
    def week_at_the_daily_rate(cls, daily_rate: Money) -> Money:
        """Return one week charged day by day, the most a weekly rate is ever worth.

        The policy charges the lower of the two totals, so a weekly rate above
        this figure would never be charged (BR-21).
        """
        return daily_rate.times(cls.WEEK_LENGTH_DAYS)

    def quote(
        self, line: LineSnapshot, period: BookingPeriod, discount_percent: Decimal
    ) -> HireQuote:
        """Price one line for one period by the rule of BR-21.

        Args:
            line: The rates, the deposit and the quantity, as snapshotted.
            period: The half open hire period.
            discount_percent: The trade discount to apply, from 0 to 100.

        Returns:
            The quote. Its basis is `WEEKLY` when the weeks and the days left
            over came to less than every day at the daily rate, and `DAILY`
            when the daily total was lower or the same.

        Raises:
            InvalidPricingInput: If the discount is not a percentage.

        """
        by_the_week = self._weekly_component(period, line.weekly_rate).add(
            self._daily_component(period, line.daily_rate)
        )
        by_the_day = line.daily_rate.times(period.days)
        if by_the_day <= by_the_week:
            basis, unit_charge = PricingBasis.DAILY, by_the_day
        else:
            basis, unit_charge = PricingBasis.WEEKLY, by_the_week
        return quote_for_unit_charge(
            line=line,
            period=period,
            basis=basis,
            unit_charge=unit_charge,
            discount_percent=discount_percent,
        )

    def _weekly_component(self, period: BookingPeriod, weekly_rate: Money) -> Money:
        """Return the charge for the complete weeks of the period."""
        return weekly_rate.times(period.whole_weeks)

    def _daily_component(self, period: BookingPeriod, daily_rate: Money) -> Money:
        """Return the charge for the days left over after the complete weeks."""
        return daily_rate.times(period.remainder_days)
