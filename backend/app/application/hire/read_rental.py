"""Reading a rental, and reading a reservation as the counter is about to check it out.

Both reads are for staff, and the routes admit nobody else. Staff read a
rental at any branch and see what the checkout of any reservation would do,
because reading is never scoped by branch (BR-43). Whether the caller may act
is worked out on the server and returned with the read, so the counter screen
draws its buttons from the answer.

A rental is named by its key or its reference, and a reservation the same way.
One that does not exist is a `NotFound`, in a sentence the counter can act on.

Nothing wakes up when a due date passes, so the read of one rental makes sure
of the status of the rental it is about to show (BR-52). A rental with a unit
out past its due date that is not yet stored as OVERDUE is locked, moved and
committed through the overdue half of the lazy sweep, and read again, so its
detail never reads OPEN while the list would read OVERDUE.

Each read takes a bounded number of statements however many units the hire
has. A rental is three, one for the rental, one for its items and one for its
charges, and twice that and the move when it has just gone overdue. A checkout
is two, one for the reservation and one for its units.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Final
from uuid import UUID

from app.application.booking.access import ReservationCommand, reservation_not_found
from app.application.clock import Clock
from app.application.hire.overdue import mark_overdue_rental
from app.application.hire.read_models import RentalDetail, RentalKey
from app.application.hire.views import (
    CheckoutView,
    RentalView,
    checkout_view_for,
    rental_view_for,
)
from app.application.unit_of_work import UnitOfWork
from app.domain.errors import NotFound
from app.domain.identity import Actor
from app.domain.policies.late_fee import LateFeePolicy

logger = logging.getLogger(__name__)

RENTAL_NOT_FOUND_MESSAGE: Final[str] = (
    "We could not find that rental. Check the reference and try again."
)


@dataclass(frozen=True, slots=True)
class RentalCommand:
    """A request to read one rental.

    Attributes:
        actor: Who is asking, with the role and the branch they hold.
        key: The rental, by its key or its reference.

    """

    actor: Actor
    key: RentalKey


def read_rental(uow: UnitOfWork, key: RentalKey) -> RentalDetail:
    """Return one rental as a read model, inside an open unit of work.

    Raises:
        NotFound: If there is no such rental.

    """
    detail = uow.rentals.find_detail(key)
    if detail is None:
        logger.info("rental.not_found", extra={"rental": str(key)})
        raise NotFound(RENTAL_NOT_FOUND_MESSAGE, {"rental": str(key)})
    return detail


class ReadRentals:
    """Return a rental, or a reservation as it would be checked out, to a member of staff."""

    def __init__(self, uow: UnitOfWork, clock: Clock, policy: LateFeePolicy) -> None:
        """Keep the unit of work the reads run in, the clock and the late fee policy.

        Args:
            uow: The unit of work the reads run in.
            clock: Where the current business day comes from.
            policy: The late fee policy, which says what each unit still out
                would owe if it came back today.

        """
        self._uow = uow
        self._clock = clock
        self._policy = policy

    def one(self, command: RentalCommand) -> RentalView:
        """Return one rental as the caller sees it.

        Raises:
            NotFound: If there is no such rental.

        """
        actor = command.actor
        logger.info(
            "rental.read_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "rental": str(command.key),
            },
        )
        today = self._clock.today()
        with self._uow as uow:
            detail = read_rental(uow, command.key)
            if detail.is_stored_short_of_overdue(today):
                detail = self._mark_overdue(uow, detail.id, today)
        logger.info(
            "rental.read_finished",
            extra={"reference": detail.reference, "outcome": detail.status.value},
        )
        return rental_view_for(actor, detail, today, self._policy)

    def _mark_overdue(self, uow: UnitOfWork, rental_id: UUID, today: date) -> RentalDetail:
        """Move the one rental a read is about to show to OVERDUE, commit that, and read it again.

        The lock is taken and the domain asked again, because a unit can come
        back between the read and the lock. The move is a change in its own
        right and is committed at once, the way the lazy sweep commits it.
        """
        key = RentalKey.of(rental_id)
        rental = uow.rentals.find_for_update(key)
        if rental is not None and mark_overdue_rental(uow, rental, self._clock.now(), today):
            uow.commit()
        return read_rental(uow, key)

    def checkout(self, command: ReservationCommand) -> CheckoutView:
        """Return a reservation as the counter would check it out, and whether it may now.

        Raises:
            NotFound: If there is no such reservation.

        """
        actor = command.actor
        logger.info(
            "rental.checkout_read_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "reservation": str(command.key),
            },
        )
        with self._uow as uow:
            detail = uow.rentals.find_checkout(command.key)
        if detail is None:
            raise reservation_not_found(command.key)
        view = checkout_view_for(actor, detail, self._clock.today())
        logger.info(
            "rental.checkout_read_finished",
            extra={
                "reference": detail.reference,
                "unit_count": len(detail.units),
                "can_check_out": view.can_check_out,
            },
        )
        return view
