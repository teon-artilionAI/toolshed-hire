"""The refusals of the route by which staff mark a booking as not collected, as data.

Marking a no show can be refused for a caller with no credential, for one who
is not staff, for a reservation that is not there, for counter staff of
another branch, for a reservation that is not confirmed or whose hire has not
started, and for a reason that is missing, blank, too long or sent with a field
the contract does not take. Each is a case here. What a case is made of is in
`reservation_refusal_cases`.

A case books for today as an administrator, who may act at any branch, so the
clock does not have to move unless the case is about the first day of the hire.
"""

from __future__ import annotations

from typing import Final
from uuid import uuid4

from fastapi import status
from httpx import Response

from app.infrastructure.models import UserAccount
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
from tests.support.checkout_api import checked_out, confirmed_today
from tests.support.counter_api import NO_SHOW_REASON as REASON
from tests.support.counter_api import no_show_path

NO_SHOW: Final[str] = "POST /api/reservations/{id}/no-show"
REASON_TOO_LONG: Final[int] = 201
NOT_STARTED: Final[str] = (
    "This reservation cannot be marked as not collected before the first day of the hire."
)
ONLY_ON_HOLD: Final[str] = "This reservation is on hold, so it cannot be marked as not collected."
ALREADY_COLLECTED: Final[str] = (
    "This reservation has been collected, so it cannot be marked as not collected."
)
ALREADY_MARKED: Final[str] = (
    "This reservation was not collected, so it cannot be marked as not collected."
)


def mark_no_show(
    stage: Stage, account: UserAccount, key: object, body: dict[str, object] | None = None
) -> Response:
    """Post a no show as `account`, with the reason of these cases unless a body is given."""
    return stage.booking.client.post(
        no_show_path(key),
        json={"reason": REASON} if body is None else body,
        headers=stage.booking.headers(account),
    )


def _confirmed_today(stage: Stage) -> str:
    """Return the key of a reservation for today, booked and confirmed by the administrator."""
    return str(confirmed_today(stage.booking, stage.world, stage.administrator)["id"])


def _elsewhere(stage: Stage) -> Response:
    """Mark a reservation for today as counter staff of another branch."""
    return mark_no_show(stage, stage.assistant_elsewhere, _confirmed_today(stage))


def _before_the_first_day(stage: Stage) -> Response:
    """Mark a reservation whose hire starts next week."""
    reservation = confirmed_today(
        stage.booking, stage.world, stage.administrator, period=FIRST_HIRE
    )
    return mark_no_show(stage, stage.administrator, reservation["id"])


def _only_on_hold(stage: Stage) -> Response:
    """Mark a reservation that is held and not confirmed."""
    draft = created(
        stage.booking.create(
            stage.administrator, stage.world.payload(customer_profile_id=stage.world.profile.id)
        )
    )
    answered(stage.booking.hold(stage.administrator, draft["id"]))
    return mark_no_show(stage, stage.administrator, draft["id"])


def _collected(stage: Stage) -> Response:
    """Mark a reservation that has been checked out."""
    key = _confirmed_today(stage)
    checked_out(stage.booking, stage.administrator, key)
    return mark_no_show(stage, stage.administrator, key)


def _twice(stage: Stage) -> Response:
    """Mark a reservation as not collected, then mark it again."""
    key = _confirmed_today(stage)
    answered(mark_no_show(stage, stage.administrator, key))
    return mark_no_show(stage, stage.administrator, key)


def _with_body(stage: Stage, body: dict[str, object]) -> Response:
    """Mark a reservation for today with the body given."""
    return mark_no_show(stage, stage.administrator, _confirmed_today(stage), body)


NO_SHOW_REFUSALS: Final[list[Refusal]] = [
    Refusal(
        "mark a no show with no credential",
        NO_SHOW,
        lambda stage: stage.booking.client.post(no_show_path(uuid4()), json={"reason": REASON}),
        status.HTTP_401_UNAUTHORIZED,
        ANONYMOUS,
    ),
    Refusal(
        "mark a no show as a customer",
        NO_SHOW,
        lambda stage: mark_no_show(stage, stage.world.customer, uuid4()),
        status.HTTP_403_FORBIDDEN,
        FORBIDDEN_ROLE,
    ),
    Refusal(
        "mark a no show on a reservation that does not exist",
        NO_SHOW,
        lambda stage: mark_no_show(stage, stage.administrator, "TSH-R-26-999999"),
        status.HTTP_404_NOT_FOUND,
        NOT_FOUND,
        NO_SUCH_RESERVATION,
    ),
    Refusal(
        "mark a no show as counter staff of another branch",
        NO_SHOW,
        _elsewhere,
        status.HTTP_403_FORBIDDEN,
        BRANCH_SCOPE,
        OTHER_BRANCH,
    ),
    Refusal(
        "mark a no show before the first day of the hire",
        NO_SHOW,
        _before_the_first_day,
        status.HTTP_409_CONFLICT,
        TRANSITION,
        NOT_STARTED,
    ),
    Refusal(
        "mark a no show on a reservation that is only on hold",
        NO_SHOW,
        _only_on_hold,
        status.HTTP_409_CONFLICT,
        TRANSITION,
        ONLY_ON_HOLD,
    ),
    Refusal(
        "mark a no show on a reservation that has been collected",
        NO_SHOW,
        _collected,
        status.HTTP_409_CONFLICT,
        TRANSITION,
        ALREADY_COLLECTED,
    ),
    Refusal(
        "mark a no show twice",
        NO_SHOW,
        _twice,
        status.HTTP_409_CONFLICT,
        TRANSITION,
        ALREADY_MARKED,
    ),
    Refusal(
        "mark a no show with no reason",
        NO_SHOW,
        lambda stage: _with_body(stage, {}),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.reason"}),
    ),
    Refusal(
        "mark a no show with a blank reason",
        NO_SHOW,
        lambda stage: _with_body(stage, {"reason": "   "}),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.reason"}),
    ),
    Refusal(
        "mark a no show with a reason that is too long",
        NO_SHOW,
        lambda stage: _with_body(stage, {"reason": "x" * REASON_TOO_LONG}),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.reason"}),
    ),
    Refusal(
        "mark a no show with a field the contract does not take",
        NO_SHOW,
        lambda stage: _with_body(stage, {"reason": REASON, "status": "NO_SHOW"}),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.status"}),
    ),
]

__all__ = ["NO_SHOW", "NO_SHOW_REFUSALS", "mark_no_show"]
