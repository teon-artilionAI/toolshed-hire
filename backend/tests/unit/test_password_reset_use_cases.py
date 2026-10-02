"""The two halves of a password reset, with no database (US-04, BR-45, C-18, R-13).

Asking for a reset is answered the same way whatever the address, with the
same work done. Only an address with an active account is sent a link. The
link works once, for an hour, and only the newest one works. Using it sets the
new password, ends every session of the account and lifts any lock, all in
one transaction with one audit event.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

import pytest

from app.application.identity.password_reset import (
    RESET_COMPLETED_ACTION,
    RESET_LINK_INVALID_MESSAGE,
    RESET_REQUESTED_ACTION,
    RESET_REVOKE_REASON,
)
from app.application.identity.sign_in import UNKNOWN_ACCOUNT_ID
from app.application.refusal import refused_parameter_of
from app.domain.account import LOCKOUT_DURATION, MAXIMUM_FAILED_LOGINS, Account
from app.domain.account_tokens import PASSWORD_RESET_LIFETIME, hash_account_token
from app.domain.enums import RevokeReason
from app.domain.errors import ResetLinkInvalid, TooManyAttempts, ValidationFailure
from tests.support.account_desk import NEW_PASSWORD, RESET_KEY, AccountDesk
from tests.support.memory_crypto import fake_hash
from tests.support.memory_identity import KNOWN_EMAIL, KNOWN_PASSWORD

ONE_SECOND: Final[timedelta] = timedelta(seconds=1)
UNKNOWN_ADDRESS: Final[str] = "nobody.at.all@example.co.za"
MADE_UP_TOKEN: Final[str] = "a-made-up-token-nobody-was-sent"


@pytest.fixture
def desk() -> AccountDesk:
    return AccountDesk()


@pytest.fixture
def account(desk: AccountDesk) -> Account:
    return desk.identity.add_account()


def refused(desk: AccountDesk, token: str) -> ResetLinkInvalid:
    with pytest.raises(ResetLinkInvalid) as refusal:
        desk.complete_reset(token)
    return refusal.value


class TestAskingForAReset:
    """The same answer for every address, and a link only for an active account."""

    def test_an_address_with_an_account_is_sent_a_link(
        self, desk: AccountDesk, account: Account
    ) -> None:
        expectation = desk.request_reset()
        (message,) = desk.gateway.sent_to(KNOWN_EMAIL)
        token = desk.sent_token(RESET_KEY)
        pending = desk.identity.account(account.id).password_reset
        assert expectation.email_deliverable is True
        assert pending is not None
        assert pending.token_hash == hash_account_token(token)
        assert pending.expires_at == desk.clock.now() + PASSWORD_RESET_LIFETIME
        assert "/signin#reset=" in message.text_body

    def test_the_address_is_matched_whatever_its_case(
        self, desk: AccountDesk, account: Account
    ) -> None:
        desk.request_reset(email=f"  {KNOWN_EMAIL.upper()} ")
        assert len(desk.gateway.sent_to(KNOWN_EMAIL)) == 1

    def test_an_unknown_address_gets_the_same_answer_and_no_message(
        self, desk: AccountDesk, account: Account
    ) -> None:
        known = desk.request_reset()
        unknown = desk.request_reset(email=UNKNOWN_ADDRESS)
        assert known == unknown
        assert desk.gateway.sent_to(UNKNOWN_ADDRESS) == []

    def test_both_paths_write_one_audit_event(self, desk: AccountDesk, account: Account) -> None:
        desk.request_reset()
        desk.request_reset(email=UNKNOWN_ADDRESS)
        known, unknown = desk.audit(RESET_REQUESTED_ACTION)
        assert (known.entity_id, known.after_state) == (account.id, {"link_issued": True})
        assert (unknown.entity_id, unknown.after_state) == (
            UNKNOWN_ACCOUNT_ID,
            {"link_issued": False},
        )

    def test_a_deactivated_account_is_answered_the_same_and_sent_nothing(
        self, desk: AccountDesk
    ) -> None:
        deactivated = desk.identity.add_account(is_active=False)
        assert desk.request_reset().email_deliverable is True
        assert desk.gateway.sent == []
        assert desk.identity.account(deactivated.id).password_reset is None

    def test_asking_is_throttled_for_the_address(self, desk: AccountDesk) -> None:
        for _ in range(desk.account_rules.reset_request_email.limit):
            desk.request_reset(email=UNKNOWN_ADDRESS)
        with pytest.raises(TooManyAttempts):
            desk.request_reset(email=UNKNOWN_ADDRESS)
        assert len(desk.audit(RESET_REQUESTED_ACTION)) == (
            desk.account_rules.reset_request_email.limit
        )


class TestUsingTheLink:
    """The new password, every session ended, the lock lifted, and one event."""

    @pytest.fixture
    def token(self, desk: AccountDesk, account: Account) -> str:
        desk.request_reset()
        return desk.sent_token(RESET_KEY)

    def test_the_new_password_replaces_the_old_one(
        self, desk: AccountDesk, account: Account, token: str
    ) -> None:
        desk.complete_reset(token)
        stored = desk.identity.account(account.id)
        assert stored.password_hash == fake_hash(NEW_PASSWORD)
        assert stored.password_reset is None
        assert desk.sign_in(password=NEW_PASSWORD).account.id == account.id
        desk.sign_in_refused(password=KNOWN_PASSWORD)

    def test_every_session_of_the_account_is_ended(
        self, desk: AccountDesk, account: Account, token: str
    ) -> None:
        desk.sign_in()
        desk.sign_in()
        desk.complete_reset(token)
        assert desk.revoke_reasons() == [RevokeReason.LOGOUT, RevokeReason.LOGOUT]
        assert RESET_REVOKE_REASON is RevokeReason.LOGOUT

    def test_a_lock_is_lifted(self, desk: AccountDesk, account: Account, token: str) -> None:
        stored = desk.identity.account(account.id)
        stored.failed_login_count = MAXIMUM_FAILED_LOGINS
        stored.locked_until = desk.clock.now() + LOCKOUT_DURATION
        desk.complete_reset(token)
        assert desk.sign_in(password=NEW_PASSWORD).account.id == account.id

    def test_one_audit_event_says_what_the_reset_did(
        self, desk: AccountDesk, account: Account, token: str
    ) -> None:
        desk.sign_in()
        desk.complete_reset(token)
        (event,) = desk.audit(RESET_COMPLETED_ACTION)
        assert (event.entity_id, event.actor_user_id) == (account.id, account.id)
        assert event.before_state == {"locked": False}
        assert event.after_state == {
            "locked": False,
            "revoked_session_count": 1,
            "revoke_reason": RevokeReason.LOGOUT.value,
        }

    def test_a_used_link_is_refused(self, desk: AccountDesk, token: str) -> None:
        desk.complete_reset(token)
        assert refused(desk, token).message == RESET_LINK_INVALID_MESSAGE

    def test_a_link_an_hour_old_is_refused_and_changes_nothing(
        self, desk: AccountDesk, account: Account, token: str
    ) -> None:
        desk.clock.advance(PASSWORD_RESET_LIFETIME)
        assert refused(desk, token).message == RESET_LINK_INVALID_MESSAGE
        assert desk.identity.account(account.id).password_hash == fake_hash(KNOWN_PASSWORD)
        assert desk.audit(RESET_COMPLETED_ACTION) == []

    def test_a_link_a_second_short_of_an_hour_still_works(
        self, desk: AccountDesk, token: str
    ) -> None:
        desk.clock.advance(PASSWORD_RESET_LIFETIME - ONE_SECOND)
        desk.complete_reset(token)

    def test_a_link_nobody_was_sent_is_refused_in_the_same_words(self, desk: AccountDesk) -> None:
        assert refused(desk, MADE_UP_TOKEN).message == RESET_LINK_INVALID_MESSAGE

    def test_a_second_request_replaces_the_first_link(
        self, desk: AccountDesk, account: Account, token: str
    ) -> None:
        desk.request_reset()
        newest = desk.sent_token(RESET_KEY)
        refused(desk, token)
        desk.complete_reset(newest)

    def test_a_new_password_under_twelve_characters_is_refused_by_name(
        self, desk: AccountDesk, token: str
    ) -> None:
        with pytest.raises(ValidationFailure) as refusal:
            desk.complete_reset(token, new_password="elevenchars")
        assert refused_parameter_of(refusal.value) == "newPassword"
        assert desk.hasher.call_count == 0
        desk.complete_reset(token)

    def test_using_links_is_throttled_for_the_client(self, desk: AccountDesk) -> None:
        for _ in range(desk.account_rules.reset_completion_address.limit):
            refused(desk, MADE_UP_TOKEN)
        with pytest.raises(TooManyAttempts):
            desk.complete_reset(MADE_UP_TOKEN)
