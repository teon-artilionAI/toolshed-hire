"""The audit log port, and how a use case builds the event it records.

Every state changing use case records one event through this port, inside its
own transaction (BR-49). The port has a single method on purpose. An audit
trail that can be read back through the same object that writes it invites a
use case to depend on it, and an append only log should have nothing depending
on what it already holds.

`audit_event_for` stamps the event with the id and the client address of the
request being served. Both come from `app.request_context`, which sits outside
the four layers, so a use case never has to be handed HTTP details to be
audited properly.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.audit import AuditEvent, StateValue
from app.domain.identity import Actor
from app.request_context import current_client_address, current_request_id

logger = logging.getLogger(__name__)


class AuditLog(Protocol):
    """Where a use case records what it changed."""

    def record(self, event: AuditEvent) -> None:
        """Write the event inside the current transaction.

        A failure must be raised and never swallowed. The use case lets it
        propagate, the unit of work rolls back, and the change the event
        described does not happen.
        """
        ...


def audit_event_for(
    *,
    actor: Actor | None,
    entity_type: str,
    entity_id: UUID,
    action: str,
    occurred_at: datetime,
    before_state: Mapping[str, StateValue] | None = None,
    after_state: Mapping[str, StateValue] | None = None,
) -> AuditEvent:
    """Build the audit event for an operation performed during the current request.

    Args:
        actor: The account acting and the role it holds right now, or None for
            an operation with no human actor.
        entity_type: The kind of record that changed, for example `reservation`.
        entity_id: The key of that record.
        action: The name of the operation, for example `reservation.held`.
        occurred_at: When it happened, from the clock.
        before_state: The changed fields as they were. None for a creation.
        after_state: The changed fields as they are now.

    Returns:
        The event, carrying the request id and the client address when a
        request is being served and neither when one is not.

    """
    request_id = current_request_id()
    event = AuditEvent(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        occurred_at=occurred_at,
        actor_user_id=actor.user_id if actor is not None else None,
        actor_role=actor.role if actor is not None else None,
        before_state=before_state,
        after_state=after_state,
        request_id=UUID(request_id) if request_id is not None else None,
        ip_address=current_client_address(),
    )
    logger.debug(
        "audit.event_built",
        extra={
            "action": action,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "has_actor": actor is not None,
        },
    )
    return event
