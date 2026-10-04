"""Rows and searches for the tests that read the two logs of the admin console on PostgreSQL.

No route can write an audit event at a chosen moment, so the events and the
notifications a read test needs are written here by hand, with the instants
and the statuses the test names. `events_of` writes a run of events a minute
apart, every third one by the sweep, and `every_event` is the first page of the
audit log narrowed by the filters a test names and no others.

Like the other factories, the writers flush and never commit, except
`events_of` and `committed_reservation`, which commit what they wrote so a
reader on a connection of its own sees it.

Importing this module opens no connection.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID, uuid4

from sqlmodel import Session

from app.application.audit_reads import AuditSearch
from app.domain.enums import NotificationChannel, NotificationStatus, NotificationType
from app.infrastructure.models import AuditEvent, Notification, Reservation, UserAccount
from tests.support.checkout_api import TODAY_HIRE
from tests.support.factories import Factory

PAGE_SIZE: Final[int] = 50
FIRST_PAGE: Final[int] = 1
RESERVATION_ENTITY: Final[str] = "reservation"
NOTIFICATION_ENTITY: Final[str] = "notification"
CONFIRMED: Final[str] = "reservation.confirmed"
EXPIRED: Final[str] = "reservation.expired"
WAIVED: Final[str] = "charge.waived"
RESENT: Final[str] = "notification.resent"
START: Final[datetime] = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
ONE_MINUTE: Final[timedelta] = timedelta(minutes=1)
# Every third event of a run is written by the sweep, which has no actor.
SWEEP_EVERY: Final[int] = 3
PROVIDER: Final[str] = "resend"
RECIPIENT: Final[str] = "nomsa.dlamini@example.co.za"
SUBJECT: Final[str] = "Your Toolshed Hire booking"
NO_ATTEMPTS: Final[int] = 0
ONE_ATTEMPT: Final[int] = 1
PROVIDER_REFUSED: Final[str] = "The email provider refused the message."


def write_event(
    session: Session,
    *,
    occurred_at: datetime,
    action: str,
    entity_type: str,
    entity_id: UUID,
    actor: UserAccount | None = None,
    after_state: dict[str, object] | None = None,
) -> int:
    """Write one audit event at a chosen instant and return its number. Nothing is committed."""
    event = AuditEvent(
        occurred_at=occurred_at,
        actor_user_id=actor.id if actor is not None else None,
        actor_role=actor.role if actor is not None else None,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before_state=None,
        after_state=after_state,
    )
    session.add(event)
    session.flush()
    assert event.id is not None
    return event.id


def write_notification(
    session: Session,
    reservation: Reservation,
    *,
    queued_at: datetime,
    status: NotificationStatus,
) -> UUID:
    """Write one booking confirmation in a status at a chosen instant. Nothing is committed."""
    sent = status is NotificationStatus.SENT
    notification = Notification(
        reservation_id=reservation.id,
        notification_type=NotificationType.BOOKING_CONFIRMATION,
        channel=NotificationChannel.EMAIL,
        recipient_email=RECIPIENT,
        subject=SUBJECT,
        status=status,
        provider=PROVIDER,
        attempts=NO_ATTEMPTS if status is NotificationStatus.QUEUED else ONE_ATTEMPT,
        last_error=PROVIDER_REFUSED if status is NotificationStatus.FAILED else None,
        queued_at=queued_at,
        sent_at=queued_at if sent else None,
    )
    session.add(notification)
    session.flush()
    return notification.id


def committed_reservation(
    session: Session, factory: Factory, created_by: UserAccount
) -> Reservation:
    """Commit a reservation for today at a branch of its own, for notifications to be about."""
    branch = factory.branch()
    booked = factory.reservation(
        profile=factory.customer_profile(branch=branch),
        created_by=created_by,
        branch=branch,
        period=TODAY_HIRE,
    )
    session.commit()
    return booked


def every_event(
    *,
    entity_id: UUID | None = None,
    action: str | None = None,
    actor_user_id: UUID | None = None,
) -> AuditSearch:
    """Return the first page of the audit log with the filters named and no others."""
    return AuditSearch(
        entity_type=None,
        entity_id=entity_id,
        action=action,
        actor_user_id=actor_user_id,
        occurred_from=None,
        occurred_before=None,
        page=FIRST_PAGE,
        page_size=PAGE_SIZE,
    )


def events_of(session: Session, administrator: UserAccount, count: int, offset: int = 0) -> None:
    """Write events a minute apart, every third one by the sweep, and commit them."""
    for number in range(offset, offset + count):
        by_hand = number % SWEEP_EVERY != 0
        write_event(
            session,
            occurred_at=START + number * ONE_MINUTE,
            action=CONFIRMED if by_hand else EXPIRED,
            entity_type=RESERVATION_ENTITY,
            entity_id=uuid4(),
            actor=administrator if by_hand else None,
        )
    session.commit()


__all__ = [
    "CONFIRMED",
    "EXPIRED",
    "FIRST_PAGE",
    "NOTIFICATION_ENTITY",
    "ONE_MINUTE",
    "PAGE_SIZE",
    "RESENT",
    "RESERVATION_ENTITY",
    "START",
    "WAIVED",
    "committed_reservation",
    "every_event",
    "events_of",
    "write_event",
    "write_notification",
]
