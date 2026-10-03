"""A walk-in customer, which is a customer profile with no login (US-20).

Somebody who comes to the counter without an online account is registered by
the counter assistant. They get a customer profile and no sign in account, so
they never receive a password, a verification message or an email at all, and
a booking made for them at the counter is theirs all the same.

The details are checked by the same rules a person registering online is
checked by (`app.domain.customer_account`), with two differences. The counter
chooses whether the customer hires as an individual or as a trade, and a trade
customer has to have a company name. The name staff see is called the display
name here, which is the name of its column, and a refusal of it names that
field.

The standing is not for the counter to choose. A walk-in starts in good
standing with no trade discount, like everybody else.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.domain.customer_account import (
    COMPANY_NAME,
    FULL_NAME,
    REFUSED_FIELD,
    TRADE_NEEDS_COMPANY_MESSAGE,
    VAT_NUMBER,
    NewCustomer,
    cleaned_value,
)
from app.domain.enums import CustomerType, IdDocType
from app.domain.errors import ValidationFailure

DISPLAY_NAME: Final[str] = "display_name"


@dataclass(frozen=True, slots=True)
class WalkInCustomer:
    """What the counter records about a customer who has no login.

    Attributes:
        details: The name, phone, identity document and billing address,
            checked as they are for somebody registering online. The name is
            the display name.
        customer_type: Whether they hire as an individual or as a trade.
        company_name: The company of a trade customer, or None.
        vat_number: Its VAT number, or None.

    """

    details: NewCustomer
    customer_type: CustomerType
    company_name: str | None
    vat_number: str | None

    @classmethod
    def registering(
        cls,
        *,
        display_name: str,
        phone: str,
        id_document_type: IdDocType,
        id_document_last4: str,
        billing_address_line1: str,
        billing_suburb: str,
        billing_city: str,
        billing_postal_code: str,
        customer_type: CustomerType,
        company_name: str | None,
        vat_number: str | None,
    ) -> WalkInCustomer:
        """Return the details of a walk-in, trimmed and checked.

        Raises:
            ValidationFailure: If a value is blank, too long or misshapen, or
                a trade customer has no company name. The detail names the
                field the way this module and `app.domain.customer_account`
                name it.

        """
        try:
            details = NewCustomer.registering(
                full_name=display_name,
                phone=phone,
                id_document_type=id_document_type,
                id_document_last4=id_document_last4,
                billing_address_line1=billing_address_line1,
                billing_suburb=billing_suburb,
                billing_city=billing_city,
                billing_postal_code=billing_postal_code,
            )
        except ValidationFailure as failure:
            if failure.detail.get(REFUSED_FIELD) != FULL_NAME:
                raise
            raise ValidationFailure(failure.message, {REFUSED_FIELD: DISPLAY_NAME}) from failure
        company = cleaned_value(COMPANY_NAME, company_name)
        if customer_type is CustomerType.TRADE and company is None:
            raise ValidationFailure(TRADE_NEEDS_COMPANY_MESSAGE, {REFUSED_FIELD: COMPANY_NAME})
        return cls(
            details=details,
            customer_type=customer_type,
            company_name=company,
            vat_number=cleaned_value(VAT_NUMBER, vat_number),
        )
