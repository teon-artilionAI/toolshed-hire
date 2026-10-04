"""Request and response models of user and role management, `AdminUser` and the customer holds.

Field names on the wire are camelCase, as everywhere else at this boundary. An
instant is ISO 8601 with the offset of Cape Town. A list is `{"items": [...],
"page": 1, "pageSize": 20, "total": 0}`.

A new staff account names its address, name, phone, role and branch. An edit
names any of the name, the phone, the role and the branch. A field an edit
leaves out keeps its value, and a field it sends as null is cleared, which the
phone and the branch allow and the name and the role do not. Every body
refuses a field it does not know, so a body that sends a password or an
address to change is refused naming it. No request carries a password and no
response holds one.

The checks here are about shape, which is a type, a length and a pattern. The
rules, for example that counter staff need a branch, are in the domain, and
both refuse a field in the same place, under `errors.fields`.
"""

from __future__ import annotations

from typing import Annotated, Final
from uuid import UUID

from pydantic import Field, field_validator

from app.api.account_schemas import EmailAddress, StrictRequest
from app.api.admin_catalogue_schemas import refuse_null
from app.api.admin_schemas import ReasonText
from app.api.reservation_schemas import BRANCH_CODE_MAX_LENGTH, Timestamp, TrimmedText
from app.api.schemas import CamelModel, ProblemDetail
from app.domain.customer_account import EDITABLE_FIELDS, FULL_NAME, PHONE
from app.domain.enums import AccountStatus, UserRole

FullNameText = Annotated[TrimmedText, Field(max_length=EDITABLE_FIELDS[FULL_NAME].max_length)]
# Blank is accepted here and keeps no number. The domain holds a number that
# is given to the rule a customer's number is held to.
PhoneText = Annotated[str, Field(max_length=EDITABLE_FIELDS[PHONE].max_length)]
BranchCodeText = Annotated[TrimmedText, Field(max_length=BRANCH_CODE_MAX_LENGTH)]

UNKNOWN_STAFF_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "No staff account has this key. A customer's account is not one.",
}
STAFF_CHANGE_REFUSED_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": (
        "The account is the last active administrator, which can never be deactivated or "
        "given another role, or it is the caller's own account, which the caller cannot "
        "deactivate. `detail` says which."
    ),
}
NO_LONGER_ADMINISTRATOR_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": (
        "The caller is not an administrator, or stopped being an active one before the change "
        "could be made."
    ),
}


class StaffCreateRequest(StrictRequest):
    """A new staff account. The person chooses their own password through the link they are sent.

    `branchCode` is required for counter staff and must be null for an administrator.
    """

    email: EmailAddress
    full_name: FullNameText = Field(validation_alias="fullName")
    phone: PhoneText | None = None
    role: UserRole
    branch_code: BranchCodeText | None = Field(default=None, validation_alias="branchCode")


class StaffUpdateRequest(StrictRequest):
    """The fields of a staff account to change, any of them. Never the address or a password."""

    full_name: FullNameText | None = Field(default=None, validation_alias="fullName")
    phone: PhoneText | None = None
    role: UserRole | None = None
    branch_code: BranchCodeText | None = Field(default=None, validation_alias="branchCode")

    @field_validator("full_name", "role", mode="before")
    @classmethod
    def not_null(cls, value: object) -> object:
        """Refuse null for the name and the role, which every staff account has."""
        return refuse_null(value)


class DeactivationRequest(StrictRequest):
    """Why an account is being stopped from signing in. The audit event keeps it."""

    reason: ReasonText


class CustomerStatusRequest(StrictRequest):
    """The standing a customer is to have, and why. The audit event keeps the reason."""

    account_status: AccountStatus = Field(validation_alias="accountStatus")
    reason: ReasonText


class AdminUserResponse(CamelModel):
    """One staff account as the administrator sees it, never with anything about a password.

    `branchCode` is null for an administrator. `lockedUntil` is when a lock
    after failed sign ins ends, and null when there has been none since the
    last success.
    """

    id: UUID
    email: str
    full_name: str = Field(serialization_alias="fullName")
    phone: str | None
    role: UserRole
    branch_code: str | None = Field(serialization_alias="branchCode")
    is_active: bool = Field(serialization_alias="isActive")
    email_verified: bool = Field(serialization_alias="emailVerified")
    last_login_at: Timestamp | None = Field(serialization_alias="lastLoginAt")
    locked_until: Timestamp | None = Field(serialization_alias="lockedUntil")
    created_at: Timestamp = Field(serialization_alias="createdAt")


class StaffCreatedResponse(CamelModel):
    """A new staff account, and whether the email with the link to choose a password was taken.

    `emailDeliverable` is false when the message could not be handed to the
    email provider. The person then asks for a new link from the sign in page
    once mail reaches them.
    """

    user: AdminUserResponse
    email_deliverable: bool = Field(serialization_alias="emailDeliverable")


class AdminUserPageResponse(CamelModel):
    """One page of the staff accounts, by name."""

    items: list[AdminUserResponse]
    page: int
    page_size: int = Field(serialization_alias="pageSize")
    total: int


__all__ = [
    "NO_LONGER_ADMINISTRATOR_RESPONSE",
    "STAFF_CHANGE_REFUSED_RESPONSE",
    "UNKNOWN_STAFF_RESPONSE",
    "AdminUserPageResponse",
    "AdminUserResponse",
    "CustomerStatusRequest",
    "DeactivationRequest",
    "StaffCreateRequest",
    "StaffCreatedResponse",
    "StaffUpdateRequest",
]
