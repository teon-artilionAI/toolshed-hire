"""The Resend adapter, against a mock transport. No request leaves the process.

`httpx.MockTransport` stands where the network would be, so the adapter is run
exactly as it runs in production up to the socket. Each test hands it a handler
that plays the provider and counts how often it was called.

Two things are pinned beyond the happy path. A delivery that does not happen is
a failed receipt and never an exception, whatever went wrong. And the API key
appears nowhere it could be read back, which means not in a receipt, not in a
log line and not in the text of an error.

The key used here is plainly made up. It is the string the tests then search
for, so a leak would show as a failed assertion.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Final

import httpx
import pytest
from pydantic import SecretStr

from app.domain.notification import EmailMessage
from app.infrastructure.notification import ResendEmailAdapter
from app.infrastructure.notification.resend import (
    NO_MESSAGE_ID_REASON,
    RECIPIENT_NOT_ALLOWED_REASON,
    RESEND_EMAILS_URL,
    RESEND_TIMEOUT_SECONDS,
    TIMEOUT_REASON,
)
from tests.support.log_capture import LogCapture

MADE_UP_KEY: Final[str] = "made-up-resend-key-for-this-test"
SENDER: Final[str] = "Toolshed Hire <onboarding@resend.dev>"
RECIPIENT: Final[str] = "nomsa.dlamini@example.co.za"
SOMEBODY_ELSE: Final[str] = "wesley.adonis@example.co.za"
IDEMPOTENCY_KEY: Final[str] = "notification-6f1c2b9e-3d4a-4c5b-8e7f-0a1b2c3d4e5f"
PROVIDER_MESSAGE_ID: Final[str] = "made-up-provider-message-id"
MESSAGE: Final[EmailMessage] = EmailMessage(
    to=RECIPIENT,
    subject="Your Toolshed Hire booking TSH-R-26-000124",
    text_body="Your booking reference is TSH-R-26-000124.",
    idempotency_key=IDEMPOTENCY_KEY,
)

type Handler = Callable[[httpx.Request], httpx.Response]


class Provider:
    """Plays the email provider and keeps every request it was sent."""

    def __init__(self, respond: Handler) -> None:
        """Answer every request with `respond`."""
        self._respond = respond
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Record the request and answer it."""
        self.requests.append(request)
        return self._respond(request)


def answering(status_code: int, body: dict[str, object]) -> Provider:
    """Return a provider that answers every request with one JSON response."""
    return Provider(lambda _request: httpx.Response(status_code, json=body))


def raising(error: Exception) -> Provider:
    """Return a provider whose every request fails with a transport fault."""

    def fail(_request: httpx.Request) -> httpx.Response:
        """Fail the request the way the network would."""
        raise error

    return Provider(fail)


def adapter_for(provider: Provider, *, allowed_recipient: str | None = None) -> ResendEmailAdapter:
    """Return the adapter wired to a mock transport in place of the network."""
    return ResendEmailAdapter(
        api_key=SecretStr(MADE_UP_KEY),
        sender=SENDER,
        allowed_recipient=allowed_recipient,
        transport=httpx.MockTransport(provider),
    )


class TestASuccessfulSend:
    """One POST, shaped the way the provider documents it."""

    def test_the_receipt_carries_the_provider_message_id(self) -> None:
        provider = answering(200, {"id": PROVIDER_MESSAGE_ID})
        receipt = adapter_for(provider).send(MESSAGE)
        assert receipt.accepted
        assert receipt.provider_message_id == PROVIDER_MESSAGE_ID
        assert receipt.error is None

    def test_the_request_is_one_post_to_the_emails_endpoint(self) -> None:
        provider = answering(200, {"id": PROVIDER_MESSAGE_ID})
        adapter_for(provider).send(MESSAGE)
        (request,) = provider.requests
        assert request.method == "POST"
        assert str(request.url) == RESEND_EMAILS_URL == "https://api.resend.com/emails"

    def test_the_key_is_sent_as_a_bearer_credential(self) -> None:
        provider = answering(200, {"id": PROVIDER_MESSAGE_ID})
        adapter_for(provider).send(MESSAGE)
        assert provider.requests[0].headers["Authorization"] == f"Bearer {MADE_UP_KEY}"

    def test_the_body_holds_the_sender_the_recipient_list_the_subject_and_the_text(self) -> None:
        provider = answering(200, {"id": PROVIDER_MESSAGE_ID})
        adapter_for(provider).send(MESSAGE)
        assert json.loads(provider.requests[0].content) == {
            "from": SENDER,
            "to": [RECIPIENT],
            "subject": MESSAGE.subject,
            "text": MESSAGE.text_body,
        }

    def test_the_idempotency_key_of_the_message_is_sent_as_a_header(self) -> None:
        provider = answering(200, {"id": PROVIDER_MESSAGE_ID})
        adapter_for(provider).send(MESSAGE)
        assert provider.requests[0].headers["Idempotency-Key"] == IDEMPOTENCY_KEY

    def test_a_message_with_no_idempotency_key_sends_no_such_header(self) -> None:
        provider = answering(200, {"id": PROVIDER_MESSAGE_ID})
        adapter_for(provider).send(EmailMessage(to=RECIPIENT, subject="s", text_body="b"))
        assert "Idempotency-Key" not in provider.requests[0].headers

    def test_the_timeout_is_five_seconds(self) -> None:
        assert RESEND_TIMEOUT_SECONDS == 5.0
        provider = answering(200, {"id": PROVIDER_MESSAGE_ID})
        adapter_for(provider).send(MESSAGE)
        assert provider.requests[0].extensions["timeout"] == {
            "connect": 5.0,
            "read": 5.0,
            "write": 5.0,
            "pool": 5.0,
        }


class TestAFailedSendIsAReceiptAndNeverAnException:
    """BR-19. The caller records the reason and the booking stands."""

    @pytest.mark.parametrize(
        ("status_code", "body", "expected_reason"),
        [
            (
                403,
                {"statusCode": 403, "name": "validation_error", "message": "not verified"},
                "Resend answered 403 (Forbidden, validation_error).",
            ),
            (
                429,
                {"statusCode": 429, "name": "rate_limit_exceeded", "message": "slow down"},
                "Resend answered 429 (Too Many Requests, rate_limit_exceeded).",
            ),
            (
                500,
                {"statusCode": 500, "name": "internal_server_error", "message": "oops"},
                "Resend answered 500 (Internal Server Error, internal_server_error).",
            ),
        ],
    )
    def test_a_status_outside_2xx_is_a_failed_receipt_naming_the_status(
        self, status_code: int, body: dict[str, object], expected_reason: str
    ) -> None:
        provider = answering(status_code, body)
        receipt = adapter_for(provider).send(MESSAGE)
        assert not receipt.accepted
        assert receipt.provider_message_id is None
        assert receipt.error == expected_reason
        assert len(provider.requests) == 1

    def test_the_providers_own_message_text_is_not_copied_into_the_reason(self) -> None:
        """It can quote the recipient or the request back."""
        body: dict[str, object] = {
            "name": "validation_error",
            "message": f"You can only send testing emails to {SOMEBODY_ELSE}",
        }
        receipt = adapter_for(answering(403, body)).send(MESSAGE)
        assert SOMEBODY_ELSE not in str(receipt.error)

    def test_an_error_name_that_is_not_a_plain_slug_is_left_out(self) -> None:
        receipt = adapter_for(answering(500, {"name": f"leaked {MADE_UP_KEY}"})).send(MESSAGE)
        assert receipt.error == "Resend answered 500 (Internal Server Error)."

    def test_a_status_with_no_standard_phrase_is_still_reported(self) -> None:
        receipt = adapter_for(answering(599, {})).send(MESSAGE)
        assert receipt.error == "Resend answered 599 (unrecognised status)."

    def test_a_body_that_is_not_json_is_still_a_failed_receipt(self) -> None:
        provider = Provider(lambda _request: httpx.Response(502, text="<html>Bad Gateway</html>"))
        receipt = adapter_for(provider).send(MESSAGE)
        assert receipt.error == "Resend answered 502 (Bad Gateway)."

    def test_a_timeout_is_a_failed_receipt(self) -> None:
        provider = raising(httpx.ReadTimeout("timed out"))
        receipt = adapter_for(provider).send(MESSAGE)
        assert not receipt.accepted
        assert receipt.error == TIMEOUT_REASON == "Resend did not answer within 5 seconds."

    def test_a_transport_error_is_a_failed_receipt_naming_the_kind_of_fault(self) -> None:
        provider = raising(httpx.ConnectError(f"could not connect using {MADE_UP_KEY}"))
        receipt = adapter_for(provider).send(MESSAGE)
        assert not receipt.accepted
        assert receipt.error == "Resend could not be reached (ConnectError)."

    def test_a_success_with_no_message_id_is_a_failed_receipt(self) -> None:
        receipt = adapter_for(answering(200, {"object": "email"})).send(MESSAGE)
        assert not receipt.accepted
        assert receipt.error == NO_MESSAGE_ID_REASON

    def test_a_success_whose_body_is_a_list_is_a_failed_receipt(self) -> None:
        provider = Provider(lambda _request: httpx.Response(200, json=[PROVIDER_MESSAGE_ID]))
        assert adapter_for(provider).send(MESSAGE).error == NO_MESSAGE_ID_REASON


class TestTheOneAllowedRecipient:
    """EMAIL_ALLOWED_RECIPIENT is enforced in the adapter, before the provider is called."""

    def test_a_message_for_anyone_else_is_refused_without_a_request(self) -> None:
        provider = answering(200, {"id": PROVIDER_MESSAGE_ID})
        receipt = adapter_for(provider, allowed_recipient=SOMEBODY_ELSE).send(MESSAGE)
        assert not receipt.accepted
        assert receipt.error == RECIPIENT_NOT_ALLOWED_REASON
        assert provider.requests == []

    def test_the_message_is_never_redirected_to_the_allowed_address(self) -> None:
        """Redirecting would deliver one customer's booking to somebody else."""
        provider = answering(200, {"id": PROVIDER_MESSAGE_ID})
        adapter_for(provider, allowed_recipient=SOMEBODY_ELSE).send(MESSAGE)
        assert all(SOMEBODY_ELSE.encode() not in request.content for request in provider.requests)

    def test_the_allowed_address_is_sent_to(self) -> None:
        provider = answering(200, {"id": PROVIDER_MESSAGE_ID})
        receipt = adapter_for(provider, allowed_recipient=RECIPIENT).send(MESSAGE)
        assert receipt.accepted
        assert len(provider.requests) == 1

    def test_the_comparison_ignores_case_and_surrounding_space(self) -> None:
        provider = answering(200, {"id": PROVIDER_MESSAGE_ID})
        adapter = adapter_for(provider, allowed_recipient="  Nomsa.Dlamini@Example.CO.ZA ")
        assert adapter.send(MESSAGE).accepted

    def test_the_refusal_does_not_name_either_address(self) -> None:
        provider = answering(200, {"id": PROVIDER_MESSAGE_ID})
        receipt = adapter_for(provider, allowed_recipient=SOMEBODY_ELSE).send(MESSAGE)
        assert RECIPIENT not in str(receipt.error)
        assert SOMEBODY_ELSE not in str(receipt.error)


class TestTheKeyIsNeverReadBack:
    """Not from a receipt, not from the log, not from an error and not from a repr."""

    @pytest.mark.parametrize(
        "provider",
        [
            answering(200, {"id": PROVIDER_MESSAGE_ID}),
            answering(403, {"name": "invalid_api_key", "message": f"bad key {MADE_UP_KEY}"}),
            answering(429, {"name": "rate_limit_exceeded"}),
            answering(500, {"name": f"echo {MADE_UP_KEY}"}),
            raising(httpx.ReadTimeout(f"timed out with {MADE_UP_KEY}")),
            raising(httpx.ConnectError(f"refused {MADE_UP_KEY}")),
        ],
        ids=["200", "403", "429", "500", "timeout", "transport-error"],
    )
    def test_neither_the_receipt_nor_the_log_holds_the_key(
        self, provider: Provider, application_log: LogCapture, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG):
            receipt = adapter_for(provider).send(MESSAGE)
        assert MADE_UP_KEY not in repr(receipt)
        assert MADE_UP_KEY not in application_log.text
        assert MADE_UP_KEY not in caplog.text
        assert all(MADE_UP_KEY not in str(record.__dict__) for record in caplog.records)

    def test_the_log_does_not_hold_the_recipient_address(
        self, application_log: LogCapture
    ) -> None:
        adapter_for(answering(200, {"id": PROVIDER_MESSAGE_ID})).send(MESSAGE)
        assert application_log.named("notification.provider_call_finished")
        assert RECIPIENT not in application_log.text

    def test_the_provider_call_is_logged_at_its_start_and_its_end(
        self, application_log: LogCapture
    ) -> None:
        adapter_for(answering(200, {"id": PROVIDER_MESSAGE_ID})).send(MESSAGE)
        started = application_log.only("notification.provider_call_started")
        finished = application_log.only("notification.provider_call_finished")
        assert started["recipient_count"] == 1
        assert finished["accepted"] is True
        assert finished["status"] == 200
        assert finished["provider_message_id"] == PROVIDER_MESSAGE_ID

    def test_the_repr_of_the_adapter_does_not_show_the_key(self) -> None:
        shown = repr(adapter_for(answering(200, {"id": PROVIDER_MESSAGE_ID})))
        assert MADE_UP_KEY not in shown
        assert "recipient_restricted=False" in shown

    def test_a_blank_key_is_refused_by_name_and_not_by_value(self) -> None:
        with pytest.raises(ValueError, match="RESEND_API_KEY") as refused:
            ResendEmailAdapter(api_key=SecretStr("   "), sender=SENDER)
        assert "blank API key" in str(refused.value)

    def test_a_blank_sender_is_refused(self) -> None:
        with pytest.raises(ValueError, match="EMAIL_FROM"):
            ResendEmailAdapter(api_key=SecretStr(MADE_UP_KEY), sender="  ")
