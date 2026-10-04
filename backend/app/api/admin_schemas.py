"""Request and response models for the admin operations, the two logs and the corrections.

Field names on the wire are camelCase, as everywhere else at this boundary. An
instant is ISO 8601 with the offset of Cape Town, money is a string with two
decimals, and a list is `{"items": [...], "page": 1, "pageSize": 20, "total": 0}`.

Every override takes a `reason` of 5 to 200 characters once trimmed, which is
written to the audit log with the administrator who gave it (BR-25). An
adjustment takes `amountIncVat` as a string with at most two decimals and an
optional minus sign, so no amount passes through a float. It may be positive
or negative and not nothing.

An audit event's `beforeState` and `afterState` are the fields the change
named, and an empty object when it named none, as a creation names nothing
before it. `actorUserId`, `actorName` and `actorRole` are null for an event
the sweep wrote. `actorRole` is the role held at the time, as stored.

A notification's `resendOf` names the failed notification it sends again. The
schema has no column for it, so it is read from the audit event of the re-send.
"""

from __future__ import annotations

from typing import Annotated, Final
from uuid import UUID

from pydantic import Field, StringConstraints

from app.api.account_schemas import StrictRequest
from app.api.reservation_schemas import Timestamp
from app.api.schemas import CamelModel, ProblemDetail
from app.domain.enums import NotificationStatus, NotificationType, UserRole
from app.domain.override_reason import REASON_MAX_LENGTH, REASON_MIN_LENGTH

# An amount in rand with at most two decimals and an optional sign, no larger
# than the money columns hold.
SIGNED_MONEY_PATTERN: Final[str] = r"^-?\d{1,10}(\.\d{1,2})?$"
# The widths of the two columns an audit search names.
ENTITY_TYPE_MAX_LENGTH: Final[int] = 40
ACTION_MAX_LENGTH: Final[int] = 60

ReasonText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=REASON_MIN_LENGTH, max_length=REASON_MAX_LENGTH
    ),
]
SignedAmountText = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=SIGNED_MONEY_PATTERN)
]

UNKNOWN_CHARGE_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "There is no such charge.",
}
WAIVER_REFUSED_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "The charge is not pending. A settled charge is reversed instead.",
}
REVERSAL_REFUSED_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": (
        "The charge is not settled, is a deposit movement, is itself a reversal or has been "
        "reversed already, and `detail` says which."
    ),
}
ADJUSTMENT_REFUSED_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": (
        "The hire is settled, so only a correction that gives money back can be made to it."
    ),
}
UNKNOWN_NOTIFICATION_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "There is no such notification.",
}
RESEND_REFUSED_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "The notification has not failed, so there is nothing to send again.",
}
UNKNOWN_ALLOCATION_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "There is no such allocation.",
}
RELEASE_REFUSED_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": (
        "The allocation is no longer active, or its unit is out on hire on the booking, and "
        "`detail` says which."
    ),
}


class ReasonRequest(StrictRequest):
    """The reason an administrator gives for an override."""

    reason: ReasonText


class AdjustmentRequest(StrictRequest):
    """An adjustment of a hire, VAT included, and the reason for it."""

    amount_inc_vat: SignedAmountText = Field(validation_alias="amountIncVat")
    reason: ReasonText


class AuditEventResponse(CamelModel):
    """One audit event, as the log shows it."""

    id: int
    occurred_at: Timestamp = Field(serialization_alias="occurredAt")
    actor_user_id: UUID | None = Field(serialization_alias="actorUserId")
    actor_name: str | None = Field(serialization_alias="actorName")
    actor_role: UserRole | None = Field(serialization_alias="actorRole")
    entity_type: str = Field(serialization_alias="entityType")
    entity_id: UUID = Field(serialization_alias="entityId")
    action: str
    before_state: dict[str, object] = Field(serialization_alias="beforeState")
    after_state: dict[str, object] = Field(serialization_alias="afterState")
    request_id: UUID | None = Field(serialization_alias="requestId")


class AuditEventPageResponse(CamelModel):
    """One page of the audit log, newest first."""

    items: list[AuditEventResponse]
    page: int
    page_size: int = Field(serialization_alias="pageSize")
    total: int


class NotificationResponse(CamelModel):
    """One notification, as the log shows it."""

    id: UUID
    reservation_id: UUID = Field(serialization_alias="reservationId")
    reservation_reference: str = Field(serialization_alias="reservationReference")
    notification_type: NotificationType = Field(serialization_alias="type")
    recipient_email: str = Field(serialization_alias="recipientEmail")
    subject: str
    status: NotificationStatus
    attempts: int
    last_error: str | None = Field(serialization_alias="lastError")
    queued_at: Timestamp = Field(serialization_alias="queuedAt")
    sent_at: Timestamp | None = Field(serialization_alias="sentAt")
    resend_of: UUID | None = Field(serialization_alias="resendOf")


class NotificationPageResponse(CamelModel):
    """One page of the notification log, newest first."""

    items: list[NotificationResponse]
    page: int
    page_size: int = Field(serialization_alias="pageSize")
    total: int
