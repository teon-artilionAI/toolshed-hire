"""Completing a password reset proves the email address, through HTTP (US-04, BR-47).

The reset link only ever goes to the address of the account, so whoever uses
it reads mail there, which is all a verification link proves. A customer who
never used their verification link, and a new member of staff who chooses a
first password through the link their new account was sent, both end
verified, and the session responses and the administrator's list say so. The
rules are proved with no database in tests/unit/test_password_reset_use_cases.py
and the transaction on PostgreSQL in
tests/integration/test_reset_proves_the_address.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.application.identity.password_reset import RESET_COMPLETED_ACTION
from app.domain.enums import UserRole
from app.infrastructure.models import AuditEvent, UserAccount
from app.infrastructure.notification import FakeEmailGateway
from tests.support.account_desk import RESET_KEY
from tests.support.accounts_api import (
    NEW_EMAIL,
    NEW_PASSWORD,
    REGISTER_PATH,
    RESET_COMPLETE_PATH,
    RESET_REQUEST_PATH,
    registration_body,
    token_from,
)
from tests.support.admin_user_api import (
    STAFF_EMAIL,
    list_users,
    open_user,
    people_client,
    staff_body,
)
from tests.support.booking_api import BookingClient, answered, created
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.sessions import ME_PATH, sign_in
from tests.support.tokens import authorization_header

STAFF_PASSWORD: Final[str] = "a-made-up-passphrase-for-staff"


def complete_reset(
    client: TestClient, gateway: FakeEmailGateway, address: str, password: str
) -> None:
    """Use the newest reset link sent to an address to choose a password."""
    token = token_from(gateway, address, RESET_KEY)
    completed = client.post(RESET_COMPLETE_PATH, json={"token": token, "newPassword": password})
    assert completed.status_code == status.HTTP_204_NO_CONTENT, completed.text


def stored_account(session: Session, address: str) -> UserAccount:
    """Return the committed account of an address, read afresh."""
    session.expire_all()
    return session.exec(select(UserAccount).where(col(UserAccount.email) == address)).one()


@pytest.mark.usefixtures("home_branch")
class TestACustomerWhoNeverVerified:
    """The reset proves the address, and every answer about the account says so."""

    def test_the_account_ends_verified_and_the_event_records_it(
        self,
        account_api: TestClient,
        session: Session,
        email_gateway: FakeEmailGateway,
        still_clock: FixedClock,
    ) -> None:
        account_api.post(REGISTER_PATH, json=registration_body())
        assert stored_account(session, NEW_EMAIL).email_verified_at is None
        account_api.post(RESET_REQUEST_PATH, json={"email": NEW_EMAIL})
        complete_reset(account_api, email_gateway, NEW_EMAIL, NEW_PASSWORD)

        # SQLite keeps the instant without its zone, which is UTC.
        verified_at = stored_account(session, NEW_EMAIL).email_verified_at
        assert verified_at == still_clock.now().replace(tzinfo=None)
        signed_in = sign_in(account_api, NEW_EMAIL, NEW_PASSWORD)
        assert signed_in.json()["user"]["emailVerified"] is True
        me = account_api.get(
            ME_PATH, headers=authorization_header(signed_in.json()["accessToken"])
        )
        assert me.json()["emailVerified"] is True
        (event,) = session.exec(
            select(AuditEvent).where(col(AuditEvent.action) == RESET_COMPLETED_ACTION)
        ).all()
        assert event.before_state is not None and event.after_state is not None
        assert (event.before_state["email_verified"], event.after_state["email_verified"]) == (
            False,
            True,
        )


class TestANewMemberOfStaff:
    """Opened unverified, and verified once the first password is chosen through the link."""

    @pytest.fixture
    def owner(self, session: Session, factory: Factory) -> UserAccount:
        factory.branch(code="CBD")
        account = factory.user(role=UserRole.ADMIN)
        session.commit()
        return account

    @pytest.fixture
    def people(
        self, session: Session, still_clock: FixedClock, email_gateway: FakeEmailGateway
    ) -> Iterator[BookingClient]:
        with people_client(session, still_clock, email_gateway) as client:
            yield client

    def test_the_first_password_proves_the_address(
        self,
        session: Session,
        people: BookingClient,
        owner: UserAccount,
        email_gateway: FakeEmailGateway,
    ) -> None:
        opened = created(open_user(people, owner, staff_body()))
        user = opened["user"]
        assert isinstance(user, dict)
        assert user["emailVerified"] is False

        complete_reset(people.client, email_gateway, STAFF_EMAIL, STAFF_PASSWORD)

        signed_in = sign_in(people.client, STAFF_EMAIL, STAFF_PASSWORD)
        assert signed_in.status_code == status.HTTP_200_OK, signed_in.text
        assert signed_in.json()["user"]["emailVerified"] is True
        items = answered(list_users(people, owner, role="COUNTER_STAFF"))["items"]
        assert isinstance(items, list)
        assert [(item["email"], item["emailVerified"]) for item in items] == [(STAFF_EMAIL, True)]
        assert stored_account(session, STAFF_EMAIL).email_verified_at is not None
