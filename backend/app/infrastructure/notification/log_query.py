"""The notification log as a query object, newest first (FR-26, US-36).

A page of the log is two statements however long the page is, the count and
the page. The page joins each notification to its booking for the reference,
and reads `resend_of` from the audit event a re-send wrote, as a correlated
subquery that is one probe of `ix_audit_event_entity` for each row of the
page, because the schema has no column for it.

The order is `queued_at`, newest first, then the key. With no status named the
page is read backwards through `ix_notification_queued_at` of revision 0008.
A status is written into the statement as the literal it is stored as, so the
log of failed sends, the one an administrator works from, is read through the
partial index `ix_notification_failed` whatever plan the server caches, and
the other two statuses through the index on `queued_at`.

One notification is one statement, by its primary key.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, Label, func, literal_column
from sqlalchemy import select as select_columns
from sqlmodel import Session, col, select

from app.application.notification.log import (
    NOTIFICATION_ENTITY_TYPE,
    NOTIFICATION_RESENT_ACTION,
    RESEND_OF_KEY,
    NotificationEntry,
    NotificationPage,
    NotificationSearch,
)
from app.domain.enums import NotificationStatus
from app.infrastructure.booking_mapping import in_utc, required_utc
from app.infrastructure.models import AuditEvent, Notification, Reservation
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)

QUEUED_AT_COLUMN: Final[str] = "notification.queued_at"
RESEND_STATE_LABEL: Final[str] = "resend_state"

# One notification as the page reads it, with its booking's reference and the
# after state of the audit event of its re-send, when there was one.
type NotificationRow = tuple[Notification, str, Mapping[str, object] | None]


def _resend_state() -> Label[Mapping[str, object] | None]:
    """Return the after state of the event that queued the row as a re-send, if one did."""
    return (
        select_columns(col(AuditEvent.after_state))
        .where(
            col(AuditEvent.entity_type) == NOTIFICATION_ENTITY_TYPE,
            col(AuditEvent.entity_id) == col(Notification.id),
            col(AuditEvent.action) == NOTIFICATION_RESENT_ACTION,
        )
        .correlate(Notification)
        .limit(1)
        .scalar_subquery()
        .label(RESEND_STATE_LABEL)
    )


def _status_condition(status: NotificationStatus) -> ColumnElement[bool]:
    """Return the condition on a status, written as the literal it is stored as."""
    return col(Notification.status) == literal_column(f"'{status.value}'")


class SqlNotificationLog:
    """Reads the notification log through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the reads to the session of the request."""
        self._session = session

    def page(self, search: NotificationSearch) -> NotificationPage:
        """Return one page of the notifications that match, newest first, in two statements."""
        conditions = [] if search.status is None else [_status_condition(search.status)]
        filters = {
            "status": search.status.value if search.status is not None else None,
            "page": search.page,
            "page_size": search.page_size,
        }
        with logged_query(logger, "notification.log_page", filters) as outcome:
            total = self._session.exec(
                select(func.count()).select_from(Notification).where(*conditions)
            ).one()
            rows = self._session.exec(
                select(Notification, col(Reservation.reference), _resend_state())
                .join(Reservation, col(Reservation.id) == col(Notification.reservation_id))
                .where(*conditions)
                .order_by(col(Notification.queued_at).desc(), col(Notification.id).desc())
                .offset(search.offset)
                .limit(search.page_size)
            ).all()
            outcome.row_count = len(rows)
        return NotificationPage(
            items=tuple(_entry_of(row) for row in rows),
            page=search.page,
            page_size=search.page_size,
            total=total,
        )

    def one(self, notification_id: UUID) -> NotificationEntry | None:
        """Return one notification as the log shows it, or None when there is none."""
        with logged_query(
            logger, "notification.log_entry", {"notification_id": str(notification_id)}
        ) as outcome:
            found = self._session.exec(
                select(Notification, col(Reservation.reference), _resend_state())
                .join(Reservation, col(Reservation.id) == col(Notification.reservation_id))
                .where(col(Notification.id) == notification_id)
            ).first()
            outcome.row_count = 0 if found is None else 1
        return None if found is None else _entry_of(found)


def _entry_of(row: NotificationRow) -> NotificationEntry:
    """Return one notification as a read model, from its row and what was read with it."""
    notification, reference, resend_state = row
    resend_of = (resend_state or {}).get(RESEND_OF_KEY)
    return NotificationEntry(
        id=notification.id,
        reservation_id=notification.reservation_id,
        reservation_reference=reference,
        notification_type=notification.notification_type,
        recipient_email=notification.recipient_email,
        subject=notification.subject,
        status=notification.status,
        attempts=notification.attempts,
        last_error=notification.last_error,
        queued_at=required_utc(notification.queued_at, QUEUED_AT_COLUMN),
        sent_at=in_utc(notification.sent_at),
        resend_of=UUID(resend_of) if isinstance(resend_of, str) else None,
    )
