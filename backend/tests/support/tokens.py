"""Access token helpers.

A valid token is minted with the application's own `create_access_token`, so a
test cannot pass by agreeing with a second implementation of the claim set that
only exists in the test suite. The invalid tokens are built by damaging a real
one in exactly the ways an attacker would: let it expire, edit the signature,
edit the payload, or sign it with a key of the attacker's own.

A token carries the role and the branch of its holder as claims. The helpers
default both to those of a customer, because the dependency chain reads the
role from the account row and a test that cares about the claims says so.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID

import jwt

from app.config import settings
from app.domain.enums import UserRole
from app.infrastructure.security import (
    CLAIM_BRANCH,
    CLAIM_ROLE,
    KEY_ID_HEADER,
    TOKEN_ISSUER,
    TOKEN_TYPE_ACCESS,
    create_access_token,
    signing_key_id,
)

logger = logging.getLogger(__name__)

BEARER_SCHEME: Final[str] = "Bearer"
AUTHORIZATION_HEADER: Final[str] = "Authorization"
# Far enough past the configured lifetime that no clock skew allowance rescues it.
EXPIRY_MARGIN_MINUTES: Final[int] = 5
FOREIGN_SIGNING_KEY: Final[str] = "an-attackers-own-signing-key-not-the-servers-one"
SIGNATURE_SEPARATOR: Final[str] = "."
JWT_SEGMENT_COUNT: Final[int] = 3


def mint_access_token(
    user_id: UUID,
    *,
    role: UserRole = UserRole.CUSTOMER,
    branch_id: UUID | None = None,
    issued_at: datetime | None = None,
) -> str:
    """Mint a currently valid access token for an account.

    Args:
        user_id: The account the token identifies.
        role: The role claim. A customer unless the test says otherwise.
        branch_id: The branch claim. None unless the test says otherwise.
        issued_at: When the token was issued. Now, by the system clock, when
            omitted. A test that holds the time still passes its own instant.

    Returns:
        The encoded token, signed exactly as the sign in endpoint signs it.

    """
    token, _expires_in = create_access_token(
        user_id, role=role, branch_id=branch_id, issued_at=issued_at or datetime.now(UTC)
    )
    return token


def mint_expired_access_token(user_id: UUID) -> str:
    """Mint a token that was valid but whose lifetime has already run out.

    The issue time is pushed back by the full configured lifetime plus a margin,
    so the token is genuinely expired rather than merely close to it.
    """
    lifetime = timedelta(minutes=settings.access_token_minutes + EXPIRY_MARGIN_MINUTES)
    token = mint_access_token(user_id, issued_at=datetime.now(UTC) - lifetime)
    logger.debug(
        "test.expired_token_minted",
        extra={"user_id": str(user_id), "backdated_minutes": int(lifetime.total_seconds() // 60)},
    )
    return token


def mint_token_signed_with_a_foreign_key(user_id: UUID, *, key_id: str | None = None) -> str:
    """Mint a structurally perfect token signed with a key the server does not hold.

    Args:
        user_id: The account the token claims to identify.
        key_id: The key identifier written into the header. The identifier of
            the foreign key itself when omitted, which is what an attacker's
            own issuer would write. Pass the server's identifier to claim the
            server's key while signing with another.

    """
    now = datetime.now(UTC)
    payload: dict[str, str | int | None] = {
        "sub": str(user_id),
        CLAIM_ROLE: UserRole.ADMIN.value,
        CLAIM_BRANCH: None,
        "iss": TOKEN_ISSUER,
        "typ": TOKEN_TYPE_ACCESS,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
    }
    return jwt.encode(
        payload,
        FOREIGN_SIGNING_KEY,
        algorithm=settings.jwt_algorithm,
        headers={KEY_ID_HEADER: key_id or signing_key_id(FOREIGN_SIGNING_KEY)},
    )


def tamper_with_signature(token: str) -> str:
    """Return the token with its signature altered and its payload untouched.

    Args:
        token: A valid encoded token.

    Returns:
        The same header and payload with a signature that cannot verify.

    Raises:
        ValueError: If the input is not a three segment JWT, which would mean
            the test is asserting against something it never built.

    """
    segments = token.split(SIGNATURE_SEPARATOR)
    if len(segments) != JWT_SEGMENT_COUNT:
        raise ValueError(
            "Attempted to tamper with the signature of a value that is not a JWT. "
            f"Expected {JWT_SEGMENT_COUNT} dot separated segments, got {len(segments)}."
        )
    header, payload, signature = segments
    flipped = "B" + signature[1:] if signature[0] != "B" else "C" + signature[1:]
    return SIGNATURE_SEPARATOR.join((header, payload, flipped))


def authorization_header(token: str) -> dict[str, str]:
    """Return the request header carrying a bearer token."""
    return {AUTHORIZATION_HEADER: f"{BEARER_SCHEME} {token}"}


__all__ = [
    "FOREIGN_SIGNING_KEY",
    "authorization_header",
    "mint_access_token",
    "mint_expired_access_token",
    "mint_token_signed_with_a_foreign_key",
    "tamper_with_signature",
]
