"""Sending the account security messages, after the commit (C-18).

A verification link, a reset link and the note for an address that somebody
tried to register twice all leave through here. They go straight to the email
gateway, and none of them has a `notification` row, because that table is the
record of the booking confirmation and of nothing else.

A message is sent inside the request that asked for it, after the transaction
has committed and with no transaction open. Cloud Run only gives a container
CPU while it is serving a request, so work left for a background thread may
never run. The price is that a slow provider slows that one response by up to
the timeout of the gateway.

Nothing in here raises. The account or the token is already committed when a
message is sent, and answering the request with an error would say something
failed that did not. A message that could not be sent is logged, and the
person can ask for another.

The log names the kind of message and what became of it. It never holds the
address it went to or the token it carried.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

from app.application.notification.ports import NotificationGateway
from app.domain.account_messages import (
    already_registered_message,
    password_reset_message,
    verification_message,
)
from app.domain.notification import EmailMessage

logger = logging.getLogger(__name__)

VERIFICATION_KIND: Final[str] = "email-verification"
RESET_KIND: Final[str] = "account-reset"
ALREADY_REGISTERED_KIND: Final[str] = "already-registered"


@dataclass(frozen=True, slots=True)
class MailExpectation:
    """What a caller may expect of the message a request may have sent.

    Attributes:
        email_deliverable: False when this environment would not hand a
            message for the address to the provider. It is worked out from
            the configuration and the address alone, so it is the same
            whether or not the address has an account.

    """

    email_deliverable: bool


class AccountMailer:
    """Builds the three account messages and hands each to the gateway."""

    def __init__(self, gateway: NotificationGateway, frontend_origin: str) -> None:
        """Keep the gateway and the origin the links point at.

        Args:
            gateway: The email provider.
            frontend_origin: The public address of the site, with no trailing
                slash, for example `https://www.example.co.za`.

        """
        self._gateway = gateway
        self._frontend_origin = frontend_origin

    def expectation_for(self, address: str) -> MailExpectation:
        """Return whether a message for this address would be delivered at all."""
        return MailExpectation(email_deliverable=self._gateway.delivers_to(address))

    def send_verification(self, *, to: str, token: str) -> None:
        """Send the link that proves an email address."""
        self._send(
            VERIFICATION_KIND,
            verification_message(to=to, frontend_origin=self._frontend_origin, token=token),
        )

    def send_password_reset(self, *, to: str, token: str) -> None:
        """Send the link that lets the holder of an account choose a new password."""
        self._send(
            RESET_KIND,
            password_reset_message(to=to, frontend_origin=self._frontend_origin, token=token),
        )

    def send_already_registered(self, *, to: str) -> None:
        """Tell the holder of an account that somebody tried to register with its address."""
        self._send(
            ALREADY_REGISTERED_KIND,
            already_registered_message(to=to, frontend_origin=self._frontend_origin),
        )

    def _send(self, kind: str, message: EmailMessage) -> None:
        """Hand one message to the gateway and log what became of it. Never raises."""
        logger.info("account_mail.send_started", extra={"kind": kind, "recipient_count": 1})
        try:
            receipt = self._gateway.send(message)
        except Exception:
            # A gateway reports a failed delivery through its receipt. Reaching
            # here means it broke that contract, which is a defect, and the
            # request that asked for the message must still succeed.
            logger.exception(
                "account_mail.gateway_fault",
                extra={"kind": kind, "attempted": "send an account message through the gateway"},
            )
            return
        log = logger.info if receipt.accepted else logger.warning
        log(
            "account_mail.send_finished",
            extra={
                "kind": kind,
                "accepted": receipt.accepted,
                "provider_message_id": receipt.provider_message_id,
                "failure_reason": receipt.error,
            },
        )
