"""The use case that records a unit as lost, which is BR-31.

A unit still out more than fourteen days after it was due back may be
recorded as lost by staff at the branch the hire went out from (BR-43). In one
unit of work the rental, the reservation and the unit are locked, the domain
charges fourteen days of late fee, lets the allocation go, moves the unit to
LOST, keeps the deposit held for it and raises the recovery of the rest of its
replacement value (`app.domain.loss`). When it was the last unit out the hire
is closed, and when nothing else is waiting the deposit is settled in the same
unit of work (BR-32). Audit events are written for the rental, the unit, the
reservation and the settlement (BR-49).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

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
    RENTAL_ITEM_LOST_ACTION,
    RESERVATION_RETURNED_ACTION,
    record_rental_change,
    record_unit_moves,
    rental_state,
)
from app.application.hire.settle import settle_when_nothing_waits
from app.application.hire.views import RentalView, rental_view_for
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.audit import StateValue
from app.domain.identity import Actor
from app.domain.loss import record_loss
from app.domain.policies.late_fee import LateFeePolicy

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LossCommand:
    """A request to record one unit of a rental as lost.

    Attributes:
        actor: The member of staff at the counter.
        key: The rental, by its key or its reference.
        rental_item_id: The unit, by the key of its rental item.

    """

    actor: Actor
    key: RentalKey
    rental_item_id: UUID


class RecordLossUseCase(UseCase[LossCommand, RentalView]):
    """Record a unit as lost and charge for it, in one transaction."""

    def __init__(self, uow: UnitOfWork, clock: Clock, policy: LateFeePolicy) -> None:
        """Keep the unit of work, the clock and the late fee policy.

        Args:
            uow: The unit of work that owns the transaction.
            clock: Where the current instant and business day come from.
            policy: The late fee policy, which also says when a unit may be lost.

        """
        super().__init__(uow, clock)
        self._policy = policy

    def execute(self, command: LossCommand) -> RentalView:
        """Record the loss, or refuse and change nothing.

        Raises:
            NotFound: If there is no such rental, or the unit is not on it.
            BranchScopeError: If counter staff record a loss at another branch.
            StateTransitionError: If the unit is already back or is not yet
                more than fourteen days late.

        """
        actor = command.actor
        logger.info(
            "rental.loss_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "rental": str(command.key),
                "rental_item_id": str(command.rental_item_id),
                "late_fee_policy": self._policy.name(),
            },
        )
        now = self._clock.now()
        today = self._clock.today()
        with self._uow as uow:
            rental = load_rental_for_change(uow, actor, command.key)
            reservation = reservation_of(uow, actor, rental)
            units = lock_units_of(uow, rental, (command.rental_item_id,))
            before = rental_state(rental)
            reservation_before = state_of(reservation)
            outcome = record_loss(
                rental=rental,
                reservation=reservation,
                rental_item_id=command.rental_item_id,
                units=units,
                policy=self._policy,
                recorded_by=actor.user_id,
                now=now,
                today=today,
            )
            uow.assets.save_units([outcome.unit.unit])
            uow.reservations.save(reservation)
            figures: dict[str, StateValue] = {
                "asset_tag": outcome.unit.unit.asset_tag,
                "days_late": outcome.unit.late_fee.days_late,
                "late_fee": str(outcome.unit.late_fee.amount.amount),
                "deposit_forfeited": (
                    str(outcome.forfeit_charge.amount_inc_vat) if outcome.forfeit_charge else None
                ),
                "recovery": (
                    str(outcome.recovery_charge.amount_inc_vat)
                    if outcome.recovery_charge
                    else None
                ),
                "closed_the_hire": outcome.closed_the_hire,
            }
            record_rental_change(
                uow,
                actor=actor,
                rental=rental,
                action=RENTAL_ITEM_LOST_ACTION,
                occurred_at=now,
                before=before,
                extra=figures,
            )
            record_unit_moves(
                uow,
                actor=actor,
                units=(outcome.unit,),
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
            "rental.loss_recorded",
            extra={
                "reference": detail.reference,
                "rental_id": str(detail.id),
                "status_before": outcome.status_before.value,
                "status": detail.status.value,
                **figures,
                "balance_due": str(detail.balance_due),
            },
        )
        return rental_view_for(actor, detail, today, self._policy)
