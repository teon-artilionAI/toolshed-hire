"""The Money value object, which is BR-22.

Three things are held here. An amount is exact, so it is never built from a
float and never combined with one. It is rounded half up to the cent, and only
when `rounded` is called. And a negative amount is an amount like any other,
because a refund has to be written down too.

Half up is not what `Decimal` does when left alone. It rounds a half to the
even neighbour, which turns R0.125 into R0.12. The cases below are chosen so
that the two rules give different answers.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from app.domain.money import CURRENCY_CODE, InvalidMoney, Money

R280 = Money.create("280.00")
R1120 = Money.create("1120.00")


class TestBuildingAnAmount:
    """An amount comes from a Decimal, a whole number or text, and never a float."""

    @pytest.mark.parametrize("amount", [Decimal("280.00"), 280, "280.00"])
    def test_a_decimal_a_whole_number_and_text_all_build_the_same_amount(
        self, amount: Decimal | int | str
    ) -> None:
        assert Money.create(amount) == R280

    def test_zero_is_no_money(self) -> None:
        assert Money.zero() == Money.create(0)
        assert not Money.zero().is_negative()

    def test_every_amount_is_in_rand(self) -> None:
        assert R280.currency == CURRENCY_CODE == "ZAR"

    @pytest.mark.parametrize("amount", [280.0, 0.1, True])
    def test_a_float_or_a_boolean_is_refused(self, amount: object) -> None:
        with pytest.raises(InvalidMoney, match="Money is exact"):
            Money.create(amount)  # type: ignore[arg-type]  # the mistake under test

    def test_a_float_is_refused_by_the_constructor_as_well(self) -> None:
        with pytest.raises(InvalidMoney, match="must be a Decimal"):
            Money(280.0)  # type: ignore[arg-type]  # the mistake under test

    @pytest.mark.parametrize("amount", ["two hundred", "", "R280", None])
    def test_text_that_does_not_spell_an_amount_is_refused(self, amount: object) -> None:
        with pytest.raises(InvalidMoney, match="does not spell an amount"):
            Money.create(amount)  # type: ignore[arg-type]  # the mistake under test

    @pytest.mark.parametrize("amount", [Decimal("NaN"), Decimal("Infinity")])
    def test_an_amount_that_is_not_a_finite_number_is_refused(self, amount: Decimal) -> None:
        with pytest.raises(InvalidMoney, match="not a finite number"):
            Money(amount)

    def test_an_amount_cannot_be_changed_once_it_exists(self) -> None:
        with pytest.raises(FrozenInstanceError):
            R280.amount = Decimal("1.00")  # type: ignore[misc]  # the mistake under test


class TestArithmetic:
    """Adding, subtracting, a whole number of times and a percentage."""

    def test_two_amounts_add(self) -> None:
        assert R1120.add(R280.times(3)) == Money.create("1960.00")

    def test_one_amount_is_taken_from_another(self) -> None:
        assert R1120.subtract(R280) == Money.create("840.00")

    def test_an_amount_is_multiplied_by_a_whole_number(self) -> None:
        assert R280.times(10) == Money.create("2800.00")
        assert R280.times(0) == Money.zero()

    def test_a_percentage_of_an_amount_is_exact_and_unrounded(self) -> None:
        assert Money.create("3920.00").percent_of(Decimal("15.00")) == Money.create("588.00")
        assert Money.create("555.00").percent_of(Decimal("12.5")) == Money.create("69.375")
        assert R280.percent_of(15) == Money.create("42.00")

    def test_arithmetic_returns_a_new_amount_and_leaves_the_old_one_alone(self) -> None:
        amount = Money.create("280.00")
        amount.add(amount)
        assert amount == Money.create("280.00")

    @pytest.mark.parametrize("factor", [1.5, Decimal("1.5"), "3", True])
    def test_an_amount_is_not_multiplied_by_anything_but_a_whole_number(
        self, factor: object
    ) -> None:
        with pytest.raises(InvalidMoney):
            R280.times(factor)  # type: ignore[arg-type]  # the mistake under test

    @pytest.mark.parametrize("rate", [15.0, "15", True, Decimal("NaN")])
    def test_a_percentage_is_a_decimal_or_a_whole_number_and_nothing_else(
        self, rate: object
    ) -> None:
        with pytest.raises(InvalidMoney):
            R280.percent_of(rate)  # type: ignore[arg-type]  # the mistake under test

    @pytest.mark.parametrize("other", [280.0, 280, Decimal("280.00"), "280.00"])
    def test_money_is_only_added_to_and_taken_from_money(self, other: object) -> None:
        with pytest.raises(InvalidMoney, match="only combined or compared with Money"):
            R280.add(other)  # type: ignore[arg-type]  # the mistake under test
        with pytest.raises(InvalidMoney, match="only combined or compared with Money"):
            R280.subtract(other)  # type: ignore[arg-type]  # the mistake under test

    def test_the_plus_sign_does_not_work_on_money_so_a_float_cannot_slip_in(self) -> None:
        with pytest.raises(TypeError):
            _ = R280 + 1.0  # type: ignore[operator]  # the mistake under test


class TestRounding:
    """Half up to the cent, once, and only when asked."""

    @pytest.mark.parametrize(
        ("exact", "written"),
        [
            ("0.005", "0.01"),
            ("0.125", "0.13"),
            ("0.135", "0.14"),
            ("2.675", "2.68"),
            ("0.0049", "0.00"),
            ("1.994", "1.99"),
            ("1.995", "2.00"),
            ("280", "280.00"),
        ],
    )
    def test_a_half_cent_rounds_up(self, exact: str, written: str) -> None:
        rounded = Money.create(exact).rounded()
        assert rounded == Money.create(written)
        assert str(rounded.amount) == written

    def test_an_amount_keeps_every_decimal_until_it_is_rounded(self) -> None:
        fraction_of_a_cent = Money.create("0.335")
        assert fraction_of_a_cent.times(3) == Money.create("1.005")
        assert fraction_of_a_cent.times(3).rounded() == Money.create("1.01")
        assert fraction_of_a_cent.rounded().times(3) == Money.create("1.02")

    def test_a_negative_half_cent_rounds_away_from_zero(self) -> None:
        assert Money.create("-0.005").rounded() == Money.create("-0.01")


class TestARefund:
    """A negative amount is representable."""

    def test_taking_more_than_there_is_leaves_a_negative_amount(self) -> None:
        refund = R280.subtract(R1120)
        assert refund == Money.create("-840.00")
        assert refund.is_negative()

    def test_a_negative_amount_adds_back_to_nothing(self) -> None:
        assert Money.create("-840.00").add(Money.create("840.00")) == Money.zero()

    def test_a_positive_amount_and_zero_are_not_negative(self) -> None:
        assert not R280.is_negative()
        assert not Money.zero().is_negative()


class TestComparing:
    """Two amounts compare by value, and money compares with nothing else."""

    def test_the_same_amount_written_two_ways_is_equal(self) -> None:
        assert Money.create("280") == Money.create("280.00")
        assert hash(Money.create("280")) == hash(Money.create("280.00"))

    def test_amounts_order_by_value(self) -> None:
        assert R280 < R1120
        assert R280 <= R280
        assert R1120 > R280
        assert R1120 >= R1120
        assert not R1120 < R280
        assert Money.create("-1") < Money.zero()

    def test_money_is_never_equal_to_a_bare_number(self) -> None:
        amount = Money.create("280.00")
        assert amount != 280.0
        assert amount != Decimal("280.00")

    @pytest.mark.parametrize("other", [280.0, 280, Decimal("280.00")])
    def test_money_is_not_ordered_against_a_bare_number(self, other: object) -> None:
        amount = Money.create("280.00")
        with pytest.raises(InvalidMoney, match="only combined or compared with Money"):
            assert amount < other  # type: ignore[operator]  # the mistake under test
        with pytest.raises(InvalidMoney):
            assert amount <= other  # type: ignore[operator]  # the mistake under test
        with pytest.raises(InvalidMoney):
            assert amount > other  # type: ignore[operator]  # the mistake under test
        with pytest.raises(InvalidMoney):
            assert amount >= other  # type: ignore[operator]  # the mistake under test
