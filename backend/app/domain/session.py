"""The refresh session, which is what keeps somebody signed in (BR-48).

Signing in opens a session and hands the browser an opaque refresh token. The
token is random, it means nothing by itself, and only its SHA-256 is ever
stored, so a copy of the database holds nothing that can be presented.

A token is used once. Using it stamps the session as rotated and opens a
successor in the same family, with a new token. A token that arrives a second
time has either been stolen or been kept by a client that fell behind, and the
two cannot be told apart, so the whole family is revoked.

A session ends in two ways without anybody revoking it. It ends fourteen days
after the sign in that started its family, however often it was used, and it
ends seven days after it was last used. `expires_at` holds the first of those
and is copied unchanged to every successor. The second is worked out from
`issued_at`, because a session is issued at the moment its predecessor was
used.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final
from uuid import UUID, uuid4

from app.domain.audit import ClientAddress
from app.domain.enums import RevokeReason

# 32 bytes from the operating system, which is 256 bits. The design document
# asks for at least 128.
REFRESH_TOKEN_BYTES: Final[int] = 32
REFRESH_ABSOLUTE_LIFETIME: Final[timedelta] = timedelta(days=14)
REFRESH_IDLE_LIFETIME: Final[timedelta] = timedelta(days=7)
# The width of the column that keeps the browser a session was opened from.
USER_AGENT_MAX_LENGTH: Final[int] = 200
TOKEN_ENCODING: Final[str] = "utf-8"


def mint_refresh_token() -> str:
    """Return a new opaque refresh token from the cryptographic random source."""
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    """Return the SHA-256 of a refresh token as hexadecimal, which is what is stored."""
    return hashlib.sha256(token.encode(TOKEN_ENCODING)).hexdigest()


@dataclass(slots=True)
class RefreshSession:
    """One refresh token, as the server remembers it.

    Attributes:
        user_account_id: The account that is signed in.
        family_id: The same for every session descended from one sign in.
        token_hash: The SHA-256 of the token. The token itself is not kept.
        issued_at: When this session was opened, which is when its
            predecessor was used.
        expires_at: When the family ends, fourteen days after the sign in.
        id: The session key.
        rotated_at: When the token was used, or None while it is unused.
        revoked_at: When the session stopped being usable, or None.
        revoked_reason: Why it stopped.
        user_agent: The browser the session was opened from, when it said.
        ip_address: The address the session was opened from, when known.

    """

    user_account_id: UUID
    family_id: UUID
    token_hash: str = field(repr=False)
    issued_at: datetime
    expires_at: datetime
    id: UUID = field(default_factory=uuid4)
    rotated_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_reason: RevokeReason | None = None
    user_agent: str | None = None
    ip_address: ClientAddress | None = None

    @classmethod
    def opened_at_sign_in(
        cls,
        *,
        user_account_id: UUID,
        token_hash: str,
        now: datetime,
        user_agent: str | None,
        ip_address: ClientAddress | None,
    ) -> RefreshSession:
        """Open the first session of a new family."""
        return cls(
            user_account_id=user_account_id,
            family_id=uuid4(),
            token_hash=token_hash,
            issued_at=now,
            expires_at=now + REFRESH_ABSOLUTE_LIFETIME,
            user_agent=_fitted(user_agent),
            ip_address=ip_address,
        )

    @property
    def was_rotated(self) -> bool:
        """Return True when the token has already been used once."""
        return self.rotated_at is not None

    @property
    def is_revoked(self) -> bool:
        """Return True when the session has stopped being usable."""
        return self.revoked_at is not None

    @property
    def usable_until(self) -> datetime:
        """Return the instant the session ends by itself, absolute or idle."""
        return min(self.expires_at, self.issued_at + REFRESH_IDLE_LIFETIME)

    def is_expired(self, now: datetime) -> bool:
        """Return True when the session has run out, by either lifetime."""
        return now >= self.usable_until

    def seconds_left(self, now: datetime) -> int:
        """Return how many whole seconds the session has left at `now`, never below zero."""
        return max(0, int((self.usable_until - now).total_seconds()))

    def rotate(
        self,
        *,
        token_hash: str,
        now: datetime,
        user_agent: str | None,
        ip_address: ClientAddress | None,
    ) -> RefreshSession:
        """Mark this session as used and return its successor.

        The successor belongs to the same family and ends on the same day.
        Only its idle time starts again.
        """
        self.rotated_at = now
        self.revoked_at = now
        self.revoked_reason = RevokeReason.ROTATION
        return RefreshSession(
            user_account_id=self.user_account_id,
            family_id=self.family_id,
            token_hash=token_hash,
            issued_at=now,
            expires_at=self.expires_at,
            user_agent=_fitted(user_agent),
            ip_address=ip_address,
        )


def _fitted(user_agent: str | None) -> str | None:
    """Return a user agent cut to the width of its column, or None for a blank one."""
    if user_agent is None or not user_agent.strip():
        return None
    return user_agent.strip()[:USER_AGENT_MAX_LENGTH]
