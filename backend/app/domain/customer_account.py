"""A customer's own details, as they give them at registration and edit them later.

Two things live here (US-01, US-05).

`NewCustomer` is what a person tells Toolshed Hire about themselves to open an
account. Everything else about the profile is decided for them. It is an
individual account in good standing with no trade discount, because those
three are for a branch or an administrator to change and never for the person
registering (C-26).

`CustomerDetails` is the profile as its owner sees it, and `apply` is the only
way it changes. It takes the eight contact and billing fields and nothing
else. A field that is not one of them is refused by name, so a submitted
account status, role or discount can never reach the database through here.

A field is named the way this module names it, for example `billing_city`.
The rule that refused it is said in a plain sentence, because the sentence is
shown beside the input.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Final
from uuid import UUID

from app.domain.enums import AccountStatus, CustomerType, IdDocType
from app.domain.errors import ValidationFailure
from app.domain.identity import NO_TRADE_DISCOUNT

# The member of the detail bag that names the refused field.
REFUSED_FIELD: Final[str] = "field"

FULL_NAME: Final[str] = "full_name"
PHONE: Final[str] = "phone"
BILLING_ADDRESS_LINE1: Final[str] = "billing_address_line1"
BILLING_SUBURB: Final[str] = "billing_suburb"
BILLING_CITY: Final[str] = "billing_city"
BILLING_POSTAL_CODE: Final[str] = "billing_postal_code"
COMPANY_NAME: Final[str] = "company_name"
VAT_NUMBER: Final[str] = "vat_number"
ID_DOCUMENT_LAST4: Final[str] = "id_document_last4"

# Only the last four characters of an identity document are ever kept.
_ID_DOCUMENT_LAST4_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9]{4}$")
PHONE_MINIMUM_DIGITS: Final[int] = 7
PHONE_PUNCTUATION: Final[frozenset[str]] = frozenset(" ()-")
INTERNATIONAL_PREFIX: Final[str] = "+"

REQUIRED_MESSAGE: Final[str] = "This is needed. Please fill it in."
TOO_LONG_MESSAGE: Final[str] = "Enter at most {limit} characters."
PHONE_MESSAGE: Final[str] = (
    "Enter a phone number of at least seven digits. Spaces, brackets and hyphens are fine."
)
ID_DOCUMENT_LAST4_MESSAGE: Final[str] = (
    "Enter the last four characters of the document, letters or digits only."
)
NOT_EDITABLE_MESSAGE: Final[str] = "This cannot be changed here."
TRADE_NEEDS_COMPANY_MESSAGE: Final[str] = "A trade account needs its company name."


@dataclass(frozen=True, slots=True)
class FieldRule:
    """What one editable field has to satisfy.

    Attributes:
        max_length: The width of the column the value is stored in.
        required: False for a field that may be left empty, which stores null.

    """

    max_length: int
    required: bool = True


# The fields a customer may edit, in the order a change is reported in. The
# widths are those of the columns in the design document.
EDITABLE_FIELDS: Final[Mapping[str, FieldRule]] = MappingProxyType(
    {
        FULL_NAME: FieldRule(max_length=120),
        PHONE: FieldRule(max_length=20),
        BILLING_ADDRESS_LINE1: FieldRule(max_length=120),
        BILLING_SUBURB: FieldRule(max_length=80),
        BILLING_CITY: FieldRule(max_length=80),
        BILLING_POSTAL_CODE: FieldRule(max_length=10),
        COMPANY_NAME: FieldRule(max_length=120, required=False),
        VAT_NUMBER: FieldRule(max_length=20, required=False),
    }
)


def _refusal(field: str, message: str) -> ValidationFailure:
    """Return the failure for one refused field."""
    return ValidationFailure(message, {REFUSED_FIELD: field})


def _is_phone_number(text: str) -> bool:
    """Return True for digits with ordinary punctuation and an optional leading plus."""
    body = text.removeprefix(INTERNATIONAL_PREFIX)
    digits = sum(character.isdigit() for character in body)
    plain = all(character.isdigit() or character in PHONE_PUNCTUATION for character in body)
    return plain and digits >= PHONE_MINIMUM_DIGITS


def _checked_text(field: str, value: str) -> str:
    """Return a value trimmed, or refuse it for being blank, too long or misshapen."""
    text = value.strip()
    if not text:
        raise _refusal(field, REQUIRED_MESSAGE)
    limit = EDITABLE_FIELDS[field].max_length
    if len(text) > limit:
        raise _refusal(field, TOO_LONG_MESSAGE.format(limit=limit))
    if field == PHONE and not _is_phone_number(text):
        raise _refusal(field, PHONE_MESSAGE)
    return text


def cleaned_value(field: str, value: str | None) -> str | None:
    """Return the value one editable field would be stored as.

    Args:
        field: The field, by the name this module gives it.
        value: The value as it was submitted. None and a blank one mean the
            same thing, which is that the field is to be left empty.

    Returns:
        The trimmed value, or None for an optional field left empty.

    Raises:
        ValidationFailure: If the field is not one a customer may edit, if a
            required field is left empty, or if the value does not fit. The
            detail names the field.

    """
    rule = EDITABLE_FIELDS.get(field)
    if rule is None:
        raise _refusal(field, NOT_EDITABLE_MESSAGE)
    if value is None or not value.strip():
        if rule.required:
            raise _refusal(field, REQUIRED_MESSAGE)
        return None
    return _checked_text(field, value)


@dataclass(frozen=True, slots=True)
class NewCustomer:
    """What a person supplies about themselves to open a customer account.

    Attributes:
        full_name: The name of the person, which is also the name staff see.
        phone: The number the branch can reach them on.
        id_document_type: The kind of identity document they will present.
        id_document_last4: Its last four characters. The rest is never sent.
        billing_address_line1: The first line of the billing address.
        billing_suburb: The suburb.
        billing_city: The city.
        billing_postal_code: The postal code.
        customer_type: Always an individual at registration.
        account_status: Always in good standing at registration.
        trade_discount_percent: Always none at registration.

    """

    full_name: str
    phone: str
    id_document_type: IdDocType
    id_document_last4: str
    billing_address_line1: str
    billing_suburb: str
    billing_city: str
    billing_postal_code: str
    customer_type: CustomerType = CustomerType.INDIVIDUAL
    account_status: AccountStatus = AccountStatus.ACTIVE
    trade_discount_percent: Decimal = NO_TRADE_DISCOUNT

    @classmethod
    def registering(
        cls,
        *,
        full_name: str,
        phone: str,
        id_document_type: IdDocType,
        id_document_last4: str,
        billing_address_line1: str,
        billing_suburb: str,
        billing_city: str,
        billing_postal_code: str,
    ) -> NewCustomer:
        """Return the details of somebody registering, trimmed and checked.

        Raises:
            ValidationFailure: If a value is blank, too long or misshapen. The
                detail names the field.

        """
        last4 = id_document_last4.strip()
        if not _ID_DOCUMENT_LAST4_PATTERN.match(last4):
            raise _refusal(ID_DOCUMENT_LAST4, ID_DOCUMENT_LAST4_MESSAGE)
        return cls(
            full_name=_checked_text(FULL_NAME, full_name),
            phone=_checked_text(PHONE, phone),
            id_document_type=id_document_type,
            id_document_last4=last4,
            billing_address_line1=_checked_text(BILLING_ADDRESS_LINE1, billing_address_line1),
            billing_suburb=_checked_text(BILLING_SUBURB, billing_suburb),
            billing_city=_checked_text(BILLING_CITY, billing_city),
            billing_postal_code=_checked_text(BILLING_POSTAL_CODE, billing_postal_code),
        )


@dataclass(slots=True)
class CustomerDetails:
    """A customer's profile and the account behind it, as the customer sees them.

    Attributes:
        profile_id: The key of the customer profile.
        user_account_id: The sign in account the profile belongs to.
        full_name: The name on the account, which is also the display name.
        email: The address the customer signs in with.
        email_verified: Whether they have proved that address.
        phone: The contact number.
        customer_type: Whether they hire as an individual or as a trade.
        company_name: The company of a trade customer.
        vat_number: Its VAT number, when it has one.
        id_document_type: The kind of identity document on file.
        id_document_last4: Its last four characters.
        billing_address_line1: The first line of the billing address.
        billing_suburb: The suburb.
        billing_city: The city.
        billing_postal_code: The postal code.
        account_status: The standing of the customer (BR-18).
        trade_discount_percent: The discount a trade customer is given.
        no_show_count: How many bookings they did not collect.
        home_branch_code: The code of the branch that registered them.
        member_since: The business day the profile was opened.

    """

    profile_id: UUID
    user_account_id: UUID
    full_name: str
    email: str
    email_verified: bool
    phone: str
    customer_type: CustomerType
    company_name: str | None
    vat_number: str | None
    id_document_type: IdDocType
    id_document_last4: str
    billing_address_line1: str
    billing_suburb: str
    billing_city: str
    billing_postal_code: str
    account_status: AccountStatus
    trade_discount_percent: Decimal
    no_show_count: int
    home_branch_code: str
    member_since: date

    def apply(self, changes: Mapping[str, str | None]) -> tuple[str, ...]:
        """Take the edits a customer asked for, all of them or none.

        Every value is checked before any is kept, so a refused field leaves
        the details exactly as they were.

        Args:
            changes: The new value of each field the customer sent, by the
                name this module gives the field.

        Returns:
            The names of the fields whose value is now different, in the
            order of `EDITABLE_FIELDS`. Empty when nothing changed.

        Raises:
            ValidationFailure: If a field may not be edited, if a value is
                refused, or if a trade customer would be left with no company
                name. The detail names the field.

        """
        cleaned = {field: cleaned_value(field, value) for field, value in changes.items()}
        company_name = cleaned.get(COMPANY_NAME) if COMPANY_NAME in cleaned else self.company_name
        if self.customer_type is CustomerType.TRADE and company_name is None:
            raise _refusal(COMPANY_NAME, TRADE_NEEDS_COMPANY_MESSAGE)
        changed = tuple(
            field
            for field in EDITABLE_FIELDS
            if field in cleaned and getattr(self, field) != cleaned[field]
        )
        for field in changed:
            setattr(self, field, cleaned[field])
        return changed
