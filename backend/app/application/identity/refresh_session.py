"""The use case that exchanges a refresh token for a new pair (BR-48).

A refresh token works once. Presenting it stamps its session as used and opens
a successor in the same family, with a new token. The account is read again at
that moment, so somebody who was deactivated since they signed in gets nothing
further.

A token that has already been used is the interesting case. It is either a
stolen copy or a client that fell behind, and there is no telling which. The
whole family is revoked, an audit event records it and the caller is told to
sign in again.

Every refusal reads the same from outside. The reason goes to the log.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Final

from app.application.audit import audit_event_for
from app.application.clock import Clock
from app.application.identity.ports import AccessTokenIssuer
from app.application.identity.sessions import (
    ACCOUNT_ENTITY_TYPE,
    ClientDetails,
    SessionGrant,
    grant_session,
)
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.enums import RevokeReason
from app.domain.errors import SessionExpired
from app.domain.session import RefreshSession, hash_refresh_token, mint_refresh_token

logger = logging.getLogger(__name__)

REFRESH_REUSE_DETECTED_ACTION: Final[str] = "auth.refresh_reuse_detected"
SESSION_EXPIRED_MESSAGE: Final[str] = "The session has ended. Sign in again to continue."


class RefreshFailure(str, Enum):
    """Why a refresh was refused. Recorded on the server and never returned."""

    MISSING = "missing"
    UNKNOWN = "unknown"
    REUSED = "reused"
    REVOKED = "revoked"
    EXPIRED = "expired"
    ACCOUNT_UNAVAILABLE = "account-unavailable"


@dataclass(frozen=True, slots=True)
class RefreshSessionCommand:
    """A request to exchange a refresh token.

    Attributes:
        presented_token: The token from the cookie, or None when there was no
            cookie. Kept out of the representation.
        client: Where the request came from.

    """

    presented_token: str | None = field(repr=False)
    client: ClientDetails = field(default_factory=ClientDetails)


class RefreshSessionUseCase(UseCase[RefreshSessionCommand, SessionGrant]):
    """Rotate a refresh token, or revoke its family when it was used before."""

    def __init__(self, uow: UnitOfWork, clock: Clock, tokens: AccessTokenIssuer) -> None:
        """Keep the collaborators the use case works with.

        Args:
            uow: The unit of work that owns the transaction.
            clock: Where the current instant comes from.
            tokens: Signs the access token.

        """
        super().__init__(uow, clock)
        self._tokens = tokens

    def execute(self, command: RefreshSessionCommand) -> SessionGrant:
        """Return a new access token and a new refresh token for a live session.

        Raises:
            SessionExpired: If there is no token, or the token is unknown,
                used, revoked or expired, or the account may no longer sign in.

        """
        logger.info("auth.refresh_started")
        if not command.presented_token:
            raise _refusal(RefreshFailure.MISSING)
        now = self._clock.now()
        token_hash = hash_refresh_token(command.presented_token)
        with self._uow as uow:
            outcome = self._rotate(uow, token_hash, command.client, now)
            # A detected reuse revokes a family and writes an audit event, so a
            # refusal is committed as well.
            uow.commit()
        if not isinstance(outcome, SessionGrant):
            raise _refusal(outcome)
        logger.info(
            "auth.refresh_succeeded",
            extra={"user_id": str(outcome.account.id), "role": outcome.account.role.value},
        )
        return outcome

    def _rotate(
        self, uow: UnitOfWork, token_hash: str, client: ClientDetails, now: datetime
    ) -> SessionGrant | RefreshFailure:
        """Use the session the hash names and open its successor. Nothing is committed here."""
        session = uow.sessions.find_by_token_hash_for_update(token_hash)
        if session is None:
            return RefreshFailure.UNKNOWN
        if session.was_rotated:
            return self._revoke_reused_family(uow, session, now)
        if session.is_revoked:
            return RefreshFailure.REVOKED
        if session.is_expired(now):
            return RefreshFailure.EXPIRED
        account = uow.accounts.get(session.user_account_id)
        if account is None or not account.is_active:
            return RefreshFailure.ACCOUNT_UNAVAILABLE

        refresh_token = mint_refresh_token()
        successor = session.rotate(
            token_hash=hash_refresh_token(refresh_token),
            now=now,
            user_agent=client.user_agent,
            ip_address=client.address,
        )
        uow.sessions.save_rotation(session)
        uow.sessions.add(successor)
        return grant_session(
            uow,
            self._tokens,
            account=account,
            session=successor,
            refresh_token=refresh_token,
            now=now,
        )

    def _revoke_reused_family(
        self, uow: UnitOfWork, session: RefreshSession, now: datetime
    ) -> RefreshFailure:
        """Revoke the family of a token that was presented twice, and record it."""
        revoked_count = uow.sessions.revoke_family(
            user_account_id=session.user_account_id,
            family_id=session.family_id,
            reason=RevokeReason.REUSE_DETECTED,
            at=now,
        )
        uow.audit.record(
            audit_event_for(
                actor=None,
                entity_type=ACCOUNT_ENTITY_TYPE,
                entity_id=session.user_account_id,
                action=REFRESH_REUSE_DETECTED_ACTION,
                occurred_at=now,
                after_state={
                    "session_family_id": str(session.family_id),
                    "revoked_session_count": revoked_count,
                    "reason": RevokeReason.REUSE_DETECTED.value,
                },
            )
        )
        logger.error(
            "auth.refresh_reuse_detected",
            extra={
                "user_id": str(session.user_account_id),
                "session_family_id": str(session.family_id),
                "revoked_session_count": revoked_count,
            },
        )
        return RefreshFailure.REUSED


def _refusal(reason: RefreshFailure) -> SessionExpired:
    """Log why the refresh was refused and return the one refusal a caller sees."""
    logger.warning("auth.refresh_refused", extra={"reason": reason.value})
    return SessionExpired(SESSION_EXPIRED_MESSAGE)
