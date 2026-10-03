"""The use case that takes units back, which is FR-18, FR-19, US-23 and US-25.

A counter assistant names the units that came back, at the branch the hire
went out from (BR-43). In one unit of work the rental is locked, then the
reservation it was opened from, then the units coming back. Each unit is
recorded as back with its condition, its meter and its accessories, the late
fee policy works out what it owes (BR-30), a late fee is raised when there is
one, its allocation is let go with the reason RETURNED, and it moves back to
AVAILABLE so it can be booked from that day. The rental moves on to
PARTIALLY_RETURNED, or to RETURNED with the reservation when the last unit is
back (BR-29). When nothing else is waiting the deposit is settled in the same
unit of work (BR-32). Audit events are written for the rental, for every unit,
for the reservation and for the settlement (BR-49). Either all of that is
committed or none of it is.

The rules are the domain's (`app.domain.returns` and `app.domain.settlement`).
What this use case adds is the order things are locked in and who is asking.
A refusal that names a field of the list names it the way the request did.

Two returns of the same unit at once take turns on the lock of the rental.
The second finds the unit already back and is refused with 409.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.application.booking.access import record_change, state_of
from app.application.clock import Clock
from app.application.hire.read_models import RentalKey
from app.application.hire.read_rental import read_rental
from app.application.hire.rental_access import (
    load_rental_for_change,
    lock_units_of,
    reservation_of,
)
from app.application.hire.rental_audit import (
    RENTAL_ITEMS_RETURNED_ACTION,
    RESERVATION_RETURNED_ACTION,
    record_rental_change,
    record_unit_moves,
    rental_state,
)
from app.application.hire.settle import settle_when_nothing_waits
from app.application.hire.views import RentalView, rental_view_for
from app.application.identity.account_rules import refused_field
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.audit import StateValue
from app.domain.errors import ValidationFailure
from app.domain.identity import Actor
from app.domain.policies.late_fee import LateFeePolicy
from app.domain.returns import ItemReturn, ReturnOutcome, return_items

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ReturnCommand:
    """A request to take some or all of the units of one rental back.

    Attributes:
        actor: The member of staff at the counter.
        key: The rental, by its key or its reference.
        returns: What the counter recorded for each unit coming back.

    """

    actor: Actor
    key: RentalKey
    returns: tuple[ItemReturn, ...]


class ReturnRentalItemsUseCase(UseCase[ReturnCommand, RentalView]):
    """Take units back, charge what they owe and settle the deposit when it may be."""

    def __init__(self, uow: UnitOfWork, clock: Clock, policy: LateFeePolicy) -> None:
        """Keep the unit of work, the clock and the late fee policy.

        Args:
            uow: The unit of work that owns the transaction.
            clock: Where the current instant and business day come from.
            policy: The late fee policy. Nothing else works out a late fee.

        """
        super().__init__(uow, clock)
        self._policy = policy

    def execute(self, command: ReturnCommand) -> RentalView:
        """Record the return of the named units, or refuse and change nothing.

        Raises:
            NotFound: If there is no such rental.
            BranchScopeError: If counter staff take units back at another branch.
            ValidationFailure: If a unit is listed twice, is not on the rental
                or has a meter reading below the one it went out with. The
                detail names the field.
            StateTransitionError: If a unit is already back.

        """
        actor = command.actor
        logger.info(
            "rental.return_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "rental": str(command.key),
                "unit_count": len(command.returns),
                "late_fee_policy": self._policy.name(),
            },
        )
        now = self._clock.now()
        today = self._clock.today()
        with self._uow as uow:
            rental = load_rental_for_change(uow, actor, command.key)
            reservation = reservation_of(uow, actor, rental)
            units = lock_units_of(uow, rental, (back.rental_item_id for back in command.returns))
            before = rental_state(rental)
            reservation_before = state_of(reservation)
            try:
                outcome = return_items(
                    rental=rental,
                    reservation=reservation,
                    returns=command.returns,
                    units=units,
                    policy=self._policy,
                    returned_by=actor.user_id,
                    now=now,
                    today=today,
                )
            except ValidationFailure as failure:
                raise refused_field(failure) from failure
            uow.assets.save_units([closed.unit for closed in outcome.units])
            uow.reservations.save(reservation)
            record_rental_change(
                uow,
                actor=actor,
                rental=rental,
                action=RENTAL_ITEMS_RETURNED_ACTION,
                occurred_at=now,
                before=before,
                extra=_returned_figures(outcome),
            )
            record_unit_moves(
                uow,
                actor=actor,
                units=outcome.units,
                rental_reference=rental.reference,
                occurred_at=now,
            )
            if outcome.closed_the_hire:
                record_change(
                    uow,
                    actor=actor,
                    reservation=reservation,
                    action=RESERVATION_RETURNED_ACTION,
                    occurred_at=now,
                    before=reservation_before,
                    extra={"rental_reference": rental.reference},
                )
            settle_when_nothing_waits(uow, rental, actor=actor, now=now)
            uow.rentals.save(rental)
            detail = read_rental(uow, RentalKey.of(rental.id))
            uow.commit()
        logger.info(
            "rental.return_finished",
            extra={
                "reference": detail.reference,
                "rental_id": str(detail.id),
                "status_before": outcome.status_before.value,
                "status": detail.status.value,
                **_returned_figures(outcome),
                "deposit_withheld": str(detail.deposit_withheld),
                "deposit_refunded": str(detail.deposit_refunded),
                "balance_due": str(detail.balance_due),
            },
        )
        return rental_view_for(actor, detail, today, self._policy)


def _returned_figures(outcome: ReturnOutcome) -> dict[str, StateValue]:
    """Return what the log and the audit event say about the units taken back."""
    return {
        "returned_count": len(outcome.units),
        "asset_tags": sorted(closed.unit.asset_tag for closed in outcome.units),
        "days_late": sum(closed.late_fee.days_late for closed in outcome.units),
        "late_fees": [str(closed.late_fee.amount.amount) for closed in outcome.units],
        "closed_the_hire": outcome.closed_the_hire,
    }
