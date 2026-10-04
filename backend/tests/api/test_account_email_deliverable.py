"""`emailDeliverable` on the signed in account, through HTTP and real SQL.

Signing in, refreshing and `GET /api/me` all return the account, and each says
whether this environment would hand a message for the account's address to the
email provider. The answer is the gateway's own rule for the address, the one
the account routes already give, so a gateway that delivers to one approved
inbox says true for that inbox and false for every other, and a gateway with
email switched off says false for everybody. Asking sends nothing.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from httpx import Response
from sqlmodel import Session

from app.api.deps import get_notification_gateway
from app.application.notification.ports import NotificationGateway
from app.domain.enums import UserRole
from app.infrastructure.models import UserAccount
from app.infrastructure.notification import FakeEmailGateway
from app.infrastructure.notification.gateways import UnconfiguredEmailGateway
from app.main import app as production_app
from tests.support.factories import Factory
from tests.support.sessions import ME_PATH, REFRESH_PATH, present, refresh_token_of, sign_in
from tests.support.tokens import authorization_header

APPROVED_EMAIL: Final[str] = "the.one.approved.inbox@example.co.za"
OTHER_EMAIL: Final[str] = "somebody.else@example.co.za"
DELIVERABLE_FIELD: Final[str] = "emailDeliverable"


class OneInboxGateway(FakeEmailGateway):
    """A fake that delivers to one approved inbox only, as a trial mail account does."""

    def __init__(self, approved: str) -> None:
        """Keep the one address mail may go to."""
        super().__init__()
        self._approved = approved.strip().lower()

    def delivers_to(self, address: str) -> bool:
        """Return True for the approved address and False for every other."""
        return address.strip().lower() == self._approved


@contextmanager
def answering_through(client: TestClient, gateway: NotificationGateway) -> Iterator[TestClient]:
    """Hand the application another gateway while the block runs, then put the earlier one back."""
    overrides = production_app.dependency_overrides
    earlier = overrides.get(get_notification_gateway)
    overrides[get_notification_gateway] = lambda: gateway
    try:
        yield client
    finally:
        overrides.pop(get_notification_gateway, None)
        if earlier is not None:
            overrides[get_notification_gateway] = earlier


def customer(session: Session, factory: Factory, email: str) -> UserAccount:
    """Commit an active customer account with this address."""
    account = factory.user(role=UserRole.CUSTOMER, email=email)
    session.commit()
    return account


def signed_in_user(response: Response) -> dict[str, object]:
    """Return the `user` member of a sign in or a refresh that succeeded."""
    assert response.status_code == status.HTTP_200_OK, response.text
    user = response.json()["user"]
    assert isinstance(user, dict)
    return user


def me(client: TestClient, response: Response) -> dict[str, object]:
    """Return `GET /api/me` read with the access token a sign in returned."""
    token = response.json()["accessToken"]
    answer = client.get(ME_PATH, headers=authorization_header(token))
    assert answer.status_code == status.HTTP_200_OK, answer.text
    body = answer.json()
    assert isinstance(body, dict)
    return body


class TestAGatewayThatDeliversToEverybody:
    """True on every response that carries the account."""

    def test_sign_in_refresh_and_me_all_say_true(
        self, auth_client: TestClient, session: Session, factory: Factory
    ) -> None:
        account = customer(session, factory, OTHER_EMAIL)
        signed_in = sign_in(auth_client, account.email)
        refreshed = present(auth_client, REFRESH_PATH, refresh_token_of(signed_in))
        assert signed_in_user(signed_in)[DELIVERABLE_FIELD] is True
        assert signed_in_user(refreshed)[DELIVERABLE_FIELD] is True
        assert me(auth_client, signed_in)[DELIVERABLE_FIELD] is True


class TestAGatewayThatDeliversToOneInbox:
    """True for the approved inbox and false for any other address."""

    @pytest.fixture
    def gateway(self) -> OneInboxGateway:
        return OneInboxGateway(APPROVED_EMAIL)

    def test_an_account_at_another_address_is_told_false_everywhere(
        self,
        auth_client: TestClient,
        session: Session,
        factory: Factory,
        gateway: OneInboxGateway,
    ) -> None:
        account = customer(session, factory, OTHER_EMAIL)
        with answering_through(auth_client, gateway) as client:
            signed_in = sign_in(client, account.email)
            refreshed = present(client, REFRESH_PATH, refresh_token_of(signed_in))
            assert signed_in_user(signed_in)[DELIVERABLE_FIELD] is False
            assert signed_in_user(refreshed)[DELIVERABLE_FIELD] is False
            assert me(client, signed_in)[DELIVERABLE_FIELD] is False
        assert gateway.sent == []

    def test_the_approved_inbox_is_told_true(
        self,
        auth_client: TestClient,
        session: Session,
        factory: Factory,
        gateway: OneInboxGateway,
    ) -> None:
        account = customer(session, factory, APPROVED_EMAIL)
        with answering_through(auth_client, gateway) as client:
            signed_in = sign_in(client, account.email)
            assert signed_in_user(signed_in)[DELIVERABLE_FIELD] is True
            assert me(client, signed_in)[DELIVERABLE_FIELD] is True


class TestEmailSwitchedOff:
    """False for everybody, staff included, and the rest of the account as it was."""

    def test_staff_and_customers_are_told_false(
        self, auth_client: TestClient, session: Session, factory: Factory
    ) -> None:
        account = customer(session, factory, OTHER_EMAIL)
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        with answering_through(auth_client, UnconfiguredEmailGateway()) as client:
            customer_user = signed_in_user(sign_in(client, account.email))
            admin_signed_in = sign_in(client, administrator.email)
            assert signed_in_user(admin_signed_in)[DELIVERABLE_FIELD] is False
            assert me(client, admin_signed_in)[DELIVERABLE_FIELD] is False
        assert customer_user == {
            "id": str(account.id),
            "email": OTHER_EMAIL,
            "fullName": account.full_name,
            "role": "customer",
            "branchCode": None,
            "emailVerified": False,
            "emailDeliverable": False,
        }
