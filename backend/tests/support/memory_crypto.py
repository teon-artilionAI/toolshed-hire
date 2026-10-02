"""The fakes that stand in for the cryptography of the identity use cases.

A use case is handed a password verifier, a password hasher and an access
token issuer through ports, so a unit test can hand it these and run with no
work factor and no signing key.

`CountingPasswordVerifier` compares against a readable stand in for a hash and
remembers every call, so a test can assert that each path verified exactly
once. `CountingPasswordHasher` produces that stand in and counts how often it
was asked, so a test can assert that a path hashed exactly once. It applies
no rule of its own. The password rule belongs to the use case, and a fake that
enforced it would hide a use case that forgot to. `FakeAccessTokenIssuer`
hands back a value that is plainly not a token.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Final
from uuid import UUID

from app.application.identity.ports import IssuedAccessToken
from app.domain.account import Account

FAKE_HASH_PREFIX: Final[str] = "stand-in-hash-of:"
FAKE_ACCESS_LIFETIME_SECONDS: Final[int] = 900


def fake_hash(plain_password: str) -> str:
    """Return the readable stand in the counting verifier treats as a hash."""
    return f"{FAKE_HASH_PREFIX}{plain_password}"


@dataclass
class CountingPasswordVerifier:
    """Compares against the stand in hash and remembers every call it was given.

    Attributes:
        calls: The stored hash handed to each call, in order. None is a call
            made for an account that could not be checked.

    """

    calls: list[str | None] = field(default_factory=list)

    def verify(self, plain_password: str, stored_hash: str | None) -> bool:
        """Record the call and answer whether the password matches the stand in."""
        self.calls.append(stored_hash)
        return stored_hash is not None and stored_hash == fake_hash(plain_password)


@dataclass
class CountingPasswordHasher:
    """Returns the stand in hash of a password and counts how often it was asked.

    Attributes:
        call_count: How many passwords it has hashed.

    """

    call_count: int = 0

    def hash(self, plain_password: str) -> str:
        """Count the call and return the stand in hash."""
        self.call_count += 1
        return fake_hash(plain_password)


@dataclass
class FakeAccessTokenIssuer:
    """Issues a value that is plainly not a token, and remembers who it was for."""

    issued_for: list[UUID] = field(default_factory=list)

    def issue(self, account: Account, issued_at: datetime) -> IssuedAccessToken:
        """Return a made up access token for the account."""
        self.issued_for.append(account.id)
        return IssuedAccessToken(
            value=f"made-up-access-token-for-{account.role.value.lower()}",
            expires_in=FAKE_ACCESS_LIFETIME_SECONDS,
        )


__all__ = [
    "FAKE_ACCESS_LIFETIME_SECONDS",
    "FAKE_HASH_PREFIX",
    "CountingPasswordHasher",
    "CountingPasswordVerifier",
    "FakeAccessTokenIssuer",
    "fake_hash",
]
