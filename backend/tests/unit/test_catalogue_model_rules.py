"""The rules a product model is held to, with no database anywhere (FR-22, US-30).

Every amount is zero or more, a weekly rate is at most seven days at the
daily rate, which is the most the pricing policy could ever charge for a week
(BR-21), the hire limits are in order and inside the 28 days any hire may last
(BR-03), a SKU and a slug are of their forms, and a model is only classified
under an active category.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.catalogue_entry_rules import (
    HIRE_DAYS_ORDER_MESSAGE,
    INACTIVE_CATEGORY_MESSAGE,
    LONGEST_HIRE_MESSAGE,
    SHORTEST_HIRE_MESSAGE,
    WEEKLY_RATE_MESSAGE,
    checked_model_terms,
    ensure_category_may_classify,
)
from app.domain.catalogue_forms import (
    BELOW_ZERO_MESSAGE,
    CODE_FORM_MESSAGE,
    REQUIRED_MESSAGE,
    SLUG_FORM_MESSAGE,
)
from app.domain.customer_account import REFUSED_FIELD
from app.domain.errors import ValidationFailure
from app.domain.money import Money
from app.domain.policies import StandardPricingPolicy
from tests.support.catalogue_terms import a_category, model_terms

CATEGORY = uuid4()


def refusal_of(error: pytest.ExceptionInfo[ValidationFailure]) -> tuple[object, str]:
    """Return the field a refusal names and its sentence."""
    return error.value.detail[REFUSED_FIELD], error.value.message


class TestTermsThatKeepEveryRule:
    """A model that keeps every rule comes back trimmed and in whole cents."""

    def test_the_hammer_at_r280_keeps_every_rule(self) -> None:
        terms = model_terms(CATEGORY)
        assert checked_model_terms(terms) == terms

    def test_text_is_trimmed_and_amounts_are_written_to_the_cent(self) -> None:
        terms = checked_model_terms(
            model_terms(CATEGORY, name="  Hammer ", daily_rate=Decimal("280"), long_description=" ")
        )
        assert (terms.name, str(terms.daily_rate), terms.long_description) == (
            "Hammer",
            "280.00",
            None,
        )

    def test_a_weekly_rate_of_exactly_seven_days_is_allowed(self) -> None:
        terms = model_terms(CATEGORY, weekly_rate=Decimal("1960.00"))
        assert checked_model_terms(terms).weekly_rate == Decimal("1960.00")

    def test_a_hire_of_one_day_to_twenty_eight_is_allowed(self) -> None:
        terms = model_terms(CATEGORY, min_hire_days=28, max_hire_days=28)
        assert checked_model_terms(terms).min_hire_days == 28


class TestEachRuleNamesItsField:
    """Each refusal names the field it is about and says what to do."""

    @pytest.mark.parametrize(
        "field",
        ["daily_rate", "weekly_rate", "deposit_amount", "late_fee_per_day", "replacement_value"],
    )
    def test_money_below_zero_is_refused(self, field: str) -> None:
        with pytest.raises(ValidationFailure) as error:
            checked_model_terms(model_terms(CATEGORY, **{field: Decimal("-1.00")}))
        assert refusal_of(error) == (field, BELOW_ZERO_MESSAGE)

    def test_a_weekly_rate_above_seven_days_at_the_daily_rate_is_refused(self) -> None:
        with pytest.raises(ValidationFailure) as error:
            checked_model_terms(model_terms(CATEGORY, weekly_rate=Decimal("1960.01")))
        assert refusal_of(error) == ("weekly_rate", WEEKLY_RATE_MESSAGE)
        assert error.value.rule == "BR-21"

    def test_a_shortest_hire_of_no_days_is_refused(self) -> None:
        with pytest.raises(ValidationFailure) as error:
            checked_model_terms(model_terms(CATEGORY, min_hire_days=0))
        assert refusal_of(error) == ("min_hire_days", SHORTEST_HIRE_MESSAGE)

    def test_a_longest_hire_past_twenty_eight_days_is_refused(self) -> None:
        with pytest.raises(ValidationFailure) as error:
            checked_model_terms(model_terms(CATEGORY, max_hire_days=29))
        assert refusal_of(error) == ("max_hire_days", LONGEST_HIRE_MESSAGE)

    def test_a_shortest_hire_longer_than_the_longest_is_refused(self) -> None:
        with pytest.raises(ValidationFailure) as error:
            checked_model_terms(model_terms(CATEGORY, min_hire_days=8, max_hire_days=7))
        assert refusal_of(error) == ("min_hire_days", HIRE_DAYS_ORDER_MESSAGE)
        assert error.value.rule == "BR-03"

    def test_a_sku_out_of_its_form_is_refused(self) -> None:
        with pytest.raises(ValidationFailure) as error:
            checked_model_terms(model_terms(CATEGORY, sku="dr-bosch"))
        assert refusal_of(error) == ("sku", CODE_FORM_MESSAGE)

    def test_a_slug_out_of_its_form_is_refused(self) -> None:
        with pytest.raises(ValidationFailure) as error:
            checked_model_terms(model_terms(CATEGORY, slug="Bosch Hammer"))
        assert refusal_of(error) == ("slug", SLUG_FORM_MESSAGE)

    @pytest.mark.parametrize(
        "field", ["name", "manufacturer", "model_number", "short_description"]
    )
    def test_blank_required_text_is_refused(self, field: str) -> None:
        with pytest.raises(ValidationFailure) as error:
            checked_model_terms(model_terms(CATEGORY, **{field: " "}))
        assert refusal_of(error) == (field, REQUIRED_MESSAGE)

    def test_a_short_description_wider_than_its_column_is_refused(self) -> None:
        with pytest.raises(ValidationFailure) as error:
            checked_model_terms(model_terms(CATEGORY, short_description="x" * 301))
        assert refusal_of(error) == ("short_description", "Enter at most 300 characters.")


class TestTheCategoryOfAModel:
    """A model is classified under an active category only."""

    def test_an_active_category_may_classify_a_model(self) -> None:
        ensure_category_may_classify(a_category())

    def test_a_category_that_was_switched_off_is_refused(self) -> None:
        with pytest.raises(ValidationFailure) as error:
            ensure_category_may_classify(a_category(is_active=False))
        assert refusal_of(error) == ("category_id", INACTIVE_CATEGORY_MESSAGE)


def test_the_policy_says_what_a_week_charged_by_the_day_comes_to() -> None:
    week = StandardPricingPolicy.week_at_the_daily_rate(Money(Decimal("280.00")))
    assert week == Money(Decimal("1960.00"))
