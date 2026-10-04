"""User and role management through HTTP (FR-25, US-35, BR-41, BR-44, BR-48, BR-51).

The administrator lists the staff, never a customer, opens an account the
person then chooses a password for through the reset link they are sent,
changes a role and a branch, deactivates an account, which stops it signing in
and refreshing at once, and reactivates it, after which it signs in with the
password it had. A role change reaches the next request, because the role is
read from the account and never from the token. These run against the in
memory database on the still clock. The refusals are in
tests/api/test_admin_user_refusals.py.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import status
from sqlmodel import Session, col, select

from app.domain.enums import RevokeReason, UserRole
from app.infrastructure.models import Branch, RefreshSession, UserAccount
from app.infrastructure.notification import FakeEmailGateway
from tests.support.account_desk import RESET_KEY
from tests.support.accounts_api import RESET_COMPLETE_PATH, token_from
from tests.support.admin_api import PAGE_MEMBERS
from tests.support.admin_user_api import (
    ADMIN_USER_MEMBERS,
    CREATED_MEMBERS,
    STAFF_EMAIL,
    actions_about,
    deactivate_user,
    edit_user,
    list_users,
    open_user,
    people_client,
    reactivate_user,
    refused_with,
    staff_body,
)
from tests.support.booking_api import BookingClient, answered, created
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.sessions import REFRESH_PATH, present, refresh_token_of, sign_in

CHOSEN_PASSWORD = "a-made-up-passphrase-for-staff"
ADMIN_ROUTE = "/api/admin/dashboard"


@pytest.fixture
def branches(session: Session, factory: Factory) -> dict[str, Branch]:
    """Commit the three branches."""
    made = {code: factory.branch(code=code) for code in ("CBD", "BLV", "SMW")}
    session.commit()
    return made


@pytest.fixture
def owner(session: Session, factory: Factory, branches: dict[str, Branch]) -> UserAccount:
    """Return the committed owner, an administrator."""
    account = factory.user(role=UserRole.ADMIN, email="owner@toolshedhire.co.za")
    account.full_name = "Pieter Kleynhans"
    session.add(account)
    session.commit()
    return account


@pytest.fixture
def people(
    session: Session, still_clock: FixedClock, email_gateway: FakeEmailGateway
) -> Iterator[BookingClient]:
    """Yield the routes on the in memory database, sending through the fake gateway."""
    with people_client(session, still_clock, email_gateway) as client:
        yield client


def assistant(factory: Factory, session: Session, branch: Branch, name: str) -> UserAccount:
    """Commit a counter assistant at a branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=branch)
    account.full_name = name
    session.add(account)
    session.commit()
    return account


class TestTheList:
    """The staff by name, narrowed and searched, and never a customer."""

    def test_the_staff_are_listed_by_name_in_the_shape_of_the_contract(
        self,
        session: Session,
        factory: Factory,
        people: BookingClient,
        owner: UserAccount,
        branches: dict[str, Branch],
    ) -> None:
        assistant(factory, session, branches["BLV"], "Bongani Zulu")
        factory.user(role=UserRole.CUSTOMER)
        session.commit()
        page = answered(list_users(people, owner))
        assert set(page) == PAGE_MEMBERS
        items = page["items"]
        assert isinstance(items, list)
        assert [item["fullName"] for item in items] == ["Bongani Zulu", "Pieter Kleynhans"]
        assert set(items[0]) == ADMIN_USER_MEMBERS
        bongani, pieter = items
        assert (bongani["role"], bongani["branchCode"], bongani["isActive"]) == (
            "COUNTER_STAFF", branches["BLV"].code, True
        )  # fmt: skip
        assert (pieter["branchCode"], pieter["lastLoginAt"], pieter["lockedUntil"]) == (
            None, None, None
        )  # fmt: skip
        assert str(pieter["createdAt"]).endswith("+02:00")

    def test_the_list_is_narrowed_by_role_and_standing_and_searched(
        self,
        session: Session,
        factory: Factory,
        people: BookingClient,
        owner: UserAccount,
        branches: dict[str, Branch],
    ) -> None:
        bongani = assistant(factory, session, branches["BLV"], "Bongani Zulu")
        bongani.is_active = False
        session.add(bongani)
        session.commit()

        def names(**params: object) -> list[object]:
            items = answered(list_users(people, owner, **params))["items"]
            assert isinstance(items, list)
            return [item["fullName"] for item in items]

        assert names(role="ADMIN") == ["Pieter Kleynhans"]
        assert names(role="COUNTER_STAFF") == ["Bongani Zulu"]
        assert names(active="false") == ["Bongani Zulu"]
        assert names(q="kleyn") == ["Pieter Kleynhans"]
        assert names(q="OWNER@") == ["Pieter Kleynhans"]
        assert names(q="%%") == []


class TestOpeningAnAccount:
    """A new account chooses its own password through the reset link it is sent."""

    def test_a_counter_assistant_is_opened_and_chooses_a_password_through_the_link(
        self,
        session: Session,
        people: BookingClient,
        owner: UserAccount,
        email_gateway: FakeEmailGateway,
    ) -> None:
        body = created(open_user(people, owner, staff_body(branchCode=" cbd ")))
        assert set(body) == CREATED_MEMBERS
        assert body["emailDeliverable"] is True
        user = body["user"]
        assert isinstance(user, dict)
        assert set(user) == ADMIN_USER_MEMBERS
        assert (user["email"], user["role"], user["branchCode"], user["emailVerified"]) == (
            STAFF_EMAIL,
            "COUNTER_STAFF",
            "CBD",
            False,
        )
        assert sign_in(people.client, STAFF_EMAIL, CHOSEN_PASSWORD).status_code == (
            status.HTTP_401_UNAUTHORIZED
        )
        token = token_from(email_gateway, STAFF_EMAIL, RESET_KEY)
        completed = people.client.post(
            RESET_COMPLETE_PATH, json={"token": token, "newPassword": CHOSEN_PASSWORD}
        )
        assert completed.status_code == status.HTTP_204_NO_CONTENT, completed.text
        signed_in = sign_in(people.client, STAFF_EMAIL, CHOSEN_PASSWORD)
        assert signed_in.status_code == status.HTTP_200_OK, signed_in.text
        assert actions_about(session, "user_account")[0] == "user_account.created"

    def test_the_answer_says_when_the_link_could_not_be_handed_over(
        self, session: Session, still_clock: FixedClock, owner: UserAccount
    ) -> None:
        refusing = FakeEmailGateway(failure_reason="The provider is not answering.")
        with people_client(session, still_clock, refusing) as people:
            body = created(
                open_user(people, owner, staff_body(role="ADMIN", branchCode=None, phone=None))
            )
        assert body["emailDeliverable"] is False
        user = body["user"]
        assert isinstance(user, dict)
        assert (user["role"], user["branchCode"], user["phone"]) == ("ADMIN", None, None)


class TestChangingAnAccount:
    """A role or a branch changes, and the change reaches the next request."""

    def test_a_counter_assistant_moves_branch_and_is_renamed(
        self,
        session: Session,
        factory: Factory,
        people: BookingClient,
        owner: UserAccount,
        branches: dict[str, Branch],
    ) -> None:
        staff = assistant(factory, session, branches["CBD"], "Thandi Mokoena")
        user = answered(
            edit_user(
                people,
                owner,
                staff.id,
                {"branchCode": branches["SMW"].code, "fullName": "Thandi M.", "phone": None},
            )
        )
        assert (user["branchCode"], user["fullName"], user["phone"]) == (
            branches["SMW"].code,
            "Thandi M.",
            None,
        )
        assert actions_about(session, "user_account") == ["user_account.updated"]

    def test_a_demoted_administrator_is_refused_an_admin_route_with_the_old_token(
        self,
        session: Session,
        factory: Factory,
        people: BookingClient,
        owner: UserAccount,
        branches: dict[str, Branch],
    ) -> None:
        bookkeeper = factory.user(role=UserRole.ADMIN)
        session.commit()
        old_headers = people.headers(bookkeeper)
        assert people.client.get(ADMIN_ROUTE, headers=old_headers).status_code == 200
        answered(
            edit_user(
                people,
                owner,
                bookkeeper.id,
                {"role": "COUNTER_STAFF", "branchCode": branches["CBD"].code},
            )
        )
        refused = people.client.get(ADMIN_ROUTE, headers=old_headers)
        assert refused_with(refused, status.HTTP_403_FORBIDDEN)["type"] == (
            "https://toolshedhire.co.za/problems/authorisation-failure"
        )

    def test_a_promoted_assistant_reaches_an_admin_route_with_the_token_they_had(
        self,
        session: Session,
        factory: Factory,
        people: BookingClient,
        owner: UserAccount,
        branches: dict[str, Branch],
    ) -> None:
        staff = assistant(factory, session, branches["CBD"], "Thandi Mokoena")
        old_headers = people.headers(staff)
        assert people.client.get(ADMIN_ROUTE, headers=old_headers).status_code == 403
        user = answered(edit_user(people, owner, staff.id, {"role": "ADMIN"}))
        assert (user["role"], user["branchCode"]) == ("ADMIN", None)
        assert people.client.get(ADMIN_ROUTE, headers=old_headers).status_code == 200


class TestDeactivatingAndReactivating:
    """A deactivated account stops at once, and a reactivated one signs in as before."""

    def test_a_deactivated_account_cannot_sign_in_refresh_or_use_its_token(
        self,
        session: Session,
        factory: Factory,
        people: BookingClient,
        owner: UserAccount,
        branches: dict[str, Branch],
    ) -> None:
        staff = assistant(factory, session, branches["CBD"], "Thandi Mokoena")
        signed_in = sign_in(people.client, staff.email)
        assert signed_in.status_code == status.HTTP_200_OK
        refresh_token = refresh_token_of(signed_in)
        old_headers = people.headers(staff)
        user = answered(deactivate_user(people, owner, staff.id))
        assert user["isActive"] is False
        assert sign_in(people.client, staff.email).status_code == status.HTTP_401_UNAUTHORIZED
        refreshed = present(people.client, REFRESH_PATH, refresh_token)
        assert refreshed.status_code == status.HTTP_401_UNAUTHORIZED
        assert people.client.get("/api/me", headers=old_headers).status_code == 403
        sessions = session.exec(
            select(RefreshSession).where(col(RefreshSession.user_account_id) == staff.id)
        ).all()
        assert {row.revoked_reason for row in sessions} == {RevokeReason.ADMIN_REVOKE}

    def test_a_reactivated_account_signs_in_with_the_password_it_had(
        self,
        session: Session,
        factory: Factory,
        people: BookingClient,
        owner: UserAccount,
        branches: dict[str, Branch],
    ) -> None:
        staff = assistant(factory, session, branches["CBD"], "Thandi Mokoena")
        answered(deactivate_user(people, owner, staff.id))
        user = answered(reactivate_user(people, owner, staff.id))
        assert user["isActive"] is True
        assert sign_in(people.client, staff.email).status_code == status.HTTP_200_OK
        assert actions_about(session, "user_account")[:2] == [
            "user_account.deactivated",
            "user_account.reactivated",
        ]
