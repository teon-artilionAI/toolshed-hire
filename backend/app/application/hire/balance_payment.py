"""The use case that records the payment of a balance, which is BR-33.

When the deposit could not cover what a hire owed, the rental stays RETURNED
with a balance due and waits on the payment. Staff at the branch the hire
went out from record the simulated payment with the reference the customer
was given (BR-43). In one unit of work the rental is locked, every charge
still pending is settled with that reference, the balance comes down to
nothing, and the rental becomes SETTLED with `settled_at` stamped (BR-53). No
payment gateway is called and no card detail is taken.

A rental with nothing due is refused with 409.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.application.clock import Clock
from app.application.hire.read_models import RentalKey
from app.application.hire.read_rental import read_rental
from app.application.hire.rental_access import load_rental_for_change
from app.application.hire.rental_audit import (
    RENTAL_BALANCE_PAID_ACTION,
    record_rental_change,
    rental_state,
)
from app.application.hire.views import RentalView, rental_view_for
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.identity import Actor
from app.domain.policies.late_fee import LateFeePolicy
from app.domain.settlement import record_balance_payment

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BalancePaymentCommand:
    """A request to record that a rental's balance was paid.

    Attributes:
        actor: The member of staff at the counter.
        key: The rental, by its key or its reference.
        payment_reference: The reference of the simulated payment.

    """

    actor: Actor
    key: RentalKey
    payment_reference: str


class RecordBalancePaymentUseCase(UseCase[BalancePaymentCommand, RentalView]):
    """Record the simulated payment of a balance and settle the rental, in one transaction."""

    def __init__(self, uow: UnitOfWork, clock: Clock, policy: LateFeePolicy) -> None:
        """Keep the unit of work, the clock and the late fee policy the answer is shown with."""
        super().__init__(uow, clock)
        self._policy = policy

    def execute(self, command: BalancePaymentCommand) -> RentalView:
        """Record the payment, or refuse and change nothing.

        Raises:
            NotFound: If there is no such rental.
            BranchScopeError: If counter staff record a payment at another branch.
            StateTransitionError: If nothing is owed on the rental.

        """
        actor = command.actor
        reference = command.payment_reference.strip()
        logger.info(
            "rental.balance_payment_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "rental": str(command.key),
                "payment_reference": reference,
            },
        )
        now = self._clock.now()
        with self._uow as uow:
            rental = load_rental_for_change(uow, actor, command.key)
            before = rental_state(rental)
            paid = record_balance_payment(rental, payment_reference=reference, now=now)
            record_rental_change(
                uow,
                actor=actor,
                rental=rental,
                action=RENTAL_BALANCE_PAID_ACTION,
                occurred_at=now,
                before=before,
                extra={"amount_paid": str(paid.amount), "payment_reference": reference},
            )
            uow.rentals.save(rental)
            detail = read_rental(uow, RentalKey.of(rental.id))
            uow.commit()
        logger.info(
            "rental.balance_paid",
            extra={
                "reference": detail.reference,
                "rental_id": str(detail.id),
                "amount_paid": str(paid.amount),
                "payment_reference": reference,
                "status": detail.status.value,
            },
        )
        return rental_view_for(actor, detail, self._clock.today(), self._policy)
