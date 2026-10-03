"""What a request for a reservation is checked against before a draft is built.

A caller asks for a reservation with a branch code, two dates, a list of
models and, when they are staff, the customer it is for. Each of those is
checked here and turned into the record it names. A refusal names the field
the value was sent in, so a form can put the sentence beside the right input,
and the sentence is a plain one because a customer reads it as it is written.

A customer books for their own profile and may name nobody. Counter staff and
administrators name the profile they are booking for, which is how a walk-in
with no login gets a booking (BR-42).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final
from uuid import UUID

from app.application.availability.hire_request import FROM_PARAMETER, TO_PARAMETER
from app.application.availability.search import UNKNOWN_BRANCH_MESSAGE
from app.application.booking.access import is_staff
from app.application.catalogue.browse import MODEL_NOT_FOUND_MESSAGE
from app.application.refusal import refused
from app.application.unit_of_work import UnitOfWork
from app.domain.booking import (
    MAXIMUM_LINE_QUANTITY,
    MINIMUM_LINE_QUANTITY,
    MODEL_ALREADY_ON_RESERVATION_MESSAGE,
    QUANTITY_OUT_OF_RANGE_MESSAGE,
)
from app.domain.catalogue import ProductModel
from app.domain.errors import AuthorisationFailure, ValidationFailure
from app.domain.identity import Actor, Branch, CustomerProfile
from app.domain.period import BookingPeriod, ensure_branch_open_for_start

logger = logging.getLogger(__name__)

BRANCH_PARAMETER: Final[str] = "branchCode"
LINES_PARAMETER: Final[str] = "lines"
CUSTOMER_PARAMETER: Final[str] = "customerProfileId"
MODEL_FIELD: Final[str] = "modelSlug"
QUANTITY_FIELD: Final[str] = "quantity"

NO_LINES_MESSAGE: Final[str] = "Add at least one tool to the reservation."
CUSTOMER_REQUIRED_MESSAGE: Final[str] = "Choose the customer this reservation is for."
UNKNOWN_CUSTOMER_MESSAGE: Final[str] = (
    "We could not find that customer. Choose a customer from the list."
)
NO_PROFILE_MESSAGE: Final[str] = (
    "This account has no customer profile yet, so it cannot make a reservation. "
    "Please speak to the branch."
)
STAFF_ONLY_CUSTOMER_MESSAGE: Final[str] = (
    "Only a member of staff can make a reservation for another customer."
)


@dataclass(frozen=True, slots=True)
class RequestedLine:
    """One model and how many of it, as the caller asked for it."""

    model_slug: str
    quantity: int


@dataclass(frozen=True, slots=True)
class CreateReservationCommand:
    """A request for a draft reservation.

    Attributes:
        actor: The account making the request and the role it holds. The
            booking records it as its creator and the audit event as its actor.
        branch_code: The code of the collection branch.
        start: The first day of the hire.
        end: The day the equipment comes back, which is not charged.
        lines: The models wanted and how many of each.
        customer_profile_id: The customer the booking is for. Staff name one.
            A customer leaves it out and books for themselves.
        notes: Anything to be written on the booking.

    """

    actor: Actor
    branch_code: str
    start: date
    end: date
    lines: tuple[RequestedLine, ...]
    customer_profile_id: UUID | None = None
    notes: str | None = None


def ensure_customer_names_nobody(command: CreateReservationCommand) -> None:
    """Refuse a customer who names a customer profile, even their own (BR-42).

    Raises:
        AuthorisationFailure: If the actor is a customer and a profile was named.

    """
    if command.customer_profile_id is None or is_staff(command.actor):
        return
    logger.warning(
        "reservation.customer_named_a_profile",
        extra={
            "actor_user_id": str(command.actor.user_id),
            "requested_customer_profile_id": str(command.customer_profile_id),
        },
    )
    raise AuthorisationFailure(
        STAFF_ONLY_CUSTOMER_MESSAGE, {"required_roles": ["ADMIN", "COUNTER_STAFF"]}
    )


def ensure_lines_are_well_formed(lines: tuple[RequestedLine, ...]) -> None:
    """Refuse no lines, a quantity out of range, or one model named twice.

    Raises:
        ValidationFailure: Naming `lines`, or the field of the line at fault.

    """
    if not lines:
        raise refused(LINES_PARAMETER, NO_LINES_MESSAGE)
    seen: set[str] = set()
    for index, line in enumerate(lines):
        if not MINIMUM_LINE_QUANTITY <= line.quantity <= MAXIMUM_LINE_QUANTITY:
            raise refused(
                f"{LINES_PARAMETER}.{index}.{QUANTITY_FIELD}",
                QUANTITY_OUT_OF_RANGE_MESSAGE,
                {"received": line.quantity},
            )
        if line.model_slug in seen:
            raise refused(
                f"{LINES_PARAMETER}.{index}.{MODEL_FIELD}",
                MODEL_ALREADY_ON_RESERVATION_MESSAGE,
                {"slug": line.model_slug},
            )
        seen.add(line.model_slug)


def ensure_start_while_branch_open(period: BookingPeriod, branch: Branch, now: datetime) -> None:
    """Refuse a hire for today at a branch that has closed for the day, naming `from` (BR-04).

    Raises:
        ValidationFailure: Naming `from`, the start date, when the hire starts
            today and the collection branch has already closed.

    """
    try:
        ensure_branch_open_for_start(period, now=now, closes_at=branch.closes_at)
    except ValidationFailure as failure:
        raise refused(
            FROM_PARAMETER,
            failure.message,
            {**failure.detail, "branch": branch.code},
            rule=failure.rule,
        ) from failure


def branch_of(uow: UnitOfWork, branch_code: str) -> Branch:
    """Return the trading branch a code names.

    Raises:
        ValidationFailure: Naming `branchCode` when no trading branch has the code.

    """
    branch = uow.branches.find_active_by_code(branch_code)
    if branch is None:
        raise refused(BRANCH_PARAMETER, UNKNOWN_BRANCH_MESSAGE, {"branch": branch_code})
    return branch


def customer_named_in(uow: UnitOfWork, command: CreateReservationCommand) -> CustomerProfile:
    """Return the customer profile the booking is for.

    Raises:
        ValidationFailure: Naming `customerProfileId` when staff named no
            customer or one that does not exist, and naming nothing when a
            customer's own account has no profile.

    """
    if not is_staff(command.actor):
        own = uow.customers.profile_for_account(command.actor.user_id)
        if own is None:
            raise ValidationFailure(
                NO_PROFILE_MESSAGE, {"customer_user_id": str(command.actor.user_id)}
            )
        return own
    if command.customer_profile_id is None:
        raise refused(CUSTOMER_PARAMETER, CUSTOMER_REQUIRED_MESSAGE)
    named = uow.customers.get(command.customer_profile_id)
    if named is None:
        raise refused(
            CUSTOMER_PARAMETER,
            UNKNOWN_CUSTOMER_MESSAGE,
            {"customer_profile_id": str(command.customer_profile_id)},
        )
    return named


def models_of(
    uow: UnitOfWork, lines: tuple[RequestedLine, ...], period: BookingPeriod
) -> list[ProductModel]:
    """Return the published model of every line, in line order.

    Raises:
        ValidationFailure: Naming the line whose model is not published, and
            naming `to` when the period is outside the hire limits of a model.

    """
    models: list[ProductModel] = []
    for index, line in enumerate(lines):
        model = uow.product_models.find_published_by_slug(line.model_slug)
        if model is None:
            raise refused(
                f"{LINES_PARAMETER}.{index}.{MODEL_FIELD}",
                MODEL_NOT_FOUND_MESSAGE,
                {"slug": line.model_slug},
            )
        try:
            model.ensure_can_be_hired_for(period)
        except ValidationFailure as failure:
            raise refused(
                TO_PARAMETER, failure.message, failure.detail, rule=failure.rule
            ) from failure
        models.append(model)
    return models
