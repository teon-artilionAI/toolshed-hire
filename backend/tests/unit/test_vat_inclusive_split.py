"""An amount quoted with VAT in it, taken apart for a charge, with no database (BR-22, BR-23).

A late fee includes VAT. It is written as the part before VAT, rounded half up
to the cent from the exact figure, and the VAT, which is whatever is left, so
the two always add back to the amount quoted. The worked example's R240.00 is
R208.70 plus R31.30.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.money import InvalidMoney, Money
from app.domain.vat import VAT_RATE_PERCENT, split_vat_inclusive


@pytest.mark.parametrize(
    ("inclusive", "before_vat", "vat"),
    [
        ("240.00", "208.70", "31.30"),
        ("120.00", "104.35", "15.65"),
        ("1680.00", "1460.87", "219.13"),
        ("3000.00", "2608.70", "391.30"),
        ("0.01", "0.01", "0.00"),
        ("0.00", "0.00", "0.00"),
    ],
)
def test_the_split_of_an_inclusive_amount(inclusive: str, before_vat: str, vat: str) -> None:
    split = split_vat_inclusive(Money.create(inclusive))
    assert (split.amount_ex_vat.amount, split.vat_amount.amount) == (
        Decimal(before_vat), Decimal(vat)
    )
    assert split.vat_rate == VAT_RATE_PERCENT
    assert split.amount_inc_vat == Money.create(inclusive)


def test_the_part_before_vat_is_rounded_half_up_and_not_cut_off() -> None:
    # 120.00 less VAT is 104.3478..., which rounds up to 104.35. Cutting the
    # figure off at the cent would give 104.34 and invent a cent of VAT.
    assert split_vat_inclusive(Money.create("120.00")).amount_ex_vat == Money.create("104.35")
    # 10.00 less VAT is 8.6956..., which rounds up, and 1.00 less VAT is
    # 0.8695..., which rounds up too.
    assert split_vat_inclusive(Money.create("10.00")).amount_ex_vat == Money.create("8.70")
    assert split_vat_inclusive(Money.create("1.00")).amount_ex_vat == Money.create("0.87")


def test_the_two_figures_always_add_back_to_the_amount_quoted() -> None:
    for cents in range(0, 100_000, 37):
        inclusive = Money(Decimal(cents) / Decimal(100))
        split = split_vat_inclusive(inclusive)
        assert split.amount_ex_vat.add(split.vat_amount) == inclusive.rounded()
        assert split.amount_ex_vat.amount == split.amount_ex_vat.rounded().amount


def test_an_amount_with_more_than_two_decimals_is_rounded_first() -> None:
    split = split_vat_inclusive(Money.create("240.004"))
    assert split.amount_inc_vat == Money.create("240.00")


def test_working_back_from_a_rate_that_leaves_nothing_is_refused() -> None:
    with pytest.raises(InvalidMoney, match="nothing to work back to"):
        Money.create("100").before_percent_added(-100)


@pytest.mark.parametrize("rate", [1.5, True, "15"])
def test_working_back_from_an_inexact_rate_is_refused(rate: object) -> None:
    with pytest.raises(InvalidMoney):
        Money.create("100").before_percent_added(rate)  # type: ignore[arg-type]  # refused on purpose


def test_working_back_from_a_rate_that_is_not_a_number_is_refused() -> None:
    with pytest.raises(InvalidMoney, match="not a finite number"):
        Money.create("100").before_percent_added(Decimal("NaN"))
