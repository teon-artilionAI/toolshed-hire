"""The audit events of a hire after checkout, written in the unit of work of the change (BR-49).

A return, a loss, a settlement, a balance payment and the sweep that marks a
hire overdue each write an event for the rental, saying where it stood before
and where it stands now, with the three figures of the deposit. A unit that
moves writes an event of its own, the way a checkout writes one for every unit
it hands over, so the history of a unit can be read without the rental.

An event names an asset by its tag. The audit trail is read by staff only, and
the tag is what they know a unit by.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Final

from app.application.audit import audit_event_for
from app.application.unit_of_work import UnitOfWork
from app.domain.audit import StateValue
from app.domain.identity import Actor
from app.domain.rental import Rental
from app.domain.returns import ClosedUnit

RENTAL_ENTITY_TYPE: Final[str] = "rental"
ASSET_ENTITY_TYPE: Final[str] = "asset"
ASSET_STATUS_CHANGED_ACTION: Final[str] = "asset.status_changed"
RENTAL_ITEMS_RETURNED_ACTION: Final[str] = "rental.items_returned"
RENTAL_ITEM_LOST_ACTION: Final[str] = "rental.item_lost"
RENTAL_DEPOSIT_SETTLED_ACTION: Final[str] = "rental.deposit_settled"
RENTAL_BALANCE_PAID_ACTION: Final[str] = "rental.balance_paid"
RENTAL_OVERDUE_ACTION: Final[str] = "rental.overdue"
RESERVATION_RETURNED_ACTION: Final[str] = "reservation.returned"


def rental_state(rental: Rental) -> dict[str, StateValue]:
    """Return what an audit event records about where a rental stands."""
    return {
        "reference": rental.reference,
        "status": rental.status.value,
        "items_out": len(rental.items_out()),
        "deposit_held": str(rental.deposit_held),
        "deposit_withheld": str(rental.deposit_withheld),
        "deposit_refunded": str(rental.deposit_refunded),
        "balance_due": str(rental.balance_due),
        "settled_at": rental.settled_at.isoformat() if rental.settled_at else None,
    }


def record_rental_change(
    uow: UnitOfWork,
    *,
    actor: Actor | None,
    rental: Rental,
    action: str,
    occurred_at: datetime,
    before: dict[str, StateValue],
    extra: dict[str, StateValue] | None = None,
) -> None:
    """Record the audit event of one change to a rental (BR-49).

    Args:
        uow: The open unit of work the change was made in.
        actor: Who made the change, or None for the sweep, which nobody asks for.
        rental: The rental as it is now.
        action: The name of the change, for example `rental.items_returned`.
        occurred_at: When it happened, from the clock.
        before: Where the rental stood before, from `rental_state`.
        extra: Anything else the event should say about the change.

    """
    uow.audit.record(
        audit_event_for(
            actor=actor,
            entity_type=RENTAL_ENTITY_TYPE,
            entity_id=rental.id,
            action=action,
            occurred_at=occurred_at,
            before_state=before,
            after_state={**rental_state(rental), **(extra or {})},
        )
    )


def record_unit_moves(
    uow: UnitOfWork,
    *,
    actor: Actor,
    units: Iterable[ClosedUnit],
    rental_reference: str,
    occurred_at: datetime,
) -> None:
    """Record the move of every unit a return or a loss closed (BR-49)."""
    for closed in units:
        uow.audit.record(
            audit_event_for(
                actor=actor,
                entity_type=ASSET_ENTITY_TYPE,
                entity_id=closed.unit.id,
                action=ASSET_STATUS_CHANGED_ACTION,
                occurred_at=occurred_at,
                before_state={"status": closed.unit_before.status.value},
                after_state={
                    "status": closed.unit.status.value,
                    "asset_tag": closed.unit.asset_tag,
                    "rental_reference": rental_reference,
                    "days_late": closed.late_fee.days_late,
                    "late_fee": str(closed.late_fee.amount.amount),
                },
            )
        )


__all__ = [
    "ASSET_ENTITY_TYPE",
    "ASSET_STATUS_CHANGED_ACTION",
    "RENTAL_BALANCE_PAID_ACTION",
    "RENTAL_DEPOSIT_SETTLED_ACTION",
    "RENTAL_ENTITY_TYPE",
    "RENTAL_ITEMS_RETURNED_ACTION",
    "RENTAL_ITEM_LOST_ACTION",
    "RENTAL_OVERDUE_ACTION",
    "RESERVATION_RETURNED_ACTION",
    "record_rental_change",
    "record_unit_moves",
    "rental_state",
]
