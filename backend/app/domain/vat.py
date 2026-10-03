"""Value added tax, which is BR-23.

The rate is written once, here, as a `Decimal`. Hire rates in the catalogue
exclude VAT and it is charged on top of them. A deposit carries none, because
a deposit that is held and returned is not a supply.

`vat_on` returns the exact figure. Like every other amount it is rounded once,
when the charge is written.

Some amounts are quoted with the VAT already in them. A late fee is one, so
two days at R120.00 is R240.00 and not R240.00 plus VAT. `split_vat_inclusive`
is the one place such an amount is taken apart. The part before VAT is worked
back from the quoted amount and rounded half up to the cent, and the VAT is
whatever is left, so the two always add back to exactly the amount quoted.
R240.00 is written as R208.70 plus R31.30 VAT.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from app.domain.money import Money

# The standard rate in force in South Africa, as a percentage.
VAT_RATE_PERCENT: Final[Decimal] = Decimal("15.00")


def vat_on(amount_ex_vat: Money) -> Money:
    """Return the VAT charged on an amount that excludes it, unrounded."""
    return amount_ex_vat.percent_of(VAT_RATE_PERCENT)


@dataclass(frozen=True, slots=True)
class VatInclusiveSplit:
    """An amount that includes VAT, taken apart into the two figures a charge is written with.

    Both figures are rounded to the cent, and they add up to the amount that
    was quoted, exactly.

    Attributes:
        amount_ex_vat: The part before VAT.
        vat_amount: The VAT in the amount.
        vat_rate: The rate the VAT was worked out at.

    """

    amount_ex_vat: Money
    vat_amount: Money
    vat_rate: Decimal = VAT_RATE_PERCENT

    @property
    def amount_inc_vat(self) -> Money:
        """Return the amount as it was quoted, VAT included."""
        return self.amount_ex_vat.add(self.vat_amount)


def split_vat_inclusive(amount_inc_vat: Money) -> VatInclusiveSplit:
    """Take an amount that includes VAT apart into the part before VAT and the VAT.

    Args:
        amount_inc_vat: The amount as quoted, VAT included. It is rounded to
            the cent first, because it is the figure the customer is charged.

    Returns:
        The two figures. The part before VAT is rounded half up and the VAT is
        the rest, so nothing is lost or invented by the rounding.

    """
    inclusive = amount_inc_vat.rounded()
    before_vat = inclusive.before_percent_added(VAT_RATE_PERCENT).rounded()
    return VatInclusiveSplit(amount_ex_vat=before_vat, vat_amount=inclusive.subtract(before_vat))
