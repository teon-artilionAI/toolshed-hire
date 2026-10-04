"""The staff who served each branch in the season, and the two customer accounts.

The seed creates a counter assistant at Cape Town CBD and at Bellville, and
none at Somerset West, so the administrator served that counter. The two
customer accounts the seed creates hire now and then as well, through their
own profiles, so a customer who signs in sees a history of their own.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Final
from uuid import UUID

from sqlmodel import Session, col, select

from app.infrastructure.models import Branch, CustomerProfile, UserAccount
from seeding.errors import SeedDataError
from seeding.people import (
    ADMIN_EMAIL,
    BLV_COUNTER_EMAIL,
    CBD_COUNTER_EMAIL,
    INDIVIDUAL_CUSTOMER_EMAIL,
    TRADE_CUSTOMER_EMAIL,
)

STAFF_BY_BRANCH: Final[Mapping[str, str]] = MappingProxyType(
    {"CBD": CBD_COUNTER_EMAIL, "BLV": BLV_COUNTER_EMAIL, "SMW": ADMIN_EMAIL}
)
ACCOUNT_CUSTOMER_EMAILS: Final[tuple[str, ...]] = (
    TRADE_CUSTOMER_EMAIL,
    INDIVIDUAL_CUSTOMER_EMAIL,
)


@dataclass(frozen=True, slots=True)
class AccountCustomer:
    """One of the two seeded customer accounts, which hire now and then."""

    email: str
    account_id: UUID
    profile_id: UUID
    branch_code: str
    discount_percent: Decimal


@dataclass(frozen=True, slots=True)
class PeopleRead:
    """Who served each branch, and the customers with a login."""

    staff_by_branch: Mapping[str, UUID]
    account_customers: tuple[AccountCustomer, ...]


def read_people(session: Session) -> PeopleRead:
    """Return the member of staff who served each branch and the two customer accounts.

    Raises:
        SeedDataError: If an account or a customer profile the history names is
            not in the database, which means the people were not loaded first.

    """
    emails = [*STAFF_BY_BRANCH.values(), *ACCOUNT_CUSTOMER_EMAILS]
    accounts = {
        str(account.email).lower(): account
        for account in session.exec(
            select(UserAccount).where(col(UserAccount.email).in_(emails))
        ).all()
    }
    missing = sorted(email for email in emails if email not in accounts)
    if missing:
        raise SeedDataError(
            f"The trading history needs the accounts {missing}, which are not in the "
            "database. Load the people before the history."
        )
    staff = {code: accounts[email].id for code, email in STAFF_BY_BRANCH.items()}
    customers = tuple(
        _account_customer(session, accounts[email]) for email in ACCOUNT_CUSTOMER_EMAILS
    )
    return PeopleRead(staff_by_branch=staff, account_customers=customers)


def _account_customer(session: Session, account: UserAccount) -> AccountCustomer:
    """Return the hire profile of one customer account and the branch it registered at.

    Raises:
        SeedDataError: If the account has no customer profile.

    """
    found = session.exec(
        select(CustomerProfile, col(Branch.code))
        .join(Branch, col(Branch.id) == col(CustomerProfile.registered_branch_id))
        .where(col(CustomerProfile.user_account_id) == account.id)
    ).first()
    if found is None:
        raise SeedDataError(
            f"Account {account.email} has no customer profile, so the trading history cannot "
            "hire to it. Load the people before the history."
        )
    profile, branch_code = found
    return AccountCustomer(
        email=str(account.email).lower(),
        account_id=account.id,
        profile_id=profile.id,
        branch_code=branch_code,
        discount_percent=profile.trade_discount_percent,
    )
