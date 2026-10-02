"""The totals of a reservation, which are the quotes of its lines added up.

A reservation can carry several lines. The pricing policy prices each one, and
this module adds those answers together, so the figures stored on a
reservation are still the output of the policy and of nothing else (BR-21).

Every amount that goes in is already rounded to the cent, because a quote is
written the way a charge is (BR-22). Adding rounded amounts is exact, so the
subtotal and the VAT of a reservation always add up to its total.

The subtotal is the amount the hire is charged at, which is what is left once
the trade discount has come off. The deposit carries no VAT (BR-23) and is not
part of the total. It is held and given back, so it is shown beside the total
and never inside it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.money import Money
from app.domain.policies.pricing import HireQuote


@dataclass(frozen=True, slots=True)
class HireTotals:
    """What a whole reservation is expected to cost.

    Attributes:
        subtotal_ex_vat: The hire of every line after the discount, excluding VAT.
        vat_amount: The VAT on that subtotal.
        estimated_total_inc_vat: The subtotal and the VAT together.
        deposit_total: The deposit held across every unit of every line.

    """

    subtotal_ex_vat: Money
    vat_amount: Money
    estimated_total_inc_vat: Money
    deposit_total: Money


def totals_of(quotes: Sequence[HireQuote]) -> HireTotals:
    """Add the quotes of the lines of one reservation together.

    Args:
        quotes: One quote for each line, as the pricing policy returned it.

    Returns:
        The totals. All four are zero for a reservation with no lines.

    """
    subtotal = Money.zero()
    vat = Money.zero()
    total = Money.zero()
    deposit = Money.zero()
    for quote in quotes:
        subtotal = subtotal.add(quote.amount_ex_vat)
        vat = vat.add(quote.vat_amount)
        total = total.add(quote.total_inc_vat)
        deposit = deposit.add(quote.deposit_total)
    return HireTotals(
        subtotal_ex_vat=subtotal,
        vat_amount=vat,
        estimated_total_inc_vat=total,
        deposit_total=deposit,
    )
