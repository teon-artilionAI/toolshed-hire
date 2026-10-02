"""The use case that signs somebody out (BR-48).

Signing out revokes on the server. Clearing the cookie alone would leave a
copied token working until it expired, so the family the token belongs to is
revoked with the reason `LOGOUT`.

It never fails. A caller with no cookie, an unknown token or a session that
has already ended is signed out as far as anybody can tell, so the answer is
the same in every case and nothing is disclosed by it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.application.use_case import UseCase
from app.domain.enums import RevokeReason
from app.domain.session import hash_refresh_token

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SignOutCommand:
    """A request to sign out.

    Attributes:
        presented_token: The token from the cookie, or None when there was no
            cookie. Kept out of the representation.

    """

    presented_token: str | None = field(repr=False)


class SignOutUseCase(UseCase[SignOutCommand, int]):
    """Revoke the family of sessions a refresh token belongs to."""

    def execute(self, command: SignOutCommand) -> int:
        """Revoke the sessions and return how many were still live.

        Returns:
            The number of sessions revoked. Zero when there was no token, the
            token was unknown or its family had already ended.

        """
        logger.info(
            "auth.logout_started", extra={"credential_presented": bool(command.presented_token)}
        )
        if not command.presented_token:
            logger.info("auth.logout_finished", extra={"revoked_session_count": 0})
            return 0
        now = self._clock.now()
        revoked_count = 0
        with self._uow as uow:
            session = uow.sessions.find_by_token_hash_for_update(
                hash_refresh_token(command.presented_token)
            )
            if session is not None:
                revoked_count = uow.sessions.revoke_family(
                    user_account_id=session.user_account_id,
                    family_id=session.family_id,
                    reason=RevokeReason.LOGOUT,
                    at=now,
                )
            uow.commit()
        logger.info(
            "auth.logout_finished",
            extra={
                "revoked_session_count": revoked_count,
                "user_id": str(session.user_account_id) if session is not None else None,
            },
        )
        return revoked_count
