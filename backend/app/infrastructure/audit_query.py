"""The audit log as a query object, newest first (FR-26, BR-49, BR-50).

A page is two statements however long the page is, the count and the page,
and the page joins the account that acted for its name. The table is never
written here. The application role may only insert into it and read it.

Each filter stands on an index, so a page is found without reading the log
from end to end, and each index ends in `occurred_at`, so the newest page of a
filter is read off the end of its index. The index of an action leaves out the
changes of status of the units, so it never competes with the partial index
the utilisation report reads them through. A search for any other action
therefore says so in the statement, as a literal the planner matches the
predicate of the index with, and the log of the changes of status is read
through `ix_audit_event_occurred_at`.

| Filter | Index |
|---|---|
| `entityType` and `entityId` together | `ix_audit_event_entity`, of the baseline |
| `entityType` alone | `ix_audit_event_entity`, the leading column |
| `entityId` alone | `ix_audit_event_entity_id`, revision 0008 |
| `action` | `ix_audit_event_action`, revision 0008, partial on all but a change of status |
| `action` of `asset.status_changed` | `ix_audit_event_occurred_at`, read backwards |
| `actorUserId` | `ix_audit_event_actor`, revision 0008, partial on an actor |
| `from` and `to` | `ix_audit_event_occurred_at`, of the baseline |
| none | `ix_audit_event_occurred_at`, read backwards |

The count is what costs the most. It counts every event that matches, so a
log with no filter is counted in full on every page.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Final

from sqlalchemy import ColumnElement, func, literal_column
from sqlmodel import Session, col, select

from app.application.audit_reads import AuditEventEntry, AuditEventPage, AuditSearch
from app.infrastructure.booking_mapping import required_utc
from app.infrastructure.models import AuditEvent, UserAccount
from app.infrastructure.query_log import logged_query
from app.infrastructure.schema_ddl import STATUS_CHANGE_ACTION

logger = logging.getLogger(__name__)

OCCURRED_AT_COLUMN: Final[str] = "audit_event.occurred_at"
EVENT_NUMBER_COLUMN: Final[str] = "audit_event.id"
# Written as a literal, so the planner can match the predicate of the partial
# index of an action whatever plan it caches.
NOT_A_STATUS_CHANGE: Final[str] = f"'{STATUS_CHANGE_ACTION}'"


class SqlAuditEventReads:
    """Reads the audit log through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the reads to the session of the request."""
        self._session = session

    def page(self, search: AuditSearch) -> AuditEventPage:
        """Return one page of the events that match, newest first, in two statements."""
        conditions = _conditions(search)
        filters = {
            "entity_type": search.entity_type,
            "entity_id": str(search.entity_id) if search.entity_id else None,
            "action": search.action,
            "filtered_by_actor": search.actor_user_id is not None,
            "from": search.occurred_from.isoformat() if search.occurred_from else None,
            "before": search.occurred_before.isoformat() if search.occurred_before else None,
            "page": search.page,
            "page_size": search.page_size,
        }
        with logged_query(logger, "audit.log_page", filters) as outcome:
            total = self._session.exec(
                select(func.count()).select_from(AuditEvent).where(*conditions)
            ).one()
            rows = self._session.exec(
                select(AuditEvent, col(UserAccount.full_name))
                .outerjoin(UserAccount, col(UserAccount.id) == col(AuditEvent.actor_user_id))
                .where(*conditions)
                .order_by(col(AuditEvent.occurred_at).desc(), col(AuditEvent.id).desc())
                .offset(search.offset)
                .limit(search.page_size)
            ).all()
            outcome.row_count = len(rows)
        return AuditEventPage(
            items=tuple(_entry_of(event, actor_name) for event, actor_name in rows),
            page=search.page,
            page_size=search.page_size,
            total=total,
        )


def _conditions(search: AuditSearch) -> list[ColumnElement[bool]]:
    """Return the condition of every filter the search names, each a bound comparison."""
    conditions: list[ColumnElement[bool]] = []
    if search.entity_type is not None:
        conditions.append(col(AuditEvent.entity_type) == search.entity_type)
    if search.entity_id is not None:
        conditions.append(col(AuditEvent.entity_id) == search.entity_id)
    if search.action is not None:
        conditions.append(col(AuditEvent.action) == search.action)
        if search.action != STATUS_CHANGE_ACTION:
            conditions.append(col(AuditEvent.action) != literal_column(NOT_A_STATUS_CHANGE))
    if search.actor_user_id is not None:
        conditions.append(col(AuditEvent.actor_user_id) == search.actor_user_id)
    if search.occurred_from is not None:
        conditions.append(col(AuditEvent.occurred_at) >= search.occurred_from)
    if search.occurred_before is not None:
        conditions.append(col(AuditEvent.occurred_at) < search.occurred_before)
    return conditions


def _entry_of(event: AuditEvent, actor_name: str | None) -> AuditEventEntry:
    """Return one event as a read model, with the name of the account that acted."""
    if event.id is None:
        raise ValueError(
            f"Attempted to read an audit event with no {EVENT_NUMBER_COLUMN}. A stored event "
            "is always numbered."
        )
    return AuditEventEntry(
        id=event.id,
        occurred_at=required_utc(event.occurred_at, OCCURRED_AT_COLUMN),
        actor_user_id=event.actor_user_id,
        actor_name=actor_name,
        actor_role=event.actor_role,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        action=event.action,
        before_state=_state(event.before_state),
        after_state=_state(event.after_state),
        request_id=event.request_id,
    )


def _state(state: Mapping[str, object] | None) -> Mapping[str, object]:
    """Return the fields of an event, an empty set when the event recorded none."""
    return dict(state) if state is not None else {}
