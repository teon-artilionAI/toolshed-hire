"""The utilisation percentage, gross contribution and the share of a hire charge, with no database.

Each is worked out in one module of the domain, and these hold the rules of
each. A percentage is rounded half up to two decimals, gross contribution is
revenue, late fees and recovery less repair costs, and a hire charge on a
whole hire is shared by each unit's part of its line, the last unit taking the
rounding cent.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.contribution import Contribution
from app.domain.money import InvalidMoney, Money
from app.domain.policies.hire_charge_share import UnitOnLine, shares_of_hire_charge
from app.domain.utilisation import utilisation_percent


def rand(text: str) -> Money:
    """Return an amount of money from its text."""
    return Money.create(text)


class TestTheUtilisationPercentage:
    """Days on hire over serviceable days, to two decimals, rounded half up."""

    def test_a_third_is_written_to_two_decimals(self) -> None:
        assert utilisation_percent(10, 30) == Decimal("33.33")

    def test_a_figure_past_the_half_is_rounded_up(self) -> None:
        assert utilisation_percent(2, 3) == Decimal("66.67")

    def test_an_exact_half_cent_is_rounded_up_and_not_to_the_even_neighbour(self) -> None:
        assert utilisation_percent(1, 32) == Decimal("3.13")

    def test_a_unit_never_hired_is_at_nought(self) -> None:
        assert utilisation_percent(0, 30) == Decimal("0.00")

    def test_a_unit_hired_every_serviceable_day_is_at_a_hundred(self) -> None:
        assert utilisation_percent(4, 4) == Decimal("100.00")

    def test_a_unit_with_no_serviceable_day_has_no_utilisation(self) -> None:
        assert utilisation_percent(0, 0) is None

    def test_a_count_below_nought_is_refused(self) -> None:
        with pytest.raises(ValueError, match="Neither can be below nought"):
            utilisation_percent(-1, 30)


class TestGrossContribution:
    """Revenue, late fees and recovery, less the repair costs."""

    def test_the_four_parts_make_the_figure(self) -> None:
        parts = Contribution(rand("299.99"), rand("0.00"), rand("400.00"), rand("350.00"))
        assert parts.gross_contribution == rand("349.99")

    def test_repairs_beyond_the_earnings_make_it_negative(self) -> None:
        parts = Contribution(rand("0.00"), rand("0.00"), rand("0.00"), rand("180.00"))
        assert parts.gross_contribution == rand("-180.00")

    def test_parts_add_up_part_by_part(self) -> None:
        first = Contribution(rand("212.63"), rand("208.70"), rand("0.00"), rand("0.00"))
        second = Contribution(rand("730.63"), rand("0.00"), rand("0.00"), rand("180.00"))
        total = Contribution.nothing().plus(first).plus(second)
        assert total == Contribution(rand("943.26"), rand("208.70"), rand("0"), rand("180.00"))
        assert total.gross_contribution == rand("971.96")


class TestTheShareOfAHireCharge:
    """A charge on a whole hire is shared by each unit's part of its line."""

    def test_two_hammers_on_one_line_and_a_mixer_on_another(self) -> None:
        units = [
            UnitOnLine(rand("425.25"), 2),
            UnitOnLine(rand("425.25"), 2),
            UnitOnLine(rand("300.00"), 1),
        ]
        shares = shares_of_hire_charge(rand("725.25"), units)
        assert shares == (rand("212.63"), rand("212.63"), rand("299.99"))

    def test_the_last_unit_takes_the_rounding_cent(self) -> None:
        units = [UnitOnLine(rand("100.00"), 3)] * 3
        assert shares_of_hire_charge(rand("100.00"), units) == (
            rand("33.33"),
            rand("33.33"),
            rand("33.34"),
        )

    def test_the_shares_always_add_up_to_the_charge(self) -> None:
        units = [UnitOnLine(rand("310.00"), 3)] * 3 + [UnitOnLine(rand("97.13"), 1)]
        shares = shares_of_hire_charge(rand("1007.13"), units)
        total = Money.zero()
        for share in shares:
            total = total.add(share)
        assert total == rand("1007.13")

    def test_a_reversal_is_shared_by_the_same_weights_and_nets_each_share_off(self) -> None:
        units = [UnitOnLine(rand("425.25"), 2)] * 2 + [UnitOnLine(rand("300.00"), 1)]
        charged = shares_of_hire_charge(rand("725.25"), units)
        reversed_ = shares_of_hire_charge(rand("-725.25"), units)
        assert [one.add(other) for one, other in zip(charged, reversed_, strict=True)] == [
            Money.zero().rounded()
        ] * 3

    def test_a_hire_booked_at_nothing_shares_its_charge_equally(self) -> None:
        units = [UnitOnLine(rand("0.00"), 1), UnitOnLine(rand("0.00"), 1)]
        assert shares_of_hire_charge(rand("10.00"), units) == (rand("5.00"), rand("5.00"))

    def test_one_unit_takes_the_whole_charge(self) -> None:
        assert shares_of_hire_charge(rand("518.00"), [UnitOnLine(rand("518.00"), 1)]) == (
            rand("518.00"),
        )

    def test_a_charge_with_no_unit_is_refused(self) -> None:
        with pytest.raises(ValueError, match="between no units"):
            shares_of_hire_charge(rand("100.00"), [])

    def test_a_line_that_books_no_unit_is_refused(self) -> None:
        with pytest.raises(InvalidMoney, match="whole above nought"):
            shares_of_hire_charge(rand("100.00"), [UnitOnLine(rand("100.00"), 0)])


class TestAnAmountInProportion:
    """Money is multiplied by the part before it is divided by the whole."""

    def test_an_exact_share_stays_exact(self) -> None:
        assert rand("725.25").in_proportion(Decimal("212.625"), Decimal("725.25")) == rand(
            "212.625"
        )

    def test_a_part_below_nought_is_refused(self) -> None:
        with pytest.raises(InvalidMoney, match="nought or more"):
            rand("10.00").in_proportion(-1, 2)

    def test_a_float_is_refused(self) -> None:
        with pytest.raises(InvalidMoney, match="float"):
            rand("10.00").in_proportion(0.5, 1)  # type: ignore[arg-type]  # the refusal under test
