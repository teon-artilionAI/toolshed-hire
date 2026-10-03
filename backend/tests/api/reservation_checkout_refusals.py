"""The refusals of the two checkout routes, as data.

Reading a checkout can be refused for a caller who is not staff and for a
reservation that is not there. Checking out can be refused for those two, for
counter staff of another branch, for a reservation that is not confirmed or
whose hire has not started, for a list of units that is wrong, for an
agreement that is not signed and for a body the framework cannot read. Each is
a case here. What a case is made of is in `reservation_refusal_cases`.

A case books for today as an administrator, who may book and check out at
any branch, so the clock does not have to move unless the case is about the
first day of the hire.
"""

from __future__ import annotations

from typing import Final
from uuid import uuid4

from fastapi import status
from httpx import Response

from tests.api.reservation_refusal_cases import (
    ANONYMOUS,
    BRANCH_SCOPE,
    FORBIDDEN_ROLE,
    FRAMEWORK,
    NO_SUCH_RESERVATION,
    NOT_ACCEPTED,
    NOT_FOUND,
    OTHER_BRANCH,
    TRANSITION,
    Refusal,
    Stage,
)
from tests.support.booking_api import FIRST_HIRE, answered, created
from tests.support.checkout_api import (
    check_out,
    checkout_body,
    checkout_path,
    confirmed_today,
    read_checkout,
)

CHECKOUT_READ: Final[str] = "GET /api/reservations/{id}/checkout"
CHECKOUT: Final[str] = "POST /api/reservations/{id}/checkout"

TOO_EARLY: Final[str] = "This reservation cannot be collected before the first day of the hire."
ONLY_ON_HOLD: Final[str] = "This reservation is on hold, so it cannot be collected."
NOT_SIGNED: Final[str] = (
    "The customer has to sign the hire agreement before the equipment is handed over."
)
UNIT_MISSING: Final[str] = (
    "Every unit on this reservation is handed over at once. One or more is missing from "
    "the list."
)
LISTED_TWICE: Final[str] = "This unit is already in the list. List each unit once."
NOT_HELD: Final[str] = "This unit is not held for this reservation."
TWO_UNITS: Final[int] = 2


def _stranger_body() -> dict[str, object]:
    """Return a body that is well formed and names an allocation nobody holds."""
    return {
        "items": [{"allocationId": str(uuid4()), "conditionOut": "A"}],
        "agreementSigned": True,
    }


def _confirmed_body(stage: Stage, *, quantity: int = 1) -> tuple[str, dict[str, object]]:
    """Confirm a reservation for today and return its key and the full checkout body."""
    reservation = confirmed_today(
        stage.booking, stage.world, stage.administrator, quantity=quantity
    )
    key = str(reservation["id"])
    preview = answered(read_checkout(stage.booking, stage.administrator, key))
    return key, checkout_body(preview)


def _as_administrator(stage: Stage, key: str, body: dict[str, object]) -> Response:
    """Post a checkout as the stage's administrator."""
    return check_out(stage.booking, stage.administrator, key, body)


def _elsewhere(stage: Stage) -> Response:
    """Check a reservation out as counter staff of another branch."""
    key, body = _confirmed_body(stage)
    return check_out(stage.booking, stage.assistant_elsewhere, key, body)


def _only_on_hold(stage: Stage) -> Response:
    """Check out a reservation that is held and not confirmed."""
    draft = created(
        stage.booking.create(
            stage.administrator, stage.world.payload(customer_profile_id=stage.world.profile.id)
        )
    )
    answered(stage.booking.hold(stage.administrator, draft["id"]))
    return _as_administrator(stage, str(draft["id"]), _stranger_body())


def _too_early(stage: Stage) -> Response:
    """Check out a reservation whose hire starts next week."""
    reservation = confirmed_today(
        stage.booking, stage.world, stage.administrator, period=FIRST_HIRE
    )
    key = str(reservation["id"])
    preview = answered(read_checkout(stage.booking, stage.administrator, key))
    return _as_administrator(stage, key, checkout_body(preview))


def _not_signed(stage: Stage) -> Response:
    """Check out without the customer's signature."""
    key, body = _confirmed_body(stage)
    return _as_administrator(stage, key, {**body, "agreementSigned": False})


def _one_left_out(stage: Stage) -> Response:
    """Check out a reservation of two units, listing one."""
    key, body = _confirmed_body(stage, quantity=TWO_UNITS)
    items = body["items"]
    assert isinstance(items, list)
    return _as_administrator(stage, key, {**body, "items": items[:1]})


def _listed_twice(stage: Stage) -> Response:
    """Check out a reservation of one unit, listing it twice."""
    key, body = _confirmed_body(stage)
    items = body["items"]
    assert isinstance(items, list)
    return _as_administrator(stage, key, {**body, "items": [*items, *items]})


def _not_held(stage: Stage) -> Response:
    """Check out naming an allocation the reservation does not hold."""
    key, _body = _confirmed_body(stage)
    return _as_administrator(stage, key, _stranger_body())


def _with(stage: Stage, **item_changes: object) -> Response:
    """Check out with every item changed as asked."""
    key, body = _confirmed_body(stage)
    items = body["items"]
    assert isinstance(items, list)
    return _as_administrator(
        stage, key, {**body, "items": [{**item, **item_changes} for item in items]}
    )


CHECKOUT_REFUSALS: Final[list[Refusal]] = [
    Refusal(
        "read a checkout as a customer",
        CHECKOUT_READ,
        lambda stage: read_checkout(stage.booking, stage.world.customer, uuid4()),
        status.HTTP_403_FORBIDDEN,
        FORBIDDEN_ROLE,
    ),
    Refusal(
        "read the checkout of a reservation that does not exist",
        CHECKOUT_READ,
        lambda stage: read_checkout(stage.booking, stage.administrator, "TSH-R-26-999999"),
        status.HTTP_404_NOT_FOUND,
        NOT_FOUND,
        NO_SUCH_RESERVATION,
    ),
    Refusal(
        "check out with no credential",
        CHECKOUT,
        lambda stage: stage.booking.client.post(checkout_path(uuid4()), json=_stranger_body()),
        status.HTTP_401_UNAUTHORIZED,
        ANONYMOUS,
    ),
    Refusal(
        "check out as a customer",
        CHECKOUT,
        lambda stage: check_out(stage.booking, stage.world.customer, uuid4(), _stranger_body()),
        status.HTTP_403_FORBIDDEN,
        FORBIDDEN_ROLE,
    ),
    Refusal(
        "check out a reservation that does not exist",
        CHECKOUT,
        lambda stage: _as_administrator(stage, str(uuid4()), _stranger_body()),
        status.HTTP_404_NOT_FOUND,
        NOT_FOUND,
        NO_SUCH_RESERVATION,
    ),
    Refusal(
        "check out as counter staff of another branch",
        CHECKOUT,
        _elsewhere,
        status.HTTP_403_FORBIDDEN,
        BRANCH_SCOPE,
        OTHER_BRANCH,
    ),
    Refusal(
        "check out a reservation that is only on hold",
        CHECKOUT,
        _only_on_hold,
        status.HTTP_409_CONFLICT,
        TRANSITION,
        ONLY_ON_HOLD,
    ),
    Refusal(
        "check out before the first day of the hire",
        CHECKOUT,
        _too_early,
        status.HTTP_409_CONFLICT,
        TRANSITION,
        TOO_EARLY,
    ),
    Refusal(
        "check out without the signed agreement",
        CHECKOUT,
        _not_signed,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        fields={"body.agreementSigned": NOT_SIGNED},
    ),
    Refusal(
        "check out leaving a unit out",
        CHECKOUT,
        _one_left_out,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        fields={"body.items": UNIT_MISSING},
    ),
    Refusal(
        "check out listing a unit twice",
        CHECKOUT,
        _listed_twice,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        fields={"body.items.1.allocationId": LISTED_TWICE},
    ),
    Refusal(
        "check out a unit the reservation does not hold",
        CHECKOUT,
        _not_held,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        fields={"body.items.0.allocationId": NOT_HELD},
    ),
    Refusal(
        "check out with an empty body",
        CHECKOUT,
        lambda stage: _as_administrator(stage, str(uuid4()), {}),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.items", "body.agreementSigned"}),
    ),
    Refusal(
        "check out listing no unit at all",
        CHECKOUT,
        lambda stage: _as_administrator(
            stage, str(uuid4()), {"items": [], "agreementSigned": True}
        ),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.items"}),
    ),
    Refusal(
        "check out with a condition that is not a grade",
        CHECKOUT,
        lambda stage: _with(stage, conditionOut="D"),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.items.0.conditionOut"}),
    ),
    Refusal(
        "check out with a meter reading below nought",
        CHECKOUT,
        lambda stage: _with(stage, hourMeterOut=-1),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.items.0.hourMeterOut"}),
    ),
    Refusal(
        "check out naming the tag of a unit, which the contract does not take",
        CHECKOUT,
        lambda stage: _with(stage, assetTag="TSH-DR-0042"),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.items.0.assetTag"}),
    ),
]
