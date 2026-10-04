"""Every refusal of user and role management, with its status, its problem type and its field.

A field a rule refuses is a 422 naming it under `errors.fields`, and so is a
field no request may carry, a password and an address to change among them.
An account nobody opened, and a customer's account, are a 404. The last
active administrator demoted and an administrator's own account deactivated
are a 409 `state-transition`. Nothing refused leaves an audit event.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import status
from sqlmodel import Session

from app.domain.enums import UserRole
from app.domain.staff_account import LAST_ADMINISTRATOR_MESSAGE, OWN_ACCOUNT_MESSAGE
from app.infrastructure.models import Branch, UserAccount
from app.infrastructure.notification import FakeEmailGateway
from tests.api.role_matrix import NOBODYS_KEY
from tests.support.admin_user_api import (
    STAFF_EMAIL,
    actions_about,
    deactivate_user,
    edit_user,
    field_refused,
    list_users,
    open_user,
    people_client,
    reactivate_user,
    refused_with,
    staff_body,
)
from tests.support.booking_api import BookingClient
from tests.support.clock import FixedClock
from tests.support.factories import Factory

STATE_TRANSITION_PROBLEM = "https://toolshedhire.co.za/problems/state-transition"
NOT_FOUND_PROBLEM = "https://toolshedhire.co.za/problems/not-found"


@pytest.fixture
def branch(session: Session, factory: Factory) -> Branch:
    """Commit the CBD branch."""
    made = factory.branch(code="CBD")
    session.commit()
    return made


@pytest.fixture
def owner(session: Session, factory: Factory, branch: Branch) -> UserAccount:
    """Return the committed owner, the only administrator."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return account


@pytest.fixture
def people(
    session: Session, still_clock: FixedClock, email_gateway: FakeEmailGateway
) -> Iterator[BookingClient]:
    """Yield the routes on the in memory database."""
    with people_client(session, still_clock, email_gateway) as client:
        yield client


@pytest.fixture
def staff(session: Session, factory: Factory, branch: Branch) -> UserAccount:
    """Return a committed counter assistant at CBD."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=branch)
    session.commit()
    return account


class TestOpeningRefusals:
    """A new account that breaks a rule is a 422 naming the field, and nothing is opened."""

    @pytest.mark.parametrize(
        ("members", "field"),
        [
            ({"role": "CUSTOMER", "branchCode": None}, "body.role"),
            ({"role": "MANAGER"}, "body.role"),
            ({"branchCode": None}, "body.branchCode"),
            ({"role": "ADMIN"}, "body.branchCode"),
            ({"branchCode": "XYZ"}, "body.branchCode"),
            ({"branchCode": "TOOLONG"}, "body.branchCode"),
            ({"fullName": "   "}, "body.fullName"),
            ({"fullName": "x" * 121}, "body.fullName"),
            ({"phone": "ring me"}, "body.phone"),
            ({"email": "not-an-address"}, "body.email"),
            ({"password": "a-made-up-passphrase"}, "body.password"),
            ({"passwordHash": "anything"}, "body.passwordHash"),
        ],
    )
    def test_a_field_that_breaks_a_rule_is_named(
        self,
        session: Session,
        people: BookingClient,
        owner: UserAccount,
        members: dict[str, object],
        field: str,
    ) -> None:
        response = open_user(people, owner, staff_body(**members))
        assert field_refused(response) == [field]
        assert actions_about(session, "user_account") == []

    def test_an_address_another_account_holds_is_named(
        self, session: Session, factory: Factory, people: BookingClient, owner: UserAccount
    ) -> None:
        factory.user(role=UserRole.CUSTOMER, email=STAFF_EMAIL)
        session.commit()
        response = open_user(people, owner, staff_body(email=STAFF_EMAIL.upper()))
        problem = refused_with(response, status.HTTP_422_UNPROCESSABLE_CONTENT)
        assert problem["errors"] == {
            "fields": {"body.email": "Another account already uses this email address."}
        }


class TestEditRefusals:
    """An edit that breaks a rule is refused, and nothing changes."""

    @pytest.mark.parametrize(
        ("body", "field"),
        [
            ({"role": None}, "body.role"),
            ({"fullName": None}, "body.fullName"),
            ({"branchCode": None}, "body.branchCode"),
            ({"role": "CUSTOMER"}, "body.role"),
            ({"email": "new.address@toolshedhire.co.za"}, "body.email"),
            ({"password": "a-made-up-passphrase"}, "body.password"),
            ({"isActive": False}, "body.isActive"),
        ],
    )
    def test_a_field_that_breaks_a_rule_is_named(
        self,
        session: Session,
        people: BookingClient,
        owner: UserAccount,
        staff: UserAccount,
        body: dict[str, object],
        field: str,
    ) -> None:
        assert field_refused(edit_user(people, owner, staff.id, body)) == [field]
        assert actions_about(session, "user_account") == []

    def test_the_last_active_administrator_is_never_given_another_role(
        self, people: BookingClient, owner: UserAccount, branch: Branch
    ) -> None:
        response = edit_user(
            people, owner, owner.id, {"role": "COUNTER_STAFF", "branchCode": branch.code}
        )
        problem = refused_with(response, status.HTTP_409_CONFLICT)
        assert (problem["type"], problem["detail"]) == (
            STATE_TRANSITION_PROBLEM,
            LAST_ADMINISTRATOR_MESSAGE,
        )
        assert problem["errors"] == {"from_status": "ADMIN", "to_status": "COUNTER_STAFF"}

    def test_a_customer_account_and_a_key_nobody_issued_are_not_found(
        self, session: Session, factory: Factory, people: BookingClient, owner: UserAccount
    ) -> None:
        customer = factory.user(role=UserRole.CUSTOMER)
        session.commit()
        for key in (customer.id, NOBODYS_KEY):
            response = edit_user(people, owner, key, {"fullName": "Somebody Else"})
            assert refused_with(response, status.HTTP_404_NOT_FOUND)["type"] == NOT_FOUND_PROBLEM

    def test_a_key_that_is_not_a_key_is_named(
        self, people: BookingClient, owner: UserAccount
    ) -> None:
        assert field_refused(edit_user(people, owner, "not-a-key", {"fullName": "X"})) == [
            "path.id"
        ]


class TestDeactivationRefusals:
    """The own account and a reason out of bounds are refused, and nothing changes."""

    def test_an_administrator_cannot_deactivate_their_own_account(
        self, session: Session, people: BookingClient, owner: UserAccount
    ) -> None:
        problem = refused_with(deactivate_user(people, owner, owner.id), status.HTTP_409_CONFLICT)
        assert (problem["type"], problem["detail"]) == (
            STATE_TRANSITION_PROBLEM,
            OWN_ACCOUNT_MESSAGE,
        )
        assert actions_about(session, "user_account") == []

    @pytest.mark.parametrize("reason", [None, "", "Gone", "x" * 201])
    def test_a_reason_out_of_bounds_is_named(
        self, people: BookingClient, owner: UserAccount, staff: UserAccount, reason: object
    ) -> None:
        response = deactivate_user(people, owner, staff.id, reason=reason)
        assert field_refused(response) == ["body.reason"]

    def test_a_missing_body_is_named(
        self, people: BookingClient, owner: UserAccount, staff: UserAccount
    ) -> None:
        response = people.client.post(
            f"/api/admin/users/{staff.id}/deactivation", headers=people.headers(owner)
        )
        assert refused_with(response, status.HTTP_422_UNPROCESSABLE_CONTENT)

    def test_an_account_nobody_opened_is_not_found_either_way(
        self, people: BookingClient, owner: UserAccount
    ) -> None:
        for response in (
            deactivate_user(people, owner, NOBODYS_KEY),
            reactivate_user(people, owner, NOBODYS_KEY),
        ):
            assert refused_with(response, status.HTTP_404_NOT_FOUND)["type"] == NOT_FOUND_PROBLEM


class TestListRefusals:
    """A query the list cannot answer is a 422 naming the parameter."""

    @pytest.mark.parametrize(
        ("params", "field"),
        [
            ({"role": "CUSTOMER"}, "query.role"),
            ({"role": "MANAGER"}, "query.role"),
            ({"q": "a"}, "query.q"),
            ({"q": "x" * 81}, "query.q"),
            ({"active": "maybe"}, "query.active"),
            ({"page": 0}, "query.page"),
            ({"pageSize": 0}, "query.pageSize"),
            ({"pageSize": 101}, "query.pageSize"),
        ],
    )
    def test_a_parameter_out_of_range_is_named(
        self,
        people: BookingClient,
        owner: UserAccount,
        params: dict[str, object],
        field: str,
    ) -> None:
        assert field_refused(list_users(people, owner, **params)) == [field]

    @pytest.mark.parametrize("role", [UserRole.COUNTER_STAFF, UserRole.CUSTOMER])
    def test_anybody_but_an_administrator_is_refused(
        self,
        session: Session,
        factory: Factory,
        people: BookingClient,
        branch: Branch,
        role: UserRole,
    ) -> None:
        caller = factory.user(
            role=role, branch=branch if role is UserRole.COUNTER_STAFF else None
        )
        session.commit()
        assert list_users(people, caller).status_code == status.HTTP_403_FORBIDDEN
        response = open_user(people, caller, staff_body())
        assert response.status_code == status.HTTP_403_FORBIDDEN
