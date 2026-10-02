"""Ownership, branch scope and the account read again, through HTTP (BR-42, BR-43).

A customer who asks for a reservation that is not theirs gets 404, never 403,
in exactly the words used for a key nobody ever issued. The scope is in the
query, so the test also counts the statements and finds no second lookup.
There is no real route that reads a booking yet, so the probe application
mounts one over the real unit of work and the real repository.

Counter staff who book at a branch that is not their own get 403 with
`BranchScopeError`, on the real booking route.

And an administrator whose role was taken away is refused by the dependency
that reads the account again, even when the session of the request still holds
the old row.
"""

from __future__ import annotations

from typing import Final
from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlmodel import Session, select

from app.domain.enums import UserRole
from app.infrastructure.models import Reservation, UserAccount
from tests.support.factories import Factory
from tests.support.http import booking_payload, future_period, problem_code, problem_of
from tests.support.probe_app import ADMIN_PATH, FRESH_ADMIN_PATH, RESERVATION_PATH_TEMPLATE
from tests.support.scenarios import AllocationScenario, build_allocation_scenario
from tests.support.statements import recorded_statements
from tests.support.tokens import authorization_header, mint_access_token

ALLOCATIONS_PATH: Final[str] = "/api/allocations"
NOT_FOUND_PROBLEM: Final[str] = "not-found"
BRANCH_SCOPE_PROBLEM: Final[str] = "branch-scope"
AUTHORISATION_PROBLEM: Final[str] = "authorisation-failure"
SHARED_REQUEST_ID: Final[dict[str, str]] = {
    "X-Request-ID": "6f1c2b9e-3d4a-4c5b-8e7f-0a1b2c3d4e5f"
}


def reservation_path(reservation_id: object) -> str:
    """Return the probe path of one reservation."""
    return RESERVATION_PATH_TEMPLATE.format(reservation_id=reservation_id)


def as_account(account: UserAccount) -> dict[str, str]:
    """Return the request headers of a signed in account, with the shared request id."""
    return {**authorization_header(mint_access_token(account.id)), **SHARED_REQUEST_ID}


@pytest.fixture
def scenario(session: Session, factory: Factory) -> AllocationScenario:
    """Return a committed booking that belongs to the scenario's customer."""
    built = build_allocation_scenario(factory, future_period())
    session.commit()
    return built


class TestOwnershipIsInTheQuery:
    """Somebody else's reservation is not found, and is never fetched (BR-42)."""

    def test_the_owner_reads_their_own_reservation(
        self, probe_client: TestClient, scenario: AllocationScenario
    ) -> None:
        response = probe_client.get(
            reservation_path(scenario.reservation.id), headers=as_account(scenario.customer)
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "id": str(scenario.reservation.id),
            "reference": scenario.reservation.reference,
        }

    def test_another_customer_gets_404_and_never_403(
        self,
        probe_client: TestClient,
        session: Session,
        factory: Factory,
        scenario: AllocationScenario,
    ) -> None:
        somebody_else = factory.user(role=UserRole.CUSTOMER)
        factory.customer_profile(branch=scenario.branch, account=somebody_else)
        session.commit()
        response = probe_client.get(
            reservation_path(scenario.reservation.id), headers=as_account(somebody_else)
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert problem_code(response) == NOT_FOUND_PROBLEM

    def test_the_answer_is_the_same_as_for_a_reservation_that_does_not_exist(
        self,
        probe_client: TestClient,
        session: Session,
        factory: Factory,
        scenario: AllocationScenario,
    ) -> None:
        somebody_else = factory.user(role=UserRole.CUSTOMER)
        session.commit()
        headers = as_account(somebody_else)
        not_theirs = problem_of(
            probe_client.get(reservation_path(scenario.reservation.id), headers=headers)
        )
        missing_id = uuid4()
        missing = problem_of(probe_client.get(reservation_path(missing_id), headers=headers))
        # The two documents differ only where they quote the key that was asked for.
        swapped = str(missing).replace(str(missing_id), str(scenario.reservation.id))
        assert swapped == str(not_theirs)

    def test_the_refusal_is_one_statement_with_the_owner_in_it(
        self,
        probe_client: TestClient,
        session: Session,
        factory: Factory,
        sqlite_engine: Engine,
        scenario: AllocationScenario,
    ) -> None:
        somebody_else = factory.user(role=UserRole.CUSTOMER)
        session.commit()
        headers = as_account(somebody_else)
        # Read before the recording starts. The test session reloads the row to
        # answer this, and that statement is not one the request made.
        path = reservation_path(scenario.reservation.id)
        with recorded_statements(sqlite_engine) as statements:
            probe_client.get(path, headers=headers)
        reads = [sql for sql in statements if "FROM reservation" in sql]
        assert len(reads) == 1
        assert "JOIN customer_profile" in reads[0]
        assert "customer_profile.user_account_id" in reads[0]

    @pytest.mark.parametrize("role", [UserRole.COUNTER_STAFF, UserRole.ADMIN])
    def test_staff_read_any_customers_reservation(
        self,
        probe_client: TestClient,
        session: Session,
        factory: Factory,
        scenario: AllocationScenario,
        role: UserRole,
    ) -> None:
        branch = factory.branch() if role is UserRole.COUNTER_STAFF else None
        member_of_staff = factory.user(role=role, branch=branch)
        session.commit()
        response = probe_client.get(
            reservation_path(scenario.reservation.id), headers=as_account(member_of_staff)
        )
        assert response.status_code == status.HTTP_200_OK

    def test_an_anonymous_caller_is_401_before_any_reservation_is_looked_up(
        self, probe_client: TestClient, scenario: AllocationScenario
    ) -> None:
        response = probe_client.get(reservation_path(scenario.reservation.id))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestBranchScope:
    """Counter staff write to their own branch and to no other (BR-43)."""

    def payload(self, scenario: AllocationScenario) -> dict[str, object]:
        body = booking_payload(
            product_model_id=scenario.product_model.id,
            branch_id=scenario.branch.id,
            period=future_period(days_ahead=14),
        )
        body["customerUserId"] = str(scenario.customer.id)
        return body

    def test_counter_staff_of_another_branch_are_refused_with_403(
        self,
        client: TestClient,
        session: Session,
        factory: Factory,
        scenario: AllocationScenario,
    ) -> None:
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=factory.branch())
        session.commit()
        response = client.post(
            ALLOCATIONS_PATH, json=self.payload(scenario), headers=as_account(assistant)
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert problem_code(response) == BRANCH_SCOPE_PROBLEM
        assert problem_of(response)["errors"] == {"branch_id": str(scenario.branch.id)}

    def test_the_refused_booking_leaves_nothing_behind(
        self,
        client: TestClient,
        session: Session,
        factory: Factory,
        scenario: AllocationScenario,
    ) -> None:
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=factory.branch())
        session.commit()
        client.post(ALLOCATIONS_PATH, json=self.payload(scenario), headers=as_account(assistant))
        remaining = session.exec(select(Reservation)).all()
        assert [reservation.id for reservation in remaining] == [scenario.reservation.id]

    def test_counter_staff_of_the_branch_may_book_there(
        self,
        client: TestClient,
        session: Session,
        factory: Factory,
        scenario: AllocationScenario,
    ) -> None:
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=scenario.branch)
        session.commit()
        response = client.post(
            ALLOCATIONS_PATH, json=self.payload(scenario), headers=as_account(assistant)
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_an_administrator_and_a_customer_are_not_branch_scoped(
        self,
        client: TestClient,
        session: Session,
        factory: Factory,
        scenario: AllocationScenario,
    ) -> None:
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        by_admin = client.post(
            ALLOCATIONS_PATH, json=self.payload(scenario), headers=as_account(administrator)
        )
        assert by_admin.status_code == status.HTTP_201_CREATED
        own = booking_payload(
            product_model_id=scenario.product_model.id,
            branch_id=scenario.branch.id,
            period=future_period(days_ahead=30),
        )
        by_customer = client.post(
            ALLOCATIONS_PATH, json=own, headers=as_account(scenario.customer)
        )
        assert by_customer.status_code == status.HTTP_201_CREATED


class TestTheAccountIsReadAgain:
    """The dependency a sensitive action uses does not trust a row it already holds."""

    @pytest.fixture
    def demoted_behind_the_session(
        self, session: Session, factory: Factory, sqlite_engine: Engine
    ) -> UserAccount:
        """Return an administrator the session still holds as one, demoted in the database.

        The row is changed on a connection of its own, so the copy the session
        has already loaded is left as it was. That is what a request would be
        holding if the role changed after it had authenticated.
        """
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        session.refresh(administrator)
        with sqlite_engine.begin() as connection:
            connection.execute(
                text("UPDATE user_account SET role = :role WHERE email = :email"),
                {"role": UserRole.CUSTOMER.value, "email": administrator.email},
            )
        return administrator

    def test_the_ordinary_chain_admits_on_the_row_the_request_already_holds(
        self, probe_client: TestClient, demoted_behind_the_session: UserAccount
    ) -> None:
        response = probe_client.get(ADMIN_PATH, headers=as_account(demoted_behind_the_session))
        assert response.status_code == status.HTTP_200_OK

    def test_the_fresh_dependency_reads_the_row_again_and_refuses(
        self, probe_client: TestClient, demoted_behind_the_session: UserAccount
    ) -> None:
        response = probe_client.get(
            FRESH_ADMIN_PATH, headers=as_account(demoted_behind_the_session)
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert problem_code(response) == AUTHORISATION_PROBLEM

    def test_the_fresh_dependency_admits_an_administrator_who_still_is_one(
        self, probe_client: TestClient, session: Session, factory: Factory
    ) -> None:
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        response = probe_client.get(FRESH_ADMIN_PATH, headers=as_account(administrator))
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["role"] == UserRole.ADMIN.value

    def test_the_fresh_dependency_refuses_a_deactivated_administrator(
        self, probe_client: TestClient, session: Session, factory: Factory
    ) -> None:
        administrator = factory.user(role=UserRole.ADMIN, is_active=False)
        session.commit()
        response = probe_client.get(FRESH_ADMIN_PATH, headers=as_account(administrator))
        assert response.status_code == status.HTTP_403_FORBIDDEN
