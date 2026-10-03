"""What every use case that changes a rental does before its own work.

A rental is found by its key or its reference and locked, with its items and
its charges, so two changes to one rental take turns and the second sees what
the first committed. Counter staff may change a rental at their own branch
only, so one at another branch is refused before anything is changed (BR-43).
An administrator acts at every branch.

The reservation the rental was opened from is locked next, because a return
lets go of its allocations and closing the hire closes the reservation. The
order is always the rental first and then the reservation, so two returns
cannot lock the two in opposite orders.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from uuid import UUID

from app.application.booking.read_models import ReservationKey
from app.application.hire.read_models import RentalKey
from app.application.hire.read_rental import RENTAL_NOT_FOUND_MESSAGE
from app.application.ownership import owner_scope_for
from app.application.unit_of_work import UnitOfWork
from app.domain.booking import Reservation
from app.domain.catalogue import Asset
from app.domain.errors import NotFound
from app.domain.identity import Actor, ensure_branch_scope
from app.domain.rental import Rental

logger = logging.getLogger(__name__)


def load_rental_for_change(uow: UnitOfWork, actor: Actor, key: RentalKey) -> Rental:
    """Return the rental a member of staff wants to change, locked, or refuse.

    Args:
        uow: The open unit of work.
        actor: Who is asking, with the role and the branch they hold.
        key: The rental asked for.

    Raises:
        NotFound: If there is no such rental.
        BranchScopeError: If the actor is counter staff and the rental went
            out from another branch.

    """
    rental = uow.rentals.find_for_update(key)
    if rental is None:
        logger.info(
            "rental.not_found",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "rental": str(key),
                "attempted": "load a rental to change it",
            },
        )
        raise NotFound(RENTAL_NOT_FOUND_MESSAGE, {"rental": str(key)})
    ensure_branch_scope(actor, rental.branch_id)
    return rental


def reservation_of(uow: UnitOfWork, actor: Actor, rental: Rental) -> Reservation:
    """Return the reservation a rental was opened from, locked.

    Raises:
        LookupError: If it cannot be read. A rental carries a foreign key to
            its reservation and nothing is ever deleted, so this is a fault in
            the data and not something a caller can put right.

    """
    reservation = uow.reservations.find_for_update(
        ReservationKey.of(rental.reservation_id), owner_scope_for(actor)
    )
    if reservation is None:
        raise LookupError(
            f"Attempted to lock reservation {rental.reservation_id} of rental "
            f"{rental.reference}, and it could not be read."
        )
    return reservation


def lock_units_of(uow: UnitOfWork, rental: Rental, item_ids: Iterable[UUID]) -> dict[UUID, Asset]:
    """Lock the units of the named items that are on the rental, and return them by their key.

    An item that is not on the rental is left out here. The domain refuses it
    with the field that named it.
    """
    asset_ids = [
        item.asset_id
        for item_id in item_ids
        if (item := rental.item_with_id(item_id)) is not None
    ]
    if not asset_ids:
        return {}
    return {unit.id: unit for unit in uow.assets.lock_units(asset_ids)}
