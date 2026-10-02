"""The three account messages, the mailer that sends them and what a gateway will deliver.

A verification link and a reset link carry their token in the fragment, in the
exact form the screens read. The third message goes to an address somebody
tried to register twice and carries no token at all (C-18, R-13).

The mailer hands each message to the gateway and never raises, whatever the
gateway does, because the account or the token is already committed when a
message is sent. The log says what kind of message it was and what became of
it, and never the address or the token.

A gateway also says whether it would deliver to an address. The Resend adapter
says no when one recipient is allowed and this is not it, the gateway that
sends nothing says no to everybody and the fake says yes.
"""

from __future__ import annotations

import logging
from typing import Final

import httpx
import pytest
from pydantic import SecretStr

from app.application.identity.account_mail import (
    ALREADY_REGISTERED_KIND,
    RESET_KIND,
    VERIFICATION_KIND,
    AccountMailer,
)
from app.application.notification.ports import DeliveryReceipt
from app.domain.account_messages import (
    ALREADY_REGISTERED_SUBJECT,
    RESET_SUBJECT,
    VERIFICATION_SUBJECT,
    already_registered_message,
    lifetime_in_words,
    password_reset_link,
    password_reset_message,
    verification_link,
    verification_message,
)
from app.domain.account_tokens import EMAIL_VERIFICATION_LIFETIME, PASSWORD_RESET_LIFETIME
from app.domain.notification import EmailMessage
from app.infrastructure.notification import (
    FakeEmailGateway,
    ResendEmailAdapter,
    UnconfiguredEmailGateway,
)

ORIGIN: Final[str] = "https://toolshed-hire.example.test"
RECIPIENT: Final[str] = "thandi.mokoena@example.co.za"
ALLOWED_RECIPIENT: Final[str] = "demo.inbox@example.co.za"
FAKE_TOKEN: Final[str] = "made-up-account-token-for-this-test"
MADE_UP_KEY: Final[str] = "made-up-resend-key-for-this-test"
SENDER: Final[str] = "Toolshed Hire <bookings@example.co.za>"
SEND_FINISHED: Final[str] = "account_mail.send_finished"
GATEWAY_FAULT: Final[str] = "account_mail.gateway_fault"


class BrokenGateway:
    """A gateway that breaks its contract and raises."""

    def send(self, message: EmailMessage) -> DeliveryReceipt:
        raise RuntimeError("could not reach the provider")

    def delivers_to(self, address: str) -> bool:
        return True


def resend_adapter(allowed_recipient: str | None) -> ResendEmailAdapter:
    """Return the Resend adapter on a transport that accepts everything."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"id": "made-up-provider-message-id"})
    )
    return ResendEmailAdapter(
        api_key=SecretStr(MADE_UP_KEY),
        sender=SENDER,
        allowed_recipient=allowed_recipient,
        transport=transport,
    )


class TestTheLinks:
    """The token rides in the fragment, in the form the screens read."""

    def test_the_verification_link_opens_the_register_screen(self) -> None:
        assert verification_link(ORIGIN, FAKE_TOKEN) == f"{ORIGIN}/register#verify={FAKE_TOKEN}"

    def test_the_reset_link_opens_the_sign_in_screen(self) -> None:
        assert password_reset_link(ORIGIN, FAKE_TOKEN) == f"{ORIGIN}/signin#reset={FAKE_TOKEN}"

    def test_a_lifetime_reads_as_hours_or_as_minutes(self) -> None:
        assert lifetime_in_words(EMAIL_VERIFICATION_LIFETIME) == "24 hours"
        assert lifetime_in_words(PASSWORD_RESET_LIFETIME) == "60 minutes"


class TestTheMessages:
    """Who each goes to, what it says and what it carries."""

    def test_the_verification_message_carries_its_link_and_its_lifetime(self) -> None:
        message = verification_message(to=RECIPIENT, frontend_origin=ORIGIN, token=FAKE_TOKEN)
        assert (message.to, message.subject) == (RECIPIENT, VERIFICATION_SUBJECT)
        assert f"{ORIGIN}/register#verify={FAKE_TOKEN}" in message.text_body
        assert "24 hours" in message.text_body

    def test_the_reset_message_carries_its_link_and_its_lifetime(self) -> None:
        message = password_reset_message(to=RECIPIENT, frontend_origin=ORIGIN, token=FAKE_TOKEN)
        assert (message.to, message.subject) == (RECIPIENT, RESET_SUBJECT)
        assert f"{ORIGIN}/signin#reset={FAKE_TOKEN}" in message.text_body
        assert "60 minutes" in message.text_body

    def test_the_note_for_a_repeated_registration_carries_no_token(self) -> None:
        message = already_registered_message(to=RECIPIENT, frontend_origin=ORIGIN)
        assert (message.to, message.subject) == (RECIPIENT, ALREADY_REGISTERED_SUBJECT)
        assert "#" not in message.text_body
        assert f"{ORIGIN}/signin" in message.text_body
        assert "already has one" in message.text_body
        assert "reset" in message.text_body


class TestTheMailer:
    """Each message goes to the gateway, and nothing the gateway does is raised."""

    def test_each_kind_of_message_is_handed_to_the_gateway(self) -> None:
        gateway = FakeEmailGateway()
        mailer = AccountMailer(gateway, ORIGIN)
        mailer.send_verification(to=RECIPIENT, token=FAKE_TOKEN)
        mailer.send_password_reset(to=RECIPIENT, token=FAKE_TOKEN)
        mailer.send_already_registered(to=RECIPIENT)
        assert [message.subject for message in gateway.sent_to(RECIPIENT)] == [
            VERIFICATION_SUBJECT,
            RESET_SUBJECT,
            ALREADY_REGISTERED_SUBJECT,
        ]

    def test_a_message_the_provider_refused_is_logged_and_not_raised(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        mailer = AccountMailer(FakeEmailGateway("Resend answered 500."), ORIGIN)
        with caplog.at_level(logging.INFO):
            mailer.send_password_reset(to=RECIPIENT, token=FAKE_TOKEN)
        (finished,) = [r for r in caplog.records if r.getMessage() == SEND_FINISHED]
        assert finished.levelno == logging.WARNING
        assert finished.__dict__["kind"] == RESET_KIND
        assert finished.__dict__["accepted"] is False
        assert finished.__dict__["failure_reason"] == "Resend answered 500."

    def test_a_gateway_that_raises_is_logged_and_not_raised(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        mailer = AccountMailer(BrokenGateway(), ORIGIN)
        with caplog.at_level(logging.INFO):
            mailer.send_already_registered(to=RECIPIENT)
        (fault,) = [r for r in caplog.records if r.getMessage() == GATEWAY_FAULT]
        assert fault.levelno == logging.ERROR
        assert fault.__dict__["kind"] == ALREADY_REGISTERED_KIND
        assert fault.exc_info is not None

    def test_the_log_holds_neither_the_address_nor_the_token(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        mailer = AccountMailer(FakeEmailGateway(), ORIGIN)
        with caplog.at_level(logging.DEBUG):
            mailer.send_verification(to=RECIPIENT, token=FAKE_TOKEN)
        written = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
        assert VERIFICATION_KIND in written
        assert RECIPIENT not in written
        assert FAKE_TOKEN not in written

    def test_what_to_expect_comes_from_the_gateway(self) -> None:
        open_mailer = AccountMailer(FakeEmailGateway(), ORIGIN)
        closed_mailer = AccountMailer(UnconfiguredEmailGateway(), ORIGIN)
        assert open_mailer.expectation_for(RECIPIENT).email_deliverable is True
        assert closed_mailer.expectation_for(RECIPIENT).email_deliverable is False


class TestWhatAGatewayWillDeliver:
    """The answer depends on the configuration and the address, and on nothing else."""

    def test_resend_delivers_to_anybody_when_no_recipient_is_set(self) -> None:
        assert resend_adapter(None).delivers_to(RECIPIENT) is True

    def test_resend_delivers_only_to_the_allowed_recipient_when_one_is_set(self) -> None:
        adapter = resend_adapter(ALLOWED_RECIPIENT)
        assert adapter.delivers_to(RECIPIENT) is False
        assert adapter.delivers_to(f"  {ALLOWED_RECIPIENT.upper()} ") is True

    def test_what_resend_says_matches_what_it_then_does(self) -> None:
        adapter = resend_adapter(ALLOWED_RECIPIENT)
        for address in (RECIPIENT, ALLOWED_RECIPIENT):
            message = EmailMessage(to=address, subject="s", text_body="b")
            assert adapter.send(message).accepted is adapter.delivers_to(address)

    def test_the_gateway_that_sends_nothing_delivers_to_nobody(self) -> None:
        assert UnconfiguredEmailGateway().delivers_to(RECIPIENT) is False

    def test_the_fake_delivers_to_everybody(self) -> None:
        assert FakeEmailGateway().delivers_to(RECIPIENT) is True
