"""A client and a few helpers for the tests of signing in, refreshing and signing out.

`session_client` gives an application the session the test holds and a clock
that stands still, and takes both away again afterwards. It works on the in
memory database and on PostgreSQL alike, and on the application any
environment would run, because the only things that differ are the session and
the application it is handed.

The helpers read the refresh cookie out of a response and present one back.
The HTTP client keeps a cookie jar of its own, which is what a browser does.
`present` empties it first, so a test that wants to send an old token sends
that token and nothing else.

`without_bcrypt` swaps the password verifier for one that refuses everything
and hashes nothing. A test about counting makes dozens of attempts, and the
work factor would be most of its running time and none of its point.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlmodel import Session

from app.api.deps import get_clock, get_notification_gateway
from app.api.identity_deps import get_password_verifier
from app.api.refresh_cookie import REFRESH_COOKIE_NAME, SET_COOKIE_HEADER
from app.infrastructure.database import get_session
from app.infrastructure.notification import FakeEmailGateway
from app.main import app as production_app
from tests.support.clock import FixedClock
from tests.support.factories import TEST_PASSWORD

LOGIN_PATH: Final[str] = "/api/auth/login"
REFRESH_PATH: Final[str] = "/api/auth/refresh"
LOGOUT_PATH: Final[str] = "/api/auth/logout"
ME_PATH: Final[str] = "/api/me"
INVALID_CREDENTIALS_PROBLEM: Final[str] = "invalid-credentials"
SESSION_EXPIRED_PROBLEM: Final[str] = "session-expired"
TOO_MANY_ATTEMPTS_PROBLEM: Final[str] = "too-many-attempts"
ORIGIN_NOT_ALLOWED_PROBLEM: Final[str] = "origin-not-allowed"
WRONG_PASSWORD: Final[str] = "not-the-password-at-all"
UNKNOWN_EMAIL: Final[str] = "nobody.at.all@toolshedhire.co.za"
# The origin the test configuration allows, which is the Vite dev server.
ALLOWED_ORIGIN: Final[str] = "http://localhost:5173"
FOREIGN_ORIGIN: Final[str] = "https://somewhere-else.example"
# Every problem document quotes the id of its own request. Two responses that
# are compared whole therefore send the same id.
SHARED_REQUEST_ID: Final[dict[str, str]] = {
    "X-Request-ID": "6f1c2b9e-3d4a-4c5b-8e7f-0a1b2c3d4e5f"
}
DEFAULT_CLIENT_PORT: Final[int] = 50000
COOKIE_HEADER: Final[str] = "Cookie"


@contextmanager
def session_client(
    session: Session,
    clock: FixedClock | None = None,
    *,
    application: FastAPI = production_app,
    client_address: str | None = None,
) -> Iterator[TestClient]:
    """Yield a client for an application, on the test's session and a still clock.

    The request session is rolled back when a request ends, as the shared
    `client` fixture does, so a test commits its setup before it asks anything.

    Args:
        session: The session every request is served with.
        clock: The clock the application is given. A fixed clock at its
            default instant when omitted.
        application: The application to drive. The real one for the test
            environment when omitted.
        client_address: The address the requests appear to come from. Left
            out, the server cannot tell, as it cannot for a bare test client.

    """
    still_clock = clock or FixedClock()

    def _session() -> Iterator[Session]:
        """Hand the request the test's session and discard uncommitted work after."""
        try:
            yield session
        finally:
            session.rollback()

    overrides = {
        get_session: _session,
        get_clock: lambda: still_clock,
        get_notification_gateway: lambda: FakeEmailGateway(),
    }
    application.dependency_overrides.update(overrides)
    try:
        if client_address is None:
            yield TestClient(application)
        else:
            yield TestClient(application, client=(client_address, DEFAULT_CLIENT_PORT))
    finally:
        for dependency in overrides:
            application.dependency_overrides.pop(dependency, None)


class RefusingVerifier:
    """A password verifier that refuses everything at once, for tests about counting."""

    def verify(self, plain_password: str, stored_hash: str | None) -> bool:
        """Refuse without hashing anything."""
        return False


@contextmanager
def without_bcrypt(application: FastAPI = production_app) -> Iterator[None]:
    """Give an application a password verifier that costs nothing, for a while."""
    application.dependency_overrides[get_password_verifier] = RefusingVerifier
    try:
        yield
    finally:
        application.dependency_overrides.pop(get_password_verifier, None)


def sign_in(client: TestClient, email: str, password: str = TEST_PASSWORD) -> Response:
    """Post credentials to the sign in route, with the shared request id."""
    return client.post(
        LOGIN_PATH, json={"email": email, "password": password}, headers=SHARED_REQUEST_ID
    )


def refresh_cookie_header(response: Response) -> str:
    """Return the one `Set-Cookie` header of a response that names the refresh cookie."""
    headers = [
        value
        for value in response.headers.get_list(SET_COOKIE_HEADER)
        if value.startswith(f"{REFRESH_COOKIE_NAME}=")
    ]
    assert len(headers) == 1, (
        f"Expected exactly one {REFRESH_COOKIE_NAME} cookie on the response and found "
        f"{len(headers)}."
    )
    return headers[0]


def refresh_token_of(response: Response) -> str:
    """Return the refresh token a response set, read out of its `Set-Cookie` header."""
    pair = refresh_cookie_header(response).split(";", 1)[0]
    return pair.split("=", 1)[1]


def present(
    client: TestClient, path: str, token: str | None, headers: dict[str, str] | None = None
) -> Response:
    """Post to a cookie route presenting exactly one refresh token, or none.

    The cookie jar of the client is emptied first, so the request carries the
    token the test names and not whichever one the last response set.
    """
    client.cookies.clear()
    sent = {**SHARED_REQUEST_ID, **(headers or {})}
    if token is not None:
        sent[COOKIE_HEADER] = f"{REFRESH_COOKIE_NAME}={token}"
    return client.post(path, headers=sent)


__all__ = [
    "ALLOWED_ORIGIN",
    "FOREIGN_ORIGIN",
    "INVALID_CREDENTIALS_PROBLEM",
    "LOGIN_PATH",
    "LOGOUT_PATH",
    "ME_PATH",
    "ORIGIN_NOT_ALLOWED_PROBLEM",
    "REFRESH_PATH",
    "SESSION_EXPIRED_PROBLEM",
    "SHARED_REQUEST_ID",
    "TOO_MANY_ATTEMPTS_PROBLEM",
    "UNKNOWN_EMAIL",
    "WRONG_PASSWORD",
    "RefusingVerifier",
    "present",
    "refresh_cookie_header",
    "refresh_token_of",
    "session_client",
    "sign_in",
    "without_bcrypt",
]
