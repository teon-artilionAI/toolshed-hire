"""`POST /api/auth/register` when it is accepted, through HTTP and real SQL (US-01, C-14).

I want this file to show what a person who registers gets, and what somebody
probing the route cannot learn. A new address is answered 202 and gets an
unverified customer account, an individual profile at the branch it chose and
one message with a verification link. Only the SHA-256 of the token in that
link is stored.

An address that already has an account is answered with the same bytes. No
second account is written, the first is left exactly as it was, and its holder
is sent a note that carries no token. Case does not make an address new, and
`emailDeliverable` depends on the gateway and the address alone.

The refusals and the throttles are in tests/api/test_register_refusals.py.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from httpx import Response
from sqlmodel import Session, SQLModel, col, select

from app.api.deps import get_notification_gateway
from app.application.identity.register import REGISTERED_ACTION
from app.application.notification.ports import NotificationGateway
from app.domain.account_tokens import EMAIL_VERIFICATION_LIFETIME
from app.domain.enums import AccountStatus, CustomerType, IdDocType, UserRole
from app.infrastructure.models import AuditEvent, Branch, CustomerProfile, UserAccount
from app.infrastructure.notification import FakeEmailGateway
from app.infrastructure.security import verify_password
from app.main import app as production_app
from tests.support.account_desk import token_in
from tests.support.accounts_api import (
    CHOSEN_PASSWORD,
    LOCAL_FRONTEND_ORIGIN,
    NEW_EMAIL,
    REGISTER_PATH,
    VERIFY_KEY,
    registration_body,
)
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.sessions import SHARED_REQUEST_ID

MIXED_CASE_EMAIL: Final[str] = "Thandi.Mokoena@Example.CO.ZA"
KNOWN_EMAIL: Final[str] = "already.a.customer@example.co.za"
APPROVED_EMAIL: Final[str] = "the.one.approved.inbox@example.co.za"
OTHER_PASSWORD: Final[str] = "a-different-made-up-passphrase"
BCRYPT_PREFIX: Final[str] = "$2b$"
TOKEN_ENCODING: Final[str] = "utf-8"
VERIFICATION_LINK_PREFIX: Final[str] = f"{LOCAL_FRONTEND_ORIGIN}/register#verify="
DELIVERABLE: Final[dict[str, bool]] = {"emailDeliverable": True}
NOT_DELIVERABLE: Final[dict[str, bool]] = {"emailDeliverable": False}
# The note to an address that already has an account carries no link with a token.
FRAGMENT_MARK: Final[str] = "#"


class _OneInboxGateway(FakeEmailGateway):
    """A fake that delivers to one approved inbox only, as a trial mail account does."""

    def __init__(self, approved: str) -> None:
        """Keep the one address mail may go to."""
        super().__init__()
        self._approved = approved.strip().lower()

    def delivers_to(self, address: str) -> bool:
        """Return True for the approved address and False for every other."""
        return address.strip().lower() == self._approved


@contextmanager
def _gateway_in_place(gateway: NotificationGateway) -> Iterator[None]:
    """Hand the application another gateway for a while, then put the earlier one back."""
    overrides = production_app.dependency_overrides
    earlier = overrides.get(get_notification_gateway)
    overrides[get_notification_gateway] = lambda: gateway
    try:
        yield
    finally:
        overrides.pop(get_notification_gateway, None)
        if earlier is not None:
            overrides[get_notification_gateway] = earlier


def _register(client: TestClient, **overrides: object) -> Response:
    """Post a registration that is accepted unless an override says otherwise."""
    body = registration_body(**overrides)
    return client.post(REGISTER_PATH, json=body, headers=SHARED_REQUEST_ID)


def _rows[Row: SQLModel](session: Session, model: type[Row]) -> list[Row]:
    """Return every row of one table as it is stored now."""
    return list(session.exec(select(model)).all())


def _columns(row: SQLModel) -> dict[str, object]:
    """Return every column of a row, read afresh."""
    return {name: getattr(row, name) for name in type(row).model_fields}


@pytest.mark.usefixtures("home_branch")
class TestANewAddress:
    """202, an unverified customer, a profile at the home branch and one link."""

    def test_it_is_answered_202_and_the_answer_is_never_stored(
        self, account_api: TestClient
    ) -> None:
        response = _register(account_api)
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.json() == DELIVERABLE
        assert response.headers["Cache-Control"] == "no-store"

    def test_the_account_is_an_active_unverified_customer_with_a_bcrypt_hash(
        self, account_api: TestClient, session: Session
    ) -> None:
        _register(account_api, email=MIXED_CASE_EMAIL)
        (account,) = _rows(session, UserAccount)
        assert account.email == NEW_EMAIL
        assert account.role == UserRole.CUSTOMER
        assert account.is_active
        assert account.email_verified_at is None
        assert account.phone == registration_body()["phone"]
        assert account.password_hash.startswith(BCRYPT_PREFIX)
        assert verify_password(CHOSEN_PASSWORD, account.password_hash)
        events = session.exec(
            select(AuditEvent).where(col(AuditEvent.action) == REGISTERED_ACTION)
        ).all()
        assert [event.entity_id for event in events] == [account.id]

    def test_the_profile_is_an_individual_in_good_standing_at_the_home_branch(
        self, account_api: TestClient, session: Session, home_branch: Branch
    ) -> None:
        _register(account_api)
        (account,) = _rows(session, UserAccount)
        (profile,) = _rows(session, CustomerProfile)
        sent = registration_body()
        assert profile.user_account_id == account.id
        assert profile.customer_type == CustomerType.INDIVIDUAL
        assert profile.account_status == AccountStatus.ACTIVE
        assert profile.trade_discount_percent == Decimal(0)
        assert profile.registered_branch_id == home_branch.id
        assert profile.display_name == sent["fullName"]
        assert profile.contact_phone == sent["phone"]
        assert profile.id_document_type == IdDocType.SA_ID
        assert profile.id_document_last4 == sent["idDocumentLast4"]
        assert profile.billing_address_line1 == sent["billingAddressLine1"]
        assert profile.billing_suburb == sent["billingSuburb"]
        assert profile.billing_city == sent["billingCity"]
        assert profile.billing_postal_code == sent["billingPostalCode"]

    def test_one_link_is_sent_and_only_the_sha256_of_its_token_is_stored(
        self,
        account_api: TestClient,
        session: Session,
        email_gateway: FakeEmailGateway,
        still_clock: FixedClock,
    ) -> None:
        _register(account_api)
        (message,) = email_gateway.sent
        assert message.to == NEW_EMAIL
        token = token_in(message, VERIFY_KEY)
        assert f"{VERIFICATION_LINK_PREFIX}{token}" in message.text_body
        (account,) = _rows(session, UserAccount)
        expected_hash = hashlib.sha256(token.encode(TOKEN_ENCODING)).hexdigest()
        assert account.email_verification_token_hash == expected_hash
        assert token not in str(_columns(account))
        assert account.email_verification_expires_at is not None
        expires_at = account.email_verification_expires_at.replace(tzinfo=None)
        assert expires_at == (still_clock.now() + EMAIL_VERIFICATION_LIFETIME).replace(tzinfo=None)


@pytest.mark.usefixtures("home_branch")
class TestAnAddressThatHasAnAccount:
    """The same bytes, nothing written or changed, and a note with no token (C-14)."""

    def test_a_second_registration_answers_the_same_and_changes_nothing(
        self, account_api: TestClient, session: Session, email_gateway: FakeEmailGateway
    ) -> None:
        first = _register(account_api)
        (account,) = _rows(session, UserAccount)
        (profile,) = _rows(session, CustomerProfile)
        account_before, profile_before = _columns(account), _columns(profile)
        second = _register(
            account_api, password=OTHER_PASSWORD, fullName="Somebody Else", phone="021 555 0199"
        )
        assert second.status_code == first.status_code == status.HTTP_202_ACCEPTED
        assert second.content == first.content
        (account_after,) = _rows(session, UserAccount)
        (profile_after,) = _rows(session, CustomerProfile)
        assert _columns(account_after) == account_before
        assert _columns(profile_after) == profile_before
        notes = email_gateway.sent_to(NEW_EMAIL)
        assert len(notes) == 2
        assert FRAGMENT_MARK not in notes[-1].text_body

    def test_an_address_is_kept_in_lower_case_and_case_does_not_make_it_new(
        self, account_api: TestClient, session: Session, email_gateway: FakeEmailGateway
    ) -> None:
        first = _register(account_api, email=MIXED_CASE_EMAIL)
        repeat = _register(account_api, email=NEW_EMAIL)
        assert repeat.status_code == status.HTTP_202_ACCEPTED
        assert repeat.content == first.content
        assert [account.email for account in _rows(session, UserAccount)] == [NEW_EMAIL]
        assert len(_rows(session, CustomerProfile)) == 1
        notes = email_gateway.sent_to(NEW_EMAIL)
        assert len(notes) == 2
        assert FRAGMENT_MARK not in notes[-1].text_body


@pytest.mark.usefixtures("home_branch")
class TestEmailDeliverable:
    """It depends on the gateway and the address, never on whether an account exists."""

    def test_it_is_false_for_an_address_the_gateway_would_not_deliver_to_known_or_not(
        self, account_api: TestClient, session: Session, factory: Factory
    ) -> None:
        factory.user(email=KNOWN_EMAIL)
        session.commit()
        with _gateway_in_place(_OneInboxGateway(APPROVED_EMAIL)):
            unknown = _register(account_api)
            known = _register(account_api, email=KNOWN_EMAIL)
            approved = _register(account_api, email=APPROVED_EMAIL)
        assert unknown.status_code == known.status_code == status.HTTP_202_ACCEPTED
        assert unknown.json() == NOT_DELIVERABLE
        assert known.content == unknown.content
        assert approved.json() == DELIVERABLE
