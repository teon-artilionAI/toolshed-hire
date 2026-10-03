"""The single use tokens behind the two account security messages (C-18).

A verification link and a reset link each carry a random token. The token is
sent once, in the message, and only its SHA-256 is stored, so a copy of the
database holds nothing that can be presented.

A token works once and stops being accepted when its time is up. An account
holds at most one token of each kind, so issuing a new one replaces the old
one and the link in an earlier message stops working.

The two lifetimes are constants and not settings. A verification link lasts a
day, because a person may only reach their mailbox in the evening. A reset
link lasts an hour, because it changes a password.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final

# 32 bytes from the operating system, which is 256 bits.
ACCOUNT_TOKEN_BYTES: Final[int] = 32
EMAIL_VERIFICATION_LIFETIME: Final[timedelta] = timedelta(hours=24)
PASSWORD_RESET_LIFETIME: Final[timedelta] = timedelta(minutes=60)
TOKEN_ENCODING: Final[str] = "utf-8"


def mint_account_token() -> str:
    """Return a new single use token from the cryptographic random source."""
    return secrets.token_urlsafe(ACCOUNT_TOKEN_BYTES)


def hash_account_token(token: str) -> str:
    """Return the SHA-256 of a token as hexadecimal, which is what is stored."""
    return hashlib.sha256(token.encode(TOKEN_ENCODING)).hexdigest()


@dataclass(frozen=True, slots=True)
class PendingToken:
    """The half of a single use token the server keeps.

    Attributes:
        token_hash: The SHA-256 of the token. The token itself is not kept,
            and the hash is left out of the representation.
        expires_at: The instant the token stops being accepted.

    """

    token_hash: str = field(repr=False)
    expires_at: datetime

    @classmethod
    def issued(cls, token: str, *, now: datetime, lifetime: timedelta) -> PendingToken:
        """Return what is stored for a token issued at `now` with this lifetime."""
        return cls(token_hash=hash_account_token(token), expires_at=now + lifetime)

    @classmethod
    def for_email_verification(cls, token: str, now: datetime) -> PendingToken:
        """Return what is stored for a verification token issued at `now`."""
        return cls.issued(token, now=now, lifetime=EMAIL_VERIFICATION_LIFETIME)

    @classmethod
    def for_password_reset(cls, token: str, now: datetime) -> PendingToken:
        """Return what is stored for a reset token issued at `now`."""
        return cls.issued(token, now=now, lifetime=PASSWORD_RESET_LIFETIME)

    def is_expired(self, now: datetime) -> bool:
        """Return True once the time of the token is up."""
        return now >= self.expires_at

    def accepts(self, presented_token: str, now: datetime) -> bool:
        """Return True when the presented token is this one and is still in time.

        The two hashes are compared in constant time, so the time the answer
        takes says nothing about how much of a guess was right.
        """
        matches = hmac.compare_digest(self.token_hash, hash_account_token(presented_token))
        return matches and not self.is_expired(now)
