"""The Resend adapter, the only class that knows which email provider is in use.

Every caller depends on the `NotificationGateway` port. Changing the email
supplier means replacing this class and nothing else.

The adapter never raises for a delivery that did not happen. A status outside
the 2xx range, a timeout and a transport error each come back as a failed
receipt with a short reason, because the caller records the reason against the
notification and carries on (BR-19).

Three rules about what leaves this module are deliberate.

1. The API key is held as a `SecretStr` and is read in exactly one place, where
   the Authorization header is built. It is never logged, never put in a
   receipt and never put in an exception message.
2. A failure reason is built from the status code and the provider's error
   name only. The provider's message text is not copied, because it can quote
   the recipient or the request back.
3. Recipient addresses are not logged. The log carries a count.

`EMAIL_ALLOWED_RECIPIENT` is enforced here, on the server. When it is set, a
message for any other address is refused before the provider is called. It is
never redirected to the allowed address, because that would deliver one
customer's booking to somebody else.
"""

from __future__ import annotations

import logging
import re
import time
from http import HTTPStatus
from typing import Final

import httpx
from pydantic import SecretStr

from app.application.notification.ports import DeliveryReceipt
from app.domain.notification import EmailMessage

logger = logging.getLogger(__name__)

RESEND_EMAILS_URL: Final[str] = "https://api.resend.com/emails"
RESEND_TIMEOUT_SECONDS: Final[float] = 5.0
IDEMPOTENCY_KEY_HEADER: Final[str] = "Idempotency-Key"
AUTHORIZATION_HEADER: Final[str] = "Authorization"
BEARER_SCHEME: Final[str] = "Bearer"
MILLISECONDS_PER_SECOND: Final[int] = 1000
DURATION_DECIMAL_PLACES: Final[int] = 2
# The provider names each kind of error with a short slug such as
# `validation_error`. Anything that is not shaped like one is left out.
_ERROR_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9_]{1,60}$")

RECIPIENT_NOT_ALLOWED_REASON: Final[str] = (
    "This environment only sends email to one approved address, and the recipient is not it."
)
TIMEOUT_REASON: Final[str] = (
    f"Resend did not answer within {RESEND_TIMEOUT_SECONDS:g} seconds."
)
NO_MESSAGE_ID_REASON: Final[str] = "Resend accepted the request but returned no message id."


class ResendEmailAdapter:
    """Sends one email through the Resend HTTP API."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        sender: str,
        allowed_recipient: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = RESEND_TIMEOUT_SECONDS,
    ) -> None:
        """Create the adapter.

        Args:
            api_key: The Resend API key.
            sender: The From header, for example `Toolshed Hire <a@b.co.za>`.
            allowed_recipient: When set, the only address this adapter will
                send to. Compared without regard to case.
            transport: The HTTP transport. The real network by default. A test
                passes a mock so that no request leaves the process.
            timeout_seconds: How long to wait for the provider.

        Raises:
            ValueError: If the key or the sender is blank. The message names
                the setting and never the value.

        """
        if not api_key.get_secret_value().strip():
            raise ValueError(
                "Attempted to build the Resend adapter with a blank API key. Set RESEND_API_KEY, "
                "or leave it unset to run with email switched off."
            )
        if not sender.strip():
            raise ValueError(
                "Attempted to build the Resend adapter with a blank sender. Set EMAIL_FROM."
            )
        self._api_key = api_key
        self._sender = sender.strip()
        self._allowed_recipient = allowed_recipient.strip().lower() if allowed_recipient else None
        self._transport = transport
        self._timeout_seconds = timeout_seconds

    def __repr__(self) -> str:
        """Describe the adapter without the key it holds."""
        return (
            f"ResendEmailAdapter(sender={self._sender!r}, "
            f"recipient_restricted={self._allowed_recipient is not None})"
        )

    def delivers_to(self, address: str) -> bool:
        """Return True unless a recipient restriction is set and this address is not it.

        The answer comes from the configuration and the address alone. It says
        nothing about whether the address belongs to anybody.
        """
        return self._may_send_to(address)

    def send(self, message: EmailMessage) -> DeliveryReceipt:
        """Send one message and report what happened. Never raises for a failed delivery."""
        if not self._may_send_to(message.to):
            logger.warning(
                "notification.recipient_not_allowed",
                extra={
                    "provider": "resend",
                    "attempted": "send to an address other than the one approved address",
                },
            )
            return DeliveryReceipt.failed(RECIPIENT_NOT_ALLOWED_REASON)

        logger.info(
            "notification.provider_call_started",
            extra={
                "provider": "resend",
                "recipient_count": 1,
                "idempotent": message.idempotency_key is not None,
                "timeout_seconds": self._timeout_seconds,
            },
        )
        started_at = time.perf_counter()
        receipt, status_code = self._post(message)
        elapsed_ms = (time.perf_counter() - started_at) * MILLISECONDS_PER_SECOND
        log = logger.info if receipt.accepted else logger.warning
        log(
            "notification.provider_call_finished",
            extra={
                "provider": "resend",
                "accepted": receipt.accepted,
                "status": status_code,
                "duration_ms": round(elapsed_ms, DURATION_DECIMAL_PLACES),
                "provider_message_id": receipt.provider_message_id,
                "failure_reason": receipt.error,
            },
        )
        return receipt

    def _may_send_to(self, recipient: str) -> bool:
        """Return True unless a recipient restriction is set and this address is not it."""
        if self._allowed_recipient is None:
            return True
        return recipient.strip().lower() == self._allowed_recipient

    def _post(self, message: EmailMessage) -> tuple[DeliveryReceipt, int | None]:
        """Call the provider once and return the receipt with the status code, if any."""
        headers = {
            AUTHORIZATION_HEADER: f"{BEARER_SCHEME} {self._api_key.get_secret_value()}"
        }
        if message.idempotency_key is not None:
            headers[IDEMPOTENCY_KEY_HEADER] = message.idempotency_key
        payload: dict[str, str | list[str]] = {
            "from": self._sender,
            "to": [message.to],
            "subject": message.subject,
            "text": message.text_body,
        }
        try:
            with httpx.Client(timeout=self._timeout_seconds, transport=self._transport) as client:
                response = client.post(RESEND_EMAILS_URL, json=payload, headers=headers)
        except httpx.TimeoutException:
            return DeliveryReceipt.failed(TIMEOUT_REASON), None
        except httpx.HTTPError as error:
            # Only the kind of fault is kept. The text of a transport error can
            # quote the request it belonged to.
            return (
                DeliveryReceipt.failed(f"Resend could not be reached ({type(error).__name__})."),
                None,
            )
        return _to_receipt(response), response.status_code


def _to_receipt(response: httpx.Response) -> DeliveryReceipt:
    """Turn the provider's answer into a receipt."""
    body = _json_object_of(response)
    if not response.is_success:
        phrase = _status_phrase(response.status_code)
        error_name = body.get("name")
        named = (
            f", {error_name}"
            if isinstance(error_name, str) and _ERROR_NAME_PATTERN.match(error_name)
            else ""
        )
        return DeliveryReceipt.failed(f"Resend answered {response.status_code} ({phrase}{named}).")
    message_id = body.get("id")
    if not isinstance(message_id, str) or not message_id.strip():
        return DeliveryReceipt.failed(NO_MESSAGE_ID_REASON)
    return DeliveryReceipt.delivered(message_id.strip())


def _json_object_of(response: httpx.Response) -> dict[str, object]:
    """Return the JSON object in a response body, or an empty one when there is none."""
    try:
        parsed: object = response.json()
    except ValueError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): value for key, value in parsed.items()}


def _status_phrase(status_code: int) -> str:
    """Return the standard phrase for a status code, or a neutral one when it has none."""
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "unrecognised status"
