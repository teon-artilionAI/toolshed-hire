"""The notification outbox of the in memory unit of work.

It keeps copies of what it is handed and hands copies back, the way a table
would, so a use case can never change a stored notification by holding on to
the object it read. Faults are switched on through the store, so a test can
make reading the queue or recording an outcome fail when it wants to.
"""

from __future__ import annotations

import copy
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from app.domain.enums import NotificationStatus
from app.domain.notification import Notification

if TYPE_CHECKING:
    from tests.support.memory import MemoryStore, Records


class StoreFault(RuntimeError):
    """Raised by the in memory store when a test has switched a fault on."""


class MemoryOutbox:
    """The notification outbox over the working copy."""

    def __init__(self, store: MemoryStore, working: Records) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def enqueue(self, notification: Notification) -> None:
        """Keep a copy of the queued notification."""
        self._working.notifications[notification.id] = copy.deepcopy(notification)

    def due(self, limit: int) -> list[Notification]:
        """Return copies of the queued notifications, oldest first."""
        if self._store.fail_outbox_read:
            raise StoreFault("The outbox could not be read.")
        queued = [
            notification
            for notification in self._working.notifications.values()
            if notification.status is NotificationStatus.QUEUED
        ]
        queued.sort(key=lambda notification: (notification.queued_at, str(notification.id)))
        return copy.deepcopy(queued[:limit])

    def find(self, notification_id: UUID) -> Notification | None:
        """Return a copy of one notification, whatever its status, or None."""
        found = self._working.notifications.get(notification_id)
        return copy.deepcopy(found) if found is not None else None

    def mark_sent(
        self, notification_id: UUID, provider_message_id: str, sent_at: datetime
    ) -> None:
        """Record a successful send."""
        if self._store.fail_outbox_write:
            raise StoreFault("The outcome could not be written.")
        self._working.notifications[notification_id].mark_sent(provider_message_id, sent_at)

    def mark_failed(self, notification_id: UUID, reason: str) -> None:
        """Record a failed send."""
        if self._store.fail_outbox_write:
            raise StoreFault("The outcome could not be written.")
        self._working.notifications[notification_id].mark_failed(reason)


__all__ = ["MemoryOutbox", "StoreFault"]
