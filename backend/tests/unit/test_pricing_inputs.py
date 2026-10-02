"""What a pricing policy refuses to price, and the policy the tests price with.

A policy is handed a snapshot and a discount by code, never by a visitor, so a
bad one is a mistake in the calling code and is refused loudly. A float is
refused wherever it is offered, because the money path holds none (BR-22).

`FixedRatePricingPolicy` is the counterpart the design document gives the
standard policy. It charges one amount for a unit whatever is hired, so a test
of a booking can state its price in a line.

The rule itself is in tests/unit/test_pricing_policy.py.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.policies import (
    FixedRatePricingPolicy,
    InvalidPricingInput,
    LineSnapshot,
    PricingBasis,
    PricingPolicy,
    StandardPricingPolicy,
)
from app.domain.policies.pricing import NO_DISCOUNT_PERCENT
from tests.support.pricing import hammer, hire_of, rand

POLICY = StandardPricingPolicy()


class TestWhatAPolicyRefusesToPrice:
    """A line or a discount no booking could carry."""

    @pytest.mark.parametrize("discount", [Decimal("-0.01"), Decimal("100.01"), Decimal("NaN")])
    def test_a_discount_outside_nought_to_a_hundred_is_refused(self, discount: Decimal) -> None:
        with pytest.raises(InvalidPricingInput, match="A discount is between"):
            POLICY.quote(hammer(), hire_of(3), discount)

    @pytest.mark.parametrize("discount", [10.0, 10, "10.00"])
    def test_a_discount_that_is_not_a_decimal_is_refused(self, discount: object) -> None:
        with pytest.raises(InvalidPricingInput, match="A discount is a Decimal percentage"):
            POLICY.quote(hammer(), hire_of(3), discount)  # type: ignore[arg-type]  # the mistake under test

    @pytest.mark.parametrize("quantity", [0, -1])
    def test_a_line_of_no_units_is_refused(self, quantity: int) -> None:
        with pytest.raises(InvalidPricingInput, match="at least 1 unit"):
            hammer(quantity=quantity)

    @pytest.mark.parametrize("quantity", [1.0, True, "2"])
    def test_a_quantity_that_is_not_a_whole_number_is_refused(self, quantity: object) -> None:
        with pytest.raises(InvalidPricingInput, match="A quantity is a whole number"):
            hammer(quantity=quantity)  # type: ignore[arg-type]  # the mistake under test

    @pytest.mark.parametrize("field", ["daily_rate", "weekly_rate", "deposit"])
    @pytest.mark.parametrize("bare", [Decimal("280.00"), 280.0, 280])
    def test_a_rate_or_deposit_that_is_not_money_is_refused(
        self, field: str, bare: object
    ) -> None:
        figures: dict[str, object] = {
            "daily_rate": rand("280.00"),
            "weekly_rate": rand("1120.00"),
            "deposit": rand("1200.00"),
        }
        figures[field] = bare
        with pytest.raises(InvalidPricingInput, match="are Money"):
            LineSnapshot(quantity=1, **figures)  # type: ignore[arg-type]  # the mistake under test

    @pytest.mark.parametrize("field", ["daily_rate", "weekly_rate", "deposit"])
    def test_a_negative_rate_or_deposit_is_refused(self, field: str) -> None:
        figures = {
            "daily_rate": rand("280.00"),
            "weekly_rate": rand("1120.00"),
            "deposit": rand("1200.00"),
        }
        figures[field] = rand("-0.01")
        with pytest.raises(InvalidPricingInput, match="never negative"):
            LineSnapshot(quantity=1, **figures)


class TestTheFixedRatePolicy:
    """The test counterpart, which charges one amount whatever is hired."""

    FIXED = FixedRatePricingPolicy(rand("100.00"))

    def test_it_stands_in_for_the_port(self) -> None:
        policy: PricingPolicy = self.FIXED
        assert policy.name() == "fixed-rate"

    @pytest.mark.parametrize("days", [1, 7, 10, 28])
    def test_one_unit_costs_the_fixed_amount_for_any_period_and_any_rates(self, days: int) -> None:
        quote = self.FIXED.quote(hammer(), hire_of(days), NO_DISCOUNT_PERCENT)
        assert quote.unit_amount_ex_vat == rand("100.00")
        assert quote.basis is PricingBasis.DAILY

    def test_the_quantity_the_discount_and_the_vat_apply_as_they_do_to_the_standard_policy(
        self,
    ) -> None:
        quote = self.FIXED.quote(hammer(quantity=3), hire_of(10), Decimal("10.00"))
        assert quote.subtotal_ex_vat == rand("300.00")
        assert quote.discount_amount == rand("30.00")
        assert quote.amount_ex_vat == rand("270.00")
        assert quote.vat_amount == rand("40.50")
        assert quote.total_inc_vat == rand("310.50")
        assert quote.deposit_total == rand("3600.00")

    @pytest.mark.parametrize("fixed", [rand("-1.00"), Decimal("100.00"), 100.0])
    def test_a_fixed_amount_that_is_negative_or_is_not_money_is_refused(
        self, fixed: object
    ) -> None:
        with pytest.raises(InvalidPricingInput, match="never negative"):
            FixedRatePricingPolicy(fixed)  # type: ignore[arg-type]  # the mistake under test
