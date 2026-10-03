"""The password rule and the rules of a customer's own details, with nothing around them.

A chosen password is at least twelve characters (BR-45). The eight contact and
billing fields are the only ones a customer may edit, each has a width and
most are required, and a trade customer keeps a company name (US-05, C-26).

No database and no HTTP. The domain names a field in its own words, for
example `billing_city`, and the last class proves the application layer turns
that into the name the request used.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Final
from uuid import uuid4

import pytest

from app.application.identity.account_rules import (
    ensure_password_may_be_set,
    normalised_email,
    refused_field,
    wire_name,
)
from app.application.refusal import refused_parameter_of
from app.domain.customer_account import (
    EDITABLE_FIELDS,
    NOT_EDITABLE_MESSAGE,
    PHONE_MESSAGE,
    REFUSED_FIELD,
    REQUIRED_MESSAGE,
    TRADE_NEEDS_COMPANY_MESSAGE,
    CustomerDetails,
    NewCustomer,
    cleaned_value,
)
from app.domain.enums import AccountStatus, CustomerType, IdDocType
from app.domain.errors import ValidationFailure
from app.domain.password_policy import (
    MAXIMUM_PASSWORD_BYTES,
    MINIMUM_PASSWORD_LENGTH,
    PASSWORD_RULE,
    PASSWORD_TOO_LONG_MESSAGE,
    PASSWORD_TOO_SHORT_MESSAGE,
    ensure_password_may_be_chosen,
)
from app.infrastructure import security

ELEVEN_CHARACTERS: Final[str] = "elevenchars"
TWELVE_CHARACTERS: Final[str] = "twelve-chars"
# Twenty five characters of three bytes each, which bcrypt would cut short.
SEVENTY_FIVE_BYTES: Final[str] = "€" * 25
FORBIDDEN_FIELDS: Final[list[str]] = ["account_status", "role", "trade_discount_percent"]


def details(**overrides: object) -> CustomerDetails:
    values: dict[str, object] = {
        "profile_id": uuid4(),
        "user_account_id": uuid4(),
        "full_name": "Thandi Mokoena",
        "email": "thandi.mokoena@example.co.za",
        "email_verified": True,
        "phone": "082 441 7719",
        "customer_type": CustomerType.INDIVIDUAL,
        "company_name": None,
        "vat_number": None,
        "id_document_type": IdDocType.SA_ID,
        "id_document_last4": "5083",
        "billing_address_line1": "12 Loop Street",
        "billing_suburb": "Gardens",
        "billing_city": "Cape Town",
        "billing_postal_code": "8001",
        "account_status": AccountStatus.ACTIVE,
        "trade_discount_percent": Decimal("0.00"),
        "no_show_count": 0,
        "home_branch_code": "CBD",
        "member_since": date(2026, 3, 2),
        **overrides,
    }
    return CustomerDetails(**values)


def trade_customer() -> CustomerDetails:
    return details(customer_type=CustomerType.TRADE, company_name="Mokoena Builders")


def new_customer(**overrides: object) -> NewCustomer:
    values: dict[str, object] = {
        "full_name": "Thandi Mokoena",
        "phone": "082 441 7719",
        "id_document_type": IdDocType.SA_ID,
        "id_document_last4": "5083",
        "billing_address_line1": "12 Loop Street",
        "billing_suburb": "Gardens",
        "billing_city": "Cape Town",
        "billing_postal_code": "8001",
        **overrides,
    }
    return NewCustomer.registering(**values)


def refused_field_of(refusal: pytest.ExceptionInfo[ValidationFailure]) -> object:
    return refusal.value.detail[REFUSED_FIELD]


class TestThePasswordRule:
    """At least twelve characters, and no longer than bcrypt reads (BR-45)."""

    def test_the_minimum_is_twelve_characters(self) -> None:
        assert MINIMUM_PASSWORD_LENGTH == 12
        assert security.MINIMUM_PASSWORD_LENGTH == MINIMUM_PASSWORD_LENGTH

    def test_eleven_characters_are_refused_and_twelve_are_accepted(self) -> None:
        with pytest.raises(ValidationFailure) as refusal:
            ensure_password_may_be_chosen(ELEVEN_CHARACTERS)
        assert refusal.value.message == PASSWORD_TOO_SHORT_MESSAGE
        assert refusal.value.rule == PASSWORD_RULE == "BR-45"
        ensure_password_may_be_chosen(TWELVE_CHARACTERS)

    def test_a_password_longer_than_bcrypt_reads_is_refused(self) -> None:
        ensure_password_may_be_chosen("x" * MAXIMUM_PASSWORD_BYTES)
        for too_long in ("x" * (MAXIMUM_PASSWORD_BYTES + 1), SEVENTY_FIVE_BYTES):
            with pytest.raises(ValidationFailure) as refusal:
                ensure_password_may_be_chosen(too_long)
            assert refusal.value.message == PASSWORD_TOO_LONG_MESSAGE

    def test_a_refusal_never_repeats_the_password(self) -> None:
        with pytest.raises(ValidationFailure) as refusal:
            ensure_password_may_be_chosen(ELEVEN_CHARACTERS)
        assert ELEVEN_CHARACTERS not in refusal.value.message
        assert ELEVEN_CHARACTERS not in str(refusal.value.detail)

    @pytest.mark.parametrize("parameter", ["password", "newPassword"])
    def test_the_refusal_names_the_field_the_request_used(self, parameter: str) -> None:
        with pytest.raises(ValidationFailure) as refusal:
            ensure_password_may_be_set(ELEVEN_CHARACTERS, parameter)
        assert refused_parameter_of(refusal.value) == parameter
        assert refusal.value.rule == PASSWORD_RULE
        ensure_password_may_be_set(TWELVE_CHARACTERS, parameter)


class TestWhatACustomerMayEdit:
    """Eight fields and no others, checked together and kept together."""

    def test_the_editable_fields_are_the_eight_of_the_contract(self) -> None:
        assert list(EDITABLE_FIELDS) == [
            "full_name",
            "phone",
            "billing_address_line1",
            "billing_suburb",
            "billing_city",
            "billing_postal_code",
            "company_name",
            "vat_number",
        ]

    def test_an_edit_changes_the_fields_that_were_sent_and_names_them(self) -> None:
        subject = details()
        changed = subject.apply({"billing_city": "  Stellenbosch ", "full_name": "Thandi M"})
        assert changed == ("full_name", "billing_city")
        assert (subject.full_name, subject.billing_city) == ("Thandi M", "Stellenbosch")
        assert subject.billing_suburb == "Gardens"

    def test_a_value_that_is_already_there_is_not_a_change(self) -> None:
        subject = details()
        assert subject.apply({"billing_city": "Cape Town", "vat_number": None}) == ()
        assert subject.apply({}) == ()

    @pytest.mark.parametrize("field", FORBIDDEN_FIELDS)
    def test_a_field_that_is_not_one_of_them_is_refused_by_name(self, field: str) -> None:
        subject = details()
        with pytest.raises(ValidationFailure) as refusal:
            subject.apply({field: "BLACKLISTED", "billing_city": "Stellenbosch"})
        assert refused_field_of(refusal) == field
        assert refusal.value.message == NOT_EDITABLE_MESSAGE
        assert subject.billing_city == "Cape Town"
        assert subject.account_status is AccountStatus.ACTIVE

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_a_required_field_cannot_be_emptied(self, value: str | None) -> None:
        with pytest.raises(ValidationFailure) as refusal:
            details().apply({"phone": value})
        assert refused_field_of(refusal) == "phone"
        assert refusal.value.message == REQUIRED_MESSAGE

    @pytest.mark.parametrize("field", list(EDITABLE_FIELDS))
    def test_a_value_wider_than_its_column_is_refused(self, field: str) -> None:
        limit = EDITABLE_FIELDS[field].max_length
        with pytest.raises(ValidationFailure) as refusal:
            cleaned_value(field, "7" * (limit + 1))
        assert refused_field_of(refusal) == field
        assert refusal.value.message == f"Enter at most {limit} characters."

    @pytest.mark.parametrize("number", ["0824417719", "+27 82 441 7719", "(021) 555-0101"])
    def test_an_ordinary_phone_number_is_accepted(self, number: str) -> None:
        assert cleaned_value("phone", number) == number

    @pytest.mark.parametrize("number", ["12345", "call me maybe", "082 441 77x9", "++27824417719"])
    def test_something_that_is_not_a_phone_number_is_refused(self, number: str) -> None:
        with pytest.raises(ValidationFailure) as refusal:
            cleaned_value("phone", number)
        assert refusal.value.message == PHONE_MESSAGE

    def test_an_optional_field_is_cleared_by_null_or_by_a_blank(self) -> None:
        subject = details(vat_number="4123456789", company_name="Mokoena Builders")
        assert subject.apply({"vat_number": None, "company_name": " "}) == (
            "company_name",
            "vat_number",
        )
        assert (subject.vat_number, subject.company_name) == (None, None)

    def test_a_trade_customer_keeps_a_company_name(self) -> None:
        subject = trade_customer()
        with pytest.raises(ValidationFailure) as refusal:
            subject.apply({"company_name": None, "billing_city": "Stellenbosch"})
        assert refused_field_of(refusal) == "company_name"
        assert refusal.value.message == TRADE_NEEDS_COMPANY_MESSAGE
        assert (subject.company_name, subject.billing_city) == ("Mokoena Builders", "Cape Town")
        assert subject.apply({"company_name": "Mokoena and Sons"}) == ("company_name",)
        assert subject.apply({"phone": "021 555 0101"}) == ("phone",)

    def test_one_refused_value_leaves_every_field_as_it_was(self) -> None:
        subject = details()
        with pytest.raises(ValidationFailure):
            subject.apply({"full_name": "Thandi M", "phone": "nope"})
        assert subject.full_name == "Thandi Mokoena"


class TestWhatAPersonRegisteringSupplies:
    """Trimmed, checked, and never more than an individual in good standing."""

    def test_the_details_are_trimmed_and_the_rest_is_decided_for_them(self) -> None:
        customer = new_customer(full_name="  Thandi Mokoena ", id_document_last4=" 5083 ")
        assert customer.full_name == "Thandi Mokoena"
        assert customer.id_document_last4 == "5083"
        assert customer.customer_type is CustomerType.INDIVIDUAL
        assert customer.account_status is AccountStatus.ACTIVE
        assert customer.trade_discount_percent == Decimal("0.00")

    @pytest.mark.parametrize("last4", ["508", "50831", "50 3", "5-83", ""])
    def test_the_document_ending_is_exactly_four_letters_or_digits(self, last4: str) -> None:
        with pytest.raises(ValidationFailure) as refusal:
            new_customer(id_document_last4=last4)
        assert refused_field_of(refusal) == "id_document_last4"
        assert new_customer(id_document_last4="A1b2").id_document_last4 == "A1b2"

    @pytest.mark.parametrize(
        "field",
        ["full_name", "phone", "billing_address_line1", "billing_suburb", "billing_city"],
    )
    def test_a_blank_detail_is_refused_by_name(self, field: str) -> None:
        with pytest.raises(ValidationFailure) as refusal:
            new_customer(**{field: "  "})
        assert refused_field_of(refusal) == field
        assert refusal.value.message == REQUIRED_MESSAGE


class TestTheNameAFieldHasInARequest:
    """The domain says `billing_city`. A form needs `billingCity`."""

    @pytest.mark.parametrize(
        ("field", "on_the_wire"),
        [
            ("phone", "phone"),
            ("full_name", "fullName"),
            ("billing_address_line1", "billingAddressLine1"),
            ("id_document_last4", "idDocumentLast4"),
        ],
    )
    def test_a_field_is_renamed_for_the_wire(self, field: str, on_the_wire: str) -> None:
        assert wire_name(field) == on_the_wire

    def test_a_refusal_of_the_domain_is_named_as_the_request_named_it(self) -> None:
        with pytest.raises(ValidationFailure) as refusal:
            details().apply({"billing_postal_code": ""})
        translated = refused_field(refusal.value)
        assert refused_parameter_of(translated) == "billingPostalCode"
        assert translated.message == REQUIRED_MESSAGE

    def test_an_address_is_compared_in_lower_case_with_no_space_around_it(self) -> None:
        assert normalised_email("  Thandi.Mokoena@Example.co.za ") == (
            "thandi.mokoena@example.co.za"
        )
