"""Access token helpers.

A valid token is minted with the application's own `create_access_token`, so a
test cannot pass by agreeing with a second implementation of the claim set that
only exists in the test suite. The invalid tokens are built by damaging a real
one in exactly the ways an attacker would: let it expire, edit the signature,
edit the payload, or sign it with a key of the attacker's own.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID

import jwt

from app.config import settings
from app.infrastructure.security import TOKEN_ISSUER, TOKEN_TYPE_ACCESS, create_access_token

logger = logging.getLogger(__name__)

BEARER_SCHEME: Final[str] = "Bearer"
AUTHORIZATION_HEADER: Final[str] = "Authorization"
# Far enough past the configured lifetime that no clock skew allowance rescues it.
EXPIRY_MARGIN_MINUTES: Final[int] = 5
FOREIGN_SIGNING_KEY: Final[str] = "an-attackers-own-signing-key-not-the-servers-one"
SIGNATURE_SEPARATOR: Final[str] = "."
JWT_SEGMENT_COUNT: Final[int] = 3


def mint_access_token(user_id: UUID) -> str:
    """Mint a currently valid access token for an account.

    Args:
        user_id: The account the token identifies.

    Returns:
        The encoded token, signed exactly as the sign in endpoint signs it.

    """
    token, _expires_in = create_access_token(user_id)
    return token


def mint_expired_access_token(user_id: UUID) -> str:
    """Mint a token that was valid but whose lifetime has already run out.

    The issue time is pushed back by the full configured lifetime plus a margin,
    so the token is genuinely expired rather than merely close to it.
    """
    lifetime = timedelta(minutes=settings.access_token_minutes + EXPIRY_MARGIN_MINUTES)
    issued_at = datetime.now(UTC) - lifetime
    token, _expires_in = create_access_token(user_id, issued_at=issued_at)
    logger.debug(
        "test.expired_token_minted",
        extra={"user_id": str(user_id), "backdated_minutes": int(lifetime.total_seconds() // 60)},
    )
    return token


def mint_token_signed_with_a_foreign_key(user_id: UUID) -> str:
    """Mint a structurally perfect token signed with a key the server does not hold."""
    now = datetime.now(UTC)
    payload: dict[str, str | int] = {
        "sub": str(user_id),
        "iss": TOKEN_ISSUER,
        "typ": TOKEN_TYPE_ACCESS,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
    }
    return jwt.encode(payload, FOREIGN_SIGNING_KEY, algorithm=settings.jwt_algorithm)


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
    "authorization_header",
    "mint_access_token",
    "mint_expired_access_token",
    "mint_token_signed_with_a_foreign_key",
    "tamper_with_signature",
]
