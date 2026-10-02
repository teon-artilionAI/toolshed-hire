"""Registration, the two account links and the profile, on real PostgreSQL (FR-01, C-18).

The fast tests prove the rules on SQLite. These prove what only PostgreSQL can.

The account and the profile are one transaction. When the audit event that
belongs to them cannot be written, neither row is there afterwards.

The token columns hold the SHA-256 of a token and never the token. The token
is read out of the message the fake gateway was handed, which is the only
place it ever exists, and no column of the account row holds it.

Each step writes its audit event, with the request id, the client address and
the role, in the native types the schema gives them.

The profile edit locks the profile and the account with `FOR UPDATE OF`, which
SQLite does not have.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session, col, select

from app.domain.enums import AccountStatus, CustomerType, UserRole
from app.infrastructure.audit import SqlAuditLog
from app.infrastructure.models import AuditEvent, Branch, CustomerProfile, UserAccount
from app.infrastructure.notification import FakeEmailGateway
from tests.support.account_desk import token_in
from tests.support.accounts_api import (
    CHOSEN_PASSWORD,
    NEW_EMAIL,
    NEW_PASSWORD,
    PROFILE_PATH,
    REGISTER_PATH,
    RESET_COMPLETE_PATH,
    RESET_KEY,
    RESET_REQUEST_PATH,
    VERIFY_KEY,
    VERIFY_PATH,
    account_client,
    registration_body,
    token_from,
)
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.sessions import sign_in
from tests.support.tokens import authorization_header

pytestmark = [pytest.mark.postgres, pytest.mark.usefixtures("postgres_session")]

CLIENT_ADDRESS: Final[str] = "203.0.113.9"
TOKEN_COLUMNS: Final[tuple[str, ...]] = (
    "email_verification_token_hash",
    "password_reset_token_hash",
)


class AuditStoreDown(RuntimeError):
    """What the audit log raises in the test that makes it fail."""


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def gateway() -> FakeEmailGateway:
    return FakeEmailGateway()


@pytest.fixture
def branch(postgres_session: Session, postgres_factory: Factory) -> Branch:
    branch = postgres_factory.branch(code="CBD")
    postgres_session.commit()
    return branch


@pytest.fixture
def api(
    postgres_session: Session, clock: FixedClock, gateway: FakeEmailGateway, branch: Branch
) -> Iterator[TestClient]:
    with account_client(
        postgres_session, clock, gateway, client_address=CLIENT_ADDRESS
    ) as client:
        yield client


def sha256(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def account_row(session: Session) -> UserAccount:
    session.expire_all()
    return session.exec(select(UserAccount).where(col(UserAccount.email) == NEW_EMAIL)).one()


def events(session: Session, action: str) -> list[AuditEvent]:
    session.expire_all()
    statement = (
        select(AuditEvent).where(col(AuditEvent.action) == action).order_by(col(AuditEvent.id))
    )
    return list(session.exec(statement).all())


def every_text_value_of(session: Session, account: UserAccount) -> str:
    """Return every column of the account row as text, joined together."""
    row = session.execute(
        text("SELECT row_to_json(user_account)::text FROM user_account WHERE id = :id"),
        {"id": account.id},
    ).scalar_one()
    return str(row)


class TestTheRegistrationTransaction:
    """The account and the profile together, or neither."""

    def test_the_account_and_the_profile_are_written_as_the_schema_types_them(
        self, api: TestClient, postgres_session: Session, branch: Branch
    ) -> None:
        body = registration_body(email="Thandi.Mokoena@Example.co.za")
        response = api.post(REGISTER_PATH, json=body)
        assert response.status_code == status.HTTP_202_ACCEPTED
        account = account_row(postgres_session)
        profile = postgres_session.exec(
            select(CustomerProfile).where(col(CustomerProfile.user_account_id) == account.id)
        ).one()
        assert (account.email, account.role, account.email_verified_at) == (
            NEW_EMAIL,
            UserRole.CUSTOMER,
            None,
        )
        assert account.password_hash.startswith("$2b$12$")
        assert (profile.customer_type, profile.account_status) == (
            CustomerType.INDIVIDUAL,
            AccountStatus.ACTIVE,
        )
        assert profile.registered_branch_id == branch.id
        assert profile.trade_discount_percent == 0
        assert account.created_at is not None and account.created_at.tzinfo is not None

    def test_when_the_audit_event_cannot_be_written_neither_row_is_kept(
        self, api: TestClient, postgres_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail(self: SqlAuditLog, event: object) -> None:
            raise AuditStoreDown("the audit log is not reachable")

        monkeypatch.setattr(SqlAuditLog, "record", fail)
        response = api.post(REGISTER_PATH, json=registration_body())
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        postgres_session.expire_all()
        assert postgres_session.exec(select(UserAccount)).all() == []
        assert postgres_session.exec(select(CustomerProfile)).all() == []

    def test_a_second_registration_of_the_address_writes_nothing_new(
        self, api: TestClient, postgres_session: Session, gateway: FakeEmailGateway
    ) -> None:
        first = api.post(REGISTER_PATH, json=registration_body())
        second = api.post(REGISTER_PATH, json=registration_body(email=NEW_EMAIL.upper()))
        assert first.json() == second.json()
        assert len(postgres_session.exec(select(UserAccount)).all()) == 1
        assert len(postgres_session.exec(select(CustomerProfile)).all()) == 1
        assert len(gateway.sent_to(NEW_EMAIL)) == 2


class TestTheTokenColumnsHoldOnlyHashes:
    """The SHA-256 of each token, cleared once the token is used."""

    def test_the_verification_token_is_stored_as_its_hash_and_cleared_when_used(
        self, api: TestClient, postgres_session: Session, gateway: FakeEmailGateway
    ) -> None:
        api.post(REGISTER_PATH, json=registration_body())
        token = token_from(gateway, NEW_EMAIL, VERIFY_KEY)
        account = account_row(postgres_session)
        assert account.email_verification_token_hash == sha256(token)
        assert token not in every_text_value_of(postgres_session, account)
        assert api.post(VERIFY_PATH, json={"token": token}).status_code == 204
        verified = account_row(postgres_session)
        assert verified.email_verification_token_hash is None
        assert verified.email_verification_expires_at is None
        assert verified.email_verified_at == FixedClock().now()

    def test_the_reset_token_is_stored_as_its_hash_and_cleared_when_used(
        self, api: TestClient, postgres_session: Session, gateway: FakeEmailGateway
    ) -> None:
        api.post(REGISTER_PATH, json=registration_body())
        api.post(RESET_REQUEST_PATH, json={"email": NEW_EMAIL})
        token = token_from(gateway, NEW_EMAIL, RESET_KEY)
        account = account_row(postgres_session)
        assert account.password_reset_token_hash == sha256(token)
        assert token not in every_text_value_of(postgres_session, account)
        completion = {"token": token, "newPassword": NEW_PASSWORD}
        completed = api.post(RESET_COMPLETE_PATH, json=completion)
        assert completed.status_code == status.HTTP_204_NO_CONTENT
        reset = account_row(postgres_session)
        assert (reset.password_reset_token_hash, reset.password_reset_expires_at) == (None, None)
        assert sign_in(api, NEW_EMAIL, NEW_PASSWORD).status_code == status.HTTP_200_OK

    def test_no_two_accounts_can_hold_one_token_hash(
        self, api: TestClient, postgres_session: Session, gateway: FakeEmailGateway
    ) -> None:
        api.post(REGISTER_PATH, json=registration_body())
        api.post(REGISTER_PATH, json=registration_body(email="sipho.ndlovu@example.co.za"))
        tokens = [
            token_in(message, VERIFY_KEY)
            for message in gateway.sent
            if "#verify=" in message.text_body
        ]
        assert len(set(tokens)) == 2
        for column in TOKEN_COLUMNS:
            indexed = postgres_session.execute(
                text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
                {"name": f"ux_user_account_{column}"},
            ).scalar_one()
            assert "UNIQUE" in indexed


class TestTheAuditTrail:
    """One event for each step, with the request id, the address and the role."""

    def test_every_step_writes_its_event(
        self, api: TestClient, postgres_session: Session, gateway: FakeEmailGateway
    ) -> None:
        api.post(REGISTER_PATH, json=registration_body())
        api.post(VERIFY_PATH, json={"token": token_from(gateway, NEW_EMAIL, VERIFY_KEY)})
        access = sign_in(api, NEW_EMAIL, CHOSEN_PASSWORD).json()["accessToken"]
        api.patch(
            PROFILE_PATH, json={"billingCity": "Stellenbosch"}, headers=authorization_header(access)
        )
        api.post(RESET_REQUEST_PATH, json={"email": NEW_EMAIL})
        token = token_from(gateway, NEW_EMAIL, RESET_KEY)
        api.post(RESET_COMPLETE_PATH, json={"token": token, "newPassword": NEW_PASSWORD})
        account = account_row(postgres_session)
        for action in (
            "auth.registered",
            "auth.email_verified",
            "customer.profile_updated",
            "auth.password_reset_requested",
            "auth.password_reset_completed",
        ):
            (event,) = events(postgres_session, action)
            assert event.request_id is not None
            assert str(event.ip_address) == CLIENT_ADDRESS
            assert event.occurred_at.tzinfo is not None
            if action != "auth.password_reset_requested":
                assert event.actor_user_id == account.id
                assert event.actor_role is UserRole.CUSTOMER
        (edit,) = events(postgres_session, "customer.profile_updated")
        assert edit.after_state == {"changed_fields": ["billing_city"]}
        (completed,) = events(postgres_session, "auth.password_reset_completed")
        assert completed.after_state is not None
        assert completed.after_state["revoke_reason"] == "LOGOUT"
        assert completed.after_state["revoked_session_count"] == 1
