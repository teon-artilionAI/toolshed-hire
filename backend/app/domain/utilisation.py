"""Utilisation as a percentage, which is the first of the report's two definitions.

Utilisation, per asset, for a period, is the days the asset was on an active
allocation within the period divided by the days it was in the fleet and
serviceable within the period. A group of units is measured the same way, the
days on hire of all of them over the serviceable days of all of them, so a
unit that could be hired for a day does not weigh as much as one that could
be hired all month.

The figure is a percentage to two decimals, rounded half up, the rule money
is rounded by. A unit that could not be hired on any day of the period has no
utilisation at all, which is None and not nought, because nought would say it
stood idle when it was never there to hire. This module is the one place the
percentage is worked out.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Final

PERCENT: Final[Decimal] = Decimal("100")
TWO_DECIMALS: Final[Decimal] = Decimal("0.01")
NO_DAYS: Final[int] = 0


def utilisation_percent(days_on_hire: int, serviceable_days: int) -> Decimal | None:
    """Return the days on hire as a percentage of the serviceable days, or None for none.

    Args:
        days_on_hire: The days on hire, nought or more.
        serviceable_days: The days the unit or the group could be hired, nought or more.

    Raises:
        ValueError: If either count is below nought, which no period can produce.

    """
    if days_on_hire < NO_DAYS or serviceable_days < NO_DAYS:
        raise ValueError(
            f"Attempted to work out utilisation from {days_on_hire} days on hire and "
            f"{serviceable_days} serviceable days. Neither can be below nought."
        )
    if serviceable_days == NO_DAYS:
        return None
    exact = Decimal(days_on_hire) * PERCENT / Decimal(serviceable_days)
    return exact.quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)
