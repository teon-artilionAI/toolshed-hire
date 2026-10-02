"""Builders for the pricing tests.

The worked example is the rotary hammer of the seed data, R280.00 a day and
R1,120.00 a week with a R1,200.00 deposit. Its weekly rate is four days of its
daily rate, so the weekly basis wins from the seventh day.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Final

from app.domain.money import Money
from app.domain.period import BookingPeriod
from app.domain.policies import HireQuote, LineSnapshot, StandardPricingPolicy

START: Final[date] = date(2026, 10, 9)
HAMMER_DEPOSIT: Final[str] = "1200.00"


def rand(amount: str) -> Money:
    """Return an amount of money from text."""
    return Money.create(amount)


def hammer(quantity: int = 1, *, daily: str = "280.00", weekly: str = "1120.00") -> LineSnapshot:
    """Return a snapshot of the rotary hammer, or of another model at other rates."""
    return LineSnapshot(
        daily_rate=rand(daily),
        weekly_rate=rand(weekly),
        deposit=rand(HAMMER_DEPOSIT),
        quantity=quantity,
    )


def hire_of(days: int) -> BookingPeriod:
    """Return a hire of this many chargeable days."""
    return BookingPeriod(START, START + timedelta(days=days))


def priced(days: int, line: LineSnapshot | None = None, discount: str = "0.00") -> HireQuote:
    """Return the standard quote for a hire of this many days."""
    return StandardPricingPolicy().quote(line or hammer(), hire_of(days), Decimal(discount))


__all__ = ["START", "hammer", "hire_of", "priced", "rand"]
