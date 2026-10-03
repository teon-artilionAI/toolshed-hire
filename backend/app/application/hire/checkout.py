"""The use case that checks a reservation out, which opens its rental (FR-17, US-22).

A counter assistant hands the equipment of a confirmed reservation over on or
after the first day of the hire, at the collection branch (BR-26). In one unit
of work the reservation is locked, the units it holds are locked, the rental is
opened with the next reference from the rental sequence, every allocation
becomes one rental item (BR-28), the hire charge and the deposit hold are
written (BR-27), every unit moves to ON_HIRE, the reservation moves to
COLLECTED, and an audit event is written for the reservation, for the rental
and for every unit (BR-49). Either all of that is committed or none of it is.

The rules are the domain's (`app.domain.checkout`). What this use case adds is
the order things are found in and who is asking.

A checkout asked for again, by a second click or a second assistant, finds the
rental the first one opened and answers with it. It writes nothing. Two that
arrive together take turns on the lock of the reservation, so the second sees
the rental the first committed, and the unique key on the reservation of a
rental is the last word if anything ever got past the lock.

A refusal that names a field of the list names it the way the request did, so
a form can put the sentence beside the right input.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final
from uuid import UUID

from app.application.audit import audit_event_for
from app.application.booking.access import (
    RESERVATION_COLLECTED_ACTION,
    load_for_change,
    record_change,
    state_of,
)
from app.application.booking.read_models import ReservationKey
from app.application.clock import Clock
from app.application.hire.read_models import RentalKey
from app.application.hire.read_rental import read_rental
from app.application.hire.rental_audit import (
    ASSET_ENTITY_TYPE,
    ASSET_STATUS_CHANGED_ACTION,
    RENTAL_ENTITY_TYPE,
)
from app.application.hire.views import RentalView, rental_view_for
from app.application.identity.account_rules import refused_field
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.audit import StateValue
from app.domain.booking import Reservation
from app.domain.catalogue import Asset
from app.domain.checkout import Checkout, HandOver, check_out, ensure_collectable
from app.domain.errors import ValidationFailure
from app.domain.identity import Actor
from app.domain.policies.late_fee import LateFeePolicy

logger = logging.getLogger(__name__)

RENTAL_CHECKED_OUT_ACTION: Final[str] = "rental.checked_out"

__all__ = [
    "ASSET_ENTITY_TYPE",
    "ASSET_STATUS_CHANGED_ACTION",
    "RENTAL_CHECKED_OUT_ACTION",
    "RENTAL_ENTITY_TYPE",
    "CheckoutCommand",
    "CheckoutOutcome",
    "CheckoutRentalUseCase",
]


@dataclass(frozen=True, slots=True)
class CheckoutCommand:
    """A request to hand the equipment of one reservation over.

    Attributes:
        actor: The member of staff at the counter.
        key: The reservation, by its key or its reference.
        hand_overs: What the counter recorded for each unit.
        agreement_signed: Whether the customer signed the hire agreement.

    """

    actor: Actor
    key: ReservationKey
    hand_overs: tuple[HandOver, ...]
    agreement_signed: bool


@dataclass(frozen=True, slots=True)
class CheckoutOutcome:
    """The rental a checkout answered with.

    Attributes:
        rental: The rental as the caller sees it.
        created: True when this checkout opened it, and False when it was
            opened by an earlier one and nothing was written now.

    """

    rental: RentalView
    created: bool


class CheckoutRentalUseCase(UseCase[CheckoutCommand, CheckoutOutcome]):
    """Open the rental of a confirmed reservation, in one transaction."""

    def __init__(self, uow: UnitOfWork, clock: Clock, policy: LateFeePolicy) -> None:
        """Keep the unit of work, the clock and the late fee policy the rental is shown with.

        Args:
            uow: The unit of work that owns the transaction.
            clock: Where the current instant and business day come from.
            policy: The late fee policy, which says what a unit still out would
                owe today when a checkout asked again finds an older rental.

        """
        super().__init__(uow, clock)
        self._policy = policy

    def execute(self, command: CheckoutCommand) -> CheckoutOutcome:
        """Check the reservation out, or answer with the rental an earlier checkout opened.

        Raises:
            NotFound: If there is no such reservation.
            BranchScopeError: If counter staff check out at another branch.
            StateTransitionError: If the reservation is not confirmed, its
                hire has not started, or a unit cannot go out on hire.
            ValidationFailure: If the list of units is wrong or the agreement
                is not signed. The detail names the field.

        """
        actor = command.actor
        logger.info(
            "rental.checkout_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "reservation": str(command.key),
                "unit_count": len(command.hand_overs),
                "agreement_signed": command.agreement_signed,
            },
        )
        now = self._clock.now()
        today = self._clock.today()
        with self._uow as uow:
            reservation = load_for_change(uow, actor, command.key)
            existing = uow.rentals.find_id_for_reservation(reservation.id)
            if existing is not None:
                detail = read_rental(uow, RentalKey.of(existing))
                logger.info(
                    "rental.checkout_repeated",
                    extra={"reference": detail.reference, "rental_id": str(existing)},
                )
                return CheckoutOutcome(
                    rental=rental_view_for(actor, detail, today, self._policy), created=False
                )
            ensure_collectable(reservation, today)
            before = state_of(reservation)
            units = {unit.id: unit for unit in uow.assets.lock_units(_held_asset_ids(reservation))}
            checkout = _checked_out(uow, command, reservation, units, now, today)
            uow.rentals.add(checkout.rental)
            uow.assets.save_units(checkout.units)
            uow.reservations.save(reservation)
            record_change(
                uow,
                actor=actor,
                reservation=reservation,
                action=RESERVATION_COLLECTED_ACTION,
                occurred_at=now,
                before=before,
                extra={
                    "rental_id": str(checkout.rental.id),
                    "rental_reference": checkout.rental.reference,
                },
            )
            _record_hand_over(uow, actor, checkout, units, reservation.reference, now)
            detail = read_rental(uow, RentalKey.of(checkout.rental.id))
            uow.commit()
        logger.info(
            "rental.checkout_finished",
            extra={
                "reference": detail.reference,
                "rental_id": str(detail.id),
                "reservation_reference": reservation.reference,
                "unit_count": len(detail.items),
                "deposit_held": str(detail.deposit_held),
            },
        )
        return CheckoutOutcome(
            rental=rental_view_for(actor, detail, today, self._policy), created=True
        )


def _held_asset_ids(reservation: Reservation) -> list[UUID]:
    """Return the key of every unit the reservation holds right now."""
    return [
        allocation.asset_id
        for line in reservation.lines
        for allocation in line.active_allocations()
    ]


def _checked_out(
    uow: UnitOfWork,
    command: CheckoutCommand,
    reservation: Reservation,
    units: dict[UUID, Asset],
    now: datetime,
    today: date,
) -> Checkout:
    """Run the checkout of the domain, naming a refused field as the request named it."""
    model_ids = [line.product_model_id for line in reservation.lines]
    try:
        return check_out(
            reservation=reservation,
            hand_overs=command.hand_overs,
            agreement_signed=command.agreement_signed,
            reference=uow.rentals.next_reference(reservation.period.start.year),
            model_names=uow.product_models.names_of(model_ids),
            units=units,
            checked_out_by=command.actor.user_id,
            now=now,
            today=today,
        )
    except ValidationFailure as failure:
        raise refused_field(failure) from failure


def _record_hand_over(
    uow: UnitOfWork,
    actor: Actor,
    checkout: Checkout,
    units_before: dict[UUID, Asset],
    reservation_reference: str,
    now: datetime,
) -> None:
    """Record the opening of the rental and the move of every unit on hire (BR-49)."""
    rental = checkout.rental
    asset_tags = sorted(unit.asset_tag for unit in checkout.units)
    rental_state: dict[str, StateValue] = {
        "reference": rental.reference,
        "reservation_reference": reservation_reference,
        "status": rental.status.value,
        "asset_tags": asset_tags,
        "deposit_held": str(rental.deposit_held),
        "charge_types": [charge.charge_type.value for charge in rental.charges],
        "agreement_signed": rental.agreement_signed,
    }
    uow.audit.record(
        audit_event_for(
            actor=actor,
            entity_type=RENTAL_ENTITY_TYPE,
            entity_id=rental.id,
            action=RENTAL_CHECKED_OUT_ACTION,
            occurred_at=now,
            after_state=rental_state,
        )
    )
    for unit in checkout.units:
        uow.audit.record(
            audit_event_for(
                actor=actor,
                entity_type=ASSET_ENTITY_TYPE,
                entity_id=unit.id,
                action=ASSET_STATUS_CHANGED_ACTION,
                occurred_at=now,
                before_state={"status": units_before[unit.id].status.value},
                after_state={
                    "status": unit.status.value,
                    "asset_tag": unit.asset_tag,
                    "rental_reference": rental.reference,
                },
            )
        )
