"""Request and response models for the HTTP boundary.

Field names on the wire match `frontend/src/shared/types.ts`, so the React
client consumes these without a translation layer. That is why the responses
are camelCase while the database and the domain are snake_case: the boundary
translates once, here, rather than in every component.

Role is the other translation. The database stores the canonical
`CUSTOMER`, `COUNTER_STAFF` and `ADMIN`, and the frontend union is
`customer`, `counter` and `admin`. The mapping is explicit and total, so a new
role cannot be added without this file failing loudly.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.domain.enums import UserRole

# Wire values, matching the Role union in the frontend type module.
WIRE_CUSTOMER = "customer"
WIRE_COUNTER = "counter"
WIRE_ADMIN = "admin"

ROLE_TO_WIRE: dict[UserRole, str] = {
    UserRole.CUSTOMER: WIRE_CUSTOMER,
    UserRole.COUNTER_STAFF: WIRE_COUNTER,
    UserRole.ADMIN: WIRE_ADMIN,
}
WIRE_TO_ROLE: dict[str, UserRole] = {wire: role for role, wire in ROLE_TO_WIRE.items()}

EMAIL_MAX_LENGTH = 254
EMAIL_MIN_LENGTH = 5
# bcrypt reads at most 72 bytes, so anything longer is refused rather than
# silently truncated. The policy minimum is deliberately not here. It belongs to
# account creation and is enforced by app.infrastructure.security.hash_password,
# which is the one place a password is chosen rather than merely presented.
MAXIMUM_PASSWORD_LENGTH = 72
MINIMUM_QUANTITY = 1
MAXIMUM_QUANTITY = 10


def wire_role(role: UserRole) -> str:
    """Return the frontend facing value for a stored role.

    Raises:
        KeyError: If a role has been added without extending the mapping. This
            is deliberate. A silent fallback would ship an unauthorised screen.

    """
    return ROLE_TO_WIRE[role]


class CamelModel(BaseModel):
    """Base model that serialises snake_case fields as camelCase on the wire."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class SignInRequest(BaseModel):
    """Credentials posted to the sign in endpoint.

    The address is checked structurally rather than with a full RFC 5322
    parser. Deliverability is proved by the verification email, not by a
    regular expression, so a validation library here would be a dependency
    that buys nothing.

    The password carries no minimum length. It deliberately did once, and that
    was a defect: a wrong password of eleven characters came back as a 422
    naming the length rule, while a wrong password of twelve came back as a 401.
    That difference is an oracle. It tells an attacker something about the value
    they submitted, and it contradicts control C-14 in the security section,
    which states that an unknown address and a wrong password are answered
    identically in body, status and timing. Length policy applies when a
    password is chosen, not when one is presented, so it lives in
    `security.hash_password` (BR-45) and not here. The maximum stays, because it
    is a property of bcrypt rather than a rule about the account, and it applies
    to the unknown address and the wrong password alike.
    """

    email: Annotated[str, Field(min_length=EMAIL_MIN_LENGTH, max_length=EMAIL_MAX_LENGTH)]
    password: Annotated[str, Field(max_length=MAXIMUM_PASSWORD_LENGTH)]

    @field_validator("email")
    @classmethod
    def check_email_shape(cls, value: str) -> str:
        """Normalise the address and reject anything that is not local@domain."""
        candidate = value.strip().lower()
        local, separator, domain = candidate.partition("@")
        if not separator or not local or "." not in domain or domain.startswith("."):
            raise ValueError(
                "email must be an address of the form name@example.co.za. "
                f"Received {value!r}."
            )
        return candidate


class UserResponse(CamelModel):
    """The signed in account, shaped like the frontend UserAccount type."""

    id: UUID
    name: str
    email: str
    role: str
    branch_code: str | None = Field(default=None, serialization_alias="branchCode")
    active: bool


class TokenResponse(CamelModel):
    """The access token and the account it belongs to."""

    access_token: str = Field(serialization_alias="accessToken")
    token_type: str = Field(default="bearer", serialization_alias="tokenType")
    expires_in: int = Field(serialization_alias="expiresIn")
    user: UserResponse


class HealthResponse(CamelModel):
    """What the health endpoint reports about its own dependencies."""

    status: str
    environment: str
    database_reachable: bool = Field(serialization_alias="databaseReachable")
    btree_gist_installed: bool = Field(serialization_alias="btreeGistInstalled")


class AllocationRequest(CamelModel):
    """A booking request posted by the client.

    The period is half open. `endDate` is the day the unit comes back and is
    not charged, which is the same rule the exclusion constraint enforces.
    """

    product_model_id: UUID = Field(validation_alias="productModelId")
    branch_id: UUID = Field(validation_alias="branchId")
    start_date: date = Field(validation_alias="startDate")
    end_date: date = Field(validation_alias="endDate")
    quantity: Annotated[int, Field(ge=MINIMUM_QUANTITY, le=MAXIMUM_QUANTITY)] = 1
    customer_user_id: UUID | None = Field(default=None, validation_alias="customerUserId")

    @field_validator("end_date")
    @classmethod
    def check_period_order(cls, value: date, info: ValidationInfo) -> date:
        """Reject a reversed period before the domain has to."""
        start = info.data.get("start_date")
        if isinstance(start, date) and value <= start:
            raise ValueError(
                "endDate must be strictly after startDate. A hire period is half open, "
                f"so a hire from {start.isoformat()} to {value.isoformat()} has no days in it."
            )
        return value


class AllocatedAssetResponse(CamelModel):
    """One physical unit held by the booking."""

    allocation_id: UUID = Field(serialization_alias="allocationId")
    asset_id: UUID = Field(serialization_alias="assetId")
    asset_tag: str = Field(serialization_alias="assetTag")


class AllocationResponse(CamelModel):
    """The committed booking returned to the client."""

    reservation_id: UUID = Field(serialization_alias="reservationId")
    reference: str
    reservation_line_id: UUID = Field(serialization_alias="reservationLineId")
    status: str
    start_date: date = Field(serialization_alias="startDate")
    end_date: date = Field(serialization_alias="endDate")
    allocated: list[AllocatedAssetResponse]


class ProblemDetail(BaseModel):
    """An RFC 9457 problem document.

    `type` is a stable slug, not a resolvable URL, because this API is not a
    public specification and inventing a documentation URL that does not exist
    is worse than a slug that does.
    """

    type: str
    title: str
    status: int
    detail: str
    instance: str | None = None
    errors: dict[str, object] | None = None
