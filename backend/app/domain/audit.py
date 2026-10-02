"""The audit event, an append only record of one state changing operation (BR-49).

An event is written in the same transaction as the change it describes. If the
event cannot be written the change does not happen, so there is never a state
change with no record of who made it.

The audit trail belongs to none of the eight modules. Every module writes to it
and none of them owns it, which is why it has a file of its own in each layer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from uuid import UUID

from app.domain.enums import UserRole

# What a before or after snapshot may hold. Deliberately narrow, so a snapshot
# can always be stored as JSON without a custom encoder.
type StateValue = str | int | bool | None | list[str]

type ClientAddress = IPv4Address | IPv6Address


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Who did what to which record, and what changed.

    Attributes:
        entity_type: The kind of record that changed, for example `reservation`.
        entity_id: The key of that record. Deliberately not a reference to it,
            so the event outlives whatever it describes.
        action: The name of the operation, for example `reservation.held`.
        occurred_at: When the operation happened, from the clock.
        actor_user_id: The account that acted, or None for a sweep with no
            human actor.
        actor_role: The role that account held at the time, copied so the log
            survives a later role change.
        before_state: The changed fields as they were, or None for a creation.
        after_state: The changed fields as they are now.
        request_id: The id of the request being served, which ties the event
            to the structured application log.
        ip_address: The address of the client, when it is known.

    """

    entity_type: str
    entity_id: UUID
    action: str
    occurred_at: datetime
    actor_user_id: UUID | None = None
    actor_role: UserRole | None = None
    before_state: Mapping[str, StateValue] | None = None
    after_state: Mapping[str, StateValue] | None = None
    request_id: UUID | None = None
    ip_address: ClientAddress | None = None

    def __post_init__(self) -> None:
        """Refuse an event that names nothing, or an actor with no role.

        Raises:
            ValueError: If the entity type or the action is blank, or if
                exactly one of the actor id and the actor role is given.

        """
        if not self.entity_type.strip() or not self.action.strip():
            raise ValueError(
                "Attempted to build an audit event with a blank entity type or action. Got "
                f"entity_type={self.entity_type!r} and action={self.action!r}. Both are required."
            )
        if (self.actor_user_id is None) != (self.actor_role is None):
            raise ValueError(
                f"Attempted to build the audit event {self.action!r} with half an actor. Got "
                f"actor_user_id={self.actor_user_id!r} and actor_role={self.actor_role!r}. "
                "The two are recorded together or not at all."
            )
