"""Load the sign in accounts and the customer profiles.

Every account is created active and with its email address already verified,
so it can sign in straight after the load. An account that already exists is
left alone, password included. Resetting a password on every run would make a
second run a change, and on a live database it would undo a password somebody
had since chosen.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Final

from sqlmodel import Session, col, select

from app.config import settings
from app.infrastructure.models import Branch, CustomerProfile, UserAccount
from app.infrastructure.security import hash_password
from seeding.errors import SeedDataError
from seeding.people import ACCOUNTS, CUSTOMER_PROFILES, AccountSeed, CustomerProfileSeed
from seeding.report import SeedTally

logger = logging.getLogger("seed")

SEED_PASSWORD_VARIABLE: Final[str] = "SEED_PASSWORD"
DEVELOPMENT_SEED_PASSWORD: Final[str] = "toolshed-dev-password"
ACCOUNT_KIND = "user_account"
CUSTOMER_PROFILE_KIND = "customer_profile"


def resolve_seed_password() -> str:
    """Return the password to seed, refusing a default outside development and test.

    Raises:
        RuntimeError: If SEED_PASSWORD is unset in an environment that is
            neither development nor test.

    """
    supplied = os.environ.get(SEED_PASSWORD_VARIABLE)
    if supplied:
        return supplied
    if not settings.environment.is_relaxed:
        raise RuntimeError(
            f"Attempted to seed environment {settings.environment.value!r} without "
            f"{SEED_PASSWORD_VARIABLE}. Set it to the password the seeded accounts should "
            "carry. The development default is never used outside development and test."
        )
    logger.warning(
        "seed.using_development_password",
        extra={"variable": SEED_PASSWORD_VARIABLE, "environment": settings.environment.value},
    )
    return DEVELOPMENT_SEED_PASSWORD


def load_accounts(
    session: Session, branches: dict[str, Branch], password: str, tally: SeedTally
) -> dict[str, UserAccount]:
    """Insert the accounts that are missing and return all of them by email address.

    The password is hashed once and only when at least one account has to be
    created, because a bcrypt hash is slow by design and a second run needs none.

    Raises:
        SeedDataError: If an account names a branch that is not in the data.
        ValidationFailure: If the password breaks the password policy.

    """
    emails = [seed.email for seed in ACCOUNTS]
    statement = select(UserAccount).where(col(UserAccount.email).in_(emails))
    by_email = {account.email.lower(): account for account in session.exec(statement).all()}
    missing = [seed for seed in ACCOUNTS if seed.email not in by_email]
    if missing:
        password_hash = hash_password(password)
        verified_at = datetime.now(UTC)
        for seed in missing:
            account = _account_from(seed, branches, password_hash, verified_at)
            session.add(account)
            by_email[seed.email] = account
            logger.info("seed.user_created", extra={"email": seed.email, "role": seed.role.value})
        session.flush()
    tally.record(ACCOUNT_KIND, created=len(missing), found=len(ACCOUNTS) - len(missing))
    return {seed.email: by_email[seed.email] for seed in ACCOUNTS}


def load_customer_profiles(
    session: Session,
    branches: dict[str, Branch],
    accounts: dict[str, UserAccount],
    tally: SeedTally,
) -> dict[str, CustomerProfile]:
    """Insert the customer profiles that are missing and return all by email address.

    Raises:
        SeedDataError: If a profile names an account or a branch that is not in
            the data.

    """
    for seed in CUSTOMER_PROFILES:
        if seed.email not in accounts:
            raise SeedDataError(
                f"Customer profile for {seed.email} has no account in the seed data. Every "
                "seeded profile belongs to a seeded account."
            )
    email_by_account_id = {accounts[seed.email].id: seed.email for seed in CUSTOMER_PROFILES}
    statement = select(CustomerProfile).where(
        col(CustomerProfile.user_account_id).in_(list(email_by_account_id))
    )
    by_email: dict[str, CustomerProfile] = {}
    for profile in session.exec(statement).all():
        if profile.user_account_id is not None:
            by_email[email_by_account_id[profile.user_account_id]] = profile
    created = 0
    for seed in CUSTOMER_PROFILES:
        if seed.email in by_email:
            logger.debug("seed.customer_profile_found", extra={"email": seed.email})
            continue
        profile = _profile_from(seed, accounts[seed.email], branches)
        session.add(profile)
        by_email[seed.email] = profile
        created += 1
        logger.info(
            "seed.customer_profile_created",
            extra={"email": seed.email, "customer_type": seed.customer_type.value},
        )
    session.flush()
    tally.record(
        CUSTOMER_PROFILE_KIND, created=created, found=len(CUSTOMER_PROFILES) - created
    )
    return {seed.email: by_email[seed.email] for seed in CUSTOMER_PROFILES}


def _branch_for(code: str, branches: dict[str, Branch], owner: str) -> Branch:
    """Return the branch a seeded person names, or say which person named a bad one."""
    branch = branches.get(code)
    if branch is None:
        raise SeedDataError(
            f"{owner} names branch {code!r}, which is not in the seed data. The known "
            f"branches are {sorted(branches)}."
        )
    return branch


def _account_from(
    seed: AccountSeed, branches: dict[str, Branch], password_hash: str, verified_at: datetime
) -> UserAccount:
    """Build the row for one account, active and already verified."""
    branch_id = None
    if seed.branch_code is not None:
        branch_id = _branch_for(seed.branch_code, branches, f"Account {seed.email}").id
    return UserAccount(
        email=seed.email,
        password_hash=password_hash,
        role=seed.role,
        full_name=seed.full_name,
        phone=seed.phone,
        branch_id=branch_id,
        is_active=True,
        email_verified_at=verified_at,
    )


def _profile_from(
    seed: CustomerProfileSeed, account: UserAccount, branches: dict[str, Branch]
) -> CustomerProfile:
    """Build the hire profile of one customer account."""
    branch = _branch_for(
        seed.registered_branch_code, branches, f"Customer profile for {seed.email}"
    )
    return CustomerProfile(
        user_account_id=account.id,
        customer_type=seed.customer_type,
        display_name=seed.display_name,
        company_name=seed.company_name,
        vat_number=seed.vat_number,
        id_document_type=seed.id_document_type,
        id_document_last4=seed.id_document_last4,
        contact_phone=seed.contact_phone,
        billing_address_line1=seed.billing_address_line1,
        billing_suburb=seed.billing_suburb,
        billing_city=seed.billing_city,
        billing_postal_code=seed.billing_postal_code,
        registered_branch_id=branch.id,
    )
