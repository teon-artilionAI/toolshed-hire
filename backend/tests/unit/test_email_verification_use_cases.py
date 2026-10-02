"""Proving an email address and asking for the link again, with no database (US-02, C-18).

A verification token works once, for a day, and only the newest one works.
Anything else is refused with one sentence, whatever the reason was. Asking
for the link again replaces the token, and an account that is already
verified is answered the same way and sent nothing.

The token is read out of the message the fake gateway was handed, which is
how a person gets it.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final
from uuid import uuid4

import pytest

from app.application.identity.email_verification import (
    EMAIL_VERIFIED_ACTION,
    VERIFICATION_LINK_INVALID_MESSAGE,
    VERIFICATION_RESENT_ACTION,
)
from app.domain.account import Account
from app.domain.account_tokens import EMAIL_VERIFICATION_LIFETIME
from app.domain.enums import UserRole
from app.domain.errors import AuthenticationFailure, TooManyAttempts, VerificationLinkInvalid
from app.infrastructure.notification import UnconfiguredEmailGateway
from tests.support.account_desk import NEW_EMAIL, VERIFY_KEY, AccountDesk

ONE_SECOND: Final[timedelta] = timedelta(seconds=1)
MADE_UP_TOKEN: Final[str] = "a-made-up-token-nobody-was-sent"


@pytest.fixture
def desk() -> AccountDesk:
    return AccountDesk()


@pytest.fixture
def account(desk: AccountDesk) -> Account:
    return desk.registered()


def refused(desk: AccountDesk, token: str) -> VerificationLinkInvalid:
    with pytest.raises(VerificationLinkInvalid) as refusal:
        desk.verify(token)
    return refusal.value


class TestRedeemingTheLink:
    """Once, for a day, and only the newest link."""

    def test_the_link_proves_the_address(self, desk: AccountDesk, account: Account) -> None:
        desk.clock.advance(timedelta(hours=3))
        desk.verify(desk.sent_token(VERIFY_KEY))
        stored = desk.account_for()
        assert stored.email_verified_at == desk.clock.now()
        assert stored.email_verification is None

    def test_proving_it_writes_one_audit_event(self, desk: AccountDesk, account: Account) -> None:
        desk.verify(desk.sent_token(VERIFY_KEY))
        (event,) = desk.audit(EMAIL_VERIFIED_ACTION)
        assert event.entity_id == account.id
        assert event.actor_user_id == account.id
        assert event.before_state == {"email_verified": False}
        assert event.after_state == {"email_verified": True}

    def test_a_used_link_is_refused(self, desk: AccountDesk, account: Account) -> None:
        token = desk.sent_token(VERIFY_KEY)
        desk.verify(token)
        refused(desk, token)

    def test_a_link_a_day_old_is_refused(self, desk: AccountDesk, account: Account) -> None:
        token = desk.sent_token(VERIFY_KEY)
        desk.clock.advance(EMAIL_VERIFICATION_LIFETIME)
        refused(desk, token)
        assert not desk.account_for().email_verified

    def test_a_link_a_second_short_of_a_day_still_works(
        self, desk: AccountDesk, account: Account
    ) -> None:
        token = desk.sent_token(VERIFY_KEY)
        desk.clock.advance(EMAIL_VERIFICATION_LIFETIME - ONE_SECOND)
        desk.verify(token)
        assert desk.account_for().email_verified

    def test_unknown_and_used_are_refused_in_the_same_words(
        self, desk: AccountDesk, account: Account
    ) -> None:
        token = desk.sent_token(VERIFY_KEY)
        unknown = refused(desk, MADE_UP_TOKEN)
        desk.verify(token)
        used = refused(desk, token)
        assert unknown.message == used.message == VERIFICATION_LINK_INVALID_MESSAGE
        assert unknown.detail == used.detail == {}

    def test_an_expired_link_is_refused_in_the_same_words(
        self, desk: AccountDesk, account: Account
    ) -> None:
        token = desk.sent_token(VERIFY_KEY)
        desk.clock.advance(EMAIL_VERIFICATION_LIFETIME)
        assert refused(desk, token).message == VERIFICATION_LINK_INVALID_MESSAGE

    def test_a_refusal_changes_nothing_and_writes_no_event(
        self, desk: AccountDesk, account: Account
    ) -> None:
        refused(desk, MADE_UP_TOKEN)
        assert desk.audit(EMAIL_VERIFIED_ACTION) == []
        assert desk.account_for().email_verification is not None

    def test_presenting_links_is_throttled_for_the_client(self, desk: AccountDesk) -> None:
        for _ in range(desk.account_rules.verification_address.limit):
            refused(desk, MADE_UP_TOKEN)
        with pytest.raises(TooManyAttempts):
            desk.verify(MADE_UP_TOKEN)


class TestAskingForTheLinkAgain:
    """A new token in place of the old one, or nothing for a verified account."""

    def test_a_new_link_is_sent_and_the_old_one_stops_working(
        self, desk: AccountDesk, account: Account
    ) -> None:
        first = desk.sent_token(VERIFY_KEY)
        expectation = desk.resend(account.id)
        second = desk.sent_token(VERIFY_KEY)
        assert expectation.email_deliverable is True
        assert len(desk.gateway.sent_to(NEW_EMAIL)) == 2
        assert first != second
        refused(desk, first)
        desk.verify(second)
        assert desk.account_for().email_verified

    def test_the_new_link_lasts_a_day_from_when_it_was_asked_for(
        self, desk: AccountDesk, account: Account
    ) -> None:
        desk.clock.advance(timedelta(hours=20))
        desk.resend(account.id)
        desk.clock.advance(timedelta(hours=20))
        desk.verify(desk.sent_token(VERIFY_KEY))
        assert desk.account_for().email_verified

    def test_asking_again_writes_one_audit_event(
        self, desk: AccountDesk, account: Account
    ) -> None:
        desk.resend(account.id)
        (event,) = desk.audit(VERIFICATION_RESENT_ACTION)
        assert (event.entity_id, event.actor_user_id) == (account.id, account.id)

    def test_a_verified_account_is_answered_the_same_and_sent_nothing(
        self, desk: AccountDesk, account: Account
    ) -> None:
        desk.verify(desk.sent_token(VERIFY_KEY))
        sent_before = len(desk.gateway.sent)
        expectation = desk.resend(account.id)
        assert expectation.email_deliverable is True
        assert len(desk.gateway.sent) == sent_before
        assert desk.audit(VERIFICATION_RESENT_ACTION) == []

    def test_any_signed_in_role_may_ask(self, desk: AccountDesk) -> None:
        assistant = desk.identity.add_account(
            email="lerato.khumalo@example.co.za", role=UserRole.COUNTER_STAFF
        )
        assert desk.resend(assistant.id, UserRole.COUNTER_STAFF).email_deliverable is True
        assert len(desk.gateway.sent_to("lerato.khumalo@example.co.za")) == 1

    def test_where_email_is_off_the_answer_says_nothing_will_arrive(self) -> None:
        desk = AccountDesk(gateway_override=UnconfiguredEmailGateway())
        account = desk.registered()
        assert desk.resend(account.id).email_deliverable is False

    def test_asking_is_throttled_for_the_account(
        self, desk: AccountDesk, account: Account
    ) -> None:
        for _ in range(desk.account_rules.resend_account.limit):
            desk.resend(account.id)
        with pytest.raises(TooManyAttempts):
            desk.resend(account.id)

    def test_an_account_that_no_longer_exists_is_refused(self, desk: AccountDesk) -> None:
        with pytest.raises(AuthenticationFailure):
            desk.resend(uuid4())
