"""The account repositories and the lockout window on real PostgreSQL, as the application role.

The running API connects as `toolshed_app`, which may read, insert and update
and may delete only an old throttle window. These prove that the writes of
registration and the reads behind the lockout window work within those grants.

Two registrations that race for one address are told apart by the unique
constraint on the address, which the repository recognises by its SQLSTATE and
its name. The name is the one PostgreSQL gave the constraint, so this is where
a migration that renamed it would be caught.

The lockout window adds up one counter for each second a failure fell in, in
`timestamptz`, and the profile edit locks two rows with `FOR UPDATE OF`. Both
are proved here because SQLite has neither.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Final

import pytest
from fastapi import status
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.application.identity.ports import EmailAlreadyRegistered
from app.application.identity.sign_in import LOGIN_FAILURES
from app.application.throttle import Throttle
from app.domain.account import (
    FAILED_LOGIN_WINDOW,
    LOCKOUT_DURATION,
    MAXIMUM_FAILED_LOGINS,
    Account,
)
from app.domain.customer_account import NewCustomer
from app.domain.enums import IdDocType
from app.infrastructure.identity_accounts import SqlAccountRepository
from app.infrastructure.models import Branch, UserAccount
from app.infrastructure.rate_limit import SqlRateLimitStore
from app.infrastructure.schema_ddl import ACCOUNT_EMAIL_CONSTRAINT_NAME
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.roles import (
    APPLICATION_ROLE,
    APPLICATION_ROLE_PASSWORD,
    engine_as,
    provision_restricted_roles,
)
from tests.support.sessions import WRONG_PASSWORD, session_client, sign_in, without_bcrypt

pytestmark = [pytest.mark.postgres, pytest.mark.usefixtures("postgres_session")]

NEW_EMAIL: Final[str] = "thandi.mokoena@example.co.za"
SALT: Final[str] = "made-up-salt-for-this-test"
SUBJECT: Final[str] = "an-account-key"
FOUR_MINUTES: Final[timedelta] = timedelta(minutes=4)


@pytest.fixture(scope="module")
def application_engine(postgres_engine: Engine, postgres_url: str) -> Iterator[Engine]:
    """Yield an engine signed in as the restricted application role."""
    provision_restricted_roles(postgres_engine, postgres_url)
    engine = engine_as(postgres_url, APPLICATION_ROLE, APPLICATION_ROLE_PASSWORD)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def branch(postgres_session: Session, postgres_factory: Factory) -> Branch:
    branch = postgres_factory.branch(code="CBD")
    postgres_session.commit()
    return branch


def new_account(email: str = NEW_EMAIL) -> Account:
    return Account.registered_customer(
        email=email,
        password_hash="stand-in-hash-not-a-real-one",
        full_name="Thandi Mokoena",
        phone="082 441 7719",
    )


def new_customer() -> NewCustomer:
    return NewCustomer.registering(
        full_name="Thandi Mokoena",
        phone="082 441 7719",
        id_document_type=IdDocType.SA_ID,
        id_document_last4="5083",
        billing_address_line1="12 Loop Street",
        billing_suburb="Gardens",
        billing_city="Cape Town",
        billing_postal_code="8001",
    )


class TestWithinTheGrantsOfTheApplicationRole:
    """Registration and an edit, written as `toolshed_app`."""

    def test_the_application_role_can_register_and_edit_a_customer(
        self, application_engine: Engine, branch: Branch
    ) -> None:
        account = new_account()
        with SqlAlchemyUnitOfWork(lambda: Session(application_engine)) as uow:
            uow.accounts.add(account)
            uow.customers.add_registered(
                user_account_id=account.id, registered_branch_id=branch.id, customer=new_customer()
            )
            uow.commit()
        with SqlAlchemyUnitOfWork(lambda: Session(application_engine)) as uow:
            details = uow.customers.details_for_account(account.id, for_update=True)
            assert details is not None
            assert details.apply({"billing_city": "Stellenbosch", "full_name": "Thandi M"})
            uow.customers.save_details(details)
            uow.commit()
        with SqlAlchemyUnitOfWork(lambda: Session(application_engine)) as uow:
            stored = uow.customers.details_for_account(account.id)
        assert stored is not None
        assert (stored.billing_city, stored.full_name, stored.home_branch_code) == (
            "Stellenbosch",
            "Thandi M",
            "CBD",
        )

    def test_the_application_role_can_add_up_a_sliding_window(
        self, application_engine: Engine
    ) -> None:
        clock = FixedClock()
        with Session(application_engine) as session:
            store = SqlRateLimitStore(session)
            throttle = Throttle(SALT)
            counts = []
            for _ in range(3):
                counts.append(throttle.count_in_span(store, LOGIN_FAILURES, SUBJECT, clock.now()))
                clock.advance(FOUR_MINUTES)
            clock.advance(FOUR_MINUTES)
            counts.append(throttle.count_in_span(store, LOGIN_FAILURES, SUBJECT, clock.now()))
            session.commit()
        assert counts == [1, 2, 3, 3]


class TestARaceForOneAddress:
    """The unique constraint on the address is recognised by its code and its name."""

    def test_the_second_insert_of_an_address_is_told_it_was_taken(
        self, postgres_engine: Engine
    ) -> None:
        with Session(postgres_engine) as session:
            SqlAccountRepository(session).add(new_account())
            session.commit()
        with Session(postgres_engine) as session, pytest.raises(EmailAlreadyRegistered) as lost:
            SqlAccountRepository(session).add(new_account(NEW_EMAIL.upper()))
        cause = lost.value.__cause__
        assert cause is not None
        diagnostics = getattr(getattr(cause, "orig", None), "diag", None)
        assert getattr(diagnostics, "constraint_name", None) == ACCOUNT_EMAIL_CONSTRAINT_NAME

    def test_any_other_integrity_fault_is_raised_unchanged(self, postgres_engine: Engine) -> None:
        account = new_account()
        with Session(postgres_engine) as session:
            SqlAccountRepository(session).add(account)
            session.commit()
        twin = new_account("someone.else@example.co.za")
        twin.id = account.id
        with Session(postgres_engine) as session, pytest.raises(IntegrityError):
            SqlAccountRepository(session).add(twin)


class TestTheLockoutWindowOverHttp:
    """Five failures inside fifteen minutes lock the account, and five spread wider do not."""

    @pytest.fixture
    def customer(self, postgres_session: Session, postgres_factory: Factory) -> UserAccount:
        account = postgres_factory.user()
        postgres_session.commit()
        return account

    def test_failures_four_minutes_apart_never_lock_and_five_together_do(
        self, postgres_session: Session, customer: UserAccount
    ) -> None:
        clock = FixedClock()
        with session_client(postgres_session, clock) as api, without_bcrypt():
            for _ in range(MAXIMUM_FAILED_LOGINS):
                assert sign_in(api, customer.email, WRONG_PASSWORD).status_code == 401
                clock.advance(FOUR_MINUTES)
            postgres_session.expire_all()
            spread = postgres_session.exec(select(UserAccount)).one()
            assert spread.locked_until is None
            assert spread.failed_login_count == MAXIMUM_FAILED_LOGINS - 1
            clock.advance(FAILED_LOGIN_WINDOW)
            for _ in range(MAXIMUM_FAILED_LOGINS):
                sign_in(api, customer.email, WRONG_PASSWORD)
        postgres_session.expire_all()
        locked = postgres_session.exec(select(UserAccount)).one()
        assert locked.locked_until == clock.now() + LOCKOUT_DURATION
        assert locked.failed_login_count == MAXIMUM_FAILED_LOGINS

    def test_the_right_password_is_refused_while_the_lock_runs(
        self, postgres_session: Session, customer: UserAccount
    ) -> None:
        clock = FixedClock()
        with session_client(postgres_session, clock) as api:
            with without_bcrypt():
                for _ in range(MAXIMUM_FAILED_LOGINS):
                    sign_in(api, customer.email, WRONG_PASSWORD)
            refused = sign_in(api, customer.email)
        assert refused.status_code == status.HTTP_401_UNAUTHORIZED

