"""A client and a few helpers for the tests of the account and profile routes.

`account_client` is `session_client` with two more things in place. Every
message goes to the fake gateway the test holds, so the test can read the
link a person would have been sent. And the password hasher is real bcrypt
that hashes each distinct password once for the whole run, so an account
that registers can then sign in with the real verifier, and fifty
registrations do not cost fifty quarter seconds.

`registration_body` is a request that is accepted, with any field replaced or
removed. `token_from` reads a token out of the link in the last message an
address was sent, which is how a person gets hold of one.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.account_deps import get_password_hasher
from app.api.deps import get_notification_gateway
from app.config import settings
from app.infrastructure.notification import FakeEmailGateway
from app.main import app as production_app
from tests.support.account_desk import RESET_KEY, VERIFY_KEY, token_in
from tests.support.clock import FixedClock
from tests.support.factories import cached_password_hash
from tests.support.sessions import session_client

REGISTER_PATH: Final[str] = "/api/auth/register"
VERIFY_PATH: Final[str] = "/api/auth/email-verification"
RESEND_PATH: Final[str] = "/api/auth/email-verification/resend"
RESET_REQUEST_PATH: Final[str] = "/api/auth/password-reset/request"
RESET_COMPLETE_PATH: Final[str] = "/api/auth/password-reset/complete"
PROFILE_PATH: Final[str] = "/api/me/profile"
VERIFICATION_LINK_INVALID_PROBLEM: Final[str] = "verification-link-invalid"
RESET_LINK_INVALID_PROBLEM: Final[str] = "reset-link-invalid"
REQUEST_VALIDATION_PROBLEM: Final[str] = "request-validation-failure"
HOME_BRANCH_CODE: Final[str] = "CBD"
NEW_EMAIL: Final[str] = "thandi.mokoena@example.co.za"
CHOSEN_PASSWORD: Final[str] = "a-made-up-passphrase-for-tests"
NEW_PASSWORD: Final[str] = "another-made-up-passphrase"
# Where the links point in the test environment, which sets no FRONTEND_ORIGIN.
LOCAL_FRONTEND_ORIGIN: Final[str] = settings.frontend_origin
# Removed from a request body by `registration_body`.
OMITTED: Final[object] = object()


class CachedBcryptHasher:
    """Real bcrypt at the real work factor, computed once for each distinct password."""

    def hash(self, plain_password: str) -> str:
        """Return the bcrypt hash of a password, from the cache when it is there."""
        return cached_password_hash(plain_password)


def registration_body(**overrides: object) -> dict[str, object]:
    """Return a registration request that is accepted, with fields replaced or removed.

    Args:
        overrides: Values by their name on the wire. A value of `OMITTED`
            takes the field out of the body.

    """
    body: dict[str, object] = {
        "email": NEW_EMAIL,
        "password": CHOSEN_PASSWORD,
        "fullName": "Thandi Mokoena",
        "phone": "0824417719",
        "idDocumentType": "SA_ID",
        "idDocumentLast4": "5083",
        "billingAddressLine1": "12 Loop Street",
        "billingSuburb": "Gardens",
        "billingCity": "Cape Town",
        "billingPostalCode": "8001",
        "homeBranchCode": HOME_BRANCH_CODE,
        "acceptsPrivacyNotice": True,
        **overrides,
    }
    return {name: value for name, value in body.items() if value is not OMITTED}


def token_from(gateway: FakeEmailGateway, address: str, key: str) -> str:
    """Return the token in the link of the last message an address was sent.

    Args:
        gateway: The fake gateway the messages went through.
        address: Who the message was for.
        key: `verify` for a verification link and `reset` for a reset link.

    """
    messages = gateway.sent_to(address)
    assert messages, f"No message was sent to {address}."
    return token_in(messages[-1], key)


@contextmanager
def account_client(
    session: Session,
    clock: FixedClock,
    gateway: FakeEmailGateway,
    *,
    application: FastAPI = production_app,
    client_address: str | None = None,
) -> Iterator[TestClient]:
    """Yield a client whose messages go to `gateway` and whose hasher is cheap after once.

    Args:
        session: The session every request is served with.
        clock: The clock the application is given.
        gateway: The fake gateway every message is handed to.
        application: The application to drive. The real one when omitted.
        client_address: The address the requests appear to come from.

    """
    with session_client(
        session, clock, application=application, client_address=client_address
    ) as client:
        application.dependency_overrides[get_notification_gateway] = lambda: gateway
        application.dependency_overrides[get_password_hasher] = CachedBcryptHasher
        try:
            yield client
        finally:
            application.dependency_overrides.pop(get_password_hasher, None)


__all__ = [
    "CHOSEN_PASSWORD",
    "HOME_BRANCH_CODE",
    "LOCAL_FRONTEND_ORIGIN",
    "NEW_EMAIL",
    "NEW_PASSWORD",
    "OMITTED",
    "PROFILE_PATH",
    "REGISTER_PATH",
    "REQUEST_VALIDATION_PROBLEM",
    "RESEND_PATH",
    "RESET_COMPLETE_PATH",
    "RESET_KEY",
    "RESET_LINK_INVALID_PROBLEM",
    "RESET_REQUEST_PATH",
    "VERIFICATION_LINK_INVALID_PROBLEM",
    "VERIFY_KEY",
    "VERIFY_PATH",
    "CachedBcryptHasher",
    "account_client",
    "registration_body",
    "token_from",
]
