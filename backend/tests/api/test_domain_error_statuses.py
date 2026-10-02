"""The status every domain error is answered with.

The domain raises meaning and the HTTP layer chooses a number, in one table in
`app/api/errors.py`. This file pins that table for the errors the design
document names. A conflict and an illegal transition are 409, because the
request was fine and lost to the state of the system. A branch scope breach and
a customer on hold are 403, because the caller is known and the answer is no.

Three of these errors are not raised by any flow yet. They are mapped already
so that the first use case to raise one cannot answer with the fallback status
by accident. The table is therefore tested directly and through a real
application, which is what proves the handler reads it.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from app.api.errors import DOMAIN_ERROR_STATUS, register_exception_handlers
from app.domain import errors
from app.domain.errors import (
    AccountOnHoldError,
    AllocationConflictError,
    BranchScopeError,
    DomainError,
    StateTransitionError,
)
from tests.support.http import problem_code, problem_of

RAISE_PATH: Final[str] = "/probe/raise/{name}"

RAISED: Final[dict[str, DomainError]] = {
    "conflict": AllocationConflictError(
        "No free unit.", period="[2026-03-09,2026-03-12)", available_quantity=0
    ),
    "transition": StateTransitionError(
        "A held reservation cannot be collected.", from_status="HELD", to_status="COLLECTED"
    ),
    "branch": BranchScopeError(
        "An assistant at Bellville opened a collection at CBD.", {"branch_code": "CBD"}
    ),
    "on-hold": AccountOnHoldError(
        "The customer account is on hold after three no-shows.", {"account_status": "ON_HOLD"}
    ),
}

EXPECTED: Final[list[tuple[str, int, str]]] = [
    ("conflict", status.HTTP_409_CONFLICT, "asset-unavailable"),
    ("transition", status.HTTP_409_CONFLICT, "state-transition"),
    ("branch", status.HTTP_403_FORBIDDEN, "branch-scope"),
    ("on-hold", status.HTTP_403_FORBIDDEN, "account-on-hold"),
]


@pytest.fixture(scope="module")
def raising_client() -> TestClient:
    """Return a client for an application whose one route raises a chosen domain error."""
    application = FastAPI()
    register_exception_handlers(application)

    @application.get(RAISE_PATH)
    def raise_named(name: str) -> None:
        """Raise the domain error registered under `name`."""
        raise RAISED[name]

    return TestClient(application)


class TestTheStatusTable:
    """One entry per domain error, so none falls through to the fallback."""

    def test_every_domain_error_class_has_a_status(self) -> None:
        declared = {
            candidate
            for candidate in vars(errors).values()
            if isinstance(candidate, type)
            and issubclass(candidate, DomainError)
            and candidate is not DomainError
        }
        assert declared == set(DOMAIN_ERROR_STATUS)

    def test_a_conflict_and_an_illegal_transition_are_409(self) -> None:
        assert DOMAIN_ERROR_STATUS[AllocationConflictError] == status.HTTP_409_CONFLICT
        assert DOMAIN_ERROR_STATUS[StateTransitionError] == status.HTTP_409_CONFLICT

    def test_a_branch_scope_breach_and_a_customer_on_hold_are_403(self) -> None:
        assert DOMAIN_ERROR_STATUS[BranchScopeError] == status.HTTP_403_FORBIDDEN
        assert DOMAIN_ERROR_STATUS[AccountOnHoldError] == status.HTTP_403_FORBIDDEN


class TestTheHandlerAnswersWithThatStatus:
    """Through a real application, as a problem document and never a 500."""

    @pytest.mark.parametrize(("name", "expected_status", "expected_code"), EXPECTED)
    def test_the_error_is_answered_with_its_status_and_its_slug(
        self, raising_client: TestClient, name: str, expected_status: int, expected_code: str
    ) -> None:
        response = raising_client.get(RAISE_PATH.format(name=name))
        assert response.status_code == expected_status
        assert problem_code(response) == expected_code

    def test_the_structured_detail_reaches_the_problem_document(
        self, raising_client: TestClient
    ) -> None:
        response = raising_client.get(RAISE_PATH.format(name="transition"))
        assert problem_of(response)["errors"] == {"from_status": "HELD", "to_status": "COLLECTED"}
