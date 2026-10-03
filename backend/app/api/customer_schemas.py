"""Request and response models for the counter's customer routes.

Field names on the wire are camelCase, as everywhere else at this boundary.

The walk-in request names every field it accepts and refuses any other with a
422 that names it, so a submitted `accountStatus` or `tradeDiscountPercent`
never reaches the database. Its checks are about shape, which is a type, a
length and a pattern. The rules, for example that a trade customer has a
company name, are in the domain, and both refuse a field in the same place,
under `errors.fields`.

A customer is written as `CustomerSummary`, with no full address and no
document number, because the counter never needs either.
"""

from __future__ import annotations

from typing import Annotated, Final
from uuid import UUID

from pydantic import Field, StringConstraints

from app.api.account_schemas import ID_DOCUMENT_LAST4_PATTERN, StrictRequest
from app.api.catalogue_schemas import Percentage
from app.api.schemas import CamelModel, ProblemDetail
from app.domain.customer_account import (
    BILLING_ADDRESS_LINE1,
    BILLING_CITY,
    BILLING_POSTAL_CODE,
    BILLING_SUBURB,
    COMPANY_NAME,
    EDITABLE_FIELDS,
    FULL_NAME,
    PHONE,
    VAT_NUMBER,
)
from app.domain.enums import AccountStatus, CustomerType, IdDocType

BRANCH_CODE_MAX_LENGTH: Final[int] = 4

UNKNOWN_CUSTOMER_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "There is no customer with this key.",
}
WRONG_BRANCH_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "The caller is not staff, or counter staff named another branch.",
}

TrimmedText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _width(field: str) -> int:
    """Return the widest value one contact field may hold."""
    return EDITABLE_FIELDS[field].max_length


class WalkInRequest(StrictRequest):
    """What the counter records to register a customer who has no login.

    `branchCode` is for an administrator, who belongs to no branch. Counter
    staff may leave it out, and the customer is registered at their branch.
    `companyName` is required for a trade customer.
    """

    display_name: Annotated[TrimmedText, Field(max_length=_width(FULL_NAME))] = Field(
        validation_alias="displayName"
    )
    phone: Annotated[TrimmedText, Field(max_length=_width(PHONE))]
    id_document_type: IdDocType = Field(validation_alias="idDocumentType")
    id_document_last4: Annotated[str, Field(pattern=ID_DOCUMENT_LAST4_PATTERN)] = Field(
        validation_alias="idDocumentLast4"
    )
    billing_address_line1: Annotated[
        TrimmedText, Field(max_length=_width(BILLING_ADDRESS_LINE1))
    ] = Field(validation_alias="billingAddressLine1")
    billing_suburb: Annotated[TrimmedText, Field(max_length=_width(BILLING_SUBURB))] = Field(
        validation_alias="billingSuburb"
    )
    billing_city: Annotated[TrimmedText, Field(max_length=_width(BILLING_CITY))] = Field(
        validation_alias="billingCity"
    )
    billing_postal_code: Annotated[
        TrimmedText, Field(max_length=_width(BILLING_POSTAL_CODE))
    ] = Field(validation_alias="billingPostalCode")
    customer_type: CustomerType = Field(
        default=CustomerType.INDIVIDUAL, validation_alias="customerType"
    )
    company_name: Annotated[str, Field(max_length=_width(COMPANY_NAME))] | None = Field(
        default=None, validation_alias="companyName"
    )
    vat_number: Annotated[str, Field(max_length=_width(VAT_NUMBER))] | None = Field(
        default=None, validation_alias="vatNumber"
    )
    branch_code: Annotated[TrimmedText, Field(max_length=BRANCH_CODE_MAX_LENGTH)] | None = Field(
        default=None, validation_alias="branchCode"
    )


class CustomerSummaryResponse(CamelModel):
    """A customer as the counter sees one.

    `email` is null and `hasLogin` is false for a walk-in, who has no account.
    """

    id: UUID
    display_name: str = Field(serialization_alias="displayName")
    email: str | None
    phone: str
    has_login: bool = Field(serialization_alias="hasLogin")
    email_verified: bool = Field(serialization_alias="emailVerified")
    customer_type: CustomerType = Field(serialization_alias="customerType")
    company_name: str | None = Field(serialization_alias="companyName")
    id_document_type: IdDocType = Field(serialization_alias="idDocumentType")
    id_document_last4: str = Field(serialization_alias="idDocumentLast4")
    billing_suburb: str = Field(serialization_alias="billingSuburb")
    billing_city: str = Field(serialization_alias="billingCity")
    account_status: AccountStatus = Field(serialization_alias="accountStatus")
    trade_discount_percent: Percentage = Field(serialization_alias="tradeDiscountPercent")
    no_show_count: int = Field(serialization_alias="noShowCount")
    home_branch_code: str = Field(serialization_alias="homeBranchCode")


class CustomerPageResponse(CamelModel):
    """One page of the customers a search found, best match first."""

    items: list[CustomerSummaryResponse]
    page: int
    page_size: int = Field(serialization_alias="pageSize")
    total: int
