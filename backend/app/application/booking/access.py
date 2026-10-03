"""What every booking use case does before and after its own work.

Before it changes a reservation a use case has to find it, and finding it is
where two rules are applied. The scope of the caller goes into the query, so a
customer who names somebody else's reservation is told there is no such
reservation (BR-42). And counter staff may change a reservation at their own
branch only, so a reservation at another branch is refused before anything is
changed (BR-43).

After the change a use case records one audit event in the same unit of work
(BR-49). `record_change` builds it from the reservation as it was and as it is
now, so every event of the lifecycle says the same things in the same words.

A refusal written here can reach a customer's screen, so each one is a plain
sentence. What was asked for goes in the detail, for the log.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from app.application.audit import audit_event_for
from app.application.booking.read_models import ReservationDetail, ReservationKey
from app.application.ownership import owner_scope_for
from app.application.unit_of_work import UnitOfWork
from app.domain.audit import StateValue
from app.domain.booking import Reservation
from app.domain.enums import UserRole
from app.domain.errors import NotFound
from app.domain.identity import Actor, CustomerProfile, ensure_branch_scope

logger = logging.getLogger(__name__)

RESERVATION_ENTITY_TYPE: Final[str] = "reservation"
RESERVATION_CREATED_ACTION: Final[str] = "reservation.created"
RESERVATION_HELD_ACTION: Final[str] = "reservation.held"
RESERVATION_CONFIRMED_ACTION: Final[str] = "reservation.confirmed"
RESERVATION_CANCELLED_ACTION: Final[str] = "reservation.cancelled"
RESERVATION_EXPIRED_ACTION: Final[str] = "reservation.expired"
RESERVATION_COLLECTED_ACTION: Final[str] = "reservation.collected"
RESERVATION_NO_SHOW_ACTION: Final[str] = "reservation.no_show"

RESERVATION_NOT_FOUND_MESSAGE: Final[str] = (
    "We could not find that reservation. Check the reference and try again."
)


@dataclass(frozen=True, slots=True)
class ReservationCommand:
    """A request to make one move on one reservation.

    Attributes:
        actor: The account making the request and the role it holds.
        key: The reservation, by its key or its reference.

    """

    actor: Actor
    key: ReservationKey


def reservation_not_found(key: ReservationKey) -> NotFound:
    """Build the one answer for a reservation that is absent or is not the caller's.

    It says the same thing in both cases on purpose. The difference between
    the two would tell a customer which references are real.
    """
    return NotFound(RESERVATION_NOT_FOUND_MESSAGE, {"reservation": str(key)})


def is_staff(actor: Actor) -> bool:
    """Return True when the actor is counter staff or an administrator."""
    return actor.role in (UserRole.COUNTER_STAFF, UserRole.ADMIN)


def load_for_change(uow: UnitOfWork, actor: Actor, key: ReservationKey) -> Reservation:
    """Return the reservation a caller wants to change, locked, or refuse.

    Args:
        uow: The open unit of work.
        actor: Who is asking, with the role and the branch they hold.
        key: The reservation asked for.

    Raises:
        NotFound: If there is no such reservation, or the actor is a customer
            and it belongs to somebody else. The two are not distinguished.
        BranchScopeError: If the actor is counter staff and the reservation is
            collected at a branch that is not their own.

    """
    reservation = uow.reservations.find_for_update(key, owner_scope_for(actor))
    if reservation is None:
        logger.info(
            "reservation.not_found",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "reservation": str(key),
                "attempted": "load a reservation to change it",
            },
        )
        raise reservation_not_found(key)
    ensure_branch_scope(actor, reservation.branch_id)
    return reservation


def read_detail(uow: UnitOfWork, actor: Actor, key: ReservationKey) -> ReservationDetail:
    """Return a reservation as a read model, under the scope of the caller.

    Raises:
        NotFound: If there is no such reservation, or it is not the caller's.

    """
    detail = uow.reservations.find_detail(key, owner_scope_for(actor))
    if detail is None:
        raise reservation_not_found(key)
    return detail


def customer_of(uow: UnitOfWork, reservation: Reservation) -> CustomerProfile:
    """Return the customer profile a reservation belongs to.

    Raises:
        LookupError: If the profile cannot be read. A reservation carries a
            foreign key to its profile and nothing is ever deleted, so this is
            a fault in the data and not something a caller can put right.

    """
    customer = uow.customers.get(reservation.customer_profile_id)
    if customer is None:
        raise LookupError(
            f"Attempted to read customer profile {reservation.customer_profile_id} of "
            f"reservation {reservation.reference}, and it could not be read."
        )
    return customer


def state_of(reservation: Reservation) -> dict[str, StateValue]:
    """Return what an audit event records about where a reservation stands."""
    hold_expires_at = reservation.hold_expires_at
    return {
        "status": reservation.status.value,
        "hold_expires_at": hold_expires_at.isoformat() if hold_expires_at else None,
        "active_allocation_count": sum(
            len(line.active_allocations()) for line in reservation.lines
        ),
    }


def record_change(
    uow: UnitOfWork,
    *,
    actor: Actor | None,
    reservation: Reservation,
    action: str,
    occurred_at: datetime,
    before: dict[str, StateValue] | None,
    extra: dict[str, StateValue] | None = None,
) -> None:
    """Record the audit event of one change to a reservation (BR-49).

    Args:
        uow: The open unit of work the change was made in.
        actor: Who made the change, or None for the sweep, which nobody asks for.
        reservation: The reservation as it is now.
        action: The name of the change, for example `reservation.held`.
        occurred_at: When it happened, from the clock.
        before: Where the reservation stood before, or None for a creation.
        extra: Anything else the event should say about the change.

    """
    uow.audit.record(
        audit_event_for(
            actor=actor,
            entity_type=RESERVATION_ENTITY_TYPE,
            entity_id=reservation.id,
            action=action,
            occurred_at=occurred_at,
            before_state=before,
            after_state={
                "reference": reservation.reference,
                **state_of(reservation),
                **(extra or {}),
            },
        )
    )
