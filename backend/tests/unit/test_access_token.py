"""The access token: its key identifier, its claims and its expiry (C-15, C-36).

A token names the key that signed it, carries the subject, the role and the
branch, and lives fifteen minutes. Each of those is pinned here against the
real signer, with the time held still by passing the instant in.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID, uuid4

import jwt
import pytest

from app.config import settings
from app.domain.enums import UserRole
from app.domain.errors import AuthenticationFailure
from app.infrastructure.security import (
    KEY_ID_HEADER,
    KEY_ID_LENGTH,
    TOKEN_ISSUER,
    TOKEN_TYPE_ACCESS,
    create_access_token,
    read_access_claims,
    signing_key_id,
)
from tests.support.tokens import (
    FOREIGN_SIGNING_KEY,
    mint_token_signed_with_a_foreign_key,
    tamper_with_signature,
)

ISSUED_AT: Final[datetime] = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
LIFETIME: Final[timedelta] = timedelta(minutes=15)
ONE_SECOND: Final[timedelta] = timedelta(seconds=1)
ACCOUNT_ID: Final[UUID] = uuid4()
BRANCH_ID: Final[UUID] = uuid4()
EXPECTED_CLAIMS: Final[set[str]] = {"sub", "role", "branch_id", "iss", "typ", "iat", "exp"}


def issue(role: UserRole = UserRole.COUNTER_STAFF, branch_id: UUID | None = BRANCH_ID) -> str:
    token, _expires_in = create_access_token(
        ACCOUNT_ID, role=role, branch_id=branch_id, issued_at=ISSUED_AT
    )
    return token


def unverified_payload(token: str) -> dict[str, object]:
    return jwt.decode(token, options={"verify_signature": False})


def reason_for(token: str, now: datetime = ISSUED_AT) -> object:
    with pytest.raises(AuthenticationFailure) as refusal:
        read_access_claims(token, now=now)
    return refusal.value.detail["reason"]


def signed_like_the_server(payload: dict[str, object]) -> str:
    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        headers={KEY_ID_HEADER: signing_key_id(settings.jwt_secret)},
    )


class TestTheKeyIdentifier:
    """The header names the signing key, and an unknown name is refused."""

    def test_the_header_carries_a_kid_derived_from_the_key(self) -> None:
        header = jwt.get_unverified_header(issue())
        digest = hashlib.sha256(settings.jwt_secret.encode("utf-8")).hexdigest()
        assert header[KEY_ID_HEADER] == digest[:KEY_ID_LENGTH]

    def test_the_kid_does_not_hold_the_key(self) -> None:
        assert signing_key_id(settings.jwt_secret) not in settings.jwt_secret
        assert settings.jwt_secret not in signing_key_id(settings.jwt_secret)

    def test_two_keys_have_two_identifiers(self) -> None:
        assert signing_key_id(settings.jwt_secret) != signing_key_id(FOREIGN_SIGNING_KEY)

    def test_a_token_naming_an_unknown_key_is_refused(self) -> None:
        assert reason_for(mint_token_signed_with_a_foreign_key(ACCOUNT_ID)) == "unknown-key"

    def test_a_token_with_no_kid_at_all_is_refused(self) -> None:
        bare = jwt.encode(
            unverified_payload(issue()), settings.jwt_secret, algorithm=settings.jwt_algorithm
        )
        assert reason_for(bare) == "unknown-key"

    def test_a_foreign_signature_under_the_servers_kid_is_refused(self) -> None:
        forged = mint_token_signed_with_a_foreign_key(
            ACCOUNT_ID, key_id=signing_key_id(settings.jwt_secret)
        )
        assert reason_for(forged, now=datetime.now(UTC)) == "invalid"

    def test_something_that_is_not_a_token_is_refused(self) -> None:
        assert reason_for("not-a-token-at-all") == "invalid"


class TestTheClaims:
    """`sub`, `role` and `branch_id`, and nothing that was not asked for."""

    def test_the_payload_carries_exactly_the_documented_claims(self) -> None:
        payload = unverified_payload(issue())
        assert payload.keys() == EXPECTED_CLAIMS
        assert payload["sub"] == str(ACCOUNT_ID)
        assert payload["role"] == UserRole.COUNTER_STAFF.value
        assert payload["branch_id"] == str(BRANCH_ID)
        assert payload["iss"] == TOKEN_ISSUER
        assert payload["typ"] == TOKEN_TYPE_ACCESS

    def test_an_account_with_no_branch_carries_a_null_branch(self) -> None:
        payload = unverified_payload(issue(role=UserRole.CUSTOMER, branch_id=None))
        assert payload["branch_id"] is None

    def test_verification_returns_the_three_claims_typed(self) -> None:
        claims = read_access_claims(issue(), now=ISSUED_AT)
        assert claims.subject == ACCOUNT_ID
        assert claims.role is UserRole.COUNTER_STAFF
        assert claims.branch_id == BRANCH_ID

    def test_a_token_with_a_role_nobody_holds_is_refused(self) -> None:
        payload = unverified_payload(issue())
        payload["role"] = "SUPERUSER"
        assert reason_for(signed_like_the_server(payload)) == "malformed-claims"

    def test_a_token_whose_subject_is_not_a_uuid_is_refused(self) -> None:
        payload = unverified_payload(issue())
        payload["sub"] = "not-a-uuid"
        assert reason_for(signed_like_the_server(payload)) == "malformed-claims"

    def test_a_token_of_another_type_is_refused(self) -> None:
        payload = unverified_payload(issue())
        payload["typ"] = "refresh"
        assert reason_for(signed_like_the_server(payload)) == "wrong-token-type"

    def test_a_token_whose_signature_was_edited_is_refused(self) -> None:
        assert reason_for(tamper_with_signature(issue())) == "invalid"


class TestTheLifetime:
    """Fifteen minutes, checked against the clock and not the operating system."""

    def test_the_token_lives_for_the_configured_fifteen_minutes(self) -> None:
        _token, expires_in = create_access_token(
            ACCOUNT_ID, role=UserRole.CUSTOMER, branch_id=None, issued_at=ISSUED_AT
        )
        payload = unverified_payload(issue())
        assert expires_in == int(LIFETIME.total_seconds())
        assert payload["iat"] == int(ISSUED_AT.timestamp())
        assert payload["exp"] == int((ISSUED_AT + LIFETIME).timestamp())

    def test_it_is_accepted_until_the_last_second(self) -> None:
        claims = read_access_claims(issue(), now=ISSUED_AT + LIFETIME - ONE_SECOND)
        assert claims.subject == ACCOUNT_ID

    def test_it_is_refused_from_the_moment_it_expires(self) -> None:
        assert reason_for(issue(), now=ISSUED_AT + LIFETIME) == "expired"

    def test_a_token_with_no_expiry_is_refused(self) -> None:
        payload = unverified_payload(issue())
        del payload["exp"]
        assert reason_for(signed_like_the_server(payload)) == "invalid"
