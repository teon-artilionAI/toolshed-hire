"""A walk-in's details, checked with no database anywhere (US-20).

The counter records a customer who has no login with the same rules a person
registering online is held to, and with the two things only the counter
decides, whether they hire as a trade and the company a trade hires as. A
refusal names the field the way the walk-in route names it in the domain's
words, so the name the staff see is refused as the display name.
"""

from __future__ import annotations

from typing import Final

import pytest

from app.domain.customer_account import REFUSED_FIELD, TRADE_NEEDS_COMPANY_MESSAGE
from app.domain.enums import AccountStatus, CustomerType, IdDocType
from app.domain.errors import ValidationFailure
from app.domain.identity import NO_TRADE_DISCOUNT
from app.domain.walk_in import WalkInCustomer

TOO_LONG_NAME: Final[str] = "x" * 121


def a_walk_in(**changes: object) -> WalkInCustomer:
    """Return a walk-in built from good details, with some of them replaced."""
    details: dict[str, object] = {
        "display_name": "  Sizwe Ndlovu ",
        "phone": " 072 555 0199 ",
        "id_document_type": IdDocType.PASSPORT,
        "id_document_last4": " A1B2 ",
        "billing_address_line1": "8 Station Road",
        "billing_suburb": "Observatory",
        "billing_city": "Cape Town",
        "billing_postal_code": "7925",
        "customer_type": CustomerType.INDIVIDUAL,
        "company_name": None,
        "vat_number": None,
    }
    details.update(changes)
    return WalkInCustomer.registering(**details)


def refused_field(**changes: object) -> object:
    """Return the field the walk-in with these details is refused on."""
    with pytest.raises(ValidationFailure) as refusal:
        a_walk_in(**changes)
    return refusal.value.detail[REFUSED_FIELD]


def test_the_details_are_trimmed_and_the_standing_is_not_the_counters_to_choose() -> None:
    walk_in = a_walk_in()
    assert (walk_in.details.full_name, walk_in.details.phone) == ("Sizwe Ndlovu", "072 555 0199")
    assert walk_in.details.id_document_last4 == "A1B2"
    assert walk_in.details.account_status is AccountStatus.ACTIVE
    assert walk_in.details.trade_discount_percent == NO_TRADE_DISCOUNT
    assert (walk_in.customer_type, walk_in.company_name, walk_in.vat_number) == (
        CustomerType.INDIVIDUAL, None, None
    )


def test_a_trade_walk_in_keeps_its_company_and_its_vat_number() -> None:
    walk_in = a_walk_in(
        customer_type=CustomerType.TRADE, company_name=" Ndlovu Plumbing ", vat_number="4123456789"
    )
    assert (walk_in.customer_type, walk_in.company_name, walk_in.vat_number) == (
        CustomerType.TRADE, "Ndlovu Plumbing", "4123456789"
    )


@pytest.mark.parametrize("company", [None, "", "   "])
def test_a_trade_walk_in_with_no_company_is_refused_naming_the_company(
    company: str | None,
) -> None:
    with pytest.raises(ValidationFailure) as refusal:
        a_walk_in(customer_type=CustomerType.TRADE, company_name=company)
    assert refusal.value.message == TRADE_NEEDS_COMPANY_MESSAGE
    assert refusal.value.detail[REFUSED_FIELD] == "company_name"


def test_an_individual_with_a_blank_company_keeps_none() -> None:
    assert a_walk_in(company_name="  ").company_name is None


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"display_name": "   "}, "display_name"),
        ({"display_name": TOO_LONG_NAME}, "display_name"),
        ({"phone": "call me"}, "phone"),
        ({"id_document_last4": "12"}, "id_document_last4"),
        ({"billing_city": ""}, "billing_city"),
        ({"billing_postal_code": "x" * 11}, "billing_postal_code"),
        ({"company_name": "x" * 121}, "company_name"),
        ({"vat_number": "x" * 21}, "vat_number"),
    ],
)
def test_a_value_that_does_not_fit_is_refused_by_the_name_of_its_field(
    changes: dict[str, object], field: str
) -> None:
    assert refused_field(**changes) == field
