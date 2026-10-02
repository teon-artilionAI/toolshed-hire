"""The SQL side of staying signed in, which is the refresh sessions.

The repository maps the `refresh_session` rows to the domain entity and back,
on the session of the unit of work that created it.

A refresh locks the session it is rotating, so of two requests presenting one
token the second finds it already used. The lock is released when the
transaction ends.

A family is revoked through the partial index on live sessions. The statement
names the account as well as the family, so the database goes to the handful
of live sessions that account holds and never reads the history. Revoking
every session of an account, which a password reset does, goes through the
same index.

A timestamp read back from a database with no time zone type arrives without
one. Every instant is stored in UTC, so a value without a zone is given UTC.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import CursorResult, update
from sqlmodel import Session, col, select

from app.domain import session as session_domain
from app.domain.enums import RevokeReason
from app.infrastructure.booking_mapping import in_utc, required_utc
from app.infrastructure.models import RefreshSession

logger = logging.getLogger(__name__)


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

    def revoke_all_for_account(
        self, *, user_account_id: UUID, reason: RevokeReason, at: datetime
    ) -> int:
        """Revoke every live session of an account, whatever its family, and return how many."""
        statement = (
            update(RefreshSession)
            .where(
                col(RefreshSession.user_account_id) == user_account_id,
                col(RefreshSession.revoked_at).is_(None),
            )
            .values(revoked_at=at, revoked_reason=reason)
        )
        result = self._session.execute(statement)
        revoked_count = result.rowcount if isinstance(result, CursorResult) else 0
        logger.info(
            "identity.refresh_sessions_revoked",
            extra={
                "user_id": str(user_account_id),
                "reason": reason.value,
                "revoked_session_count": revoked_count,
            },
        )
        return revoked_count


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
        issued_at=required_utc(row.issued_at, "refresh_session.issued_at"),
        expires_at=required_utc(row.expires_at, "refresh_session.expires_at"),
        rotated_at=in_utc(row.rotated_at),
        revoked_at=in_utc(row.revoked_at),
        revoked_reason=row.revoked_reason,
    )
