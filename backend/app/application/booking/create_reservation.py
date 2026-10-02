"""The use case that creates a reservation, as a draft (FR-05, US-11).

A draft is a basket. It names a branch, a period and one or more models, and
it is priced, so the customer sees what the hire will cost before anything is
held. Nothing is allocated here. Units are taken when the draft is put on
hold, which is a use case of its own.

The figures are fixed at this moment. The rates, the deposit, the late fee and
the replacement value of each model are copied onto its line (BR-20), the
pricing policy prices each line from that copy with the customer's trade
discount (BR-21), and the totals are stored. A later change to the catalogue
does not alter them.

A reservation belongs to a customer profile and not to an account. A customer
books for their own profile. Counter staff and administrators name the profile
they are booking for, which is how a walk-in with no login gets a booking, and
counter staff may only book at their own branch (BR-43).

The reservation, its lines and its audit event are written in one unit of
work, so either all of it exists or none of it does (BR-49).

Every refusal about something the caller sent names the field it was sent in,
so a form can put the sentence beside the right input.
"""

from __future__ import annotations

import logging

from app.application.availability.hire_request import requested_period
from app.application.booking.access import (
    RESERVATION_CREATED_ACTION,
    read_detail,
    record_change,
)
from app.application.booking.read_models import ReservationKey
from app.application.booking.reservation_request import (
    CreateReservationCommand,
    branch_of,
    customer_named_in,
    ensure_customer_names_nobody,
    ensure_lines_are_well_formed,
    models_of,
)
from app.application.booking.views import ReservationView, view_for
from app.application.clock import Clock
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.booking import Reservation
from app.domain.identity import ensure_branch_scope
from app.domain.policies.pricing import PricingPolicy

logger = logging.getLogger(__name__)

class CreateReservationUseCase(UseCase[CreateReservationCommand, ReservationView]):
    """Create a priced draft reservation, with nothing held yet."""

    def __init__(self, uow: UnitOfWork, clock: Clock, pricing: PricingPolicy) -> None:
        """Keep the collaborators the use case works with.

        Args:
            uow: The unit of work that owns the transaction.
            clock: Where the current instant and business day come from.
            pricing: The policy that works out what the hire costs.

        """
        super().__init__(uow, clock)
        self._pricing = pricing

    def execute(self, command: CreateReservationCommand) -> ReservationView:
        """Create the draft and return it as the caller sees it.

        Raises:
            AuthorisationFailure: If a customer names a customer profile.
            ValidationFailure: If the period, the branch, a line or the
                customer is refused. The failure names the field.
            BranchScopeError: If counter staff book at another branch.
            AccountOnHoldError: If the customer's account is on hold (BR-18).

        """
        actor = command.actor
        logger.info(
            "reservation.create_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "branch_code": command.branch_code,
                "line_count": len(command.lines),
                "for_named_customer": command.customer_profile_id is not None,
            },
        )
        ensure_customer_names_nobody(command)
        period = requested_period(command.start, command.end, self._clock.today())
        ensure_lines_are_well_formed(command.lines)

        now = self._clock.now()
        with self._uow as uow:
            branch = branch_of(uow, command.branch_code)
            ensure_branch_scope(actor, branch.id)
            customer = customer_named_in(uow, command)
            customer.ensure_may_book()
            models = models_of(uow, command.lines, period)

            reservation = Reservation.draft(
                reference=uow.reservations.next_reference(period.start.year),
                customer_profile_id=customer.id,
                branch_id=branch.id,
                period=period,
                created_by_user_id=actor.user_id,
                notes=command.notes,
            )
            for requested, model in zip(command.lines, models, strict=True):
                reservation.add_line(model, requested.quantity)
            reservation.price_with(self._pricing, customer.trade_discount_percent)
            uow.reservations.add(reservation)
            record_change(
                uow,
                actor=actor,
                reservation=reservation,
                action=RESERVATION_CREATED_ACTION,
                occurred_at=now,
                before=None,
                extra={
                    "customer_profile_id": str(customer.id),
                    "branch_id": str(branch.id),
                    "start_date": period.start.isoformat(),
                    "end_date": period.end.isoformat(),
                    "model_skus": [model.sku for model in models],
                    "estimated_total_inc_vat": str(reservation.estimated_total_inc_vat),
                },
            )
            detail = read_detail(uow, actor, ReservationKey.of(reservation.id))
            uow.commit()
        logger.info(
            "reservation.create_finished",
            extra={
                "reference": reservation.reference,
                "reservation_id": str(reservation.id),
                "outcome": reservation.status.value,
                "pricing_policy": self._pricing.name(),
                "line_count": len(reservation.lines),
            },
        )
        return view_for(actor, detail, now)
