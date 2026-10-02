"""The pricing policy, which is BR-21, with BR-22 and BR-23 behind it.

One unit is charged the lower of two totals. Complete weeks at the weekly rate
with the days left over at the daily rate, or every day at the daily rate. The
quantity multiplies that, the trade discount comes off, and VAT at 15 percent
goes on. The deposit is shown beside the price and carries no VAT.

The worked example is the rotary hammer of the seed data, R280.00 a day and
R1,120.00 a week with a R1,200.00 deposit. Its weekly rate is four days of its
daily rate, so the weekly basis wins from the seventh day.

Nothing here needs a database. The policy is handed a snapshot and a period.

What a policy refuses to price, and the fixed rate policy the tests of a
booking use, are in tests/unit/test_pricing_inputs.py.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.period import DAYS_IN_A_WEEK
from app.domain.policies import PricingBasis, StandardPricingPolicy
from app.domain.policies.pricing import NO_DISCOUNT_PERCENT
from app.domain.vat import VAT_RATE_PERCENT, vat_on
from tests.support.pricing import hammer, hire_of, priced, rand

POLICY = StandardPricingPolicy()


class TestTheBasisForOneUnit:
    """Whichever of the two totals is lower."""

    def test_under_a_week_every_day_is_charged_at_the_daily_rate(self) -> None:
        quote = priced(3)
        assert quote.basis is PricingBasis.DAILY
        assert quote.unit_amount_ex_vat == rand("840.00")

    def test_six_days_have_no_complete_week_so_they_are_six_daily_rates(self) -> None:
        """The rule as written. It comes to more than the week that follows it."""
        quote = priced(6)
        assert quote.basis is PricingBasis.DAILY
        assert quote.unit_amount_ex_vat == rand("1680.00")

    def test_exactly_a_week_is_charged_at_the_weekly_rate(self) -> None:
        quote = priced(7)
        assert quote.basis is PricingBasis.WEEKLY
        assert quote.unit_amount_ex_vat == rand("1120.00")
        assert (quote.period.whole_weeks, quote.period.remainder_days) == (1, 0)

    def test_a_week_and_three_days_is_one_weekly_rate_and_three_daily_rates(self) -> None:
        quote = priced(10)
        assert quote.basis is PricingBasis.WEEKLY
        assert quote.unit_amount_ex_vat == rand("1960.00")
        assert (quote.period.whole_weeks, quote.period.remainder_days) == (1, 3)

    def test_two_whole_weeks_are_two_weekly_rates(self) -> None:
        quote = priced(14)
        assert quote.basis is PricingBasis.WEEKLY
        assert quote.unit_amount_ex_vat == rand("2240.00")
        assert (quote.period.whole_weeks, quote.period.remainder_days) == (2, 0)

    def test_the_daily_basis_wins_when_a_week_costs_more_than_seven_days(self) -> None:
        dear_week = hammer(daily="100.00", weekly="800.00")
        quote = priced(8, dear_week)
        assert quote.basis is PricingBasis.DAILY
        assert quote.unit_amount_ex_vat == rand("800.00")

    def test_when_the_two_totals_are_the_same_the_basis_is_daily(self) -> None:
        even_week = hammer(daily="100.00", weekly="700.00")
        quote = priced(7, even_week)
        assert quote.basis is PricingBasis.DAILY
        assert quote.unit_amount_ex_vat == rand("700.00")

    def test_the_week_the_policy_charges_by_is_seven_days(self) -> None:
        assert StandardPricingPolicy.WEEK_LENGTH_DAYS == DAYS_IN_A_WEEK == 7

    def test_the_policy_is_logged_under_its_name(self) -> None:
        assert POLICY.name() == "standard"


class TestTheAmountsOfAQuote:
    """The quantity, the discount, the VAT and the deposit."""

    def test_the_worked_example_of_the_contract(self) -> None:
        quote = priced(10, hammer(quantity=2))
        assert quote.quantity == 2
        assert quote.daily_rate == rand("280.00")
        assert quote.weekly_rate == rand("1120.00")
        assert quote.subtotal_ex_vat == rand("3920.00")
        assert quote.discount_percent == Decimal("0.00")
        assert quote.discount_amount == rand("0.00")
        assert quote.amount_ex_vat == rand("3920.00")
        assert quote.vat_rate_percent == Decimal("15.00")
        assert quote.vat_amount == rand("588.00")
        assert quote.total_inc_vat == rand("4508.00")
        assert quote.deposit_per_unit == rand("1200.00")
        assert quote.deposit_total == rand("2400.00")

    def test_a_quantity_above_one_multiplies_the_unit_amount_and_the_deposit(self) -> None:
        quote = priced(3, hammer(quantity=3))
        assert quote.unit_amount_ex_vat == rand("840.00")
        assert quote.subtotal_ex_vat == rand("2520.00")
        assert quote.vat_amount == rand("378.00")
        assert quote.total_inc_vat == rand("2898.00")
        assert quote.deposit_total == rand("3600.00")

    def test_a_trade_discount_comes_off_before_the_vat_goes_on(self) -> None:
        quote = priced(10, hammer(quantity=2), discount="10.00")
        assert quote.subtotal_ex_vat == rand("3920.00")
        assert quote.discount_amount == rand("392.00")
        assert quote.amount_ex_vat == rand("3528.00")
        assert quote.vat_amount == rand("529.20")
        assert quote.total_inc_vat == rand("4057.20")

    def test_no_discount_changes_nothing(self) -> None:
        assert priced(10, discount="0.00") == priced(10, discount="0")
        assert priced(10).amount_ex_vat == priced(10).subtotal_ex_vat

    def test_a_full_discount_leaves_nothing_to_charge_and_the_deposit_still_stands(self) -> None:
        quote = priced(3, discount="100.00")
        assert quote.amount_ex_vat == rand("0.00")
        assert quote.vat_amount == rand("0.00")
        assert quote.total_inc_vat == rand("0.00")
        assert quote.deposit_total == rand("1200.00")

    def test_the_deposit_carries_no_vat_and_is_not_in_the_total(self) -> None:
        quote = priced(1)
        assert quote.total_inc_vat == rand("322.00")
        assert quote.deposit_total == quote.deposit_per_unit == rand("1200.00")

    def test_the_vat_rate_is_fifteen_percent_and_is_written_in_one_place(self) -> None:
        assert Decimal("15.00") == VAT_RATE_PERCENT
        assert vat_on(rand("100.00")) == rand("15.00")


class TestTheRoundingPoint:
    """Nothing is rounded before the amounts a charge is written with (BR-22)."""

    def test_the_amount_charged_is_rounded_once_from_the_exact_figure(self) -> None:
        """R555.00 less 12.5 percent is R485.625, which is written as R485.63.

        Rounding the discount first would take R69.38 off and charge R485.62.
        """
        quote = priced(1, hammer(quantity=3, daily="185.00", weekly="740.00"), discount="12.5")
        assert quote.subtotal_ex_vat == rand("555.00")
        assert quote.amount_ex_vat == rand("485.63")
        assert quote.vat_amount == rand("72.84")
        assert quote.total_inc_vat == rand("558.47")

    def test_the_vat_is_worked_out_on_the_exact_amount_and_not_on_the_rounded_one(self) -> None:
        """R555.08 less 12.5 percent is R485.695, and 15 percent of that is R72.85425.

        Fifteen percent of the rounded R485.70 is R72.855, which would be
        written as R72.86.
        """
        quote = priced(1, hammer(daily="555.08", weekly="2220.32"), discount="12.5")
        assert quote.amount_ex_vat == rand("485.70")
        assert quote.vat_amount == rand("72.85")

    def test_a_half_cent_of_vat_rounds_up(self) -> None:
        """Fifteen percent of R185.90 is R27.885. Rounding to even would write R27.88."""
        quote = priced(1, hammer(daily="185.90", weekly="743.60"))
        assert quote.vat_amount == rand("27.89")
        assert quote.total_inc_vat == rand("213.79")

    def test_a_rate_with_a_fraction_of_a_cent_is_not_rounded_before_it_is_multiplied(
        self,
    ) -> None:
        quote = priced(3, hammer(daily="0.335", weekly="2.00"))
        assert quote.unit_amount_ex_vat == rand("1.01")

    @pytest.mark.parametrize("discount", ["0.00", "2.50", "7.50", "12.50", "33.33"])
    @pytest.mark.parametrize("daily", ["185.00", "280.00", "99.95", "555.08"])
    @pytest.mark.parametrize("quantity", [1, 3, 7])
    def test_the_figures_on_a_quote_always_add_up_to_the_cent(
        self, discount: str, daily: str, quantity: int
    ) -> None:
        quote = priced(5, hammer(quantity=quantity, daily=daily, weekly="5000.00"), discount)
        assert quote.subtotal_ex_vat.subtract(quote.discount_amount) == quote.amount_ex_vat
        assert quote.amount_ex_vat.add(quote.vat_amount) == quote.total_inc_vat

    def test_every_amount_on_a_quote_is_written_to_the_cent(self) -> None:
        quote = priced(10, hammer(quantity=3, daily="99.95", weekly="399.80"), discount="7.5")
        amounts = [
            quote.daily_rate,
            quote.weekly_rate,
            quote.unit_amount_ex_vat,
            quote.subtotal_ex_vat,
            quote.discount_amount,
            quote.amount_ex_vat,
            quote.vat_amount,
            quote.total_inc_vat,
            quote.deposit_per_unit,
            quote.deposit_total,
        ]
        assert all(amount == amount.rounded() for amount in amounts)
        assert all(amount.amount.as_tuple().exponent == -2 for amount in amounts)


class TestAPriceComesFromASnapshot:
    """BR-20. A later catalogue change never rewrites an existing booking."""

    def test_a_quote_from_a_snapshot_at_r280_is_unaffected_by_the_rate_becoming_r310(
        self,
    ) -> None:
        booked_at_280 = hammer(daily="280.00", weekly="1120.00")
        before = POLICY.quote(booked_at_280, hire_of(3), NO_DISCOUNT_PERCENT)

        catalogue_now_at_310 = hammer(daily="310.00", weekly="1240.00")
        new_booking = POLICY.quote(catalogue_now_at_310, hire_of(3), NO_DISCOUNT_PERCENT)

        assert POLICY.quote(booked_at_280, hire_of(3), NO_DISCOUNT_PERCENT) == before
        assert before.unit_amount_ex_vat == rand("840.00")
        assert new_booking.unit_amount_ex_vat == rand("930.00")

    def test_a_snapshot_cannot_be_changed_after_it_was_taken(self) -> None:
        with pytest.raises(AttributeError):
            hammer().daily_rate = rand("310.00")  # type: ignore[misc]  # the mistake under test
