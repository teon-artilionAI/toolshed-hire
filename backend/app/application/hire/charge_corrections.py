"""The use cases that correct the money of a hire, which are BR-24, BR-25 and US-28.

An administrator waives a charge still owed, reverses a settled charge with a
new negated one, or adjusts a hire with a new ADJUSTMENT charge. The rules of
each are the domain's, in `app.domain.charge_corrections`. What the three use
cases share is the order things happen in, which lives once here.

In one unit of work the rental is locked with its items and its charges, the
part of the deposit paying for pending charges is noted, the correction is
made, the deposit, the balance and the status are worked out again through
the settlement (`rework_after_correction`), and the rental is written back.
The repository writes a charge's status only from PENDING to SETTLED or
WAIVED and refuses to write over any other, so no path here updates a settled
row. The audit event of the correction carries the actor and the reason
(BR-25), beside the event of the rework when there is one, and the whole is
committed once.

A charge is named by its key. One that does not exist is a 404. A refused
reason or amount names its field the way the request did, so a form can put
the sentence beside the right input.
"""

from __future__ import annotations

import logging
from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from app.application.audit import audit_event_for
from app.application.clock import Clock
from app.application.hire.read_models import RentalKey
from app.application.hire.read_rental import read_rental
from app.application.hire.rental_access import load_rental_for_change
from app.application.hire.settle import rework_after_correction
from app.application.hire.views import RentalView, rental_view_for
from app.application.identity.account_rules import refused_field
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.audit import StateValue
from app.domain.charge import Charge
from app.domain.charge_corrections import adjust, charge_on, reverse, waive
from app.domain.enums import ChargeStatus
from app.domain.errors import NotFound, ValidationFailure
from app.domain.identity import Actor
from app.domain.money import Money
from app.domain.policies.late_fee import LateFeePolicy
from app.domain.rental import Rental
from app.domain.resettlement import deposit_paying_for_pending

logger = logging.getLogger(__name__)

CHARGE_ENTITY_TYPE: Final[str] = "charge"
CHARGE_WAIVED_ACTION: Final[str] = "charge.waived"
CHARGE_REVERSED_ACTION: Final[str] = "charge.reversed"
CHARGE_ADJUSTED_ACTION: Final[str] = "charge.adjusted"
CHARGE_NOT_FOUND_MESSAGE: Final[str] = "We could not find that charge."


@dataclass(frozen=True, slots=True)
class ChargeCorrectionCommand:
    """A request to waive or to reverse one charge.

    Attributes:
        actor: The administrator correcting it.
        charge_id: The key of the charge.
        reason: Why, which is kept on the charge and in the audit log.

    """

    actor: Actor
    charge_id: UUID
    reason: str


@dataclass(frozen=True, slots=True)
class AdjustmentCommand:
    """A request to adjust a hire by an amount that includes VAT.

    Attributes:
        actor: The administrator adjusting it.
        key: The rental, by its key or its reference.
        amount_inc_vat: What the customer owes more, or a negative amount
            they are owed, VAT included.
        reason: Why, which is kept on the charge and in the audit log.

    """

    actor: Actor
    key: RentalKey
    amount_inc_vat: Money
    reason: str


@dataclass(frozen=True, slots=True)
class Correction:
    """What a correction did, for its audit event.

    Attributes:
        action: The name of the event.
        subject: The charge the event is about, which is the one waived, the
            one reversed or the new adjustment.
        written: The charge the correction wrote. The same as `subject`,
            except for a reversal, where it is the new negated charge.
        before: Where the subject stood before, or None for a new charge.

    """

    action: str
    subject: Charge
    written: Charge
    before: dict[str, StateValue] | None


class _CorrectionUseCase[CommandT: (ChargeCorrectionCommand, AdjustmentCommand)](
    UseCase[CommandT, RentalView]
):
    """The order every correction of a hire's money happens in, in one transaction."""

    def __init__(self, uow: UnitOfWork, clock: Clock, policy: LateFeePolicy) -> None:
        """Keep the unit of work, the clock and the late fee policy the rental is shown with."""
        super().__init__(uow, clock)
        self._policy = policy

    def execute(self, command: CommandT) -> RentalView:
        """Make the correction and work the rental out again, or refuse and change nothing.

        Raises:
            NotFound: If there is no such charge or rental.
            ValidationFailure: If the reason or the amount is refused.
            StateTransitionError: If the charge cannot be corrected that way.

        """
        actor = command.actor
        logger.info(
            "charge.correction_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "correction": type(self).__name__,
                **self._log_context(command),
            },
        )
        now = self._clock.now()
        with self._uow as uow:
            rental = load_rental_for_change(uow, actor, self._rental_key(uow, command))
            paying_before = deposit_paying_for_pending(rental)
            try:
                correction = self._correct(rental, command, now)
            except ValidationFailure as failure:
                raise refused_field(failure) from failure
            rework_after_correction(uow, rental, paying_before=paying_before, actor=actor, now=now)
            uow.rentals.save(rental)
            _record(uow, actor, rental, correction, now)
            detail = read_rental(uow, RentalKey.of(rental.id))
            uow.commit()
        logger.info(
            "charge.correction_finished",
            extra={
                "action": correction.action,
                "charge_id": str(correction.written.id),
                "reference": detail.reference,
                "rental_status": detail.status.value,
                "balance_due": str(detail.balance_due),
            },
        )
        return rental_view_for(actor, detail, self._clock.today(), self._policy)

    @abstractmethod
    def _rental_key(self, uow: UnitOfWork, command: CommandT) -> RentalKey:
        """Return the rental the command is about."""

    @abstractmethod
    def _correct(self, rental: Rental, command: CommandT, now: datetime) -> Correction:
        """Apply the correction to the locked rental and say what it did."""

    @abstractmethod
    def _log_context(self, command: CommandT) -> dict[str, str]:
        """Return what the log says about the command."""


class WaiveChargeUseCase(_CorrectionUseCase[ChargeCorrectionCommand]):
    """Waive a charge still owed, with a reason (BR-25)."""

    def _rental_key(self, uow: UnitOfWork, command: ChargeCorrectionCommand) -> RentalKey:
        """Return the rental the charge is on."""
        return rental_of_charge(uow, command.charge_id)

    def _correct(
        self, rental: Rental, command: ChargeCorrectionCommand, now: datetime
    ) -> Correction:
        """Waive the charge."""
        waived = waive(rental, charge_on(rental, command.charge_id), reason=command.reason)
        return Correction(
            action=CHARGE_WAIVED_ACTION,
            subject=waived,
            written=waived,
            before={"status": ChargeStatus.PENDING.value},
        )

    def _log_context(self, command: ChargeCorrectionCommand) -> dict[str, str]:
        """Return the charge being waived."""
        return {"charge_id": str(command.charge_id)}


class ReverseChargeUseCase(_CorrectionUseCase[ChargeCorrectionCommand]):
    """Reverse a settled charge with a new negated one, with a reason (BR-24)."""

    def _rental_key(self, uow: UnitOfWork, command: ChargeCorrectionCommand) -> RentalKey:
        """Return the rental the charge is on."""
        return rental_of_charge(uow, command.charge_id)

    def _correct(
        self, rental: Rental, command: ChargeCorrectionCommand, now: datetime
    ) -> Correction:
        """Raise the reversal of the charge, which is left exactly as it was."""
        original = charge_on(rental, command.charge_id)
        reversal = reverse(
            rental, original, reason=command.reason, raised_by=command.actor.user_id, now=now
        )
        return Correction(
            action=CHARGE_REVERSED_ACTION,
            subject=original,
            written=reversal,
            before={"status": original.status.value},
        )

    def _log_context(self, command: ChargeCorrectionCommand) -> dict[str, str]:
        """Return the charge being reversed."""
        return {"charge_id": str(command.charge_id)}


class AdjustRentalUseCase(_CorrectionUseCase[AdjustmentCommand]):
    """Adjust a hire by an amount that includes VAT, with a reason."""

    def _rental_key(self, uow: UnitOfWork, command: AdjustmentCommand) -> RentalKey:
        """Return the rental the command names."""
        return command.key

    def _correct(self, rental: Rental, command: AdjustmentCommand, now: datetime) -> Correction:
        """Raise the adjustment."""
        adjustment = adjust(
            rental,
            amount_inc_vat=command.amount_inc_vat,
            reason=command.reason,
            raised_by=command.actor.user_id,
            now=now,
        )
        return Correction(
            action=CHARGE_ADJUSTED_ACTION, subject=adjustment, written=adjustment, before=None
        )

    def _log_context(self, command: AdjustmentCommand) -> dict[str, str]:
        """Return the rental and the amount."""
        return {"rental": str(command.key), "amount_inc_vat": str(command.amount_inc_vat.amount)}


def rental_of_charge(uow: UnitOfWork, charge_id: UUID) -> RentalKey:
    """Return the rental a charge is on.

    Raises:
        NotFound: If there is no such charge.

    """
    rental_id = uow.rentals.find_rental_of_charge(charge_id)
    if rental_id is None:
        logger.info("charge.not_found", extra={"charge_id": str(charge_id)})
        raise NotFound(CHARGE_NOT_FOUND_MESSAGE, {"charge": str(charge_id)})
    return RentalKey.of(rental_id)


def _record(
    uow: UnitOfWork, actor: Actor, rental: Rental, correction: Correction, now: datetime
) -> None:
    """Record the audit event of the correction, with the actor and the reason (BR-25)."""
    written = correction.written
    after: dict[str, StateValue] = {
        "status": correction.subject.status.value,
        "reason": written.reason,
        "rental_reference": rental.reference,
        "charge_type": written.charge_type.value,
        "amount_inc_vat": str(written.amount_inc_vat),
        "rental_status": rental.status.value,
        "balance_due": str(rental.balance_due),
    }
    if written.id != correction.subject.id:
        after["reversal_charge_id"] = str(written.id)
    uow.audit.record(
        audit_event_for(
            actor=actor,
            entity_type=CHARGE_ENTITY_TYPE,
            entity_id=correction.subject.id,
            action=correction.action,
            occurred_at=now,
            before_state=correction.before,
            after_state=after,
        )
    )
