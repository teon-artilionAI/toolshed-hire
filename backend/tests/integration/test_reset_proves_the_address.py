"""Completing a password reset proves the address, in one transaction on PostgreSQL (BR-49).

The fast tests prove the rule. These prove the transaction. The new hash, the
cleared token, the lifted lock, the verified address and the audit event that
records all of them are committed together, and when that audit event cannot
be written, none of them is kept and the link still works afterwards.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.application.identity.password_reset import RESET_COMPLETED_ACTION
from app.domain.audit import AuditEvent as AuditRecord
from app.infrastructure.audit import SqlAuditLog
from app.infrastructure.models import AuditEvent, UserAccount
from app.infrastructure.notification import FakeEmailGateway
from app.infrastructure.security import verify_password
from tests.support.accounts_api import (
    CHOSEN_PASSWORD,
    NEW_EMAIL,
    NEW_PASSWORD,
    REGISTER_PATH,
    RESET_COMPLETE_PATH,
    RESET_KEY,
    RESET_REQUEST_PATH,
    account_client,
    registration_body,
    token_from,
)
from tests.support.clock import FixedClock
from tests.support.factories import Factory

pytestmark = [pytest.mark.postgres, pytest.mark.usefixtures("postgres_session")]


class AuditStoreDown(RuntimeError):
    """What the audit log raises in the test that makes the reset's event fail."""


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def gateway() -> FakeEmailGateway:
    return FakeEmailGateway()


@pytest.fixture
def api(
    postgres_session: Session,
    postgres_factory: Factory,
    clock: FixedClock,
    gateway: FakeEmailGateway,
) -> Iterator[TestClient]:
    """Yield the account routes once a customer has registered and asked for a reset link."""
    postgres_factory.branch(code="CBD")
    postgres_session.commit()
    with account_client(postgres_session, clock, gateway) as client:
        client.post(REGISTER_PATH, json=registration_body())
        client.post(RESET_REQUEST_PATH, json={"email": NEW_EMAIL})
        yield client


def stored(session: Session) -> UserAccount:
    """Return the committed account, read afresh."""
    session.expire_all()
    return session.exec(select(UserAccount).where(col(UserAccount.email) == NEW_EMAIL)).one()


def completion(gateway: FakeEmailGateway) -> dict[str, str]:
    """Return the body that uses the reset link the account was sent."""
    return {"token": token_from(gateway, NEW_EMAIL, RESET_KEY), "newPassword": NEW_PASSWORD}


def completed_events(session: Session) -> list[AuditEvent]:
    """Return every committed audit event of a completed reset."""
    session.expire_all()
    statement = select(AuditEvent).where(col(AuditEvent.action) == RESET_COMPLETED_ACTION)
    return list(session.exec(statement).all())


class TestTheResetAndTheVerificationAreOneCommit:
    """Everything the reset changes, with its event, or nothing."""

    def test_the_hash_the_token_the_verification_and_the_event_commit_together(
        self,
        api: TestClient,
        postgres_session: Session,
        gateway: FakeEmailGateway,
        clock: FixedClock,
    ) -> None:
        assert stored(postgres_session).email_verified_at is None
        response = api.post(RESET_COMPLETE_PATH, json=completion(gateway))
        assert response.status_code == status.HTTP_204_NO_CONTENT, response.text
        account = stored(postgres_session)
        assert account.email_verified_at == clock.now()
        assert account.password_reset_token_hash is None
        assert verify_password(NEW_PASSWORD, account.password_hash)
        (event,) = completed_events(postgres_session)
        assert event.before_state == {"locked": False, "email_verified": False}
        assert event.after_state is not None
        assert event.after_state["email_verified"] is True
        assert event.occurred_at == account.email_verified_at

    def test_when_the_event_cannot_be_written_nothing_is_kept_and_the_link_still_works(
        self,
        api: TestClient,
        postgres_session: Session,
        gateway: FakeEmailGateway,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        body = completion(gateway)
        original_record = SqlAuditLog.record

        def fail(self: SqlAuditLog, event: AuditRecord) -> None:
            raise AuditStoreDown("the audit log is not reachable")

        monkeypatch.setattr(SqlAuditLog, "record", fail)
        refused = api.post(RESET_COMPLETE_PATH, json=body)
        assert refused.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        account = stored(postgres_session)
        assert account.email_verified_at is None
        assert account.password_reset_token_hash is not None
        assert verify_password(CHOSEN_PASSWORD, account.password_hash)
        assert completed_events(postgres_session) == []

        monkeypatch.setattr(SqlAuditLog, "record", original_record)
        assert api.post(RESET_COMPLETE_PATH, json=body).status_code == status.HTTP_204_NO_CONTENT
        assert stored(postgres_session).email_verified_at is not None
