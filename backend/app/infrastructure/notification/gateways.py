"""The gateways that are not Resend, and the choice between all three.

`UnconfiguredEmailGateway` is what the application runs with when no API key
has been set. It sends nothing and says so in its receipt, which lets a
deployment start and take bookings before the email account exists. Every
confirmation queued in that state is marked failed with a reason an
administrator can read.

`FakeEmailGateway` is the test double. It keeps what it was asked to send and
answers the way a test tells it to.

`build_notification_gateway` picks the gateway for a configuration. It is
called once when the application is built, so the warning it logs for a missing
key appears once at start-up.
"""

from __future__ import annotations

import logging
from typing import Final

import httpx
from pydantic import SecretStr

from app.application.notification.ports import DeliveryReceipt, NotificationGateway
from app.domain.notification import EmailMessage
from app.infrastructure.notification.resend import ResendEmailAdapter

logger = logging.getLogger(__name__)

EMAIL_NOT_CONFIGURED_REASON: Final[str] = "Email is not configured in this environment."
FAKE_MESSAGE_ID_PREFIX: Final[str] = "fake-message-"


class UnconfiguredEmailGateway:
    """The gateway used while there is no API key. Sends nothing."""

    def send(self, message: EmailMessage) -> DeliveryReceipt:
        """Return a failed receipt saying email is not configured. No request is made."""
        logger.info(
            "notification.send_skipped",
            extra={"reason": "email is not configured", "recipient_count": 1},
        )
        return DeliveryReceipt.failed(EMAIL_NOT_CONFIGURED_REASON)


class FakeEmailGateway:
    """A gateway for tests. It records every message and never touches the network."""

    def __init__(self, failure_reason: str | None = None) -> None:
        """Create the fake.

        Args:
            failure_reason: When set, every send fails with this reason. When
                left as None, every send is accepted.

        """
        self._failure_reason = failure_reason
        self._sent: list[EmailMessage] = []

    @property
    def sent(self) -> list[EmailMessage]:
        """Return every message the fake was asked to send, in order."""
        return list(self._sent)

    def send(self, message: EmailMessage) -> DeliveryReceipt:
        """Record the message and answer with the configured outcome."""
        self._sent.append(message)
        if self._failure_reason is not None:
            return DeliveryReceipt.failed(self._failure_reason)
        return DeliveryReceipt.delivered(f"{FAKE_MESSAGE_ID_PREFIX}{len(self._sent)}")

    def sent_to(self, address: str) -> list[EmailMessage]:
        """Return the messages addressed to one recipient, compared without regard to case."""
        wanted = address.strip().lower()
        return [message for message in self._sent if message.to.strip().lower() == wanted]


def build_notification_gateway(
    *,
    api_key: SecretStr | None,
    sender: str,
    allowed_recipient: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> NotificationGateway:
    """Return the gateway a configuration calls for.

    Args:
        api_key: The Resend API key, or None when none has been configured.
        sender: The From header for outgoing mail.
        allowed_recipient: When set, the only address mail may be sent to.
        transport: The HTTP transport for the Resend adapter. The real network
            by default.

    Returns:
        The Resend adapter when there is a key, and the gateway that sends
        nothing when there is not.

    """
    if api_key is None:
        logger.warning(
            "notification.email_not_configured",
            extra={
                "consequence": "booking confirmations are marked FAILED and nothing is sent",
                "remedy": "set RESEND_API_KEY in the environment of this service",
            },
        )
        return UnconfiguredEmailGateway()
    logger.info(
        "notification.gateway_selected",
        extra={
            "provider": "resend",
            "sender": sender,
            "recipient_restricted": allowed_recipient is not None,
        },
    )
    return ResendEmailAdapter(
        api_key=api_key,
        sender=sender,
        allowed_recipient=allowed_recipient,
        transport=transport,
    )
