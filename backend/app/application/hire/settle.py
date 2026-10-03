"""Settling the deposit when nothing is waiting any more, inside the caller's unit of work (BR-32).

The deposit of a hire is settled the moment the last thing it waits on is
lifted. A return that brings the last unit back is such a moment, and so is a
loss that closes the last unit, and so is the damage report that completes the
last assessment of a hire whose units are all back. All three call this.

`settle_when_nothing_waits` asks `settlement_wait` of the domain what the
rental still waits on. Only when the answer is nothing, and the deposit has
not already been settled, does it settle it, in the same unit of work as the
change that lifted the last wait, and record the figures it produced.

How many returned units still wait for their damage to be assessed is
`assessments_due_on` in `app.domain.quarantine`. A unit that came back worse
or flagged waits until a damage report names it (BR-35).
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.application.hire.rental_audit import (
    RENTAL_DEPOSIT_SETTLED_ACTION,
    record_rental_change,
    rental_state,
)
from app.application.unit_of_work import UnitOfWork
from app.domain.identity import Actor
from app.domain.quarantine import assessments_due_on
from app.domain.rental import Rental
from app.domain.settlement import (
    DepositSettlement,
    deposit_was_settled,
    settle_deposit,
    settlement_wait,
)

logger = logging.getLogger(__name__)


def settle_when_nothing_waits(
    uow: UnitOfWork, rental: Rental, *, actor: Actor, now: datetime
) -> DepositSettlement | None:
    """Settle the deposit of a rental if nothing is waiting, and record it. Nothing is committed.

    Args:
        uow: The open unit of work that holds the lock on the rental.
        rental: The rental, as the change before this left it.
        actor: The member of staff whose action lifted the last wait.
        now: The current instant, from the clock.

    Returns:
        The figures of the settlement, or None when the rental still waits on
        something or was settled already.

    """
    waiting = settlement_wait(
        status=rental.status,
        items_out=len(rental.items_out()),
        assessments_due=assessments_due_on(rental),
        balance_due=rental.balance_due,
    )
    if waiting is not None or deposit_was_settled(rental):
        logger.debug(
            "rental.settlement_not_yet",
            extra={
                "reference": rental.reference,
                "waiting_on": waiting.value if waiting is not None else None,
            },
        )
        return None
    before = rental_state(rental)
    settlement = settle_deposit(rental, settled_by=actor.user_id, now=now)
    record_rental_change(
        uow,
        actor=actor,
        rental=rental,
        action=RENTAL_DEPOSIT_SETTLED_ACTION,
        occurred_at=now,
        before=before,
        extra={
            "deposit_forfeited": str(settlement.forfeited.amount),
            "owed": str(settlement.owed.amount),
        },
    )
    logger.info(
        "rental.deposit_settled",
        extra={
            "reference": rental.reference,
            "rental_id": str(rental.id),
            "deposit_held": str(settlement.held.amount),
            "deposit_forfeited": str(settlement.forfeited.amount),
            "owed": str(settlement.owed.amount),
            "deposit_withheld": str(settlement.withheld.amount),
            "deposit_released": str(settlement.released.amount),
            "balance_due": str(settlement.balance_due.amount),
            "status": rental.status.value,
        },
    )
    return settlement
