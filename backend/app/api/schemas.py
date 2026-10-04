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

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
# How the client is told to present the access token.
BEARER_TOKEN_TYPE = "Bearer"
MAXIMUM_QUANTITY = 10


def wire_role(role: UserRole) -> str:
    """Return the frontend facing value for a stored role.

    Raises:
        KeyError: If a role has been added without extending the mapping. This
            is deliberate. A silent fallback would ship an unauthorised screen.

    """
    return ROLE_TO_WIRE[role]


def normalised_email_address(value: str) -> str:
    """Return an address in lower case, or refuse anything that is not local@domain.

    Raises:
        ValueError: If the value has no local part, no `@` or no dot in its
            domain. Every request that carries an address checks it here.

    """
    candidate = value.strip().lower()
    local, separator, domain = candidate.partition("@")
    if not separator or not local or "." not in domain or domain.startswith("."):
        raise ValueError(
            f"email must be an address of the form name@example.co.za. Received {value!r}."
        )
    return candidate


class CamelModel(BaseModel):
    """Base model that serialises snake_case fields as camelCase on the wire."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class LoginRequest(BaseModel):
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
        return normalised_email_address(value)


class UserResponse(CamelModel):
    """The signed in account, as every session response and `/api/me` return it.

    `branchCode` is null unless the account is counter staff.

    `emailDeliverable` is false when this environment would not hand a message
    for the account's address to the email provider, because email is off or
    because mail goes to one approved address and this is not it. It is the
    same rule the account routes answer with, and it depends on the
    configuration and the address alone. A screen reads it so that it never
    promises a confirmation email that cannot arrive.
    """

    id: UUID
    email: str
    full_name: str = Field(serialization_alias="fullName")
    role: str
    branch_code: str | None = Field(default=None, serialization_alias="branchCode")
    email_verified: bool = Field(serialization_alias="emailVerified")
    email_deliverable: bool = Field(serialization_alias="emailDeliverable")


class TokenResponse(CamelModel):
    """The access token and the account it belongs to.

    Signing in and refreshing both return this. The refresh token is not in
    it. That travels in a cookie the page cannot read.
    """

    access_token: str = Field(serialization_alias="accessToken")
    token_type: str = Field(default=BEARER_TOKEN_TYPE, serialization_alias="tokenType")
    expires_in: int = Field(serialization_alias="expiresIn")
    user: UserResponse


class HealthResponse(CamelModel):
    """What the health endpoint reports about its own dependencies."""

    status: str
    environment: str
    database_reachable: bool = Field(serialization_alias="databaseReachable")
    btree_gist_installed: bool = Field(serialization_alias="btreeGistInstalled")
    # The Cloud Run revision that answered, so a deployment can be confirmed
    # from outside without reading the console.
    revision: str


class ProblemDetail(BaseModel):
    """An RFC 9457 problem document.

    `type` is a stable slug, not a resolvable URL, because this API is not a
    public specification and inventing a documentation URL that does not exist
    is worse than a slug that does.

    `requestId` is an extension member. It is the same value as the
    `X-Request-ID` response header and the `request_id` on every log record of
    the request, so a caller who quotes it has named the exact log lines.
    """

    type: str
    title: str
    status: int
    detail: str
    instance: str | None = None
    errors: dict[str, object] | None = None
    request_id: str | None = Field(default=None, serialization_alias="requestId")
