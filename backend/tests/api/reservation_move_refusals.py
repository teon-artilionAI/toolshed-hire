"""The refusals of every reservation route but the one that creates a draft, as data.

Holding, confirming, cancelling, listing and reading can each be refused, for
a reservation that is not there or not the caller's, for a move its status
does not permit, for units that are not free, for a hold that has run out and
for an address that is not verified. Each is a case here. What a case is made
of is in `reservation_refusal_cases`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final
from uuid import uuid4

from fastapi import status
from httpx import Response

from app.domain.enums import ReservationStatus
from tests.api.reservation_refusal_cases import (
    ACCOUNT_ON_HOLD,
    BRANCH_SCOPE,
    CANCEL,
    CONFIRM,
    FORBIDDEN_ROLE,
    FRAMEWORK,
    HOLD,
    LIST,
    NO_SUCH_RESERVATION,
    NOT_ACCEPTED,
    NOT_FOUND,
    NOT_VERIFIED,
    ON_HOLD,
    OTHER_BRANCH,
    READ,
    RULE,
    TRANSITION,
    UNAVAILABLE,
    Refusal,
    Stage,
)
from tests.support.booking_api import force_status, hold_path, reservation_path

VERIFY_FIRST: Final[str] = (
    "Please verify your email address before you confirm this reservation. "
    "A counter assistant can also confirm it for you at the branch."
)
UNAVAILABLE_SENTENCE: Final[str] = (
    "GBH 2-26 DRE Rotary Hammer is not available at Cape Town CBD from 9 March 2026 to "
    "12 March 2026. Choose other dates or another branch."
)
JUST_PAST_THE_HOLD: Final[timedelta] = timedelta(minutes=30, seconds=1)
REASON_TOO_LONG: Final[int] = 201


def _draft_then_on_hold(stage: Stage) -> Response:
    """Create a draft, put the customer on hold, then try to hold the draft."""
    draft = stage.booking.drafted(stage.world)
    stage.put_customer_on_hold()
    return stage.booking.hold(stage.world.customer, draft["id"])


def _hold_after_the_start_has_passed(stage: Stage) -> Response:
    """Create a draft, let eight days pass, then try to hold it."""
    draft = stage.booking.drafted(stage.world)
    stage.booking.clock.advance(timedelta(days=8))
    return stage.booking.hold(stage.world.customer, draft["id"])


def _confirm_unverified(stage: Stage) -> Response:
    """Hold a reservation, take the customer's verification away, then confirm."""
    held = stage.booking.held(stage.world)
    stage.world.customer.email_verified_at = None
    stage.session.add(stage.world.customer)
    stage.session.commit()
    return stage.booking.confirm(stage.world.customer, held["id"])


def _confirm_after_the_hold(stage: Stage) -> Response:
    """Hold a reservation, let the hold run out, then confirm."""
    held = stage.booking.held(stage.world)
    stage.booking.clock.advance(JUST_PAST_THE_HOLD)
    return stage.booking.confirm(stage.world.customer, held["id"])


def _cancel_twice(stage: Stage) -> Response:
    """Cancel a held reservation, then cancel it again."""
    held = stage.booking.held(stage.world)
    stage.booking.cancel(stage.world.customer, held["id"])
    return stage.booking.cancel(stage.world.customer, held["id"])


def _cancel_collected(stage: Stage) -> Response:
    """Confirm a reservation, mark it collected, then try to cancel it."""
    confirmed = stage.booking.confirmed(stage.world)
    force_status(stage.session, confirmed["id"], ReservationStatus.COLLECTED)
    return stage.booking.cancel(stage.world.customer, confirmed["id"])


def _hold_three_of_two(stage: Stage) -> Response:
    """Ask for three units at a branch that holds two."""
    draft = stage.booking.drafted(stage.world, quantity=3)
    return stage.booking.hold(stage.world.customer, draft["id"])


def _hold_twice(stage: Stage) -> Response:
    """Hold a reservation, then hold it again."""
    held = stage.booking.held(stage.world)
    return stage.booking.hold(stage.world.customer, held["id"])


MOVE_REFUSALS: Final[list[Refusal]] = [
    Refusal(
        "hold a reservation that does not exist",
        HOLD,
        lambda stage: stage.booking.hold(stage.world.customer, uuid4()),
        status.HTTP_404_NOT_FOUND,
        NOT_FOUND,
        NO_SUCH_RESERVATION,
    ),
    Refusal(
        "hold somebody else's draft",
        HOLD,
        lambda stage: stage.booking.client.post(
            hold_path(stage.booking.drafted(stage.world)["id"]),
            headers=stage.booking.headers(stage.stranger),
        ),
        status.HTTP_404_NOT_FOUND,
        NOT_FOUND,
        NO_SUCH_RESERVATION,
    ),
    Refusal(
        "hold a reservation that is already on hold",
        HOLD,
        _hold_twice,
        status.HTTP_409_CONFLICT,
        TRANSITION,
        "This reservation is on hold, so it cannot be put on hold.",
    ),
    Refusal(
        "hold three units where two are free",
        HOLD,
        _hold_three_of_two,
        status.HTTP_409_CONFLICT,
        UNAVAILABLE,
        UNAVAILABLE_SENTENCE,
    ),
    Refusal(
        "hold a draft whose start has passed",
        HOLD,
        _hold_after_the_start_has_passed,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        RULE,
        "The hire has to start today or later.",
    ),
    Refusal(
        "hold as counter staff of another branch",
        HOLD,
        lambda stage: stage.booking.hold(
            stage.assistant_elsewhere, stage.booking.drafted(stage.world)["id"]
        ),
        status.HTTP_403_FORBIDDEN,
        BRANCH_SCOPE,
        OTHER_BRANCH,
    ),
    Refusal(
        "hold for a customer put on hold since the draft",
        HOLD,
        _draft_then_on_hold,
        status.HTTP_403_FORBIDDEN,
        ON_HOLD,
        ACCOUNT_ON_HOLD,
    ),
    Refusal(
        "confirm with an address that is not verified",
        CONFIRM,
        _confirm_unverified,
        status.HTTP_403_FORBIDDEN,
        NOT_VERIFIED,
        VERIFY_FIRST,
    ),
    Refusal(
        "confirm after the hold has run out",
        CONFIRM,
        _confirm_after_the_hold,
        status.HTTP_409_CONFLICT,
        TRANSITION,
        "This reservation has expired, so it cannot be confirmed.",
    ),
    Refusal(
        "confirm a draft",
        CONFIRM,
        lambda stage: stage.booking.confirm(
            stage.world.customer, stage.booking.drafted(stage.world)["id"]
        ),
        status.HTTP_409_CONFLICT,
        TRANSITION,
        "This reservation is still a draft, so it cannot be confirmed.",
    ),
    Refusal(
        "confirm a reservation that does not exist",
        CONFIRM,
        lambda stage: stage.booking.confirm(stage.world.customer, "TSH-R-26-999999"),
        status.HTTP_404_NOT_FOUND,
        NOT_FOUND,
        NO_SUCH_RESERVATION,
    ),
    Refusal(
        "cancel a reservation twice",
        CANCEL,
        _cancel_twice,
        status.HTTP_409_CONFLICT,
        TRANSITION,
        "This reservation has been cancelled, so it cannot be cancelled.",
    ),
    Refusal(
        "cancel a reservation that has been collected",
        CANCEL,
        _cancel_collected,
        status.HTTP_409_CONFLICT,
        TRANSITION,
        "This reservation has been collected, so it cannot be cancelled.",
    ),
    Refusal(
        "cancel with a reason that is too long",
        CANCEL,
        lambda stage: stage.booking.cancel(
            stage.world.customer,
            stage.booking.held(stage.world)["id"],
            "x" * REASON_TOO_LONG,
        ),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        field_names=frozenset({"body.reason"}),
    ),
    Refusal(
        "cancel somebody else's reservation",
        CANCEL,
        lambda stage: stage.booking.cancel(
            stage.stranger, stage.booking.held(stage.world)["id"]
        ),
        status.HTTP_404_NOT_FOUND,
        NOT_FOUND,
        NO_SUCH_RESERVATION,
    ),
    Refusal(
        "list with a status that is not one",
        LIST,
        lambda stage: stage.booking.listing(stage.world.customer, status="PENDING"),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        FRAMEWORK,
        NOT_ACCEPTED,
        fields={"query.status": "Choose one of the options offered."},
    ),
    Refusal(
        "list one branch as a customer",
        LIST,
        lambda stage: stage.booking.listing(
            stage.world.customer, branch=stage.world.branch.code
        ),
        status.HTTP_403_FORBIDDEN,
        FORBIDDEN_ROLE,
        "Only a member of staff can list the reservations of another customer or of one branch.",
    ),
    Refusal(
        "read a reservation that does not exist",
        READ,
        lambda stage: stage.booking.read(stage.world.customer, uuid4()),
        status.HTTP_404_NOT_FOUND,
        NOT_FOUND,
        NO_SUCH_RESERVATION,
    ),
    Refusal(
        "read somebody else's reservation",
        READ,
        lambda stage: stage.booking.client.get(
            reservation_path(stage.booking.drafted(stage.world)["id"]),
            headers=stage.booking.headers(stage.stranger),
        ),
        status.HTTP_404_NOT_FOUND,
        NOT_FOUND,
        NO_SUCH_RESERVATION,
    ),
]
