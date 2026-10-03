"""Password hashing and access token issue and verification.

Self hosted JWT with bcrypt, which is the decision recorded in the canonical
decisions. Four properties matter and are enforced here.

A token names its signing key. The header carries a `kid`, which is the first
characters of the SHA-256 of the key, so the identifier needs no setting of
its own and gives nothing away about the key. Verification looks the key up by
that identifier and refuses a token that names a key this service does not
hold. That is what lets the key be rotated (C-36). A second key is added to
the ring, new tokens are signed with it, and tokens signed with the old one
keep working until they expire.

A token carries `sub`, `role` and `branch_id`, as the design document sets out.
The dependency chain in `app/api/deps.py` still loads the account and reads
the role from the row on every request, which is stricter than the fifteen
minutes the document allows a claim to be trusted for. The claims are there
for a reader that has no database to ask.

The time is never read here. A token is issued at an instant the caller
supplies and its expiry is checked against one, so both come from the clock
and a test can hold them still.

A verification failure is never swallowed. Every path raises
AuthenticationFailure with the reason attached.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final
from uuid import UUID

import jwt
from passlib.context import CryptContext

from app.config import settings
from app.domain.enums import UserRole
from app.domain.errors import AuthenticationFailure, ValidationFailure
from app.domain.password_policy import MAXIMUM_PASSWORD_BYTES, MINIMUM_PASSWORD_LENGTH

logger = logging.getLogger(__name__)

# The two limits `hash_password` enforces are the password rule of the domain,
# imported above. The seed and the tests hash through here with no use case in
# front of them, so the rule is checked again at this boundary.
BCRYPT_ROUNDS: Final[int] = 12
TOKEN_TYPE_ACCESS: Final[str] = "access"
TOKEN_ISSUER: Final[str] = "toolshed-hire"
KEY_ID_HEADER: Final[str] = "kid"
# Sixteen hexadecimal characters of the digest. Enough to tell keys apart and
# far too little to learn anything about one.
KEY_ID_LENGTH: Final[int] = 16
CLAIM_ROLE: Final[str] = "role"
CLAIM_BRANCH: Final[str] = "branch_id"
SECONDS_PER_MINUTE: Final[int] = 60
SECRET_ENCODING: Final[str] = "utf-8"

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


def signing_key_id(secret: str) -> str:
    """Return the identifier a signing key is known by, derived from the key itself."""
    return hashlib.sha256(secret.encode(SECRET_ENCODING)).hexdigest()[:KEY_ID_LENGTH]


def _verification_keys() -> dict[str, str]:
    """Return every key a token may have been signed with, by identifier.

    There is one today. Rotating the key means returning the old one here as
    well until the last token signed with it has expired.
    """
    return {signing_key_id(settings.jwt_secret): settings.jwt_secret}


@dataclass(frozen=True, slots=True)
class AccessClaims:
    """What a verified access token says about its holder.

    Attributes:
        subject: The account the token identifies.
        role: The role the account held when the token was issued.
        branch_id: The branch of a counter account at that moment, else None.

    """

    subject: UUID
    role: UserRole
    branch_id: UUID | None


def create_access_token(
    user_id: UUID, *, role: UserRole, branch_id: UUID | None, issued_at: datetime
) -> tuple[str, int]:
    """Mint a signed access token for the given account.

    Args:
        user_id: The account the token identifies.
        role: The role the account holds now.
        branch_id: The branch of a counter account, and None for anyone else.
        issued_at: The instant of issue, from the clock.

    Returns:
        A tuple of the encoded token and its lifetime in seconds.

    """
    lifetime = timedelta(minutes=settings.access_token_minutes)
    payload: dict[str, str | int | None] = {
        "sub": str(user_id),
        CLAIM_ROLE: role.value,
        CLAIM_BRANCH: str(branch_id) if branch_id is not None else None,
        "iss": TOKEN_ISSUER,
        "typ": TOKEN_TYPE_ACCESS,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + lifetime).timestamp()),
    }
    key_id = signing_key_id(settings.jwt_secret)
    token = jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        headers={KEY_ID_HEADER: key_id},
    )
    expires_in = settings.access_token_minutes * SECONDS_PER_MINUTE
    logger.info(
        "security.access_issued",
        extra={
            "user_id": str(user_id),
            "role": role.value,
            "expires_in_seconds": expires_in,
            "algorithm": settings.jwt_algorithm,
            "key_id": key_id,
        },
    )
    return token, expires_in


def read_access_claims(token: str, *, now: datetime) -> AccessClaims:
    """Verify a token and return what it says about its holder.

    Args:
        token: The bearer token taken from the Authorization header.
        now: The current instant, from the clock. Expiry is checked against it.

    Raises:
        AuthenticationFailure: If the key identifier is unknown, or the
            signature, issuer, type, expiry, subject, role or branch is wrong.
            The message names the fault for the log.

    """
    key = _key_named_by(token)
    try:
        # Expiry is checked below against the clock. The library would check
        # it against the operating system, which a test cannot hold still.
        claims: dict[str, str | int | None] = jwt.decode(
            token,
            key,
            algorithms=[settings.jwt_algorithm],
            issuer=TOKEN_ISSUER,
            options={
                "require": ["exp", "iat", "sub", "iss"],
                "verify_exp": False,
                "verify_iat": False,
            },
        )
    except jwt.InvalidTokenError as exc:
        raise AuthenticationFailure(
            f"Attempted to authenticate with a token that failed verification: {exc}",
            {"reason": "invalid"},
        ) from exc

    expires_at = claims.get("exp")
    if not isinstance(expires_at, int) or now.timestamp() >= expires_at:
        raise AuthenticationFailure(
            "Attempted to authenticate with an expired access token.",
            {"reason": "expired"},
        )
    if claims.get("typ") != TOKEN_TYPE_ACCESS:
        raise AuthenticationFailure(
            "Attempted to authenticate with a token that is not an access token. "
            f"Token type claim was {claims.get('typ')!r}.",
            {"reason": "wrong-token-type"},
        )
    return _claims_of(claims)


def _claims_of(claims: dict[str, str | int | None]) -> AccessClaims:
    """Read the subject, the role and the branch out of a verified payload.

    Raises:
        AuthenticationFailure: If any of the three is missing or malformed.

    """
    branch = claims.get(CLAIM_BRANCH)
    try:
        return AccessClaims(
            subject=UUID(str(claims.get("sub", ""))),
            role=UserRole(str(claims.get(CLAIM_ROLE, ""))),
            branch_id=UUID(str(branch)) if branch is not None else None,
        )
    except ValueError as exc:
        raise AuthenticationFailure(
            "Attempted to authenticate with a token whose subject, role or branch claim "
            "is missing or malformed.",
            {"reason": "malformed-claims"},
        ) from exc


def _key_named_by(token: str) -> str:
    """Return the signing key a token names in its header.

    Raises:
        AuthenticationFailure: If the token cannot be read at all, or names a
            key this service does not hold.

    """
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise AuthenticationFailure(
            f"Attempted to authenticate with a token that failed verification: {exc}",
            {"reason": "invalid"},
        ) from exc
    key = _verification_keys().get(str(header.get(KEY_ID_HEADER, "")))
    if key is None:
        raise AuthenticationFailure(
            "Attempted to authenticate with a token signed by a key this service does not "
            "hold. Its key identifier is missing or unknown.",
            {"reason": "unknown-key"},
        )
    return key
