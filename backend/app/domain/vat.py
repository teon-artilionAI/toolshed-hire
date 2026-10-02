"""Value added tax, which is BR-23.

The rate is written once, here, as a `Decimal`. Hire rates in the catalogue
exclude VAT and it is charged on top of them. A deposit carries none, because
a deposit that is held and returned is not a supply.

`vat_on` returns the exact figure. Like every other amount it is rounded once,
when the charge is written.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from app.domain.money import Money

# The standard rate in force in South Africa, as a percentage.
VAT_RATE_PERCENT: Final[Decimal] = Decimal("15.00")


def vat_on(amount_ex_vat: Money) -> Money:
    """Return the VAT charged on an amount that excludes it, unrounded."""
    return amount_ex_vat.percent_of(VAT_RATE_PERCENT)
