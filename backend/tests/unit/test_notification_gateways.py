"""Which gateway a configuration gets, and the two gateways that are not Resend.

The application has to start before its email account exists. With
`RESEND_API_KEY` unset, or still holding the placeholder a new deployment is
given, the gateway in use sends nothing and says so in its receipt. These tests
pin that choice from the environment variable all the way to the receipt, and
they prove that no request is made on that path.

The fake gateway is pinned here too. Every other test trusts it to behave like
a gateway, so it gets tests of its own.
"""

from __future__ import annotations

import logging
from typing import Final

import httpx
import pytest

from app.application.notification.ports import NotificationGateway
from app.config import DEFAULT_EMAIL_FROM, RESEND_API_KEY_PLACEHOLDER, Environment
from app.domain.notification import EmailMessage
from app.infrastructure.notification import (
    FakeEmailGateway,
    ResendEmailAdapter,
    UnconfiguredEmailGateway,
    build_notification_gateway,
)
from app.infrastructure.notification.gateways import EMAIL_NOT_CONFIGURED_REASON
from tests.support.request_probe import settings_for

MADE_UP_KEY: Final[str] = "made-up-resend-key-for-this-test"
RECIPIENT: Final[str] = "nomsa.dlamini@example.co.za"
ALLOWED_RECIPIENT: Final[str] = "demo.inbox@example.co.za"
MESSAGE: Final[EmailMessage] = EmailMessage(
    to=RECIPIENT, subject="Your Toolshed Hire booking TSH-R-26-000124", text_body="Thank you."
)
NOT_CONFIGURED_WARNING: Final[str] = "notification.email_not_configured"


class CountingTransport:
    """A transport that counts the requests it is asked to make and accepts them all."""

    def __init__(self) -> None:
        """Start with no requests made."""
        self.request_count = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        """Count the request and accept it."""
        self.request_count += 1
        return httpx.Response(200, json={"id": "made-up-provider-message-id"})

    def as_transport(self) -> httpx.MockTransport:
        """Return the httpx transport that calls this counter."""
        return httpx.MockTransport(self.handler)


def gateway_from_environment(counter: CountingTransport, **variables: str) -> NotificationGateway:
    """Build the gateway the way the application factory does, from loaded settings."""
    configuration = settings_for(Environment.TEST, **variables)
    return build_notification_gateway(
        api_key=configuration.resend_api_key,
        sender=configuration.email_from,
        allowed_recipient=configuration.email_allowed_recipient,
        transport=counter.as_transport(),
    )


class TestTheEmailSettings:
    """RESEND_API_KEY, EMAIL_FROM and EMAIL_ALLOWED_RECIPIENT, as config.py reads them."""

    def test_with_no_key_set_email_is_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        configuration = settings_for(Environment.TEST)
        assert configuration.resend_api_key is None
        assert not configuration.email_configured

    @pytest.mark.parametrize("value", [RESEND_API_KEY_PLACEHOLDER, "", "   "])
    def test_the_placeholder_and_a_blank_value_count_as_no_key(self, value: str) -> None:
        assert RESEND_API_KEY_PLACEHOLDER == "not-configured-yet"
        assert not settings_for(Environment.PRODUCTION, RESEND_API_KEY=value).email_configured

    def test_a_real_key_is_kept_and_is_not_shown_when_the_settings_are_printed(self) -> None:
        configuration = settings_for(Environment.TEST, RESEND_API_KEY=MADE_UP_KEY)
        assert configuration.email_configured
        assert configuration.resend_api_key is not None
        assert configuration.resend_api_key.get_secret_value() == MADE_UP_KEY
        assert MADE_UP_KEY not in repr(configuration)

    def test_a_deployed_environment_still_starts_with_no_key(self) -> None:
        """Email being off is not a reason to refuse to start."""
        for environment in (Environment.STAGING, Environment.PRODUCTION):
            assert not settings_for(environment, RESEND_API_KEY="").email_configured

    def test_the_sender_defaults_to_the_address_that_needs_no_verified_domain(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("EMAIL_FROM", raising=False)
        assert settings_for(Environment.TEST).email_from == DEFAULT_EMAIL_FROM
        assert DEFAULT_EMAIL_FROM == "Toolshed Hire <onboarding@resend.dev>"
        assert settings_for(Environment.TEST, EMAIL_FROM="  ").email_from == DEFAULT_EMAIL_FROM

    def test_the_sender_can_be_set(self) -> None:
        sender = "Toolshed Hire <bookings@example.co.za>"
        assert settings_for(Environment.TEST, EMAIL_FROM=sender).email_from == sender

    def test_the_allowed_recipient_is_optional_and_kept_in_lower_case(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("EMAIL_ALLOWED_RECIPIENT", raising=False)
        unset = settings_for(Environment.TEST)
        blank = settings_for(Environment.TEST, EMAIL_ALLOWED_RECIPIENT=" ")
        mixed_case = settings_for(
            Environment.TEST, EMAIL_ALLOWED_RECIPIENT=" Demo.Inbox@Example.co.za "
        )
        assert unset.email_allowed_recipient is None
        assert blank.email_allowed_recipient is None
        assert mixed_case.email_allowed_recipient == ALLOWED_RECIPIENT

    def test_the_redacted_configuration_shows_the_state_of_email_and_no_secret(self) -> None:
        shown = settings_for(
            Environment.PRODUCTION,
            RESEND_API_KEY=MADE_UP_KEY,
            EMAIL_ALLOWED_RECIPIENT=ALLOWED_RECIPIENT,
        ).redacted()
        assert shown["email_delivery"] == "configured"
        assert shown["email_recipient_restriction"] == "on"
        assert shown["email_sender"] == DEFAULT_EMAIL_FROM
        assert MADE_UP_KEY not in str(shown)
        assert ALLOWED_RECIPIENT not in str(shown)

    def test_the_redacted_configuration_says_so_when_email_is_off(self) -> None:
        shown = settings_for(Environment.PRODUCTION, RESEND_API_KEY="").redacted()
        assert shown["email_delivery"] == "not-configured"
        assert shown["email_recipient_restriction"] == "off"


class TestWithNoKeyNothingIsSent:
    """The gateway in use sends nothing and returns a receipt that says why."""

    @pytest.mark.parametrize("value", [RESEND_API_KEY_PLACEHOLDER, ""])
    def test_an_unconfigured_key_gives_a_failed_receipt_and_makes_no_request(
        self, value: str
    ) -> None:
        counter = CountingTransport()
        gateway = gateway_from_environment(counter, RESEND_API_KEY=value)
        receipt = gateway.send(MESSAGE)
        assert isinstance(gateway, UnconfiguredEmailGateway)
        assert not receipt.accepted
        assert receipt.error == EMAIL_NOT_CONFIGURED_REASON
        assert receipt.error == "Email is not configured in this environment."
        assert counter.request_count == 0

    def test_building_it_logs_one_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            build_notification_gateway(api_key=None, sender=DEFAULT_EMAIL_FROM)
        warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
        assert [record.getMessage() for record in warnings] == [NOT_CONFIGURED_WARNING]

    def test_with_a_key_the_resend_adapter_is_chosen_and_no_warning_is_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        counter = CountingTransport()
        with caplog.at_level(logging.INFO):
            gateway = gateway_from_environment(counter, RESEND_API_KEY=MADE_UP_KEY)
        assert isinstance(gateway, ResendEmailAdapter)
        assert NOT_CONFIGURED_WARNING not in [record.getMessage() for record in caplog.records]
        assert MADE_UP_KEY not in caplog.text
        assert gateway.send(MESSAGE).accepted
        assert counter.request_count == 1

    def test_the_allowed_recipient_reaches_the_adapter_from_the_environment(self) -> None:
        counter = CountingTransport()
        gateway = gateway_from_environment(
            counter, RESEND_API_KEY=MADE_UP_KEY, EMAIL_ALLOWED_RECIPIENT=ALLOWED_RECIPIENT
        )
        assert not gateway.send(MESSAGE).accepted
        assert counter.request_count == 0


class TestTheFakeGateway:
    """The test double every other test relies on."""

    def test_it_accepts_a_message_and_keeps_it(self) -> None:
        gateway = FakeEmailGateway()
        receipt = gateway.send(MESSAGE)
        assert receipt.accepted
        assert receipt.provider_message_id == "fake-message-1"
        assert gateway.sent == [MESSAGE]

    def test_each_message_gets_a_message_id_of_its_own(self) -> None:
        gateway = FakeEmailGateway()
        first, second = gateway.send(MESSAGE), gateway.send(MESSAGE)
        assert first.provider_message_id != second.provider_message_id

    def test_it_fails_every_send_when_told_to_and_still_keeps_the_message(self) -> None:
        gateway = FakeEmailGateway("Resend answered 500 (Internal Server Error).")
        receipt = gateway.send(MESSAGE)
        assert not receipt.accepted
        assert receipt.error == "Resend answered 500 (Internal Server Error)."
        assert gateway.sent == [MESSAGE]

    def test_sent_to_finds_the_messages_for_one_address_whatever_its_case(self) -> None:
        gateway = FakeEmailGateway()
        gateway.send(MESSAGE)
        gateway.send(EmailMessage(to=ALLOWED_RECIPIENT, subject="s", text_body="b"))
        assert gateway.sent_to(RECIPIENT.upper()) == [MESSAGE]
        assert gateway.sent_to("nobody@example.co.za") == []

    def test_the_list_it_returns_is_a_copy(self) -> None:
        gateway = FakeEmailGateway()
        gateway.send(MESSAGE)
        gateway.sent.clear()
        assert gateway.sent == [MESSAGE]
