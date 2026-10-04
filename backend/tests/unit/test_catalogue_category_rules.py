"""The rules a category of the catalogue is held to, with no database anywhere (FR-22).

A code is capital letters and digits and a slug small letters and digits, each
in words joined by single hyphens, text fits its column, and nesting stops at
two levels. Each refusal names its field the way the domain names it, so the
use case can name it the way the request did.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.catalogue_forms import (
    BELOW_ZERO_MESSAGE,
    CODE_FORM_MESSAGE,
    NOT_AN_AMOUNT_MESSAGE,
    PART_OF_A_CENT_MESSAGE,
    REQUIRED_MESSAGE,
    SLUG_FORM_MESSAGE,
    TOO_LARGE_MESSAGE,
    amount_held,
    optional_text,
)
from app.domain.category_rules import (
    HAS_CHILDREN_MESSAGE,
    LAST_SORT_ORDER,
    OWN_PARENT_MESSAGE,
    PARENT_NOT_AT_TOP_MESSAGE,
    SORT_ORDER_MESSAGE,
    checked_category_terms,
    ensure_parent_may_hold,
)
from app.domain.customer_account import REFUSED_FIELD
from app.domain.errors import ValidationFailure
from tests.support.catalogue_terms import a_category, category_terms


def refusal_of(error: pytest.ExceptionInfo[ValidationFailure]) -> tuple[object, str]:
    """Return the field a refusal names and its sentence."""
    return error.value.detail[REFUSED_FIELD], error.value.message


class TestTheFormsOfACategory:
    """A code, a slug and the text of a category are of their forms and fit their columns."""

    def test_terms_that_keep_every_rule_come_back_trimmed(self) -> None:
        terms = checked_category_terms(
            category_terms(code="  BREAK-DRILL ", name=" Breaking ", description="   ")
        )
        assert (terms.code, terms.name, terms.description) == ("BREAK-DRILL", "Breaking", None)

    @pytest.mark.parametrize("code", ["drill", "DRILL--SDS", "-DRILL", "DRILL SDS", "DRILL_SDS"])
    def test_a_code_out_of_its_form_is_refused(self, code: str) -> None:
        with pytest.raises(ValidationFailure) as error:
            checked_category_terms(category_terms(code=code))
        assert refusal_of(error) == ("code", CODE_FORM_MESSAGE)

    @pytest.mark.parametrize("slug", ["Drilling", "drilling--sds", "drilling-", "dril ling"])
    def test_a_slug_out_of_its_form_is_refused(self, slug: str) -> None:
        with pytest.raises(ValidationFailure) as error:
            checked_category_terms(category_terms(slug=slug))
        assert refusal_of(error) == ("slug", SLUG_FORM_MESSAGE)

    def test_a_blank_name_is_refused(self) -> None:
        with pytest.raises(ValidationFailure) as error:
            checked_category_terms(category_terms(name="   "))
        assert refusal_of(error) == ("name", REQUIRED_MESSAGE)

    def test_a_code_wider_than_its_column_is_refused(self) -> None:
        with pytest.raises(ValidationFailure) as error:
            checked_category_terms(category_terms(code="A" * 17))
        assert refusal_of(error) == ("code", "Enter at most 16 characters.")

    @pytest.mark.parametrize("sort_order", [-1, LAST_SORT_ORDER + 1])
    def test_a_sort_order_outside_a_smallint_is_refused(self, sort_order: int) -> None:
        with pytest.raises(ValidationFailure) as error:
            checked_category_terms(category_terms(sort_order=sort_order))
        assert refusal_of(error) == ("sort_order", SORT_ORDER_MESSAGE)

    def test_optional_text_wider_than_its_column_is_refused(self) -> None:
        with pytest.raises(ValidationFailure) as error:
            optional_text("company", "x" * 11, 10)
        assert refusal_of(error) == ("company", "Enter at most 10 characters.")


class TestNestingStopsAtTwoLevels:
    """A parent is at the top, is not the category itself, and a parent of children stays up."""

    def test_a_top_level_parent_may_hold_a_new_category(self) -> None:
        ensure_parent_may_hold(None, a_category(), has_children=False)

    def test_a_category_cannot_sit_under_itself(self) -> None:
        category = a_category()
        with pytest.raises(ValidationFailure) as error:
            ensure_parent_may_hold(category.id, category, has_children=False)
        assert refusal_of(error) == ("parent_category_id", OWN_PARENT_MESSAGE)

    def test_a_parent_that_has_a_parent_is_refused(self) -> None:
        child = a_category(parent_category_id=uuid4())
        with pytest.raises(ValidationFailure) as error:
            ensure_parent_may_hold(uuid4(), child, has_children=False)
        assert refusal_of(error) == ("parent_category_id", PARENT_NOT_AT_TOP_MESSAGE)

    def test_a_category_with_children_cannot_be_put_under_another(self) -> None:
        with pytest.raises(ValidationFailure) as error:
            ensure_parent_may_hold(uuid4(), a_category(), has_children=True)
        assert refusal_of(error) == ("parent_category_id", HAS_CHILDREN_MESSAGE)


class TestAnAmountTheCatalogueHolds:
    """Money is a number, zero or more, fits NUMERIC(12,2) and is in whole cents (BR-22)."""

    def test_an_amount_comes_back_with_two_decimals(self) -> None:
        assert str(amount_held("daily_rate", Decimal("280"))) == "280.00"

    def test_nothing_is_an_amount(self) -> None:
        assert amount_held("deposit_amount", Decimal("0")) == Decimal("0.00")

    @pytest.mark.parametrize(
        ("amount", "message"),
        [
            (Decimal("NaN"), NOT_AN_AMOUNT_MESSAGE),
            (Decimal("Infinity"), NOT_AN_AMOUNT_MESSAGE),
            (Decimal("-0.01"), BELOW_ZERO_MESSAGE),
            (Decimal("10000000000.00"), TOO_LARGE_MESSAGE),
            (Decimal("1E+40"), TOO_LARGE_MESSAGE),
            (Decimal("280.005"), PART_OF_A_CENT_MESSAGE),
        ],
    )
    def test_an_amount_the_catalogue_cannot_hold_is_refused(
        self, amount: Decimal, message: str
    ) -> None:
        with pytest.raises(ValidationFailure) as error:
            amount_held("daily_rate", amount)
        assert refusal_of(error) == ("daily_rate", message)
        assert error.value.rule == "BR-22"
