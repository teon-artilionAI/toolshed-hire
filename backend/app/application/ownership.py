"""Whose records a read may return (BR-42).

A customer may read their own bookings, hires and charges and nobody else's.
Staff may read any customer's. That rule is applied inside the query. A
repository that reads a record on behalf of somebody takes an `OwnerScope` and
puts it in the WHERE clause, so a record that belongs to another customer is
simply not found.

There is deliberately no second step. Fetching the record first and comparing
its owner afterwards would make it possible to answer "that exists but is not
yours", and the difference between that and "there is no such record" tells a
customer which identifiers are real. One query, one answer, and the answer for
a record that is not theirs is the same 404 as for one that never existed.

This belongs to no module. Every module that returns a customer's records
applies it the same way.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domain.enums import UserRole
from app.domain.errors import NotFound
from app.domain.identity import Actor


@dataclass(frozen=True, slots=True)
class OwnerScope:
    """The limit a read is run under.

    Attributes:
        customer_user_id: The account whose records may be returned, or None
            when the reader is staff and may be shown any customer's.

    """

    customer_user_id: UUID | None

    @property
    def is_restricted(self) -> bool:
        """Return True when the read is limited to one customer's records."""
        return self.customer_user_id is not None


def owner_scope_for(actor: Actor) -> OwnerScope:
    """Return the scope a read by this actor runs under.

    A customer is limited to their own records. Counter staff and
    administrators are not limited by owner.
    """
    if actor.role is UserRole.CUSTOMER:
        return OwnerScope(customer_user_id=actor.user_id)
    return OwnerScope(customer_user_id=None)


def not_found(entity: str, entity_id: UUID) -> NotFound:
    """Build the one answer for a record that is absent or is not the reader's.

    Args:
        entity: What kind of record was asked for, for example `reservation`.
        entity_id: The key that was asked for.

    Returns:
        The error to raise. It says the same thing in both cases on purpose.

    """
    return NotFound(
        f"Attempted to read {entity} {entity_id}, and there is no such {entity}.",
        {f"{entity}_id": str(entity_id)},
    )
