"""The refusals of the loss, the balance payment, the read and the two lists, as data.

A loss can be refused for a caller who is not staff, at another branch, for a
unit that is not on the rental, one that is back, and one that is not yet more
than fourteen days late. A balance payment can be refused for the same
callers, when nothing is due and for a reference that is blank or too long.
The lists are for staff and for customers respectively, and the staff list
refuses a branch that does not trade. What a case is made of is in
`rental_refusal_cases`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final
from uuid import uuid4

from fastapi import status
from httpx import Response

from tests.api.rental_refusal_cases import (
    ALREADY_BACK,
    BALANCE,
    LIST,
    LOSS,
    MINE,
    NO_SUCH_RENTAL,
    PAYMENT_REFERENCE,
    READ,
    RentalRefusal,
    RentalStage,
    back_already,
    out_on_hire,
)
from tests.api.reservation_refusal_cases import (
    ANONYMOUS,
    BRANCH_SCOPE,
    FORBIDDEN_ROLE,
    FRAMEWORK,
    NOT_ACCEPTED,
    NOT_FOUND,
    OTHER_BRANCH,
    TRANSITION,
)
from tests.support.checkout_api import rental_path
from tests.support.rental_api import (
    MY_RENTALS_PATH,
    RENTALS_LIST_PATH,
    item_ids,
    list_rentals,
    my_rentals,
    pay_balance,
    record_loss,
)

NOT_LATE_ENOUGH: Final[str] = (
    "This unit is not late enough to be recorded as lost. A unit can be recorded as lost "
    "once it is more than fourteen days past its due date."
)
NO_SUCH_UNIT: Final[str] = (
    "We could not find that unit on this rental. Check the rental and try again."
)
NOTHING_DUE: Final[str] = "Nothing is owed on this rental, so there is no balance to pay."
UNKNOWN_BRANCH: Final[str] = (
    "We do not have a branch with that code. Choose a branch from the list."
)
# From the second of March to the twentieth, fourteen days after the sixth.
FOURTEEN_DAYS_LATE: Final[timedelta] = timedelta(days=18)
TOO_LONG_REFERENCE: Final[str] = "R" * 41


def _lost_too_soon(stage: RentalStage) -> Response:
    """Record a unit as lost fourteen days after its due date, which is one day too soon."""
    rental = out_on_hire(stage)
    stage.booking.clock.advance(FOURTEEN_DAYS_LATE)
    return record_loss(stage.booking, stage.administrator, rental["id"], item_ids(rental)[0])


def _lost_when_back(stage: RentalStage) -> Response:
    """Record a unit that is already back as lost."""
    rental, key = back_already(stage)
    return record_loss(stage.booking, stage.administrator, rental["id"], key)


def _paid_when_nothing_due(stage: RentalStage) -> Response:
    """Pay the balance of a hire that settled with nothing due."""
    rental, _key = back_already(stage)
    return pay_balance(stage.booking, stage.administrator, rental["id"], PAYMENT_REFERENCE)


SETTLEMENT_REFUSALS: Final[list[RentalRefusal]] = [
    RentalRefusal(
        "record a loss as a customer",
        LOSS,
        lambda stage: record_loss(stage.booking, stage.world.customer, uuid4(), uuid4()),
        status.HTTP_403_FORBIDDEN,
        FORBIDDEN_ROLE,
    ),
    RentalRefusal(
        "record a loss at another branch",
        LOSS,
        lambda stage: record_loss(
            stage.booking, stage.assistant_elsewhere, out_on_hire(stage)["id"], uuid4()
        ),
        status.HTTP_403_FORBIDDEN,
        BRANCH_SCOPE,
        OTHER_BRANCH,
    ),
    RentalRefusal(
        "record a loss of a unit that is not on the rental",
        LOSS,
        lambda stage: record_loss(
            stage.booking, stage.administrator, out_on_hire(stage)["id"], uuid4()
        ),
        status.HTTP_404_NOT_FOUND,
        NOT_FOUND,
        NO_SUCH_UNIT,
    ),
    RentalRefusal(
        "record a loss fourteen days after the due date",
        LOSS,
        _lost_too_soon,
        status.HTTP_409_CONFLICT,
        TRANSITION,
        NOT_LATE_ENOUGH,
    ),
    RentalRefusal(
        "record a loss of a unit that is already back",
        LOSS,
        _lost_when_back,
        status.HTTP_409_CONFLICT,
        TRANSITION,
        ALREADY_BACK,
    ),
    RentalRefusal(
        "pay a balance as a customer",
        BALANCE,
        lambda stage: pay_balance(
            stage.booking, stage.world.customer, uuid4(), PAYMENT_REFERENCE
        ),
        status.HTTP_403_FORBIDDEN,
        FORBIDDEN_ROLE,
    ),
    RentalRefusal(
        "pay a balance at another branch",
        BALANCE,
        lambda stage: pay_balance(
            stage.booking, stage.assistant_elsewhere, out_on_hire(stage)["id"], PAYMENT_REFERENCE
        ),
        status.HTTP_403_FORBIDDEN,
        BRANCH_SCOPE,
        OTHER_BRANCH,
    ),
    RentalRefusal(
        "pay a balance when nothing is due",
        BALANCE,
        _paid_when_nothing_due,
        status.HTTP_409_CONFLICT,
        TRANSITION,
        NOTHING_DUE,
    ),
    RentalRefusal(
        "pay a balance with a blank reference",
        BALANCE,
        lambda stage: pay_balance(stage.booking, stage.administrator, uuid4(), "   "),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.paymentReference"}),
    ),
    RentalRefusal(
        "pay a balance with a reference longer than forty characters",
        BALANCE,
        lambda stage: pay_balance(stage.booking, stage.administrator, uuid4(), TOO_LONG_REFERENCE),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.paymentReference"}),
    ),
    RentalRefusal(
        "list rentals with no credential",
        LIST,
        lambda stage: stage.booking.client.get(RENTALS_LIST_PATH),
        status.HTTP_401_UNAUTHORIZED,
        ANONYMOUS,
    ),
    RentalRefusal(
        "list rentals as a customer",
        LIST,
        lambda stage: list_rentals(stage.booking, stage.world.customer),
        status.HTTP_403_FORBIDDEN,
        FORBIDDEN_ROLE,
    ),
    RentalRefusal(
        "list rentals at a branch that does not trade",
        LIST,
        lambda stage: list_rentals(stage.booking, stage.administrator, branchCode="XYZ"),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        fields={"query.branchCode": UNKNOWN_BRANCH},
    ),
    RentalRefusal(
        "read a rental that does not exist",
        READ,
        lambda stage: stage.booking.client.get(
            rental_path("TSH-H-26-999999"), headers=stage.booking.headers(stage.administrator)
        ),
        status.HTTP_404_NOT_FOUND,
        NOT_FOUND,
        NO_SUCH_RENTAL,
    ),
    RentalRefusal(
        "list my rentals with no credential",
        MINE,
        lambda stage: stage.booking.client.get(MY_RENTALS_PATH),
        status.HTTP_401_UNAUTHORIZED,
        ANONYMOUS,
    ),
    RentalRefusal(
        "list my rentals as staff",
        MINE,
        lambda stage: my_rentals(stage.booking, stage.administrator),
        status.HTTP_403_FORBIDDEN,
        FORBIDDEN_ROLE,
    ),
]

__all__ = ["SETTLEMENT_REFUSALS"]
