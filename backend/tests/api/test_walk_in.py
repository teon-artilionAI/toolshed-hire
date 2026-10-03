"""Registering a walk-in at the counter, through HTTP (US-20, BR-43).

A counter assistant registers a customer who has no login. The customer gets
a profile at the assistant's branch and no account, so nothing is mailed and
no password exists. An administrator belongs to no branch and names one.
These pin the answer, what is stored, the audit event, the branch rules, and
that the walk-in can then be booked for. Every refusal of a field is pinned
in tests/api/test_walk_in_refusals.py.

These run against the in memory database.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.domain.enums import UserRole
from app.infrastructure.models import AuditEvent, Branch, CustomerProfile, UserAccount
from tests.support.booking_api import BookingClient, answered, build_booking_world, created
from tests.support.checkout_api import CUSTOMERS_PATH, TODAY_HIRE, customer_path
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of
from tests.support.walk_in_api import headers_of, walk_in_body

BRANCH_SCOPE_PROBLEM: Final[str] = "branch-scope"
LOCATION_HEADER: Final[str] = "Location"
CHOOSE_A_BRANCH: Final[str] = "Choose the branch the customer is registered at."
NOT_OUR_BRANCH: Final[str] = "Choose one of our branches."


@pytest.fixture
def branch(session: Session, factory: Factory) -> Branch:
    """Return the committed branch the assistant works at."""
    built = factory.branch(code="CBD")
    session.commit()
    return built


@pytest.fixture
def other_branch(session: Session, factory: Factory) -> Branch:
    """Return a second committed branch."""
    built = factory.branch(code="BLV", name="Bellville")
    session.commit()
    return built


@pytest.fixture
def assistant(session: Session, factory: Factory, branch: Branch) -> UserAccount:
    """Return a committed counter assistant of the branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=branch)
    session.commit()
    return account


@pytest.fixture
def administrator(session: Session, factory: Factory) -> UserAccount:
    """Return a committed administrator, who belongs to no branch."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return account


def register(
    client: TestClient, account: UserAccount, body: dict[str, object]
) -> dict[str, object]:
    """Register a walk-in and return the customer, failing on anything but a 201."""
    response = client.post(CUSTOMERS_PATH, json=body, headers=headers_of(account))
    assert response.status_code == status.HTTP_201_CREATED, response.text
    created_body: dict[str, object] = response.json()
    return created_body


class TestRegisteringAWalkIn:
    """A profile with no account, at the assistant's branch."""

    def test_the_walk_in_is_answered_as_the_counter_sees_a_customer(
        self, client: TestClient, branch: Branch, assistant: UserAccount
    ) -> None:
        response = client.post(CUSTOMERS_PATH, json=walk_in_body(), headers=headers_of(assistant))
        assert response.status_code == status.HTTP_201_CREATED
        body = response.json()
        assert response.headers[LOCATION_HEADER] == customer_path(body["id"])
        assert {key: body[key] for key in body if key != "id"} == {
            "displayName": "Sizwe Ndlovu",
            "email": None,
            "phone": "072 555 0199",
            "hasLogin": False,
            "emailVerified": False,
            "customerType": "INDIVIDUAL",
            "companyName": None,
            "idDocumentType": "DRIVING_LICENCE",
            "idDocumentLast4": "7Q2B",
            "billingSuburb": "Observatory",
            "billingCity": "Cape Town",
            "accountStatus": "ACTIVE",
            "tradeDiscountPercent": "0.00",
            "noShowCount": 0,
            "homeBranchCode": branch.code,
        }

    def test_the_profile_is_stored_with_no_account_and_none_is_made(
        self, client: TestClient, session: Session, assistant: UserAccount
    ) -> None:
        accounts_before = len(session.exec(select(UserAccount)).all())
        body = register(client, assistant, walk_in_body())
        profile = session.get(CustomerProfile, UUID(str(body["id"])))
        assert profile is not None
        assert profile.user_account_id is None
        assert profile.billing_address_line1 == "8 Station Road"
        assert len(session.exec(select(UserAccount)).all()) == accounts_before

    def test_the_registration_is_audited_without_the_customers_details(
        self, client: TestClient, session: Session, branch: Branch, assistant: UserAccount
    ) -> None:
        body = register(client, assistant, walk_in_body())
        (event,) = session.exec(
            select(AuditEvent).where(col(AuditEvent.action) == "customer.walk_in_registered")
        ).all()
        assert (event.entity_type, str(event.entity_id)) == ("customer_profile", body["id"])
        assert event.actor_user_id == assistant.id
        assert event.after_state == {
            "customer_type": "INDIVIDUAL",
            "home_branch_code": branch.code,
            "has_login": False,
        }

    def test_the_new_customer_is_read_back_by_its_key(
        self, client: TestClient, assistant: UserAccount
    ) -> None:
        body = register(client, assistant, walk_in_body())
        response = client.get(customer_path(body["id"]), headers=headers_of(assistant))
        assert response.json() == body

    def test_a_trade_customer_is_registered_with_the_company(
        self, client: TestClient, assistant: UserAccount
    ) -> None:
        body = register(
            client,
            assistant,
            walk_in_body(
                customerType="TRADE", companyName="Ndlovu Plumbing", vatNumber="4123456789"
            ),
        )
        assert (body["customerType"], body["companyName"]) == ("TRADE", "Ndlovu Plumbing")

    def test_the_walk_in_can_be_booked_for_and_confirmed_at_the_counter(
        self,
        booking: BookingClient,
        session: Session,
        factory: Factory,
    ) -> None:
        world = build_booking_world(factory)
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
        session.commit()
        customer = created(booking.client.post(
            CUSTOMERS_PATH, json=walk_in_body(), headers=booking.headers(assistant)
        ))
        body = world.payload(TODAY_HIRE, customer_profile_id=UUID(str(customer["id"])))
        draft = created(booking.create(assistant, body))
        answered(booking.hold(assistant, draft["id"]))
        confirmed = answered(booking.confirm(assistant, draft["id"]))
        assert (confirmed["status"], confirmed["customerName"]) == ("CONFIRMED", "Sizwe Ndlovu")


class TestTheBranch:
    """The assistant's own branch, or the one an administrator names (BR-43)."""

    def test_counter_staff_may_name_their_own_branch(
        self, client: TestClient, branch: Branch, assistant: UserAccount
    ) -> None:
        body = register(client, assistant, walk_in_body(branchCode=branch.code))
        assert body["homeBranchCode"] == branch.code

    def test_counter_staff_naming_another_branch_are_refused_with_403(
        self,
        client: TestClient,
        session: Session,
        other_branch: Branch,
        assistant: UserAccount,
    ) -> None:
        response = client.post(
            CUSTOMERS_PATH,
            json=walk_in_body(branchCode=other_branch.code),
            headers=headers_of(assistant),
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert problem_code(response) == BRANCH_SCOPE_PROBLEM
        assert session.exec(select(CustomerProfile)).all() == []

    def test_an_administrator_registers_at_the_branch_named(
        self, client: TestClient, other_branch: Branch, administrator: UserAccount
    ) -> None:
        body = register(client, administrator, walk_in_body(branchCode=other_branch.code))
        assert body["homeBranchCode"] == other_branch.code

    def test_an_administrator_who_names_no_branch_is_asked_for_one(
        self, client: TestClient, administrator: UserAccount
    ) -> None:
        response = client.post(
            CUSTOMERS_PATH, json=walk_in_body(), headers=headers_of(administrator)
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert problem_of(response)["errors"] == {"fields": {"body.branchCode": CHOOSE_A_BRANCH}}

    @pytest.mark.parametrize("role", [UserRole.COUNTER_STAFF, UserRole.ADMIN])
    def test_a_branch_nobody_trades_from_is_refused_by_name(
        self,
        client: TestClient,
        assistant: UserAccount,
        administrator: UserAccount,
        role: UserRole,
    ) -> None:
        account = assistant if role is UserRole.COUNTER_STAFF else administrator
        response = client.post(
            CUSTOMERS_PATH, json=walk_in_body(branchCode="XYZ"), headers=headers_of(account)
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert problem_of(response)["errors"] == {"fields": {"body.branchCode": NOT_OUR_BRANCH}}
