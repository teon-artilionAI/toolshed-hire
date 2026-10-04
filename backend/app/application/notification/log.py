"""The notification log an administrator reads, which is FR-26 and US-36.

The log is every booking confirmation the outbox ever held, newest first,
narrowed by status, so a failed send is visible and can be sent again. It is
a read, so it goes through a query object, `NotificationLogQuery`, that
returns the small frozen dataclasses defined here and never a table row.

The schema has nowhere to store which notification a re-send repeats, so
`resend_of` is read from the audit event the re-send wrote, `notification.resent`,
whose after state names the one that failed. A notification nobody re-sent
carries None.

`ReadNotificationLog` is the service the route calls. It says what it was
asked for and what it found in the log, and nothing else, because the API has
already held the page and the status to their ranges.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol
from uuid import UUID

from app.application.admin_lists import offset_of
from app.domain.enums import NotificationStatus, NotificationType
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

# The action of the audit event a re-send writes, which `resend_of` is read from.
NOTIFICATION_RESENT_ACTION: Final[str] = "notification.resent"
NOTIFICATION_ENTITY_TYPE: Final[str] = "notification"
# The member of that event's after state that names the notification sent again.
RESEND_OF_KEY: Final[str] = "resend_of"


@dataclass(frozen=True, slots=True)
class NotificationEntry:
    """One notification as the log shows it.

    Attributes:
        id: The notification key.
        reservation_id: The booking it is about.
        reservation_reference: That booking's reference.
        notification_type: What it is about.
        recipient_email: The address it was sent to.
        subject: Its subject line.
        status: Whether it is waiting, delivered or failed.
        attempts: How many times a send was tried.
        last_error: Why the last attempt failed, when it did.
        queued_at: When it was written.
        sent_at: When the provider accepted it.
        resend_of: The failed notification this one sends again, or None.

    """

    id: UUID
    reservation_id: UUID
    reservation_reference: str
    notification_type: NotificationType
    recipient_email: str
    subject: str
    status: NotificationStatus
    attempts: int
    last_error: str | None
    queued_at: datetime
    sent_at: datetime | None
    resend_of: UUID | None


@dataclass(frozen=True, slots=True)
class NotificationSearch:
    """Which notifications to list, and which page of them."""

    status: NotificationStatus | None
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        """Return how many notifications come before the first one on the page."""
        return offset_of(self.page, self.page_size)


@dataclass(frozen=True, slots=True)
class NotificationPage:
    """One page of the log, newest first, and how many match across every page."""

    items: tuple[NotificationEntry, ...]
    page: int
    page_size: int
    total: int


class NotificationLogQuery(Protocol):
    """The notification log, as the administrator reads it."""

    def page(self, search: NotificationSearch) -> NotificationPage:
        """Return one page of the notifications that match, newest first.

        It takes the same number of statements however long the page is.
        """
        ...

    def one(self, notification_id: UUID) -> NotificationEntry | None:
        """Return one notification as the log shows it, or None when there is none."""
        ...


@dataclass(frozen=True, slots=True)
class NotificationLogQueryRequest:
    """What the administrator asked the log for.

    Attributes:
        actor: The administrator reading it.
        status: Only notifications in this status, or None for every one.
        page: The page, counted from one.
        page_size: How many a page holds.

    """

    actor: Actor
    status: NotificationStatus | None
    page: int
    page_size: int


class ReadNotificationLog:
    """Reads the notification log for an administrator."""

    def __init__(self, log: NotificationLogQuery) -> None:
        """Keep the query object the log is read through."""
        self._log = log

    def page(self, request: NotificationLogQueryRequest) -> NotificationPage:
        """Return one page of the log, newest first."""
        logger.info(
            "notification.log_requested",
            extra={
                "actor_user_id": str(request.actor.user_id),
                "status": request.status.value if request.status is not None else None,
                "page": request.page,
                "page_size": request.page_size,
            },
        )
        found = self._log.page(
            NotificationSearch(
                status=request.status, page=request.page, page_size=request.page_size
            )
        )
        logger.info(
            "notification.log_read",
            extra={"row_count": len(found.items), "total": found.total, "page": found.page},
        )
        return found
