"""The single use tokens of an account, with nothing around them (C-18).

A verification token and a reset token follow the same three rules. Each works
once, each stops working when its time is up, and a new one replaces the old
one. These prove the three against the account entity and a moment in time
the test chooses. No database, no HTTP and no hashing of passwords.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import uuid4

from app.domain.account import LOCKOUT_DURATION, MAXIMUM_FAILED_LOGINS, Account
from app.domain.account_tokens import (
    ACCOUNT_TOKEN_BYTES,
    EMAIL_VERIFICATION_LIFETIME,
    PASSWORD_RESET_LIFETIME,
    PendingToken,
    hash_account_token,
    mint_account_token,
)
from app.domain.enums import UserRole

NOW: Final[datetime] = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
ONE_SECOND: Final[timedelta] = timedelta(seconds=1)
FAKE_TOKEN: Final[str] = "made-up-account-token-for-this-test"
OTHER_FAKE_TOKEN: Final[str] = "another-made-up-account-token"
OLD_HASH: Final[str] = "stand-in-hash-of-the-old-password"
NEW_HASH: Final[str] = "stand-in-hash-of-the-new-password"
SHA256_HEX_LENGTH: Final[int] = 64
MINIMUM_TOKEN_BYTES: Final[int] = 32
BITS_PER_BYTE: Final[int] = 8
BITS_PER_URLSAFE_CHARACTER: Final[int] = 6
MINTED_SAMPLE: Final[int] = 50


def account() -> Account:
    return Account(
        id=uuid4(),
        email="thandi.mokoena@example.co.za",
        password_hash=OLD_HASH,
        role=UserRole.CUSTOMER,
        full_name="Thandi Mokoena",
    )


def awaiting_verification(token: str = FAKE_TOKEN) -> Account:
    subject = account()
    subject.start_email_verification(PendingToken.for_email_verification(token, NOW))
    return subject


def awaiting_reset(token: str = FAKE_TOKEN) -> Account:
    subject = account()
    subject.start_password_reset(PendingToken.for_password_reset(token, NOW))
    return subject


class TestTheToken:
    """Random, at least 32 bytes and stored only as its SHA-256."""

    def test_a_token_carries_at_least_32_bytes(self) -> None:
        assert ACCOUNT_TOKEN_BYTES >= MINIMUM_TOKEN_BYTES
        bits = len(mint_account_token()) * BITS_PER_URLSAFE_CHARACTER
        assert bits >= MINIMUM_TOKEN_BYTES * BITS_PER_BYTE

    def test_no_two_tokens_are_the_same(self) -> None:
        assert len({mint_account_token() for _ in range(MINTED_SAMPLE)}) == MINTED_SAMPLE

    def test_the_stored_form_is_the_sha256_of_the_token(self) -> None:
        digest = hash_account_token(FAKE_TOKEN)
        assert digest == hashlib.sha256(FAKE_TOKEN.encode("utf-8")).hexdigest()
        assert len(digest) == SHA256_HEX_LENGTH
        assert FAKE_TOKEN not in digest

    def test_what_is_kept_is_the_hash_and_the_moment_it_stops_working(self) -> None:
        pending = PendingToken.issued(FAKE_TOKEN, now=NOW, lifetime=timedelta(minutes=5))
        assert pending.token_hash == hash_account_token(FAKE_TOKEN)
        assert pending.expires_at == NOW + timedelta(minutes=5)

    def test_the_hash_is_left_out_of_the_representation(self) -> None:
        pending = PendingToken.for_password_reset(FAKE_TOKEN, NOW)
        assert hash_account_token(FAKE_TOKEN) not in repr(pending)
        assert hash_account_token(FAKE_TOKEN) not in repr(awaiting_reset())

    def test_the_two_lifetimes_are_a_day_and_an_hour(self) -> None:
        assert timedelta(hours=24) == EMAIL_VERIFICATION_LIFETIME
        assert timedelta(minutes=60) == PASSWORD_RESET_LIFETIME
        verification = PendingToken.for_email_verification(FAKE_TOKEN, NOW)
        reset = PendingToken.for_password_reset(FAKE_TOKEN, NOW)
        assert verification.expires_at == NOW + EMAIL_VERIFICATION_LIFETIME
        assert reset.expires_at == NOW + PASSWORD_RESET_LIFETIME

    def test_a_token_is_accepted_until_the_instant_its_time_is_up(self) -> None:
        pending = PendingToken.for_password_reset(FAKE_TOKEN, NOW)
        last_moment = NOW + PASSWORD_RESET_LIFETIME - ONE_SECOND
        assert pending.accepts(FAKE_TOKEN, last_moment)
        assert not pending.is_expired(last_moment)
        assert pending.is_expired(NOW + PASSWORD_RESET_LIFETIME)
        assert not pending.accepts(FAKE_TOKEN, NOW + PASSWORD_RESET_LIFETIME)

    def test_another_token_is_not_accepted(self) -> None:
        pending = PendingToken.for_password_reset(FAKE_TOKEN, NOW)
        assert not pending.accepts(OTHER_FAKE_TOKEN, NOW)


class TestTheVerificationToken:
    """Single use, a day long and replaced by the next one."""

    def test_a_new_account_is_a_customer_with_an_unproved_address(self) -> None:
        subject = Account.registered_customer(
            email="thandi.mokoena@example.co.za",
            password_hash=OLD_HASH,
            full_name="Thandi Mokoena",
            phone="082 441 7719",
        )
        assert subject.role is UserRole.CUSTOMER
        assert subject.is_active
        assert not subject.email_verified
        assert subject.branch_id is None
        assert subject.phone == "082 441 7719"

    def test_redeeming_it_proves_the_address_and_clears_the_token(self) -> None:
        subject = awaiting_verification()
        assert subject.verify_email(FAKE_TOKEN, NOW + ONE_SECOND) is True
        assert subject.email_verified_at == NOW + ONE_SECOND
        assert subject.email_verification is None

    def test_it_works_once(self) -> None:
        subject = awaiting_verification()
        subject.verify_email(FAKE_TOKEN, NOW)
        assert subject.verify_email(FAKE_TOKEN, NOW) is False

    def test_it_stops_working_after_a_day(self) -> None:
        subject = awaiting_verification()
        assert subject.verify_email(FAKE_TOKEN, NOW + EMAIL_VERIFICATION_LIFETIME) is False
        assert not subject.email_verified
        assert subject.email_verification is not None

    def test_a_token_that_was_never_issued_changes_nothing(self) -> None:
        subject = awaiting_verification()
        assert subject.verify_email(OTHER_FAKE_TOKEN, NOW) is False
        assert account().verify_email(FAKE_TOKEN, NOW) is False
        assert not subject.email_verified

    def test_a_new_token_replaces_the_old_one(self) -> None:
        subject = awaiting_verification()
        subject.start_email_verification(
            PendingToken.for_email_verification(OTHER_FAKE_TOKEN, NOW)
        )
        assert subject.verify_email(FAKE_TOKEN, NOW) is False
        assert subject.verify_email(OTHER_FAKE_TOKEN, NOW) is True

    def test_verifying_again_keeps_the_first_moment_the_address_was_proved(self) -> None:
        subject = awaiting_verification()
        subject.verify_email(FAKE_TOKEN, NOW)
        subject.start_email_verification(
            PendingToken.for_email_verification(OTHER_FAKE_TOKEN, NOW)
        )
        assert subject.verify_email(OTHER_FAKE_TOKEN, NOW + ONE_SECOND) is True
        assert subject.email_verified_at == NOW


class TestTheResetToken:
    """Single use, an hour long and replaced by the next one."""

    def test_redeeming_it_takes_the_new_hash_and_clears_the_token(self) -> None:
        subject = awaiting_reset()
        assert subject.reset_password(FAKE_TOKEN, NEW_HASH, NOW) is True
        assert subject.password_hash == NEW_HASH
        assert subject.password_reset is None

    def test_it_works_once(self) -> None:
        subject = awaiting_reset()
        subject.reset_password(FAKE_TOKEN, NEW_HASH, NOW)
        assert subject.reset_password(FAKE_TOKEN, "a-third-stand-in-hash", NOW) is False
        assert subject.password_hash == NEW_HASH

    def test_it_stops_working_after_an_hour(self) -> None:
        subject = awaiting_reset()
        assert subject.reset_password(FAKE_TOKEN, NEW_HASH, NOW + PASSWORD_RESET_LIFETIME) is False
        assert subject.password_hash == OLD_HASH
        assert subject.password_reset is not None

    def test_a_token_that_was_never_issued_changes_nothing(self) -> None:
        subject = awaiting_reset()
        assert subject.reset_password(OTHER_FAKE_TOKEN, NEW_HASH, NOW) is False
        assert account().reset_password(FAKE_TOKEN, NEW_HASH, NOW) is False
        assert subject.password_hash == OLD_HASH

    def test_a_new_token_replaces_the_old_one(self) -> None:
        subject = awaiting_reset()
        subject.start_password_reset(PendingToken.for_password_reset(OTHER_FAKE_TOKEN, NOW))
        assert subject.reset_password(FAKE_TOKEN, NEW_HASH, NOW) is False
        assert subject.reset_password(OTHER_FAKE_TOKEN, NEW_HASH, NOW) is True

    def test_redeeming_it_lifts_a_lock_and_forgets_the_failures(self) -> None:
        subject = awaiting_reset()
        subject.failed_login_count = MAXIMUM_FAILED_LOGINS
        subject.locked_until = NOW + LOCKOUT_DURATION
        subject.reset_password(FAKE_TOKEN, NEW_HASH, NOW)
        assert not subject.is_locked(NOW)
        assert subject.failed_login_count == 0

    def test_a_refused_token_leaves_the_lock_where_it_was(self) -> None:
        subject = awaiting_reset()
        subject.locked_until = NOW + LOCKOUT_DURATION
        subject.reset_password(OTHER_FAKE_TOKEN, NEW_HASH, NOW)
        assert subject.is_locked(NOW)

    def test_the_two_tokens_are_kept_apart(self) -> None:
        subject = awaiting_reset()
        assert subject.verify_email(FAKE_TOKEN, NOW) is False
        assert subject.password_reset is not None
