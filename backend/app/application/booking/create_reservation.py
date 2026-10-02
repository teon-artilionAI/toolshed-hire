"""The use case that creates a held reservation.

It creates a reservation and one line, allocates specific assets to that line,
records the audit event, queues the confirmation and commits, all in one unit
of work. Either the whole booking exists or none of it does, which is BR-09
and BR-49 stated as code and not as a comment. If the audit event cannot be
written, nothing is committed.

The confirmation is sent only after the commit, with no transaction open. A
provider failure marks the notification failed and leaves the booking exactly
as it was committed (BR-19).

A reservation belongs to a customer profile and not to an account. The caller
still names the customer by account, because that is what the token and the
request carry, and the profile is resolved here.

The price snapshots on the line are copied from the product model (BR-20). The
money totals are not calculated yet. They are the output of the pricing policy
(BR-21), which is not built, so they are written as zero and not as a figure
worked out some other way that would look right and be wrong. The hold expiry
is left unset for the same reason. Setting it is BR-12, and it arrives with the
reservation lifecycle that also expires it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from app.application.audit import audit_event_for
from app.application.availability.allocation import (
    AllocatedAsset,
    AllocationCommand,
    allocate_assets,
)
from app.application.clock import Clock
from app.application.notification.confirmation import queue_booking_confirmation
from app.application.notification.dispatcher import NotificationDispatcher
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.audit import StateValue
from app.domain.booking import Reservation, ReservationLine
from app.domain.enums import ReservationStatus
from app.domain.errors import NotFound
from app.domain.identity import Actor, CustomerProfile
from app.domain.period import BookingPeriod, ensure_within_booking_window

logger = logging.getLogger(__name__)

RESERVATION_ENTITY_TYPE: Final[str] = "reservation"
RESERVATION_HELD_ACTION: Final[str] = "reservation.held"


@dataclass(frozen=True, slots=True)
class CreateReservationCommand:
    """A request to book `quantity` units of one product model at one branch.

    Attributes:
        actor: The account making the request and the role it holds. The
            booking records it as its creator and the audit event as its actor.
        customer_user_id: The account of the customer the booking is for. The
            use case resolves it to that customer's profile.
        branch_id: The collection branch.
        product_model_id: The catalogue entry being hired.
        period: The half open hire period.
        quantity: How many units.

    """

    actor: Actor
    customer_user_id: UUID
    branch_id: UUID
    product_model_id: UUID
    period: BookingPeriod
    quantity: int


@dataclass(frozen=True, slots=True)
class ReservationView:
    """The committed booking, flattened for the API layer."""

    reservation_id: UUID
    reference: str
    reservation_line_id: UUID
    status: ReservationStatus
    allocated: list[AllocatedAsset]


class CreateReservationUseCase(UseCase[CreateReservationCommand, ReservationView]):
    """Create a held reservation with its assets allocated, in one transaction."""

    def __init__(self, uow: UnitOfWork, clock: Clock, dispatcher: NotificationDispatcher) -> None:
        """Keep the collaborators the use case works with.

        Args:
            uow: The unit of work that owns the booking transaction.
            clock: Where the current instant and business day come from.
            dispatcher: Sends the queued confirmation once the booking is committed.

        """
        super().__init__(uow, clock)
        self._dispatcher = dispatcher

    def execute(self, command: CreateReservationCommand) -> ReservationView:
        """Create the booking, commit it and then send its confirmation.

        Args:
            command: The booking to create.

        Returns:
            The committed reservation, its line and the units held.

        Raises:
            ValidationFailure: If the period starts in the past or too far
                ahead, or the quantity is outside the permitted range.
            NotFound: If the branch or the product model does not exist, or if
                the customer account has no customer profile to book against.
            AllocationConflictError: If the units could not be held. Nothing
                is committed.

        """
        logger.info(
            "reservation.create_requested",
            extra={
                "actor_user_id": str(command.actor.user_id),
                "actor_role": command.actor.role.value,
                "branch_id": str(command.branch_id),
                "product_model_id": str(command.product_model_id),
                "period": command.period.as_postgres_daterange(),
                "quantity": command.quantity,
            },
        )
        ensure_within_booking_window(command.period, self._clock.today())

        with self._uow as uow:
            view = self._create(uow, command)
            uow.commit()
        logger.info(
            "reservation.create_committed",
            extra={
                "reference": view.reference,
                "reservation_id": str(view.reservation_id),
                "allocated_count": len(view.allocated),
            },
        )

        # After the commit and outside the transaction. The dispatcher never
        # raises, so nothing that happens here can undo or misreport a booking.
        accepted_count = self._dispatcher.dispatch_due()
        logger.info(
            "reservation.create_finished",
            extra={
                "reference": view.reference,
                "reservation_id": str(view.reservation_id),
                "notifications_accepted": accepted_count,
            },
        )
        return view

    def _create(self, uow: UnitOfWork, command: CreateReservationCommand) -> ReservationView:
        """Write the whole booking inside the open unit of work. Nothing is committed here."""
        branch = uow.branches.get(command.branch_id)
        if branch is None:
            raise NotFound(
                f"Attempted to create a reservation at branch {command.branch_id}, "
                "which does not exist.",
                {"branch_id": str(command.branch_id)},
            )
        product_model = uow.product_models.get(command.product_model_id)
        if product_model is None:
            raise NotFound(
                "Attempted to create a reservation for product model "
                f"{command.product_model_id}, which does not exist.",
                {"product_model_id": str(command.product_model_id)},
            )
        profile = _customer_profile_of(uow, command.customer_user_id)

        reference = uow.reservations.next_reference(command.period.start.year)
        logger.info(
            "reservation.create_started",
            extra={
                "reference": reference,
                "branch_code": branch.code,
                "product_model_sku": product_model.sku,
                "period": command.period.as_postgres_daterange(),
                "quantity": command.quantity,
            },
        )

        reservation = Reservation.held(
            reference=reference,
            customer_profile_id=profile.id,
            branch_id=command.branch_id,
            period=command.period,
            created_by_user_id=command.actor.user_id,
        )
        line = reservation.add_line(product_model, command.quantity)
        uow.reservations.add(reservation)

        allocated = allocate_assets(
            uow.assets,
            self._clock,
            AllocationCommand(
                reservation_line_id=line.id,
                product_model_id=command.product_model_id,
                branch_id=command.branch_id,
                period=command.period,
                quantity=command.quantity,
            ),
        )
        line.allocations.extend(item.allocation for item in allocated)

        occurred_at = self._clock.now()
        uow.audit.record(
            audit_event_for(
                actor=command.actor,
                entity_type=RESERVATION_ENTITY_TYPE,
                entity_id=reservation.id,
                action=RESERVATION_HELD_ACTION,
                occurred_at=occurred_at,
                after_state=_held_state(reservation, line, allocated),
            )
        )
        queue_booking_confirmation(
            uow.notifications, reservation=reservation, customer=profile, queued_at=occurred_at
        )

        return ReservationView(
            reservation_id=reservation.id,
            reference=reservation.reference,
            reservation_line_id=line.id,
            status=reservation.status,
            allocated=allocated,
        )


def _held_state(
    reservation: Reservation, line: ReservationLine, allocated: list[AllocatedAsset]
) -> dict[str, StateValue]:
    """Return what the audit event records about a newly held reservation.

    A creation has no before state, so every field that was set is a change.
    """
    return {
        "status": reservation.status.value,
        "reference": reservation.reference,
        "customer_profile_id": str(reservation.customer_profile_id),
        "branch_id": str(reservation.branch_id),
        "start_date": reservation.period.start.isoformat(),
        "end_date": reservation.period.end.isoformat(),
        "product_model_id": str(line.product_model_id),
        "quantity": line.quantity,
        "asset_tags": [item.asset_tag for item in allocated],
    }


def _customer_profile_of(uow: UnitOfWork, customer_user_id: UUID) -> CustomerProfile:
    """Return the customer profile that belongs to an account.

    Raises:
        NotFound: If the account has no profile. Staff accounts have none, and
            a booking cannot be owned by an account that is not a customer.

    """
    profile = uow.customers.profile_for_account(customer_user_id)
    if profile is None:
        logger.warning(
            "reservation.customer_profile_missing",
            extra={
                "customer_user_id": str(customer_user_id),
                "attempted": "resolve the customer profile for a reservation",
            },
        )
        raise NotFound(
            f"Attempted to create a reservation for account {customer_user_id}, which has "
            "no customer profile. A booking belongs to a customer profile, so name the "
            "account of a registered customer.",
            {"customer_user_id": str(customer_user_id)},
        )
    return profile
