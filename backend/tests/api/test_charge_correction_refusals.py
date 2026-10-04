"""Everything the three charge corrections refuse, and the words each refusal uses (BR-24, BR-25).

A waiver, a reversal and an adjustment are each asked for by a caller who is
not an administrator, about a charge or a hire that is not there, with a
reason or an amount the contract does not take, and for a correction the
charge cannot take. Each case pins the status, the problem type and the words,
and a guard checks that no sentence reads like a log line (NFR-12).

The hires are the worked example's, built in tests/support/correction_api.py.
These run against the in memory database, and the clock stands still on
Monday the second of March 2026 until a case moves it.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from sqlmodel import Session

from app.application.hire.charge_corrections import CHARGE_NOT_FOUND_MESSAGE
from app.application.hire.read_rental import RENTAL_NOT_FOUND_MESSAGE
from app.domain.charge_corrections import (
    ALREADY_REVERSED_MESSAGE,
    DEPOSIT_MOVEMENT_MESSAGE,
    NOT_SETTLED_MESSAGE,
    REVERSAL_OF_A_REVERSAL_MESSAGE,
    ZERO_ADJUSTMENT_MESSAGE,
)
from app.domain.enums import UserRole
from tests.api.reservation_refusal_cases import (
    ANONYMOUS,
    FORBIDDEN_ROLE,
    FRAMEWORK,
    NOT_FOUND,
    TRANSITION,
)
from tests.api.test_plain_refusals import FORBIDDEN_PATTERNS, sentences_of
from tests.support.admin_api import REASON, charge_of, reverse, waive
from tests.support.booking_api import BookingClient, answered
from tests.support.catalogue import refused_fields
from tests.support.correction_api import (
    ADJUST,
    COUNTER,
    CUSTOMER,
    NOBODY,
    REVERSE,
    WAIVE,
    Case,
    Desk,
    adjusted_by,
    asked_by,
    deposit_movement_reversed,
    pending_fee_reversed,
    posted_with,
    reversal_reversed,
    reversed_twice,
    settled_fee,
    settled_hire,
    unknown,
)
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of
from tests.support.rental_api import worked_example_world

SETTLED_ALREADY: Final[str] = (
    "This charge is settled, so it cannot be changed. A correction is a new charge."
)
REASON_TOO_LONG: Final[int] = 201
TOO_SHORT: Final[str] = "abcd"
NOT_FOUND_STATUS: Final[int] = status.HTTP_404_NOT_FOUND
CONFLICT: Final[int] = status.HTTP_409_CONFLICT
REFUSED: Final[int] = status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.fixture
def desk(booking: BookingClient, session: Session, factory: Factory) -> Desk:
    """Return two units of the worked example, a counter assistant and an administrator."""
    world = worked_example_world(session, factory, units=2)
    assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    administrator = factory.user(role=UserRole.ADMIN)
    session.commit()
    return Desk(booking, session, world, assistant, administrator)


def _refusals_by_role() -> list[Case]:
    """Return the three callers who are refused, for each of the three corrections."""
    refused = (status.HTTP_403_FORBIDDEN, FORBIDDEN_ROLE)
    expected = {COUNTER: refused, CUSTOMER: refused}
    expected[NOBODY] = (status.HTTP_401_UNAUTHORIZED, ANONYMOUS)
    return [
        Case(f"{correction} as {role}", asked_by(role, correction), answer, code)
        for correction in (WAIVE, REVERSE, ADJUST)
        for role, (answer, code) in expected.items()
    ]


REASON_FIELD: Final[frozenset[str]] = frozenset({"body.reason"})
AMOUNT_FIELD: Final[frozenset[str]] = frozenset({"body.amountIncVat"})


CASES: Final[list[Case]] = [
    *_refusals_by_role(),
    Case(
        "waive a charge that does not exist",
        unknown(WAIVE),
        NOT_FOUND_STATUS,
        NOT_FOUND,
        CHARGE_NOT_FOUND_MESSAGE,
    ),
    Case(
        "waive a settled charge",
        lambda desk: waive(desk.booking, desk.administrator, settled_fee(desk)),
        CONFLICT,
        TRANSITION,
        SETTLED_ALREADY,
    ),
    Case("waive with no reason", posted_with(WAIVE, {}), REFUSED, FRAMEWORK, fields=REASON_FIELD),
    Case(
        "waive with a blank reason",
        posted_with(WAIVE, {"reason": "   "}),
        REFUSED,
        FRAMEWORK,
        fields=REASON_FIELD,
    ),
    Case(
        "waive with a reason too short",
        posted_with(WAIVE, {"reason": TOO_SHORT}),
        REFUSED,
        FRAMEWORK,
        fields=REASON_FIELD,
    ),
    Case(
        "waive with a reason too long",
        posted_with(WAIVE, {"reason": "x" * REASON_TOO_LONG}),
        REFUSED,
        FRAMEWORK,
        fields=REASON_FIELD,
    ),
    Case(
        "waive with a field the contract does not take",
        posted_with(WAIVE, {"reason": REASON, "status": "WAIVED"}),
        REFUSED,
        FRAMEWORK,
        fields=frozenset({"body.status"}),
    ),
    Case(
        "reverse a charge that does not exist",
        unknown(REVERSE),
        NOT_FOUND_STATUS,
        NOT_FOUND,
        CHARGE_NOT_FOUND_MESSAGE,
    ),
    Case("reverse a charge twice", reversed_twice, CONFLICT, TRANSITION, ALREADY_REVERSED_MESSAGE),
    Case(
        "reverse a reversal",
        reversal_reversed,
        CONFLICT,
        TRANSITION,
        REVERSAL_OF_A_REVERSAL_MESSAGE,
    ),
    Case(
        "reverse the deposit hold",
        deposit_movement_reversed("DEPOSIT_HOLD"),
        CONFLICT,
        TRANSITION,
        DEPOSIT_MOVEMENT_MESSAGE,
    ),
    Case(
        "reverse the deposit release",
        deposit_movement_reversed("DEPOSIT_RELEASE"),
        CONFLICT,
        TRANSITION,
        DEPOSIT_MOVEMENT_MESSAGE,
    ),
    Case(
        "reverse a charge still owed",
        pending_fee_reversed,
        CONFLICT,
        TRANSITION,
        NOT_SETTLED_MESSAGE,
    ),
    Case(
        "adjust a rental that does not exist",
        unknown(ADJUST),
        NOT_FOUND_STATUS,
        NOT_FOUND,
        RENTAL_NOT_FOUND_MESSAGE,
    ),
    Case(
        "adjust by nothing",
        adjusted_by("0.00"),
        REFUSED,
        FRAMEWORK,
        sentences={"body.amountIncVat": ZERO_ADJUSTMENT_MESSAGE},
    ),
    Case("adjust by a number", adjusted_by(150), REFUSED, FRAMEWORK, fields=AMOUNT_FIELD),
    Case("adjust by thousandths", adjusted_by("150.000"), REFUSED, FRAMEWORK, fields=AMOUNT_FIELD),
    Case("adjust by letters", adjusted_by("abc"), REFUSED, FRAMEWORK, fields=AMOUNT_FIELD),
    Case("adjust with no reason", posted_with(ADJUST, {}), REFUSED, FRAMEWORK, fields=REASON_FIELD),
]
CASE_IDS: Final[list[str]] = [case.name for case in CASES]


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_the_refusal_is_answered_as_the_case_says(desk: Desk, case: Case) -> None:
    response = case.ask(desk)
    assert response.status_code == case.status, response.text
    assert problem_code(response) == case.code
    body = problem_of(response)
    if case.detail is not None:
        assert body["detail"] == case.detail
    if case.fields is not None:
        assert refused_fields(body).keys() == case.fields
    if case.sentences is not None:
        assert refused_fields(body) == case.sentences


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_no_sentence_reads_like_a_log_line(desk: Desk, case: Case) -> None:
    offenders = [
        f"{sentence!r} contains {pattern!r}"
        for sentence in sentences_of(problem_of(case.ask(desk)))
        for pattern in FORBIDDEN_PATTERNS
        if pattern in sentence
    ]
    assert offenders == []


def test_a_refused_correction_leaves_the_hire_exactly_as_it_was(desk: Desk) -> None:
    rental = settled_hire(desk)
    refused = reverse(desk.booking, desk.administrator, charge_of(rental, "DEPOSIT_HOLD")["id"])
    assert refused.status_code == status.HTTP_409_CONFLICT
    again = answered(
        desk.booking.client.get(
            f"/api/rentals/{rental['id']}", headers=desk.booking.headers(desk.administrator)
        )
    )
    assert again == rental
