"""Request and response models for registration, account security and the profile.

Field names on the wire are camelCase, as everywhere else at this boundary.

The two models a customer fills in themselves refuse unknown fields (C-26).
Each is a list of what may be sent and nothing else, so a submitted
`accountStatus`, `role` or `tradeDiscountPercent` is answered 422 with the
field named, and never reaches a use case. They are separate from the tables
they end up in for the same reason. Nothing is copied from a request onto a
row by name.

The checks here are about shape, which is a type, a length and a pattern. The
rules, for example that a trade customer keeps a company name, are in the
domain, and both refuse a field in the same place, under `errors.fields`.

A password chosen here carries the minimum length of the password rule. The
sign in request deliberately does not, for the reason its own docstring gives.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Final, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.api.catalogue_schemas import Percentage
from app.api.schemas import (
    EMAIL_MAX_LENGTH,
    EMAIL_MIN_LENGTH,
    MAXIMUM_PASSWORD_LENGTH,
    CamelModel,
    ProblemDetail,
    normalised_email_address,
)
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
from app.domain.password_policy import MINIMUM_PASSWORD_LENGTH

BRANCH_CODE_MAX_LENGTH: Final[int] = 4
ID_DOCUMENT_LAST4_PATTERN: Final[str] = r"^[A-Za-z0-9]{4}$"
# A token is 43 characters. The bound only keeps a request from carrying a
# megabyte where a token belongs.
TOKEN_MAX_LENGTH: Final[int] = 200

REFUSED_BODY_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "A field was refused. `errors.fields` names it.",
}
TOO_MANY_ATTEMPTS_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "Too many attempts. `Retry-After` carries the wait in seconds.",
}
LINK_INVALID_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": (
        "The token is unknown, already used or out of time. The answer is the same for "
        "all three."
    ),
}
NO_PROFILE_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "The account has no customer profile.",
}

EmailAddress = Annotated[
    str,
    Field(min_length=EMAIL_MIN_LENGTH, max_length=EMAIL_MAX_LENGTH),
    AfterValidator(normalised_email_address),
]
ChosenPassword = Annotated[
    str, Field(min_length=MINIMUM_PASSWORD_LENGTH, max_length=MAXIMUM_PASSWORD_LENGTH)
]
Token = Annotated[str, Field(min_length=1, max_length=TOKEN_MAX_LENGTH)]
TrimmedText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _width(field: str) -> int:
    """Return the widest value one contact field may hold."""
    return EDITABLE_FIELDS[field].max_length


class StrictRequest(BaseModel):
    """A request body that names every field it accepts and refuses any other."""

    model_config = ConfigDict(extra="forbid")


class RegisterRequest(StrictRequest):
    """What a person sends to open a customer account.

    Only the last four characters of the identity document are sent. The full
    number never reaches the service.
    """

    email: EmailAddress
    password: ChosenPassword
    full_name: Annotated[TrimmedText, Field(max_length=_width(FULL_NAME))] = Field(
        validation_alias="fullName"
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
    home_branch_code: Annotated[TrimmedText, Field(max_length=BRANCH_CODE_MAX_LENGTH)] = Field(
        validation_alias="homeBranchCode"
    )
    accepts_privacy_notice: Literal[True] = Field(validation_alias="acceptsPrivacyNotice")


class EmailDeliverableResponse(CamelModel):
    """Whether a message for the address would be delivered in this environment.

    False when the environment only delivers mail to one address and this is
    not it. It never depends on whether the address has an account.
    """

    email_deliverable: bool = Field(serialization_alias="emailDeliverable")


class TokenRequest(BaseModel):
    """The token of a verification link."""

    token: Token


class PasswordResetRequest(BaseModel):
    """The address a reset link is asked for."""

    email: EmailAddress


class PasswordResetCompletionRequest(BaseModel):
    """The token of a reset link and the password chosen with it."""

    token: Token
    new_password: ChosenPassword = Field(validation_alias="newPassword")


class ProfileUpdateRequest(StrictRequest):
    """The contact and billing fields a customer may change, each of them optional.

    A field that is left out is left alone. `companyName` and `vatNumber` may
    be sent as null or as an empty string to clear them.
    """

    full_name: Annotated[TrimmedText, Field(max_length=_width(FULL_NAME))] | None = Field(
        default=None, validation_alias="fullName"
    )
    phone: Annotated[TrimmedText, Field(max_length=_width(PHONE))] | None = None
    billing_address_line1: (
        Annotated[TrimmedText, Field(max_length=_width(BILLING_ADDRESS_LINE1))] | None
    ) = Field(default=None, validation_alias="billingAddressLine1")
    billing_suburb: Annotated[TrimmedText, Field(max_length=_width(BILLING_SUBURB))] | None = (
        Field(default=None, validation_alias="billingSuburb")
    )
    billing_city: Annotated[TrimmedText, Field(max_length=_width(BILLING_CITY))] | None = Field(
        default=None, validation_alias="billingCity"
    )
    billing_postal_code: (
        Annotated[TrimmedText, Field(max_length=_width(BILLING_POSTAL_CODE))] | None
    ) = Field(default=None, validation_alias="billingPostalCode")
    company_name: Annotated[str, Field(max_length=_width(COMPANY_NAME))] | None = Field(
        default=None, validation_alias="companyName"
    )
    vat_number: Annotated[str, Field(max_length=_width(VAT_NUMBER))] | None = Field(
        default=None, validation_alias="vatNumber"
    )


class ProfileResponse(CamelModel):
    """A customer's own details.

    `accountStatus`, `tradeDiscountPercent` and `noShowCount` are shown and
    cannot be changed by the customer.
    """

    full_name: str = Field(serialization_alias="fullName")
    email: str
    email_verified: bool = Field(serialization_alias="emailVerified")
    phone: str
    customer_type: CustomerType = Field(serialization_alias="customerType")
    company_name: str | None = Field(serialization_alias="companyName")
    vat_number: str | None = Field(serialization_alias="vatNumber")
    id_document_type: IdDocType = Field(serialization_alias="idDocumentType")
    id_document_last4: str = Field(serialization_alias="idDocumentLast4")
    billing_address_line1: str = Field(serialization_alias="billingAddressLine1")
    billing_suburb: str = Field(serialization_alias="billingSuburb")
    billing_city: str = Field(serialization_alias="billingCity")
    billing_postal_code: str = Field(serialization_alias="billingPostalCode")
    account_status: AccountStatus = Field(serialization_alias="accountStatus")
    trade_discount_percent: Percentage = Field(serialization_alias="tradeDiscountPercent")
    no_show_count: int = Field(serialization_alias="noShowCount")
    home_branch_code: str = Field(serialization_alias="homeBranchCode")
    member_since: date = Field(serialization_alias="memberSince")
