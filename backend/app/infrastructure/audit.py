"""The SQL audit log (BR-49).

`SqlAuditLog` writes one `audit_event` row through the session of the unit of
work that created it, so the event commits or rolls back together with the
change it describes. The row is flushed at once. If it cannot be written the
caller finds out inside the transaction, while there is still something to
roll back.

The table is append only. The application role holds INSERT and SELECT on it
and nothing else, so this class has one method and it only adds.
"""

from __future__ import annotations

import logging

from sqlmodel import Session

from app.domain import audit as domain
from app.infrastructure.models import AuditEvent

logger = logging.getLogger(__name__)


class SqlAuditLog:
    """Writes audit events through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the audit log to the session of its unit of work."""
        self._session = session

    def record(self, event: domain.AuditEvent) -> None:
        """Write the event inside the current transaction.

        Raises:
            SQLAlchemyError: If the row cannot be written. It is not caught
                here, because an operation that cannot be audited must not
                happen.

        """
        logger.debug(
            "audit.event_insert_started",
            extra={
                "action": event.action,
                "entity_type": event.entity_type,
                "entity_id": str(event.entity_id),
            },
        )
        row = AuditEvent(
            occurred_at=event.occurred_at,
            actor_user_id=event.actor_user_id,
            actor_role=event.actor_role,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            action=event.action,
            before_state=dict(event.before_state) if event.before_state is not None else None,
            after_state=dict(event.after_state) if event.after_state is not None else None,
            request_id=event.request_id,
            ip_address=event.ip_address,
        )
        self._session.add(row)
        self._session.flush()
        logger.info(
            "audit.event_recorded",
            extra={
                "action": event.action,
                "entity_type": event.entity_type,
                "entity_id": str(event.entity_id),
                "actor_role": event.actor_role.value if event.actor_role else None,
            },
        )
