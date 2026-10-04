"""What the routes of the admin operations share, which is the path keys and the responses.

An audit event and a notification are written out the same way by every route
that returns one, so the mapping from a read model to its shape on the wire is
here once. Nothing is worked out in it.
"""

from __future__ import annotations

from typing import Annotated, Final
from uuid import UUID

from fastapi import Path

from app.api.admin_schemas import (
    AuditEventPageResponse,
    AuditEventResponse,
    NotificationPageResponse,
    NotificationResponse,
)
from app.application.audit_reads import AuditEventEntry, AuditEventPage
from app.application.notification.log import NotificationEntry, NotificationPage

ADMIN_PREFIX: Final[str] = "/admin"
# The tags of the routers, which are the modules they belong to. The audit log
# belongs to no module, so it has a tag of its own.
AUDIT_TAG: Final[str] = "audit"
NOTIFICATION_TAG: Final[str] = "notification"

NotificationPathKey = Annotated[UUID, Path(alias="id", description="The key of the notification.")]
ChargePathKey = Annotated[UUID, Path(alias="id", description="The key of the charge.")]
AllocationPathKey = Annotated[UUID, Path(alias="id", description="The key of the allocation.")]


def audit_event_response(entry: AuditEventEntry) -> AuditEventResponse:
    """Write one audit event in the shape the contract gives it."""
    return AuditEventResponse(
        id=entry.id,
        occurred_at=entry.occurred_at,
        actor_user_id=entry.actor_user_id,
        actor_name=entry.actor_name,
        actor_role=entry.actor_role,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        action=entry.action,
        before_state=dict(entry.before_state),
        after_state=dict(entry.after_state),
        request_id=entry.request_id,
    )


def audit_page_response(page: AuditEventPage) -> AuditEventPageResponse:
    """Write one page of the audit log in the shape the contract gives a list."""
    return AuditEventPageResponse(
        items=[audit_event_response(entry) for entry in page.items],
        page=page.page,
        page_size=page.page_size,
        total=page.total,
    )


def notification_response(entry: NotificationEntry) -> NotificationResponse:
    """Write one notification in the shape the contract gives it."""
    return NotificationResponse(
        id=entry.id,
        reservation_id=entry.reservation_id,
        reservation_reference=entry.reservation_reference,
        notification_type=entry.notification_type,
        recipient_email=entry.recipient_email,
        subject=entry.subject,
        status=entry.status,
        attempts=entry.attempts,
        last_error=entry.last_error,
        queued_at=entry.queued_at,
        sent_at=entry.sent_at,
        resend_of=entry.resend_of,
    )


def notification_page_response(page: NotificationPage) -> NotificationPageResponse:
    """Write one page of the notification log in the shape the contract gives a list."""
    return NotificationPageResponse(
        items=[notification_response(entry) for entry in page.items],
        page=page.page,
        page_size=page.page_size,
        total=page.total,
    )
