"""Password hashing and access token issue and verification.

Self hosted JWT with bcrypt, which is the decision recorded in the canonical
decisions. Two properties matter and are enforced here.

A token carries the subject and nothing that grants authority. The role is
never read from a claim, because a token minted before a demotion would
otherwise keep the old permissions until it expired. The dependency chain loads
the account and reads the role from the database on every request.

A verification failure is never swallowed. Every path raises
AuthenticationFailure with the reason attached, and the API turns that into a
401 with a problem document that says nothing about which half of the credential
pair was wrong.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID

import jwt
from passlib.context import CryptContext

from app.config import settings
from app.domain.errors import AuthenticationFailure, ValidationFailure

logger = logging.getLogger(__name__)

BCRYPT_ROUNDS: Final[int] = 12
MINIMUM_PASSWORD_LENGTH: Final[int] = 12
# bcrypt silently truncates beyond 72 bytes, so a longer password is rejected
# rather than accepted and quietly shortened.
MAXIMUM_PASSWORD_BYTES: Final[int] = 72
TOKEN_TYPE_ACCESS: Final[str] = "access"
TOKEN_ISSUER: Final[str] = "toolshed-hire"

_password_context = CryptContext(
    schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=BCRYPT_ROUNDS
)


def hash_password(plain_password: str) -> str:
    """Hash a plain password with bcrypt at work factor 12.

    Args:
        plain_password: The password as typed by the account holder.

    Returns:
        The bcrypt hash, safe to store.

    Raises:
        ValidationFailure: If the password is shorter than the policy minimum
            or longer than bcrypt can hash without truncation.

    """
    if len(plain_password) < MINIMUM_PASSWORD_LENGTH:
        raise ValidationFailure(
            "Attempted to hash a password shorter than the policy minimum. "
            f"Received {len(plain_password)} characters, the minimum is "
            f"{MINIMUM_PASSWORD_LENGTH} (BR-45).",
            {"minimum_length": MINIMUM_PASSWORD_LENGTH},
        )
    encoded_length = len(plain_password.encode("utf-8"))
    if encoded_length > MAXIMUM_PASSWORD_BYTES:
        raise ValidationFailure(
            "Attempted to hash a password longer than bcrypt can process. "
            f"Received {encoded_length} bytes, the maximum is {MAXIMUM_PASSWORD_BYTES}.",
            {"maximum_bytes": MAXIMUM_PASSWORD_BYTES},
        )
    # passlib ships no type information, so CryptContext.hash is typed Any.
    # str() pins the return type at this boundary instead of letting an Any
    # travel into every caller that stores a password hash.
    return str(_password_context.hash(plain_password))


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Return True when the plain password matches the stored hash.

    A malformed stored hash is reported as a mismatch and logged, because it is
    an operational fault rather than a reason to hand the caller a 500.
    """
    try:
        # bool() for the same reason hash_password wraps in str(). passlib is
        # untyped, so the verify result arrives as Any.
        return bool(_password_context.verify(plain_password, password_hash))
    except ValueError as exc:
        logger.error(
            "security.password_hash_unreadable",
            extra={"attempted": "verify stored bcrypt hash", "error": str(exc)},
        )
        return False


def create_access_token(user_id: UUID, *, issued_at: datetime | None = None) -> tuple[str, int]:
    """Mint a signed access token for the given account.

    Args:
        user_id: The account the token identifies. This is the only authority
            the token carries.
        issued_at: Override for the issue time, used by tests.

    Returns:
        A tuple of the encoded token and its lifetime in seconds.

    """
    now = issued_at or datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.access_token_minutes)
    payload: dict[str, str | int] = {
        "sub": str(user_id),
        "iss": TOKEN_ISSUER,
        "typ": TOKEN_TYPE_ACCESS,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    logger.info(
        "security.access_token_issued",
        extra={
            "user_id": str(user_id),
            "expires_in_seconds": settings.access_token_minutes * 60,
            "algorithm": settings.jwt_algorithm,
        },
    )
    return token, settings.access_token_minutes * 60


def read_subject(token: str) -> UUID:
    """Verify a token and return the account id it identifies.

    Args:
        token: The bearer token taken from the Authorization header.

    Returns:
        The account id from the `sub` claim.

    Raises:
        AuthenticationFailure: If the signature, issuer, type, expiry or
            subject is wrong. The message names the fault for the log, and the
            API layer replaces it with a deliberately vague response.

    """
    try:
        claims: dict[str, str | int] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=TOKEN_ISSUER,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationFailure(
            "Attempted to authenticate with an expired access token.",
            {"reason": "expired"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationFailure(
            f"Attempted to authenticate with a token that failed verification: {exc}",
            {"reason": "invalid"},
        ) from exc

    if claims.get("typ") != TOKEN_TYPE_ACCESS:
        raise AuthenticationFailure(
            "Attempted to authenticate with a token that is not an access token. "
            f"Token type claim was {claims.get('typ')!r}.",
            {"reason": "wrong-token-type"},
        )
    subject = str(claims.get("sub", ""))
    try:
        return UUID(subject)
    except ValueError as exc:
        raise AuthenticationFailure(
            f"Attempted to authenticate with a token whose subject claim {subject!r} "
            "is not a UUID.",
            {"reason": "malformed-subject"},
        ) from exc
