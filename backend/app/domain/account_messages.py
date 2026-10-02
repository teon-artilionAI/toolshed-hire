"""The account security messages, and the links two of them carry (C-18).

Three messages are written here. One asks a new customer to prove their email
address. One lets somebody who forgot their password choose a new one. The
third goes to an address that already has an account when somebody tries to
register with it again, and it carries no token at all.

A link puts its token in the fragment, the part of an address after `#`. A
browser never sends the fragment to a server, so the token reaches no access
log and no `Referer` header. The screen reads it and takes it out of the
address bar.

None of these messages has a `notification` row. That table records the
booking confirmation and nothing else, so these are built here and handed
straight to the gateway.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from app.domain.account_tokens import EMAIL_VERIFICATION_LIFETIME, PASSWORD_RESET_LIFETIME
from app.domain.notification import EmailMessage

REGISTER_PATH: Final[str] = "/register"
SIGN_IN_PATH: Final[str] = "/signin"
VERIFY_FRAGMENT_KEY: Final[str] = "verify"
RESET_FRAGMENT_KEY: Final[str] = "reset"
SECONDS_PER_MINUTE: Final[int] = 60
MINUTES_PER_HOUR: Final[int] = 60

VERIFICATION_SUBJECT: Final[str] = "Confirm your email address for Toolshed Hire"
VERIFICATION_BODY_TEMPLATE: Final[str] = (
    "Thank you for registering with Toolshed Hire.\n"
    "\n"
    "Please confirm your email address by opening the link below. It works once "
    "and stays valid for {lifetime}.\n"
    "\n"
    "{link}\n"
    "\n"
    "If you did not register, you can ignore this message.\n"
    "\n"
    "Toolshed Hire\n"
)
RESET_SUBJECT: Final[str] = "Reset your Toolshed Hire password"
RESET_BODY_TEMPLATE: Final[str] = (
    "We were asked to reset the password of your Toolshed Hire account.\n"
    "\n"
    "Open the link below to choose a new password. It works once and stays "
    "valid for {lifetime}.\n"
    "\n"
    "{link}\n"
    "\n"
    "If you did not ask for this, you can ignore this message and your password "
    "stays as it is.\n"
    "\n"
    "Toolshed Hire\n"
)
ALREADY_REGISTERED_SUBJECT: Final[str] = "Your Toolshed Hire account"
ALREADY_REGISTERED_BODY_TEMPLATE: Final[str] = (
    "Somebody tried to register a Toolshed Hire account with this email address, "
    "and the address already has one.\n"
    "\n"
    "If that was you, sign in at {sign_in_page}. If you have forgotten your "
    "password you can reset it from the same page.\n"
    "\n"
    "If it was not you, there is nothing you need to do. Nothing about your "
    "account has changed.\n"
    "\n"
    "Toolshed Hire\n"
)


def verification_link(frontend_origin: str, token: str) -> str:
    """Return the link that proves an email address, with the token in the fragment."""
    return f"{frontend_origin}{REGISTER_PATH}#{VERIFY_FRAGMENT_KEY}={token}"


def password_reset_link(frontend_origin: str, token: str) -> str:
    """Return the link that resets a password, with the token in the fragment."""
    return f"{frontend_origin}{SIGN_IN_PATH}#{RESET_FRAGMENT_KEY}={token}"


def lifetime_in_words(lifetime: timedelta) -> str:
    """Return a lifetime as a person reads it, in whole hours or in minutes."""
    minutes = int(lifetime.total_seconds()) // SECONDS_PER_MINUTE
    hours, minutes_over = divmod(minutes, MINUTES_PER_HOUR)
    if hours > 1 and not minutes_over:
        return f"{hours} hours"
    return f"{minutes} minutes"


def verification_message(*, to: str, frontend_origin: str, token: str) -> EmailMessage:
    """Return the message that asks a new customer to prove their address."""
    return EmailMessage(
        to=to,
        subject=VERIFICATION_SUBJECT,
        text_body=VERIFICATION_BODY_TEMPLATE.format(
            lifetime=lifetime_in_words(EMAIL_VERIFICATION_LIFETIME),
            link=verification_link(frontend_origin, token),
        ),
    )


def password_reset_message(*, to: str, frontend_origin: str, token: str) -> EmailMessage:
    """Return the message that lets the holder of an account choose a new password."""
    return EmailMessage(
        to=to,
        subject=RESET_SUBJECT,
        text_body=RESET_BODY_TEMPLATE.format(
            lifetime=lifetime_in_words(PASSWORD_RESET_LIFETIME),
            link=password_reset_link(frontend_origin, token),
        ),
    )


def already_registered_message(*, to: str, frontend_origin: str) -> EmailMessage:
    """Return the message for an address that somebody tried to register again.

    It carries no token. It says what happened and where to sign in, so the
    holder of the account learns of the attempt and the person who made it
    learns nothing from the response.
    """
    return EmailMessage(
        to=to,
        subject=ALREADY_REGISTERED_SUBJECT,
        text_body=ALREADY_REGISTERED_BODY_TEMPLATE.format(
            sign_in_page=f"{frontend_origin}{SIGN_IN_PATH}"
        ),
    )
