"""The seed can give customers a different password from staff.

A demonstration customer login is meant to be published, and the counter staff
and admin logins are not. These tests seed an empty database with two
passwords and check which account opens with which, and that leaving the
customer password out keeps every account on the one password as before.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Final

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, select

from app.domain.enums import UserRole
from app.infrastructure.models import UserAccount
from app.infrastructure.security import verify_password
from seeding import seed_database
from tests.support.pg import truncate_schema_tables

pytestmark = pytest.mark.postgres

STAFF_PASSWORD: Final[str] = "made-up-staff-password-for-this-test"
CUSTOMER_PASSWORD: Final[str] = "made-up-customer-password-for-this-test"


@pytest.fixture
def empty_database(postgres_engine: Engine) -> Iterator[Engine]:
    """Hand over an empty database and empty it again afterwards."""
    truncate_schema_tables(postgres_engine)
    try:
        yield postgres_engine
    finally:
        truncate_schema_tables(postgres_engine)


def _accounts(engine: Engine) -> list[UserAccount]:
    with Session(engine) as session:
        return list(session.exec(select(UserAccount)).all())


def test_customers_and_staff_get_different_passwords_when_both_are_given(
    empty_database: Engine,
) -> None:
    with Session(empty_database) as session:
        seed_database(session, STAFF_PASSWORD, CUSTOMER_PASSWORD)
        session.commit()

    accounts = _accounts(empty_database)
    customers = [account for account in accounts if account.role is UserRole.CUSTOMER]
    staff = [account for account in accounts if account.role is not UserRole.CUSTOMER]

    assert customers and staff
    for account in customers:
        assert verify_password(CUSTOMER_PASSWORD, account.password_hash)
        assert not verify_password(STAFF_PASSWORD, account.password_hash)
    for account in staff:
        assert verify_password(STAFF_PASSWORD, account.password_hash)
        assert not verify_password(CUSTOMER_PASSWORD, account.password_hash)


def test_every_account_shares_one_password_when_no_customer_password_is_given(
    empty_database: Engine,
) -> None:
    with Session(empty_database) as session:
        seed_database(session, STAFF_PASSWORD)
        session.commit()

    accounts = _accounts(empty_database)

    assert accounts
    for account in accounts:
        assert verify_password(STAFF_PASSWORD, account.password_hash)
