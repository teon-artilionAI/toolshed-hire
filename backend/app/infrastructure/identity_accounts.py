"""The SQL side of the sign in account, and the adapters for its cryptography.

The repository maps the `user_account` rows to the domain entity and back, on
the session of the unit of work that created it. The three adapters put bcrypt
and the token signer behind the ports the use cases ask for. The refresh
sessions are in `identity_sessions.py`.

Four reads take a row lock. A sign in locks the account it is checking, so two
attempts cannot both read the same failure count. A verification link and a
reset link each lock the account that holds the token, so of two requests
presenting one token the second finds it already used. The lock is released
when the transaction ends.

A token is looked up by its SHA-256, through the partial unique index on the
column, and the token itself is never stored.

A registration that loses a race for an address is told so. The violation is
recognised by SQLSTATE `23505` together with the name of the constraint, both
read from the diagnostics of the driver and never from the message. Any other
integrity fault is raised unchanged.

A timestamp read back from a database with no time zone type arrives without
one. Every instant is stored in UTC, so a value without a zone is given UTC.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.application.identity.ports import EmailAlreadyRegistered, IssuedAccessToken
from app.domain import account as account_domain
from app.domain.account_tokens import PendingToken
from app.infrastructure.booking_mapping import in_utc
from app.infrastructure.models import UserAccount
from app.infrastructure.schema_ddl import ACCOUNT_EMAIL_CONSTRAINT_NAME
from app.infrastructure.security import create_access_token, hash_password, verify_password

logger = logging.getLogger(__name__)

# PostgreSQL unique_violation.
UNIQUE_VIOLATION_SQLSTATE: Final[str] = "23505"

# What a password is compared against when there is no account to check, so a
# refusal for an unknown address costs one bcrypt verification like any other.
_TIMING_EQUALISER_HASH = hash_password("not-a-real-password-timing-equaliser")


class SqlAccountRepository:
    """Reads and writes sign in accounts through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session

    def find_by_email_for_update(self, email: str) -> account_domain.Account | None:
        """Return the account with this address, locked for the rest of the transaction."""
        return self._find_locked(col(UserAccount.email) == email, "email")

    def find_by_email_verification_hash_for_update(
        self, token_hash: str
    ) -> account_domain.Account | None:
        """Return the account holding this verification token hash, locked, or None."""
        return self._find_locked(
            col(UserAccount.email_verification_token_hash) == token_hash, "verification-link"
        )

    def find_by_password_reset_hash_for_update(
        self, token_hash: str
    ) -> account_domain.Account | None:
        """Return the account holding this reset token hash, locked, or None."""
        return self._find_locked(
            col(UserAccount.password_reset_token_hash) == token_hash, "reset-link"
        )

    def get_for_update(self, account_id: UUID) -> account_domain.Account | None:
        """Return the account with this key, locked for the rest of the transaction."""
        return self._find_locked(col(UserAccount.id) == account_id, "key")

    def get(self, account_id: UUID) -> account_domain.Account | None:
        """Return the account with this key as it is stored now, or None."""
        statement = (
            select(UserAccount)
            .where(col(UserAccount.id) == account_id)
            .execution_options(populate_existing=True)
        )
        row = self._session.exec(statement).first()
        logger.debug(
            "identity.account_read",
            extra={"user_id": str(account_id), "found": row is not None},
        )
        return _account_of(row) if row is not None else None

    def add(self, account: account_domain.Account) -> None:
        """Write a new account inside the current transaction.

        Raises:
            EmailAlreadyRegistered: If the unique constraint on the address
                refused the row, because another transaction took the address.
            IntegrityError: Unchanged, for every other integrity fault.

        """
        row = UserAccount(
            id=account.id,
            email=account.email,
            password_hash=account.password_hash,
            role=account.role,
            full_name=account.full_name,
            phone=account.phone,
            branch_id=account.branch_id,
            is_active=account.is_active,
        )
        _write_security_state(row, account)
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as error:
            if is_duplicate_email(error):
                logger.warning("identity.account_address_taken")
                raise EmailAlreadyRegistered from error
            logger.error(
                "identity.account_insert_failed",
                extra={"sqlstate": _sqlstate_of(error), "attempted": "insert a user_account row"},
            )
            raise
        logger.info("identity.account_added", extra={"user_id": str(account.id)})

    def save_login_state(self, account: account_domain.Account) -> None:
        """Write the failure count, the lock and the last sign in of an account.

        Raises:
            RuntimeError: If the account has no row, which would mean a use
                case is saving an account it never loaded.

        """
        row = self._loaded(account.id)
        row.failed_login_count = account.failed_login_count
        row.locked_until = account.locked_until
        row.last_login_at = account.last_login_at
        self._session.add(row)
        self._session.flush()
        logger.debug(
            "identity.account_login_state_saved",
            extra={
                "user_id": str(account.id),
                "failed_login_count": account.failed_login_count,
                "locked": account.locked_until is not None,
            },
        )

    def save_security_state(self, account: account_domain.Account) -> None:
        """Write the password hash, the verification, the two tokens and the lockout.

        Raises:
            RuntimeError: If the account has no row.

        """
        row = self._loaded(account.id)
        row.password_hash = account.password_hash
        _write_security_state(row, account)
        self._session.add(row)
        self._session.flush()
        logger.debug(
            "identity.account_security_state_saved",
            extra={
                "user_id": str(account.id),
                "email_verified": account.email_verified,
                "verification_pending": account.email_verification is not None,
                "reset_pending": account.password_reset is not None,
            },
        )

    def _find_locked(
        self, condition: ColumnElement[bool], sought_by: str
    ) -> account_domain.Account | None:
        """Return the one account a condition picks, locked for the rest of the transaction."""
        logger.debug("identity.account_lookup_started", extra={"sought_by": sought_by})
        statement = (
            select(UserAccount)
            .where(condition)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        row = self._session.exec(statement).first()
        logger.debug(
            "identity.account_lookup_finished",
            extra={"sought_by": sought_by, "found": row is not None},
        )
        return _account_of(row) if row is not None else None

    def _loaded(self, account_id: UUID) -> UserAccount:
        """Return the row of an account a use case has already loaded."""
        row = self._session.get(UserAccount, account_id)
        if row is None:
            raise RuntimeError(
                f"Attempted to save account {account_id}, which has no row. Load the account "
                "through this repository before saving it."
            )
        return row


class BcryptPasswordVerifier:
    """Verifies a password with bcrypt, doing the same work when there is no hash."""

    def verify(self, plain_password: str, stored_hash: str | None) -> bool:
        """Return True when the password matches the hash, and False for no hash.

        With no hash the password is still verified, against a dummy value,
        and the result is thrown away. One verification runs either way.
        """
        if stored_hash is None:
            verify_password(plain_password, _TIMING_EQUALISER_HASH)
            return False
        return verify_password(plain_password, stored_hash)


class BcryptPasswordHasher:
    """Hashes a chosen password with bcrypt at the work factor of the service (BR-45)."""

    def hash(self, plain_password: str) -> str:
        """Return the bcrypt hash of a password."""
        return hash_password(plain_password)


class JwtAccessTokenIssuer:
    """Signs access tokens with the key of the service."""

    def issue(self, account: account_domain.Account, issued_at: datetime) -> IssuedAccessToken:
        """Return a signed access token carrying the role and branch of the account."""
        value, expires_in = create_access_token(
            account.id, role=account.role, branch_id=account.branch_id, issued_at=issued_at
        )
        return IssuedAccessToken(value=value, expires_in=expires_in)


def is_duplicate_email(error: IntegrityError) -> bool:
    """Return True when an integrity error is the unique constraint on the address."""
    diagnostics = getattr(error.orig, "diag", None)
    constraint = getattr(diagnostics, "constraint_name", None) if diagnostics is not None else None
    return (
        _sqlstate_of(error) == UNIQUE_VIOLATION_SQLSTATE
        and constraint == ACCOUNT_EMAIL_CONSTRAINT_NAME
    )


def _sqlstate_of(error: IntegrityError) -> str | None:
    """Return the five character SQLSTATE the driver reported, if any."""
    state = getattr(error.orig, "sqlstate", None)
    return str(state) if state is not None else None


def _write_security_state(row: UserAccount, account: account_domain.Account) -> None:
    """Copy the verification, the two tokens and the lockout of an account onto its row."""
    verification, reset = account.email_verification, account.password_reset
    row.email_verified_at = account.email_verified_at
    row.failed_login_count = account.failed_login_count
    row.locked_until = account.locked_until
    row.email_verification_token_hash = verification.token_hash if verification else None
    row.email_verification_expires_at = verification.expires_at if verification else None
    row.password_reset_token_hash = reset.token_hash if reset else None
    row.password_reset_expires_at = reset.expires_at if reset else None


def _pending(token_hash: str | None, expires_at: datetime | None) -> PendingToken | None:
    """Return the pending token two columns hold, or None when either is empty."""
    aware = in_utc(expires_at)
    if token_hash is None or aware is None:
        return None
    return PendingToken(token_hash=token_hash, expires_at=aware)


def _account_of(row: UserAccount) -> account_domain.Account:
    """Return the domain account for a `user_account` row."""
    return account_domain.Account(
        id=row.id,
        email=row.email,
        password_hash=row.password_hash,
        role=row.role,
        full_name=row.full_name,
        phone=row.phone,
        branch_id=row.branch_id,
        is_active=row.is_active,
        email_verified_at=in_utc(row.email_verified_at),
        failed_login_count=row.failed_login_count,
        locked_until=in_utc(row.locked_until),
        last_login_at=in_utc(row.last_login_at),
        email_verification=_pending(
            row.email_verification_token_hash, row.email_verification_expires_at
        ),
        password_reset=_pending(row.password_reset_token_hash, row.password_reset_expires_at),
    )
