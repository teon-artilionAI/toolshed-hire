"""The audit log as an administrator reads it, which is FR-26 and US-28 (BR-49, BR-50).

The owner asks who did what, to which record and when. The log is read
through a query object, `AuditEventQuery`, which is a port of its own and not
a second method on `AuditLog`, so nothing that writes the log can read it and
nothing that reads it can write it. There is no write path here at all, and
the database role the application runs as cannot change or remove an event.

`ReadAuditLog` narrows the log by the kind and the key of the record, the
action, the account that acted and a span of business days, newest first.
`from` and `to` are days in Cape Town, and both are included, so a search for
one day from that day to that day finds everything that happened on it. The
span is turned into two instants here, the start of `from` and the start of
the day after `to`, so the query object compares instants against
`occurred_at` and never works a day out itself. A `to` before `from` is
refused, naming `to`.

An event the sweep wrote has no actor, so its actor, name and role are None.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Final, Protocol
from uuid import UUID

from app.application.admin_lists import offset_of
from app.application.refusal import refused
from app.domain.business_time import business_instant
from app.domain.enums import UserRole
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

ONE_DAY: Final[timedelta] = timedelta(days=1)
START_OF_DAY: Final[time] = time.min
TO_PARAMETER: Final[str] = "to"
SPAN_REVERSED_MESSAGE: Final[str] = "The last day has to be on or after the first day."


@dataclass(frozen=True, slots=True)
class AuditEventEntry:
    """One audit event as the log shows it.

    Attributes:
        id: The event's number, which grows with every event written.
        occurred_at: When it happened.
        actor_user_id: The account that acted, or None for the sweep.
        actor_name: That account's name, or None for the sweep.
        actor_role: The role the account held at the time, or None.
        entity_type: The kind of record it is about, for example `reservation`.
        entity_id: The key of that record.
        action: What happened, for example `reservation.confirmed`.
        before_state: The fields that changed, as they were.
        after_state: The fields that changed, as they became.
        request_id: The request it happened in, which ties it to the log.

    """

    id: int
    occurred_at: datetime
    actor_user_id: UUID | None
    actor_name: str | None
    actor_role: UserRole | None
    entity_type: str
    entity_id: UUID
    action: str
    before_state: Mapping[str, object]
    after_state: Mapping[str, object]
    request_id: UUID | None


@dataclass(frozen=True, slots=True)
class AuditSearch:
    """Which events to list, and which page of them. Every filter is optional.

    Attributes:
        entity_type: Only events about this kind of record.
        entity_id: Only events about the record with this key.
        action: Only events of this action.
        actor_user_id: Only events this account made.
        occurred_from: Only events at or after this instant.
        occurred_before: Only events before this instant.
        page: The page, counted from one.
        page_size: How many events a page holds.

    """

    entity_type: str | None
    entity_id: UUID | None
    action: str | None
    actor_user_id: UUID | None
    occurred_from: datetime | None
    occurred_before: datetime | None
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        """Return how many events come before the first one on the page."""
        return offset_of(self.page, self.page_size)


@dataclass(frozen=True, slots=True)
class AuditEventPage:
    """One page of the log, newest first, and how many events match across every page."""

    items: tuple[AuditEventEntry, ...]
    page: int
    page_size: int
    total: int


class AuditEventQuery(Protocol):
    """The audit log, as the administrator reads it."""

    def page(self, search: AuditSearch) -> AuditEventPage:
        """Return one page of the events that match, newest first.

        It takes the same number of statements however long the page is.
        """
        ...


@dataclass(frozen=True, slots=True)
class AuditLogRequest:
    """What the administrator asked the log for.

    Attributes:
        actor: The administrator reading it.
        entity_type: The kind of record, or None.
        entity_id: The key of the record, or None.
        action: The action, or None.
        actor_user_id: The account that acted, or None.
        from_day: The first business day, or None.
        to_day: The last business day, which is included, or None.
        page: The page, counted from one.
        page_size: How many events a page holds.

    """

    actor: Actor
    entity_type: str | None
    entity_id: UUID | None
    action: str | None
    actor_user_id: UUID | None
    from_day: date | None
    to_day: date | None
    page: int
    page_size: int


class ReadAuditLog:
    """Reads the audit log for an administrator."""

    def __init__(self, events: AuditEventQuery) -> None:
        """Keep the query object the log is read through."""
        self._events = events

    def page(self, request: AuditLogRequest) -> AuditEventPage:
        """Return one page of the log, newest first.

        Raises:
            ValidationFailure: If `to` is before `from`, naming `to`.

        """
        logger.info(
            "audit.log_requested",
            extra={
                "actor_user_id": str(request.actor.user_id),
                "entity_type": request.entity_type,
                "entity_id": str(request.entity_id) if request.entity_id else None,
                "action": request.action,
                "filtered_by_actor": request.actor_user_id is not None,
                "from": request.from_day.isoformat() if request.from_day else None,
                "to": request.to_day.isoformat() if request.to_day else None,
                "page": request.page,
                "page_size": request.page_size,
            },
        )
        if request.from_day and request.to_day and request.to_day < request.from_day:
            raise refused(
                TO_PARAMETER,
                SPAN_REVERSED_MESSAGE,
                {"from": request.from_day.isoformat(), "to": request.to_day.isoformat()},
            )
        found = self._events.page(
            AuditSearch(
                entity_type=request.entity_type,
                entity_id=request.entity_id,
                action=request.action,
                actor_user_id=request.actor_user_id,
                occurred_from=_start_of(request.from_day),
                occurred_before=_start_of(request.to_day + ONE_DAY if request.to_day else None),
                page=request.page,
                page_size=request.page_size,
            )
        )
        logger.info(
            "audit.log_read",
            extra={"row_count": len(found.items), "total": found.total, "page": found.page},
        )
        return found


def _start_of(day: date | None) -> datetime | None:
    """Return the instant a business day begins in Cape Town, or None for no day."""
    return business_instant(day, START_OF_DAY) if day is not None else None
