"""The SQL side of signing in, which is accounts and refresh sessions.

Two repositories and two small adapters. The repositories map the
`user_account` and `refresh_session` rows to the domain entities and back, on
the session of the unit of work that created them. The adapters put bcrypt and
the token signer behind the two ports the use cases ask for.

Two reads take a row lock. A sign in locks the account it is checking, so two
attempts cannot both read the same failure count. A refresh locks the session
it is rotating, so of two requests presenting one token the second finds it
already used. The lock is released when the transaction ends.

A family is revoked through the partial index on live sessions. The statement
names the account as well as the family, so the database goes to the handful
of live sessions that account holds and never reads the history.

A timestamp read back from a database with no time zone type arrives without
one. Every instant is stored in UTC, so a value without a zone is given UTC.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import CursorResult, update
from sqlmodel import Session, col, select

from app.application.identity.ports import IssuedAccessToken
from app.domain import account as account_domain
from app.domain import session as session_domain
from app.domain.enums import RevokeReason
from app.infrastructure.models import RefreshSession, UserAccount
from app.infrastructure.security import create_access_token, hash_password, verify_password

logger = logging.getLogger(__name__)

# What a password is compared against when there is no account to check, so a
# refusal for an unknown address costs one bcrypt verification like any other.
_TIMING_EQUALISER_HASH = hash_password("not-a-real-password-timing-equaliser")


class SqlAccountRepository:
    """Reads sign in accounts and writes their lockout state through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session

    def find_by_email_for_update(self, email: str) -> account_domain.Account | None:
        """Return the account with this address, locked for the rest of the transaction."""
        logger.debug("identity.account_lookup_started")
        statement = select(UserAccount).where(col(UserAccount.email) == email).with_for_update()
        row = self._session.exec(statement).first()
        logger.debug("identity.account_lookup_finished", extra={"found": row is not None})
        return _account_of(row) if row is not None else None

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

    def save_login_state(self, account: account_domain.Account) -> None:
        """Write the failure count, the lock and the last sign in of an account.

        Raises:
            RuntimeError: If the account has no row, which would mean a use
                case is saving an account it never loaded.

        """
        row = self._session.get(UserAccount, account.id)
        if row is None:
            raise RuntimeError(
                f"Attempted to save the sign in state of account {account.id}, which has no "
                "row. Load the account through this repository before saving it."
            )
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


class SqlSessionRepository:
    """Stores refresh sessions through one session of the database."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session

    def add(self, session: session_domain.RefreshSession) -> None:
        """Write a new refresh session inside the current transaction."""
        self._session.add(
            RefreshSession(
                id=session.id,
                user_account_id=session.user_account_id,
                family_id=session.family_id,
                token_hash=session.token_hash,
                issued_at=session.issued_at,
                expires_at=session.expires_at,
                user_agent=session.user_agent,
                ip_address=session.ip_address,
            )
        )
        self._session.flush()
        logger.debug(
            "identity.refresh_session_added",
            extra={
                "session_id": str(session.id),
                "session_family_id": str(session.family_id),
                "user_id": str(session.user_account_id),
            },
        )

    def find_by_token_hash_for_update(
        self, token_hash: str
    ) -> session_domain.RefreshSession | None:
        """Return the session a token hash names, locked for the rest of the transaction."""
        statement = (
            select(RefreshSession)
            .where(col(RefreshSession.token_hash) == token_hash)
            .with_for_update()
        )
        row = self._session.exec(statement).first()
        logger.debug("identity.refresh_session_lookup_finished", extra={"found": row is not None})
        return _session_of(row) if row is not None else None

    def save_rotation(self, session: session_domain.RefreshSession) -> None:
        """Write that a session was used, with when and why it stopped.

        Raises:
            RuntimeError: If the session has no row.

        """
        row = self._session.get(RefreshSession, session.id)
        if row is None:
            raise RuntimeError(
                f"Attempted to save refresh session {session.id}, which has no row. Load the "
                "session through this repository before saving it."
            )
        row.rotated_at = session.rotated_at
        row.revoked_at = session.revoked_at
        row.revoked_reason = session.revoked_reason
        self._session.add(row)
        self._session.flush()
        logger.debug("identity.refresh_session_rotated", extra={"session_id": str(session.id)})

    def revoke_family(
        self, *, user_account_id: UUID, family_id: UUID, reason: RevokeReason, at: datetime
    ) -> int:
        """Revoke every live session of a family and return how many there were."""
        statement = (
            update(RefreshSession)
            .where(
                col(RefreshSession.user_account_id) == user_account_id,
                col(RefreshSession.family_id) == family_id,
                col(RefreshSession.revoked_at).is_(None),
            )
            .values(revoked_at=at, revoked_reason=reason)
        )
        result = self._session.execute(statement)
        revoked_count = result.rowcount if isinstance(result, CursorResult) else 0
        logger.info(
            "identity.refresh_family_revoked",
            extra={
                "session_family_id": str(family_id),
                "user_id": str(user_account_id),
                "reason": reason.value,
                "revoked_session_count": revoked_count,
            },
        )
        return revoked_count


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


class JwtAccessTokenIssuer:
    """Signs access tokens with the key of the service."""

    def issue(self, account: account_domain.Account, issued_at: datetime) -> IssuedAccessToken:
        """Return a signed access token carrying the role and branch of the account."""
        value, expires_in = create_access_token(
            account.id, role=account.role, branch_id=account.branch_id, issued_at=issued_at
        )
        return IssuedAccessToken(value=value, expires_in=expires_in)


def _in_utc(instant: datetime | None) -> datetime | None:
    """Return a stored instant with its zone, giving UTC to one that lost it."""
    if instant is None or instant.tzinfo is not None:
        return instant
    return instant.replace(tzinfo=UTC)


def _required_utc(instant: datetime) -> datetime:
    """Return a stored instant that is never null, with its zone."""
    return instant if instant.tzinfo is not None else instant.replace(tzinfo=UTC)


def _account_of(row: UserAccount) -> account_domain.Account:
    """Return the domain account for a `user_account` row."""
    return account_domain.Account(
        id=row.id,
        email=row.email,
        password_hash=row.password_hash,
        role=row.role,
        full_name=row.full_name,
        branch_id=row.branch_id,
        is_active=row.is_active,
        email_verified_at=_in_utc(row.email_verified_at),
        failed_login_count=row.failed_login_count,
        locked_until=_in_utc(row.locked_until),
        last_login_at=_in_utc(row.last_login_at),
    )


def _session_of(row: RefreshSession) -> session_domain.RefreshSession:
    """Return the domain session for a `refresh_session` row.

    The address and the browser are written once and never read back, so they
    are left out.
    """
    return session_domain.RefreshSession(
        id=row.id,
        user_account_id=row.user_account_id,
        family_id=row.family_id,
        token_hash=row.token_hash,
        issued_at=_required_utc(row.issued_at),
        expires_at=_required_utc(row.expires_at),
        rotated_at=_in_utc(row.rotated_at),
        revoked_at=_in_utc(row.revoked_at),
        revoked_reason=row.revoked_reason,
    )
